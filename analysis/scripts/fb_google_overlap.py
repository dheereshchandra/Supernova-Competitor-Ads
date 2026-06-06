#!/usr/bin/env python3
"""
fb_google_overlap.py — Phase 3 step 3 (OFFLINE, no API). Answers Q12: does the
same advertiser's Facebook ad reappear on Google, and is it the top-ranked ones?

For one competitor present on both platforms, it matches each Facebook ad to its
nearest Google ad by script-signature embedding (cosine). A match means "the same
creative/script ran on both." It then reports the transfer ratio and whether
matched FB ads skew toward high rank (i.e. they port their winners, not everything).

Needs the embedding caches on BOTH sides (embed_scripts.py for facebook AND
google) plus the enriched metrics for rank/verdict context.

Output: analysis/derived/cross_platform/{competitor}_overlap.csv

Usage:
    python3 analysis/scripts/fb_google_overlap.py --competitor duolingo
    python3 analysis/scripts/fb_google_overlap.py --competitor duolingo --threshold 0.82
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


def repo_root(explicit):
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_embeddings(path: Path):
    ids, vecs = [], []
    if not path.exists():
        return ids, np.zeros((0, 0))
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            ids.append(str(rec["ad_id"]))
            vecs.append(rec["vec"])
    return ids, np.asarray(vecs, dtype=float)


def unit(mat):
    if mat.size == 0:
        return mat
    n = np.linalg.norm(mat, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return mat / n


def enriched_index(root: Path, pipeline: str, slug: str) -> dict:
    idx = {}
    for r in read_csv(root / "analysis" / "derived" / pipeline / f"{slug}_enriched.csv"):
        idx[r["ad_id"]] = r
    return idx


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competitor", required=True)
    ap.add_argument("--base", default=None)
    ap.add_argument("--threshold", type=float, default=0.82,
                    help="cosine >= this = same creative across platforms (looser "
                         "than within-platform; tune on a labeled sample)")
    args = ap.parse_args()

    root = repo_root(args.base)
    slug = args.competitor.lower().strip()
    fb_ids, fb_mat = load_embeddings(
        root / "analysis" / "enrichment" / "facebook" / "embeddings" / f"{slug}.jsonl")
    g_ids, g_mat = load_embeddings(
        root / "analysis" / "enrichment" / "google" / "embeddings" / f"{slug}.jsonl")
    if len(fb_ids) == 0 or len(g_ids) == 0:
        raise SystemExit(f"[error] need embeddings on BOTH platforms for {slug} "
                         f"(facebook: {len(fb_ids)}, google: {len(g_ids)}). "
                         f"Run embed_scripts.py for each.")

    sim = unit(fb_mat) @ unit(g_mat).T            # (n_fb, n_g)
    best_j = sim.argmax(axis=1)
    best_s = sim.max(axis=1)

    fb_enr = enriched_index(root, "facebook", slug)
    g_enr = enriched_index(root, "google", slug)

    rows, matched = [], 0
    for i, fb_ad in enumerate(fb_ids):
        s = float(best_s[i])
        is_match = s >= args.threshold
        g_ad = g_ids[int(best_j[i])] if is_match else ""
        if is_match:
            matched += 1
        fe = fb_enr.get(fb_ad, {})
        ge = g_enr.get(g_ad, {})
        rows.append({
            "competitor": slug, "fb_ad_id": fb_ad,
            "fb_best_page_rank": fe.get("best_page_rank", ""),
            "fb_verdict": fe.get("verdict", ""),
            "matched": is_match, "cosine": round(s, 3),
            "google_ad_id": g_ad,
            "google_best_page_rank": ge.get("best_page_rank", ""),
        })

    out = root / "analysis" / "derived" / "cross_platform" / f"{slug}_overlap.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["competitor", "fb_ad_id", "fb_best_page_rank", "fb_verdict",
            "matched", "cosine", "google_ad_id", "google_best_page_rank"]
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader(); w.writerows(rows)

    # do matched FB ads skew higher-ranked than unmatched? (Q12b)
    def med_rank(subset):
        vals = sorted(int(r["fb_best_page_rank"]) for r in subset
                      if str(r["fb_best_page_rank"]).isdigit())
        return vals[len(vals) // 2] if vals else None
    m = [r for r in rows if r["matched"]]
    u = [r for r in rows if not r["matched"]]
    ratio = matched / len(fb_ids) if fb_ids else 0
    print(f"{slug}: {len(fb_ids)} FB ads, {len(g_ids)} Google ads | "
          f"transfer ratio = {matched}/{len(fb_ids)} = {ratio:.0%}")
    print(f"  median FB rank — matched: {med_rank(m)}  vs  unmatched: {med_rank(u)} "
          f"(lower matched rank ⇒ they port their winners)")
    print(f"  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
