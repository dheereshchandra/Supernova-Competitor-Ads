#!/bin/zsh
set -eu
LABEL="live.gosupernova.daily-scrape"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Removed '$LABEL'. (Logs kept. To stop the auto-wake: sudo pmset repeat cancel)"
