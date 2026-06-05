#!/usr/bin/env python3
"""Synchronous, concurrent video decompose — bypasses the congested Gemini Batch
queue AND the unresponsive gemini-3.1-pro-preview model. Writes sidecars identical
in shape to cmd_poll's output: {competitor_id, parsed, model, decoded_at}.
Idempotent + resumable: skips any id with a valid sidecar. Run in background.

Env:
  MODEL_OVERRIDE  model id to use (default: gemini-2.5-pro fallback)
  WORKERS         concurrent calls (default 5)
"""
import json, re, sys, os, time, pathlib, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import step4_decompose as D
from google import genai
from google.genai import types as gt

MODEL = os.environ.get("MODEL_OVERRIDE", "gemini-2.5-pro")
WORKERS = int(os.environ.get("WORKERS", "5"))

def load_env():
    env={}
    for line in open(".env"):
        line=line.strip()
        if "=" in line and not line.startswith("#"):
            k,v=line.split("=",1); env[k]=v
    return env

def valid_sidecar(p):
    try:
        return len(json.loads(p.read_text()).get("parsed",{}).get("scenes",[]))>=1
    except Exception:
        return False

def main():
    competitor=sys.argv[1]; ids=sys.argv[2:]
    env=load_env()
    client=genai.Client(api_key=env["GEMINI_API_KEY"],
        http_options=gt.HttpOptions(timeout=75000))  # 75s per-call timeout → hung calls abort & retry
    state=json.loads((D.UPLOADS_DIR/f"{competitor}.json").read_text())
    todo=[a for a in ids if not (D.SCENES_DIR/f"{a}.json").exists() or not valid_sidecar(D.SCENES_DIR/f"{a}.json")]
    print(f"[start] model={MODEL} workers={WORKERS} todo={len(todo)}/{len(ids)}", flush=True)
    lock=threading.Lock()

    def work(aid):
        uri=client.files.get(name=state[aid]).uri
        for attempt in range(3):
            try:
                r=client.models.generate_content(model=MODEL,
                    contents=[gt.Content(role="user",parts=[gt.Part(text=D.PROMPT),
                        gt.Part(file_data=gt.FileData(mime_type="video/mp4",file_uri=uri))])],
                    config=gt.GenerateContentConfig(temperature=0.1,max_output_tokens=16384,
                        response_mime_type="application/json"))
                txt=r.candidates[0].content.parts[0].text
                txt=re.sub(r"^```(?:json)?\s*","",txt.strip()); txt=re.sub(r"\s*```$","",txt)
                parsed=json.loads(txt)
                if len(parsed.get("scenes",[]))<1: raise ValueError("no scenes")
                (D.SCENES_DIR/f"{aid}.json").write_text(json.dumps(
                    {"competitor_id":aid,"parsed":parsed,"model":MODEL,"decoded_at":time.time()},indent=2))
                with lock:
                    print(f"  [{aid}] OK scenes={len(parsed['scenes'])} chars={len(parsed.get('characters',[]))}",flush=True)
                return True
            except Exception as e:
                if attempt==2:
                    with lock: print(f"  [{aid}] FAIL {type(e).__name__}: {str(e)[:100]}",flush=True)
                    return False
                time.sleep(3)

    ok=0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(work,a):a for a in todo}
        for f in as_completed(futs):
            if f.result(): ok+=1
    present=sum(1 for a in ids if (D.SCENES_DIR/f"{a}.json").exists() and valid_sidecar(D.SCENES_DIR/f"{a}.json"))
    print(f"[done] new_ok={ok} present={present}/{len(ids)} {'ALL-DONE' if present>=len(ids) else 'MORE-REMAINING'}",flush=True)

if __name__=="__main__":
    main()
