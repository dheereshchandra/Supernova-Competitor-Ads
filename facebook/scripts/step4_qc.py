#!/usr/bin/env python3
"""
step4_qc.py — QC linter + gate for generated Supernova scripts.

Catches the recurring post-pipeline defects that the LLM brand-safety auditor and the
docx structural verifier miss, on BOTH the English master (<id>.supernova.json) and the
localized / direct sidecars (<id>.<lang>.supernova.json, <id>.<lang>.direct.supernova.json):

  BLOCK (gate — real bugs in the deliverable):
    MISS_NOVA_SPOKEN        the character name "Miss Nova" appears INSIDE a spoken line (it is a
                            speaker LABEL only; in the VO she is "I"/"me", others say "an AI teacher").
    PLACEHOLDER_SPOKEN      a "[music only, no speech]" / "[scene needs manual edit]" placeholder
                            leaked into the script as a spoken "Name says: [...]" line.
    SPEAKER_ROLE_INVERSION  (LLM) in a grammar-correction ad, the AI teacher voices the learner's
                            wrong-English mistake instead of correcting it. High confidence → block.
  FLAG (review — non-gating, surfaced for a human):
    BANNED_PHRASE           "out loud" / "loudly" / "mother tongue" / "ASMR".
    CLAIM_VALUE             a time-to-result claim that is not "30 days".
    BRAND_FULLNAME          bare "Supernova" not followed by "AI".
    SPEAKER_ROLE_INVERSION  medium-confidence inversion → flag (low → ignored).

Deterministic checks run on the spoken portion only (after the "Name says:" label), on the English
`supernova_script` and the romanized `script_roman` (native script mirrors the Latin strings). The
role-inversion check is ONE Gemini Flash call per sidecar comparing the decompose's original diarized
turns vs the rewrite (skip with --no-llm).

Writes step4_workspace/scenes/<id>.qc.json {verdict: pass|flag|block, issues, checked, at}.
Exit 2 if any BLOCK issue is found (so it can gate a pipeline step); else 0.

Usage (run from facebook/):
  python3 scripts/step4_qc.py <id> [<id>...]                  # every sidecar for these ids + qc.json
  python3 scripts/step4_qc.py <id> --competitor mysivi         # (competitor is informational)
  python3 scripts/step4_qc.py <id> --lang Telugu               # one localized sidecar
  python3 scripts/step4_qc.py --all                            # every *.supernova.json sidecar
  python3 scripts/step4_qc.py <id> --no-llm                    # deterministic checks only (no spend)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import re

HERE = pathlib.Path(__file__).resolve().parent          # facebook/scripts
ROOT = HERE.parent.parent                               # repo root
SCENES = pathlib.Path("step4_workspace") / "scenes"

sys.path.insert(0, str(HERE))
import _remarks  # noqa: E402  (ad-level no-voiceover / English-original remarks; single source of truth)

# "Name says: <spoken>" -> "<spoken>"; a non-dialogue line passes through unchanged.
_SAYS = re.compile(r"^.{1,40}?\bsays:\s*(.*)$")

def speech_of(line: str) -> str:
    line = line.strip()
    m = _SAYS.match(line)
    return (m.group(1).strip() if m else line)

_MISS_NOVA = re.compile(r"\bmiss\s*nova\b", re.I)
_PLACEHOLDER = re.compile(r"\[\s*(?:music only|no speech|scene needs manual edit)[^\]]*\]", re.I)
_BARE_BRAND = re.compile(r"\bsupernova\b(?!\s*ai\b)", re.I)   # "Supernova" not followed by "AI"
_DAYS = re.compile(r"\b(\d+)\s*days?\b", re.I)
_BANNED = [
    (re.compile(r"\bout\s*loud\b", re.I), "out loud (use speaking practice)"),
    (re.compile(r"\bloudly\b", re.I), "loudly (use speaking practice)"),
    (re.compile(r"\bmother[\s-]*tongue\b", re.I), "mother tongue (name the language plainly)"),
    (re.compile(r"\byour own language\b", re.I), "'your own language' (name the language plainly)"),
    (re.compile(r"\bASMR\b", re.I), "ASMR mentioned in script"),
]

_SEV = {
    "MISS_NOVA_SPOKEN": "block", "PLACEHOLDER_SPOKEN": "block",
    "BANNED_PHRASE": "flag", "CLAIM_VALUE": "flag", "BRAND_FULLNAME": "flag",
    "NO_VOICEOVER": "flag", "INTERACTION_PATTERN_DRIFT": "flag", "HOOK_DRIFT": "flag",
}


# --------------------------------------------------------------------------- deterministic
def lint_lines(lines: list[str], where: str) -> list[dict]:
    out = []
    def add(code, detail):
        out.append({"severity": _SEV[code], "code": code, "where": where, "detail": detail})
    for raw in lines:
        sp = speech_of(raw)
        if not sp:
            continue
        snip = raw.strip()[:90]
        if _MISS_NOVA.search(sp):
            add("MISS_NOVA_SPOKEN", f'"Miss Nova" spoken in VO → {snip}')
        if _PLACEHOLDER.search(sp):
            add("PLACEHOLDER_SPOKEN", f'placeholder rendered as speech → {snip}')
        for rx, msg in _BANNED:
            if rx.search(sp):
                add("BANNED_PHRASE", f"{msg} → {snip}")
        for m in _DAYS.finditer(sp):
            if m.group(1) != "30":
                add("CLAIM_VALUE", f'time claim "{m.group(0)}" should be "30 days" → {snip}')
        if _BARE_BRAND.search(sp):
            add("BRAND_FULLNAME", f'bare "Supernova" (use "Supernova AI") → {snip}')
    return out


def lint_sidecar(path: pathlib.Path) -> tuple[str, list[dict]]:
    """Return (language, issues) for one sidecar — deterministic checks only."""
    data = json.loads(path.read_text())
    parsed = data.get("parsed", {})
    lang = data.get("language", "English")
    issues: list[dict] = []
    for sc in parsed.get("scenes", []):
        n = sc.get("n", "?")
        for key in ("supernova_script", "script_roman"):
            txt = sc.get(key)
            if txt:
                issues += lint_lines(txt.split("\n"), f"{path.name} · scene {n} · {key}")
    return lang, issues


# --------------------------------------------------------------------------- LLM role check
_FLASH = {"client": None, "tried": False}

def _flash_client():
    """Lazily build a Gemini Flash client; None if unavailable (keeps deterministic lint dependency-free)."""
    if _FLASH["tried"]:
        return _FLASH["client"]
    _FLASH["tried"] = True
    try:
        sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
        import _flash  # noqa: E402
        _FLASH["mod"] = _flash
        _FLASH["client"] = _flash.get_client(_flash.find_env(ROOT, "facebook"))
    except Exception as e:
        print(f"[qc] LLM role-check unavailable ({type(e).__name__}: {str(e)[:80]}) — skipping it", file=sys.stderr)
        _FLASH["client"] = None
    return _FLASH["client"]

_ROLE_SCHEMA = {
    "type": "object",
    "properties": {
        "applicable": {"type": "boolean"},
        "inverted": {"type": "boolean"},
        "confidence": {"type": "string"},   # high | medium | low
        "evidence": {"type": "string"},
        "pattern_changed": {"type": "boolean"},
        "pattern_confidence": {"type": "string"},   # high | medium | low
        "pattern_desc": {"type": "string"},
        "hook_drifted": {"type": "boolean"},
        "hook_confidence": {"type": "string"},   # high | medium | low
        "hook_desc": {"type": "string"},
    },
    "required": ["applicable", "inverted", "confidence", "evidence",
                 "pattern_changed", "pattern_confidence", "pattern_desc",
                 "hook_drifted", "hook_confidence", "hook_desc"],
}

_ROLE_PROMPT = """You are a QC check for a re-skinned spoken-English ad. The ORIGINAL is a competitor ad
(in its seed language); the REWRITE is our Supernova version. In a GRAMMAR-CORRECTION ad, a human LEARNER
says a WRONG-English phrase (the mistake) and the AI TEACHER corrects it. In our rewrite the AI teacher's
speaker label is "Miss Nova".

TASK 1 — role inversion: in the REWRITE, did the roles get INVERTED — i.e. does the AI teacher (Miss Nova)
end up SAYING the learner's wrong-English mistake as her own line (e.g. Miss Nova says "I am having two
brothers" or "I am adding oil"), instead of the learner saying it and Miss Nova correcting it? Set
applicable=false, inverted=false if there is no wrong-English-correction beat (e.g. a monologue). Be
conservative: inverted=true only with high confidence when you can quote the AI teacher speaking the mistake.

TASK 2 — interaction-pattern drift: did the REWRITE change the ad's TEACHING MECHANIC (what the LEARNER is
doing) compared to the ORIGINAL? Examples of drift: a repeat-after-me DRILL (teacher SAYS a phrase, learner
ECHOES it back) became a QUIZ (teacher ASKS, learner ANSWERS correctly on her own); a struggling beginner now
produces fluent correct English; a live correction became a testimonial. Set pattern_changed=true ONLY if the
CATEGORY of what the learner does changed (be conservative); give pattern_confidence (high|medium|low) and
pattern_desc (one line: 'original mechanic → rewrite mechanic'). If unchanged, pattern_changed=false,
pattern_confidence="low", pattern_desc="".

TASK 3 — hook fidelity: compare the FIRST line of the REWRITE to the FIRST line of the ORIGINAL (the hook /
thumbstop). Did the opener's CLAIM / FRAMING change — i.e. WHAT it asserts? Drift examples: "not able to
speak English" / "don't know English" became "afraid / scared to speak", "can't speak", or a different
question; or the brand's fear / no-judgement angle got front-loaded into the opener. A faithful TRANSLATION
into the target language and the brand swap are NOT drift. Set hook_drifted=true ONLY if the opener's
meaning/claim moved (be conservative; the inability↔fear↔not-knowing axis matters most); give hook_confidence
(high|medium|low) and hook_desc (one line: 'original hook claim → rewrite hook claim'). If faithful,
hook_drifted=false, hook_confidence="low", hook_desc="".

Return JSON with all of: applicable, inverted, confidence, evidence (Task 1); pattern_changed,
pattern_confidence, pattern_desc (Task 2); hook_drifted, hook_confidence, hook_desc (Task 3).
"""

def check_role_inversion(decompose_parsed: dict, rewrite_parsed: dict, lang: str, where: str) -> list[dict]:
    client = _flash_client()
    if client is None:
        return []
    chars = "; ".join(f"{c.get('id')}={c.get('role','')}" for c in decompose_parsed.get("characters", []))
    pattern = (decompose_parsed.get("interaction_pattern") or "").strip()
    orig = [f"Scene {s.get('n')}: {(s.get('audio_transcript') or '').strip()}"
            for s in decompose_parsed.get("scenes", []) if (s.get("audio_transcript") or "").strip()]
    rew = [f"Scene {s.get('n')}: {((s.get('script_roman') or s.get('supernova_script')) or '').strip()}"
           for s in rewrite_parsed.get("scenes", []) if ((s.get('script_roman') or s.get('supernova_script')) or '').strip()]
    if not orig or not rew:
        return []
    prompt = (_ROLE_PROMPT + f"\nCHARACTER ROLES (original): {chars}\n"
              + (f"ORIGINAL interaction_pattern (from decompose): {pattern}\n" if pattern else "")
              + f"\nORIGINAL (competitor, seed language):\n" + "\n".join(orig) +
              f"\n\nREWRITE (Supernova, {lang}):\n" + "\n".join(rew))
    try:
        res = _FLASH["mod"].generate_json(client, _FLASH["mod"].DEFAULT_MODEL, prompt,
                                          temperature=0.0, response_schema=_ROLE_SCHEMA)
    except Exception as e:
        print(f"[qc] role-check call failed ({type(e).__name__}) — skipping", file=sys.stderr)
        return []
    findings: list[dict] = []
    # Task 1 — role inversion
    conf = (res.get("confidence") or "").lower()
    if res.get("applicable") and res.get("inverted") and conf in ("high", "medium"):
        findings.append({"severity": "block" if conf == "high" else "flag",
                         "code": "SPEAKER_ROLE_INVERSION", "where": where,
                         "detail": f'AI teacher voices the learner\'s mistake ({conf}) → {res.get("evidence","")[:120]}'})
    # Task 2 — interaction-pattern drift (non-gating FLAG; conservative)
    pconf = (res.get("pattern_confidence") or "").lower()
    if res.get("pattern_changed") and pconf in ("high", "medium"):
        findings.append({"severity": "flag", "code": "INTERACTION_PATTERN_DRIFT", "where": where,
                         "detail": f'teaching mechanic changed ({pconf}) → {res.get("pattern_desc","")[:160]}'})
    # Task 3 — hook-claim drift (non-gating FLAG; conservative)
    hconf = (res.get("hook_confidence") or "").lower()
    if res.get("hook_drifted") and hconf in ("high", "medium"):
        findings.append({"severity": "flag", "code": "HOOK_DRIFT", "where": where,
                         "detail": f'hook claim changed ({hconf}) → {res.get("hook_desc","")[:160]}'})
    return findings


# --------------------------------------------------------------------------- aggregation
def compute_verdict(issues: list[dict]) -> str:
    sev = {i["severity"] for i in issues}
    return "block" if "block" in sev else ("flag" if "flag" in sev else "pass")


def ad_id_of(path: pathlib.Path) -> str:
    return path.name.split(".")[0]


def lint_ad(ad_id: str, paths: list[pathlib.Path], use_llm: bool) -> dict:
    """Lint every sidecar for one ad; write <id>.qc.json; return the verdict record."""
    dec_path = SCENES / f"{ad_id}.json"
    decompose = json.loads(dec_path.read_text()).get("parsed", {}) if dec_path.exists() else {}
    issues: list[dict] = []
    checked: list[str] = []
    remarks: list[str] = []
    # Ad-level: no-voiceover / synthetic-VO reviewer note (deterministic, no LLM). The direct path
    # bypasses step4_localize (the other caller of detect_remarks), so surface it here — a non-gating
    # FLAG that names the audio (song/music) and notes the script came from on-screen text.
    if decompose and _remarks.is_no_voiceover(decompose):
        note = _remarks.no_voiceover_remark(decompose)
        issues.append({"severity": "flag", "code": "NO_VOICEOVER",
                       "where": f"{ad_id} (ad-level)", "detail": note})
        remarks.append(note)
    for p in paths:
        lang, det = lint_sidecar(p)
        issues += det
        if use_llm and decompose:
            issues += check_role_inversion(decompose, json.loads(p.read_text()).get("parsed", {}),
                                            lang, p.name)
        checked.append(lang)
    rec = {"ad_id": ad_id, "verdict": compute_verdict(issues), "issues": issues,
           "remarks": remarks, "checked": checked, "at": time.time()}
    (SCENES / f"{ad_id}.qc.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--lang", default=None)
    ap.add_argument("--langs", default=None,
                    help="comma list — lint ONLY these languages' sidecars (scopes out stale English "
                         "masters / other-language / prototype .direct. sidecars). 'English' = the master.")
    ap.add_argument("--competitor", default=None, help="informational (env is auto-resolved)")
    ap.add_argument("--no-llm", action="store_true", help="deterministic checks only (no Flash spend)")
    args = ap.parse_args()

    langs = [l.strip().lower() for l in (args.langs or "").split(",") if l.strip()]
    if args.all:
        paths = sorted(SCENES.glob("*.supernova.json"))
    else:
        paths = []
        for ad in args.ids:
            if args.lang:                                # single language (legacy)
                paths += list(SCENES.glob(f"{ad}.{args.lang.lower()}*.supernova.json"))
            elif langs:                                  # scoped to the job's languages — exact match only
                for L in langs:
                    p = SCENES / (f"{ad}.supernova.json" if L == "english" else f"{ad}.{L}.supernova.json")
                    if p.exists():
                        paths.append(p)
            else:                                        # everything for the ad (may include stale masters)
                paths += sorted(SCENES.glob(f"{ad}*.supernova.json"))
    if not paths:
        sys.exit("[error] no sidecars to lint (pass ad ids or --all)")

    # group by ad so we write one <id>.qc.json per ad
    by_ad: dict[str, list[pathlib.Path]] = {}
    for p in paths:
        by_ad.setdefault(ad_id_of(p), []).append(p)

    any_block = False
    for ad_id, ps in by_ad.items():
        rec = lint_ad(ad_id, ps, use_llm=not args.no_llm)
        blocks = [i for i in rec["issues"] if i["severity"] == "block"]
        flags = [i for i in rec["issues"] if i["severity"] == "flag"]
        any_block = any_block or bool(blocks)
        icon = {"block": "⛔", "flag": "⚠️ ", "pass": "✅"}[rec["verdict"]]
        print(f"{icon} {ad_id} — {rec['verdict'].upper()} ({len(blocks)} block, {len(flags)} flag; "
              f"langs: {', '.join(rec['checked'])})")
        for i in rec["issues"]:
            print(f"     [{i['severity'].upper():<5}] {i['code']}: {i['detail']}")

    print(f"\nDONE — {len(by_ad)} ad(s) checked; wrote <id>.qc.json")
    return 2 if any_block else 0


if __name__ == "__main__":
    raise SystemExit(main())
