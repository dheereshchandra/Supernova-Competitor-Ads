#!/usr/bin/env python3
"""
Step 4 cost estimator (fb-ads-video-analysis, Stage 0).

Reads master/{competitor}.csv, identifies rows missing one or both analysis
docx URLs (i.e. candidate rows for Step 4), optionally narrows to a scope
(--random N / --ids X,Y,Z / --all / --start-date YYYY-MM-DD), and prints a
per-row cost estimate plus batch totals.

Important: no Gemini API key needed. Pure local math + ffprobe.

See skills/fb-ads-video-analysis/SKILL.md "Stage 0" for the integration point.
See skills/ARCHITECTURE.md "How the cost-estimate-and-approval gate works"
for design rationale.

Usage:
    python3 scripts/estimate_step4_cost.py \
        --competitor zinglish \
        [--random 5]
        [--ids 12345,67890]
        [--all]
        [--start-date 2026-05-01]

Exit code is 0 on success regardless of cost — the human decides whether to
proceed. Non-zero only on usage errors / missing master CSV.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Pricing constants (mid-2025 figures; UPDATE IF GEMINI PRICING CHANGES)
# ---------------------------------------------------------------------------
# Sources: https://ai.google.dev/pricing and Cloudflare R2 pricing pages.
# These are USD per the listed unit.

GEMINI_PRO_INPUT_PER_1M_TOKENS = 1.25     # gemini-3.1-pro-preview
GEMINI_PRO_OUTPUT_PER_1M_TOKENS = 5.00
GEMINI_PRO_VIDEO_TOKENS_PER_SECOND = 258  # Google's quoted figure
NANO_BANANA_PRO_PER_IMAGE = 0.04          # rough — verify vs. your bill

# Output token assumptions (model dependent — these are calibrated heuristics)
DECOMPOSE_OUTPUT_TOKENS = 5000
REWRITE_INPUT_TOKENS_BASE = 4000          # decompose JSON re-fed in
REWRITE_OUTPUT_TOKENS = 3000

# Heuristics for unknown values (when ffprobe fails or file is missing)
DEFAULT_DURATION_S = 30
SCENES_PER_SECOND = 1 / 6                 # ~1 scene every 6 seconds
MAX_SCENES = 12
MIN_SCENES = 1
DEFAULT_CHARACTERS = 2

# Image-only ad: no panel gen, simpler analysis
IMAGE_ONLY_DECOMPOSE_TOKENS_IN = 1000
IMAGE_ONLY_DECOMPOSE_TOKENS_OUT = 1500
IMAGE_ONLY_GEN_IMAGES = 1                  # one regenerated clean image


# ---------------------------------------------------------------------------
# Probing video duration
# ---------------------------------------------------------------------------

def ffprobe_duration(video_path: Path) -> Optional[float]:
    """Return duration in seconds, or None if probe fails."""
    if not video_path.exists():
        return None
    if shutil.which("ffprobe") is None:
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(video_path)],
            capture_output=True, text=True, timeout=10
        )
        return float(out.stdout.strip())
    except (subprocess.SubprocessError, ValueError, subprocess.TimeoutExpired):
        return None


# ---------------------------------------------------------------------------
# Per-row cost estimation
# ---------------------------------------------------------------------------

def estimate_row_cost(row: dict, videos_dir: Path) -> dict:
    """Returns a dict with cost breakdown + assumptions used."""
    ad_library_id = row.get("ad_library_id", "").strip()
    creative_index = int(row.get("creative_index_in_ad", "0").strip() or "0")
    media_type = row.get("ad_media_type", "").strip()

    is_image_only = (media_type == "Image")

    if is_image_only:
        # Image-only ads use a much simpler (cheaper) pipeline.
        cost_decompose = (
            IMAGE_ONLY_DECOMPOSE_TOKENS_IN  / 1_000_000 * GEMINI_PRO_INPUT_PER_1M_TOKENS
            + IMAGE_ONLY_DECOMPOSE_TOKENS_OUT / 1_000_000 * GEMINI_PRO_OUTPUT_PER_1M_TOKENS
        )
        cost_sheets = 0.0    # no character sheets for static images
        cost_panels = IMAGE_ONLY_GEN_IMAGES * NANO_BANANA_PRO_PER_IMAGE
        cost_rewrite = (
            IMAGE_ONLY_DECOMPOSE_TOKENS_OUT / 1_000_000 * GEMINI_PRO_INPUT_PER_1M_TOKENS  # re-feed
            + 1000 / 1_000_000 * GEMINI_PRO_OUTPUT_PER_1M_TOKENS
        )
        return {
            "ad_library_id": ad_library_id,
            "creative_index": creative_index,
            "media_type": media_type,
            "duration_s": None,
            "scenes": None,
            "characters": None,
            "cost_decompose": cost_decompose,
            "cost_sheets": cost_sheets,
            "cost_panels": cost_panels,
            "cost_rewrite": cost_rewrite,
            "cost_total": cost_decompose + cost_sheets + cost_panels + cost_rewrite,
            "assumption_notes": "image-only ad — simpler pipeline, no scene decomposition",
        }

    # Video / Carousel / DCO: probe duration if possible
    fname = f"{ad_library_id}.mp4" if creative_index == 0 else f"{ad_library_id}_v{creative_index + 1}.mp4"
    video_path = videos_dir / fname
    duration = ffprobe_duration(video_path)

    if duration is None:
        duration = DEFAULT_DURATION_S
        duration_source = "default assumption (file missing or ffprobe unavailable)"
    else:
        duration_source = "ffprobe"

    # Scene + character estimates
    scenes_est = max(MIN_SCENES, min(MAX_SCENES, int(round(duration * SCENES_PER_SECOND))))
    characters_est = DEFAULT_CHARACTERS

    # If we have a decompose sidecar already, use exact counts
    sidecar = Path("step4_workspace/scenes") / f"{ad_library_id}.json"
    used_sidecar = False
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text())
            parsed = data.get("parsed", {})
            real_scenes = parsed.get("scenes", [])
            real_chars = parsed.get("characters", [])
            if real_scenes:
                scenes_est = len(real_scenes)
                characters_est = max(1, len(real_chars))
                used_sidecar = True
        except (json.JSONDecodeError, OSError):
            pass

    # Decompose cost
    video_tokens_in = duration * GEMINI_PRO_VIDEO_TOKENS_PER_SECOND
    cost_decompose = (
        video_tokens_in / 1_000_000 * GEMINI_PRO_INPUT_PER_1M_TOKENS
        + DECOMPOSE_OUTPUT_TOKENS / 1_000_000 * GEMINI_PRO_OUTPUT_PER_1M_TOKENS
    )

    # Character sheets
    cost_sheets = characters_est * NANO_BANANA_PRO_PER_IMAGE

    # Panels — assume 1 panel per scene (carousels would cost more, but rare)
    cost_panels = scenes_est * NANO_BANANA_PRO_PER_IMAGE

    # Supernova rewrite
    cost_rewrite = (
        REWRITE_INPUT_TOKENS_BASE / 1_000_000 * GEMINI_PRO_INPUT_PER_1M_TOKENS
        + REWRITE_OUTPUT_TOKENS / 1_000_000 * GEMINI_PRO_OUTPUT_PER_1M_TOKENS
    )

    return {
        "ad_library_id": ad_library_id,
        "creative_index": creative_index,
        "media_type": media_type,
        "duration_s": round(duration, 1),
        "duration_source": duration_source,
        "scenes": scenes_est,
        "characters": characters_est,
        "used_sidecar": used_sidecar,
        "cost_decompose": cost_decompose,
        "cost_sheets": cost_sheets,
        "cost_panels": cost_panels,
        "cost_rewrite": cost_rewrite,
        "cost_total": cost_decompose + cost_sheets + cost_panels + cost_rewrite,
        "assumption_notes": (
            f"{duration_source}; scenes={'exact (sidecar)' if used_sidecar else 'estimated'}"
        ),
    }


# ---------------------------------------------------------------------------
# Candidate row selection
# ---------------------------------------------------------------------------

def candidate_rows(master_rows: list[dict]) -> list[dict]:
    """Rows missing one or both docx URLs AND having an r2_public_url."""
    out = []
    for r in master_rows:
        if not r.get("r2_public_url", "").strip():
            continue  # video not yet in R2 — Step 4 can't run on this row
        comp_url = r.get("competitor_analysis_docx_r2_url", "").strip()
        rewrite_url = r.get("supernova_rewrite_docx_r2_url", "").strip()
        if not comp_url or not rewrite_url:
            out.append(r)
    return out


def apply_scope(rows: list[dict], *, random_n: Optional[int],
                ids: Optional[list[str]], all_flag: bool,
                start_date: Optional[str],
                top_by_rank: Optional[int] = None) -> list[dict]:
    if ids:
        wanted = set(ids)
        return [r for r in rows if r.get("ad_library_id", "") in wanted]
    if start_date:
        return [r for r in rows if r.get("ad_start_date", "") >= start_date]
    if top_by_rank:
        # "Top N by row_rank" — pick the lowest N row_rank values that are
        # *also* candidates. This is the default operator scope for Step 4 per
        # the Learna AI retro: top of scrape = most prominent / most-active ads,
        # which is what we want to analyse first. Deterministic (no seed needed).
        def _rank_key(r):
            try:
                return int(r.get("row_rank", "999999"))
            except (TypeError, ValueError):
                return 999999
        return sorted(rows, key=_rank_key)[:top_by_rank]
    if random_n:
        if len(rows) <= random_n:
            return list(rows)
        return random.sample(rows, random_n)
    if all_flag:
        return list(rows)
    # No scope flag → default to ALL candidate rows but warn
    return list(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competitor", required=True,
                    help="Competitor slug (must match master/{competitor}.csv).")
    ap.add_argument("--master-dir", default="master")
    ap.add_argument("--videos-dir", default=None,
                    help="Where the .mp4 files live for ffprobe. "
                         "Defaults to ./videos/{competitor}-*/ (latest).")

    scope = ap.add_mutually_exclusive_group()
    scope.add_argument("--top-by-rank", type=int, metavar="N",
                       help="Top N candidates by row_rank ascending — "
                            "deterministic, matches FB Ad Library prominence. "
                            "RECOMMENDED default for Step 4 (use --top-by-rank 20).")
    scope.add_argument("--random", type=int, metavar="N",
                       help="N random candidate rows. Use --seed for reproducibility.")
    scope.add_argument("--ids", type=str,
                       help="Comma-separated ad_library_ids to estimate.")
    scope.add_argument("--all", action="store_true",
                       help="All candidate rows in the master.")
    scope.add_argument("--start-date", type=str,
                       help="Only rows with ad_start_date >= this YYYY-MM-DD.")

    ap.add_argument("--seed", type=int, default=None,
                    help="Random seed for reproducible --random sampling.")
    ap.add_argument("--json", action="store_true",
                    help="Emit machine-readable JSON instead of the human report.")
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    competitor = args.competitor.lower().strip()
    master_path = Path(args.master_dir) / f"{competitor}.csv"
    if not master_path.exists():
        sys.exit(f"[error] master CSV not found: {master_path}")

    with master_path.open(encoding="utf-8-sig", newline="") as f:
        master_rows = list(csv.DictReader(f))

    # Resolve videos dir (latest run if multiple)
    if args.videos_dir:
        videos_dir = Path(args.videos_dir)
    else:
        candidates = sorted(Path("videos").glob(f"{competitor}-*"))
        videos_dir = candidates[-1] if candidates else Path("videos") / f"{competitor}-unknown"

    # Step 1: find all candidates, then narrow by scope
    cands = candidate_rows(master_rows)
    selected = apply_scope(
        cands,
        random_n=args.random,
        ids=args.ids.split(",") if args.ids else None,
        all_flag=args.all,
        start_date=args.start_date,
        top_by_rank=args.top_by_rank,
    )

    # Step 2: estimate per row
    estimates = [estimate_row_cost(r, videos_dir) for r in selected]

    # Tally
    total_cost = sum(e["cost_total"] for e in estimates)
    image_only_count = sum(1 for e in estimates if e["media_type"] == "Image")
    video_count = len(estimates) - image_only_count

    if args.json:
        print(json.dumps({
            "competitor": competitor,
            "master_total_rows": len(master_rows),
            "candidate_rows": len(cands),
            "selected_rows": len(estimates),
            "video_rows": video_count,
            "image_only_rows": image_only_count,
            "total_cost_usd": round(total_cost, 4),
            "estimates": estimates,
        }, indent=2))
        return 0

    # Human-readable report
    print()
    print(f"fb-ads-video-analysis — Step 4 cost estimate")
    print(f"─" * 60)
    print(f"competitor:          {competitor}")
    print(f"master total rows:   {len(master_rows)}")
    print(f"candidate rows:      {len(cands)}  (missing one or both docx URLs)")
    print(f"selected for est:    {len(selected)}  ({video_count} video, {image_only_count} image-only)")
    print(f"videos dir probed:   {videos_dir}")
    print()
    if not estimates:
        print("Nothing to estimate. Either every candidate row already has both docx")
        print("URLs (Step 4 already done) or your scope filter matched nothing.")
        return 0

    # Per-row breakdown — sort by cost ascending so cheapest is first
    estimates_sorted = sorted(estimates, key=lambda e: e["cost_total"])
    print(f"Per-row breakdown (sorted cheapest → most expensive):")
    print(f"  {'ad_library_id':<18} {'kind':<8} {'dur':>6} {'sc':>3} {'ch':>3} {'$decompose':>11} {'$sheets':>9} {'$panels':>9} {'$rewrite':>10} {'TOTAL $':>10}")
    for e in estimates_sorted:
        dur = f"{e['duration_s']}s" if e['duration_s'] else "—"
        sc = str(e['scenes']) if e['scenes'] else "—"
        ch = str(e['characters']) if e['characters'] else "—"
        kind = e['media_type'] or "—"
        print(f"  {e['ad_library_id']:<18} {kind:<8} {dur:>6} {sc:>3} {ch:>3}"
              f" {e['cost_decompose']:>11.4f} {e['cost_sheets']:>9.4f}"
              f" {e['cost_panels']:>9.4f} {e['cost_rewrite']:>10.4f} {e['cost_total']:>10.4f}")

    print()
    print(f"BATCH TOTAL:         ${total_cost:.2f}")
    print(f"Wall-clock estimate: {15 + len(estimates) * 2}–{30 + len(estimates) * 3} min")
    print(f"                     (Gemini Batch API queue + image generation)")
    print()
    print(f"NOTE: pricing constants in this script are mid-2025 figures. Verify")
    print(f"against your actual Gemini billing after the first run.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
