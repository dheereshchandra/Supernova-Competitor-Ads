#!/usr/bin/env python3
"""
Multi-provider TTS clients for step4_tts.py.

ONE interface — `synth(text, voice_id, ...) -> mp3 bytes` — over Cartesia and
ElevenLabs, so the voice registry (facebook/generation/supernova_voices.json)
decides, per character-slot and language, WHICH provider and voice renders each
line. `list_voices()` enumerates a provider's library so the registry can be
filled with real voice ids.

Keys live in the repo-root .env: CARTESIA_API_KEY, ELEVENLABS_API_KEY.
A provider whose key is absent raises TTSConfigError only when actually used —
the engine's --dry-run path never calls synth(), so the whole pipeline is
exercisable without keys. The Cartesia API version is pinned but overridable via
the CARTESIA_VERSION env var in case the provider bumps it.
"""
from __future__ import annotations

import requests

ELEVEN_BASE = "https://api.elevenlabs.io/v1"
CARTESIA_BASE = "https://api.cartesia.ai"
CARTESIA_VERSION_DEFAULT = "2024-11-13"

DEFAULT_MODELS = {"elevenlabs": "eleven_multilingual_v2", "cartesia": "sonic-2"}


class TTSConfigError(RuntimeError):
    """Missing key / misconfiguration — a human must fix .env or the registry."""


class TTSError(RuntimeError):
    """The provider returned an error for a synth/list call."""


def _key(env: dict, name: str) -> str:
    return (env.get(name) or "").strip()


class _Provider:
    name = "base"

    def __init__(self, env: dict):
        self.env = env

    def synth(self, text: str, voice_id: str, *, model=None, language=None,
              settings=None) -> bytes:
        raise NotImplementedError

    def list_voices(self, language: str | None = None) -> list[dict]:
        raise NotImplementedError


class ElevenLabsProvider(_Provider):
    name = "elevenlabs"

    def __init__(self, env: dict):
        super().__init__(env)
        self.api_key = _key(env, "ELEVENLABS_API_KEY")

    def _headers(self) -> dict:
        if not self.api_key:
            raise TTSConfigError("ELEVENLABS_API_KEY missing in .env")
        return {"xi-api-key": self.api_key}

    def synth(self, text, voice_id, *, model=None, language=None, settings=None) -> bytes:
        model = model or DEFAULT_MODELS["elevenlabs"]
        body = {"text": text, "model_id": model}
        settings = settings or {}
        vs = {k: settings[k] for k in
              ("stability", "similarity_boost", "style", "use_speaker_boost")
              if k in settings}
        if vs:
            body["voice_settings"] = vs
        # eleven_multilingual_v2 auto-detects the language from the (native-script) text.
        resp = requests.post(
            f"{ELEVEN_BASE}/text-to-speech/{voice_id}",
            headers={**self._headers(), "accept": "audio/mpeg",
                     "content-type": "application/json"},
            params={"output_format": "mp3_44100_128"},
            json=body, timeout=120,
        )
        if resp.status_code != 200:
            raise TTSError(f"elevenlabs {resp.status_code}: {resp.text[:300]}")
        return resp.content

    def list_voices(self, language=None) -> list[dict]:
        resp = requests.get(f"{ELEVEN_BASE}/voices", headers=self._headers(), timeout=30)
        resp.raise_for_status()
        out = []
        for v in resp.json().get("voices", []):
            labels = v.get("labels", {}) or {}
            out.append({"voice_id": v.get("voice_id"), "name": v.get("name"),
                        "language": labels.get("language", ""),
                        "gender": labels.get("gender", ""),
                        "labels": labels})
        if language:
            lang = language.lower()
            pref = [v for v in out if lang in (v.get("language") or "").lower()]
            return pref or out
        return out


class CartesiaProvider(_Provider):
    name = "cartesia"

    # Cartesia wants ISO codes; this is the subset most relevant to us. Unmapped
    # languages omit the field (the model auto-detects / uses the voice default).
    LANG_CODES = {"English": "en", "Hindi": "hi", "Tamil": "ta", "Telugu": "te",
                  "Bengali": "bn", "Gujarati": "gu", "Marathi": "mr", "Kannada": "kn",
                  "Malayalam": "ml", "Punjabi": "pa"}

    def __init__(self, env: dict):
        super().__init__(env)
        self.api_key = _key(env, "CARTESIA_API_KEY")
        self.version = _key(env, "CARTESIA_VERSION") or CARTESIA_VERSION_DEFAULT

    def _headers(self) -> dict:
        if not self.api_key:
            raise TTSConfigError("CARTESIA_API_KEY missing in .env")
        return {"X-API-Key": self.api_key, "Cartesia-Version": self.version}

    def synth(self, text, voice_id, *, model=None, language=None, settings=None) -> bytes:
        model = model or DEFAULT_MODELS["cartesia"]
        body = {
            "model_id": model,
            "transcript": text,
            "voice": {"mode": "id", "id": voice_id},
            "output_format": {"container": "mp3", "sample_rate": 44100, "bit_rate": 128000},
        }
        code = self.LANG_CODES.get(language or "")
        if code:
            body["language"] = code
        resp = requests.post(
            f"{CARTESIA_BASE}/tts/bytes",
            headers={**self._headers(), "content-type": "application/json"},
            json=body, timeout=120,
        )
        if resp.status_code != 200:
            raise TTSError(f"cartesia {resp.status_code}: {resp.text[:300]}")
        return resp.content

    def list_voices(self, language=None) -> list[dict]:
        # /voices is paginated (default 10/page) — walk all pages via starting_after.
        out, seen, params = [], set(), {"limit": 100}
        for _ in range(25):  # page cap
            resp = requests.get(f"{CARTESIA_BASE}/voices", headers=self._headers(),
                                params=params, timeout=30)
            resp.raise_for_status()
            d = resp.json()
            data = (d.get("data") if isinstance(d, dict) else d) or []
            for v in data:
                vid = v.get("id")
                if vid in seen:
                    continue
                seen.add(vid)
                out.append({"voice_id": vid, "name": v.get("name"),
                            "language": v.get("language", ""), "gender": v.get("gender", "")})
            if not (isinstance(d, dict) and d.get("has_more")) or not data:
                break
            params = {"limit": 100, "starting_after": data[-1].get("id")}
        if language:
            code = self.LANG_CODES.get(language, language.lower())
            pref = [v for v in out if (v.get("language") or "").lower() in (code, language.lower())]
            return pref or out
        return out


PROVIDERS = {"elevenlabs": ElevenLabsProvider, "cartesia": CartesiaProvider}


def get_provider(name: str, env: dict) -> _Provider:
    cls = PROVIDERS.get((name or "").lower())
    if not cls:
        raise TTSConfigError(f"unknown TTS provider '{name}' (one of {list(PROVIDERS)})")
    return cls(env)
