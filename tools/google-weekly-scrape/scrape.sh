#!/bin/zsh
# WEEKLY Google FREE data refresh — full cycle (scrape → yt-dlp metadata → R2 upload), then one
# free-analysis pass, for every competitor in competitors.txt. Google is slower + rate-limited
# than Facebook, so this runs ONCE A WEEK and throttles ~30 min between competitors to avoid a
# 429 IP block. NO enrichment (that's paid + stays on the Ad Studio "Enrich" button).
#
# Each competitor is committed; pushed after each + once at the end so origin stays
# fast-forwardable. Scheduled runs use the canonical clone (single writer) + a once-per-week guard.
#
# ⚠ REQUIRES the same VPN / fresh IP that let the manual run through — without it Google may 429
#   every competitor. A blocked competitor is SKIPPED (not retried), so a bad-IP week fails cleanly.
#
# Triggered by launchd weekly (see install.sh). Manual/targeted run (skips guards, may run from a
# worktree, no week-stamp written):
#   GOOGLE_SCRAPE_THROTTLE=1800 zsh tools/google-weekly-scrape/scrape.sh "Busuu" "Memrise"
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/Library/Python/3.13/bin:$PATH"

REPO="${0:A:h:h:h}"            # tools/google-weekly-scrape/scrape.sh -> repo root
cd "$REPO" || exit 1
LIST="$REPO/tools/google-weekly-scrape/competitors.txt"
LOG_DIR="$HOME/Library/Application Support/SupernovaGoogleWeekly"
LOG="$LOG_DIR/scrape.log"
STAMP_FILE="$LOG_DIR/last-run-week"
mkdir -p "$LOG_DIR"
THROTTLE="${GOOGLE_SCRAPE_THROTTLE:-1800}"   # seconds between competitors (default 30 min)

log()    { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }
notify() { zsh "$REPO/tools/notify/notify.sh" "$1" "$2" >/dev/null 2>&1 || true; }
slugify(){ echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-//; s/-$//'; }

push_now() {
  if git push >> "$LOG" 2>&1; then log "pushed."; else
    git pull --no-rebase >> "$LOG" 2>&1 && git push >> "$LOG" 2>&1 && log "pushed after pull." \
      || { log "PUSH FAILED — commits are local."; notify "Google weekly: push failed" "Open Conductor to push."; }
  fi
}

# Manual targeted run: `scrape.sh "Busuu" "Speak"` runs just those, skips the guards, allows a worktree.
MANUAL=0
if [ "$#" -gt 0 ]; then
  MANUAL=1
  log "manual targeted run: $*"
else
  # Scheduled mode: canonical clone only + once-per-ISO-week guard.
  if [ "$(git rev-parse --git-common-dir 2>/dev/null)" != ".git" ]; then
    log "REFUSING: not the canonical clone (a worktree). Skipping."; exit 1
  fi
  WEEK="$(date '+%G-W%V')"
  if [ "$(cat "$STAMP_FILE" 2>/dev/null)" = "$WEEK" ]; then
    log "already ran this week ($WEEK) — skipping."; exit 0
  fi
fi

# Single-instance lock (don't overlap a still-running batch — a full round can take hours).
LOCK="$LOG_DIR/run.lock"
if ! mkdir "$LOCK" 2>/dev/null; then log "another run holds the lock — skipping."; exit 0; fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# run_one — scrape + yt-dlp + R2 upload for one competitor. 0=ok, 10=blocked/no-ads, 1=error.
run_one() {
  local comp="$1"
  local slug; slug=$(slugify "$comp")
  local d;    d=$(date +%Y-%m-%d)
  local csv="google/inputs/g-ads-${slug}-${d}.csv"
  local videos="google/videos/${slug}-${d}"
  local images="google/images/${slug}-${d}"

  if [ "${GOOGLE_SCRAPE_DRYRUN:-0}" = "1" ]; then
    log "   [dry-run] would scrape+upload $comp (slug=$slug) — no network, no commit"; return 10
  fi

  log "[1/3] scrape $comp (slug=$slug)"
  python3.13 google/scripts/scrape_google_ads.py \
      --competitor "$comp" --region IN --out google --no-guardrail >> "$LOG" 2>&1 || true
  if [ ! -f "$csv" ]; then log "   $slug: no CSV (429 / 0 ads) — skipped"; return 10; fi
  local rows; rows=$(( $(wc -l < "$csv") - 1 ))
  if [ "$rows" -le 0 ]; then log "   $slug: 0 rows — skipped"; return 10; fi
  log "   $slug: scraped $rows rows"

  log "[2/3] yt-dlp metadata"
  python3.13 google/scripts/download_google_ads.py "$csv" \
      --videos-out "$videos/" --images-out "$images/" --batch-size 600 >> "$LOG" 2>&1 || true

  log "[3/3] R2 upload + master"
  python3.13 google/scripts/upload_to_r2.py --input "$csv" \
      --videos "$videos/" --images "$images/" --competitor "$slug" \
      --master-dir google/master --log-dir google/step3_logs >> "$LOG" 2>&1 \
    || { log "   $slug: R2 upload FAILED"; return 1; }
  return 0
}

# commit_one — stage this competitor's master + input snapshot + step3 log + ledger, then log_and_commit.
commit_one() {
  local slug="$1" p=google
  setopt LOCAL_OPTIONS NULL_GLOB
  git add -- "$p/master/$slug.csv" "$p/logs/scrape_history.jsonl" \
    "$p"/inputs/g-ads-${slug}-*.csv "$p"/step3_logs/${slug}-* 2>/dev/null || true
  bash tools/log_and_commit.sh "$p" "$slug" "google-weekly" "weekly Google scrape (scrape→R2)" >> "$LOG" 2>&1 || true
}

# ---- build the work list ----
if [ "$MANUAL" = 1 ]; then
  comps=("$@")
else
  comps=()
  while read -r line; do
    line="${line%%#*}"                                                   # strip trailing comment
    line="$(echo "$line" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')" # trim whitespace
    [ -z "$line" ] && continue
    comps+=("$line")
  done < "$LIST"
fi
n=${#comps[@]}

log "=== weekly Google scrape start ($(date '+%Y-%m-%d %H:%M')) — $n competitor(s), throttle=${THROTTLE}s ==="
ok=0; blocked=0; failed=0; i=0
for comp in "${comps[@]}"; do
  i=$((i+1))
  log "---- ($i/$n) $comp ----"
  run_one "$comp"; rc=$?
  if [ "$rc" = 0 ]; then
    commit_one "$(slugify "$comp")"; push_now; log "   $comp: ok"; ok=$((ok+1))
  elif [ "$rc" = 10 ]; then
    blocked=$((blocked+1))
  else
    failed=$((failed+1)); notify "Google weekly: $comp FAILED" "see scrape.log"
  fi
  if [ "$i" -lt "$n" ]; then
    log "throttle: sleeping ${THROTTLE}s before the next competitor (resume ~$(date -v+${THROTTLE}S '+%H:%M' 2>/dev/null || echo '?'))..."
    sleep "$THROTTLE"
  fi
done

# ---- one free-analysis pass for the whole Google pipeline + commit ----
if [ "${GOOGLE_SCRAPE_DRYRUN:-0}" = "1" ]; then
  log "[dry-run] skipping analysis / commit / push"
else
  log "[analysis] run_all_free.sh google"
  bash analysis/scripts/run_all_free.sh google >> "$LOG" 2>&1 || true
  setopt LOCAL_OPTIONS NULL_GLOB
  git add analysis/derived/google analysis/history/google analysis/reports/*_google_* 2>/dev/null || true
  git commit -m "run: google/all by google-weekly — free analysis refresh" >> "$LOG" 2>&1 || true
  push_now
  [ "$MANUAL" = 0 ] && echo "$(date '+%G-W%V')" > "$STAMP_FILE"
fi
log "=== done: ok=$ok blocked=$blocked failed=$failed ==="
notify "Google weekly scrape done" "ok=$ok blocked=$blocked failed=$failed — see scrape.log (blocked = 429/0-ads, not retried)"
