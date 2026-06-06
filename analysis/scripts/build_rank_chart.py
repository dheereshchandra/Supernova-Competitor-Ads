#!/usr/bin/env python3
"""
build_rank_chart.py — Phase 1, script 3 of the competitor-ad analysis system.

Regenerates the two rank-over-time views from the history log (+ enriched
metrics for the verdict column). Rebuilt from scratch each run.

Outputs (under analysis/derived/{pipeline}/):
  {competitor}_rank_timeline.csv  long form: one row per (ad, scrape_date),
      with page_rank, present, and the rank delta vs the previous observation.
  {competitor}_rank_pivot.csv     wide form: one row per ad, one column per
      scrape_date (cell = page_rank, blank = absent that scrape). Sorted so the
      best-ranked / longest-lived ads float to the top — this is the literal
      "rank chart" you open in a spreadsheet.

CSV only — no chart images are committed (they produce noisy git diffs; open the
pivot in Sheets to see the lines).

Usage:
    python3 analysis/scripts/build_rank_chart.py --pipeline facebook --competitor duolingo
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional


def repo_root(explicit: Optional[str]) -> Path:
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def days_between(a: str, b: str) -> Optional[int]:
    try:
        return (date.fromisoformat(b) - date.fromisoformat(a)).days
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pipeline", required=True, choices=["facebook", "google"])
    ap.add_argument("--competitor", required=True)
    ap.add_argument("--base", default=None)
    args = ap.parse_args()

    root = repo_root(args.base)
    slug = args.competitor.lower().strip()
    hpath = root / "analysis" / "history" / args.pipeline / f"{slug}.csv"
    if not hpath.exists():
        raise SystemExit(f"[error] no history: {hpath} (run build_history.py first)")
    rows = read_csv(hpath)

    derived = root / "analysis" / "derived" / args.pipeline
    epath = derived / f"{slug}_enriched.csv"
    enr = {e["ad_id"]: e for e in read_csv(epath)} if epath.exists() else {}

    all_dates = sorted({r["scrape_date"] for r in rows})
    by_ad: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_ad[r["ad_id"]].append(r)

    # ---- long timeline (observed rows + delta vs previous observation) ----
    timeline: list[dict] = []
    for ad_id, ar in by_ad.items():
        ar.sort(key=lambda r: r["scrape_date"])
        prev_rank: Optional[int] = None
        prev_date: Optional[str] = None
        for r in ar:
            rank = int(r["page_rank"]) if r["page_rank"].isdigit() else None
            delta = (prev_rank - rank) if (prev_rank is not None and rank is not None) else ""
            gap = days_between(prev_date, r["scrape_date"]) if prev_date else ""
            timeline.append({
                "pipeline": args.pipeline, "competitor": slug,
                "page_id": r["page_id"], "ad_id": ad_id,
                "scrape_date": r["scrape_date"], "page_rank": r["page_rank"],
                "row_rank": r["row_rank"], "present": "true",
                "page_rank_delta": delta,          # positive = improved (toward #1)
                "days_since_prev_obs": gap,
            })
            prev_rank, prev_date = rank, r["scrape_date"]

    tcols = ["pipeline", "competitor", "page_id", "ad_id", "scrape_date",
             "page_rank", "row_rank", "present", "page_rank_delta", "days_since_prev_obs"]
    tpath = derived / f"{slug}_rank_timeline.csv"
    derived.mkdir(parents=True, exist_ok=True)
    with tpath.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=tcols, extrasaction="ignore")
        w.writeheader(); w.writerows(timeline)

    # ---- wide pivot (the "rank chart") ----
    pivot: list[dict] = []
    for ad_id, ar in by_ad.items():
        ar.sort(key=lambda r: r["scrape_date"])
        rank_on = {r["scrape_date"]: r["page_rank"] for r in ar}
        e = enr.get(ad_id, {})
        row = {
            "page_id": ar[-1]["page_id"], "page_name": ar[-1]["page_name"],
            "ad_id": ad_id, "media_type": ar[-1]["media_type"],
            "verdict": e.get("verdict", ""),
            "first_seen": e.get("first_seen", ar[0]["scrape_date"]),
            "last_seen": e.get("last_seen", ar[-1]["scrape_date"]),
            "present_now": e.get("present_latest", ""),
            "best_page_rank": e.get("best_page_rank", ""),
            "run_days": e.get("run_days", ""),
        }
        for dt in all_dates:
            row[dt] = rank_on.get(dt, "")     # blank = absent that scrape
        pivot.append(row)

    def sort_key(row):
        try:
            best = int(row["best_page_rank"])
        except (ValueError, TypeError):
            best = 10 ** 9
        return (row["page_id"], best)

    pivot.sort(key=sort_key)
    pcols = ["page_id", "page_name", "ad_id", "media_type", "verdict",
             "first_seen", "last_seen", "present_now", "best_page_rank",
             "run_days"] + all_dates
    ppath = derived / f"{slug}_rank_pivot.csv"
    with ppath.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=pcols, extrasaction="ignore")
        w.writeheader(); w.writerows(pivot)

    print(f"{slug}: {len(all_dates)} scrape dates, {len(by_ad)} ads")
    print(f"  -> {tpath}")
    print(f"  -> {ppath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
