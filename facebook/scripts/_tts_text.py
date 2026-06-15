#!/usr/bin/env python3
"""
Shared TTS-text helpers — used by step4_tts.py (synth), step4_build_docs.py (render
the "TTS input" block in the Doc) and step4_localize.py (persist the dual-form lines).
ONE source so the block shown in the Doc is exactly what gets voiced. Kept dependency-
light + import-cycle-free (it imports none of the step4_* modules).
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

# _flash lives in analysis/scripts — needed only for native-script conversion.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent / "analysis" / "scripts"))

LINE_RE = re.compile(r"^\s*(.+?)\s+says:\s*(.*)$", re.IGNORECASE)
BRACKET_RE = re.compile(r"\[[^\]]*\]")  # strip [English translation] / [SFX] cues

# Headings/labels for the "TTS input" block. Also used as stop-markers when the Doc
# is parsed back, and to find the block for synthesis — keep them STABLE.
TTS_BLOCK_TITLE = "TTS input — paste into a voice provider"
TTS_NOTE = "(Spoken order · one turn per line · no character names — those would be read aloud.)"
NATIVE_LABEL = "Native script + English:"
ROMAN_LABEL = "Romanized + English:"
ENGLISH_LABEL = "Script (for TTS):"

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


def _scene_script(sc: dict) -> str:
    """A scene's spoken script, whether it's a rewrite shape (supernova_script) or a
    localized shape (script)."""
    return sc.get("supernova_script") or sc.get("script") or ""


def parse_turns(script: str) -> list[dict]:
    """One scene's script -> ordered [{speaker, text}] spoken turns. Strips the
    'Name says:' prefix + bracketed [..] cues; skips non-dialogue lines."""
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
    """Romanized code-mix -> native-script + English code-mix (Gemini Flash).
    English / empty / no client -> returned unchanged."""
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


def build_tts_lines(scenes: list, language: str, client=None) -> list[dict]:
    """Across all scenes (in order) -> [{speaker, romanized, native}] for spoken turns.
    English (or no client) -> native == romanized (no Flash call)."""
    turns = []
    for sc in scenes:
        turns.extend(parse_turns(_scene_script(sc)))
    roms = [t["text"] for t in turns]
    nats = to_native_script(client, language, roms)
    return [{"speaker": t["speaker"], "romanized": r, "native": n}
            for t, r, n in zip(turns, roms, nats)]


def tts_block_groups(tts_lines: list, language: str) -> list:
    """-> [(label, [line, …]), …] for rendering the block. English: a single group."""
    if not tts_lines:
        return []
    roms = [t.get("romanized", "") for t in tts_lines]
    nats = [t.get("native") or t.get("romanized", "") for t in tts_lines]
    if language.lower() == "english":
        return [(ENGLISH_LABEL, roms)]
    return [(NATIVE_LABEL, nats), (ROMAN_LABEL, roms)]


def parse_tts_input_block(doc_text: str, language: str) -> list[str]:
    """Read the spoken lines back out of an exported Doc's 'TTS input' block — the
    NATIVE-form lines (English: the single list), in order. Lets team EDITS to the
    block flow into the synthesized audio."""
    idx = doc_text.find(TTS_BLOCK_TITLE)
    if idx < 0:
        return []
    block = doc_text[idx + len(TTS_BLOCK_TITLE):]
    want = ENGLISH_LABEL if language.lower() == "english" else NATIVE_LABEL
    li = block.find(want)
    if li < 0:
        return []
    seg = block[li + len(want):]
    if language.lower() != "english":  # native section ends at the romanized label
        stop = seg.find(ROMAN_LABEL)
        if stop >= 0:
            seg = seg[:stop]
    out = []
    for raw in seg.splitlines():
        s = raw.strip()
        if not s or s.startswith("(") or set(s) <= {"─", "-", " "}:
            continue
        out.append(s)
    return out
