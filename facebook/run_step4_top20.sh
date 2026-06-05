#!/usr/bin/env bash
# Step 4 — run all 8 stages on Learna-AI top-20 by row_rank.
# IDs are baked in. Pollers loop with 60s sleep. Safe to Ctrl+C and re-run.
# Every stage is idempotent — re-running picks up where it died.
set -e

cd "$(dirname "$0")"

IDS="1305320435143159 1331000942346730 1561946748353523 919639600763237 1223854759864038 941670845124918 3350647341767877 2696378104080682 1688507795702436 4091989534424274 4339287476329546 1867248917309068 2233023087508211 1272799508356017 1818618209105079 2956993031298495 1732276511091533 1282726410490010 816518274603313 920285514395314"

LOG_DIR=step4_workspace/run_logs
mkdir -p "$LOG_DIR"
STAMP=$(date +%Y-%m-%d-%H%M%S)

echo "═══════════════════════════════════════════════════════════════"
echo "Step 4 — Learna-AI top 20 by row_rank (~\$11.83 est.)"
echo "═══════════════════════════════════════════════════════════════"
date

echo ""
echo "───────── Stage 1a — upload videos to Gemini Files API ─────────"
python3.13 scripts/step4_decompose.py upload --competitor learna-ai $IDS

echo ""
echo "───────── Stage 1b — submit decompose batch ─────────"
SUBMIT_OUT="$LOG_DIR/decompose_submit_${STAMP}.txt"
python3.13 scripts/step4_decompose.py submit --competitor learna-ai $IDS | tee "$SUBMIT_OUT"
DECOMPOSE_SHORT=$(grep -E "short id:" "$SUBMIT_OUT" | head -1 | awk '{print $NF}')
if [ -z "$DECOMPOSE_SHORT" ]; then
    echo "[error] Could not capture decompose short_id from submit output."
    exit 1
fi
echo "[ok] decompose short_id: $DECOMPOSE_SHORT"

echo ""
echo "───────── Stage 1c — poll decompose batch (60s interval) ─────────"
echo "This typically takes 10–40 min. Ctrl+C is safe; re-running this script resumes."
while true; do
    OUT=$(python3.13 scripts/step4_decompose.py poll "$DECOMPOSE_SHORT" 2>&1)
    echo "$OUT" | tail -3
    if echo "$OUT" | grep -q "DONE"; then
        echo "[ok] decompose batch DONE"
        break
    fi
    if echo "$OUT" | grep -qE "FAILED|EXPIRED|CANCELLED"; then
        echo "[error] decompose batch failed:"
        echo "$OUT"
        exit 2
    fi
    echo "  ...still waiting, sleeping 60s"
    sleep 60
done

echo ""
echo "───────── Stage 2 — extract frames (ffmpeg, instant) ─────────"
python3.13 scripts/step4_frames.py --competitor learna-ai $IDS

echo ""
echo "───────── Stage 3 — character reference sheets (Nano Banana Pro) ─────────"
for attempt in 1 2 3 4 5; do
    echo "[attempt $attempt]"
    OUT=$(python3.13 scripts/step4_character_sheets.py --competitor learna-ai $IDS 2>&1)
    echo "$OUT" | tail -5
    if echo "$OUT" | grep -qE "all .* sheets present|status clear|nothing to do"; then
        break
    fi
done

echo ""
echo "───────── Stage 4 — clean panel imagery (Nano Banana Pro) ─────────"
for attempt in 1 2 3 4 5 6 7 8; do
    echo "[attempt $attempt]"
    OUT=$(python3.13 scripts/step4_panels.py --competitor learna-ai $IDS 2>&1)
    echo "$OUT" | tail -5
    if echo "$OUT" | grep -qE "all .* panels present|status clear|nothing to do"; then
        break
    fi
done

echo ""
echo "───────── Stage 5a — submit Supernova rewrite batch ─────────"
REWRITE_OUT="$LOG_DIR/rewrite_submit_${STAMP}.txt"
python3.13 scripts/step4_rewrite.py submit --competitor learna-ai $IDS | tee "$REWRITE_OUT"
REWRITE_SHORT=$(grep -E "short id:" "$REWRITE_OUT" | head -1 | awk '{print $NF}')
if [ -z "$REWRITE_SHORT" ]; then
    echo "[error] Could not capture rewrite short_id from submit output."
    exit 1
fi
echo "[ok] rewrite short_id: $REWRITE_SHORT"

echo ""
echo "───────── Stage 5b — poll rewrite batch (30s interval) ─────────"
echo "Typically 3–5 min."
while true; do
    OUT=$(python3.13 scripts/step4_rewrite.py poll "$REWRITE_SHORT" 2>&1)
    echo "$OUT" | tail -3
    if echo "$OUT" | grep -q "DONE"; then
        echo "[ok] rewrite batch DONE"
        break
    fi
    if echo "$OUT" | grep -qE "FAILED|EXPIRED|CANCELLED"; then
        echo "[error] rewrite batch failed:"
        echo "$OUT"
        exit 2
    fi
    echo "  ...still waiting, sleeping 30s"
    sleep 30
done

echo ""
echo "───────── Stage 6 — build docx files ─────────"
python3.13 scripts/step4_build_docs.py --competitor learna-ai $IDS

echo ""
echo "───────── Stage 7+8 — upload docs to R2, back-fill master CSV ─────────"
python3.13 scripts/step4_upload_and_update.py --competitor learna-ai $IDS

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "Step 4 COMPLETE."
echo "═══════════════════════════════════════════════════════════════"
date
echo ""
echo "Final verification:"
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
echo "Done. Open master/learna-ai.csv to inspect."
