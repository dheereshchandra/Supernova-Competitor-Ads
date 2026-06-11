#!/bin/zsh
# Installer for the durable Facebook pipeline runner (macOS launchd LaunchAgent).
#
# INSTALL (on-demand runner): run ONCE from your MAIN clone (NOT a Conductor worktree):
#     zsh tools/pipeline-run/install.sh
# It renders ~/Library/LaunchAgents/live.gosupernova.pipeline-run.plist from the
# template (absolute paths for THIS clone) and loads it. ON-DEMAND ONLY — there is NO
# daily schedule; it runs when you TRIGGER it (below), and auto-resumes on crash via
# KeepAlive{SuccessfulExit:false}. Safe to re-run.
#
# RUN / RESUME (detached, survives the session dying) — e.g. from a UX "run" button:
#     launchctl kickstart -k gui/$(id -u)/live.gosupernova.pipeline-run
# WATCH:   bash tools/pipeline-run/status.sh
# STOP a run:  launchctl kill TERM gid; or zsh tools/pipeline-run/uninstall.sh
#
# NOTE: whichever clone you install from is the one the runner uses — install from
# the clone whose `main` you want driven (single writer, like the other launchd jobs).
set -eu

SCRIPT_DIR="${0:A:h}"
RUN_BATCH="$SCRIPT_DIR/run_batch.sh"
TEMPLATE="$SCRIPT_DIR/live.gosupernova.pipeline-run.plist.template"
LABEL="live.gosupernova.pipeline-run"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Application Support/SupernovaPipelineRun"
LOG="$LOG_DIR/pipeline-run.log"

[ -f "$RUN_BATCH" ] || { echo "ERR missing $RUN_BATCH"; exit 1; }
[ -f "$TEMPLATE" ]  || { echo "ERR missing $TEMPLATE"; exit 1; }

chmod +x "$RUN_BATCH" "$SCRIPT_DIR/status.sh" "$SCRIPT_DIR/uninstall.sh" 2>/dev/null || true
mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

sed -e "s|__RUN_BATCH__|$RUN_BATCH|g" -e "s|__LOG__|$LOG|g" "$TEMPLATE" > "$PLIST_DEST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"

echo "Installed '$LABEL' — ON-DEMAND only (no daily schedule; auto-resume on crash)."
echo "  repo:   ${SCRIPT_DIR:h:h}"
echo "  runner: $RUN_BATCH"
echo "  log:    $LOG   (+ per-day repo log under analysis/logs/)"
echo
echo "Run it NOW (detached, survives session death):"
echo "  launchctl kickstart -k gui/$(id -u)/$LABEL"
echo "Watch:   bash tools/pipeline-run/status.sh"
echo "Remove:  zsh tools/pipeline-run/uninstall.sh"
