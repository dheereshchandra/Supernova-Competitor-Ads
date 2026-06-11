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

cd "$REPO" 2>/dev/null || { log "ERR repo not found: $REPO"; exit 1; }

# config from .env (grep, not source — values can contain anything): Slack alerts +
# the daily cost cap. Defaults are generous enough for the one-time first backfill
# (~$35); lower PIPELINE_COST_CAP_USD for steady-state daily once enrichment is built.
SLACK_URL="$(grep -E '^SLACK_WEBHOOK_URL=' "$REPO/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'\'' ')"
COST_CAP="$(grep -E '^PIPELINE_COST_CAP_USD=' "$REPO/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d ' ')"; COST_CAP="${COST_CAP:-50}"
COST_PER_VIDEO=0.012

json_escape() { "$PY" -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }
slack() {  # best-effort Slack post; never fails the run. Works headless (curl).
  [ -n "$SLACK_URL" ] || return 0
  curl -sS -m 10 -X POST "$SLACK_URL" -H 'Content-Type: application/json' \
       --data "{\"text\": $(json_escape "$1")}" >/dev/null 2>&1 || true
}
log()    { print -r -- "$(date '+%Y-%m-%d %H:%M:%S')  $1" | tee -a "$LOG"; }
notify() { # $1 title, $2 body → macOS notification + Slack + log (reaches you when away)
  osascript -e "display notification \"$2\" with title \"$1\"" >/dev/null 2>&1 || true
  slack "*$1* — $2"
}
st()     { "$PY" "$STATE_PY" "$@" 2>>"$LOG"; }

# estimate enrichment $ for a slug = (video ads in master with NO transcript) × per-video.
# Uses existing files (pre-scrape), so it slightly under-counts today's brand-new ads —
# fine for a guardrail. Prints "<dollars> <video_count>".
est_cost() {
  "$PY" - "$1" "$COST_PER_VIDEO" <<'PY'
import sys, csv, pathlib
slug, per = sys.argv[1], float(sys.argv[2])
master = pathlib.Path(f"facebook/master/{slug}.csv")
tdir = pathlib.Path(f"analysis/enrichment/facebook/transcripts/{slug}")
done = {p.stem for p in tdir.glob("*.json")} if tdir.is_dir() else set()
todo, seen = 0, set()
if master.is_file():
    for r in csv.DictReader(open(master, encoding="utf-8-sig")):
        aid = (r.get("ad_library_id") or "").strip()
        mt = (r.get("ad_media_type") or "").strip().lower()
        if aid and aid not in seen and aid not in done and ("video" in mt or mt == ""):
            seen.add(aid); todo += 1
print(f"{todo*per:.2f} {todo}")
PY
}

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
spent=0.00                       # cumulative estimated enrichment spend this run
typeset -a REPORT                # per-competitor lines for the daily report
log "BATCH start (run $RUN_ID) pid=$$ competitors: ${(j:, :)slugs}"
slack ":rocket: Pipeline run *$RUN_ID* started — ${(j:, :)slugs} (cost cap \$$COST_CAP)"

# ── per-competitor pipeline (cost-capped) with a live heartbeat ─────────────
run_one() {
  local slug="$1" rc child stage=5 est ed en
  # cost cap (F): estimate enrichment $; if it would bust the cap, run stages 1–4
  # only (NO enrichment) and alert — never blow the budget silently.
  est="$(est_cost "$slug")"; ed="${est%% *}"; en="${est##* }"
  if "$PY" -c "import sys; sys.exit(0 if ($spent + $ed) > $COST_CAP else 1)"; then
    stage=4
    log "  [cost] $slug est \$$ed ($en videos) + spent \$$spent would exceed cap \$$COST_CAP → stages 1–4 only (skip enrichment)"
    notify "Pipeline: cost cap hit" "$slug enrichment skipped (est \$$ed, cap \$$COST_CAP). Raise PIPELINE_COST_CAP_USD to run it."
  fi
  st current "$slug" "1-$stage"
  st set "$slug" running
  log "── $slug: run_pipeline --through-stage $stage ──"
  bash "$REPO/analysis/scripts/run_pipeline.sh" \
       --pipeline facebook --competitor "$slug" --through-stage "$stage" >> "$LOG" 2>&1 &
  child=$!
  while kill -0 "$child" 2>/dev/null; do st heartbeat; sleep 20; done
  wait "$child"; rc=$?
  if [ "$stage" = 5 ] && [ "$rc" = 0 ]; then
    spent="$("$PY" -c "print(f'{$spent + $ed:.2f}')")"
  fi
  return $rc
}

for slug in "${slugs[@]}"; do
  # skip competitors already finished today (resume semantics).
  # NB: 'status' is a read-only special var in zsh — use cstat.
  cstat="$(st summary | grep -E "^   . ${slug} " | awk '{print $3}')"
  if [ "$cstat" = "done" ]; then log "skip $slug (already done today)"; continue; fi

  att="$(st summary | grep -E "^   . ${slug} " | grep -oE 'attempt [0-9]+' | awk '{print $2}')"
  att=$(( ${att:-0} + 1 ))

  run_one "$slug"; prc=$?

  # per-run sanity AUDIT (C) — catches "exit 0 but BAD" (0 ads, silent enrichment hole)
  averdict="$("$PY" "$SCRIPT_DIR/audit.py" "$slug" 2>>"$LOG" | grep '^AUDIT ' | head -1)"
  averd="$(echo "$averdict" | awk '{print $3}')"; areason="${averdict#*| }"

  if [ "$prc" = 0 ] && [ "$averd" != FAIL ]; then
    st set "$slug" done "$att"
    log "OK $slug done — audit:$averd"
    REPORT+=("✓ $slug — done (audit ${averd:-?}; $areason)")
    [ "$averd" = WARN ] && notify "Pipeline: $slug ⚠" "Done but audit WARN: $areason"
  else
    st set "$slug" failed "$att"
    log "FAIL $slug (pipeline rc=$prc, audit=$averd, attempt $att)"
    REPORT+=("✗ $slug — FAIL (pipeline rc=$prc; audit ${averd:-?}; $areason)")
    notify "Pipeline: $slug FAILED" "rc=$prc, audit=$averd — $areason. Retry $att; see log."
  fi
  st current "" ""
  st heartbeat
done

# ── decide exit code (drives launchd auto-resume) ───────────────────────────
verdict="$(st verdict)"
log "BATCH pass done — verdict: $verdict"

write_daily_report() {  # durable, committed record of the day's run
  local f="$REPO/analysis/reports/daily-run-$(date +%Y-%m-%d).md"
  mkdir -p "$REPO/analysis/reports"
  {
    echo "# Daily pipeline run — $(date +%Y-%m-%d)  (run $RUN_ID)"
    echo
    echo "- Competitors: ${(j:, :)slugs}"
    echo "- Estimated enrichment spend: \$$spent  (cap \$$COST_CAP)"
    echo "- Verdict: $verdict"
    echo
    echo "## Results (pipeline status + sanity-audit verdict)"
    for line in "${REPORT[@]}"; do echo "- $line"; done
    echo
    echo "Full log: \`analysis/logs/pipeline-run-$(date +%Y-%m-%d).log\`"
  } > "$f"
  log "daily report → ${f#$REPO/}"
}

if [ "$verdict" = "done" ]; then
  log "ALL competitors settled — exiting 0 (launchd will not relaunch)."
  write_daily_report
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
      # E: refresh the Sheet now (don't wait for the 19:00 csv-sync) so today's
      # ranks/columns are visible same-hour.
      launchctl kickstart -k "gui/$(id -u)/live.gosupernova.csv-sync" >/dev/null 2>&1 \
        && log "triggered csv-sync (Sheet refresh)" \
        || log "(csv-sync job not installed — Sheet refreshes on its own schedule)"
    fi
  else
    log "not committing (branch=$branch, or clean) — worktree run; commit manually + the Sheet refreshes from main"
  fi
  # final summary to Slack (reaches you when away) + macOS
  fails=$(printf '%s\n' "${REPORT[@]}" | grep -c '^✗') || true
  icon=":white_check_mark:"; [ "${fails:-0}" -gt 0 ] && icon=":warning:"
  slack "$icon Pipeline run *$RUN_ID* complete — ${fails:-0} failed, spend ~\$$spent.
${(F)REPORT}"
  notify "Pipeline batch complete" "${fails:-0} failed. See $LOG"
  exit 0
fi
# pending/retriable work remains → non-zero so launchd KeepAlive relaunches (throttled)
pend="$(st pending)"
log "pending after this pass: ${pend:-none} — exiting 1 so launchd relaunches to continue."
slack ":hourglass_flowing_sand: Pipeline run *$RUN_ID* pass done — still pending: ${pend:-none}. Auto-retrying."
exit 1
