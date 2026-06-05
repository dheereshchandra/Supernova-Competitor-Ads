# Loora FB Ads Pipeline — Run Summary (2026-06-04)

**Scope run:** Step 2 prep + Step 2 (download) + Step 3 (master merge) + Step 4 preparation.
**Step 4 analysis/API processing NOT executed** — awaiting explicit approval.

---

## Country selection
- New scrape `target_country` = **IN for all 34 rows**. India has active ads, so per the
  country-selection rule the pipeline **proceeded with the India dataset**. No switch to
  All Countries required.

## 1. Scrape analysis & master comparison

Input: `inputs/fb-ads-loora-2026-06-04.csv` (saved from the uploaded scrape).
Compared against `master/loora.csv` keyed on **(ad_library_id, creative_index_in_ad)**.

| Metric | Value |
|---|---|
| Total rows in new scrape | **34** |
| Unique keys in scrape | 34 (0 in-scrape duplicates) |
| Page-wise breakdown | Loora (page_id 105478174979714): 34 |
| Media-type breakdown | Video: 32 · Image: 2 |
| Carry-forward rows (already in master) | **25** |
| Genuinely new rows | **9** (7 Video, 2 Image) |
| Retired rows (in master, absent from scrape) | **26** |
| Master size before | 51 |
| Final projected master size | **60** |
| Final master size (after merge) | **60** ✓ |

**Key finding:** Loora has meaningfully refreshed its creative since the 2026-05-27 master.
**9 new ads** appeared (including 2 image creatives), while **26 older ads** from the prior
scrape are no longer running (retired). 25 ads carry forward unchanged.

## 2. Step 2 — media download

Terminal workflow (`scripts/download_fb_ads.py` for video, `scripts/download_fb_images.py`
for image-only ads), run over the 9 genuinely new rows.

| Metric | Value |
|---|---|
| Assets required (new rows only) | 9 (7 video + 2 image) |
| Total assets downloaded | **9** |
| Failed downloads | **0** |
| Completion percentage | **100%** |

- Videos → `videos/loora-2026-06-04/` (7 × .mp4)
- Images → `images/loora-2026-06-04/` (2 × .jpg)

## 3. Step 3 — master merge

Dry-run, then real merge (`scripts/upload_to_r2.py`). Backup taken first:
`master/loora.csv.bak.pre-merge-20260604-1515`.

| Merge counts | Dry-run | Executed |
|---|---|---|
| Carry-forward | 25 | 25 |
| New (uploaded) | 9 | 9 |
| Retired (preserved) | 26 | 26 |
| Duplicates | 0 | 0 |
| Errors | 0 | 0 |

> The merge was resumed across several shell windows (45s shell cap); the script is
> idempotent and atomic-write checkpointed, so already-uploaded new rows carried forward
> on each pass with no partial writes or data loss. Final run exited 0.

Post-merge integrity verification (current master vs. pre-merge backup):
- Master rows: **51 → 60** · duplicate keys: **0**
- Old rows lost: **0**
- Existing R2 video URLs changed: **0 / 51** (all preserved)
- Existing `competitor_analysis_docx_r2_url` / `supernova_rewrite_docx_r2_url` changed: **0 / 0**
- `first_scrape_run_date` on old rows changed: **0** (preserved)
- **9 new rows:** `first_scrape_run_date` = 2026-06-04, all 9 have `r2_public_url`
- **25 carry-forward rows:** `latest_scrape_run_date` advanced to **2026-06-04**
- **26 retired rows:** preserved untouched — `r2_public_url` intact (26/26),
  `latest_scrape_run_date` left at **2026-05-27** (correct: not in this scrape)
- No existing rows overwritten, edited, or deleted.

## 4. Step 4 preparation (NOT executed)

"Top 20 newly added" — only **9 new ads** exist this cycle, so the candidate set is **all 9**,
ranked by `row_rank` (default impression-rank definition).

| # | ad_library_id | Type | Impression rank (`row_rank`) | Scenes | Est. $ |
|---|---|---|---|---|---|
| 1 | 1758731028824393 | Video | 4 | 12 | 0.6287 |
| 2 | 887166504395248 | Video | 8 | 8 | 0.4600 |
| 3 | 1009996348169330 | Video | 14 | 11 | 0.5865 |
| 4 | 2065316954367727 | Video | 17 | 7 | 0.4182 |
| 5 | 1020433583744483 | Video | 19 | 11 | 0.5865 |
| 6 | 869185468874772 | Video | 26 | 11 | 0.5865 |
| 7 | 1017749350907847 | Video | 30 | 12 | 0.6315 |
| 8 | 1546272363585692 | Image | 32 | — | 0.0556 |
| 9 | 1633635301042962 | Image | 34 | — | 0.0556 |

- Impression rank = `row_rank`. 7 Video + 2 Image-only.
- **Step 4 cost estimate (all 9 new ads): $4.01**, wall-clock ~33–57 min.
- Pricing constants are mid-2025 figures — verify against actual Gemini billing.

## Errors / warnings / data-quality notes
- No scientific-notation ID corruption; all IDs 15–16 digits, clean.
- 3 new videos share identical byte sizes (8,023,137 B: ids 1009996348169330,
  1020433583744483, 869185468874772) — likely the same creative re-run under different
  Ad Library IDs/ranks. Treated as distinct rows per unique-key rules; flagged for awareness.
- Merge required multiple resume passes due to the sandbox's 45s shell cap; no impact on
  correctness (atomic writes + idempotent carry-forward).

## Awaiting your decision on Step 4
9 genuinely new ads are ready to analyze (top-20 = all 9, est. **$4.01**). Reply to approve —
no Gemini/API calls will fire without explicit approval. Optionally, the broader backlog of
40 master rows missing analysis docs can be scoped separately.
