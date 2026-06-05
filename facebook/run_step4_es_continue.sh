#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Step 4 continuation — English Seekho top-20 (by row_rank), batch 2026-06-04.
# Decompose batch short_id: qzkjw63snkpsue1j  (submitted 2026-06-04, $11.78 est.)
#
# Safe to re-run any number of times — every stage is idempotent and resumes
# from its on-disk checkpoint. Run this AFTER the decompose batch reports DONE.
# Usage:  bash run_step4_es_continue.sh
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")"

COMP=english-seekho
DECOMPOSE_SHORT=xjplmqf0tdozichh
IDS="2490626478079076 1008376008280324 27545658091701815 27417472307892610 835603072955889 1753605869341627 2200879757377961 1302516825430257 1483037666208224 1052565497102220 876287251448118 2078950623024665 2505471363291833 1719504072403935 2056613488574281 2092207258026410 984431433971622 968883082730315 995219973120049 2230315987725301"
PY=python3

echo "===> ensuring deps"
$PY -c "import google.genai, boto3, PIL, docx, openpyxl" 2>/dev/null || \
  pip install --break-system-packages --quiet google-genai boto3 pillow python-docx openpyxl

echo "===> Stage 1 — checking decompose batch $DECOMPOSE_SHORT"
OUT=$($PY scripts/step4_decompose.py poll "$DECOMPOSE_SHORT" 2>&1)
echo "$OUT" | grep -E "state:|DONE|elapsed" || echo "$OUT" | tail -3
if ! echo "$OUT" | grep -q "DONE"; then
  echo "[wait] decompose batch not DONE yet — re-run this script later."
  exit 3
fi

echo "===> Stage 2 — frames (ffmpeg)"
$PY scripts/step4_frames.py --competitor $COMP $IDS 2>&1 | tail -3

echo "===> Stage 3 — character sheets (Nano Banana Pro)"
for a in 1 2 3 4 5; do
  O=$($PY scripts/step4_character_sheets.py --competitor $COMP $IDS 2>&1)
  echo "$O" | tail -2
  echo "$O" | grep -qiE "all .* sheets present|status clear|nothing to do" && break
done

echo "===> Stage 4 — clean panels (Nano Banana Pro)"
for a in 1 2 3 4 5 6 7 8; do
  O=$($PY scripts/step4_panels.py --competitor $COMP $IDS 2>&1)
  echo "$O" | tail -2
  echo "$O" | grep -qiE "all .* panels present|status clear|nothing to do" && break
done

echo "===> Stage 4.5 — upload images to R2"
$PY scripts/step4_upload_images.py --competitor $COMP $IDS 2>&1 | tail -3

echo "===> Stage 5 — Supernova rewrite batch"
RW_STATE=$(ls -t step4_workspace/batches/rewrite_*.json 2>/dev/null | head -1)
if [ -z "$RW_STATE" ]; then
  RWOUT=$($PY scripts/step4_rewrite.py submit --competitor $COMP $IDS 2>&1); echo "$RWOUT" | tail -4
  RW_SHORT=$(echo "$RWOUT" | grep -E "short id:" | head -1 | awk '{print $NF}')
else
  RW_SHORT=$(basename "$RW_STATE" .json | sed 's/^rewrite_//')
fi
echo "rewrite short_id: $RW_SHORT"
for i in $(seq 1 40); do
  O=$($PY scripts/step4_rewrite.py poll "$RW_SHORT" 2>&1)
  echo "$O" | grep -E "state:|DONE|elapsed" | tail -1
  echo "$O" | grep -q "DONE" && break
  echo "$O" | grep -qE "FAILED|EXPIRED|CANCELLED" && { echo "[error] rewrite batch failed"; break; }
  sleep 30
done

echo "===> Stage 6 — build docx"
$PY scripts/step4_build_docs.py --competitor $COMP $IDS 2>&1 | tail -4

echo "===> Stage 7+8 — upload docs + back-fill master"
$PY scripts/step4_upload_and_update.py --competitor $COMP $IDS 2>&1 | tail -6

echo "===> Audit"
$PY scripts/step4_audit.py --competitor $COMP $IDS 2>&1 | tail -8

echo "===> Verification"
$PY - <<'PYEOF'
import csv
rows=list(csv.DictReader(open('master/english-seekho.csv',encoding='utf-8-sig')))
ids=set("2490626478079076 1008376008280324 27545658091701815 27417472307892610 835603072955889 1753605869341627 2200879757377961 1302516825430257 1483037666208224 1052565497102220 876287251448118 2078950623024665 2505471363291833 1719504072403935 2056613488574281 2092207258026410 984431433971622 968883082730315 995219973120049 2230315987725301".split())
sel=[r for r in rows if r.get('ad_library_id','').strip() in ids]
def has(r,c): return bool(r.get(c,'').strip())
print('master rows:', len(rows))
print('top20 with competitor_analysis_docx_r2_url:', sum(1 for r in sel if has(r,'competitor_analysis_docx_r2_url')))
print('top20 with supernova_rewrite_docx_r2_url:  ', sum(1 for r in sel if has(r,'supernova_rewrite_docx_r2_url')))
PYEOF
echo "===> Step 4 continuation finished."
