#!/usr/bin/env python3
"""
script_cluster.py — Phase 3 step 2 (OFFLINE, no API). Clusters ads by script
similarity and labels how each was replicated. Answers Q6-Q10.

From the embedding cache (embed_scripts.py), it builds cosine-similarity groups
(ads with sim >= --threshold share a script). Within each group, the language/
format/presenter tags name the axis of variation, and the VERBATIM TEXT (transcript
+ on-screen text from the sidecars) then splits an otherwise-identical replica into
a true exact copy vs a re-scripted reword (B5):
  original           — the earliest ad in the group (or a singleton's own script)
  translation_replica— different language                                         (Q8)
  visual_variant     — same language, different device format                     (Q7)
  character_variant  — same language/format, different presenter (actor swap)
  exact_replica      — same language/format/presenter AND verbatim text
                       (ratio >= --text-exact-threshold, or no text to compare)   (Q6)
  reworded_replica   — same language/format/presenter, but re-scripted text
                       (ratio < --text-exact-threshold)                           (Q8)
  unique             — singleton (its own one-off script)
A per-replica `text_similarity` (difflib ratio vs the group original, 0-1) is
recorded for every replica, so a "translation" that is actually verbatim (a lying
language tag) is visible as a high ratio.

Output: analysis/enrichment/{pipeline}/scripts/{competitor}.csv
        (ad_id, script_group_id, group_size, variant_role, replication_type,
         text_similarity)

Usage:
    python3 analysis/scripts/script_cluster.py --pipeline facebook --competitor duolingo
    python3 analysis/scripts/script_cluster.py --pipeline facebook --competitor duolingo --threshold 0.9
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import unicodedata
from pathlib import Path

import numpy as np


def norm_text(s: str) -> str:
    """Lowercase, drop [English] bracketed glosses (compare the NATIVE surface so a
    Hindi original vs its English translation read as different), drop punctuation/
    symbols, collapse whitespace. Keeps letters AND combining MARKS + digits, so
    Devanagari/Tamil diacritics survive (a plain `\\w` regex drops Mn/Mc marks and
    would collapse distinct Hindi words to the same string)."""
    s = (s or "").lower()
    s = re.sub(r"\[[^\]]*\]", " ", s)          # drop "[English translation]" glosses
    s = "".join(ch if (ch.isspace() or unicodedata.category(ch)[0] in ("L", "M", "N"))
                else " " for ch in s)
    return re.sub(r"\s+", " ", s).strip()


def text_sim(a: str, b: str):
    """difflib character ratio of two normalized transcripts, or None when either has
    too little text to judge (image-only / music-only / un-transcribed)."""
    na, nb = norm_text(a), norm_text(b)
    if len(na) < 8 or len(nb) < 8:
        return None
    return difflib.SequenceMatcher(None, na, nb).ratio()


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
            txt = " ".join(str(d.get(k, "")) for k in ("transcript", "on_screen_text")).strip()
            if txt:
                rec["text"] = txt
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
    ap.add_argument("--text-exact-threshold", type=float, default=0.90,
                    help="difflib text ratio >= this (vs the group original) = exact_replica (B5)")
    ap.add_argument("--sweep", action="store_true",
                    help="diagnostic: print group counts across a range of cosine thresholds "
                         "(validate the 0.95 cutoff) and exit — writes nothing (B9)")
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

    if args.sweep:   # B9: threshold sensitivity — no output written
        print(f"{slug}: {len(ids)} ads — cosine-threshold sweep "
              f"(current default = {args.threshold})")
        print(f"  {'thresh':>7} {'groups':>7} {'multi':>6} {'clustered':>10} {'largest':>8}")
        for t in (0.85, 0.88, 0.90, 0.92, 0.95, 0.97, 0.99):
            comps_t = cluster(ids, mat, t)
            multi = [c for c in comps_t if len(c) > 1]
            clustered = sum(len(c) for c in multi)
            largest = max((len(c) for c in comps_t), default=0)
            star = "  <-- default" if abs(t - args.threshold) < 1e-9 else ""
            print(f"  {t:>7.2f} {len(comps_t):>7} {len(multi):>6} {clustered:>10} {largest:>8}{star}")
        return 0

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
                         "variant_role": "original", "replication_type": "unique",
                         "text_similarity": ""})
            counts["unique"] = counts.get("unique", 0) + 1
            continue
        # original = earliest first_seen (fallback: smallest ad_id)
        def _fs(a):
            return (meta.get(a, {}).get("first_seen", "") or "9999", a)
        original = min(member_ids, key=_fs)
        olang = meta.get(original, {}).get("language", "")
        ofmt = meta.get(original, {}).get("device_format", "")
        opres = meta.get(original, {}).get("presenter_type", "")
        otext = meta.get(original, {}).get("text", "")
        for ad in member_ids:
            if ad == original:
                role, rtype, tsim = "original", "original", ""
            else:
                lang = meta.get(ad, {}).get("language", "")
                fmt = meta.get(ad, {}).get("device_format", "")
                pres = meta.get(ad, {}).get("presenter_type", "")
                role = "replica"
                sim = text_sim(otext, meta.get(ad, {}).get("text", ""))
                tsim = "" if sim is None else f"{sim:.3f}"
                # The tags name the axis of variation (language > format > presenter);
                # the verbatim text then splits an otherwise-identical replica into a
                # true exact copy vs a re-scripted reword. text_similarity is recorded
                # for ALL replicas, so a "translation" that is actually verbatim (a
                # lying language tag) is still visible as a high ratio.
                if olang and lang and lang != olang:
                    rtype = "translation_replica"
                elif ofmt and fmt and fmt != ofmt:
                    rtype = "visual_variant"
                elif opres and pres and pres != opres:
                    rtype = "character_variant"
                elif sim is not None and sim < args.text_exact_threshold:
                    rtype = "reworded_replica"
                else:
                    rtype = "exact_replica"              # same tags + verbatim (or no text)
            rows.append({"ad_id": ad, "script_group_id": gid, "group_size": size,
                         "variant_role": role, "replication_type": rtype,
                         "text_similarity": tsim})
            counts[rtype] = counts.get(rtype, 0) + 1

    out = root / "analysis" / "enrichment" / args.pipeline / "scripts" / f"{slug}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["ad_id", "script_group_id", "group_size", "variant_role", "replication_type",
            "text_similarity"]
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
