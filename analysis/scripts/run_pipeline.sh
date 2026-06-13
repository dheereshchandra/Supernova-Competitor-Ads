#!/usr/bin/env bash
# =============================================================================
# run_pipeline.sh — the ONE staged orchestrator for a competitor, end to end.
#
# Six named stages, in COST order. The costliest stage (Stage 6, Creative Studio
# — Supernova script + document generation, Gemini *Pro* text; image generation
# is a separate later step, NOT part of this pass; implemented by the legacy
# step4_* scripts) is the EXPLICIT LAST stage and runs only behind a typed cost gate:
#
#   1 scrape    detect a fresh input snapshot (FB scrape is MANUAL; google is
#               guardrailed) — missing/stale → print how-to + exit 10 (resumable)
#   2 download  pull media from the CDN          (download_*_ads.py)
#   3 r2upload  push media to R2 + refresh master (upload_to_r2.py)
#   4 free      build_history → metrics → chart → report   (FREE, no API)
#   5 enrich    run_enrichment.sh --full — INCREMENTAL (only NEW videos pay)
#   6 step4     Creative Studio. GATED. estimate → show BATCH TOTAL → typed `yes`
#               → runbook (default) or auto-run the chain (--execute-step4). Pro
#               + image-gen.
#
# This REUSES the existing runners — it does NOT reimplement them, and it routes
# AROUND the unwired facebook/scripts/run_step4.py skeleton, driving the real
# step4_*.py modules directly.
#
# Idempotency is provided by the underlying scripts (transcribe/embed/upload all
# skip already-done work); Stage 5 always runs --full and the per-ad skip bounds
# the spend — the orchestrator logs the "already / ready / new" counts.
#
# Usage:
#   analysis/scripts/run_pipeline.sh --competitor mysivi
#   analysis/scripts/run_pipeline.sh --competitor mysivi --dry-run
#   analysis/scripts/run_pipeline.sh --competitor mysivi --through-stage 5
#   analysis/scripts/run_pipeline.sh --competitor mysivi --from-stage 4
#   analysis/scripts/run_pipeline.sh --all --through-stage 5          # refresh everyone
#   analysis/scripts/run_pipeline.sh --competitor mysivi --step4-scope top:20
#   analysis/scripts/run_pipeline.sh --competitor mysivi --step4-scope ids:123,456 --execute-step4 --yes
#
# Exit codes: 0 ok · 2 usage · 10 manual scrape needed (re-run to resume).
# =============================================================================
set -uo pipefail

PY=python3.13
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# ---- defaults ---------------------------------------------------------------
PIPELINE=facebook
COMP=""
ALL=0
FROM=1
THROUGH=5            # Creative Studio (6) is opt-in: providing --step4-scope bumps this to 6
STEP4_SCOPE=""       # top:N | ids:a,b,c | random:N | start:YYYY-MM-DD | all
EXECUTE_STEP4=0      # default: emit a runbook after the gate, don't auto-spend
ASSUME_YES=0
DRY=0
MAX_INPUT_AGE=0      # 0 = ignore snapshot age; >0 = exit 10 if newest input older
RESCRAPE=0           # force a fresh FB V2 scrape even if today's snapshot exists
NO_SCRAPE=0          # never scrape — use the newest existing snapshot as-is

usage() { sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-2}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --competitor) COMP="${2:-}"; shift 2;;
    --all) ALL=1; shift;;
    --pipeline) PIPELINE="${2:-}"; shift 2;;
    --from-stage) FROM="${2:-}"; shift 2;;
    --through-stage) THROUGH="${2:-}"; shift 2;;
    --step4-scope) STEP4_SCOPE="${2:-}"; shift 2;;
    --execute-step4) EXECUTE_STEP4=1; shift;;
    --yes|-y) ASSUME_YES=1; shift;;
    --dry-run) DRY=1; shift;;
    --rescrape) RESCRAPE=1; shift;;
    --no-scrape) NO_SCRAPE=1; shift;;
    --max-input-age-days) MAX_INPUT_AGE="${2:-}"; shift 2;;
    -h|--help) usage 0;;
    *) echo "[error] unknown arg: $1" >&2; usage 2;;
  esac
done

case "$PIPELINE" in facebook|google) ;; *) echo "[error] --pipeline must be facebook|google" >&2; exit 2;; esac
[ "$ALL" = 1 ] || [ -n "$COMP" ] || { echo "[error] need --competitor SLUG or --all" >&2; usage 2; }
# Providing a Creative Studio scope opts that stage in (extends the range to 6).
[ -n "$STEP4_SCOPE" ] && [ "$THROUGH" -lt 6 ] && THROUGH=6

STAMP="$(date +%Y%m%d-%H%M%S)"
LOGDIR="$ROOT/analysis/logs"; mkdir -p "$LOGDIR"

# ---- helpers ----------------------------------------------------------------

# Newest canonical input snapshot for a competitor. Allowlist (not blocklist):
# a canonical input is EXACTLY {prefix}-{slug}-YYYY-MM-DD(-HHMM)?.csv with no
# suffix — so every working copy (_enriched, _NEW_ONLY, _videos_only, …) is
# rejected by construction, regardless of how it's named.
newest_input() {
  local slug="$1" dir prefix
  if [ "$PIPELINE" = facebook ]; then dir="facebook/inputs"; prefix="fb-ads"
  else dir="google/inputs"; prefix="g-ads"; fi
  ls -1t "$dir"/${prefix}-${slug}-*.csv 2>/dev/null \
    | grep -iE "/${prefix}-${slug}-[0-9]{4}-[0-9]{2}-[0-9]{2}(-[0-9]{4})?\.csv$" \
    | head -1
}

# Date (YYYY-MM-DD) embedded in an input filename → drives the videos/ dir name.
input_date() { echo "$1" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | head -1; }

age_days() {  # whole days since a file's mtime
  local mt now; mt=$(stat -f %m "$1" 2>/dev/null || echo 0); now=$(date +%s)
  echo $(( (now - mt) / 86400 ))
}

# Competitor list: explicit one, or every master minus the run_all_free skip-list.
competitors() {
  if [ "$ALL" != 1 ]; then echo "$COMP"; return; fi
  local f c
  for f in "$PIPELINE"/master/*.csv; do
    [ -e "$f" ] || continue
    c="$(basename "$f" .csv)"
    case "$c" in *_newly_added*|*_step4*|*_top20*|*_new_only*) continue;; esac
    echo "$c"
  done
}

run() {  # echo + run (or just echo under --dry-run)
  echo "  \$ $*"
  [ "$DRY" = 1 ] && return 0
  "$@"
}

# ----------------------------------------------------------------------------
# Stage implementations (each takes the competitor slug)
# ----------------------------------------------------------------------------

# Facebook auto-scrape via the V2 terminal scraper (fb_scrape_v2.py). Writes a
# -v2 file, then CANONICALISES it (strips -v2) so the rest of the pipeline — whose
# input selector ignores -v2 by design — ingests it. Only canonicalises on a clean
# exit (audit-FAIL / partial runs keep their -AUDITFAIL/-PARTIAL suffix and are NOT
# promoted). Skips scraping if today's canonical snapshot already exists (idempotent
# re-runs); --rescrape forces, --no-scrape uses the newest existing snapshot as-is.
fb_v2_scrape() {
  local slug="$1" today; today="$(date +%Y-%m-%d)"
  echo "  [stage1] scraping '$slug' with the V2 terminal scraper (fb_scrape_v2.py) ..."
  if [ "$DRY" = 1 ]; then echo "  \$ $PY facebook/scripts/fb_scrape_v2.py $slug"; return 0; fi
  $PY facebook/scripts/fb_scrape_v2.py "$slug" || {
    echo "  [stage1] V2 scrape did not finish clean (0 ads / audit FAIL / login wall / throttle) — see above."
    return 10; }   # 10 = scrape needs ATTENTION → the runner BLOCKS this competitor (NO auto-retry).
                   # Re-scraping a 0-ad / blocked page is pointless and worsens throttling.
  local v2csv; v2csv="$(ls -1t facebook/inputs/fb-ads-${slug}-${today}-*-v2.csv 2>/dev/null | head -1)"
  [ -n "$v2csv" ] || { echo "  [stage1] no clean -v2 output produced — aborting '$slug'."; return 10; }
  cp "$v2csv" "${v2csv/-v2.csv/.csv}"
  echo "  [stage1] canonicalised → $(basename "${v2csv/-v2.csv/.csv}")"
}

stage1_scrape() {
  local slug="$1" inp today; inp="$(newest_input "$slug")"; today="$(date +%Y-%m-%d)"

  # Facebook: auto-scrape with V2 unless today's snapshot already exists (or --no-scrape).
  if [ "$PIPELINE" = facebook ] && [ "$NO_SCRAPE" != 1 ]; then
    if [ -n "$inp" ] && [ "$(input_date "$inp")" = "$today" ] && [ "$RESCRAPE" != 1 ]; then
      echo "  [stage1] today's snapshot already present: $inp  (--rescrape to force a fresh scrape)"
    else
      fb_v2_scrape "$slug" || return $?   # propagate 10 (scrape-blocked) so the runner won't retry
      inp="$(newest_input "$slug")"
    fi
  fi

  if [ -z "$inp" ]; then
    if [ "$PIPELINE" = facebook ]; then
      echo "  [stage1] no snapshot for '$slug' and scraping disabled/failed — provide one or drop --no-scrape."
    else
      echo "  [stage1] no input snapshot for '$slug' — google scrape is guardrailed/manual:"
      echo "    → $PY google/scripts/scrape_guardrail.py status   # check first"
      echo "    → $PY google/scripts/scrape_google_ads.py --competitor <Name> --region IN --out ."
    fi
    return 10
  fi
  echo "  [stage1] input: $inp"
  if [ "$MAX_INPUT_AGE" -gt 0 ]; then
    local a; a="$(age_days "$inp")"
    if [ "$a" -gt "$MAX_INPUT_AGE" ]; then
      echo "  [stage1] STALE: newest snapshot is ${a}d old (> ${MAX_INPUT_AGE}d) — re-scrape '$slug'."
      return 10
    fi
  fi
  [ "$PIPELINE" = google ] && run $PY google/scripts/scrape_guardrail.py status
  return 0
}

stage2_download() {
  local slug="$1" inp; inp="$(newest_input "$slug")"
  [ -z "$inp" ] && { echo "  [stage2] no input for '$slug' — skipping."; return 0; }
  local d; d="$(input_date "$inp")"; [ -z "$d" ] && d="$STAMP"
  local vdir="$PIPELINE/videos/${slug}-${d}"
  if [ "$PIPELINE" = facebook ]; then
    # INCREMENTAL: download only ads NOT already in the master. The rest already
    # live in R2 and carry forward at upload (Stage 3), so re-fetching them is pure
    # waste — a fresh worktree has no local videos and a mature competitor is ~90%+
    # already archived. No master yet (first run) → download everything.
    local master="$PIPELINE/master/${slug}.csv" dlsrc="$inp"
    if [ -f "$master" ] && [ "$DRY" != 1 ]; then
      local newcsv="$LOGDIR/${slug}-${d}-new-ads.csv" n
      n="$($PY - "$inp" "$master" "$newcsv" <<'PYEOF'
import csv, sys
inp, master, out = sys.argv[1:4]
have = {r["ad_library_id"] for r in csv.DictReader(open(master, encoding="utf-8-sig"))}
rows = list(csv.DictReader(open(inp, encoding="utf-8-sig")))
new = [r for r in rows if r["ad_library_id"] not in have]
with open(out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(new)
print(len({r["ad_library_id"] for r in new}))
PYEOF
)"
      echo "  [stage2] incremental: ${n:-0} new ad(s) to fetch (the rest carry forward from R2)"
      [ "${n:-0}" = 0 ] && { echo "  [stage2] nothing new — skipping download."; return 0; }
      dlsrc="$newcsv"
    fi
    run $PY facebook/scripts/download_fb_ads.py "$dlsrc" --out "$vdir"
  else
    run $PY google/scripts/download_google_ads.py "$inp" \
      --videos-out "$vdir" --images-out "$PIPELINE/images/${slug}-${d}"
  fi
}

stage3_r2upload() {
  local slug="$1" inp; inp="$(newest_input "$slug")"
  [ -z "$inp" ] && { echo "  [stage3] no input for '$slug' — skipping."; return 0; }
  local d; d="$(input_date "$inp")"; [ -z "$d" ] && d="$STAMP"
  local vdir="$PIPELINE/videos/${slug}-${d}" idir="$PIPELINE/images/${slug}-${d}"
  # upload_to_r2's --master-dir/--log-dir default to ./master and ./step3_logs
  # (relative to cwd). The orchestrator runs from the repo ROOT, so they MUST be
  # passed explicitly — otherwise it writes a stray master to repo-root/master/
  # and carries forward nothing.
  if [ "$PIPELINE" = facebook ]; then
    run $PY facebook/scripts/upload_to_r2.py --input "$inp" --videos "$vdir" \
      $( [ -d "$idir" ] && echo --images "$idir" ) --competitor "$slug" \
      --master-dir "$PIPELINE/master" --log-dir "$PIPELINE/step3_logs"
  else
    run $PY google/scripts/upload_to_r2.py --input "$inp" --videos "$vdir" \
      --images "$idir" --competitor "$slug" \
      --master-dir "$PIPELINE/master" --log-dir "$PIPELINE/step3_logs"
  fi
}

stage4_free() {  # FREE — mirrors run_all_free.sh's body, for one competitor
  local slug="$1"
  # build_history requires a source mode; --backfill replays every dated snapshot
  # in inputs/ oldest→newest (google has no snapshots → seed from master).
  local mode=--backfill; [ "$PIPELINE" = google ] && mode=--from-master
  run $PY analysis/scripts/build_history.py --pipeline "$PIPELINE" --competitor "$slug" $mode
  run $PY analysis/scripts/compute_rank_metrics.py --pipeline "$PIPELINE" --competitor "$slug"
  run $PY analysis/scripts/build_rank_chart.py --pipeline "$PIPELINE" --competitor "$slug"
  run $PY analysis/scripts/build_report.py --pipeline "$PIPELINE" --competitor "$slug"
}

stage5_enrich() {  # PAID-but-incremental: only NEW videos hit Flash
  local slug="$1"
  run bash analysis/scripts/run_enrichment.sh "$PIPELINE" "$slug" --full
}

# ---- Stage 6: the gated Creative Studio (Pro + image-gen) -------------------
# Maps --step4-scope to estimate_step4_cost.py flags.
scope_flags() {
  case "$STEP4_SCOPE" in
    top:*)    echo "--top-by-rank ${STEP4_SCOPE#top:}";;
    ids:*)    echo "--ids ${STEP4_SCOPE#ids:}";;
    random:*) echo "--random ${STEP4_SCOPE#random:}";;
    start:*)  echo "--start-date ${STEP4_SCOPE#start:}";;
    all)      echo "--all";;
    *)        echo "--top-by-rank 20";;   # conservative default
  esac
}

stage6_step4() {
  local slug="$1"
  [ "$PIPELINE" = facebook ] || { echo "  [stage6] Creative Studio is facebook-only — skipping."; return 0; }
  local flags; flags="$(scope_flags)"
  echo "  [stage6] estimating Creative Studio cost for '$slug' (scope: ${STEP4_SCOPE:-top:20}) ..."

  # estimate must run from facebook/ (relative master-dir + videos auto-discovery)
  local json; json="$( cd "$ROOT/facebook" && $PY scripts/estimate_step4_cost.py \
                         --competitor "$slug" $flags --json 2>/dev/null )" || {
    echo "  [stage6] estimate failed (no master / no candidates?)."; return 1; }

  # parse total + selected ids with python (no jq dependency)
  local parsed; parsed="$($PY - "$json" <<'PYEOF'
import json,sys
d=json.loads(sys.argv[1])
ids=[e["ad_library_id"] for e in d.get("estimates",[])]
print(f"{d.get('total_cost_usd',0):.2f}|{d.get('selected_rows',0)}|{d.get('video_rows',0)}|{','.join(ids)}")
PYEOF
)"
  local total sel vids ids; IFS='|' read -r total sel vids ids <<<"$parsed"
  echo "  ┌──────────────────────────────────────────────"
  echo "  │ Creative Studio (Supernova script + docs — Gemini PRO text; images: separate later step)"
  echo "  │ competitor : $slug      scope: ${STEP4_SCOPE:-top:20}"
  echo "  │ selected   : ${sel} ad(s)   (videos: ${vids})"
  echo "  │ BATCH TOTAL: \$${total}"
  echo "  │ ad ids     : ${ids:-（none）}"
  echo "  └──────────────────────────────────────────────"

  [ -z "$ids" ] && { echo "  [stage6] nothing to generate (all already have docs)."; return 0; }
  if [ "$DRY" = 1 ]; then echo "  [stage6] --dry-run: stopping before the cost gate."; return 0; fi

  # --- cost gate ---
  if [ "$ASSUME_YES" != 1 ]; then
    if [ ! -t 0 ]; then
      echo "  [stage6] BLOCKED: non-interactive and no --yes. Nothing spent."
      step4_runbook "$slug" "$ids"; return 0
    fi
    printf "  Type 'yes' to spend \$%s on Creative Studio for %s ad(s): " "$total" "$sel"
    local ans; read -r ans
    [ "$ans" = yes ] || { echo "  [stage6] not approved — nothing spent."; step4_runbook "$slug" "$ids"; return 0; }
  fi

  if [ "$EXECUTE_STEP4" != 1 ]; then
    echo "  [stage6] approved. (--execute-step4 not set → emitting the runbook instead of auto-running.)"
    step4_runbook "$slug" "$ids"; return 0
  fi
  step4_execute "$slug" "$ids"
}

step4_runbook() {  # print the exact ordered commands for the approved ids
  local slug="$1" ids="$2" sp; sp="${ids//,/ }"
  cat <<EOF
  ── Creative Studio runbook (run from $ROOT/facebook) ─────
    cd "$ROOT/facebook"
    $PY scripts/step4_decompose.py upload $sp
    $PY scripts/step4_decompose_sync.py $slug $sp        # sync decompose (Pro)
    $PY scripts/step4_frames.py --competitor $slug $sp
    $PY scripts/step4_upload_images.py --competitor $slug $sp        # original frames only (image gen is a separate later step)
    $PY scripts/step4_rewrite.py submit --competitor $slug $sp   # prints a poll id
    $PY scripts/step4_rewrite.py poll <short_id>                 # repeat until done
    $PY scripts/step4_build_docs.py --competitor $slug $sp
    $PY scripts/step4_upload_and_update.py --competitor $slug $sp
    $PY scripts/step4_build_html.py --competitor $slug --ids $ids --upload --update-master   # browser-friendly HTML links
  ──────────────────────────────────────────────────────────
EOF
}

step4_execute() {  # auto-run the chain (cwd=facebook); each module is idempotent/resumable
  local slug="$1" ids="$2" sp; sp="${ids//,/ }"
  ( cd "$ROOT/facebook" || exit 1
    set -e
    echo "  [stage6] decompose (upload + sync) ..."
    $PY scripts/step4_decompose.py upload $sp
    $PY scripts/step4_decompose_sync.py "$slug" $sp
    echo "  [stage6] frames (original screenshots) ..."
    $PY scripts/step4_frames.py --competitor "$slug" $sp
    $PY scripts/step4_upload_images.py --competitor "$slug" $sp   # original frames only; image generation is a separate later step
    echo "  [stage6] rewrite (submit → poll) ..."
    short="$($PY scripts/step4_rewrite.py submit --competitor "$slug" $sp \
             | tee /dev/stderr | grep -oE 'poll [A-Za-z0-9_-]+' | awk '{print $2}' | tail -1)"
    [ -n "$short" ] || { echo "  [stage6] could not capture rewrite poll id — resume with the runbook."; exit 1; }
    for _ in $(seq 1 80); do
      if $PY scripts/step4_rewrite.py poll "$short"; then break; fi
      sleep 30
    done
    echo "  [stage6] build docs + upload + update master ..."
    $PY scripts/step4_build_docs.py --competitor "$slug" $sp
    $PY scripts/step4_upload_and_update.py --competitor "$slug" $sp
    $PY scripts/step4_build_html.py --competitor "$slug" --ids "$ids" --upload --update-master
  ) || { echo "  [stage6] chain halted — re-run with --from-stage 6 (idempotent) to resume."; return 1; }
  echo "  [stage6] Creative Studio complete for '$slug'."
}

# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------
declare -a STAGE_NAMES=(_ scrape download r2upload free enrich step4)
echo "=============================================================="
echo " run_pipeline · pipeline=$PIPELINE · stages ${FROM}→${THROUGH}$([ "$DRY" = 1 ] && echo ' · DRY-RUN')"
echo " competitors: $(competitors | paste -sd' ' -)"
echo "=============================================================="

OVERALL=0
for slug in $(competitors); do
  LOG="$LOGDIR/run_pipeline-${slug}-${STAMP}.log"
  echo; echo "### $slug  (log: ${LOG#$ROOT/})"
  {
    for s in $(seq "$FROM" "$THROUGH"); do
      echo "-- stage $s (${STAGE_NAMES[$s]}) --"
      case "$s" in
        1) stage1_scrape "$slug";;
        2) stage2_download "$slug";;
        3) stage3_r2upload "$slug";;
        4) stage4_free "$slug";;
        5) stage5_enrich "$slug";;
        6) stage6_step4 "$slug";;
        *) echo "  [skip] no stage $s";;
      esac
      rc=$?
      if [ "$rc" = 10 ]; then echo "  → stage $s needs a manual scrape; stopping '$slug'."; OVERALL=10; break; fi
      if [ "$rc" != 0 ]; then echo "  → stage $s exited $rc; stopping '$slug'."; OVERALL=$rc; break; fi
    done
  } > >(tee -a "$LOG") 2>&1     # process-sub (NOT a pipe) so OVERALL persists in this shell
  wait                          # let tee flush before the next competitor
done

echo; echo "run_pipeline done (overall rc=$OVERALL)."
exit "$OVERALL"
