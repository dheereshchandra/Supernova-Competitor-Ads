#!/bin/zsh
# Remove the host-presence monitor launchd job. Safe to re-run.
#     zsh tools/host-monitor/uninstall.sh
set -u
LABEL="live.gosupernova.host-monitor"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Application Support/SupernovaHostMonitor"

# Suppress the spurious '🔴 DOWN' that stopping the agent would otherwise fire (removing the
# monitor is not the host going down).
mkdir -p "$LOG_DIR"; touch "$LOG_DIR/admin_stop"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$LOG_DIR/admin_stop"
rm -f "$PLIST_DEST"
echo "Removed '$LABEL' (the log under $LOG_DIR is kept)."
