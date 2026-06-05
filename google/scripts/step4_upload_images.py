#!/usr/bin/env python3
"""
Step 4 — Stage 6a (Google): upload per-creative images to R2 before docs are built.

For each (creative_id, variant_index) in the args, uploads:
  - Original frame screenshots:    step4_workspace/frames/{ckey}/orig_NN.jpg
  - Clean regenerated panels:      step4_workspace/images/{ckey}/gen_NN_pos.jpg
  - Character reference sheets:    step4_workspace/images/{ckey}/char_X_sheet.jpg

R2 key naming (g_ prefix added automatically when sharing the FB bucket):
  - {ckey}_img_orig_NN.jpg
  - {ckey}_img_panel_NN_pos.jpg
  - {ckey}_img_char_X.jpg
where ckey = creative_id (variant 0) or {creative_id}_v{N+1} (variant N≥1).

Writes a URL map sidecar at step4_workspace/image_urls/{ckey}.json:
  {
    "competitor_analysis_images": [
      {"type": "original_frame", "scene_n": 1, "r2_key": "...", "r2_url": "...", "local_filename": "orig_01.jpg"},
      {"type": "clean_panel",    "scene_n": 1, "position": "full", "r2_key": "...", ...},
      {"type": "character_sheet","character_id": "A", "r2_key": "...", ...}
    ],
    "supernova_rewrite_images": [
      // clean panels only — the Supernova rewrite doc doesn't embed originals or character sheets
    ]
  }

The sidecar is the source of truth for Stage 6b (build docs) and Stage 8 (master CSV update).

Idempotent: skips images already recorded in the sidecar. Safe to re-run after Cowork's
45-second bash cap kills it mid-way — already-uploaded images carry forward via the sidecar.

Usage:
    python3 scripts/step4_upload_images.py --competitor zinglish <creative_id1> ...
    python3 scripts/step4_upload_images.py --competitor zinglish CR123 CR456_v2 --dry-run
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Tuple

WORKSPACE = pathlib.Path("step4_workspace")
FRAMES_DIR = WORKSPACE / "frames"
IMAGES_DIR = WORKSPACE / "images"
URLS_DIR = WORKSPACE / "image_urls"


def load_env() -> dict:
    env = {}
    for line in pathlib.Path(".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def r2_client(env: dict):
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=env["R2_S3_ENDPOINT"],
        aws_access_key_id=env["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def creative_key(creative_id: str, variant_index: int) -> str:
    """Workspace key: 'CR123' for variant 0; 'CR123_v2' for variant 1, etc.
    Matches the convention used by step4_build_docs.py and step4_upload_and_update.py."""
    return creative_id if variant_index == 0 else f"{creative_id}_v{variant_index + 1}"


def parse_id(raw: str) -> Tuple[str, int]:
    """Accept either '{creative_id}' or '{creative_id}_v{N+1}' from the operator."""
    m = raw.rsplit("_v", 1)
    if len(m) == 2 and m[1].isdigit():
        return m[0], int(m[1]) - 1
    return raw, 0


def image_r2_key(ckey: str, kind: str, ident: str, bucket_name: str) -> str:
    """Build R2 key for an image. Adds g_ prefix if sharing the FB bucket.
    kind: 'orig' | 'panel' | 'char'
    ident: scene_n string for orig/panel ('01' or '01_full'); character id for char ('A')."""
    base = f"{ckey}_img_{kind}_{ident}.jpg"
    if bucket_name.lower() in ("video-ads",):
        return f"g_{base}"
    return base


def upload_image(s3, bucket: str, local_path: pathlib.Path, r2_key: str) -> bool:
    """Upload one image to R2 as image/jpeg. Returns True on success."""
    try:
        with open(local_path, "rb") as fh:
            s3.put_object(
                Bucket=bucket, Key=r2_key, Body=fh, ContentType="image/jpeg",
            )
        return True
    except Exception as e:
        print(f"  upload FAILED for {r2_key}: {type(e).__name__}: {e}")
        return False


def load_existing_sidecar(path: pathlib.Path) -> dict:
    if not path.exists():
        return {"competitor_analysis_images": [], "supernova_rewrite_images": []}
    try:
        data = json.loads(path.read_text())
        # Ensure both keys exist
        data.setdefault("competitor_analysis_images", [])
        data.setdefault("supernova_rewrite_images", [])
        return data
    except (json.JSONDecodeError, OSError):
        return {"competitor_analysis_images": [], "supernova_rewrite_images": []}


def write_sidecar(path: pathlib.Path, sidecar: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sidecar, indent=2))


def collect_seen_r2_keys(sidecar: dict) -> set:
    seen = set()
    for k in ("competitor_analysis_images", "supernova_rewrite_images"):
        for img in sidecar.get(k, []):
            if "r2_key" in img:
                seen.add(img["r2_key"])
    return seen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competitor", required=True,
                    help="Competitor slug (for logging only; sidecars are keyed on creative_id).")
    ap.add_argument("ids", nargs="+",
                    help="creative_id (variant 0) or creative_id_v{N+1} for variants.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would be uploaded; write sidecars with DRY-RUN URLs.")
    args = ap.parse_args()

    URLS_DIR.mkdir(parents=True, exist_ok=True)
    env = load_env()
    public_base = env["R2_PUBLIC_URL_BASE"]
    bucket = env["R2_BUCKET"]
    s3 = None if args.dry_run else r2_client(env)

    print(f"Stage 6a — uploading per-creative images for {len(args.ids)} ad(s)")
    print(f"  competitor: {args.competitor}")
    print(f"  bucket:     {bucket}  ({public_base})")
    print(f"  dry-run:    {args.dry_run}")
    print()

    uploaded_total = 0
    skipped_total = 0
    failed_total = 0
    no_workspace = 0

    for raw in args.ids:
        creative_id, variant_index = parse_id(raw)
        ckey = creative_key(creative_id, variant_index)

        # NOTE: Stage 2 (frames) and Stage 4 (panels) and Stage 3 (character sheets)
        # currently write to creative_id-based directories (not ckey-based). Sidecar
        # is keyed on ckey for variant-aware doc naming, but image lookup is by creative_id.
        frame_dir = FRAMES_DIR / creative_id
        img_dir = IMAGES_DIR / creative_id

        if not frame_dir.exists() and not img_dir.exists():
            print(f"  [{ckey}] SKIP — no workspace directories (Stages 2-4 not yet run for this id)")
            no_workspace += 1
            continue

        sidecar_path = URLS_DIR / f"{ckey}.json"
        sidecar = load_existing_sidecar(sidecar_path)
        comp_imgs = sidecar["competitor_analysis_images"]
        sup_imgs = sidecar["supernova_rewrite_images"]
        seen_keys = collect_seen_r2_keys(sidecar)

        ad_uploaded = 0
        ad_skipped = 0
        ad_failed = 0

        # 1. Original frames → competitor analysis doc only
        if frame_dir.exists():
            for frame in sorted(frame_dir.glob("orig_*.jpg")):
                stem = frame.stem  # "orig_01"
                parts = stem.split("_")
                if len(parts) < 2 or not parts[1].isdigit():
                    continue
                scene_n = int(parts[1])
                r2_key = image_r2_key(ckey, "orig", f"{scene_n:02d}", bucket)
                if r2_key in seen_keys:
                    ad_skipped += 1
                    continue
                if args.dry_run:
                    url = f"{public_base}/{r2_key}  [DRY-RUN]"
                    ok = True
                else:
                    ok = upload_image(s3, bucket, frame, r2_key)
                    url = f"{public_base}/{r2_key}" if ok else ""
                if ok:
                    comp_imgs.append({
                        "type": "original_frame",
                        "scene_n": scene_n,
                        "r2_key": r2_key,
                        "r2_url": url,
                        "local_filename": frame.name,
                    })
                    seen_keys.add(r2_key)
                    ad_uploaded += 1
                    # Checkpoint after every successful upload — survives bash-cap interruptions
                    write_sidecar(sidecar_path, sidecar)
                else:
                    ad_failed += 1

        # 2. Clean panels → BOTH docs (competitor + supernova)
        if img_dir.exists():
            for panel in sorted(img_dir.glob("gen_*.jpg")):
                stem = panel.stem  # "gen_01_full"
                parts = stem.split("_", 2)
                if len(parts) < 3 or not parts[1].isdigit():
                    continue
                scene_n = int(parts[1])
                position = parts[2]
                r2_key = image_r2_key(ckey, "panel", f"{scene_n:02d}_{position}", bucket)
                if r2_key in seen_keys:
                    ad_skipped += 1
                    continue
                if args.dry_run:
                    url = f"{public_base}/{r2_key}  [DRY-RUN]"
                    ok = True
                else:
                    ok = upload_image(s3, bucket, panel, r2_key)
                    url = f"{public_base}/{r2_key}" if ok else ""
                if ok:
                    entry = {
                        "type": "clean_panel",
                        "scene_n": scene_n,
                        "position": position,
                        "r2_key": r2_key,
                        "r2_url": url,
                        "local_filename": panel.name,
                    }
                    comp_imgs.append(entry)
                    sup_imgs.append(dict(entry))
                    seen_keys.add(r2_key)
                    ad_uploaded += 1
                    write_sidecar(sidecar_path, sidecar)
                else:
                    ad_failed += 1

        # 3. Character reference sheets → competitor analysis doc only
        if img_dir.exists():
            for char_sheet in sorted(img_dir.glob("char_*_sheet.jpg")):
                stem = char_sheet.stem  # "char_A_sheet"
                parts = stem.split("_")
                if len(parts) < 3:
                    continue
                char_id = parts[1]
                r2_key = image_r2_key(ckey, "char", char_id, bucket)
                if r2_key in seen_keys:
                    ad_skipped += 1
                    continue
                if args.dry_run:
                    url = f"{public_base}/{r2_key}  [DRY-RUN]"
                    ok = True
                else:
                    ok = upload_image(s3, bucket, char_sheet, r2_key)
                    url = f"{public_base}/{r2_key}" if ok else ""
                if ok:
                    comp_imgs.append({
                        "type": "character_sheet",
                        "character_id": char_id,
                        "r2_key": r2_key,
                        "r2_url": url,
                        "local_filename": char_sheet.name,
                    })
                    seen_keys.add(r2_key)
                    ad_uploaded += 1
                    write_sidecar(sidecar_path, sidecar)
                else:
                    ad_failed += 1

        # Final sidecar write (also captures any zero-upload state for clarity)
        write_sidecar(sidecar_path, sidecar)
        print(f"  [{ckey}] uploaded={ad_uploaded} skipped={ad_skipped} failed={ad_failed}  "
              f"sidecar→ {len(comp_imgs)} competitor + {len(sup_imgs)} supernova images")
        uploaded_total += ad_uploaded
        skipped_total += ad_skipped
        failed_total += ad_failed

    print()
    print(f"Stage 6a done — uploaded={uploaded_total} skipped={skipped_total} "
          f"failed={failed_total} no-workspace={no_workspace}")
    return 0 if failed_total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
