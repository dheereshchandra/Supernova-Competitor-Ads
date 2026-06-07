#!/usr/bin/env python3
"""
fb_scrape.py — EXPERIMENTAL terminal Facebook Ad Library scraper (Playwright).

Ports the Claude-in-Chrome `scraper_prompt.md` flow to one terminal command:
reuses the competitor→page mapping, the navigate URL, the lazy-scroll, AND the
Pass-2 hover interaction (so media type + CDN URLs load). Writes the standard
input-CSV schema.

⚠️ Validate before trusting: run this, then `fb_scrape_diff.py` against a known
Claude-in-Chrome CSV for the same competitor.

Setup (your Mac):
    pip3.13 install --user --break-system-packages playwright
    python3.13 -m playwright install chromium

Usage:
    python3.13 facebook/scripts/fb_scrape.py "Duolingo"
    python3.13 facebook/scripts/fb_scrape.py "Duolingo" --headless --debug
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys
import time

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
  return { iterations: iter };
}
"""

# Per-card: walk up to the FULL ad card (largest ancestor still holding exactly one
# "Library ID"), hover to load media, then extract metadata + media + CDN URLs.
EXTRACT_JS = r"""
async () => {
  const isIdLeaf = el => el.children.length === 0 && el.textContent
      && el.textContent.trim().startsWith('Library ID:');
  const countIds = el => [...el.querySelectorAll('*')].filter(isIdLeaf).length;

  const cleanJsonUrl = s => s.replace(/\\\//g,'/').replace(/\\u0026/g,'&').replace(/\\u0025/g,'%');
  const decodeExpiry = url => {
    if (!url) return '';
    const m = url.match(/[?&]oe=([0-9a-fA-F]+)/);
    if (m) { const ts = parseInt(m[1],16); if (ts>1e9 && ts<1e10) return new Date(ts*1000).toISOString(); }
    return '';
  };
  const computeAspect = (w,h) => {
    if (!w||!h) return '';
    if (Math.abs(w/h-9/16)<0.05) return '9:16';
    if (Math.abs(w/h-1)<0.05) return '1:1';
    if (Math.abs(w/h-16/9)<0.05) return '16:9';
    if (Math.abs(w/h-4/5)<0.05) return '4:5';
    return w+'x'+h;
  };

  const anchors = [...document.querySelectorAll('*')].filter(isIdLeaf);
  const out = [], seen = new Set();
  for (const a of anchors) {
    // climb to the largest container that still holds just THIS one Library ID
    let card = a;
    while (card.parentElement && countIds(card.parentElement) === 1) card = card.parentElement;

    const idm = (card.innerText || '').match(/Library ID:\s*([0-9]+)/);
    if (!idm) continue;
    const adId = idm[1];
    if (seen.has(adId)) continue;
    seen.add(adId);

    card.scrollIntoView({ block: 'center' });
    await new Promise(r => setTimeout(r, 350));
    card.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
    await new Promise(r => setTimeout(r, 800));

    const txt = card.innerText || '';
    const html = card.outerHTML;
    const findInJson = keys => { for (const k of keys) { const m = html.match(new RegExp('"'+k+'":"([^"]+)"')); if (m) return cleanJsonUrl(m[1]); } return ''; };

    const started = txt.match(/Started running on\s+([0-9]{1,2}\s+\w+,?\s+[0-9]{4})/i);
    const ran = txt.match(/Ran from\s+([0-9]{1,2}\s+\w+,?\s+[0-9]{4})\s+to\s+([0-9]{1,2}\s+\w+,?\s+[0-9]{4})/i);

    const vidEls = [...card.querySelectorAll('video')];
    const realImgs = [...card.querySelectorAll('img')].filter(im => {
      const s = im.src || '';
      return s && !s.startsWith('data:') && !s.startsWith('blob:')
          && (s.includes('fbcdn.net') || s.includes('scontent'))
          && (im.naturalWidth||0) >= 200 && (im.naturalHeight||0) >= 200;
    });
    let mediaType = vidEls.length > 0 ? 'Video' : (realImgs.length > 0 ? 'Image' : '');
    const creativeCount = Math.max(vidEls.length, realImgs.length, 1);

    let videoUrl = '';
    if (vidEls[0]) videoUrl = (vidEls[0].src && !vidEls[0].src.startsWith('blob:')) ? vidEls[0].src
        : (vidEls[0].querySelector('source')?.src || '');
    if (!videoUrl || videoUrl.startsWith('blob:')) videoUrl = findInJson(['playable_url_quality_hd','playable_url']);
    const thumbUrl = (realImgs[0] && realImgs[0].src) || findInJson(['preferred_thumbnail','image_url','original_image_url','resized_image_url']);
    const aspect = realImgs[0] ? computeAspect(realImgs[0].naturalWidth, realImgs[0].naturalHeight) : '';
    const expiry = decodeExpiry(videoUrl) || decodeExpiry(thumbUrl);

    const vM = txt.match(/This ad has (\d+) versions/i);
    let cta = ''; const btn = card.querySelector('div[role="button"] span, a[role="button"] span'); if (btn) cta = (btn.innerText||'').trim();
    let dest = ''; const lnk = card.querySelector('a[href*="l.facebook.com/l.php"]'); if (lnk) { try { dest = decodeURIComponent(new URL(lnk.href).searchParams.get('u')||''); } catch(e){} }
    const plats = [...new Set([...card.querySelectorAll('[aria-label]')].map(e=>e.getAttribute('aria-label')).filter(l=>['Facebook','Instagram','Messenger','Audience Network'].includes(l)))].join(', ');

    const blocks = txt.split('\n').map(s=>s.trim()).filter(Boolean).filter(s =>
      !/^Library ID:/.test(s) && !/^Sponsored$/i.test(s)
      && !/Started running|Ran from|This ad has|See ad details|See summary details|Open Drop-down/i.test(s)
      && !['Facebook','Instagram','Messenger','Audience Network','Active','Inactive'].includes(s));
    const primary = blocks.length ? blocks.reduce((x,y)=> y.length>x.length?y:x, '') : '';

    out.push({ adId,
      startRaw: ran ? ran[1] : (started ? started[1] : ''), endRaw: ran ? ran[2] : '',
      mediaType, creativeCount, versionCount: vM ? vM[1] : '1',
      hasMultiple: /multiple versions/i.test(txt), lowImp: /low impression/i.test(txt),
      cta, dest, plats, primary, videoUrl, thumbUrl, aspect, expiry });
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
    raw = (raw or "").strip().replace(",", "")
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
    ap.add_argument("competitor")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--out", default="facebook/inputs")
    ap.add_argument("--debug", action="store_true",
                    help="dump the first card's HTML to fb_card_debug.html for inspection")
    args = ap.parse_args()

    key = next((k for k in COMPETITOR_PAGES if k.lower() == args.competitor.lower()), None)
    if not key:
        sys.exit(f"[error] unknown competitor '{args.competitor}'. Known: {', '.join(COMPETITOR_PAGES)}")
    pages = COMPETITOR_PAGES[key]
    slug = slugify(key)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Playwright not installed:\n  pip3.13 install --user --break-system-packages playwright\n"
                 "  python3.13 -m playwright install chromium")

    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%H%M")
    rows, rank = [], 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        for i, pg in enumerate(pages, 1):
            print(f"[page {i}/{len(pages)}] {pg['page_name']} ({pg['page_id']}) — loading…")
            page.goto(NAV_URL.format(page_id=pg["page_id"]), wait_until="domcontentloaded", timeout=90000)
            for label in ("Allow all cookies", "Accept all", "Only allow essential cookies"):
                try:
                    page.get_by_role("button", name=label).click(timeout=2500); break
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(4)
            body = page.inner_text("body")[:4000].lower()
            if any(w in body for w in ("log in to continue", "you must log in", "checkpoint")):
                print("  [abort] login/checkpoint wall."); browser.close(); return 2
            followers = ""
            fm = re.search(r"([\d,.]+[KMB]?)\s*(?:followers|likes)", body, re.I)
            if fm:
                followers = fm.group(1)
            print("  scrolling…")
            sc = page.evaluate(SCROLL_JS)
            print(f"  scroll done ({sc['iterations']} cycles). extracting (with hover — slower)…")
            cards = page.evaluate(EXTRACT_JS)
            print(f"  {len(cards)} ad(s).")
            if args.debug and cards:
                html = page.evaluate(
                    "() => { const a=[...document.querySelectorAll('*')].find(e=>e.children.length===0 && (e.textContent||'').trim().startsWith('Library ID:'));"
                    " let c=a; while(c.parentElement && [...c.parentElement.querySelectorAll('*')].filter(x=>x.children.length===0 && (x.textContent||'').trim().startsWith('Library ID:')).length===1) c=c.parentElement; return c.outerHTML; }")
                open("fb_card_debug.html", "w", encoding="utf-8").write(html)
                print("  [debug] first card HTML → fb_card_debug.html")
            for c in cards:
                rank += 1
                rows.append({
                    "row_rank": rank, "competitor_name": key,
                    "facebook_page_id": pg["page_id"], "facebook_page_name": pg["page_name"],
                    "facebook_page_followers": followers, "target_country": "IN",
                    "ad_library_id": c["adId"],
                    "ad_library_url": f"https://www.facebook.com/ads/library/?id={c['adId']}",
                    "ad_start_date": iso_date(c["startRaw"]), "ad_end_date": iso_date(c["endRaw"]),
                    "has_low_impression_warning": str(bool(c["lowImp"])).upper(),
                    "ad_has_multiple_versions": str(bool(c["hasMultiple"])).upper(),
                    "ad_version_count": c["versionCount"], "ad_primary_text": c["primary"],
                    "ad_description": "", "ad_cta_label": c["cta"],
                    "ad_destination_url": c["dest"], "ad_media_type": c["mediaType"],
                    "ad_distribution_platforms": c["plats"],
                    "creative_count_in_ad": c["creativeCount"], "creative_index_in_ad": 0,
                    "creative_aspect_ratio": c["aspect"],
                    "facebook_video_cdn_url_at_scrape": c["videoUrl"],
                    "facebook_thumbnail_cdn_url_at_scrape": c["thumbUrl"],
                    "facebook_cdn_url_expiry_at_scrape": c["expiry"], "scrape_run_date": today,
                })
        browser.close()

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, f"fb-ads-{slug}-{today}-{now}.csv")
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    # quick fill-rate so you can see at a glance what came through
    def filled(col):
        return sum(1 for r in rows if (r[col] or "").strip())
    print(f"\n✅ {len(rows)} ads → {out_path}")
    print(f"   fill rates: media_type {filled('ad_media_type')}/{len(rows)} · "
          f"start_date {filled('ad_start_date')}/{len(rows)} · "
          f"primary_text {filled('ad_primary_text')}/{len(rows)} · "
          f"video_url {filled('facebook_video_cdn_url_at_scrape')}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
