# Daily free Facebook refresh

Runs the **free** part of the pipeline (stages 1–4: scrape → download → R2 upload →
rankings/analysis) for every competitor in `competitors.txt`, **twice a day** (06:00 + 13:00).
It commits each competitor's fresh data and pushes, so the Library, the master Sheet, and
everyone's clone wake up to up-to-date rankings.

**It deliberately does NOT run enrichment** (stage 5 — transcripts/tags). That step costs
money (~$0.012/video), so it stays on the **Enrich** button in Ad Studio: because the
scrape ran this morning, the pending-enrichment count there is accurate, and you choose
when to spend.

## Why two batches a day (rate-limit hardening, 2026-06-16)
Facebook throttles this Mac's single static IP after ~8 back-to-back competitor
scrapes/downloads. In the old single 6 AM run, the **back half of the list came back
"0 ads" for everyone** — not because those advertisers were empty, but because the IP was
rate-limited (the heavy `english-seekho` download, ~138 videos, was the usual trigger).
For ~5 days straight this meant `blocked=7–10` every morning, which looked alarming but was
expected. Four mitigations now run automatically (all in `scrape.sh`, all env-tunable):

| # | Fix | Knob (env var) | Default |
|---|-----|----------------|---------|
| 1 | **Split** the list into an AM half (fresh IP) + PM half (cooled IP) | the `batch-split` line in `competitors.txt` | AM = first 8, PM = rest |
| 2 | **Pace** between competitors in a batch | `COMPETITOR_PAUSE_SECS` | 90s |
| 3 | **Retry** 0-ad competitors ONCE after a cool-down (when the IP has recovered) | `RETRY_COOLDOWN_SECS` | 900s (15m) |
| 4 | **Classify** unrecovered 0-ad competitors as *empty* (expected) vs *blocked* (alert) | — | `classify_zero.py` |
| — | CDN-download backoff (pauses when a download clearly hits the throttle wall) | `FB_DL_THROTTLE_COOLDOWN` / `FB_DL_MAX_COOLDOWNS` | 60s / 3 |

A *cooled* retry (fix 3) is the sanctioned exception to the pipeline's "never re-scrape a
0-ad page" rule — that rule is about *immediate* re-scrapes, which only deepen the throttle.
A scrape 15 min later is exactly when another shot is worth it.

### Reading the summary line
```
=== done (AM): ok=7 recovered=1 empty=1 blocked=0 failed=0 ===
```
- **ok** — scraped fine on the first try.
- **recovered** — got 0 ads first, then succeeded on the cooled retry → it *was* throttled, now fixed.
- **empty** — 0 ads on both tries, and history says it's genuinely not advertising (e.g. `memrise`, `praktika-ai`). **Expected — no alert.**
- **blocked** — 0 ads on both tries but it's a real, recent advertiser → **a human should look** (persistent throttle or a page-id problem). Slack alerts on this.
- **failed** — a real error (not a 0-ad result). Slack alerts on this.

Slack (`tools/notify`) only pings on **blocked** or **failed** — an expected *empty* stays quiet.

## Install (once, from the canonical MAIN clone)
```sh
zsh tools/daily-scrape/install.sh
```
Re-run it after changing the fire times in the plist template (and `DAILY_SCRAPE_PM_HOUR`
in `scrape.sh`, the morning/afternoon cutoff).

## Does the laptop need to be on at 06:00 / 13:00?
launchd only fires while the Mac is awake. So:
- **Awake at a fire time** → runs then. ✅
- **Asleep at 06:00** → the AM batch runs the next time you wake it (the per-batch date-guard
  makes sure each batch runs at most once per day). The Mac is normally in use by 13:00, so
  the PM batch usually just fires.
- **One wake that missed BOTH fires** (e.g. you open the lid at 14:00) → it catches up: runs
  AM, waits a cool-down so the IP recovers, then runs PM.
- **To make 06:00 happen with the lid closed / unattended** → let the Mac wake itself
  (needs AC power): `sudo pmset repeat wakeorpoweron MTWRFSU 05:58:00`. Cancel with
  `sudo pmset repeat cancel`.

## Which competitors
`competitors.txt` — edit freely (the next run picks it up; no reinstall). Each slug must be
one the scraper knows (`fb_scrape_v2.py` `COMPETITOR_PAGES`). The list is split at the
`batch-split` marker line: slugs **above** run at 06:00 (fresh IP), slugs **below** run at
13:00 (cooled IP). **Keep each half ≲ 8–9** and put the heavy one (`english-seekho`) **last
in the AM half**. Remove the marker and it all runs as one paced + retried morning batch.

## Operate
```sh
# run it right now (real scrape — runs whichever batch is due for the current time):
launchctl kickstart -k gui/$(id -u)/live.gosupernova.daily-scrape
tail -f "$HOME/Library/Application Support/SupernovaDailyScrape/scrape.log"

# run a specific batch's competitors ad-hoc (paced + retried, no date-stamp):
zsh tools/daily-scrape/scrape.sh ewa memrise speak

# dry-run (no scrape/commit, no sleeps) to sanity-check the loop:
DAILY_SCRAPE_DRYRUN=1 zsh tools/daily-scrape/scrape.sh duolingo

# faster live test (short pacing / cool-down):
COMPETITOR_PAUSE_SECS=5 RETRY_COOLDOWN_SECS=30 zsh tools/daily-scrape/scrape.sh ewa

launchctl list | grep daily-scrape      # is it loaded?
zsh tools/daily-scrape/uninstall.sh     # remove
```

## How it coexists with the other jobs
The **AM batch (06:00)** runs well before the 11:30 repo-sync / 11:35 capture-sync /
11:45 csv-sync. The **PM batch (13:00)** is timed to land *after* those finish (and well
before the 19:00 csv-sync), so it never contends with them for git. It commits + pushes so
the tree is clean and main is fast-forwardable. Enrichment and Creative Studio are never
touched here.
