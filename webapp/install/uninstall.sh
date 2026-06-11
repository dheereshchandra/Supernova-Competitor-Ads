#!/bin/zsh
# Stop + remove the Ad Studio launchd job. (Does not touch the Cloudflare tunnel
# service — remove that with `sudo cloudflared service uninstall` if desired.)
set -eu
LABEL="live.gosupernova.ad-studio"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Removed '$LABEL'. (Tunnel + logs left in place.)"
