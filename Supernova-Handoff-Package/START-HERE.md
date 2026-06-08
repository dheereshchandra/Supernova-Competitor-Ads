# Supernova Competitor-Ads — Handoff Package

This folder contains everything needed to set up and improve Supernova's competitor-ad
pipelines (Facebook + Google). It's self-contained — hand it to a fresh Claude and say
*"read START-HERE.md and 00_INDEX.md, then help me execute these."*

## Start from scratch on Conductor (Onboarding v1 — 2026-06-08)

New teammate, non-technical, opening this repo in Conductor for the first time? Your agent
should walk you through these steps one at a time, checking each succeeds before the next.

**Prerequisites (before Step 1 — confirm these are in place):**

- macOS (this setup targets macOS — Homebrew, the launchd daily-sync, and the Facebook auto-clicker
  are Mac-only; on Windows/Linux you can still run the Google pipeline, but do the Facebook scrape on a Mac).
- The Conductor app is installed and this repo is opened as a Conductor workspace.
- Git + GitHub access: the repo is cloned and GitHub auth works (`git pull` / `git push`
  succeed without prompting for a password).
- Google Chrome is installed with the Claude-for-Chrome extension (used for the Facebook scrape
  in Step 6a).

**Ground rules the agent follows:**

- Always use `python3.13` (never `python3`). Always run from the repo root — the folder where you
  cloned this repo (its path differs on every machine; ignore any absolute path shown in these docs).
- Do ONE step at a time. After each command, check the success signal before moving on. If a
  step fails, do the fix and re-run that same step — do not skip ahead.
- Never print, commit, or paste the contents of `.env`. Never approve a paid step the human
  didn't ask for.

**Step 1 — Confirm the basics are installed (Homebrew, Python 3.13, ffmpeg).**

Check each tool; install only what's missing. Run each, in order:

```
brew --version
python3.13 --version
ffmpeg -version
```

Success looks like: brew prints a version; `python3.13` prints "Python 3.13.x"; ffmpeg prints
version info.

If it fails:

- No Homebrew → run `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
  (it will ask for the Mac password — that's normal), then re-check `brew --version`.
- No python3.13 → `brew install python@3.13`, then re-check.
- No ffmpeg → `brew install ffmpeg`, then re-check (this also installs ffprobe).

**Step 2 — Install all Python packages in one shot.**

Install every dependency the whole repo needs (pipeline + analysis + the Facebook auto-clicker)
with one command:

```
python3.13 -m pip install --upgrade --break-system-packages --user requests openpyxl boto3 yt-dlp google-genai python-docx Pillow numpy pyobjc-framework-Vision pyobjc-framework-Quartz pyobjc-framework-Cocoa
```

Success looks like: pip finishes with no red "ERROR" lines (a yellow PATH warning is fine).

If it fails: re-run the exact command once (transient network). If a single package keeps
failing, tell the human the package name and stop — don't guess substitutes.

**Step 3 — Set up the secrets file (`.env`).**

Create `.env` at the repo root with the SIX required keys. The human pastes the secret VALUES
(the agent must never invent or echo them). The six keys (no quotes around values):

```
R2_S3_ENDPOINT
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET
R2_PUBLIC_URL_BASE
GEMINI_API_KEY
```

Where the human gets them: R2 keys → Cloudflare → R2 → Manage R2 API Tokens → Create API Token
(Object Read & Write). Gemini key → https://aistudio.google.com/apikey

Success looks like: a `.env` file exists at the repo root with all six lines filled, no quotes
around any value.

If it fails / unsure: ask the human for any missing key by name. Reminder: never wrap values in
quotes; never commit or paste `.env` anywhere.

**Step 4 — Preflight (prove the setup is healthy before touching real data).**

Run both preflight checks:

```
python3.13 facebook/scripts/preflight.py
python3.13 analysis/scripts/preflight_enrichment.py
```

Success looks like: the first prints all-green / exits 0; the second prints READY and lists the
Flash model.

If it fails: read the printed hint — it names exactly what's missing (a package → go back to
Step 2; a `.env` key → go back to Step 3; ffmpeg/ffprobe → `brew install ffmpeg`). Fix that one
thing, then re-run the same preflight.

**Step 5 — Smoke test (a tiny, safe try-run before any real scrape).**

Confirm the free analysis machinery runs without spending money or needing a fresh scrape. Pick
a competitor that already has data (e.g. duolingo):

```
analysis/scripts/run_all_free.sh facebook
```

Success looks like: it regenerates files under `analysis/derived/facebook/` and
`analysis/reports/` with no errors.

If it fails: if it complains about no history yet, that's fine for a brand-new repo — note it
and continue; any other error, read it and fix the named dependency, then re-run.

**Step 6 — Run the full pipeline for ONE competitor (the real thing).**

Pick one competitor nobody else is working on. Do the sub-steps in order; verify each before the
next.

**6a. FACEBOOK SCRAPE — set up the auto-clicker FIRST** (so you don't click 30-40 times by
hand). Why: facebook.com is a restricted site for the Claude Chrome extension, so Claude asks to
approve EVERY JavaScript step. The auto-clicker approves only the facebook.com "Allow this
action" popup, safely.

One-time macOS permissions (the human does this once): System Settings → Privacy & Security →
enable Terminal under BOTH (1) Screen Recording and (2) Accessibility. Then FULLY QUIT Terminal
(Cmd-Q) and reopen it (Screen Recording only activates after a relaunch; Accessibility is
immediate).

One-time dependency (already covered by the Step 2 one-line install; here for completeness):

```
python3.13 -m pip install --user --break-system-packages pyobjc-framework-Vision pyobjc-framework-Quartz pyobjc-framework-Cocoa
```

Start the auto-clicker from a STANDALONE Terminal.app (NOT the Conductor built-in terminal),
BEFORE you start the scrape:

```
python3.13 facebook/scripts/fb_allow_clicker.py --dry-run
python3.13 facebook/scripts/fb_allow_clicker.py
```

(The first validates with no clicking; the second runs for real.) Success looks like: a `[perm]`
line showing Screen Recording + Accessibility OK, a `[safeguards]` banner, and a `[scan]`
heartbeat every ~3 seconds.

If it fails: "[warn] Screen Recording NOT granted" → grant it, then Cmd-Q and reopen the SAME
terminal. "[paused] frontmost app is Terminal" → bring Chrome to the front, or restart it with
`--any-app`.

Now do the scrape: open Claude Desktop (standalone Chrome-extension chat, NOT Cowork), paste the
entire contents of `facebook/scraper_prompt.md`, reply with one competitor name, let it run, and
reply "yes" to download. The auto-clicker handles the popups. The CSV lands in `~/Downloads/` as
`fb-ads-{competitor}-{date}.csv` — move it into `facebook/inputs/`. When the scrape is done,
press Ctrl-C in the auto-clicker terminal to stop it.

(GOOGLE alternative for this competitor: first check
`python3.13 google/scripts/scrape_guardrail.py status`; if allowed, run
`python3.13 google/scripts/scrape_google_ads.py --competitor <Name> --region IN --out .` If
BLOCKED, stop and tell the human when the next run is allowed.)

**6b. DOWNLOAD the media:**

```
python3.13 facebook/scripts/download_fb_ads.py "facebook/inputs/<the-csv>" --out "facebook/videos/<slug>-<date>/" --column ad_library_url --batch-size 10
python3.13 google/scripts/download_google_ads.py "google/inputs/<the-csv>" --videos-out "google/videos/<slug>-<date>/" --images-out "google/images/<slug>-<date>/" --batch-size 600
```

Success looks like: `.mp4` files appear in the videos folder plus a download summary.

If it fails: HTTP 429 → wait ~30 minutes and re-run the SAME command (it's resumable —
already-downloaded ads are skipped).

**6c. UPLOAD to R2 (also updates the master CSV):**

```
python3.13 <pipeline>/scripts/upload_to_r2.py --input <the-input-csv> --videos <the-videos-folder>
```

Success looks like: `master/<slug>.csv` has `r2_public_url` filled for the new rows; a sample
URL opens.

If it fails: re-run the same command — it's idempotent (already-uploaded rows are carried
forward).

**6d. FREE ANALYSIS:**

```
analysis/scripts/run_all_free.sh <pipeline>
```

Success looks like: a fresh report under `analysis/reports/` for this competitor.

**6e. FULL ENRICHMENT (paid — Flash only).** Do the CHEAP calibration first:

```
analysis/scripts/run_enrichment.sh <pipeline> <slug>
```

Eyeball the calibration output. Only if it looks right, run the full pass:

```
analysis/scripts/run_enrichment.sh <pipeline> <slug> --full
```

Success looks like: transcripts + language/format/replication columns appear; the report is
richer.

If it fails: a missing-key error → re-check Step 3; otherwise read the hint and fix the named
dependency. Never jump straight to `--full` without seeing calibration.

**Step 7 — Save the work (commit + push).**

Stamp the run log and commit the small text artifacts, then push:

```
tools/log_and_commit.sh <pipeline> <slug> "<your name>" "<one-line note, e.g. full pipeline; 12 new ads>"
git push
```

Success looks like: the helper prints "[ok] committed", `RUN_LOG.md` gains a new top entry, and
`git push` succeeds.

If it fails: push rejected (non-fast-forward) → `git pull --no-rebase` then `git push` again (if
a blank merge editor opens, close it; if needed run `git commit --no-edit`). Set your git name
once if asked: `git config user.name "Your Name"` and
`git config user.email "you@gosupernova.live"`.

**Step 8 (one-time) — Set up the daily 9 AM auto-sync.**

A one-time setup that keeps your canonical clone current so teammates' pushes land
automatically every morning (we work one competitor per person on a shared repo). Run this ONCE
from your MAIN clone — the primary copy of the repo on your Mac, NOT a Conductor worktree (Conductor
workspaces are lightweight worktrees linked to your main clone; if unsure, ask Claude):

```
zsh tools/daily-sync/install.sh
```

It installs a macOS launchd job (label `live.gosupernova.repo-sync`) that runs `git fetch` +
`git pull --ff-only` on `main` every day at 9:00 AM local time.

Success looks like: the installer reports the job was loaded. Verify it actually runs:

```
launchctl kickstart -k gui/$(id -u)/live.gosupernova.repo-sync && sleep 2 && tail -n 5 "$HOME/Library/Application Support/SupernovaRepoSync/sync.log"
```

Expect an `OK ...` line in the log.

Pull-only safety note: it NEVER pushes, hard-resets, or force-merges. If `main` is dirty, ahead,
diverged, or not checked out, it SKIPS and posts a macOS notification (open Conductor and ask
Claude to resolve) — reasons are logged.

Change the time: edit `Hour`/`Minute` in
`tools/daily-sync/live.gosupernova.repo-sync.plist.template`, then re-run `install.sh`. Remove
it: `zsh tools/daily-sync/uninstall.sh`. Full details: `tools/daily-sync/README.md`.

**Reminders the agent repeats to the human:**

- Steps 2-4 of the pipeline must run on YOUR Mac's Terminal, not the Cowork sandbox (the sandbox
  can't reach Facebook's CDN, R2, YouTube, or the AI API).
- One competitor per person at a time; never hand-edit a master CSV; never commit `.env`.
- Need media a teammate already processed?
  `python3.13 tools/rehydrate.py --pipeline <facebook|google> --competitor <slug>`.

The agent driver for this is the repo-root `CLAUDE.md`.

## Read in this order

1. **`00_INDEX.md`** — the master list of work items, priorities, dependencies, and the
   decisions already made vs. still open. **Start here.**
2. **`01_collaboration_git_r2_repo.md`** — set up one shared Git repo (two folders: facebook +
   google) with heavy media in Cloudflare R2 and all links + run logs in git.
3. **`02_per_page_rank_fix.md`** — make ad rank restart at 1 per Facebook page so winners on
   smaller pages aren't missed.
4. **`03_analysis_system.md`** — the data model and metrics that answer the competitive-
   intelligence questions (volume, winners, format mix, script replication, FB→Google transfer).
5. **`04_google_pipeline_repair.md`** — diagnose and fix the outdated Google pipeline (low
   priority).

Once you have read these, the day-to-day commands live in the root **`README.md`** and
**`facebook/HANDOVER.md`**; the start-from-scratch setup is the **Onboarding v1** section above.

## Companion files

- **`REPO-SETUP-PLAN.md`** — the long-form, plain-English rationale behind item 01.
- **`Supernova-Ad-Formats-taxonomy-seed.csv`** — the team's own ad-format sheet; the seed for
  the format taxonomy used in item 03.

## Two decisions to settle with the team before item 03 finishes

- **"Winner" definition** (proposed: live ≥ 15 days AND top-100 per-page rank in any scrape).
- **Format taxonomy** (formalize a fixed list from the seed CSV above).

## Important context

- Each document is standalone and references the real files/line numbers in the pipeline repos.
- Items 01 and 02 can be done in parallel; 03 builds on both; 04 is low priority.
- Facebook is the mature, reliable pipeline; Google is currently outdated.
