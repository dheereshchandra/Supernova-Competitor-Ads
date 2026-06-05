"""Synchronous, time-boxed, idempotent decompose for Praktika ads — bypasses the
congested Gemini Batch queue. Same MODEL/PROMPT/sidecar shape as step4_decompose.cmd_poll.
Usage: python3 scripts/_sync_decompose_praktika.py <id> <id> ...
"""
import json, re, sys, time, pathlib
sys.path.insert(0, "scripts")
import step4_decompose as D
from google.genai import types as gt

IDS = sys.argv[1:]
TIME_BUDGET = 40.0
start = time.time()
client = D.get_client()
state = json.loads((D.UPLOADS_DIR / "praktika-ai.json").read_text())
D.SCENES_DIR.mkdir(parents=True, exist_ok=True)
done = sum(1 for i in IDS if (D.SCENES_DIR / f"{i}.json").exists())
print(f"start: {done}/{len(IDS)} have sidecars", flush=True)
for ad_id in IDS:
    if (D.SCENES_DIR / f"{ad_id}.json").exists():
        continue
    if time.time() - start > TIME_BUDGET:
        print("[time budget — re-run to continue]"); break
    fn = state.get(ad_id)
    if not fn:
        print(f"  [{ad_id}] no upload — skip"); continue
    try:
        file_uri = client.files.get(name=fn).uri
        resp = client.models.generate_content(
            model=D.MODEL,
            contents=[gt.Content(role="user", parts=[
                gt.Part(text=D.PROMPT),
                gt.Part(file_data=gt.FileData(mime_type="video/mp4", file_uri=file_uri)),
            ])],
            config=gt.GenerateContentConfig(
                temperature=0.1, max_output_tokens=12000,
                response_mime_type="application/json",
                thinking_config=gt.ThinkingConfig(thinking_level="low")),
        )
        text = resp.candidates[0].content.parts[0].text
        text = re.sub(r"^```(?:json)?\s*", "", text.strip()); text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
        (D.SCENES_DIR / f"{ad_id}.json").write_text(json.dumps(
            {"competitor_id": ad_id, "parsed": parsed, "model": D.MODEL,
             "decoded_at": time.time()}, indent=2))
        print(f"  [{ad_id}] OK — {len(parsed.get('scenes',[]))} scenes", flush=True)
    except Exception as e:
        print(f"  [{ad_id}] {type(e).__name__}: {e}", flush=True)
done = sum(1 for i in IDS if (D.SCENES_DIR / f"{i}.json").exists())
print(f"end: {done}/{len(IDS)} sidecars present", flush=True)
