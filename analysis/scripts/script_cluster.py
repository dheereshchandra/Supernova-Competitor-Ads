#!/usr/bin/env python3
"""
script_cluster.py — Phase 3 step 2 (OFFLINE, no API). Clusters ads by script
similarity and labels how each was replicated. Answers Q6-Q10.

From the embedding cache (embed_scripts.py), it builds cosine-similarity groups
(ads with sim >= --threshold share a script), then within each group labels each
ad's replication_type using language + format:
  original           — the earliest ad in the group (or a singleton's own script)
  exact_replica      — same script, same language, same format   (Q6 duplicate)
  translation_replica— same script, DIFFERENT language           (Q7)
  visual_variant     — same script + language, DIFFERENT format  (Q8)
  unique             — singleton (its own one-off script)

Output: analysis/enrichment/{pipeline}/scripts/{competitor}.csv
        (ad_id, script_group_id, group_size, variant_role, replication_type)

Usage:
    python3 analysis/scripts/script_cluster.py --pipeline facebook --competitor duolingo
    python3 analysis/scripts/script_cluster.py --pipeline facebook --competitor duolingo --threshold 0.9
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
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        ids.append(str(rec["ad_id"]))
        vecs.append(rec["vec"])
    return ids, np.asarray(vecs, dtype=float)


def load_meta(root: Path, pipeline: str, slug: str) -> dict:
    """Per-ad {language, device_format, first_seen} from sidecars + enriched."""
    base = root / "analysis" / "enrichment" / pipeline
    meta: dict[str, dict] = {}
    lang_csv = base / "language" / f"{slug}.csv"
    for r in read_csv(lang_csv):
        meta.setdefault(r["ad_id"], {})["language"] = r.get("language", "")
    tdir = base / "transcripts" / slug
    if tdir.is_dir():
        for p in tdir.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            rec = meta.setdefault(p.stem, {})
            if d.get("language"):
                rec["language"] = d["language"]
            if d.get("device_format"):
                rec["device_format"] = d["device_format"]
            if d.get("presenter_type"):
                rec["presenter_type"] = d["presenter_type"]
    for r in read_csv(root / "analysis" / "derived" / pipeline / f"{slug}_enriched.csv"):
        meta.setdefault(r["ad_id"], {})["first_seen"] = r.get("first_seen", "")
    return meta


class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def cluster(ids, mat, threshold):
    """Union-find connected components on cosine sim >= threshold."""
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = mat / norms
    sim = unit @ unit.T
    n = len(ids)
    uf = UnionFind(n)
    for i in range(n):
        # only upper triangle; threshold edges
        js = np.where(sim[i, i + 1:] >= threshold)[0]
        for j in js:
            uf.union(i, i + 1 + int(j))
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)
    return list(groups.values())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pipeline", required=True, choices=["facebook", "google"])
    ap.add_argument("--competitor", required=True)
    ap.add_argument("--base", default=None)
    ap.add_argument("--threshold", type=float, default=0.95,
                    help="cosine >= this = same script (honors the >95% bar; tune on a labeled sample)")
    args = ap.parse_args()

    root = repo_root(args.base)
    slug = args.competitor.lower().strip()
    epath = root / "analysis" / "enrichment" / args.pipeline / "embeddings" / f"{slug}.jsonl"
    if not epath.exists():
        raise SystemExit(f"[error] no embeddings for {slug}: {epath}\n"
                         f"        run embed_scripts.py first.")

    ids, mat = load_embeddings(epath)
    if len(ids) == 0:
        raise SystemExit(f"[error] embedding cache is empty: {epath}")
    meta = load_meta(root, args.pipeline, slug)
    comps = cluster(ids, mat, args.threshold)

    rows = []
    counts: dict[str, int] = {}
    for gi, members in enumerate(sorted(comps, key=len, reverse=True)):
        member_ids = [ids[i] for i in members]
        size = len(member_ids)
        gid = f"{slug}-g{gi:04d}"
        if size == 1:
            ad = member_ids[0]
            rows.append({"ad_id": ad, "script_group_id": gid, "group_size": 1,
                         "variant_role": "original", "replication_type": "unique"})
            counts["unique"] = counts.get("unique", 0) + 1
            continue
        # original = earliest first_seen (fallback: smallest ad_id)
        def _fs(a):
            return (meta.get(a, {}).get("first_seen", "") or "9999", a)
        original = min(member_ids, key=_fs)
        olang = meta.get(original, {}).get("language", "")
        ofmt = meta.get(original, {}).get("device_format", "")
        opres = meta.get(original, {}).get("presenter_type", "")
        for ad in member_ids:
            if ad == original:
                role, rtype = "original", "original"
            else:
                lang = meta.get(ad, {}).get("language", "")
                fmt = meta.get(ad, {}).get("device_format", "")
                pres = meta.get(ad, {}).get("presenter_type", "")
                role = "replica"
                if olang and lang and lang != olang:
                    rtype = "translation_replica"
                elif ofmt and fmt and fmt != ofmt:
                    rtype = "visual_variant"
                elif opres and pres and pres != opres:
                    rtype = "character_variant"
                else:
                    rtype = "exact_replica"
            rows.append({"ad_id": ad, "script_group_id": gid, "group_size": size,
                         "variant_role": role, "replication_type": rtype})
            counts[rtype] = counts.get(rtype, 0) + 1

    out = root / "analysis" / "enrichment" / args.pipeline / "scripts" / f"{slug}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["ad_id", "script_group_id", "group_size", "variant_role", "replication_type"]
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader(); w.writerows(rows)

    n_groups = len(comps)
    n_multi = sum(1 for c in comps if len(c) > 1)
    print(f"{slug}: {len(ids)} ads -> {n_groups} script groups "
          f"({n_multi} with replication) | types: {dict(sorted(counts.items()))}")
    print(f"  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
