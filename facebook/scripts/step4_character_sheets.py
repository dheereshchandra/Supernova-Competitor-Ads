#!/usr/bin/env python3
"""
Step 4 — Stage 3: generate character reference sheets via Nano Banana Pro.

For each character in each video's decompose sidecar, build a prompt from the
character's appearance/wardrobe/demeanor description and generate a clean
reference sheet image. Output: step4_workspace/images/<id>/char_<X>_sheet.jpg.

Deadline-bounded parallel-sync runner. Designed to clear ~10–15 sheets per
~38-second bash window (each call is ~20–30s; parallel across threads).
Re-run until status shows nothing left.

Usage:
    python3 scripts/step4_character_sheets.py --competitor zinglish <id1> <id2> ...

Idempotent: skips sheets that already exist on disk.
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

MODEL_IMG = "gemini-3-pro-image-preview"

DEADLINE_SEC = 38  # safe margin under Cowork's 45s bash cap


def load_env() -> dict:
    env = {}
    for line in pathlib.Path(".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def build_sheet_prompt(character: dict) -> str:
    return f"""Generate a single clean character reference sheet image. This is for an internal storyboarding workflow at Supernova, a Hindi spoken-English app — we are recreating a competitor advertisement and need a consistent visual reference for one character across multiple scenes.

Character ID: {character.get('id', '?')}
Role: {character.get('role', '')}

Appearance: {character.get('appearance', '')}

Wardrobe: {character.get('wardrobe', '')}

Demeanor: {character.get('demeanor', '')}

REQUIREMENTS:
- A single clean studio-style portrait of this character against a neutral light grey background.
- 3/4 view, head-and-shoulders to mid-torso, looking slightly off-camera.
- Photorealistic style, natural lighting, no text, no captions, no watermarks, no logos.
- Skin tone, hair, build, age, wardrobe MUST match the description above precisely.
- Composition: subject centred, plenty of clean space around for clipping.

Output: one image, no text, no commentary."""


def _build_image_config(gt, aspect_ratio: str = "1:1", image_size: str = "2K"):
    """Build Nano Banana Pro image_config asking for max resolution.

    Resolution policy (HANDOVER §9.7): every Gemini image call MUST request
    image_size="2K" so the output is ~2048px on the long edge. Some SDK
    versions use `types.ImageConfig`, others accept a plain dict — we try
    both and fall through to a bare response_modalities config if the SDK is
    older than the image_config feature.
    """
    cfg = {"response_modalities": ["IMAGE"]}
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
    return gt.GenerateContentConfig(**cfg)


def generate_one_sheet(client, character: dict, out_path: pathlib.Path) -> tuple[bool, str]:
    """Returns (success, msg). Writes to out_path on success.

    Resolution: requests 2K @ 1:1 — character sheets are studio-portrait style,
    square framing is the cleanest reference for downstream panel generation.
    """
    if out_path.exists() and out_path.stat().st_size > 50000:
        return True, "skip-exists"

    try:
        from google.genai import types as gt
        prompt = build_sheet_prompt(character)
        resp = client.models.generate_content(
            model=MODEL_IMG,
            contents=prompt,
            config=_build_image_config(gt, aspect_ratio="1:1", image_size="2K"),
        )
        # Pull the first inline image part out of the response
        for part in resp.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                img_bytes = part.inline_data.data
                if isinstance(img_bytes, str):
                    import base64
                    img_bytes = base64.b64decode(img_bytes)
                out_path.write_bytes(img_bytes)
                if out_path.stat().st_size > 50000:
                    return True, "ok"
                else:
                    return False, "too-small"
        return False, "no-image-in-response"
    except Exception as e:
        msg = f"{type(e).__name__}: {str(e)[:120]}"
        # Distinguish content-policy blocks from real errors
        if "safety" in msg.lower() or "policy" in msg.lower() or "block" in msg.lower():
            return False, f"policy-block: {msg}"
        return False, f"error: {msg}"


def collect_pending_work(ids: list[str]) -> list[tuple[str, dict, pathlib.Path]]:
    """Return list of (ad_id, character_dict, out_path) for sheets not yet on disk."""
    work = []
    for ad_id in ids:
        sidecar = SCENES_DIR / f"{ad_id}.json"
        if not sidecar.exists():
            continue
        data = json.loads(sidecar.read_text())
        chars = data.get("parsed", {}).get("characters", [])
        img_dir = IMAGES_DIR / ad_id
        img_dir.mkdir(parents=True, exist_ok=True)
        for char in chars:
            cid = char.get("id", "?")
            out_path = img_dir / f"char_{cid}_sheet.jpg"
            if out_path.exists() and out_path.stat().st_size > 50000:
                continue
            work.append((ad_id, char, out_path))
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
    print(f"Stage 3 — {len(work)} character sheets to generate "
          f"(across {len(args.ids)} videos)")
    if not work:
        print("Nothing to do.")
        return 0

    deadline = time.time() + DEADLINE_SEC
    completed = 0
    blocked = 0
    errored = 0

    with ThreadPoolExecutor(max_workers=args.max_parallel) as ex:
        futs = {ex.submit(generate_one_sheet, client, char, out): (aid, char.get('id'))
                for aid, char, out in work}
        for fut in as_completed(futs):
            aid, cid = futs[fut]
            ok, msg = fut.result()
            tag = "OK" if ok else ("BLOCK" if "policy" in msg else "FAIL")
            print(f"  [{aid}] char_{cid}  {tag}  {msg}", flush=True)
            if ok:
                completed += 1
            elif "policy" in msg:
                blocked += 1
            else:
                errored += 1
            if time.time() > deadline:
                # Cancel remaining and bail
                for f in futs:
                    f.cancel()
                print(f"\nDEADLINE — {completed} done, {len(work) - completed} remaining. "
                      f"Re-run this script to continue.")
                return 1

    print(f"\nStage 3 done — {completed} new sheets, {blocked} policy-blocked, {errored} errored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
