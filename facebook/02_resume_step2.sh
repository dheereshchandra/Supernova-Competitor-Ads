#!/usr/bin/env bash
# Resume Step 2 download of Learna-AI ads.
# Picks up from 282/490 — pre-skip handles already-downloaded files.
# Re-run this script any time if it dies, hits 429, etc.
set -e

cd "$(dirname "$0")"

INPUT=inputs/fb-ads-learna-ai-2026-05-28-1230.csv
OUT=videos/learna-ai-2026-05-28

echo "===> Pre-run count:"
ls $OUT/*.mp4 2>/dev/null | wc -l

echo "===> Running downloader..."
python3.13 scripts/download_fb_ads.py "$INPUT" --out "$OUT/" --column ad_library_url --batch-size 10

echo "===> Post-run count:"
ls $OUT/*.mp4 2>/dev/null | wc -l

echo ""
echo "If still under 490: re-run this script after a short wait (15-30 min if you hit HTTP 429)."
echo "When you've maxed out what's downloadable (some IDs are permanently 'unable to extract'): run 03_step3_upload.sh"
