#!/bin/zsh
# One-time installer for the twice-daily CSV → Google-Sheet auto-sync (macOS launchd).
#
# Run ONCE, from your canonical MAIN clone of the repo (NOT a Conductor worktree — single writer):
#     zsh tools/csv-sync/install.sh
#
# It generates ~/Library/LaunchAgents/live.gosupernova.csv-sync.plist from the template (filling in
# absolute paths), then loads it. Safe to re-run (idempotent). Requires the one-time Google setup
# (service account + Shared Drive from the Google-Docs feature, plus the Sheets API enabled) — see
# tools/csv-sync/README.md.
set -eu

SCRIPT_DIR="${0:A:h}"
SYNC_SH="$SCRIPT_DIR/sync.sh"
TEMPLATE="$SCRIPT_DIR/live.gosupernova.csv-sync.plist.template"
LABEL="live.gosupernova.csv-sync"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Application Support/SupernovaCsvSync"
LOG="$LOG_DIR/sync.log"

[ -f "$SYNC_SH" ]  || { echo "ERR missing $SYNC_SH"; exit 1; }
[ -f "$TEMPLATE" ] || { echo "ERR missing $TEMPLATE"; exit 1; }

chmod +x "$SYNC_SH"
mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

sed -e "s|__SYNC_SH__|$SYNC_SH|g" -e "s|__LOG__|$LOG|g" "$TEMPLATE" > "$PLIST_DEST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"

echo "Installed '$LABEL' — runs twice daily at 09:15 and 21:15 local."
echo "  repo:   ${SCRIPT_DIR:h:h}"
echo "  script: $SYNC_SH"
echo "  log:    $LOG"
echo
echo "Test it right now (forces one run):"
echo "  launchctl kickstart -k gui/$(id -u)/$LABEL && sleep 3 && tail -n 8 \"$LOG\""
echo "Remove later with:  zsh tools/csv-sync/uninstall.sh"
