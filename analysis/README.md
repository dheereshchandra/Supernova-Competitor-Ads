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

## Enrichment (Gemini **Flash** — runs on YOUR Mac)

Adds `language`, `format`, and `transcript` so the metrics can answer per-language,
format-mix, and (later) script-similarity questions. **Flash only, never Pro**
(cost rule). These need `google-genai` + a `GEMINI_API_KEY` in a `.env`, so they
run on your Mac, not in the sandbox. Each runs **once per ad and caches** a
committed sidecar — re-runs only touch new ads, and teammates reuse via `git pull`.

```bash
# language from ad copy (cheap, batched; no videos needed)
python3 analysis/scripts/detect_language.py  --pipeline facebook --competitor duolingo
# transcribe + tag format/production (needs the videos — rehydrate from R2 first)
python3 tools/rehydrate.py                   --pipeline facebook --competitor duolingo
python3 analysis/scripts/transcribe_tag.py   --pipeline facebook --competitor duolingo
# then recompute — metrics auto-pick up the sidecars and add by_language / by_format
python3 analysis/scripts/compute_rank_metrics.py --pipeline facebook --competitor duolingo
python3 analysis/scripts/build_report.py         --pipeline facebook --competitor duolingo
```

Cost: ~$0.005–0.01 per video on Flash (full Facebook corpus ≈ $40–60 one-time,
then ~$1–3/week for new ads). Add `--dry-run` to preview / `--limit N` to test.
Sidecars: `enrichment/{pipeline}/language/{competitor}.csv` and
`enrichment/{pipeline}/transcripts/{competitor}/{ad_id}.json`. The format taxonomy
(presenter_type × device_format × production_type) is a **starter set** in
`transcribe_tag.py` — tune the enum to your "Supernova Ad Formats" vocabulary.

## Phase 3 — script similarity, replication & FB↔Google (on the transcripts)

Once transcripts exist, cluster scripts to answer "which winners share a script",
"how much is translated vs re-shot", and "do FB ads port to Google".

```bash
# 1) embed each ad's English script-signature (cheap; embeddings, not chat)
python3 analysis/scripts/embed_scripts.py    --pipeline facebook --competitor duolingo
# 2) cluster into script groups + label replication_type (OFFLINE, no API)
python3 analysis/scripts/script_cluster.py   --pipeline facebook --competitor duolingo
# 3) cross-platform transfer (needs embeddings for BOTH facebook & google)
python3 analysis/scripts/fb_google_overlap.py --competitor duolingo
# then recompute → enriched gains script_group_id/replication_type + by_replication
python3 analysis/scripts/compute_rank_metrics.py --pipeline facebook --competitor duolingo
python3 analysis/scripts/build_report.py         --pipeline facebook --competitor duolingo
```

`replication_type` per ad: `original` · `exact_replica` (same script/lang/format) ·
`translation_replica` (same script, new language) · `visual_variant` (same script,
new visuals) · `unique` (one-off). Tune `--threshold` on a labelled sample. The
clustering + overlap math is unit-tested on synthetic embeddings; the only API
step is `embed_scripts.py` (and it runs on your Mac).

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
