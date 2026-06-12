#!/bin/zsh
# Supernova competitor-ads — daily repo auto-sync (PULL-ONLY, safe).
#
# Runs from a macOS launchd job every morning so a teammate's pushes show up in
# your canonical clone without manual pulls. It ONLY ever fast-forwards main:
#   • never pushes, never hard-resets, never forces, never merges non-trivially
#   • only fast-forwards when main is checked out, clean, and strictly behind origin
# Anything else (dirty tree, unpushed commits, divergence, not on main) => it does
# NOT touch your work; it logs the reason and posts a macOS notification so you can
# open Conductor and ask Claude to resolve.
#
# Install once with:  zsh tools/daily-sync/install.sh   (see tools/daily-sync/README.md)
set -u

# Repo root = two levels up from this script: <repo>/tools/daily-sync/sync.sh
SCRIPT_DIR="${0:A:h}"
REPO="${SCRIPT_DIR:h:h}"
LOG_DIR="$HOME/Library/Application Support/SupernovaRepoSync"
LOG="$LOG_DIR/sync.log"
mkdir -p "$LOG_DIR"

log()    { print -r -- "$(date '+%Y-%m-%d %H:%M:%S')  $1" >> "$LOG"; }
# macOS banner + Slack (when SLACK_WEBHOOK_URL is in .env) via the shared notifier
notify() { zsh "$REPO/tools/notify/notify.sh" "$1" "$2" >/dev/null 2>&1 || true; }

cd "$REPO" 2>/dev/null || { log "ERR repo not found: $REPO"; exit 1; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { log "ERR not a git repo: $REPO"; exit 1; }

git fetch --all --prune >> "$LOG" 2>&1

BRANCH="$(git symbolic-ref --short -q HEAD || echo DETACHED)"
if [ "$BRANCH" != "main" ]; then
  log "SKIP on branch '$BRANCH' (not main) — not syncing"
  notify "Supernova sync skipped" "On branch $BRANCH, not main. Open Conductor to resolve."
  exit 0
fi

if [ -n "$(git status --porcelain)" ]; then
  log "SKIP uncommitted changes on main — not syncing"
  notify "Supernova sync skipped" "Uncommitted changes on main. Open Conductor to resolve."
  exit 0
fi

UPSTREAM="$(git rev-parse --abbrev-ref @{u} 2>/dev/null || echo none)"
if [ "$UPSTREAM" = "none" ]; then log "ERR no upstream for main"; exit 1; fi

LOCAL="$(git rev-parse @)"
REMOTE="$(git rev-parse @{u})"
BASE="$(git merge-base @ @{u})"

if [ "$LOCAL" = "$REMOTE" ]; then
  log "OK already up to date"
elif [ "$LOCAL" = "$BASE" ]; then
  if git merge --ff-only @{u} >> "$LOG" 2>&1; then
    log "OK fast-forwarded main to origin"
  else
    log "ERR ff-only merge failed"
    notify "Supernova sync failed" "Fast-forward failed. Open Conductor."
  fi
elif [ "$REMOTE" = "$BASE" ]; then
  log "SKIP local main is AHEAD of origin (unpushed commits) — not syncing"
  notify "Supernova sync skipped" "Local main has unpushed commits. Push or open Conductor."
else
  log "SKIP main and origin have DIVERGED — manual resolution needed"
  notify "Supernova sync needs you" "main diverged from origin. Open Conductor and ask Claude to resolve."
fi
exit 0
