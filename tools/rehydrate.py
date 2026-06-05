#!/usr/bin/env python3
"""
rehydrate.py — refill a competitor's local media cache from Cloudflare R2.

Git holds the master CSV (with every r2_public_url); the heavy media lives in
R2. This pulls the media back down so you can work a competitor someone else
scraped, without a 60 GB transfer. R2 public URLs need no credentials.

Usage:
  python3 tools/rehydrate.py --pipeline facebook --competitor zinglish
  python3 tools/rehydrate.py --pipeline google   --competitor speakx --dry-run

Reads {repo}/{pipeline}/master/{competitor}.csv and, for every row with a
non-empty r2_public_url, downloads the asset into
{pipeline}/videos/{slug}-{date}/ or {pipeline}/images/{slug}-{date}/, using the
pipeline's id/variant naming. Skips files already on disk. Prints a tally.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import pathlib
import sys
import urllib.error
import urllib.request

csv.field_size_limit(10 ** 9)

VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# id / variant column names differ per pipeline
ID_COL = {"facebook": "ad_library_id", "google": "creative_id"}
VAR_COL = {"facebook": "creative_index_in_ad", "google": "variant_index"}


def ext_of(url: str) -> str:
    path = url.split("?", 1)[0]
    dot = path.rfind(".")
    return path[dot:].lower() if dot != -1 else ""


def local_name(cid: str, variant, ext: str) -> str:
    """Reproduce the downloader's naming: {id}.ext, variants as {id}_v2.ext …"""
    try:
        v = int(str(variant).strip() or "0")
    except ValueError:
        v = 0
    suffix = "" if v <= 0 else f"_v{v + 1}"
    return f"{cid}{suffix}{ext}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Pull a competitor's media from R2 into the local cache.")
    ap.add_argument("--pipeline", required=True, choices=["facebook", "google"])
    ap.add_argument("--competitor", required=True,
                    help="slug, e.g. zinglish (matches master/{slug}.csv)")
    ap.add_argument("--base", default=str(REPO_ROOT),
                    help="repo root (default: auto-detected from this script)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be downloaded; makes no network calls")
    ap.add_argument("--limit", type=int, help="cap number of downloads (testing)")
    args = ap.parse_args()

    base = pathlib.Path(args.base)
    slug = args.competitor
    master = base / args.pipeline / "master" / f"{slug}.csv"
    if not master.exists():
        sys.exit(f"master not found: {master}")

    id_col = ID_COL[args.pipeline]
    var_col = VAR_COL[args.pipeline]

    with master.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    planned = []          # (url, dest_path)
    seen_dest = set()
    for r in rows:
        url = (r.get("r2_public_url") or "").strip()
        if not url.startswith("http"):
            continue
        ext = ext_of(url)
        if ext in VIDEO_EXTS:
            kind = "videos"
        elif ext in IMAGE_EXTS:
            kind = "images"
        else:
            continue  # unknown asset type — skip
        cid = (r.get(id_col) or "").strip()
        if not cid:
            continue
        date = ((r.get("scrape_run_date") or r.get("latest_scrape_run_date")
                 or datetime.date.today().isoformat()).strip())
        dest = base / args.pipeline / kind / f"{slug}-{date}" / local_name(
            cid, r.get(var_col), ext)
        if dest in seen_dest:
            continue
        seen_dest.add(dest)
        planned.append((url, dest))

    if args.limit:
        planned = planned[:args.limit]

    print(f"[rehydrate] {args.pipeline}/{slug}: "
          f"{len(planned)} asset(s) referenced in master")
    dl = skip = fail = 0
    for url, dest in planned:
        if dest.exists() and dest.stat().st_size > 0:
            skip += 1
            continue
        if args.dry_run:
            print(f"  WOULD GET {url}\n            -> {dest}")
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(dest.suffix + ".part")
            urllib.request.urlretrieve(url, tmp)
            tmp.replace(dest)
            dl += 1
            print(f"  OK   {dest.name}")
        except (urllib.error.URLError, OSError) as e:
            fail += 1
            print(f"  FAIL {dest.name} — {e}")

    tag = " (dry-run)" if args.dry_run else ""
    print(f"[rehydrate] done: {dl} downloaded, {skip} already present, "
          f"{fail} failed{tag}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
