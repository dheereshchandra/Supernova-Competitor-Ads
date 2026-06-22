"""Translations playground API — an ad-hoc, REAL-TIME (synchronous) translation workbench.

Distinct from the per-ad localize JOB (api_jobs.py): nothing here touches the jobs table,
tracker, Google Docs, R2, or the step4 sidecars. Each request shells synchronously into a
`--playground` mode of the step4 scripts (the same subprocess pattern as /api/tts/setup) and
returns the result in one round-trip — NOT the async job queue, NOT the Gemini Batch API.

Endpoints (all require a signed-in user):
  GET  /api/translate/prompts          default Script + TTS prompt text (for the editable boxes)
  POST /api/translate/script           pasted source -> per-language Romanized + native (Gemini Flash)
  POST /api/translate/native           re-transliterate edited Romanized -> native (Gemini 2.5 Pro)
  POST /api/translate/tts              synth one native block -> mp3 (Cartesia/ElevenLabs narrator)
  GET  /api/translate/audio/{token}    serve a freshly-synthesized mp3
"""
from __future__ import annotations

import json
import secrets
import subprocess
import threading
import time
from collections import deque, defaultdict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .auth import require_user
from .config import FACEBOOK_DIR, STATE_DIR

router = APIRouter()

# Per-section model defaults (the team opted Gemini 2.5 Pro into the TTS section only; the Pro
# escape hatch in analysis/scripts/_flash.py fires for any model id containing "pro").
SCRIPT_DEFAULT_MODEL = "gemini-flash-latest"
TTS_DEFAULT_MODEL = "gemini-2.5-pro"

RULES_PATH = FACEBOOK_DIR / "generation" / "supernova_translation_rules.md"
AUDIO_DIR = STATE_DIR / "translations"
_AUDIO_TTL = 3600          # delete synthesized mp3s older than 1h
_MAX_TARGETS = 8
_RUN_TIMEOUT = 180         # seconds per subprocess (a fan-out of up to 8 Flash calls)

# Mirrors facebook/scripts/_tts_text.py::native_instruction (kept in sync — it's only the editing
# starting point; the real default is applied server-side when the box is left untouched).
DEFAULT_TTS_PROMPT = (
    "You convert romanized <your target language> ad-script lines into the SAME language written "
    "in its NATIVE SCRIPT, for a text-to-speech engine.\n\n"
    "RULES:\n"
    "- Transliterate the romanized words into correct native script. This is transliteration into "
    "proper spelling, NOT translation — keep the SAME words.\n"
    "- Keep English words in Latin script (code-mix), and keep numbers, 'Supernova AI', 'Miss Nova' "
    "and proper nouns exactly as written.\n"
    "- Do NOT add, drop, reorder, or paraphrase words. Exactly one output line per input line.\n"
    "- It will be read aloud, so spell native words the natural, correct way."
)


# ---------------- lightweight per-user throttle (abuse guard; this path has no job cost cap) ----
_BUCKET: dict[str, deque] = defaultdict(deque)
_BUCKET_LOCK = threading.Lock()
_RATE_MAX, _RATE_WINDOW = 40, 60     # ≤40 generate/synth calls per user per minute


def _throttle(user: str) -> None:
    now = time.monotonic()
    with _BUCKET_LOCK:
        q = _BUCKET[user]
        while q and now - q[0] > _RATE_WINDOW:
            q.popleft()
        if len(q) >= _RATE_MAX:
            raise HTTPException(429, "Too many translation requests — wait a moment.")
        q.append(now)


# ---------------- subprocess helper ----------------
def _run_playground(script: str, args: list[str], body: dict) -> dict:
    """Run a step4 --playground mode synchronously, piping `body` as JSON stdin, parse stdout JSON."""
    try:
        proc = subprocess.run(
            ["python3.13", f"scripts/{script}", *args],
            cwd=FACEBOOK_DIR, input=json.dumps(body), capture_output=True,
            text=True, timeout=_RUN_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Translation timed out — try fewer languages or a shorter script.")
    out = proc.stdout or ""
    brace = out.find("{")
    if brace < 0:
        detail = (proc.stderr or out or "no output").strip()[-400:]
        raise HTTPException(502, f"Translation backend error: {detail}")
    try:
        return json.loads(out[brace:])
    except json.JSONDecodeError:
        raise HTTPException(502, "Translation backend returned malformed output.")


def _sweep_audio() -> None:
    if not AUDIO_DIR.is_dir():
        return
    cutoff = time.time() - _AUDIO_TTL
    for f in AUDIO_DIR.glob("*.mp3"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


# ---------------- request models ----------------
class ScriptBody(BaseModel):
    source_text: str = Field(min_length=1, max_length=20_000)
    source_language: str = Field(min_length=1, max_length=40)
    target_languages: list[str] = Field(min_length=1, max_length=_MAX_TARGETS)
    model: str = SCRIPT_DEFAULT_MODEL
    rules_override: str | None = Field(default=None, max_length=200_000)


class NativeBody(BaseModel):
    language: str = Field(min_length=1, max_length=40)
    roman: str = Field(min_length=1, max_length=20_000)
    model: str = TTS_DEFAULT_MODEL
    prompt_override: str | None = Field(default=None, max_length=20_000)


class TtsBody(BaseModel):
    language: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=8_000)
    voice_id: str | None = Field(default=None, max_length=80)


# ---------------- endpoints ----------------
@router.get("/api/translate/prompts")
def translate_prompts(_user: str = Depends(require_user)):
    """The default Script (translation rules) + TTS (transliteration) prompt text, for the
    editable prompt boxes. The rules doc is read live so the UI never drifts from the real prompt."""
    try:
        script = RULES_PATH.read_text()
    except OSError:
        script = ""
    return {"script": script, "tts": DEFAULT_TTS_PROMPT}


@router.post("/api/translate/script")
def translate_script(body: ScriptBody, user: str = Depends(require_user)):
    """Translate the pasted source into per-language Romanized + native code-mix (real-time)."""
    _throttle(user)
    res = _run_playground("step4_localize.py", ["--playground"], {
        "source_text": body.source_text,
        "source_language": body.source_language,
        "target_languages": body.target_languages,
        "model": (body.model or SCRIPT_DEFAULT_MODEL).strip(),
        "rules_override": body.rules_override or None,
    })
    return res


@router.post("/api/translate/native")
def translate_native(body: NativeBody, user: str = Depends(require_user)):
    """Transliterate the (edited) Romanized text into native script (real-time)."""
    _throttle(user)
    res = _run_playground("step4_tts.py", ["--playground-native"], {
        "language": body.language,
        "roman": body.roman,
        "model": (body.model or TTS_DEFAULT_MODEL).strip(),
        "prompt_override": body.prompt_override or None,
    })
    return res


@router.post("/api/translate/tts")
def translate_tts(body: TtsBody, user: str = Depends(require_user)):
    """Synthesize one native-script block to audio with the default narrator voice (real-time)."""
    _throttle(user)
    _sweep_audio()
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(16)
    out_path = AUDIO_DIR / f"{token}.mp3"
    res = _run_playground("step4_tts.py", ["--playground-synth", "--out", str(out_path)], {
        "language": body.language, "text": body.text,
        "voice_id": body.voice_id or "",
    })
    if not res.get("ok") or not out_path.is_file():
        raise HTTPException(502, f"TTS failed: {res.get('error', 'unknown error')}")
    return {"audio_url": f"/api/translate/audio/{token}",
            "provider": res.get("provider"), "voice_id": res.get("voice_id")}


@router.get("/api/translate/audio/{token}")
def translate_audio(token: str, _user: str = Depends(require_user)):
    """Serve a synthesized mp3 (token is a 32-char hex; reject anything else)."""
    if not token.isalnum() or len(token) != 32:
        raise HTTPException(404, "Not found")
    f = AUDIO_DIR / f"{token}.mp3"
    if not f.is_file():
        raise HTTPException(404, "Audio expired or not found")
    return FileResponse(f, media_type="audio/mpeg")
