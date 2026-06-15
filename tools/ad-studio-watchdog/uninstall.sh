#!/bin/zsh
# Remove the Ad Studio funnel/backend watchdog launchd job.
#     zsh tools/ad-studio-watchdog/uninstall.sh
set -u
LABEL="live.gosupernova.ad-studio-watchdog"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Removed '$LABEL' (Ad Studio watchdog). The log is left at:"
echo "  $HOME/Library/Application Support/SupernovaAdStudioWatchdog/watchdog.log"
