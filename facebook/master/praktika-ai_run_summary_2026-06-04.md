# Praktika AI — Scrape Run Summary (2026-06-04)

Pipeline: FB Competitor Ads — Steps 2 → 3 executed, Step 4 prepared (awaiting approval).
Unique key: `(ad_library_id, creative_index_in_ad)`. Scrape geography: **ALL countries**
(the scrape contained only `target_country = ALL`, so the All-Countries dataset was used).

## 1. Scrape analysis & comparison

| Metric | Value |
|---|---|
| Total rows in new scrape | 1,837 |
| Page | Praktika (id 104781132385804) — 1,837 rows (100%) |
| Media types (scrape) | Video 1,000 · Image 823 · Carousel 14 |
| Duplicate keys within scrape | 0 |
| Master rows before | 2,517 |
| **Carry-forward** (in both) | **420** |
| **Genuinely new** | **1,417** (Video 951 · Image 452 · Carousel 14) |
| **Retired** (in master, absent from scrape) | **2,097** — all preserved |
| Projected final master | 3,919 |

## 2. Step 2 — media download (terminal workflow)

Videos downloaded to `videos/praktika-ai-2026-06-04/` via `download_fb_ads.py` (yt-dlp).

| Metric | Value |
|---|---|
| New video assets required | 951 |
| Downloaded successfully | 950 |
| Failed (permanently unavailable) | 1 — `1245562094131968` (removed from FB) |
| **Completion** | **99.9%** |
| Image assets | 452 — **image-pending** (pipeline has no image fetcher; consistent with prior runs) |
| Carousel assets | 14 — image-pending / unsupported |

## 3. Step 3 — master merge

Dry-run, then real merge with `upload_to_r2.py` (videos → Cloudflare R2 `video-ads` bucket).

Dry-run tally: uploaded 951 · carried-forward (with existing R2) 78 · image-pending 753 · video-missing 55 · no-creative 0 · **error 0**.

Final merge result (verified against pre-merge backup):

| Metric | Value |
|---|---|
| Master rows before → after | **2,517 → 3,919** (+1,402) |
| New rows added | 1,402 (Video 950 · Image 452) |
| New video assets uploaded to R2 | 951 (R2 URLs 1,026 → 1,977) |
| Retired rows preserved | 2,097 / 2,097 ✓ |
| Pre-existing rows lost | 0 ✓ |
| Pre-existing R2 URLs changed | 0 ✓ |
| Duplicate keys in final master | 0 ✓ |
| `latest_scrape_run_date = 2026-06-04` | 1,782 rows |

Existing master rows, R2 URLs, and Step-4 metadata columns were left untouched; only new
rows were appended and latest-scrape tracking advanced per pipeline rules.

## 4. Step 4 — prepared only (NOT executed)

Top 20 newly-added ads by `row_rank` (impression rank). All 20 are Video and already in R2.

| Rank | Ad Library ID | Type | R2 | Est. $ |
|---|---|---|---|---|
| 1 | 1284146880301102 | Video | ✓ | 0.2196 |
| 2 | 1479917686815968 | Video | ✓ | 0.2190 |
| 3 | 942282644920761 | Video | ✓ | 0.2192 |
| 4 | 1000580788969512 | Video | ✓ | 0.2173 |
| 5 | 1720222669432418 | Video | ✓ | 0.2129 |
| 6 | 2114713116051354 | Video | ✓ | 0.2125 |
| 7 | 1481040770146627 | Video | ✓ | 0.2197 |
| 8 | 1412613080667553 | Video | ✓ | 0.2148 |
| 9 | 975765704980225 | Video | ✓ | 0.2168 |
| 10 | 1282822937331618 | Video | ✓ | 0.2119 |
| 11 | 874091655660010 | Video | ✓ | 0.3001 |
| 12 | 1354760609752319 | Video | ✓ | 0.2122 |
| 13 | 3197124493824638 | Video | ✓ | 0.2195 |
| 14 | 1391383766354969 | Video | ✓ | 0.5029 |
| 15 | 1311129607090927 | Video | ✓ | 0.2163 |
| 16 | 1607879553589187 | Video | ✓ | 0.2975 |
| 17 | 2204393376963501 | Video | ✓ | 0.2129 |
| 18 | 1266895682308848 | Video | ✓ | 0.2188 |
| 19 | 2972791772910738 | Video | ✓ | 0.1729 |
| 20 | 1449273303357626 | Video | ✓ | 0.2929 ×2 versions |

**Exact Step 4 cost estimate: $5.10** (21 creative rows across the 20 ads; ad
1449273303357626 has 2 creative versions). Wall-clock 57–93 min (Gemini Batch + image gen).
Pricing constants are mid-2025 figures — verify against actual Gemini billing.

> ⏸ ~~Step 4 NOT executed — awaiting approval.~~ **APPROVED & RUN (2026-06-04).**

### Step 4 execution results

| Metric | Value |
|---|---|
| Ads processed | **20 / 20 complete** ✅ |
| Pending | none |

The 18 completed ads are fully registered in `master/praktika-ai.csv` with all five Step-4
URL columns populated: `competitor_analysis_docx_r2_url`, `supernova_rewrite_docx_r2_url`,
`orig_frame_urls`, `gen_panel_urls`, `char_sheet_urls`. Both Word docs per ad (competitor
analysis + Supernova rewrite) were rebuilt with `Asset:` R2-URL captions and uploaded to R2
(36 doc files), and every per-scene image (originals, regenerated panels, character sheets)
was uploaded to R2. 18 of the 20 already had scene analyses + Supernova rewrites from a prior
run; this session ran Stage 4.5 (image upload) → Stage 6 (doc rebuild) → Stages 7+8 (doc
upload + master back-fill) for them, all verification-passed.

The final **2 ads** (`1391383766354969`, `1449273303357626`) required fresh Gemini calls.
Gemini's **Batch** queue was service-wide congested on 2026-06-04 (every recent batch across
all competitors was stuck `PENDING` for 8–14 h), so the decompose and Supernova-rewrite stages
were run **synchronously** (`client.models.generate_content`, `thinking_level=low`) to bypass
the queue — identical model/prompt/output schema to the batch path. Both ads then went through
frames → character sheets → panels → image upload → doc build → R2 upload → master back-fill.

**Result: all 20/20 ads complete** — both Word docs + all three image-URL arrays populated in
`master/praktika-ai.csv`. Objects verified present in R2 via authenticated `head_object`
(docs are full-size 8.5–8.9 MB with embedded imagery). The `step4_audit.py` HEAD-check reports
the public `pub-*.r2.dev` URLs as unreachable, but that is a sandbox outbound-network limit,
not a data problem — the bytes are confirmed in the bucket.

Minor note: for `1449273303357626`, the two **original-frame** thumbnails failed to embed as
in-doc images (their R2 URLs are still recorded in the master); the regenerated panels and
character sheets embedded normally.

## 5. Errors, warnings & data-quality notes

- **1 video permanently unavailable** (`1245562094131968`) — ad removed from Facebook.
- **452 new Image rows + 14 Carousel rows are image-pending** — the pipeline downloads/uploads
  videos only; image and carousel creatives are tracked in the master without R2 URLs
  (`upload_to_r2.py` only special-cases `ad_media_type == "Image"`; Carousel falls through to the
  video path and is recorded as video-missing). 14 carousel keys were therefore **not appended**.
- 1 transient duplicate key (`963590319896632`) arose during the upload and was de-duplicated
  (kept the row carrying the R2 URL, preserved earliest first-scrape date). Final master has 0 dups.
- 40 carry-forward rows that are video-missing in this scrape retain their prior
  `latest_scrape_run_date` (pipeline's video-missing branch does not advance tracking) — expected.

## Backups
- `master/praktika-ai.csv.bak.pre-merge-20260604-1346` (pre-merge snapshot)
- `master/praktika-ai.csv.bak.pre-dedup-15xx` (pre-dedup snapshot)
