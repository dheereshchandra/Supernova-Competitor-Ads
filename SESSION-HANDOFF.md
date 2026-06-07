# Session Handoff — Competitor-Ad Analysis System

> Running status so this work can resume in any workspace. Last updated 2026-06-07.
> Read this first, then the linked docs.

## What this project is
A competitor-ad intelligence system (Facebook + Google) for Supernova. It scrapes
each competitor's live ads, tracks how they perform **over time**, and answers 12
strategic questions (volume, format mix, winners/losers, run-days, win-ratios,
script similarity & replication, FB↔Google transfer). Git holds the small precious
text (scripts, master CSVs with R2 links, the analysis); Cloudflare R2 holds the
heavy media. See `README.md` (collaboration model) and `analysis/README.md` (the
analysis system + run recipes).

## ✅ BUILT & MERGED (PRs #1–#6) — fully working
The whole analysis system is on `main` and validated end-to-end on a real Mac.

**Free rank pipeline** (`analysis/scripts/`, no API):
`build_history.py` (dated snapshots → append-only per-competitor rank history;
`--backfill` for FB, `--from-master` for Google) → `compute_rank_metrics.py`
(winners/losers via 4 tiers: strong_winner >45d & ≥½ life top-25%; winner ≥15d &
top-10/10%; loser gone-&-never-won; sore_loser=inactive[inert]; +new/undecided;
retired winners keep `is_retired`) → `build_rank_chart.py` (wide rank pivot = the
chart) → `build_report.py` (markdown review). `run_all_free.sh <pipeline>` = all
competitors.

**Paid enrichment** — Gemini **Flash ONLY, never Pro** (hard cost rule):
`detect_language.py`, `transcribe_tag.py` (1 Flash call/video → transcript +
format + language, cached/idempotent), `embed_scripts.py`, `script_cluster.py`
(script_group_id + replication_type), `fb_google_overlap.py` (FB↔Google transfer).
`run_enrichment.sh <pipeline> <competitor> [--full]` chains it all (defaults to a
cheap `--limit 5` calibration); `preflight_enrichment.py` gates it. Outputs land in
`analysis/{enrichment,derived,reports}/` and are committed (teammates reuse
transcripts → never re-pay).

**Design docs:** `.context/rank-tracking-brainstorm.md` + `-addendum-inactive.md`
(workspace-local). Gap analysis of the 12 questions is in the plan file / memory.

## ✅ Operationally validated (on the operator's Mac)
- **Facebook Duolingo**: full enrichment run + pushed (40 transcripts, by_language/
  by_format/by_replication). Insights: app-screencast-heavy; heavy script reuse
  (17 visual_variants, 5 exact_replicas vs 12 unique); originals win more than copies.
- **Google Duolingo**: full enrichment run + pushed (19 video transcripts). Mostly
  `new` verdicts (Google has only ~2 days of history; longevity needs more scrapes).

## How to run (the everyday rhythm)
```bash
cd <repo>
git pull
bash analysis/scripts/run_enrichment.sh facebook <competitor> --full
git add -A && git commit -m "enrichment: <competitor> facebook" && git push
```
Full from-scratch workflow (scrape→download→R2→analyze→push), incl. the FB
Claude-in-Chrome scrape and the Google CLI scrape: see chat / `facebook/HANDOVER.md`
+ `google/README.md`. Quick map:
- **FB scrape** = Claude-in-Chrome (paste `facebook/scraper_prompt.md`) → `inputs/`.
- **Google scrape** = `python3 scripts/scrape_google_ads.py --competitor X --region IN`
  (Terminal; ⛔ guardrail: 1 competitor/run, 24h gaps).
- Download/upload: `download_*_ads.py` → `upload_to_r2.py`.
- Then the analysis rhythm above.

## ⚙️ Setup on a fresh Mac
1. `pip3.13 install --user --break-system-packages google-genai numpy boto3 yt-dlp`
2. `.env` with R2 + Gemini keys — put it at **repo root** (works for everything) and/or
   `facebook/.env`. **Do NOT wrap values in quotes** (Mac smart-quotes break the API;
   the loaders now strip them, but bare values are safest).
3. `python3.13 facebook/scripts/preflight.py` and
   `python3.13 analysis/scripts/preflight_enrichment.py` → both READY.

## 🩹 Operational gotchas hit & fixed (so the friend won't)
- **Smart quotes in `.env`** → `'ascii' codec can't encode '”'`. Fixed: loaders
  strip curly quotes (PR #5). Use bare values.
- **R2 403 on rehydrate** → bucket public access is off. Fixed: `rehydrate.py`
  downloads **authenticated** via R2 keys (PR #5); finds `.env` in any folder (PR #6).
- **Flash model name**: `gemini-flash-latest` works; embeddings `gemini-embedding-001`.
- **git push rejected (non-fast-forward)** → `git pull --no-rebase` then `git push`
  (if a merge editor opens and you close it blank, run `git commit --no-edit`).
- **`page_id` unstable across FB scrapes** (ewa) → presence judged at competitor level
  by `ad_id`. **Master CSVs are latest-only** → time series comes from dated `inputs/`.

## 📁 Data locations
- **Git (committed):** scripts, `*/master/*.csv` (R2 links), `*/inputs/*.csv` (FB
  snapshots; Google now too), `analysis/{history,derived,reports,enrichment}/`.
- **R2 (durable media):** videos/images/docs, referenced by `r2_public_url` in masters.
- **Local cache (gitignored):** `{facebook,google}/{videos,images}/{slug}-{date}/`.
  Pull on demand: `python3 tools/rehydrate.py --pipeline facebook --competitor X`.

## 🔬 IN PROGRESS — terminal Facebook scraper (the current experiment)
Goal: move the FB scrape off Claude-in-Chrome to a pure terminal command (Google is
already terminal). **Success bar (per operator): EVERY field must match a
Claude-in-Chrome scrape, zero misses — not just ad-id recall.**

State:
- `facebook/scripts/fb_scrape_probe.py` (PR #7) — proved Meta lets a Playwright
  browser load the ads (no anti-bot block). ✅
- `facebook/scripts/fb_scrape.py` + `fb_scrape_diff.py` (PR #8) — first cut. Result:
  **100% ad-id recall** on Duolingo's page, but metadata (`media_type`, `start_date`,
  `primary_text`) came back **blank** — the card-container detection grabbed too small
  a wrapper, and media needs hover.
- **Latest push (this session):** rewrote `fb_scrape.py` — (a) container fix: climb to
  the largest ancestor still holding exactly one "Library ID" (no fragile classes),
  (b) added hover (loads `<video>`/`<img>` + CDN URLs), (c) `--debug` dumps the first
  card's HTML to `fb_card_debug.html`, (d) prints per-field fill-rates.

Next step (the fix loop):
1. `python3.13 facebook/scripts/fb_scrape.py "Duolingo" --debug`
2. `python3.13 facebook/scripts/fb_scrape_diff.py <new_csv> <reference_csv>`
3. If any field is still blank/wrong → share `fb_card_debug.html` so the exact Meta
   DOM selectors can be nailed; repeat until every field agrees ~100%.
4. **Best benchmark:** do a *same-day* Claude-in-Chrome scrape of the same competitor
   and diff against THAT (the old `06-04` CSV has blank start-dates + a different ad
   set, so it's an imperfect reference).
5. Once faithful: add carousel `creative_index` splitting + the per-page mapping gaps
   (e.g. Duolingo English Test page `1829461027108598` isn't in the map), then wire it
   into the pipeline as the FB Step-1.
Fallback if DOM stays fragile: capture Meta's GraphQL responses (structured data)
instead of scraping the DOM.

## 🔀 PR history
#1 Phase 1 (free rank) · #2 Phase 0+2 (Google snapshots + Flash enrichment) ·
#3 Phase 3 (script replication + FB↔Google) · #4 ops (Google seed + runners) ·
#5 authenticated R2 + smart-quote tolerance · #6 .env found anywhere ·
#7 FB scrape probe · #8 first-cut terminal FB scraper. (All merged except the
in-progress scraper iteration.)

## 📌 Open decisions / later
- Format taxonomy: re-author a clean schema (the seed CSV is Supernova's own ads).
- ">95% script match" threshold + similarity thresholds: calibrate on real data.
- Inactive-ad scraping (sore_loser tier) — designed, not built (see addendum).
- Real Google scrapes to build Google longevity (currently ~2 days only).
