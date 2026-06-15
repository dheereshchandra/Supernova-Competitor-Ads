#!/bin/zsh
# Supernova Ad Studio — funnel/backend WATCHDOG (detect + auto-heal the public door).
#
# Background: the team reaches Ad Studio through a Tailscale Funnel that proxies the
# public URL -> 127.0.0.1:8787 on this Mac. A transient host network / LAN-IP change
# (DHCP renewal, Wi-Fi reconnect) leaves the Funnel's PUBLIC ingress registration
# STALE with no automatic recovery — remote users get "site can't be reached"
# (ERR_CONNECTION_CLOSED) while the operator on localhost/tailnet sees nothing. The
# documented repair is `tailscale serve reset && tailscale funnel --bg 8787`.
# This watchdog does that automatically, plus restarts the backend if it's down, and
# alerts via the shared notifier. Runs every 60s (and on a network change) via launchd.
#
# IMPORTANT — it can only verify LOCAL truth (backend port, tailscale Online, funnel
# config) and re-assert the funnel after an IP change; the genuinely PUBLIC path can
# only be checked from off-tailnet (see .github/workflows/ad-studio-uptime.yml), because
# MagicDNS resolves the *.ts.net name to the tailnet IP and bypasses the public edge.
#
# Install once (from the canonical clone): zsh tools/ad-studio-watchdog/install.sh
set -u
# launchd hands jobs a minimal PATH; we need homebrew (python3.13), /usr/local/bin
# (tailscale), and /usr/sbin + /sbin (ipconfig, route).
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

SCRIPT_DIR="${0:A:h}"
REPO="${SCRIPT_DIR:h:h}"
LOG_DIR="$HOME/Library/Application Support/SupernovaAdStudioWatchdog"
LOG="$LOG_DIR/watchdog.log"
STATE="$LOG_DIR/state"
mkdir -p "$STATE"

PORT="${STUDIO_PORT:-8787}"
STUDIO_LABEL="live.gosupernova.ad-studio"
HEALTH_URL="http://127.0.0.1:${PORT}/api/health"
IP_FILE="$STATE/last_ip"
HEAL_CNT="$STATE/heal_count"
HEAL_WIN="$STATE/heal_window"
MAX_HEALS_PER_HOUR=4          # hard cap so a wedged edge can't loop/alert forever

log()    { print -r -- "$(date '+%Y-%m-%d %H:%M:%S')  $1" >> "$LOG"; }
notify() { zsh "$REPO/tools/notify/notify.sh" "$1" "$2" >/dev/null 2>&1 || true; }

# --- heal rate-limit (per wall-clock hour) ---
now_hour=$(( $(date +%s) / 3600 ))
win="$(cat "$HEAL_WIN" 2>/dev/null || echo 0)"
cnt="$(cat "$HEAL_CNT" 2>/dev/null || echo 0)"
if [ "$win" != "$now_hour" ]; then win="$now_hour"; cnt=0; print -r -- "$win" > "$HEAL_WIN"; fi
can_heal()  { [ "$cnt" -lt "$MAX_HEALS_PER_HOUR" ]; }
bump_heal() { cnt=$((cnt + 1)); print -r -- "$cnt" > "$HEAL_CNT"; }

reassert_funnel() {                      # the de-facto repair for a stale public ingress
  tailscale serve reset >> "$LOG" 2>&1 || true
  tailscale funnel --bg "$PORT" >> "$LOG" 2>&1 || true
}

problems=()
healed=()

# --- 1. backend on 127.0.0.1:PORT (KeepAlive should cover this; we add detect + alert) ---
if ! curl -fsS --max-time 8 "$HEALTH_URL" >/dev/null 2>&1; then
  problems+=("backend :${PORT} not responding")
  if can_heal; then
    log "HEAL backend down -> kickstart $STUDIO_LABEL"
    launchctl kickstart -k "gui/$(id -u)/$STUDIO_LABEL" >> "$LOG" 2>&1 || true
    bump_heal; healed+=("restarted backend"); sleep 3
  fi
fi

# --- 2. tailscaled up & node online? ---
ts_ok="$(tailscale status --json 2>/dev/null | python3.13 -c '
import sys, json
try:
    d = json.load(sys.stdin); s = d.get("Self", {})
    print("ok" if d.get("BackendState") == "Running" and s.get("Online") else "bad")
except Exception:
    print("bad")
' 2>/dev/null || echo bad)"
[ "$ts_ok" != "ok" ] && problems+=("tailscale not Online/Running")

# --- 3. funnel still configured to proxy our port? ---
if ! tailscale funnel status 2>/dev/null | grep -q "127.0.0.1:${PORT}"; then
  problems+=("funnel not proxying :${PORT}")
  if [ "$ts_ok" = "ok" ] && can_heal; then
    log "HEAL funnel config missing -> re-assert"
    reassert_funnel; bump_heal; healed+=("re-asserted funnel (config missing)")
  fi
fi

# --- 4. LAN IP changed since last run? THIS is the flap that wedges the public ingress.
#        Re-assert proactively so the stale-edge outage self-heals within ~60s. ---
cur_ip="$(route -n get default 2>/dev/null | awk '/interface:/{print $2}' \
          | xargs -I{} ipconfig getifaddr {} 2>/dev/null)"
[ -z "$cur_ip" ] && cur_ip="$(ipconfig getifaddr en0 2>/dev/null || true)"
last_ip="$(cat "$IP_FILE" 2>/dev/null || true)"
if [ -n "$cur_ip" ] && [ -n "$last_ip" ] && [ "$cur_ip" != "$last_ip" ]; then
  log "INFO LAN IP changed ${last_ip} -> ${cur_ip}; re-asserting funnel"
  if [ "$ts_ok" = "ok" ] && can_heal; then
    reassert_funnel; bump_heal; healed+=("re-asserted funnel after IP change ${last_ip}->${cur_ip}")
  fi
fi
[ -n "$cur_ip" ] && print -r -- "$cur_ip" > "$IP_FILE"

# --- verdict ---
if [ ${#problems[@]} -eq 0 ]; then
  log "OK backend+tailscale+funnel healthy (ip=${cur_ip:-?})"
  exit 0
fi

detail="${(j:; :)problems}"
if [ ${#healed[@]} -gt 0 ]; then
  acts="${(j:; :)healed}"
  log "RECOVERED [$detail] via [$acts]"
  notify "Ad Studio auto-recovered" "$detail -> $acts. (heal $cnt/$MAX_HEALS_PER_HOUR this hr)"
  if ! can_heal; then
    notify "Ad Studio: heal cap hit" "Auto-healed $cnt× this hour — likely flapping. Check the Mac's network + watchdog.log."
  fi
else
  log "ALERT unhealed [$detail] (heal cap reached or tailscale down)"
  notify "Ad Studio DEGRADED" "$detail — auto-heal could not resolve it. See watchdog.log."
fi
exit 0
