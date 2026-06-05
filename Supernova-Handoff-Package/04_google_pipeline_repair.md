# Handoff 04 — Google Pipeline Repair (diagnose, then decide)

**Priority: LOW.** Facebook is the primary, reliable pipeline. The Google pipeline is outdated
and its last run did not produce usable assets. Fix it only after the Facebook items (01–03),
or when Google coverage becomes a priority.

---

## Known symptoms (from the last Google run — SpeakX, 2026-05-29)

- The scrape produced **46 rows / 12 ads**, but **2 rows came back as `Unknown` /
  `error_tag = scrape-stalled-during-enrichment`** — the scraper stalled mid-run.
- **All 44 YouTube video downloads failed** with `youtube-restricted`. No `.mp4` files were
  saved; `images/` is empty; Step 4 never ran.
- The master's `r2_public_url` is empty and the R2 public base in `.env` was still the
  placeholder `pub-placeholder.r2.dev` — i.e. **R2 was never fully configured** for Google.

## Most likely causes (in order)

1. **The download was attempted from the Cowork sandbox**, whose network blocks `youtube.com`.
   Step 2 must run on the operator's **own Mac Terminal**. This alone could explain every
   `youtube-restricted`.
2. **Stale `yt-dlp`** — YouTube breaks it regularly; fix is `python3 -m pip install --upgrade
   yt-dlp`.
3. **Scraper selector drift** — Google's Ads Transparency Center UI may have changed since the
   scraper was written (it was built without live DOM verification; see its HANDOVER §14).

---

## Steps

1. **Confirm the environment.** Run Step 2 from a real Mac Terminal (NOT the Cowork sandbox)
   on the 2 known SpeakX video IDs (`mPx0ccxP9ag`, `wZVFw8XTx7M`). If they download there, the
   sandbox network was the whole problem — document it and move on.
2. **Upgrade `yt-dlp`** and retry if step 1 still fails.
3. **Run the scraper's Pass-0 probe** against the live Transparency Center for one advertiser
   to check for selector drift. If the probe reports mismatches, update the text-anchored
   selectors in `google/scraper_prompt.md` (per its own §6.8 guidance) — do not change region
   (`IN`) or the JS architecture.
4. **Finish R2 config:** replace the placeholder `R2_PUBLIC_URL_BASE` in the Google `.env` with
   the real public bucket URL, then re-run Step 3 so `r2_public_url` populates.
5. **Apply the per-page rank change** (handoff 02, section B) to the Google scraper while you're
   in it.

---

## Acceptance criteria

- A fresh Google scrape completes with **0 `scrape-stalled` rows**.
- Step 2 (on a real Mac) downloads the YouTube videos with **0 `youtube-restricted`** failures.
- Step 3 populates `r2_public_url` against a **real** R2 public base.
- The Google master gains `page_rank` (handoff 02).

> If repair proves expensive and Google coverage isn't urgent, it is acceptable to **pause**
> the Google pipeline and keep Facebook as the sole source — just record that decision in
> `RUN_LOG.md` / `analysis/LEARNINGS.md`.
