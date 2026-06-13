#!/usr/bin/env python3
"""
step4_tts.py — generate a per-language VOICEOVER (TTS audio) for an approved
Supernova ad script. Splits out of "Stage 5a (TTS + video)" — this is the TTS
half only; video is a separate later step.

Per ad + language:
  1. Resolve the approved script — prefer the team-EDITED Google Doc (English
     master doc for English; the per-language Doc otherwise), fall back to the
     committed sidecar (<id>.supernova.json / <id>.<lang>.supernova.json).
  2. Parse the "<Name> says: ..." lines and map each speaker to a VOICE SLOT
     (Miss Nova / male|female lead|secondary / narrator) via the inferred
     gender + appearance order.
  3. For non-English, convert each romanized line -> NATIVE-SCRIPT + English
     code-mix (Gemini Flash) — TTS engines pronounce native script correctly.
  4. Synthesize each line with its slot's voice (Cartesia or ElevenLabs, per the
     registry facebook/generation/supernova_voices.json).
  5. ffmpeg-stitch the line clips into ONE per-language track (keeping the
     per-line clips), upload clips + track to R2, and record the URLs on
     <id>.gdocs.json (a `tts` map) + a resume sidecar <id>.<lang>.tts.json.

Run from facebook/ (WORKSPACE-relative paths). Resume-safe; --dry-run makes
silent placeholder clips (no provider calls, no spend) so the whole flow is
exercisable without API keys.

Usage:
    python3.13 scripts/step4_tts.py <ad_id> --competitor mysivi --languages Hindi,Telugu
        [--source auto|gdoc|sidecar] [--dry-run] [--regenerate]
    python3.13 scripts/step4_tts.py --list-voices --provider elevenlabs|cartesia [--language Hindi]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import time

WORKSPACE = pathlib.Path("step4_workspace")
SCENES_DIR = WORKSPACE / "scenes"
AUDIO_DIR = WORKSPACE / "audio"

_HERE = pathlib.Path(__file__).resolve().parent
REGISTRY_PATH = _HERE.parent / "generation" / "supernova_voices.json"
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent.parent / "analysis" / "scripts"))
import _flash                       # noqa: E402
import _gdrive                      # noqa: E402
import _tts_providers as tts        # noqa: E402
import step4_localize as loc        # noqa: E402  (reuse parse_doc_scenes)
from r2_utils import load_env, make_r2_client, upload_file  # noqa: E402

SUPPORTED_LANGUAGES = ["English", "Hindi", "Telugu", "Tamil", "Marathi", "Kannada",
                       "Malayalam", "Bengali", "Gujarati", "Assamese", "Punjabi"]

LINE_RE = re.compile(r"^\s*(.+?)\s+says:\s*(.*)$", re.IGNORECASE)
BRACKET_RE = re.compile(r"\[[^\]]*\]")  # strip [English translation] / [SFX] cues before synth
AI_TEACHER_RE = re.compile(r"miss\s*nova|\b(a\.?i\.?|robot|avatar|assistant|tutor|bot|hologram|virtual)\b", re.I)
NARRATOR_RE = re.compile(r"\b(narrator|voice\s*-?\s*over|voiceover|\bvo\b)\b", re.I)
FEMALE_RE = re.compile(r"\b(female|woman|women|girl|lady|mother|mom|mum|aunt|sister|daughter|wife|grandmother|she|her)\b", re.I)
MALE_RE = re.compile(r"\b(male|man|men|boy|father|dad|uncle|brother|son|husband|grandfather|he|him)\b", re.I)

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


# ---------------------------------------------------------------- registry / voices
def load_registry() -> dict:
    try:
        return json.loads(REGISTRY_PATH.read_text())
    except FileNotFoundError:
        sys.exit(f"[error] voice registry missing at {REGISTRY_PATH}")


def resolve_voice(reg: dict, language: str, slot: str) -> dict | None:
    base = (reg.get("slots") or {}).get(slot) or {}
    override = ((reg.get("language_overrides") or {}).get(language) or {}).get(slot) or {}
    entry = {**base, **override}
    vid = entry.get("voice_id")
    if not entry.get("provider") or not vid:
        return None
    pdef = (reg.get("providers") or {}).get(entry["provider"], {})
    return {
        "slot": slot,
        "provider": entry["provider"],
        "voice_id": vid,
        "model": entry.get("model") or pdef.get("model"),
        "settings": {**(pdef.get("settings") or {}), **(entry.get("settings") or {})},
        "configured": not str(vid).startswith("TODO"),
    }


def infer_gender(name: str, role: str) -> str:
    text = f"{name} {role}"
    if FEMALE_RE.search(text):
        return "female"
    if MALE_RE.search(text):
        return "male"
    return "female"  # rare fallback; the decompose role almost always states gender


def assign_slots(characters: list) -> dict:
    """name(lower) -> voice slot. Miss Nova -> miss_nova; narrator/VO -> narrator;
    else first-of-that-gender -> *_lead, the rest -> *_secondary (appearance order)."""
    out, fem, male = {}, 0, 0
    for c in characters:
        name = (c.get("name") or "").strip()
        role = (c.get("role") or "")
        text = f"{name} {role}"
        if re.search(r"miss\s*nova", text, re.I) or AI_TEACHER_RE.search(role):
            slot = "miss_nova"
        elif NARRATOR_RE.search(text):
            slot = "narrator"
        else:
            if infer_gender(name, role) == "female":
                slot = "female_lead" if fem == 0 else "female_secondary"; fem += 1
            else:
                slot = "male_lead" if male == 0 else "male_secondary"; male += 1
        if name:
            out[name.lower()] = slot
    return out


# ---------------------------------------------------------------- script resolution
def _load_json(p: pathlib.Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def resolve_script(ad_id: str, language: str, source_mode: str) -> tuple[list, list, str]:
    """Return (scenes, characters, source_label).
    scenes = [{n, label, script}] with the team-edited Doc text overlaid when available."""
    base = _load_json(SCENES_DIR / f"{ad_id}.supernova.json")
    base_parsed = base.get("parsed", {})
    characters = base_parsed.get("characters", [])
    is_english = language.lower() == "english"

    if is_english:
        scenes = [{"n": s.get("n"), "label": s.get("scene_label", ""),
                   "script": s.get("supernova_script", "")}
                  for s in base_parsed.get("scenes", [])]
        doc_key = "supernova_doc"
        gdocs = _load_json(SCENES_DIR / f"{ad_id}.gdocs.json")
        fid = (gdocs.get(doc_key) or {}).get("file_id")
    else:
        side = _load_json(SCENES_DIR / f"{ad_id}.{language.lower()}.supernova.json")
        if not side:
            sys.exit(f"[error] no {language} script for {ad_id} — run localization first.")
        scenes = [{"n": s.get("n"), "label": s.get("scene_label", ""),
                   "script": s.get("script", "")}
                  for s in side.get("parsed", {}).get("scenes", [])]
        gdocs = _load_json(SCENES_DIR / f"{ad_id}.gdocs.json")
        fid = ((gdocs.get("locales") or {}).get(language.lower()) or {}).get("file_id")

    source = "sidecar (committed script)"
    if source_mode in ("auto", "gdoc") and fid:
        try:
            svc = _gdrive.build_drive_service(load_env())
            edited = loc.parse_doc_scenes(_gdrive.export_doc_text(svc, fid))
            applied = 0
            for sc in scenes:
                e = edited.get(sc["n"])
                if e and e.get("script"):
                    sc["script"] = e["script"]; applied += 1
            source = f"EDITED gdoc — {applied}/{len(scenes)} scenes overlaid"
        except Exception as ex:
            source = f"sidecar (gdoc read failed: {type(ex).__name__})"
            if source_mode == "gdoc":
                sys.exit(f"[error] --source gdoc but {source}")
    return scenes, characters, source


def parse_lines(scenes: list) -> list:
    """Flatten scenes -> ordered [{scene, idx, speaker, text}] spoken turns."""
    out = []
    for sc in scenes:
        for k, raw in enumerate((sc.get("script") or "").split("\n")):
            line = raw.strip()
            if not line:
                continue
            m = LINE_RE.match(line)
            if not m:
                continue  # stage direction / non-dialogue
            speaker = m.group(1).strip().strip("*").strip()
            text = BRACKET_RE.sub("", m.group(2)).strip()
            if text:
                out.append({"scene": sc.get("n"), "idx": k, "speaker": speaker, "text": text})
    return out


def to_native_script(client, language: str, texts: list[str]) -> list[str]:
    """Romanized code-mix -> native-script + English code-mix (Flash). English: unchanged."""
    if language.lower() == "english" or not texts:
        return texts
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


# ---------------------------------------------------------------- ffmpeg helpers
def _ffmpeg(args: list[str]) -> None:
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[:300]}")


def _silence_clip(path: pathlib.Path, secs: float) -> None:
    _ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", f"{max(0.1, secs):.2f}",
             "-c:a", "libmp3lame", "-b:a", "128k", str(path)])


def _stitch(clips: list[pathlib.Path], out_path: pathlib.Path, gap: float = 0.3) -> None:
    """Concatenate clips with `gap` seconds of silence between them (re-encoded, so
    differing provider sample rates/bitrates are normalized)."""
    sil = out_path.parent / "_gap.mp3"
    _silence_clip(sil, gap)
    inputs, parts, n = [], [], 0
    for i, clip in enumerate(clips):
        inputs += ["-i", str(clip)]; parts.append(f"[{n}:a]"); n += 1
        if i != len(clips) - 1:
            inputs += ["-i", str(sil)]; parts.append(f"[{n}:a]"); n += 1
    filt = "".join(parts) + f"concat=n={n}:v=0:a=1[out]"
    _ffmpeg([*inputs, "-filter_complex", filt, "-map", "[out]",
             "-c:a", "libmp3lame", "-b:a", "128k", str(out_path)])


# ---------------------------------------------------------------- per-language run
def tts_one(client, s3, env, reg, ad_id, competitor, language, source_mode,
            dry_run, regenerate) -> dict:
    lang_key = language.lower()
    side_path = SCENES_DIR / f"{ad_id}.{lang_key}.tts.json"
    if side_path.exists() and not regenerate:
        side = _load_json(side_path)
        print(f"  [{language}] reuse — {side.get('track_url', '(no track)')}")
        return side

    scenes, characters, source = resolve_script(ad_id, language, source_mode)
    print(f"  [{language}] source: {source}")
    slot_by_name = assign_slots(characters)
    lines = parse_lines(scenes)
    if not lines:
        raise RuntimeError(f"no spoken lines parsed for {language}")

    natives = to_native_script(client, language, [ln["text"] for ln in lines])

    out_dir = AUDIO_DIR / ad_id / lang_key
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_paths, line_meta = [], []
    for n, (ln, native) in enumerate(zip(lines, natives)):
        slot = slot_by_name.get(ln["speaker"].lower())
        if not slot:  # unknown speaker (not in roster) -> narrator
            slot = "narrator"
        voice = resolve_voice(reg, language, slot)
        clip = out_dir / f"line_{n:03d}_{slot}.mp3"
        if dry_run:
            _silence_clip(clip, max(1.0, len(native) / 14.0))
        else:
            if not voice or not voice["configured"]:
                raise tts.TTSConfigError(
                    f"no configured voice for slot '{slot}' / {language} — fill "
                    f"facebook/generation/supernova_voices.json (voice_id still 'TODO').")
            provider = tts.get_provider(voice["provider"], env)
            audio = provider.synth(native, voice["voice_id"], model=voice["model"],
                                   language=language, settings=voice["settings"])
            clip.write_bytes(audio)
        clip_paths.append(clip)
        line_meta.append({"scene": ln["scene"], "speaker": ln["speaker"], "slot": slot,
                          "provider": (voice or {}).get("provider"),
                          "voice_id": (voice or {}).get("voice_id"), "clip": clip.name})

    track = out_dir / f"{ad_id}_{lang_key}.mp3"
    _stitch(clip_paths, track)

    track_url, line_urls = "(dry-run)", []
    if not dry_run:
        for cp, meta in zip(clip_paths, line_meta):
            meta["url"] = upload_file(s3, env, cp, f"audio/{ad_id}/{lang_key}/{cp.name}")
            line_urls.append(meta["url"])
        track_url = upload_file(s3, env, track, f"audio/{ad_id}/{lang_key}/{track.name}")

    side = {"ad_library_id": ad_id, "language": language, "track_url": track_url,
            "line_urls": line_urls, "lines": line_meta, "dry_run": dry_run,
            "model": _flash.DEFAULT_MODEL, "tts_at": time.time()}
    if not dry_run:
        side_path.write_text(json.dumps(side, indent=2, ensure_ascii=False))

    # record on the shared gdocs sidecar (the `tts` map mirrors `locales`)
    gpath = SCENES_DIR / f"{ad_id}.gdocs.json"
    gdocs = _load_json(gpath) or {"ad_library_id": ad_id, "competitor": competitor}
    tts_map = gdocs.setdefault("tts", {})
    tts_map[lang_key] = {"track_url": track_url, "line_count": len(line_meta),
                         "voices": sorted({m["slot"] for m in line_meta}),
                         "verified": (tts_map.get(lang_key) or {}).get("verified", False),
                         "verified_by": (tts_map.get(lang_key) or {}).get("verified_by", ""),
                         "tts_at": time.time()}
    if not dry_run:
        gpath.write_text(json.dumps(gdocs, indent=2, ensure_ascii=False))
    print(f"  [{language}] {len(line_meta)} lines → {track_url}"
          + ("  (dry-run, not uploaded)" if dry_run else ""))
    return side


def cmd_tts(ad_id, competitor, languages, source_mode, dry_run, regenerate) -> int:
    for lg in languages:
        if lg not in SUPPORTED_LANGUAGES:
            sys.exit(f"[error] unsupported language '{lg}'. One of: {', '.join(SUPPORTED_LANGUAGES)}")
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    env = load_env()
    reg = load_registry()
    client = _flash.get_client(env)
    s3 = None if dry_run else make_r2_client(env)

    print(f"TTS {ad_id} ({competitor}) → {', '.join(languages)}"
          + ("  [DRY-RUN]" if dry_run else ""))
    results = []
    for language in languages:
        try:
            results.append(tts_one(client, s3, env, reg, ad_id, competitor, language,
                                   source_mode, dry_run, regenerate))
        except Exception as ex:
            print(f"  [{language}] FAILED — {type(ex).__name__}: {str(ex)[:160]}")
            results.append({"language": language, "error": str(ex)})

    print("\nDONE:")
    for r in results:
        if r.get("error"):
            print(f"  {r.get('language', '?'):<10} ERROR {r['error'][:100]}")
        else:
            print(f"  {r['language']:<10} {r.get('track_url', '')}")
    return 0 if all(not r.get("error") for r in results) else 1


def cmd_list_voices(provider: str, language: str | None) -> int:
    env = load_env()
    prov = tts.get_provider(provider, env)
    voices = prov.list_voices(language)
    print(f"{provider} voices" + (f" (filtered: {language})" if language else "") + f" — {len(voices)}")
    for v in voices[:300]:
        print(f"  {v.get('voice_id', ''):<40} {str(v.get('name', '')):<28} "
              f"{str(v.get('language', '')):<10} {v.get('gender', '')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ad_id", nargs="?")
    ap.add_argument("--competitor", default="")
    ap.add_argument("--languages", help="comma-separated, e.g. Hindi,Telugu")
    ap.add_argument("--source", choices=["auto", "gdoc", "sidecar"], default="auto")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--regenerate", action="store_true")
    ap.add_argument("--list-voices", action="store_true")
    ap.add_argument("--provider", choices=["elevenlabs", "cartesia"])
    ap.add_argument("--language", help="filter for --list-voices")
    args = ap.parse_args()

    if args.list_voices:
        if not args.provider:
            sys.exit("[error] --list-voices needs --provider elevenlabs|cartesia")
        return cmd_list_voices(args.provider, args.language)

    if not args.ad_id or not args.languages:
        sys.exit("[error] usage: step4_tts.py <ad_id> --competitor X --languages Hindi,Telugu")
    langs = [x.strip() for x in args.languages.split(",") if x.strip()]
    return cmd_tts(args.ad_id, args.competitor.lower().strip(), langs,
                   args.source, args.dry_run, args.regenerate)


if __name__ == "__main__":
    raise SystemExit(main())
