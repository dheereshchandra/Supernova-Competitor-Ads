#!/usr/bin/env python3
"""
Step 4 — Stage 1 (Google): ad decomposition via Gemini 3.1 Pro.

Format-aware:
  - YouTubeVideo: full Batch API flow (upload → submit → poll → sidecars)
  - Image: synchronous single-image analysis (no Batch needed)
  - Text: synchronous text-only analysis of headline+description

Sub-commands:
    upload   <id1> <id2> ...           Upload videos to Files API (resumable). YouTube only.
    submit   <id1> <id2> ...           Submit a Batch job for YouTube + sync calls for Image/Text.
    poll     <job_short_id>            Poll the named YouTube batch; on success write sidecars.
    status                              List in-flight batch jobs.

For Image and Text rows, `submit` produces sidecars immediately (no poll needed).
For YouTubeVideo rows, `submit` returns a short_id; `poll` is required.

Outputs land at step4_workspace/scenes/<creative_id>.json with the schema
documented in skills/google-ads-video-analysis/SKILL.md "Stage 1".
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

WORKSPACE = pathlib.Path("step4_workspace")
BATCHES_DIR = WORKSPACE / "batches"
SCENES_DIR = WORKSPACE / "scenes"
UPLOADS_DIR = WORKSPACE / ".gemini_uploads"
LOGS_DIR = WORKSPACE / "logs"

MODEL = "gemini-3.1-pro-preview"

# ---------------------------------------------------------------------------
# Prompts — three variants, one per format
# ---------------------------------------------------------------------------

VIDEO_PROMPT = """You are analysing a short YouTube ad video to support storyboarding for a competitor brand's recreation.

Watch the video AND listen to the audio carefully. Reply with EXACTLY ONE JSON object — no markdown fences, no commentary. Schema:

{
  "duration_s": <float, total video length>,
  "production_type": "human-recorded" | "AI-generated" | "mixed",
  "production_notes": "<1-2 sentences explaining your reasoning>",
  "characters": [
    {
      "id": "A",
      "role": "<e.g. male presenter, female learner, AI tutor avatar>",
      "appearance": "<2-3 sentence reusable physical description>",
      "wardrobe": "<what they are wearing throughout the video>",
      "demeanor": "<expression / body language vibe>"
    }
  ],
  "scenes": [
    {
      "n": 1,
      "start_s": 0.0,
      "end_s": 4.5,
      "screenshot_at_s": 2.0,
      "scene_label": "<short title>",
      "setting": "<location, time of day, props, color palette>",
      "characters_in_scene": ["A", "B"],
      "camera": "<framing>",
      "layout": "<single | split-horizontal | split-vertical | inset | grid>",
      "panels": [
        {
          "position": "<full | top | bottom | left | right | background | inset>",
          "panel_visual_description": "<5-8 sentence CLEAN visual description of ONLY this panel. NO text overlays, captions, logos, app UI, end-cards, watermarks. Reference characters by stable id.>",
          "characters_in_panel": ["A"]
        }
      ],
      "visual_description": "<5-8 sentences describing the whole composite shot including overlays>",
      "audio_transcript": "<verbatim transcript. Prefix every line with the speaker character ID, e.g. 'Character A says: …'. Use native script + bracketed [English translation].>",
      "on_screen_text": "<verbatim text overlays, captions, end-card copy>"
    }
  ]
}

Rules:
- Pick scene boundaries at natural cuts. Aim 4-10 scenes for 30-90s ads. For very short ads (<15s), 2-4 scenes is fine.
- panel_visual_description must EXCLUDE all text overlays, logos, UI, watermarks.
- Be precise. Don't invent details that aren't in the video.
"""

IMAGE_PROMPT = """You are analysing a single static image advertisement from Google's Ads Transparency Center for storyboarding.

Look at the image carefully. Reply with EXACTLY ONE JSON object — no markdown fences, no commentary. Use the same schema as a video analysis but with exactly ONE synthetic scene:

{
  "duration_s": null,
  "production_type": "static-image",
  "production_notes": "<1-2 sentences about composition, style, AI-generated vs photographed>",
  "characters": [
    {
      "id": "A",
      "role": "<role>",
      "appearance": "<physical description>",
      "wardrobe": "<wardrobe>",
      "demeanor": "<demeanor>"
    }
  ],
  "scenes": [
    {
      "n": 1,
      "start_s": 0.0,
      "end_s": 0.0,
      "screenshot_at_s": 0.0,
      "scene_label": "static image",
      "setting": "<location, props, palette>",
      "characters_in_scene": ["A"],
      "camera": "<framing>",
      "layout": "single",
      "panels": [
        {
          "position": "full",
          "panel_visual_description": "<5-8 sentence CLEAN description of the imagery only, NO text/logos/UI>",
          "characters_in_panel": ["A"]
        }
      ],
      "visual_description": "<5-8 sentences of the whole image including overlays>",
      "audio_transcript": "[no audio — static image]",
      "on_screen_text": "<verbatim text from the image>"
    }
  ]
}

If there are no characters (e.g. product-only shot), characters can be an empty array and the scene's characters_in_scene/characters_in_panel arrays empty.
"""

TEXT_PROMPT = """You are analysing a Google Search ad (text-only) from the Ads Transparency Center.

You have ONLY the headline and description — no images, no video. Your job is to produce a structured analysis sidecar in the same shape as a video decomposition, so the downstream docx-building code can treat all formats uniformly.

Inputs:
  Advertiser:  {advertiser_name}
  Regions:     {regions_shown}
  Headline:    {ad_headline}
  Description: {ad_description}
  CTA dest:    {ad_destination_url}

Reply with EXACTLY ONE JSON object — no markdown fences, no commentary:

{{
  "duration_s": null,
  "production_type": "text-search-ad",
  "production_notes": "<1-2 sentences about the messaging strategy / target audience / value-prop>",
  "characters": [],
  "scenes": [
    {{
      "n": 1,
      "start_s": 0.0,
      "end_s": 0.0,
      "screenshot_at_s": 0.0,
      "scene_label": "text ad copy",
      "setting": "<implied context — what scenario does this ad assume the user is in>",
      "characters_in_scene": [],
      "camera": "n/a",
      "layout": "single",
      "panels": [],
      "visual_description": "<3-5 sentences imagining how this ad would render visually if displayed as a Search result>",
      "audio_transcript": "{ad_description}",
      "on_screen_text": "{ad_headline}"
    }}
  ],
  "messaging_analysis": "<3-5 sentence analysis of: hook, value-prop, urgency / social-proof / scarcity tactics, target persona, expected click intent>"
}}
"""


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------

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
        sys.exit("[error] GEMINI_API_KEY missing from .env")
    from google import genai
    return genai.Client(api_key=env["GEMINI_API_KEY"])


def ensure_dirs():
    for d in (BATCHES_DIR, SCENES_DIR, UPLOADS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def find_master_row(creative_id: str, competitor: str) -> Optional[dict]:
    master_path = pathlib.Path("master") / f"{competitor}.csv"
    if not master_path.exists():
        return None
    with master_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("creative_id") or "").strip() == creative_id:
                return row
    return None


def video_path_for(creative_id: str, competitor: str) -> Optional[pathlib.Path]:
    candidates = sorted(pathlib.Path("videos").glob(f"{competitor}-*"))
    if not candidates:
        return None
    vdir = candidates[-1]
    p = vdir / f"{creative_id}.mp4"
    return p if p.exists() else None


def image_path_for(creative_id: str, competitor: str) -> Optional[pathlib.Path]:
    candidates = sorted(pathlib.Path("images").glob(f"{competitor}-*"))
    if not candidates:
        return None
    idir = candidates[-1]
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        p = idir / f"{creative_id}{ext}"
        if p.exists():
            return p
    return None


def split_ids_by_format(ids: list[str], competitor: str) -> dict[str, list[str]]:
    """Group creative_ids by their format in the master CSV."""
    groups = {"YouTubeVideo": [], "Image": [], "Text": [], "Shopping": [], "Maps": [], "Unknown": []}
    for cid in ids:
        row = find_master_row(cid, competitor)
        if not row:
            groups["Unknown"].append(cid)
            continue
        fmt = (row.get("creative_format") or "").strip() or "Unknown"
        groups.setdefault(fmt, []).append(cid)
    return groups


def ffprobe_meta(video_path: pathlib.Path) -> dict:
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(video_path),
        ], timeout=15).decode()
        data = json.loads(out)
        duration = float(data.get("format", {}).get("duration", 0.0))
        return {"duration_s": round(duration, 2)}
    except (subprocess.SubprocessError, OSError, ValueError):
        return {"duration_s": None}


# ---------------------------------------------------------------------------
# Sync path — Image and Text (no Batch API needed)
# ---------------------------------------------------------------------------

def decompose_image_sync(client, creative_id: str, competitor: str) -> tuple[bool, str]:
    """Run a synchronous Gemini call against a static image. Write sidecar on success."""
    img = image_path_for(creative_id, competitor)
    if img is None:
        return False, "no-image-file"

    from google.genai import types as gt
    try:
        with img.open("rb") as fh:
            img_bytes = fh.read()
        mime = "image/jpeg"
        if img.suffix.lower() == ".png":
            mime = "image/png"
        elif img.suffix.lower() == ".webp":
            mime = "image/webp"
        elif img.suffix.lower() == ".gif":
            mime = "image/gif"

        resp = client.models.generate_content(
            model=MODEL,
            contents=[
                gt.Content(role="user", parts=[
                    gt.Part(text=IMAGE_PROMPT),
                    gt.Part(inline_data=gt.Blob(mime_type=mime, data=img_bytes)),
                ]),
            ],
            config=gt.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=8192,
                response_mime_type="application/json",
            ),
        )
        text = resp.candidates[0].content.parts[0].text
        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
        sidecar = {"competitor_id": creative_id, "creative_format": "Image",
                    "parsed": parsed, "model": MODEL, "decoded_at": time.time()}
        (SCENES_DIR / f"{creative_id}.json").write_text(json.dumps(sidecar, indent=2))
        return True, "OK"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:200]}"


def decompose_text_sync(client, creative_id: str, competitor: str) -> tuple[bool, str]:
    """Run a synchronous Gemini call against the text fields of a Text/Search ad."""
    row = find_master_row(creative_id, competitor)
    if row is None:
        return False, "no-master-row"

    headline = (row.get("ad_headline") or "").strip()
    description = (row.get("ad_description") or "").strip()
    if not headline and not description:
        return False, "no-copy-in-master"

    prompt = TEXT_PROMPT.format(
        advertiser_name=row.get("advertiser_name", ""),
        regions_shown=row.get("regions_shown", ""),
        ad_headline=headline.replace('"', '\\"'),
        ad_description=description.replace('"', '\\"'),
        ad_destination_url=row.get("ad_destination_url", ""),
    )

    from google.genai import types as gt
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=[gt.Content(role="user", parts=[gt.Part(text=prompt)])],
            config=gt.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=4096,
                response_mime_type="application/json",
            ),
        )
        text = resp.candidates[0].content.parts[0].text
        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
        sidecar = {"competitor_id": creative_id, "creative_format": "Text",
                    "parsed": parsed, "model": MODEL, "decoded_at": time.time()}
        (SCENES_DIR / f"{creative_id}.json").write_text(json.dumps(sidecar, indent=2))
        return True, "OK"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:200]}"


# ---------------------------------------------------------------------------
# Upload sub-command (YouTube only)
# ---------------------------------------------------------------------------

def cmd_upload(client, ids: list[str], competitor: str) -> int:
    groups = split_ids_by_format(ids, competitor)
    yt_ids = groups.get("YouTubeVideo", [])
    print(f"YouTube video ids to upload: {len(yt_ids)} (of {len(ids)} total). "
          f"Skipping {len(ids) - len(yt_ids)} non-video formats.")

    if not yt_ids:
        return 0

    upload_state_path = UPLOADS_DIR / f"{competitor}.json"
    state = json.loads(upload_state_path.read_text()) if upload_state_path.exists() else {}

    still_active = {}
    for cid, file_name in state.items():
        try:
            f = client.files.get(name=file_name)
            if f.state.name == "ACTIVE":
                still_active[cid] = file_name
        except Exception:
            pass
    state = still_active

    to_upload = [cid for cid in yt_ids if cid not in state]
    print(f"to_upload: {len(to_upload)}/{len(yt_ids)} (skipping {len(state)} already-uploaded)")

    if not to_upload:
        upload_state_path.write_text(json.dumps(state, indent=2))
        return 0

    def _upload_one(creative_id: str) -> tuple[str, str, Optional[str]]:
        vpath = video_path_for(creative_id, competitor)
        if vpath is None:
            return creative_id, "NO VIDEO", None
        try:
            up = client.files.upload(file=str(vpath),
                                       config={"mime_type": "video/mp4",
                                                "display_name": creative_id})
            return creative_id, "OK", up.name
        except Exception as e:
            return creative_id, f"FAIL {type(e).__name__}: {str(e)[:120]}", None

    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(_upload_one, cid): cid for cid in to_upload}
        for fut in as_completed(futs):
            cid, status, file_name = fut.result()
            print(f"  [{cid}] {status}  {file_name or ''}", flush=True)
            if file_name:
                state[cid] = file_name

    upload_state_path.write_text(json.dumps(state, indent=2))

    print()
    print("Waiting for all files to reach ACTIVE state…")
    waiting = list(state.values())
    deadline = time.time() + 120
    while waiting and time.time() < deadline:
        still_waiting = []
        for name in waiting:
            try:
                f = client.files.get(name=name)
                if f.state.name == "ACTIVE":
                    continue
                if f.state.name == "FAILED":
                    print(f"  FAILED: {name}")
                    continue
                still_waiting.append(name)
            except Exception:
                still_waiting.append(name)
        waiting = still_waiting
        if waiting:
            time.sleep(3)
    print(f"  all {len(state)} files ACTIVE" if not waiting else f"  warning: {len(waiting)} not ACTIVE after 120s")
    return 0


# ---------------------------------------------------------------------------
# Submit sub-command
# ---------------------------------------------------------------------------

def cmd_submit(client, ids: list[str], competitor: str) -> int:
    groups = split_ids_by_format(ids, competitor)
    yt_ids = groups.get("YouTubeVideo", [])
    image_ids = groups.get("Image", []) + groups.get("Shopping", []) + groups.get("Maps", [])
    text_ids = groups.get("Text", [])
    unknown_ids = groups.get("Unknown", [])

    print(f"Submit breakdown:")
    print(f"  YouTubeVideo (Batch): {len(yt_ids)}")
    print(f"  Image (sync):         {len(image_ids)}")
    print(f"  Text (sync):          {len(text_ids)}")
    if unknown_ids:
        print(f"  Unknown (skipping):   {len(unknown_ids)} — {unknown_ids[:5]}{'…' if len(unknown_ids) > 5 else ''}")

    # ----- sync paths first (Image + Text) -----
    if image_ids:
        print()
        print(f"Running Image sync decompose for {len(image_ids)} ads…")
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(decompose_image_sync, client, cid, competitor): cid for cid in image_ids}
            for fut in as_completed(futs):
                cid = futs[fut]
                ok, detail = fut.result()
                print(f"  [{cid}] {'OK' if ok else 'FAIL'} — {detail}", flush=True)

    if text_ids:
        print()
        print(f"Running Text sync decompose for {len(text_ids)} ads…")
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(decompose_text_sync, client, cid, competitor): cid for cid in text_ids}
            for fut in as_completed(futs):
                cid = futs[fut]
                ok, detail = fut.result()
                print(f"  [{cid}] {'OK' if ok else 'FAIL'} — {detail}", flush=True)

    # ----- batch path for YouTube -----
    if not yt_ids:
        print()
        print("No YouTube videos in this submission — done (sync results already written).")
        return 0

    upload_state_path = UPLOADS_DIR / f"{competitor}.json"
    if not upload_state_path.exists():
        sys.exit(f"[error] no upload state at {upload_state_path}. Run 'upload' first.")
    state = json.loads(upload_state_path.read_text())

    missing = [cid for cid in yt_ids if cid not in state]
    if missing:
        sys.exit(f"[error] not uploaded yet: {missing}. Run 'upload' first.")

    from google.genai import types as gt
    inlined_requests = []
    for cid in yt_ids:
        vpath = video_path_for(cid, competitor)
        meta = ffprobe_meta(vpath) if vpath else {}
        file_uri = client.files.get(name=state[cid]).uri
        inlined_requests.append({
            "contents": [
                gt.Content(role="user", parts=[
                    gt.Part(text=VIDEO_PROMPT),
                    gt.Part(file_data=gt.FileData(mime_type="video/mp4",
                                                    file_uri=file_uri)),
                ]),
            ],
            "config": gt.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=16384,
                response_mime_type="application/json",
            ),
            "metadata": {"key": cid,
                          "duration_s": str(meta.get("duration_s") or "?")},
        })

    print()
    print(f"Submitting YouTube Batch with {len(inlined_requests)} requests…")
    job = client.batches.create(
        model=MODEL,
        src=inlined_requests,
        config={"display_name": f"step4-decompose-google-{competitor}-{int(time.time())}"},
    )
    short = job.name.split("/")[-1][:16] if "/" in job.name else job.name[:16]
    state_path = BATCHES_DIR / f"decompose_{short}.json"
    state_path.write_text(json.dumps({
        "short_id": short,
        "job_name": job.name,
        "competitor": competitor,
        "ids": yt_ids,
        "submitted_at": time.time(),
        "state_history": [{"t": time.time(), "state": str(job.state.name)}],
    }, indent=2))
    print()
    print(f"  submitted: {job.name}")
    print(f"  short id:  {short}")
    print(f"  state:     {job.state.name}")
    print()
    print(f"Now poll with:")
    print(f"  python3 scripts/step4_decompose.py poll {short}")
    return 0


# ---------------------------------------------------------------------------
# Poll sub-command
# ---------------------------------------------------------------------------

def cmd_poll(client, short_id: str) -> int:
    state_path = BATCHES_DIR / f"decompose_{short_id}.json"
    if not state_path.exists():
        sys.exit(f"[error] no batch state at {state_path}")
    state = json.loads(state_path.read_text())
    job_name = state["job_name"]

    job = client.batches.get(name=job_name)
    state["state_history"].append({"t": time.time(), "state": str(job.state.name)})
    state_path.write_text(json.dumps(state, indent=2))

    print(f"job:  {job_name}")
    print(f"state: {job.state.name}")
    elapsed = time.time() - state["submitted_at"]
    print(f"elapsed: {elapsed:.0f}s")

    if job.state.name not in ("JOB_STATE_SUCCEEDED", "BATCH_STATE_SUCCEEDED"):
        if job.state.name in ("JOB_STATE_FAILED", "BATCH_STATE_FAILED",
                                "JOB_STATE_CANCELLED", "BATCH_STATE_CANCELLED"):
            print(f"  TERMINAL FAILURE: {job.state.name}")
            if hasattr(job, "error") and job.error:
                print(f"  error: {job.error}")
            return 2
        print(f"  still running. Re-run this command in ~60 seconds.")
        return 1

    print()
    print("Job succeeded. Writing per-video sidecars…")
    written = 0
    failed = 0
    for resp in job.dest.inlined_responses:
        key = resp.metadata.get("key") if hasattr(resp, "metadata") and resp.metadata else None
        if not key:
            print(f"  WARN: response missing metadata.key, skipping")
            continue
        try:
            if hasattr(resp, "error") and resp.error:
                print(f"  [{key}] response error: {resp.error}")
                failed += 1
                continue
            text = resp.response.candidates[0].content.parts[0].text
            text = re.sub(r"^```(?:json)?\s*", "", text.strip())
            text = re.sub(r"\s*```$", "", text)
            parsed = json.loads(text)
            sidecar = {"competitor_id": key, "creative_format": "YouTubeVideo",
                       "parsed": parsed, "model": MODEL, "decoded_at": time.time()}
            (SCENES_DIR / f"{key}.json").write_text(json.dumps(sidecar, indent=2))
            written += 1
            scenes_n = len(parsed.get("scenes", []))
            chars_n = len(parsed.get("characters", []))
            print(f"  [{key}] OK — {scenes_n} scenes, {chars_n} characters")
        except json.JSONDecodeError as e:
            print(f"  [{key}] JSON decode failed: {e}")
            failed += 1
        except Exception as e:
            print(f"  [{key}] {type(e).__name__}: {e}")
            failed += 1

    print()
    print(f"DONE — {written} sidecars written, {failed} failed")
    return 0


# ---------------------------------------------------------------------------
# Status sub-command
# ---------------------------------------------------------------------------

def cmd_status() -> int:
    for p in sorted(BATCHES_DIR.glob("decompose_*.json")):
        state = json.loads(p.read_text())
        last = state.get("state_history", [{"state": "UNKNOWN"}])[-1]
        elapsed = time.time() - state["submitted_at"]
        print(f"{state['short_id']}  {state['competitor']:<15}  {last['state']:<22}  "
              f"{elapsed:.0f}s ago  ({len(state['ids'])} videos)")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_upload = sub.add_parser("upload")
    p_upload.add_argument("--competitor", required=True)
    p_upload.add_argument("ids", nargs="+")

    p_submit = sub.add_parser("submit")
    p_submit.add_argument("--competitor", required=True)
    p_submit.add_argument("ids", nargs="+")

    p_poll = sub.add_parser("poll")
    p_poll.add_argument("short_id")

    sub.add_parser("status")

    args = ap.parse_args()
    ensure_dirs()

    if args.cmd == "status":
        return cmd_status()

    client = get_client()

    if args.cmd == "upload":
        return cmd_upload(client, args.ids, args.competitor.lower().strip())
    if args.cmd == "submit":
        return cmd_submit(client, args.ids, args.competitor.lower().strip())
    if args.cmd == "poll":
        return cmd_poll(client, args.short_id)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
