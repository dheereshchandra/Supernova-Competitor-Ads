#!/usr/bin/env python3
"""
upgrade_master_schema.py — ensure every master CSV carries the full link schema.

Older master CSVs predate some columns (notably the Step-4 image-array link
columns), so a link kind can have nowhere to live. This adds any missing columns
(empty) to every {pipeline}/master/{slug}.csv, preserving all existing data and
column order. Non-destructive and idempotent; writes a .bak before changing.

The required columns mirror MASTER_EXTRA_COLS in each pipeline's
scripts/upload_to_r2.py — keep them in sync if those lists change.

Usage:
  python3 tools/upgrade_master_schema.py            # dry-run (report only)
  python3 tools/upgrade_master_schema.py --apply    # write changes (.bak first)
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import shutil
import sys

csv.field_size_limit(10 ** 9)
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Mirrors scripts/upload_to_r2.py MASTER_EXTRA_COLS in each pipeline.
EXTRA = {
    "facebook": [
        "r2_public_url", "first_scrape_run_date", "latest_scrape_run_date",
        "competitor_analysis_docx_r2_url", "supernova_rewrite_docx_r2_url",
        "orig_frame_urls", "gen_panel_urls", "char_sheet_urls",
    ],
    "google": [
        "ad_cta_text", "ad_overlay_text", "youtube_video_title",
        "youtube_video_description", "youtube_channel_name",
        "youtube_video_duration_s", "error_tag",
        "r2_public_url", "first_scrape_run_date", "latest_scrape_run_date",
        "competitor_analysis_docx_r2_url", "supernova_rewrite_docx_r2_url",
        "competitor_analysis_image_r2_urls", "supernova_rewrite_image_r2_urls",
    ],
}

SKIP_SUBSTRINGS = (".bak", "_review", "_newly_added", "_step4_top",
                   ".savedcopy", "_run_summary")


def master_files(base: pathlib.Path, pipeline: str):
    d = base / pipeline / "master"
    if not d.exists():
        return []
    return [p for p in sorted(d.glob("*.csv"))
            if not any(s in p.name for s in SKIP_SUBSTRINGS)]


def process(p: pathlib.Path, required, apply: bool):
    with p.open(encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        header = list(rd.fieldnames or [])
        rows = list(rd)
    missing = [c for c in required if c not in header]
    if missing and apply:
        shutil.copy2(p, str(p) + ".bak.pre-schema-upgrade")
        new_fields = header + missing
        with p.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=new_fields, extrasaction="ignore")
            w.writeheader()
            for row in rows:
                for c in missing:
                    row.setdefault(c, "")
                w.writerow(row)
    return missing, len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(REPO_ROOT))
    ap.add_argument("--apply", action="store_true",
                    help="write changes (default: dry-run report only)")
    args = ap.parse_args()
    base = pathlib.Path(args.base)

    changed = 0
    for pipeline in ("facebook", "google"):
        files = master_files(base, pipeline)
        print(f"\n=== {pipeline} — {len(files)} master file(s) ===")
        for p in files:
            missing, nrows = process(p, EXTRA[pipeline], args.apply)
            if missing:
                changed += 1
                verb = "ADDED" if args.apply else "would add"
                print(f"  {p.name} ({nrows} rows): {verb} {missing}")
            else:
                print(f"  {p.name} ({nrows} rows): OK (full schema)")
    tail = "" if args.apply else "  — re-run with --apply to write."
    print(f"\n{'APPLIED to' if args.apply else 'WOULD change'} {changed} file(s).{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
