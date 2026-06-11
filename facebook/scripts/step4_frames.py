#!/usr/bin/env python3
"""
Step 4 — Stage 2: extract one screenshot per scene from each video via ffmpeg.

Reads each row's step4_workspace/scenes/<id>.json sidecar, finds every scene's
screenshot_at_s, runs ffmpeg to extract that frame as orig_NN.jpg in
step4_workspace/frames/<id>/.

Idempotent: skips any orig_NN.jpg that already exists. Designed to fit
comfortably in one ~45s bash window for ~5 videos × 4 scenes each.

Usage:
    python3 scripts/step4_frames.py --competitor zinglish <id1> <id2> ...
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

WORKSPACE = pathlib.Path("step4_workspace")
SCENES_DIR = WORKSPACE / "scenes"
FRAMES_DIR = WORKSPACE / "frames"


def _is_embeddable_jpeg(path: pathlib.Path) -> bool:
    """True if the JPEG is already a normalised baseline JFIF (JFIF marker present AND no Exif).

    JFIF is the marker python-docx needs and Pillow writes; ffmpeg MJPEG frames (build-dependent) often
    start with a COM marker ("Lavc…") and no JFIF, so they fail this and get normalised. We check JFIF at
    its canonical offset (byte 6, immediately after SOI + APP0 length) — where python-docx + Pillow put
    it — and ALSO require Exif to be absent: an Exif block may carry an Orientation tag we must bake into
    pixels, so an Exif-bearing JPEG is normalised once (after which it is JFIF-only and this returns True
    — idempotent, no repeated re-encode on re-runs). A cheap 128-byte header read."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(128)
    except OSError:
        return False
    return head[:2] == b"\xff\xd8" and head[6:10] == b"JFIF" and b"Exif" not in head


def _normalize_jpeg(path: pathlib.Path) -> None:
    """Rewrite a JPEG as a baseline JFIF via Pillow so python-docx can embed it.

    ffmpeg's MJPEG encoder can emit a COM-marked JPEG with no JFIF APP0 marker (build-dependent;
    observed on Homebrew ffmpeg 8.1), which python-docx's strict image parser then rejects with
    UnrecognizedImageError — so the frame
    silently fails to embed and the competitor-analysis doc loses ALL its original
    screenshots (Stage 6, step4_build_docs.py). A Pillow round-trip rewrites a standard
    baseline JFIF JPEG python-docx accepts, at the SAME native resolution (no downscale)
    and visually-lossless quality (q95, 4:4:4). EXIF orientation is baked into the pixels
    first, so a rotated scraped source JPEG doesn't embed sideways.

    Idempotent (no-op when the frame is already baseline JFIF — so it's safe + cheap to
    call on the skip path, which fixes frames left by the pre-fix script on re-run) and
    best-effort (on any error, incl. Pillow missing, the original frame is left untouched
    — never worse than before)."""
    if _is_embeddable_jpeg(path):
        return
    tmp = path.with_suffix(".norm.jpg")
    try:
        from PIL import Image, ImageOps
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)        # bake orientation in (no-op w/o EXIF)
            im.convert("RGB").save(tmp, "JPEG", quality=95, subsampling=0)
        tmp.replace(path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass


def video_path_for(ad_id: str, competitor: str) -> pathlib.Path | None:
    # Search ALL dated folders (newest first), not just the latest — a long-running
    # ad's video may have come from an earlier scrape (see step4_decompose.video_path_for).
    for vdir in sorted(pathlib.Path("videos").glob(f"{competitor}-*"), reverse=True):
        for fname in (f"{ad_id}.mp4", f"{ad_id}_v2.mp4", f"{ad_id}_v3.mp4"):
            p = vdir / fname
            if p.exists():
                return p
    return None


def image_path_for(ad_id: str, competitor: str) -> pathlib.Path | None:
    """Mirror of video_path_for() for Image-type ads (HANDOVER §8.5/§9.5).
    Searches ALL dated folders (newest first), not just the latest."""
    for idir in sorted(pathlib.Path("images").glob(f"{competitor}-*"), reverse=True):
        for fname in (f"{ad_id}.jpg", f"{ad_id}_c2.jpg", f"{ad_id}_c3.jpg",
                      f"{ad_id}_c4.jpg", f"{ad_id}_c5.jpg"):
            p = idir / fname
            if p.exists():
                return p
    return None


def extract_one(video_path: pathlib.Path, t: float, out_path: pathlib.Path) -> bool:
    """Return True on success, False on failure.

    Resolution policy (HANDOVER §9.7):
      - No `-vf scale=...` filter is applied — frames come out at the source
        video's native resolution (typically 720x1280 or 1080x1920 for a
        vertical mobile ad).
      - `-q:v 2` is the highest practical MJPEG quality (≈90%). Do NOT lower
        this; downstream image-quality automation depends on full fidelity.
      - Validity floor: 20 KB. Anything smaller means ffmpeg wrote a placeholder
        or the seek landed past EOF.
    """
    if out_path.exists() and out_path.stat().st_size > 20_000:
        return True  # already done, valid
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(t), "-i", str(video_path),
             "-vframes", "1", "-q:v", "2", str(out_path)],
            capture_output=True, timeout=15, check=True,
        )
        if not (out_path.exists() and out_path.stat().st_size > 20_000):
            return False
        # ffmpeg MJPEG output is not python-docx-embeddable; rewrite it as a baseline
        # JPEG so Stage 6 can embed the original screenshot (see _normalize_jpeg).
        _normalize_jpeg(out_path)
        return out_path.exists() and out_path.stat().st_size > 20_000
    except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
        return False


def process_row(ad_id: str, competitor: str) -> dict:
    sidecar = SCENES_DIR / f"{ad_id}.json"
    if not sidecar.exists():
        return {"id": ad_id, "status": "no-sidecar", "extracted": 0, "failed": 0}

    data = json.loads(sidecar.read_text())
    scenes = data.get("parsed", {}).get("scenes", [])
    if not scenes:
        return {"id": ad_id, "status": "no-scenes", "extracted": 0, "failed": 0}

    frame_dir = FRAMES_DIR / ad_id
    frame_dir.mkdir(parents=True, exist_ok=True)

    # Image-only path: just copy the local jpg to orig_01.jpg (HANDOVER §9.5).
    if data.get("is_image_only"):
        img = image_path_for(ad_id, competitor)
        # Prefer the explicitly-recorded source_image_path from decompose if present
        recorded = data.get("source_image_path")
        if recorded and pathlib.Path(recorded).exists():
            img = pathlib.Path(recorded)
        if img is None:
            return {"id": ad_id, "status": "no-image", "extracted": 0, "failed": 0}
        out_path = frame_dir / f"orig_{scenes[0].get('n', 1):02d}.jpg"
        if out_path.exists() and out_path.stat().st_size > 20_000:
            _normalize_jpeg(out_path)   # idempotent; fixes frames left by the pre-fix script
            return {"id": ad_id, "status": "ok", "extracted": 0,
                    "skipped": 1, "failed": 0, "scenes": 1}
        try:
            shutil.copyfile(img, out_path)
            _normalize_jpeg(out_path)  # scraped source jpgs can also be non-embeddable
            return {"id": ad_id, "status": "ok", "extracted": 1,
                    "skipped": 0, "failed": 0, "scenes": 1}
        except OSError as e:
            return {"id": ad_id, "status": f"copy-failed: {e}",
                    "extracted": 0, "failed": 1, "scenes": 1}

    video = video_path_for(ad_id, competitor)
    if video is None:
        return {"id": ad_id, "status": "no-video", "extracted": 0, "failed": 0}

    extracted = 0
    failed = 0
    skipped = 0
    for scene in scenes:
        n = scene.get("n", 0)
        t = scene.get("screenshot_at_s")
        if t is None:
            # Fallback to midpoint of start/end
            s = scene.get("start_s", 0)
            e = scene.get("end_s", s + 1)
            t = (s + e) / 2
        out_path = frame_dir / f"orig_{n:02d}.jpg"
        if out_path.exists() and out_path.stat().st_size > 20_000:
            _normalize_jpeg(out_path)   # idempotent; fixes frames left by the pre-fix script
            skipped += 1
            continue
        if extract_one(video, float(t), out_path):
            extracted += 1
        else:
            failed += 1

    return {"id": ad_id, "status": "ok", "extracted": extracted,
            "skipped": skipped, "failed": failed, "scenes": len(scenes)}


def check_ffmpeg_available() -> None:
    """Hard preflight — fail loudly if ffmpeg is missing.

    Without this, every per-scene extract_one() call returns False (the OSError
    inside is swallowed) and the script reports "0 extracted / N failed" for
    every row. Operators on the Learna AI run misread that as a video-data
    problem and burned ~30 min before realising ffmpeg simply wasn't installed.
    """
    import shutil
    if shutil.which("ffmpeg"):
        return
    sys.exit(
        "\n[error] ffmpeg is not installed. Stage 2 cannot extract any frames.\n"
        "        Fix on macOS:   brew install ffmpeg\n"
        "        Fix on Linux:   apt-get install -y ffmpeg\n"
        "        Then re-run this command. Already-extracted frames are kept.\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competitor", required=True)
    ap.add_argument("ids", nargs="+")
    args = ap.parse_args()

    check_ffmpeg_available()
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    competitor = args.competitor.lower().strip()

    print(f"Stage 2 — extracting frames for {len(args.ids)} videos")
    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(process_row, aid, competitor): aid for aid in args.ids}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            print(f"  [{r['id']}] {r['status']}  "
                  f"extracted={r.get('extracted', 0)} skipped={r.get('skipped', 0)} "
                  f"failed={r.get('failed', 0)} (scenes={r.get('scenes', '?')})",
                  flush=True)

    fail_count = sum(1 for r in results if r['status'] != 'ok' or r.get('failed', 0) > 0)
    print(f"\nStage 2 done — {len(results)} rows processed, {fail_count} with failures")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
