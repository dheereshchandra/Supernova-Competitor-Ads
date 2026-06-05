#!/usr/bin/env bash
# Step 4 — run the 8-stage pipeline on a random-5 Learna-AI sample.
# Uses seed=42 so the same 5 IDs are selected as the estimate script picked.
#
# This script pauses at the Gemini-batch stages where you need to wait for
# the queue. Re-run it any time — every stage is idempotent.
set -e

cd "$(dirname "$0")"

echo "===> Extracting the same 5 IDs the estimator picked (seed=42)..."
IDS=$(python3.13 scripts/estimate_step4_cost.py --competitor learna-ai --random 5 --seed 42 --json \
    | python3.13 -c "import json,sys; d=json.load(sys.stdin); print(' '.join(e['ad_library_id'] for e in d['estimates']))")
echo "IDs: $IDS"
if [ -z "$IDS" ]; then
    echo "[error] No IDs extracted. Run 04_step4_estimate.sh first."
    exit 1
fi

echo ""
echo "===> Stage 1a — upload videos to Gemini Files API..."
python3.13 scripts/step4_decompose.py upload --competitor learna-ai $IDS

echo ""
echo "===> Stage 1b — submit decompose batch..."
python3.13 scripts/step4_decompose.py submit --competitor learna-ai $IDS

echo ""
echo "===> Active Gemini batch jobs:"
python3.13 scripts/step4_decompose.py status

echo ""
echo "===> Decompose batch submitted. It usually takes 10-40 min in the Gemini queue."
echo "===> Copy the short_id from above (it looks like 'xxxxxxxx'), then in a NEW terminal:"
echo ""
echo "    cd ~/Desktop/fb-ad-downloader"
echo "    while ! python3.13 scripts/step4_decompose.py poll <SHORT_ID> | grep -q DONE; do echo waiting...; sleep 60; done"
echo ""
echo "===> When that poll returns DONE, come back here and run: bash 06_step4_continue.sh"
