#!/usr/bin/env python3
"""
embed_scripts.py — Phase 3 step 1. Embed each ad's "script signature" so scripts
can be clustered (same-script, translation-replica, visual-variant) and matched
across Facebook <-> Google.

Cross-language trick: the transcripts from transcribe_tag.py carry an inline
[English translation] for every non-English line. We embed the ENGLISH content
(translations + on-screen text + summary fallback), so a Hindi ad and its Tamil
translation land near each other in vector space — no multilingual model needed.

Embeddings are cheap (~free) and a separate model class from chat, so this is NOT
the Flash/Pro cost lever — but it still runs on YOUR Mac (needs google-genai +
GEMINI_API_KEY). Idempotent: one vector per ad, cached; re-runs only embed new ads.

Input:  analysis/enrichment/{pipeline}/transcripts/{competitor}/{ad_id}.json
Output: analysis/enrichment/{pipeline}/embeddings/{competitor}.jsonl  ({ad_id, vec})

Usage:
    python3 analysis/scripts/embed_scripts.py --pipeline facebook --competitor duolingo
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import _flash

EMBED_MODEL = "gemini-embedding-001"   # embeddings, not a chat model


def repo_root(explicit):
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def signature(sidecar: dict) -> str:
    """Build a language-neutral script signature, preferring English."""
    t = (sidecar.get("transcript") or "")
    ost = (sidecar.get("on_screen_text") or "")
    eng = " ".join(re.findall(r"\[([^\]]+)\]", f"{t} {ost}")).strip()
    sig = eng
    if len(sig) < 20:                       # already-English or no brackets
        sig = f"{t} {ost}".strip()
    if len(sig) < 20:
        sig = (sidecar.get("summary") or "").strip()
    return sig[:4000]


def embed(client, model: str, text: str) -> list[float]:
    resp = client.models.embed_content(model=model, contents=text)
    emb = resp.embeddings[0]
    return list(getattr(emb, "values", emb))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pipeline", required=True, choices=["facebook", "google"])
    ap.add_argument("--competitor", required=True)
    ap.add_argument("--base", default=None)
    ap.add_argument("--model", default=EMBED_MODEL)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = repo_root(args.base)
    slug = args.competitor.lower().strip()
    tdir = root / "analysis" / "enrichment" / args.pipeline / "transcripts" / slug
    if not tdir.is_dir():
        raise SystemExit(f"[error] no transcripts for {slug}: {tdir}\n"
                         f"        run transcribe_tag.py first.")
    out = root / "analysis" / "enrichment" / args.pipeline / "embeddings" / f"{slug}.jsonl"

    done = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["ad_id"])
            except (ValueError, KeyError):
                pass

    todo = []
    for p in sorted(tdir.glob("*.json")):
        ad_id = p.stem
        if ad_id in done:
            continue
        try:
            sc = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        sig = signature(sc)
        if sig:
            todo.append((ad_id, sig))
    if args.limit:
        todo = todo[:args.limit]

    print(f"{slug}: {len(done)} embedded, {len(todo)} new (model={args.model})")
    if not todo:
        print("nothing to do.")
        return 0
    if args.dry_run:
        for ad_id, sig in todo[:3]:
            print(f"   {ad_id}: {sig[:90]!r}")
        print("[dry-run] writing nothing.")
        return 0

    client = _flash.get_client(_flash.find_env(root, args.pipeline))
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0; failed = []
    with out.open("a", encoding="utf-8") as fh:
        for ad_id, sig in todo:
            try:
                vec = embed(client, args.model, sig)
                fh.write(json.dumps({"ad_id": ad_id, "vec": vec}) + "\n")
                fh.flush()
                n += 1
                if n % 50 == 0 or n == len(todo):
                    print(f"  embedded {n}/{len(todo)}")
            except Exception as e:  # noqa: BLE001
                failed.append((ad_id, str(e)[:160]))
                print(f"  [warn] {ad_id} failed: {e}")
    print(f"done: {n} new vectors, {len(failed)} FAILED -> {out}")
    # Embeddings are recoverable (re-run retries the misses), so only fail LOUD if
    # the step is broadly broken (>50% failed → likely API/key/network down).
    if todo and len(failed) > 0.5 * len(todo):
        print(f"[error] embedding failed for {len(failed)}/{len(todo)} (>50%) — "
              f"surfacing (API/key/network issue?). Re-run retries only the misses.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
