#!/usr/bin/env python3
"""
fb_scrape_probe.py — EXPERIMENTAL feasibility check (throwaway).

Question: can we drive the Meta Ad Library from a terminal browser (Playwright)
instead of Claude-in-Chrome? This does NOT scrape — it just opens one competitor's
Ad Library in Chromium and reports whether ad cards render (→ worth building a full
terminal scraper) or anti-bot blocks it (→ stick with Claude-in-Chrome).

Runs on YOUR Mac. One-time setup:
    pip3.13 install --user playwright
    python3.13 -m playwright install chromium

Usage (a visible browser window will open — that's expected):
    python3.13 facebook/scripts/fb_scrape_probe.py "Duolingo"
    python3.13 facebook/scripts/fb_scrape_probe.py "Duolingo" --headless
"""
import sys
import time

comp, headless = "Duolingo", False
for a in sys.argv[1:]:
    if a == "--headless":
        headless = True
    elif not a.startswith("-"):
        comp = a

URL = ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
       f"&country=IN&media_type=all&q={comp}&search_type=keyword_unordered")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Playwright not installed. Run:\n"
             "  pip3.13 install --user playwright\n"
             "  python3.13 -m playwright install chromium")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=headless)
    page = browser.new_page()
    print(f"opening Ad Library for '{comp}' (region IN)…  (headless={headless})")
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)

    # best-effort: dismiss the cookie consent banner if it appears
    for label in ("Allow all cookies", "Accept all", "Only allow essential cookies",
                  "Decline optional cookies"):
        try:
            page.get_by_role("button", name=label).click(timeout=2500)
            break
        except Exception:  # noqa: BLE001
            pass

    time.sleep(10)  # let the lazy-loaded results render
    html = page.content()
    cards = html.count("Library ID")          # each ad card shows "Library ID: …"
    low = (page.url + " " + html[:6000]).lower()
    blocked = any(w in low for w in ("/login", "checkpoint", "log in to continue",
                                     "you must log in", "temporarily blocked"))
    page.screenshot(path="fb_probe.png", full_page=False)

    print("─" * 56)
    print(f"final URL                          : {page.url}")
    print(f"ad cards seen (≈ 'Library ID' count): {cards}")
    print(f"login / block wall detected        : {blocked}")
    print(f"screenshot saved                   : fb_probe.png  (open it to verify)")
    print("─" * 56)
    if cards > 0 and not blocked:
        print("RESULT: ✅ ads loaded — terminal scraping looks FEASIBLE.")
        print("        Next: port the scraper JS into a full Playwright scraper + validate.")
    else:
        print("RESULT: ⚠️  no ad cards / blocked — anti-bot likely wins here.")
        print("        Recommendation: keep Claude-in-Chrome for Facebook.")
    browser.close()
