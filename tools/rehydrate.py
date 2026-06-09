#!/usr/bin/env python3
"""
rehydrate.py — refill a competitor's local media cache from Cloudflare R2.

Git holds the master CSV (with every r2_public_url); the heavy media lives in
R2. This pulls the media back down so you can work a competitor someone else
scraped, without a 60 GB transfer.

Two download modes (auto-selected):
  • AUTHENTICATED (preferred) — if R2 keys are in your .env, downloads with the
    S3 API. Works even when the bucket's public access is off (a 403 on the
    public URL). The object key is derived from the public URL's path.
  • PUBLIC — if no keys are present, falls back to the public r2.dev URL (needs
    the bucket to have public access enabled).

Usage:
  python3 tools/rehydrate.py --pipeline facebook --competitor zinglish
  python3 tools/rehydrate.py --pipeline google   --competitor speakx --dry-run
"""
from __future__ import annotations

import argparse
import csv
import datetime
import pathlib
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

csv.field_size_limit(10 ** 9)

VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

ID_COL = {"facebook": "ad_library_id", "google": "creative_id"}
VAR_COL = {"facebook": "creative_index_in_ad", "google": "variant_index"}

# straight + curly quotes — strip any that wrap a .env value
_QUOTES = "".join(chr(c) for c in (0x22, 0x27, 0x2018, 0x2019, 0x201c, 0x201d))


def load_env(base: pathlib.Path, pipeline: str) -> dict:
    """Merge keys from every common .env location (root, this pipeline's dir, and
    the other pipeline's dir), first-found wins. So keys put in facebook/.env work
    for a google run too, without the operator having to copy files around."""
    env: dict = {}
    for p in (base / ".env", base / pipeline / ".env",
              base / "facebook" / ".env", base / "google" / ".env"):
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    if k not in env:                 # earlier files win
                        env[k] = v.strip().strip(_QUOTES)
    return env


def r2_client(env: dict):
    """Build an S3 client for R2 if keys are present, else (None, None)."""
    need = ("R2_S3_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
    if not all(env.get(k) for k in need):
        return None, None
    try:
        import boto3
    except ImportError:
        return None, None
    client = boto3.client(
        "s3", endpoint_url=env["R2_S3_ENDPOINT"],
        aws_access_key_id=env["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
        region_name="auto")
    return client, env["R2_BUCKET"]


def ext_of(url: str) -> str:
    path = url.split("?", 1)[0]
    dot = path.rfind(".")
    return path[dot:].lower() if dot != -1 else ""


def object_key(url: str) -> str:
    """The R2 object key = the public URL's path (everything after the host)."""
    return urlparse(url).path.lstrip("/")


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
    ap.add_argument("--public", action="store_true",
                    help="force public-URL download even if R2 keys are present")
    args = ap.parse_args()

    base = pathlib.Path(args.base)
    slug = args.competitor
    master = base / args.pipeline / "master" / f"{slug}.csv"
    if not master.exists():
        sys.exit(f"master not found: {master}")

    id_col = ID_COL[args.pipeline]
    var_col = VAR_COL[args.pipeline]

    client, bucket = (None, None)
    if not args.public:
        client, bucket = r2_client(load_env(base, args.pipeline))

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
            continue
        cid = (r.get(id_col) or "").strip()
        if not cid:
            continue
        date = ((r.get("scrape_run_date") or r.get("latest_scrape_run_date")
                 or datetime.date.today().isoformat()).strip())
        # Local filename = the R2 object key's basename. upload_to_r2.py uses a flat
        # namespace where the key IS the media filename, so this matches byte-for-byte
        # what was uploaded — including version-expansion names {id}_ver{V}_c{C}.mp4.
        dest = base / args.pipeline / kind / f"{slug}-{date}" / pathlib.Path(
            object_key(url)).name
        if dest in seen_dest:
            continue
        seen_dest.add(dest)
        planned.append((url, dest))

    if args.limit:
        planned = planned[:args.limit]

    mode = "authenticated (your R2 keys)" if client is not None else "public URL"
    print(f"[rehydrate] {args.pipeline}/{slug}: {len(planned)} asset(s) referenced "
          f"in master — mode: {mode}")
    if client is None and not args.public:
        print("[rehydrate] note: no R2 keys found in .env — using public URLs. "
              "If you get 403s, add R2 keys to your .env.")

    dl = skip = fail = 0
    for url, dest in planned:
        if dest.exists() and dest.stat().st_size > 0:
            skip += 1
            continue
        # Already downloaded under a DIFFERENT dated folder for this competitor?
        # The master re-dates rows to the latest scrape, but the file may already sit
        # in an earlier {slug}-DATE/ folder. Downstream find_video globs {slug}-* across
        # ALL dates, so re-downloading into a new date folder is pure waste — skip it.
        # (dest = .../{pipeline}/{kind}/{slug}-{date}/{name}; .parent.parent = the kind dir)
        if any(p.stat().st_size > 0
               for p in dest.parent.parent.glob(f"{slug}-*/{dest.name}")):
            skip += 1
            continue
        if args.dry_run:
            print(f"  WOULD GET {url}\n            -> {dest}")
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(dest.suffix + ".part")
            if client is not None:
                client.download_file(bucket, object_key(url), str(tmp))
            else:
                urllib.request.urlretrieve(url, tmp)
            tmp.replace(dest)
            dl += 1
            print(f"  OK   {dest.name}")
        except (urllib.error.URLError, OSError, Exception) as e:  # noqa: BLE001
            fail += 1
            print(f"  FAIL {dest.name} — {e}")

    tag = " (dry-run)" if args.dry_run else ""
    print(f"[rehydrate] done: {dl} downloaded, {skip} already present, "
          f"{fail} failed{tag}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
