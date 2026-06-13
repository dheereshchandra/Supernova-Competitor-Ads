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
                "script": {"type": "string"},
                "on_screen_text": {"type": "string"},
            },
            "required": ["n", "scene_label", "script", "on_screen_text"],
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
    """Parse exported Supernova-rewrite Doc text back into {n: {script, on_screen_text}}.
    Anchors on the stable 'Scene N — …' headings the docx builder writes."""
    parts = re.split(r"(?m)^Scene (\d+)\s+[—–-]\s+", text)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        try:
            n = int(parts[i])
        except ValueError:
            continue
        body = parts[i + 1]
        out[n] = {"script": _extract_section(body, "Supernova-voice script"),
                  "on_screen_text": _extract_section(body, "On-screen text (Supernova version)")}
    return out


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
                 "script": s.get("supernova_script", ""),
                 "on_screen_text": s.get("supernova_on_screen_text", "")}
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
                edited = parse_doc_scenes(_gdrive.export_doc_text(svc, fid))
                applied = 0
                for sc in skeleton:
                    e = edited.get(sc["n"])
                    if e and e.get("script"):
                        sc["script"] = e["script"]
                        if e.get("on_screen_text"):
                            sc["on_screen_text"] = e["on_screen_text"]
                        applied += 1
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
              production_type: str, seed_lang: str) -> dict:
    rules = load_rules()
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

Translate the APPROVED ENGLISH MASTER below — scene-for-scene, line-for-line — into romanized,
code-mixed {target}. Keep '[music only, no speech]' scenes as-is. Same scene count and order.

ENGLISH MASTER:
"""
    contents = rules + header + json.dumps({"scenes": skeleton}, ensure_ascii=False)
    return _flash.generate_json(client, _flash.DEFAULT_MODEL, contents,
                                temperature=0.4, response_schema=LOCALE_SCHEMA)


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
        if s.get("script"):
            lines.append(f"  [SCRIPT]\n{s['script']}")
        if (s.get("on_screen_text") or "").strip():
            lines.append(f"  [ON-SCREEN] {s['on_screen_text']}")
    return "\n".join(lines)


def to_rewrite_shape(translated: dict, english_skeleton: list, base_parsed: dict) -> dict:
    """Adapt a translation into the rewrite shape build_supernova_doc expects."""
    summ = {s["n"]: s for s in english_skeleton}
    scenes = [{
        "n": s.get("n"), "scene_label": s.get("scene_label", ""),
        "supernova_script": s.get("script", ""),
        "scene_summary": "",
        "supernova_on_screen_text": s.get("on_screen_text", ""),
    } for s in translated.get("scenes", [])]
    return {"production_type": base_parsed.get("production_type", ""),
            "characters": base_parsed.get("characters", []),
            "scenes": scenes,
            "payload_audit": {}, "brand_swaps_detected": []}


# ---------------------------------------------------------------- per-language run
def localize_one(client, svc, env, ad_id, competitor, target, skeleton, comments,
                 decompose, base_parsed, seed_lang, folder_id, gdocs, dry_run, regenerate):
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
                "safety": verdict, "model": _flash.DEFAULT_MODEL, "localized_at": time.time()}
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
    rewrite_shaped = {"parsed": to_rewrite_shape(side["parsed"], skeleton, base_parsed)}
    build_docs.build_supernova_doc(ad_id, competitor, decompose, rewrite_shaped, docx_path,
                                   lambda m: None)
    title = f"{competitor.title()} {ad_id} — Supernova Rewrite ({target})"
    fid, link = _gdrive.upload_docx_as_gdoc(svc, env, docx_path, title, folder_id)
    _gdrive.set_link_permission(svc, env, fid)
    link = link or _gdrive.get_web_view_link(svc, fid)
    locales[lang_key] = {"file_id": fid, "link": link, "verified": False,
                         "verified_by": "", "localized_at": time.time()}
    return {"language": target, "verdict": side["safety"]["verdict"], "link": link}


def cmd_localize(ad_id, competitor, languages, source_mode, dry_run, regenerate) -> int:
    for lg in languages:
        if lg not in SUPPORTED_LANGUAGES:
            sys.exit(f"[error] unsupported language '{lg}'. One of: {', '.join(SUPPORTED_LANGUAGES)}")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    prefer_gdoc = source_mode in ("auto", "gdoc")
    skeleton, comments, source, decompose, comp_from_side = resolve_english_source(ad_id, prefer_gdoc)
    competitor = (competitor or comp_from_side or "").lower().strip()
    if source_mode == "gdoc" and not source.startswith("EDITED"):
        sys.exit(f"[error] --source gdoc requested but {source}")
    base_parsed = json.loads((SCENES_DIR / f"{ad_id}.supernova.json").read_text()).get("parsed", {})
    seed_lang = _seed_language(competitor, ad_id)

    print(f"Localize {ad_id} ({competitor}) → {', '.join(languages)}")
    print(f"  English source: {source}")
    print(f"  seed language: {seed_lang} | scenes: {len(skeleton)}")

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
                                        gdocs, dry_run, regenerate))
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


def main() -> int:
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
    args = ap.parse_args()
    langs = [x.strip() for x in args.languages.split(",") if x.strip()]
    return cmd_localize(args.ad_id, args.competitor, langs, args.source,
                        args.dry_run, args.regenerate)


if __name__ == "__main__":
    raise SystemExit(main())
