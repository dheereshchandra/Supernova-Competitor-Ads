#!/usr/bin/env bash
# Step 4 continuation — picks up after Stage 1b (batch already submitted).
# decompose short_id: 31fy8n8dugiowgxx
# Fixed: set -e disabled around poll loops so PENDING (rc=1) doesn't kill us.
#
# Safe to Ctrl+C and re-run. All stages are idempotent.

cd "$(dirname "$0")"

DECOMPOSE_SHORT="31fy8n8dugiowgxx"
IDS="1305320435143159 1331000942346730 1561946748353523 919639600763237 1223854759864038 941670845124918 3350647341767877 2696378104080682 1688507795702436 4091989534424274 4339287476329546 1867248917309068 2233023087508211 1272799508356017 1818618209105079 2956993031298495 1732276511091533 1282726410490010 816518274603313 920285514395314"

LOG_DIR=step4_workspace/run_logs
mkdir -p "$LOG_DIR"
STAMP=$(date +%Y-%m-%d-%H%M%S)

echo "═══════════════════════════════════════════════════════════════"
echo "Step 4 CONTINUE — Learna-AI top 20 (decompose batch already in flight)"
echo "═══════════════════════════════════════════════════════════════"
date

# ── helper: poll loop without set -e killing us on rc=1 (PENDING)
poll_until_done() {
    local script="$1"
    local short="$2"
    local sleep_s="$3"
    local stage_name="$4"

    echo ""
    echo "───────── Polling $stage_name (every ${sleep_s}s, short_id $short) ─────────"
    while true; do
        OUT=$(python3.13 "$script" poll "$short" 2>&1)
        echo "$OUT" | tail -3
        if echo "$OUT" | grep -q "DONE"; then
            echo "[ok] $stage_name DONE"
            return 0
        fi
        if echo "$OUT" | grep -qE "TERMINAL FAILURE|FAILED|EXPIRED|CANCELLED"; then
            echo "[error] $stage_name failed:"
            echo "$OUT"
            return 2
        fi
        echo "  ...still waiting, sleeping ${sleep_s}s"
        sleep "$sleep_s"
    done
}

poll_until_done scripts/step4_decompose.py "$DECOMPOSE_SHORT" 60 "decompose batch" || exit 2

echo ""
echo "───────── Stage 2 — extract frames (ffmpeg, instant) ─────────"
python3.13 scripts/step4_frames.py --competitor learna-ai $IDS || { echo "[error] frames failed"; exit 3; }

echo ""
echo "───────── Stage 3 — character reference sheets (Nano Banana Pro) ─────────"
for attempt in 1 2 3 4 5 6; do
    echo "[attempt $attempt]"
    OUT=$(python3.13 scripts/step4_character_sheets.py --competitor learna-ai $IDS 2>&1)
    echo "$OUT" | tail -5
    if echo "$OUT" | grep -qE "all .* sheets present|status clear|nothing to do|0 still missing"; then
        break
    fi
    sleep 5
done

echo ""
echo "───────── Stage 4 — clean panel imagery (Nano Banana Pro) ─────────"
for attempt in 1 2 3 4 5 6 7 8 9 10; do
    echo "[attempt $attempt]"
    OUT=$(python3.13 scripts/step4_panels.py --competitor learna-ai $IDS 2>&1)
    echo "$OUT" | tail -5
    if echo "$OUT" | grep -qE "all .* panels present|status clear|nothing to do|0 still missing"; then
        break
    fi
    sleep 5
done

echo ""
echo "───────── Stage 5a — submit Supernova rewrite batch ─────────"
REWRITE_OUT="$LOG_DIR/rewrite_submit_${STAMP}.txt"
python3.13 scripts/step4_rewrite.py submit --competitor learna-ai $IDS | tee "$REWRITE_OUT"
REWRITE_SHORT=$(grep -E "short id:" "$REWRITE_OUT" | head -1 | awk '{print $NF}')
if [ -z "$REWRITE_SHORT" ]; then
    echo "[error] Could not capture rewrite short_id."
    exit 4
fi
echo "[ok] rewrite short_id: $REWRITE_SHORT"

poll_until_done scripts/step4_rewrite.py "$REWRITE_SHORT" 30 "rewrite batch" || exit 5

echo ""
echo "───────── Stage 6 — build docx files ─────────"
python3.13 scripts/step4_build_docs.py --competitor learna-ai $IDS || { echo "[error] build_docs failed"; exit 6; }

echo ""
echo "───────── Stage 7+8 — upload docs to R2, back-fill master CSV ─────────"
python3.13 scripts/step4_upload_and_update.py --competitor learna-ai $IDS || { echo "[error] upload_and_update failed"; exit 7; }

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
echo "Done. Open master/learna-ai.csv to inspect, or check the docs at the R2 URLs."
