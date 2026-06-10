#!/usr/bin/env python3
"""
Step 4 — Stage 9: store the deliverable docs as collaborative GOOGLE DOCS + record the links.

For each ad it uploads the two already-built .docx files and CONVERTS them to native Google Docs in a
Google Workspace **Shared Drive** (so the team owns + collaborates: open, assign, edit, comment, verify),
then writes the Google-Doc links into the per-competitor master CSV (alongside the existing R2 links).

Converts both:
  step4_workspace/docs/<id>_supernova_rewrite.docx   -> master col  supernova_rewrite_gdoc_url
  step4_workspace/docs/<id>_competitor_analysis.docx -> master col  competitor_analysis_gdoc_url

Idempotency = COLLABORATION PROTECTION. A git-tracked sidecar  step4_workspace/scenes/<id>.gdocs.json
remembers each Doc's file_id. On re-run (no --force) we REUSE the existing Docs — never clobbering a Doc
the team has commented on / assigned / edited. --force creates a NEW versioned Doc and leaves the old one
(with its comments) untouched.

One-time human setup (service account + Shared Drive) is documented in facebook/HANDOVER.md §9.10.

Usage:
    python3.13 scripts/step4_upload_gdocs.py --competitor <slug> <id1> <id2> ... [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import sys
import time
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from r2_utils import load_env  # noqa: E402
import _gdrive  # noqa: E402

WORKSPACE = pathlib.Path("step4_workspace")
DOCS_DIR = WORKSPACE / "docs"
SCENES_DIR = WORKSPACE / "scenes"   # git-tracked — the .gdocs.json sidecar lives here

# (sidecar_key, docx suffix, master column, title suffix)
DOC_SPECS = [
    ("supernova_doc", "_supernova_rewrite.docx", "supernova_rewrite_gdoc_url", "Supernova Rewrite"),
    ("competitor_doc", "_competitor_analysis.docx", "competitor_analysis_gdoc_url", "Competitor Analysis"),
]
GDOC_URL_COLS = [spec[2] for spec in DOC_SPECS]


def read_master(master: pathlib.Path):
    with master.open(encoding="utf-8-sig", newline="") as fh:
        r = csv.DictReader(fh)
        return list(r), list(r.fieldnames or [])


def sidecar_path(ad_id: str) -> pathlib.Path:
    return SCENES_DIR / f"{ad_id}.gdocs.json"


def load_sidecar(ad_id: str) -> dict:
    p = sidecar_path(ad_id)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}


def write_sidecar(ad_id: str, data: dict) -> None:
    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    p = sidecar_path(ad_id)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    os.replace(tmp, p)


def _retry(fn, attempts: int = 3):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — transient Drive 429/5xx
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def process_ad(svc, env: dict, competitor: str, ad_id: str,
               folder_cache: dict, force: bool, dry_run: bool):
    """Returns (payload_or_None, status). payload = {master_col: link}. status in
    {missing, dry-run, reused, adopted, created}."""
    docx_paths = {key: DOCS_DIR / f"{ad_id}{suffix}" for key, suffix, _, _ in DOC_SPECS}
    missing = [p.name for p in docx_paths.values() if not p.exists()]
    if missing:
        print(f"  [{ad_id}] SKIP — docs not built yet ({', '.join(missing)})")
        return None, "missing"

    side = load_sidecar(ad_id)

    # ----- dry-run: never touch Drive -----
    if dry_run:
        if side and not force and all((side.get(k) or {}).get("file_id") for k, _, _, _ in DOC_SPECS):
            print(f"  [{ad_id}] (dry-run) would SKIP — existing Docs in sidecar")
            return {col: (side.get(key) or {}).get("link", "") for key, _, col, _ in DOC_SPECS}, "reused"
        print(f"  [{ad_id}] (dry-run) would create folder + upload+convert {len(DOC_SPECS)} docs + share")
        return {col: "[DRY-RUN]" for _, _, col, _ in DOC_SPECS}, "dry-run"

    # ----- reuse from sidecar (the common path; protects team edits) -----
    if side and not force:
        payload, ok = {}, True
        for key, _, col, _ in DOC_SPECS:
            entry = side.get(key) or {}
            fid = entry.get("file_id")
            if fid and _gdrive.file_exists(svc, fid):
                payload[col] = entry.get("link") or _gdrive.get_web_view_link(svc, fid)
            else:
                ok = False
                break
        if ok:
            print(f"  [{ad_id}] SKIP gdoc — reusing existing Docs (collaboration preserved)")
            return payload, "reused"

    folder_id = _gdrive.ensure_competitor_folder(svc, env, competitor, folder_cache)

    # ----- adopt by name (sidecar lost/never-synced; avoids duplicate Docs) -----
    if not force:
        adopted, found_all = {}, True
        new_side = {"ad_library_id": ad_id, "competitor": competitor, "folder_id": folder_id}
        for key, _, col, title_suffix in DOC_SPECS:
            title = f"{competitor} — {ad_id} — {title_suffix}"
            fid, link = _gdrive.find_doc_in_folder(svc, env, title, folder_id)
            if fid:
                link = link or _gdrive.get_web_view_link(svc, fid)
                new_side[key] = {"file_id": fid, "link": link}
                adopted[col] = link
            else:
                found_all = False
                break
        if found_all:
            new_side.update(version=1, shared_mode="adopted",
                            uploaded_at=datetime.now().isoformat(timespec="seconds"))
            write_sidecar(ad_id, new_side)
            print(f"  [{ad_id}] adopted existing Docs by name (no re-upload)")
            return adopted, "adopted"

    # ----- create (fresh, or a new version under --force) -----
    version = (side.get("version", 1) + 1) if (force and side) else 1
    new_side = {"ad_library_id": ad_id, "competitor": competitor, "folder_id": folder_id,
                "version": version, "uploaded_at": datetime.now().isoformat(timespec="seconds")}
    payload, modes = {}, []
    for key, suffix, col, title_suffix in DOC_SPECS:
        title = f"{competitor} — {ad_id} — {title_suffix}" + (f" (v{version})" if version > 1 else "")
        fid, link = _retry(lambda: _gdrive.upload_docx_as_gdoc(svc, env, docx_paths[key], title, folder_id))
        mode = _gdrive.set_link_permission(svc, env, fid)
        link = link or _gdrive.get_web_view_link(svc, fid)
        new_side[key] = {"file_id": fid, "link": link}
        payload[col] = link
        modes.append(mode)
        print(f"  [{ad_id}] {title_suffix} -> {link}  (sharing={mode})")
    new_side["shared_mode"] = modes[0] if modes else None
    write_sidecar(ad_id, new_side)
    return payload, "created"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competitor", required=True)
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--master-dir", default="master")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="create a NEW versioned Doc instead of reusing (old Doc + comments kept)")
    args = ap.parse_args()

    env = load_env()
    competitor = args.competitor.lower().strip()
    master_path = pathlib.Path(args.master_dir) / f"{competitor}.csv"
    if not master_path.exists():
        sys.exit(f"[error] master CSV not found: {master_path}")

    svc = None if args.dry_run else _gdrive.build_drive_service(env)

    rows, cols = read_master(master_path)
    for c in GDOC_URL_COLS:
        if c not in cols:
            cols.append(c)
            for r in rows:
                r.setdefault(c, "")

    by_id: dict[str, list[dict]] = {}
    for r in rows:
        by_id.setdefault((r.get("ad_library_id") or "").strip(), []).append(r)

    folder_cache: dict = {}
    created = reused = skipped = failed = updated = 0

    for ad_id in args.ids:
        if ad_id not in by_id:
            print(f"  [{ad_id}] SKIP — not in master CSV")
            skipped += 1
            continue
        try:
            payload, status = process_ad(svc, env, competitor, ad_id, folder_cache,
                                          args.force, args.dry_run)
        except Exception as e:  # noqa: BLE001
            print(f"  [{ad_id}] FAILED: {type(e).__name__}: {e}")
            failed += 1
            continue

        if payload is None:
            skipped += 1
            continue
        if status in ("created", "adopted"):
            created += 1
        elif status == "reused":
            reused += 1

        for r in by_id[ad_id]:
            for col, link in payload.items():
                r[col] = link
            updated += 1

        if not args.dry_run:
            tmp = master_path.with_suffix(master_path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
            os.replace(tmp, master_path)

    print()
    print(f"Stage 9 done — created/adopted={created}, reused={reused}, "
          f"master rows updated={updated}, skipped={skipped}, failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
