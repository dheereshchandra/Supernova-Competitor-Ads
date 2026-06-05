#!/usr/bin/env python3
"""
Step 4 — Stages 7 + 8: upload the two .docx files per row to R2 and update
master/{competitor}.csv with the doc URL columns AND the three image-URL
columns produced by Stage 4.5.

Reads:
  - step4_workspace/docs/<id>_competitor_analysis.docx
  - step4_workspace/docs/<id>_supernova_rewrite.docx
  - step4_workspace/images/<id>/r2_urls.json  (from Stage 4.5)

Writes the following master CSV columns (HANDOVER §9.7):
  - competitor_analysis_docx_r2_url     (single URL)
  - supernova_rewrite_docx_r2_url       (single URL)
  - orig_frame_urls                     (JSON array of original-frame URLs, scene order)
  - gen_panel_urls                      (JSON array of regenerated-panel URLs)
  - char_sheet_urls                     (JSON array of character-sheet URLs)
  - latest_scrape_run_date              (today)

Per-row checkpointing of the master CSV survives Cowork's bash cap.

Usage:
    python3 scripts/step4_upload_and_update.py --competitor zinglish <id1> <id2> ...

Idempotent: re-running on the same id overwrites the R2 object and the master
row's columns. Safe to re-run.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import sys
from datetime import date

# r2_utils sits in the same scripts/ directory
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from r2_utils import (  # noqa: E402
    load_env, make_r2_client, public_url_for, upload_with_retry,
    content_type_for,
)


WORKSPACE = pathlib.Path("step4_workspace")
DOCS_DIR = WORKSPACE / "docs"
IMAGES_DIR = WORKSPACE / "images"


# All columns this stage owns. Mirrors MASTER_EXTRA_COLS in upload_to_r2.py.
DOC_URL_COLS = [
    "competitor_analysis_docx_r2_url",
    "supernova_rewrite_docx_r2_url",
]
IMAGE_URL_COLS = [
    "orig_frame_urls",
    "gen_panel_urls",
    "char_sheet_urls",
]
ALL_URL_COLS = DOC_URL_COLS + IMAGE_URL_COLS


def load_sidecar(ad_id: str) -> dict:
    """Return the Stage 4.5 sidecar or an empty skeleton if it's missing."""
    p = IMAGES_DIR / ad_id / "r2_urls.json"
    if not p.exists():
        return {"orig": {}, "gen": {}, "char": {}}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {"orig": {}, "gen": {}, "char": {}}


def sidecar_to_json_arrays(sidecar: dict) -> dict:
    """Project the sidecar dict into the three JSON-array columns we record.

    Order:
      - orig: by scene number (zero-padded keys -> natural sort)
      - gen:  by scene number then position
      - char: by character id (numeric if possible, else lexicographic)
    """
    orig = sidecar.get("orig") or {}
    gen = sidecar.get("gen") or {}
    char = sidecar.get("char") or {}

    orig_list = [orig[k] for k in sorted(orig.keys())]
    gen_list = [gen[k] for k in sorted(gen.keys())]

    def _char_sort_key(k: str):
        try:
            return (0, int(k))
        except ValueError:
            return (1, k)

    char_list = [char[k] for k in sorted(char.keys(), key=_char_sort_key)]

    return {
        "orig_frame_urls": json.dumps(orig_list, ensure_ascii=False),
        "gen_panel_urls": json.dumps(gen_list, ensure_ascii=False),
        "char_sheet_urls": json.dumps(char_list, ensure_ascii=False),
    }


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

    s3 = None if args.dry_run else make_r2_client(env)
    public_base = env["R2_PUBLIC_URL_BASE"]
    bucket = env["R2_BUCKET"]

    # Load master
    with master_path.open(encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
        cols = list(rdr.fieldnames or [])

    # Ensure every URL column exists in the master schema
    for c in ALL_URL_COLS:
        if c not in cols:
            cols.append(c)
            for r in rows:
                r.setdefault(c, "")

    # Index rows by ad_library_id for fast lookup
    by_id: dict[str, list[dict]] = {}
    for r in rows:
        aid = (r.get("ad_library_id") or "").strip()
        by_id.setdefault(aid, []).append(r)

    today_str = date.today().isoformat()
    uploaded = 0
    updated = 0
    skipped = 0
    failed = 0

    for ad_id in args.ids:
        comp_doc = DOCS_DIR / f"{ad_id}_competitor_analysis.docx"
        sn_doc = DOCS_DIR / f"{ad_id}_supernova_rewrite.docx"

        if not comp_doc.exists() or not sn_doc.exists():
            print(f"  [{ad_id}] SKIP — docs not built yet")
            skipped += 1
            continue

        if ad_id not in by_id:
            print(f"  [{ad_id}] SKIP — not in master CSV")
            skipped += 1
            continue

        # Flat naming for docs preserved — only the per-image keys use the
        # new images/<ad_id>/ layout.
        comp_key = f"{ad_id}_competitor_analysis.docx"
        sn_key = f"{ad_id}_supernova_rewrite.docx"

        sidecar = load_sidecar(ad_id)
        image_cols_payload = sidecar_to_json_arrays(sidecar)

        if args.dry_run:
            comp_url = public_url_for(env, comp_key) + "  [DRY-RUN]"
            sn_url = public_url_for(env, sn_key) + "  [DRY-RUN]"
            print(f"  [{ad_id}] would upload + update master with doc + image URLs")
            uploaded += 2
        else:
            try:
                comp_url = upload_with_retry(s3, env, comp_doc, comp_key)
                sn_url = upload_with_retry(s3, env, sn_doc, sn_key)
                uploaded += 2
            except Exception as e:
                print(f"  [{ad_id}] upload FAILED: {type(e).__name__}: {e}")
                failed += 1
                continue

        # Update all rows that match this ad_library_id.
        # (this propagates to all variant rows; per-variant docs would need
        # _v2 suffixes in the key — left for future enhancement, see HANDOVER §9.7)
        for r in by_id[ad_id]:
            r["competitor_analysis_docx_r2_url"] = comp_url
            r["supernova_rewrite_docx_r2_url"] = sn_url
            r.update(image_cols_payload)
            r["latest_scrape_run_date"] = today_str
            updated += 1

        # Checkpoint the master after every successful upload — survives interruptions
        if not args.dry_run:
            tmp = master_path.with_suffix(master_path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
            os.replace(tmp, master_path)
        n_orig = len(json.loads(image_cols_payload["orig_frame_urls"]))
        n_gen = len(json.loads(image_cols_payload["gen_panel_urls"]))
        n_char = len(json.loads(image_cols_payload["char_sheet_urls"]))
        print(f"  [{ad_id}] OK — uploaded docs; master got orig={n_orig} gen={n_gen} char={n_char}")

    print()
    print(f"Stage 7+8 done — uploaded={uploaded} doc files, updated={updated} master rows, "
          f"skipped={skipped}, failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
