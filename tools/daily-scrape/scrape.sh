#!/bin/zsh
# Daily 6 AM FREE data refresh — Facebook pipeline stages 1–4 (scrape → download →
# R2 upload → rankings/analysis) for every competitor in competitors.txt. NO enrichment
# (stage 5 is paid and stays behind the "Enrich" button in Ad Studio).
#
# Each competitor's data is committed + the whole batch is pushed at the end, so
# origin/main + the Sheet get fresh ranks and the tree stays clean for the 11:30 sync.
#
# Triggered by launchd at 06:00 (see install.sh). If the Mac is asleep at 6 AM, launchd
# runs this on the next wake; the date-guard below stops it running twice in one day.
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

REPO="${0:A:h:h:h}"            # tools/daily-scrape/scrape.sh -> repo root
cd "$REPO" || exit 1
LIST="$REPO/tools/daily-scrape/competitors.txt"
LOG_DIR="$HOME/Library/Application Support/SupernovaDailyScrape"
LOG="$LOG_DIR/scrape.log"
STAMP_FILE="$LOG_DIR/last-run-date"
mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# Run from the canonical clone only (has videos/, on main, single writer).
if [ "$(git rev-parse --git-common-dir 2>/dev/null)" != ".git" ]; then
  log "REFUSING: not the canonical clone (a worktree). Skipping."; exit 1
fi

# Optional competitor args: `scrape.sh duolingo speak` runs just those (a manual/test
# run — skips the once-per-day date guard and doesn't write the daily stamp).
TODAY="$(date '+%Y-%m-%d')"
MANUAL=0
if [ "$#" -gt 0 ]; then
  MANUAL=1
  log "manual targeted run: $*"
else
  # Date guard — launchd may re-fire on wake after a missed 6 AM; only run once per day.
  if [ "$(cat "$STAMP_FILE" 2>/dev/null)" = "$TODAY" ]; then
    log "already ran today ($TODAY) — skipping."; exit 0
  fi
fi

# Single-instance lock (don't overlap a still-running batch).
LOCK="$LOG_DIR/run.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  log "another run holds the lock — skipping."; exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

DRY=""; [ "${DAILY_SCRAPE_DRYRUN:-0}" = "1" ] && DRY="--dry-run"

# Commit one competitor's free-refresh data (master + analysis/derived + history +
# report). log_and_commit alone misses the derived CSVs that drive verdicts/ranks.
commit_one() {
  local slug="$1" p=facebook
  # NULL_GLOB: an empty glob expands to nothing instead of aborting the whole git add
  # (zsh's default nomatch would otherwise stage NOTHING when e.g. {slug}-* matches none).
  setopt LOCAL_OPTIONS NULL_GLOB
  git add -- "$p/master/$slug.csv" "analysis/history/$p/$slug.csv" \
    analysis/derived/$p/${slug}_* analysis/derived/$p/${slug}-* analysis/derived/$p/${slug}.* \
    analysis/reports/*_${slug}_* 2>/dev/null || true
  bash tools/log_and_commit.sh "$p" "$slug" "daily-scrape" "daily free refresh (stages 1-4)" >> "$LOG" 2>&1 || true
}

log "=== daily free refresh start ($TODAY) — $(grep -cvE '^\s*(#|$)' "$LIST") competitors ==="
ok=0; blocked=0; failed=0
# process substitution (NOT a pipe) so the counters survive in this shell
while read -r slug; do
  slug="${slug// /}"; [ -z "$slug" ] && continue
  log "-- $slug --"
  if bash analysis/scripts/run_pipeline.sh --competitor "$slug" --pipeline facebook --through-stage 4 $DRY >> "$LOG" 2>&1; then
    commit_one "$slug"; log "   $slug: ok"; ok=$((ok+1))
  else
    rc=$?
    if [ "$rc" = 10 ]; then log "   $slug: scrape BLOCKED (0 ads/throttle) — skipped"; blocked=$((blocked+1))
    else log "   $slug: FAILED rc=$rc"; failed=$((failed+1)); fi
  fi
done < <(if [ "$MANUAL" = 1 ]; then printf '%s\n' "$@"; else grep -vE '^\s*(#|$)' "$LIST"; fi)

# Push everything once (with one pull-retry), so main stays fast-forwardable.
if ! git diff --quiet HEAD origin/main 2>/dev/null; then :; fi
if git push >> "$LOG" 2>&1; then
  log "pushed."
else
  git pull --no-rebase >> "$LOG" 2>&1 && git push >> "$LOG" 2>&1 && log "pushed after pull." || log "PUSH FAILED — resolve manually."
fi

[ "$MANUAL" = 0 ] && echo "$TODAY" > "$STAMP_FILE"
log "=== done: ok=$ok blocked=$blocked failed=$failed ==="
