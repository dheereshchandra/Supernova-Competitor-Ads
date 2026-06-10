#!/usr/bin/env python3
"""
Step 4 — Stage 1: video decomposition via Gemini 3.1 Pro Batch API.

Sub-commands:
    upload   <id1> <id2> ...           Upload videos to Files API (resumable).
    submit   <id1> <id2> ...           Submit a decompose Batch job.
    poll     <job_short_id>            Poll the named job; on success write sidecars.
    status                              List in-flight batch jobs.
    images   <id1> <id2> ...           Image-only ads: synchronous per-image Pro call,
                                       writes a video-shaped sidecar directly (no Batch,
                                       no Files API, no polling). HANDOVER §9.5.

Workflow (mirrors competitor-video-scenes skill's pattern):
    1. python3 step4_decompose.py upload <ids...>
    2. python3 step4_decompose.py submit <ids...>
       → prints job_short_id
    3. python3 step4_decompose.py poll <job_short_id>
       → re-run every minute or so until SUCCEEDED

Outputs land at step4_workspace/scenes/<id>.json with the schema documented in
skills/fb-ads-video-analysis/SKILL.md "Stage 1".

All sub-commands are idempotent. Re-running upload skips already-uploaded files;
re-running submit creates a new batch (use only if you need to retry a failed
one); re-running poll re-checks status.
"""
from __future__ import annotations

import argparse
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

# Decompose prompt — lifted from competitor-video-scenes skill for schema
# compatibility. This is the single canonical scene-decompose schema.
PROMPT = """You are analysing a short Indian-language video advertisement to support storyboarding for a competitor brand's recreation.

Watch the video AND listen to the audio carefully. Reply with EXACTLY ONE JSON object — no markdown fences, no commentary. Schema:

{
  "duration_s": <float, total video length>,
  "production_type": "human-recorded" | "AI-generated" | "mixed",
  "production_notes": "<1-2 sentences explaining your reasoning — look for uncanny faces, perfectly static cuts, AI-typical fingers/eyes, unnatural lighting, etc.>",

  "characters": [
    {
      "id": "A",
      "role": "<e.g. male presenter, female learner, AI tutor avatar>",
      "appearance": "<2-3 sentence reusable physical description: age, build, complexion, hair, facial features, distinguishing marks. Detailed enough to redraw consistently.>",
      "wardrobe": "<what they are wearing throughout the video, including colors and styling>",
      "demeanor": "<expression / body language vibe>"
    }
  ],

  "scenes": [
    {
      "n": 1,
      "start_s": 0.0,
      "end_s": 4.5,
      "screenshot_at_s": 2.0,
      "scene_label": "<short title for this beat>",
      "setting": "<location, time of day, props, color palette>",
      "characters_in_scene": ["A", "B"],
      "camera": "<framing: e.g. medium close-up, over-shoulder, wide, talking-head, split-screen, app-screencast>",
      "layout": "<one of: single | split-horizontal (top/bottom) | split-vertical (left/right) | inset (PIP) | grid>",
      "panels": [
        {
          "position": "<for split-horizontal: 'top' or 'bottom'; for split-vertical: 'left' or 'right'; for inset: 'background' or 'inset'; for single: 'full'>",
          "panel_visual_description": "<5-8 sentence CLEAN visual description of ONLY this panel, written so it can directly brief an image-generation model. Critical: describe ONLY the imagery — no text overlays, captions, subtitles, infographics, callouts, watermarks, logos, app UI, end-cards, brand bugs, or progress bars. Describe characters, props, setting, lighting, composition, framing, expressions, blocking. Reference characters by their stable id (Character A, Character B).>",
          "characters_in_panel": ["A"]
        }
      ],
      "visual_description": "<5-8 sentences describing the WHOLE composite shot (all panels together, including text/UI overlays). For analyst reference; not used for image generation.>",
      "audio_transcript": "<verbatim transcript of speech in this scene. CRITICAL: prefix EVERY spoken line with the speaking character's ID, e.g. 'Character A says: मुझे एटीएम कार्ड एक्टिवेट करवाना है। [I want to get my ATM card activated.]'. Each line on its own paragraph. Use native script (Devanagari/Tamil/Bengali/etc.) for the original speech, followed by a bracketed [English translation]. If a section is music with no speech, write '[music only, no speech]'. If a speaker can't be identified, label them 'Unknown speaker'.>",
      "on_screen_text": "<verbatim text overlays, captions, end-card copy visible in this scene. Original script + English in parentheses for non-Latin. This is for analyst reference and is intentionally NOT included in panel_visual_description.>"
    }
  ]
}

Rules:
- Pick scene boundaries at natural cuts / shot changes / location changes. Don't over-segment; aim for 4-10 scenes for a 30-90 second ad. For very short ads (<15s), 2-4 scenes is fine.
- screenshot_at_s should be a moment that best represents the scene (typically the midpoint).
- Reference characters by their stable id (A/B/C) so the same person stays consistent across scenes.
- For split-screen scenes, list ALL panels in the panels[] array (top AND bottom, etc.).
- For single-layout scenes, panels[] has exactly one entry with position='full'.
- CRITICAL: panel_visual_description must EXCLUDE all text overlays, captions, subtitles, infographics, logos, app UI, end-cards, brand bugs, callouts, watermarks, progress bars, and any other graphic-overlay element. Describe ONLY the underlying scene as if those overlays were removed. The editing team will add the overlays themselves later.
- Be precise. Don't invent details that aren't in the video.
"""


# ---------------------------------------------------------------------------
# Setup
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


def video_path_for(ad_id: str, competitor: str) -> Optional[pathlib.Path]:
    """Find the local .mp4 for an ad_library_id. Searches ALL dated folders
    (newest first), not just the latest — a long-running ad's video may have been
    downloaded in an earlier scrape and never re-downloaded. Tries primary + variants."""
    for vdir in sorted(pathlib.Path("videos").glob(f"{competitor}-*"), reverse=True):
        for fname in (f"{ad_id}.mp4", f"{ad_id}_v2.mp4", f"{ad_id}_v3.mp4"):
            p = vdir / fname
            if p.exists():
                return p
    return None


def image_path_for(ad_id: str, competitor: str) -> Optional[pathlib.Path]:
    """Find the local .jpg for an Image-type ad_library_id. Mirrors video_path_for()
    but in images/{competitor}-*/ instead of videos/. Tries primary + variants per
    the convention in scripts/download_fb_images.py and HANDOVER §8.5. Searches ALL
    dated folders (newest first), not just the latest."""
    for idir in sorted(pathlib.Path("images").glob(f"{competitor}-*"), reverse=True):
        for fname in (f"{ad_id}.jpg", f"{ad_id}_c2.jpg", f"{ad_id}_c3.jpg",
                      f"{ad_id}_c4.jpg", f"{ad_id}_c5.jpg"):
            p = idir / fname
            if p.exists():
                return p
    return None


def load_master_rows(competitor: str) -> dict:
    """Return {ad_library_id: master_row_dict}. Used to read ad_media_type, ad_primary_text,
    etc. when building image-only decompose prompts."""
    import csv
    master_path = pathlib.Path("master") / f"{competitor}.csv"
    if not master_path.exists():
        return {}
    out = {}
    with master_path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            aid = (row.get("ad_library_id") or "").strip()
            if aid:
                out[aid] = row
    return out


def ffprobe_meta(video_path: pathlib.Path) -> dict:
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(video_path),
        ], timeout=15).decode()
        data = json.loads(out)
        duration = float(data.get("format", {}).get("duration", 0.0))
        w = h = None
        for s in data.get("streams", []):
            if s.get("codec_type") == "video" and w is None:
                w, h = s.get("width"), s.get("height")
        return {"duration_s": round(duration, 2),
                "resolution": f"{w}x{h}" if w else None}
    except (subprocess.SubprocessError, OSError, ValueError):
        return {"duration_s": None, "resolution": None}


# ---------------------------------------------------------------------------
# Upload sub-command
# ---------------------------------------------------------------------------

def cmd_upload(client, ids: list[str], competitor: str) -> int:
    """Upload each video to Files API, store {id: file_name} mapping."""
    upload_state_path = UPLOADS_DIR / f"{competitor}.json"
    state = json.loads(upload_state_path.read_text()) if upload_state_path.exists() else {}

    # Check which uploaded files are still active server-side
    still_active = {}
    for ad_id, file_name in state.items():
        try:
            f = client.files.get(name=file_name)
            if f.state.name == "ACTIVE":
                still_active[ad_id] = file_name
        except Exception:
            pass
    state = still_active

    to_upload = [aid for aid in ids if aid not in state]
    print(f"to_upload: {len(to_upload)}/{len(ids)} (skipping {len(state)} already-uploaded)")

    if not to_upload:
        print("nothing to upload")
        upload_state_path.write_text(json.dumps(state, indent=2))
        return 0

    def _upload_one(ad_id: str) -> tuple[str, str, Optional[str]]:
        vpath = video_path_for(ad_id, competitor)
        if vpath is None:
            return ad_id, "NO VIDEO", None
        try:
            up = client.files.upload(file=str(vpath),
                                     config={"mime_type": "video/mp4",
                                             "display_name": ad_id})
            return ad_id, "OK", up.name
        except Exception as e:
            return ad_id, f"FAIL {type(e).__name__}: {str(e)[:120]}", None

    def _persist_state() -> None:
        """Atomic write so bash-cap kills mid-write don't corrupt the state file."""
        tmp = upload_state_path.with_suffix(upload_state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.replace(upload_state_path)

    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(_upload_one, ad_id): ad_id for ad_id in to_upload}
        for fut in as_completed(futs):
            ad_id, status, file_name = fut.result()
            print(f"  [{ad_id}] {status}  {file_name or ''}", flush=True)
            if file_name:
                state[ad_id] = file_name
                # Persist after EACH successful upload so a SIGTERM doesn't
                # erase our memory of files Gemini already accepted. Otherwise
                # the next invocation re-uploads them, wasting bandwidth and
                # the user's Gemini quota.
                _persist_state()

    _persist_state()

    # Wait for ACTIVE state (Gemini processes the video upload)
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
            except Exception as e:
                print(f"  status check error for {name}: {e}")
                still_waiting.append(name)
        waiting = still_waiting
        if waiting:
            time.sleep(3)
    if waiting:
        print(f"  warning: {len(waiting)} files still not ACTIVE after 120s")
    else:
        print(f"  all {len(state)} files ACTIVE")
    return 0


# ---------------------------------------------------------------------------
# Submit sub-command
# ---------------------------------------------------------------------------

def cmd_submit(client, ids: list[str], competitor: str) -> int:
    """Build inline requests and submit a Gemini Batch job."""
    upload_state_path = UPLOADS_DIR / f"{competitor}.json"
    if not upload_state_path.exists():
        sys.exit(f"[error] no upload state at {upload_state_path}. Run 'upload' first.")
    state = json.loads(upload_state_path.read_text())

    missing = [aid for aid in ids if aid not in state]
    if missing:
        sys.exit(f"[error] not uploaded yet: {missing}. Run 'upload' first.")

    from google.genai import types as gt
    inlined_requests = []
    for ad_id in ids:
        vpath = video_path_for(ad_id, competitor)
        meta = ffprobe_meta(vpath) if vpath else {}
        file_uri = client.files.get(name=state[ad_id]).uri
        inlined_requests.append({
            "contents": [
                gt.Content(role="user", parts=[
                    gt.Part(text=PROMPT),
                    gt.Part(file_data=gt.FileData(mime_type="video/mp4",
                                                  file_uri=file_uri)),
                ]),
            ],
            "config": gt.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=16384,
                response_mime_type="application/json",
            ),
            "metadata": {"key": ad_id,
                         "duration_s": str(meta.get("duration_s") or "?")},
        })

    print(f"Submitting batch with {len(inlined_requests)} requests for competitor '{competitor}'…")
    job = client.batches.create(
        model=MODEL,
        src=inlined_requests,
        config={"display_name": f"step4-decompose-{competitor}-{int(time.time())}"},
    )
    short = job.name.split("/")[-1][:16] if "/" in job.name else job.name[:16]
    state_path = BATCHES_DIR / f"decompose_{short}.json"
    state_path.write_text(json.dumps({
        "short_id": short,
        "job_name": job.name,
        "competitor": competitor,
        "ids": ids,
        "submitted_at": time.time(),
        "state_history": [{"t": time.time(), "state": str(job.state.name)}],
    }, indent=2))
    print()
    print(f"  submitted: {job.name}")
    print(f"  short id:  {short}")
    print(f"  state:     {job.state.name}")
    print(f"  saved to:  {state_path}")
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
    print(f"elapsed since submission: {elapsed:.0f}s")

    if job.state.name not in ("JOB_STATE_SUCCEEDED", "BATCH_STATE_SUCCEEDED"):
        if job.state.name in ("JOB_STATE_FAILED", "BATCH_STATE_FAILED",
                              "JOB_STATE_CANCELLED", "BATCH_STATE_CANCELLED"):
            print(f"  TERMINAL FAILURE: {job.state.name}")
            if hasattr(job, "error") and job.error:
                print(f"  error: {job.error}")
            return 2
        print(f"  still running. Re-run this command in ~60 seconds.")
        return 1

    # SUCCEEDED — pull inline responses and write sidecars
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
            # Strip code-fence wrapping if any
            text = re.sub(r"^```(?:json)?\s*", "", text.strip())
            text = re.sub(r"\s*```$", "", text)
            parsed = json.loads(text)
            sidecar = {"competitor_id": key, "parsed": parsed,
                       "model": MODEL, "decoded_at": time.time()}
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
# Image-only sub-command (HANDOVER §9.5)
# ---------------------------------------------------------------------------

# Image-only decompose prompt. Output shape MATCHES the video schema so all
# downstream stages (frames, character_sheets, panels, rewrite, build_docs)
# work without media-type branching. The convention is:
#   - characters = [] (image ads usually feature stock people we don't track)
#   - scenes = exactly one entry, n=1, layout=single, one panel position=full
#   - audio_transcript = the ad's spoken-style copy (we hand-fill from master)
#     so the existing Supernova rewrite naturally produces a rewritten ad copy.
#   - on_screen_text = verbatim text visible IN the image
IMAGE_PROMPT = """You are analysing a single static image advertisement from the Meta Ad Library to support competitor creative analysis for Supernova, a Hindi spoken-English learning app.

You will receive ONE image and the ad's text copy from the ad library. Produce EXACTLY ONE JSON object — no markdown fences, no commentary — describing the image so it can drive a clean re-render (without text/UI overlays) and a brand-voice rewrite downstream.

Schema (match exactly; do not invent fields):

{
  "production_type": "human-photographed" | "AI-generated" | "stock" | "mixed",
  "production_notes": "<1-2 sentences explaining your reasoning. Look for AI-typical artefacts, perfect lighting, uncanny faces, fingers/eyes, etc.>",

  "characters": [],

  "scenes": [
    {
      "n": 1,
      "start_s": 0.0,
      "end_s": 0.0,
      "screenshot_at_s": 0.0,
      "scene_label": "<short title for this image, e.g. 'app screenshot with happy learner' or 'lifestyle photo with text overlay'>",
      "setting": "<location, props, color palette, mood>",
      "characters_in_scene": [],
      "camera": "single static frame",
      "layout": "single",
      "panels": [
        {
          "position": "full",
          "panel_visual_description": "<5-8 sentence CLEAN visual description of ONLY the image. Critical: describe ONLY the imagery — no text overlays, captions, app UI, infographics, logos, watermarks, end-cards, brand bugs. Describe the subject, setting, props, lighting, composition, framing.>",
          "characters_in_panel": []
        }
      ],
      "visual_description": "<5-8 sentences describing the WHOLE composite image — including any text overlays, UI elements, branding, end-cards. For analyst reference.>",
      "audio_transcript": "<the ad's COPY rephrased as if it were a voiceover narration. Use the AD COPY provided below verbatim where possible, formatted as natural sentences. Prefix with 'Narrator says:' so it matches the speaker-attributed style of video sidecars. Keep the original native script (Devanagari/Tamil/etc.) followed by a bracketed [English translation] if the copy is non-English.>",
      "on_screen_text": "<verbatim text VISIBLE IN THE IMAGE (not the ad copy that's separate from the image — only what's literally rendered on the image pixels). Include all captions, slogans, prices, CTAs, UI labels. Original script + English in parentheses for non-Latin.>"
    }
  ]
}

AD COPY (already provided to you separately by the ad library; use this to fill audio_transcript):
- Primary text: __AD_PRIMARY_TEXT__
- Description:  __AD_DESCRIPTION__
- CTA label:    __AD_CTA_LABEL__

Rules:
- characters MUST be []. Don't invent character entries for image ads.
- scenes MUST have exactly one entry.
- panels MUST have exactly one entry with position='full'.
- panel_visual_description MUST exclude all text/UI/branding — describe only the underlying photographed/rendered scene.
- on_screen_text MUST be the literal text visible inside the image's pixels, not the ad copy.
- audio_transcript MUST be the ad copy rephrased as narration (use the copy provided above).
- Be precise. Don't invent details that aren't in the image.
"""


def cmd_decompose_images(client, ids: list[str], competitor: str) -> int:
    """Synchronous per-image Gemini Pro analysis for Image-type ads.

    Bypasses Files API and Batch — for a single image inline upload is faster
    than a batch round-trip. Writes a video-shaped sidecar to scenes/<id>.json
    with is_image_only=True so build_docs can choose the right header.
    """
    import csv, re as _re
    master = load_master_rows(competitor)
    if not master:
        sys.exit(f"[error] no master CSV for {competitor}. Run Step 3 first.")

    from google.genai import types as gt

    written = 0
    skipped = 0
    failed = 0
    for ad_id in ids:
        sidecar_path = SCENES_DIR / f"{ad_id}.json"
        if sidecar_path.exists():
            # Idempotent: skip if already decomposed
            print(f"  [{ad_id}] skip-exists — sidecar already at {sidecar_path}")
            skipped += 1
            continue

        master_row = master.get(ad_id)
        if not master_row:
            print(f"  [{ad_id}] SKIP — not in master/{competitor}.csv")
            skipped += 1
            continue
        if (master_row.get("ad_media_type") or "").strip() != "Image":
            print(f"  [{ad_id}] SKIP — ad_media_type is not 'Image' "
                  f"({master_row.get('ad_media_type')!r}); use upload/submit/poll instead")
            skipped += 1
            continue

        img_path = image_path_for(ad_id, competitor)
        if img_path is None:
            print(f"  [{ad_id}] SKIP — local image not found in images/{competitor}-*/")
            skipped += 1
            continue

        try:
            img_bytes = img_path.read_bytes()
            prompt = (IMAGE_PROMPT
                      .replace("__AD_PRIMARY_TEXT__", master_row.get("ad_primary_text") or "(none)")
                      .replace("__AD_DESCRIPTION__",  master_row.get("ad_description") or "(none)")
                      .replace("__AD_CTA_LABEL__",    master_row.get("ad_cta_label") or "(none)"))
            resp = client.models.generate_content(
                model=MODEL,
                contents=[
                    gt.Part(text=prompt),
                    gt.Part(inline_data=gt.Blob(mime_type="image/jpeg", data=img_bytes)),
                ],
                config=gt.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                ),
            )
            text = resp.candidates[0].content.parts[0].text
            text = _re.sub(r"^```(?:json)?\s*", "", text.strip())
            text = _re.sub(r"\s*```$", "", text)
            parsed = json.loads(text)
            sidecar = {
                "competitor_id": ad_id,
                "is_image_only": True,
                "source_image_path": str(img_path),
                "parsed": parsed,
                "model": MODEL,
                "decoded_at": time.time(),
            }
            sidecar_path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False))
            written += 1
            n_scenes = len(parsed.get("scenes", []))
            print(f"  [{ad_id}] OK — {n_scenes} scene(s), image-only sidecar")
        except json.JSONDecodeError as e:
            failed += 1
            print(f"  [{ad_id}] JSON decode failed: {e}")
        except Exception as e:
            failed += 1
            print(f"  [{ad_id}] {type(e).__name__}: {str(e)[:140]}")

    print()
    print(f"DONE — {written} sidecars written, {skipped} skipped, {failed} failed")
    return 0 if failed == 0 else 1


# ---------------------------------------------------------------------------
# Status sub-command
# ---------------------------------------------------------------------------

def cmd_status() -> int:
    for p in sorted(BATCHES_DIR.glob("decompose_*.json")):
        state = json.loads(p.read_text())
        last = state.get("state_history", [{"state": "UNKNOWN"}])[-1]
        elapsed = time.time() - state["submitted_at"]
        print(f"{state['short_id']}  {state['competitor']:<15}  {last['state']:<22}  {elapsed:.0f}s ago  ({len(state['ids'])} videos)")
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

    p_images = sub.add_parser("images",
        help="Image-only ads: synchronous per-image Pro call. Writes a video-shaped "
             "sidecar so downstream stages work without modification. HANDOVER §9.5.")
    p_images.add_argument("--competitor", required=True)
    p_images.add_argument("ids", nargs="+")

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
    if args.cmd == "images":
        return cmd_decompose_images(client, args.ids, args.competitor.lower().strip())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
