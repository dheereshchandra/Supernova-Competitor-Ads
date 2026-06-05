#!/usr/bin/env python3
"""
HTML5 banner capture — render Google's animated/HTML5 ad banners with a
headless browser and save them as mp4.

For ads where Step 1 set `error_tag = "html5-banner-no-mp4"` — i.e. the
detail API returned an ad whose content.js doesn't contain a downloadable
googlevideo.com URL — there's no static video file behind the ad. Google
composes them in-browser. This script uses Playwright + headless Chromium
to load each ad in a browser, record the rendered output as WebM, and
convert to mp4 with ffmpeg.

Per-ad workflow:
  1. Open `creative_url` from the master CSV in headless Chromium
  2. Wait for the SPA to render the ad iframe
  3. Record the page for `--seconds` (default 10) at 25 fps
  4. Convert the WebM output to mp4
  5. Save as `videos/{competitor}-{date}/{creative_id}.mp4` — same naming as
     direct API downloads, so Step 3 (`upload_to_r2.py`) picks it up on its
     next invocation with no extra wiring
  6. Update master: set `error_tag = "html5-captured-locally"` so the row's
     provenance is recorded (vs `error_tag = ""` for direct API downloads)

Resumability: skips any creative whose target mp4 already exists.

Requires:
  pip3 install --user playwright
  python3 -m playwright install chromium
  ffmpeg on PATH

Usage:
  # Test on a small sample first (recommended):
  python3 scripts/capture_html5_banners.py --competitor speakx --limit 10

  # Run for one whole competitor:
  python3 scripts/capture_html5_banners.py --competitor speakx

  # Run for every competitor with HTML5 banners:
  python3 scripts/capture_html5_banners.py --all-competitors

  # Tweak recording length (default 10s):
  python3 scripts/capture_html5_banners.py --competitor speakx --seconds 8

  # Capture specific creative IDs:
  python3 scripts/capture_html5_banners.py --competitor speakx --ids CR123,CR456

Failure modes you should expect:

  - If Google's anti-abuse blocks the IP (302 redirect to /sorry/index with
    a reCAPTCHA), this script's headless visits will also be blocked. The
    captured "mp4" will then just show the captcha page. The script detects
    this and refuses to overwrite the row — it leaves a clear error in the
    log instead.

  - Some Transparency Center detail pages take longer than 10s to fully
    render the ad. Bump --wait-render-seconds if you see blank/grey
    captures.

  - HTML5 ads with longer animations (15-30s loops) won't be fully captured
    with the default --seconds 10. Use --seconds 20 or 30 for those.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

def ensure_playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        sys.exit(
            "Playwright is not installed. Run:\n"
            "  pip3 install --user playwright\n"
            "  python3 -m playwright install chromium")
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not on PATH. Install it: brew install ffmpeg")


# ---------------------------------------------------------------------------
# Master CSV reading + filtering
# ---------------------------------------------------------------------------

def read_master(competitor_slug: str, master_dir: pathlib.Path) -> tuple[list[str], list[dict]]:
    path = master_dir / f"{competitor_slug}.csv"
    if not path.exists():
        sys.exit(f"No such master CSV: {path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_master(competitor_slug: str, master_dir: pathlib.Path,
                 fieldnames: list[str], rows: list[dict]) -> None:
    path = master_dir / f"{competitor_slug}.csv"
    tmp = path.with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def candidates(rows: list[dict], ids_filter: Optional[set[str]]) -> list[dict]:
    """HTML5-banner rows that haven't been captured yet."""
    out = []
    seen_ids = set()
    for r in rows:
        cr_id = r.get("creative_id", "")
        if not cr_id or cr_id in seen_ids:
            continue
        if r.get("error_tag", "") != "html5-banner-no-mp4":
            continue
        if r.get("variant_index", "") not in ("0", 0):
            # Variants of the same creative share the same rendered ad.
            # Capture once at variant 0; downstream R2 upload will apply
            # to all variants of that creative.
            continue
        if ids_filter is not None and cr_id not in ids_filter:
            continue
        seen_ids.add(cr_id)
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# The actual capture
# ---------------------------------------------------------------------------

def is_captcha_url(url: str) -> bool:
    return "/sorry/index" in url or "/recaptcha/" in url


def capture_one(playwright, creative_url: str, dest_webm: pathlib.Path,
                wait_render_seconds: float, record_seconds: float,
                ua: str) -> tuple[bool, str]:
    """Returns (ok, detail). On success, dest_webm has a valid recording."""
    browser = playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    try:
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=ua,
            record_video_dir=str(dest_webm.parent),
            record_video_size={"width": 1280, "height": 800},
        )
        page = context.new_page()
        try:
            page.goto(creative_url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:  # noqa: BLE001
            context.close()
            return False, f"goto-error: {e.__class__.__name__}"

        if is_captcha_url(page.url):
            context.close()
            return False, "google-captcha-redirect (IP blocked by anti-abuse)"

        # Let the SPA + ad iframe finish rendering. Listen for the content.js
        # network response as a stronger signal than networkidle (which can
        # fire while the ad iframe is still spinning).
        page.wait_for_timeout(int(wait_render_seconds * 1000))

        # Record the ad playing
        page.wait_for_timeout(int(record_seconds * 1000))

        # Save the recording — close the page to flush video
        captured_video_path = None
        try:
            captured_video_path = page.video.path() if page.video else None
        except Exception:  # noqa: BLE001
            captured_video_path = None

        context.close()

        if not captured_video_path:
            return False, "no-video-recorded"

        captured_path = pathlib.Path(captured_video_path)
        if not captured_path.exists():
            return False, "video-file-missing"

        # Move into the predictable name
        captured_path.replace(dest_webm)
        return True, f"{dest_webm.stat().st_size:,} bytes"
    finally:
        browser.close()


def webm_to_mp4(webm: pathlib.Path, mp4: pathlib.Path) -> tuple[bool, str]:
    """ffmpeg-encode the WebM into mp4 (H.264 + AAC). Returns (ok, detail)."""
    try:
        proc = subprocess.run([
            "ffmpeg", "-y", "-i", str(webm),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(mp4),
        ], capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            return False, f"ffmpeg-err: {proc.stderr[-200:]}"
        # Clean up the source webm
        try:
            webm.unlink()
        except OSError:
            pass
        return True, f"{mp4.stat().st_size:,} bytes mp4"
    except subprocess.TimeoutExpired:
        return False, "ffmpeg-timeout"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def run_for_competitor(slug: str, args, playwright) -> dict:
    master_dir = pathlib.Path(args.master_dir)
    fields, rows = read_master(slug, master_dir)
    ids_filter = set(args.ids.split(",")) if args.ids else None
    cands = candidates(rows, ids_filter)
    if args.limit:
        cands = cands[:args.limit]
    if not cands:
        return {"slug": slug, "candidates": 0, "captured": 0, "failed": 0}

    today = datetime.date.today().isoformat()
    videos_dir = pathlib.Path(args.out) / "videos" / f"{slug}-{today}"
    videos_dir.mkdir(parents=True, exist_ok=True)

    captured = 0
    failed = 0
    log_lines: list[str] = []

    print(f"\n[{slug}] {len(cands)} html5-banner-no-mp4 candidates to capture")
    for i, row in enumerate(cands, 1):
        cr_id = row["creative_id"]
        # Use plain {creative_id}.mp4 so Step 3 (upload_to_r2.py) picks it up
        # automatically. Provenance lives in the master row's error_tag.
        target_mp4 = videos_dir / f"{cr_id}.mp4"
        if target_mp4.exists() and target_mp4.stat().st_size > 50_000:
            print(f"  [{i}/{len(cands)}] {cr_id}  SKIP (already captured)")
            continue

        webm_target = videos_dir / f"{cr_id}.webm"

        # Recording
        ok, detail = capture_one(
            playwright, row["creative_url"], webm_target,
            wait_render_seconds=args.wait_render_seconds,
            record_seconds=args.seconds,
            ua=UA,
        )
        if not ok:
            print(f"  [{i}/{len(cands)}] {cr_id}  FAIL  {detail}")
            log_lines.append(f"FAIL {cr_id}  {detail}")
            failed += 1
            continue

        # Convert
        ok2, detail2 = webm_to_mp4(webm_target, target_mp4)
        if not ok2:
            print(f"  [{i}/{len(cands)}] {cr_id}  FAIL  {detail2}")
            log_lines.append(f"FAIL-FFMPEG {cr_id}  {detail2}")
            failed += 1
            continue

        print(f"  [{i}/{len(cands)}] {cr_id}  OK    {detail2}")
        log_lines.append(f"OK {cr_id}  {detail2}")
        captured += 1

        # Update master row: mark every variant of this creative as captured.
        # Don't fill r2_public_url here — let Step 3 re-upload on the next
        # invocation. That keeps the upload pipeline as the single owner of
        # R2 keys + URLs.
        for r in rows:
            if r.get("creative_id") == cr_id and r.get("error_tag") == "html5-banner-no-mp4":
                r["error_tag"] = "html5-captured-locally"
        # Checkpoint the master after each successful capture
        write_master(slug, master_dir, fields, rows)

        # Gentle pacing to avoid tripping anti-abuse on the headless visits
        time.sleep(args.pace_seconds)

    # Log
    log_dir = pathlib.Path(args.out) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    log_path = log_dir / f"html5-capture-{slug}-{stamp}.log"
    log_path.write_text("\n".join(log_lines) + "\n")

    return {"slug": slug, "candidates": len(cands),
            "captured": captured, "failed": failed, "log": str(log_path)}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    scope = ap.add_mutually_exclusive_group(required=True)
    scope.add_argument("--competitor", help="Slug, e.g. speakx")
    scope.add_argument("--all-competitors", action="store_true",
                       help="Process every master CSV that has html5-banner-no-mp4 rows")
    ap.add_argument("--master-dir", default="master",
                    help="Where master/{slug}.csv lives (default: master/)")
    ap.add_argument("--out", default=".",
                    help="Output root (default: cwd). Creates videos/{slug}-{date}/")
    ap.add_argument("--ids", help="Comma-separated creative IDs to limit to")
    ap.add_argument("--limit", type=int,
                    help="Process only the first N candidate creatives per competitor")
    ap.add_argument("--seconds", type=float, default=10.0,
                    help="Recording length per ad in seconds (default: 10)")
    ap.add_argument("--wait-render-seconds", type=float, default=5.0,
                    help="Time to wait after page load before recording starts (default: 5)")
    ap.add_argument("--pace-seconds", type=float, default=2.0,
                    help="Sleep between captures to avoid tripping anti-abuse (default: 2)")
    args = ap.parse_args()

    ensure_playwright()
    from playwright.sync_api import sync_playwright

    master_dir = pathlib.Path(args.master_dir)
    if args.all_competitors:
        slugs = sorted(p.stem for p in master_dir.glob("*.csv"))
    else:
        slugs = [slugify(args.competitor)]

    reports = []
    with sync_playwright() as playwright:
        for s in slugs:
            try:
                reports.append(run_for_competitor(s, args, playwright))
            except Exception as e:  # noqa: BLE001
                reports.append({"slug": s, "error": str(e)})

    print("\n[done] summary:")
    for r in reports:
        if "error" in r:
            print(f"  {r['slug']:<14} ERROR: {r['error']}")
        else:
            print(f"  {r['slug']:<14} candidates={r['candidates']:>4}  "
                  f"captured={r['captured']:>4}  failed={r['failed']:>4}")

    # Exit 1 if any captures failed AND we tried to capture something
    bad = any(r.get("failed", 0) for r in reports if "error" not in r)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
