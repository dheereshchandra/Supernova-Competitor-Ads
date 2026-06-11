#!/usr/bin/env python3
"""
Step 3 — Upload competitor ad videos (and images, when implemented) to Cloudflare R2.

Designed to be run after Step 2 (download_fb_ads.py). Reads the per-run input CSV from
Step 1, looks up each (library_id, creative_index) in the per-competitor master CSV,
and decides per row whether to upload-and-record or carry-forward an existing R2 URL.

See HANDOVER.md §8 for the full design.

Usage:
    python3 scripts/upload_to_r2.py \
        --input  inputs/fb-ads-zinglish-2026-05-26-0728.csv \
        --videos videos/zinglish-2026-05-26/ \
        [--competitor zinglish]   # auto-inferred from input filename if omitted
        [--dry-run]               # report what would happen, upload nothing

Outputs (idempotent on re-run, resumable):
    master/{competitor}.csv                       — rolling per-competitor truth
    inputs/{input-stem}_enriched.csv              — same rows as input + r2_url filled in
    step3_logs/{competitor}-{YYYY-MM-DD-HHMM}.log — per-row outcome
"""
from __future__ import annotations

import argparse
import csv
import os
import pathlib
import re
import sys
from datetime import date, datetime
from typing import Dict, Iterable, Optional, Tuple

# -------- env loading (no external dependency) --------

def load_env(env_path: pathlib.Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not env_path.exists():
        sys.exit(f"[error] .env not found at {env_path}. See HANDOVER §8.2.")
    for line in env_path.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    required = ["R2_S3_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                "R2_BUCKET", "R2_PUBLIC_URL_BASE"]
    missing = [k for k in required if not env.get(k)]
    if missing:
        sys.exit(f"[error] .env missing required keys: {', '.join(missing)}")
    return env


# -------- CSV helpers --------

MASTER_EXTRA_COLS = [
    # page_rank — per-page rank (restarts at 1 per facebook_page_id); added 2026-06.
    # Listed here so older input CSVs that predate it still yield a master with the column.
    "page_rank",
    "r2_public_url",
    "first_scrape_run_date",
    "latest_scrape_run_date",
    # Step 4 (fb-ads-video-analysis) columns — populated later by Step 4.
    # Listed here so Step 3 preserves them across runs and the schema is stable.
    "competitor_analysis_docx_r2_url",
    "supernova_rewrite_docx_r2_url",
    # Step 4 image-URL columns (HANDOVER §9.7).
    # Each is a JSON array of R2 public URLs in scene order. Populated by
    # scripts/step4_upload_images.py and propagated by step4_upload_and_update.py.
    # See r2_utils.orig_frame_key / gen_panel_key / char_sheet_key for the
    # key naming convention these URLs follow.
    "orig_frame_urls",
    "gen_panel_urls",
    "char_sheet_urls",
]


def read_csv(path: pathlib.Path) -> Tuple[list, list]:
    if not path.exists():
        return [], []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames or []), list(r)


def write_csv(path: pathlib.Path, fieldnames: list, rows: list) -> None:
    """Atomic write: write to .tmp then rename. Crash-safe under bash-cap kills.

    Without this, a SIGTERM/SIGKILL mid-write would leave a partially-written
    CSV at `path` and on the next run we'd silently lose hundreds of master
    rows (the in-memory list is rebuilt from disk, so any half-written file
    becomes the new ground truth). The atomic rename guarantees that `path`
    is either the previous good state or the new complete state, never
    a half-written hybrid.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
        fh.flush()
        import os
        os.fsync(fh.fileno())
    tmp.replace(path)  # atomic on POSIX


# -------- file resolution: CSV row → local file on disk --------

def _int0(x) -> int:
    try:
        return int(str(x or "0").strip() or "0")
    except (ValueError, TypeError):
        return 0


def media_name(ad_id: str, version_index, creative_index, ext: str,
               v0_creative_prefix: str) -> str:
    """Canonical local/R2 media filename for a (ad, version, creative). MUST match
    download_fb_ads.py, rehydrate.py and transcribe_tag.py.

      version 0  → backward-compatible legacy scheme (so existing masters/R2 keep
                   working): creative 0 → {id}{ext}; creative N≥1 → {id}{prefix}{N+1}{ext}
                   (prefix is "_v" for video, "_c" for image — the pre-v2.3 conventions).
      version V≥1 → {id}_ver{V}_c{C}{ext}  (version-expansion; one file per version+creative).
    """
    v, c = _int0(version_index), _int0(creative_index)
    if v <= 0:
        return f"{ad_id}{ext}" if c == 0 else f"{ad_id}{v0_creative_prefix}{c + 1}{ext}"
    return f"{ad_id}_ver{v}_c{c}{ext}"


def local_file_for_row(row: dict, videos_dir: pathlib.Path,
                       images_dir: Optional[pathlib.Path] = None) -> Tuple[Optional[pathlib.Path], str]:
    """
    Decide which file on disk corresponds to this CSV row.

    Returns (path_or_None, kind) where kind is one of:
        "video"          — found a .mp4 to upload
        "video-missing"  — expected a .mp4 but it isn't on disk
        "image"          — found a .jpg to upload (HANDOVER §8.5 MVP)
        "image-pending"  — Image-type ad, no local .jpg found (image fetcher not run yet,
                           or thumbnail URL expired before fetch)
        "no-creative"    — ad_library_id missing or other parse failure
    """
    ad_library_id = (row.get("ad_library_id") or "").strip()
    if not ad_library_id or not ad_library_id.isdigit():
        return None, "no-creative"

    ad_media_type = (row.get("ad_media_type") or "").strip()
    creative_index_in_ad = _int0(row.get("creative_index_in_ad"))
    version_index = _int0(row.get("version_index"))  # version-expansion (v2.3); blank → 0

    # Image-only ads: look for a local .jpg under images_dir before falling through
    # to image-pending. Naming via media_name() (version-aware; v0 keeps {id}.jpg /
    # {id}_c{N+1}.jpg, vN≥1 → {id}_ver{V}_c{C}.jpg).
    if ad_media_type == "Image":
        if images_dir is not None:
            img_fname = media_name(ad_library_id, version_index, creative_index_in_ad,
                                   ".jpg", "_c")
            img_candidate = images_dir / img_fname
            if img_candidate.exists():
                return img_candidate, "image"
        return None, "image-pending"

    # Video: same filename convention Step 2 (download_fb_ads.py) writes — version-aware.
    #   v0: creative 0 → {id}.mp4, creative N → {id}_v{N+1}.mp4 ; vN≥1 → {id}_ver{V}_c{C}.mp4
    fname = media_name(ad_library_id, version_index, creative_index_in_ad, ".mp4", "_v")
    candidate = videos_dir / fname

    if candidate.exists():
        return candidate, "video"

    return None, "video-missing"


# -------- competitor slug inference --------

INPUT_NAME_RE = re.compile(r"^fb-ads-(?P<slug>[a-z0-9-]+)-\d{4}-\d{2}-\d{2}(-\d{4})?\.csv$", re.I)


def infer_competitor(path: pathlib.Path) -> Optional[str]:
    m = INPUT_NAME_RE.match(path.name)
    return m.group("slug").lower() if m else None


# -------- main --------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="Per-run input CSV from Step 1 (or its enriched copy).")
    ap.add_argument("--videos", required=True, help="Directory containing the .mp4 files from Step 2.")
    ap.add_argument("--images", default=None,
                    help="Directory containing the .jpg files from download_fb_images.py (optional; HANDOVER §8.5).")
    ap.add_argument("--competitor", default=None,
                    help="Slug for the master CSV file. Inferred from --input filename if omitted.")
    ap.add_argument("--master-dir", default="master", help="Where master CSVs live (default: ./master/).")
    ap.add_argument("--log-dir", default="step3_logs", help="Where per-run logs are written (default: ./step3_logs/).")
    ap.add_argument("--dry-run", action="store_true", help="Don't upload; report decisions only.")
    args = ap.parse_args()

    folder = pathlib.Path.cwd()
    env = load_env(folder / ".env")

    input_csv = pathlib.Path(args.input)
    if not input_csv.exists():
        sys.exit(f"[error] input CSV not found: {input_csv}")
    videos_dir = pathlib.Path(args.videos)
    images_dir = pathlib.Path(args.images) if args.images else None

    competitor = (args.competitor or infer_competitor(input_csv) or "").lower()
    if not competitor:
        sys.exit("[error] could not infer competitor slug from input filename; pass --competitor.")

    master_path = pathlib.Path(args.master_dir) / f"{competitor}.csv"
    enriched_path = input_csv.with_name(input_csv.stem + "_enriched.csv")
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    log_path = pathlib.Path(args.log_dir) / f"{competitor}-{stamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[info] competitor:  {competitor}")
    print(f"[info] input:       {input_csv}")
    print(f"[info] videos:      {videos_dir}")
    print(f"[info] images:      {images_dir if images_dir else '(none — image rows will be image-pending)'}")
    print(f"[info] master:      {master_path}")
    print(f"[info] enriched:    {enriched_path}")
    print(f"[info] log:         {log_path}")
    print(f"[info] dry-run:     {args.dry_run}")
    print(f"[info] bucket:      {env['R2_BUCKET']}  ({env['R2_PUBLIC_URL_BASE']})")

    # Load input
    input_cols, input_rows = read_csv(input_csv)
    if not input_rows:
        sys.exit(f"[error] input CSV has no rows: {input_csv}")

    # Load master (or initialise empty schema)
    master_cols, master_rows = read_csv(master_path)
    if not master_cols:
        master_cols = list(input_cols) + [c for c in MASTER_EXTRA_COLS if c not in input_cols]
    else:
        # Ensure new scraper columns get added to master without losing existing data
        for c in input_cols:
            if c not in master_cols:
                master_cols.append(c)
        for c in MASTER_EXTRA_COLS:
            if c not in master_cols:
                master_cols.append(c)

    # Index master by (ad_library_id, version_index, creative_index_in_ad).
    # version_index is part of the row identity so version-expansion produces one
    # master row per (ad, version, creative slot). A BLANK version_index normalises
    # to "0" so OLD committed masters (no version_index column) map onto
    # version_index=0 — additive-safe, no orphaning of pre-existing rows.
    def key_for(row: dict) -> Tuple[str, str, str]:
        return (str(row.get("ad_library_id", "")).strip(),
                str(row.get("version_index", "0")).strip() or "0",
                str(row.get("creative_index_in_ad", "0")).strip() or "0")

    master_by_key: Dict[Tuple[str, str, str], dict] = {key_for(r): r for r in master_rows}

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
    log_lines: list[str] = []
    counts = {"uploaded": 0, "carried-forward": 0, "image-pending": 0,
              "video-missing": 0, "no-creative": 0, "error": 0}

    enriched_rows: list[dict] = []

    for row in input_rows:
        k = key_for(row)
        ad_library_id, version_index, creative_index_in_ad = k
        existing_master = master_by_key.get(k)

        # 1. carry-forward path: master already has an R2 URL
        if existing_master and existing_master.get("r2_public_url"):
            r2_public_url = existing_master["r2_public_url"]
            # Update mutable fields in master (latest scrape wins for these)
            for c in input_cols:
                if c in ("first_scrape_run_date",):
                    continue
                existing_master[c] = row.get(c, existing_master.get(c, ""))
            existing_master["latest_scrape_run_date"] = today
            existing_master["r2_public_url"] = r2_public_url  # preserve
            enriched_rows.append({**row, "r2_public_url": r2_public_url})
            counts["carried-forward"] += 1
            log_lines.append(f"carried-forward  {ad_library_id} c{creative_index_in_ad}  → {r2_public_url}")
            continue

        # 2. resolve local file
        local_path, kind = local_file_for_row(row, videos_dir, images_dir)

        if kind == "no-creative":
            counts["no-creative"] += 1
            log_lines.append(f"no-creative      {ad_library_id} c{creative_index_in_ad}  (blank/invalid ad_library_id)")
            enriched_rows.append({**row, "r2_public_url": ""})
            continue
        if kind == "image-pending":
            counts["image-pending"] += 1
            log_lines.append(f"image-pending    {ad_library_id} c{creative_index_in_ad}  (HANDOVER §8.5 — image handling not yet built)")
            enriched_rows.append({**row, "r2_public_url": ""})
            # Track in master so it's visible
            new_master_row = {**row, "r2_public_url": "", "first_scrape_run_date": today, "latest_scrape_run_date": today}
            if existing_master:
                existing_master.update({c: row.get(c, existing_master.get(c, "")) for c in input_cols})
                existing_master["latest_scrape_run_date"] = today
            else:
                master_rows.append(new_master_row)
                master_by_key[k] = new_master_row
            continue
        if kind == "video-missing":
            counts["video-missing"] += 1
            log_lines.append(f"video-missing    {ad_library_id} c{creative_index_in_ad}  (expected file not found in {videos_dir})")
            enriched_rows.append({**row, "r2_public_url": ""})
            continue

        # 3. upload path (kind in {"video", "image"})
        assert local_path is not None
        r2_key = local_path.name  # flat namespace: {ad_library_id}[_v{N}].mp4 or [_c{N}].jpg
        content_type = "image/jpeg" if kind == "image" else "video/mp4"
        if args.dry_run:
            r2_public_url = f"{env['R2_PUBLIC_URL_BASE']}/{r2_key}  [DRY-RUN]"
            counts["uploaded"] += 1
            log_lines.append(f"would-upload     {ad_library_id} c{creative_index_in_ad}  ({kind:<5}) ← {local_path.name}  → {r2_public_url}")
            enriched_rows.append({**row, "r2_public_url": r2_public_url})
            continue

        try:
            with open(local_path, "rb") as fh:
                s3.put_object(Bucket=env["R2_BUCKET"], Key=r2_key, Body=fh, ContentType=content_type)
            r2_public_url = f"{env['R2_PUBLIC_URL_BASE']}/{r2_key}"
            counts["uploaded"] += 1
            log_lines.append(f"uploaded         {ad_library_id} c{creative_index_in_ad}  ({kind:<5}) ← {local_path.name}  → {r2_public_url}")
            enriched_rows.append({**row, "r2_public_url": r2_public_url})
            # Upsert into master
            if existing_master:
                existing_master.update({c: row.get(c, existing_master.get(c, "")) for c in input_cols})
                existing_master["r2_public_url"] = r2_public_url
                existing_master["latest_scrape_run_date"] = today
            else:
                new_master_row = {**row, "r2_public_url": r2_public_url,
                                  "first_scrape_run_date": today, "latest_scrape_run_date": today}
                master_rows.append(new_master_row)
                master_by_key[k] = new_master_row
            # Checkpoint the master after every successful upload so an interrupted run
            # can be resumed: re-running will see existing r2_public_url and carry-forward.
            write_csv(master_path, master_cols, master_rows)
        except Exception as e:
            counts["error"] += 1
            log_lines.append(f"error-upload     {ad_library_id} c{creative_index_in_ad}  ← {local_path.name}  : {type(e).__name__}: {e}")
            enriched_rows.append({**row, "r2_public_url": ""})

    # --- persist outputs ---
    if not args.dry_run:
        write_csv(master_path, master_cols, master_rows)
    write_csv(enriched_path,
              list(input_cols) + (["r2_public_url"] if "r2_public_url" not in input_cols else []),
              enriched_rows)

    log_header = [
        f"# Step 3 run log",
        f"# competitor : {competitor}",
        f"# started_at : {datetime.now().isoformat(timespec='seconds')}",
        f"# input      : {input_csv}",
        f"# videos     : {videos_dir}",
        f"# master     : {master_path}  ({'updated' if not args.dry_run else 'unchanged (dry-run)'})",
        f"# enriched   : {enriched_path}",
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
        print(f"  {k_:<16} {v_}")
    print(f"[done] enriched: {enriched_path}")
    if not args.dry_run:
        print(f"[done] master:   {master_path}  ({len(master_rows)} rows total)")
    print(f"[done] log:      {log_path}")

    # exit code: non-zero ONLY on real upload errors (S3/network). video-missing is
    # surfaced as a warning but is NON-FATAL — it's usually benign (re-keyed
    # multi-version rows whose key changed, or an ad whose CDN expired). Treating it
    # as fatal halted whole competitors (the MySivi case). The per-run audit
    # (tools/pipeline-run/audit.py) checks LEAD-creative coverage and escalates if a
    # real creative was actually lost.
    if counts["video-missing"]:
        print(f"[warn] {counts['video-missing']} video-missing row(s) — surfaced, NON-FATAL "
              f"(logged in {log_path}); audit verifies lead-creative coverage.")
    return 1 if counts["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
