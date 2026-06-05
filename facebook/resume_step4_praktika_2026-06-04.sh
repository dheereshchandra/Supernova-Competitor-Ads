#!/usr/bin/env bash
# Resume Step 4 for the final 2 Praktika ads once the decompose batch finishes.
# 18 of the top-20 are already complete and registered in master/praktika-ai.csv.
# These 2 were submitted in decompose batch short_id=cyx65718byv6114g (Gemini queue
# was congested on 2026-06-04 and had not finished when the session ended).
set -e
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

IDS="1391383766354969 1449273303357626"
BATCH=cyx65718byv6114g

echo "===> 1. Poll decompose batch until DONE:"
while ! python3 scripts/step4_decompose.py poll $BATCH | grep -q DONE; do echo "  waiting..."; sleep 60; done

echo "===> 2. Frames (ffmpeg)";            python3 scripts/step4_frames.py           --competitor praktika-ai $IDS
echo "===> 3. Character sheets";           python3 scripts/step4_character_sheets.py --competitor praktika-ai $IDS
echo "===> 4. Panels";                     python3 scripts/step4_panels.py           --competitor praktika-ai $IDS
echo "===> 4.5 Upload images to R2";       python3 scripts/step4_upload_images.py    --competitor praktika-ai $IDS
echo "===> 5. Submit Supernova rewrite";   python3 scripts/step4_rewrite.py submit   --competitor praktika-ai $IDS
echo "    (copy the rewrite short_id printed above, then poll until DONE:)"
echo "    while ! python3 scripts/step4_rewrite.py poll <SHORT_ID> | grep -q DONE; do sleep 30; done"
echo "===> Then finalize:"
echo "    python3 scripts/step4_build_docs.py        --competitor praktika-ai $IDS"
echo "    python3 scripts/step4_upload_and_update.py --competitor praktika-ai $IDS"
echo "    python3 scripts/step4_audit.py             --competitor praktika-ai $IDS"
