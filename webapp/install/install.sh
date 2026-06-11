#!/bin/zsh
# One-time installer for the Supernova Ad Studio backend (macOS launchd, KeepAlive server).
#
# Run ONCE, from your canonical MAIN clone (NOT a Conductor worktree — it has the videos/
# cache, sits on main, and is the single writer the daily sync jobs expect):
#     zsh webapp/install/install.sh
#
# Prereqs (the installer checks and tells you what's missing):
#   • python3.13 + the web deps:  python3.13 -m pip install --break-system-packages --user fastapi "uvicorn[standard]" itsdangerous
#   • the committed frontend build at webapp/frontend/dist/ (built by a developer, committed to git)
#   • .env keys: STUDIO_PASSWORD, STUDIO_SESSION_SECRET (+ the existing R2/Gemini/GDrive keys)
# Cloudflare Tunnel (the public URL) is a SEPARATE one-time step — see webapp/install/README.md.
set -eu

SCRIPT_DIR="${0:A:h}"
REPO="${SCRIPT_DIR:h:h}"
SERVE_SH="$SCRIPT_DIR/serve.sh"
TEMPLATE="$SCRIPT_DIR/live.gosupernova.ad-studio.plist.template"
LABEL="live.gosupernova.ad-studio"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Application Support/SupernovaAdStudio"
LOG="$LOG_DIR/serve.log"

cd "$REPO"

# --- guardrails ---
if [ "$(git rev-parse --git-common-dir 2>/dev/null)" != ".git" ]; then
  if [ "${STUDIO_ALLOW_WORKTREE:-0}" = "1" ]; then
    echo "WARN installing from a git worktree (STUDIO_ALLOW_WORKTREE=1). OK for v0; move to the canonical clone for production."
  else
    echo "ERR this looks like a git worktree, not the canonical clone. Install from your MAIN clone," >&2
    echo "    or re-run with STUDIO_ALLOW_WORKTREE=1 to override for v0 testing." >&2
    exit 1
  fi
fi
command -v python3.13 >/dev/null || { echo "ERR python3.13 not found (brew install python@3.13)"; exit 1; }
python3.13 -c "import fastapi, uvicorn, itsdangerous" 2>/dev/null || {
  echo "ERR web deps missing. Run:"
  echo "  python3.13 -m pip install --break-system-packages --user fastapi \"uvicorn[standard]\" itsdangerous"; exit 1; }
[ -f "$REPO/webapp/frontend/dist/index.html" ] || {
  echo "WARN no built frontend at webapp/frontend/dist/ — the app will only serve the API."
  echo "     A developer should run 'npm run build' in webapp/frontend and commit dist/."; }
grep -q '^STUDIO_PASSWORD=' "$REPO/.env" 2>/dev/null || {
  echo "WARN STUDIO_PASSWORD not set in .env — the app will run with auth DISABLED (open to anyone on the URL)."; }

chmod +x "$SERVE_SH"
mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"
sed -e "s|__SERVE_SH__|$SERVE_SH|g" -e "s|__LOG__|$LOG|g" "$TEMPLATE" > "$PLIST_DEST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"

echo "Installed '$LABEL' — starts now and on login, restarts if it crashes."
echo "  repo: $REPO"
echo "  log:  $LOG"
echo
echo "Check it:  sleep 3 && curl -s localhost:${STUDIO_PORT:-8787}/api/health | head -c 300; echo"
echo "Logs:      tail -f \"$LOG\""
echo "Public URL: set up the Cloudflare tunnel — see webapp/install/README.md"
echo "Remove:    zsh webapp/install/uninstall.sh"
