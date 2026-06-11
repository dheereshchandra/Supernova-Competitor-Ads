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
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import _flash


class _CallTimeout(Exception):
    pass


def run_with_timeout(fn, seconds: int):
    """Run fn() on a daemon thread and hard-stop WAITING after `seconds`.

    SIGALRM is unreliable for this: the google-genai SDK retries an upload/generate
    internally and catches exceptions, so it swallows the signal-raised exception — and
    signal.alarm() is one-shot, so it never fires again and the batch hangs forever. A
    thread join with timeout cannot be defeated by anything the SDK does: if the call
    hasn't returned in time we raise _CallTimeout and move on. The worker is a daemon, so
    a leaked hung call dies with the process and never blocks the main loop."""
    box: dict = {}

    def target():
        try:
            box["v"] = fn()
        except Exception as e:   # noqa: BLE001 — re-raised on the main thread below
            box["e"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise _CallTimeout(f"timed out after {seconds}s")
    if "e" in box:
        raise box["e"]
    return box.get("v")

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
  "message_angle": "<the main persuasion hook, one of: speak-correctly (AI/teacher corrects your grammar or pronunciation) | translation-practice (say it in your language then get the English) | fear-shame (embarrassment / interview rejection / consequence of poor English) | understand-cant-speak (you understand English but freeze when speaking) | social-proof (results, testimonials, download counts) | feature-demo (product / trial walkthrough) | habit-aspiration (daily practice, lifestyle, time-waste reframe) | other>",
  "split_screen_role": "<ONLY meaningful when device_format is split-screen — who corrects whom: ai-corrects-human | human-corrects-ai | ai-corrects-ai | none. Use none for any non-split-screen ad.>",
  "has_price_offer": <true or false: true if the ad mentions any price, discount, or free trial (e.g. '7x cheaper', '1 rupee', '3-day trial', 'free'), else false>,
  "duration_s": <number>,
  "transcript": "<verbatim transcript of all speech, in order. Use native script for the original, followed by a bracketed [English translation]. Prefix each speaker turn with a stable label like 'Speaker A:'. If music-only, write '[music only, no speech]'.>",
  "on_screen_text": "<verbatim on-screen text / captions / end-card copy, original + [English]>",
  "summary": "<2-3 sentence plain-English summary of the ad's hook, message, and CTA>"
}

Be precise; do not invent details not present in the video. Pick the single best
enum value for each categorical field.
"""

# CONTROLLED-GENERATION schema: forces Gemini to return valid JSON with exactly these
# fields, so an unescaped quote in a long transcript can no longer break parsing (the
# chronic "Expecting ',' delimiter" failures). Keys must match the PROMPT's JSON object.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string"},
        "presenter_type": {"type": "string"},
        "device_format": {"type": "string"},
        "production_type": {"type": "string"},
        "message_angle": {"type": "string"},
        "split_screen_role": {"type": "string"},
        "has_price_offer": {"type": "boolean"},
        "duration_s": {"type": "number"},
        "transcript": {"type": "string"},
        "on_screen_text": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["language", "presenter_type", "device_format", "production_type",
                 "message_angle", "split_screen_role", "has_price_offer", "duration_s",
                 "transcript", "on_screen_text", "summary"],
}


def repo_root(explicit):
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def find_video(root: Path, pipeline: str, competitor: str, ad_id: str,
               version_index: int = 0) -> Path | None:
    """Locate the local mp4 for an ad (or a specific version). version-aware naming
    matches upload_to_r2.media_name / download_fb_ads: version 0 → {id}.mp4 (+ legacy
    _v2/_v1 variants); version V≥1 → {id}_ver{V}_c0.mp4 (first creative of that version)."""
    try:
        v = int(version_index or 0)
    except (ValueError, TypeError):
        v = 0
    if v >= 1:
        names = (f"{ad_id}_ver{v}_c0.mp4", f"{ad_id}_ver{v}_c1.mp4")
    else:
        names = (f"{ad_id}.mp4", f"{ad_id}_v2.mp4", f"{ad_id}_v1.mp4")
    vbase = root / pipeline / "videos"
    for d in sorted(vbase.glob(f"{competitor}-*")):
        for name in names:
            p = d / name
            if p.exists():
                return p
    return None


def upload_active(client, path: Path, timeout_s: int = 180):
    """Upload a video and wait until the Files API marks it ACTIVE. The whole per-video
    operation is wrapped by run_with_timeout at the call site, so no per-call guard is
    needed here (and the SDK can't swallow a thread-join timeout)."""
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
    ap.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS", "6")),
                    help="videos transcribed in parallel (default 6; ~8-10 max before 429s)")
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
    total = len(ready)
    workers = max(1, args.workers)
    print(f"transcribing {total} video(s) with {workers} parallel worker(s) ...")
    lock = threading.Lock()
    state = {"ok": 0, "done": 0, "failed": 0, "failures": []}
    # A degraded run must FAIL LOUD, not silently commit holes. Tunable.
    max_fail_rate = float(os.environ.get("TRANSCRIBE_MAX_FAIL_RATE", "0.10"))

    def transcribe_one(ad_id, vpath):
        # Per-video body unchanged; the hard 300s cap (run_with_timeout) is the only
        # guarantee a hung worker is freed since the SDK can swallow exceptions —
        # a leaked daemon dies with the process. genai.Client is thread-safe (shared).
        def _do():
            f = upload_active(client, vpath)
            obj = _flash.generate_json(client, args.model, [f, PROMPT],
                                       response_schema=RESPONSE_SCHEMA)
            # QUALITY GATE: a Gemini safety-block / failed extraction returns a valid
            # JSON shell with empty content. Do NOT write it — a written sidecar is
            # counted "done" and NEVER retried, silently poisoning downstream
            # clustering. Raise instead, so it's recorded as a failure and retried.
            if not (obj.get("transcript") or "").strip() \
               and not (obj.get("on_screen_text") or "").strip():
                raise ValueError("empty transcript AND on_screen_text "
                                 "(likely safety-block / failed extraction)")
            obj.update({"ad_id": ad_id, "competitor": slug,
                        "pipeline": args.pipeline, "model": args.model,
                        "source_video": vpath.name, "decoded_at": time.time()})
            (outdir / f"{ad_id}.json").write_text(
                json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                client.files.delete(name=f.name)   # tidy server-side upload
            except Exception:  # noqa: BLE001
                pass
        try:
            run_with_timeout(_do, 300)
            with lock:
                state["ok"] += 1; state["done"] += 1
                print(f"  [{state['done']}/{total}] {ad_id} ok", flush=True)
        except Exception as e:  # noqa: BLE001 — a `start` with no `ok` is the stuck/failed signal
            with lock:
                state["done"] += 1; state["failed"] += 1
                state["failures"].append((ad_id, str(e)[:200]))
                print(f"  [{state['done']}/{total}] {ad_id} FAILED: {e}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(transcribe_one, a, p) for a, p in ready]
        for _ in as_completed(futs):
            pass

    failed = state["failed"]
    print(f"done: {state['ok']}/{total} transcribed, {failed} FAILED in {outdir}")
    for aid, err in state["failures"][:10]:          # surface failures, don't bury them
        print(f"  FAILED {aid}: {err}")
    if failed > 10:
        print(f"  ... and {failed - 10} more failures")
    rate = (failed / total) if total else 0.0
    # FAIL LOUD only when failures are BOTH a meaningful fraction AND an absolute
    # count. A single straggler in a tiny daily delta (e.g. 1/1 new ad that's
    # music-only or a transient blip) must NOT fail the whole competitor — that was
    # a false-failure that halted MySivi. Real degradation (many videos failing on a
    # real batch) still trips it.
    if failed > max(3, int(total * max_fail_rate)):
        print(f"[error] transcription: {failed}/{total} FAILED ({rate:.0%}) exceeds the "
              f"gate (>{max(3, int(total * max_fail_rate))}) — failing the step. Re-run resumes "
              f"(the {state['ok']} ok sidecars are cached; only the {failed} failures retry).", flush=True)
        return 2
    if failed:
        print(f"  ({failed} failed but under the gate — tolerated; they retry next run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
