"""
_flash.py — shared Gemini **Flash** helper for the analysis enrichment scripts.

HARD RULE: this project uses Gemini **Flash only, never Pro** (cost control).
Default model is a Flash alias; override with --model if your key needs a
specific Flash version, but never point it at a Pro model.

Mirrors the working pattern in facebook/scripts/step4_decompose.py:
  from google import genai
  client = genai.Client(api_key=...)
  client.models.generate_content(model=..., contents=..., config=...)
The google-genai SDK and a GEMINI_API_KEY (.env) are required — these live on
the operator's Mac, not in the sandbox.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

# Flash only. (`-latest` is a stable alias; set --model if your key needs an
# explicit Flash version like gemini-2.5-flash.)
DEFAULT_MODEL = "gemini-flash-latest"

_PRO_GUARD = ("pro",)  # refuse obvious Pro models so the cost rule can't be bypassed


def assert_flash(model: str) -> None:
    low = model.lower()
    if any(tok in low for tok in _PRO_GUARD):
        raise SystemExit(
            f"[error] model '{model}' looks like a Pro model. This project is "
            f"Flash-only (cost rule). Use a Flash model.")


# straight + curly quotes — strip any that wrap a value (Macs auto-insert curly
# "smart quotes" when keys are pasted from Notes/Docs/chat, which corrupts headers)
_QUOTES = "".join(chr(c) for c in (0x22, 0x27, 0x2018, 0x2019, 0x201c, 0x201d))


def load_env(*candidates: Path) -> dict:
    """Read the first .env found among the candidate paths (key=value lines)."""
    for p in candidates:
        if p and p.is_file():
            env = {}
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip(_QUOTES)
            if env:
                return env
    return {}


def find_env(root: Path, pipeline: str) -> dict:
    """Look for .env at repo root, the pipeline dir, then cwd."""
    return load_env(root / ".env", root / pipeline / ".env", Path(".env"))


def get_client(env: dict):
    key = env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("[error] GEMINI_API_KEY missing — add it to your .env "
                         "(repo root, or {facebook,google}/.env). Runs on your Mac.")
    try:
        from google import genai
    except ImportError:
        raise SystemExit("[error] google-genai not installed. Run: "
                         "pip install google-genai")
    return genai.Client(api_key=key)


def generate_json(client, model: str, contents, *, temperature: float = 0.0,
                  max_retries: int = 4):
    """Call Flash for a JSON response, with simple backoff + lenient parsing.
    Returns the parsed object, or raises after exhausting retries."""
    assert_flash(model)
    from google.genai import types as gt
    cfg = gt.GenerateContentConfig(
        temperature=temperature, response_mime_type="application/json")
    last = None
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=model, contents=contents, config=cfg)
            text = (resp.text or "").strip()
            # tolerate accidental code fences
            if text.startswith("```"):
                text = text.strip("`")
                text = text[text.find("{") if "{" in text else 0:]
            return json.loads(text)
        except Exception as e:   # noqa: BLE001 — transient API / parse errors
            last = e
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"Flash call failed after {max_retries} tries: {last}")
