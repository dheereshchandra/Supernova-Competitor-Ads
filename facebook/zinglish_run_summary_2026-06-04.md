# Zinglish FB Ads Pipeline — Run Summary (2026-06-04)

**Scope run:** Step 2 prep + Step 2 (download) + Step 3 (master merge) + Step 4 preparation.
**Step 4 analysis/API processing NOT executed** — awaiting explicit approval.

---

## Country selection
- New scrape `target_country` = **IN for all 31 rows**. India has active ads, so per the
  country-selection rule the pipeline **proceeded with the India dataset**. No switch to
  All Countries was required.

## 1. Scrape analysis & master comparison

Input: `inputs/fb-ads-zinglish-2026-06-04-1345.csv` (saved from the uploaded scrape).
Compared against `master/zinglish.csv` keyed on **(ad_library_id, creative_index_in_ad)**.

| Metric | Value |
|---|---|
| Total rows in new scrape | **31** |
| Unique keys in scrape | 31 (0 in-scrape duplicates) |
| Page-wise breakdown | Zinglish (page_id 680109015195106): 31 |
| Media-type breakdown | Video: 31 (Image/Carousel: 0) |
| Carry-forward rows (already in master) | **31** |
| Genuinely new rows | **0** |
| Retired rows (in master, absent from scrape) | **0** |
| Master size before | 31 |
| Final projected master size | **31** |

**Key finding:** the 2026-06-04 scrape contains the **exact same 31 ad creatives** as the
2026-05-26 master — identical ID set, no additions, no retirements. Zinglish is still running
the same active ad set.

## 2. Step 2 — media download
- Genuinely new rows = 0 → **no new media to download**.
- All 31 creatives already have local videos (`videos/zinglish-2026-05-26/`) and R2 URLs.
- Assets downloaded this run: **0** · Failed: **0** · Completion: **100% (nothing required)**.

## 3. Step 3 — master merge

Dry-run, then real merge (`scripts/upload_to_r2.py`). Backup taken first:
`master/zinglish.csv.bak.pre-merge-20260604-1345`.

| Merge counts | Dry-run | Executed |
|---|---|---|
| Carry-forward | 31 | 31 |
| New (uploaded) | 0 | 0 |
| Retired (preserved) | 0 | 0 |
| Duplicates | 0 | 0 |
| Errors | 0 | 0 |

Post-merge integrity verification:
- Master rows: **31** (unchanged) · duplicate keys: **0**
- Existing R2 video URLs changed: **0** (all preserved)
- Existing analysis/rewrite docx URLs preserved: **5 / 5**
- `first_scrape_run_date`: all **2026-05-26** (preserved)
- `latest_scrape_run_date`: all advanced to **2026-06-04** (tracking updated per pipeline rules)
- No existing rows overwritten, edited, or deleted.

## 4. Step 4 preparation (NOT executed)

**Genuinely new ads this scrape = 0**, so the "top 20 newly added" set is **empty → $0**.

For reference, the standard fallback scope (`--top-by-rank 20` over un-analyzed master
candidates) covers the **26 carry-forward ads still missing analysis docs** (5 of 31 were
analyzed in the earlier sample run). Top-20-by-rank estimate:

| ad_library_id | type | scenes | $total |
|---|---|---|---|
| 1505919334867604 | Video | 2 | 0.2080 |
| 908822938160022 | Video | 2 | 0.2087 |
| 2145402302955929 | Video | 2 | 0.2088 |
| 895901269731389 | Video | 2 | 0.2088 |
| 894945046633710 | Video | 2 | 0.2092 |
| 1421135246404699 | Video | 2 | 0.2092 |
| 826441597149033 | Video | 3 | 0.2505 |
| 25674228382269402 | Video | 3 | 0.2508 |
| 1446451490465131 | Video | 3 | 0.2509 |
| 1299322238926571 | Video | 3 | 0.2510 |
| 1443156474268077 | Video | 3 | 0.2511 |
| 1417738519758197 | Video | 3 | 0.2513 |
| 1428345402211481 | Video | 3 | 0.2516 |
| 1981093915820751 | Video | 3 | 0.2517 |
| 1286723966731755 | Video | 4 | 0.2922 |
| 1214331300401198 | Video | 4 | 0.2922 |
| 1228162876124945 | Video | 4 | 0.2922 |
| 2004457904289111 | Video | 4 | 0.2926 |
| 1457798545962459 | Video | 4 | 0.2928 |
| 1414823376812512 | Video | 5 | 0.3354 |

- Impression rank = `row_rank` (default "top" definition). All candidates are Video.
- **Step 4 cost estimate (top 20): $5.06**, wall-clock 55–90 min.
- Pricing constants are mid-2025 figures — verify against actual Gemini billing.

## Errors / warnings / data-quality notes
- `boto3` was missing in the sandbox on first attempt; installed and re-ran cleanly. Merge
  errored *before* touching the master, so no partial writes occurred.
- No genuinely new ads means no creative refresh from Zinglish since the last scrape — worth
  noting for the competitive-tracking cadence.
- No scientific-notation ID corruption; all IDs 15–17 digits, clean.

## Awaiting your decision on Step 4
Since there are **0 newly added ads**, there is nothing to analyze under the "top 20 newly
added" definition. Options:
1. **Skip Step 4** this cycle (recommended — no new creative).
2. **Run Step 4 on the 26 un-analyzed carry-forwards** (top 20 = ~$5.06) to backfill analysis
   docs for previously-scraped ads.

Reply with your choice — no Gemini/API calls will fire without explicit approval.
