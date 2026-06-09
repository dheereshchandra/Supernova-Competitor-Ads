#!/usr/bin/env python3
"""
Shared R2 helpers for every step of the pipeline.

All scripts that talk to R2 (`upload_to_r2.py`, `step4_upload_images.py`,
`step4_upload_and_update.py`, `backfill_step4_images.py`) should import from
this module instead of inlining their own boto3 boilerplate. That way the
endpoint, bucket, public-URL pattern, retry behaviour and verification path
are defined in one place — which is what makes the URL-presence audit step
trustworthy.

Public URL convention
---------------------
Every public URL is built as:

    f"{env['R2_PUBLIC_URL_BASE']}/{key}"

with no extra slashes, no leading "https://" rewriting. The keys themselves
embed any folder structure (`images/<ad_library_id>/orig_01.jpg`) — R2 / S3
treats forward slashes inside keys as prefix segments.

See HANDOVER.md §8.7 (master CSV schema) and §9.7 (image URL contract) for
the canonical column names and folder layout this module enforces.
"""
from __future__ import annotations

import pathlib
import sys
import time
from typing import Optional


REQUIRED_R2_ENV_KEYS = [
    "R2_S3_ENDPOINT",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
    "R2_PUBLIC_URL_BASE",
]


# ---------------------------------------------------------------------------
# .env loading (kept dependency-free so every Step-2/3/4 script can use it)
# ---------------------------------------------------------------------------

def load_env(env_path: pathlib.Path = pathlib.Path(".env")) -> dict:
    """Read a flat KEY=VALUE .env file. Mirrors what upload_to_r2.py used to do."""
    if not env_path.exists():
        sys.exit(f"[error] .env not found at {env_path}.")
    env: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def require_r2_keys(env: dict) -> None:
    missing = [k for k in REQUIRED_R2_ENV_KEYS if not env.get(k)]
    if missing:
        sys.exit(f"[error] .env missing required R2 keys: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# Client + upload + verify
# ---------------------------------------------------------------------------

def make_r2_client(env: dict):
    """Construct a boto3 S3 client pointed at Cloudflare R2."""
    import boto3
    require_r2_keys(env)
    return boto3.client(
        "s3",
        endpoint_url=env["R2_S3_ENDPOINT"],
        aws_access_key_id=env["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def public_url_for(env: dict, key: str) -> str:
    """Build the public URL that the master CSV records and the docx hyperlinks point at."""
    base = env["R2_PUBLIC_URL_BASE"].rstrip("/")
    return f"{base}/{key.lstrip('/')}"


CONTENT_TYPE_BY_EXT = {
    ".mp4": "video/mp4",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".html": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
}

# Types a browser can RENDER — serve these with `Content-Disposition: inline` so the
# public R2 link OPENS in a tab (read + copy) instead of downloading a file. A .docx
# can't render in any browser, so it always downloads regardless — that's the whole
# reason the rewrite link now ships as .html instead.
INLINE_TYPES = {"text/html; charset=utf-8", "application/pdf", "text/plain; charset=utf-8"}


def content_type_for(path: pathlib.Path) -> str:
    return CONTENT_TYPE_BY_EXT.get(path.suffix.lower(), "application/octet-stream")


def upload_file(s3, env: dict, local_path: pathlib.Path, key: str,
                content_type: Optional[str] = None) -> str:
    """
    Upload `local_path` to R2 under `key`. Returns the public URL.

    Idempotent: re-uploading the same key just overwrites the existing object,
    which is what we want — every script in the pipeline is resumable, so a
    re-run should never see a stale R2 object. Browser-renderable types are tagged
    `inline` so the link opens in a tab rather than downloading.
    """
    ct = content_type or content_type_for(local_path)
    extra = {"ContentDisposition": "inline"} if ct in INLINE_TYPES else {}
    with open(local_path, "rb") as fh:
        s3.put_object(
            Bucket=env["R2_BUCKET"],
            Key=key,
            Body=fh,
            ContentType=ct,
            **extra,
        )
    return public_url_for(env, key)


def head_check(url: str, timeout: float = 8.0) -> tuple[bool, int]:
    """
    HEAD the public URL and return (ok, status_code).

    Used by the verification step to confirm each URL recorded in the docx /
    master CSV actually resolves to a real R2 object. Network failures count
    as "not ok" (ok=False, status=0).
    """
    try:
        import urllib.request
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            return (200 <= status < 400), status
    except Exception:
        return False, 0


# ---------------------------------------------------------------------------
# Image R2 key conventions for Step 4
# ---------------------------------------------------------------------------
#
# Per HANDOVER.md §9.7, every Step-4 image lives under a per-ad folder:
#
#     images/<ad_library_id>/orig_<NN>.jpg          original scene frame
#     images/<ad_library_id>/gen_<NN>_<pos>.jpg     clean regenerated panel
#     images/<ad_library_id>/char_<X>_sheet.jpg     character reference sheet
#
# Videos and docs keep the historical flat naming (<id>.mp4, <id>_competitor_analysis.docx)
# so downstream consumers of those columns are unaffected.

def orig_frame_key(ad_id: str, scene_n: int) -> str:
    return f"images/{ad_id}/orig_{int(scene_n):02d}.jpg"


def gen_panel_key(ad_id: str, scene_n: int, position: str) -> str:
    return f"images/{ad_id}/gen_{int(scene_n):02d}_{position}.jpg"


def char_sheet_key(ad_id: str, char_id: str | int) -> str:
    return f"images/{ad_id}/char_{char_id}_sheet.jpg"


def upload_with_retry(s3, env: dict, local_path: pathlib.Path, key: str,
                      attempts: int = 3) -> str:
    """Wrap upload_file with a small backoff loop — R2 occasionally returns 5xx."""
    last_exc: Optional[Exception] = None
    for i in range(attempts):
        try:
            return upload_file(s3, env, local_path, key)
        except Exception as e:
            last_exc = e
            time.sleep(1.5 * (i + 1))
    assert last_exc is not None
    raise last_exc
