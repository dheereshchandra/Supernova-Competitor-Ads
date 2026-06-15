# Weekly Google scrape (launchd)

A once-a-week automated Google FREE refresh — the Google counterpart to the daily Facebook
`tools/daily-scrape/` job. Google's Ads Transparency endpoints are slower and rate-limited, so
instead of running daily it runs **once a week (Monday 12:00 local)** and **throttles ~30 min
between competitors** to avoid a 429 IP block.

## What it does

For every competitor in `competitors.txt`, in order:
1. **scrape** — `scrape_google_ads.py --competitor "<Name>" --region IN --out google --no-guardrail` (resumable — checkpoints every creative)
2. **yt-dlp metadata** — `download_google_ads.py`
3. **R2 upload + master** — `upload_to_r2.py … --master-dir google/master --log-dir google/step3_logs`
4. **Pass 3 — HTML5 banner capture** — `capture_html5_banners.py --competitor <slug> --out google --limit $GOOGLE_HTML5_LIMIT`: renders `html5-banner-no-mp4` ads in headless Chromium → mp4. **Pass 4** then re-runs the R2 upload so the new mp4s fill `r2_public_url`.
5. commit that competitor, push.

Then one `analysis/scripts/run_all_free.sh google` pass, commit, push.

**Pass 3 guardrails** (mirror the scrape's): gated on `GOOGLE_HTML5_CAPTURE` (default on) + Playwright/ffmpeg presence (self-skips + notifies if missing); bounded **per round** via `GOOGLE_HTML5_LIMIT` (default 150 — the capture is **resumable**, skipping banners already on disk, so the remainder carry to the next round); bounded retries via `GOOGLE_HTML5_MAX_ATTEMPTS`; notifies on outcome; **non-fatal** (never blocks the commit). As of 2026-06-15 there are ~1,780 HTML5 banners pending across the masters, so capture fills in over several weekly rounds (raise `GOOGLE_HTML5_LIMIT` to go faster).

A competitor that 429s / returns 0 ads is **skipped, not retried** (logged as `blocked`). It uses
`--no-guardrail` because the per-CLI 24h-gap guardrail would otherwise block competitors 2..N in the
same run — the 30-min throttle + skip-on-block is the rate-limit strategy instead.

## ⚠ Two things to know

- **VPN / IP.** The manual 2026-06-15 round only succeeded because a VPN gave a fresh IP. The
  scheduled job has no way to turn the VPN on — if your normal IP is 429-blocked at run time,
  **every competitor is skipped** and the run is a clean no-op. Keep the VPN auto-connecting, or
  treat the weekly run as best-effort and re-run manually when it reports `ok=0`.
- **Duration.** A full round is ~4-5 h (9 competitors × ~30 min). Lower the gap with
  `GOOGLE_SCRAPE_THROTTLE=900` (15 min) etc. It runs on the canonical clone and commits to `main`.

## Install / remove (run from the canonical MAIN clone, after the PR is merged + pulled)

```
zsh tools/google-weekly-scrape/install.sh      # load the weekly launchd job
zsh tools/google-weekly-scrape/uninstall.sh    # remove it
```

Verify:  `launchctl print gui/$(id -u)/live.gosupernova.google-weekly-scrape | grep -i 'state\|next'`
Log:     `~/Library/Application Support/SupernovaGoogleWeekly/scrape.log`

## Manual / targeted run (skips the once-per-week guard; may run from a worktree)

```
# all competitors, default 30-min throttle:
zsh tools/google-weekly-scrape/scrape.sh
# just a few, 5-min throttle, dry-run plumbing test:
GOOGLE_SCRAPE_THROTTLE=300 GOOGLE_SCRAPE_DRYRUN=1 zsh tools/google-weekly-scrape/scrape.sh "Memrise" "Busuu"
```

## Change the schedule

Edit `Weekday`/`Hour`/`Minute` in `live.gosupernova.google-weekly-scrape.plist.template`
(`Weekday`: 0/7=Sun, 1=Mon … 6=Sat) and re-run `install.sh`.
