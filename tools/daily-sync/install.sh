#!/bin/zsh
# One-time installer for the daily 11:30 AM repo auto-sync (macOS launchd).
#
# Run ONCE, from your MAIN clone of the repo (NOT a Conductor worktree):
#     zsh tools/daily-sync/install.sh
#
# It generates ~/Library/LaunchAgents/live.gosupernova.repo-sync.plist from the
# template (filling in absolute paths), then loads it. Safe to re-run (idempotent).
set -eu

SCRIPT_DIR="${0:A:h}"
SYNC_SH="$SCRIPT_DIR/sync.sh"
TEMPLATE="$SCRIPT_DIR/live.gosupernova.repo-sync.plist.template"
LABEL="live.gosupernova.repo-sync"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Application Support/SupernovaRepoSync"
LOG="$LOG_DIR/sync.log"

[ -f "$SYNC_SH" ]   || { echo "ERR missing $SYNC_SH"; exit 1; }
[ -f "$TEMPLATE" ]  || { echo "ERR missing $TEMPLATE"; exit 1; }

chmod +x "$SYNC_SH"
mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

sed -e "s|__SYNC_SH__|$SYNC_SH|g" -e "s|__LOG__|$LOG|g" "$TEMPLATE" > "$PLIST_DEST"

# Reload cleanly (ignore "not loaded" on first run)
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"

echo "Installed '$LABEL' — runs every day at 11:30 AM (pull-only, safe)."
echo "  repo:   ${SCRIPT_DIR:h:h}"
echo "  script: $SYNC_SH"
echo "  log:    $LOG"
echo
echo "Test it right now (forces one run):"
echo "  launchctl kickstart -k gui/$(id -u)/$LABEL && sleep 2 && tail -n 5 \"$LOG\""
echo "Remove later with:  zsh tools/daily-sync/uninstall.sh"
