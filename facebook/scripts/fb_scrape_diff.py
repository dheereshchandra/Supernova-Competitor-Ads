#!/usr/bin/env python3
"""
fb_scrape_diff.py — measure how faithfully fb_scrape.py (Playwright) reproduces a
known-good Claude-in-Chrome scrape. Run after fb_scrape.py to decide whether the
terminal scraper is trustworthy (no data loss) before adopting it.

Compares two FB input CSVs by ad_library_id, broken down per facebook_page_id
(so a missing PAGE — a gap in the hardcoded mapping — is told apart from a missing
AD — an actual scraper miss). Reports recall + field agreement on the overlap.

Usage:
    python3.13 facebook/scripts/fb_scrape_diff.py <new_csv> <reference_csv>
e.g.
    python3.13 facebook/scripts/fb_scrape_diff.py \
        facebook/inputs/fb-ads-duolingo-2026-06-07-1830.csv \
        facebook/inputs/fb-ads-duolingo-2026-06-04-1540.csv
"""
import csv
import sys
from collections import defaultdict

csv.field_size_limit(10 ** 9)
FIELDS = ["ad_start_date", "ad_media_type", "ad_version_count",
          "has_low_impression_warning"]


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def by_page(rows):
    d = defaultdict(dict)   # page_id -> {ad_id: row}
    for r in rows:
        aid = (r.get("ad_library_id") or "").strip()
        if aid:
            d[(r.get("facebook_page_id") or "").strip()][aid] = r
    return d


def main() -> int:
    if len(sys.argv) != 3:
        sys.exit("usage: fb_scrape_diff.py <new_csv> <reference_csv>")
    new_rows, ref_rows = load(sys.argv[1]), load(sys.argv[2])
    new, ref = by_page(new_rows), by_page(ref_rows)

    print(f"NEW : {sys.argv[1]}  ({len(new_rows)} rows, {len(new)} page(s))")
    print(f"REF : {sys.argv[2]}  ({len(ref_rows)} rows, {len(ref)} page(s))")
    print("=" * 64)

    total_ref = total_matched = 0
    for page_id, ref_ads in sorted(ref.items(), key=lambda kv: -len(kv[1])):
        new_ads = new.get(page_id, {})
        matched = set(ref_ads) & set(new_ads)
        missing = set(ref_ads) - set(new_ads)
        total_ref += len(ref_ads)
        total_matched += len(matched)
        pname = next(iter(ref_ads.values())).get("facebook_page_name", "")
        if not new_ads:
            print(f"\n● page {page_id} ({pname})")
            print(f"    ⚠ NOT in new scrape — {len(ref_ads)} ads (mapping gap, not a miss)")
            continue
        recall = len(matched) / len(ref_ads) * 100 if ref_ads else 0
        print(f"\n● page {page_id} ({pname})")
        print(f"    ref ads={len(ref_ads)}  new ads={len(new_ads)}  "
              f"matched={len(matched)}  missing={len(missing)}  recall={recall:.0f}%")
        # field agreement on the overlap
        for fld in FIELDS:
            agree = sum(1 for a in matched
                        if (ref_ads[a].get(fld) or "").strip() == (new_ads[a].get(fld) or "").strip())
            pct = agree / len(matched) * 100 if matched else 0
            print(f"      {fld:<28} agree {agree}/{len(matched)} ({pct:.0f}%)")
        if missing:
            print(f"      missing ad_ids (first 5): {list(missing)[:5]}")

    # extras (new ads not in ref — usually new ads launched since the ref scrape)
    extra = set().union(*[set(v) for v in new.values()]) - set().union(*[set(v) for v in ref.values()])
    print("\n" + "=" * 64)
    overall = total_matched / total_ref * 100 if total_ref else 0
    print(f"OVERALL recall (ads in ref also found by new): "
          f"{total_matched}/{total_ref} = {overall:.0f}%")
    print(f"Extra ads in new (not in ref — likely new launches): {len(extra)}")
    print("\nHow to read: per-page recall ≈100% with high field-agreement = the "
          "scraper is faithful for the pages it covers. A whole page shown as "
          "'NOT in new scrape' is a mapping gap (add the page_id), not a scraper bug.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
