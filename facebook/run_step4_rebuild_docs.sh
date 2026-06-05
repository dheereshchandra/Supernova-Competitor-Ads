#!/usr/bin/env bash
# Rebuild docs (now that Stage 4.5 sidecars exist) and re-upload to R2.
# The placeholder "Asset: [missing — Stage 4.5 not run]" in old docs gets
# replaced by the proper R2 image references.

cd "$(dirname "$0")"

IDS="1305320435143159 1331000942346730 1561946748353523 919639600763237 1223854759864038 941670845124918 3350647341767877 2696378104080682 1688507795702436 4091989534424274 4339287476329546 1867248917309068 2233023087508211 1272799508356017 1818618209105079 2956993031298495 1282726410490010 816518274603313 920285514395314"

echo "═══════════════════════════════════════════════════════════════"
echo "Rebuild docs with image refs + re-upload"
echo "═══════════════════════════════════════════════════════════════"
date

echo ""
echo "───────── Re-running Stage 6 — build docx files ─────────"
python3.13 scripts/step4_build_docs.py --competitor learna-ai $IDS

echo ""
echo "───────── Re-running Stage 7+8 — upload + master back-fill ─────────"
python3.13 scripts/step4_upload_and_update.py --competitor learna-ai $IDS

echo ""
echo "Done. R2 URLs are the same keys so the old docs are overwritten."
echo "Open one of the docx files to verify the 'Asset:' lines now show real URLs."
