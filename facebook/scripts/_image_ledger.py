"""Shared R2-image ledger helper (localization image-once guardrail).

The git-tracked sidecar  step4_workspace/images/<id>/r2_urls.json  is the SOURCE OF
TRUTH for whether an ad's generated imagery already exists in R2. The costly Nano
Banana Pro stages (panels, character sheets) and the frame extraction skip on this
ledger — so a FRESH CLONE (no local image files, but the ledger committed) reuses the
existing R2 images instead of re-paying to regenerate them.

Ledger shape:
    {"ad_library_id": "...",
     "orig": {"01": "https://…orig_01.jpg", …},
     "gen":  {"01_full": "https://…gen_01_full.jpg", …},
     "char": {"A": "https://…char_A_sheet.jpg", …},
     "uploaded_at": "…"}
"""
from __future__ import annotations

import json
import pathlib


def load_ledger(images_dir: pathlib.Path, ad_id: str) -> dict:
    p = images_dir / ad_id / "r2_urls.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def ledger_url(images_dir: pathlib.Path, ad_id: str, section: str, key: str) -> str | None:
    """Return the recorded R2 URL for this image, or None."""
    url = (load_ledger(images_dir, ad_id).get(section) or {}).get(key, "")
    return url if isinstance(url, str) and url.startswith("http") else None


def ledger_has(images_dir: pathlib.Path, ad_id: str, section: str, key: str) -> bool:
    """True if r2_urls.json already records an http(s) URL for this image — i.e. it
    exists in R2 and must NOT be regenerated (the image-once guardrail)."""
    return ledger_url(images_dir, ad_id, section, key) is not None
