#!/usr/bin/env python3
"""
detect_language.py — Phase 0 enrichment. Tags each ad's LANGUAGE with Gemini Flash.

The scrape data is country-keyed (everything is "India"), but India is
multilingual — so language must be DETECTED from the ad copy. This reads the
master's text fields and asks Flash (batched, cheap) for the dominant language.
Ads with no usable text (video-only) get their language from transcribe_tag.py
later instead.

Flash ONLY (never Pro). Cached + idempotent: results live in a per-competitor
sidecar and ads already tagged are skipped, so re-runs only do new ads.

Output: analysis/enrichment/{pipeline}/language/{competitor}.csv  (ad_id, language)

Runs on YOUR Mac (needs google-genai + GEMINI_API_KEY in .env). Usage:
    python3 analysis/scripts/detect_language.py --pipeline facebook --competitor duolingo
    python3 analysis/scripts/detect_language.py --pipeline facebook --competitor duolingo --limit 20 --dry-run
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import _flash

TEXT_FIELDS = {
    "facebook": ("ad_primary_text", "ad_description", "ad_cta_label"),
    "google": ("ad_headline", "ad_description", "ad_cta_text", "ad_overlay_text"),
}
AD_ID = {"facebook": "ad_library_id", "google": "creative_id"}

PROMPT_HEAD = (
    "You are a language identifier for advertising copy from India (multilingual). "
    "For each item below, return the DOMINANT human language of the text as a plain "
    "English language name (e.g. Hindi, English, Tamil, Telugu, Bengali, Marathi, "
    "Kannada, Malayalam, Gujarati, Punjabi, Urdu). Hinglish/code-mixed → pick the "
    "dominant language. If there is no meaningful language content, use \"unknown\". "
    "Reply with EXACTLY one JSON object: {\"results\":[{\"id\":\"...\",\"language\":\"...\"}]} "
    "— one entry per input id, no commentary.\n\nITEMS:\n"
)


def repo_root(explicit):
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def combined_text(row: dict, pipeline: str) -> str:
    parts = [(row.get(f) or "").strip() for f in TEXT_FIELDS[pipeline]]
    return "  ".join(p for p in parts if p)[:600]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pipeline", required=True, choices=["facebook", "google"])
    ap.add_argument("--competitor", required=True)
    ap.add_argument("--base", default=None)
    ap.add_argument("--model", default=_flash.DEFAULT_MODEL)
    ap.add_argument("--batch", type=int, default=40, help="ads per Flash call")
    ap.add_argument("--limit", type=int, default=None, help="cap new ads (testing)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    _flash.assert_flash(args.model)

    root = repo_root(args.base)
    slug = args.competitor.lower().strip()
    master = root / args.pipeline / "master" / f"{slug}.csv"
    if not master.exists():
        raise SystemExit(f"[error] master not found: {master}")
    id_col = AD_ID[args.pipeline]

    out_path = root / "analysis" / "enrichment" / args.pipeline / "language" / f"{slug}.csv"
    done: dict[str, str] = {}
    if out_path.exists():
        done = {r["ad_id"]: r["language"] for r in read_csv(out_path)}

    # one row per ad with usable text, not already tagged
    todo: dict[str, str] = {}
    for r in read_csv(master):
        ad_id = (r.get(id_col) or "").strip()
        if not ad_id or ad_id in done or ad_id in todo:
            continue
        text = combined_text(r, args.pipeline)
        if text:
            todo[ad_id] = text
    items = list(todo.items())
    if args.limit:
        items = items[:args.limit]

    print(f"{slug}: {len(done)} already tagged, {len(items)} new ad(s) to detect "
          f"(model={args.model}, batch={args.batch})")
    if not items:
        print("nothing to do.")
        return 0
    if args.dry_run:
        print("[dry-run] would call Flash for the above; writing nothing.")
        for ad_id, text in items[:5]:
            print(f"   {ad_id}: {text[:80]!r}")
        return 0

    client = _flash.get_client(_flash.find_env(root, args.pipeline))
    results: dict[str, str] = {}
    n_batches = 0; failed_batches = 0
    for i in range(0, len(items), args.batch):
        n_batches += 1
        chunk = items[i:i + args.batch]
        payload = [{"id": a, "text": t} for a, t in chunk]
        contents = PROMPT_HEAD + json.dumps(payload, ensure_ascii=False)
        try:
            obj = _flash.generate_json(client, args.model, contents)
            for rec in obj.get("results", []):
                if rec.get("id"):
                    results[str(rec["id"])] = (rec.get("language") or "unknown").strip()
        except Exception as e:  # noqa: BLE001
            failed_batches += 1
            print(f"  [warn] batch {i // args.batch} failed: {e}")
        print(f"  detected {len(results)}/{len(items)}")

    # merge + write (idempotent)
    merged = dict(done)
    merged.update(results)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ad_id", "language"])
        for ad_id, lang in sorted(merged.items()):
            w.writerow([ad_id, lang])
    print(f"wrote {len(merged)} total ({failed_batches}/{n_batches} batches FAILED) -> {out_path}")
    # Language is recoverable (re-run retries skipped ads), so only fail LOUD if the
    # step is broadly broken (>50% of batches failed).
    if n_batches and failed_batches > 0.5 * n_batches:
        print(f"[error] {failed_batches}/{n_batches} language batches failed (>50%) — "
              f"surfacing (API/network issue?). Re-run retries the missing ads.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
