#!/usr/bin/env bash
# Step 4 stages 6-8 + final verification.
set -e

cd "$(dirname "$0")"

IDS=$(python3.13 scripts/estimate_step4_cost.py --competitor learna-ai --random 5 --seed 42 --json \
    | python3.13 -c "import json,sys; d=json.load(sys.stdin); print(' '.join(e['ad_library_id'] for e in d['estimates']))")
echo "IDs: $IDS"

echo ""
echo "===> Stage 6 — build the docx files..."
python3.13 scripts/step4_build_docs.py --competitor learna-ai $IDS

echo ""
echo "===> Stage 7+8 — upload docs to R2, back-fill master CSV..."
python3.13 scripts/step4_upload_and_update.py --competitor learna-ai $IDS

echo ""
echo "===> Final verification:"
python3.13 - <<'PY'
import csv
with open('master/learna-ai.csv', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))
print(f'master total rows: {len(rows)}')
have_video = sum(1 for r in rows if r.get('r2_public_url'))
have_analysis = sum(1 for r in rows if r.get('competitor_analysis_docx_r2_url'))
have_rewrite = sum(1 for r in rows if r.get('supernova_rewrite_docx_r2_url'))
print(f'with r2_public_url:                       {have_video}')
print(f'with competitor_analysis_docx_r2_url:     {have_analysis}')
print(f'with supernova_rewrite_docx_r2_url:       {have_rewrite}')
PY

echo ""
echo "===> Pipeline complete. Open master/learna-ai.csv to inspect."
