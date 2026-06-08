# capture-sync — daily time-critical media capture (macOS launchd)

A one-time-install background job that makes sure a freshly-scraped competitor
snapshot is **downloaded and pushed to R2 before its CDN URLs expire (~4 days)** —
even if you forget to process it that day. It is the recurring half of the pipeline;
the one-command half is `analysis/scripts/run_pipeline.sh`.

## What it does (every day at 09:30 local)

For every competitor master in both pipelines, it finds the newest **canonical**
input snapshot (`fb-ads-{slug}-DATE.csv` / `g-ads-{slug}-DATE.csv` — working copies
like `_enriched`/`_NEW_ONLY` are ignored) and:

- **fresh + unprocessed** (snapshot ≤ 4 days old AND newer than the master) → runs
  `run_pipeline.sh --pipeline <p> --competitor <slug> --through-stage 5`
  (download → R2 upload → free analysis → **incremental** enrichment), then commits
  via `tools/log_and_commit.sh` and pushes.
- **missing or stale** (no snapshot, or > 4 days old) → adds it to a **"re-scrape due"**
  macOS notification. The Facebook scrape is manual (Claude-in-Chrome), so the job can
  only remind you — it never scrapes.

It deliberately stops at Stage 5: **Step-4 (Supernova script/image generation — Gemini
Pro + image-gen) is never run automatically.** Run that yourself, gated, with
`run_pipeline.sh --competitor <slug> --step4-scope top:20 --execute-step4`.

## Safety (it guards your work)

Modeled on `tools/daily-sync`, but because it also commits/pushes the guards matter more:

- Acts **only** when `main` is checked out, **clean**, and has an upstream — otherwise it
  **SKIPs and notifies** (it will not stomp on uncommitted edits).
- `git pull --ff-only` first; **never** hard-resets, force-pushes, or merges non-trivially.
- On a rejected push it does `git pull --no-rebase` once and retries; if that still fails it
  leaves the commit **local** and notifies you to push from Conductor.
- A competitor is processed only when its snapshot is **newer than its master**, so
  already-captured snapshots are not reprocessed every day.

## Install / verify / remove

```sh
# INSTALL — run ONCE from your MAIN clone (not a Conductor worktree)
zsh tools/capture-sync/install.sh

# VERIFY — force one run and read the tail of the log
launchctl kickstart -k gui/$(id -u)/live.gosupernova.capture-sync \
  && sleep 3 && tail -n 15 "$HOME/Library/Application Support/SupernovaCaptureSync/capture.log"

# REMOVE
zsh tools/capture-sync/uninstall.sh
```

**Change the time / window:** edit `Hour`/`Minute` in
`live.gosupernova.capture-sync.plist.template` (then re-run `install.sh`), or
`CDN_WINDOW_DAYS` at the top of `sync.sh`. Log lives at
`~/Library/Application Support/SupernovaCaptureSync/capture.log`.

**Pairs with** `tools/daily-sync/` (09:00 pull-only) — capture-sync runs at 09:30 so it
sees the morning's freshly-pulled snapshots.
