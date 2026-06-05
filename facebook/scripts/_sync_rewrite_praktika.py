"""Synchronous, idempotent Supernova rewrite (text-only) — bypasses the congested
Gemini Batch queue. Same MODEL/PROMPT/sidecar shape as step4_rewrite.cmd_poll.
Usage: python3 scripts/_sync_rewrite_praktika.py <id> <id> ...
"""
import json, re, sys, time
sys.path.insert(0, "scripts")
import step4_rewrite as R
import step4_decompose as D
from google.genai import types as gt

IDS = sys.argv[1:]
client = D.get_client()
for ad_id in IDS:
    out = R.SCENES_DIR / f"{ad_id}.supernova.json"
    if out.exists():
        print(f"  [{ad_id}] skip — exists"); continue
    dec = R.SCENES_DIR / f"{ad_id}.json"
    if not dec.exists():
        print(f"  [{ad_id}] no decompose sidecar — skip"); continue
    parsed_in = json.loads(dec.read_text()).get("parsed", {})
    user_text = R.PROMPT + json.dumps(parsed_in, ensure_ascii=False)
    try:
        resp = client.models.generate_content(
            model=R.MODEL,
            contents=[gt.Content(role="user", parts=[gt.Part(text=user_text)])],
            config=gt.GenerateContentConfig(
                temperature=0.4, max_output_tokens=16384,
                response_mime_type="application/json",
                thinking_config=gt.ThinkingConfig(thinking_level="low")),
        )
        text = resp.candidates[0].content.parts[0].text
        text = re.sub(r"^```(?:json)?\s*", "", text.strip()); text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
        out.write_text(json.dumps({"competitor_id": ad_id, "parsed": parsed,
                                   "model": R.MODEL, "rewrote_at": time.time()},
                                  indent=2, ensure_ascii=False))
        print(f"  [{ad_id}] OK — {len(parsed.get('scenes', []))} scenes", flush=True)
    except Exception as e:
        print(f"  [{ad_id}] {type(e).__name__}: {e}", flush=True)
print("DONE")
