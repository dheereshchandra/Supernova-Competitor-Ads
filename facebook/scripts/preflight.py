#!/usr/bin/env python3
"""
Preflight — verify the pipeline can run end-to-end before any step starts.

Catches the failure modes that have, in practice, forced operators back to the
Terminal mid-run:

  • Wrong Python (Apple's 3.9 default — fails on `str | None` type hints used in
    download_fb_ads.py and elsewhere)
  • Missing Python deps (yt-dlp, boto3, python-docx, Pillow)
  • Missing google-genai (NOT google-generativeai — that's the deprecated SDK
    and step4_decompose.py imports the new `from google import genai`)
  • Missing ffmpeg / ffprobe (Step 4 silently produces "0 frames extracted"
    if these aren't installed; step4_frames.py catches OSError and reports
    every row as failed)
  • .env missing keys (R2_* + GEMINI_API_KEY)
  • Folder layout broken

Each skill MUST call this before doing anything else. Exit 0 = ready to go.
Non-zero exit = surface the printed remediation hint to the operator and stop.

Usage:
    python3 scripts/preflight.py                    # all checks
    python3 scripts/preflight.py --skip-gemini      # for Steps 2/3 only (no GEMINI_API_KEY needed)
    python3 scripts/preflight.py --json             # machine-readable
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys


REQUIRED_R2_KEYS = (
    "R2_S3_ENDPOINT",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
    "R2_PUBLIC_URL_BASE",
)


def load_env(env_path: pathlib.Path) -> dict:
    if not env_path.exists():
        return {}
    out = {}
    for line in env_path.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def check_python_version() -> tuple[bool, str]:
    v = sys.version_info
    if v.major == 3 and v.minor >= 10:
        return True, f"Python {v.major}.{v.minor}.{v.micro}"
    return False, (
        f"Python {v.major}.{v.minor}.{v.micro} is too old. "
        f"Need 3.10+ (the pipeline uses `str | None` type hints). "
        f"Install Homebrew Python: `brew install python@3.13` and re-run "
        f"with `python3.13` instead of `python3`."
    )


def check_module(name: str, install_hint: str) -> tuple[bool, str]:
    try:
        mod = __import__(name)
        ver = getattr(mod, "__version__", "ok")
        return True, f"{name} {ver}"
    except ImportError:
        return False, f"{name} not installed — {install_hint}"


def check_genai() -> tuple[bool, str]:
    """The new SDK. NOT to be confused with google-generativeai (deprecated)."""
    try:
        from google import genai  # type: ignore
        return True, "google-genai (new SDK) ok"
    except ImportError:
        return False, (
            "google-genai not installed — run `python3.13 -m pip install "
            "--upgrade --break-system-packages --user google-genai`. "
            "WARNING: do NOT install `google-generativeai` (old, deprecated SDK) — "
            "step4_decompose.py imports `from google import genai` which only the "
            "new package provides."
        )


def check_bin(name: str, install_hint: str) -> tuple[bool, str]:
    path = shutil.which(name)
    if path:
        try:
            ver = subprocess.run(
                [name, "-version" if name in ("ffmpeg", "ffprobe") else "--version"],
                capture_output=True, text=True, timeout=4,
            ).stdout.splitlines()[0][:80]
            return True, f"{name} @ {path}  ({ver})"
        except Exception:
            return True, f"{name} @ {path}"
    return False, f"{name} not on PATH — {install_hint}"


def check_env(env: dict, skip_gemini: bool) -> tuple[bool, str]:
    missing = [k for k in REQUIRED_R2_KEYS if not env.get(k)]
    if not skip_gemini and not env.get("GEMINI_API_KEY"):
        missing.append("GEMINI_API_KEY")
    if missing:
        return False, f".env missing key(s): {', '.join(missing)}"
    return True, f".env has {len(REQUIRED_R2_KEYS) + (0 if skip_gemini else 1)} required keys"


def check_layout() -> tuple[bool, str]:
    root = pathlib.Path.cwd()
    must_exist = ["scripts", ".env"]
    missing = [p for p in must_exist if not (root / p).exists()]
    if missing:
        return False, (
            f"Not in pipeline root (cwd={root}). Missing: {missing}. "
            f"Run from ~/Desktop/fb-ad-downloader/."
        )
    # ensure these subfolders exist (create if absent)
    for d in ("inputs", "videos", "master", "step3_logs", "step4_workspace"):
        (root / d).mkdir(exist_ok=True)
    return True, f"layout ok (cwd={root})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-gemini", action="store_true",
                    help="Don't require GEMINI_API_KEY or google-genai (Steps 2/3 only).")
    ap.add_argument("--json", action="store_true", help="Machine-readable output.")
    args = ap.parse_args()

    env = load_env(pathlib.Path(".env"))

    checks = []
    checks.append(("python_version", *check_python_version()))
    checks.append(("layout", *check_layout()))
    checks.append(("env", *check_env(env, args.skip_gemini)))
    checks.append(("module:requests",
                   *check_module("requests", "pip install requests")))
    checks.append(("module:openpyxl",
                   *check_module("openpyxl", "pip install openpyxl")))
    checks.append(("module:boto3",
                   *check_module("boto3", "pip install boto3")))
    checks.append(("module:yt_dlp",
                   *check_module("yt_dlp", "pip install yt-dlp")))
    checks.append(("module:docx",
                   *check_module("docx", "pip install python-docx")))
    checks.append(("module:PIL",
                   *check_module("PIL", "pip install Pillow")))
    checks.append(("bin:ffmpeg",
                   *check_bin("ffmpeg", "brew install ffmpeg (Step 4 frame extraction needs it)")))
    checks.append(("bin:ffprobe",
                   *check_bin("ffprobe", "brew install ffmpeg (includes ffprobe)")))
    if not args.skip_gemini:
        checks.append(("module:google-genai", *check_genai()))

    all_ok = all(ok for _, ok, _ in checks)

    if args.json:
        print(json.dumps({
            "ok": all_ok,
            "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
        }, indent=2))
        return 0 if all_ok else 1

    # human-readable
    print("Pipeline preflight")
    print("─" * 60)
    for name, ok, detail in checks:
        mark = "✓" if ok else "✗"
        print(f"  {mark} {name:<22} {detail}")
    print("─" * 60)
    if all_ok:
        print("READY. All checks passed.")
        return 0
    print("NOT READY. Fix the items marked ✗ above, then re-run preflight.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
