#!/usr/bin/env python3
"""
Step 4 — Stage 8 (Google): upload the two .docx files per ad to R2 and
update master/{competitor}.csv with the four URL columns.

Reads step4_workspace/docs/<ckey>_competitor_analysis.docx and
_supernova_rewrite.docx, uploads them to R2, writes the public URLs into the
master CSV's:
  - competitor_analysis_docx_r2_url
  - supernova_rewrite_docx_r2_url

Also reads step4_workspace/image_urls/<ckey>.json (written by Stage 6a) and
JSON-stringifies the two image arrays into the master CSV's:
  - competitor_analysis_image_r2_urls
  - supernova_rewrite_image_r2_urls

R2 key naming for docs: `{ckey}_competitor_analysis.docx` (or `g_{…}` if using
the FB pipeline's shared bucket — auto-detected from R2_BUCKET).

Per-row checkpointing of the master CSV survives Cowork's bash cap.

Stage 7a (step4_audit_docs.py) should have been run first. This script does NOT
re-audit; it trusts the audit's PASS/FAIL. If an operator runs it on a FAIL-state
ckey, the upload proceeds anyway (because the audit report is advisory at this
script's layer) — but the maintainer should normally gate the run.

Usage:
    python3 scripts/step4_upload_and_update.py --competitor zinglish <creative_id1> ...
    python3 scripts/step4_upload_and_update.py --competitor zinglish CR123 CR456_v2

Idempotent on re-run.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import sys
from datetime import date
from typing import Tuple

WORKSPACE = pathlib.Path("step4_workspace")
DOCS_DIR = WORKSPACE / "docs"
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


def upload_one(s3, bucket: str, local_path: pathlib.Path, key: str) -> bool:
    try:
        with open(local_path, "rb") as fh:
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=fh,
                ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        return True
    except Exception as e:
        print(f"  upload FAILED for {key}: {type(e).__name__}: {e}")
        return False


def docx_r2_key(creative_id: str, variant_index: int, suffix: str, bucket_name: str) -> str:
    """Build the R2 key for a docx. Prepend g_ if using the shared FB bucket.
    variant_index=0 → {creative_id}_{suffix}.docx
    variant_index=N≥1 → {creative_id}_v{N+1}_{suffix}.docx
    """
    v_suffix = "" if variant_index == 0 else f"_v{variant_index + 1}"
    base = f"{creative_id}{v_suffix}_{suffix}.docx"
    if bucket_name.lower() in ("video-ads",):
        return f"g_{base}"
    return base


def creative_key(creative_id: str, variant_index: int) -> str:
    """Unique workspace key for sidecars/docs: '{creative_id}' or '{creative_id}_v{N+1}'."""
    return creative_id if variant_index == 0 else f"{creative_id}_v{variant_index + 1}"


def load_image_urls_sidecar(ckey: str) -> dict:
    """Read step4_workspace/image_urls/{ckey}.json. Returns dict with two arrays
    (competitor_analysis_images, supernova_rewrite_images), each entry a dict with
    type/scene_n/r2_url/local_filename/etc. Returns empty arrays if file missing."""
    p = URLS_DIR / f"{ckey}.json"
    blank = {"competitor_analysis_images": [], "supernova_rewrite_images": []}
    if not p.exists():
        return blank
    try:
        data = json.loads(p.read_text())
        data.setdefault("competitor_analysis_images", [])
        data.setdefault("supernova_rewrite_images", [])
        return data
    except (json.JSONDecodeError, OSError):
        return blank


def image_urls_to_csv_value(image_list: list[dict]) -> str:
    """Compact JSON-stringify an image array for storage in a single CSV cell.
    Keep only the relational fields: type, scene_n, position, character_id, r2_url.
    Drop r2_key and local_filename (those are internal/diagnostic)."""
    compact = []
    for img in image_list:
        entry = {"type": img.get("type"), "r2_url": img.get("r2_url")}
        for k in ("scene_n", "position", "character_id"):
            if k in img:
                entry[k] = img[k]
        compact.append(entry)
    return json.dumps(compact, separators=(",", ":"), ensure_ascii=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competitor", required=True)
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--master-dir", default="master")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    env = load_env()
    competitor = args.competitor.lower().strip()
    master_path = pathlib.Path(args.master_dir) / f"{competitor}.csv"
    if not master_path.exists():
        sys.exit(f"[error] master CSV not found: {master_path}")

    s3 = None if args.dry_run else r2_client(env)
    public_base = env["R2_PUBLIC_URL_BASE"]
    bucket = env["R2_BUCKET"]

    with master_path.open(encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
        cols = list(rdr.fieldnames or [])

    for c in ("competitor_analysis_docx_r2_url", "supernova_rewrite_docx_r2_url",
              "competitor_analysis_image_r2_urls", "supernova_rewrite_image_r2_urls"):
        if c not in cols:
            cols.append(c)
            for r in rows:
                r.setdefault(c, "")

    # Index master rows by (creative_id, variant_index)
    def vi_of(r: dict) -> int:
        try:
            return int((r.get("variant_index") or "0").strip() or "0")
        except (ValueError, AttributeError):
            return 0

    by_key: dict[Tuple[str, int], dict] = {}
    for r in rows:
        cid = (r.get("creative_id") or "").strip()
        if cid:
            by_key[(cid, vi_of(r))] = r

    today_str = date.today().isoformat()
    uploaded = 0
    updated = 0
    skipped = 0
    failed = 0

    for raw_id in args.ids:
        # Accept either "{creative_id}" or "{creative_id}_v{N+1}" forms from the operator
        m = raw_id.rsplit("_v", 1)
        if len(m) == 2 and m[1].isdigit():
            creative_id, variant_index = m[0], int(m[1]) - 1
        else:
            creative_id, variant_index = raw_id, 0

        ckey = creative_key(creative_id, variant_index)
        comp_doc = DOCS_DIR / f"{ckey}_competitor_analysis.docx"
        sn_doc = DOCS_DIR / f"{ckey}_supernova_rewrite.docx"

        if not comp_doc.exists() or not sn_doc.exists():
            print(f"  [{ckey}] SKIP — docs not built yet")
            skipped += 1
            continue

        if (creative_id, variant_index) not in by_key:
            print(f"  [{ckey}] SKIP — not in master CSV (cid={creative_id}, vi={variant_index})")
            skipped += 1
            continue

        comp_key = docx_r2_key(creative_id, variant_index, "competitor_analysis", bucket)
        sn_key = docx_r2_key(creative_id, variant_index, "supernova_rewrite", bucket)

        if args.dry_run:
            comp_url = f"{public_base}/{comp_key}  [DRY-RUN]"
            sn_url = f"{public_base}/{sn_key}  [DRY-RUN]"
            print(f"  [{ckey}] would upload + update master with URLs")
            uploaded += 2
        else:
            ok_comp = upload_one(s3, bucket, comp_doc, comp_key)
            ok_sn = upload_one(s3, bucket, sn_doc, sn_key)
            if not (ok_comp and ok_sn):
                failed += 1
                continue
            comp_url = f"{public_base}/{comp_key}"
            sn_url = f"{public_base}/{sn_key}"
            uploaded += 2

        # Load per-creative image URL sidecar (written by Stage 6a step4_upload_images.py)
        # and JSON-stringify the two arrays into the master CSV columns.
        sidecar = load_image_urls_sidecar(ckey)
        comp_img_csv = image_urls_to_csv_value(sidecar.get("competitor_analysis_images", []))
        sn_img_csv = image_urls_to_csv_value(sidecar.get("supernova_rewrite_images", []))

        r = by_key[(creative_id, variant_index)]
        r["competitor_analysis_docx_r2_url"] = comp_url
        r["supernova_rewrite_docx_r2_url"] = sn_url
        r["competitor_analysis_image_r2_urls"] = comp_img_csv
        r["supernova_rewrite_image_r2_urls"] = sn_img_csv
        r["latest_scrape_run_date"] = today_str
        updated += 1

        if not args.dry_run:
            tmp = master_path.with_suffix(master_path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
            os.replace(tmp, master_path)
        print(f"  [{ckey}] OK — uploaded both docs, master updated")

    print()
    print(f"Stage 7+8 done — uploaded={uploaded} files, updated={updated} master rows, "
          f"skipped={skipped}, failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
