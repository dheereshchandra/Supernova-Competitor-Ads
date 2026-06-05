#!/usr/bin/env python3
"""
Step 3 — Upload Google ad assets (videos + images) to Cloudflare R2 +
update the per-competitor master CSV.

Designed to be run after Step 2 (download_google_ads.py). Reads the per-run
input CSV produced by Step 1 (`scripts/scrape_google_ads.py`), looks up each
`creative_id` in the per-competitor master CSV, and decides per row whether
to upload-and-record, carry-forward an existing R2 URL, or skip (Text rows,
unsupported formats, asset-missing).

For YouTubeVideo rows whose .info.json sidecar exists from Step 2, the
script also reads the sidecar and back-fills the master row's
youtube_video_title / description / channel_name / duration_s columns.

See ../HANDOVER.md §6 for the full design and known issues (notably: the
carried-forward branch currently doesn't re-read .info.json on a re-scrape —
the operator's wrapper `run_all_competitors.sh` has a backfill snippet for
that case).

Usage:
    python3 scripts/upload_to_r2.py \\
        --input  inputs/g-ads-zinglish-2026-05-27.csv \\
        --videos videos/zinglish-2026-05-27/ \\
        --images images/zinglish-2026-05-27/ \\
        [--competitor zinglish]   # auto-inferred from input filename if omitted
        [--dry-run]               # report what would happen, upload nothing

R2 key naming: `{creative_id}.mp4` or `{creative_id}.jpg` in the configured
bucket. If `R2_BUCKET=video-ads` (shared with FB pipeline), the script
auto-prepends `g_` so Google assets don't collide with Facebook ones.

Outputs (idempotent on re-run, resumable):
    master/{competitor}.csv                       — rolling per-competitor truth
    inputs/{input-stem}_enriched.csv              — same rows as input + r2_public_url filled in
    step3_logs/{competitor}-{YYYY-MM-DD-HHMM}.log — per-row outcome
"""
from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import os
import pathlib
import re
import sys
from datetime import date, datetime
from typing import Dict, Iterable, Optional, Tuple


# ---------------------------------------------------------------------------
# .env loader (no external dependency)
# ---------------------------------------------------------------------------

def load_env(env_path: pathlib.Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not env_path.exists():
        sys.exit(f"[error] .env not found at {env_path}. Copy .env.template → .env and fill in the values.")
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


# ---------------------------------------------------------------------------
# YouTube metadata enrichment (reads yt-dlp's .info.json sidecars)
# ---------------------------------------------------------------------------

# Columns that come from {video}.info.json (written by Step 2's download_google_ads.py
# when yt-dlp is invoked with --write-info-json). These are added to the master CSV
# for YouTubeVideo rows so the analytical view has the YouTube watch-page title,
# description, channel, and duration alongside the Transparency Center metadata.
YOUTUBE_METADATA_COLS = [
    "youtube_video_title",
    "youtube_video_description",
    "youtube_channel_name",
    "youtube_video_duration_s",
]


def read_youtube_info_json(video_path: pathlib.Path) -> Dict[str, str]:
    """Return a dict with YOUTUBE_METADATA_COLS populated from {video_path}.info.json,
    or empty strings if the sidecar is missing / unparseable.
    Description is truncated to 2000 chars; title to 500 chars."""
    blank = {c: "" for c in YOUTUBE_METADATA_COLS}
    info_path = video_path.with_suffix(".info.json")
    if not info_path.exists():
        return blank
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return blank
    title = (data.get("title") or "")[:500]
    desc = (data.get("description") or "")[:2000]
    channel = data.get("uploader") or data.get("channel") or data.get("uploader_id") or ""
    duration = data.get("duration")
    return {
        "youtube_video_title": title,
        "youtube_video_description": desc,
        "youtube_channel_name": channel,
        "youtube_video_duration_s": str(int(duration)) if isinstance(duration, (int, float)) and duration > 0 else "",
    }


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

# Columns this script either adds or guarantees on the master CSV. Listed here so
# the master schema is stable across runs even when an older input CSV omits some.
MASTER_EXTRA_COLS = [
    # Step 1 columns introduced after the scraper rewrite — included here so older
    # input CSVs that predate them still produce a master CSV with the right schema.
    "ad_cta_text",
    "ad_overlay_text",
    "youtube_video_title",
    "youtube_video_description",
    "youtube_channel_name",
    "youtube_video_duration_s",
    "error_tag",
    # Step 3-added
    "r2_public_url",
    "first_scrape_run_date",
    "latest_scrape_run_date",
    # Step 4-added (reserved here so the schema is stable across step ordering)
    "competitor_analysis_docx_r2_url",
    "supernova_rewrite_docx_r2_url",
    "competitor_analysis_image_r2_urls",   # JSON array of {type, scene_n/character_id, r2_url, ...}
    "supernova_rewrite_image_r2_urls",     # JSON array, clean panels only
]


def read_csv(path: pathlib.Path) -> Tuple[list[str], list[dict]]:
    if not path.exists():
        return [], []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames or []), list(r)


def write_csv(path: pathlib.Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


# ---------------------------------------------------------------------------
# Local-file resolution per row
# ---------------------------------------------------------------------------

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def local_file_for_row(row: dict, videos_dir: pathlib.Path,
                        images_dir: pathlib.Path) -> Tuple[Optional[pathlib.Path], str]:
    """
    Decide which local file corresponds to this CSV row.

    Filename convention (mirrors FB pipeline for variants):
        variant_index 0   → {creative_id}.mp4 / {creative_id}.{ext}
        variant_index N≥1 → {creative_id}_v{N+1}.mp4 / {creative_id}_v{N+1}.{ext}

    Returns (path_or_None, kind) where kind is one of:
        "video"             — found a .mp4 to upload
        "image"             — found an image file to upload
        "text-no-asset"     — Text-format ad, no upload needed
        "asset-missing"     — expected a file but it isn't on disk
        "unsupported"       — Shopping/Maps with no asset captured
        "no-creative"       — creative_id missing or invalid
    """
    creative_id = (row.get("creative_id") or "").strip()
    if not creative_id:
        return None, "no-creative"

    # Rows tagged with a scrape-time error_tag in Step 1 have empty media fields by definition.
    # Surface them distinctly in the Step 3 log so the operator can decide to re-scrape.
    err = (row.get("error_tag") or "").strip()
    if err:
        return None, f"scrape-error:{err}"

    fmt = (row.get("creative_format") or "").strip()

    # Variant index — defaults to 0 if missing (pre-variant-schema CSVs)
    try:
        vi = int((row.get("variant_index") or "0").strip() or "0")
    except (ValueError, AttributeError):
        vi = 0

    def with_variant_suffix(base: str, ext: str) -> str:
        if vi == 0:
            return f"{base}{ext}"
        return f"{base}_v{vi + 1}{ext}"

    if fmt == "Text":
        return None, "text-no-asset"

    if fmt == "YouTubeVideo":
        candidate = videos_dir / with_variant_suffix(creative_id, ".mp4")
        if candidate.exists() and candidate.stat().st_size > 10_000:
            return candidate, "video"
        return None, "asset-missing"

    if fmt == "Image" or fmt in ("Shopping", "Maps"):
        for ext in IMAGE_EXTS:
            candidate = images_dir / with_variant_suffix(creative_id, ext)
            if candidate.exists() and candidate.stat().st_size > 1_000:
                return candidate, "image"
        if fmt in ("Shopping", "Maps"):
            return None, "unsupported"
        return None, "asset-missing"

    return None, "unsupported"


# ---------------------------------------------------------------------------
# R2 key naming — handles both dedicated bucket and shared-with-FB bucket
# ---------------------------------------------------------------------------

def r2_key_for(creative_id: str, local_file: pathlib.Path, bucket_name: str) -> str:
    """
    Build the R2 object key. If using the FB pipeline's bucket name, prefix with
    g_ to avoid flat-namespace collisions. Otherwise use the bare filename.
    """
    ext = local_file.suffix.lower() or ".bin"
    base = f"{creative_id}{ext}"
    if bucket_name.lower() in ("video-ads",):  # FB pipeline's bucket name
        return f"g_{base}"
    return base


def content_type_for(local_file: pathlib.Path) -> str:
    ext = local_file.suffix.lower()
    if ext == ".mp4":
        return "video/mp4"
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    if ext == ".gif":
        return "image/gif"
    guessed, _ = mimetypes.guess_type(str(local_file))
    return guessed or "application/octet-stream"


# ---------------------------------------------------------------------------
# Competitor slug inference
# ---------------------------------------------------------------------------

INPUT_NAME_RE = re.compile(
    r"^g-ads-(?P<slug>[a-z0-9-]+)-\d{4}-\d{2}-\d{2}(-\d{4})?(_enriched)?\.csv$",
    re.I,
)


def infer_competitor(path: pathlib.Path) -> Optional[str]:
    m = INPUT_NAME_RE.match(path.name)
    return m.group("slug").lower() if m else None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="Per-run input CSV from Step 1.")
    ap.add_argument("--videos", required=True, help="Directory containing the .mp4 files from Step 2.")
    ap.add_argument("--images", required=True, help="Directory containing the image files from Step 2.")
    ap.add_argument("--competitor", default=None,
                    help="Slug for the master CSV file. Inferred from --input filename if omitted.")
    ap.add_argument("--master-dir", default="master", help="Where master CSVs live (default: ./master/).")
    ap.add_argument("--log-dir", default="step3_logs", help="Where per-run logs are written.")
    ap.add_argument("--dry-run", action="store_true", help="Don't upload; report decisions only.")
    args = ap.parse_args()

    folder = pathlib.Path.cwd()
    env = load_env(folder / ".env")

    input_csv = pathlib.Path(args.input)
    if not input_csv.exists():
        sys.exit(f"[error] input CSV not found: {input_csv}")
    videos_dir = pathlib.Path(args.videos)
    images_dir = pathlib.Path(args.images)

    competitor = (args.competitor or infer_competitor(input_csv) or "").lower()
    if not competitor:
        sys.exit("[error] could not infer competitor slug from input filename; pass --competitor.")

    master_path = pathlib.Path(args.master_dir) / f"{competitor}.csv"
    enriched_path = input_csv.with_name(input_csv.stem.replace("_enriched", "") + "_enriched.csv")
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    log_path = pathlib.Path(args.log_dir) / f"{competitor}-{stamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[info] competitor:  {competitor}")
    print(f"[info] input:       {input_csv}")
    print(f"[info] videos:      {videos_dir}")
    print(f"[info] images:      {images_dir}")
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
        for c in input_cols:
            if c not in master_cols:
                master_cols.append(c)
        for c in MASTER_EXTRA_COLS:
            if c not in master_cols:
                master_cols.append(c)

    # Index master by (creative_id, variant_index) — variants of the same ad get separate rows.
    # variant_index defaults to "0" for backwards-compat with older CSVs that lack the column.
    def key_for(row: dict) -> Tuple[str, str]:
        cid = (row.get("creative_id") or "").strip()
        vi = (row.get("variant_index") or "0").strip() or "0"
        return (cid, vi)

    master_by_key: Dict[Tuple[str, str], dict] = {
        key_for(r): r for r in master_rows if key_for(r)[0]
    }

    # boto3 client (lazy — only if not dry-run)
    s3 = None
    if not args.dry_run:
        try:
            import boto3
        except ImportError:
            sys.exit("[error] boto3 not installed. Run: python3 -m pip install --upgrade boto3")
        s3 = boto3.client(
            "s3",
            endpoint_url=env["R2_S3_ENDPOINT"],
            aws_access_key_id=env["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
        )

    today = date.today().isoformat()
    log_lines: list[str] = []
    counts = {"uploaded-video": 0, "uploaded-image": 0,
              "carried-forward": 0, "text-no-asset": 0,
              "asset-missing": 0, "unsupported": 0,
              "no-creative": 0, "scrape-error": 0, "error": 0}

    enriched_rows: list[dict] = []

    for row in input_rows:
        k = key_for(row)
        creative_id, variant_index = k
        existing_master = master_by_key.get(k) if creative_id else None

        # 1. carry-forward path — master already has an R2 URL for this creative
        if existing_master and (existing_master.get("r2_public_url") or "").strip():
            r2_public_url = existing_master["r2_public_url"]
            # Update mutable fields in master (latest scrape wins for these)
            for c in input_cols:
                if c == "first_scrape_run_date":
                    continue
                existing_master[c] = row.get(c, existing_master.get(c, ""))
            existing_master["latest_scrape_run_date"] = today
            existing_master["r2_public_url"] = r2_public_url
            enriched_rows.append({**row, "r2_public_url": r2_public_url})
            counts["carried-forward"] += 1
            log_lines.append(f"carried-forward  {creative_id} v{variant_index}  → {r2_public_url}")
            continue

        # 2. resolve local file
        local_path, kind = local_file_for_row(row, videos_dir, images_dir)

        if kind == "no-creative":
            counts["no-creative"] += 1
            log_lines.append(f"no-creative      (blank creative_id)")
            enriched_rows.append({**row, "r2_public_url": ""})
            continue

        if kind.startswith("scrape-error:"):
            tag = kind.split(":", 1)[1]
            counts["scrape-error"] += 1
            log_lines.append(f"scrape-error     {creative_id} v{variant_index}  (Step 1 tag: {tag}; re-run Step 1 to recover)")
            # Keep the row in master so Step 1 re-runs can fill it in via carry-forward logic.
            new_row = {**row, "r2_public_url": "",
                       "first_scrape_run_date": today, "latest_scrape_run_date": today}
            if existing_master:
                # Refresh the existing master row from the new input — including
                # error_tag — so a re-scrape with updated tags propagates. Without
                # this, an older asset-missing-from-disk tag from a previous Step 3
                # run sticks even though the fresh input now carries the correct
                # html5-banner-no-mp4 / image-url-not-extracted / etc. tag.
                existing_master.update(
                    {c: row.get(c, existing_master.get(c, "")) for c in input_cols})
                existing_master["latest_scrape_run_date"] = today
            else:
                master_rows.append(new_row)
                master_by_key[k] = new_row
            enriched_rows.append({**row, "r2_public_url": ""})
            continue

        if kind == "text-no-asset":
            counts["text-no-asset"] += 1
            log_lines.append(f"text-no-asset    {creative_id}  (Text ad — no upload, analysis in Step 4 uses headline+desc)")
            # Track in master so Step 4 can find it
            new_row = {**row, "r2_public_url": "",
                       "first_scrape_run_date": today, "latest_scrape_run_date": today}
            if existing_master:
                existing_master.update({c: row.get(c, existing_master.get(c, "")) for c in input_cols})
                existing_master["latest_scrape_run_date"] = today
            else:
                master_rows.append(new_row)
                master_by_key[k] = new_row
            enriched_rows.append({**row, "r2_public_url": ""})
            continue

        if kind == "unsupported":
            counts["unsupported"] += 1
            log_lines.append(f"unsupported      {creative_id}  (format = {row.get('creative_format')!r}, no asset)")
            enriched_rows.append({**row, "r2_public_url": ""})
            new_row = {**row, "r2_public_url": "",
                       "first_scrape_run_date": today, "latest_scrape_run_date": today}
            if not existing_master:
                master_rows.append(new_row)
                master_by_key[k] = new_row
            continue

        if kind == "asset-missing":
            counts["asset-missing"] += 1
            log_lines.append(f"asset-missing    {creative_id}  (expected local file not found; will upsert on next Step 3 run after Step 2 produces the file)")
            # If the row arrived with an empty error_tag (i.e. Step 1 thought
            # the asset existed but Step 3 can't find a local file), make the
            # gap self-documenting in the master CSV.
            row_with_tag = dict(row)
            if not (row_with_tag.get("error_tag") or "").strip():
                row_with_tag["error_tag"] = "asset-missing-from-disk"
            # Track in master with empty r2_public_url so the master always reflects
            # the complete pipeline state. The next Step 3 run after Step 2 finishes
            # downloading will upsert the URL into this row.
            new_row = {**row_with_tag, "r2_public_url": "",
                       "first_scrape_run_date": today, "latest_scrape_run_date": today}
            if existing_master:
                existing_master.update({c: row_with_tag.get(c, existing_master.get(c, "")) for c in input_cols})
                existing_master["latest_scrape_run_date"] = today
            else:
                master_rows.append(new_row)
                master_by_key[k] = new_row
            enriched_rows.append({**row_with_tag, "r2_public_url": ""})
            continue

        # 3. upload path (video or image)
        assert local_path is not None
        r2_key = r2_key_for(creative_id, local_path, env["R2_BUCKET"])
        content_type = content_type_for(local_path)

        # YouTube metadata enrichment — for video rows, read the .info.json sidecar
        # that Step 2 (download_google_ads.py) wrote via yt-dlp's --write-info-json.
        # This adds youtube_video_title / description / channel / duration_s to both
        # the enriched per-run CSV and the master CSV.
        yt_meta = read_youtube_info_json(local_path) if kind == "video" else {c: "" for c in YOUTUBE_METADATA_COLS}

        if args.dry_run:
            r2_public_url = f"{env['R2_PUBLIC_URL_BASE']}/{r2_key}  [DRY-RUN]"
            counts[f"uploaded-{kind}"] += 1
            log_lines.append(f"would-upload     {creative_id}  ← {local_path.name}  → {r2_public_url}")
            enriched_rows.append({**row, **yt_meta, "r2_public_url": r2_public_url})
            continue

        try:
            with open(local_path, "rb") as fh:
                s3.put_object(Bucket=env["R2_BUCKET"], Key=r2_key, Body=fh, ContentType=content_type)
            r2_public_url = f"{env['R2_PUBLIC_URL_BASE']}/{r2_key}"
            counts[f"uploaded-{kind}"] += 1
            log_lines.append(f"uploaded-{kind:<5}  {creative_id}  ← {local_path.name}  → {r2_public_url}")
            enriched_rows.append({**row, **yt_meta, "r2_public_url": r2_public_url})
            # Upsert into master, including any YouTube metadata captured from .info.json
            if existing_master:
                existing_master.update({c: row.get(c, existing_master.get(c, "")) for c in input_cols})
                # Don't overwrite existing YouTube metadata with empties — only update if non-empty
                for c, v in yt_meta.items():
                    if v:
                        existing_master[c] = v
                existing_master["r2_public_url"] = r2_public_url
                existing_master["latest_scrape_run_date"] = today
            else:
                new_row = {**row, **yt_meta, "r2_public_url": r2_public_url,
                            "first_scrape_run_date": today, "latest_scrape_run_date": today}
                master_rows.append(new_row)
                master_by_key[k] = new_row
            # Checkpoint per row — survives Cowork's 45s bash cap
            write_csv(master_path, master_cols, master_rows)
        except Exception as e:
            counts["error"] += 1
            log_lines.append(f"error-upload     {creative_id}  ← {local_path.name}  : {type(e).__name__}: {e}")
            enriched_rows.append({**row, "r2_public_url": ""})

    # --- persist outputs ---
    if not args.dry_run:
        write_csv(master_path, master_cols, master_rows)
    # Enriched per-run CSV gets input columns + r2_public_url + youtube metadata columns
    # so a downstream consumer sees the same schema as the master.
    enriched_cols = list(input_cols)
    for c in YOUTUBE_METADATA_COLS + ["r2_public_url"]:
        if c not in enriched_cols:
            enriched_cols.append(c)
    write_csv(enriched_path, enriched_cols, enriched_rows)

    log_header = [
        f"# Step 3 run log (Google pipeline)",
        f"# competitor : {competitor}",
        f"# started_at : {datetime.now().isoformat(timespec='seconds')}",
        f"# input      : {input_csv}",
        f"# videos     : {videos_dir}",
        f"# images     : {images_dir}",
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
        if v_:
            print(f"  {k_:<18} {v_}")
    print(f"[done] enriched: {enriched_path}")
    if not args.dry_run:
        print(f"[done] master:   {master_path}  ({len(master_rows)} rows total)")
    print(f"[done] log:      {log_path}")

    return 1 if (counts["error"] + counts["asset-missing"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
