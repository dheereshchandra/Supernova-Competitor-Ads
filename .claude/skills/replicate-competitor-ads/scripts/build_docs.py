#!/usr/bin/env python3.13
"""Build one plain-text doc body per ad (the deliverable layout — SINGLE SOURCE OF
THE DOC FORMAT). Each body, in order:
    Title
    🎬 Competitor reference link
    ⚠️ Reviewer note (if any)
    VISUAL & CAST  (Format, Look, Cast, Scenes at a glance)
    FULL SCRIPT — ENGLISH               (one continuous block, no scene headers)
    FULL SCRIPT — <LANGUAGE> (ROMANIZED)(one continuous block)
(No per-scene split, no TTS section.)

Reads generated.json + source_master.json. Writes <out>/NN-lang-slug.txt + upload_manifest.json
(the manifest is what the agent reads to create one Google Doc per entry).

Usage: python3.13 build_docs.py --gen generated.json --src source_master.json --out <dir>
"""
import argparse, json, pathlib, re

BAR = "━" * 56

def lines(block):
    return [ln.strip() for ln in (block or "").split("\n") if ln.strip()]

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]

def continuous(sc, field):
    blocks = []
    for scene in sc.get("scenes", []):
        ls = lines(scene.get(field))
        if ls:
            blocks.append("\n".join(ls))
    return "\n\n".join(blocks)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    GEN = json.load(open(args.gen))
    SRC = {a["n"]: a for a in json.load(open(args.src))}
    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)

    manifest = []
    for rec in sorted(GEN, key=lambda r: r["n"]):
        n = rec["n"]; sc = rec["script"]; src = SRC.get(n, {})
        lang = sc.get("language") or src.get("language", "")
        name = src.get("name", sc.get("name", f"ad-{n}")); ref = src.get("ref_link", "")
        L = [f"Supernova Script ({lang}) — {name} (W26)", "",
             f"🎬 Competitor reference (original ad): {ref}"]
        if (sc.get("reviewer_note") or "").strip():
            L += ["", f"⚠️ Reviewer note: {sc['reviewer_note'].strip()}"]
        L += ["", BAR, "VISUAL & CAST", BAR,
              f"Format: {sc.get('format','')}", f"Look: {sc.get('visual_overview','')}"]
        cast = sc.get("cast") or []
        if cast:
            L.append(""); L.append("Cast:")
            for c in cast:
                tail = f" — {c.get('role','')}" if c.get("role") else ""
                L.append(f"   • Character {c.get('id','')} = {c.get('name','')}{tail}")
        glance = sc.get("scenes_at_a_glance") or []
        if glance:
            L.append(""); L.append("Scenes at a glance:")
            for g in glance:
                L.append(f"   • {g}")
        # Render whichever script blocks exist: English master (Claude / English path) and/or
        # native script (repo direct seed→target path), always the romanized target language.
        eng, nat, rom = continuous(sc, "english"), continuous(sc, "native"), continuous(sc, "romanized")
        if eng:
            L += ["", BAR, "FULL SCRIPT — ENGLISH", BAR, eng]
        if nat:
            L += ["", BAR, f"FULL SCRIPT — {lang.upper()} (NATIVE SCRIPT)", BAR, nat]
        if rom:
            L += ["", BAR, f"FULL SCRIPT — {lang.upper()} (ROMANIZED)", BAR, rom]
        L += [""]
        body = "\n".join(L)
        fn = f"{n:02d}-{lang.lower()}-{slug(name)}.txt"
        (out / fn).write_text(body, encoding="utf-8")
        manifest.append({"n": n, "language": lang, "name": name, "ref_link": ref, "txt": fn,
                         "title": f"Supernova Script ({lang}) — {name} (W26)", "chars": len(body)})

    (out / "upload_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"[build_docs] {len(manifest)} doc bodies -> {out}")
    for m in manifest:
        print(f"  #{m['n']:>2} [{m['language'][:3]}] {m['chars']:>5}c  {m['txt']}")

if __name__ == "__main__":
    main()
