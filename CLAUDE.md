# CLAUDE.md — Agent entry point (Supernova competitor-ads)

Label: Onboarding v1 — 2026-06-08.

Canonical repo root: the folder where you cloned this repo — its path differs on every machine, so ignore any absolute path shown in these docs. ALL commands run from there and start with `python3.13` (system `python3` is 3.9 and lacks packages).

This file is the first thing an agent reads when the repo opens in Conductor. It is the driver + index. The full plain-language roadmap lives in `Supernova-Handoff-Package/START-HERE.md` → "Start from scratch on Conductor (Onboarding v1)"; do not duplicate that prose here.

## If a teammate is starting from scratch

Drive the teammate through the onboarding roadmap **one step at a time**. Run each command yourself (the human only does what a script cannot — install apps, click macOS permission toggles, paste the scrape prompt, type the `.env` secrets). After each command, verify the step's success signal **before** moving to the next. If a step fails, do the fix and re-run that same step — do not skip ahead.

Point them at `Supernova-Handoff-Package/START-HERE.md` → "Start from scratch on Conductor (Onboarding v1)" for the full plain-language roadmap (what-to-do / success-signal / if-it-fails for every step).

The 8 steps as a compact checklist (Steps 1–7 are onboarding; Step 8 is a one-time daily-sync):

1. **Confirm basics installed.** macOS only (the auto-clicker is macOS-only). The human must already have: the **Conductor app** installed with this repo opened as a workspace; **Git + GitHub access** (the repo cloned and auth working — `git fetch` succeeds); and **Google Chrome + the Claude-for-Chrome extension** (for the Facebook scrape). Then check each tool, install only what's missing:
   - `brew --version`
   - `python3.13 --version` → expect `Python 3.13.x`
   - `ffmpeg -version`
   - If no Homebrew: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
   - If no python3.13: `brew install python@3.13`
   - If no ffmpeg (also gives ffprobe): `brew install ffmpeg`

2. **Install all Python packages in one shot:**
   ```
   python3.13 -m pip install --upgrade --break-system-packages --user requests openpyxl boto3 yt-dlp google-genai python-docx Pillow numpy google-api-python-client google-auth google-auth-httplib2 pyobjc-framework-Vision pyobjc-framework-Quartz pyobjc-framework-Cocoa
   ```
   (`google-api-python-client google-auth google-auth-httplib2` power Step-4 Stage 9 — the Google-Docs deliverable upload.)
   Success: pip finishes with no red `ERROR` lines (a yellow PATH warning is fine).
   - If a later command fails with `command not found: yt-dlp` (or similar), add Python's user-bin to PATH once: `echo 'export PATH="$HOME/Library/Python/3.13/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc`

3. **Create the repo-root `.env`** with the SIX required keys (the human pastes the values; the agent must never invent or echo them). NO quotes around values; never echo, commit, or paste `.env`:
   ```
   R2_S3_ENDPOINT
   R2_ACCESS_KEY_ID
   R2_SECRET_ACCESS_KEY
   R2_BUCKET
   R2_PUBLIC_URL_BASE
   GEMINI_API_KEY
   ```
   Where to get them: R2 creds → Cloudflare → R2 → Manage R2 API Tokens → Create API Token (Object Read & Write, scoped to the bucket). Gemini key → https://aistudio.google.com/apikey

4. **Preflight** (run before any pipeline work):
   - `python3.13 facebook/scripts/preflight.py` → expect all green / exit 0 (`--skip-gemini` for Steps 2/3 only; `--json` for machine-readable)
   - `python3.13 analysis/scripts/preflight_enrichment.py` → expect `READY` (lists the Flash model)

5. **Smoke test** (free, no spend, no fresh scrape needed):
   - `analysis/scripts/run_all_free.sh facebook` → regenerates files under `analysis/derived/facebook/` and `analysis/reports/` with no errors. ("No history yet" on a brand-new repo is fine — note and continue.)

6. **Run the full pipeline for ONE competitor** — Steps 1–6 of the canonical pipeline below (scrape → download → R2 upload → free analysis → full enrichment). For Facebook, start the **auto-clicker** first (its TWO macOS permissions + standalone-Terminal requirement are described in "Facebook scrape: run the auto-clicker"). Do the cheap enrichment calibration before `--full`.

7. **Save the work:**
   - `tools/log_and_commit.sh <pipeline> <slug> "<your name>" "<one-line note>"`
   - `git push`
   Success: helper prints `[ok] committed`, `RUN_LOG.md` gains a new top entry, push succeeds. (Push rejected / non-fast-forward → `git pull --no-rebase` then `git push` again.)

**Step 8 (one-time): Daily 9 AM auto-sync.** Walk the teammate through installing the daily auto-pull once so teammates' morning pushes land automatically. Run from their MAIN clone (NOT a Conductor worktree): `zsh tools/daily-sync/install.sh`. Verify with `launchctl kickstart -k gui/$(id -u)/live.gosupernova.repo-sync && sleep 2 && tail -n 5 "$HOME/Library/Application Support/SupernovaRepoSync/sync.log"` (expect an `OK ...` line). It is pull-only and never pushes/resets — full description under "## One-time setup: Daily 9 AM auto-sync" below.

## The canonical pipeline (the one true numbered list)

One competitor, end to end.

> **One-command shortcut:** `analysis/scripts/run_pipeline.sh --competitor <slug>` runs Steps 1→6 below as named stages in cost order. The costly Step-4 (Supernova script/image gen — Gemini **Pro** + image-gen) is the EXPLICIT LAST stage and runs only behind a typed cost gate (it prints the real `BATCH TOTAL $X` and needs `yes`); enrichment is incremental (only NEW videos pay). Use `--dry-run` to preview, `--through-stage 5` to stop before Step-4, `--from-stage N` to resume, `--step4-scope top:20` + `--execute-step4 --yes` to actually generate. A missing/stale FB snapshot makes Stage 1 print the manual scrape steps and exit 10 (re-run resumes). The individual numbered steps below remain the source of truth for each stage.

**Step 0. Preflight:** `python3.13 facebook/scripts/preflight.py` (and `python3.13 analysis/scripts/preflight_enrichment.py`)

**Step 1. SCRAPE:**
- **FACEBOOK = MANUAL Claude-in-Chrome** (Claude Desktop standalone, NOT Cowork): paste `facebook/scraper_prompt.md`, pick one competitor, reply `"yes"` to download → CSV lands in `~/Downloads/` as `fb-ads-{competitor}-{YYYY-MM-DD}.csv`, then move it to `facebook/inputs/`. During this step run the AUTO-CLICKER (see below).
- **GOOGLE = Terminal:** `python3.13 google/scripts/scrape_google_ads.py --competitor <Name> --region IN --out .` (guardrail-enforced: 1 competitor/run, 24h gap, 24h cooldown after a 429). Check first: `python3.13 google/scripts/scrape_guardrail.py status`

**Step 2. DOWNLOAD:** facebook → `python3.13 facebook/scripts/download_fb_ads.py ...` ; google → `python3.13 google/scripts/download_google_ads.py ...`

**Step 3. R2 UPLOAD** (updates `master/{slug}.csv`): `python3.13 <pipeline>/scripts/upload_to_r2.py ...`

**Step 4. FREE ANALYSIS:** `analysis/scripts/run_all_free.sh <pipeline>` (chains `build_history.py` → `compute_rank_metrics.py` → `build_rank_chart.py` → `build_report.py`)

**Step 5. FULL ENRICHMENT** (paid, Flash only): `analysis/scripts/run_enrichment.sh <pipeline> <slug>` (DEFAULT = cheap `--limit 5` calibration); add `--full` only after eyeballing calibration output. Chains preflight → detect_language → rehydrate → transcribe_tag (1 Flash call/video) → embed_scripts → script_cluster → compute_rank_metrics → build_report → (if both platforms) fb_google_overlap.

**Step 6. COMMIT/PUSH:** `tools/log_and_commit.sh <pipeline> <slug> "<operator name>" "<one-line note>"` then `git push`

## Facebook scrape: run the auto-clicker

**File:** `facebook/scripts/fb_allow_clicker.py`

**What/why:** facebook.com is a RESTRICTED site in the Claude Chrome extension — "Always allow actions on this site" is withheld ("Site-level permissions are disabled for this site"), so Claude prompts to approve EVERY JavaScript execution (30–40 clicks per 30-ad page; also open upstream bug anthropics/claude-code#55124). This watcher auto-approves **only** the facebook.com "Allow this action" popup, safely.

**RUN IT FROM A STANDALONE `Terminal.app` (NOT the Conductor built-in terminal)**, STARTED BEFORE the scrape; Ctrl-C when done.

> macOS only. On Windows/Linux the auto-clicker can't run — do the Facebook scrape on a Mac (or with a Mac teammate), or skip Facebook and run the Google pipeline (which works on any OS).

Three commands (verbatim):
```
python3.13 facebook/scripts/fb_allow_clicker.py --test-image /path/to/screenshot.png   # validate OCR on a screenshot, no clicking
python3.13 facebook/scripts/fb_allow_clicker.py --dry-run                               # detect + log on the live screen, no clicking
python3.13 facebook/scripts/fb_allow_clicker.py                                         # for real
```
Useful flags: `--any-app` (don't require Chrome frontmost), `--verbose` (log every scan). Others: `--site` (default facebook.com), `--interval` (default 0.7), `--no-restore`, `--save-capture PATH`.

Dependency (one-time; already covered by the Step 2 full install above; numpy already present):
```
python3.13 -m pip install --user --break-system-packages pyobjc-framework-Vision pyobjc-framework-Quartz pyobjc-framework-Cocoa
```

**TWO macOS permissions** (one-time, granted to the Terminal app that launches it): System Settings → Privacy & Security → (1) **Screen Recording** and (2) **Accessibility** — enable Terminal in BOTH, then FULLY QUIT (**Cmd-Q**) and reopen Terminal (Screen Recording only takes effect on relaunch; Accessibility is immediate). Without Screen Recording it sees a blank screen; without Accessibility its clicks are silently ignored.

Success looks like: a `[perm]` line showing Screen Recording + Accessibility OK, a `[safeguards]` banner, and a `[scan]` heartbeat ~every 3 seconds. Fixes: `[warn] Screen Recording NOT granted` → grant it + Cmd-Q/reopen the SAME terminal; `[paused] frontmost app is Terminal` → bring Chrome to front or add `--any-app`.

For the full walkthrough see **`facebook/HANDOVER.md` §6**.

## Hard rules

- **`python3.13` everywhere** — system `python3` is 3.9 and lacks packages. Every command literally starts with `python3.13`.
- **Gemini FLASH, never Pro** — every AI/LLM call uses Flash (enforced in `analysis/scripts/_flash.py`, which rejects any model containing "pro"). Default `gemini-flash-latest`; embeddings `gemini-embedding-001`.
- **Steps 2–4 run on the Mac Terminal, not the Cowork sandbox** — the sandbox can't reach Facebook's CDN, R2, YouTube, or the AI API.
- **One competitor per person at a time.**
- **Never hand-edit a master CSV.**
- **Never commit or paste `.env`** (it is `.gitignored`; values are bare — no quotes, since Mac smart-quotes break the API).
- **Google guardrail:** always check first with `python3.13 google/scripts/scrape_guardrail.py status`. Policy: 1 competitor/run, MIN 24h gap, 24h cooldown after a 429. If BLOCKED, do NOT scrape — tell the operator when the next run is allowed. Ledger `google/logs/scrape_history.jsonl` is never deleted.

## One-time setup: Daily 9 AM auto-sync

A one-time setup that keeps your canonical clone current so teammates' pushes land automatically every morning (we work one competitor per person on a shared repo). Walk the teammate through it once, as the final one-time-setup step of onboarding (it is **Step 8 (one-time)** in `START-HERE.md`).

- **INSTALL** (run ONCE from your MAIN clone, NOT a Conductor worktree — your *main clone* is the primary copy of the repo on your Mac; Conductor workspaces are lightweight worktrees linked to it; if unsure, ask Claude): `zsh tools/daily-sync/install.sh`
  - Installs a macOS launchd job (label `live.gosupernova.repo-sync`) that runs `git fetch` + `git pull --ff-only` on `main` every day at 9:00 AM local.
- **SAFETY (pull-only):** it NEVER pushes, hard-resets, or force-merges. If `main` is dirty, ahead, diverged, or not checked out, it SKIPS and posts a macOS notification (open Conductor and ask Claude to resolve). Reasons are logged.
- **VERIFY:** `launchctl kickstart -k gui/$(id -u)/live.gosupernova.repo-sync && sleep 2 && tail -n 5 "$HOME/Library/Application Support/SupernovaRepoSync/sync.log"` (expect an `OK ...` line).
- **CHANGE TIME:** edit `Hour`/`Minute` in `tools/daily-sync/live.gosupernova.repo-sync.plist.template` then re-run `install.sh`. **REMOVE:** `zsh tools/daily-sync/uninstall.sh`.
- **FULL DETAILS:** `tools/daily-sync/README.md`. Committed files: `tools/daily-sync/{sync.sh, install.sh, uninstall.sh, live.gosupernova.repo-sync.plist.template, README.md}`.

## Where things live

- `README.md` — collaboration model + daily-workflow rule (Steps 2–4 on your Mac's Terminal).
- `Supernova-Handoff-Package/` — onboarding + signed-off handoff items 01–04 + `START-HERE.md` (full Onboarding v1 roadmap) + `00_INDEX.md`.
- `facebook/HANDOVER.md` — Facebook single source of truth (auto-clicker walkthrough in §6).
- `google/HANDOVER.md` — Google pipeline (CLI / direct RPC since 2026-06-01).
- `analysis/README.md` — free analysis + paid enrichment internals.
- `SESSION-HANDOFF.md` — current resume state; read it to pick up in any workspace.
- `tools/` — `rehydrate.py` (pull media from R2: `python3.13 tools/rehydrate.py --pipeline <facebook|google> --competitor <slug>`), `log_and_commit.sh`, `daily-sync/` (one-time Daily 9 AM auto-pull job — see "## One-time setup: Daily 9 AM auto-sync").
- `conductor.json` runs the one-shot setup when the workspace opens.

Data model (one line): Git holds small precious text (scripts, master CSVs with R2 links, dated inputs, analysis outputs); Cloudflare R2 holds heavy media; pull on demand with `python3.13 tools/rehydrate.py ...`. Masters are latest-only; time-series comes from dated `inputs/` snapshots. Conductor workspaces are git worktrees of one canonical clone (a fetch in one updates `origin/*` for all).
