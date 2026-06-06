#!/usr/bin/env python3
"""
build_report.py — Phase 1, script 4 of the competitor-ad analysis system.

Assembles a human-readable markdown review for one competitor from the derived
enriched + weekly + timeline CSVs. Rebuilt from scratch each run.

Output: analysis/reports/{latest_date}_{competitor}_{pipeline}_review.md

Usage:
    python3 analysis/scripts/build_report.py --pipeline facebook --competitor duolingo
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

CAVEAT = (
    "> **How to read this:** rank is the ad library's *impression ordering*, a "
    "position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). "
    "A \"winner\" means the advertiser **sustained** the ad (longevity, the primary "
    "signal) and the platform **kept surfacing** it (rank, confirmatory) — strong "
    "revealed preference, not proof of conversion. Longevity carries the verdict; "
    "rank only corroborates."
)


def repo_root(explicit: Optional[str]) -> Path:
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _int(x, default=10 ** 9):
    try:
        return int(x)
    except (ValueError, TypeError):
        return default


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pipeline", required=True, choices=["facebook", "google"])
    ap.add_argument("--competitor", required=True)
    ap.add_argument("--base", default=None)
    args = ap.parse_args()

    root = repo_root(args.base)
    slug = args.competitor.lower().strip()
    derived = root / "analysis" / "derived" / args.pipeline
    enriched = read_csv(derived / f"{slug}_enriched.csv")
    weekly = read_csv(derived / f"{slug}_weekly.csv")
    timeline = read_csv(derived / f"{slug}_rank_timeline.csv")
    if not enriched:
        raise SystemExit(f"[error] no enriched data for {slug} "
                         f"(run compute_rank_metrics.py first).")

    dates = sorted({r["last_seen"] for r in enriched} | {r["first_seen"] for r in enriched})
    latest = max(r["last_seen"] for r in enriched)
    verdicts = Counter(r["verdict"] for r in enriched)
    n_pages = len({r["page_id"] for r in enriched})

    def winners_sorted():
        w = [r for r in enriched if r["verdict"] in ("strong_winner", "winner")]
        return sorted(w, key=lambda r: (-_int(r["run_days"], 0), _int(r["best_page_rank"])))

    L: list[str] = []
    L.append(f"# Competitor review — {slug} ({args.pipeline})")
    L.append("")
    L.append(f"*Generated from {len(dates)} scrape date(s), latest {latest}. "
             f"{len(enriched)} ads across {n_pages} page(s).*")
    L.append("")
    L.append(CAVEAT)
    L.append("")

    # ---- verdict summary ----
    L.append("## Verdict mix")
    L.append("")
    L.append("| verdict | count |")
    L.append("|---|---|")
    for v in ["strong_winner", "winner", "undecided", "new", "loser", "sore_loser"]:
        if verdicts.get(v):
            L.append(f"| {v} | {verdicts[v]} |")
    L.append("")
    if not verdicts.get("sore_loser"):
        L.append("*(No `sore_loser`s yet — that tier needs inactive-ad scraping, "
                 "which isn't turned on. Today's `loser`s are inferred from an ad "
                 "disappearing between scrapes.)*")
        L.append("")

    # ---- winners ----
    winners = winners_sorted()
    L.append(f"## Winners ({len(winners)})")
    L.append("")
    if winners:
        L.append("| ad_id | verdict | run_days | best rank | % life top-25% | start | conf |")
        L.append("|---|---|--:|--:|--:|---|---|")
        for r in winners[:30]:
            lb = "≥" if r["run_days_is_lower_bound"] == "True" else ""
            L.append(f"| {r['ad_id']} | {r['verdict']} | {lb}{r['run_days']} | "
                     f"{r['best_page_rank']} | {r['frac_top_25']} | "
                     f"{r['ad_start_date'] or '—'} | {r['verdict_confidence']} |")
        if len(winners) > 30:
            L.append(f"")
            L.append(f"*…and {len(winners) - 30} more (see `{slug}_enriched.csv`).*")
    else:
        L.append("*No certified winners yet — needs ≥15-day longevity, which the "
                 "current scrape history can only confirm for ads carrying a start "
                 "date. This fills in as history accrues.*")
    L.append("")

    # ---- losers / retired ----
    losers = [r for r in enriched if r["verdict"] == "loser"]
    L.append(f"## Losers / disappeared ({len(losers)})")
    L.append("")
    if losers:
        L.append(f"{len(losers)} ad(s) ran briefly or never ranked, then dropped out "
                 f"of the latest scrape. Examples:")
        L.append("")
        L.append("| ad_id | run_days | best rank | times seen | last seen |")
        L.append("|---|--:|--:|--:|---|")
        for r in sorted(losers, key=lambda r: _int(r["best_page_rank"]))[:15]:
            L.append(f"| {r['ad_id']} | {r['run_days']} | {r['best_page_rank']} | "
                     f"{r['times_seen']} | {r['last_seen']} |")
    else:
        L.append("*None yet (no ads have disappeared between scrapes).*")
    L.append("")

    # ---- weekly volume ----
    L.append("## Weekly volume & win-ratio (per page)")
    L.append("")
    if weekly:
        L.append("| page | week | ads live | new | winners | win ratio |")
        L.append("|---|---|--:|--:|--:|--:|")
        for r in weekly:
            L.append(f"| {r['page_name'] or r['page_id']} | {r['week']} | "
                     f"{r['ads_live']} | {r['new_ads']} | {r['winners_live']} | "
                     f"{r['win_ratio']} |")
    L.append("")
    if len(dates) < 3:
        L.append("*Week-on-week deltas are thin until there are ≥3 weekly scrapes; "
                 "with only a couple of dates so far, weekly ≈ scrape-on-scrape.*")
        L.append("")

    # ---- biggest movers (rank changes between observations) ----
    movers = [t for t in timeline if str(t.get("page_rank_delta", "")).lstrip("-").isdigit()
              and int(t["page_rank_delta"]) != 0]
    if movers:
        movers.sort(key=lambda t: abs(int(t["page_rank_delta"])), reverse=True)
        L.append("## Biggest rank movers")
        L.append("")
        L.append("| ad_id | scrape | Δ rank | new rank |")
        L.append("|---|---|--:|--:|")
        for t in movers[:10]:
            d = int(t["page_rank_delta"])
            arrow = "↑" if d > 0 else "↓"
            L.append(f"| {t['ad_id']} | {t['scrape_date']} | {arrow}{abs(d)} | "
                     f"{t['page_rank']} |")
        L.append("")

    reports = root / "analysis" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    out = reports / f"{latest}_{slug}_{args.pipeline}_review.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{slug}: wrote report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
