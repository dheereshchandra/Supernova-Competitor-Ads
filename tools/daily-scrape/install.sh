#!/bin/zsh
# One-time installer for the daily 6 AM FREE Facebook refresh (stages 1-4).
# Run ONCE from your canonical MAIN clone (NOT a Conductor worktree — single writer):
#     zsh tools/daily-scrape/install.sh
set -eu

SCRIPT_DIR="${0:A:h}"
REPO="${SCRIPT_DIR:h:h}"
SCRAPE_SH="$SCRIPT_DIR/scrape.sh"
TEMPLATE="$SCRIPT_DIR/live.gosupernova.daily-scrape.plist.template"
LABEL="live.gosupernova.daily-scrape"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Application Support/SupernovaDailyScrape/scrape.log"

cd "$REPO"
if [ "$(git rev-parse --git-common-dir 2>/dev/null)" != ".git" ]; then
  echo "ERR install from your canonical MAIN clone, not a worktree." >&2; exit 1
fi
command -v python3.13 >/dev/null || { echo "ERR python3.13 missing"; exit 1; }
python3.13 -c "import playwright" 2>/dev/null || echo "WARN playwright missing — the FB scraper needs it (python3.13 -m playwright install chromium)"

chmod +x "$SCRAPE_SH"
mkdir -p "$(dirname "$LOG")" "$HOME/Library/LaunchAgents"
sed -e "s|__SCRAPE_SH__|$SCRAPE_SH|g" -e "s|__LOG__|$LOG|g" "$TEMPLATE" > "$PLIST_DEST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"

echo "Installed '$LABEL' — runs the FREE refresh daily at 06:00 for the competitors in"
echo "  tools/daily-scrape/competitors.txt"
echo "  log: $LOG"
echo
echo "IMPORTANT — the Mac must be awake at 6 AM for it to run on time. Two options:"
echo "  • keep it plugged in and let it wake itself:  sudo pmset repeat wakeorpoweron MTWRFSU 05:58:00"
echo "  • or do nothing — if it's asleep at 6 AM, the job runs the next time you wake it (once/day)."
echo
echo "Test it now (real scrape, ~free):  launchctl kickstart -k gui/$(id -u)/$LABEL && tail -f \"$LOG\""
echo "Remove later:  zsh tools/daily-scrape/uninstall.sh"
