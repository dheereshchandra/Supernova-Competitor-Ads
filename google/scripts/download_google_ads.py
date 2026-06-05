#!/usr/bin/env python3
"""
Step 2 — YouTube metadata enrichment for the Step 1 CSV.

Reads the per-run CSV produced by `scripts/scrape_google_ads.py` (Step 1)
and runs yt-dlp against every `youtube_video_url` to produce a
`{stem}.info.json` sidecar next to the existing `.mp4`. The sidecar carries
YouTube title, description, channel/uploader, and duration — Step 3
(`upload_to_r2.py`) reads them into the master CSV's `youtube_video_*` columns.

Step 1's mp4 and image downloads have already happened by the time this
script runs, so this stage is almost entirely a metadata pass. For any row
where the .mp4 is missing (rare — usually means Step 1 couldn't extract a
googlevideo URL for that variant), the script attempts a fresh yt-dlp
download from `youtube_video_url`. Image rows are no-ops here: Step 1
downloaded the .jpg/.png directly and there's no equivalent metadata API.

Branching per row based on `creative_format`:

  YouTubeVideo  → yt-dlp .info.json (or full download if mp4 missing)
                → videos/{competitor}-{date}/{creative_id}.mp4 + .info.json
  Image         → no-op (Step 1 already downloaded the image)
  Text          → no-op (asset is the headline+description text in the CSV)
  Shopping/Maps → best-effort: if image_url_at_scrape is populated, treat as Image; else skip
  Unknown       → log and skip

The script is **resumable**: any file already on disk + already-sidecar'd is
pre-skipped before the network call.

Usage:
    python3 scripts/download_google_ads.py \\
        "inputs/g-ads-zinglish-2026-05-27.csv" \\
        --videos-out "./videos/zinglish-2026-05-27/" \\
        --images-out "./images/zinglish-2026-05-27/" \\
        --batch-size 600

`--batch-size 600` is the standard for this pipeline. The FB-style default of
5 is meant to throttle full yt-dlp downloads; here we're mostly metadata-only
and want one pass to finish a 500-row CSV.

Outputs:
    videos/{competitor}-{date}/{creative_id}.info.json   — yt-dlp metadata
    {videos-out}/download_summary.csv                   — per-row outcome
    {videos-out}/failed_ads.txt                         — IDs that failed (only if any)

Note: a row tagged `youtube-id-missing` is expected behaviour, not an error
— it means the source ad is an HTML5 banner with no public YouTube video
underneath (no `youtube_video_url` to feed yt-dlp).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# yt-dlp discovery
# ---------------------------------------------------------------------------

def find_ytdlp() -> Optional[list[str]]:
    """Locate a usable yt-dlp invocation. Returns the command as a list or None."""
    # Prefer the binary on PATH
    p = shutil.which("yt-dlp")
    if p:
        return [p]
    # Common pip --user install location on macOS Homebrew Python
    candidates = [
        pathlib.Path.home() / "Library" / "Python" / "3.13" / "bin" / "yt-dlp",
        pathlib.Path.home() / "Library" / "Python" / "3.12" / "bin" / "yt-dlp",
        pathlib.Path.home() / "Library" / "Python" / "3.11" / "bin" / "yt-dlp",
        pathlib.Path.home() / ".local" / "bin" / "yt-dlp",
    ]
    for c in candidates:
        if c.exists():
            return [str(c)]
    # Fallback to module invocation
    try:
        subprocess.run([sys.executable, "-m", "yt_dlp", "--version"],
                        capture_output=True, check=True, timeout=5)
        return [sys.executable, "-m", "yt_dlp"]
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def read_csv(path: pathlib.Path) -> Tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames or []), list(r)


def write_summary(path: pathlib.Path, rows: list[dict]) -> None:
    if not rows:
        return
    fieldnames = ["creative_id", "creative_format", "status", "local_path", "detail"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ---------------------------------------------------------------------------
# YouTube download
# ---------------------------------------------------------------------------

def download_youtube(url: str, out_path: pathlib.Path, ytdlp_cmd: list[str]) -> Tuple[bool, str]:
    """Download a YouTube video to out_path AND write a {stem}.info.json sidecar with
    title / description / uploader / duration etc. Step 3 reads the .info.json to
    populate the master CSV's youtube_video_* columns.
    Returns (ok, detail). If the .mp4 is already on disk but .info.json is missing,
    fetches metadata via --skip-download so the sidecar still gets written.
    """
    info_path = out_path.with_suffix(".info.json")

    # Already-on-disk fast path
    if out_path.exists() and out_path.stat().st_size > 10_000:
        if not info_path.exists():
            # Try to fetch metadata only — best-effort, doesn't fail the row if it errors
            fetch_info_json_only(url, info_path, ytdlp_cmd)
        return True, "skipped-already-on-disk"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # --write-info-json: yt-dlp emits {stem}.info.json with full metadata
    # --merge-output-format mp4: one merged .mp4 output
    # -o template: force the .mp4 + .info.json stems to be exactly out_path's stem
    template = str(out_path.with_suffix("")) + ".%(ext)s"
    cmd = ytdlp_cmd + [
        "--no-progress",
        "--no-warnings",
        "--quiet",
        "--no-playlist",
        "--restrict-filenames",
        "--write-info-json",
        "-f", "best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", template,
        url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip().splitlines()
            last = err[-1] if err else "unknown error"
            if "Video unavailable" in (r.stderr or "") or "404" in (r.stderr or ""):
                return False, "youtube-404"
            if "age" in (r.stderr or "").lower() or "restricted" in (r.stderr or "").lower():
                return False, "youtube-restricted"
            if "region" in (r.stderr or "").lower():
                return False, "youtube-region-blocked"
            return False, f"yt-dlp-error: {last[:200]}"
    except subprocess.TimeoutExpired:
        return False, "yt-dlp-timeout"
    except FileNotFoundError:
        return False, "yt-dlp-not-found"

    if out_path.exists() and out_path.stat().st_size > 10_000:
        return True, "downloaded"
    stem = out_path.stem
    for cand in out_path.parent.glob(f"{stem}.*"):
        if cand.suffix.lower() in (".mp4", ".mkv", ".webm"):
            if cand != out_path:
                cand.rename(out_path)
            return True, "downloaded"
    return False, "yt-dlp-no-output"


def fetch_info_json_only(url: str, out_info_path: pathlib.Path,
                          ytdlp_cmd: list[str]) -> bool:
    """Fetch only the JSON metadata for a YouTube URL (no video download).
    Used for already-downloaded videos whose .info.json sidecar is missing.
    Returns True on success."""
    if out_info_path.exists() and out_info_path.stat().st_size > 100:
        return True
    out_info_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ytdlp_cmd + [
        "--no-warnings",
        "--quiet",
        "--no-playlist",
        "--skip-download",
        "--dump-single-json",
        url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return False
        # Sanity-check that the output parses as JSON before writing
        try:
            import json as _json
            _json.loads(r.stdout)
        except Exception:
            return False
        out_info_path.write_text(r.stdout)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


# ---------------------------------------------------------------------------
# Image download
# ---------------------------------------------------------------------------

def download_image(url: str, out_dir: pathlib.Path, creative_id: str,
                    variant_suffix: str = "") -> Tuple[bool, str, Optional[pathlib.Path]]:
    """Download an image to out_dir/{creative_id}{variant_suffix}.{ext}. Returns (ok, detail, path)."""
    if not url:
        return False, "image-url-missing", None

    parsed = urllib.parse.urlparse(url)
    pathname = parsed.path.lower()
    ext = ".jpg"
    if pathname.endswith(".png"):
        ext = ".png"
    elif pathname.endswith(".gif"):
        ext = ".gif"
    elif pathname.endswith(".webp"):
        ext = ".webp"

    out_path = out_dir / f"{creative_id}{variant_suffix}{ext}"
    if out_path.exists() and out_path.stat().st_size > 1_000:
        return True, "skipped-already-on-disk", out_path

    out_dir.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "image/*,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if len(data) < 200:
            return False, "image-too-small", None
        out_path.write_bytes(data)
        return True, "downloaded", out_path
    except urllib.request.HTTPError as e:
        if e.code == 403:
            return False, "image-expired-403", None
        if e.code == 404:
            return False, "image-404", None
        return False, f"image-http-{e.code}", None
    except (urllib.request.URLError, TimeoutError, OSError) as e:
        return False, f"image-error: {type(e).__name__}: {str(e)[:120]}", None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("input_csv", help="Step 1 CSV (g-ads-{competitor}-{date}.csv).")
    ap.add_argument("--videos-out", required=True, help="Directory for downloaded YouTube .mp4 files.")
    ap.add_argument("--images-out", required=True, help="Directory for downloaded display images.")
    ap.add_argument("--batch-size", type=int, default=5,
                    help="Max items to process per script invocation (Cowork bash-cap aware).")
    ap.add_argument("--limit", type=int, default=None, help="Only process the first N rows.")
    ap.add_argument("--offset", type=int, default=0, help="Skip the first N rows.")
    ap.add_argument("--summary", default=None,
                    help="Where to write the per-row summary CSV. Default: {videos-out}/download_summary.csv")
    args = ap.parse_args()

    input_csv = pathlib.Path(args.input_csv)
    if not input_csv.exists():
        sys.exit(f"[error] input CSV not found: {input_csv}")

    videos_out = pathlib.Path(args.videos_out)
    images_out = pathlib.Path(args.images_out)
    videos_out.mkdir(parents=True, exist_ok=True)
    images_out.mkdir(parents=True, exist_ok=True)

    summary_path = pathlib.Path(args.summary) if args.summary else (videos_out / "download_summary.csv")
    failed_path = videos_out / "failed_ads.txt"

    print(f"[info] input:        {input_csv}")
    print(f"[info] videos-out:   {videos_out}")
    print(f"[info] images-out:   {images_out}")
    print(f"[info] batch-size:   {args.batch_size}")
    print(f"[info] summary:      {summary_path}")

    cols, rows = read_csv(input_csv)
    print(f"[info] csv rows:     {len(rows)}")

    # Required columns
    required = {"creative_id", "creative_format"}
    missing_cols = required - set(cols)
    if missing_cols:
        sys.exit(f"[error] input CSV missing required columns: {sorted(missing_cols)}")

    # Slice via offset/limit
    if args.offset:
        rows = rows[args.offset:]
    if args.limit:
        rows = rows[:args.limit]

    ytdlp = find_ytdlp()
    if ytdlp is None:
        print("[warn] yt-dlp not found. YouTube downloads will fail. Install with:")
        print("       python3 -m pip install --upgrade --user yt-dlp")
    else:
        print(f"[info] yt-dlp:       {' '.join(ytdlp)}")

    # Pre-scan: how much of this batch is already done?
    pending = []
    summary_rows = []
    skipped_already = 0

    def variant_suffix(vi: int) -> str:
        return "" if vi == 0 else f"_v{vi + 1}"

    for row in rows:
        creative_id = (row.get("creative_id") or "").strip()
        fmt = (row.get("creative_format") or "").strip()
        try:
            vi = int((row.get("variant_index") or "0").strip() or "0")
        except (ValueError, AttributeError):
            vi = 0
        suffix = variant_suffix(vi)

        if not creative_id:
            summary_rows.append({"creative_id": "", "creative_format": fmt,
                                  "status": "no-creative-id", "local_path": "", "detail": ""})
            continue

        if fmt == "YouTubeVideo":
            out = videos_out / f"{creative_id}{suffix}.mp4"
            if out.exists() and out.stat().st_size > 10_000:
                # Backfill missing .info.json sidecar so Step 3 can still enrich master CSV
                info_path = out.with_suffix(".info.json")
                if ytdlp is not None and not info_path.exists():
                    url = (row.get("youtube_video_url") or "").strip()
                    if not url:
                        vid = (row.get("youtube_video_id") or "").strip()
                        if vid:
                            url = f"https://www.youtube.com/watch?v={vid}"
                    if url:
                        fetch_info_json_only(url, info_path, ytdlp)
                summary_rows.append({"creative_id": creative_id, "creative_format": fmt,
                                      "status": "skipped-already-on-disk",
                                      "local_path": str(out), "detail": f"variant_index={vi}"})
                skipped_already += 1
                continue
            pending.append(("yt", creative_id, fmt, row, out))
            continue

        if fmt == "Image" or (fmt in ("Shopping", "Maps") and (row.get("image_url_at_scrape") or "").strip()):
            existing = None
            for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                cand = images_out / f"{creative_id}{suffix}{ext}"
                if cand.exists() and cand.stat().st_size > 1_000:
                    existing = cand
                    break
            if existing:
                summary_rows.append({"creative_id": creative_id, "creative_format": fmt,
                                      "status": "skipped-already-on-disk",
                                      "local_path": str(existing), "detail": f"variant_index={vi}"})
                skipped_already += 1
                continue
            # Pass the variant suffix down via the row by reference (download_image reads creative_id only)
            row["_variant_suffix"] = suffix
            pending.append(("img", creative_id, fmt, row, images_out))
            continue

        if fmt == "Text":
            summary_rows.append({"creative_id": creative_id, "creative_format": fmt,
                                  "status": "text-no-asset", "local_path": "",
                                  "detail": "Text format — no media to download; analysis uses headline+description."})
            continue

        if fmt in ("Shopping", "Maps"):
            summary_rows.append({"creative_id": creative_id, "creative_format": fmt,
                                  "status": "unsupported-no-asset", "local_path": "",
                                  "detail": "No asset URL captured by scraper."})
            continue

        summary_rows.append({"creative_id": creative_id, "creative_format": fmt,
                              "status": "unknown-format", "local_path": "",
                              "detail": f"creative_format = {fmt!r}"})

    print(f"[info] already on disk: {skipped_already}")
    print(f"[info] pending:         {len(pending)}")

    # Process the batch
    failed_ids: list[str] = []
    counts = {"downloaded-video": 0, "downloaded-image": 0,
              "youtube-404": 0, "youtube-restricted": 0, "youtube-region-blocked": 0,
              "image-expired-403": 0, "image-url-missing": 0,
              "error": 0}

    processed = 0
    for kind, creative_id, fmt, row, out in pending:
        if processed >= args.batch_size and args.batch_size > 0:
            summary_rows.append({"creative_id": creative_id, "creative_format": fmt,
                                  "status": "deferred-batch-cap", "local_path": "",
                                  "detail": "Re-run the script to pick this up."})
            continue
        processed += 1
        print(f"[{processed:>3}/{len(pending)}] {fmt:<14} {creative_id}", end=" ", flush=True)

        if kind == "yt":
            if ytdlp is None:
                summary_rows.append({"creative_id": creative_id, "creative_format": fmt,
                                      "status": "error", "local_path": "",
                                      "detail": "yt-dlp not installed in sandbox"})
                counts["error"] += 1
                failed_ids.append(creative_id)
                print("→ yt-dlp not installed")
                continue
            url = (row.get("youtube_video_url") or "").strip()
            if not url:
                video_id = (row.get("youtube_video_id") or "").strip()
                if video_id:
                    url = f"https://www.youtube.com/watch?v={video_id}"
            if not url:
                summary_rows.append({"creative_id": creative_id, "creative_format": fmt,
                                      "status": "youtube-id-missing", "local_path": "",
                                      "detail": "No youtube_video_url or youtube_video_id in CSV row"})
                failed_ids.append(creative_id)
                print("→ no youtube URL")
                continue

            ok, detail = download_youtube(url, out, ytdlp)
            if ok:
                counts["downloaded-video"] += 1
                summary_rows.append({"creative_id": creative_id, "creative_format": fmt,
                                      "status": "downloaded-video", "local_path": str(out),
                                      "detail": detail})
                print("→ ok")
            else:
                if detail in counts:
                    counts[detail] += 1
                else:
                    counts["error"] += 1
                summary_rows.append({"creative_id": creative_id, "creative_format": fmt,
                                      "status": "error" if "error" in detail or "yt-dlp" in detail else detail,
                                      "local_path": "", "detail": detail})
                failed_ids.append(creative_id)
                print(f"→ {detail[:60]}")
            continue

        if kind == "img":
            url = (row.get("image_url_at_scrape") or "").strip()
            v_suffix = row.get("_variant_suffix", "") or ""
            ok, detail, path = download_image(url, out, creative_id, v_suffix)
            if ok:
                counts["downloaded-image"] += 1
                summary_rows.append({"creative_id": creative_id, "creative_format": fmt,
                                      "status": "downloaded-image",
                                      "local_path": str(path) if path else "",
                                      "detail": detail})
                print("→ ok")
            else:
                if detail in counts:
                    counts[detail] += 1
                else:
                    counts["error"] += 1
                summary_rows.append({"creative_id": creative_id, "creative_format": fmt,
                                      "status": detail, "local_path": "", "detail": detail})
                failed_ids.append(creative_id)
                print(f"→ {detail[:60]}")
            continue

    write_summary(summary_path, summary_rows)
    if failed_ids:
        failed_path.write_text("\n".join(failed_ids) + "\n")

    # Final tally
    print()
    print("[done] tally:")
    for k, v in counts.items():
        if v:
            print(f"  {k:<28} {v}")
    still_pending = sum(1 for r in summary_rows if r["status"] == "deferred-batch-cap")
    print(f"  {'already-on-disk':<28} {skipped_already}")
    if still_pending:
        print(f"  {'deferred-batch-cap':<28} {still_pending}  (re-run to process these)")
    print(f"[done] {len(rows)} rows total processed, {still_pending} still pending")
    print(f"[done] summary: {summary_path}")
    if failed_ids:
        print(f"[done] failed:  {failed_path}  ({len(failed_ids)} ids)")

    # Exit code 0 if all rows were processed or skipped successfully; 1 if items still pending or hard errors
    return 0 if still_pending == 0 and counts["error"] == 0 else (2 if still_pending else 1)


if __name__ == "__main__":
    raise SystemExit(main())
