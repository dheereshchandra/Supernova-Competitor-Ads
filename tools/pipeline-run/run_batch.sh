#!/bin/zsh
# run_batch.sh — DURABLE batch runner for the Facebook competitor-ads pipeline.
#
# WHY: running the pipeline as a Claude-session background task means it DIES when
# the session/account switches (and nobody finds out). This script is meant to run
# under launchd (tools/pipeline-run/install.sh) — fully detached from any Claude
# session — so the work survives, auto-resumes, and is observable.
#
# WHAT: for each competitor (tools/pipeline-run/competitors.txt, or args) it runs
#   analysis/scripts/run_pipeline.sh --competitor <slug> --through-stage 5
# i.e. scrape (V2 auto) → download (incremental) → R2 upload → free analysis →
# enrichment. Creative Studio (stage 6, Gemini Pro) is INTENTIONALLY excluded.
# Every underlying stage is idempotent, so a relaunch resumes for free.
#
# DURABILITY:
#   • caffeinate -i wrapper        → idle sleep can't stall a multi-hour run
#   • PID lock                     → two runners never collide (stale lock is stolen)
#   • heartbeat every 20s          → state.py records liveness + a progress fingerprint
#   • exit 0 only when ALL settled → with launchd KeepAlive{SuccessfulExit:false},
#                                     a crash/kill exits non-zero ⇒ launchd relaunches
#                                     ⇒ it resumes; once everything's done it exits 0
#                                     and stays stopped. Per-competitor attempts are
#                                     capped (state.py MAX_ATTEMPTS) so a hard failure
#                                     can't loop forever.
#   • osascript notify             → you hear about done / failures even while away
#
# Usage:  zsh tools/pipeline-run/run_batch.sh [slug ...]
set -u

# launchd has a minimal PATH; Homebrew python3.13/ffmpeg live outside it.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="${0:A:h}"
REPO="${SCRIPT_DIR:h:h}"
PY="python3.13"
STATE_PY="$SCRIPT_DIR/state.py"
COMP_FILE="$SCRIPT_DIR/competitors.txt"
LOG_DIR="$REPO/analysis/logs"
LOG="$LOG_DIR/pipeline-run-$(date +%Y-%m-%d).log"
LOCK="$REPO/analysis/state/pipeline-run.lock"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$LOG_DIR" "$REPO/analysis/state"

log()    { print -r -- "$(date '+%Y-%m-%d %H:%M:%S')  $1" | tee -a "$LOG"; }
notify() { osascript -e "display notification \"$2\" with title \"$1\"" >/dev/null 2>&1 || true; }
st()     { "$PY" "$STATE_PY" "$@" 2>>"$LOG"; }

cd "$REPO" 2>/dev/null || { log "ERR repo not found: $REPO"; exit 1; }

# ── single-writer lock (steal a stale lock whose pid is dead) ────────────────
if [ -f "$LOCK" ]; then
  oldpid="$(cat "$LOCK" 2>/dev/null)"
  if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then
    log "another runner is active (pid $oldpid) — exiting"; exit 0
  fi
  log "stale lock (pid ${oldpid:-?} dead) — taking over"
fi
print -r -- "$$" > "$LOCK"
trap 'rm -f "$LOCK"' EXIT INT TERM

# Prevent idle-sleep from stalling a multi-hour run: a background caffeinate that
# asserts only while THIS runner is alive (-w $$), then exits with us. No re-exec.
caffeinate -i -w $$ >/dev/null 2>&1 &

# ── competitor list ─────────────────────────────────────────────────────────
if [ "$#" -gt 0 ]; then
  slugs=("$@")
else
  slugs=(${(f)"$(grep -vE '^\s*(#|$)' "$COMP_FILE" 2>/dev/null | tr ',' '\n' | tr -d ' ')"})
fi
[ ${#slugs} -gt 0 ] || { log "no competitors (args or $COMP_FILE)"; exit 1; }

st ensure "$RUN_ID" "${slugs[@]}"
st pid "$$"
log "BATCH start (run $RUN_ID) pid=$$ competitors: ${(j:, :)slugs}"

# ── per-competitor pipeline with a live heartbeat ───────────────────────────
run_one() {
  local slug="$1" rc child
  st current "$slug" "1-5"
  st set "$slug" running
  log "── $slug: run_pipeline --through-stage 5 ──"
  bash "$REPO/analysis/scripts/run_pipeline.sh" \
       --pipeline facebook --competitor "$slug" --through-stage 5 >> "$LOG" 2>&1 &
  child=$!
  while kill -0 "$child" 2>/dev/null; do st heartbeat; sleep 20; done
  wait "$child"; rc=$?
  return $rc
}

for slug in "${slugs[@]}"; do
  # skip competitors already finished today (resume semantics).
  # NB: 'status' is a read-only special var in zsh — use cstat.
  cstat="$(st summary | grep -E "^   . ${slug} " | awk '{print $3}')"
  if [ "$cstat" = "done" ]; then log "skip $slug (already done today)"; continue; fi

  att="$(st summary | grep -E "^   . ${slug} " | grep -oE 'attempt [0-9]+' | awk '{print $2}')"
  att=$(( ${att:-0} + 1 ))

  if run_one "$slug"; then
    st set "$slug" done "$att"
    log "OK $slug done"
    notify "Pipeline: $slug ✓" "Finished stages 1–5."
  else
    rc=$?
    st set "$slug" failed "$att"
    log "FAIL $slug (rc=$rc, attempt $att)"
    notify "Pipeline: $slug failed" "Attempt $att, rc=$rc — will retry; check $LOG"
  fi
  st current "" ""
  st heartbeat
done

# ── decide exit code (drives launchd auto-resume) ───────────────────────────
verdict="$(st verdict)"
log "BATCH pass done — verdict: $verdict"
if [ "$verdict" = "done" ]; then
  log "ALL competitors settled — exiting 0 (launchd will not relaunch)."
  # Persist the day's data so csv-sync (and teammates) pick it up — but ONLY from a
  # clean main checkout (the daily-production install). A Conductor worktree / dirty
  # tree / non-main branch is left for a human to commit (so this never stomps edits).
  branch="$(git symbolic-ref --short -q HEAD || echo DETACHED)"
  if [ "$branch" = main ] && [ -n "$(git status --porcelain)" ]; then
    note="pipeline-run: ${(j:, :)slugs} ($(date +%F))"
    if bash "$REPO/tools/log_and_commit.sh" facebook "${slugs[1]}" pipeline-run "$note" >> "$LOG" 2>&1 \
       || { git add -A && git commit -q -m "$note" >> "$LOG" 2>&1; }; then
      git push >> "$LOG" 2>&1 || { git pull --no-rebase >> "$LOG" 2>&1; git push >> "$LOG" 2>&1; } \
        || { log "WARN push failed — commit is local"; notify "Pipeline: push failed" "Committed locally; push manually."; }
      log "committed + pushed the day's data"
    fi
  else
    log "not committing (branch=$branch, or clean) — commit manually if this is a worktree run"
  fi
  notify "Pipeline batch complete" "All competitors processed. See $LOG"
  exit 0
fi
# pending/retriable work remains → non-zero so launchd KeepAlive relaunches (throttled)
pend="$(st pending)"
log "pending after this pass: ${pend:-none} — exiting 1 so launchd relaunches to continue."
exit 1
