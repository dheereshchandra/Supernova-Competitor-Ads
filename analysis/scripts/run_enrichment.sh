#!/bin/bash
# run_enrichment.sh — one-command Flash enrichment for a single competitor.
#
# Chains: preflight -> language -> rehydrate -> transcribe+tag -> embed -> cluster
#         -> recompute metrics -> report (+ FB<->Google overlap if both embedded).
#
# DEFAULT = calibration mode: caps the paid steps at 5 items so the FIRST run is
# cheap and inspectable (the first real run is also where you confirm the Flash
# model name + eyeball the format tags). Pass --full to do the whole competitor.
#
# Runs on the operator's Mac (needs google-genai + GEMINI_API_KEY + R2 for videos).
#
#   analysis/scripts/run_enrichment.sh facebook duolingo          # calibrate (5)
#   analysis/scripts/run_enrichment.sh facebook duolingo --full   # whole competitor
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT"

PIPELINE="${1:-}"; COMP="${2:-}"; MODE="${3:-}"
if [ -z "$PIPELINE" ] || [ -z "$COMP" ]; then
  echo "usage: run_enrichment.sh <facebook|google> <competitor> [--full]"; exit 2
fi
LIMIT="--limit 5"; LABEL="calibration (5 items)"
if [ "$MODE" = "--full" ]; then LIMIT=""; LABEL="FULL"; fi
PY="$(command -v python3.13 2>/dev/null || command -v python3)"

echo "== preflight =="
$PY analysis/scripts/preflight_enrichment.py || { echo ">> fix preflight, then re-run."; exit 1; }

echo "== 1/6 language ($COMP) =="
$PY analysis/scripts/detect_language.py --pipeline "$PIPELINE" --competitor "$COMP" $LIMIT

echo "== 2/6 rehydrate videos from R2 =="
$PY tools/rehydrate.py --pipeline "$PIPELINE" --competitor "$COMP" || echo "(rehydrate issue — transcribe will report any missing videos)"

echo "== 2b/6 probe media: resolution + bitrate (ffprobe, offline, no API) =="
$PY analysis/scripts/probe_media.py --pipeline "$PIPELINE" --competitor "$COMP" || echo "(ffprobe issue — non-fatal)"

echo "== 3/6 transcribe + tag [$LABEL] =="
$PY analysis/scripts/transcribe_tag.py --pipeline "$PIPELINE" --competitor "$COMP" $LIMIT

echo "== 4/6 embed scripts [$LABEL] =="
$PY analysis/scripts/embed_scripts.py --pipeline "$PIPELINE" --competitor "$COMP" $LIMIT || echo "(need transcripts first)"

echo "== 5/6 cluster scripts =="
$PY analysis/scripts/script_cluster.py --pipeline "$PIPELINE" --competitor "$COMP" || echo "(need >=1 embedding)"

echo "== 6/6 recompute metrics + report =="
$PY analysis/scripts/compute_rank_metrics.py --pipeline "$PIPELINE" --competitor "$COMP"
$PY analysis/scripts/build_report.py --pipeline "$PIPELINE" --competitor "$COMP"
$PY analysis/scripts/build_strategic_views.py --pipeline "$PIPELINE" --competitor "$COMP"

if [ -f "analysis/enrichment/facebook/embeddings/$COMP.jsonl" ] && \
   [ -f "analysis/enrichment/google/embeddings/$COMP.jsonl" ]; then
  echo "== bonus: FB<->Google overlap =="
  $PY analysis/scripts/fb_google_overlap.py --competitor "$COMP" || true
fi

echo ""
echo "DONE ($LABEL)."
if [ -n "$LIMIT" ]; then
  echo "Eyeball a sidecar: analysis/enrichment/$PIPELINE/transcripts/$COMP/"
  echo "Happy? run full:   analysis/scripts/run_enrichment.sh $PIPELINE $COMP --full"
fi
echo "Commit:  tools/log_and_commit.sh $PIPELINE $COMP \"<you>\" \"enrichment\" && git push"
