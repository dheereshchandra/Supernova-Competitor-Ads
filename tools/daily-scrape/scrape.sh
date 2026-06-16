#!/bin/zsh
# Daily FREE Facebook refresh — pipeline stages 1–4 (scrape → download → R2 upload →
# rankings/analysis) for every competitor in competitors.txt. NO enrichment (stage 5 is
# paid and stays behind the "Enrich" button in Ad Studio).
#
# Each competitor's data is committed + the whole fire is pushed at the end, so origin/main
# + the Sheet get fresh ranks and the tree stays clean for the 11:30 sync.
#
# ── RATE-LIMIT HARDENING (2026-06-16) ──────────────────────────────────────────────────
# Facebook throttles this Mac's single static IP after ~8 back-to-back competitor
# scrapes/downloads, so the BACK HALF of one long run used to come back "0 ads" for
# everyone (it wasn't 0 advertisers — it was a throttled IP). Four mitigations:
#   1. SPLIT    The list is cut at the "batch-split" marker in competitors.txt into an
#               AM half (06:00, fresh IP) and a PM half (13:00, cooled IP). The launchd job
#               fires TWICE; each half is small enough to stay under the limit.
#   2. PACE     COMPETITOR_PAUSE_SECS (default 90) between competitors within a batch.
#   3. RETRY    Competitors that get 0 ads are retried ONCE after a RETRY_COOLDOWN_SECS
#               (default 900 = 15 min) cool-down, when the IP has recovered. (A *cooled*
#               retry is the sanctioned exception to run_pipeline's "never re-scrape a 0-ad
#               page" rule — that rule targets *immediate* re-scrapes, which only deepen the
#               throttle. A scrape 15 min later is exactly when it's worth another shot.)
#   4. CLASSIFY A 0-ad competitor that never recovers is split into "empty" (genuinely no
#               active ads — e.g. memrise/praktika-ai) vs "blocked" (a real, recent
#               advertiser still returning 0 — needs a human). Slack alerts only on
#               blocked/failed, so an expected empty no longer cries wolf.
#
# Triggered by launchd at 06:00 and 13:00 (see install.sh). If the Mac is asleep at a fire
# time, launchd runs this on the next wake; the per-batch date-guard stops a double run, and
# a single coalesced wake that missed BOTH fires catches up by running AM, cooling down, then
# PM in one go.
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

REPO="${0:A:h:h:h}"            # tools/daily-scrape/scrape.sh -> repo root
cd "$REPO" || exit 1
LIST="$REPO/tools/daily-scrape/competitors.txt"
LOG_DIR="$HOME/Library/Application Support/SupernovaDailyScrape"
LOG="$LOG_DIR/scrape.log"
AM_STAMP="$LOG_DIR/last-run-am"   # holds YYYY-MM-DD of the last AM batch start
PM_STAMP="$LOG_DIR/last-run-pm"   # holds YYYY-MM-DD of the last PM batch start
mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }
# macOS banner + Slack (when SLACK_WEBHOOK_URL is in .env) via the shared notifier
notify() { zsh "$REPO/tools/notify/notify.sh" "$1" "$2" >/dev/null 2>&1 || true; }

# Run from the canonical clone only (has videos/, on main, single writer).
if [ "$(git rev-parse --git-common-dir 2>/dev/null)" != ".git" ]; then
  log "REFUSING: not the canonical clone (a worktree). Skipping."; exit 1
fi

# ── tunables (env-overridable) ──────────────────────────────────────────────────────────
PAUSE="${COMPETITOR_PAUSE_SECS:-90}"      # seconds between competitors in a batch
COOLDOWN="${RETRY_COOLDOWN_SECS:-900}"    # cool-down before the 0-ad retry pass (15 min)
BATCH_GAP="${BATCH_GAP_SECS:-$COOLDOWN}"  # gap between AM and PM on a coalesced cold-wake
PM_AFTER_HOUR="${DAILY_SCRAPE_PM_HOUR:-11}"  # a fire at/after this local hour is the PM fire

DRY=""
if [ "${DAILY_SCRAPE_DRYRUN:-0}" = "1" ]; then
  DRY="--dry-run"; PAUSE=0; COOLDOWN=0; BATCH_GAP=0   # dry-run must not actually sleep
fi

TODAY="$(date '+%Y-%m-%d')"
HOUR="$(date '+%H')"; HOUR="${HOUR#0}"; [ -z "$HOUR" ] && HOUR=0   # strip leading zero

# Optional competitor args: `scrape.sh duolingo speak` runs just those, as one ad-hoc batch
# (paced + retried like a normal batch) — skips the AM/PM split + date-guard, writes no stamp.
MANUAL=0
typeset -a MANUAL_SLUGS
if [ "$#" -gt 0 ]; then MANUAL=1; MANUAL_SLUGS=("$@"); fi

# Per-fire result buckets (slug lists; counts derived from these).
typeset -ga OK_S RECOVERED_S EMPTY_S BLOCKED_S FAILED_S
OK_S=(); RECOVERED_S=(); EMPTY_S=(); BLOCKED_S=(); FAILED_S=()

# ── helpers ─────────────────────────────────────────────────────────────────────────────

# Print one half of competitors.txt. The list is split at the first line containing
# "batch-split" (a comment): lines ABOVE = am, BELOW = pm. No marker → am gets everything,
# pm gets nothing (back-compat: behaves like one batch, just paced + retried).
batch_slugs() {  # $1 = am|pm
  local which="$1" split_ln
  # Match ONLY the real marker line (`# ===== batch-split ... =====`), not prose in the
  # header that happens to mention "batch-split".
  split_ln="$(grep -niE '^[[:space:]]*#+[[:space:]]*=+[[:space:]]*batch-split' "$LIST" | head -1 | cut -d: -f1)"
  if [ -z "$split_ln" ]; then
    [ "$which" = am ] && grep -vE '^[[:space:]]*(#|$)' "$LIST"
    return 0
  fi
  if [ "$which" = am ]; then
    awk -v n="$split_ln" 'NR<n' "$LIST" | grep -vE '^[[:space:]]*(#|$)'
  else
    awk -v n="$split_ln" 'NR>n' "$LIST" | grep -vE '^[[:space:]]*(#|$)'
  fi
}

# Read stdin into the global SLUGS array, trimming spaces and skipping blanks.
read_slugs() {  # populates SLUGS
  typeset -ga SLUGS; SLUGS=()
  local line
  while IFS= read -r line; do
    line="${line// /}"
    [ -n "$line" ] && SLUGS+=("$line")
  done
}

# Commit one competitor's free-refresh data (master + analysis/derived + history + report).
# log_and_commit alone misses the derived CSVs that drive verdicts/ranks.
commit_one() {
  local slug="$1" p=facebook
  setopt LOCAL_OPTIONS NULL_GLOB   # an empty glob expands to nothing (zsh would else abort)
  git add -- "$p/master/$slug.csv" "analysis/history/$p/$slug.csv" \
    analysis/derived/$p/${slug}_* analysis/derived/$p/${slug}-* analysis/derived/$p/${slug}.* \
    analysis/reports/*_${slug}_* 2>/dev/null || true
  bash tools/log_and_commit.sh "$p" "$slug" "daily-scrape" "daily free refresh (stages 1-4)" >> "$LOG" 2>&1 || true
}

# Run one competitor through stages 1–4. Returns the pipeline rc (0 ok · 10 = 0-ads/blocked ·
# anything else = real failure). Commits on success.
run_one() {
  local slug="$1" rc
  bash analysis/scripts/run_pipeline.sh --competitor "$slug" --pipeline facebook --through-stage 4 $DRY >> "$LOG" 2>&1
  rc=$?
  [ "$rc" = 0 ] && commit_one "$slug"
  return $rc
}

# Classify a competitor that returned 0 ads even after the cooled retry, into EMPTY
# (expected — no active ads) vs BLOCKED (real advertiser, needs attention). Uses the
# history-aware helper; falls back to BLOCKED if it can't decide.
classify_zero() {
  local slug="$1" out cls note
  out="$(python3.13 "$REPO/tools/daily-scrape/classify_zero.py" "$slug" 2>/dev/null)"
  cls="${out%%|*}"; note="${out#*|}"
  if [ "$cls" = "EMPTY" ]; then
    log "   $slug: empty — ${note:-no active ads}"; EMPTY_S+=("$slug")
  else
    log "   $slug: BLOCKED — ${note:-0 ads after cooled retry}"; BLOCKED_S+=("$slug")
  fi
}

# Run one paced batch (main pass), then a single cooled retry pass for whatever got 0 ads,
# then classify the survivors. $1 = am|pm|manual (label only).
run_batch() {
  local name="$1" slug rc first
  if [ "$name" = manual ]; then SLUGS=("${MANUAL_SLUGS[@]}"); else read_slugs < <(batch_slugs "$name"); fi
  local n=${#SLUGS}
  if [ "$n" -eq 0 ]; then log "── batch '$name': no competitors configured — nothing to do ──"; return 0; fi

  log "── batch '$name' ($n competitor(s); pace=${PAUSE}s) ──"
  local -a blocked
  blocked=()
  first=1
  for slug in "${SLUGS[@]}"; do
    if [ "$first" = 0 ] && [ "$PAUSE" -gt 0 ]; then
      log "   …pacing ${PAUSE}s before next competitor (stay under FB's rate limit)"; sleep "$PAUSE"
    fi
    first=0
    log "-- $slug --"
    run_one "$slug"; rc=$?
    if [ "$rc" = 0 ]; then log "   $slug: ok"; OK_S+=("$slug")
    elif [ "$rc" = 10 ]; then log "   $slug: 0 ads — queued for a cooled retry"; blocked+=("$slug")
    else
      log "   $slug: FAILED rc=$rc"; FAILED_S+=("$slug")
      notify "Daily scrape: $slug FAILED" "exit $rc — see scrape.log"
    fi
  done

  # Cooled retry pass — only for the 0-ad set, and only once.
  if [ ${#blocked} -gt 0 ]; then
    if [ "$COOLDOWN" -gt 0 ]; then
      log "── batch '$name': ${#blocked} got 0 ads (${blocked[*]}) — cooling down $((COOLDOWN/60))m, then one retry ──"
      sleep "$COOLDOWN"
    else
      log "── batch '$name': ${#blocked} got 0 ads (${blocked[*]}) — retrying (no cooldown: dry-run) ──"
    fi
    first=1
    for slug in "${blocked[@]}"; do
      if [ "$first" = 0 ] && [ "$PAUSE" -gt 0 ]; then sleep "$PAUSE"; fi
      first=0
      log "-- $slug (retry) --"
      run_one "$slug"; rc=$?
      if [ "$rc" = 0 ]; then log "   $slug: ok (recovered on cooled retry — was throttled)"; RECOVERED_S+=("$slug")
      elif [ "$rc" = 10 ]; then classify_zero "$slug"
      else log "   $slug: FAILED rc=$rc (on retry)"; FAILED_S+=("$slug"); notify "Daily scrape: $slug FAILED" "exit $rc on retry — see scrape.log"
      fi
    done
  fi
}

# Per-batch date-guard helpers (auto mode only).
am_done() { [ "$(cat "$AM_STAMP" 2>/dev/null)" = "$TODAY" ]; }
pm_done() { [ "$(cat "$PM_STAMP" 2>/dev/null)" = "$TODAY" ]; }

# ── single-instance lock ────────────────────────────────────────────────────────────────
LOCK="$LOG_DIR/run.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  log "another run holds the lock — skipping."; exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# ── drive the run ───────────────────────────────────────────────────────────────────────
RAN=""
if [ "$MANUAL" = 1 ]; then
  log "=== manual targeted run ($TODAY): ${MANUAL_SLUGS[*]} ==="
  run_batch manual
  RAN="manual"
else
  # AM = early fire (fresh IP); PM = late fire (cooled IP). On a single coalesced wake that
  # missed BOTH fires, run AM, gap, then PM.
  run_am=0; run_pm=0
  if [ "$HOUR" -lt "$PM_AFTER_HOUR" ]; then
    am_done || run_am=1
  else
    am_done || run_am=1        # missed the morning fire entirely → catch it up now
    pm_done || run_pm=1
  fi

  if [ "$run_am" = 0 ] && [ "$run_pm" = 0 ]; then
    log "=== already ran today's due batch(es) ($TODAY, hour $HOUR) — skipping ==="
    exit 0
  fi

  log "=== daily free refresh start ($TODAY, hour $HOUR) — AM=$run_am PM=$run_pm ==="
  if [ "$run_am" = 1 ]; then
    run_batch am
    [ "$DRY" = "" ] && echo "$TODAY" > "$AM_STAMP"
    RAN="AM"
  fi
  if [ "$run_pm" = 1 ]; then
    if [ "$run_am" = 1 ] && [ "$BATCH_GAP" -gt 0 ]; then
      log "── cold-wake catch-up: gapping $((BATCH_GAP/60))m so the PM batch hits a cooled IP ──"
      sleep "$BATCH_GAP"
    fi
    run_batch pm
    [ "$DRY" = "" ] && echo "$TODAY" > "$PM_STAMP"
    RAN="${RAN:+$RAN+}PM"
  fi
fi

# ── push everything once (with one pull-retry) so main stays fast-forwardable ────────────
if git push >> "$LOG" 2>&1; then
  log "pushed."
else
  git pull --no-rebase >> "$LOG" 2>&1 && git push >> "$LOG" 2>&1 && log "pushed after pull." \
    || { log "PUSH FAILED — resolve manually."; notify "Daily scrape: push failed" "Commits are local — open Conductor to push."; }
fi

# ── summary + alert ─────────────────────────────────────────────────────────────────────
ok=${#OK_S}; recovered=${#RECOVERED_S}; empty=${#EMPTY_S}; blocked=${#BLOCKED_S}; failed=${#FAILED_S}
log "=== done ($RAN): ok=$ok recovered=$recovered empty=$empty blocked=$blocked failed=$failed ==="
[ "$recovered" -gt 0 ] && log "    recovered (were throttled, now fresh): ${RECOVERED_S[*]}"
[ "$empty"     -gt 0 ] && log "    empty (no active ads — expected):       ${EMPTY_S[*]}"
[ "$blocked"   -gt 0 ] && log "    BLOCKED (real advertiser, 0 ads — check): ${BLOCKED_S[*]}"
[ "$failed"    -gt 0 ] && log "    FAILED (real errors):                   ${FAILED_S[*]}"

# Alert ONLY when something needs a human — an expected "empty" stays quiet.
if [ "$blocked" -gt 0 ] || [ "$failed" -gt 0 ]; then
  binfo=""; [ "$blocked" -gt 0 ] && binfo="blocked: ${BLOCKED_S[*]} · "
  finfo=""; [ "$failed"  -gt 0 ] && finfo="failed: ${FAILED_S[*]} · "
  notify "Daily scrape ($RAN): blocked=$blocked failed=$failed" \
    "blocked = real advertiser returned 0 ads even after a cooled retry (likely throttle/page issue) · failed = real errors · ${binfo}${finfo}see scrape.log"
fi
