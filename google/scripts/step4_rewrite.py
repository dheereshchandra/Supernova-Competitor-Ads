#!/usr/bin/env python3
"""
Step 4 — Stage 5 (Google): Supernova-voice rewrite of each ad.

Reads each row's step4_workspace/scenes/<creative_id>.json sidecar (any format),
sends it to Gemini 3.1 Pro Batch API with a Supernova brand-voice prompt, writes
the rewritten output to step4_workspace/scenes/<creative_id>.supernova.json.

Works uniformly across YouTubeVideo / Image / Text formats — the decompose
sidecars all share the same scene-shaped schema (Image and Text use 1 synthetic
scene each), so the rewrite prompt and Batch submission are identical.

Sub-commands:
    submit  <id1> <id2> ...      Submit a rewrite Batch job.
    poll    <job_short_id>       Poll the named job; on success write sidecars.
    status                        List in-flight rewrite jobs.
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

PROMPT = """You are a brand copywriter for **Supernova**, a Hindi-language spoken-English learning app from India.

You will receive a structured JSON scene-breakdown of a *competitor's* ad (from Google's Ads Transparency Center). Your job is to rewrite the audio script and on-screen text in Supernova's voice — same scene-by-scene structure, same character beats, but reframed for Supernova's brand and messaging.

The ad may be a video (multiple scenes), a static image (one synthetic scene), or a text-only Search ad (one synthetic scene with the headline as on_screen_text and description as audio_transcript). Handle all uniformly.

OUTPUT: exactly one JSON object (no markdown fences, no commentary). Schema:

{
  "production_type": "<same as input>",
  "characters": [<same as input — copy through unchanged>],
  "scenes": [
    {
      "n": <same as input>,
      "scene_label": "<same as input>",
      "supernova_script": "<your Supernova-voice rewrite of audio_transcript. For video: same character speaker attribution ('Character A says: …'). For image/text: no character prefix needed. Keep same beat/intent. Keep same native language script + bracketed [English translation] format.>",
      "scene_summary": "<2-4 bullet points, hyphen-prefixed, summarising what this scene does — purpose, emotion, payoff.>",
      "supernova_on_screen_text": "<rewritten on_screen_text if relevant; otherwise empty string>"
    }
  ],
  "brand_swaps_detected": [
    {"competitor_brand": "<original brand name>",
     "supernova_swap": "<what we replaced it with — usually 'Supernova' or removed>"}
  ]
}

SUPERNOVA BRAND VOICE — read carefully:
- **Audience**: Hindi-first Indian learners who want to speak English with confidence — usually 20–40 year-olds in tier-2/tier-3 cities.
- **Tone**: warm, practical, encouraging, never patronising. Like a trusted older sibling. Hindi-English code-mix is OK and authentic.
- **What Supernova offers**: a Hindi-medium English learning app with AI tutor practice, daily lessons, real-world speaking situations. It is NOT free; do not invent specific pricing.
- **STRIP from rewrite**: competitor brand names (replace with "Supernova" or remove), specific pricing claims, aggressive hype ("world's #1", "guaranteed in 30 days"), direct disparagement of other apps.
- **KEEP**: dramatic beat structure (hook → problem → solution → CTA), same character voices and emotions, same length, same language mix.

CONSTRAINTS:
- Output ONLY a valid JSON object. No commentary, no markdown fences.
- Every scene from the input must appear in the output with the same `n`.
- For video: `supernova_script` MUST keep the "Character X says:" prefix on every spoken line.
- Stay in the same language script as the original.
- If you cannot rewrite a particular scene, still emit it with `supernova_script: "[scene-too-brand-specific-to-rewrite — manual edit needed]"`. Do not silently skip scenes.

INPUT:
"""


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
    inlined = []
    missing = []
    for cid in ids:
        sidecar = SCENES_DIR / f"{cid}.json"
        if not sidecar.exists():
            missing.append(cid)
            continue
        decompose = json.loads(sidecar.read_text())
        parsed = decompose.get("parsed", {})
        # Include the creative_format so the rewriter knows what kind of ad it's rewriting
        parsed_with_meta = {**parsed, "_creative_format": decompose.get("creative_format", "Unknown")}
        user_text = PROMPT + json.dumps(parsed_with_meta, ensure_ascii=False)
        inlined.append({
            "contents": [
                gt.Content(role="user", parts=[gt.Part(text=user_text)]),
            ],
            "config": gt.GenerateContentConfig(
                temperature=0.4,
                max_output_tokens=16384,
                response_mime_type="application/json",
            ),
            "metadata": {"key": cid},
        })

    if missing:
        sys.exit(f"[error] no decompose sidecar for: {missing}. Run Stage 1 first.")
    if not inlined:
        sys.exit("[error] nothing to submit")

    print(f"Submitting Supernova-rewrite batch with {len(inlined)} requests…")
    job = client.batches.create(
        model=MODEL,
        src=inlined,
        config={"display_name": f"step4-rewrite-google-{competitor}-{int(time.time())}"},
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
            (SCENES_DIR / f"{key}.supernova.json").write_text(
                json.dumps(sidecar, indent=2, ensure_ascii=False))
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
