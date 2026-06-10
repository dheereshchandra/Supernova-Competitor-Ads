#!/bin/zsh
# Remove the daily 11:30 AM repo auto-sync launchd job.
#     zsh tools/daily-sync/uninstall.sh
set -u
LABEL="live.gosupernova.repo-sync"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Removed '$LABEL' (daily auto-sync). The sync log is left at:"
echo "  $HOME/Library/Application Support/SupernovaRepoSync/sync.log"
