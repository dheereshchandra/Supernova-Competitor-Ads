# Handoff 03 — Competitive Analysis System (data model + metrics)

**Goal:** turn the scraped competitor data into answers to Supernova's competitive-intelligence
questions — how much competitors ship, what formats they use, which ads win, how they replicate
scripts across languages, and what crosses from Facebook to Google.

**Depends on:** handoff 01 (git/R2 storage for the analysis folder) and handoff 02 (`page_rank`,
so "top per page" is correct). Do those first, or in parallel.

---

## The questions this must answer

1. How many ads do they take live per day / per week, per language?
2. What is the **format mix** — split-screen AI+AI grammar/translation, AI+Human, Human-only,
   pen-&-paper translations, scrolling-text, news/Tonight-show format, etc.?
3. How many ads are **winners** (live > ~15 days, and/or top-rank), overall and per language?
4. How long do winners run (average run-days)?
5. **Win ratio** per week and per creative type / ad format?
6. How many winners share the **same script** (> 95% match)?
7. How many are **replicated across languages** as a translation only (> 95% script match)?
8. How many are replicated with **character or scene changes** (same script, new visuals)?
9. How many **brand-new scripts/formats** are tried weekly, and their win ratio?
10. How often / how fast do they replicate a new script, and what type of replication?
11. **Facebook → Google transfer:** do all FB ads go to Google or only selective ones? Which
    ones overlap — only top FB ads, or something else?

---

## The core idea: shape the data first

Most of these questions are about **time** (per week, run-days, replication speed). The master
spreadsheet only stores each ad's *latest* state, so the time dimension must be added. Don't
overload the master — use three light layers.

### Layer 1 — Master (keep as-is)
The current snapshot of each competitor's ads. Pipeline-owned.

### Layer 2 — History / observations log (NEW — the time machine)
An append-only sheet. **Every scrape appends one row per ad** with: `competitor`, `platform`
(facebook/google), `page_id`/`advertiser_id`, `ad_library_id`, `creative_index_in_ad`,
`language`, `row_rank`, `page_rank`, `present` (true/false), `scrape_date`. This is what makes
volume, run-days, winners, and churn computable. **Bonus:** it can be retro-built by stacking
the per-scrape CSVs already archived in `inputs/`.

### Layer 3 — Enrichment (NEW — computed, stored so you just filter/sort)
Per-ad attributes added by the analysis scripts:
`language`, `format_type` (from the taxonomy), `production_type` (human/AI/mixed — reuse Creative Studio
decompose where it exists), `duration_s`, `is_winner`, `run_days`, `best_page_rank`,
`times_seen`, `weeks_seen`, `script_group_id`, `replication_type`
(original / translation_replica / character_swap / scene_change / new), `variant_role`,
`cross_platform_match_id`.

---

## Building blocks (reusable scripts, in `analysis/scripts/`)

1. **`build_history.py`** — stack all `inputs/` CSVs (+ each new scrape) into the Layer-2 log.
   Pure data; free. *This alone answers Q1, Q3, Q4, Q5 (volume, winners, run-days, win-ratio).*
2. **`detect_language.py`** — tag each ad's language from `ad_primary_text` / transcript (the
   data is country-keyed = all `IN`, so language must be detected). Cheap.
3. **`classify_format.py`** — tag each ad with the **format taxonomy** (see open decision
   below). Reuses Creative Studio decomposition (`production_type`, layout, characters) where present; a
   light Gemini call otherwise. *Answers Q2, Q5-by-format.*
4. **`script_similarity.py`** — transcribe → translate to a common language → embed → cluster.
   One engine answers Q6–Q10: same script, translation replica, character/scene-swap, brand-new
   script, and replication speed (all are clustering + dates).
5. **`fb_google_overlap.py`** — run the same embeddings across both pipelines' masters;
   high-similarity cross-platform pairs = transfers. *Answers Q11.* Hardest; do last.

---

## Build order (tiers, cheapest first)

- **Tier 1 — free, do first:** `build_history.py` → volume per week, winners, average run-days,
  win-ratio per week. Prove it on one competitor with deep history (e.g. `praktika-ai` or
  `english-seekho`) before spending anything.
- **Tier 2 — small cost:** language + format classification → format mix, win-ratio per format.
- **Tier 3 — medium cost:** script-similarity → same-script, replication types, new-vs-replica,
  replication speed.
- **Tier 4 — hardest:** FB→Google overlap.

---

## DECISIONS NEEDED FROM THE HUMAN BEFORE TIER 1 FINISHES

1. **"Winner" definition.** Proposed starting point: an ad **live ≥ 15 days** (measured from the
   history log: first-seen → last-seen, or `ad_start_date` → retirement) **AND** reaching
   **top-100 `page_rank`** in at least one weekly scrape. Longevity is the primary signal; rank
   is secondary (see handoff 02 for why per-page rank matters). Confirm or adjust the
   thresholds.
2. **Format taxonomy.** Formalize a fixed list, seeded from the team's own *"Supernova Ad
   Formats"* sheet (the `Type` column). Observed seed categories include: *translation
   micro-narrative for AI teaching, translation scrolling-text AI teaching, organic teaching
   (pen & paper), news/Tonight-show format, AI tutor product explainer.* Recommended structure
   is a few independent dimensions rather than one label, e.g.:
   - `presenter_type`: AI-only / Human-only / AI+Human / AI+AI / Robot / none
   - `teaching_device`: translation / grammar-correction / scrolling-text / pen-&-paper /
     micro-narrative / news-format / product-explainer
   - `has_subtitles`, `duration_bucket`
   Confirm the canonical vocabulary so classification is consistent.
3. **Priority order** of the 11 questions, if not just cheapest-first.

---

## How the analysis is stored in git (the `analysis/` folder)

```
analysis/
├── LEARNINGS.md              ← running narrative insights (dated bullets)
├── taxonomy/format_taxonomy.md   ← the agreed format vocabulary (single source of truth)
├── history/                  ← the Layer-2 observations log(s), per pipeline/competitor (CSV)
├── scripts/                  ← build_history, detect_language, classify_format,
│                                script_similarity, fb_google_overlap
├── derived/                  ← machine-built datasets: enriched ads, weekly volume,
│                                winners, script clusters (small CSVs)
└── reports/{date}_review.md  ← periodic human-readable competitive reviews
```

All of it is text → commits cleanly. Derived datasets and reports are committed after each
analysis run (same model as the pipeline: data + findings in git, heavy media in R2).

---

## Acceptance criteria (per tier)

- **Tier 1:** for one competitor, produce committed `derived/` CSVs + a `reports/` write-up
  showing ads-launched-per-week, a winners list (run-days + best per-page rank), and weekly
  win-ratio — entirely from the history log, no API spend.
- **Tier 2:** every analysed ad has a `language` and a `format_type` from the agreed taxonomy;
  format-mix and win-ratio-per-format tables produced.
- **Tier 3:** ads grouped by `script_group_id`; each tagged `replication_type`; a report of
  same-script %, translation-replica %, character/scene-swap %, and new-scripts-per-week.
- **Tier 4:** a cross-platform overlap report (which FB ads also appear on Google, and whether
  they skew to top-ranked FB ads).
