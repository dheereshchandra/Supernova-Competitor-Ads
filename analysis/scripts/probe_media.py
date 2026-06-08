#!/usr/bin/env python3.13
"""
probe_media.py — Phase 1 enrichment (OFFLINE, no API). Record the TRUE
video_resolution + video_bitrate (+ duration_s) per ad via ffprobe on the
DOWNLOADED file.

Why ffprobe, not the scrape URL: the scrape CDN URL's `efg`/`vencode_tag` label
LIES — it reported "360 / SD" for MySivi videos that ffprobe shows are 720x1280.
The downloaded file is ground truth. **Bitrate** (varied ~3x across MySivi:
0.57-1.63 Mbps) is the higher-value signal than resolution (~constant 720p).

Reads {pipeline}/master/{slug}.csv; for each video ad it resolves the local file
(version-aware naming, matching upload_to_r2.media_name) and ffprobes it; writes
analysis/enrichment/{pipeline}/media/{slug}.csv — one row per
(ad_id, version_index, creative_index). Idempotent (already-probed rows skipped).
Backfillable: re-run any time over media pulled from R2 (rehydrate first if missing).

Usage:
    python3.13 analysis/scripts/probe_media.py --pipeline facebook --competitor mysivi
    python3.13 analysis/scripts/probe_media.py --pipeline facebook --competitor mysivi --limit 20
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path

AD_ID = {"facebook": "ad_library_id", "google": "creative_id"}
MEDIA_COL = {"facebook": "ad_media_type", "google": "creative_format"}
VIDEO_VALUES = {"facebook": ("video",), "google": ("youtubevideo", "video")}
OUT_COLS = ["ad_id", "version_index", "creative_index",
            "video_resolution", "video_bitrate", "duration_s"]


def repo_root(explicit):
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _int0(x) -> int:
    try:
        return int(str(x or "0").strip() or "0")
    except (ValueError, TypeError):
        return 0


def media_name(ad_id: str, v, c, ext: str = ".mp4", prefix: str = "_v") -> str:
    """MUST match upload_to_r2.media_name / download_fb_ads / transcribe_tag.find_video."""
    vi, ci = _int0(v), _int0(c)
    if vi <= 0:
        return f"{ad_id}{ext}" if ci == 0 else f"{ad_id}{prefix}{ci + 1}{ext}"
    return f"{ad_id}_ver{vi}_c{ci}{ext}"


def find_video(root: Path, pipeline: str, competitor: str, ad_id: str, v, c) -> Path | None:
    vbase = root / pipeline / "videos"
    name = media_name(ad_id, v, c)
    for d in sorted(vbase.glob(f"{competitor}-*")):
        p = d / name
        if p.exists():
            return p
    if _int0(v) == 0:   # legacy variant fallback for version-0 rows
        for d in sorted(vbase.glob(f"{competitor}-*")):
            for nm in (f"{ad_id}.mp4", f"{ad_id}_v2.mp4", f"{ad_id}_v1.mp4"):
                p = d / nm
                if p.exists():
                    return p
    return None


def ffprobe(path: Path) -> dict | None:
    """Return {video_resolution, video_bitrate, duration_s} or None on failure.
    Bitrate falls back from format.bit_rate -> the video stream's bit_rate."""
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)], timeout=20).decode()
        data = json.loads(out)
        dur = float(data.get("format", {}).get("duration", 0.0) or 0.0)
        w = h = vbr = None
        for s in data.get("streams", []):
            if s.get("codec_type") == "video" and w is None:
                w, h, vbr = s.get("width"), s.get("height"), s.get("bit_rate")
        bitrate = _int0(data.get("format", {}).get("bit_rate")) or _int0(vbr)
        return {
            "video_resolution": f"{w}x{h}" if w and h else "",
            "video_bitrate": str(bitrate) if bitrate else "",
            "duration_s": round(dur, 2) if dur else "",
        }
    except (subprocess.SubprocessError, OSError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pipeline", required=True, choices=["facebook", "google"])
    ap.add_argument("--competitor", required=True)
    ap.add_argument("--base", default=None)
    ap.add_argument("--limit", type=int, default=None, help="cap new probes (testing)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = repo_root(args.base)
    slug = args.competitor.lower().strip()
    master = root / args.pipeline / "master" / f"{slug}.csv"
    if not master.exists():
        raise SystemExit(f"[error] master not found: {master}")
    id_col, media_col = AD_ID[args.pipeline], MEDIA_COL[args.pipeline]

    outpath = root / "analysis" / "enrichment" / args.pipeline / "media" / f"{slug}.csv"
    done = {(r["ad_id"], r["version_index"], r["creative_index"]): r
            for r in read_csv(outpath)}

    new, missing, probed = [], 0, 0
    for r in read_csv(master):
        aid = (r.get(id_col) or "").strip()
        if not aid:
            continue
        media = (r.get(media_col) or "").strip().lower()
        if not any(v in media for v in VIDEO_VALUES[args.pipeline]):
            continue
        v, c = str(_int0(r.get("version_index"))), str(_int0(r.get("creative_index_in_ad")))
        key = (aid, v, c)
        if key in done:
            continue
        vpath = find_video(root, args.pipeline, slug, aid, v, c)
        if vpath is None:
            missing += 1
            continue
        if args.dry_run:
            probed += 1
            if args.limit and probed >= args.limit:
                break
            continue
        meta = ffprobe(vpath)
        if meta is None:
            continue
        new.append({"ad_id": aid, "version_index": v, "creative_index": c, **meta})
        probed += 1
        if args.limit and probed >= args.limit:
            break

    if args.dry_run:
        print(f"{slug}: would probe {probed} videos ({len(done)} already, {missing} video-missing)")
        return 0

    allrows = list(done.values()) + new
    outpath.parent.mkdir(parents=True, exist_ok=True)
    with outpath.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(allrows)
    print(f"{slug}: probed {probed} new ({len(done)} already, {missing} video-missing) "
          f"-> {outpath}")
    if missing:
        print(f"  -> pull missing media first: python3.13 tools/rehydrate.py "
              f"--pipeline {args.pipeline} --competitor {slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
