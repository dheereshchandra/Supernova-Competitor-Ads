#!/usr/bin/env python3
"""
Step 4 — Stage 4 (Google): generate clean (text-free) panel imagery via Nano Banana Pro.

For each scene's panels[] in the decompose sidecar, build a prompt and ask
Nano Banana Pro to render the scene without text overlays, captions, brand
bugs, or UI.

Format-aware:
  - YouTubeVideo: full multi-scene panel gen (same as FB)
  - Image:        one panel per the single synthetic scene
  - Text:         no panels (sidecar has empty panels[])

Output: step4_workspace/images/<creative_id>/gen_<NN>_<pos>.jpg

Deadline-bounded parallel-sync runner. Re-run until status shows nothing left.

Usage:
    python3 scripts/step4_panels.py --competitor zinglish <creative_id1> ...
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

WORKSPACE = pathlib.Path("step4_workspace")
SCENES_DIR = WORKSPACE / "scenes"
IMAGES_DIR = WORKSPACE / "images"
FRAMES_DIR = WORKSPACE / "frames"

MODEL_IMG = "gemini-3-pro-image-preview"
DEADLINE_SEC = 38


def load_env() -> dict:
    env = {}
    for line in pathlib.Path(".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def build_panel_prompt(panel: dict, scene: dict, characters: list[dict]) -> str:
    chars_in_panel = panel.get("characters_in_panel", [])
    char_descs = []
    for c in characters:
        if c.get("id") in chars_in_panel:
            char_descs.append(
                f"Character {c.get('id', '?')} — {c.get('role', '')}. "
                f"Appearance: {c.get('appearance', '')} "
                f"Wardrobe: {c.get('wardrobe', '')}."
            )

    return f"""Generate a single clean photorealistic image of this scene panel for an internal storyboarding workflow.

PANEL DESCRIPTION (what to draw):
{panel.get('panel_visual_description', '')}

SCENE CONTEXT:
- Setting: {scene.get('setting', '')}
- Camera framing: {scene.get('camera', '')}

CHARACTERS IN THIS PANEL:
{chr(10).join(char_descs) if char_descs else 'No human characters in this panel.'}

HARD REQUIREMENTS:
- Photorealistic. Match the panel description precisely.
- ZERO text overlays. ZERO captions. ZERO subtitles. ZERO infographics.
- ZERO brand logos, watermarks, app UI, end-cards, brand bugs.
- ZERO progress bars or video player controls.
- Just the underlying scene as if all those overlays were removed.
- Characters must match the appearance/wardrobe descriptions exactly.

Output: one image, no text, no commentary."""


def generate_one_panel(client, creative_id: str, scene: dict, panel: dict,
                        characters: list[dict], out_path: pathlib.Path
                        ) -> tuple[bool, str]:
    if out_path.exists() and out_path.stat().st_size > 30000:
        return True, "skip-exists"

    try:
        from google.genai import types as gt
        prompt = build_panel_prompt(panel, scene, characters)
        resp = client.models.generate_content(
            model=MODEL_IMG,
            contents=prompt,
            config=gt.GenerateContentConfig(response_modalities=["IMAGE"]),
        )
        for part in resp.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                img_bytes = part.inline_data.data
                if isinstance(img_bytes, str):
                    import base64
                    img_bytes = base64.b64decode(img_bytes)
                out_path.write_bytes(img_bytes)
                if out_path.stat().st_size > 30000:
                    return True, "ok"
                else:
                    return False, "too-small"
        return False, "no-image-in-response"
    except Exception as e:
        msg = f"{type(e).__name__}: {str(e)[:120]}"
        if "safety" in msg.lower() or "policy" in msg.lower() or "block" in msg.lower():
            return False, f"policy-block: {msg}"
        return False, f"error: {msg}"


def collect_pending_work(ids: list[str]) -> list[tuple]:
    work = []
    for cid in ids:
        sidecar = SCENES_DIR / f"{cid}.json"
        if not sidecar.exists():
            continue
        data = json.loads(sidecar.read_text())
        fmt = data.get("creative_format", "YouTubeVideo")
        # Text rows: sidecar has empty panels[] — naturally no work
        if fmt == "Text":
            continue
        parsed = data.get("parsed", {})
        scenes = parsed.get("scenes", [])
        characters = parsed.get("characters", [])
        img_dir = IMAGES_DIR / cid
        img_dir.mkdir(parents=True, exist_ok=True)
        for scene in scenes:
            n = scene.get("n", 0)
            for panel in scene.get("panels", []):
                pos = panel.get("position", "full")
                out_path = img_dir / f"gen_{n:02d}_{pos}.jpg"
                if out_path.exists() and out_path.stat().st_size > 30000:
                    continue
                work.append((cid, scene, panel, characters, out_path))
    return work


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competitor", required=True)
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--max-parallel", type=int, default=8)
    args = ap.parse_args()

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    env = load_env()
    if not env.get("GEMINI_API_KEY"):
        sys.exit("[error] GEMINI_API_KEY missing")

    from google import genai
    client = genai.Client(api_key=env["GEMINI_API_KEY"])

    work = collect_pending_work(args.ids)
    print(f"Stage 4 — {len(work)} panels to generate (across {len(args.ids)} ads; Text rows skipped)")
    if not work:
        print("Nothing to do.")
        return 0

    deadline = time.time() + DEADLINE_SEC
    completed = 0
    blocked = 0
    errored = 0

    with ThreadPoolExecutor(max_workers=args.max_parallel) as ex:
        futs = {ex.submit(generate_one_panel, client, cid, scene, panel, chars, out):
                (cid, scene.get('n'), panel.get('position'))
                for cid, scene, panel, chars, out in work}
        for fut in as_completed(futs):
            cid, n, pos = futs[fut]
            ok, msg = fut.result()
            tag = "OK" if ok else ("BLOCK" if "policy" in msg else "FAIL")
            print(f"  [{cid}] scene{n}_{pos}  {tag}  {msg}", flush=True)
            if ok:
                completed += 1
            elif "policy" in msg:
                blocked += 1
            else:
                errored += 1
            if time.time() > deadline:
                for f in futs:
                    f.cancel()
                print(f"\nDEADLINE — {completed} done, {len(work) - completed} remaining. "
                      f"Re-run this script to continue.")
                return 1

    print(f"\nStage 4 done — {completed} new panels, {blocked} policy-blocked, {errored} errored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
