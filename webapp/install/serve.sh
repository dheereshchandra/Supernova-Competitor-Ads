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

# Read the worktree override from .env too (launchd doesn't inherit shell env).
if grep -q '^STUDIO_ALLOW_WORKTREE=1' "$REPO/.env" 2>/dev/null; then
  export STUDIO_ALLOW_WORKTREE=1
fi

# --- preflight: prefer the canonical clone (no videos/, wrong branch in a worktree).
# STUDIO_ALLOW_WORKTREE=1 overrides for v0 testing from a Conductor worktree. ---
if [ "$(git rev-parse --git-common-dir 2>/dev/null)" != ".git" ]; then
  if [ "${STUDIO_ALLOW_WORKTREE:-0}" = "1" ]; then
    echo "[ad-studio] WARNING: running from a git worktree (STUDIO_ALLOW_WORKTREE=1). Fine for v0 testing; move to the canonical clone for production." >&2
  else
    echo "[ad-studio] REFUSING: this is a git worktree, not the canonical clone. Run from the main clone, or set STUDIO_ALLOW_WORKTREE=1 to override." >&2
    exit 1
  fi
fi

PORT="${STUDIO_PORT:-8787}"
echo "[ad-studio] starting on 127.0.0.1:$PORT from $REPO ($(git symbolic-ref --short HEAD 2>/dev/null))"

# caffeinate keeps the Mac awake while serving (so the team's URL stays up); -s only
# prevents idle sleep on AC power. Harmless if already prevented via pmset.
exec caffeinate -s python3.13 -m uvicorn webapp.backend.app:app \
  --host 127.0.0.1 --port "$PORT" --log-level info
