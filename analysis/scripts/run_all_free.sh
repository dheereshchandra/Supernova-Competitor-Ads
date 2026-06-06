#!/bin/bash
# run_all_free.sh — refresh the FREE rank pipeline for every competitor in a
# pipeline. No API, no cost. Facebook replays its committed input snapshots;
# Google seeds a low-fidelity history from its master (no snapshots committed yet).
#
#   analysis/scripts/run_all_free.sh facebook
#   analysis/scripts/run_all_free.sh google
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT"

PIPELINE="${1:-}"
[ -z "$PIPELINE" ] && { echo "usage: run_all_free.sh <facebook|google>"; exit 2; }
PY="$(command -v python3.13 2>/dev/null || command -v python3)"
MODE="--backfill"; [ "$PIPELINE" = "google" ] && MODE="--from-master"

for f in "$PIPELINE"/master/*.csv; do
  [ -e "$f" ] || continue
  comp="$(basename "$f" .csv)"
  # skip Facebook working-file masters (not real competitors)
  case "$comp" in *_newly_added*|*_step4*|*_top20*|*_new_only*) continue;; esac
  $PY analysis/scripts/build_history.py --pipeline "$PIPELINE" --competitor "$comp" $MODE >/dev/null 2>&1
  [ -f "analysis/history/$PIPELINE/$comp.csv" ] || { echo "  --  $comp (no history)"; continue; }
  $PY analysis/scripts/compute_rank_metrics.py --pipeline "$PIPELINE" --competitor "$comp" >/dev/null 2>&1 \
   && $PY analysis/scripts/build_rank_chart.py --pipeline "$PIPELINE" --competitor "$comp" >/dev/null 2>&1 \
   && $PY analysis/scripts/build_report.py     --pipeline "$PIPELINE" --competitor "$comp" >/dev/null 2>&1 \
   && echo "  ok  $comp" || echo "  ERR $comp"
done
echo "done — analysis/derived/$PIPELINE + reports refreshed (free, no API)."
