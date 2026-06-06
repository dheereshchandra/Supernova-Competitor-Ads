#!/usr/bin/env python3
"""
transcribe_tag.py — Phase 2 enrichment. ONE Gemini **Flash** call per video →
transcript + on-screen text + language + format/production tags.

This is the paid step, but cost-controlled by design:
  * Flash ONLY (never Pro) — ~$0.005-0.01 per video.
  * Run ONCE per video, then cached forever: each video's result is a committed
    per-ad sidecar. Ads that already have a sidecar are SKIPPED, so the first run
    is the full back-catalog and every run after only does NEW videos. Because
    sidecars are committed, a teammate reuses them via `git pull` and never re-pays.

Output: analysis/enrichment/{pipeline}/transcripts/{competitor}/{ad_id}.json

Runs on YOUR Mac. Needs: google-genai + GEMINI_API_KEY (.env), and the video
files present locally (rehydrate first:
  python3 tools/rehydrate.py --pipeline facebook --competitor duolingo).

Usage:
    python3 analysis/scripts/transcribe_tag.py --pipeline facebook --competitor duolingo
    python3 analysis/scripts/transcribe_tag.py --pipeline facebook --competitor duolingo --limit 5
    python3 analysis/scripts/transcribe_tag.py --pipeline facebook --competitor duolingo --ids 123,456
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import _flash

AD_ID = {"facebook": "ad_library_id", "google": "creative_id"}
MEDIA_COL = {"facebook": "ad_media_type", "google": "creative_format"}
VIDEO_VALUES = {"facebook": ("video",), "google": ("youtubevideo", "video")}

# Starter format taxonomy (tunable — see analysis/README.md). Flash classifies
# each video into these fixed buckets so format-mix is countable.
PROMPT = """You are analysing a short Indian-language video advertisement for a competitor-ad
intelligence database. Watch the video AND listen to the audio. Reply with EXACTLY ONE
JSON object — no markdown fences, no commentary:

{
  "language": "<dominant spoken/on-screen human language as an English name, e.g. Hindi, Tamil, English; 'unknown' if none>",
  "presenter_type": "<one of: human-only | ai-avatar-only | ai+human | voiceover-only | none>",
  "device_format": "<one of: talking-head | split-screen | app-screencast | text-on-screen-only | pen-and-paper | skit-narrative | listicle-montage | other>",
  "production_type": "<one of: human-recorded | ai-generated | mixed>",
  "duration_s": <number>,
  "transcript": "<verbatim transcript of all speech, in order. Use native script for the original, followed by a bracketed [English translation]. Prefix each speaker turn with a stable label like 'Speaker A:'. If music-only, write '[music only, no speech]'.>",
  "on_screen_text": "<verbatim on-screen text / captions / end-card copy, original + [English]>",
  "summary": "<2-3 sentence plain-English summary of the ad's hook, message, and CTA>"
}

Be precise; do not invent details not present in the video. Pick the single best
enum value for each categorical field.
"""


def repo_root(explicit):
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def find_video(root: Path, pipeline: str, competitor: str, ad_id: str) -> Path | None:
    """Locate the local mp4 for an ad (primary or first variant)."""
    vbase = root / pipeline / "videos"
    for d in sorted(vbase.glob(f"{competitor}-*")):
        for name in (f"{ad_id}.mp4", f"{ad_id}_v2.mp4", f"{ad_id}_v1.mp4"):
            p = d / name
            if p.exists():
                return p
    return None


def upload_active(client, path: Path, timeout_s: int = 180):
    """Upload a video and wait until the Files API marks it ACTIVE."""
    f = client.files.upload(file=str(path))
    waited = 0
    while getattr(f.state, "name", str(f.state)) == "PROCESSING" and waited < timeout_s:
        time.sleep(3)
        waited += 3
        f = client.files.get(name=f.name)
    state = getattr(f.state, "name", str(f.state))
    if state != "ACTIVE":
        raise RuntimeError(f"file not ACTIVE (state={state})")
    return f


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pipeline", required=True, choices=["facebook", "google"])
    ap.add_argument("--competitor", required=True)
    ap.add_argument("--base", default=None)
    ap.add_argument("--model", default=_flash.DEFAULT_MODEL)
    ap.add_argument("--ids", default=None, help="comma-separated ad ids only")
    ap.add_argument("--limit", type=int, default=None, help="cap new videos (testing)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    _flash.assert_flash(args.model)

    root = repo_root(args.base)
    slug = args.competitor.lower().strip()
    master = root / args.pipeline / "master" / f"{slug}.csv"
    if not master.exists():
        raise SystemExit(f"[error] master not found: {master}")
    id_col, media_col = AD_ID[args.pipeline], MEDIA_COL[args.pipeline]
    want_ids = set(args.ids.split(",")) if args.ids else None

    outdir = root / "analysis" / "enrichment" / args.pipeline / "transcripts" / slug

    # distinct video ads not already transcribed
    seen, todo = set(), []
    for r in read_csv(master):
        ad_id = (r.get(id_col) or "").strip()
        if not ad_id or ad_id in seen:
            continue
        seen.add(ad_id)
        media = (r.get(media_col) or "").strip().lower()
        if not any(v in media for v in VIDEO_VALUES[args.pipeline]):
            continue
        if want_ids and ad_id not in want_ids:
            continue
        if (outdir / f"{ad_id}.json").exists():
            continue
        todo.append(ad_id)
    if args.limit:
        todo = todo[:args.limit]

    # locate videos
    located = [(a, find_video(root, args.pipeline, slug, a)) for a in todo]
    missing = [a for a, p in located if p is None]
    ready = [(a, p) for a, p in located if p is not None]
    already = len(list(outdir.glob("*.json"))) if outdir.exists() else 0

    print(f"{slug}: {already} already transcribed | {len(ready)} ready | "
          f"{len(missing)} video-missing (rehydrate from R2) | model={args.model}")
    if missing[:5]:
        print(f"   missing examples: {missing[:5]}")
    if not ready:
        if missing:
            print("→ run: python3 tools/rehydrate.py --pipeline "
                  f"{args.pipeline} --competitor {slug}")
        return 0
    if args.dry_run:
        est = len(ready) * 0.008
        print(f"[dry-run] would transcribe {len(ready)} videos on Flash "
              f"(~${est:.2f}); writing nothing.")
        return 0

    client = _flash.get_client(_flash.find_env(root, args.pipeline))
    outdir.mkdir(parents=True, exist_ok=True)
    ok = 0
    for ad_id, vpath in ready:
        try:
            f = upload_active(client, vpath)
            obj = _flash.generate_json(client, args.model, [f, PROMPT])
            obj.update({"ad_id": ad_id, "competitor": slug,
                        "pipeline": args.pipeline, "model": args.model,
                        "source_video": vpath.name, "decoded_at": time.time()})
            (outdir / f"{ad_id}.json").write_text(
                json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                client.files.delete(name=f.name)   # tidy server-side upload
            except Exception:  # noqa: BLE001
                pass
            ok += 1
            if ok % 10 == 0 or ok == len(ready):
                print(f"  transcribed {ok}/{len(ready)}")
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] {ad_id} failed: {e}")
    print(f"done: {ok}/{len(ready)} new sidecars in {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
