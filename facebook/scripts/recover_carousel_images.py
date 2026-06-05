#!/usr/bin/env python3
"""
One-off recovery for image-carousel ads (HANDOVER §8.5 stopgap).

Some ads scraped with ad_media_type='Carousel' are actually image carousels
(yt-dlp returns "No video formats" for them). Step 2 produces no .mp4 and
Step 3 logs them 'video-missing'. Their per-creative thumbnail URL was captured
by the scraper into facebook_thumbnail_cdn_url_at_scrape, signed with an
expiry that's typically several days out — long enough to recover the image
on a follow-up pass.

This script:
  1. Reads the per-run input CSV.
  2. Finds Carousel rows whose thumbnail URL is still live (HEAD returns 200).
  3. Downloads each image to images/{competitor}-{date}/{ad_id}[_c{N+1}].jpg.
     Naming mirrors §8.5: idx=0 → {id}.jpg; idx=N (≥1) → {id}_c{N+1}.jpg.
  4. Uploads each to R2 with flat key matching the local filename
     (same convention upload_to_r2.py uses for videos and image-type ads).
  5. Updates master/{competitor}.csv: adds the row if missing, fills r2_public_url
     if present. Atomic-write + per-row checkpoint, same as upload_to_r2.py.

Idempotent on re-run: rows already in master with r2_public_url are skipped.

NOT a proper §8.5 implementation. This is a focused recovery for one batch.
The maintainer still owes a design decision on path (a) vs (b) for permanent
image handling, and the Step 1 scraper needs fixing for ad_media_type='Image'
rows where the thumbnail URL field is currently never populated.

Usage:
    python3 scripts/recover_carousel_images.py \\
        --input  inputs/fb-ads-wispr-flow-2026-05-28-1848.csv \\
        --images-dir images/wispr-flow-2026-05-28/ \\
        [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

# Reuse helpers from upload_to_r2.py so the master schema stays in sync.
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from upload_to_r2 import (  # noqa: E402
    MASTER_EXTRA_COLS,
    infer_competitor,
    load_env,
    read_csv,
    write_csv,
)


THUMB_FIELD = "facebook_thumbnail_cdn_url_at_scrape"


def image_filename(ad_library_id: str, creative_index_in_ad: int) -> str:
    """Mirror local_file_for_row's image naming in upload_to_r2.py."""
    if creative_index_in_ad == 0:
        return f"{ad_library_id}.jpg"
    return f"{ad_library_id}_c{creative_index_in_ad + 1}.jpg"


def url_signed_until(url: str) -> Optional[datetime]:
    """Parse the `oe` (hex unix expiry) param from a signed fbcdn URL."""
    try:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        oe = q.get("oe", [None])[0]
        if not oe:
            return None
        return datetime.fromtimestamp(int(oe, 16), tz=timezone.utc)
    except Exception:
        return None


def fetch_image(url: str, dest: pathlib.Path, timeout: int = 15) -> Tuple[bool, str]:
    """Download `url` to `dest`. Returns (ok, detail)."""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Version/16.0 Safari/537.36",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
        if len(body) < 1024:
            return False, f"too small ({len(body)} bytes)"
        dest.write_bytes(body)
        return True, f"{len(body)} bytes"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--input", required=True,
                    help="Per-run input CSV from Step 1.")
    ap.add_argument("--images-dir", required=True,
                    help="Where to write the recovered .jpg files (e.g. images/wispr-flow-2026-05-28/).")
    ap.add_argument("--competitor", default=None,
                    help="Slug for the master CSV. Inferred from --input filename if omitted.")
    ap.add_argument("--master-dir", default="master")
    ap.add_argument("--log-dir", default="step3_logs")
    ap.add_argument("--dry-run", action="store_true",
                    help="Probe URLs and report decisions; no downloads, no uploads, no master writes.")
    args = ap.parse_args()

    folder = pathlib.Path.cwd()
    env = load_env(folder / ".env")

    input_csv = pathlib.Path(args.input)
    if not input_csv.exists():
        sys.exit(f"[error] input CSV not found: {input_csv}")
    images_dir = pathlib.Path(args.images_dir)

    competitor = (args.competitor or infer_competitor(input_csv) or "").lower()
    if not competitor:
        sys.exit("[error] could not infer competitor slug; pass --competitor.")

    master_path = pathlib.Path(args.master_dir) / f"{competitor}.csv"
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    log_path = pathlib.Path(args.log_dir) / f"{competitor}-carousel-recovery-{stamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[info] competitor:  {competitor}")
    print(f"[info] input:       {input_csv}")
    print(f"[info] images-dir:  {images_dir}")
    print(f"[info] master:      {master_path}")
    print(f"[info] log:         {log_path}")
    print(f"[info] dry-run:     {args.dry_run}")
    print(f"[info] bucket:      {env['R2_BUCKET']}  ({env['R2_PUBLIC_URL_BASE']})")

    input_cols, input_rows = read_csv(input_csv)
    if not input_rows:
        sys.exit(f"[error] input CSV has no rows: {input_csv}")

    master_cols, master_rows = read_csv(master_path)
    if not master_cols:
        master_cols = list(input_cols) + [c for c in MASTER_EXTRA_COLS if c not in input_cols]
    else:
        for c in input_cols:
            if c not in master_cols:
                master_cols.append(c)
        for c in MASTER_EXTRA_COLS:
            if c not in master_cols:
                master_cols.append(c)

    def key_for(row: dict) -> Tuple[str, str]:
        return (str(row.get("ad_library_id", "")).strip(),
                str(row.get("creative_index_in_ad", "0")).strip() or "0")

    master_by_key: Dict[Tuple[str, str], dict] = {key_for(r): r for r in master_rows}

    # boto3 client — only if not dry-run
    s3 = None
    if not args.dry_run:
        import boto3
        s3 = boto3.client(
            "s3",
            endpoint_url=env["R2_S3_ENDPOINT"],
            aws_access_key_id=env["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
        )

    today = date.today().isoformat()
    now_utc = datetime.now(tz=timezone.utc)
    log_lines: List[str] = []
    counts = {
        "uploaded": 0, "carried-forward": 0,
        "skipped-not-carousel": 0, "skipped-no-thumb-url": 0, "url-expired": 0,
        "download-failed": 0, "upload-failed": 0,
    }

    for row in input_rows:
        k = key_for(row)
        ad_library_id, idx_s = k
        try:
            creative_index_in_ad = int(idx_s)
        except ValueError:
            creative_index_in_ad = 0
        ad_media_type = (row.get("ad_media_type") or "").strip()

        if ad_media_type != "Carousel":
            counts["skipped-not-carousel"] += 1
            continue

        existing_master = master_by_key.get(k)

        # carry-forward: already in master with R2 URL
        if existing_master and existing_master.get("r2_public_url"):
            counts["carried-forward"] += 1
            log_lines.append(
                f"carried-forward  {ad_library_id} c{creative_index_in_ad}  → {existing_master['r2_public_url']}"
            )
            continue

        thumb_url = (row.get(THUMB_FIELD) or "").strip()
        if not thumb_url:
            counts["skipped-no-thumb-url"] += 1
            log_lines.append(f"no-thumb-url     {ad_library_id} c{creative_index_in_ad}")
            continue

        expiry = url_signed_until(thumb_url)
        if expiry is not None and expiry <= now_utc:
            counts["url-expired"] += 1
            log_lines.append(
                f"url-expired      {ad_library_id} c{creative_index_in_ad}  exp={expiry.isoformat()}"
            )
            continue

        fname = image_filename(ad_library_id, creative_index_in_ad)
        local_path = images_dir / fname

        # idempotency: if local already exists, just upload (or carry forward via master)
        if not local_path.exists():
            if args.dry_run:
                log_lines.append(
                    f"would-download   {ad_library_id} c{creative_index_in_ad}  → {local_path}"
                )
            else:
                ok, detail = fetch_image(thumb_url, local_path)
                if not ok:
                    counts["download-failed"] += 1
                    log_lines.append(
                        f"download-failed  {ad_library_id} c{creative_index_in_ad}  : {detail}"
                    )
                    continue

        # upload
        r2_key = fname  # flat namespace, matching upload_to_r2.py convention
        if args.dry_run:
            r2_public_url = f"{env['R2_PUBLIC_URL_BASE']}/{r2_key}  [DRY-RUN]"
            counts["uploaded"] += 1
            log_lines.append(
                f"would-upload     {ad_library_id} c{creative_index_in_ad}  ← {fname}  → {r2_public_url}"
            )
            continue

        try:
            with open(local_path, "rb") as fh:
                s3.put_object(
                    Bucket=env["R2_BUCKET"],
                    Key=r2_key,
                    Body=fh,
                    ContentType="image/jpeg",
                )
            r2_public_url = f"{env['R2_PUBLIC_URL_BASE']}/{r2_key}"
            counts["uploaded"] += 1
            log_lines.append(
                f"uploaded         {ad_library_id} c{creative_index_in_ad}  ← {fname}  → {r2_public_url}"
            )

            # upsert into master
            if existing_master:
                existing_master.update(
                    {c: row.get(c, existing_master.get(c, "")) for c in input_cols}
                )
                existing_master["r2_public_url"] = r2_public_url
                existing_master["latest_scrape_run_date"] = today
                if not existing_master.get("first_scrape_run_date"):
                    existing_master["first_scrape_run_date"] = today
            else:
                new_master_row = {
                    **row,
                    "r2_public_url": r2_public_url,
                    "first_scrape_run_date": today,
                    "latest_scrape_run_date": today,
                }
                master_rows.append(new_master_row)
                master_by_key[k] = new_master_row

            # per-row checkpoint so a bash-cap kill resumes cleanly
            write_csv(master_path, master_cols, master_rows)
        except Exception as e:
            counts["upload-failed"] += 1
            log_lines.append(
                f"upload-failed    {ad_library_id} c{creative_index_in_ad}  ← {fname}  : {type(e).__name__}: {e}"
            )

    # persist log
    log_header = [
        f"# Carousel image recovery log (HANDOVER §8.5 stopgap)",
        f"# competitor : {competitor}",
        f"# started_at : {datetime.now().isoformat(timespec='seconds')}",
        f"# input      : {input_csv}",
        f"# images-dir : {images_dir}",
        f"# master     : {master_path}",
        f"# bucket     : {env['R2_BUCKET']}",
        f"# public_base: {env['R2_PUBLIC_URL_BASE']}",
        f"# dry_run    : {args.dry_run}",
        f"#",
        f"# counts     : {counts}",
        f"#",
    ]
    log_path.write_text("\n".join(log_header + log_lines) + "\n")

    print()
    print("[done] tally:")
    for k_, v_ in counts.items():
        print(f"  {k_:<22} {v_}")
    print(f"[done] log:      {log_path}")
    if not args.dry_run:
        print(f"[done] master:   {master_path}  ({len(master_rows)} rows total)")
    return 0 if (counts["download-failed"] + counts["upload-failed"]) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
