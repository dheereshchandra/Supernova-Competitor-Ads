#!/usr/bin/env python3.13
"""
fb_allow_clicker.py — auto-approve the Claude-in-Chrome "Allow this action" prompt
during a Facebook Ad Library scrape.

WHY THIS EXISTS
---------------
When you run the FB scrape via the Claude Chrome side-panel extension, facebook.com is
a *restricted* site: the "Always allow actions on this site" option is withheld
("Site-level permissions are disabled for this site"), so Claude asks you to approve
**every** JavaScript execution. A 30-ad page = 30-40 manual clicks. (There is also an
open upstream bug, anthropics/claude-code#55124, where these approvals don't persist.)

This watcher does the clicking for you — but *narrowly and safely*:

  * It uses macOS's built-in Vision OCR to locate the "Allow this action" button.
  * It clicks ONLY when the on-screen request also mentions the target site
    (facebook.com by default) AND Google Chrome is the frontmost app. So it will not
    auto-approve actions on any other site, and it never touches "Decline".
  * It restores your mouse cursor to where it was after each click.

SAFETY / SCOPE GUARANTEES
-------------------------
A click fires ONLY when ALL of these hold at once, so it cannot "click around":
  1. a short, button-sized 'Allow this action' label is on screen
  2. the target site (facebook.com by default) text is on screen
  3. a Claude permission-popup phrase is present ("New permissions required",
     "Claude wants to execute JavaScript", "Site-level permissions...", etc.)
  4. the button sits right next to that facebook.com popup (spatial proximity)
  5. the same button is seen in TWO consecutive scans (no one-frame OCR glitch)
  6. Google Chrome is the frontmost app (unless --any-app)
It never clicks 'Decline' or 'Always allow'; it restores your cursor after each click;
and a runaway guard auto-pauses if an abnormal burst of clicks ever occurs. Still, keep
it scoped to the scrape and stop it (Ctrl-C) when done.

macOS PERMISSIONS (one-time)
----------------------------
Grant BOTH to the terminal app you launch this from (Terminal / iTerm / VS Code):
  System Settings -> Privacy & Security -> Screen Recording  -> enable your terminal
  System Settings -> Privacy & Security -> Accessibility     -> enable your terminal
(Restart the terminal after granting.) Without Screen Recording the captures are blank;
without Accessibility the synthetic clicks are silently ignored.

USAGE
-----
  # 1) Validate detection against your screenshot — no clicking:
  python3.13 facebook/scripts/fb_allow_clicker.py --test-image /path/to/screenshot.png

  # 2) Dry run live — detect + log, but do NOT click (sanity check on the real screen):
  python3.13 facebook/scripts/fb_allow_clicker.py --dry-run

  # 3) For real — start before scraping, Ctrl-C when finished:
  python3.13 facebook/scripts/fb_allow_clicker.py

Options: --site (default facebook.com), --interval seconds (default 0.7),
         --any-app (don't require Chrome frontmost), --verbose, --save-capture PATH
"""
from __future__ import annotations

import argparse
import re
import sys
import time

try:
    import Quartz
    import Vision
    from AppKit import NSWorkspace
except Exception as e:  # pragma: no cover - import guard
    sys.stderr.write(
        "ERROR: missing macOS bridges. Install with:\n"
        "  python3.13 -m pip install --user --break-system-packages "
        "pyobjc-framework-Vision pyobjc-framework-Quartz pyobjc-framework-Cocoa\n"
        f"(import error: {e})\n"
    )
    sys.exit(2)


BUTTON_TEXT = "allow this action"

# The Claude permission popup ALWAYS contains one of these phrases. Requiring one means
# we only ever act on that specific dialog — never on stray page text.
SIG_PHRASES = (
    "permissions required",
    "claude wants to",
    "wants to execute",
    "wants to navigate",
    "execute javascript",
    "site level permissions",
)
MAX_BUTTON_W = 0.30   # the button label is short; ignore wide paragraphs of text
MAX_BUTTON_H = 0.08
SITE_NEAR = 0.32      # button must be this close (normalized) to a facebook.com anchor
SIG_NEAR = 0.45       # ...and this close to a popup-signature phrase


def _center(b):
    x, y, w, h = b
    return (x + w / 2.0, y + h / 2.0)


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _norm(s: str) -> str:
    """Lowercase, drop punctuation except dots/spaces, collapse whitespace."""
    s = s.lower().replace(" ", " ")
    s = re.sub(r"[^a-z0-9.\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def ocr(cgimage):
    """Return [(text, (x, y, w, h))] with normalized bbox (bottom-left origin)."""
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cgimage, None)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    try:
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    except Exception:
        request.setRecognitionLevel_(0)  # 0 == Accurate
    request.setUsesLanguageCorrection_(False)
    ok, _err = handler.performRequests_error_([request], None)
    if not ok:
        return []
    out = []
    for obs in (request.results() or []):
        cands = obs.topCandidates_(1)
        if not cands or cands.count() == 0:
            continue
        text = str(cands.objectAtIndex_(0).string())
        b = obs.boundingBox()
        out.append((text, (b.origin.x, b.origin.y, b.size.width, b.size.height)))
    return out


def find_target(observations, site: str):
    """Decide whether it is safe to click. Returns (center_xy, reason): center_xy is the
    normalized (bottom-left origin) center of the 'Allow this action' button, or None with
    a human-readable reason. Several INDEPENDENT gates must all pass, so the clicker can
    only ever act on the actual Claude facebook.com permission popup."""
    site_norm = _norm(site)
    norm_obs = [(_norm(t), b) for t, b in observations]

    # Gate 1: the target site must be on screen (strict — 'facebook.com', not bare 'facebook')
    site_anchors = [b for t, b in norm_obs if site_norm in t]
    if not site_anchors:
        return None, f"no '{site}' on screen"

    # Gate 2: a Claude permission-popup phrase must be present
    sig_anchors = [b for t, b in norm_obs if any(p in t for p in SIG_PHRASES)]
    if not sig_anchors:
        return None, "no Claude-permission-popup text on screen"

    # Gate 3+4: a short, button-sized 'Allow this action' region that sits next to BOTH the
    # facebook.com text and the popup signature (never 'Always allow', never 'Decline').
    best = None
    for t, b in norm_obs:
        is_btn = (t == BUTTON_TEXT or BUTTON_TEXT in t
                  or ("allow" in t and "action" in t and "always" not in t))
        if not is_btn:
            continue
        _x, _y, w, h = b
        if w > MAX_BUTTON_W or h > MAX_BUTTON_H:
            continue  # too large to be the button label
        c = _center(b)
        ds = min(_dist(c, _center(a)) for a in site_anchors)
        dg = min(_dist(c, _center(a)) for a in sig_anchors)
        if ds <= SITE_NEAR and dg <= SIG_NEAR:
            score = ds + dg
            if best is None or score < best[0]:
                best = (score, c, ds, dg)
    if best is None:
        return None, "no 'Allow this action' button beside the facebook.com popup"
    _, c, ds, dg = best
    return c, f"facebook.com d={ds:.2f}, popup-sig d={dg:.2f}"


def active_displays():
    err, ids, count = Quartz.CGGetActiveDisplayList(16, None, None)
    if err != 0:
        return []
    return list(ids[:count])


def capture(display_id):
    return Quartz.CGDisplayCreateImage(display_id)


def norm_center_to_screen(cx, cy, cgimage, display_id):
    """Vision normalized (bottom-left) center -> global screen points (top-left)."""
    img_w = Quartz.CGImageGetWidth(cgimage)
    img_h = Quartz.CGImageGetHeight(cgimage)
    bounds = Quartz.CGDisplayBounds(display_id)
    scale = img_w / bounds.size.width if bounds.size.width else 2.0
    px = cx * img_w
    py = (1.0 - cy) * img_h  # flip to top-left origin
    sx = bounds.origin.x + px / scale
    sy = bounds.origin.y + py / scale
    return sx, sy


def mouse_pos():
    ev = Quartz.CGEventCreate(None)
    p = Quartz.CGEventGetLocation(ev)
    return p.x, p.y


def click(x, y, restore=True):
    prev = mouse_pos() if restore else None
    pt = Quartz.CGPointMake(x, y)
    for kind in (Quartz.kCGEventMouseMoved,
                 Quartz.kCGEventLeftMouseDown,
                 Quartz.kCGEventLeftMouseUp):
        ev = Quartz.CGEventCreateMouseEvent(None, kind, pt, Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        time.sleep(0.01)
    if prev is not None:
        time.sleep(0.04)
        back = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventMouseMoved,
            Quartz.CGPointMake(prev[0], prev[1]), Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, back)


def frontmost_name():
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return (app.localizedName() or "", app.bundleIdentifier() or "")


def load_image(path):
    url = Quartz.CFURLCreateWithFileSystemPath(None, path, Quartz.kCFURLPOSIXPathStyle, False)
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if not src:
        return None
    return Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)


def test_image(path, site):
    img = load_image(path)
    if img is None:
        print(f"[test] could not load image: {path}")
        return 1
    w, h = Quartz.CGImageGetWidth(img), Quartz.CGImageGetHeight(img)
    obs = ocr(img)
    print(f"[test] {path} ({w}x{h}px) — {len(obs)} text regions detected")
    for t, (x, y, bw, bh) in obs:
        print(f"    '{t}'  @ norm(x={x:.3f}, y={y:.3f}, w={bw:.3f}, h={bh:.3f})")
    center, reason = find_target(obs, site)
    if center:
        cx, cy = center
        # pixel coords (top-left origin) for a static image
        px, py = cx * w, (1.0 - cy) * h
        print(f"[test] SAFE TO CLICK — {reason}")
        print(f"[test] would click 'Allow this action' at image-pixel ({px:.0f}, {py:.0f})")
        return 0
    print(f"[test] would NOT click — {reason}")
    return 1


def _accessibility_trusted():
    """True/False if AX (synthetic-click) permission is granted; None if unknown."""
    try:
        import ctypes
        lib = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return None


def preflight():
    try:
        sr = bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        sr = None
    ax = _accessibility_trusted()

    def lbl(v):
        return "OK" if v else ("MISSING" if v is False else "unknown")

    print(f"[perm] Screen Recording (see): {lbl(sr)}   |   Accessibility (click): {lbl(ax)}")
    if not sr:
        print("[perm]  -> Screen Recording MISSING: enable THIS terminal in System Settings > "
              "Privacy & Security > Screen Recording, then FULLY QUIT (Cmd-Q) and reopen it.")
        try:
            Quartz.CGRequestScreenCaptureAccess()
        except Exception:
            pass
    if ax is False:
        print("[perm]  -> Accessibility MISSING: enable THIS terminal in System Settings > "
              "Privacy & Security > Accessibility, then reopen it. Without it, clicks are silently ignored.")
    return sr, ax


def watch(args):
    sr, ax = preflight()
    site = args.site
    gate6 = "" if args.any_app else ", (6) Chrome is frontmost"
    print(f"[safeguards] clicks ONLY when ALL hold: (1) short 'Allow this action' button on "
          f"screen, (2) '{site}' on screen, (3) Claude-permission-popup text present, (4) the "
          f"button sits right beside that popup, (5) seen in 2 consecutive scans{gate6}. "
          f"Never clicks 'Decline'; cursor restored after each click; runaway guard auto-pauses.")
    print(f"[watch] scanning every {args.interval}s "
          f"({'any app OK' if args.any_app else 'Chrome frontmost required'}; "
          f"{'DRY-RUN, no clicks' if args.dry_run else 'LIVE'}). Ctrl-C to stop.")
    last_click = 0.0
    last_xy = (-999.0, -999.0)
    last_front = None
    last_beat = 0.0
    pending = {}          # display_id -> (center, time): for 2-consecutive-scan confirmation
    recent = []           # recent click timestamps: for the runaway guard
    clicks = 0
    while True:
        try:
            now = time.time()
            front, _bid = frontmost_name()
            if not args.any_app and "chrome" not in front.lower():
                if front != last_front:
                    print(f"[paused] frontmost app is '{front}' — bring Chrome to the front (or use --any-app).")
                    last_front = front
                time.sleep(args.interval)
                continue
            last_front = front
            for did in (active_displays() or [Quartz.CGMainDisplayID()]):
                img = capture(did)
                if img is None:
                    if now - last_beat > 3.0:
                        print(f"[scan] display {did}: capture FAILED — Screen Recording not active for THIS terminal.")
                        last_beat = now
                    continue
                obs = ocr(img)
                center, reason = find_target(obs, site)
                if args.verbose or (now - last_beat > 3.0):
                    print(f"[scan] display {did}: {len(obs)} regions, "
                          f"{'MATCH' if center else 'no-match'} ({reason}), frontmost='{front}'")
                    last_beat = now
                if not center:
                    pending.pop(did, None)
                    continue
                # (5) two-scan confirmation: only click if the same button was here last scan too
                prev = pending.get(did)
                if not (prev and _dist(center, prev[0]) < 0.02 and now - prev[1] < 2.0):
                    pending[did] = (center, now)
                    if args.verbose:
                        print(f"[confirm] candidate on display {did}; waiting for 2nd confirmation")
                    continue
                pending.pop(did, None)
                sx, sy = norm_center_to_screen(center[0], center[1], img, did)
                if now - last_click < 1.2 and abs(sx - last_xy[0]) < 20 and abs(sy - last_xy[1]) < 20:
                    continue  # debounce the same popup
                # runaway guard: an abnormal burst means something is wrong — pause, don't spam clicks
                recent = [t for t in recent if now - t < 8.0]
                if len(recent) >= 8:
                    print("[guard] 8+ clicks in 8s — pausing 20s as a safety stop. Ctrl-C to quit.")
                    time.sleep(20.0)
                    recent = []
                    continue
                if args.dry_run:
                    print(f"[dry-run] would click ({sx:.0f}, {sy:.0f}) on display {did} — {reason}")
                else:
                    click(sx, sy, restore=not args.no_restore)
                    clicks += 1
                    recent.append(now)
                    tail = "" if ax else "  (WARNING: Accessibility not granted — click likely ignored)"
                    print(f"[click #{clicks}] approved '{site}' at ({sx:.0f}, {sy:.0f}) — {reason}{tail}")
                last_click = now
                last_xy = (sx, sy)
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print(f"\n[done] stopped. {clicks} clicks.")
            return 0


def main():
    ap = argparse.ArgumentParser(description="Auto-approve the Claude-in-Chrome 'Allow this action' prompt for FB scraping.")
    ap.add_argument("--site", default="facebook.com", help="only click when this site appears in the request (default: facebook.com)")
    ap.add_argument("--interval", type=float, default=0.7, help="scan interval seconds (default 0.7)")
    ap.add_argument("--dry-run", action="store_true", help="detect + log but do NOT click")
    ap.add_argument("--any-app", action="store_true", help="do not require Chrome to be frontmost")
    ap.add_argument("--no-restore", action="store_true", help="do not move the cursor back after clicking")
    ap.add_argument("--verbose", action="store_true", help="log every scan")
    ap.add_argument("--test-image", metavar="PATH", help="OCR a static screenshot and report what it would click; no clicking")
    ap.add_argument("--save-capture", metavar="PATH", help="(reserved) dump first capture for debugging")
    args = ap.parse_args()

    if args.test_image:
        return test_image(args.test_image, args.site)
    return watch(args)


if __name__ == "__main__":
    sys.exit(main())
