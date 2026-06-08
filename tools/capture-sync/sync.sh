#!/bin/zsh
# Supernova competitor-ads — capture-sync (time-critical media capture + enrich).
#
# WHY: a scraped Facebook/Google snapshot points at CDN media URLs that EXPIRE in
# ~4 days. If nobody downloads + pushes that media to R2 before then, it is lost
# forever. This launchd job runs every morning and, for any competitor whose newest
# CANONICAL snapshot is fresh-but-not-yet-processed, runs the staged orchestrator
# (download → R2 upload → free analysis → incremental enrichment) and commits the
# result — so a forgotten snapshot still gets captured inside the expiry window.
#
# It also NOTIFIES which competitors need a fresh MANUAL scrape (their newest
# snapshot is missing or older than the CDN window) — the FB scrape stays manual
# (Claude-in-Chrome), so the job can only remind, not scrape.
#
# SAFETY — mirrors tools/daily-sync (pull-only there; here we also commit/push, so
# the guards matter more):
#   • acts ONLY when main is checked out, clean, and has an upstream — else SKIP+notify
#   • git pull --ff-only first; never hard-resets / force-pushes / merges non-trivially
#   • commits via tools/log_and_commit.sh and pushes; on a non-ff push it pulls
#     --no-rebase once and retries, else leaves the commit local and notifies
#   • a competitor is processed only when its snapshot is NEWER than its master
#     (so already-captured snapshots are not re-run daily)
#
# Install once:  zsh tools/capture-sync/install.sh   (see tools/capture-sync/README.md)
set -u

CDN_WINDOW_DAYS=4          # process snapshots newer than this; older ⇒ "re-scrape"
OPERATOR="capture-sync"    # author label passed to log_and_commit.sh
DRY="${CAPTURE_DRY:-0}"    # CAPTURE_DRY=1 → preview the scan; no pipeline, no git writes

SCRIPT_DIR="${0:A:h}"
REPO="${SCRIPT_DIR:h:h}"
PY="python3.13"
LOG_DIR="$HOME/Library/Application Support/SupernovaCaptureSync"
LOG="$LOG_DIR/capture.log"
mkdir -p "$LOG_DIR"

log()    { print -r -- "$(date '+%Y-%m-%d %H:%M:%S')  $1" >> "$LOG"; }
notify() { osascript -e "display notification \"$2\" with title \"$1\"" >/dev/null 2>&1 || true; }

cd "$REPO" 2>/dev/null || { log "ERR repo not found: $REPO"; exit 1; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { log "ERR not a git repo: $REPO"; exit 1; }

# ---- safety preflight (same shape as daily-sync) ----------------------------
if [ "$DRY" = 1 ]; then log "DRY preview run (no pipeline, no git writes)"; fi
BRANCH="$(git symbolic-ref --short -q HEAD || echo DETACHED)"
if [ "$DRY" != 1 ] && [ "$BRANCH" != "main" ]; then
  log "SKIP on branch '$BRANCH' (not main) — not capturing"
  notify "Capture-sync skipped" "On branch $BRANCH, not main. Open Conductor to run captures."
  exit 0
fi
if [ "$DRY" != 1 ] && [ -n "$(git status --porcelain)" ]; then
  log "SKIP uncommitted changes on main — not capturing (won't stomp your edits)"
  notify "Capture-sync skipped" "Uncommitted changes on main. Commit/stash, then it resumes tomorrow."
  exit 0
fi
[ "$DRY" != 1 ] && git fetch --all --prune >> "$LOG" 2>&1
if [ "$DRY" != 1 ] && git rev-parse --abbrev-ref @{u} >/dev/null 2>&1; then
  git merge --ff-only @{u} >> "$LOG" 2>&1 && log "OK pulled (ff-only) before capture" \
    || { log "SKIP could not ff-only pull (diverged?) — resolve in Conductor"; \
         notify "Capture-sync skipped" "main diverged from origin. Open Conductor to resolve."; exit 0; }
fi

# ---- newest CANONICAL snapshot for a (pipeline,slug) ------------------------
# Allowlist (matches run_pipeline.sh): {prefix}-{slug}-YYYY-MM-DD(-HHMM)?.csv only.
newest_input() {
  local pipeline="$1" slug="$2" dir prefix f
  if [ "$pipeline" = facebook ]; then dir="facebook/inputs"; prefix="fb-ads"
  else dir="google/inputs"; prefix="g-ads"; fi
  # (Nom): N=nullglob (no error when nothing matches), om=newest-mtime first.
  for f in "$dir"/${prefix}-${slug}-*.csv(Nom); do
    if [[ "${f:t}" =~ "^${prefix}-${slug}-[0-9]{4}-[0-9]{2}-[0-9]{2}(-[0-9]{4})?\.csv$" ]]; then
      print -r -- "$f"; return 0
    fi
  done
  return 0
}
age_days() { local mt; mt=$(stat -f %m "$1" 2>/dev/null || echo 0); echo $(( ($(date +%s) - mt) / 86400 )); }

# ---- scan every competitor in both pipelines --------------------------------
processed=(); scrape_needed=(); changed=0
for pipeline in facebook google; do
  for master in "$REPO/$pipeline"/master/*.csv(N); do
    slug="${master:t:r}"
    case "$slug" in *_newly_added*|*_step4*|*_top20*|*_new_only*) continue;; esac
    inp="$(newest_input "$pipeline" "$slug")"
    if [ -z "$inp" ]; then
      scrape_needed+=("$pipeline/$slug(none)"); continue
    fi
    a="$(age_days "$inp")"
    if [ "$a" -gt "$CDN_WINDOW_DAYS" ]; then
      scrape_needed+=("$pipeline/$slug(${a}d)"); continue
    fi
    # process only if the snapshot is NEWER than the master it would feed
    if [ "$inp" -nt "$master" ]; then
      if [ "$DRY" = 1 ]; then
        log "WOULD PROCESS $pipeline/$slug — snapshot ${inp:t} (${a}d) newer than master"
        processed+=("$pipeline/$slug"); continue
      fi
      log "PROCESS $pipeline/$slug — snapshot ${inp:t} (${a}d) newer than master"
      if bash "$REPO/analysis/scripts/run_pipeline.sh" \
            --pipeline "$pipeline" --competitor "$slug" --through-stage 5 >> "$LOG" 2>&1; then
        processed+=("$pipeline/$slug")
        [ -n "$(git status --porcelain)" ] && changed=1
      else
        log "WARN run_pipeline failed for $pipeline/$slug (rc=$?) — see log"
      fi
    fi
  done
done

# ---- commit + push anything captured ----------------------------------------
if [ "$DRY" != 1 ] && [ "$changed" = 1 ] && [ -n "$(git status --porcelain)" ]; then
  note="capture-sync: ${(j:, :)processed}"
  if [ -x "$REPO/tools/log_and_commit.sh" ]; then
    # log_and_commit expects <pipeline> <slug> <name> <note>; use the first processed
    first="${processed[1]}"; cp="${first%%/*}"; cs="${first##*/}"
    bash "$REPO/tools/log_and_commit.sh" "$cp" "$cs" "$OPERATOR" "$note" >> "$LOG" 2>&1 \
      || { git add -A && git commit -q -m "$note" >> "$LOG" 2>&1; }
  else
    git add -A && git commit -q -m "$note" >> "$LOG" 2>&1
  fi
  if git push >> "$LOG" 2>&1; then
    log "OK committed + pushed: $note"
  else
    log "WARN push rejected — pulling --no-rebase and retrying once"
    git pull --no-rebase >> "$LOG" 2>&1
    git push >> "$LOG" 2>&1 && log "OK pushed on retry" \
      || { log "ERR push still failing — commit is local"; \
           notify "Capture-sync: push failed" "Captured locally but push failed. Open Conductor to push."; }
  fi
fi

# ---- summarise --------------------------------------------------------------
summary="captured: ${#processed} · re-scrape due: ${#scrape_needed}"
log "DONE $summary"
[ ${#scrape_needed} -gt 0 ] && log "  re-scrape: ${(j:, :)scrape_needed}"
if [ ${#scrape_needed} -gt 0 ]; then
  notify "Capture-sync: scrape due (${#scrape_needed})" "${(j:, :)scrape_needed}"
elif [ ${#processed} -gt 0 ]; then
  notify "Capture-sync done" "$summary"
fi
exit 0
