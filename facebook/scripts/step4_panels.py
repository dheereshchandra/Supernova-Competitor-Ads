#!/usr/bin/env python3
"""
Step 4 — Stage 4: generate clean (text-free) panel imagery via Nano Banana Pro.

For each scene's panels[] in the decompose sidecar, build a prompt from the
panel_visual_description plus the character reference sheets generated in
Stage 3, and ask Nano Banana Pro to render the same scene composition WITHOUT
text overlays, captions, brand bugs, or UI.

Output: step4_workspace/images/<id>/gen_<NN>_<pos>.jpg

Deadline-bounded parallel-sync runner. ~25-30 panels per ~38-second window.
Re-run until status shows nothing left.

Usage:
    python3 scripts/step4_panels.py --competitor zinglish <id1> <id2> ...
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _casting  # noqa: E402  — shared India-localisation + Miss Nova casting rules (feedback #8)

WORKSPACE = pathlib.Path("step4_workspace")
SCENES_DIR = WORKSPACE / "scenes"
IMAGES_DIR = WORKSPACE / "images"
FRAMES_DIR = WORKSPACE / "frames"

MODEL_IMG = "gemini-3-pro-image-preview"
DEADLINE_SEC = 38


def _aspect_ratio_for_ad(ad_id: str) -> str:
    """Pick the panel aspect ratio that matches the source ad.

    Reads the decompose sidecar's recorded resolution if present, otherwise
    ffprobes the source video / image. Falls back to "9:16" (vertical mobile)
    which is what the vast majority of competitor ads are.
    """
    sidecar = SCENES_DIR / f"{ad_id}.json"
    w, h = None, None
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text())
            res = data.get("source_resolution") or ""
            if isinstance(res, str) and "x" in res:
                a, b = res.split("x", 1)
                w, h = int(a), int(b)
        except (json.JSONDecodeError, ValueError, OSError):
            pass
    if w and h:
        r = w / h
        if r > 1.4:
            return "16:9"
        if r < 0.7:
            return "9:16"
        return "1:1"
    return "9:16"


def _build_image_config(gt, aspect_ratio: str = "9:16", image_size: str = "2K"):
    """Same shape as step4_character_sheets._build_image_config (HANDOVER §9.7)."""
    try:
        return gt.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=gt.ImageConfig(
                aspect_ratio=aspect_ratio,
                image_size=image_size,
            ),
        )
    except (AttributeError, TypeError):
        pass
    try:
        return gt.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config={"aspect_ratio": aspect_ratio, "image_size": image_size},
        )
    except (AttributeError, TypeError):
        pass
    return gt.GenerateContentConfig(response_modalities=["IMAGE"])


def load_env() -> dict:
    env = {}
    for line in pathlib.Path(".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def build_panel_prompt(panel: dict, scene: dict, characters: list[dict]) -> str:
    """Build the prompt that briefs Nano Banana Pro for one clean panel."""
    chars_in_panel = panel.get("characters_in_panel", [])
    char_descs = []
    for c in characters:
        if c.get("id") in chars_in_panel:
            if _casting.is_ai_teacher(c):
                char_descs.append(
                    f"Character {c.get('id', '?')} is the AI teacher — render as MISS NOVA: "
                    f"{_casting.MISS_NOVA_DESC}"
                )
            else:
                char_descs.append(
                    f"Character {c.get('id', '?')} — {c.get('role', '')}. "
                    f"Source appearance (use for age/build/gender/expression, NOT ethnicity): "
                    f"{c.get('appearance', '')} "
                    f"Source wardrobe (localise to the Indian equivalent): {c.get('wardrobe', '')}."
                )

    return f"""Generate a single clean photorealistic image of this scene panel for an internal storyboarding workflow.

PANEL DESCRIPTION (what to draw):
{panel.get('panel_visual_description', '')}

SCENE CONTEXT:
- Setting: {scene.get('setting', '')}
- Camera framing: {scene.get('camera', '')}

CHARACTERS IN THIS PANEL:
{chr(10).join(char_descs) if char_descs else 'No human characters in this panel.'}

{_casting.INDIA_CASTING_RULE}

{_casting.INDIA_SETTING_RULE}

HARD REQUIREMENTS:
- Photorealistic for human characters; Miss Nova stays clean 3D-animated. Match the panel description's composition precisely.
- ZERO text overlays. ZERO captions. ZERO subtitles. ZERO infographics.
- ZERO brand logos, watermarks, app UI, end-cards, brand bugs.
- ZERO progress bars or video player controls.
- Just the underlying scene as if all those overlays were removed.
- Keep each character consistent across panels (same person/look).

Output: one image, no text, no commentary."""


def generate_one_panel(client, ad_id: str, scene: dict, panel: dict,
                        characters: list[dict], out_path: pathlib.Path
                        ) -> tuple[bool, str]:
    if out_path.exists() and out_path.stat().st_size > 30000:
        return True, "skip-exists"

    try:
        from google.genai import types as gt
        prompt = build_panel_prompt(panel, scene, characters)
        aspect = _aspect_ratio_for_ad(ad_id)
        resp = client.models.generate_content(
            model=MODEL_IMG,
            contents=prompt,
            config=_build_image_config(gt, aspect_ratio=aspect, image_size="2K"),
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
    """Return list of (ad_id, scene, panel, characters, out_path)."""
    work = []
    for ad_id in ids:
        sidecar = SCENES_DIR / f"{ad_id}.json"
        if not sidecar.exists():
            continue
        data = json.loads(sidecar.read_text())
        parsed = data.get("parsed", {})
        scenes = parsed.get("scenes", [])
        characters = parsed.get("characters", [])
        img_dir = IMAGES_DIR / ad_id
        img_dir.mkdir(parents=True, exist_ok=True)
        for scene in scenes:
            n = scene.get("n", 0)
            for panel in scene.get("panels", []):
                pos = panel.get("position", "full")
                out_path = img_dir / f"gen_{n:02d}_{pos}.jpg"
                if out_path.exists() and out_path.stat().st_size > 30000:
                    continue
                work.append((ad_id, scene, panel, characters, out_path))
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
    print(f"Stage 4 — {len(work)} panels to generate (across {len(args.ids)} videos)")
    if not work:
        print("Nothing to do.")
        return 0

    deadline = time.time() + DEADLINE_SEC
    completed = 0
    blocked = 0
    errored = 0

    with ThreadPoolExecutor(max_workers=args.max_parallel) as ex:
        futs = {ex.submit(generate_one_panel, client, aid, scene, panel, chars, out):
                (aid, scene.get('n'), panel.get('position'))
                for aid, scene, panel, chars, out in work}
        for fut in as_completed(futs):
            aid, n, pos = futs[fut]
            ok, msg = fut.result()
            tag = "OK" if ok else ("BLOCK" if "policy" in msg else "FAIL")
            print(f"  [{aid}] scene{n}_{pos}  {tag}  {msg}", flush=True)
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
