# Handoff 02 — Per-Page Rank Fix (so winners on smaller pages aren't missed)

> ⚠️ HISTORICAL (documents the original 26→27-column per-page-rank fix). The live FB schema is now **36 columns** (v2.3 version-expansion) — see `facebook/scraper_prompt.md`.

**Goal:** make the ad rank **restart at 1 for each Facebook page** a competitor runs, so the
creative team's "top 50 / top 100" filter surfaces the best ads of *every* page — not just the
biggest one.

---

## The problem (with real evidence)

A competitor often runs ads from several Facebook pages. **MySivi runs 6 pages.** Meta's Ad
Library sorts each page's ads by impressions (the scraper uses
`sort_data[mode]=total_impressions&direction=desc`), so *within a page*, rank 1 = that page's
top ad.

But the scraper stacks all pages into one list and numbers them **1…N straight through**
(`row_rank` = "1-based position across the entire `allRows` array", per `scraper_prompt.md`
line ~430). So only the first/biggest page gets the low numbers. In the real MySivi master,
the *best* ad of four of the six pages sits at rank **191, 370, 410, and 923** — all below a
top-100 cutoff. The Telugu page's #1 ad (a genuine winner) is invisible.

Analogy: ranking students from 6 schools on one combined leaderboard — the top 100 is all from
the biggest school, and a small school's #1 student lands at rank 410. To see the best from
every school, rank within each school.

---

## The fix: add a `page_rank` column

Introduce a new column `page_rank` = the ad's 1-based position **within its own page's**
impression-sorted list. Keep the existing global `row_rank` too (still useful for "biggest
overall"). The creative team then filters **top-N per `facebook_page_id` by `page_rank`**.

Semantics (match `row_rank`'s existing rules):
- `page_rank` ranks **ads** within a page, in the page's impression order.
- All creative rows of the same ad (same `ad_library_id`, different `creative_index_in_ad`)
  **share** the same `page_rank`, exactly as they share `row_rank`.
- `page_rank` starts at 1 for the first ad of *each* page.

---

## Changes to make

### A. Facebook scraper — `facebook/scraper_prompt.md`

1. In **Step 2f — "Assemble rows for this page"** (around line 326–345), the scraper already
   processes one page at a time in impression order and appends to `allRows`. Add a **per-page
   ad counter** that increments once per ad on that page, and set `page_rank` = that counter on
   every row emitted for that ad. Reset the counter to 0 at the start of each page.
2. Add `page_rank` to the **CSV column schema** (line ~427), immediately **after** `row_rank`
   (schema goes from 26 → 27 columns). Update the description at line ~430 to define both:
   *"`row_rank` = 1-based position across the entire `allRows` array (global, impression order
   across all pages stacked); `page_rank` = 1-based position of the ad within its own page's
   impression-sorted list (restarts at 1 per `facebook_page_id`)."*
3. Keep `row_rank` exactly as it is. Do **not** remove it.

### B. Google scraper — `google/scraper_prompt.md`

Apply the equivalent change. The Google scraper iterates per advertiser entry (`AR…` IDs) and
assigns `row_rank` as a global 1-based position. Add `page_rank` that restarts at 1 per
`advertiser_id`, placed right after `row_rank` in its column list. *(Lower urgency — Google is
secondary; see handoff 04.)*

### C. Master schema — `scripts/upload_to_r2.py` (both pipelines)

Add `"page_rank"` to `MASTER_EXTRA_COLS` so the master CSV always carries the column and it
survives merges. Place it logically next to `row_rank`.

### D. Analysis convention (feeds handoff 03)

Anywhere the creative team or the analysis scripts pick "top ads," group by `facebook_page_id`
(or `advertiser_id` for Google) and rank by `page_rank` — e.g. "top 50 per page." `page_rank`
also becomes one of the enrichment fields in the analysis system.

---

## Backfill note (important)

`page_rank` cannot be perfectly reconstructed for past scrapes — it was never captured. Two
options:
- **Going forward only** (simplest): new scrapes get correct `page_rank`; older rows stay
  blank until re-scraped.
- **Approximate backfill** from the archived per-scrape input CSVs in `inputs/`: for each
  historical scrape file, re-derive a within-page rank by grouping that file's rows by
  `facebook_page_id` and ordering by the original `row_rank`. Reasonable but only as good as
  the archived files. Recommended only if the team wants history immediately.

---

## Acceptance criteria

- A fresh scrape CSV contains a `page_rank` column where **each `facebook_page_id` starts at 1**
  and increments in impression order; multiple creatives of one ad share a `page_rank`.
- `row_rank` is unchanged (still global).
- The master CSV gains the `page_rank` column and preserves it across merges.
- Filtering "top 100 per page" surfaces the top ads of *every* page MySivi runs, including the
  Telugu page — verify the Telugu page's `page_rank=1` ad now appears.
