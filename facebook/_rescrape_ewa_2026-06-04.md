# EWA re-scrape — paste this into a fresh Claude-in-Chrome chat

> **Context for the operator.** The 2026-06-04 EWA scrape we received was produced by a *different* tool (Apify/Bright-Data-style output), not the canonical Meta Ad Library scraper in `scraper_prompt.md`. It had a 26-column schema with `library_id`, `media_type`, `started_running`, `spend`, `impressions`, `is_active` etc. — none of which our pipeline can consume. It also used `page_id = 165004157332215` instead of the canonical `61572590343208` from COMPETITOR_PAGES. We need a clean re-run of the standard v2.1 scraper.

---

## The prompt (paste exactly as-is)

I'm running the Supernova FB competitor-ads pipeline. The last EWA scrape we got was from a non-standard scraping tool and produced output the pipeline can't consume — different column names (`library_id` instead of `ad_library_id`, `media_type` instead of `ad_media_type`, etc.), missing critical columns (`row_rank`, `ad_library_url`, `ad_primary_text`, `ad_description`, `ad_distribution_platforms`, the `facebook_*_cdn_url_at_scrape` fields), extra columns we don't use (`spend`, `impressions`, `is_active`), and a different `page_id` for the EWA brand (`165004157332215`) than the one our pipeline expects (`61572590343208`).

I need a fresh scrape from the canonical v2.1 scraper. Please run it as follows:

1. Open the file `/Users/iniyan/Desktop/fb-ad-downloader/scraper_prompt.md` and **copy its entire contents verbatim** into this chat as your next message — do not paraphrase, summarize, or modify anything.
2. When the prompt's Step 0 asks "Which competitor should I scrape?", reply with exactly: **EWA**
3. Before running, confirm out loud:
   - Scraper version sentinel echoed: `v2.1-2026-05-30 — image-extraction fix active`
   - EWA mapping in `COMPETITOR_PAGES` resolves to a single page: `page_id = 61572590343208`, `page_name = "EWA"`
   - URL contains `active_status=active` (Active ads only — do NOT change this)
   - URL contains `country=IN`
4. Run all the Ad Library page passes per the prompt. Per-card extraction may fail on a handful — that's normal, the downloader will re-resolve them in Step 2.
5. The output CSV must have **exactly these 26 columns, in this exact order**, with a UTF-8 BOM and standard CSV quoting (so Excel doesn't mangle the 16-digit IDs):

   ```
   row_rank, competitor_name, facebook_page_id, facebook_page_name, facebook_page_followers,
   target_country, ad_library_id, ad_library_url, ad_start_date, ad_end_date,
   has_low_impression_warning, ad_has_multiple_versions, ad_version_count,
   ad_primary_text, ad_description, ad_cta_label, ad_destination_url, ad_media_type,
   ad_distribution_platforms, creative_count_in_ad, creative_index_in_ad,
   creative_aspect_ratio, facebook_video_cdn_url_at_scrape, facebook_thumbnail_cdn_url_at_scrape,
   facebook_cdn_url_expiry_at_scrape, scrape_run_date
   ```

6. Critical correctness checks before download:
   - For any ad with `creative_count_in_ad = 1`, `creative_index_in_ad` must be `0` (Step 2f of the prompt — this is the off-by-one rule, don't skip it).
   - `facebook_page_id` for every row must be `61572590343208` (not any other ID).
   - Every `ad_library_id` is a pure-digit number 15–17 digits long — no scientific notation, no underscores, no blanks.
7. Filename must be exactly `fb-ads-ewa-2026-06-04.csv` (today's date in ISO format) and download it to `~/Downloads/`.

When the scrape is finished, report the final tally (page row count, distinct ad_library_id count, video vs image breakdown) and confirm the download. I'll drag the CSV into Cowork from there.

If anything blocks the run (captcha, login wall, scraper-version mismatch, page-header mismatch on `EWA`), stop immediately and tell me — don't try to work around it.

---

## How to use this file

1. Open Claude Desktop and start a **new chat** where the Claude-in-Chrome extension is active (NOT in Cowork — the extension only runs in the standalone Chrome-extension chat).
2. Copy everything in the "The prompt (paste exactly as-is)" section above (from "I'm running the Supernova…" through "…don't try to work around it.").
3. Paste it as your first message.
4. The assistant will then read `scraper_prompt.md`, paste it back, and walk through Step 0 → final download.
5. Drag the resulting `~/Downloads/fb-ads-ewa-2026-06-04.csv` into the Cowork chat and resume the merge.
