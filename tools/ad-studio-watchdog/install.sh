#!/bin/zsh
# One-time installer for the Ad Studio funnel/backend watchdog (macOS launchd).
#
# Run ONCE, on the SAME Mac that serves Ad Studio (the canonical clone):
#     zsh tools/ad-studio-watchdog/install.sh
#
# Generates ~/Library/LaunchAgents/live.gosupernova.ad-studio-watchdog.plist from the
# template (absolute paths filled in) and loads it. Safe to re-run (idempotent).
set -eu

SCRIPT_DIR="${0:A:h}"
WATCHDOG_SH="$SCRIPT_DIR/watchdog.sh"
TEMPLATE="$SCRIPT_DIR/live.gosupernova.ad-studio-watchdog.plist.template"
LABEL="live.gosupernova.ad-studio-watchdog"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Application Support/SupernovaAdStudioWatchdog"
LOG="$LOG_DIR/watchdog.log"

[ -f "$WATCHDOG_SH" ] || { echo "ERR missing $WATCHDOG_SH"; exit 1; }
[ -f "$TEMPLATE" ]    || { echo "ERR missing $TEMPLATE"; exit 1; }

chmod +x "$WATCHDOG_SH"
mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

sed -e "s|__WATCHDOG_SH__|$WATCHDOG_SH|g" -e "s|__LOG__|$LOG|g" "$TEMPLATE" > "$PLIST_DEST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"

echo "Installed '$LABEL' — checks every 60s + on every network change."
echo "  repo:   ${SCRIPT_DIR:h:h}"
echo "  script: $WATCHDOG_SH"
echo "  log:    $LOG"
echo
echo "Test it right now (forces one run):"
echo "  launchctl kickstart -k gui/$(id -u)/$LABEL && sleep 4 && tail -n 8 \"$LOG\""
echo "Remove later with:  zsh tools/ad-studio-watchdog/uninstall.sh"
