#!/usr/bin/env python3.13
"""Resolve every shortlisted ad to a competitor transcript -> source_master.json + ads.json.

Resolution order per ad (by its reference link):
  1. Repo transcript: analysis/enrichment/*/transcripts/*/<id>.json  (reuse — free, instant)
  2. Direct video: an R2 / .mp4 link is downloaded as-is
  3. Master lookup: an FB/Google ad id found in <pipeline>/master/*.csv -> its r2_public_url
  4. Social link (instagram/youtube/facebook watch/...): yt-dlp
  ...then transcribe (steps 2-4) with the project's own Flash prompt (analysis/scripts/transcribe_tag).
Anything it cannot resolve is listed under "unresolved" — supply an mp4 or transcript and re-run.

Transcripts already in the repo and freshly-decoded ones are cached under <workdir>/transcripts/.

Outputs:
  source_master.json : [{n,row,name,language,brief_raw,faithful,ref_link, src:{...full transcript...}}]
  ads.json           : compact args.ads for generate_workflow.js [{n,name,language,faithful,brief_raw,duration_s,format,angle}]

Usage:
  python3.13 resolve_sources.py --shortlist shortlist.json --root <repo> --workdir <dir> \
      [--pipeline facebook] [--no-transcribe]
"""
import argparse, json, pathlib, re, subprocess, sys, time, urllib.request

def extract_id(link):
    """Return (id, kind) where kind in {fb_ads, r2_mp4, direct_mp4, social, unknown}."""
    link = (link or "").strip()
    m = re.search(r"[?&]id=(\d+)", link)
    if m:
        return m.group(1), "fb_ads"
    m = re.search(r"/(\d{6,})\.mp4(?:\?|$)", link)
    if m:
        return m.group(1), "r2_mp4"
    if link.endswith(".mp4"):
        return re.sub(r"[^a-zA-Z0-9]+", "_", link.rsplit("/", 1)[-1])[:40], "direct_mp4"
    m = re.search(r"(?:instagram\.com|youtube\.com|youtu\.be|fb\.watch|facebook\.com/reel|tiktok\.com)/[^?]*?([A-Za-z0-9_-]{6,})", link)
    if m:
        return m.group(1), "social"
    return None, "unknown"

def find_repo_transcript(root, adid):
    if not adid:
        return None
    for p in (root / "analysis" / "enrichment").glob(f"*/transcripts/*/{adid}.json"):
        return p
    return None

def find_master_r2(root, adid):
    if not adid:
        return None
    import csv
    for masters in (root / "facebook" / "master", root / "google" / "master"):
        if not masters.exists():
            continue
        for f in masters.glob("*.csv"):
            try:
                with open(f, encoding="utf-8") as fh:
                    rd = csv.DictReader(fh)
                    for row in rd:
                        if adid in (row.get("ad_library_id", ""), row.get("advertiser_ad_id", "")) \
                           or adid in (row.get("r2_public_url", "") or ""):
                            url = (row.get("r2_public_url") or "").strip()
                            if url:
                                return url
            except Exception:
                continue
    return None

def download(url, dest):
    try:
        urllib.request.urlretrieve(url, dest)
        return dest.exists() and dest.stat().st_size > 1000
    except Exception as e:
        print(f"   [download] failed: {e}")
        return False

def ytdlp(url, out_tmpl):
    try:
        subprocess.run(["yt-dlp", "--no-playlist", "--socket-timeout", "30", "--retries", "2",
                        "-o", out_tmpl, url], check=True, capture_output=True, text=True, timeout=300)
        return True
    except Exception as e:
        print(f"   [yt-dlp] failed: {getattr(e,'stderr','') or e}")
        return False

def to_src(obj):
    """Normalize a transcript JSON (repo or fresh) into the generate-workflow `src` shape."""
    return {
        "language": obj.get("language"), "duration_s": obj.get("duration_s"),
        "format": obj.get("device_format"), "presenter": obj.get("presenter_type"),
        "angle": obj.get("message_angle"), "split_role": obj.get("split_screen_role"),
        "transcript": obj.get("transcript"), "on_screen_text": obj.get("on_screen_text"),
        "summary": obj.get("summary"),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shortlist", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--pipeline", default="facebook")
    ap.add_argument("--no-transcribe", action="store_true")
    args = ap.parse_args()
    root = pathlib.Path(args.root)
    work = pathlib.Path(args.workdir); work.mkdir(parents=True, exist_ok=True)
    (work / "videos").mkdir(exist_ok=True); (work / "transcripts").mkdir(exist_ok=True)
    shortlist = json.load(open(args.shortlist))

    client = None
    def get_client():
        nonlocal client
        if client is None:
            sys.path.insert(0, str(root / "analysis" / "scripts"))
            import _flash  # noqa
            client = ("flash", _flash, _flash.get_client(_flash.find_env(root, args.pipeline)))
        return client

    def transcribe(vpath):
        _, _flash, cl = get_client()
        from transcribe_tag import upload_active, PROMPT, RESPONSE_SCHEMA
        f = upload_active(cl, vpath)
        obj = _flash.generate_json(cl, _flash.DEFAULT_MODEL, [f, PROMPT], response_schema=RESPONSE_SCHEMA)
        try: cl.files.delete(name=f.name)
        except Exception: pass
        return obj

    ads, unresolved = [], []
    for a in shortlist:
        n = a["n"]; adid, kind = extract_id(a["ref_link"])
        print(f"#{n:>2} [{a['language'][:3]}] {a['name'][:36]:<36} id={adid} kind={kind}")
        cache = work / "transcripts" / f"{n:02d}_{adid or 'noid'}.json"
        obj = None
        if cache.exists():
            obj = json.load(open(cache))
        else:
            repo = find_repo_transcript(root, adid)
            if repo:
                obj = json.load(open(repo)); print(f"   reuse repo transcript: {repo.relative_to(root)}")
            elif not args.no_transcribe:
                vpath = work / "videos" / f"{n:02d}_{adid or 'vid'}.mp4"
                ok = False
                if kind in ("r2_mp4", "direct_mp4"):
                    ok = download(a["ref_link"], vpath)
                if not ok and kind == "fb_ads":
                    url = find_master_r2(root, adid)
                    if url: ok = download(url, vpath)
                if not ok and kind == "social":
                    if ytdlp(a["ref_link"], str(work / "videos" / f"{n:02d}_{adid}.%(ext)s")):
                        cands = list((work / "videos").glob(f"{n:02d}_{adid}.*"))
                        if cands: vpath = cands[0]; ok = True
                if ok:
                    print(f"   transcribing {vpath.name} ...")
                    try:
                        obj = transcribe(vpath)
                        cache.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
                    except Exception as e:
                        print(f"   [transcribe] FAILED: {e}")
        if not obj or not (obj.get("transcript") or obj.get("on_screen_text")):
            unresolved.append({"n": n, "name": a["name"], "ref_link": a["ref_link"], "id": adid, "kind": kind})
            continue
        if not cache.exists():
            cache.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
        src = to_src(obj)
        a2 = dict(a); a2["src"] = src; ads_entry = {
            "n": n, "name": a["name"], "language": a["language"], "faithful": a["faithful"],
            "brief_raw": a["brief_raw"], "duration_s": src.get("duration_s"),
            "format": src.get("format"), "angle": src.get("angle"),
        }
        a.update({"src": src}); ads.append(ads_entry)

    resolved = [a for a in shortlist if a.get("src")]
    (work / "source_master.json").write_text(json.dumps(resolved, ensure_ascii=False, indent=2))
    (work / "ads.json").write_text(json.dumps(ads, ensure_ascii=False, indent=2))
    print(f"\n[resolve_sources] resolved {len(resolved)}/{len(shortlist)} -> {work/'source_master.json'}")
    if unresolved:
        print(f"[resolve_sources] UNRESOLVED {len(unresolved)} (supply an mp4 or transcript, then re-run):")
        for u in unresolved:
            print(f"   #{u['n']} {u['name']} — {u['ref_link']} (id={u['id']}, kind={u['kind']})")

if __name__ == "__main__":
    main()
