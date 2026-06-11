#!/usr/bin/env python3.13
"""audit.py — per-competitor sanity audit. Catches the dangerous "exit 0 but BAD"
runs that exit codes miss: an anti-bot partial scrape, a silent enrichment hole, or
a collapse in R2 coverage. Run after a competitor's pipeline finishes.

  python3.13 tools/pipeline-run/audit.py <slug> [pipeline]

Emits a human summary and a final machine line:
  AUDIT <slug>: OK|WARN|FAIL | <reasons>
- FAIL  → real degradation (0 ads, scrape collapse, mostly-missing transcripts). The
          runner surfaces + alerts and must NOT treat the run as clean.
- WARN  → worth a look (moderate ad-count drop, some missing enrichment/coverage).
- OK    → looks healthy.
Designed to never crash: a missing input just downgrades that check to "n/a".
"""
from __future__ import annotations
import csv, sys, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]

# thresholds (tunable)
DROP_WARN, DROP_FAIL = 0.30, 0.55          # ad-count drop vs previous scrape
ENRICH_WARN, ENRICH_FAIL = 0.80, 0.50      # transcribed / video-ads
R2_WARN = 0.90                             # ads with an R2 lead creative


def _read_csv(p: pathlib.Path):
    try:
        with p.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return None


def audit(slug: str, pipeline: str = "facebook") -> tuple[str, list[str], list[str]]:
    reasons, notes = [], []
    verdict = "OK"

    def bump(v):
        nonlocal verdict
        order = {"OK": 0, "WARN": 1, "FAIL": 2}
        if order[v] > order[verdict]:
            verdict = v

    # ── 1. scrape health: today's ad count vs the previous scrape (history log) ──
    hist = _read_csv(ROOT / "analysis" / "history" / pipeline / f"{slug}.csv")
    media_today = {}
    if hist:
        by_date = {}
        for r in hist:
            d = (r.get("scrape_date") or "").strip()
            aid = (r.get("ad_id") or "").strip()
            if d and aid:
                by_date.setdefault(d, set()).add(aid)
        dates = sorted(by_date)
        if dates:
            cur = dates[-1]
            cur_n = len(by_date[cur])
            for r in hist:                 # today's media types (for enrichment check)
                if (r.get("scrape_date") or "").strip() == cur:
                    media_today[(r.get("ad_id") or "").strip()] = (r.get("media_type") or "").strip().lower()
            if cur_n == 0:
                bump("FAIL"); reasons.append(f"0 ads in latest scrape ({cur})")
            elif len(dates) >= 2:
                prev_n = len(by_date[dates[-2]])
                drop = (prev_n - cur_n) / prev_n if prev_n else 0.0
                if drop >= DROP_FAIL:
                    bump("FAIL"); reasons.append(f"ad count collapsed {prev_n}->{cur_n} ({drop:.0%} drop, {dates[-2]}->{cur})")
                elif drop >= DROP_WARN:
                    bump("WARN"); reasons.append(f"ad count dropped {prev_n}->{cur_n} ({drop:.0%})")
                else:
                    notes.append(f"ads {cur}: {cur_n} (prev {prev_n})")
            else:
                notes.append(f"ads {cur}: {cur_n} (first scrape)")
    else:
        notes.append("no history yet (n/a scrape-health)")

    # ── 2. enrichment completeness: transcribed / VIDEO ads ──
    tdir = ROOT / "analysis" / "enrichment" / pipeline / "transcripts" / slug
    transcribed = {p.stem for p in tdir.glob("*.json")} if tdir.is_dir() else set()
    video_ads = {a for a, m in media_today.items() if m in ("video", "")} if media_today else set()
    if video_ads:
        have = len(video_ads & transcribed)
        ratio = have / len(video_ads)
        if ratio < ENRICH_FAIL:
            bump("FAIL"); reasons.append(f"only {have}/{len(video_ads)} video ads transcribed ({ratio:.0%})")
        elif ratio < ENRICH_WARN:
            bump("WARN"); reasons.append(f"{have}/{len(video_ads)} video ads transcribed ({ratio:.0%})")
        else:
            notes.append(f"transcribed {have}/{len(video_ads)} video ads ({ratio:.0%})")
    else:
        notes.append("n/a enrichment (no video ads in latest scrape)")

    # ── 3. R2 lead-creative coverage (master) ──
    master = _read_csv(ROOT / pipeline / "master" / f"{slug}.csv")
    if master:
        ads = {}
        for r in master:
            aid = (r.get("ad_library_id") or "").strip()
            if aid:
                ads.setdefault(aid, False)
                if (r.get("r2_public_url") or "").strip():
                    ads[aid] = True
        if ads:
            cov = sum(1 for v in ads.values() if v) / len(ads)
            if cov < R2_WARN:
                bump("WARN"); reasons.append(f"R2 lead coverage {cov:.0%} of {len(ads)} ads")
            else:
                notes.append(f"R2 coverage {cov:.0%}")
    else:
        notes.append("no master yet (n/a R2 coverage)")

    return verdict, reasons, notes


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: audit.py <slug> [pipeline]")
    slug = sys.argv[1]
    pipeline = sys.argv[2] if len(sys.argv) > 2 else "facebook"
    verdict, reasons, notes = audit(slug, pipeline)
    print(f"── audit {slug} ({pipeline}) ──")
    for n in notes:
        print(f"   · {n}")
    for r in reasons:
        print(f"   ! {r}")
    print(f"AUDIT {slug}: {verdict} | {'; '.join(reasons) if reasons else 'healthy'}")
    return 0 if verdict != "FAIL" else 3


if __name__ == "__main__":
    raise SystemExit(main())
