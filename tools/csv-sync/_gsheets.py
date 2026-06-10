"""
_gsheets.py — Google Sheets v4 client + spreadsheet/tab lifecycle for the CSV→Sheet sync.

Reuses the SAME service account + Shared Drive as the Google-Docs feature (facebook/scripts/_gdrive.py).
The SA has no personal Drive quota, so the spreadsheet MUST be created inside the Shared Drive
(via the Drive API, not sheets.spreadsheets.create). Once it exists, all sheets.spreadsheets.* calls
address it by spreadsheetId (the SA's Content-Manager membership grants access).

One-time human step: enable the Google Sheets API in the GCP project (the SA + Shared Drive already
exist). See tools/csv-sync/README.md.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

# Reuse the Drive auth/helpers from facebook/scripts/_gdrive.py.
_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "facebook" / "scripts"))
import _gdrive  # noqa: E402

SHEETS_SCOPES = ["https://www.googleapis.com/auth/drive",
                 "https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_MIME = "application/vnd.google-apps.spreadsheet"
SPREADSHEET_NAME = "Supernova Competitor Master"
MAX_CELL_CHARS = 49_500  # Sheets hard limit is 50k/cell; truncate below it


def build_services(env: dict):
    """Build (drive_v3, sheets_v4) from the same service-account credential."""
    _gdrive.require_gdrive_keys(env)
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    sa = pathlib.Path(os.path.expanduser(env["GOOGLE_SERVICE_ACCOUNT_JSON"]))
    if not sa.is_file():
        sys.exit(f"[error] GOOGLE_SERVICE_ACCOUNT_JSON not found: {sa}")
    creds = service_account.Credentials.from_service_account_file(str(sa), scopes=SHEETS_SCOPES)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    return drive, sheets


def with_backoff(fn, tries: int = 6):
    """Retry a Sheets/Drive call on transient quota/5xx errors (exp backoff + jitter)."""
    from googleapiclient.errors import HttpError
    import random
    last = None
    for attempt in range(tries):
        try:
            return fn()
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", None)
            if status in (429, 500, 503):
                last = e
                time.sleep(min(60, 2 ** attempt) + random.random())
                continue
            raise
    raise last


# ----------------------------------------------------------------------------- spreadsheet lifecycle

def ensure_spreadsheet(drive, sheets, env: dict, sidecar_path: pathlib.Path) -> tuple[str, bool]:
    """Return (spreadsheet_id, is_new). Reuse the sidecar id if it still resolves; else search the
    Shared Drive by name; else create it INSIDE the Shared Drive (Drive API). Always (re)apply sharing."""
    drive_id = env["GDRIVE_SHARED_DRIVE_ID"]
    parent = env.get("GDRIVE_ROOT_FOLDER_ID") or drive_id

    # 1) sidecar
    if sidecar_path.exists():
        try:
            sid = json.loads(sidecar_path.read_text()).get("spreadsheet_id")
        except json.JSONDecodeError:
            sid = None
        if sid and _gdrive.file_exists(drive, sid):
            return sid, False

    # 2) search the Shared Drive by name (adopt an existing sheet if the sidecar was lost)
    safe = SPREADSHEET_NAME.replace("\\", "\\\\").replace("'", "\\'")
    q = (f"name = '{safe}' and mimeType = '{SPREADSHEET_MIME}' "
         f"and '{parent}' in parents and trashed = false")
    resp = with_backoff(lambda: drive.files().list(
        q=q, corpora="drive", driveId=drive_id,
        includeItemsFromAllDrives=True, supportsAllDrives=True,
        fields="files(id,name)", pageSize=10).execute())
    files = resp.get("files", [])
    if files:
        sid = files[0]["id"]
    else:
        # 3) create fresh inside the Shared Drive (SA cannot own files in My Drive)
        body = {"name": SPREADSHEET_NAME, "mimeType": SPREADSHEET_MIME, "parents": [parent]}
        sid = with_backoff(lambda: drive.files().create(
            body=body, supportsAllDrives=True, fields="id").execute())["id"]

    _gdrive.set_link_permission(drive, env, sid)
    return sid, True


def get_tabs(sheets, ssid: str) -> dict:
    """Map of {tab title -> sheetId(gid)}."""
    meta = with_backoff(lambda: sheets.spreadsheets().get(
        spreadsheetId=ssid, fields="sheets(properties(sheetId,title))").execute())
    return {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta.get("sheets", [])}


def ensure_tab(sheets, ssid: str, title: str, tabs: dict) -> None:
    """Create the tab if absent (mutates `tabs`)."""
    if title in tabs:
        return
    res = with_backoff(lambda: sheets.spreadsheets().batchUpdate(
        spreadsheetId=ssid,
        body={"requests": [{"addSheet": {"properties": {"title": title}}}]}).execute())
    gid = res["replies"][0]["addSheet"]["properties"]["sheetId"]
    tabs[title] = gid


def delete_tab(sheets, ssid: str, title: str, tabs: dict) -> None:
    """Delete a tab by title (used to drop the default 'Sheet1' on a fresh spreadsheet)."""
    if title not in tabs:
        return
    with_backoff(lambda: sheets.spreadsheets().batchUpdate(
        spreadsheetId=ssid,
        body={"requests": [{"deleteSheet": {"sheetId": tabs[title]}}]}).execute())
    tabs.pop(title, None)


# ----------------------------------------------------------------------------- value helpers

def a1_quote_title(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


def col_to_a1(idx0: int) -> str:
    """0-based column index -> A1 letters (0->A, 26->AA)."""
    s, n = "", idx0 + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def sanitize_cell(value) -> str:
    s = "" if value is None else str(value)
    if len(s) > MAX_CELL_CHARS:
        s = s[:MAX_CELL_CHARS] + f"… [truncated {len(s) - MAX_CELL_CHARS} chars]"
    return s


def read_tab_values(sheets, ssid: str, title: str) -> list:
    """Whole-tab values (list of rows). Empty list if the tab is empty."""
    res = with_backoff(lambda: sheets.spreadsheets().values().get(
        spreadsheetId=ssid, range=a1_quote_title(title),
        valueRenderOption="UNFORMATTED_VALUE", majorDimension="ROWS").execute())
    return res.get("values", [])


def write_row(sheets, ssid: str, title: str, row_number: int, values: list) -> None:
    rng = f"{a1_quote_title(title)}!A{row_number}:{col_to_a1(len(values) - 1)}{row_number}"
    with_backoff(lambda: sheets.spreadsheets().values().update(
        spreadsheetId=ssid, range=rng, valueInputOption="RAW",
        body={"values": [values]}).execute())


def batch_update_values(sheets, ssid: str, data: list) -> None:
    """data = [{"range": "...!A5:U5", "values": [[...]]}, ...]. Chunked to stay under quotas."""
    CHUNK = 400
    for i in range(0, len(data), CHUNK):
        chunk = data[i:i + CHUNK]
        with_backoff(lambda c=chunk: sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=ssid,
            body={"valueInputOption": "RAW", "data": c}).execute())


def append_rows(sheets, ssid: str, title: str, rows: list) -> None:
    CHUNK = 5000
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        with_backoff(lambda c=chunk: sheets.spreadsheets().values().append(
            spreadsheetId=ssid, range=a1_quote_title(title),
            valueInputOption="RAW", insertDataOption="INSERT_ROWS",
            body={"values": c}).execute())
