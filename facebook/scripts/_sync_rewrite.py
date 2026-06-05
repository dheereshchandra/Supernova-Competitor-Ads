"""Synchronous Supernova rewrite (text-only) — bypasses the congested Gemini
Batch queue. Writes the SAME sidecar shape as step4_rewrite.cmd_poll:
  scenes/<id>.supernova.json = {"competitor_id", "parsed", "model", "rewrote_at"}
"""
import json, re, sys, time
sys.path.insert(0, "scripts")
import step4_rewrite as R
import step4_decompose as D
from google.genai import types as gt

IDS = sys.argv[1:] or ["1391383766354969", "1449273303357626"]
client = D.get_client()
R.SCENES_DIR.mkdir(parents=True, exist_ok=True)

for ad_id in IDS:
    out = R.SCENES_DIR / f"{ad_id}.supernova.json"
    if out.exists():
        print(f"  [{ad_id}] skip — exists"); continue
    dec = R.SCENES_DIR / f"{ad_id}.json"
    parsed_in = json.loads(dec.read_text()).get("parsed", {})
    user_text = R.PROMPT + json.dumps(parsed_in, ensure_ascii=False)
    resp = client.models.generate_content(
        model=R.MODEL,
        contents=[gt.Content(role="user", parts=[gt.Part(text=user_text)])],
        config=gt.GenerateContentConfig(
            temperature=0.4, max_output_tokens=16384,
            response_mime_type="application/json",
            thinking_config=gt.ThinkingConfig(thinking_level="low"),
        ),
    )
    text = resp.candidates[0].content.parts[0].text
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    out.write_text(json.dumps({"competitor_id": ad_id, "parsed": parsed,
                               "model": R.MODEL, "rewrote_at": time.time()},
                              indent=2, ensure_ascii=False))
    print(f"  [{ad_id}] OK — {len(parsed.get('scenes', []))} scenes")
print("DONE")
