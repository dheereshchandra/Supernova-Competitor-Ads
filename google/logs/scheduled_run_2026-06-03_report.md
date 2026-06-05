# Scheduled Run Report — google-ads-429-retry-duolingo-english-seekho

**Date:** 2026-06-03
**Status:** ❌ STOPPED — persistent 429 from Cowork sandbox IP + environmental constraints

## TL;DR

Both retries were blocked **before any rows were scraped**. Google's anti-abuse
returns 429 on the very first `SearchCreatives` call from the Cowork sandbox
IP — for Duolingo, Memrise, and (by extension) English Seekho. Per the task
instructions ("don't restart automatically; just stop and report"), no
recovery was attempted. The user should re-run the same commands from their
Mac terminal (different IP, no 45s bash cap).

## What was attempted

| # | Action | Result |
|---|---|---|
| 1 | Background `nohup` Duolingo scrape | Started, then process was killed when the bash call exited (bwrap `--die-with-parent`). Log shows 1 × 429 backoff message before death. |
| 2 | Probe: `Duolingo --limit 3 --no-download` | 429 on attempt 1 → backoff 15s → 429 on attempt 2 → backoff 30s → bash timeout. |
| 3 | Probe: `Memrise --limit 3 --no-download` | Same: 429 on attempt 1 → 15s backoff → 429 on attempt 2 → 30s backoff → bash timeout. Confirms the block is sandbox-wide, not advertiser-specific. |
| 4 | English Seekho scrape | Not attempted (same sandbox-IP block applies, and HANDOVER §2 specifically warns big advertisers won't fit in the 45s cap anyway). |
| 5 | Downloads / R2 uploads / YouTube backfill | All skipped — nothing new to feed them. |

## Pre-run state (baseline, unchanged)

| File | Rows | Notes |
|---|---|---|
| `master/duolingo.csv` | 743 data rows (744 incl. header) | 219 clean, 230 `detail-fetch: HTTPError`, 287 `html5-banner-no-mp4`, 6 `text-no-asset`, 1 `image-url-not-extracted` |
| `master/english-seekho.csv` | — | does not exist |

## Post-run state

**Identical to pre-run state.** No rows added, no rows recovered, no R2 URLs
written, no YouTube metadata backfilled. The pre-existing
`inputs/g-ads-duolingo-2026-06-03.csv` (744 rows) is the failed-run output
and was not regenerated.

- Scrape-error rows remaining in `master/duolingo.csv`: **230** (unchanged)
- New R2 URLs landed: **0**
- 429 events: **persistent** — fired on attempt 0 (first SearchCreatives call) for every probe
- Total wall-clock time of attempted runs: ~70s across two short probes

## Why this can't be retried from the Cowork sandbox

Two independent blockers, either of which is fatal:

1. **Google's anti-abuse blocks the Cowork sandbox IP.** The 429 fires on
   the *first* SearchCreatives call and survives the script's built-in
   `[15s, 30s, 60s, 120s, 240s]` backoff schedule (we only got through 2
   tiers per probe, but the immediate re-block on retry strongly suggests
   the full 7-min cycle would also fail). HANDOVER §10 calls this exact
   scenario: "wait several hours and retry from a different network."

2. **Cowork's 45-second bash cap prevents any long-running scrape.**
   `mcp__workspace__bash` is capped at 45000ms, and the sandbox uses bwrap
   with `--die-with-parent`, so `nohup` + `&` does not survive between
   calls. The first attempt confirmed this: the background process was
   killed the moment its launching bash call returned. HANDOVER §2 says the
   same thing in prose: *"the sandbox can scrape, but bash commands cap at
   45 seconds so big advertisers (Duolingo, English Seekho) won't finish in
   one call. Your Mac has no such cap."*

## Recommended next step (for a human operator)

Run the four commands from the task verbatim on the Mac terminal, after
waiting a few hours for the Google anti-abuse block to lift. The patched
backoff logic and the wrapper script `run_all_competitors.sh` are both
ready to go.

```bash
cd ~/Desktop/google-ad-downloader

# Duolingo — recovers the 230 scrape-error rows
python3 scripts/scrape_google_ads.py --competitor "Duolingo" --region IN --out .
python3 scripts/download_google_ads.py "inputs/g-ads-duolingo-$(date +%F).csv" \
  --videos-out "./videos/duolingo-$(date +%F)/" \
  --images-out "./images/duolingo-$(date +%F)/" --batch-size 600
python3 scripts/upload_to_r2.py --input "inputs/g-ads-duolingo-$(date +%F).csv" \
  --videos "videos/duolingo-$(date +%F)/" --images "images/duolingo-$(date +%F)/"

# English Seekho — the long one (~30-40 min)
python3 scripts/scrape_google_ads.py --competitor "English Seekho" --region IN --out .
python3 scripts/download_google_ads.py "inputs/g-ads-english-seekho-$(date +%F).csv" \
  --videos-out "./videos/english-seekho-$(date +%F)/" \
  --images-out "./images/english-seekho-$(date +%F)/" --batch-size 600
python3 scripts/upload_to_r2.py --input "inputs/g-ads-english-seekho-$(date +%F).csv" \
  --videos "videos/english-seekho-$(date +%F)/" --images "images/english-seekho-$(date +%F)/"
```

Then run the §6 backfill snippet from HANDOVER.md.

## Log artifacts

- `logs/scrape_duolingo_2026-06-03_retry.log` — output from the initial background scrape attempt (1 × 429 message, then killed by bwrap)
