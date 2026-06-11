# Daily 6 AM free Facebook refresh

Runs the **free** part of the pipeline (stages 1–4: scrape → download → R2 upload →
rankings/analysis) for every competitor in `competitors.txt`, every morning at **6:00 AM**.
It commits each competitor's fresh data and pushes, so the Library, the master Sheet, and
everyone's clone wake up to up-to-date rankings.

**It deliberately does NOT run enrichment** (stage 5 — transcripts/tags). That step costs
money (~$0.012/video), so it stays on the **Enrich** button in Ad Studio: because the
scrape ran this morning, the pending-enrichment count there is accurate, and you choose
when to spend.

## Install (once, from the canonical MAIN clone)
```sh
zsh tools/daily-scrape/install.sh
```

## Does the laptop need to be on at 6 AM?
launchd only fires while the Mac is awake. So:
- **If it's awake at 6 AM** → runs at 6 AM. ✅
- **If it's asleep at 6 AM** → runs automatically the next time you wake it (the script's
  date-guard makes sure it only runs once per day). So you still get a daily refresh — just
  whenever you next open the laptop, not 6 AM sharp.
- **To make 6 AM happen with the lid closed / unattended** → let the Mac wake itself
  (needs AC power): `sudo pmset repeat wakeorpoweron MTWRFSU 05:58:00`. It wakes at 5:58,
  the job runs at 6:00. Cancel with `sudo pmset repeat cancel`.

## Which competitors
`competitors.txt` — edit freely (the next run picks it up; no reinstall). Each slug must be
one the scraper knows (`fb_scrape_v2.py` `COMPETITOR_PAGES`). Currently 11 are auto-scrapeable.
Four tracked competitors (**boldvoice, fluently, learna-ai, wispr-flow**) have data but no FB
page configured in the scraper — to auto-refresh them, add their page IDs to `fb_scrape_v2.py`
first, then add the slug here.

## Operate
```sh
# run it right now (real scrape):
launchctl kickstart -k gui/$(id -u)/live.gosupernova.daily-scrape
tail -f "$HOME/Library/Application Support/SupernovaDailyScrape/scrape.log"

# dry-run (no scrape/commit) to sanity-check the loop:
DAILY_SCRAPE_DRYRUN=1 zsh tools/daily-scrape/scrape.sh

launchctl list | grep daily-scrape      # is it loaded?
zsh tools/daily-scrape/uninstall.sh     # remove
```

## How it coexists with the other jobs
Runs at 6 AM — well before the 11:30 repo-sync / 11:35 capture-sync / 11:45 csv-sync. It
commits + pushes so the tree is clean and main is fast-forwardable by the time those run.
A blocked scrape (0 ads / throttle) is skipped, never retried (same guardrail as the rest of
the pipeline). Enrichment and Creative Studio are never touched here.
