#!/usr/bin/env bash
# Step 4 stages 2-8 (after decompose batch is DONE).
# Run this only after the decompose batch poll returns DONE.
set -e

cd "$(dirname "$0")"

IDS=$(python3.13 scripts/estimate_step4_cost.py --competitor learna-ai --random 5 --seed 42 --json \
    | python3.13 -c "import json,sys; d=json.load(sys.stdin); print(' '.join(e['ad_library_id'] for e in d['estimates']))")
echo "IDs: $IDS"

echo ""
echo "===> Stage 2 — extract frames (ffmpeg, instant)..."
python3.13 scripts/step4_frames.py --competitor learna-ai $IDS

echo ""
echo "===> Stage 3 — character reference sheets (Nano Banana Pro)..."
echo "    (re-run this whole script if it dies mid-way; sheets pre-skip on re-run)"
python3.13 scripts/step4_character_sheets.py --competitor learna-ai $IDS

echo ""
echo "===> Stage 4 — clean panel imagery (Nano Banana Pro)..."
python3.13 scripts/step4_panels.py --competitor learna-ai $IDS

echo ""
echo "===> Stage 5 — submit Supernova rewrite batch..."
python3.13 scripts/step4_rewrite.py submit --competitor learna-ai $IDS
echo ""
echo "===> Active rewrite jobs:"
python3.13 scripts/step4_rewrite.py status

echo ""
echo "===> Rewrite batch submitted. Usually 3-5 min."
echo "===> In a new terminal, poll until DONE:"
echo ""
echo "    cd ~/Desktop/fb-ad-downloader"
echo "    while ! python3.13 scripts/step4_rewrite.py poll <SHORT_ID> | grep -q DONE; do echo waiting...; sleep 30; done"
echo ""
echo "===> When DONE, run: bash 07_step4_finalize.sh"
