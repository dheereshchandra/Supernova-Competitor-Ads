#!/bin/zsh
# One-time installer for capture-sync (macOS launchd) — daily time-critical media
# capture + enrichment for any fresh, unprocessed snapshot.
#
# Run ONCE, from your MAIN clone of the repo (NOT a Conductor worktree):
#     zsh tools/capture-sync/install.sh
#
# It generates ~/Library/LaunchAgents/live.gosupernova.capture-sync.plist from the
# template (filling in absolute paths), then loads it. Safe to re-run (idempotent).
#
# NOTE: capture-sync commits + pushes captured work. It only acts when main is clean
# and not diverged (else it SKIPs + notifies). Pair it with tools/daily-sync (11:30
# pull) — capture-sync runs at 11:35 so it sees the freshly pulled snapshots.
set -eu

SCRIPT_DIR="${0:A:h}"
SYNC_SH="$SCRIPT_DIR/sync.sh"
TEMPLATE="$SCRIPT_DIR/live.gosupernova.capture-sync.plist.template"
LABEL="live.gosupernova.capture-sync"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Application Support/SupernovaCaptureSync"
LOG="$LOG_DIR/capture.log"

[ -f "$SYNC_SH" ]  || { echo "ERR missing $SYNC_SH"; exit 1; }
[ -f "$TEMPLATE" ] || { echo "ERR missing $TEMPLATE"; exit 1; }

chmod +x "$SYNC_SH"
mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

sed -e "s|__SYNC_SH__|$SYNC_SH|g" -e "s|__LOG__|$LOG|g" "$TEMPLATE" > "$PLIST_DEST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"

echo "Installed '$LABEL' — runs every day at 11:35 AM."
echo "  repo:   ${SCRIPT_DIR:h:h}"
echo "  script: $SYNC_SH"
echo "  log:    $LOG"
echo
echo "Test it right now (forces one run):"
echo "  launchctl kickstart -k gui/$(id -u)/$LABEL && sleep 3 && tail -n 15 \"$LOG\""
echo "Remove later with:  zsh tools/capture-sync/uninstall.sh"
