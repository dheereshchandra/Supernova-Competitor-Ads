#!/bin/zsh
# Remove the daily capture-sync launchd job.
#     zsh tools/capture-sync/uninstall.sh
set -u
LABEL="live.gosupernova.capture-sync"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Removed '$LABEL' (daily capture-sync). The capture log is left at:"
echo "  $HOME/Library/Application Support/SupernovaCaptureSync/capture.log"
