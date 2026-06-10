#!/usr/bin/env python3
"""
fb_scrape_v2.py — EXPERIMENTAL terminal Facebook Ad Library scraper, V2
(structured-payload interception). Emits the full 36-column v2.3 schema,
including per-version rows.

🧪 STATUS: BENCH (parallel-run) — the production FB scrape remains
Claude-in-Chrome (`scraper_prompt.md` v2.3). Protocol for the next days:
run BOTH for the same competitor on the same day, then

    python3.13 facebook/scripts/fb_scrape_diff.py <v2_csv> <claude_csv>

and fix every real mismatch. Cut over per-competitor only on a clean diff
(operator's bar: every field matches, zero misses).

WHY V2 / how it differs from the PAUSED fb_scrape.py (v1, DOM-based):
v1 parsed the *rendered* DOM (regex on date text, "longest block" for primary
text, hover to load media) and was paused 2026-06-07 with real field misses.
V2 drives the same listing URL with Playwright but reads the STRUCTURED JSON
the page itself receives — the server-embedded first result batch plus every
`AdLibrarySearchPaginationQuery` XHR (captured via page.on("response")).
Each search edge is a *collation*; its `collated_results[]` are the ad's
VERSIONS, each a complete node (own ad_archive_id, own unix start/end dates,
body/title/cta/link/platforms and own media URLs). So the v2.3 "Pass 3"
(detail-view click-walk, the part that makes Claude-in-Chrome runs take
10-24 h) collapses into data that arrives with the listing. Probe evidence +
full field map: SESSION-HANDOFF.md ("terminal Facebook scraper — V2").

Known, deliberate mapping decisions (validate during the bench window):
  * DATE_TZ / DATE_SHIFT_DAYS: card dates are unix timestamps at MIDNIGHT
    US-Pacific. The 2026-06-10 same-day MySivi bench (5 ads spanning both PST
    and PDT) showed Meta's "Started running on" label — what a Claude-in-Chrome
    scrape reads — is consistently the day BEFORE that Pacific midnight, in both
    DST regimes. So we floor to the Pacific date and shift one day back to match
    the reference. Both knobs are one line; re-validate as more same-day diffs
    land.
  * ad_end_date is blank while the ad is active (Claude semantics), even
    though the payload carries a rolling end_date for active ads.
  * DCO ads: the payload exposes ALL card variants; the rendered card (what
    Claude scrapes) shows ONE. Default --dco-mode card mimics Claude
    (creative 0 only); --dco-mode full emits every variant (richer, but will
    show as creative_count diffs vs Claude).
  * version_id: blank for single-version ads (prompt spec); for multi-version
    ads V2 fills the member's own ad_archive_id (the version's real,
    deeplinkable identifier — Claude usually finds none in the UI).
  * has_low_impression_warning comes from the card badge text via one
    zero-click DOM pass (same source Claude reads); the payload candidates
    (impressions_with_index / gated_type / fev_info) are recorded in the
    debug sidecar until we learn the payload mapping.
  * creative_aspect_ratio is computed from the creative's preview-image
    dimensions (small ranged fetch + Pillow) — covers version creatives the
    DOM never renders. --no-aspect skips the fetches.
  * row_rank increments per ROW (matches §6.3 and every historical CSV);
    page_rank increments per AD within its page (prompt Step 2f).

Setup (one-time, on your Mac — NOT the Cowork sandbox):
    python3.13 -m pip install --user --break-system-packages playwright requests Pillow
    python3.13 -m playwright install chromium

Usage:
    python3.13 facebook/scripts/fb_scrape_v2.py "Duolingo"
    python3.13 facebook/scripts/fb_scrape_v2.py "MySivi" --debug
    python3.13 facebook/scripts/fb_scrape_v2.py "MySivi" --pages 1 --headed

Output: facebook/inputs/fb-ads-{slug}-{YYYY-MM-DD}-{HHMM}-v2.csv
(timestamped + "-v2" so it never collides with the Claude-in-Chrome file
fb-ads-{slug}-{YYYY-MM-DD}.csv during the parallel-run window).

Exit codes: 0 ok · 2 login/checkpoint wall (partial CSV saved) ·
3 audit FAIL (CSV saved with -AUDITFAIL suffix; do NOT ingest) ·
4 3+ consecutive page failures (throttling suspected).
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys
import time
import zoneinfo
from collections import OrderedDict

SCRIPT_VERSION = "v2.0-payload-2026-06-10"

# Meta renders "Started running on …" in US-Pacific regardless of browser TZ.
# v1's off-by-one-day bug was converting in the wrong zone. Bench-validated knob.
DATE_TZ = zoneinfo.ZoneInfo("America/Los_Angeles")
DATE_SHIFT_DAYS = -1  # see DATE_TZ note in the module docstring (bench-calibrated)

# ── competitor → page mapping (kept in lockstep with scraper_prompt.md v2.3) ──
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
    "EnglishBolo": [
        {"page_id": "313529161993416", "page_name": "Englishbolo"},
        {"page_id": "1611615522438426", "page_name": "English Bolo"},
        {"page_id": "777222062151804", "page_name": "English BoLo"},
        {"page_id": "1007859149343323", "page_name": "EnglishBolo"},
        {"page_id": "808919705639211", "page_name": "englishboloji"},
        {"page_id": "104669312291031", "page_name": "English bolo mere sath 4"},
        {"page_id": "101921357862790", "page_name": "English bolo mere sath 3"},
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
  return { iterations: iter, hitCeiling: iter >= HARD_CEILING };
}
"""

# Zero-click DOM pass: map each card's Library ID → "low impression" badge bool.
# Same text source Claude-in-Chrome reads (page is pinned to English).
BADGE_JS = r"""
() => {
  const isIdLeaf = el => el.children.length === 0 && el.textContent
      && el.textContent.trim().startsWith('Library ID:');
  const countIds = el => [...el.querySelectorAll('*')].filter(isIdLeaf).length;
  const out = {};
  for (const a of [...document.querySelectorAll('*')].filter(isIdLeaf)) {
    let card = a;
    while (card.parentElement && countIds(card.parentElement) === 1) card = card.parentElement;
    const m = (card.innerText || '').match(/Library ID:\s*([0-9]+)/);
    if (m) out[m[1]] = /low impression/i.test(card.innerText || '');
  }
  return out;
}
"""

CSV_HEADER = [
    "row_rank", "page_rank", "competitor_name", "facebook_page_id",
    "facebook_page_name", "facebook_page_followers", "target_country",
    "ad_library_id", "ad_library_url", "ad_start_date", "ad_end_date",
    "has_low_impression_warning", "ad_has_multiple_versions", "ad_version_count",
    "version_index", "version_id", "version_start_date", "version_end_date",
    "version_primary_text", "version_description", "version_cta_label",
    "version_destination_url", "version_platforms_distribution",
    "ad_primary_text", "ad_description", "ad_cta_label", "ad_destination_url",
    "ad_media_type", "ad_distribution_platforms", "creative_count_in_ad",
    "creative_index_in_ad", "creative_aspect_ratio",
    "facebook_video_cdn_url_at_scrape", "facebook_thumbnail_cdn_url_at_scrape",
    "facebook_cdn_url_expiry_at_scrape", "scrape_run_date",
]

PLATFORM_LABEL = {
    "FACEBOOK": "Facebook", "INSTAGRAM": "Instagram", "MESSENGER": "Messenger",
    "AUDIENCE_NETWORK": "Audience Network", "THREADS": "Threads",
}

TEMPLATE_RE = re.compile(r"\{\{.+?\}\}")  # DCO placeholder text e.g. {{product.brand}}


# ───────────────────────────── payload plumbing ─────────────────────────────

def parse_json_blobs(text):
    """Meta's GraphQL bodies are one-or-more JSON objects on separate lines."""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("{") or line.startswith("["):
            try:
                yield json.loads(line)
            except Exception:  # noqa: BLE001
                continue


def embedded_json_blobs(html):
    for m in re.finditer(r'<script type="application/json"[^>]*>(.*?)</script>', html, re.S):
        try:
            yield json.loads(m.group(1))
        except Exception:  # noqa: BLE001
            continue


def find_ad_nodes(obj, out):
    """Collect every ad node (anything carrying an ad_archive_id). Each node is
    one ad VERSION; nodes that share a collation_id are versions of the SAME ad.

    Meta is inconsistent about how it ships an ad's versions: sometimes nested in
    a node's collated_results[], and sometimes (the MySivi pages, 2026-06-10) as
    SEPARATE top-level search results that each carry only their own collation_id
    with an empty collated_results. Gathering every node here and grouping by
    collation_id in collations_from_sources() handles both shapes; the old code
    only read collated_results[] and so split scattered versions into separate
    single-version 'ads'."""
    if isinstance(obj, dict):
        if obj.get("ad_archive_id"):
            out.append(obj)
            cr = obj.get("collated_results")          # nested siblings, when present
            if isinstance(cr, list):
                for v in cr:
                    find_ad_nodes(v, out)
            return                                     # don't descend this node's other fields
        for v in obj.values():
            find_ad_nodes(v, out)
    elif isinstance(obj, list):
        for v in obj:
            find_ad_nodes(v, out)


def collations_from_sources(html, xhr_bodies):
    """Ordered list of collations (one per ad), each a list of version-member
    nodes. Nodes are gathered from the embedded first batch (impression order)
    then the scroll XHRs (arrival order), then GROUPED BY collation_id — the
    field every version of one ad shares.

    First-seen order is impression order, so members[0] is the lead / version-0:
    the single card Meta renders in the grid (the highest-impression member),
    which is exactly the baseline a Claude-in-Chrome scrape captures. Later
    members are versions 1..n. Within a collation, dedup by ad_archive_id (a node
    recurs across scroll batches). Ads with no collation_id fall back to a solo
    group keyed on their own id."""
    nodes = []
    for ob in embedded_json_blobs(html):
        find_ad_nodes(ob, nodes)
    for body in xhr_bodies:
        for ob in parse_json_blobs(body):
            find_ad_nodes(ob, nodes)
    groups = OrderedDict()
    for n in nodes:
        aid = str(n.get("ad_archive_id") or "")
        if not aid:
            continue
        cid = str(n.get("collation_id") or "").strip() or f"solo:{aid}"
        groups.setdefault(cid, OrderedDict()).setdefault(aid, n)
    return [list(bucket.values()) for bucket in groups.values()]


# ───────────────────────────── field mapping ─────────────────────────────

def unix_to_date(ts):
    if not isinstance(ts, (int, float)) or not ts:
        return ""
    d = datetime.datetime.fromtimestamp(ts, tz=DATE_TZ).date()
    return (d + datetime.timedelta(days=DATE_SHIFT_DAYS)).isoformat()


def decode_expiry(url):
    if not url:
        return ""
    m = re.search(r"[?&]oe=([0-9a-fA-F]+)", url)
    if m:
        ts = int(m.group(1), 16)
        if 1e9 < ts < 1e10:
            return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc) \
                .isoformat().replace("+00:00", ".000Z").replace(".000.000Z", ".000Z")
    return ""


def platforms_str(node):
    plats = node.get("publisher_platform") or []
    return ",".join(PLATFORM_LABEL.get(p, p.replace("_", " ").title()) for p in plats)


def text_fields(snapshot):
    """(primary_text, description, cta_label, destination_url) for one version.
    DCO template placeholders ({{product.name}}) fall back to the first card's
    real per-variant text — that's what the rendered card (and Claude) shows."""
    body = ((snapshot.get("body") or {}).get("text")) or ""
    title = snapshot.get("title") or ""
    link_desc = snapshot.get("link_description") or ""
    cta = snapshot.get("cta_text") or ""
    dest = snapshot.get("link_url") or ""
    cards = snapshot.get("cards") or []
    c0 = cards[0] if cards else {}
    if TEMPLATE_RE.search(body) and c0.get("body"):
        body = c0["body"]
    desc = title if title else link_desc
    if TEMPLATE_RE.search(desc):
        alt = c0.get("title") or c0.get("link_description") or ""
        if alt and not TEMPLATE_RE.search(alt):
            desc = alt
    if not dest and c0.get("link_url"):
        dest = c0["link_url"]
    if not cta and c0.get("cta_text"):
        cta = c0["cta_text"]
    return body, desc, cta, dest


def creatives_of(snapshot, display_format, dco_mode):
    """List of per-creative dicts: {kind, video_url, thumb_url}."""
    videos = snapshot.get("videos") or []
    images = snapshot.get("images") or []
    cards = snapshot.get("cards") or []
    out = []
    if videos:
        for v in videos:
            out.append({
                "kind": "video",
                "video_url": v.get("video_hd_url") or v.get("video_sd_url") or "",
                "thumb_url": v.get("video_preview_image_url") or "",
            })
    elif images:
        for i in images:
            out.append({
                "kind": "image",
                "video_url": "",
                "thumb_url": i.get("original_image_url") or i.get("resized_image_url") or "",
            })
    elif cards:
        use = cards if (display_format == "CAROUSEL" or dco_mode == "full") else cards[:1]
        for c in use:
            if c.get("video_hd_url") or c.get("video_sd_url"):
                out.append({
                    "kind": "video",
                    "video_url": c.get("video_hd_url") or c.get("video_sd_url") or "",
                    "thumb_url": c.get("video_preview_image_url") or "",
                })
            else:
                out.append({
                    "kind": "image",
                    "video_url": "",
                    "thumb_url": c.get("original_image_url") or c.get("resized_image_url") or "",
                })
    if not out:
        out = [{"kind": "unknown", "video_url": "", "thumb_url": ""}]
    return out


def media_type_of(display_format, creatives, dco_mode):
    """Claude-compatible label. The rendered card shows DCO ads as a single
    video/image tile, which is what historical CSVs contain — so in the default
    card mode DCO maps by its lead creative; --dco-mode full keeps 'DCO'."""
    if display_format == "VIDEO":
        return "Video"
    if display_format == "IMAGE":
        return "Image"
    if display_format == "CAROUSEL":
        return "Carousel"
    if display_format == "DCO":
        if dco_mode == "full":
            return "DCO"
        return "Video" if creatives and creatives[0]["kind"] == "video" else "Image"
    return (display_format or "").title()


# ───────────────────────── aspect ratio (preview dims) ─────────────────────────

class AspectResolver:
    """creative_aspect_ratio from the preview image's pixel dimensions.
    Small ranged GET per unique URL; Pillow reads dims from partial bytes."""

    def __init__(self, enabled):
        self.enabled = enabled
        self.cache = {}
        self.failures = 0
        if enabled:
            import requests  # noqa: PLC0415  (repo standard dep)
            from PIL import Image  # noqa: PLC0415
            from io import BytesIO  # noqa: PLC0415
            self._requests, self._Image, self._BytesIO = requests, Image, BytesIO

    @staticmethod
    def bucket(w, h):
        if not w or not h:
            return ""
        for name, ratio in (("9:16", 9 / 16), ("1:1", 1.0), ("16:9", 16 / 9), ("4:5", 4 / 5)):
            if abs(w / h - ratio) < 0.05:
                return name
        return f"{w}x{h}"

    def resolve(self, url):
        if not self.enabled or not url:
            return ""
        if url in self.cache:
            return self.cache[url]
        val = ""
        try:
            r = self._requests.get(url, headers={"Range": "bytes=0-131071"}, timeout=10)
            img = self._Image.open(self._BytesIO(r.content))
            val = self.bucket(*img.size)
        except Exception:  # noqa: BLE001
            self.failures += 1
        self.cache[url] = val
        return val


# ───────────────────────────── audit (Step-2g port) ─────────────────────────────

def audit_rows(rows):
    by_type = {"Video": 0, "Image": 0, "Carousel": 0, "DCO": 0, "Other": 0}
    image_rows, blank_image, blank_video, blank_carousel = [], [], [], []
    for r in rows:
        t = r["ad_media_type"] if r["ad_media_type"] in by_type else "Other"
        by_type[t] += 1
        if t == "Image":
            image_rows.append(r)
            if not (r["facebook_thumbnail_cdn_url_at_scrape"] or "").strip():
                blank_image.append(r["ad_library_id"])
        elif t == "Video":
            if not (r["facebook_video_cdn_url_at_scrape"] or "").strip():
                blank_video.append(r["ad_library_id"])
        elif t in ("Carousel", "DCO"):
            if not ((r["facebook_video_cdn_url_at_scrape"] or "").strip()
                    or (r["facebook_thumbnail_cdn_url_at_scrape"] or "").strip()):
                blank_carousel.append(r["ad_library_id"])
    image_cov = 1.0 if not image_rows else (len(image_rows) - len(blank_image)) / len(image_rows)

    by_ad = {}
    index_violations = []
    for r in rows:
        a = by_ad.setdefault(r["ad_library_id"], {"versions": set(), "count": int(r["ad_version_count"] or 0)})
        a["versions"].add(int(r["version_index"]))
        vi, vc = int(r["version_index"]), int(r["ad_version_count"] or 0)
        ci, cc = int(r["creative_index_in_ad"]), int(r["creative_count_in_ad"] or 0)
        if not (vi < vc and ci < cc):
            index_violations.append(r["ad_library_id"])
    version_count_mismatch = [aid for aid, a in by_ad.items() if len(a["versions"]) != a["count"]]
    version_verdict = "PASS" if not index_violations and not version_count_mismatch else "FAIL"
    verdict = "PASS" if image_cov >= 0.90 and version_verdict == "PASS" else "FAIL"
    return {
        "scraper_version": SCRIPT_VERSION,
        "verdict": verdict,
        "total_rows": len(rows),
        "total_ads": len(by_ad),
        "by_type": by_type,
        "image_coverage_pct": round(image_cov * 100, 1),
        "blank_image_count": len(blank_image),
        "blank_image_sample": blank_image[:10],
        "blank_video_count": len(blank_video),
        "blank_video_sample": blank_video[:10],
        "blank_carousel_count": len(blank_carousel),
        "blank_carousel_sample": blank_carousel[:10],
        "version_verdict": version_verdict,
        "version_index_violation_count": len(index_violations),
        "version_index_violation_sample": sorted(set(index_violations))[:10],
        "version_count_mismatch_count": len(version_count_mismatch),
        "version_count_mismatch_sample": version_count_mismatch[:10],
    }


# ───────────────────────────── main scrape ─────────────────────────────

def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("competitor")
    ap.add_argument("--headed", action="store_true", help="visible browser (default headless)")
    ap.add_argument("--out", default="facebook/inputs")
    ap.add_argument("--pages", type=int, default=0, help="limit to first N pages (smoke tests)")
    ap.add_argument("--dco-mode", choices=("card", "full"), default="card",
                    help="DCO ads: 'card' = lead variant only (Claude-equivalent, default); "
                         "'full' = every card variant (richer; diffs vs Claude expected)")
    ap.add_argument("--no-aspect", action="store_true",
                    help="skip preview-image fetches; creative_aspect_ratio left blank")
    ap.add_argument("--debug", action="store_true",
                    help="dump raw payload nodes + low-impression payload candidates to /tmp")
    args = ap.parse_args()

    key = next((k for k in COMPETITOR_PAGES if k.lower() == args.competitor.lower()), None)
    if not key:
        sys.exit(f"[error] unknown competitor '{args.competitor}'. "
                 f"Known: {', '.join(COMPETITOR_PAGES)}")
    pages = COMPETITOR_PAGES[key]
    if args.pages:
        pages = pages[:args.pages]
    slug = slugify(key)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Playwright not installed:\n"
                 "  python3.13 -m pip install --user --break-system-packages playwright\n"
                 "  python3.13 -m playwright install chromium")

    print(f"[{SCRIPT_VERSION}] {key} — {len(pages)} page(s) | dco-mode={args.dco_mode} "
          f"| aspect={'off' if args.no_aspect else 'on'}")

    aspect = AspectResolver(not args.no_aspect)
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%H%M")
    debug_dir = f"/tmp/fb_v2_debug-{slug}-{today}-{now}"
    if args.debug:
        os.makedirs(debug_dir, exist_ok=True)

    rows = []
    page_reports = []
    debug_payload_candidates = []
    row_rank = 0
    consecutive_failures = 0
    aborted = ""

    xhr_bodies = []      # all captured GraphQL bodies (watermarked per phase)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        # IST viewport like a real India browser; Accept-Language pins the UI to
        # English so badge text / header parse reliably. Do NOT use locale="en-IN"
        # (Playwright locale broke card rendering entirely in the 2026-06-07 runs).
        ctx = browser.new_context(viewport={"width": 1400, "height": 1000},
                                  timezone_id="Asia/Kolkata",
                                  extra_http_headers={"Accept-Language": "en-US,en;q=0.9"})
        pw_page = ctx.new_page()

        def on_response(resp):
            try:
                if "/api/graphql/" not in resp.url:
                    return
                body = resp.text()
                if "ad_archive_id" in body or "collated_results" in body:
                    xhr_bodies.append(body)
            except Exception:  # noqa: BLE001
                pass

        pw_page.on("response", on_response)

        for i, pg in enumerate(pages, 1):
            t0 = time.time()
            print(f"\n[page {i}/{len(pages)}] {pg['page_name']} ({pg['page_id']}) — loading…")
            xhr_start = len(xhr_bodies)
            try:
                pw_page.goto(NAV_URL.format(page_id=pg["page_id"]),
                             wait_until="domcontentloaded", timeout=90000)
            except Exception as e:  # noqa: BLE001
                print(f"  [warn] navigation failed: {e} — skipping page")
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    aborted = "3+ consecutive page failures (Meta throttling?)"
                    break
                continue
            for label in ("Allow all cookies", "Accept all", "Only allow essential cookies",
                          "Decline optional cookies"):
                try:
                    pw_page.get_by_role("button", name=label).click(timeout=2000)
                    break
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(4)

            body_text = pw_page.inner_text("body")[:4000]
            low = body_text.lower()
            if any(w in low for w in ("log in to continue", "you must log in", "checkpoint",
                                      "temporarily blocked")):
                aborted = "login/checkpoint wall"
                print(f"  [ABORT] {aborted} — stopping entire run (per Step 2b rule).")
                break

            followers = ""
            fm = re.search(r"([\d,.]+[KMB]?)\s*(?:followers|likes)", low, re.I)
            if fm:
                followers = fm.group(1)

            print("  scrolling…")
            sc = pw_page.evaluate(SCROLL_JS)
            print(f"  scroll done ({sc['iterations']} cycles"
                  f"{', HIT CEILING' if sc.get('hitCeiling') else ''}). parsing payloads…")
            html = pw_page.content()
            badge_map = {}
            try:
                badge_map = pw_page.evaluate(BADGE_JS)
            except Exception as e:  # noqa: BLE001
                print(f"  [warn] badge DOM pass failed ({e}) — has_low_impression_warning "
                      f"will be false for this page")

            collations = collations_from_sources(html, xhr_bodies[xhr_start:])
            # sanity: payload page_id must match the page we asked for
            matched = [m for m in collations
                       if str((m[0].get("page_id") or (m[0].get("snapshot") or {}).get("page_id")))
                       == pg["page_id"]]
            if collations and not matched:
                seen_ids = {str(m[0].get("page_id")) for m in collations}
                print(f"  [warn] page_id mismatch (payload says {seen_ids}) — skipping page")
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    aborted = "3+ consecutive page failures (Meta throttling?)"
                    break
                continue
            collations = matched
            if not collations:
                print("  [warn] 0 ads found — skipping page (header may not match, or page empty)")
                consecutive_failures += 1
                page_reports.append({"page": pg["page_name"], "ads": 0, "rows": 0,
                                     "multi_version": 0, "secs": round(time.time() - t0)})
                if consecutive_failures >= 3:
                    aborted = "3+ consecutive page failures (Meta throttling?)"
                    break
                continue
            consecutive_failures = 0

            # ── enumerate: ad (collation) → versions (members) → creatives ──
            page_ad_rank = 0
            n_multi = 0
            truncation_fixups = []
            for members in collations:
                lead = members[0]
                coll_count = 0
                for m in members:
                    try:
                        coll_count = max(coll_count, int(m.get("collation_count") or 0))
                    except (TypeError, ValueError):
                        pass
                if coll_count > len(members):
                    truncation_fixups.append((lead, coll_count, len(members)))
                if len(members) > 1:
                    n_multi += 1

                page_ad_rank += 1
                ad_id = str(lead["ad_archive_id"])
                lead_snap = lead.get("snapshot") or {}
                lead_creatives = creatives_of(lead_snap, lead_snap.get("display_format"),
                                              args.dco_mode)
                ad_media = media_type_of(lead_snap.get("display_format"), lead_creatives,
                                         args.dco_mode)
                ad_primary, ad_desc, ad_cta, ad_dest = text_fields(lead_snap)
                ad_plats = platforms_str(lead)
                ad_start = unix_to_date(lead.get("start_date"))
                ad_end = "" if lead.get("is_active") else unix_to_date(lead.get("end_date"))
                low_imp = bool(badge_map.get(ad_id, False))

                if args.debug:
                    debug_payload_candidates.append({
                        "ad_library_id": ad_id, "badge_low_impression": low_imp,
                        "impressions_with_index": lead.get("impressions_with_index"),
                        "gated_type": lead.get("gated_type"),
                        "fev_info": lead.get("fev_info"),
                        "hide_data_status": lead.get("hide_data_status"),
                        "is_aaa_eligible": lead.get("is_aaa_eligible"),
                        "page_like_count": lead_snap.get("page_like_count"),
                    })

                n_versions = len(members)
                for vi, member in enumerate(members):
                    snap = member.get("snapshot") or {}
                    v_primary, v_desc, v_cta, v_dest = text_fields(snap)
                    v_creatives = creatives_of(snap, snap.get("display_format"), args.dco_mode)
                    v_start = unix_to_date(member.get("start_date"))
                    v_end = "" if member.get("is_active") else unix_to_date(member.get("end_date"))
                    v_id = "" if n_versions == 1 else str(member.get("ad_archive_id") or "")
                    v_plats = platforms_str(member)
                    cc = len(v_creatives)
                    for ci, cr in enumerate(v_creatives):
                        assert ci < cc and vi < n_versions, \
                            f"index invariant broken for ad {ad_id} (vi={vi} ci={ci})"
                        row_rank += 1
                        rows.append({
                            "row_rank": row_rank,
                            "page_rank": page_ad_rank,
                            "competitor_name": key,
                            "facebook_page_id": pg["page_id"],
                            "facebook_page_name": pg["page_name"],
                            "facebook_page_followers": followers,
                            "target_country": "IN",
                            "ad_library_id": ad_id,
                            "ad_library_url": f"https://www.facebook.com/ads/library/?id={ad_id}",
                            "ad_start_date": ad_start,
                            "ad_end_date": ad_end,
                            "has_low_impression_warning": str(low_imp).lower(),
                            "ad_has_multiple_versions": str(n_versions > 1).lower(),
                            "ad_version_count": n_versions,
                            "version_index": vi,
                            "version_id": v_id,
                            "version_start_date": v_start,
                            "version_end_date": v_end,
                            "version_primary_text": v_primary,
                            "version_description": v_desc,
                            "version_cta_label": v_cta,
                            "version_destination_url": v_dest,
                            "version_platforms_distribution": v_plats,
                            "ad_primary_text": ad_primary,
                            "ad_description": ad_desc,
                            "ad_cta_label": ad_cta,
                            "ad_destination_url": ad_dest,
                            "ad_media_type": ad_media,
                            "ad_distribution_platforms": ad_plats,
                            "creative_count_in_ad": cc,
                            "creative_index_in_ad": ci,
                            "creative_aspect_ratio": aspect.resolve(cr["thumb_url"]),
                            "facebook_video_cdn_url_at_scrape": cr["video_url"],
                            "facebook_thumbnail_cdn_url_at_scrape": cr["thumb_url"],
                            "facebook_cdn_url_expiry_at_scrape":
                                decode_expiry(cr["video_url"]) or decode_expiry(cr["thumb_url"]),
                            "scrape_run_date": today,
                        })

            if truncation_fixups:
                print(f"  [note] {len(truncation_fixups)} ad(s) report more versions than the "
                      f"payload carried (collation_count > members) — recorded for the bench: "
                      + ", ".join(f"{str(l['ad_archive_id'])}({got}/{want})"
                                  for l, want, got in truncation_fixups[:5]))

            page_rows = sum(1 for r in rows if r["facebook_page_id"] == pg["page_id"])
            secs = round(time.time() - t0)
            page_reports.append({"page": pg["page_name"], "ads": page_ad_rank,
                                 "rows": page_rows, "multi_version": n_multi, "secs": secs,
                                 "version_truncations": len(truncation_fixups)})
            print(f"  page done: {page_ad_rank} ads → {page_rows} rows "
                  f"({n_multi} multi-version) in {secs}s")
            if args.debug:
                with open(f"{debug_dir}/page_{pg['page_id']}_collations.json", "w") as f:
                    json.dump([[m for m in members] for members in collations], f,
                              indent=1, default=str)

        browser.close()

    # ───────────────────────── audit + write ─────────────────────────
    audit = audit_rows(rows) if rows else {"verdict": "FAIL", "total_rows": 0,
                                           "reason": "no rows scraped"}
    audit["aspect_fetch_failures"] = aspect.failures
    print("\n===== AUDIT (Step-2g equivalent) =====")
    print(json.dumps(audit, indent=2))

    suffix = "-v2"
    exit_code = 0
    if aborted == "login/checkpoint wall":
        suffix += "-PARTIAL"
        exit_code = 2
    elif aborted:
        suffix += "-PARTIAL"
        exit_code = 4
    elif audit["verdict"] != "PASS":
        suffix += "-AUDITFAIL"
        exit_code = 3

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, f"fb-ads-{slug}-{today}-{now}{suffix}.csv")
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER, extrasaction="ignore",
                           lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)

    if args.debug:
        with open(f"{debug_dir}/low_impression_payload_candidates.json", "w") as f:
            json.dump(debug_payload_candidates, f, indent=1, default=str)
        with open(f"{debug_dir}/audit.json", "w") as f:
            json.dump(audit, f, indent=2)
        print(f"[debug] payload nodes + candidates + audit → {debug_dir}")

    print("\n===== FINAL REPORT =====")
    print(f"Scraper version : {SCRIPT_VERSION}")
    print(f"Competitor      : {key}")
    print(f"Pages           : {len(page_reports)}/{len(pages)} attempted"
          + (f"  [ABORTED: {aborted}]" if aborted else ""))
    for rep in page_reports:
        print(f"  - {rep['page']}: {rep['ads']} ads → {rep['rows']} rows "
              f"({rep['multi_version']} multi-version, {rep['secs']}s"
              + (f", {rep.get('version_truncations', 0)} version-truncations" if rep.get("version_truncations") else "")
              + ")")
    print(f"Total rows      : {len(rows)}  (ads: {audit.get('total_ads', 0)})")
    print(f"Audit verdict   : {audit['verdict']}"
          + ("" if audit["verdict"] == "PASS" else "  ⚠️ DO NOT INGEST — see audit above"))
    print(f"CSV             : {out_path}")
    print("\nNext (bench): diff against the same-day Claude-in-Chrome CSV:\n"
          f"  python3.13 facebook/scripts/fb_scrape_diff.py {out_path} "
          f"facebook/inputs/fb-ads-{slug}-{today}.csv")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
