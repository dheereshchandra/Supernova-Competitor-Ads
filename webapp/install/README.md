# Supernova Ad Studio — deployment

A team web app over the competitor-ads repo: browse winning competitor ads, watch
them, one-click generate a Supernova script (the Creative Studio pipeline), and track
each ad from shortlist → script → production. Runs on the operator's Mac (the canonical
clone), exposed to the team through a Cloudflare Tunnel.

> **Run from the canonical MAIN clone only** — not a Conductor worktree. The worktree
> lacks the `facebook/videos/` cache, sits on a feature branch, and isn't the single
> writer the daily sync jobs expect. The installer refuses to run from a worktree.

## 1. One-time prerequisites

```sh
# Python web deps (user-site, same idiom as the rest of the repo)
python3.13 -m pip install --break-system-packages --user fastapi "uvicorn[standard]" itsdangerous

# Frontend build (a developer does this in a worktree and commits dist/ — the Mac needs no node)
cd webapp/frontend && npm install && npm run build && cd -
```

Add to the repo-root `.env` (no quotes — Mac smart-quotes break values):

```
STUDIO_PASSWORD=<one shared team password>
STUDIO_SESSION_SECRET=<random 40+ chars; e.g. `python3.13 -c "import secrets;print(secrets.token_hex(32))"`>
STUDIO_PUBLIC_URL=https://studio.gosupernova.live      # used for the "Open in Ad Studio" deep links in the Sheet
STUDIO_SHEET_SYNC=1                                     # mirror the Production Tracker to the team Sheet (omit to keep it local)
# optional guardrails (defaults shown):
# STUDIO_MAX_JOB_COST=5     STUDIO_MAX_DAILY_COST=15    STUDIO_BLACKOUT=11:05-11:55
```

The R2 / Gemini / Google service-account keys are already in `.env` from the existing
pipeline — nothing to add there.

## 2. Install the backend (launchd)

```sh
zsh webapp/install/install.sh
sleep 3 && curl -s localhost:8787/api/health | head -c 300; echo
```

`live.gosupernova.ad-studio` is a KeepAlive server: it starts now, on login, and is
revived if it crashes or after the Mac wakes. Logs:
`~/Library/Application Support/SupernovaAdStudio/serve.log`.

## 3. Public URL — Cloudflare named tunnel (one-time)

A **named** tunnel (stable hostname), not a quick tunnel (random URL each restart).
Requires `gosupernova.live` to be a Cloudflare-managed zone.

```sh
brew install cloudflared
cloudflared tunnel login                       # authorize the gosupernova.live zone
cloudflared tunnel create ad-studio            # writes ~/.cloudflared/<UUID>.json
cloudflared tunnel route dns ad-studio studio.gosupernova.live
```

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: ad-studio
credentials-file: /Users/<you>/.cloudflared/<UUID>.json
ingress:
  - hostname: studio.gosupernova.live
    service: http://localhost:8787
  - service: http_status:404
```

Install it as a background service (cloudflared ships its own keepalive LaunchDaemon —
use it, don't write another plist):

```sh
sudo cloudflared service install
```

The team now opens **https://studio.gosupernova.live**, signs in with their name + the
shared password, and they're in.

## 4. Keep the Mac awake

`serve.sh` already wraps uvicorn in `caffeinate -s` (no idle sleep while serving on AC).
Belt-and-suspenders for an always-on box:

```sh
sudo pmset -c sleep 0 displaysleep 10     # never sleep on power; screen may sleep
```

If the Mac ever does sleep mid-generation, launchd revives the backend on wake and the
job resumes from its last completed step (every pipeline step is idempotent).

## 5. How it coexists with the daily automation

This is a fourth tenant on the machine alongside the 11:30 repo-sync, 11:35 capture-sync,
and 11:45/19:00 csv-sync launchd jobs. Contracts it honors:

- **Clean main**: every generation job ends by committing its artifacts (via
  `tools/log_and_commit.sh`) **and pushing**, so the tree is clean for the 11:30 pull.
- **Blackout**: no job *starts* during `STUDIO_BLACKOUT` (default 11:05–11:55), so no job
  straddles the morning sync jobs (which skip on a dirty tree).
- **One tab**: the tracker writes only the `Production Tracker` tab — csv-sync owns
  Legend/Overview/Analysis.
- **Data refresh**: the backend re-reads the CSVs by mtime after the 11:30 pull; no restart.

## 6. Operator runbook

```sh
# restart / status
launchctl kickstart -k gui/$(id -u)/live.gosupernova.ad-studio
launchctl list | grep gosupernova
tail -f "$HOME/Library/Application Support/SupernovaAdStudio/serve.log"

# a job is stuck → retry from the Runs page, or just restart the backend (it re-queues
# 'running' jobs and resumes them from their current step).

# the daily sync skipped because the tree is dirty from app activity:
git -C <repo> status --short          # confirm it's generation artifacts
tools/log_and_commit.sh facebook <slug> "operator" "manual cleanup" && git -C <repo> push
launchctl kickstart -k gui/$(id -u)/live.gosupernova.repo-sync

# rotate the team password: edit STUDIO_PASSWORD in .env, then restart (kickstart above).
```

## 7. Lifting to a cloud Linux box later

The serve/generate path is python3.13 + ffmpeg + git + cloudflared — all Linux-trivial.
Only macOS-specific surface is the launchd plist (→ a systemd unit) and `caffeinate`/`pmset`
(drop them). The `pyobjc-*` deps are scraper-only and never imported here. Lifting the app
also means lifting the pipeline (videos cache, `.env`, the generation scripts) — the app is
a thin layer over the repo, so move the repo + secrets and re-point the tunnel.
