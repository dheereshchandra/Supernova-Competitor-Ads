#!/bin/zsh
# Supernova Ad Studio — funnel/backend WATCHDOG (detect + auto-heal the public door).
#
# The team reaches Ad Studio through a Tailscale Funnel proxying the public URL ->
# 127.0.0.1:8787 on this Mac. A change to this Mac's network identity (DHCP renewal,
# Wi-Fi switch, or turning a system-wide VPN on/off) leaves the Funnel's PUBLIC ingress
# STALE with no auto-recovery — remote users get "site can't be reached" while the
# operator on localhost/tailnet sees nothing. The documented repair is
# `tailscale serve reset && tailscale funnel --bg 8787`; this does it automatically.
#
# VPN-AWARE: the operator sometimes turns on a system-wide rotating-IP VPN to run the
# Google scraper (which needs a fresh IP). While that VPN owns the default route, the
# public site is intentionally down — so the watchdog stays QUIET (no churn, no alerts).
# The moment the VPN is turned off and the normal IP returns, it re-asserts the Funnel
# automatically (~1-2 min) so the site comes back with NO operator action.
#
# Runs every 60s + on every network change (launchd WatchPaths). Manual instant fix:
#   zsh tools/ad-studio-watchdog/watchdog.sh --force   (or tools/ad-studio-watchdog/recover.sh)
#
# Install once (canonical clone): zsh tools/ad-studio-watchdog/install.sh
set -u
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
ASSERTED_FILE="$STATE/asserted_netsig"   # the network signature we last re-asserted the funnel for
VPN_FLAG="$STATE/vpn_active"             # present while a system VPN owns the default route
NOTIFY_FILE="$STATE/last_recover_notify"
PUB_STATE="$STATE/public_state"          # "up"/"down": edge-trigger ONE down + ONE up alert per episode
HEAL_CNT="$STATE/heal_count"; HEAL_WIN="$STATE/heal_window"
MAX_HEALS_PER_HOUR=6                      # backstop for backend/funnel repairs (recovery re-assert is exempt)
NOTIFY_COOLDOWN=1200                      # min seconds between recovery Slack notes
FORCE=0; [ "${1:-}" = "--force" ] && FORCE=1

log()    { print -r -- "$(date '+%Y-%m-%d %H:%M:%S')  $1" >> "$LOG"; }
notify() { zsh "$REPO/tools/notify/notify.sh" "$1" "$2" >/dev/null 2>&1 || true; }
reassert_funnel() { tailscale serve reset >> "$LOG" 2>&1 || true; tailscale funnel --bg "$PORT" >> "$LOG" 2>&1 || true; }

# Public-state edge trigger: alert exactly ONCE when the public site goes down, and ONCE
# when it comes back — whatever the cause (VPN on, backend dead, funnel gone). Repeats are
# logged, not re-alerted, so a wedged edge can't spam Slack every 60s.
pub_state() { cat "$PUB_STATE" 2>/dev/null || echo up; }   # assume healthy on first run
mark_down() { [ "$(pub_state)" = down ] || { print -r -- down > "$PUB_STATE"; notify "🔴 Ad Studio is DOWN" "$1"; }; }
mark_up()   { [ "$(pub_state)" = up ]   || { print -r -- up   > "$PUB_STATE"; notify "🟢 Ad Studio is back UP" "$1"; }; }

# heal cap (per wall-clock hour) — guards backend/funnel-config repair loops, NOT recovery
now_hour=$(( $(date +%s) / 3600 ))
[ "$(cat "$HEAL_WIN" 2>/dev/null || echo 0)" != "$now_hour" ] && { print -r -- "$now_hour" > "$HEAL_WIN"; print -r -- 0 > "$HEAL_CNT"; }
cnt="$(cat "$HEAL_CNT" 2>/dev/null || echo 0)"
can_heal()  { [ "$cnt" -lt "$MAX_HEALS_PER_HOUR" ]; }
bump_heal() { cnt=$((cnt + 1)); print -r -- "$cnt" > "$HEAL_CNT"; }

# --- network signature + is a system VPN owning the default route? ---
def_iface="$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')"
gw="$(route -n get default 2>/dev/null | awk '/gateway:/{print $2}')"
lan_ip="$(ipconfig getifaddr "${def_iface:-en0}" 2>/dev/null || true)"
[ -z "$lan_ip" ] && lan_ip="$(ipconfig getifaddr en0 2>/dev/null || true)"
netsig="${def_iface:-?}|${lan_ip:-?}|${gw:-?}"
# A tunnel interface owning the default route => a system VPN (Surfshark etc.) is active.
# Tailscale's own utun carries a 100.64.0.0/10 address; we do NOT treat that as a VPN
# (the operator uses Funnel, not an exit node, so Tailscale never owns the default route).
vpn_active=0
if [[ "$def_iface" == utun* || "$def_iface" == ppp* || "$def_iface" == ipsec* ]]; then
  ifa="$(ifconfig "$def_iface" 2>/dev/null | awk '/inet /{print $2; exit}')"
  case "$ifa" in 100.*) vpn_active=0 ;; *) vpn_active=1 ;; esac
fi

reassert_funnel_record() { reassert_funnel; print -r -- "$netsig" > "$ASSERTED_FILE"; }

# --- manual instant recovery (works regardless of VPN state) ---
if [ "$FORCE" = "1" ]; then
  log "FORCE re-assert on [$netsig]"; reassert_funnel_record
  if [ "$vpn_active" = "1" ]; then
    # A manual re-assert can't beat an active VPN — the public URL stays down until the VPN
    # is off. Do NOT announce a (false) recovery, and keep state 'down' so we don't re-DOWN.
    mark_down "Re-asserted, but a system VPN still owns the connection — the public URL is still down. Turn the VPN off and it recovers on its own."
    echo "Re-asserted, but a VPN is still active — the public URL stays down until you turn the VPN off."
  else
    rm -f "$VPN_FLAG"
    mark_up "Manually re-asserted (recover.sh / --force). Public URL should be back in a few seconds."
    echo "Funnel re-asserted (serve reset && funnel --bg $PORT). Public URL should be back in a few seconds."
  fi
  exit 0
fi

# --- VPN active: site is intentionally down. Alert ONCE that it's down, then stay quiet. ---
if [ "$vpn_active" = "1" ]; then
  [ -f "$VPN_FLAG" ] || { touch "$VPN_FLAG"; log "VPN active (default route via $def_iface) — site intentionally down; holding. Auto-recovers when VPN is turned off."; }
  mark_down "A system VPN is on, so the public URL is intentionally down for the team. It comes back on its own the moment you turn the VPN off (≈1–2 min; run tools/ad-studio-watchdog/recover.sh to make it instant)."
  exit 0
fi

# --- normal (no system VPN) ---
ts_ok="$(tailscale status --json 2>/dev/null | python3.13 -c '
import sys, json
try:
    d = json.load(sys.stdin); s = d.get("Self", {})
    print("ok" if d.get("BackendState") == "Running" and s.get("Online") else "bad")
except Exception:
    print("bad")
' 2>/dev/null || echo bad)"

asserted_sig="$(cat "$ASSERTED_FILE" 2>/dev/null || true)"
problems=(); healed=()

# AUTO-RECOVERY: we just came back from a VPN, OR the network signature changed
# (Wi-Fi switch / DHCP). Re-assert ONCE per new signature (deduped, so it can't loop).
if [ -z "$asserted_sig" ]; then            # first run after install: assume healthy, no spurious re-assert
  print -r -- "$netsig" > "$ASSERTED_FILE"
elif [ "$ts_ok" = "ok" ] && { [ -f "$VPN_FLAG" ] || [ "$netsig" != "$asserted_sig" ]; }; then
  from_vpn=0; reason="network changed -> [$netsig]"
  [ -f "$VPN_FLAG" ] && { from_vpn=1; reason="VPN turned off; normal IP back [$netsig]"; }
  log "RECOVERY $reason -> re-asserting funnel"
  reassert_funnel_record; rm -f "$VPN_FLAG"; healed+=("auto-recovered Funnel")
  if [ "$from_vpn" = 1 ]; then
    # VPN off: funnel re-asserted. Don't announce UP yet — the verdict's mark_up posts the
    # single 🟢 UP once backend+tailscale+funnel actually verify healthy, so a brief
    # funnel-status lag right after the network change can't trigger a premature UP that a
    # later DOWN would contradict. public_state stays 'down' until then (set by the VPN-on DOWN).
    log "VPN off — re-asserted; UP will be confirmed by the verdict once the door is serving."
  else
    # Plain Wi-Fi/DHCP change (site wasn't down) — informational re-assert note, rate-limited.
    now="$(date +%s)"
    if [ $((now - $(cat "$NOTIFY_FILE" 2>/dev/null || echo 0))) -ge "$NOTIFY_COOLDOWN" ]; then
      print -r -- "$now" > "$NOTIFY_FILE"
      notify "Ad Studio: Funnel re-asserted" "$reason — public URL should be back within seconds. (normal after a Wi-Fi/network change)"
    fi
  fi
fi

# --- immediate repairs (capped) ---
if ! curl -fsS --max-time 8 "$HEALTH_URL" >/dev/null 2>&1; then
  problems+=("backend :${PORT} down")
  if can_heal; then log "HEAL kickstart $STUDIO_LABEL"; launchctl kickstart -k "gui/$(id -u)/$STUDIO_LABEL" >> "$LOG" 2>&1 || true; bump_heal; healed+=("restarted backend"); sleep 3; fi
fi
if [ "$ts_ok" != "ok" ]; then
  problems+=("tailscale not Online/Running")
elif ! tailscale funnel status 2>/dev/null | grep -q "127.0.0.1:${PORT}"; then
  problems+=("funnel not proxying :${PORT}")
  if can_heal; then log "HEAL funnel config missing -> re-assert"; reassert_funnel_record; bump_heal; healed+=("re-asserted funnel (config missing)"); fi
fi

# --- verdict (edge-triggered: ONE DOWN per outage, ONE UP on recovery — see mark_down/up) ---
if [ ${#problems[@]} -eq 0 ]; then
  mark_up "Recovered — backend + tailscale + funnel are healthy again."
  [ ${#healed[@]} -gt 0 ] && log "RECOVERED ${(j:; :)healed} (sig=$netsig)" || log "OK healthy (sig=$netsig)"
  exit 0
fi
detail="${(j:; :)problems}"
if [ ${#healed[@]} -gt 0 ]; then
  # actively healing this run — don't declare DOWN yet; let the next run confirm.
  log "RECOVERED-with-issues [$detail] via [${(j:; :)healed}] (rechecking next run)"
else
  # nothing healed this run (no auto-fix available, or heal cap reached) -> a real outage.
  can_heal || log "heal cap $MAX_HEALS_PER_HOUR/hr reached — no more auto-repairs this hour"
  log "ALERT [$detail]"
  mark_down "$detail — the public URL looks down and auto-heal hasn't resolved it. See watchdog.log."
fi
exit 0
