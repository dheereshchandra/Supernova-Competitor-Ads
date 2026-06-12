#!/bin/zsh
# One-time installer for the daily data-sync check (macOS launchd).
#
# Run ONCE, from your canonical MAIN clone (NOT a Conductor worktree):
#     zsh tools/data-sync-check/install.sh
#
# Generates ~/Library/LaunchAgents/live.gosupernova.sync-check.plist from the
# template (absolute paths filled in) and loads it. Idempotent — safe to re-run.
# Requires the same Google setup csv-sync already uses (service account + Sheets
# API); nothing new to configure.
set -eu

SCRIPT_DIR="${0:A:h}"
CHECK_SH="$SCRIPT_DIR/check.sh"
TEMPLATE="$SCRIPT_DIR/live.gosupernova.sync-check.plist.template"
LABEL="live.gosupernova.sync-check"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Application Support/SupernovaSyncCheck"
LOG="$LOG_DIR/check.log"

[ -f "$CHECK_SH" ]  || { echo "ERR missing $CHECK_SH"; exit 1; }
[ -f "$TEMPLATE" ]  || { echo "ERR missing $TEMPLATE"; exit 1; }

chmod +x "$CHECK_SH" "$SCRIPT_DIR/check_sync.py"
mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

sed -e "s|__CHECK_SH__|$CHECK_SH|g" -e "s|__LOG__|$LOG|g" "$TEMPLATE" > "$PLIST_DEST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"

echo "Installed '$LABEL' — runs daily at 12:15 local (after the morning sync chain)."
echo "  repo:   ${SCRIPT_DIR:h:h}"
echo "  script: $CHECK_SH"
echo "  log:    $LOG"
echo
echo "Test it right now (forces one run):"
echo "  launchctl kickstart -k gui/$(id -u)/$LABEL && sleep 30 && tail -n 30 \"$LOG\""
echo "Remove later with:  zsh tools/data-sync-check/uninstall.sh"
