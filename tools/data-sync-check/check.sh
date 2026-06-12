#!/bin/zsh
# Supernova competitor-ads — daily data-sync check (launchd wrapper).
#
# Runs check_sync.py (read-only: Mac ↔ repo ↔ Google Sheet) and ALERTS the
# operator via tools/notify (macOS banner + Slack when configured) when
# anything is out of sync or the check itself can't complete. Silent when
# everything agrees — only the log records the daily OK.
#
# Scheduled at 12:15 — after the 11:30 repo-sync, 11:35 capture-sync and
# 11:45 csv-sync, so it validates the whole morning chain end-to-end.
# Install once: zsh tools/data-sync-check/install.sh
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="${0:A:h}"
REPO="${SCRIPT_DIR:h:h}"
LOG_DIR="$HOME/Library/Application Support/SupernovaSyncCheck"
LOG="$LOG_DIR/check.log"
mkdir -p "$LOG_DIR"

log()    { print -r -- "$(date '+%Y-%m-%d %H:%M:%S')  $1" >> "$LOG"; }
notify() { zsh "$REPO/tools/notify/notify.sh" "$1" "$2" >/dev/null 2>&1 || true; }

log "=== data-sync check start ==="
out="$(python3.13 "$SCRIPT_DIR/check_sync.py" 2>&1)"
rc=$?
print -r -- "$out" >> "$LOG"
summary="$(print -r -- "$out" | grep '^RESULT:' | tail -1)"

if [ $rc -eq 0 ]; then
  log "OK ${summary:-consistent}"
elif [ $rc -eq 1 ]; then
  log "ALERT ${summary:-mismatches found}"
  notify "Data sync check: MISMATCHES" "${summary:-Mac/repo/Sheet disagree} — see check.log"
else
  log "ERROR check could not complete (rc=$rc)"
  notify "Data sync check: could not verify" "A source was unreachable or the check crashed — see check.log"
fi
exit 0
