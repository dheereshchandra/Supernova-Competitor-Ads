# Archive — obsolete Chrome-extension prompts

The two files here (`scraper_prompt.md` and `find_advertiser_ids_prompt.md`)
are the **original** Step 1 implementation, which ran inside a Claude-in-Chrome
browser session by injecting JavaScript into the Google Ads Transparency
Center page.

**They are no longer used.** Step 1 of the pipeline is now a Python script
(`scripts/scrape_google_ads.py`) that talks to Google's internal RPC endpoint
directly. See `../README.md` and `../HANDOVER.md` for the current workflow.

## Why the change

The Chrome scrape was refused by the Chrome agent (the IIFE was structured
in ways that read as evasion of oversight — hidden iframe, fire-and-forget
promise, auto-download) and was orders of magnitude more expensive: each
detail-page traversal needed a full LLM step in the Chrome agent. The
CLI scraper makes the same data flow as zero AI inference calls — pure
deterministic Python HTTP — and finishes in ~3 minutes for a 150-ad
advertiser instead of 20-30 minutes.

## Kept for historical reference because…

- the data schema (CSV column layout) was defined here and is still used by
  Steps 2-4 unchanged
- the COMPETITOR_ADVERTISERS map evolved here before being ported to the
  CLI script
- the failure modes documented in the comments (region code 2356 for India,
  case-sensitivity of "Last shown:", chevron-based variant navigation, etc.)
  remain useful context if Google's UI is ever scraped again for a new field

**Do not** paste these into a Chrome session or any LLM. Open them only to
read the historical reasoning.
