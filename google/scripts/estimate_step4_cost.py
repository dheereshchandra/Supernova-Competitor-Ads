#!/usr/bin/env python3
"""
Step 4 cost estimator (google-ads-video-analysis, Stage 0).

Reads master/{competitor}.csv, identifies rows missing one or both analysis
docx URLs (i.e. candidate rows for Step 4), optionally narrows to a scope
(--random N / --ids X,Y,Z / --all / --start-date YYYY-MM-DD), and prints a
per-row cost estimate plus batch totals.

Important: no Gemini API key needed. Pure local math + ffprobe.

Format-aware:
  - YouTubeVideo: ffprobe duration → scene count → decompose + sheets + panels + rewrite
  - Image:        fixed ~$0.05 (single Gemini sync + 1 panel + rewrite)
  - Text:         fixed ~$0.02 (two Gemini sync calls, no images)
  - Shopping/Maps: treated as Image if r2_public_url is set; else excluded

See skills/google-ads-video-analysis/SKILL.md "Stage 0" for the integration point.
See skills/ARCHITECTURE.md "How the cost-estimate-and-approval gate works"
for design rationale.

Usage:
    python3 scripts/estimate_step4_cost.py \\
        --competitor zinglish \\
        [--random 5]
        [--ids creativeA,creativeB]
        [--all]
        [--start-date 2026-05-01]
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

GEMINI_PRO_INPUT_PER_1M_TOKENS = 1.25
GEMINI_PRO_OUTPUT_PER_1M_TOKENS = 5.00
GEMINI_PRO_VIDEO_TOKENS_PER_SECOND = 258
NANO_BANANA_PRO_PER_IMAGE = 0.04

DECOMPOSE_OUTPUT_TOKENS = 5000
REWRITE_INPUT_TOKENS_BASE = 4000
REWRITE_OUTPUT_TOKENS = 3000

DEFAULT_DURATION_S = 30
SCENES_PER_SECOND = 1 / 6
MAX_SCENES = 12
MIN_SCENES = 1
DEFAULT_CHARACTERS = 2

# Image-only ad: no panel gen beyond 1, simpler analysis
IMAGE_ONLY_DECOMPOSE_TOKENS_IN = 1000
IMAGE_ONLY_DECOMPOSE_TOKENS_OUT = 1500
IMAGE_ONLY_GEN_IMAGES = 1

# Text-only ad: no media, just headline + description
TEXT_ONLY_DECOMPOSE_TOKENS_IN = 500
TEXT_ONLY_DECOMPOSE_TOKENS_OUT = 1000
TEXT_ONLY_REWRITE_TOKENS_IN = 800
TEXT_ONLY_REWRITE_TOKENS_OUT = 800


# ---------------------------------------------------------------------------
# Probing video duration
# ---------------------------------------------------------------------------

def ffprobe_duration(video_path: Path) -> Optional[float]:
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
# Per-row cost estimation (format-aware)
# ---------------------------------------------------------------------------

def estimate_row_cost(row: dict, videos_dir: Path) -> dict:
    creative_id = (row.get("creative_id") or "").strip()
    fmt = (row.get("creative_format") or "").strip()

    if fmt == "Text":
        cost_decompose = (
            TEXT_ONLY_DECOMPOSE_TOKENS_IN / 1_000_000 * GEMINI_PRO_INPUT_PER_1M_TOKENS
            + TEXT_ONLY_DECOMPOSE_TOKENS_OUT / 1_000_000 * GEMINI_PRO_OUTPUT_PER_1M_TOKENS
        )
        cost_rewrite = (
            TEXT_ONLY_REWRITE_TOKENS_IN / 1_000_000 * GEMINI_PRO_INPUT_PER_1M_TOKENS
            + TEXT_ONLY_REWRITE_TOKENS_OUT / 1_000_000 * GEMINI_PRO_OUTPUT_PER_1M_TOKENS
        )
        return {
            "creative_id": creative_id,
            "creative_format": fmt,
            "duration_s": None,
            "scenes": None,
            "characters": None,
            "cost_decompose": cost_decompose,
            "cost_sheets": 0.0,
            "cost_panels": 0.0,
            "cost_rewrite": cost_rewrite,
            "cost_total": cost_decompose + cost_rewrite,
            "assumption_notes": "text-only ad — two Gemini sync calls, no images",
        }

    if fmt == "Image" or (fmt in ("Shopping", "Maps") and (row.get("r2_public_url") or "").strip()):
        cost_decompose = (
            IMAGE_ONLY_DECOMPOSE_TOKENS_IN / 1_000_000 * GEMINI_PRO_INPUT_PER_1M_TOKENS
            + IMAGE_ONLY_DECOMPOSE_TOKENS_OUT / 1_000_000 * GEMINI_PRO_OUTPUT_PER_1M_TOKENS
        )
        cost_panels = IMAGE_ONLY_GEN_IMAGES * NANO_BANANA_PRO_PER_IMAGE
        cost_rewrite = (
            IMAGE_ONLY_DECOMPOSE_TOKENS_OUT / 1_000_000 * GEMINI_PRO_INPUT_PER_1M_TOKENS
            + 1000 / 1_000_000 * GEMINI_PRO_OUTPUT_PER_1M_TOKENS
        )
        return {
            "creative_id": creative_id,
            "creative_format": fmt,
            "duration_s": None,
            "scenes": None,
            "characters": None,
            "cost_decompose": cost_decompose,
            "cost_sheets": 0.0,
            "cost_panels": cost_panels,
            "cost_rewrite": cost_rewrite,
            "cost_total": cost_decompose + cost_panels + cost_rewrite,
            "assumption_notes": "image-only ad — simpler pipeline, single panel",
        }

    # YouTubeVideo (default video branch)
    fname = f"{creative_id}.mp4"
    video_path = videos_dir / fname
    duration = ffprobe_duration(video_path)

    if duration is None:
        duration = DEFAULT_DURATION_S
        duration_source = "default assumption (file missing or ffprobe unavailable)"
    else:
        duration_source = "ffprobe"

    scenes_est = max(MIN_SCENES, min(MAX_SCENES, int(round(duration * SCENES_PER_SECOND))))
    characters_est = DEFAULT_CHARACTERS

    # If we have a decompose sidecar already, use exact counts
    sidecar = Path("step4_workspace/scenes") / f"{creative_id}.json"
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

    video_tokens_in = duration * GEMINI_PRO_VIDEO_TOKENS_PER_SECOND
    cost_decompose = (
        video_tokens_in / 1_000_000 * GEMINI_PRO_INPUT_PER_1M_TOKENS
        + DECOMPOSE_OUTPUT_TOKENS / 1_000_000 * GEMINI_PRO_OUTPUT_PER_1M_TOKENS
    )

    cost_sheets = characters_est * NANO_BANANA_PRO_PER_IMAGE
    cost_panels = scenes_est * NANO_BANANA_PRO_PER_IMAGE

    cost_rewrite = (
        REWRITE_INPUT_TOKENS_BASE / 1_000_000 * GEMINI_PRO_INPUT_PER_1M_TOKENS
        + REWRITE_OUTPUT_TOKENS / 1_000_000 * GEMINI_PRO_OUTPUT_PER_1M_TOKENS
    )

    return {
        "creative_id": creative_id,
        "creative_format": fmt or "YouTubeVideo",
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

def is_candidate(row: dict) -> bool:
    """A row is a Step 4 candidate if it's analysable AND missing one or both docx URLs."""
    if (row.get("competitor_analysis_docx_r2_url") or "").strip() and (row.get("supernova_rewrite_docx_r2_url") or "").strip():
        return False  # already done
    fmt = (row.get("creative_format") or "").strip()
    has_r2 = bool((row.get("r2_public_url") or "").strip())

    if fmt == "Text":
        # Text rows are candidates if they have copy
        return bool((row.get("ad_headline") or "").strip() or (row.get("ad_description") or "").strip())
    if fmt in ("YouTubeVideo", "Image"):
        return has_r2
    if fmt in ("Shopping", "Maps"):
        return has_r2
    return False


def candidate_rows(master_rows: list[dict]) -> list[dict]:
    return [r for r in master_rows if is_candidate(r)]


def apply_scope(rows: list[dict], *, random_n: Optional[int],
                ids: Optional[list[str]], all_flag: bool,
                start_date: Optional[str]) -> list[dict]:
    if ids:
        wanted = set(ids)
        return [r for r in rows if r.get("creative_id", "") in wanted]
    if start_date:
        # Google's Transparency Center doesn't expose a "first shown" date for India ads;
        # filter by creative_last_shown_date instead (the only date column available).
        return [r for r in rows if (r.get("creative_last_shown_date") or "") >= start_date]
    if random_n:
        if len(rows) <= random_n:
            return list(rows)
        return random.sample(rows, random_n)
    if all_flag:
        return list(rows)
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
    scope.add_argument("--random", type=int, metavar="N",
                       help="Estimate cost for N random candidate rows.")
    scope.add_argument("--ids", type=str,
                       help="Comma-separated creative_ids to estimate.")
    scope.add_argument("--all", action="store_true",
                       help="All candidate rows in the master.")
    scope.add_argument("--start-date", type=str,
                       help="Only rows with creative_last_shown_date >= this YYYY-MM-DD.")

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

    if args.videos_dir:
        videos_dir = Path(args.videos_dir)
    else:
        candidates = sorted(Path("videos").glob(f"{competitor}-*"))
        videos_dir = candidates[-1] if candidates else Path("videos") / f"{competitor}-unknown"

    cands = candidate_rows(master_rows)
    selected = apply_scope(
        cands,
        random_n=args.random,
        ids=args.ids.split(",") if args.ids else None,
        all_flag=args.all,
        start_date=args.start_date,
    )

    estimates = [estimate_row_cost(r, videos_dir) for r in selected]

    total_cost = sum(e["cost_total"] for e in estimates)
    by_format = {}
    for e in estimates:
        by_format[e["creative_format"]] = by_format.get(e["creative_format"], 0) + 1

    if args.json:
        print(json.dumps({
            "competitor": competitor,
            "master_total_rows": len(master_rows),
            "candidate_rows": len(cands),
            "selected_rows": len(estimates),
            "format_breakdown": by_format,
            "total_cost_usd": round(total_cost, 4),
            "estimates": estimates,
        }, indent=2))
        return 0

    # Human report
    print()
    print(f"google-ads-video-analysis — Step 4 cost estimate")
    print(f"─" * 60)
    print(f"competitor:          {competitor}")
    print(f"master total rows:   {len(master_rows)}")
    print(f"candidate rows:      {len(cands)}  (missing one or both docx URLs)")
    print(f"selected for est:    {len(selected)}")
    if by_format:
        breakdown = ", ".join(f"{n} {fmt}" for fmt, n in sorted(by_format.items()))
        print(f"format breakdown:    {breakdown}")
    print(f"videos dir probed:   {videos_dir}")
    print()
    if not estimates:
        print("Nothing to estimate. Either every candidate row already has both docx")
        print("URLs (Step 4 already done) or your scope filter matched nothing.")
        return 0

    estimates_sorted = sorted(estimates, key=lambda e: e["cost_total"])
    print(f"Per-row breakdown (sorted cheapest → most expensive):")
    print(f"  {'creative_id':<24} {'format':<14} {'dur':>6} {'sc':>3} {'ch':>3} "
          f"{'$decomp':>9} {'$sheets':>9} {'$panels':>9} {'$rewrite':>9} {'TOTAL $':>9}")
    for e in estimates_sorted:
        dur = f"{e['duration_s']}s" if e['duration_s'] is not None else "—"
        sc = str(e['scenes']) if e['scenes'] is not None else "—"
        ch = str(e['characters']) if e['characters'] is not None else "—"
        cid = (e['creative_id'] or '—')[:22]
        print(f"  {cid:<24} {e['creative_format']:<14} {dur:>6} {sc:>3} {ch:>3}"
              f" {e['cost_decompose']:>9.4f} {e['cost_sheets']:>9.4f}"
              f" {e['cost_panels']:>9.4f} {e['cost_rewrite']:>9.4f} {e['cost_total']:>9.4f}")

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
