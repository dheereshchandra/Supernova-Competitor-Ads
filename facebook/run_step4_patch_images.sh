#!/usr/bin/env bash
# Patch — run the missing Stage 4.5 (upload frames/panels/sheets to R2,
# write sidecar) and then re-run Stage 8 to populate the URL arrays in master.

cd "$(dirname "$0")"

IDS="1305320435143159 1331000942346730 1561946748353523 919639600763237 1223854759864038 941670845124918 3350647341767877 2696378104080682 1688507795702436 4091989534424274 4339287476329546 1867248917309068 2233023087508211 1272799508356017 1818618209105079 2956993031298495 1732276511091533 1282726410490010 816518274603313 920285514395314"

echo "═══════════════════════════════════════════════════════════════"
echo "Patch — run Stage 4.5 (image uploads) and re-update master"
echo "═══════════════════════════════════════════════════════════════"
date

echo ""
echo "───────── Stage 4.5 — upload images to R2 + write sidecars ─────────"
python3.13 scripts/step4_upload_images.py --competitor learna-ai $IDS

echo ""
echo "───────── Stage 8 (re-run) — back-fill URL arrays in master ─────────"
python3.13 scripts/step4_upload_and_update.py --competitor learna-ai $IDS

echo ""
echo "Verification:"
python3.13 - <<'PY'
import csv, json
top20 = "1305320435143159 1331000942346730 1561946748353523 919639600763237 1223854759864038 941670845124918 3350647341767877 2696378104080682 1688507795702436 4091989534424274 4339287476329546 1867248917309068 2233023087508211 1272799508356017 1818618209105079 2956993031298495 1732276511091533 1282726410490010 816518274603313 920285514395314".split()
with open('master/learna-ai.csv', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))
by_id = {r['ad_library_id']: r for r in rows}
print(f"{'id':<18} {'#orig':>6} {'#gen':>5} {'#char':>6}")
for lid in top20:
    r = by_id.get(lid, {})
    try:
        n_o = len(json.loads(r.get('orig_frame_urls','[]') or '[]'))
        n_g = len(json.loads(r.get('gen_panel_urls','[]') or '[]'))
        n_c = len(json.loads(r.get('char_sheet_urls','[]') or '[]'))
    except Exception:
        n_o = n_g = n_c = -1
    print(f'{lid:<18} {n_o:>6} {n_g:>5} {n_c:>6}')
PY
echo ""
echo "Done."
