#!/usr/bin/env python3.13
"""DEFAULT generation engine: run the REPO / Ad-Studio Creative-Studio pipeline
(Gemini) for a shortlist of competitor ads, then adapt its output into the skill's
generated.json shape. This delegates to the SAME repo scripts Ad Studio's jobs.py
calls, so any change to the repo pipeline (prompts, models, QC) is picked up here
automatically — there is NO second copy of the generation logic.

Sequence (mirrors webapp/backend/jobs.py STEPS_VIDEO_DIRECT), all run from `facebook/`:
  download videos -> step4_decompose.py upload -> step4_decompose_sync.py
  -> [write <id>.brief.txt for brief ads] -> step4_rewrite.py submit/poll (per target
  language, direct seed->target, Gemini 3.1 Pro) -> step4_qc.py (Gemini Flash audit)
  -> adapt <id>.<lang>.supernova.json -> generated.json

Requires the ads to be rows in facebook/master/<competitor>.csv with an r2_public_url,
and facebook/.env with GEMINI_API_KEY (+ R2). Cost ≈ $0.05/ad (Gemini Pro decompose+rewrite).

Usage:
  python3.13 generate_repo_pipeline.py --shortlist shortlist.json --root <repo> \
      --competitor <slug> --workdir <dir> [--max-poll-min 45] [--no-qc]
"""
import argparse, json, pathlib, re, subprocess, sys, time, collections

def sh(args, cwd, timeout=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)

def ad_id_of(link):
    m = re.search(r"/(\d+)\.mp4", link or "") or re.search(r"[?&]id=(\d+)", link or "")
    return m.group(1) if m else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shortlist", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--competitor", required=True, help="master slug, e.g. mysivi")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--max-poll-min", type=int, default=45)
    ap.add_argument("--no-qc", action="store_true")
    ap.add_argument("--date", default="pipeline", help="video subdir tag")
    args = ap.parse_args()
    root = pathlib.Path(args.root); fb = root / "facebook"
    work = pathlib.Path(args.workdir); work.mkdir(parents=True, exist_ok=True)
    scenes = fb / "step4_workspace" / "scenes"; scenes.mkdir(parents=True, exist_ok=True)
    vdir = fb / "videos" / f"{args.competitor}-{args.date}"; vdir.mkdir(parents=True, exist_ok=True)
    short = json.load(open(args.shortlist))

    # map ad -> id, language, brief; group ids by language
    by_lang = collections.OrderedDict(); n2id = {}; all_ids = []
    for a in short:
        aid = ad_id_of(a["ref_link"])
        if not aid:
            print(f"[warn] no ad id for #{a['n']} {a['name']!r}; skipping"); continue
        n2id[a["n"]] = {"id": aid, "language": a["language"], "name": a["name"]}
        by_lang.setdefault(a["language"], [])
        if aid not in by_lang[a["language"]]:
            by_lang[a["language"]].append(aid)
        if aid not in all_ids:
            all_ids.append(aid)
        if not a.get("faithful"):
            (scenes / f"{aid}.brief.txt").write_text(a["brief_raw"], encoding="utf-8")
    json.dump(n2id, open(work / "n_to_id.json", "w"))

    # 1. download videos (curl with a UA — R2 rejects urllib's default UA)
    for a in short:
        aid = ad_id_of(a["ref_link"])
        if not aid: continue
        dest = vdir / f"{aid}.mp4"
        if dest.exists() and dest.stat().st_size > 1000: continue
        sh(["curl", "-fsSL", "-A", "Mozilla/5.0", a["ref_link"], "-o", str(dest)], cwd=root)
    have = sum(1 for i in all_ids if (vdir / f"{i}.mp4").exists())
    print(f"[videos] {have}/{len(all_ids)} present in {vdir}")

    # 2. decompose (only ids lacking a sidecar) — upload + sync (Gemini)
    todo = [i for i in all_ids if not (scenes / f"{i}.json").exists()]
    if todo:
        print(f"[decompose] {len(todo)} ids need decompose")
        sh(["python3.13", "scripts/step4_decompose.py", "upload", "--competitor", args.competitor, *todo], cwd=fb, timeout=1800)
        for _ in range(3):  # sync decompose is idempotent; retry transient timeouts
            sh(["python3.13", "scripts/step4_decompose_sync.py", args.competitor, *todo], cwd=fb, timeout=1800)
            todo = [i for i in todo if not (scenes / f"{i}.json").exists()]
            if not todo: break
        if todo: print(f"[decompose] WARNING still missing: {todo}")
    else:
        print("[decompose] all sidecars present, skipping")

    # 3. rewrite submit + poll, per target language (direct seed->target, Gemini 3.1 Pro)
    deadline = time.time() + args.max_poll_min * 60
    for lang, ids in by_lang.items():
        r = sh(["python3.13", "scripts/step4_rewrite.py", "submit", "--competitor", args.competitor,
                "--target-languages", lang, *ids], cwd=fb, timeout=600)
        m = re.search(r"poll\s+([A-Za-z0-9_-]+)", r.stdout)
        if not m:
            print(f"[rewrite:{lang}] submit failed:\n{r.stdout}\n{r.stderr}"); continue
        short_id = m.group(1); print(f"[rewrite:{lang}] submitted {len(ids)} -> poll {short_id}")
        retried = False
        while time.time() < deadline:
            p = sh(["python3.13", "scripts/step4_rewrite.py", "poll", short_id], cwd=fb, timeout=300)
            rc = p.returncode
            if rc == 0:
                print(f"[rewrite:{lang}] DONE"); break
            if rc == 4:  # some keys dropped (malformed JSON) — resubmit dropped once
                fpath = fb / "step4_workspace" / "batches" / f"rewrite_{short_id}.failures.json"
                dropped = list(json.load(open(fpath)).get("missing", [])) if fpath.exists() else []
                drop_ids = [d.split(".")[0] for d in dropped]
                print(f"[rewrite:{lang}] {len(drop_ids)} dropped: {drop_ids}")
                if drop_ids and not retried:
                    retried = True
                    r2 = sh(["python3.13", "scripts/step4_rewrite.py", "submit", "--competitor", args.competitor,
                             "--target-languages", lang, *drop_ids], cwd=fb, timeout=600)
                    m2 = re.search(r"poll\s+([A-Za-z0-9_-]+)", r2.stdout)
                    if m2: short_id = m2.group(1); continue
                break
            if rc == 2:
                print(f"[rewrite:{lang}] FAILED: {p.stdout[-200:]}"); break
            time.sleep(70)  # rc 1 = still running

    # 4. QC (Gemini Flash audit) — non-fatal, advisory
    if not args.no_qc:
        for lang, ids in by_lang.items():
            sh(["python3.13", "scripts/step4_qc.py", *ids, "--competitor", args.competitor, "--langs", lang], cwd=fb, timeout=900)

    # 5. adapt <id>.<lang>.supernova.json -> generated.json (skill schema; native + romanized)
    out, missing = [], []
    SRC = {a["n"]: a for a in short}
    for n_str, meta in n2id.items():
        n = int(n_str); aid = meta["id"]; lang = meta["language"]
        p = scenes / f"{aid}.{lang.lower()}.supernova.json"
        if not p.exists(): missing.append((n, aid, lang)); continue
        parsed = json.load(open(p)).get("parsed", {})
        sc = [{"n": s.get("n"), "scene_label": s.get("scene_label", ""),
               "native": s.get("script_native", "") or s.get("supernova_script", ""),
               "romanized": s.get("script_roman", "") or s.get("script_romanized", "")}
              for s in parsed.get("scenes", [])]
        out.append({"n": n, "revised": False, "verdict": {"pass": True, "issues": []}, "script": {
            "n": n, "name": SRC[n]["name"], "language": lang,
            "format": parsed.get("format", ""), "visual_overview": parsed.get("visual_overview", ""),
            "reviewer_note": "Generated by the repo Creative-Studio pipeline (Gemini decompose -> Gemini 3.1-Pro rewrite, direct seed->target).",
            "cast": [{"id": c.get("id", ""), "name": c.get("name", ""), "role": c.get("role", "")} for c in parsed.get("characters", [])],
            "scenes_at_a_glance": [f"Scene {s.get('n')} — {s.get('scene_label','')}" for s in parsed.get("scenes", []) if s.get("scene_label")],
            "scenes": sc}})
    out.sort(key=lambda r: r["n"])
    (work / "generated.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"[adapt] {len(out)}/{len(n2id)} -> {work/'generated.json'}")
    if missing: print(f"[adapt] MISSING (resubmit/poll again): {missing}")

if __name__ == "__main__":
    main()
