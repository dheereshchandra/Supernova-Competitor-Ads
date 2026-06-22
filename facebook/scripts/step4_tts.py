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
import _tts_text as ttx             # noqa: E402  (shared TTS text helpers)
from r2_utils import load_env, make_r2_client, upload_file  # noqa: E402

SUPPORTED_LANGUAGES = ["English", "Hindi", "Telugu", "Tamil", "Marathi", "Kannada",
                       "Malayalam", "Bengali", "Gujarati", "Assamese", "Punjabi"]

LINE_RE = re.compile(r"^\s*(.+?)\s+says:\s*(.*)$", re.IGNORECASE)
BRACKET_RE = re.compile(r"\[[^\]]*\]")  # strip [English translation] / [SFX] cues before synth

# Playground-only speaker-label detection. Handles "Name says: ..." (any case) AND "Name: ..."
# (Title-Case / CAPS name only — so a mid-sentence colon like "I said: stop" is NOT a label).
# Production stays on LINE_RE ("Name says:" only); this only affects the Translations tab.
_PG_SAYS_RE = re.compile(r"^(.{1,40}?)\s+says\s*:\s*(.+)$", re.IGNORECASE)
_PG_COLON_RE = re.compile(r"^\*{0,2}\s*([A-Z][\w.'\-]*(?:\s+[A-Z][\w.'\-]*){0,3})\*{0,2}\s*:\s*(.+)$")
# A line that is ONLY a speaker label with no inline dialogue ("Robot says:" / "Priya:") — a
# production cue, never voiced.
_PG_LABEL_ONLY_RE = re.compile(r"^\*{0,2}\s*[\w.'\- ]{1,40}?\s*\*{0,2}\s*:\s*\*{0,2}\s*$", re.IGNORECASE)


def _split_label(line: str) -> tuple[str | None, str]:
    """(speaker, dialogue) if the line opens with a speaker label, else (None, original line)."""
    s = line.strip()
    m = _PG_SAYS_RE.match(s) or _PG_COLON_RE.match(s)
    if m:
        return m.group(1).strip().strip("*").strip(), m.group(2).strip()
    return None, line
AI_TEACHER_RE = re.compile(r"miss\s*nova|\b(a\.?i\.?|robot|avatar|assistant|tutor|bot|hologram|virtual)\b", re.I)
NARRATOR_RE = re.compile(r"\b(narrator|voice\s*-?\s*over|voiceover|\bvo\b)\b", re.I)
FEMALE_RE = re.compile(r"\b(female|woman|women|girl|lady|mother|mom|mum|aunt|sister|daughter|wife|grandmother|she|her)\b", re.I)
MALE_RE = re.compile(r"\b(male|man|men|boy|father|dad|uncle|brother|son|husband|grandfather|he|him)\b", re.I)


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


def voice_catalog(reg: dict) -> dict:
    """Every distinct configured voice in the registry (slots + all language overrides),
    keyed by voice_id -> a resolve_voice-shaped entry, so a per-character OVERRIDE voice_id
    drops straight into the synth path. Carries the human `name` (the registry `_voice`)."""
    out: dict = {}

    def add(entry: dict, slot: str):
        vid, prov = entry.get("voice_id"), entry.get("provider")
        if not vid or not prov or str(vid).startswith("TODO") or vid in out:
            return
        pdef = (reg.get("providers") or {}).get(prov, {})
        out[vid] = {
            "slot": slot, "provider": prov, "voice_id": vid,
            "name": entry.get("_voice") or vid,
            "model": entry.get("model") or pdef.get("model"),
            "settings": {**(pdef.get("settings") or {}), **(entry.get("settings") or {})},
            "configured": True,
        }

    for slot, e in (reg.get("slots") or {}).items():
        add(e, slot)
    for _lang, slots in (reg.get("language_overrides") or {}).items():
        for slot, e in (slots or {}).items():
            add(e, slot)
    return out


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
        # post-#90 the localized sidecar carries script_roman + script_native (older: script).
        scenes = [{"n": s.get("n"), "label": s.get("scene_label", ""),
                   "script": s.get("script_roman") or s.get("script", "")}
                  for s in side.get("parsed", {}).get("scenes", [])]
        gdocs = _load_json(SCENES_DIR / f"{ad_id}.gdocs.json")
        fid = ((gdocs.get("locales") or {}).get(language.lower()) or {}).get("file_id")

    source = "sidecar (committed script)"
    doc_native: list = []
    if source_mode in ("auto", "gdoc") and fid:
        try:
            svc = _gdrive.build_drive_service(load_env())
            txt = _gdrive.export_doc_text(svc, fid)
            applied = loc.overlay_doc_edits(scenes, txt)
            doc_native = ttx.parse_tts_input_block(txt, language)  # team edits to the TTS block
            source = (f"EDITED gdoc — {applied}/{len(scenes)} scenes overlaid"
                      + (f", {len(doc_native)} TTS-input lines" if doc_native else ""))
        except Exception as ex:
            source = f"sidecar (gdoc read failed: {type(ex).__name__})"
            if source_mode == "gdoc":
                sys.exit(f"[error] --source gdoc but {source}")
    return scenes, characters, source, doc_native


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

    scenes, characters, source, doc_native = resolve_script(ad_id, language, source_mode)
    print(f"  [{language}] source: {source}")
    slot_by_name = assign_slots(characters)
    lines = parse_lines(scenes)
    if not lines:
        raise RuntimeError(f"no spoken lines parsed for {language}")

    # Native synth text, in priority: the edited Doc's TTS-input block (so team edits get voiced)
    # → the localized sidecar's persisted script_native → on-the-fly conversion. The speaker for
    # each turn always comes from the main script's turn order (lines).
    sc_path = (f"{ad_id}.{lang_key}.supernova.json" if lang_key != "english"
               else f"{ad_id}.supernova.json")
    sidecar_native = [t["text"]
                      for s in _load_json(SCENES_DIR / sc_path).get("parsed", {}).get("scenes", [])
                      for t in ttx.parse_turns(s.get("script_native") or "")]
    if doc_native and len(doc_native) == len(lines):
        natives, nsrc = doc_native, "edited Doc TTS-input block"
    elif sidecar_native and len(sidecar_native) == len(lines):
        natives, nsrc = sidecar_native, "localized sidecar (script_native)"
    else:
        if doc_native or sidecar_native:
            print(f"  [{language}] [warn] TTS-input line count mismatch — reconverting on the fly")
        natives = ttx.to_native_script(client, language, [ln["text"] for ln in lines])
        nsrc = "on-the-fly conversion"
    print(f"  [{language}] voicing from: {nsrc}")

    # Per-character voice OVERRIDES (from the Ad Studio picker): {character name -> voice_id}.
    # An override wins over the auto-assigned slot voice; unknown ids fall back to the slot.
    overrides = {str(k).lower(): v for k, v in
                 _load_json(SCENES_DIR / f"{ad_id}.voices.json").items()}
    catalog = voice_catalog(reg)
    if overrides:
        print(f"  [{language}] voice overrides for: {', '.join(sorted(overrides))}")

    out_dir = AUDIO_DIR / ad_id / lang_key
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_paths, line_meta = [], []
    for n, (ln, native) in enumerate(zip(lines, natives)):
        ov = overrides.get(ln["speaker"].lower())
        if ov and ov in catalog:
            voice = catalog[ov]
            slot = voice["slot"]
        else:
            slot = slot_by_name.get(ln["speaker"].lower()) or "narrator"
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


def cmd_list_voices(provider: str, language: str | None, as_json: bool = False) -> int:
    env = load_env()
    prov = tts.get_provider(provider, env)
    voices = prov.list_voices(language)
    if as_json:   # for the Translations tab voice picker
        print(json.dumps({"provider": provider, "voices": voices}, ensure_ascii=False))
        return 0
    print(f"{provider} voices" + (f" (filtered: {language})" if language else "") + f" — {len(voices)}")
    for v in voices[:300]:
        print(f"  {v.get('voice_id', ''):<40} {str(v.get('name', '')):<28} "
              f"{str(v.get('language', '')):<10} {v.get('gender', '')}")
    return 0


def cmd_setup(ad_id: str, competitor: str, language: str) -> int:
    """Emit JSON for the Ad Studio voice picker: the ad's CHARACTERS (each with its
    auto-assigned default voice for this language) + the VOICE CATALOG to choose from.
    Cast comes from the English master sidecar (same across languages); the default voice
    is language-specific (per the registry overrides)."""
    reg = load_registry()
    base = _load_json(SCENES_DIR / f"{ad_id}.supernova.json").get("parsed", {})
    characters = base.get("characters", [])
    slot_by_name = assign_slots(characters)
    cat = voice_catalog(reg)
    chars, seen = [], set()
    for c in characters:
        name = (c.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        slot = slot_by_name.get(name.lower()) or "narrator"
        dv = resolve_voice(reg, language or "English", slot) or {}
        chars.append({"name": name, "role": c.get("role", ""), "slot": slot,
                      "default_voice_id": dv.get("voice_id", "")})
    voices = sorted(({"provider": v["provider"], "voice_id": v["voice_id"], "name": v["name"]}
                     for v in cat.values()), key=lambda x: (x["provider"], x["name"]))
    print(json.dumps({"characters": chars, "voices": voices}, ensure_ascii=False))
    return 0


def cmd_playground_native() -> int:
    """Real-time native-script transliteration for the "Translations" playground tab. Reads
    {"language", "roman", "model"?, "prompt_override"?} from stdin, prints {"native"}.
    The "Name says:" label is a production cue (never voiced), so it is STRIPPED here — the native
    TTS script is a clean continuous flow of the spoken sentences, kept line-aligned to the romanized
    block (one line per turn) so speakers map back positionally at synth time.
    SYNCHRONOUS — NOT the job queue, NOT the Gemini Batch API."""
    req = json.loads(sys.stdin.read() or "{}")
    language = (req.get("language") or "").strip()
    roman = req.get("roman") or ""
    model = (req.get("model") or _flash.DEFAULT_MODEL).strip()
    prompt_override = req.get("prompt_override") or None
    if not language or not roman.strip():
        print(json.dumps({"native": roman}, ensure_ascii=False))
        return 0
    allow_pro = "pro" in model.lower()
    env = load_env()
    client = _flash.get_client(env)
    lines = roman.split("\n")
    # if the script has ANY speaker labels, unlabelled lines are stage directions / scene headings —
    # not voiced (mirrors the production parse_turns "dialogue-only" contract).
    has_labels = any(_split_label(ln)[0] for ln in lines if ln.strip())
    payloads, idx = [], []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or _PG_LABEL_ONLY_RE.match(s):     # blank or a bare "Name:" cue line -> not voiced
            continue
        spk, dialogue = _split_label(ln)            # strip "Name:" / "Name says:" label if present
        if has_labels and not spk:                  # a stage direction inside a labelled script
            continue
        dialogue = BRACKET_RE.sub("", dialogue).strip()   # drop [SFX]/[music only] cues
        if not dialogue:
            continue
        payloads.append(dialogue)
        idx.append(i)
    converted = ttx.to_native_script(client, language, payloads,
                                     model=model, allow_pro=allow_pro,
                                     prompt_override=prompt_override)
    out = [""] * len(lines)                         # blank for cues/labels/non-dialogue lines
    for i, txt in zip(idx, converted):
        out[i] = txt                                # label-free native sentence, aligned to its roman line
    print(json.dumps({"native": "\n".join(out)}, ensure_ascii=False))
    return 0


def _playground_turns(roman: str, native: str) -> tuple[list, bool]:
    """Pair each native sentence with its speaker. The native block is label-free by construction;
    its text is taken VERBATIM (NEVER re-parsed for labels — that would drop legitimate leading words
    like 'Supernova AI:'); speakers come only from the romanized labels, aligned by line position.
    Returns (turns, aligned). On a line-count mismatch (a manual native edit) it falls back to a
    continuous read with no speaker — deterministic, never guesses."""
    nlines = native.split("\n")
    rlines = roman.split("\n")
    aligned = bool(roman.strip()) and len(rlines) == len(nlines)
    has_labels = aligned and any(_split_label(r)[0] for r in rlines if r.strip())
    turns = []
    if aligned:
        for r, n in zip(rlines, nlines):
            text = BRACKET_RE.sub("", n).strip()    # native verbatim (minus bracket cues)
            if not text:
                continue
            speaker, _ = _split_label(r)            # speaker from the romanized label only
            if has_labels and not speaker:          # unlabelled line in a labelled script -> not voiced
                continue
            turns.append({"speaker": speaker or "", "text": text})
    else:
        for n in nlines:
            text = BRACKET_RE.sub("", n).strip()
            if text:
                turns.append({"speaker": "", "text": text})
    return turns, aligned


def cmd_playground_synth(out_path: str) -> int:
    """Real-time TTS synth for the "Translations" playground tab. Reads from stdin:
        {"language", "native" (label-free TTS script), "roman"? (for per-character mapping),
         "voices"? {character: {provider, voice_id}}, "voice_id"?, "speed"?, "emotion"? [..]}
    Writes an mp3 to --out, prints {"ok", ...}. With a voices map, each sentence is voiced by its
    character's voice and stitched into one continuous track (no labels are ever spoken); otherwise
    the whole block is read by one voice. speed/emotion are Cartesia sonic-3 controls (ignored by
    ElevenLabs)."""
    req = json.loads(sys.stdin.read() or "{}")
    language = (req.get("language") or "English").strip()
    native = req.get("native") or req.get("text") or ""
    roman = req.get("roman") or ""
    voice_id = (req.get("voice_id") or "").strip()
    voices_map = {str(k).lower(): v for k, v in (req.get("voices") or {}).items()
                  if isinstance(v, dict) and v.get("voice_id")}
    speed = (req.get("speed") or "").strip() or None
    emotion = req.get("emotion") or None
    if not native.strip():
        print(json.dumps({"ok": False, "error": "text is empty"}))
        return 1
    env = load_env()
    reg = load_registry()
    op = pathlib.Path(out_path)
    op.parent.mkdir(parents=True, exist_ok=True)
    turns, aligned = _playground_turns(roman, native)

    def _voice_for(spec: dict) -> dict:
        prov = (spec.get("provider") or "cartesia").lower()
        pdef = (reg.get("providers") or {}).get(prov, {})
        return {"provider": prov, "voice_id": spec["voice_id"],
                "model": pdef.get("model") or tts.DEFAULT_MODELS.get(prov),
                "settings": pdef.get("settings") or {}}

    MAX_TURNS = 100   # bound per-turn provider calls (an ad script is short; abuse/spend guard)
    if len(turns) > MAX_TURNS:
        print(json.dumps({"ok": False, "error": f"too many turns ({len(turns)} > {MAX_TURNS})"}))
        return 1

    warnings = []
    try:
        if voices_map and turns:
            # per-character casting: voice each sentence with its mapped voice (narrator fallback), stitch
            import shutil
            import tempfile
            narrator = resolve_voice(reg, language, "narrator")
            tmp = pathlib.Path(tempfile.mkdtemp(prefix="pg_synth_"))
            clips, used, matched = [], set(), set()
            try:
                for i, t in enumerate(turns):
                    key = t["speaker"].lower()
                    spec = voices_map.get(key) if key else None
                    if spec:
                        v = _voice_for(spec)
                        matched.add(key)
                    else:
                        v = narrator
                        if not v or not v.get("configured"):
                            raise tts.TTSConfigError(f"no configured narrator voice for {language}")
                    if not v.get("voice_id"):
                        raise tts.TTSConfigError(f"no voice for '{t['speaker']}' in {language}")
                    provider = tts.get_provider(v["provider"], env)
                    audio = provider.synth(t["text"], v["voice_id"], model=v.get("model"),
                                           language=language, settings=v.get("settings") or {},
                                           speed=speed, emotion=emotion)
                    clip = tmp / f"line_{i:03d}.mp3"
                    clip.write_bytes(audio)
                    clips.append(clip)
                    used.add(f"{v['provider']}:{v['voice_id']}")
                _stitch(clips, op)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            if not aligned:
                warnings.append("Native edits changed the line structure — voices couldn't be mapped "
                                "to speakers; narrator used. Re-run Update native to restore casting.")
            else:
                unmatched = [k for k in voices_map if k not in matched]
                if unmatched:
                    warnings.append("Cast voices not applied (no matching speaker): "
                                    + ", ".join(sorted(unmatched)))
            out = {"ok": True, "voices": sorted(used), "lines": len(clips)}
            if warnings:
                out["warning"] = " ".join(warnings)
            print(json.dumps(out, ensure_ascii=False))
            return 0

        # single-voice path: one voice reads the whole (label-free) block
        catalog = voice_catalog(reg)
        voice = catalog.get(voice_id) if voice_id else None
        if not voice:
            voice = resolve_voice(reg, language, "narrator")
        if not voice or not voice.get("configured"):
            print(json.dumps({"ok": False,
                              "error": f"no configured voice for {language} (narrator slot)"}))
            return 1
        speak = "\n".join(t["text"] for t in turns) if turns else BRACKET_RE.sub("", native).strip()
        speak = speak or native.strip()
        provider = tts.get_provider(voice["provider"], env)
        audio = provider.synth(speak, voice["voice_id"], model=voice["model"],
                               language=language, settings=voice["settings"],
                               speed=speed, emotion=emotion)
        op.write_bytes(audio)
        print(json.dumps({"ok": True, "provider": voice.get("provider"),
                          "voice_id": voice.get("voice_id"), "bytes": len(audio)}))
        return 0
    except (tts.TTSConfigError, tts.TTSError, RuntimeError) as ex:
        # RuntimeError covers ffmpeg/_stitch failures (e.g. a zero-byte clip) -> clean JSON, not a traceback
        print(json.dumps({"ok": False, "error": f"{type(ex).__name__}: {str(ex)[:200]}"}))
        return 1


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
    ap.add_argument("--setup", action="store_true", help="emit picker JSON (characters + voices)")
    ap.add_argument("--playground-native", action="store_true",
                    help="Translations tab: transliterate romanized -> native (stdin/stdout JSON)")
    ap.add_argument("--playground-synth", action="store_true",
                    help="Translations tab: synth one native-script block to --out mp3 (stdin JSON)")
    ap.add_argument("--out", help="output mp3 path for --playground-synth")
    ap.add_argument("--provider", choices=["elevenlabs", "cartesia"])
    ap.add_argument("--language", help="filter for --list-voices / target for --setup")
    ap.add_argument("--json", action="store_true", help="JSON output for --list-voices")
    args = ap.parse_args()

    if args.playground_native:
        return cmd_playground_native()
    if args.playground_synth:
        if not args.out:
            sys.exit("[error] --playground-synth needs --out PATH")
        return cmd_playground_synth(args.out)

    if args.list_voices:
        if not args.provider:
            sys.exit("[error] --list-voices needs --provider elevenlabs|cartesia")
        return cmd_list_voices(args.provider, args.language, as_json=args.json)

    if args.setup:
        if not args.ad_id or not args.language:
            sys.exit("[error] --setup needs <ad_id> --competitor X --language L")
        return cmd_setup(args.ad_id, args.competitor.lower().strip(), args.language)

    if not args.ad_id or not args.languages:
        sys.exit("[error] usage: step4_tts.py <ad_id> --competitor X --languages Hindi,Telugu")
    langs = [x.strip() for x in args.languages.split(",") if x.strip()]
    return cmd_tts(args.ad_id, args.competitor.lower().strip(), langs,
                   args.source, args.dry_run, args.regenerate)


if __name__ == "__main__":
    raise SystemExit(main())
