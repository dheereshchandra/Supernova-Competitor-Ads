#!/usr/bin/env python3
"""
Shared TTS-text helpers used by step4_tts.py (voiceover synth). ONE source of truth for parsing the
spoken turns + the Doc's "TTS input" block, so the audio is voiced from exactly what the team
sees/edits. Import-cycle-free (imports no step4_* module).
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent / "analysis" / "scripts"))

LINE_RE = re.compile(r"^\s*(.+?)\s+says:\s*(.*)$", re.IGNORECASE)
BRACKET_RE = re.compile(r"\[[^\]]*\]")  # strip [English translation] / [SFX] cues before synth

# The "TTS input" block headings — MUST match what step4_build_docs.py renders (the localized doc
# has a Romanized section then a Native section; the English master has no TTS block).
TTS_BLOCK_TITLE = "TTS input"
ROMAN_LABEL = "Romanized (Latin + English)"
NATIVE_LABEL = "Native script + English"

NATIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {"type": "array", "items": {
            "type": "object",
            "properties": {"i": {"type": "integer"}, "text": {"type": "string"}},
            "required": ["i", "text"],
        }},
    },
    "required": ["lines"],
}


def parse_turns(script: str) -> list[dict]:
    """One scene's script -> ordered [{speaker, text}] spoken turns. Strips the 'Name says:'
    prefix + bracketed [..] cues; skips non-dialogue lines."""
    out = []
    for raw in (script or "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        speaker = m.group(1).strip().strip("*").strip()
        text = BRACKET_RE.sub("", m.group(2)).strip()
        if text:
            out.append({"speaker": speaker, "text": text})
    return out


def to_native_script(client, language: str, texts: list[str]) -> list[str]:
    """Romanized code-mix -> native-script + English code-mix (Gemini Flash). English / empty /
    no client -> returned unchanged."""
    if not texts or language.lower() == "english" or client is None:
        return list(texts)
    import _flash  # noqa: E402 — analysis/scripts is on sys.path above
    payload = [{"i": i, "text": t} for i, t in enumerate(texts)]
    prompt = (
        f"You convert romanized {language} ad-script lines into the SAME language written in its "
        f"NATIVE SCRIPT, for a text-to-speech engine.\n\n"
        f"RULES:\n"
        f"- Transliterate the romanized {language} words into correct native {language} script. This "
        f"is transliteration into proper spelling, NOT translation — keep the SAME words.\n"
        f"- Keep English words in Latin script (code-mix), and keep numbers, 'Supernova AI', "
        f"'Miss Nova' and proper nouns exactly as written.\n"
        f"- Do NOT add, drop, reorder, or paraphrase words. Exactly one output line per input line, "
        f"same index i.\n"
        f"- It will be read aloud, so spell native words the natural, correct way.\n\n"
        f"Return ONE JSON object: {{\"lines\":[{{\"i\":<index>,\"text\":\"<native-script line>\"}}]}}\n\n"
        f"INPUT LINES:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    res = _flash.generate_json(client, _flash.DEFAULT_MODEL, prompt,
                               temperature=0.0, response_schema=NATIVE_SCHEMA)
    by_i = {ln.get("i"): ln.get("text", "") for ln in res.get("lines", [])}
    return [by_i.get(i) or texts[i] for i in range(len(texts))]


def parse_tts_input_block(doc_text: str, language: str) -> list[str]:
    """Read the spoken NATIVE-form lines back out of an exported Doc's 'TTS input' block (the
    section that gets voiced), in order — so team EDITS to the block flow into the audio.
    Localized docs only; the English master has no TTS block."""
    if language.lower() == "english":
        return []
    idx = doc_text.find(TTS_BLOCK_TITLE)
    if idx < 0:
        return []
    block = doc_text[idx + len(TTS_BLOCK_TITLE):]
    li = block.find(NATIVE_LABEL)
    if li < 0:
        return []
    seg = block[li + len(NATIVE_LABEL):]
    stop = seg.find("Provenance")
    if stop >= 0:
        seg = seg[:stop]
    out = []
    for raw in seg.splitlines():
        s = raw.strip()
        if not s or s.startswith("(") or set(s) <= {"─", "-", " "}:
            continue
        out.append(s)
    return out
