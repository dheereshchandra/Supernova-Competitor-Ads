#!/bin/zsh
# One-time installer for the WEEKLY Google FREE refresh (Monday 12:00 by default).
# Run ONCE from your canonical MAIN clone (NOT a Conductor worktree — single writer):
#     zsh tools/google-weekly-scrape/install.sh
set -eu

SCRIPT_DIR="${0:A:h}"
REPO="${SCRIPT_DIR:h:h}"
SCRAPE_SH="$SCRIPT_DIR/scrape.sh"
TEMPLATE="$SCRIPT_DIR/live.gosupernova.google-weekly-scrape.plist.template"
LABEL="live.gosupernova.google-weekly-scrape"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Application Support/SupernovaGoogleWeekly/scrape.log"

cd "$REPO"
if [ "$(git rev-parse --git-common-dir 2>/dev/null)" != ".git" ]; then
  echo "ERR install from your canonical MAIN clone, not a worktree." >&2; exit 1
fi
command -v python3.13 >/dev/null || { echo "ERR python3.13 missing"; exit 1; }
[ -f "$SCRAPE_SH" ]  || { echo "ERR $SCRAPE_SH not found (merge the PR + pull first)"; exit 1; }

chmod +x "$SCRAPE_SH"
mkdir -p "$(dirname "$LOG")" "$HOME/Library/LaunchAgents"
sed -e "s|__SCRAPE_SH__|$SCRAPE_SH|g" -e "s|__LOG__|$LOG|g" "$TEMPLATE" > "$PLIST_DEST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"

echo "Installed '$LABEL' — runs the FREE Google refresh WEEKLY on Monday 12:00 for the competitors in"
echo "  tools/google-weekly-scrape/competitors.txt"
echo "  log: $LOG"
echo
echo "⚠ The scrape needs your VPN / fresh IP active at run time, or Google 429-blocks every"
echo "  competitor (blocked ones are skipped, not retried — a bad-IP week just fails cleanly)."
echo "⚠ A full round throttles ~30 min/competitor (≈4-5 h). Lower it with GOOGLE_SCRAPE_THROTTLE."
echo
echo "IMPORTANT — the Mac must be awake at the scheduled time (or it runs on the next wake, once/week)."
echo "Change time/day: edit Weekday/Hour/Minute in the .plist.template and re-run this installer."
echo
echo "Test it now (REAL scrape of ALL competitors — long!):  launchctl kickstart -k gui/$(id -u)/$LABEL && tail -f \"$LOG\""
echo "Remove later:  zsh tools/google-weekly-scrape/uninstall.sh"
