#!/bin/zsh
# Shared "it ran" HEARTBEAT alert — the success twin of notify.sh.
#
#   tools/notify/heartbeat.sh "<title>" "<message>"
#
# Same delivery as notify.sh (macOS banner + Slack when SLACK_WEBHOOK_URL is in
# .env), but for ROUTINE good-news pings: "the daily scrape finished", "the sync
# ran", etc. — so the team can see the automation is alive, not only hear from it
# when something breaks.
#
# Silence ALL of these routine pings in ONE place (failures still alert via
# notify.sh) by adding to the repo-root .env:
#     NOTIFY_HEARTBEATS=0
# An explicit NOTIFY_HEARTBEATS env var (e.g. in a launchd plist) overrides .env.
# Default = ON.
#
# Best-effort by design: ALWAYS exits 0 — a broken notifier must never break the
# automation that calls it.
set -u
SCRIPT_DIR="${0:A:h}"
REPO="${SCRIPT_DIR:h:h}"

# precedence: explicit env var > .env > default(on). Same grep idiom as notify.sh.
flag="${NOTIFY_HEARTBEATS:-}"
if [ -z "$flag" ]; then
  flag="$(grep -E '^NOTIFY_HEARTBEATS=' "$REPO/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'\'' ')"
fi
[ -z "$flag" ] && flag=1
[ "$flag" = "0" ] && exit 0

zsh "$SCRIPT_DIR/notify.sh" "${1:-Supernova}" "${2:-}" >/dev/null 2>&1 || true
exit 0
