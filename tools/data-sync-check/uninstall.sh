#!/bin/zsh
# Remove the daily data-sync check launchd job. Logs are left in place.
set -eu
LABEL="live.gosupernova.sync-check"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "Removed '$LABEL' (log kept at ~/Library/Application Support/SupernovaSyncCheck/check.log)."
