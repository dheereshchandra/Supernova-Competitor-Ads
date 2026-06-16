#!/usr/bin/env python3.13
"""Classify a competitor that returned 0 ads (AFTER a cooled retry) as either genuinely
EMPTY (no active ads — expected, no action) or BLOCKED (a real, recent advertiser still
returning 0 — worth a human's attention). Used by tools/daily-scrape/scrape.sh.

Prints ONE line on stdout:   EMPTY|<note>   or   BLOCKED|<note>

A 0-ad result alone can't *prove* "throttled" vs. "stopped advertising", so we lean on how
real/recent an advertiser the competitor is (from the free-analysis history file, which
records every ad seen per scrape_date):
  - no history / no dated ads      -> BLOCKED  (never scraped clean — check the page id / first run)
  - peak ads on any one day <= 5   -> EMPTY    (never a meaningful advertiser, e.g. memrise)
  - last advertised <= RECENT days -> BLOCKED  (was active days ago, 0 now even cooled — concerning)
  - last advertised  > RECENT days -> EMPTY    (no ads for a while — most likely stopped; note the date)

The retry in scrape.sh already separates the *recoverable* (throttled) cases out before this
runs, so anything reaching here is 0-ads on two attempts including one on a cooled IP — which
makes "no active ads right now" the most likely truth for a stale advertiser.
"""
import collections
import csv
import datetime
import pathlib
import sys

RECENT_DAYS = 9   # advertised within this many days => still treat 0-now as a real concern
EMPTY_PEAK = 5    # peak ads/day at or below this => never a meaningful advertiser


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("BLOCKED|no slug given")
        return
    slug = sys.argv[1].strip()
    # repo root = two levels up from tools/daily-scrape/classify_zero.py
    root = pathlib.Path(__file__).resolve().parents[2]
    hist = root / "analysis" / "history" / "facebook" / f"{slug}.csv"
    if not hist.exists():
        print("BLOCKED|no scrape history — verify the page id (possible first run / bad config)")
        return

    per_day: collections.Counter = collections.Counter()
    try:
        with open(hist, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                date = (row.get("scrape_date") or "").strip()[:10]
                if date:
                    per_day[date] += 1
    except (OSError, csv.Error) as exc:
        print(f"BLOCKED|could not read history ({exc})")
        return

    if not per_day:
        print("BLOCKED|history has no dated ads — verify the page id")
        return

    peak = max(per_day.values())
    last_date = max(per_day)
    try:
        age = (datetime.date.today() - datetime.date.fromisoformat(last_date)).days
    except ValueError:
        age = -1

    if peak <= EMPTY_PEAK:
        print(f"EMPTY|genuinely no active ads (only ever {peak} ad(s) in history; last {last_date})")
        return
    if 0 <= age <= RECENT_DAYS:
        print(f"BLOCKED|real advertiser ({peak} ads peak) still 0 after a cooled retry — "
              f"last advertised {last_date} ({age}d ago); throttle or a page issue — check")
        return
    age_txt = f"{age}d" if age >= 0 else "a while"
    print(f"EMPTY|no active ads for {age_txt} (last advertised {last_date}, {peak} ads peak) "
          f"— likely stopped advertising")


if __name__ == "__main__":
    main()
