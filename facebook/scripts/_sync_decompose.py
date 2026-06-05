#!/usr/bin/env python3
"""Synchronous fallback for Stage 1 decompose — bypasses the Gemini Batch queue.
Reuses step4_decompose PROMPT/MODEL/uploaded-file URIs and writes sidecars in the
IDENTICAL shape to cmd_poll. Idempotent + time-boxed."""
import json, re, sys, time
sys.path.insert(0, "scripts")
import step4_decompose as D
from google.genai import types as gt

COMP = "english-seekho"
IDS = """2490626478079076 1008376008280324 27545658091701815 27417472307892610
835603072955889 1753605869341627 2200879757377961 1302516825430257
1483037666208224 1052565497102220 876287251448118 2078950623024665
2505471363291833 1719504072403935 2056613488574281 2092207258026410
984431433971622 968883082730315 995219973120049 2230315987725301""".split()

TIME_BUDGET = float(sys.argv[1]) if len(sys.argv) > 1 else 36.0
start = time.time()
client = D.get_client()
upload_state = json.loads((D.UPLOADS_DIR / f"{COMP}.json").read_text())
D.SCENES_DIR.mkdir(parents=True, exist_ok=True)
done = sum(1 for i in IDS if (D.SCENES_DIR / f"{i}.json").exists())
print(f"start: {done}/{len(IDS)} already have sidecars")
for ad_id in IDS:
    if (D.SCENES_DIR / f"{ad_id}.json").exists():
        continue
    if time.time() - start > TIME_BUDGET:
        print("[time budget reached — re-run to continue]"); break
    fname = upload_state.get(ad_id)
    if not fname:
        print(f"  [{ad_id}] no uploaded file — skip"); continue
    try:
        file_uri = client.files.get(name=fname).uri
        resp = client.models.generate_content(
            model=D.MODEL,
            contents=[gt.Content(role="user", parts=[
                gt.Part(text=D.PROMPT),
                gt.Part(file_data=gt.FileData(mime_type="video/mp4", file_uri=file_uri)),
            ])],
            config=gt.GenerateContentConfig(
                temperature=0.1, max_output_tokens=16384,
                response_mime_type="application/json"),
        )
        text = resp.candidates[0].content.parts[0].text
        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
        (D.SCENES_DIR / f"{ad_id}.json").write_text(json.dumps(
            {"competitor_id": ad_id, "parsed": parsed, "model": D.MODEL,
             "decoded_at": time.time()}, indent=2))
        print(f"  [{ad_id}] OK — {len(parsed.get('scenes',[]))} scenes, "
              f"{len(parsed.get('characters',[]))} characters")
    except Exception as e:
        print(f"  [{ad_id}] {type(e).__name__}: {e}")
done = sum(1 for i in IDS if (D.SCENES_DIR / f"{i}.json").exists())
print(f"end: {done}/{len(IDS)} sidecars present")
