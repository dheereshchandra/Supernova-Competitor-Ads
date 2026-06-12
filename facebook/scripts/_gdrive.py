#!/usr/bin/env python3
"""
Shared Google Drive helpers — the analog of r2_utils.py for the Google-Docs stage.

We store the per-ad deliverable docs as native Google Docs inside a Google Workspace **Shared Drive**
(not a personal My Drive) so the team owns + collaborates on them, and so a service account — which has
NO personal Drive storage quota — can create files at all. Every Drive call therefore carries
`supportsAllDrives=True` (and searches carry `corpora/driveId/includeItemsFromAllDrives`); omitting these
is the #1 Shared-Drive bug (calls silently scope to My Drive and 404 / return nothing).

Auth: a service-account JSON key, referenced by PATH from .env (a path, not inline — the multi-line
private key would be shredded by the flat KEY=VALUE .env parser). One-time human setup: create the SA,
create a Shared Drive, add the SA email as a Content Manager member. See facebook/HANDOVER.md §9.10.

.env keys (load via r2_utils.load_env / _flash.find_env):
    GOOGLE_SERVICE_ACCOUNT_JSON   path to the SA json (keep it OUTSIDE the repo, e.g. ~/.config/...)
    GDRIVE_SHARED_DRIVE_ID        the Shared Drive id (starts with 0A...)
    GDRIVE_ROOT_FOLDER_ID         optional: a folder inside the Shared Drive to nest under
    GDRIVE_LINK_SHARING           anyone | domain | none   (default: anyone)
    GDRIVE_DOMAIN                  Workspace domain, used only when sharing falls back to "domain"
"""
from __future__ import annotations

import os
import pathlib
import sys

SCOPES = ["https://www.googleapis.com/auth/drive"]
GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
FOLDER_MIME = "application/vnd.google-apps.folder"

REQUIRED_GDRIVE_ENV_KEYS = ["GOOGLE_SERVICE_ACCOUNT_JSON", "GDRIVE_SHARED_DRIVE_ID"]


def require_gdrive_keys(env: dict) -> None:
    missing = [k for k in REQUIRED_GDRIVE_ENV_KEYS if not env.get(k)]
    if missing:
        sys.exit(f"[error] .env missing required Google Drive keys: {', '.join(missing)}")


def build_drive_service(env: dict):
    """Build an authenticated Drive v3 service from the service-account JSON."""
    require_gdrive_keys(env)
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    sa_path = pathlib.Path(os.path.expanduser(env["GOOGLE_SERVICE_ACCOUNT_JSON"]))
    if not sa_path.is_file():
        sys.exit(f"[error] GOOGLE_SERVICE_ACCOUNT_JSON not found: {sa_path}")
    creds = service_account.Credentials.from_service_account_file(str(sa_path), scopes=SCOPES)
    # cache_discovery=False avoids the noisy file-cache warning on py3.13.
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _esc(name: str) -> str:
    """Escape a value for a Drive query 'name = ...' clause."""
    return name.replace("\\", "\\\\").replace("'", "\\'")


def ensure_competitor_folder(svc, env: dict, competitor: str, cache: dict | None = None) -> str:
    """Create-once a <competitor> folder in the Shared Drive (or under GDRIVE_ROOT_FOLDER_ID).
    Returns the folder id. Search-by-name first so two machines don't make duplicates."""
    if cache is not None and competitor in cache:
        return cache[competitor]
    drive_id = env["GDRIVE_SHARED_DRIVE_ID"]
    parent = env.get("GDRIVE_ROOT_FOLDER_ID") or drive_id
    q = (f"name = '{_esc(competitor)}' and mimeType = '{FOLDER_MIME}' "
         f"and '{parent}' in parents and trashed = false")
    resp = svc.files().list(
        q=q, corpora="drive", driveId=drive_id,
        includeItemsFromAllDrives=True, supportsAllDrives=True,
        fields="files(id,name)", pageSize=10).execute()
    files = resp.get("files", [])
    if files:
        fid = files[0]["id"]
    else:
        meta = {"name": competitor, "mimeType": FOLDER_MIME, "parents": [parent]}
        fid = svc.files().create(body=meta, supportsAllDrives=True, fields="id").execute()["id"]
    if cache is not None:
        cache[competitor] = fid
    return fid


def upload_docx_as_gdoc(svc, env: dict, docx_path, title: str, parent_folder_id: str) -> tuple[str, str]:
    """Upload a .docx and CONVERT it to a native Google Doc inside the Shared Drive.
    Returns (file_id, web_view_link)."""
    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(str(docx_path), mimetype=DOCX_MIME, resumable=True)
    body = {"name": title, "mimeType": GOOGLE_DOC_MIME, "parents": [parent_folder_id]}
    created = svc.files().create(
        body=body, media_body=media,
        supportsAllDrives=True, fields="id, webViewLink").execute()
    return created["id"], created.get("webViewLink", "")


def set_link_permission(svc, env: dict, file_id: str) -> str:
    """Apply link-sharing per GDRIVE_LINK_SHARING. Returns the mode actually applied
    ('anyone' | 'domain' | 'inherited'). Falls back anyone -> domain -> inherited if a
    Workspace policy blocks the broader scope (so collaboration degrades gracefully)."""
    from googleapiclient.errors import HttpError
    mode = (env.get("GDRIVE_LINK_SHARING") or "anyone").strip().lower()
    order = {"anyone": ["anyone", "domain"], "domain": ["domain"], "none": []}.get(mode, ["anyone", "domain"])
    for m in order:
        try:
            if m == "anyone":
                body = {"type": "anyone", "role": "writer"}
            else:  # domain
                if not env.get("GDRIVE_DOMAIN"):
                    continue
                body = {"type": "domain", "role": "writer", "domain": env["GDRIVE_DOMAIN"]}
            svc.permissions().create(
                fileId=file_id, body=body,
                supportsAllDrives=True, sendNotificationEmail=False, fields="id").execute()
            return m
        except HttpError:
            continue
    return "inherited"  # Shared-Drive members can still open it


def file_exists(svc, file_id: str) -> bool:
    """True if the file id still resolves and isn't trashed."""
    from googleapiclient.errors import HttpError
    try:
        meta = svc.files().get(fileId=file_id, supportsAllDrives=True, fields="id,trashed").execute()
        return not meta.get("trashed", False)
    except HttpError as e:
        if getattr(e, "resp", None) is not None and e.resp.status in (403, 404):
            return False
        raise


def find_doc_in_folder(svc, env: dict, name: str, parent_folder_id: str) -> tuple[str | None, str | None]:
    """Find a Google Doc by exact name in a folder (to adopt a doc made by a prior run elsewhere)."""
    drive_id = env["GDRIVE_SHARED_DRIVE_ID"]
    q = (f"name = '{_esc(name)}' and mimeType = '{GOOGLE_DOC_MIME}' "
         f"and '{parent_folder_id}' in parents and trashed = false")
    resp = svc.files().list(
        q=q, corpora="drive", driveId=drive_id,
        includeItemsFromAllDrives=True, supportsAllDrives=True,
        fields="files(id,webViewLink)", pageSize=10).execute()
    files = resp.get("files", [])
    if files:
        return files[0]["id"], files[0].get("webViewLink", "")
    return None, None


def get_web_view_link(svc, file_id: str) -> str:
    meta = svc.files().get(fileId=file_id, supportsAllDrives=True, fields="webViewLink").execute()
    return meta.get("webViewLink", "")


def export_doc_text(svc, file_id: str) -> str:
    """Export a Google Doc as plain text — the team's LIVE edited content (localization
    reads this as the source of truth, not the originally-generated sidecar)."""
    data = svc.files().export(fileId=file_id, mimeType="text/plain").execute()
    if isinstance(data, bytes):
        return data.decode("utf-8", "replace")
    return str(data)


def list_unresolved_comments(svc, file_id: str) -> list[str]:
    """Return the text of UNRESOLVED comment threads on a Doc — these are binding
    localization instructions from the reviewer (resolved threads are ignored)."""
    out: list[str] = []
    try:
        resp = svc.comments().list(
            fileId=file_id, fields="comments(content,resolved,quotedFileContent/value)",
            pageSize=100).execute()
    except Exception:
        return out
    for c in resp.get("comments", []):
        if c.get("resolved"):
            continue
        body = (c.get("content") or "").strip()
        if not body:
            continue
        anchor = ((c.get("quotedFileContent") or {}).get("value") or "").strip()
        out.append(f'on "{anchor[:80]}": {body}' if anchor else body)
    return out
