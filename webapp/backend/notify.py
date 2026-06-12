"""Fire-and-forget operator alerts.

Delegates to tools/notify/notify.sh (macOS banner + Slack when
SLACK_WEBHOOK_URL is set in .env) so the backend and the launchd automation
all alert through ONE shared path. Never raises, never waits — a broken
notifier must never break a job.
"""
from __future__ import annotations

import subprocess

from .config import REPO


def notify(title: str, body: str) -> None:
    try:
        subprocess.Popen(
            ["zsh", str(REPO / "tools" / "notify" / "notify.sh"), title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(REPO),
        )
    except Exception:
        pass
