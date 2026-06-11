#!/bin/bash
# watch_pipeline.sh — live, read-only progress for a running run_pipeline.sh.
#
# The pipeline scripts buffer stdout, so their progress lines don't appear until
# each step exits. This watcher instead reports the OBSERVABLE state — which step
# is running + the file counts that grow as it works — refreshed every few seconds.
# It changes nothing; Ctrl-C to stop.
#
#   bash analysis/scripts/watch_pipeline.sh [competitor] [pipeline] [interval_s]
#   bash analysis/scripts/watch_pipeline.sh mysivi facebook 5
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT" || exit 1
SLUG="${1:-mysivi}"; PIPE="${2:-facebook}"; INT="${3:-5}"

STEPS='fb_scrape_v2|scrape_google_ads|download_fb_ads|download_google_ads|upload_to_r2|build_history|compute_rank_metrics|build_rank_chart|build_report|build_strategic|build_launch|build_language|build_version|run_enrichment|detect_language|rehydrate|probe_media|visual_fingerprint|transcribe_tag|embed_scripts|script_cluster|fb_google_overlap|estimate_step4|step4_'

count() { ls $1 2>/dev/null | wc -l | tr -d ' '; }

while true; do
  clear
  echo "=================================================="
  echo " ${PIPE}/${SLUG} pipeline — $(date +%H:%M:%S)"
  echo "=================================================="
  echo "ACTIVE STEP(S):"
  ps -eo command 2>/dev/null \
    | grep -E "scripts/($STEPS)" | grep -v grep \
    | sed -E 's#.*scripts/##; s/\.py.*/.py/; s/\.sh.*/.sh/' \
    | sort | uniq -c | sed 's/^/   /' \
    | grep . || echo "   (idle / between steps — or pipeline finished)"
  echo
  echo "videos (latest dir) : $(find ${PIPE}/videos/${SLUG}-* -name '*.mp4' 2>/dev/null | wc -l | tr -d ' ')"
  echo "transcripts         : $(count "analysis/enrichment/${PIPE}/transcripts/${SLUG}/*.json")"
  echo "master rows         : $( [ -f ${PIPE}/master/${SLUG}.csv ] && tail -n +2 ${PIPE}/master/${SLUG}.csv | wc -l | tr -d ' ' )"
  echo "today's reports     : $(count "analysis/reports/$(date +%Y-%m-%d)_${SLUG}_${PIPE}_*.md")"
  echo
  echo "(Ctrl-C to stop watching — read-only, does not touch the pipeline)"
  sleep "$INT"
done
