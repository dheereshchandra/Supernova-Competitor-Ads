#!/usr/bin/env python3
"""
step4_build_html.py — render the Supernova rewrite as a clean, BROWSER-FRIENDLY HTML
page instead of a download-only .docx.

Team feedback (objective bucket):
  • #2 the .docx links DOWNLOAD (browsers can't render Word) and need Word/logins.
       HTML is served from R2 with `text/html; inline`, so the link OPENS in a tab —
       read + copy, nothing to install.
  • #7 visual cues were buried in paragraphs. Each scene is now laid out as a clear
       Scene → (Character, Script) table.
  • #1 English-forward. The rewrite sidecars store "<native> [English]" lines; this
       shows the ENGLISH as the primary script with the native line muted underneath
       (and once step4_rewrite.py emits English natively, it just renders that).

Reads  facebook/step4_workspace/scenes/<id>.supernova.json   (the rewrite output)
Writes facebook/step4_workspace/docs/<id>_supernova_rewrite.html
With --upload: pushes each HTML to R2 (text/html, inline) and, with --update-master,
records `supernova_rewrite_html_r2_url` in master/<competitor>.csv (additive column).

Usage:
    python3 facebook/scripts/step4_build_html.py --competitor mysivi            # build locally
    python3 facebook/scripts/step4_build_html.py --competitor mysivi --ids 123,456
    python3 facebook/scripts/step4_build_html.py --competitor mysivi --upload --update-master
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # facebook/scripts
FB = HERE.parent                                # facebook
SCENES_DIR = FB / "step4_workspace" / "scenes"
DOCS_DIR = FB / "step4_workspace" / "docs"

_SPEAKER = re.compile(r"^\s*(Character\s+\w+|Miss\s+Nova|Narrator|VO|Voice\s*over)\s*(?:says?)?\s*:\s*(.*)$", re.I)
_GENERIC = re.compile(r"^\s*([^:]{1,32}?)\s*:\s*(.*)$")
_BRACKET = re.compile(r"^(.*?)\s*[\[(]([^\])]*)[\])]\s*$", re.S)


def parse_line(line: str) -> tuple[str, str]:
    """'Character A says: नमस्ते [Hello]' -> ('Character A', 'नमस्ते [Hello]')."""
    m = _SPEAKER.match(line) or _GENERIC.match(line)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", line.strip()


def split_native_english(text: str) -> tuple[str, str]:
    """'नमस्ते [Hello]' -> ('नमस्ते', 'Hello'). No bracket -> (text, '')."""
    m = _BRACKET.match(text)
    if m and m.group(2).strip():
        return m.group(1).strip(), m.group(2).strip()
    return text.strip(), ""


def esc(s) -> str:
    return html.escape(str(s or ""))


def render_script_rows(supernova_script: str) -> str:
    rows = []
    for raw in (supernova_script or "").split("\n"):
        if not raw.strip():
            continue
        speaker, text = parse_line(raw)
        native, english = split_native_english(text)
        primary = english or native           # English-forward; native if no translation
        secondary = native if english else ""
        rows.append(
            f'<tr><td class="char">{esc(speaker)}</td>'
            f'<td class="script"><div class="en">{esc(primary)}</div>'
            + (f'<div class="na">{esc(secondary)}</div>' if secondary else "")
            + "</td></tr>"
        )
    if not rows:
        return '<p class="muted">[no script lines]</p>'
    return ('<table class="lines"><thead><tr><th>Character</th><th>Script</th></tr></thead>'
            "<tbody>" + "".join(rows) + "</tbody></table>")


def render_html(ad_id: str, competitor: str, parsed: dict) -> str:
    scenes = parsed.get("scenes", []) if isinstance(parsed, dict) else []
    chars = parsed.get("characters", [])
    char_html = ""
    if chars:
        items = "".join(f"<li>{esc(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))}</li>"
                        for c in chars)
        char_html = f'<section class="chars"><h2>Characters</h2><ul>{items}</ul></section>'

    blocks = []
    for sc in scenes:
        label = esc(sc.get("scene_label", ""))
        n = esc(sc.get("n", ""))
        ost = (sc.get("supernova_on_screen_text") or "").strip()
        summ = (sc.get("scene_summary") or "").strip()
        summ_html = ""
        if summ:
            bullets = "".join(f"<li>{esc(b.lstrip('- ').strip())}</li>"
                              for b in summ.split("\n") if b.strip())
            summ_html = f'<details><summary>Scene notes</summary><ul>{bullets}</ul></details>'
        ost_html = (f'<div class="ost"><span class="lbl">On-screen text</span>'
                    f'<div>{esc(ost).replace(chr(10), "<br>")}</div></div>') if ost else ""
        blocks.append(
            f'<section class="scene"><h2><span class="n">Scene {n}</span> {label}</h2>'
            f'{render_script_rows(sc.get("supernova_script", ""))}{ost_html}{summ_html}</section>'
        )

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Supernova rewrite — {esc(competitor)} {esc(ad_id)}</title>
<style>
  :root {{ --ink:#1a1a1a; --muted:#777; --line:#e5e5e5; --brand:#5b34d6; --bg:#fafafa; }}
  body {{ font:16px/1.55 -apple-system,Segoe UI,Roboto,Arial,sans-serif; color:var(--ink);
         background:var(--bg); margin:0; padding:0 16px 64px; }}
  .wrap {{ max-width:820px; margin:0 auto; }}
  header {{ padding:28px 0 8px; border-bottom:2px solid var(--brand); margin-bottom:8px; }}
  header h1 {{ margin:0; font-size:22px; }} header .sub {{ color:var(--muted); font-size:13px; }}
  .scene {{ background:#fff; border:1px solid var(--line); border-radius:10px;
           padding:14px 18px; margin:18px 0; }}
  .scene h2 {{ font-size:17px; margin:.2em 0 .6em; }}
  .scene h2 .n {{ background:var(--brand); color:#fff; font-size:12px; padding:2px 8px;
                 border-radius:20px; margin-right:8px; vertical-align:middle; }}
  table.lines {{ border-collapse:collapse; width:100%; }}
  table.lines th {{ text-align:left; font-size:12px; color:var(--muted); border-bottom:1px solid var(--line);
                   padding:4px 8px; }}
  table.lines td {{ padding:7px 8px; vertical-align:top; border-bottom:1px solid #f0f0f0; }}
  td.char {{ white-space:nowrap; color:var(--brand); font-weight:600; font-size:13px; width:120px; }}
  .en {{ font-size:16px; }} .na {{ color:var(--muted); font-size:13px; margin-top:2px; }}
  .ost {{ margin-top:10px; background:#f6f3ff; border-radius:8px; padding:8px 10px; font-size:14px; }}
  .ost .lbl {{ color:var(--brand); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }}
  details {{ margin-top:8px; }} summary {{ cursor:pointer; color:var(--muted); font-size:13px; }}
  .chars ul {{ columns:2; font-size:14px; }} .muted {{ color:var(--muted); }}
  footer {{ color:var(--muted); font-size:12px; margin-top:24px; }}
</style></head><body><div class="wrap">
<header><h1>Supernova rewrite</h1>
<div class="sub">{esc(competitor)} · ad {esc(ad_id)} · {len(scenes)} scene(s) · select &amp; copy any text</div></header>
{char_html}
{"".join(blocks) if blocks else '<p class="muted">No scenes in this rewrite.</p>'}
<footer>Generated from the Supernova rewrite. Script shown English-first; native line muted underneath.</footer>
</div></body></html>"""


def read_master(master: Path) -> tuple[list[dict], list[str]]:
    with master.open(encoding="utf-8-sig", newline="") as fh:
        r = csv.DictReader(fh)
        return list(r), list(r.fieldnames or [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competitor", required=True)
    ap.add_argument("--ids", help="comma-separated ad ids only (default: every rewrite sidecar)")
    ap.add_argument("--upload", action="store_true", help="push each HTML to R2 (text/html, inline)")
    ap.add_argument("--update-master", action="store_true",
                    help="record supernova_rewrite_html_r2_url in master/<competitor>.csv")
    args = ap.parse_args()
    slug = args.competitor.lower().strip()

    sidecars = sorted(SCENES_DIR.glob("*.supernova.json"))
    if args.ids:
        want = set(args.ids.split(","))
        sidecars = [p for p in sidecars if p.name.replace(".supernova.json", "") in want]
    if not sidecars:
        print(f"[error] no rewrite sidecars in {SCENES_DIR}")
        return 1

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    built: dict[str, Path] = {}
    for p in sidecars:
        ad_id = p.name.replace(".supernova.json", "")
        try:
            parsed = json.loads(p.read_text()).get("parsed", {})
        except (ValueError, OSError) as e:
            print(f"  [warn] {ad_id}: {e}")
            continue
        out = DOCS_DIR / f"{ad_id}_supernova_rewrite.html"
        out.write_text(render_html(ad_id, slug, parsed), encoding="utf-8")
        built[ad_id] = out
    print(f"{slug}: built {len(built)} HTML rewrite(s) -> {DOCS_DIR}")

    if not args.upload:
        print("  (build-only; pass --upload to push to R2)")
        return 0

    sys.path.insert(0, str(HERE))
    import r2_utils
    env = r2_utils.load_env()
    s3 = r2_utils.make_r2_client(env)
    urls: dict[str, str] = {}
    for ad_id, out in built.items():
        key = f"{ad_id}_supernova_rewrite.html"
        urls[ad_id] = r2_utils.upload_file(s3, env, out, key)
    print(f"  uploaded {len(urls)} HTML page(s) to R2 (open-in-browser links)")

    if args.update_master:
        master = FB / "master" / f"{slug}.csv"
        if not master.exists():
            print(f"  [warn] master not found: {master}")
            return 0
        rows, cols = read_master(master)
        col = "supernova_rewrite_html_r2_url"
        if col not in cols:
            cols.append(col)
        n = 0
        for r in rows:
            u = urls.get((r.get("ad_library_id") or "").strip())
            if u:
                r[col] = u
                n += 1
        with master.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader(); w.writerows(rows)
        print(f"  master updated: {col} set on {n} row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
