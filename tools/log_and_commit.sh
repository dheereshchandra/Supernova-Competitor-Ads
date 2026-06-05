#!/usr/bin/env bash
# log_and_commit.sh — run at the END of every pipeline run.
#
# Stamps RUN_LOG.md, writes a per-run links manifest, and commits the small text
# artifacts under your name. Heavy media is excluded automatically by .gitignore.
#
# Usage:
#   tools/log_and_commit.sh <pipeline> <competitor> "<operator name>" "<one-line note>"
# Example:
#   tools/log_and_commit.sh facebook loora "Iniyan" "Steps 2+3; 9 new ads, master 51->60"
#
# Note: the git author/timestamp comes from your own `git config user.name/user.email`
# (set once per machine), so each commit is correctly attributed.
set -euo pipefail

if [ "$#" -lt 4 ]; then
  echo "usage: tools/log_and_commit.sh <pipeline> <competitor> \"<operator>\" \"<note>\"" >&2
  exit 2
fi
PIPELINE="$1"; COMPETITOR="$2"; OPERATOR="$3"; NOTE="$4"
case "$PIPELINE" in facebook|google) ;; *) echo "pipeline must be 'facebook' or 'google'" >&2; exit 2 ;; esac

# Repo root = parent of this script's directory
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DATE="$(date +%F)"
STAMP="$(date +"%Y-%m-%d %H:%M %Z")"
RUNS_DIR="$PIPELINE/runs"
MANIFEST="$RUNS_DIR/${COMPETITOR}_${DATE}_links.json"
mkdir -p "$RUNS_DIR"

# 1) Build the per-run links manifest from the master + r2_urls.json sidecars.
python3 - "$PIPELINE" "$COMPETITOR" "$MANIFEST" <<'PY'
import csv, json, sys, pathlib
csv.field_size_limit(10 ** 9)
pipeline, competitor, manifest = sys.argv[1], sys.argv[2], sys.argv[3]
root = pathlib.Path(".")
master = root / pipeline / "master" / f"{competitor}.csv"
DOC_COLS = ["competitor_analysis_docx_r2_url", "supernova_rewrite_docx_r2_url"]
ARRAY_COLS = ["orig_frame_urls", "gen_panel_urls", "char_sheet_urls",
              "competitor_analysis_image_r2_urls", "supernova_rewrite_image_r2_urls"]
links = {"source_assets": set(), "docs": set(), "images": set()}
rows = 0
if master.exists():
    with master.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            rows += 1
            u = (r.get("r2_public_url") or "").strip()
            if u.startswith("http"):
                links["source_assets"].add(u)
            for c in DOC_COLS:
                u = (r.get(c) or "").strip()
                if u.startswith("http"):
                    links["docs"].add(u)
            for c in ARRAY_COLS:
                raw = (r.get(c) or "").strip()
                if raw.startswith("["):
                    try:
                        for u in json.loads(raw):
                            if isinstance(u, str) and u.startswith("http"):
                                links["images"].add(u)
                    except json.JSONDecodeError:
                        pass
# sweep the per-image r2_urls.json sidecars (kept in git)
sidecar_root = root / pipeline / "step4_workspace" / "images"
if sidecar_root.exists():
    for p in sidecar_root.glob("*/r2_urls.json"):
        try:
            d = json.loads(p.read_text())
            vals = d.values() if isinstance(d, dict) else d
            for v in vals:
                if isinstance(v, str) and v.startswith("http"):
                    links["images"].add(v)
        except Exception:
            pass
out = {"pipeline": pipeline, "competitor": competitor, "master_rows": rows,
       "counts": {k: len(v) for k, v in links.items()},
       "source_assets": sorted(links["source_assets"]),
       "docs": sorted(links["docs"]), "images": sorted(links["images"])}
pathlib.Path(manifest).write_text(json.dumps(out, indent=2))
print(f"[manifest] {manifest}: {out['counts']}")
PY

# 2) Prepend a RUN_LOG entry (newest first), just after the insert marker.
ENTRY="## ${STAMP} — ${PIPELINE} / ${COMPETITOR} — operator: ${OPERATOR}
- ${NOTE}
- Links manifest: ${MANIFEST}
"
MARK="<!-- New entries are inserted below this line, newest first. -->"
awk -v entry="$ENTRY" -v mark="$MARK" '
  { print }
  $0 == mark && !done { print ""; printf "%s", entry; done = 1 }
' RUN_LOG.md > RUN_LOG.md.tmp && mv RUN_LOG.md.tmp RUN_LOG.md

# 3) Stage the small text artifacts and commit under the operator.
git add "$PIPELINE/master/${COMPETITOR}.csv" 2>/dev/null || true
git add "$PIPELINE"/inputs/*"$COMPETITOR"* 2>/dev/null || true
git add "$RUNS_DIR"/* 2>/dev/null || true
git add "$PIPELINE"/step3_logs/*"$COMPETITOR"* 2>/dev/null || true
git add "$PIPELINE"/step4_workspace/images/*/r2_urls.json 2>/dev/null || true
git add "$PIPELINE"/step4_workspace/scenes/*.json 2>/dev/null || true
git add RUN_LOG.md 2>/dev/null || true

if git commit -m "run: ${PIPELINE}/${COMPETITOR} by ${OPERATOR} — ${NOTE}"; then
  echo "[ok] committed. Now run:  git push"
else
  echo "[git] nothing new to commit."
fi
