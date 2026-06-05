#!/usr/bin/env bash
# Step 3 — upload videos to R2, create master/learna-ai.csv
set -e

cd "$(dirname "$0")"

INPUT=inputs/fb-ads-learna-ai-2026-05-28-1230.csv
VIDEOS=videos/learna-ai-2026-05-28

echo "===> Step 3 dry-run (no uploads, just shows decisions)..."
python3.13 scripts/upload_to_r2.py --input "$INPUT" --videos "$VIDEOS/" --dry-run

echo ""
echo "===> If the tally above looks right, press ENTER to upload for real (Ctrl+C to abort)."
read -r

echo "===> Step 3 real upload..."
python3.13 scripts/upload_to_r2.py --input "$INPUT" --videos "$VIDEOS/"

echo ""
echo "===> Step 3 done. Master CSV at: master/learna-ai.csv"
echo "===> Now run: bash 04_step4_estimate.sh"
