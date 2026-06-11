#!/bin/zsh
# Remove the durable pipeline-run LaunchAgent. (Does NOT touch any data/logs.)
#     zsh tools/pipeline-run/uninstall.sh
set -u
LABEL="live.gosupernova.pipeline-run"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Removed '$LABEL'. (Run state, logs, and analysis are untouched.)"
echo "Note: a run currently in flight keeps going until it exits; to stop it now:"
echo "  launchctl kill TERM gui/$(id -u)/$LABEL  2>/dev/null; rm -f analysis/state/pipeline-run.lock"
