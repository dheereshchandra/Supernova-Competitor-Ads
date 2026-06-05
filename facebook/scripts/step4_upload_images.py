#!/usr/bin/env python3
"""
Step 4 — Stage 4.5: upload every scraped frame, regenerated panel, and
character sheet to R2, and write an ``images/<ad_id>/r2_urls.json`` sidecar
that Stage 6 (build_docs) and Stages 7+8 (upload_and_update) read from.

Why this is a separate stage:
  - Build_docs needs the public R2 URL of every image so it can render the
    "Asset: <url>" hyperlink beneath each embedded picture.
  - Upload_and_update needs the same URLs to fill the three new master-CSV
    columns (orig_frame_urls / gen_panel_urls / char_sheet_urls).
  - Putting the upload BEFORE build_docs makes both consumers trivially
    correct — they just read the sidecar.

R2 key layout (HANDOVER §9.7):
    images/<ad_library_id>/orig_<NN>.jpg
    images/<ad_library_id>/gen_<NN>_<pos>.jpg
    images/<ad_library_id>/char_<X>_sheet.jpg

Sidecar format (step4_workspace/images/<id>/r2_urls.json):
    {
      "ad_library_id": "1234567890123456",
      "orig":  {"01": "https://...orig_01.jpg", "02": "..."},
      "gen":   {"01_full": "https://...gen_01_full.jpg", "02_left": "..."},
      "char":  {"1": "https://...char_1_sheet.jpg", "2": "..."},
      "uploaded_at": "2026-05-28T13:45:01"
    }

Idempotent: each file is HEAD-checked on R2 before re-upload — only missing
or zero-byte objects are re-pushed.

Usage:
    python3 scripts/step4_upload_images.py --competitor zinglish <id1> <id2> ...
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from datetime import datetime

# r2_utils sits in the same scripts/ directory
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from r2_utils import (  # noqa: E402
    load_env, make_r2_client, public_url_for, upload_with_retry,
    orig_frame_key, gen_panel_key, char_sheet_key,
)


WORKSPACE = pathlib.Path("step4_workspace")
FRAMES_DIR = WORKSPACE / "frames"
IMAGES_DIR = WORKSPACE / "images"
SCENES_DIR = WORKSPACE / "scenes"


ORIG_RE = re.compile(r"^orig_(\d+)\.jpg$")
GEN_RE = re.compile(r"^gen_(\d+)_([a-zA-Z0-9_-]+)\.jpg$")
CHAR_RE = re.compile(r"^char_([A-Za-z0-9]+)_sheet\.jpg$")


def object_exists(s3, bucket: str, key: str) -> bool:
    """Cheap HEAD on R2. Treat any error as "missing" — we'll just re-upload."""
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def collect_images_for(ad_id: str) -> dict:
    """Return what's on disk for one ad, grouped by kind.

    Shape:
      {
        "orig": [(scene_n_str, path), ...],   # NN-padded
        "gen":  [(scene_n_str, pos, path), ...],
        "char": [(char_id_str, path), ...],
      }
    """
    out: dict[str, list] = {"orig": [], "gen": [], "char": []}

    frame_dir = FRAMES_DIR / ad_id
    if frame_dir.is_dir():
        for p in sorted(frame_dir.iterdir()):
            m = ORIG_RE.match(p.name)
            if m:
                out["orig"].append((m.group(1), p))

    img_dir = IMAGES_DIR / ad_id
    if img_dir.is_dir():
        for p in sorted(img_dir.iterdir()):
            m = GEN_RE.match(p.name)
            if m:
                out["gen"].append((m.group(1), m.group(2), p))
                continue
            m = CHAR_RE.match(p.name)
            if m:
                out["char"].append((m.group(1), p))

    return out


def upload_for_ad(s3, env: dict, ad_id: str, *, dry_run: bool, log) -> dict:
    """Upload all images for one ad. Returns the sidecar dict that gets written."""
    bucket = env["R2_BUCKET"]
    found = collect_images_for(ad_id)

    sidecar: dict = {
        "ad_library_id": ad_id,
        "orig": {},
        "gen": {},
        "char": {},
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
    }

    counts = {"orig_uploaded": 0, "orig_skipped": 0,
              "gen_uploaded": 0, "gen_skipped": 0,
              "char_uploaded": 0, "char_skipped": 0,
              "failed": 0}

    # --- original frames ---
    for scene_n, path in found["orig"]:
        key = orig_frame_key(ad_id, int(scene_n))
        if dry_run:
            sidecar["orig"][scene_n] = public_url_for(env, key) + "  [DRY-RUN]"
            counts["orig_uploaded"] += 1
            continue
        # Already-on-R2 fast path — read the URL, don't waste a PUT
        if object_exists(s3, bucket, key) and path.stat().st_size == _r2_size(s3, bucket, key):
            sidecar["orig"][scene_n] = public_url_for(env, key)
            counts["orig_skipped"] += 1
            continue
        try:
            url = upload_with_retry(s3, env, path, key)
            sidecar["orig"][scene_n] = url
            counts["orig_uploaded"] += 1
        except Exception as e:
            counts["failed"] += 1
            log(f"  [{ad_id}] orig_{scene_n} FAILED: {type(e).__name__}: {e}")

    # --- generated panels ---
    for scene_n, pos, path in found["gen"]:
        key = gen_panel_key(ad_id, int(scene_n), pos)
        slot = f"{scene_n}_{pos}"
        if dry_run:
            sidecar["gen"][slot] = public_url_for(env, key) + "  [DRY-RUN]"
            counts["gen_uploaded"] += 1
            continue
        if object_exists(s3, bucket, key) and path.stat().st_size == _r2_size(s3, bucket, key):
            sidecar["gen"][slot] = public_url_for(env, key)
            counts["gen_skipped"] += 1
            continue
        try:
            url = upload_with_retry(s3, env, path, key)
            sidecar["gen"][slot] = url
            counts["gen_uploaded"] += 1
        except Exception as e:
            counts["failed"] += 1
            log(f"  [{ad_id}] gen_{slot} FAILED: {type(e).__name__}: {e}")

    # --- character sheets ---
    for char_id, path in found["char"]:
        key = char_sheet_key(ad_id, char_id)
        if dry_run:
            sidecar["char"][char_id] = public_url_for(env, key) + "  [DRY-RUN]"
            counts["char_uploaded"] += 1
            continue
        if object_exists(s3, bucket, key) and path.stat().st_size == _r2_size(s3, bucket, key):
            sidecar["char"][char_id] = public_url_for(env, key)
            counts["char_skipped"] += 1
            continue
        try:
            url = upload_with_retry(s3, env, path, key)
            sidecar["char"][char_id] = url
            counts["char_uploaded"] += 1
        except Exception as e:
            counts["failed"] += 1
            log(f"  [{ad_id}] char_{char_id} FAILED: {type(e).__name__}: {e}")

    # Persist sidecar
    img_dir = IMAGES_DIR / ad_id
    img_dir.mkdir(parents=True, exist_ok=True)
    side_path = img_dir / "r2_urls.json"
    side_path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False))

    log(f"  [{ad_id}] orig +{counts['orig_uploaded']}/=={counts['orig_skipped']}  "
        f"gen +{counts['gen_uploaded']}/=={counts['gen_skipped']}  "
        f"char +{counts['char_uploaded']}/=={counts['char_skipped']}  "
        f"failed={counts['failed']}")

    return sidecar


def _r2_size(s3, bucket: str, key: str) -> int:
    try:
        h = s3.head_object(Bucket=bucket, Key=key)
        return int(h.get("ContentLength", -1))
    except Exception:
        return -1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competitor", required=True,
                    help="Competitor slug — used only for log labelling here; "
                         "image keys are namespaced by ad_library_id so the slug "
                         "doesn't actually appear in R2 paths.")
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    env = load_env()
    s3 = None if args.dry_run else make_r2_client(env)

    print(f"Stage 4.5 — uploading per-ad images for {len(args.ids)} videos "
          f"(competitor={args.competitor}, dry_run={args.dry_run})")
    print(f"           bucket={env['R2_BUCKET']}  base={env['R2_PUBLIC_URL_BASE']}")

    def log(msg: str) -> None:
        print(msg, flush=True)

    total_failed = 0
    for ad_id in args.ids:
        sidecar = upload_for_ad(s3, env, ad_id, dry_run=args.dry_run, log=log)
        # if the sidecar has empty kinds and no files existed at all, that's
        # OK (e.g. image-only ad with no gen panels yet) — only count true
        # upload errors as failures.

    print(f"\nStage 4.5 done — sidecars written to step4_workspace/images/<id>/r2_urls.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
