#!/bin/zsh
# Host Mac PRESENCE monitor — one "UP" alert when this Mac genuinely comes back, and one
# best-effort "DOWN" alert when it logs out / restarts / shuts down.
#
# WHY: the whole operation (Ad Studio public URL + every daily launchd job) lives on this
# one Mac. If it goes down, the team should hear it once — and hear once when it's back —
# instead of guessing from silence. This is the host-level twin of the Ad Studio watchdog
# (which watches the public *door*, not the *machine*).
#
# HOW: runs as a long-lived launchd LaunchAgent (KeepAlive). On a graceful logout / restart
# / shutdown, launchd sends SIGTERM; we trap it, fire ONE DOWN alert, and exit. On the next
# real boot we fire ONE UP alert. Both are EDGE-TRIGGERED off a persisted state file so an
# administrative reinstall or a mid-session KeepAlive crash-restart can't fake an alert.
#
#   ── HOW RELIABLE IS THE DOWN ALERT? ──
#   • Logout            — reliable (network is still up when the SIGTERM trap runs).
#   • Restart / shutdown — BEST-EFFORT: macOS tears the network down at the same moment it
#                          SIGTERMs agents, so the Slack POST often loses the race and never
#                          leaves the Mac. Treat a missing DOWN at shutdown as expected.
#   • Hard power-loss / kernel panic / battery death — NO DOWN is possible (no SIGTERM).
#   For the restart/shutdown and hard cases, the real backstop is the OFF-HOST monitors:
#   the GitHub uptime workflow (.github/workflows/ad-studio-uptime.yml) and the Ad Studio
#   watchdog — not this script. The "UP" alert, by contrast, is reliable on every real boot.
#
# Install once on the host Mac (canonical clone): zsh tools/host-monitor/install.sh
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

SCRIPT_DIR="${0:A:h}"
REPO="${SCRIPT_DIR:h:h}"
LOG_DIR="$HOME/Library/Application Support/SupernovaHostMonitor"
LOG="$LOG_DIR/host-monitor.log"
STATE="$LOG_DIR/presence_state"   # up|down — edge-trigger so a crash-restart can't fake an UP
ADMIN_STOP="$LOG_DIR/admin_stop"  # present only while install/uninstall stops us — suppresses DOWN
FRESH_BOOT_SECS=900               # system uptime under this ⇒ treat an UP as a genuine boot
mkdir -p "$LOG_DIR"

log()    { print -r -- "$(date '+%Y-%m-%d %H:%M:%S')  $1" >> "$LOG"; }
notify() { zsh "$REPO/tools/notify/notify.sh" "$1" "$2" >/dev/null 2>&1 || true; }

host="$(scutil --get ComputerName 2>/dev/null || hostname 2>/dev/null || echo 'the host Mac')"

# Graceful logout / restart / shutdown: launchd SIGTERMs us. Fire ONE DOWN, then go.
going_down() {
  # An administrative reinstall/uninstall (launchctl bootout) ALSO SIGTERMs us — that is not
  # the host going down, so suppress the alert and leave the state file untouched.
  if [ -f "$ADMIN_STOP" ]; then log "SIGTERM during admin stop — no DOWN alert"; exit 0; fi
  print -r -- down > "$STATE"
  log "SIGTERM — host going DOWN (shutdown / restart / logout)"
  notify "🔴 Host Mac going DOWN" "$host is shutting down / restarting / logging out — Ad Studio and the daily jobs will pause until it's back. (A hard power-loss, or a fast restart that severs the network first, can't send this — the external uptime monitor is the backstop.)"
  exit 0
}
trap going_down TERM INT HUP

# Wait (briefly) for the network so the UP Slack post can actually leave the Mac.
for i in {1..30}; do
  route -n get default >/dev/null 2>&1 && break
  sleep 2
done

# Send UP only on a genuine come-back — NOT on a mid-session KeepAlive crash-restart:
#   • previous recorded state was "down" (we logged a graceful shutdown that's now over), OR
#   • the SYSTEM booted recently (covers a hard power-loss, which leaves no "down" marker).
# A crash-restart while the host stayed up has prev="up" and a large uptime ⇒ no UP.
prev="$(cat "$STATE" 2>/dev/null || echo down)"   # absent (first ever run) ⇒ treat as a come-back
boot="$(sysctl -n kern.boottime 2>/dev/null | grep -oE 'sec = [0-9]+' | head -1 | grep -oE '[0-9]+')"
now="$(date +%s)"
uptime=$(( now - ${boot:-0} ))
print -r -- up > "$STATE"
if [ "$prev" = down ] || { [ -n "$boot" ] && [ "$uptime" -lt "$FRESH_BOOT_SECS" ]; }; then
  log "UP — host booted / agent loaded (prev=$prev, uptime=${uptime}s)"
  notify "🟢 Host Mac is UP" "$host just booted / logged in — Ad Studio and the daily jobs are coming back online."
else
  log "agent (re)loaded mid-session (prev=$prev, uptime=${uptime}s) — no UP alert (host never went down)"
fi

# Idle until launchd's shutdown SIGTERM hits the trap above. `wait` lets the trap fire
# immediately (a bare sleep would delay it until the sleep returns).
while true; do
  sleep 3600 &
  wait $!
done
