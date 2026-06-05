#!/bin/bash
# One-command end-to-end refresh of every Google competitor in COMPETITORS.
# Pipe-and-walk-away: paste once, walk away, come back to a complete master.
#
# Usage from ~/Desktop/google-ad-downloader:
#   bash run_all_competitors.sh                 # full treatment (default)
#   bash run_all_competitors.sh --quick         # Steps 1+2+3 only, no retries, no HTML5
#   bash run_all_competitors.sh --skip-html5    # skip the HTML5 banner capture pass
#   bash run_all_competitors.sh --skip-retry    # skip the 429 retry pass
#
# What "full treatment" means — the script runs four passes:
#
#   Pass 1 — for every competitor: Step 1 (scrape) + Step 2 (yt-dlp) +
#            Step 3 (R2 upload) + YouTube metadata backfill.
#   Pass 2 — wait 30 minutes for Google's anti-abuse cooldown, then re-run
#            Steps 1+2+3 for any competitor that hit 429s on the first pass.
#            One retry only; bounded wait. If still blocked, surface the
#            failure and continue.
#   Pass 3 — for every html5-banner-no-mp4 row in master, render the ad in
#            a headless Chromium and record it as mp4. ~15-20 seconds per
#            ad; ~6-8 hours for ~1,400 banners across all competitors.
#            Skipped if Playwright isn't installed.
#   Pass 4 — re-run Step 3 for each competitor so the captured HTML5 mp4s
#            land in R2 and r2_public_url fills in.
#
# Tail the live log from a second terminal tab:
#   tail -f logs/run-all-*.log
#
# Expected total runtime (default mode):
#   ~1 hour       Pass 1
#   ~30 min wait  Pass 2 cooldown (if any competitor hit 429)
#   ~10 min       Pass 2 retry
#   ~6-8 hours    Pass 3 HTML5 capture (if Playwright present)
#   ~5 min        Pass 4 final R2 upload
#   ──────────
#   ~8-10 hours total for a fresh full run.

set -u
cd "$(dirname "$0")"

# ---------------------------------------------------------------------------
# Flag parsing
# ---------------------------------------------------------------------------
SKIP_HTML5=0
SKIP_RETRY=0
QUICK=0
for arg in "$@"; do
  case "$arg" in
    --skip-html5)        SKIP_HTML5=1 ;;
    --skip-retry|--skip-retry-blocked) SKIP_RETRY=1 ;;
    --quick)             QUICK=1; SKIP_HTML5=1; SKIP_RETRY=1 ;;
    -h|--help)
      sed -n '2,30p' "$0"; exit 0 ;;
    *)
      echo "Unknown flag: $arg"; echo "Try --help"; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
COMPETITORS=(
  "Memrise"
  "Loora"
  "Praktika AI"
  "Busuu"
  "Speak"
  "SpeakX"
  "Duolingo"
  "English Seekho"
)

# DATE is recomputed per-competitor inside run_competitor and step3_only so
# that a long-running wrapper (e.g. an 11-hour Duolingo scrape) doesn't lock
# itself to the start-of-run date — Step 1 internally uses today's date for
# its CSV filename via Python's date.today(), and Step 3 must use the same.
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/run-all-$(date +%Y%m%d-%H%M).log"

slugify() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-//; s/-$//'
}

# Track competitors that need a retry pass
NEED_RETRY=()

# ---------------------------------------------------------------------------
# run_competitor — Steps 1+2+3+backfill for one competitor
#   Sets the global NEED_RETRY array if the competitor hit a 429 / detail-fetch
#   error during scrape, so Pass 2 can re-attempt only what needs retrying.
# ---------------------------------------------------------------------------
run_competitor() {
  local COMP="$1"
  local SLUG; SLUG=$(slugify "$COMP")
  # Compute date NOW (not at script start) so a long-running wrapper that
  # crosses midnight still pairs Step 1's CSV with Step 3's --input correctly.
  local DATE; DATE=$(date +%Y-%m-%d)
  local CSV="inputs/g-ads-${SLUG}-${DATE}.csv"
  local VIDEOS="videos/${SLUG}-${DATE}"
  local IMAGES="images/${SLUG}-${DATE}"

  echo "" | tee -a "$LOG"
  echo "######################################################" | tee -a "$LOG"
  echo "### $COMP  (slug=$SLUG)   started $(date +%H:%M:%S)" | tee -a "$LOG"
  echo "######################################################" | tee -a "$LOG"

  echo "[step 1] scraping..." | tee -a "$LOG"
  python3 scripts/scrape_google_ads.py \
      --competitor "$COMP" --region IN --out . 2>&1 | tee -a "$LOG"

  if [ ! -f "$CSV" ]; then
    echo "[error] $COMP -- no CSV produced; flagging for Pass 2 retry" | tee -a "$LOG"
    NEED_RETRY+=("$COMP")
    return 1
  fi

  # If the scraped CSV contains scrape-error rows, mark for retry pass
  if grep -q "detail-fetch:" "$CSV" 2>/dev/null; then
    local N_ERR
    N_ERR=$(grep -c "detail-fetch:" "$CSV")
    echo "[note] $COMP has $N_ERR scrape-error rows; will retry in Pass 2" | tee -a "$LOG"
    NEED_RETRY+=("$COMP")
  fi

  echo "[step 2] yt-dlp metadata..." | tee -a "$LOG"
  python3 scripts/download_google_ads.py "$CSV" \
      --videos-out "./$VIDEOS/" --images-out "./$IMAGES/" \
      --batch-size 600 2>&1 | tee -a "$LOG"

  echo "[step 3] R2 upload + master..." | tee -a "$LOG"
  python3 scripts/upload_to_r2.py --input "$CSV" \
      --videos "$VIDEOS/" --images "$IMAGES/" 2>&1 | tee -a "$LOG"

  echo "[backfill] YouTube metadata sidecars into master..." | tee -a "$LOG"
  python3 - "$SLUG" "$VIDEOS" <<'PY' 2>&1 | tee -a "$LOG"
import csv, json, pathlib, sys
slug, videos_dir = sys.argv[1], sys.argv[2]
videos = pathlib.Path(videos_dir)
master = pathlib.Path(f"master/{slug}.csv")
if not master.exists():
    print(f"[backfill] {master} not found, skipping"); sys.exit(0)
meta = {}
for info_path in videos.glob("*.info.json"):
    cr_id = info_path.name.split(".")[0]
    try:
        with info_path.open() as f: data = json.load(f)
    except Exception as e:
        print(f"[backfill] skipping {info_path.name}: {e}"); continue
    meta[cr_id] = {
        "youtube_video_title": (data.get("title") or "")[:500],
        "youtube_video_description": (data.get("description") or "")[:2000],
        "youtube_channel_name": data.get("uploader") or data.get("channel") or "",
        "youtube_video_duration_s": str(data.get("duration", "") or ""),
    }
if not meta:
    print("[backfill] no .info.json sidecars found; nothing to fill"); sys.exit(0)
with master.open(encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f); fields = reader.fieldnames; rows = list(reader)
filled = 0
for r in rows:
    cr = r.get("creative_id", "")
    if cr in meta:
        for col, val in meta[cr].items():
            if val and not r.get(col):
                r[col] = val; filled += 1
with master.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
print(f"[backfill] {slug}: filled {filled} cells from {len(meta)} sidecars")
PY

  echo "### $COMP done at $(date +%H:%M:%S)" | tee -a "$LOG"
}

# ---------------------------------------------------------------------------
# step3_only — re-run Step 3 for one competitor (used in Pass 4 after HTML5
#   captures land on disk). Quick — no scrape, no yt-dlp.
# ---------------------------------------------------------------------------
step3_only() {
  local COMP="$1"
  local SLUG; SLUG=$(slugify "$COMP")
  # Find the most-recent input CSV for this competitor — handles the case
  # where Step 1 ran on Jun 4 and Step 3 re-runs on Jun 5 (different DATE).
  local CSV
  CSV=$(ls -t "inputs/g-ads-${SLUG}-"*.csv 2>/dev/null | grep -v "_enriched\.csv$" | head -1)
  [ -z "$CSV" ] && return 0
  [ ! -f "$CSV" ] && return 0
  # Derive the matching videos / images folders from the CSV's date suffix.
  local STEM CSV_DATE VIDEOS IMAGES
  STEM=$(basename "$CSV" .csv)
  CSV_DATE=${STEM##*-}-${STEM##*-2}   # crude; simpler:
  CSV_DATE=$(echo "$STEM" | grep -Eo '[0-9]{4}-[0-9]{2}-[0-9]{2}$')
  VIDEOS="videos/${SLUG}-${CSV_DATE}"
  IMAGES="images/${SLUG}-${CSV_DATE}"
  echo "[step 3 re-run] $COMP (using $CSV)" | tee -a "$LOG"
  python3 scripts/upload_to_r2.py --input "$CSV" \
      --videos "$VIDEOS/" --images "$IMAGES/" 2>&1 | tee -a "$LOG"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo "=== run-all started $(date) ===" | tee -a "$LOG"
echo "competitors: ${#COMPETITORS[@]}" | tee -a "$LOG"
echo "flags: quick=$QUICK skip-html5=$SKIP_HTML5 skip-retry=$SKIP_RETRY" | tee -a "$LOG"
echo "log: $LOG" | tee -a "$LOG"

# ===== Pass 1: Steps 1+2+3 + backfill for every competitor =====
echo "" | tee -a "$LOG"
echo "===================================" | tee -a "$LOG"
echo "===== PASS 1: first attempt =====" | tee -a "$LOG"
echo "===================================" | tee -a "$LOG"
for COMP in "${COMPETITORS[@]}"; do
  run_competitor "$COMP"
done

# ===== Pass 2: 30-min cooldown + retry blocked =====
if [ $SKIP_RETRY -eq 0 ] && [ ${#NEED_RETRY[@]} -gt 0 ]; then
  echo "" | tee -a "$LOG"
  echo "===================================" | tee -a "$LOG"
  echo "===== PASS 2: 429 retry =====" | tee -a "$LOG"
  echo "===================================" | tee -a "$LOG"
  echo "competitors flagged: ${NEED_RETRY[*]}" | tee -a "$LOG"
  echo "waiting 30 minutes for Google anti-abuse cooldown..." | tee -a "$LOG"
  echo "(start: $(date +%H:%M:%S),  resume: ~$(date -v+30M +%H:%M:%S 2>/dev/null || date -d '+30 minutes' +%H:%M:%S 2>/dev/null || echo '?'))" | tee -a "$LOG"
  sleep 1800
  echo "" | tee -a "$LOG"
  echo "[Pass 2] cooldown elapsed, retrying..." | tee -a "$LOG"
  # Clone the list — run_competitor may re-add to NEED_RETRY but Pass 2 is one-shot
  RETRY_LIST=("${NEED_RETRY[@]}")
  NEED_RETRY=()
  for COMP in "${RETRY_LIST[@]}"; do
    run_competitor "$COMP"
  done
  if [ ${#NEED_RETRY[@]} -gt 0 ]; then
    echo "" | tee -a "$LOG"
    echo "[Pass 2] still blocked after retry: ${NEED_RETRY[*]}" | tee -a "$LOG"
    echo "         not retrying again. Run from a different network when you can." | tee -a "$LOG"
  fi
fi

# ===== Pass 3: HTML5 banner capture =====
if [ $SKIP_HTML5 -eq 0 ]; then
  if python3 -c "import playwright" 2>/dev/null; then
    echo "" | tee -a "$LOG"
    echo "===================================" | tee -a "$LOG"
    echo "===== PASS 3: HTML5 capture =====" | tee -a "$LOG"
    echo "===================================" | tee -a "$LOG"
    echo "this is the long pass — ~15-20 sec per ad" | tee -a "$LOG"
    python3 scripts/capture_html5_banners.py --all-competitors --out . 2>&1 | tee -a "$LOG"
  else
    echo "" | tee -a "$LOG"
    echo "[Pass 3 skipped] playwright not installed" | tee -a "$LOG"
    echo "  to enable: pip3 install --user playwright && python3 -m playwright install chromium" | tee -a "$LOG"
  fi
fi

# ===== Pass 4: re-upload R2 to pick up the captured mp4s =====
if [ $SKIP_HTML5 -eq 0 ] && python3 -c "import playwright" 2>/dev/null; then
  echo "" | tee -a "$LOG"
  echo "===================================" | tee -a "$LOG"
  echo "===== PASS 4: re-upload R2 for new captures =====" | tee -a "$LOG"
  echo "===================================" | tee -a "$LOG"
  for COMP in "${COMPETITORS[@]}"; do
    step3_only "$COMP"
  done
fi

# ===== Summary =====
echo "" | tee -a "$LOG"
echo "=== run-all finished $(date) ===" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Summary of master CSVs:" | tee -a "$LOG"
for COMP in "${COMPETITORS[@]}"; do
  SLUG=$(slugify "$COMP")
  MASTER="master/${SLUG}.csv"
  if [ -f "$MASTER" ]; then
    ROWS=$(($(wc -l < "$MASTER") - 1))
    R2_COUNT=$(awk -F, 'NR>1 {for(i=1;i<=NF;i++) if($i~/^https:\/\/pub-/) {print; break}}' "$MASTER" | wc -l)
    printf "  %-18s  %5d rows  %4d with r2_public_url\n" "$COMP" "$ROWS" "$R2_COUNT" | tee -a "$LOG"
  fi
done

if [ ${#NEED_RETRY[@]} -gt 0 ]; then
  echo "" | tee -a "$LOG"
  echo "Unrecovered competitors (still 429-blocked):" | tee -a "$LOG"
  for c in "${NEED_RETRY[@]}"; do echo "  - $c" | tee -a "$LOG"; done
  echo "Re-run from a different network or after a longer cooldown." | tee -a "$LOG"
fi
