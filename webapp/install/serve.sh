#!/bin/zsh
# Launches the Ad Studio backend (uvicorn). Invoked by launchd (KeepAlive), so it
# must set the Homebrew PATH itself — launchd gives processes a minimal PATH that
# lacks /opt/homebrew/bin (python3.13, ffmpeg, git, cloudflared all live there).
#
# Runs from the CANONICAL clone only. The 11:30 git pull refreshes that checkout's
# main; the backend re-reads the CSVs by mtime, so data stays current with no restart.
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

REPO="${0:A:h:h:h}"   # webapp/install/serve.sh -> repo root
cd "$REPO" || exit 1

# --- preflight: refuse to run from a Conductor worktree (no videos/, wrong branch) ---
if [ "$(git rev-parse --git-common-dir 2>/dev/null)" != ".git" ]; then
  echo "[ad-studio] REFUSING: this is a git worktree, not the canonical clone. Run from the main clone." >&2
  exit 1
fi

PORT="${STUDIO_PORT:-8787}"
echo "[ad-studio] starting on 127.0.0.1:$PORT from $REPO ($(git symbolic-ref --short HEAD 2>/dev/null))"

# caffeinate keeps the Mac awake while serving (so the team's URL stays up); -s only
# prevents idle sleep on AC power. Harmless if already prevented via pmset.
exec caffeinate -s python3.13 -m uvicorn webapp.backend.app:app \
  --host 127.0.0.1 --port "$PORT" --log-level info
