#!/usr/bin/env python3
"""
fb_scrape.py — EXPERIMENTAL terminal Facebook Ad Library scraper (Playwright).

A first-cut port of the Claude-in-Chrome `scraper_prompt.md` flow to a single
terminal command. Reuses the same competitor→page mapping, the same navigate URL,
and the same lazy-scroll logic. It captures the RELIABLE metadata (ad_library_id,
rank, dates, media type, counts, page) — enough for the rank/analysis pipeline and
for Step 2 (download re-resolves fresh CDN URLs anyway, so the at-scrape CDN columns
are intentionally left blank in this first cut).

⚠️ Validate before trusting: run this, then `fb_scrape_diff.py` against a known
Claude-in-Chrome CSV for the same competitor to measure data loss.

Runs on YOUR Mac (visible browser). Setup:
    pip3.13 install --user --break-system-packages playwright
    python3.13 -m playwright install chromium

Usage:
    python3.13 facebook/scripts/fb_scrape.py "Duolingo"
    python3.13 facebook/scripts/fb_scrape.py "Duolingo" --headless --out facebook/inputs
"""
import argparse
import csv
import datetime
import re
import sys
import time

# competitor → [{page_id, page_name}] — copied verbatim from scraper_prompt.md Step 1
COMPETITOR_PAGES = {
    "MySivi": [
        {"page_id": "974103675777955", "page_name": "MySivi Spoken English App"},
        {"page_id": "104392002393583", "page_name": "MySivi"},
        {"page_id": "960932370437481", "page_name": "MySivi - Best English Speaking App"},
        {"page_id": "775663658968839", "page_name": "MySivi - AI English speaking App"},
        {"page_id": "1095436856980624", "page_name": "MySivi App"},
        {"page_id": "942391945633379", "page_name": "MySivi - Learn English in Telugu"},
    ],
    "SpeakX": [
        {"page_id": "540653459131632", "page_name": "SpeakX - Learn to Speak English"},
        {"page_id": "104428871316786", "page_name": "SpeakX English"},
    ],
    "English Seekho": [
        {"page_id": "565574549966663", "page_name": "English Seekho App"},
        {"page_id": "213520808522229", "page_name": "English Seekho"},
    ],
    "Zinglish": [
        {"page_id": "680109015195106", "page_name": "Zinglish"},
        {"page_id": "810112592525384", "page_name": "Zinglish"},
    ],
    "Speak": [{"page_id": "743138162511061", "page_name": "Speak"}],
    "Loora": [
        {"page_id": "105478174979714", "page_name": "Loora"},
        {"page_id": "936721566182539", "page_name": "Loora: AI English Tutor"},
    ],
    "Duolingo": [{"page_id": "141935472517297", "page_name": "Duolingo"}],
    "Busuu": [{"page_id": "18949798807", "page_name": "Busuu"}],
    "Memrise": [{"page_id": "149149908445051", "page_name": "Memrise"}],
    "EnglishBhashi": [{"page_id": "117256651366792", "page_name": "Englishbhashi"}],
    "Multibhashi": [{"page_id": "1704560136456926", "page_name": "Multibhashi"}],
    "Praktika AI": [
        {"page_id": "104781132385804", "page_name": "Praktika"},
        {"page_id": "902151746306097", "page_name": "Praktika - Learn English with AI"},
    ],
    "EWA": [{"page_id": "165004157332215", "page_name": "EWA: Learn Languages"}],
}

NAV_URL = ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
           "&country=IN&is_targeted_country=false&media_type=all&search_type=page"
           "&sort_data[mode]=total_impressions&sort_data[direction]=desc"
           "&view_all_page_id={page_id}")

SCROLL_JS = """
async () => {
  const HARD_CEILING = 500, STABLE_THRESHOLD = 5;
  let stable = 0, last = 0, iter = 0;
  while (stable < STABLE_THRESHOLD && iter < HARD_CEILING) {
    window.scrollTo(0, document.body.scrollHeight);
    await new Promise(r => setTimeout(r, 2500));
    const h = document.body.scrollHeight;
    if (h === last) stable++; else { stable = 0; last = h; }
    iter++;
  }
  return { iterations: iter, finalHeight: last };
}
"""

# Pass-1 metadata extraction — text-anchored on "Library ID:", same approach as
# scraper_prompt.md Step 2d. Returns one object per card (raw strings; parsed below).
EXTRACT_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  const anchors = [...document.querySelectorAll('*')].filter(
    el => el.children.length === 0 && el.textContent
       && el.textContent.trim().startsWith('Library ID:'));
  for (const a of anchors) {
    const card = a.closest('div[role="article"]') || a.closest('div[class*="x1"]');
    if (!card) continue;
    const txt = card.innerText || '';
    const idm = txt.match(/Library ID:\s*([0-9]+)/);
    if (!idm) continue;
    const adId = idm[1];
    if (seen.has(adId)) continue;
    seen.add(adId);

    const started = txt.match(/Started running on\s+([0-9]{1,2}\s+\w+\s+[0-9]{4})/i);
    const ran = txt.match(/Ran from\s+([0-9]{1,2}\s+\w+\s+[0-9]{4})\s+to\s+([0-9]{1,2}\s+\w+\s+[0-9]{4})/i);
    const startRaw = ran ? ran[1] : (started ? started[1] : '');
    const endRaw = ran ? ran[2] : '';

    const vids = card.querySelectorAll('video').length;
    const realImgs = [...card.querySelectorAll('img')].filter(im => {
      const s = im.src || '';
      return s && !s.startsWith('data:') && !s.startsWith('blob:')
          && (s.includes('fbcdn.net') || s.includes('scontent'))
          && (im.naturalWidth || 0) >= 200 && (im.naturalHeight || 0) >= 200;
    }).length;
    let mediaType = vids > 0 ? 'Video' : (realImgs > 0 ? 'Image' : '');
    const creativeCount = Math.max(vids, realImgs, 1);

    const vM = txt.match(/This ad has (\d+) versions/i);
    const versionCount = vM ? vM[1] : '1';
    const hasMultiple = /multiple versions/i.test(txt);
    const lowImp = /low impression/i.test(txt);

    // CTA: a button-like label near the card footer
    let cta = '';
    const btn = card.querySelector('div[role="button"] span, a[role="button"] span');
    if (btn) cta = (btn.innerText || '').trim();

    // destination URL via l.facebook.com/l.php?u=
    let dest = '';
    const lnk = card.querySelector('a[href*="l.facebook.com/l.php"]');
    if (lnk) { try { dest = decodeURIComponent(new URL(lnk.href).searchParams.get('u') || ''); } catch (e) {} }

    // distribution platforms (aria-labels on the platform icons row)
    const plats = [...new Set([...card.querySelectorAll('[aria-label]')]
      .map(e => e.getAttribute('aria-label'))
      .filter(l => ['Facebook','Instagram','Messenger','Audience Network'].includes(l)))].join(', ');

    // primary text: best-effort — longest text block that isn't a known label line
    let primary = '';
    const blocks = txt.split('\n').map(s => s.trim()).filter(Boolean).filter(s =>
      !/^Library ID:/.test(s) && !/^Sponsored$/i.test(s) && !/Started running|Ran from|This ad has|Open Drop-down|See ad details|See summary details/i.test(s)
      && !['Facebook','Instagram','Messenger','Audience Network'].includes(s));
    if (blocks.length) primary = blocks.reduce((a,b)=> b.length>a.length?b:a, '');

    out.push({ adId, startRaw, endRaw, mediaType, creativeCount,
      versionCount, hasMultiple, lowImp, cta, dest, plats, primary });
  }
  return out;
}
"""

HEADER = ["row_rank", "competitor_name", "facebook_page_id", "facebook_page_name",
          "facebook_page_followers", "target_country", "ad_library_id",
          "ad_library_url", "ad_start_date", "ad_end_date",
          "has_low_impression_warning", "ad_has_multiple_versions",
          "ad_version_count", "ad_primary_text", "ad_description", "ad_cta_label",
          "ad_destination_url", "ad_media_type", "ad_distribution_platforms",
          "creative_count_in_ad", "creative_index_in_ad", "creative_aspect_ratio",
          "facebook_video_cdn_url_at_scrape", "facebook_thumbnail_cdn_url_at_scrape",
          "facebook_cdn_url_expiry_at_scrape", "scrape_run_date"]


def iso_date(raw: str) -> str:
    """'5 Feb 2026' -> '2026-02-05'; '' if unparseable."""
    raw = (raw or "").strip()
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("competitor", help="competitor name (must match the mapping)")
    ap.add_argument("--headless", action="store_true", help="run without a visible window")
    ap.add_argument("--out", default="facebook/inputs", help="where to write the CSV")
    args = ap.parse_args()

    # resolve competitor (case-insensitive)
    key = next((k for k in COMPETITOR_PAGES if k.lower() == args.competitor.lower()), None)
    if not key:
        sys.exit(f"[error] unknown competitor '{args.competitor}'. "
                 f"Known: {', '.join(COMPETITOR_PAGES)}")
    pages = COMPETITOR_PAGES[key]
    slug = slugify(key)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Playwright not installed. Run:\n"
                 "  pip3.13 install --user --break-system-packages playwright\n"
                 "  python3.13 -m playwright install chromium")

    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%H%M")
    rows = []
    rank = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page()
        for i, pg in enumerate(pages, 1):
            print(f"[page {i}/{len(pages)}] {pg['page_name']} ({pg['page_id']}) — loading…")
            page.goto(NAV_URL.format(page_id=pg["page_id"]),
                      wait_until="domcontentloaded", timeout=90000)
            for label in ("Allow all cookies", "Accept all", "Only allow essential cookies"):
                try:
                    page.get_by_role("button", name=label).click(timeout=2500); break
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(4)
            body = (page.inner_text("body")[:4000]).lower()
            if any(w in body for w in ("log in to continue", "you must log in", "checkpoint")):
                print("  [abort] login/checkpoint wall — Meta blocked the session.")
                browser.close()
                return 2
            print("  scrolling to load all ads…")
            sc = page.evaluate(SCROLL_JS)
            print(f"  scroll done ({sc['iterations']} cycles). extracting…")
            cards = page.evaluate(EXTRACT_JS)
            print(f"  {len(cards)} ad(s) on this page.")
            for c in cards:
                rank += 1
                rows.append({
                    "row_rank": rank, "competitor_name": key,
                    "facebook_page_id": pg["page_id"], "facebook_page_name": pg["page_name"],
                    "facebook_page_followers": "", "target_country": "IN",
                    "ad_library_id": c["adId"],
                    "ad_library_url": f"https://www.facebook.com/ads/library/?id={c['adId']}",
                    "ad_start_date": iso_date(c["startRaw"]), "ad_end_date": iso_date(c["endRaw"]),
                    "has_low_impression_warning": str(bool(c["lowImp"])).upper(),
                    "ad_has_multiple_versions": str(bool(c["hasMultiple"])).upper(),
                    "ad_version_count": c["versionCount"],
                    "ad_primary_text": c["primary"], "ad_description": "",
                    "ad_cta_label": c["cta"], "ad_destination_url": c["dest"],
                    "ad_media_type": c["mediaType"],
                    "ad_distribution_platforms": c["plats"],
                    "creative_count_in_ad": c["creativeCount"], "creative_index_in_ad": 0,
                    "creative_aspect_ratio": "",
                    "facebook_video_cdn_url_at_scrape": "",
                    "facebook_thumbnail_cdn_url_at_scrape": "",
                    "facebook_cdn_url_expiry_at_scrape": "", "scrape_run_date": today,
                })
        browser.close()

    import os
    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, f"fb-ads-{slug}-{today}-{now}.csv")
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    print(f"\n✅ {len(rows)} ads → {out_path}")
    print(f"   Validate it:  python3.13 facebook/scripts/fb_scrape_diff.py "
          f"{out_path} facebook/inputs/fb-ads-{slug}-<existing-date>.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
