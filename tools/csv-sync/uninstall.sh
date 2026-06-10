#!/bin/zsh
# Remove the twice-daily CSV → Google-Sheet auto-sync launchd job.
#     zsh tools/csv-sync/uninstall.sh
set -u
LABEL="live.gosupernova.csv-sync"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Removed '$LABEL' (CSV → Sheet auto-sync). The sync log is left at:"
echo "  $HOME/Library/Application Support/SupernovaCsvSync/sync.log"
echo "(The Google Sheet itself + tools/csv-sync/sheet_id.json are untouched.)"
