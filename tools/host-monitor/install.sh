#!/bin/zsh
# One-time installer for the host-presence monitor (macOS launchd).
#
# Run ONCE on the host Mac (the canonical clone — the same Mac that serves Ad Studio):
#     zsh tools/host-monitor/install.sh
#
# Generates ~/Library/LaunchAgents/live.gosupernova.host-monitor.plist from the template
# (absolute paths filled in) and loads it. Safe to re-run (idempotent).
set -eu

SCRIPT_DIR="${0:A:h}"
PRESENCE_SH="$SCRIPT_DIR/presence.sh"
TEMPLATE="$SCRIPT_DIR/live.gosupernova.host-monitor.plist.template"
LABEL="live.gosupernova.host-monitor"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Application Support/SupernovaHostMonitor"
LOG="$LOG_DIR/host-monitor.log"

[ -f "$PRESENCE_SH" ] || { echo "ERR missing $PRESENCE_SH"; exit 1; }
[ -f "$TEMPLATE" ]    || { echo "ERR missing $TEMPLATE"; exit 1; }

chmod +x "$PRESENCE_SH"
mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

sed -e "s|__PRESENCE_SH__|$PRESENCE_SH|g" -e "s|__LOG__|$LOG|g" "$TEMPLATE" > "$PLIST_DEST"

# Stopping a running instance SIGTERMs it — without this sentinel that would fire a spurious
# '🔴 DOWN'. The sentinel tells presence.sh "this stop is an admin reinstall, not a shutdown".
ADMIN_STOP="$LOG_DIR/admin_stop"
touch "$ADMIN_STOP"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$ADMIN_STOP"
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"

echo "Installed '$LABEL' — fires one '🟢 UP' on a genuine boot/login,"
echo "and one '🔴 DOWN' on graceful logout/restart/shutdown. (A reinstall is silent — no"
echo "false UP/DOWN — and a mid-session crash-restart won't fake an UP.)"
echo "  repo:   ${SCRIPT_DIR:h:h}"
echo "  script: $PRESENCE_SH"
echo "  log:    $LOG"
echo
echo "On a FIRST install it just sent a '🟢 Host Mac is UP'. Verify the log:"
echo "  sleep 3 && tail -n 6 \"$LOG\""
echo "Test the DOWN alert (sends '🔴 ... going DOWN', then stops the agent):"
echo "  launchctl kill TERM gui/$(id -u)/$LABEL"
echo "  # bring it back afterwards (re-arms UP/DOWN):"
echo "  launchctl kickstart -k gui/$(id -u)/$LABEL"
echo "Remove later with:  zsh tools/host-monitor/uninstall.sh"
