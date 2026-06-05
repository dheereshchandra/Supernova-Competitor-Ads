#!/usr/bin/env python3
"""
Step 4 — Stage 3 (Google): generate character reference sheets via Nano Banana Pro.

Only runs for sidecars whose creative_format is YouTubeVideo (the only format
with multi-scene character continuity needs). Image / Text / Shopping / Maps
rows are skipped silently — their sidecars either have no characters or a single
synthetic scene that doesn't need a sheet.

Deadline-bounded parallel-sync runner. Re-run until status shows nothing left.

Usage:
    python3 scripts/step4_character_sheets.py --competitor zinglish <creative_id1> ...

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


def generate_one_sheet(client, character: dict, out_path: pathlib.Path) -> tuple[bool, str]:
    if out_path.exists() and out_path.stat().st_size > 50000:
        return True, "skip-exists"

    try:
        from google.genai import types as gt
        prompt = build_sheet_prompt(character)
        resp = client.models.generate_content(
            model=MODEL_IMG,
            contents=prompt,
            config=gt.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )
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
        if "safety" in msg.lower() or "policy" in msg.lower() or "block" in msg.lower():
            return False, f"policy-block: {msg}"
        return False, f"error: {msg}"


def collect_pending_work(ids: list[str]) -> list[tuple[str, dict, pathlib.Path]]:
    work = []
    for cid in ids:
        sidecar = SCENES_DIR / f"{cid}.json"
        if not sidecar.exists():
            continue
        data = json.loads(sidecar.read_text())
        fmt = data.get("creative_format", "YouTubeVideo")
        if fmt != "YouTubeVideo":
            # Image/Text rows: no character sheets — single synthetic scene only
            continue
        chars = data.get("parsed", {}).get("characters", [])
        img_dir = IMAGES_DIR / cid
        img_dir.mkdir(parents=True, exist_ok=True)
        for char in chars:
            char_id = char.get("id", "?")
            out_path = img_dir / f"char_{char_id}_sheet.jpg"
            if out_path.exists() and out_path.stat().st_size > 50000:
                continue
            work.append((cid, char, out_path))
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
          f"(across {len(args.ids)} ads; non-video formats skipped)")
    if not work:
        print("Nothing to do.")
        return 0

    deadline = time.time() + DEADLINE_SEC
    completed = 0
    blocked = 0
    errored = 0

    with ThreadPoolExecutor(max_workers=args.max_parallel) as ex:
        futs = {ex.submit(generate_one_sheet, client, char, out): (cid, char.get('id'))
                for cid, char, out in work}
        for fut in as_completed(futs):
            cid, char_id = futs[fut]
            ok, msg = fut.result()
            tag = "OK" if ok else ("BLOCK" if "policy" in msg else "FAIL")
            print(f"  [{cid}] char_{char_id}  {tag}  {msg}", flush=True)
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

    print(f"\nStage 3 done — {completed} new sheets, {blocked} policy-blocked, {errored} errored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
