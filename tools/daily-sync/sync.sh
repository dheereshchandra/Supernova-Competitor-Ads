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
# ONE narrow exception (added 2026-06-25): a scrape / Ad-Studio run that dies before its
# commit step (FB throttle, enrichment timeout) leaves append-only dated input snapshots
# (facebook/inputs|google/inputs) UNCOMMITTED — which used to make this SKIP every day until
# someone hand-committed them. If those are the ONLY uncommitted changes, we now commit + push
# just them (immutable data, can't conflict) so the morning chain stays self-clean. Any OTHER
# uncommitted change still falls through to the safe SKIP.
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
notify()    { zsh "$REPO/tools/notify/notify.sh" "$1" "$2" >/dev/null 2>&1 || true; }
# routine "it ran" ping — silenceable in one place via NOTIFY_HEARTBEATS=0 in .env
heartbeat() { zsh "$REPO/tools/notify/heartbeat.sh" "$1" "$2" >/dev/null 2>&1 || true; }

cd "$REPO" 2>/dev/null || { log "ERR repo not found: $REPO"; exit 1; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { log "ERR not a git repo: $REPO"; exit 1; }

git fetch --all --prune >> "$LOG" 2>&1

BRANCH="$(git symbolic-ref --short -q HEAD || echo DETACHED)"
if [ "$BRANCH" != "main" ]; then
  log "SKIP on branch '$BRANCH' (not main) — not syncing"
  notify "Supernova sync skipped" "On branch $BRANCH, not main. Open Conductor to resolve."
  exit 0
fi

# Self-heal orphaned input snapshots (see header). If the ONLY uncommitted changes are under
# facebook/inputs or google/inputs, commit + push just them so we don't skip the whole sync.
if [ -n "$(git status --porcelain)" ]; then
  OTHER="$(git status --porcelain | cut -c4- | grep -vE '^(facebook|google)/inputs/' || true)"
  if [ -z "$OTHER" ]; then
    git add facebook/inputs google/inputs >> "$LOG" 2>&1 || true
    if ! git diff --cached --quiet; then
      git commit -q -m "Sweep orphaned scrape input snapshots (keep main clean for auto-sync)" >> "$LOG" 2>&1
      if [ "$(git rev-parse @{u} 2>/dev/null)" = "$(git merge-base @ @{u} 2>/dev/null)" ] \
         && git push origin main >> "$LOG" 2>&1; then
        log "swept + pushed orphaned input snapshot(s) — main is clean"
        heartbeat "Repo sync: swept inputs" "Committed + pushed orphaned scrape input snapshot(s) to keep main clean."
      else
        log "swept input snapshot(s) committed locally; push deferred (origin moved/diverged)"
      fi
    fi
  fi
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
  heartbeat "Repo sync ✓ (11:30)" "Already up to date with origin/main — nothing to pull."
elif [ "$LOCAL" = "$BASE" ]; then
  if git merge --ff-only @{u} >> "$LOG" 2>&1; then
    log "OK fast-forwarded main to origin"
    heartbeat "Repo sync ✓ (11:30)" "Fast-forwarded main to origin — teammates' pushes are now pulled in."
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
