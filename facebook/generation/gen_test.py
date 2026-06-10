#!/usr/bin/env python3
"""
Manual EVAL harness for the Supernova creative context (feedback #3 "re-pitch" + #4 "real context").

Use it to sanity-check the brand context BEFORE/AFTER editing supernova_creative_context.md: it takes
a divergence battery of PROVEN, visually-distinct competitor ads and, for EACH, KEEPS the core visual
shell / scene structure AS-IS (the look drives performance) and RE-PITCHES only the message into
Supernova's disciplined payload + Miss Nova voice. Two passes per ad (draft -> critique+refine), run
concurrently on Gemini 3.1 Pro (the same model the production step4_rewrite uses).

This is a fast iteration/eval tool — the PRODUCTION generator is facebook/scripts/step4_rewrite.py,
which feeds on the richer step4_decompose scene breakdown. Edits to the context .md flow into both.

Usage:
    python3.13 facebook/generation/gen_test.py            # runs the default 5-ad battery
    python3.13 facebook/generation/gen_test.py <ad_id> ...
"""
from __future__ import annotations
import json, pathlib, sys
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CONTEXT = (HERE / "supernova_creative_context.md").read_text()
TDIR = ROOT / "analysis/enrichment/facebook/transcripts/mysivi"
MODELS = ["gemini-3.1-pro-preview", "gemini-2.5-pro"]

# default battery — 5 maximally visually-distinct strong-winners
BATTERY = [
    ("913058388118205", "DEPORTATION THRILLER (cinematic skit-narrative)"),
    ("1268336871323861", "SPLIT-SCREEN DAY-1/7/15 CORRECTION"),
    ("746424205071026", "SKYDIVING AI-BABY (absurdist pattern-break)"),
    ("4333182190269237", "FARMER-AMAZES-DOCTOR (social-proof reveal, human cast)"),
    ("1292326936145402", "PEN-AND-PAPER TRANSLATION DRILL (no-face VO)"),
]


def load_key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if k.strip() == "GEMINI_API_KEY":
                return v.strip()
    sys.exit("[error] GEMINI_API_KEY missing")


def gen(client, prompt: str, temperature: float) -> str:
    from google.genai import types as gt
    last = None
    for model in MODELS:
        try:
            r = client.models.generate_content(
                model=model, contents=prompt,
                config=gt.GenerateContentConfig(temperature=temperature, max_output_tokens=8192),
            )
            return (r.text or "").strip()
        except Exception as e:
            last = f"{model}: {type(e).__name__}: {e}"
    return f"[ERROR — all Pro models failed -> {last}]"


def reference(ad_id: str) -> str:
    t = json.loads((TDIR / f"{ad_id}.json").read_text())
    return (
        f"PROVEN COMPETITOR AD — its CORE VISUAL SHELL is what you must PRESERVE:\n"
        f"- language: {t.get('language')}\n- visual format: {t.get('device_format')}\n"
        f"- presenter: {t.get('presenter_type')}\n- angle: {t.get('message_angle')}\n"
        f"- duration: {t.get('duration_s')}s\n"
        f"- summary (the visual concept): {t.get('summary')}\n"
        f"- transcript (scene-by-scene audio):\n{t.get('transcript')}\n"
        f"- on-screen text (the visual beats):\n{t.get('on_screen_text')}\n"
    )


DRAFT_TASK = """
=== YOUR TASK ===
You are the senior creative writer for **Supernova**. Above is the full Supernova brand + payload
context, then a PROVEN competitor ad that ran a long time.

THE BALANCE (read twice):
- **KEEP THE CORE OF THE AD AS-IS.** The visual concept, the setting, the scene-by-scene structure,
  the cast/characters, the hook device, the overall LOOK — these are PROVEN and the visuals drive
  performance as much as the words. Stay INSIDE this ad's world. Do NOT invent a new concept, do NOT
  drift to a generic "job interview / 15-day transformation" template, do NOT change what the viewer SEES.
- **RE-PITCH ONLY THE MESSAGE inside that exact shell.** Swap the competitor brand -> Supernova. Replace
  its thin pitch with Supernova's disciplined PAYLOAD, woven naturally into the EXISTING beats: lead with
  personalization (a) + privacy/no-judgement (b), name **Miss Nova** as the AI teacher, name **English**
  in the first 10s, use an in-story reveal, and add the ChatGPT-contrast / mother-tongue reframe / a named
  real-life scenario WHERE THEY FIT THIS WORLD. Strip any hard rupee price. Keep the tight close.
- You MAY lightly expand a beat or add ONE line only if a payload beat needs it — but NEVER alter the core
  visual or the scene order. If the seed is absurdist (e.g. a skydiving baby), keep it absurdist.

Write the SCRIPT in clean simple **English** (the base the team localises), keeping a warm Hinglish rhythm.

OUTPUT EXACTLY THIS SHAPE (plain text, no JSON, no markdown fences):

TITLE: <name>
KEPT-FROM-SEED: <one line naming the core visual/structure you preserved>
LENGTH: <approx s>  HOOK FAMILY: <which family>

SCENE 1 — [VISUAL: <describe the seed's visual for this beat — preserved>]
<Character> says: <line>
ON-SCREEN TEXT: <words>

SCENE 2 — ... (one scene per seed beat, same order)

CLOSE / CTA: <tight close>

--- SELF-AUDIT ---
VISUAL FIDELITY: <confirm the core visual shell + scene order is unchanged from the seed; name anything you added>
PAYLOAD BEATS COVERED: <letters a-g present, 3-word note each>
HOOK: <family + literal first line>
ENGLISH NAMED BY 10s: <yes/no — quote>
MISS NOVA NAMED: <yes/no>
IN-STORY REVEAL TRIGGER: <quote it>
PRICE CHECK: <confirm no hard rupee figure>
"""

REFINE_TASK = """
=== REFINE ===
Above is the Supernova context, the competitor seed, and a FIRST DRAFT.
You are a ruthless creative director. Critique the draft, then output an IMPROVED FINAL in the same shape.

Check hard: (1) VISUAL FIDELITY — did it keep the seed's core visual concept, setting, cast and scene
order? If it drifted to a generic template or changed what the viewer sees, pull it back into the seed's
world. (2) Is personalization (a) AND privacy (b) genuinely present and vivid, woven into the existing
beats (not bolted on)? (3) Any hard rupee price -> remove. (4) Hook in first 5s, English named by 10s?
(5) Does Miss Nova sound like a warm human, not a marketing bot (natural Hinglish)? (6) Is the close tight?
Goal: a script that needs ZERO human edits AND keeps the proven visual shell.

Output ONLY the improved final ad in the same shape. Start with 'REVISION NOTES:' (2-4 concrete changes), then the final ad.
"""


def run_one(client, ad_id: str, label: str) -> str:
    base = f"{CONTEXT}\n\n{'='*80}\n{reference(ad_id)}\n"
    draft = gen(client, base + DRAFT_TASK, temperature=0.9)
    refined = gen(client, base + "\n=== FIRST DRAFT ===\n" + draft + "\n" + REFINE_TASK, temperature=0.6)
    return f"{'#'*92}\n# {label}\n# seed ad: {ad_id}\n{'#'*92}\n\n{refined}\n"


def main(ids_labels):
    from google import genai
    client = genai.Client(api_key=load_key())
    with ThreadPoolExecutor(max_workers=len(ids_labels)) as ex:
        outs = list(ex.map(lambda il: run_one(client, il[0], il[1]), ids_labels))
    for o in outs:
        print(o)


if __name__ == "__main__":
    args = sys.argv[1:]
    battery = [(a, a) for a in args] if args else BATTERY
    main(battery)
