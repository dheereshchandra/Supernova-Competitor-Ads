#!/usr/bin/env python3
"""
preflight_enrichment.py — fail fast before any paid Flash/embedding run.

The free Phase-1 scripts need nothing special. The enrichment scripts
(detect_language / transcribe_tag / embed_scripts) need, on the operator's Mac:
  • Python 3.10+
  • google-genai (the new SDK — `from google import genai`), NOT google-generativeai
  • numpy (script_cluster / fb_google_overlap)
  • GEMINI_API_KEY in a .env (repo root, or facebook/.env / google/.env)
This checks all of that and prints the Flash + embedding models that WILL be used,
so a $-spending run never starts half-configured.

Usage:
    python3 analysis/scripts/preflight_enrichment.py
    python3 analysis/scripts/preflight_enrichment.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _flash


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def check_python():
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 9       # analysis scripts + google-genai run on 3.9+
    return ok, (f"Python {v.major}.{v.minor}.{v.micro}" if ok else
                f"Python {v.major}.{v.minor} too old — need 3.9+ "
                f"(`brew install python@3.13`)")


def check_genai():
    try:
        from google import genai  # noqa: F401
        return True, "google-genai (new SDK) ok"
    except ImportError:
        return False, ("google-genai not installed — `pip install google-genai`. "
                       "Do NOT install google-generativeai (deprecated).")


def check_numpy():
    try:
        import numpy
        return True, f"numpy {numpy.__version__}"
    except ImportError:
        return False, "numpy not installed — `pip install numpy`"


def check_key():
    root = repo_root()
    env = _flash.load_env(root / ".env", root / "facebook" / ".env",
                          root / "google" / ".env", Path(".env"))
    key = env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
    if key:
        return True, f"GEMINI_API_KEY found (…{key[-4:]})"
    return False, ("GEMINI_API_KEY missing — add it to .env (repo root, or "
                   "facebook/.env / google/.env). Runs on your Mac.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    checks = [
        ("python", *check_python()),
        ("google-genai", *check_genai()),
        ("numpy", *check_numpy()),
        ("GEMINI_API_KEY", *check_key()),
    ]
    all_ok = all(ok for _, ok, _ in checks)
    models = {"chat_model (Flash only)": _flash.DEFAULT_MODEL,
              "embed_model": "gemini-embedding-001"}

    if args.json:
        print(json.dumps({"ok": all_ok, "models": models,
                          "checks": [{"name": n, "ok": ok, "detail": d}
                                     for n, ok, d in checks]}, indent=2))
        return 0 if all_ok else 1

    print("Enrichment preflight")
    print("─" * 60)
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name:<16} {detail}")
    print("─" * 60)
    for k, v in models.items():
        print(f"  · {k}: {v}")
    print("─" * 60)
    if all_ok:
        print("READY. (Flash-only — never Pro. Start with `--limit 5` to calibrate.)")
        return 0
    print("NOT READY. Fix the ✗ items above, then re-run. (The free Phase-1 "
          "scripts work without any of this.)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
