#!/usr/bin/env python3.13
"""
build_language_reconciliation.py — B9. Reconcile the TWO language signals (OFFLINE).

The pipeline detects language twice, from different surfaces:
  • COPY  — detect_language.py runs Flash on the ad's written copy
            (ad_primary_text/description/cta) → analysis/enrichment/{p}/language/{slug}.csv
  • AUDIO — transcribe_tag.py's sidecar "language" is the dominant SPOKEN/on-screen
            language of the video → analysis/enrichment/{p}/transcripts/{slug}/{ad_id}.json

Downstream they are merged by a blind override (the audio sidecar silently overwrites
the copy language in compute_rank_metrics.py), which THROWS AWAY the disagreement. But
the disagreement is itself a signal: e.g. Hindi audio + English copy = code-switch /
"Hinglish" targeting, a deliberate localisation choice worth tracking per competitor.

This keeps BOTH and flags agreement, writing:
  analysis/derived/{pipeline}/{slug}_language_reconciliation.csv   (one row per ad)
      ad_id, language_copy, language_audio, agreement_status, is_codeswitch
  analysis/derived/{pipeline}/{slug}_language_recon_summary.csv    (rollup)
      pipeline, competitor, agreement_status, ads   +   the top audio→copy mismatch pairs

agreement_status ∈ {agree, disagree, copy_only, audio_only, none}.

Usage:
    python3.13 analysis/scripts/build_language_reconciliation.py --pipeline facebook --competitor mysivi
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def repo_root(explicit):
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# Flash / transcription occasionally emit a non-answer; treat these as NO signal
# (not as a language that can "disagree" — that would be a false code-switch).
MISSING = {"", "unknown", "none", "na", "n/a", "und", "undetermined", "unclear"}


def norm_lang(s: str) -> str:
    return (s or "").strip().lower()


def is_real(norm: str) -> bool:
    return norm not in MISSING


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pipeline", required=True, choices=["facebook", "google"])
    ap.add_argument("--competitor", required=True)
    ap.add_argument("--base", default=None)
    args = ap.parse_args()

    root = repo_root(args.base)
    slug = args.competitor.lower().strip()
    enr = root / "analysis" / "enrichment" / args.pipeline
    derived = root / "analysis" / "derived" / args.pipeline
    derived.mkdir(parents=True, exist_ok=True)

    # COPY language (text)
    copy_lang: dict[str, str] = {}
    for r in read_csv(enr / "language" / f"{slug}.csv"):
        if r.get("ad_id"):
            copy_lang[r["ad_id"]] = r.get("language", "")

    # AUDIO language (sidecar)
    audio_lang: dict[str, str] = {}
    tdir = enr / "transcripts" / slug
    if tdir.is_dir():
        for p in tdir.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if d.get("language"):
                audio_lang[p.stem] = d["language"]

    if not copy_lang and not audio_lang:
        raise SystemExit(f"[error] no language signals for {slug} "
                         f"(run detect_language.py / transcribe_tag.py first).")

    rows = []
    status_counts: Counter = Counter()
    mismatch_pairs: Counter = Counter()   # (audio, copy) -> n
    for ad_id in sorted(set(copy_lang) | set(audio_lang)):
        c, a = copy_lang.get(ad_id, ""), audio_lang.get(ad_id, "")
        cn, an = norm_lang(c), norm_lang(a)
        cr, ar = is_real(cn), is_real(an)
        if cr and ar:
            status = "agree" if cn == an else "disagree"
        elif cr:
            status = "copy_only"
        elif ar:
            status = "audio_only"
        else:
            status = "none"
        is_cs = status == "disagree"
        if is_cs:
            mismatch_pairs[(a, c)] += 1
        status_counts[status] += 1
        rows.append({"ad_id": ad_id, "language_copy": c, "language_audio": a,
                     "agreement_status": status, "is_codeswitch": "true" if is_cs else "false"})

    out = derived / f"{slug}_language_reconciliation.csv"
    cols = ["ad_id", "language_copy", "language_audio", "agreement_status", "is_codeswitch"]
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader(); w.writerows(rows)

    # summary: status rollup + the mismatch pairs (the real signal)
    srows = [{"pipeline": args.pipeline, "competitor": slug, "kind": "status",
              "key": k, "ads": v} for k, v in status_counts.most_common()]
    for (a, c), n in mismatch_pairs.most_common():
        srows.append({"pipeline": args.pipeline, "competitor": slug, "kind": "mismatch",
                      "key": f"audio={a} | copy={c}", "ads": n})
    sout = derived / f"{slug}_language_recon_summary.csv"
    with sout.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["pipeline", "competitor", "kind", "key", "ads"])
        w.writeheader(); w.writerows(srows)

    both = status_counts["agree"] + status_counts["disagree"]
    print(f"{slug}: {len(rows)} ads | both-signals: {both} "
          f"(agree {status_counts['agree']}, disagree {status_counts['disagree']}) "
          f"| copy_only {status_counts['copy_only']} audio_only {status_counts['audio_only']}")
    if mismatch_pairs:
        top = ", ".join(f"{a}->{c}:{n}" for (a, c), n in mismatch_pairs.most_common(5))
        print(f"  code-switch pairs (audio->copy): {top}")
    print(f"  -> {out}\n  -> {sout}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
