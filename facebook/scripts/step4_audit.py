#!/usr/bin/env python3
"""
Step 4 — Audit step.

Runs the full URL-and-content audit on the deliverables produced by Stages 6
through 8, after R2 uploads have completed. This is the verification gate
the operator looks at before declaring a run "done".

For each ad_library_id passed in, the audit checks:

  1. Both docx files exist in step4_workspace/docs/
  2. verify_docs() programmatic checks pass (paragraph count, scene headings,
     no placeholders, image count == "Asset:" caption count, no missing-URL
     captions, sidecar consistency).
  3. Every hyperlink target in the docs HEAD-resolves on R2 (200/3xx).
  4. The master CSV row for the ad has all five URL columns populated:
       competitor_analysis_docx_r2_url
       supernova_rewrite_docx_r2_url
       orig_frame_urls
       gen_panel_urls
       char_sheet_urls
  5. orig_frame_urls / gen_panel_urls / char_sheet_urls parse as JSON arrays.
  6. Every URL in the master columns HEAD-resolves on R2.
  7. The URLs recorded in master match the URLs in the docs (no drift).

Usage:
    python3 scripts/step4_audit.py --competitor zinglish <id1> <id2> ...
    python3 scripts/step4_audit.py --competitor zinglish --all   # every ad with docs

Exit code: 0 if every audited ad passes, 1 if any audited ad fails.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from r2_utils import load_env, head_check  # noqa: E402
from step4_build_docs import (  # noqa: E402
    verify_docs, ASSET_CAPTION_PREFIX, _extract_hyperlinks,
)


WORKSPACE = pathlib.Path("step4_workspace")
DOCS_DIR = WORKSPACE / "docs"
SCENES_DIR = WORKSPACE / "scenes"
IMAGES_DIR = WORKSPACE / "images"


def _load_master(competitor: str) -> tuple[list[str], list[dict]]:
    path = pathlib.Path("master") / f"{competitor}.csv"
    if not path.exists():
        sys.exit(f"[error] master CSV not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        return list(rdr.fieldnames or []), list(rdr)


def _all_ids_with_docs() -> list[str]:
    """List every ad_library_id that has both docx files on disk."""
    seen: set[str] = set()
    for p in DOCS_DIR.glob("*_competitor_analysis.docx"):
        ad_id = p.name.removesuffix("_competitor_analysis.docx")
        if (DOCS_DIR / f"{ad_id}_supernova_rewrite.docx").exists():
            seen.add(ad_id)
    return sorted(seen)


def audit_one(ad_id: str, master_rows: list[dict], env: dict) -> list[str]:
    """Return a list of audit issues. Empty list = clean."""
    issues: list[str] = []
    comp_path = DOCS_DIR / f"{ad_id}_competitor_analysis.docx"
    sn_path = DOCS_DIR / f"{ad_id}_supernova_rewrite.docx"

    # Number of scenes — from decompose sidecar
    n_scenes = 0
    sidecar = SCENES_DIR / f"{ad_id}.json"
    if sidecar.exists():
        try:
            n_scenes = len(json.loads(sidecar.read_text())
                           .get("parsed", {}).get("scenes", []))
        except json.JSONDecodeError:
            pass

    # (1)+(2)+(3): docx structural + URL-HEAD checks
    issues.extend(verify_docs(ad_id, comp_path, sn_path, n_scenes,
                              check_urls=True, env=env))

    # (4)+(5)+(6)+(7): master CSV checks
    rows = [r for r in master_rows if (r.get("ad_library_id") or "").strip() == ad_id]
    if not rows:
        issues.append("master: no row found for this ad_library_id")
        return issues

    # All variant rows must agree on the URL columns (they're shared today).
    expected = {
        "competitor_analysis_docx_r2_url": None,
        "supernova_rewrite_docx_r2_url": None,
        "orig_frame_urls": None,
        "gen_panel_urls": None,
        "char_sheet_urls": None,
    }
    for col in expected:
        vals = sorted({(r.get(col) or "").strip() for r in rows})
        if len(vals) > 1:
            issues.append(f"master: column {col} has inconsistent values across variant rows: {vals}")
        v = (rows[0].get(col) or "").strip()
        if not v:
            issues.append(f"master: column {col} is empty")
        expected[col] = v

    # JSON-array columns must parse + every URL must resolve.
    for col in ("orig_frame_urls", "gen_panel_urls", "char_sheet_urls"):
        v = expected[col] or ""
        if not v:
            continue
        try:
            arr = json.loads(v)
        except json.JSONDecodeError:
            issues.append(f"master: {col} is not valid JSON ({v[:80]}...)")
            continue
        if not isinstance(arr, list):
            issues.append(f"master: {col} is JSON but not a list")
            continue
        for u in arr:
            ok, status = head_check(u)
            if not ok:
                issues.append(f"master: {col} URL not reachable (HTTP {status}): {u}")

    # Cross-check: docx hyperlinks must be a SUPERSET of the URLs in the master arrays.
    doc_urls: set[str] = set()
    try:
        from docx import Document
        for path in (comp_path, sn_path):
            if path.exists():
                doc_urls.update(_extract_hyperlinks(Document(str(path))))
    except Exception as e:
        issues.append(f"audit: failed to enumerate docx hyperlinks: {e}")

    for col in ("orig_frame_urls", "gen_panel_urls", "char_sheet_urls"):
        v = expected[col] or ""
        if not v:
            continue
        try:
            arr = json.loads(v)
        except json.JSONDecodeError:
            continue
        missing = [u for u in arr if u not in doc_urls]
        if missing:
            issues.append(f"audit: {col} has {len(missing)} URL(s) not present as docx "
                          f"hyperlinks (first: {missing[0]})")

    # Doc URLs themselves should HEAD-resolve too.
    for col in ("competitor_analysis_docx_r2_url", "supernova_rewrite_docx_r2_url"):
        v = expected[col]
        if v:
            ok, status = head_check(v)
            if not ok:
                issues.append(f"master: {col} not reachable (HTTP {status}): {v}")

    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competitor", required=True)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("ids", nargs="*", default=[])
    g.add_argument("--all", action="store_true",
                   help="Audit every ad_library_id that has both docs on disk.")
    ap.add_argument("--no-head-check", action="store_true",
                    help="Skip HTTP HEAD checks (offline mode — only structural checks).")
    args = ap.parse_args()

    env = load_env()
    competitor = args.competitor.lower().strip()
    _, master_rows = _load_master(competitor)

    if args.all:
        ids = _all_ids_with_docs()
    else:
        ids = list(args.ids)
    if not ids:
        sys.exit("[error] pass ad_library_ids or --all")

    print(f"Step 4 audit — competitor={competitor}  ads={len(ids)}  "
          f"head_checks={'off' if args.no_head_check else 'on'}")
    print()

    if args.no_head_check:
        # Monkey-patch head_check to a no-op for offline runs.
        import r2_utils
        r2_utils.head_check = lambda url, timeout=8.0: (True, 200)  # type: ignore

    fail = 0
    for ad_id in ids:
        issues = audit_one(ad_id, master_rows, env)
        if issues:
            fail += 1
            print(f"  [{ad_id}] FAIL ({len(issues)} issue(s))")
            for iss in issues:
                print(f"      - {iss}")
        else:
            print(f"  [{ad_id}] PASS")

    print()
    print(f"Audit complete — {len(ids) - fail} pass, {fail} fail")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
