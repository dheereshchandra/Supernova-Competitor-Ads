#!/bin/zsh
# Shared operator alert — ONE place every automation reports problems.
#
#   tools/notify/notify.sh "<title>" "<message>"
#
# Posts a macOS notification AND (when SLACK_WEBHOOK_URL is set in the repo-root
# .env) a Slack message, so failures reach the operator even away from the Mac.
# Used by: tools/daily-scrape, tools/daily-sync, tools/csv-sync, tools/capture-sync,
# and the Ad Studio backend (webapp/backend/notify.py).
#
# To enable Slack: create an Incoming Webhook (api.slack.com/apps → Incoming
# Webhooks → Add to a channel) and add to .env:  SLACK_WEBHOOK_URL=https://hooks.slack.com/...
#
# Best-effort by design: ALWAYS exits 0 — a broken notifier must never break
# the automation that calls it.
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="${0:A:h}"
REPO="${SCRIPT_DIR:h:h}"
TITLE="${1:-Supernova alert}"
BODY="${2:-}"

# macOS banner (no-op on a headless or locked session)
osascript -e "display notification \"$BODY\" with title \"$TITLE\"" >/dev/null 2>&1 || true

# Slack — same .env idiom as tools/pipeline-run/run_batch.sh (grep, never source)
SLACK_URL="$(grep -E '^SLACK_WEBHOOK_URL=' "$REPO/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'\'' ')"
if [ -n "$SLACK_URL" ]; then
  payload="$(python3.13 -c 'import json,sys; print(json.dumps({"text": "*%s* — %s" % (sys.argv[1], sys.argv[2])}))' "$TITLE" "$BODY" 2>/dev/null || true)"
  [ -n "$payload" ] && curl -sS -m 10 -X POST "$SLACK_URL" \
    -H 'Content-Type: application/json' --data "$payload" >/dev/null 2>&1 || true
fi
exit 0
