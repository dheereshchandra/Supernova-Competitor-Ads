import json, re, sys, time
sys.path.insert(0, "scripts")
import step4_decompose as D
from google.genai import types as gt
ad_id = sys.argv[1]; COMP="english-seekho"
client = D.get_client()
up = json.loads((D.UPLOADS_DIR / f"{COMP}.json").read_text())
t=time.time()
file_uri = client.files.get(name=up[ad_id]).uri
resp = client.models.generate_content(model=D.MODEL, contents=[gt.Content(role="user", parts=[
    gt.Part(text=D.PROMPT), gt.Part(file_data=gt.FileData(mime_type="video/mp4", file_uri=file_uri))])],
    config=gt.GenerateContentConfig(temperature=0.1, max_output_tokens=16384, response_mime_type="application/json"))
text=resp.candidates[0].content.parts[0].text
text=re.sub(r"^```(?:json)?\s*","",text.strip()); text=re.sub(r"\s*```$","",text)
parsed=json.loads(text)
(D.SCENES_DIR / f"{ad_id}.json").write_text(json.dumps({"competitor_id":ad_id,"parsed":parsed,"model":D.MODEL,"decoded_at":time.time()},indent=2))
print(f"[{ad_id}] OK {len(parsed.get('scenes',[]))} scenes in {time.time()-t:.1f}s")
