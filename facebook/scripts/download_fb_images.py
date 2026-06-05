#!/usr/bin/env python3
"""
Download image creatives from the Facebook Ad Library in bulk (MVP).

Companion to download_fb_ads.py — that one handles video; this one handles
ad_media_type=Image rows. See HANDOVER §8.5 for the design context.

How it differs from the video downloader
----------------------------------------
The Ad Library is heavily JavaScript-rendered, so a plain HTTP fetch of the
ad page does not return the image URL — you'd need a real browser to
re-resolve a fresh signed image URL. The scraper (Step 1) already captures
the image URL into the `facebook_thumbnail_cdn_url_at_scrape` column at the
moment of scrape, when it's fresh. That signed URL is bound to a 600x600
thumbnail and is valid for ~3–5 days.

So this script's only job is: read that column for Image-type rows, fetch the
image, save it locally with the same naming convention as videos.

Constraints
-----------
- Only works while the scrape's captured thumbnail URL is still inside its
  signature expiry window (`facebook_cdn_url_expiry_at_scrape`). If you wait
  too long after scraping, you'll get HTTP 403 and need to re-scrape.
- Only the 600x600 thumbnail is fetchable. Stripping the `stp=` query param
  to get the full-resolution image breaks the signature.

Output naming (mirrors the video convention from download_fb_ads.py / §8.5)
---------------------------------------------------------------------------
    images/{competitor}-{date}/
        {ad_library_id}.jpg          (creative_index_in_ad = 0)
        {ad_library_id}_c2.jpg       (creative_index_in_ad = 1)
        {ad_library_id}_c3.jpg       (creative_index_in_ad = 2)
        download_summary.csv         per-row outcome
        failed_ads.txt               (only if anything failed)

Idempotency
-----------
Re-running is safe: any image whose local file already exists is skipped
before any network call. This is the same resumability story as the video
downloader.

Usage
-----
    python3 scripts/download_fb_images.py inputs/fb-ads-memrise-2026-05-28-0833.csv \\
        --out images/memrise-2026-05-28/

The script is a no-op for non-Image rows.
"""
from __future__ import annotations
import argparse
import csv
import pathlib
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Optional


UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def local_image_path(out_dir: pathlib.Path, ad_library_id: str, creative_index: int) -> pathlib.Path:
    """Match the convention in upload_to_r2.py and HANDOVER §8.5."""
    if creative_index == 0:
        fname = f"{ad_library_id}.jpg"
    else:
        fname = f"{ad_library_id}_c{creative_index + 1}.jpg"
    return out_dir / fname


def fetch_to_file(url: str, dest: pathlib.Path, timeout: int = 30) -> int:
    """Fetch url → dest atomically. Returns bytes written."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r, tmp.open("wb") as fh:
        data = r.read()
        fh.write(data)
    tmp.replace(dest)
    return len(data)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("input", help="Per-run input CSV from Step 1.")
    ap.add_argument("--out", required=True, help="Output directory for images.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report which rows would be fetched, write nothing.")
    args = ap.parse_args()

    src = pathlib.Path(args.input)
    if not src.exists():
        sys.exit(f"[error] input CSV not found: {src}")

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    with src.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        sys.exit(f"[error] input CSV has no rows: {src}")

    image_rows = [r for r in rows if (r.get("ad_media_type") or "").strip() == "Image"]

    print(f"[info] input    : {src}")
    print(f"[info] out      : {out_dir}")
    print(f"[info] rows     : {len(rows)} total, {len(image_rows)} image-type")
    print(f"[info] dry-run  : {args.dry_run}")

    if not image_rows:
        print("[done] no image rows to fetch.")
        return 0

    counts = {"fetched": 0, "skipped": 0, "would-fetch": 0,
              "no-url": 0, "expired-or-blocked": 0, "error": 0}
    summary_rows = []
    failed: list[str] = []

    for row in image_rows:
        ad_library_id = (row.get("ad_library_id") or "").strip()
        try:
            creative_index = int((row.get("creative_index_in_ad") or "0").strip())
        except ValueError:
            creative_index = 0
        url = (row.get("facebook_thumbnail_cdn_url_at_scrape") or "").strip()
        dest = local_image_path(out_dir, ad_library_id, creative_index)

        rec = {
            "ad_library_id": ad_library_id,
            "creative_index_in_ad": creative_index,
            "local_path": str(dest),
            "status": "",
            "bytes": "",
            "detail": "",
        }

        if not ad_library_id.isdigit():
            counts["no-url"] += 1
            rec["status"] = "no-creative"
            rec["detail"] = "blank/invalid ad_library_id"
            summary_rows.append(rec)
            print(f"  no-creative      {ad_library_id!r}  (skipping)")
            continue

        if not url:
            counts["no-url"] += 1
            rec["status"] = "no-url"
            rec["detail"] = "facebook_thumbnail_cdn_url_at_scrape is blank"
            summary_rows.append(rec)
            failed.append(ad_library_id)
            print(f"  no-url           {ad_library_id}  (no thumbnail URL in CSV)")
            continue

        if dest.exists():
            counts["skipped"] += 1
            rec["status"] = "skipped-exists"
            rec["bytes"] = dest.stat().st_size
            summary_rows.append(rec)
            print(f"  skipped-exists   {ad_library_id} c{creative_index}  ← {dest.name} ({dest.stat().st_size} B)")
            continue

        if args.dry_run:
            counts["would-fetch"] += 1
            rec["status"] = "would-fetch"
            rec["detail"] = "dry-run"
            summary_rows.append(rec)
            print(f"  would-fetch      {ad_library_id} c{creative_index}  → {dest.name}")
            continue

        try:
            n = fetch_to_file(url, dest)
            counts["fetched"] += 1
            rec["status"] = "fetched"
            rec["bytes"] = n
            summary_rows.append(rec)
            print(f"  fetched          {ad_library_id} c{creative_index}  → {dest.name} ({n} B)")
        except urllib.error.HTTPError as e:
            # 403 typically means the signed URL has expired
            if e.code == 403:
                counts["expired-or-blocked"] += 1
                rec["status"] = "expired-or-blocked"
                rec["detail"] = f"HTTP 403 — captured URL likely expired (expiry={row.get('facebook_cdn_url_expiry_at_scrape','?')})"
            else:
                counts["error"] += 1
                rec["status"] = "error"
                rec["detail"] = f"HTTP {e.code}: {e.reason}"
            summary_rows.append(rec)
            failed.append(ad_library_id)
            print(f"  {rec['status']:<16} {ad_library_id} c{creative_index}  : {rec['detail']}")
        except Exception as e:
            counts["error"] += 1
            rec["status"] = "error"
            rec["detail"] = f"{type(e).__name__}: {e}"
            summary_rows.append(rec)
            failed.append(ad_library_id)
            print(f"  error            {ad_library_id} c{creative_index}  : {rec['detail']}")

    # write summary CSV
    summary_path = out_dir / "download_summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["ad_library_id", "creative_index_in_ad",
                                           "local_path", "status", "bytes", "detail"])
        w.writeheader()
        for r in summary_rows:
            w.writerow(r)

    if failed:
        (out_dir / "failed_ads.txt").write_text("\n".join(failed) + "\n")

    print()
    print("[done] tally:")
    for k_, v_ in counts.items():
        print(f"  {k_:<20} {v_}")
    print(f"[done] summary: {summary_path}")
    if failed:
        print(f"[done] failed:  {out_dir / 'failed_ads.txt'}")

    # Exit nonzero only on hard errors, not on expired URLs (those are an
    # expected condition; the operator needs to know but the script shouldn't
    # crash the pipeline).
    return 1 if counts["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
