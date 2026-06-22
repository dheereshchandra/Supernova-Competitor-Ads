#!/usr/bin/env python3
"""
step4_localize.py — Workflow 2: replicate an APPROVED English Supernova master into
target Indian languages, reusing the SAME images (no regeneration).

Per ad + language:
  1. Resolve the English source — prefer the team-EDITED Google Doc (export its live
     text + unresolved comments = the source of truth); fall back to the committed
     <id>.supernova.json sidecar, flagging the fallback.
  2. Translate (Gemini FLASH, schema-constrained via _flash.generate_json) using the
     runtime rules doc facebook/generation/supernova_translation_rules.md.
  3. Brand-safety audit the localized script (reuse step4_safety_check.audit).
  4. Build the per-language .docx (reuses the ad's existing R2 images — the image-once
     guardrail means localization NEVER touches the image stages).
  5. Upload one Google Doc per language into the ad's Drive folder; record links in a
     `locales` map on <id>.gdocs.json (idempotent — never clobbers a Doc with comments).

Run from facebook/ (WORKSPACE-relative paths). Resume-safe: a per-language sidecar
<id>.<lang>.supernova.json is written; re-runs skip it unless --regenerate.

Usage:
    python3.13 scripts/step4_localize.py --competitor mysivi <ad_id> \
        --languages Hindi,Telugu [--source auto|gdoc|sidecar] [--dry-run] [--regenerate]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

WORKSPACE = pathlib.Path("step4_workspace")
SCENES_DIR = WORKSPACE / "scenes"
DOCS_DIR = WORKSPACE / "docs"

_HERE = pathlib.Path(__file__).resolve().parent
RULES_PATH = _HERE.parent / "generation" / "supernova_translation_rules.md"
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent.parent / "analysis" / "scripts"))
import _gdrive            # noqa: E402
import step4_safety_check as safety   # noqa: E402
import step4_build_docs as build_docs  # noqa: E402
import _flash             # noqa: E402
import _remarks           # noqa: E402
from r2_utils import load_env  # noqa: E402

SUPPORTED_LANGUAGES = ["Hindi", "Telugu", "Tamil", "Marathi", "Kannada", "Malayalam",
                       "Bengali", "Gujarati", "Assamese", "Punjabi"]

LOCALE_SCHEMA = {
    "type": "object",
    "properties": {
        "scenes": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "n": {"type": "integer"},
                "scene_label": {"type": "string"},
                # Two code-mixed forms of the SAME dialogue, for the 2-form TTS feed.
                "script_native": {"type": "string"},   # native script + English (Devanagari/Tamil/…)
                "script_roman": {"type": "string"},     # romanized Latin + English
            },
            "required": ["n", "scene_label", "script_native", "script_roman"],
        }},
        "self_critique_fixed": {"type": "string"},
    },
    "required": ["scenes", "self_critique_fixed"],
}


def load_rules() -> str:
    try:
        return RULES_PATH.read_text()
    except FileNotFoundError:
        sys.exit(f"[error] translation rules missing at {RULES_PATH}")


# ---------------------------------------------------------------- source resolution
def _extract_section(scene_body: str, start_marker: str) -> str:
    """Pull the lines under a heading (e.g. 'Supernova-voice script') until the next
    heading / separator inside one scene block of the exported Doc text."""
    idx = scene_body.find(start_marker)
    if idx < 0:
        return ""
    stops = ("On-screen text (Supernova version)", "Scene summary", "Brand swaps applied",
             "Provenance", "Supernova-voice script", "────", "──")
    out = []
    for line in scene_body[idx + len(start_marker):].splitlines()[1:]:
        s = line.strip()
        if not s:
            continue
        if any(s.startswith(m) for m in stops) or set(s) <= {"─", "-", " "}:
            break
        out.append(s)
    return "\n".join(out).strip()


def parse_doc_scenes(text: str) -> dict:
    """Parse exported Supernova Script Doc text back into {n: {script}} for the 3-zone layout:
    the 'Script' zone (after 'Same cast as above.') holds 'Scene N' headings, each followed by
    'Name says: …' dialogue lines, until the TTS / Provenance section or a separator. This lets the
    team's EDITS to the English Doc overlay the committed skeleton before localization."""
    start = text.find("Same cast as above.")
    if start < 0:
        m = re.search(r"(?m)^Script\s*$", text)
        start = m.start() if m else 0
    zone = text[start:]
    for stop in ("TTS input", "Provenance"):
        i = zone.find(stop)
        if i >= 0:
            zone = zone[:i]
    out = {}
    parts = re.split(r"(?m)^\s*Scene (\d+)\s*$", zone)
    for i in range(1, len(parts) - 1, 2):
        try:
            n = int(parts[i])
        except ValueError:
            continue
        lines = [s for ln in parts[i + 1].splitlines()
                 if (s := ln.strip()) and set(s) > {"─", "-", " "}]
        if lines:
            out[n] = {"script": "\n".join(lines)}
    return out


def parse_doc_script_lines(text: str) -> list:
    """Ordered dialogue lines in the 'Script' zone of an exported Supernova Doc, as a FLAT list — for the
    flowing (header-less) English master where the script is one continuous block with no 'Scene N'
    headings. Same zone bounds as parse_doc_scenes; skips separators / zone labels."""
    start = text.find("Same cast as above.")
    if start < 0:
        m = re.search(r"(?m)^Script\s*$", text)
        start = m.start() if m else 0
    zone = text[start:]
    for stop in ("TTS input", "Provenance"):
        i = zone.find(stop)
        if i >= 0:
            zone = zone[:i]
    out = []
    for ln in zone.splitlines():
        s = ln.strip()
        if not s or set(s) <= {"─", "-", " "}:
            continue
        if s in ("Same cast as above.", "Script", "English") or re.match(r"^Scene \d+$", s):
            continue
        out.append(s)
    return out


def overlay_doc_edits(scenes: list, doc_text: str) -> int:
    """Overlay the team's EDITED English Doc onto the per-scene skeleton (each {n, script, ...}).
    Two doc shapes are supported so the round-trip survives the move to a flowing master:
      • headed (legacy / localized docs): 'Scene N' headings → map edits per scene.
      • flowing English master (current): no scene headings → re-segment the edited Script zone back into
        scenes by each scene's committed line count (graceful: any extra lines append to the last spoken
        scene; if the team added/removed lines the grouping is approximate but no text is lost).
    Mutates scenes in place; returns how many scenes were overlaid."""
    headed = parse_doc_scenes(doc_text)
    if headed:
        applied = 0
        for sc in scenes:
            e = headed.get(sc.get("n"))
            if e and e.get("script"):
                sc["script"] = e["script"]
                applied += 1
        return applied
    flat = parse_doc_script_lines(doc_text)
    if not flat:
        return 0
    # Only scenes that actually rendered dialogue into the doc consume `flat` lines — use the SAME
    # predicate build_supernova_doc used (scene_scripts_in_order drops empty AND placeholder scenes such
    # as "[music only, no speech]"), so the committed per-scene line counts stay in lockstep with the
    # rendered line stream. (Counting a non-empty placeholder scene here would offset every later scene.)
    spoken = [sc for sc in scenes if not build_docs._is_placeholder_script(sc.get("script"))]
    i, applied = 0, 0
    for idx, sc in enumerate(spoken):
        count = len([l for l in (sc.get("script") or "").split("\n") if l.strip()])
        chunk = flat[i:i + count]
        i += count
        if idx == len(spoken) - 1 and i < len(flat):   # dump any remainder onto the last spoken scene
            chunk += flat[i:]
            i = len(flat)
        if chunk:
            sc["script"] = "\n".join(chunk)
            applied += 1
    return applied


def resolve_english_source(ad_id: str, prefer_gdoc: bool):
    """Return (skeleton, comments, source_label, decompose, competitor).
    skeleton = list of {n, scene_label, script, on_screen_text}: the committed structure
    with the team's EDITED Doc text overlaid per scene where confidently parsed."""
    sup_path = SCENES_DIR / f"{ad_id}.supernova.json"
    if not sup_path.exists():
        sys.exit(f"[error] no English rewrite sidecar {sup_path} — generate the master first.")
    sup = json.loads(sup_path.read_text())
    parsed = sup.get("parsed", {})
    skeleton = [{"n": s.get("n"), "scene_label": s.get("scene_label", ""),
                 "script": s.get("supernova_script", "")}
                for s in parsed.get("scenes", [])]
    dec_path = SCENES_DIR / f"{ad_id}.json"
    decompose = json.loads(dec_path.read_text()) if dec_path.exists() else {"parsed": {}}

    comments: list[str] = []
    source = "sidecar (committed English master)"
    gdocs_path = SCENES_DIR / f"{ad_id}.gdocs.json"
    if prefer_gdoc and gdocs_path.exists():
        fid = (json.loads(gdocs_path.read_text()).get("supernova_doc") or {}).get("file_id")
        if fid:
            try:
                svc = _gdrive.build_drive_service(load_env())
                applied = overlay_doc_edits(skeleton, _gdrive.export_doc_text(svc, fid))
                comments = _gdrive.list_unresolved_comments(svc, fid)
                source = (f"EDITED gdoc — {applied}/{len(skeleton)} scenes parsed, "
                          f"{len(comments)} unresolved comments"
                          + ("" if applied == len(skeleton)
                             else f"; {len(skeleton) - applied} scenes fell back to sidecar"))
            except Exception as ex:
                source = f"sidecar (gdoc read FAILED: {type(ex).__name__}: {str(ex)[:80]})"
    return skeleton, comments, source, decompose, sup.get("competitor", "")


# ---------------------------------------------------------------- translate + audit
def translate(client, target: str, skeleton: list, comments: list,
              production_type: str, seed_lang: str, *, source_lang: str = "English",
              model: str | None = None, allow_pro: bool = False,
              rules_override: str | None = None) -> dict:
    """Translate the source skeleton into code-mixed `target` (script_native + script_roman).

    Production localization always passes an ENGLISH master (source_lang stays "English"), so the
    header below is byte-identical to before. The ad-hoc Translations playground passes a non-English
    `source_lang` (the pasted script's language), an optional `model`/`allow_pro` (its model dropdown),
    and an optional `rules_override` (its editable-prompt box, used in-memory — the committed .md is
    never touched)."""
    rules = rules_override if rules_override is not None else load_rules()
    model = model or _flash.DEFAULT_MODEL
    if source_lang and source_lang.strip().lower() != "english":
        master_clause = f"the SOURCE SCRIPT below (written in {source_lang})"
        master_label = f"SOURCE SCRIPT ({source_lang}):"
    else:
        master_clause = "the APPROVED ENGLISH MASTER below"
        master_label = "ENGLISH MASTER:"
    header = f"""

================================================================================
=== THIS LOCALIZATION JOB ===
TARGET LANGUAGE: {target}. Apply the {target} language module + global rules above.
PRODUCTION TYPE: "{production_type}" — select the ONE matching FORMAT REGISTER module (§2).
SEED LANGUAGE of the original competitor ad: {seed_lang} (context only; output is {target}).

REVIEWER COMMENTS on the English Doc — BINDING instructions, follow them. If a comment asks
for something the brand-safety guardrails ban (e.g. a hard rupee price), IGNORE that one
comment and say so in self_critique_fixed:
{chr(10).join('- ' + c for c in comments) if comments else '(none)'}

Translate {master_clause} — scene-for-scene, line-for-line — into code-mixed
{target}. Output BOTH forms of every scene's dialogue (same words, same speaker labels 'Name says:',
one turn per line):
  - script_native : {target} in its NATIVE script + English keywords kept inline (code-mix).
  - script_roman  : the SAME, romanized in Latin letters + English keywords.
Keep '[music only, no speech]' scenes as-is. Same scene count and order.

{master_label}
"""
    contents = rules + header + json.dumps({"scenes": skeleton}, ensure_ascii=False)
    return _flash.generate_json(client, model, contents, temperature=0.4,
                                response_schema=LOCALE_SCHEMA, allow_pro=allow_pro)


def audit_text(translated: dict, decompose: dict) -> str:
    dec_scenes = {s.get("n"): s for s in decompose.get("parsed", {}).get("scenes", [])}
    lines = []
    for s in translated.get("scenes", []):
        n = s.get("n")
        lines.append(f"SCENE {n} — {s.get('scene_label', '')}")
        vd = (dec_scenes.get(n, {}) or {}).get("visual_description")
        if vd:
            lines.append(f"  [VISUAL — competitor source; brand swapped downstream, do NOT flag a "
                         f"competitor brand NAME only here] {vd}")
        script = (s.get("script_native") or s.get("script_roman")
                  or s.get("supernova_script") or s.get("script") or "")
        if script:
            lines.append(f"  [SCRIPT]\n{script}")
    return "\n".join(lines)


def to_rewrite_shape(translated: dict, english_skeleton: list, base_parsed: dict,
                     language: str = "", remarks: list | None = None) -> dict:
    """Adapt a translation into the rewrite shape build_supernova_doc expects.
    The visuals are identical to the English master, so reuse its format / visual_overview /
    per-scene brief (English context for the editor). The Script zone carries BOTH the English
    source line (`english_script`, from the same edited skeleton the translation was made from) and
    the NATIVE-script localized form (`supernova_script`) — the doc renders them as English + the
    target language per scene. The TTS block carries BOTH forms (romanized + native), labels stripped."""
    base_scenes = {s.get("n"): s for s in base_parsed.get("scenes", [])}
    skel_by_n = {sc.get("n"): (sc.get("script") or "") for sc in english_skeleton}
    scenes, roman_lines, native_lines = [], [], []
    for s in translated.get("scenes", []):
        n = s.get("n")
        native = s.get("script_native") or s.get("script") or ""
        roman = s.get("script_roman") or ""
        scenes.append({
            "n": n, "scene_label": s.get("scene_label", ""),
            "scene_brief": base_scenes.get(n, {}).get("scene_brief", ""),
            "supernova_script": native,
            "english_script": skel_by_n.get(n) or base_scenes.get(n, {}).get("supernova_script", ""),
        })
        native_lines += [sp for ln in native.split("\n") if (sp := build_docs._strip_speaker(ln))]
        roman_lines += [sp for ln in roman.split("\n") if (sp := build_docs._strip_speaker(ln))]
    return {"production_type": base_parsed.get("production_type", ""),
            "format": base_parsed.get("format", ""),
            "visual_overview": base_parsed.get("visual_overview", ""),
            "characters": base_parsed.get("characters", []),
            "language": language,
            "remarks": remarks or [],
            "scenes": scenes,
            "tts": {"romanized": roman_lines, "native": native_lines}}


# ---------------------------------------------------------------- per-language run
def localize_one(client, svc, env, ad_id, competitor, target, skeleton, comments,
                 decompose, base_parsed, seed_lang, folder_id, gdocs, dry_run, regenerate,
                 remarks=None):
    lang_key = target.lower()
    side_path = SCENES_DIR / f"{ad_id}.{lang_key}.supernova.json"
    if side_path.exists() and not regenerate:
        side = json.loads(side_path.read_text())
    else:
        print(f"  [{target}] translating (Flash)…", flush=True)
        translated = translate(client, target, skeleton, comments,
                               base_parsed.get("production_type", ""), seed_lang)
        verdict = safety.audit(client, audit_text(translated, decompose))
        side = {"ad_library_id": ad_id, "language": target, "parsed": translated,
                "safety": verdict, "remark": remarks or [],
                "model": _flash.DEFAULT_MODEL, "localized_at": time.time()}
        if not dry_run:
            side_path.write_text(json.dumps(side, indent=2, ensure_ascii=False))
        print(f"  [{target}] script OK — safety={verdict['verdict'].upper()} | "
              f"{side['parsed'].get('self_critique_fixed', '')[:80]}")

    # gdoc (idempotent via the locales map)
    locales = gdocs.setdefault("locales", {})
    link = (locales.get(lang_key) or {}).get("link")
    if link and not regenerate and not dry_run:
        return {"language": target, "verdict": side["safety"]["verdict"], "link": link, "reused": True}
    if dry_run:
        return {"language": target, "verdict": side["safety"]["verdict"], "link": "(dry-run)"}

    docx_path = DOCS_DIR / f"{ad_id}_{lang_key}_supernova_rewrite.docx"
    rewrite_shaped = {"parsed": to_rewrite_shape(side["parsed"], skeleton, base_parsed, target,
                                                 side.get("remark") or remarks)}
    build_docs.build_supernova_doc(ad_id, competitor, decompose, rewrite_shaped, docx_path,
                                   lambda m: None)
    title = f"{competitor.title()} {ad_id} — Supernova Rewrite ({target})"
    fid, link = _gdrive.upload_docx_as_gdoc(svc, env, docx_path, title, folder_id)
    _gdrive.set_link_permission(svc, env, fid)
    link = link or _gdrive.get_web_view_link(svc, fid)
    locales[lang_key] = {"file_id": fid, "link": link, "verified": False,
                         "verified_by": "", "localized_at": time.time()}
    return {"language": target, "verdict": side["safety"]["verdict"], "link": link}


def to_direct_shape(direct_parsed: dict, decompose_parsed: dict, language: str,
                    remarks: list | None = None) -> dict:
    """Adapt a DIRECT (no-English) sidecar's parsed into the rewrite shape build_supernova_doc expects.
    There is no English master, so `english_script` is "" — the doc then renders ONE flowing native-script
    block (no 'English' column, no per-scene headings). format/characters/visual_overview come from the
    direct parsed itself; the TTS block carries both romanized + native forms (labels stripped)."""
    dec_scenes = {s.get("n"): s for s in decompose_parsed.get("scenes", [])}
    scenes, roman_lines, native_lines = [], [], []
    for s in direct_parsed.get("scenes", []):
        n = s.get("n")
        native = s.get("script_native") or ""
        roman = s.get("script_roman") or ""
        scenes.append({
            "n": n,
            "scene_label": s.get("scene_label", "") or (dec_scenes.get(n, {}) or {}).get("scene_label", ""),
            "scene_brief": "",
            "supernova_script": native,
            "english_script": "",
        })
        native_lines += [sp for ln in native.split("\n") if (sp := build_docs._strip_speaker(ln))]
        roman_lines += [sp for ln in roman.split("\n") if (sp := build_docs._strip_speaker(ln))]
    return {"production_type": direct_parsed.get("production_type", ""),
            "format": direct_parsed.get("format", ""),
            "visual_overview": direct_parsed.get("visual_overview", ""),
            "characters": direct_parsed.get("characters", []),
            "language": language,
            "remarks": remarks or [],
            "scenes": scenes,
            "tts": {"romanized": roman_lines, "native": native_lines}}


def to_english_shape(eng_parsed: dict, remarks: list | None = None) -> dict:
    """Adapt an English-master parsed (scenes[].supernova_script) into the rewrite shape for a per-language
    English deliverable in direct mode — flowing English block (english_script=''), no TTS zone."""
    scenes = [{"n": s.get("n"), "scene_label": s.get("scene_label", ""),
               "scene_brief": s.get("scene_brief", ""),
               "supernova_script": s.get("supernova_script", ""), "english_script": ""}
              for s in eng_parsed.get("scenes", [])]
    return {"production_type": eng_parsed.get("production_type", ""),
            "format": eng_parsed.get("format", ""),
            "visual_overview": eng_parsed.get("visual_overview", ""),
            "characters": eng_parsed.get("characters", []),
            "language": "English",
            "remarks": remarks or [],
            "scenes": scenes,
            "tts": {}}


def direct_one(client, svc, env, ad_id, competitor, target, decompose, folder_id, gdocs,
               dry_run, remarks=None):
    """Build + upload a per-language Doc from a DIRECT sidecar (no English master). English reads the
    English-master sidecar <id>.supernova.json; other languages read <id>.<lang>.supernova.json."""
    lang_key = target.lower()
    is_english = (lang_key == "english")
    side_path = SCENES_DIR / (f"{ad_id}.supernova.json" if is_english
                              else f"{ad_id}.{lang_key}.supernova.json")
    if not side_path.exists():
        raise FileNotFoundError(f"no sidecar {side_path} — run step4_rewrite submit --target-languages first")
    side = json.loads(side_path.read_text())
    parsed = side.get("parsed", {})
    verdict = safety.audit(client, audit_text(parsed, decompose))
    side["safety"] = verdict
    if not dry_run:
        side_path.write_text(json.dumps(side, indent=2, ensure_ascii=False))
    print(f"  [{target}] {'english master' if is_english else 'direct sidecar'} OK — "
          f"safety={verdict['verdict'].upper()}")

    shaped = {"parsed": (to_english_shape(parsed, remarks) if is_english
                         else to_direct_shape(parsed, decompose.get("parsed", {}), target, remarks))}
    docx_path = DOCS_DIR / f"{ad_id}_{lang_key}_supernova_rewrite.docx"
    build_docs.build_supernova_doc(ad_id, competitor, decompose, shaped, docx_path, lambda m: None)
    if dry_run:
        return {"language": target, "verdict": verdict["verdict"], "link": "(dry-run)"}
    title = f"{competitor.title()} {ad_id} — Supernova Script ({target})"
    fid, link = _gdrive.upload_docx_as_gdoc(svc, env, docx_path, title, folder_id)
    _gdrive.set_link_permission(svc, env, fid)
    link = link or _gdrive.get_web_view_link(svc, fid)
    gdocs.setdefault("locales", {})[lang_key] = {"file_id": fid, "link": link, "verified": False,
                                                 "verified_by": "", "localized_at": time.time()}
    return {"language": target, "verdict": verdict["verdict"], "link": link}


def _cmd_direct(ad_id, competitor, languages, dry_run) -> int:
    """Direct seed→target: build per-language Docs from the direct sidecars (NO English master needed)."""
    competitor = (competitor or "").lower().strip()
    if not competitor:
        sys.exit("[error] --direct requires --competitor")
    dec_path = SCENES_DIR / f"{ad_id}.json"
    if not dec_path.exists():
        sys.exit(f"[error] no decompose sidecar {dec_path} — decompose the ad first")
    decompose = json.loads(dec_path.read_text())
    seed_lang = _seed_language(competitor, ad_id)
    remarks = _remarks.detect_remarks(decompose.get("parsed", {}), seed_lang)
    print(f"Direct docs {ad_id} ({competitor}) → {', '.join(languages)}  [no English master]")
    print(f"  seed language: {seed_lang}" + (f" | remarks: {' | '.join(remarks)}" if remarks else ""))
    env = load_env()
    client = _flash.get_client(env)
    svc = None if dry_run else _gdrive.build_drive_service(env)
    folder_id = None if dry_run else _gdrive.ensure_competitor_folder(svc, env, competitor, {})
    gdocs_path = SCENES_DIR / f"{ad_id}.gdocs.json"
    gdocs = json.loads(gdocs_path.read_text()) if gdocs_path.exists() else \
        {"ad_library_id": ad_id, "competitor": competitor}
    results = []
    for target in languages:
        try:
            results.append(direct_one(client, svc, env, ad_id, competitor, target, decompose,
                                      folder_id, gdocs, dry_run, remarks))
        except Exception as ex:
            print(f"  [{target}] FAILED — {type(ex).__name__}: {str(ex)[:140]}")
            results.append({"language": target, "verdict": "error", "link": "", "error": str(ex)})
    if not dry_run:
        gdocs_path.write_text(json.dumps(gdocs, indent=2, ensure_ascii=False))
    print("\nDONE:")
    for r in results:
        print(f"  {r['language']:<10} safety={str(r.get('verdict','?')).upper():<6} {r.get('link','')}")
    return 0 if all(r.get("verdict") != "error" for r in results) else 1


def cmd_localize(ad_id, competitor, languages, source_mode, dry_run, regenerate, direct=False) -> int:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    if direct:
        return _cmd_direct(ad_id, competitor, languages, dry_run)
    for lg in languages:
        if lg not in SUPPORTED_LANGUAGES:
            sys.exit(f"[error] unsupported language '{lg}'. One of: {', '.join(SUPPORTED_LANGUAGES)}")

    prefer_gdoc = source_mode in ("auto", "gdoc")
    skeleton, comments, source, decompose, comp_from_side = resolve_english_source(ad_id, prefer_gdoc)
    competitor = (competitor or comp_from_side or "").lower().strip()
    if source_mode == "gdoc" and not source.startswith("EDITED"):
        sys.exit(f"[error] --source gdoc requested but {source}")
    base_parsed = json.loads((SCENES_DIR / f"{ad_id}.supernova.json").read_text()).get("parsed", {})
    seed_lang = _seed_language(competitor, ad_id)
    # Deterministic ad-level reviewer remarks (English-original / no-voiceover). Same for every
    # language; shown in each Doc + the app + recorded on the per-language sidecar.
    remarks = _remarks.detect_remarks(decompose.get("parsed", {}), seed_lang)

    print(f"Localize {ad_id} ({competitor}) → {', '.join(languages)}")
    print(f"  English source: {source}")
    print(f"  seed language: {seed_lang} | scenes: {len(skeleton)}")
    if remarks:
        print(f"  remarks: {' | '.join(remarks)}")

    env = load_env()
    client = _flash.get_client(env)
    svc = None if dry_run else _gdrive.build_drive_service(env)
    folder_id = None if dry_run else _gdrive.ensure_competitor_folder(svc, env, competitor, {})

    gdocs_path = SCENES_DIR / f"{ad_id}.gdocs.json"
    gdocs = json.loads(gdocs_path.read_text()) if gdocs_path.exists() else \
        {"ad_library_id": ad_id, "competitor": competitor}

    results = []
    for target in languages:
        try:
            results.append(localize_one(client, svc, env, ad_id, competitor, target, skeleton,
                                        comments, decompose, base_parsed, seed_lang, folder_id,
                                        gdocs, dry_run, regenerate, remarks))
        except Exception as ex:
            print(f"  [{target}] FAILED — {type(ex).__name__}: {str(ex)[:140]}")
            results.append({"language": target, "verdict": "error", "link": "", "error": str(ex)})

    if not dry_run:
        gdocs_path.write_text(json.dumps(gdocs, indent=2, ensure_ascii=False))

    print("\nDONE:")
    for r in results:
        tag = "↻ reused" if r.get("reused") else ""
        print(f"  {r['language']:<10} safety={str(r.get('verdict','?')).upper():<6} {r.get('link','')} {tag}")
    return 0 if all(r.get("verdict") != "error" for r in results) else 1


def _seed_language(competitor: str, ad_id: str) -> str:
    enr = _HERE.parent.parent / "analysis" / "derived" / "facebook" / f"{competitor}_enriched.csv"
    if enr.exists():
        import csv
        csv.field_size_limit(10 ** 9)
        try:
            for r in csv.DictReader(enr.open(encoding="utf-8-sig")):
                if r.get("ad_id") == ad_id and (r.get("language") or "").strip():
                    return r["language"].strip()
        except Exception:
            pass
    return "unknown"


def cmd_playground() -> int:
    """Real-time, SYNCHRONOUS translate for the Ad Studio "Translations" playground tab.
    Reads a JSON request from stdin, prints a JSON result to stdout. Ephemeral — NO Drive/R2/
    safety audit/sidecars, NOT the job queue, NOT the Gemini Batch API.

      stdin : {"source_text": str, "source_language": str, "target_languages": [str],
               "model"?: str, "rules_override"?: str}
      stdout: {"results": [{"language", "script_roman", "script_native",
                            "self_critique_fixed", "error"?}], "model": str}
    """
    import concurrent.futures as _fut
    req = json.loads(sys.stdin.read() or "{}")
    source_text = (req.get("source_text") or "").strip()
    source_lang = (req.get("source_language") or "English").strip()
    targets = [t.strip() for t in (req.get("target_languages") or []) if t and t.strip()]
    model = (req.get("model") or _flash.DEFAULT_MODEL).strip()
    rules_override = req.get("rules_override") or None
    if not source_text or not targets:
        print(json.dumps({"results": [], "model": model,
                          "error": "source_text and target_languages are required"}))
        return 1
    allow_pro = "pro" in model.lower()   # the playground is the one sanctioned Pro path
    env = load_env()
    client = _flash.get_client(env)
    skeleton = [{"n": 1, "scene_label": "Script", "script": source_text}]

    def _one(target: str) -> dict:
        if target.strip().lower() == source_lang.lower():
            return {"language": target, "error": "source and target language are the same"}
        try:
            tr = translate(client, target, skeleton, [], "", source_lang,
                           source_lang=source_lang, model=model, allow_pro=allow_pro,
                           rules_override=rules_override)
            scenes = tr.get("scenes", [])
            roman = "\n\n".join((s.get("script_roman") or "").strip() for s in scenes).strip()
            native = "\n\n".join((s.get("script_native") or "").strip() for s in scenes).strip()
            return {"language": target, "script_roman": roman, "script_native": native,
                    "self_critique_fixed": tr.get("self_critique_fixed", "")}
        except Exception as ex:   # noqa: BLE001
            return {"language": target, "error": f"{type(ex).__name__}: {str(ex)[:200]}"}

    with _fut.ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
        results = list(pool.map(_one, targets))
    print(json.dumps({"results": results, "model": model}, ensure_ascii=False))
    return 0


def main() -> int:
    if "--playground" in sys.argv:   # real-time synchronous Translations-tab path
        return cmd_playground()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ad_id")
    ap.add_argument("--competitor", default="")
    ap.add_argument("--languages", required=True, help="comma-separated, e.g. Hindi,Telugu")
    ap.add_argument("--source", choices=["auto", "gdoc", "sidecar"], default="auto",
                    help="auto = edited gdoc if present else sidecar (default)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--regenerate", action="store_true",
                    help="re-translate + re-create Docs even if they already exist")
    ap.add_argument("--direct", action="store_true",
                    help="DIRECT seed→target mode: build per-language Docs from the <id>.<lang>.supernova.json "
                         "sidecars written by `step4_rewrite submit --target-languages` (NO English master).")
    args = ap.parse_args()
    langs = [x.strip() for x in args.languages.split(",") if x.strip()]
    return cmd_localize(args.ad_id, args.competitor, langs, args.source,
                        args.dry_run, args.regenerate, args.direct)


if __name__ == "__main__":
    raise SystemExit(main())
