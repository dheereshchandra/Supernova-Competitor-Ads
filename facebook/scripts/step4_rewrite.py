#!/usr/bin/env python3
"""
Step 4 — Stage 5: Supernova-voice rewrite of each video's script.

Reads each row's step4_workspace/scenes/<id>.json sidecar, sends it to Gemini
3.1 Pro Batch API with a Supernova brand-voice prompt, writes the rewritten
output to step4_workspace/scenes/<id>.supernova.json.

Mirrors step4_decompose.py's submit/poll pattern. Text-only requests so the
Batch API response is small and downloads cleanly.

Sub-commands:
    submit  <id1> <id2> ...      Submit a rewrite Batch job.
    poll    <job_short_id>       Poll the named job; on success write sidecars.
    status                        List in-flight rewrite jobs.

Usage:
    python3 scripts/step4_rewrite.py submit --competitor zinglish <ids...>
    python3 scripts/step4_rewrite.py poll <short_id>
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
BATCHES_DIR = WORKSPACE / "batches"

MODEL = "gemini-3.1-pro-preview"

# The full Supernova brand + payload context (feedback #3 "re-pitch, don't name-swap" + #4 "real
# Supernova context") is the single source of truth in facebook/generation/. We load it at runtime
# and prepend it to the rewrite instructions, so editing the .md updates the prompt everywhere.
CONTEXT_PATH = pathlib.Path(__file__).resolve().parent.parent / "generation" / "supernova_creative_context.md"


def load_context() -> str:
    try:
        return CONTEXT_PATH.read_text()
    except FileNotFoundError:
        sys.exit(f"[error] Supernova creative context missing at {CONTEXT_PATH}")


# Brand-safety guardrails (feedback #5) — the hard NEVERs, loaded so the writer avoids violations up
# front. An independent Flash audit (step4_safety_check.py) verifies every script against the same doc.
SAFETY_PATH = pathlib.Path(__file__).resolve().parent.parent / "generation" / "supernova_brand_safety.md"


def load_safety() -> str:
    try:
        return SAFETY_PATH.read_text()
    except FileNotFoundError:
        sys.exit(f"[error] brand-safety policy missing at {SAFETY_PATH}")


# Rewrite instructions, appended AFTER the brand context. The governing idea (validated on 5 proven
# competitor seeds): KEEP the ad's core visual shell exactly, RE-PITCH only the message into the
# Supernova payload. The visuals are reused unchanged, so the script must keep fitting them.
INSTRUCTIONS = """

================================================================================
YOUR JOB — GENERATE A SUPERNOVA AD FROM A COMPETITOR'S PROVEN AD

Everything above is Supernova's brand + payload context AND its brand-safety guardrails. After INPUT
below you receive a structured scene-by-scene breakdown of a *competitor's* ad — a PROVEN winner. Each
scene carries its VISUALS (`setting`, `visual_description`, `panel_visual_description`) plus its AUDIO
(`audio_transcript`) and its `on_screen_text`.

THE BALANCE — read twice:
- **KEEP THE CORE OF THE AD AS-IS.** The visual concept, setting, scene order, cast, hook device and
  overall LOOK are proven and drive performance as much as the words. These visuals are reused
  UNCHANGED downstream — your script MUST keep fitting them. Do NOT invent a new concept, do NOT drift
  to a generic "job interview / 15-day transformation" template, do NOT change what the viewer sees.
  Stay inside this ad's world (if the seed is absurdist, e.g. a skydiving baby, keep it absurdist).
- **RE-PITCH ONLY THE MESSAGE inside that exact shell.** Rewrite each scene's `audio_transcript` into
  `supernova_script` and its `on_screen_text` into `supernova_on_screen_text` so the ad now delivers
  Supernova's disciplined PAYLOAD (above), woven naturally into the EXISTING beats: swap the competitor
  brand -> Supernova; lead with personalization (a) + privacy/no-judgement (b); name **Miss Nova** as
  the AI teacher; name **English** within the first ~10s; keep an in-story reveal; add the ChatGPT
  contrast / mother-tongue reframe / a named real-life scenario WHERE THEY FIT this world. Strip any
  hard rupee price (a comparative like "7x cheaper than classes" is allowed only if it fits the scene;
  a "1 crore+ users" social-proof line is fine where it fits — don't let it carry the ad alone).
- **MATCH PAYLOAD DEPTH TO LENGTH.** A short/absurdist ad (2-3 scenes) should lead with just a+b; a
  longer narrative can stack more beats. Never cram so many beats that the pace breaks.
- You MAY lightly expand ONE line within a scene if a payload beat needs it, but NEVER change the
  visual, the scene order, or what is shown.
- **NEVER violate the BRAND-SAFETY GUARDRAILS above** (the hard NEVERs — no brand-voiced guarantees,
  no hard rupee price, no personal-attribute phrasing, no demeaning of any group, no competitor
  trashing, shame must resolve in dignity). They override all creative latitude.

OUTPUT: exactly one JSON object (no markdown fences, no commentary). Schema:

{
  "production_type": "<same as input>",
  "characters": [<same as input — copy through unchanged>],
  "scenes": [
    {
      "n": <same as input>,
      "scene_label": "<same as input>",
      "supernova_script": "<your Supernova re-pitch of this scene's audio_transcript, in ENGLISH. Put each spoken turn on its OWN line, prefixed 'Character X says:' (one line per turn — this makes the Scene/Character/Script layout clean). Same visual beat and pacing; Supernova payload + Miss Nova voice.>",
      "scene_summary": "<2-4 hyphen-prefixed bullets: what this scene does — purpose, emotion, which payload beat(s) it lands. For analyst reference.>",
      "supernova_on_screen_text": "<re-pitched on_screen_text if relevant; otherwise empty string>"
    }
  ],
  "payload_audit": {
    "beats_covered": "<which payload beats a-g the whole ad lands, with a 3-word note each>",
    "kept_from_seed": "<one line naming the core visual/structure you preserved>",
    "miss_nova_named": <true|false>,
    "english_named_early": <true|false>,
    "price_check": "<confirm no hard rupee figure; note any comparative used>"
  },
  "brand_swaps_detected": [
    {"competitor_brand": "<original brand name found in script or on-screen text>",
     "supernova_swap": "<what we replaced it with — usually 'Supernova' or removed>"}
  ]
}

CONSTRAINTS:
- Output ONLY a valid JSON object. No commentary, no markdown fences.
- Every scene from the input must appear in the output with the same `n`, in the same order.
- `supernova_script` MUST put each spoken turn on its OWN line with a "Character X says:" prefix — one line per turn (this renders as a clean Scene -> Character -> Script layout).
- Write EVERYTHING (script + on-screen text) in ENGLISH — this is the base the team edits and localises to Hindi/Telugu/Tamil/etc. Capture the warm, conversational Hinglish *rhythm*, but do NOT output Devanagari/Tamil/etc. script or bracketed [translations].
- Do NOT change the visuals or scene order. If a scene's dialogue is too brand-specific to re-pitch, still emit it with `supernova_script: "[scene-too-brand-specific-to-rewrite — manual edit needed]"`. Never silently skip scenes.

INPUT:
"""


def build_prompt() -> str:
    """Full rewrite prompt = brand context + brand-safety guardrails + rewrite instructions."""
    return load_context() + "\n\n" + load_safety() + INSTRUCTIONS


def load_env() -> dict:
    env = {}
    for line in pathlib.Path(".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def get_client():
    env = load_env()
    if not env.get("GEMINI_API_KEY"):
        sys.exit("[error] GEMINI_API_KEY missing")
    from google import genai
    return genai.Client(api_key=env["GEMINI_API_KEY"])


def cmd_submit(client, ids: list[str], competitor: str) -> int:
    from google.genai import types as gt
    prompt = build_prompt()
    inlined = []
    missing = []
    for ad_id in ids:
        sidecar = SCENES_DIR / f"{ad_id}.json"
        if not sidecar.exists():
            missing.append(ad_id)
            continue
        decompose = json.loads(sidecar.read_text())
        parsed = decompose.get("parsed", {})
        user_text = prompt + json.dumps(parsed, ensure_ascii=False)
        inlined.append({
            "contents": [
                gt.Content(role="user", parts=[gt.Part(text=user_text)]),
            ],
            "config": gt.GenerateContentConfig(
                temperature=0.4,
                max_output_tokens=16384,
                response_mime_type="application/json",
            ),
            "metadata": {"key": ad_id},
        })

    if missing:
        sys.exit(f"[error] no decompose sidecar for: {missing}. Run Stage 1 first.")
    if not inlined:
        sys.exit("[error] nothing to submit")

    print(f"Submitting Supernova-rewrite batch with {len(inlined)} requests…")
    job = client.batches.create(
        model=MODEL,
        src=inlined,
        config={"display_name": f"step4-rewrite-{competitor}-{int(time.time())}"},
    )
    short = job.name.split("/")[-1][:16]
    state_path = BATCHES_DIR / f"rewrite_{short}.json"
    state_path.write_text(json.dumps({
        "short_id": short,
        "job_name": job.name,
        "competitor": competitor,
        "ids": ids,
        "submitted_at": time.time(),
        "state_history": [{"t": time.time(), "state": str(job.state.name)}],
    }, indent=2))
    print(f"  submitted: {job.name}")
    print(f"  short id:  {short}")
    print(f"  state:     {job.state.name}")
    print(f"  saved to:  {state_path}")
    print()
    print(f"Now poll with:  python3 scripts/step4_rewrite.py poll {short}")
    return 0


def cmd_poll(client, short_id: str) -> int:
    state_path = BATCHES_DIR / f"rewrite_{short_id}.json"
    if not state_path.exists():
        sys.exit(f"[error] no batch state at {state_path}")
    state = json.loads(state_path.read_text())
    job = client.batches.get(name=state["job_name"])
    state["state_history"].append({"t": time.time(), "state": str(job.state.name)})
    state_path.write_text(json.dumps(state, indent=2))

    print(f"job:  {state['job_name']}")
    print(f"state: {job.state.name}")
    elapsed = time.time() - state["submitted_at"]
    print(f"elapsed: {elapsed:.0f}s")

    if job.state.name not in ("JOB_STATE_SUCCEEDED", "BATCH_STATE_SUCCEEDED"):
        if job.state.name in ("JOB_STATE_FAILED", "BATCH_STATE_FAILED",
                              "JOB_STATE_CANCELLED", "BATCH_STATE_CANCELLED"):
            print(f"  TERMINAL FAILURE")
            return 2
        print(f"  still running. Re-run in ~60s.")
        return 1

    written = failed = 0
    for resp in job.dest.inlined_responses:
        key = resp.metadata.get("key") if hasattr(resp, "metadata") and resp.metadata else None
        if not key:
            continue
        try:
            if hasattr(resp, "error") and resp.error:
                print(f"  [{key}] error: {resp.error}")
                failed += 1
                continue
            text = resp.response.candidates[0].content.parts[0].text
            text = re.sub(r"^```(?:json)?\s*", "", text.strip())
            text = re.sub(r"\s*```$", "", text)
            parsed = json.loads(text)
            sidecar = {"competitor_id": key, "parsed": parsed,
                       "model": MODEL, "rewrote_at": time.time()}
            (SCENES_DIR / f"{key}.supernova.json").write_text(json.dumps(sidecar, indent=2, ensure_ascii=False))
            written += 1
            print(f"  [{key}] OK — {len(parsed.get('scenes', []))} scenes")
        except Exception as e:
            print(f"  [{key}] {type(e).__name__}: {e}")
            failed += 1

    print(f"\nDONE — {written} sidecars written, {failed} failed")
    return 0


def cmd_status() -> int:
    for p in sorted(BATCHES_DIR.glob("rewrite_*.json")):
        state = json.loads(p.read_text())
        last = state.get("state_history", [{"state": "?"}])[-1]
        elapsed = time.time() - state["submitted_at"]
        print(f"{state['short_id']}  {state['competitor']:<15}  {last['state']:<22}  {elapsed:.0f}s ago")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_submit = sub.add_parser("submit")
    p_submit.add_argument("--competitor", required=True)
    p_submit.add_argument("ids", nargs="+")
    p_poll = sub.add_parser("poll")
    p_poll.add_argument("short_id")
    sub.add_parser("status")
    args = ap.parse_args()

    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    SCENES_DIR.mkdir(parents=True, exist_ok=True)

    if args.cmd == "status":
        return cmd_status()
    client = get_client()
    if args.cmd == "submit":
        return cmd_submit(client, args.ids, args.competitor.lower().strip())
    if args.cmd == "poll":
        return cmd_poll(client, args.short_id)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
