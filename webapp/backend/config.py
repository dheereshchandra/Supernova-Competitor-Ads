"""Ad Studio configuration: repo paths + merged .env loading.

The .env loader is a port of tools/rehydrate.py:load_env — merges keys from
every common .env location (root, facebook/, google/), first-found wins, and
strips straight + curly quotes (Mac smart-quotes break API keys).
"""
from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
FACEBOOK_DIR = REPO / "facebook"
GOOGLE_DIR = REPO / "google"
ANALYSIS_DIR = REPO / "analysis"
STATE_DIR = REPO / "webapp" / "state"
FRONTEND_DIST = REPO / "webapp" / "frontend" / "dist"

# straight + curly quotes — strip any that wrap a .env value
_QUOTES = "".join(chr(c) for c in (0x22, 0x27, 0x2018, 0x2019, 0x201C, 0x201D))

# Keys the pipeline needs end-to-end; /api/health reports presence (never values).
PIPELINE_ENV_KEYS = (
    "R2_S3_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET", "R2_PUBLIC_URL_BASE", "GEMINI_API_KEY",
    "GOOGLE_SERVICE_ACCOUNT_JSON", "GDRIVE_SHARED_DRIVE_ID",
)
STUDIO_ENV_KEYS = ("STUDIO_PASSWORD", "STUDIO_SESSION_SECRET")


def load_env() -> dict:
    env: dict = {}
    for p in (REPO / ".env", FACEBOOK_DIR / ".env", GOOGLE_DIR / ".env"):
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    if k not in env:  # earlier files win
                        env[k] = v.strip().strip(_QUOTES)
    return env


class Settings:
    """Lazily-loaded settings snapshot. Re-instantiate to pick up .env edits."""

    def __init__(self) -> None:
        self.env = load_env()
        self.port = int(self.env.get("STUDIO_PORT", "8787"))
        self.password = self.env.get("STUDIO_PASSWORD", "")
        self.session_secret = self.env.get("STUDIO_SESSION_SECRET", "")
        # Spend guardrails (USD). Estimates come from estimate_step4_cost.py.
        self.max_job_cost = float(self.env.get("STUDIO_MAX_JOB_COST", "5"))
        self.max_daily_cost = float(self.env.get("STUDIO_MAX_DAILY_COST", "15"))
        # No job may START inside this local-time window — it protects the
        # 11:30 repo-sync / 11:35 capture-sync / 11:45 csv-sync launchd jobs
        # from seeing a dirty tree (jobs run up to ~20 min).
        self.blackout = (self.env.get("STUDIO_BLACKOUT", "11:05-11:55"))

    @property
    def auth_enabled(self) -> bool:
        return bool(self.password)

    def key_presence(self) -> dict:
        return {k: bool(self.env.get(k)) for k in PIPELINE_ENV_KEYS + STUDIO_ENV_KEYS}


_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
