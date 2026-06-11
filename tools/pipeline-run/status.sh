#!/bin/bash
# status.sh — one-shot snapshot of the durable pipeline run. Read-only.
#
#   bash tools/pipeline-run/status.sh
#
# Prints the per-competitor stage dashboard + heartbeat/stall state (from state.py),
# whether the launchd job is loaded/running, and the live file counts. The last line
# is `OVERALL: done|running|stalled|dead|empty` — the Claude monitor loop parses it
# to decide whether to relaunch.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT" || exit 1
PY="$(command -v python3.13 || command -v python3)"
LABEL="live.gosupernova.pipeline-run"

echo "============================================================"
"$PY" tools/pipeline-run/state.py summary
echo "------------------------------------------------------------"
# launchd job state (if installed)
if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  pidline="$(launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | grep -E '^\s*pid =' | head -1 | tr -d ' ')"
  state="$(launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | grep -E '^\s*state =' | head -1 | sed 's/^[[:space:]]*//')"
  echo "launchd: $LABEL loaded | $state | ${pidline:-no-pid}"
else
  echo "launchd: $LABEL NOT installed (running ad-hoc, or not yet installed)"
fi
# live counts for the competitor currently in progress
cur="$("$PY" - <<'PY'
import json,pathlib
try:
    d=json.loads((pathlib.Path("analysis/state/pipeline-run.json")).read_text()); print(d.get("current") or "")
except Exception: print("")
PY
)"
if [ -n "$cur" ]; then
  echo "live ($cur): videos=$(find facebook/videos/${cur}-* -name '*.mp4' 2>/dev/null | wc -l | tr -d ' ')  transcripts=$(ls analysis/enrichment/facebook/transcripts/${cur}/*.json 2>/dev/null | wc -l | tr -d ' ')"
fi
echo "------------------------------------------------------------"
echo "today's log: analysis/logs/pipeline-run-$(date +%Y-%m-%d).log   (tail -f to watch)"
echo "============================================================"
