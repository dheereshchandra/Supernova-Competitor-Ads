#!/usr/bin/env python3
"""
fb_scrape_diff.py — measure how faithfully a terminal scrape (fb_scrape_v2.py)
reproduces a known-good Claude-in-Chrome scrape. The bench instrument for the
V1↔V2 parallel-run window: run BOTH scrapers for the same competitor on the
same day, diff, fix every real miss, repeat until clean — only then cut over.

Compares two FB input CSVs by ad_library_id, broken down per facebook_page_id
(so a missing PAGE — a gap in the hardcoded mapping — is told apart from a
missing AD — an actual scraper miss). When BOTH files carry the v2.3 columns
(version_index / creative_index_in_ad), it additionally checks version-row
recall and the version_* fields at (ad, version) grain.

Field agreement is reported in FOUR classes so "the new scraper filled a field
the reference left blank" (richer — common: old Claude CSVs leave platforms /
destination_url / start_date blank) is never conflated with a real loss:
    agree      same non-blank value (or both blank)
    richer     ref blank, new filled        → new scraper captured MORE
    MISS       ref filled, new blank        → data loss — must reach 0
    mismatch   both filled, values differ   → real disagreement — must reach 0

Zero-miss bar (operator's): for every field, MISS == 0 and mismatch == 0
(after explainable mismatches — e.g. dates that moved between two scrape
times — are ruled out by scraping the same day).

Usage:
    python3.13 facebook/scripts/fb_scrape_diff.py <new_csv> <reference_csv>
e.g.
    python3.13 facebook/scripts/fb_scrape_diff.py \
        facebook/inputs/fb-ads-mysivi-2026-06-10-1830-v2.csv \
        facebook/inputs/fb-ads-mysivi-2026-06-10.csv
"""
import csv
import re
import sys
from collections import defaultdict

csv.field_size_limit(10 ** 9)

# ad-level fields (checked in both modes; CDN URLs excluded — they are signed
# per scrape and never match by design)
AD_FIELDS = ["ad_start_date", "ad_end_date", "ad_media_type", "ad_version_count",
             "ad_has_multiple_versions", "has_low_impression_warning",
             "ad_primary_text", "ad_description", "ad_cta_label",
             "ad_destination_url", "ad_distribution_platforms",
             "creative_count_in_ad", "creative_aspect_ratio",
             "facebook_page_followers", "page_rank"]

# version-level fields (v2.3 mode only, compared at (ad_id, version_index))
VERSION_FIELDS = ["version_start_date", "version_end_date", "version_primary_text",
                  "version_description", "version_cta_label",
                  "version_destination_url", "version_platforms_distribution"]


def norm(s):
    """whitespace-insensitive, case-insensitive compare (so trivial formatting
    differences don't count as a miss)."""
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def has_v23(rows):
    return bool(rows) and "version_index" in rows[0] and "creative_index_in_ad" in rows[0]


def by_page_ad(rows):
    """page_id -> {ad_id: baseline_row} (first row seen = version-0/creative-0)."""
    d = defaultdict(dict)
    for r in rows:
        aid = (r.get("ad_library_id") or "").strip()
        if aid:
            d[(r.get("facebook_page_id") or "").strip()].setdefault(aid, r)
    return d


def version_rows(rows):
    """(ad_id, version_key) -> first row of that version. version_key is the
    STABLE version_id (the version's own ad_archive_id) when present, else the
    positional version_index.

    Two scrapers enumerate an ad's versions in different orders (the listing
    payload is impression-ordered; a Claude detail-view walk is in Meta's version
    order), so the same version gets a different version_index in each file.
    Matching on version_id is what lets identical versions line up; we fall back
    to the index only when a scrape left version_id blank (e.g. some Claude rows
    for ads Meta reports as single-version)."""
    d = {}
    for r in rows:
        aid = (r.get("ad_library_id") or "").strip()
        if not aid:
            continue
        vid = (r.get("version_id") or "").strip()
        vkey = ("id", vid) if vid else ("idx", (r.get("version_index") or "0").strip() or "0")
        d.setdefault((aid, vkey), r)
    return d


def classify(ref_val, new_val):
    rn, nn = norm(ref_val), norm(new_val)
    if rn == nn:
        return "agree"
    if not rn and nn:
        return "richer"
    if rn and not nn:
        return "MISS"
    return "mismatch"


def field_report(pairs, fields, indent="      "):
    """pairs: list of (ref_row, new_row). Prints the 4-class breakdown per field."""
    clean = True
    for fld in fields:
        counts = defaultdict(int)
        examples = {}
        for ref_r, new_r in pairs:
            if fld not in ref_r and fld not in new_r:
                counts["n/a"] += 1
                continue
            cls = classify(ref_r.get(fld), new_r.get(fld))
            counts[cls] += 1
            if cls in ("MISS", "mismatch") and cls not in examples:
                examples[cls] = (ref_r.get("ad_library_id"),
                                 new_r.get(fld), ref_r.get(fld))
        total = len(pairs)
        if counts.get("n/a") == total:
            print(f"{indent}{fld:<30} (column absent — skipped)")
            continue
        bad = counts["MISS"] + counts["mismatch"]
        flag = "" if bad == 0 else "  ← check"
        if bad:
            clean = False
        summary = f"agree {counts['agree']}/{total}"
        if counts["richer"]:
            summary += f" · richer {counts['richer']}"
        if counts["MISS"]:
            summary += f" · MISS {counts['MISS']}"
        if counts["mismatch"]:
            summary += f" · mismatch {counts['mismatch']}"
        print(f"{indent}{fld:<30} {summary}{flag}")
        for cls, (aid, nv, rv) in examples.items():
            print(f"{indent}  e.g. {cls} {aid}: new={str(nv)[:60]!r}  ref={str(rv)[:60]!r}")
    return clean


def main() -> int:
    if len(sys.argv) != 3:
        sys.exit("usage: fb_scrape_diff.py <new_csv> <reference_csv>")
    new_rows, ref_rows = load(sys.argv[1]), load(sys.argv[2])
    v23 = has_v23(new_rows) and has_v23(ref_rows)
    new, ref = by_page_ad(new_rows), by_page_ad(ref_rows)

    print(f"NEW : {sys.argv[1]}  ({len(new_rows)} rows, {len(new)} page(s))")
    print(f"REF : {sys.argv[2]}  ({len(ref_rows)} rows, {len(ref)} page(s))")
    print(f"MODE: {'v2.3 row-grain (versions checked)' if v23 else 'ad-grain (a file lacks v2.3 columns)'}")
    print("=" * 64)

    total_ref = total_matched = 0
    all_clean = True
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
            all_clean = False
            continue
        recall = len(matched) / len(ref_ads) * 100 if ref_ads else 0
        print(f"\n● page {page_id} ({pname})")
        print(f"    ref ads={len(ref_ads)}  new ads={len(new_ads)}  "
              f"matched={len(matched)}  missing={len(missing)}  recall={recall:.0f}%")
        if missing:
            all_clean = False
            print(f"    missing ad_ids (first 5): {sorted(missing)[:5]}")
        pairs = [(ref_ads[a], new_ads[a]) for a in sorted(matched)]
        if not field_report(pairs, AD_FIELDS):
            all_clean = False

    # ── version-grain check (only when both files speak v2.3) ──
    if v23:
        print("\n" + "=" * 64)
        print("VERSION-GRAIN CHECK (multi-version ads, matched on both sides)")
        ref_v, new_v = version_rows(ref_rows), version_rows(new_rows)
        # an ad is multi-version if it has >1 distinct version row in the reference
        ref_ad_vcount = defaultdict(int)
        for (aid, _vk) in ref_v:
            ref_ad_vcount[aid] += 1
        ref_multi_ads = {aid for aid, c in ref_ad_vcount.items() if c > 1}
        matched_ads = {aid for (aid, _) in ref_v} & {aid for (aid, _) in new_v}
        multi_matched = ref_multi_ads & matched_ads
        if not ref_multi_ads:
            print("  (reference has no multi-version ads — nothing to check)")
        else:
            vkeys_ref = {k for k in ref_v if k[0] in multi_matched}
            vkeys_new = {k for k in new_v if k[0] in multi_matched}
            vmissing = vkeys_ref - vkeys_new
            print(f"  multi-version ads in ref: {len(ref_multi_ads)} "
                  f"(matched in new: {len(multi_matched)})")
            print(f"  version rows: ref={len(vkeys_ref)}  new(matching ads)={len(vkeys_new)}  "
                  f"missing={len(vmissing)}")
            if vmissing:
                all_clean = False
                print(f"  missing (ad, version) keys (first 5): {sorted(vmissing)[:5]}")
            vpairs = [(ref_v[k], new_v[k]) for k in sorted(vkeys_ref & vkeys_new)]
            if vpairs and not field_report(vpairs, VERSION_FIELDS, indent="    "):
                all_clean = False

    extra = set().union(*[set(v) for v in new.values()], set()) \
        - set().union(*[set(v) for v in ref.values()], set())
    print("\n" + "=" * 64)
    overall = total_matched / total_ref * 100 if total_ref else 0
    print(f"OVERALL recall (ads in ref also found by new): "
          f"{total_matched}/{total_ref} = {overall:.0f}%")
    print(f"Extra ads in new (not in ref — likely new launches): {len(extra)}")
    print(f"\nVERDICT: {'CLEAN — zero MISS / zero mismatch on the overlap' if all_clean else 'NOT CLEAN — fix every MISS/mismatch above (richer is OK)'}")
    print("How to read: 'richer' = new scraper filled a field the reference left "
          "blank (fine). 'MISS' = reference had data the new scraper lost (never "
          "OK). 'mismatch' = both filled but different (investigate; same-day "
          "scrapes should agree). A page 'NOT in new scrape' is a mapping gap.")
    return 0 if all_clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
