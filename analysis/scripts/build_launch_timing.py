#!/usr/bin/env python3.13
"""
build_launch_timing.py — Q3: WHEN do they launch ads?

OFFLINE, backfillable. Buckets each ad's TRUE launch date (`ad_start_date` —
100% populated for Facebook; this is FB's "Started running on", NOT the
scrape-derived `first_seen`) by weekday and day-of-month, so you can see the
launch cadence (e.g. "most launches on Mondays / at month-start").

Reads analysis/derived/{pipeline}/{slug}_enriched.csv (one row per ad); writes
analysis/derived/{pipeline}/{slug}_launch_timing.csv — rows of
(bucket_type, bucket, ads, winners, win_ratio).

DATE-DRIFT NOTE: `ad_start_date` is rendered by Facebook relative to the SCRAPE
browser's timezone, which can shift midnight-boundary dates ±1 day. The fix is at
capture time — pin the scrape browser to Asia/Kolkata (see scraper_prompt.md Step 2d).
Do NOT "correct" by adding a day downstream (date.fromisoformat here is exact).

Usage:
    python3.13 analysis/scripts/build_launch_timing.py --pipeline facebook --competitor mysivi
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

WINNER_VERDICTS = {"winner", "strong_winner"}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def repo_root(explicit):
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def d(s):
    try:
        return date.fromisoformat((s or "").strip())
    except ValueError:
        return None


def win_ratio(w: int, a: int) -> float:
    return round(w / a, 3) if a else 0.0


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
    rows = read_csv(derived / f"{slug}_enriched.csv")
    if not rows:
        raise SystemExit(f"[error] no enriched data for {slug} "
                         f"(run compute_rank_metrics.py first).")

    by_weekday = defaultdict(lambda: {"ads": 0, "winners": 0})
    by_dom = defaultdict(lambda: {"ads": 0, "winners": 0})
    no_date = 0
    for r in rows:
        dt = d(r.get("ad_start_date"))
        if dt is None:
            no_date += 1
            continue
        is_win = (r.get("verdict") or "").strip() in WINNER_VERDICTS
        wd = WEEKDAYS[dt.weekday()]
        by_weekday[wd]["ads"] += 1
        by_weekday[wd]["winners"] += 1 if is_win else 0
        by_dom[dt.day]["ads"] += 1
        by_dom[dt.day]["winners"] += 1 if is_win else 0

    out = []
    for wd in WEEKDAYS:  # fixed Mon..Sun order
        v = by_weekday.get(wd, {"ads": 0, "winners": 0})
        out.append({"pipeline": args.pipeline, "competitor": slug,
                    "bucket_type": "weekday", "bucket": wd,
                    "ads": v["ads"], "winners": v["winners"],
                    "win_ratio": win_ratio(v["winners"], v["ads"])})
    for dom in range(1, 32):
        v = by_dom.get(dom)
        if not v:
            continue
        out.append({"pipeline": args.pipeline, "competitor": slug,
                    "bucket_type": "day_of_month", "bucket": str(dom),
                    "ads": v["ads"], "winners": v["winners"],
                    "win_ratio": win_ratio(v["winners"], v["ads"])})

    cols = ["pipeline", "competitor", "bucket_type", "bucket", "ads", "winners", "win_ratio"]
    outpath = derived / f"{slug}_launch_timing.csv"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    with outpath.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    note = f"  ({no_date} ads without ad_start_date)" if no_date else ""
    print(f"{slug}: launch timing -> {outpath}{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
