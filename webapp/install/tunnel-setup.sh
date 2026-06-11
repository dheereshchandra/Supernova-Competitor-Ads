#!/bin/zsh
# Guided Cloudflare named-tunnel setup for Ad Studio.
#
# The browser-login step CANNOT be automated, so this script walks you through it:
# it runs what it can and pauses for the two interactive commands. Re-running is safe.
#
#   zsh webapp/install/tunnel-setup.sh [hostname]
# default hostname: studio.gosupernova.live
set -eu
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

HOST="${1:-studio.gosupernova.live}"
SCRIPT_DIR="${0:A:h}"
CF_DIR="$HOME/.cloudflared"

command -v cloudflared >/dev/null || { echo "ERR cloudflared not installed (brew install cloudflared)"; exit 1; }

echo "=== Ad Studio tunnel setup for: $HOST ==="
echo

if [ ! -f "$CF_DIR/cert.pem" ]; then
  echo "STEP 1 (interactive — opens a browser): authorize your Cloudflare zone."
  echo "      Run this, pick the gosupernova.live zone, then re-run this script:"
  echo "        cloudflared tunnel login"
  exit 0
fi
echo "[ok] cloudflared is logged in (cert.pem present)."

if ! cloudflared tunnel list 2>/dev/null | grep -q '\bad-studio\b'; then
  echo "[..] creating tunnel 'ad-studio'…"
  cloudflared tunnel create ad-studio
fi
UUID="$(cloudflared tunnel list 2>/dev/null | awk '/\bad-studio\b/{print $1; exit}')"
CREDS="$CF_DIR/$UUID.json"
echo "[ok] tunnel ad-studio = $UUID"

CONF="$CF_DIR/config.yml"
if [ ! -f "$CONF" ]; then
  sed -e "s|__CREDENTIALS_FILE__|$CREDS|" -e "s|__HOSTNAME__|$HOST|" \
      "$SCRIPT_DIR/cloudflared-config.template.yml" > "$CONF"
  echo "[ok] wrote $CONF"
fi

echo "[..] routing DNS $HOST -> tunnel…"
cloudflared tunnel route dns ad-studio "$HOST" || echo "    (route may already exist — fine)"

echo
echo "STEP 2 (one-time, needs sudo): install the tunnel as a background service:"
echo "        sudo cloudflared service install"
echo
echo "Then the team opens:  https://$HOST"
echo "(The Ad Studio backend must be running on localhost:8787 — see install.sh.)"
