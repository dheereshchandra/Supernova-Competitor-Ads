#!/usr/bin/env python3
"""
Step 4 — Stage 2 (Google): extract one screenshot per scene from each ad.

Format-aware:
  - YouTubeVideo: ffmpeg-extracts each scene's screenshot_at_s as orig_NN.jpg
  - Image: copies the local image to orig_01.jpg
  - Text: no-op (no frames needed)

Reads each row's step4_workspace/scenes/<creative_id>.json sidecar.

Idempotent: skips any orig_NN.jpg that already exists.

Usage:
    python3 scripts/step4_frames.py --competitor zinglish <creative_id1> <creative_id2> ...
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

WORKSPACE = pathlib.Path("step4_workspace")
SCENES_DIR = WORKSPACE / "scenes"
FRAMES_DIR = WORKSPACE / "frames"


def find_master_row(creative_id: str, competitor: str) -> dict | None:
    master_path = pathlib.Path("master") / f"{competitor}.csv"
    if not master_path.exists():
        return None
    with master_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("creative_id") or "").strip() == creative_id:
                return row
    return None


def video_path_for(creative_id: str, competitor: str) -> pathlib.Path | None:
    candidates = sorted(pathlib.Path("videos").glob(f"{competitor}-*"))
    if not candidates:
        return None
    vdir = candidates[-1]
    p = vdir / f"{creative_id}.mp4"
    return p if p.exists() else None


def image_path_for(creative_id: str, competitor: str) -> pathlib.Path | None:
    candidates = sorted(pathlib.Path("images").glob(f"{competitor}-*"))
    if not candidates:
        return None
    idir = candidates[-1]
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        p = idir / f"{creative_id}{ext}"
        if p.exists():
            return p
    return None


def extract_one(video_path: pathlib.Path, t: float, out_path: pathlib.Path) -> bool:
    if out_path.exists() and out_path.stat().st_size > 5000:
        return True
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(t), "-i", str(video_path),
             "-vframes", "1", "-q:v", "2", str(out_path)],
            capture_output=True, timeout=15, check=True,
        )
        return out_path.exists() and out_path.stat().st_size > 5000
    except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
        return False


def process_row(creative_id: str, competitor: str) -> dict:
    sidecar = SCENES_DIR / f"{creative_id}.json"
    if not sidecar.exists():
        return {"id": creative_id, "status": "no-sidecar", "extracted": 0, "failed": 0}

    data = json.loads(sidecar.read_text())
    parsed = data.get("parsed", {})
    fmt = data.get("creative_format") or parsed.get("creative_format", "YouTubeVideo")

    frame_dir = FRAMES_DIR / creative_id
    frame_dir.mkdir(parents=True, exist_ok=True)

    # Text: no frames
    if fmt == "Text":
        return {"id": creative_id, "status": "ok", "format": fmt,
                "extracted": 0, "skipped": 0, "failed": 0, "scenes": 0,
                "note": "Text format — no frames needed"}

    # Image: copy local image
    if fmt == "Image" or fmt in ("Shopping", "Maps"):
        img = image_path_for(creative_id, competitor)
        if img is None:
            return {"id": creative_id, "status": "no-image", "extracted": 0, "failed": 1}
        out_path = frame_dir / "orig_01.jpg"
        if out_path.exists() and out_path.stat().st_size > 5000:
            return {"id": creative_id, "status": "ok", "format": fmt,
                    "extracted": 0, "skipped": 1, "failed": 0, "scenes": 1}
        try:
            # Normalise to JPEG via ffmpeg (handles png/webp input)
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(img), "-q:v", "2", str(out_path)],
                capture_output=True, timeout=15, check=True,
            )
            ok = out_path.exists() and out_path.stat().st_size > 5000
        except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
            # Fallback: bare copy (may not be JPEG — Stage 6 will handle)
            shutil.copy(img, out_path)
            ok = out_path.exists()
        return {"id": creative_id, "status": "ok" if ok else "extract-failed",
                "format": fmt, "extracted": 1 if ok else 0,
                "skipped": 0, "failed": 0 if ok else 1, "scenes": 1}

    # YouTubeVideo (default)
    video = video_path_for(creative_id, competitor)
    if video is None:
        return {"id": creative_id, "status": "no-video", "extracted": 0, "failed": 0}

    scenes = parsed.get("scenes", [])
    if not scenes:
        return {"id": creative_id, "status": "no-scenes", "extracted": 0, "failed": 0}

    extracted = 0
    failed = 0
    skipped = 0
    for scene in scenes:
        n = scene.get("n", 0)
        t = scene.get("screenshot_at_s")
        if t is None:
            s = scene.get("start_s", 0)
            e = scene.get("end_s", s + 1)
            t = (s + e) / 2
        out_path = frame_dir / f"orig_{n:02d}.jpg"
        if out_path.exists() and out_path.stat().st_size > 5000:
            skipped += 1
            continue
        if extract_one(video, float(t), out_path):
            extracted += 1
        else:
            failed += 1

    return {"id": creative_id, "status": "ok", "format": fmt,
            "extracted": extracted, "skipped": skipped, "failed": failed,
            "scenes": len(scenes)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competitor", required=True)
    ap.add_argument("ids", nargs="+")
    args = ap.parse_args()

    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    competitor = args.competitor.lower().strip()

    print(f"Stage 2 — extracting frames for {len(args.ids)} ads")
    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(process_row, cid, competitor): cid for cid in args.ids}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            note = f" [{r['note']}]" if r.get("note") else ""
            print(f"  [{r['id']}] {r['status']}  format={r.get('format', '?')}  "
                  f"extracted={r.get('extracted', 0)} skipped={r.get('skipped', 0)} "
                  f"failed={r.get('failed', 0)} (scenes={r.get('scenes', '?')}){note}",
                  flush=True)

    fail_count = sum(1 for r in results if r['status'] not in ('ok',) or r.get('failed', 0) > 0)
    print(f"\nStage 2 done — {len(results)} rows processed, {fail_count} with failures")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
