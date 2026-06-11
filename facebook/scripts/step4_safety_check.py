#!/usr/bin/env python3
"""
Step 4 — Brand-safety audit of the Supernova rewrite (feedback item #5).

An INDEPENDENT adversarial pass: for each ad it reads the Supernova rewrite (script + on-screen
text) plus the decompose visuals, audits them against facebook/generation/supernova_brand_safety.md,
and writes a verdict sidecar  step4_workspace/scenes/<id>.safety.json:

    {"verdict": "pass|flag|block", "violations": [ {guardrail_id, category, severity, scene,
      quote, why, fix}, ... ], "summary": "..."}

The verdict is computed DETERMINISTICALLY from the violation severities (any SEVERE -> block; else any
MODERATE -> flag; else pass) — the model only has to detect violations accurately, not label the verdict.

Runs on Gemini **Flash** (this is classification/audit, not creative generation — Flash-only, cheap).
It is a SEPARATE pass, not the generator grading itself, which is far more reliable.

Sub-commands:
    check   --competitor <slug> [<ids...> | --all]   audit rewrite sidecars, write <id>.safety.json
    demo                                             audit a built-in clean + unsafe sample, print verdicts
    status  [--competitor <slug>]                    list existing verdicts

Usage:
    python3.13 facebook/scripts/step4_safety_check.py demo
    python3.13 facebook/scripts/step4_safety_check.py check --competitor mysivi <ids...>
    python3.13 facebook/scripts/step4_safety_check.py check --competitor mysivi --all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # facebook/scripts
FB = HERE.parent                                # facebook
ROOT = FB.parent                                # repo root
SCENES_DIR = FB / "step4_workspace" / "scenes"
SAFETY_DOC = FB / "generation" / "supernova_brand_safety.md"

sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
import _flash  # noqa: E402  (shared Flash helper; enforces Flash-only + valid-JSON via response_schema)

MODEL = _flash.DEFAULT_MODEL

SAFETY_SCHEMA = {
    "type": "object",
    "properties": {
        "violations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "guardrail_id": {"type": "string"},
                    "category": {"type": "string"},
                    "severity": {"type": "string"},   # "severe" | "moderate"
                    "scene": {"type": "string"},
                    "quote": {"type": "string"},
                    "why": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["guardrail_id", "category", "severity", "scene", "quote", "why", "fix"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["violations", "summary"],
}

AUDIT_INSTRUCTIONS = """

================================================================================
YOU ARE AN INDEPENDENT BRAND-SAFETY & AD-POLICY AUDITOR FOR SUPERNOVA.

Everything above is Supernova's brand-safety policy (the rubric). Below (after AD) is a GENERATED
Supernova ad — its per-scene script, on-screen text, and visual descriptions.

Audit the ad AGAINST the policy. Find EVERY real violation. For each, output an object:
  - guardrail_id : the policy id, e.g. "G6.1"
  - category     : the section name, e.g. "Price & financial"
  - severity     : "severe" or "moderate" (use the tag on that guardrail)
  - scene        : which scene/line it is in (e.g. "Scene 3" or "on-screen text")
  - quote        : the EXACT offending text, verbatim
  - why          : one sentence on why it violates that guardrail
  - fix          : a concrete one-line rewrite that resolves it

Be STRICT but PRECISE: report only genuine violations, and always quote the exact text. Do NOT invent
violations to look thorough, and do NOT flag on-brand creative choices that the policy explicitly allows
(ChatGPT contrast, comparative cost, "1 crore+ users", absurdist fiction, a relatable self-diagnosed
error, a shame hook that resolves in dignity). A competitor BRAND NAME or LOGO that appears ONLY in a
[VISUAL] line (never in [SCRIPT] or [ON-SCREEN]) is an expected downstream re-branding artifact — only
the brand name/logo is swapped — so do NOT flag a competitor brand name that appears only there. (DO
still flag any NON-brand problem in a [VISUAL] line — fake UI, countdown timers, government seals,
military/political imagery — the rest of the visual shell ships as-is.) If the ad is clean, return an
empty violations array.
Also return a one-line `summary`. Do NOT output a verdict — the pipeline computes it from severities.

AD:
"""


def load_safety() -> str:
    try:
        return SAFETY_DOC.read_text()
    except FileNotFoundError:
        sys.exit(f"[error] brand-safety policy missing at {SAFETY_DOC}")


def compute_verdict(violations: list) -> str:
    sev = {(v.get("severity") or "").strip().lower() for v in violations}
    if "severe" in sev:
        return "block"
    if "moderate" in sev:
        return "flag"
    return "pass"


def audit(client, ad_text: str) -> dict:
    """One Flash call. Returns {verdict, violations, summary}, verdict recomputed in code.

    The one real false positive — the auditor flagging a competitor brand-name/logo that survives only
    in the PRESERVED [VISUAL] line (e.g. "the Praktika logo is displayed") — is handled entirely at the
    PROMPT level: ad_text_from_sidecars labels that line "[VISUAL — competitor source … do NOT flag a
    competitor brand NAME that appears ONLY here]" and AUDIT_INSTRUCTIONS repeats the rule (while still
    requiring any NON-brand visual problem to be flagged). There is deliberately NO deterministic
    post-filter: a brand-safety gate must never risk dropping a genuine violation, so the conservative
    failure mode here is a (rare) false BLOCK a human reviews — never a false PASS."""
    prompt = load_safety() + AUDIT_INSTRUCTIONS + ad_text
    res = _flash.generate_json(client, MODEL, prompt, temperature=0.0,
                               response_schema=SAFETY_SCHEMA)
    violations = res.get("violations", []) or []
    return {
        "verdict": compute_verdict(violations),
        "violations": violations,
        "summary": res.get("summary", ""),
        "model": MODEL,
    }


def ad_text_from_sidecars(ad_id: str) -> str | None:
    """Build the audit input from the rewrite sidecar (+ decompose visuals if present).

    The competitor's preserved visual_description is included as a LABELLED [VISUAL] line; that label
    plus AUDIT_INSTRUCTIONS tell the auditor not to flag a competitor brand NAME that survives only there
    (it's swapped downstream), while still flagging any NON-brand visual problem. Returns the audit
    string, or None if there's no rewrite sidecar."""
    sup = SCENES_DIR / f"{ad_id}.supernova.json"
    if not sup.exists():
        return None
    parsed = json.loads(sup.read_text()).get("parsed", {})
    dec_path = SCENES_DIR / f"{ad_id}.json"
    dec = json.loads(dec_path.read_text()).get("parsed", {}) if dec_path.exists() else {}
    dec_scenes = {s.get("n"): s for s in dec.get("scenes", [])}
    lines = []
    for sc in parsed.get("scenes", []):
        n = sc.get("n")
        lines.append(f"SCENE {n} — {sc.get('scene_label', '')}")
        vd = dec_scenes.get(n, {}).get("visual_description")
        if vd:
            lines.append(f"  [VISUAL — competitor source; the brand name/logo here is swapped downstream, "
                         f"so do NOT flag a competitor brand NAME that appears ONLY here] {vd}")
        if sc.get("supernova_script"):
            lines.append(f"  [SCRIPT]\n{sc['supernova_script']}")
        ost = (sc.get("supernova_on_screen_text") or "").strip()
        if ost:
            lines.append(f"  [ON-SCREEN] {ost}")
    return "\n".join(lines)


def print_result(label: str, res: dict) -> None:
    icon = {"pass": "✅ PASS", "flag": "⚠️  FLAG", "block": "⛔ BLOCK"}[res["verdict"]]
    print(f"\n{'='*78}\n{label}: {icon}   — {res.get('summary','')}")
    for v in res["violations"]:
        print(f"  • [{v.get('severity','?').upper()}] {v.get('guardrail_id','')} "
              f"({v.get('category','')}) @ {v.get('scene','')}")
        print(f"      quote: \"{v.get('quote','')}\"")
        print(f"      why:   {v.get('why','')}")
        print(f"      fix:   {v.get('fix','')}")


def cmd_check(client, competitor: str, ids: list[str], do_all: bool, force: bool) -> int:
    if do_all:
        ids = sorted(p.name[:-len(".supernova.json")]
                     for p in SCENES_DIR.glob("*.supernova.json"))
    if not ids:
        sys.exit("[error] pass ad ids or --all (need <id>.supernova.json rewrite sidecars)")
    counts = {"pass": 0, "flag": 0, "block": 0}
    for ad_id in ids:
        out = SCENES_DIR / f"{ad_id}.safety.json"
        if out.exists() and not force:
            res = json.loads(out.read_text())
            counts[res["verdict"]] = counts.get(res["verdict"], 0) + 1
            print(f"[skip] {ad_id} — already audited ({res['verdict']})")
            continue
        ad_text = ad_text_from_sidecars(ad_id)
        if ad_text is None:
            print(f"[warn] {ad_id} — no rewrite sidecar, skipping")
            continue
        res = audit(client, ad_text)
        res["ad_id"] = ad_id
        res["competitor"] = competitor
        out.write_text(json.dumps(res, indent=2, ensure_ascii=False))
        counts[res["verdict"]] += 1
        print_result(ad_id, res)
    print(f"\nDONE — pass {counts['pass']} · flag {counts['flag']} · block {counts['block']}")
    return 2 if counts["block"] else 0


CLEAN_SAMPLE = """\
SCENE 1 — [VISUAL] AI-generated skeleton character in a USA street, looking confused but alert.
  [SCRIPT]
Voiceover says: Kya ho agar aapko 7 din ke liye USA mein rehna pade... woh bhi ek skeleton bankar?
  [ON-SCREEN] WHAT IF / FOR 7 DAYS
SCENE 2 — [VISUAL] Skeleton holds a phone showing an AI teacher interface, practising speaking.
  [SCRIPT]
Voiceover says: Yahan aap padhte nahi — apni AI teacher, Miss Nova ke saath actually English bolte ho.
Voiceover says: Woh pehle aapka level samajhti hai, sirf aapke liye plan banati hai. Raat ke 3 baje 1000 galtiyan karo, bina judge kiye theek karti hai.
  [ON-SCREEN] PERSONAL AI TEACHER / ZERO JUDGEMENT
SCENE 3 — [VISUAL] A police officer smiles and shakes the skeleton's hand, impressed.
  [SCRIPT]
Officer says: Your English is impressive! Yeh itni jaldi kab seekh li aapne?
Skeleton says: Saari practice main Miss Nova se karta hoon!
  [ON-SCREEN] STOP SCROLLING REELS / JUST 15 MIN A DAY / INSTALL SUPERNOVA
"""

UNSAFE_SAMPLE = """\
SCENE 1 — [VISUAL] A man in a village looks ashamed; a caption points at him.
  [SCRIPT]
Narrator says: Are you an illiterate gawar who still can't speak English? Don't stay backward your whole life.
  [ON-SCREEN] CAN'T SPEAK ENGLISH? YOU'RE FINISHED.
SCENE 2 — [VISUAL] App logo with a money-back stamp.
  [SCRIPT]
Narrator says: Supernova guarantees 100% fluency in just 7 days, or your money back — and a US visa is guaranteed once you do.
Narrator says: Unlike that useless Hello English app, which is a complete scam run by frauds.
  [ON-SCREEN] GUARANTEED FLUENT IN 7 DAYS / GET YOUR US VISA
SCENE 3 — [VISUAL] A fake government seal and a countdown timer.
  [SCRIPT]
Narrator says: Government-approved and certified by Cambridge examiners. Install now for just ₹9 — offer ends in 5 minutes!
  [ON-SCREEN] GOVT APPROVED / ONLY ₹9 / HURRY
"""


def cmd_demo(client) -> int:
    print("Running the brand-safety auditor on a CLEAN sample and an UNSAFE sample…")
    clean = audit(client, CLEAN_SAMPLE)
    unsafe = audit(client, UNSAFE_SAMPLE)
    print_result("CLEAN sample (expected PASS)", clean)
    print_result("UNSAFE sample (expected BLOCK)", unsafe)
    ok = clean["verdict"] == "pass" and unsafe["verdict"] == "block"
    print(f"\n{'✅ demo behaved as expected' if ok else '❌ demo did NOT behave as expected'}")
    return 0 if ok else 1


def cmd_status(competitor: str) -> int:
    rows = sorted(SCENES_DIR.glob("*.safety.json"))
    if competitor:
        rows = [p for p in rows if json.loads(p.read_text()).get("competitor") == competitor]
    if not rows:
        print("no safety verdicts yet")
        return 0
    for p in rows:
        r = json.loads(p.read_text())
        print(f"{r.get('ad_id', p.name):<22} {r['verdict']:<6} "
              f"({len(r.get('violations', []))} violations)  {r.get('summary', '')[:80]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_check = sub.add_parser("check")
    p_check.add_argument("--competitor", required=True)
    p_check.add_argument("ids", nargs="*")
    p_check.add_argument("--all", action="store_true")
    p_check.add_argument("--force", action="store_true", help="re-audit even if a verdict exists")
    sub.add_parser("demo")
    p_status = sub.add_parser("status")
    p_status.add_argument("--competitor", default="")
    args = ap.parse_args()

    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    if args.cmd == "status":
        return cmd_status(args.competitor)
    client = _flash.get_client(_flash.find_env(ROOT, "facebook"))
    if args.cmd == "demo":
        return cmd_demo(client)
    if args.cmd == "check":
        return cmd_check(client, args.competitor.lower().strip(), args.ids, args.all, args.force)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
