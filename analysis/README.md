# analysis/ — competitor-ad rank-over-time analysis

Turns the dated scrape snapshots into rank-over-time charts and winner/loser
verdicts per competitor. **Phase 1 (this folder) is free — pure Python, no API.**

## The model (git holds the precious text)

- **`history/{pipeline}/{competitor}.csv`** — the append-only **source of truth**.
  One row per ad per scrape date (rank, page_rank, start date, media type). Only
  grows; never rewritten. One file per competitor → two people on different
  competitors never clash.
- **`derived/{pipeline}/{competitor}_*.csv`** — rebuilt from history each run
  (rank pivot/timeline, per-ad metrics, weekly volume). Committed for convenience
  (open the pivot in Sheets to *see* the rank chart) but treat as build output.
- **`reports/{date}_{competitor}_{pipeline}_review.md`** — human-readable summary.

## How to run (per competitor)

```bash
# 1. fold the dated snapshots into the history log (idempotent; --scrape FILE for one)
python3 analysis/scripts/build_history.py     --pipeline facebook --competitor duolingo --backfill
# 2. metrics + the 4-tier verdict
python3 analysis/scripts/compute_rank_metrics.py --pipeline facebook --competitor duolingo
# 3. the rank chart (wide pivot + long timeline)
python3 analysis/scripts/build_rank_chart.py  --pipeline facebook --competitor duolingo
# 4. the markdown review
python3 analysis/scripts/build_report.py      --pipeline facebook --competitor duolingo
```

Re-running is always safe: history is idempotent (re-ingesting a scrape replaces
that date's rows); everything in `derived/` and `reports/` is regenerated from
scratch. After a new scrape, run all four and commit.

## Verdict tiers (longevity primary, rank confirmatory)

| verdict | meaning |
|---|---|
| `strong_winner` | ran > 45 days AND spent ≥ half its life in the page's top 25% |
| `winner` | ran ≥ 15 days (or seen ≥ 3 weeks) AND best rank in top-10 / top-10% of page |
| `loser` | gone from the latest scrape and never won |
| `sore_loser` | *(needs inactive-ad scraping — inert today)* |
| `new` | first seen ≤ 7 days ago, ≤ 2 scrapes — too early to judge |
| `undecided` | still live, in-flight |

A winner that later disappears **stays** a winner with `is_retired=true` (never
demoted). `verdict_confidence` is `low` for absence-inferred / lower-bound calls.

> **Caveat:** rank is the ad library's *impression ordering* — a position proxy,
> not a measured performance metric (no CTR/CVR/ROAS). "Winner" = the advertiser
> sustained it and the platform surfaced it (revealed preference), not proof of
> conversion. Longevity carries the verdict; rank only corroborates.

## Known data caveats (surfaced while building)

- **`facebook_page_id` is not stable across scrapes** for some advertisers (e.g.
  ewa), so presence/retirement is judged at the competitor level (`ad_id`),
  not per page.
- A few June snapshots use an **experimental scraper schema** (`library_id`,
  `is_active`, `spend`, `impressions` …). `build_history.py` skips non-standard
  files and logs `[skip]`; those competitors show only their conforming dates.
  That richer schema may be worth supporting later (it carries delivery signals).
- Run-length needs `ad_start_date`; it's sparse and missing entirely on Google,
  so those `run_days` are lower bounds. Longevity certainty grows as history
  accrues across more scrapes.
