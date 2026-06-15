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
import csv
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


# Rewrite instructions, appended AFTER the brand context. The governing idea (v3, faithful-replication):
# the competitor ad is PROVEN — replicate it as-is and only re-skin it for Supernova. Change as little as
# possible; apply the concept brief; never rewrite in the name of "guidelines" (only the 4 hard lines).
INSTRUCTIONS = """

================================================================================
YOUR JOB — REPLICATE A PROVEN COMPETITOR AD, LIGHTLY RE-SKINNED FOR SUPERNOVA

Everything above is Supernova's context + pitch points + the few HARD LINES. After INPUT below you get a
scene-by-scene breakdown of a *competitor's* ad (a PROVEN winner), the SEED LANGUAGE it was made in, and
a CONCEPT BRIEF. The competitor ad works for a reason we don't fully know — hook, script, or visuals — so
**CHANGE AS LITTLE AS POSSIBLE.** You are RE-SKINNING it, not rewriting it. Your OUTPUT is 100% English.

THE HEADLINE: the competitor's script is the source of truth — keep its hook, its specific lines and
examples, who speaks first, and the turn order. Re-skin = swap the brand to Supernova + weave in ≥3 pitch
points + re-point the CTA + apply the concept brief. Above all, the result must read as a SMOOTH, NATURAL
conversation — never a sales pitch, never an abrupt Miss Nova drop-in.

PRIORITY ORDER:
1. **[HARD] Apply the CONCEPT BRIEF first — it is MANDATORY.** It overrides the competitor original where
   they differ: character swaps (e.g. a baby or a robot instead of the original person), format
   reclassification (treat as a talking-head / TED; if the seed is an ASMR split-screen with filler video
   below, treat it as a single talking-head and DO NOT mention ASMR), and any script/visual direction it
   gives. The script + visuals may flex to accommodate the brief. (If no brief is provided, replicate the
   competitor faithfully.)
2. **[HARD] Then replicate the competitor faithfully for everything the brief doesn't change:**
   - **[SOFT, strong default] Keep the specific line content** — the exact wrong-English example being
     corrected ("I'm having two brothers" STAYS "I'm having two brothers", NOT "I'm having a doubt"), the
     specific question, the exact beat. Change a line ONLY if the brief requires it or the script genuinely
     needs it to flow. Do NOT substitute a different example or invent new dialogue.
   - **[SOFT, strong default] Keep the opening speaker + turn order** — if the robot / Miss Nova opens,
     keep it; flip it ONLY if the brief or natural flow demands.
   - **[SOFT] Keep the hook** unless the brief changes it or it names the competitor brand.
3. **[HARD] Re-skin for Supernova — the only deliberate changes:**
   - Swap the competitor brand -> **Supernova AI**; the AI teacher -> **Miss Nova**.
   - Weave in **AT LEAST 3 pitch points** (PART 2) into the EXISTING beats, naturally — never jammed. If a
     pitch point doesn't fit, pick one that does. Minimum 3; more only if there's room.
   - Re-point the **CTA** to Supernova (install, ~10–15 min/day, with the help of Hindi).
   - **[SOFT] Benefits first, brand second** — lean toward the first half carrying the relatable / benefit
     content and bringing Supernova / Miss Nova in around the second half — but follow the seed if it
     reveals the product early.
4. **[HARD] SMOOTH, NATURAL FLOW IS THE #1 GOAL.** The script must read like a real conversation. NEVER add
   a pitch point just to hit the count; NEVER drop Miss Nova in abruptly. Flow wins over count — but you
   must still land at least 3 pitch points, woven lightly enough that the conversation stays natural.
5. **[HARD] INDIANIZE EVERY REFERENCE** — names -> Indian (Rahul, Priya, Anjali, Imran…, never
   "Jenny"/"John"), cities/places -> Indian (never France/London-as-home), currency/food/festivals ->
   Indian. The audience is in India.
6. **[HARD] NEVER cross the four HARD LINES above.** Otherwise do NOT rewrite anything in the name of
   guidelines — when unsure, KEEP THE SEED.

OUTPUT: exactly one JSON object (no markdown fences, no commentary). The deliverable doc has two
zones for this English master — a skim-able **Visual & Cast** block (format + look + cast +
scenes-at-a-glance) and the clean **Script** (a TTS feed is generated later, only on the localized
versions). Put all visual/analyst detail in the top-level fields and keep `supernova_script` PURE
DIALOGUE (no stage directions, no on-screen text, no narration). Schema:

{
  "production_type": "<same as input>",
  "format": "<the ad's format/container in a few words — e.g. 'Split-screen grammar-correction skit', 'TED-style stage monologue', 'Interview / talk-show', 'Family narrative drama', 'Mock breaking-news bulletin'. Name the container (Part 5) + whether it's split-screen / single-presenter / multi-cast.>",
  "visual_overview": "<2–4 plain sentences describing what the ad LOOKS like end to end — the setting(s), who is on screen and where (left/right in a split-screen), any app-UI cutaways or end card, and the caption style. Faithful to the seed's REUSED visuals. This is skim-context for the editor, NOT the script.>",
  "characters": [
    {
      "id": "<same as input — the stable A/B/C label>",
      "name": "<the character's ASSIGNED NAME, used as the speaker label in supernova_script. Human → a consistent Indian name (the SAME in every scene they appear in). AI teacher/assistant/robot/avatar → \"Miss Nova\". A minor non-speaking figure may take a short descriptive label (e.g. \"Interviewer\").>",
      "role": "<same as input — short>",
      "brief": "<ONE short line: who they are + key look, e.g. 'AI tutor avatar, glossy white-grey robot casing' or 'young male office-worker learner'>"
    }
  ],
  "scenes": [
    {
      "n": <same as input>,
      "scene_label": "<same as input>",
      "scene_brief": "<ONE short line — what this scene does, for the 'scenes at a glance' list. e.g. 'Rapid present→past verb drill' / 'No-judgement: speak out loud, make 1000 mistakes' / 'Affordability + 15 min/day close'.>",
      "supernova_script": "<your Supernova AI re-pitch of this scene's audio_transcript, in ENGLISH. Each spoken turn on its OWN line, prefixed with the speaking character's ASSIGNED NAME + ' says:' — e.g. 'Ramesh says:' / 'Miss Nova says:' — using the names from characters[] (one line per turn). PURE DIALOGUE — what is SPOKEN, nothing else. Same visual beat + pacing; Supernova payload + Miss Nova voice.>"
    }
  ],
  "pitch_points_used": ["<the >=3 Supernova pitch points you landed — e.g. 'personalization', 'no-judgement', 'cheaper than coaching'>"],
  "self_check": "<one line: confirm the flow is natural, the brand sits in the back half (or why the seed put it early), and you KEPT the seed's hook / opening speaker / specific lines (or note exactly what the concept brief changed)>"
}

CONSTRAINTS:
- Output ONLY a valid JSON object. No commentary, no markdown fences.
- Every scene from the input appears in the output with the same `n`, in the same order. Keep the same
  OPENING SPEAKER and TURN ORDER as the seed, unless the concept brief or natural flow requires a change.
- Keep the seed's SPECIFIC lines and examples (the exact wrong-English phrase being corrected, the exact
  question). Do not substitute a different example or invent dialogue — only re-skin (brand + pitch points
  + CTA) and apply the concept brief.
- `supernova_script` MUST put each spoken turn on its OWN line prefixed with the speaker's ASSIGNED NAME + " says:" (e.g. "Ramesh says:", "Miss Nova says:"), using the names from `characters[]` — never "Character A says:". One line per turn. PURE DIALOGUE only — no stage directions, no on-screen text.
- **WRITE 100% PURE ENGLISH — every word.** The master is entirely in English: NO Hindi/Tamil/Telugu/etc.
  words at all, not even romanized flavour ("yaar", "koi baat nahi"). The code-mix is added later at
  localization, not here. Keep the warm, conversational rhythm — in plain English. Never output
  Devanagari/Tamil/etc. script. EXCEPTION: brand proper nouns (Supernova AI, Miss Nova).
- Do NOT change the visuals or scene order. If a scene's dialogue is genuinely impossible to re-skin, emit
  it with `supernova_script: "[scene needs manual edit]"`. Never silently skip scenes.

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


# Seed (source) language per ad — fed to the rewrite so the model adapts idioms/world to the
# competitor ad's original audience (output is still 100% English). Sourced from the enriched
# CSV's `language` column; falls back to inference-from-transcript when unavailable.
ENRICHED_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "analysis" / "derived" / "facebook"


def load_seed_languages(competitor: str) -> dict:
    path = ENRICHED_DIR / f"{competitor}_enriched.csv"
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                aid, lang = r.get("ad_id"), (r.get("language") or "").strip()
                if aid and lang:
                    out.setdefault(aid, lang)
    except Exception:
        pass
    return out


def cmd_submit(client, ids: list[str], competitor: str) -> int:
    from google.genai import types as gt
    prompt = build_prompt()
    seed_langs = load_seed_languages(competitor)
    inlined = []
    missing = []
    for ad_id in ids:
        sidecar = SCENES_DIR / f"{ad_id}.json"
        if not sidecar.exists():
            missing.append(ad_id)
            continue
        decompose = json.loads(sidecar.read_text())
        parsed = decompose.get("parsed", {})
        seed_lang = seed_langs.get(ad_id) or "unknown (infer it from the audio_transcript)"
        # Concept brief (MANDATORY input when present): step4_workspace/scenes/<id>.brief.txt — the
        # team's replication direction (character swaps, ASMR->talking-head, format). The driver / Ad
        # Studio writes it from the Ideas-sheet `Concept Brief` column; absent → faithful replication.
        brief_path = SCENES_DIR / f"{ad_id}.brief.txt"
        brief = brief_path.read_text(encoding="utf-8").strip() if brief_path.exists() else ""
        brief_block = (f"CONCEPT BRIEF (MANDATORY — apply over the competitor original where they differ):\n{brief}\n\n"
                       if brief else "CONCEPT BRIEF: (none provided — replicate the competitor faithfully)\n\n")
        user_text = (f"{prompt}SEED LANGUAGE: {seed_lang}\n\n{brief_block}"
                     + json.dumps(parsed, ensure_ascii=False))
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
