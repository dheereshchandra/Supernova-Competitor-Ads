#!/bin/zsh
set -eu
LABEL="live.gosupernova.google-weekly-scrape"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Removed '$LABEL'. (Logs kept at ~/Library/Application Support/SupernovaGoogleWeekly/)"
