#!/usr/bin/env python3
"""
Backfill Stage 4.5 + the docx rebuild for ads whose docs were produced before
HANDOVER §9.7 (per-image R2 URLs) shipped.

What it does, per ad_library_id:

  1. Calls step4_upload_images.upload_for_ad — uploads every local frame /
     panel / character sheet to R2 under images/<ad_id>/... and writes the
     r2_urls.json sidecar.
  2. Re-runs step4_build_docs.build_competitor_doc + build_supernova_doc.
     They now read the sidecar and embed the Asset hyperlink under each image.
  3. Calls step4_upload_and_update — re-uploads the rebuilt docx files and
     patches the master CSV row's five URL columns.
  4. Calls step4_audit.audit_one — confirms everything resolves.

Safe to re-run: every underlying step is idempotent. If any stage fails the
script reports the failure and moves to the next ad.

Usage:
    # Backfill specific ads:
    python3 scripts/backfill_step4_images.py --competitor zinglish 973909435205486 ...
    # Backfill every ad that has both docs already on disk:
    python3 scripts/backfill_step4_images.py --competitor zinglish --all
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from r2_utils import load_env, make_r2_client  # noqa: E402
from step4_upload_images import upload_for_ad  # noqa: E402
from step4_build_docs import build_competitor_doc, build_supernova_doc, verify_docs  # noqa: E402
from step4_upload_and_update import (  # noqa: E402
    load_sidecar, sidecar_to_json_arrays, ALL_URL_COLS,
)
from r2_utils import upload_with_retry, public_url_for  # noqa: E402
from step4_audit import audit_one  # noqa: E402


WORKSPACE = pathlib.Path("step4_workspace")
DOCS_DIR = WORKSPACE / "docs"
SCENES_DIR = WORKSPACE / "scenes"


def _load_master(competitor: str) -> tuple[pathlib.Path, list[str], list[dict]]:
    master_path = pathlib.Path("master") / f"{competitor}.csv"
    if not master_path.exists():
        sys.exit(f"[error] master CSV not found: {master_path}")
    with master_path.open(encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
        cols = list(rdr.fieldnames or [])
    for c in ALL_URL_COLS:
        if c not in cols:
            cols.append(c)
            for r in rows:
                r.setdefault(c, "")
    return master_path, cols, rows


def _write_master(path: pathlib.Path, cols: list[str], rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def _all_ids_with_docs() -> list[str]:
    seen: set[str] = set()
    for p in DOCS_DIR.glob("*_competitor_analysis.docx"):
        ad_id = p.name.removesuffix("_competitor_analysis.docx")
        if (DOCS_DIR / f"{ad_id}_supernova_rewrite.docx").exists():
            seen.add(ad_id)
    return sorted(seen)


def _all_ids_with_workspace() -> list[str]:
    """Every ad_library_id that has either frames or images on disk."""
    seen: set[str] = set()
    for sub in (WORKSPACE / "frames").glob("*"):
        if sub.is_dir():
            seen.add(sub.name)
    for sub in (WORKSPACE / "images").glob("*"):
        if sub.is_dir():
            seen.add(sub.name)
    return sorted(seen)


def backfill_one(ad_id: str, competitor: str, s3, env: dict,
                 master_cols: list[str], master_rows: list[dict],
                 master_path: pathlib.Path, *, audit: bool, dry_run: bool, log) -> bool:
    """Returns True on full success, False if anything failed."""
    log(f"\n=== {ad_id} ===")

    # 1. Stage 4.5: upload every image and write r2_urls.json
    log("  [1/4] uploading images to R2 + writing sidecar")
    sidecar = upload_for_ad(s3, env, ad_id, dry_run=dry_run, log=log)

    # 2. Rebuild both docs (sidecar is now present)
    log("  [2/4] rebuilding both .docx files with Asset captions")
    decompose_path = SCENES_DIR / f"{ad_id}.json"
    rewrite_path = SCENES_DIR / f"{ad_id}.supernova.json"
    if not decompose_path.exists():
        log(f"      SKIP — no decompose sidecar at {decompose_path}")
        return False
    if not rewrite_path.exists():
        log(f"      SKIP — no supernova rewrite sidecar at {rewrite_path}")
        return False
    decompose = json.loads(decompose_path.read_text())
    rewrite = json.loads(rewrite_path.read_text())
    n_scenes = len(decompose.get("parsed", {}).get("scenes", []))

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    comp_path = DOCS_DIR / f"{ad_id}_competitor_analysis.docx"
    sn_path = DOCS_DIR / f"{ad_id}_supernova_rewrite.docx"
    try:
        build_competitor_doc(ad_id, competitor, decompose, comp_path, log)
        build_supernova_doc(ad_id, competitor, decompose, rewrite, sn_path, log)
    except Exception as e:
        log(f"      BUILD FAILED: {type(e).__name__}: {e}")
        return False

    issues = verify_docs(ad_id, comp_path, sn_path, n_scenes,
                        check_urls=False, env=env)
    if issues:
        log("      verify (offline) reports:")
        for iss in issues:
            log(f"        - {iss}")
        # Continue — verify_urls will give the final word after upload.

    # 3. Stage 7+8: re-upload docs and patch master row
    log("  [3/4] re-uploading docs + patching master row")
    if dry_run:
        comp_url = public_url_for(env, f"{ad_id}_competitor_analysis.docx") + "  [DRY-RUN]"
        sn_url = public_url_for(env, f"{ad_id}_supernova_rewrite.docx") + "  [DRY-RUN]"
    else:
        try:
            comp_url = upload_with_retry(s3, env, comp_path, f"{ad_id}_competitor_analysis.docx")
            sn_url = upload_with_retry(s3, env, sn_path, f"{ad_id}_supernova_rewrite.docx")
        except Exception as e:
            log(f"      DOC UPLOAD FAILED: {type(e).__name__}: {e}")
            return False
    image_payload = sidecar_to_json_arrays(load_sidecar(ad_id))
    today_str = date.today().isoformat()
    matched = 0
    for r in master_rows:
        if (r.get("ad_library_id") or "").strip() == ad_id:
            r["competitor_analysis_docx_r2_url"] = comp_url
            r["supernova_rewrite_docx_r2_url"] = sn_url
            r.update(image_payload)
            r["latest_scrape_run_date"] = today_str
            matched += 1
    if matched == 0:
        log(f"      master: no row matched ad_library_id={ad_id} (will skip master write)")
    elif not dry_run:
        _write_master(master_path, master_cols, master_rows)
        log(f"      master: updated {matched} row(s)")

    # 4. Audit
    if audit and not dry_run:
        log("  [4/4] audit (HEAD-checking every URL)")
        issues = audit_one(ad_id, master_rows, env)
        if issues:
            log(f"      AUDIT FAILED ({len(issues)} issue(s)):")
            for iss in issues:
                log(f"        - {iss}")
            return False
        log("      audit PASS")
    else:
        log("  [4/4] audit skipped (dry-run)")

    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competitor", required=True,
                    help="Competitor slug — used for log labelling and master/{competitor}.csv resolution.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("ids", nargs="*", default=[])
    g.add_argument("--all-with-docs", action="store_true",
                   help="Backfill every ad that has both docx files on disk.")
    g.add_argument("--all-with-workspace", action="store_true",
                   help="Backfill every ad that has frames/ or images/ on disk, "
                        "even if no docx exists yet (will build them).")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-audit", action="store_true",
                    help="Skip the per-ad audit step (HEAD checks).")
    args = ap.parse_args()

    env = load_env()
    competitor = args.competitor.lower().strip()
    s3 = None if args.dry_run else make_r2_client(env)

    if args.all_with_docs:
        ids = _all_ids_with_docs()
    elif args.all_with_workspace:
        ids = _all_ids_with_workspace()
    else:
        ids = list(args.ids)

    if not ids:
        sys.exit("[error] pass ad_library_ids or --all-with-docs / --all-with-workspace")

    master_path, master_cols, master_rows = _load_master(competitor)
    print(f"Backfill — competitor={competitor}  ads={len(ids)}  dry_run={args.dry_run}")
    print(f"           master={master_path}  bucket={env['R2_BUCKET']}")

    def log(msg: str) -> None:
        print(msg, flush=True)

    passed = 0
    failed = 0
    for ad_id in ids:
        ok = backfill_one(ad_id, competitor, s3, env,
                          master_cols, master_rows, master_path,
                          audit=not args.no_audit, dry_run=args.dry_run, log=log)
        if ok:
            passed += 1
        else:
            failed += 1

    print()
    print(f"Backfill done — {passed} OK, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
