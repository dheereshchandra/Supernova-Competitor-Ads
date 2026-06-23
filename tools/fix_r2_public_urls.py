#!/usr/bin/env python3.13
"""One-time (idempotent) repair: master CSVs that stored R2's PRIVATE S3 API endpoint
(`<accountid>.r2.cloudflarestorage.com/<key>`, which 400s in a browser) instead of the
PUBLIC URL (`pub-<hash>.r2.dev/<key>`). The object key/path is identical, so we just swap
the host. The public base is read from R2_PUBLIC_URL_BASE in .env (must be a public host,
NOT the S3 endpoint — enforce_public_base() guards that).

Root cause: an operator's .env had R2_PUBLIC_URL_BASE pointing at the S3 endpoint, and
upload_to_r2.py carries forward existing URLs — so the bad form stuck. Fixed in .env +
guarded in preflight/upload; this script repairs the already-written rows.

Usage:
  python3.13 tools/fix_r2_public_urls.py [--dry-run] [--public-base https://pub-XXX.r2.dev]
"""
import argparse, pathlib, re, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
S3_HOST_RE = re.compile(r"https://[A-Za-z0-9]+\.r2\.cloudflarestorage\.com")

def public_base_from_env():
    for envp in (REPO / ".env", REPO / "facebook" / ".env"):
        if envp.exists():
            for line in envp.read_text().splitlines():
                if line.startswith("R2_PUBLIC_URL_BASE="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    return None

def enforce_public_base(base):
    if not base:
        sys.exit("[error] R2_PUBLIC_URL_BASE not found in .env")
    if "r2.cloudflarestorage.com" in base:
        sys.exit(f"[error] R2_PUBLIC_URL_BASE is the PRIVATE S3 endpoint ({base}). "
                 "Set it to the public pub-<hash>.r2.dev (or custom domain) first.")
    return base

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--public-base", default=None)
    args = ap.parse_args()
    base = enforce_public_base(args.public_base or public_base_from_env())
    print(f"[fix] public base = {base}")
    masters = sorted(list((REPO / "facebook" / "master").glob("*.csv"))
                     + list((REPO / "google" / "master").glob("*.csv")))
    total = 0; files = 0
    for f in masters:
        text = f.read_text(encoding="utf-8")
        new, n = S3_HOST_RE.subn(base, text)
        if n:
            files += 1; total += n
            print(f"  {'(dry) ' if args.dry_run else ''}{f.relative_to(REPO)}: {n} URL(s)")
            if not args.dry_run:
                f.write_text(new, encoding="utf-8")
    print(f"[fix] {'would rewrite' if args.dry_run else 'rewrote'} {total} URL(s) across {files} file(s)")
    # post-check
    if not args.dry_run:
        left = sum(len(S3_HOST_RE.findall(f.read_text(encoding='utf-8'))) for f in masters)
        print(f"[fix] remaining S3-endpoint URLs in masters: {left}")

if __name__ == "__main__":
    main()
