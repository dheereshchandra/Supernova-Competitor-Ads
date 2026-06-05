#!/usr/bin/env python3
"""Synchronous (non-Batch) video decompose for Step 4.

Drop-in replacement for the Gemini Batch decompose stage when the batch queue
is stuck. Reuses everything from step4_decompose.py (model, PROMPT, file refs,
sidecar shape) so downstream stages (frames/sheets/panels/build_docs) read the
output identically to a batch run.

Idempotent: skips any ad_id that already has scenes/<id>.json. Deadline-bounded
so it plays nicely with a ~45s shell cap — re-run until it prints ALL-DONE.

Usage:
    python3 scripts/_sync_decompose_videos.py loora <id1> <id2> ... [--deadline 35]
"""
import importlib.util, json, re, sys, time, pathlib

spec = importlib.util.spec_from_file_location("d", "scripts/step4_decompose.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

from google.genai import types as gt

competitor = sys.argv[1]
deadline = 35.0
ids = []
i = 2
while i < len(sys.argv):
    if sys.argv[i] == "--deadline":
        deadline = float(sys.argv[i + 1]); i += 2; continue
    ids.append(sys.argv[i]); i += 1

client = m.get_client()
upload_state = json.loads((m.UPLOADS_DIR / f"{competitor}.json").read_text())

start = time.time()
written = skipped = failed = 0
remaining = []
for ad_id in ids:
    sidecar = m.SCENES_DIR / f"{ad_id}.json"
    if sidecar.exists():
        skipped += 1
        continue
    if time.time() - start > deadline:
        remaining.append(ad_id)
        continue
    if ad_id not in upload_state:
        print(f"  [{ad_id}] SKIP — not in upload state; run upload first")
        failed += 1
        continue
    try:
        file_uri = client.files.get(name=upload_state[ad_id]).uri
        resp = client.models.generate_content(
            model=m.MODEL,
            contents=[gt.Content(role="user", parts=[
                gt.Part(text=m.PROMPT),
                gt.Part(file_data=gt.FileData(mime_type="video/mp4", file_uri=file_uri)),
            ])],
            config=gt.GenerateContentConfig(
                temperature=0.1, max_output_tokens=16384,
                response_mime_type="application/json"),
        )
        text = resp.candidates[0].content.parts[0].text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
        sidecar.write_text(json.dumps(
            {"competitor_id": ad_id, "parsed": parsed,
             "model": m.MODEL, "decoded_at": time.time()},
            indent=2, ensure_ascii=False))
        written += 1
        print(f"  [{ad_id}] OK — {len(parsed.get('scenes',[]))} scenes, "
              f"{len(parsed.get('characters',[]))} characters")
    except Exception as e:
        failed += 1
        print(f"  [{ad_id}] {type(e).__name__}: {str(e)[:160]}")

done = sum(1 for a in ids if (m.SCENES_DIR / f"{a}.json").exists())
print(f"\nwritten={written} skipped={skipped} failed={failed} "
      f"| {done}/{len(ids)} sidecars present")
if done == len(ids):
    print("ALL-DONE")
elif remaining:
    print(f"deadline hit; {len(remaining)} remaining — re-run to continue")
