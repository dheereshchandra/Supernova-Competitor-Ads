#!/usr/bin/env python3
"""
Driver wrapper that downloads in small chunks and normalises after each chunk,
so pre-skip works on the next bash-cap restart.

Usage:
    python3 scripts/_drive_step2.py <input_csv> <videos_dir> [budget_seconds]

Calls run_ytdlp_batch() directly with small batches, normalising in between.
Exits when either:
  - the input is fully processed, or
  - the per-call wall-clock budget is exceeded (default 38s; leaves ~5s for the
    final normalise + cleanup pass before the 45s bash cap fires)
"""
from __future__ import annotations
import csv, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from download_fb_ads import (
    run_ytdlp_batch,
    normalise_filenames,
    cleanup_partials,
    find_ytdlp,
)

def main():
    csv_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    budget = float(sys.argv[3]) if len(sys.argv) > 3 else 38.0
    out_dir.mkdir(parents=True, exist_ok=True)

    # Read IDs from the input CSV.
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    all_ids = [(r.get("ad_library_id") or "").strip() for r in rows]
    all_ids = [i for i in all_ids if i.isdigit()]

    # Pre-skip via existing {id}.mp4
    todo = [i for i in all_ids if not (out_dir / f"{i}.mp4").exists()]
    print(f"[drive] total={len(all_ids)}  done={len(all_ids)-len(todo)}  todo={len(todo)}", flush=True)
    if not todo:
        print("[drive] nothing to do", flush=True)
        return 0

    ytdlp = find_ytdlp(None)
    print(f"[drive] yt-dlp: {ytdlp}", flush=True)

    start = time.monotonic()
    chunk_size = 6  # smaller batches = more frequent normalise checkpoints
    downloaded_this_call = 0
    failed_this_call = 0

    while todo and (time.monotonic() - start) < budget:
        chunk = todo[:chunk_size]
        t0 = time.monotonic()
        succeeded, errors = run_ytdlp_batch(chunk, out_dir, ytdlp, timeout=30)
        elapsed = time.monotonic() - t0
        downloaded_this_call += len(succeeded)
        failed_this_call += len(errors)
        # Normalise immediately so the next pre-skip pass catches them.
        normalise_filenames(out_dir)
        # Refresh todo from disk (some entries may have produced files w/ different ids).
        todo = [i for i in all_ids if not (out_dir / f"{i}.mp4").exists()]
        done = len(all_ids) - len(todo)
        print(f"[drive] chunk done in {elapsed:.1f}s  +{len(succeeded)} -{len(errors)}  "
              f"total_done={done}/{len(all_ids)}", flush=True)
        # If a chunk burned a lot of time, bail before we overshoot
        if (time.monotonic() - start) + (elapsed * 0.5) > budget:
            print("[drive] budget nearly exhausted, stopping", flush=True)
            break

    cleanup_partials(out_dir)
    normalise_filenames(out_dir)
    final_done = len([i for i in all_ids if (out_dir / f"{i}.mp4").exists()])
    print(f"[drive] FINAL  done={final_done}/{len(all_ids)}  this_call_+{downloaded_this_call} -{failed_this_call}", flush=True)
    return 0 if final_done == len(all_ids) else 2

if __name__ == "__main__":
    sys.exit(main())
