"""Lazy video-thumbnail cache.

No thumbnails exist for most ads (only generated ones have orig_frame_urls), so a
60-card grid would otherwise mount 60 <video> elements all streaming MP4s from R2's
rate-limited dev domain — slow, and some fail to load. Instead each card shows a
tiny JPG poster from this endpoint; the <video> only mounts on hover.

On first request we pull the video (authenticated R2, reused from jobs._download),
extract one frame with ffmpeg, and cache a ~15 KB JPG under webapp/state/thumbs/.
A semaphore caps concurrent extraction so a fresh page can't stampede the Mac.
"""
from __future__ import annotations

import pathlib
import subprocess
import tempfile
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from .config import STATE_DIR
from .data import catalog

router = APIRouter()

THUMBS = STATE_DIR / "thumbs"
_sem = threading.Semaphore(4)        # cap concurrent ffmpeg/download
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()

# 1x1 transparent PNG — returned when a thumb can't be made, so the <img> doesn't 404-loop.
_BLANK = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000100052d0a2db40000000049454e44ae426082")


def _key(pipeline: str, slug: str, ad_id: str) -> str:
    return f"{pipeline}_{slug}_{ad_id}.jpg"


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def _make_thumb(media_url: str, dest: pathlib.Path) -> bool:
    from .jobs import _download  # authenticated R2 download with public fallback
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as tmp:
        try:
            _download(media_url, pathlib.Path(tmp.name))
        except Exception:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp.name,
             "-ss", "00:00:01", "-frames:v", "1", "-vf", "scale=360:-1",
             "-q:v", "5", str(dest)],
            capture_output=True, timeout=60)
        # some videos are <1s; retry grabbing the very first frame
        if proc.returncode != 0 or not dest.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp.name,
                 "-frames:v", "1", "-vf", "scale=360:-1", "-q:v", "5", str(dest)],
                capture_output=True, timeout=60)
        return dest.exists() and dest.stat().st_size > 0


def prewarm(limit: int = 400) -> None:
    """Generate posters for the top winners in the background so the first browse is
    instant. Runs on a worker thread; respects the same semaphore as live requests, so
    it naturally yields to anyone actively browsing. Skips ads that already have a frame
    URL (those redirect) or a cached JPG."""
    try:
        res = catalog().list_ads(pipeline="facebook", verdict=["strong_winner", "winner"],
                                 has_media=True, sort="run_days", page=1, page_size=limit)
    except Exception:
        return
    made = 0
    for ad in res["ads"]:
        if ad["thumb_url"] or (ad["media_type"] or "").lower() == "image":
            continue
        dest = THUMBS / _key(ad["pipeline"], ad["competitor"], ad["ad_id"])
        if dest.is_file():
            continue
        lock = _lock_for(dest.name)
        with lock:
            if dest.is_file():
                continue
            with _sem:
                if _make_thumb(ad["media_url"], dest):
                    made += 1
    if made:
        print(f"[media] pre-warmed {made} winner thumbnails")


@router.get("/api/thumb/{pipeline}/{slug}/{ad_id}")
def thumb(pipeline: str, slug: str, ad_id: str):
    key = _key(pipeline, slug, ad_id)
    dest = THUMBS / key
    if dest.is_file():
        return FileResponse(dest, media_type="image/jpeg",
                            headers={"Cache-Control": "public, max-age=86400"})

    ad = catalog().get(pipeline, slug, ad_id)
    if not ad or not ad["media_url"]:
        return Response(_BLANK, media_type="image/png")
    # already-generated ads have a real frame URL — redirect the browser straight to it
    if ad["thumb_url"]:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(ad["thumb_url"])
    if (ad["media_type"] or "").lower() == "image":
        from fastapi.responses import RedirectResponse
        return RedirectResponse(ad["media_url"])

    lock = _lock_for(key)
    with lock:                       # one extraction per ad even under concurrent hits
        if dest.is_file():
            return FileResponse(dest, media_type="image/jpeg")
        with _sem:
            ok = _make_thumb(ad["media_url"], dest)
    if ok:
        return FileResponse(dest, media_type="image/jpeg",
                            headers={"Cache-Control": "public, max-age=86400"})
    return Response(_BLANK, media_type="image/png")
