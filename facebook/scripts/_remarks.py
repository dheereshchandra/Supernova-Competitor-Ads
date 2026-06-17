"""_remarks.py — deterministic, edge-case "reviewer remarks" for a generated script.

Pure (stdlib only; operates on already-parsed dicts and a language string), so it can be
imported by BOTH the facebook pipeline scripts (step4_localize / step4_build_docs / the W25
CSV driver) AND the Ad Studio backend (webapp/backend/data.py) with no side effects.

Two ad-level edge cases the team must see BEFORE they trust or voice a localized script:
  1. the original competitor ad is in ENGLISH — localizing it to an Indian language may be the
     wrong call (the script is a translation, not a like-for-like replication);
  2. the original ad has NO voiceover (text-only / on-screen conversation) — any voiceover
     generated here is fully synthetic, not a replication of the source.

Both are detected with zero LLM cost from data we already have (the enriched `language` column
for the seed language, and the decompose's per-scene `audio_transcript`). The common case
returns `[]` (no remark).
"""
from __future__ import annotations

import re

# Bracketed stage/sound markers the decompose emits, e.g. '[music only, no speech]',
# '[upbeat regional Indian music playing]'. A scene is voiceless only if NOTHING but these
# (or whitespace) remains — so a scene that also has real 'Name says: …' speech is NOT voiceless.
_BRACKET_RE = re.compile(r"\[[^\]]*\]")

EN_ORIGINAL = ("Original ad is in English — the localized script is a translation; "
               "consider keeping it in English.")
NO_VOICEOVER = ("No voiceover in the original ad (it's text-only) — any voiceover here is "
                "fully synthetic, not a replication of the original.")


def _voiceless(audio_transcript) -> bool:
    """True only if a scene carries no spoken dialogue. Bracketed markers like
    '[music only, no speech]' are stripped first, so a scene that also contains real
    'Name says: …' speech (a common decompose shape — speech then a music outro) is NOT
    counted voiceless; a scene that is purely markers (or empty) is."""
    t = (audio_transcript or "").strip()
    if not t:
        return True
    return _BRACKET_RE.sub("", t).strip() == ""


def is_english_original(seed_language: str) -> bool:
    """The ad's spoken language (enriched `language` column) is English."""
    return (seed_language or "").strip().lower() == "english"


def is_no_voiceover(decompose_parsed: dict) -> bool:
    """Every scene in the decomposition is voiceless (and there is at least one scene)."""
    scenes = (decompose_parsed or {}).get("scenes") or []
    if not scenes:
        return False
    return all(_voiceless(s.get("audio_transcript")) for s in scenes)


def audio_note(decompose_parsed: dict) -> str:
    """Best available description of the ad's audio, for the no-voiceover remark. Prefers the
    decompose's top-level `audio_track`; else the distinct bracketed audio markers across scenes
    (e.g. '[background song, no spoken dialogue]')."""
    track = ((decompose_parsed or {}).get("audio_track") or "").strip()
    if track:
        return track
    seen: set[str] = set()
    out: list[str] = []
    for s in (decompose_parsed or {}).get("scenes") or []:
        for m in _BRACKET_RE.findall(s.get("audio_transcript") or ""):
            t = m.strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
    return "; ".join(out)


def no_voiceover_remark(decompose_parsed: dict) -> str:
    """The rich no-voiceover reviewer note: states there's no spoken dialogue, what the audio is,
    and that the on-screen text (not a VO) is what was replicated/translated."""
    note = audio_note(decompose_parsed)
    base = ("No spoken dialogue in the original ad — the message is carried by ON-SCREEN TEXT "
            "(replicated/translated here); any voiceover generated is synthetic, not a replication "
            "of the original.")
    return f"{base} Audio: {note}." if note else base


def detect_remarks(decompose_parsed: dict, seed_language: str) -> list[str]:
    """Ad-level reviewer remarks (deterministic, no LLM). Empty list for the common case."""
    out: list[str] = []
    if is_english_original(seed_language):
        out.append(EN_ORIGINAL)
    if is_no_voiceover(decompose_parsed):
        out.append(no_voiceover_remark(decompose_parsed))
    return out
