#!/usr/bin/env python3.13
"""
visual_fingerprint.py — B6 (OFFLINE, no API). Perceptual-hash the VISUALS of each
video ad so we can catch visual variation that the script/text clustering misses.

Why: script_cluster groups by what an ad SAYS (transcript embeddings). Two ads with
the same script can look completely different (re-shot with another actor/scene), and
two visually-identical ads can carry different overlaid text. A perceptual hash of
sampled frames gives a VISUAL identity, orthogonal to the script identity:
  • same script_group + different visual_group  → a genuine re-shoot (Q7)
  • same visual_group  + different script_group  → same footage, new copy/CTA

Implementation note: imagehash/scipy are NOT installed here, so the pHash is computed
from scratch with Pillow + numpy (2-D DCT-II, low-frequency 8x8 block, median threshold
→ 64-bit hash). Frames are sampled with the SAME ffmpeg call step4_frames.py uses.

Reads {pipeline}/master/{slug}.csv; for each video ad it resolves the local file
(version-aware, matching probe_media.find_video), samples frames, hashes them, then
groups ads by min pairwise Hamming distance <= --hamming. Writes
analysis/enrichment/{pipeline}/visual/{slug}.csv — one row per
(ad_id, version_index, creative_index):
  ad_id, version_index, creative_index, visual_hash, phash_frames,
  visual_group_id, visual_group_size
Idempotent (already-hashed ads are skipped; grouping is recomputed deterministically).
Backfillable from R2 media (rehydrate first if missing).

Usage:
    python3.13 analysis/scripts/visual_fingerprint.py --pipeline facebook --competitor mysivi
    python3.13 analysis/scripts/visual_fingerprint.py --pipeline facebook --competitor mysivi --limit 30
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

AD_ID = {"facebook": "ad_library_id", "google": "creative_id"}
MEDIA_COL = {"facebook": "ad_media_type", "google": "creative_format"}
VIDEO_VALUES = {"facebook": ("video",), "google": ("youtubevideo", "video")}
OUT_COLS = ["ad_id", "version_index", "creative_index", "visual_hash",
            "phash_frames", "visual_group_id", "visual_group_size"]

_DCT_N = 32          # frame is downscaled to 32x32 before the DCT
_HASH_SIDE = 8       # low-frequency 8x8 block -> 64-bit hash
_FRAME_FRACS = (0.2, 0.5, 0.8)   # sample at 20/50/80% of duration


# ---- perceptual hash (Pillow + numpy, no scipy/imagehash) -------------------
def _dct_matrix(n: int) -> np.ndarray:
    """Orthonormal DCT-II basis. Self-consistent (used for every frame), so Hamming
    distances are meaningful even though the scaling differs from scipy's default."""
    k = np.arange(n)
    m = np.cos(np.pi * (2 * k[None, :] + 1) * k[:, None] / (2 * n)) * np.sqrt(2.0 / n)
    m[0] *= 1 / np.sqrt(2)
    return m


_DCT = _dct_matrix(_DCT_N)


def phash_image(path: Path) -> str | None:
    try:
        img = Image.open(path).convert("L").resize((_DCT_N, _DCT_N), Image.LANCZOS)
    except (OSError, ValueError):
        return None
    a = np.asarray(img, dtype=float)
    d = _DCT @ a @ _DCT.T
    low = d[:_HASH_SIDE, :_HASH_SIDE]
    bits = (low > np.median(low)).flatten()
    val = 0
    for b in bits:
        val = (val << 1) | int(b)
    return f"{val:016x}"


def hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def min_frame_hamming(fa: list[str], fb: list[str]) -> int:
    """Smallest Hamming distance across any frame-pair (catches a shared scene)."""
    return min((hamming(x, y) for x in fa for y in fb), default=64)


# ---- media discovery (mirrors probe_media.find_video) -----------------------
def _int0(x) -> int:
    try:
        return int(str(x or "0").strip() or "0")
    except (ValueError, TypeError):
        return 0


def media_name(ad_id: str, v, c, ext: str = ".mp4", prefix: str = "_v") -> str:
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
    if _int0(v) == 0:
        for d in sorted(vbase.glob(f"{competitor}-*")):
            for nm in (f"{ad_id}.mp4", f"{ad_id}_v2.mp4", f"{ad_id}_v1.mp4"):
                p = d / nm
                if p.exists():
                    return p
    return None


def video_duration(path: Path) -> float:
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", str(path)], timeout=20).decode()
        return float(json.loads(out).get("format", {}).get("duration", 0.0) or 0.0)
    except (subprocess.SubprocessError, OSError, ValueError):
        return 0.0


def sample_hashes(path: Path) -> list[str]:
    """Extract a few frames (same ffmpeg call as step4_frames) and pHash each."""
    dur = video_duration(path)
    times = ([round(dur * f, 2) for f in _FRAME_FRACS] if dur > 0.5
             else [0.5, 1.0, 2.0])
    hashes: list[str] = []
    for t in times:
        fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)                      # mkstemp opens an fd we don't use — close it
        tmp = Path(tmp_path)              # (else ~2100 frames would exhaust the fd limit)
        try:
            subprocess.run(["ffmpeg", "-y", "-ss", str(t), "-i", str(path),
                            "-vframes", "1", "-q:v", "2", str(tmp)],
                           capture_output=True, timeout=20, check=True)
            h = phash_image(tmp)
            if h:
                hashes.append(h)
        except (subprocess.SubprocessError, OSError):
            pass
        finally:
            tmp.unlink(missing_ok=True)
    return hashes


# ---- grouping (union-find on min-frame Hamming) -----------------------------
class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def group_visuals(rows: list[dict], hamming_max: int) -> None:
    """Set visual_group_id / visual_group_size in place. Ads whose frame sets are
    within hamming_max bits are unioned (transitive)."""
    framelists = [list(filter(None, r["phash_frames"].split(";"))) if r.get("phash_frames")
                  else [] for r in rows]
    n = len(rows)
    uf = UnionFind(n)
    for i in range(n):
        if not framelists[i]:
            continue
        for j in range(i + 1, n):
            if framelists[j] and min_frame_hamming(framelists[i], framelists[j]) <= hamming_max:
                uf.union(i, j)
    comps: dict[int, list[int]] = {}
    for i in range(n):
        comps.setdefault(uf.find(i), []).append(i)
    slug_groups = sorted(comps.values(), key=len, reverse=True)
    for gi, members in enumerate(slug_groups):
        gid = f"{rows[members[0]]['_slug']}-v{gi:04d}"
        for idx in members:
            rows[idx]["visual_group_id"] = gid
            rows[idx]["visual_group_size"] = len(members)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pipeline", required=True, choices=["facebook", "google"])
    ap.add_argument("--competitor", required=True)
    ap.add_argument("--base", default=None)
    ap.add_argument("--hamming", type=int, default=10,
                    help="<= this many differing bits (of 64) = same visual (default 10)")
    ap.add_argument("--limit", type=int, default=None, help="cap new hashes (testing)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = Path(args.base).resolve() if args.base else Path(__file__).resolve().parents[2]
    slug = args.competitor.lower().strip()
    master = root / args.pipeline / "master" / f"{slug}.csv"
    if not master.exists():
        raise SystemExit(f"[error] master not found: {master}")
    id_col, media_col = AD_ID[args.pipeline], MEDIA_COL[args.pipeline]

    outpath = root / "analysis" / "enrichment" / args.pipeline / "visual" / f"{slug}.csv"
    done = {(r["ad_id"], r["version_index"], r["creative_index"]): r for r in read_csv(outpath)}

    new, missing, hashed = [], 0, 0
    for r in read_csv(master):
        aid = (r.get(id_col) or "").strip()
        if not aid:
            continue
        if not any(v in (r.get(media_col) or "").strip().lower()
                   for v in VIDEO_VALUES[args.pipeline]):
            continue
        v, c = str(_int0(r.get("version_index"))), str(_int0(r.get("creative_index_in_ad")))
        if (aid, v, c) in done:
            continue
        vpath = find_video(root, args.pipeline, slug, aid, v, c)
        if vpath is None:
            missing += 1
            continue
        if args.dry_run:
            hashed += 1
            if args.limit and hashed >= args.limit:
                break
            continue
        frames = sample_hashes(vpath)
        if not frames:
            missing += 1
            continue
        new.append({"ad_id": aid, "version_index": v, "creative_index": c,
                    "visual_hash": frames[len(frames) // 2], "phash_frames": ";".join(frames)})
        hashed += 1
        if args.limit and hashed >= args.limit:
            break

    if args.dry_run:
        print(f"{slug}: would hash {hashed} videos ({len(done)} already, {missing} video-missing)")
        return 0

    allrows = list(done.values()) + new
    for rec in allrows:                      # tag slug for group-id construction
        rec["_slug"] = slug
        rec.setdefault("visual_group_id", "")
        rec.setdefault("visual_group_size", "")
    group_visuals(allrows, args.hamming)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    with outpath.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(allrows)

    n_multi = sum(1 for r in allrows if _int0(r.get("visual_group_size")) > 1)
    n_groups = len({r["visual_group_id"] for r in allrows if r.get("visual_group_id")})
    print(f"{slug}: hashed {hashed} new ({len(done)} already, {missing} video-missing) | "
          f"{len(allrows)} ads -> {n_groups} visual groups ({n_multi} ads share visuals) "
          f"-> {outpath}")
    if missing:
        print(f"  -> pull missing media first: python3.13 tools/rehydrate.py "
              f"--pipeline {args.pipeline} --competitor {slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
