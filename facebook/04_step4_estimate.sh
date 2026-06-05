#!/usr/bin/env bash
# Step 4 cost estimate (free, no API calls).
# Random-5 sample with seed=42 for reproducibility.
set -e

cd "$(dirname "$0")"

python3.13 scripts/estimate_step4_cost.py --competitor learna-ai --random 5 --seed 42

echo ""
echo "===> If the BATCH TOTAL above looks reasonable (expect ~\$1-2), run: bash 05_step4_run.sh"
