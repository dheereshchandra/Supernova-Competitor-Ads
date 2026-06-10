#!/usr/bin/env python3
"""
Step 4 orchestrator (fb-ads-video-analysis).

Reads master/{competitor}.csv, selects candidate rows (those missing one or
both analysis docx URLs and having a populated r2_public_url), and runs each
through the 9-stage pipeline (HANDOVER §9):

    Stage 0:   cost estimate + operator approval gate (handled by Cowork chat,
               this script only fires when approval is captured upstream)
    Stage 1:   decompose videos        (Gemini 3.1 Pro Batch API)
    Stage 2:   extract frames          (ffmpeg, local — source-native resolution)
    Stage 3:   character sheets        (Nano Banana Pro @ 2K, parallel-sync)
    Stage 4:   clean panel imagery     (Nano Banana Pro @ 2K, parallel-sync)
    Stage 4.5: upload images to R2     (boto3) — produces r2_urls.json sidecar
    Stage 5:   Supernova rewrite       (Gemini 3.1 Pro Batch API)
    Stage 6:   build two docx files    (python-docx, local; each image is
               followed by an "Asset: <R2 URL>" hyperlink caption)
               + programmatic verification of image/URL parity
    Stage 7:   upload docs to R2       (boto3)
    Stage 8:   update master CSV       (local; per-row checkpoint — fills both
               docx URL columns AND the three JSON-array image URL columns)
    Stage 9:   Google Docs upload      (Drive API — convert both docx to native
               Google Docs in a Shared Drive; fills the two *_gdoc_url columns.
               Real impl: scripts/step4_upload_gdocs.py)
    Audit:    HEAD-check every URL in docs + master (scripts/step4_audit.py)

This file owns the stage glue + verification gates. The actual Gemini /
Nano Banana Pro calls live in helper modules under scripts/step4/ which
are imported at runtime (left as TODOs in this skeleton — they'll be wired
up once GEMINI_API_KEY arrives).

The script is fully idempotent and resumable. Cowork's ~45-second bash cap
means longer stages will be killed mid-way; just re-invoke the script and
already-done work is skipped automatically.

See skills/fb-ads-video-analysis/SKILL.md for the operator-facing description.
See skills/ARCHITECTURE.md for the architectural rationale.

Usage:
    python3 scripts/run_step4.py --competitor zinglish --random 5
    python3 scripts/run_step4.py --competitor zinglish --ids 12345,67890
    python3 scripts/run_step4.py --competitor zinglish --all
    python3 scripts/run_step4.py --competitor zinglish --random 5 --dry-run-everything
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import random
import shutil
import sys
import time
from datetime import datetime
from typing import Optional


WORKSPACE = pathlib.Path("step4_workspace")
WORKSPACE_SUBDIRS = ["batches", "scenes", "frames", "images", "docs", "logs",
                     ".gemini_uploads"]


# ---------------------------------------------------------------------------
# Environment / .env loading
# ---------------------------------------------------------------------------

def load_env() -> dict:
    env_path = pathlib.Path(".env")
    if not env_path.exists():
        sys.exit("[error] .env not found at folder root. Add R2 + GEMINI_API_KEY.")
    env = {}
    for line in env_path.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def require_keys(env: dict, *keys: str, fail_on_missing: bool = True) -> list[str]:
    missing = [k for k in keys if not env.get(k)]
    if missing and fail_on_missing:
        sys.exit(f"[error] .env missing required keys for Step 4: {', '.join(missing)}")
    return missing


# ---------------------------------------------------------------------------
# Candidate row selection (mirrors estimate_step4_cost.py logic)
# ---------------------------------------------------------------------------

def candidate_rows(master_rows: list[dict]) -> list[dict]:
    out = []
    for r in master_rows:
        if not r.get("r2_public_url", "").strip():
            continue
        comp_url = r.get("competitor_analysis_docx_r2_url", "").strip()
        rewrite_url = r.get("supernova_rewrite_docx_r2_url", "").strip()
        if not comp_url or not rewrite_url:
            out.append(r)
    return out


def apply_scope(rows: list[dict], args) -> list[dict]:
    if args.ids:
        wanted = set(s.strip() for s in args.ids.split(","))
        return [r for r in rows if r.get("ad_library_id", "") in wanted]
    if args.start_date:
        return [r for r in rows if r.get("ad_start_date", "") >= args.start_date]
    if args.random:
        if args.seed is not None:
            random.seed(args.seed)
        return random.sample(rows, min(args.random, len(rows)))
    return list(rows)


# ---------------------------------------------------------------------------
# Workspace setup
# ---------------------------------------------------------------------------

def ensure_workspace() -> None:
    for d in WORKSPACE_SUBDIRS:
        (WORKSPACE / d).mkdir(parents=True, exist_ok=True)


def videos_dir_for(competitor: str) -> pathlib.Path:
    candidates = sorted(pathlib.Path("videos").glob(f"{competitor}-*"))
    if not candidates:
        sys.exit(f"[error] no videos/{competitor}-*/ folder found. Run Step 2 first.")
    return candidates[-1]


def video_path_for_row(row: dict, vdir: pathlib.Path) -> Optional[pathlib.Path]:
    aid = row.get("ad_library_id", "").strip()
    ci = int(row.get("creative_index_in_ad", "0").strip() or "0")
    fname = f"{aid}.mp4" if ci == 0 else f"{aid}_v{ci + 1}.mp4"
    p = vdir / fname
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# Stage stubs — to be filled in once GEMINI_API_KEY is in .env
# ---------------------------------------------------------------------------

class StageNotYetWiredError(NotImplementedError):
    """Raised by stages that need GEMINI_API_KEY but haven't been wired up yet."""


def stage1_decompose(rows: list[dict], vdir: pathlib.Path, env: dict, log) -> dict:
    """
    Submit a Gemini 3.1 Pro Batch job for video decomposition.
    See competitor-video-scenes/scripts/batch_decompose_async.py for the
    reference implementation pattern.

    Returns: { id: scenes_json_path } for rows that completed; raises on hard fail.
    """
    log("Stage 1: decompose — TODO: wire Gemini Batch API once GEMINI_API_KEY is available")
    # When wired: upload videos to Files API, submit batch, poll, write scenes/<id>.json per row
    raise StageNotYetWiredError("Stage 1 decompose requires GEMINI_API_KEY")


def stage1_verify(rows: list[dict], log) -> tuple[list[dict], list[dict]]:
    """Returns (passed, failed) rows. See SKILL.md 'Verification gate after Stage 1'."""
    passed, failed = [], []
    for r in rows:
        aid = r.get("ad_library_id", "").strip()
        sidecar = WORKSPACE / "scenes" / f"{aid}.json"
        if not sidecar.exists():
            failed.append((r, "no sidecar"))
            continue
        try:
            data = json.loads(sidecar.read_text())
        except json.JSONDecodeError as e:
            failed.append((r, f"bad json: {e}"))
            continue
        parsed = data.get("parsed", {})
        scenes = parsed.get("scenes", [])
        chars = parsed.get("characters", [])
        if len(scenes) < 1:
            failed.append((r, "no scenes"))
            continue
        if len(chars) < 1:
            failed.append((r, "no characters"))
            continue
        # Check transcript presence
        has_content = any(
            (s.get("audio_transcript", "").strip() or s.get("on_screen_text", "").strip())
            for s in scenes
        )
        if not has_content:
            failed.append((r, "all scenes empty transcript+OST"))
            continue
        passed.append(r)
    log(f"Stage 1 verify: {len(passed)} passed, {len(failed)} failed")
    for r, why in failed:
        log(f"  FAIL  {r.get('ad_library_id', '?')}: {why}")
    return passed, [r for r, _ in failed]


def stage2_extract_frames(rows: list[dict], vdir: pathlib.Path, log) -> dict:
    """Run ffmpeg to extract one screenshot per scene. See SKILL.md Stage 2."""
    log("Stage 2: frames — TODO: implement ffmpeg parallel-extract loop")
    raise StageNotYetWiredError("Stage 2 not yet implemented")


def stage3_character_sheets(rows: list[dict], env: dict, log) -> dict:
    """Nano Banana Pro parallel-sync character sheets. See SKILL.md Stage 3."""
    log("Stage 3: character sheets — TODO: wire Nano Banana Pro calls")
    raise StageNotYetWiredError("Stage 3 requires GEMINI_API_KEY (Nano Banana Pro)")


def stage4_panels(rows: list[dict], env: dict, log) -> dict:
    """Nano Banana Pro parallel-sync clean panels. See SKILL.md Stage 4."""
    log("Stage 4: panels — TODO: wire Nano Banana Pro calls")
    raise StageNotYetWiredError("Stage 4 requires GEMINI_API_KEY (Nano Banana Pro)")


def stage4_5_upload_images(rows: list[dict], env: dict, log) -> dict:
    """Upload every per-ad image to R2 and write the r2_urls.json sidecars.

    This MUST run before Stage 6 so build_docs can read the URLs.
    See scripts/step4_upload_images.py.
    """
    log("Stage 4.5: upload images — TODO: invoke step4_upload_images.py")
    raise StageNotYetWiredError("Stage 4.5 not yet wired into run_step4 (call "
                                "step4_upload_images.py directly until then)")


def stage5_rewrite(rows: list[dict], env: dict, log) -> dict:
    """Gemini 3.1 Pro Batch — Supernova-voice rewrite. See SKILL.md Stage 5."""
    log("Stage 5: Supernova rewrite — TODO: wire Gemini Batch API")
    raise StageNotYetWiredError("Stage 5 requires GEMINI_API_KEY")


def stage6_build_docx(rows: list[dict], log) -> dict:
    """python-docx assembly of two docs per row. See SKILL.md Stage 6.

    The real implementation lives in scripts/step4_build_docs.py — it reads the
    Stage 4.5 r2_urls.json sidecar and inserts "Asset:" hyperlink captions
    beneath every embedded picture (HANDOVER §9.7).
    """
    log("Stage 6: build docx — TODO: invoke step4_build_docs.py (reads Stage 4.5 sidecar)")
    raise StageNotYetWiredError("Stage 6 not yet implemented")


def stage6_verify_and_review(rows: list[dict], log) -> tuple[list[dict], list[dict]]:
    """
    After each docx pair, verify programmatically THEN have Claude review.
    See SKILL.md 'Verification gate after Stage 6 (programmatic)' and
    '(Claude review of each doc)'.
    """
    log("Stage 6 verify: TODO — programmatic checks then Claude-review hook")
    raise StageNotYetWiredError("Stage 6 verify not yet implemented")


def stage7_upload_docs(rows: list[dict], env: dict, log) -> dict:
    """Upload the two docx files per row to R2. Same flat-namespace pattern as Step 3."""
    log("Stage 7: upload docs — TODO: implement boto3 put_object for .docx")
    raise StageNotYetWiredError("Stage 7 not yet implemented")


def stage8_update_master(rows: list[dict], master_path: pathlib.Path,
                         doc_urls: dict, log) -> None:
    """Write the five Step-4 URL columns back into master. See SKILL.md Stage 8.

    Columns updated (HANDOVER §9.7):
      - competitor_analysis_docx_r2_url
      - supernova_rewrite_docx_r2_url
      - orig_frame_urls       (JSON array)
      - gen_panel_urls        (JSON array)
      - char_sheet_urls       (JSON array)
      - latest_scrape_run_date
    """
    log("Stage 8: update master — TODO: implement per-row checkpointed update")
    raise StageNotYetWiredError("Stage 8 not yet implemented")


def stage9_upload_gdocs(rows: list[dict], env: dict, log) -> None:
    """Convert both docx to native Google Docs in a Shared Drive + fill the two
    *_gdoc_url master columns. Needs the service-account + Shared Drive (HANDOVER §9.10).

    The real implementation lives in scripts/step4_upload_gdocs.py; run it directly
    until this orchestrator stage is wired up.
    """
    log("Stage 9: Google Docs — TODO: invoke step4_upload_gdocs.py (needs GDRIVE_* creds)")
    raise StageNotYetWiredError("Stage 9 not yet wired into run_step4 (call "
                                "step4_upload_gdocs.py directly until then)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competitor", required=True,
                    help="Competitor slug (must match master/{competitor}.csv).")
    ap.add_argument("--master-dir", default="master")

    scope = ap.add_mutually_exclusive_group()
    scope.add_argument("--random", type=int, metavar="N")
    scope.add_argument("--ids", type=str)
    scope.add_argument("--all", action="store_true")
    scope.add_argument("--start-date", type=str)
    ap.add_argument("--seed", type=int, default=None)

    ap.add_argument("--dry-run-everything", action="store_true",
                    help="Exercise the orchestration logic without firing any Gemini call. "
                         "Useful before GEMINI_API_KEY is configured.")
    ap.add_argument("--require-approval", action="store_true",
                    help="If set, refuses to run unless an APPROVAL_TOKEN env var is present "
                         "(set by the master skill after the operator clicked Approve).")
    args = ap.parse_args()

    env = load_env()

    if args.require_approval and not env.get("APPROVAL_TOKEN"):
        sys.exit("[error] --require-approval was passed but no APPROVAL_TOKEN in env. "
                 "The master skill (fb-ads-pipeline) is supposed to set this after "
                 "the operator approves the cost estimate. Refusing to run.")

    if not args.dry_run_everything:
        require_keys(env, "GEMINI_API_KEY")  # hard fail if missing
    require_keys(env, "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET",
                 "R2_PUBLIC_URL_BASE", "R2_S3_ENDPOINT")

    competitor = args.competitor.lower().strip()
    master_path = pathlib.Path(args.master_dir) / f"{competitor}.csv"
    if not master_path.exists():
        sys.exit(f"[error] master CSV not found: {master_path}")

    with master_path.open(encoding="utf-8-sig", newline="") as f:
        master_rows = list(csv.DictReader(f))

    cands = candidate_rows(master_rows)
    selected = apply_scope(cands, args)

    if not selected:
        print("Nothing to do — every candidate row already has both docx URLs.")
        return 0

    print(f"\nfb-ads-video-analysis starting")
    print(f"  competitor:     {competitor}")
    print(f"  candidate rows: {len(cands)}")
    print(f"  selected rows:  {len(selected)}")
    print(f"  dry-run:        {args.dry_run_everything}")
    print()

    ensure_workspace()
    vdir = videos_dir_for(competitor)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    log_path = WORKSPACE / "logs" / f"step4-{competitor}-{stamp}.log"
    log_lines: list[str] = []

    def log(msg: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        print(line)
        log_lines.append(line)

    try:
        # ---- Stage 1: decompose ----
        log(f"Stage 1: decomposing {len(selected)} rows via Gemini 3.1 Pro Batch")
        try:
            stage1_decompose(selected, vdir, env, log)
        except StageNotYetWiredError as e:
            if args.dry_run_everything:
                log(f"  (dry-run) would call: {e}")
            else:
                raise
        passed, failed_1 = stage1_verify(selected, log) if not args.dry_run_everything else (selected, [])

        # ---- Stage 2: frames ----
        if passed:
            log(f"Stage 2: extracting frames for {len(passed)} rows")
            try:
                stage2_extract_frames(passed, vdir, log)
            except StageNotYetWiredError as e:
                if args.dry_run_everything:
                    log(f"  (dry-run) would call: {e}")
                else:
                    raise

        # ---- Stage 3: character sheets ----
        if passed:
            log(f"Stage 3: generating character sheets")
            try:
                stage3_character_sheets(passed, env, log)
            except StageNotYetWiredError as e:
                if args.dry_run_everything:
                    log(f"  (dry-run) would call: {e}")
                else:
                    raise

        # ---- Stage 4: clean panels ----
        if passed:
            log(f"Stage 4: generating clean panel imagery")
            try:
                stage4_panels(passed, env, log)
            except StageNotYetWiredError as e:
                if args.dry_run_everything:
                    log(f"  (dry-run) would call: {e}")
                else:
                    raise

        # ---- Stage 4.5: upload images to R2 (HANDOVER §9.7) ----
        # Runs after every image exists locally and BEFORE build_docs so the
        # builder can embed R2 URLs as captions.
        if passed:
            log(f"Stage 4.5: uploading per-ad images to R2")
            try:
                stage4_5_upload_images(passed, env, log)
            except StageNotYetWiredError as e:
                if args.dry_run_everything:
                    log(f"  (dry-run) would call: {e}")
                else:
                    raise

        # ---- Stage 5: Supernova rewrite ----
        if passed:
            log(f"Stage 5: Supernova-voice rewrite")
            try:
                stage5_rewrite(passed, env, log)
            except StageNotYetWiredError as e:
                if args.dry_run_everything:
                    log(f"  (dry-run) would call: {e}")
                else:
                    raise

        # ---- Stage 6: build docx + verify + Claude review ----
        if passed:
            log(f"Stage 6: building docx files + verification + Claude review")
            try:
                stage6_build_docx(passed, log)
                passed, failed_6 = stage6_verify_and_review(passed, log)
            except StageNotYetWiredError as e:
                if args.dry_run_everything:
                    log(f"  (dry-run) would call: {e}")
                else:
                    raise

        # ---- Stage 7: upload to R2 ----
        if passed:
            log(f"Stage 7: uploading {len(passed)} doc pairs to R2")
            try:
                doc_urls = stage7_upload_docs(passed, env, log)
            except StageNotYetWiredError as e:
                if args.dry_run_everything:
                    log(f"  (dry-run) would call: {e}")
                    doc_urls = {}
                else:
                    raise

        # ---- Stage 8: update master ----
        if passed:
            log(f"Stage 8: updating master CSV")
            try:
                stage8_update_master(passed, master_path, doc_urls, log)
            except StageNotYetWiredError as e:
                if args.dry_run_everything:
                    log(f"  (dry-run) would call: {e}")
                else:
                    raise

        # ---- Stage 9: Google Docs (collaborative copies) ----
        if passed:
            log(f"Stage 9: uploading {len(passed)} doc pairs to Google Docs (Shared Drive)")
            try:
                stage9_upload_gdocs(passed, env, log)
            except StageNotYetWiredError as e:
                if args.dry_run_everything:
                    log(f"  (dry-run) would call: {e}")
                else:
                    raise

        log(f"DONE.")
        return 0

    finally:
        # Always flush log
        log_path.write_text("\n".join(log_lines) + "\n")
        print(f"\n[log] {log_path}")


if __name__ == "__main__":
    raise SystemExit(main())
