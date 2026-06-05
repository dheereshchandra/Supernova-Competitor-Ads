#!/usr/bin/env python3
"""Download a small chunk of missing MySivi ads, fast and resumable.

Each invocation:
  * loads /tmp/missing_ids.txt
  * walks them, skipping any whose final <id>.mp4 already exists
  * downloads each with yt_dlp --playlist-items 1
  * stops once wall-clock approaches the bash 45s cap
"""
import os, sys, time, subprocess, re
from pathlib import Path

OUT = Path("/sessions/nifty-wonderful-hypatia/mnt/fb-ad-downloader/videos/mysivi-2026-05-26")
DEADLINE = time.monotonic() + float(os.environ.get("MAX_SECS", "38"))
PER_AD_TIMEOUT = 18

ids = [x.strip() for x in open("/tmp/missing_ids.txt").read().splitlines() if x.strip()]
done = 0
failed = 0
for aid in ids:
    if (OUT / f"{aid}.mp4").exists():
        continue
    # any raw form left behind (e.g. <id>_1.mp4)? skip too.
    if list(OUT.glob(f"{aid}_*.mp4")):
        continue
    if time.monotonic() > DEADLINE:
        break
    url = f"https://www.facebook.com/ads/library/?id={aid}"
    out_tmpl = str(OUT / "%(id)s.%(ext)s")
    cmd = [sys.executable, "-m", "yt_dlp",
           "--no-warnings", "--no-progress", "--ignore-errors",
           "--no-playlist-reverse",
           "--playlist-items", "1",
           "-o", out_tmpl, url]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=PER_AD_TIMEOUT)
        # success if any file with that id now exists
        produced = list(OUT.glob(f"{aid}*.mp4"))
        if produced:
            done += 1
            print(f"OK {aid}")
        else:
            failed += 1
            err = (p.stderr or "").strip().splitlines()
            print(f"FAIL {aid} :: {err[-1][:120] if err else 'no output'}")
    except subprocess.TimeoutExpired:
        failed += 1
        print(f"TIMEOUT {aid}")
        # clean any partial
        for f in OUT.glob(f"{aid}*.part"):
            try: f.unlink()
            except: pass

# normalise filenames inline (so next run sees <id>.mp4 form)
groups = {}
for f in OUT.glob("*.mp4"):
    if re.fullmatch(r"\d+(_v\d+)?", f.stem):
        continue
    m = re.match(r"^(\d{8,})", f.stem)
    if m:
        groups.setdefault(m.group(1), []).append(f)
for lid, files in groups.items():
    files.sort(key=lambda p: (int(re.search(r"_p?(\d+)", p.stem[len(lid):]).group(1)) if re.search(r"_p?(\d+)", p.stem[len(lid):]) else 0, p.name))
    for idx, f in enumerate(files):
        target = OUT / (f"{lid}.mp4" if idx == 0 else f"{lid}_v{idx+1}.mp4")
        if target.exists() and target != f:
            try: f.unlink()
            except: pass
        else:
            try: f.rename(target)
            except: pass

print(f"--- done={done} failed={failed}")
