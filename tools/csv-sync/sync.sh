#!/bin/zsh
# Supernova competitor-ads — csv-sync: push the local analysis into ONE Google Sheet.
#
# WHY: the team reads competitor analysis in a shared Google Sheet. Re-uploading it by hand after
# every pipeline run is manual + error-prone. This launchd job runs twice daily and UPSERTS the local
# CSVs (kept fresh by the 9 AM daily-sync git pull) into the persistent "Supernova Competitor Master"
# spreadsheet — Overview + Analysis tabs — without ever changing the sheet's URL/tabs.
#
# Read-only of the repo (it only reads CSVs and writes to the remote Sheet), so the guards are light.
# Install ONCE from your canonical MAIN clone (single writer): zsh tools/csv-sync/install.sh
set -u

SCRIPT_DIR="${0:A:h}"
REPO="${SCRIPT_DIR:h:h}"
PY="python3.13"
LOG_DIR="$HOME/Library/Application Support/SupernovaCsvSync"
LOG="$LOG_DIR/sync.log"
mkdir -p "$LOG_DIR"

log()    { print -r -- "$(date '+%Y-%m-%d %H:%M:%S')  $1" >> "$LOG"; }
notify() { osascript -e "display notification \"$2\" with title \"$1\"" >/dev/null 2>&1 || true; }

cd "$REPO" 2>/dev/null || { log "ERR repo not found: $REPO"; exit 1; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { log "ERR not a git repo: $REPO"; exit 1; }

# Best-effort freshness: if cleanly on main, fast-forward (daily-sync usually already did this at 9 AM).
if [ "$(git symbolic-ref --short -q HEAD)" = main ] && [ -z "$(git status --porcelain)" ]; then
  git rev-parse --abbrev-ref @{u} >/dev/null 2>&1 && git merge --ff-only @{u} >> "$LOG" 2>&1 || true
fi

# Gate: Sheets readiness (libs present + service account + Sheets API enabled + sheet reachable).
if ! "$PY" facebook/scripts/preflight.py --check-sheets --skip-gemini >> "$LOG" 2>&1; then
  log "SKIP — Sheets preflight failed (is the Google Sheets API enabled + .env set?)"
  notify "CSV-sync skipped" "Sheets preflight failed — open Conductor / check sync.log"
  exit 0
fi

log "running sync_to_sheets --all"
if "$PY" "$REPO/tools/csv-sync/sync_to_sheets.py" --all >> "$LOG" 2>&1; then
  log "OK sync complete"
else
  log "ERR sync_to_sheets failed"
  notify "CSV-sync failed" "sync_to_sheets.py errored — check sync.log"
fi
exit 0
