# tools/csv-sync — auto-sync local analysis → one Google Sheet (twice daily)

Pushes the local competitor-ad data into ONE persistent Google Sheet the team reads, so nobody has to
re-upload a CSV by hand. A launchd job runs **twice daily (09:15 + 21:15)** on the canonical clone,
reads the local CSVs (kept fresh by the 9 AM `daily-sync` git pull), and **upserts** two curated,
cross-competitor tabs into **"Supernova Competitor Master"** (auto-created in the existing Shared Drive).

## What's in the sheet
One spreadsheet, three tabs, data tabs **one row per `(Competitor, Ad ID)`** across all competitors:
- **`Overview`** — the decision-scan (21 cols): Verdict · Status · Current/Best Rank · % Time in Top 25% · Days Running · Language · Ad Format · Presenter · Message Angle · Script Reuse · Price Offer? · Ad Copy + links (Video, Supernova Rewrite Doc, Competitor Analysis Doc).
- **`Analysis`** — the full per-ad pivot dataset (36 cols): the entire enriched CSV + Message Angle / Duration (s) / Price Offer?.
- **`Legend`** — auto-generated reference: every column, which tab(s) it's on, and what it means in plain English.

Column headers are **short, self-explanatory display names** mapped at the sheet layer (`OVERVIEW_COLS` / `ANALYSIS_COLS` / `COLUMN_DEFS` in `sync_to_sheets.py`); the internal CSV column names are unchanged. To rename or add a column: edit those mappings, then run once with `--rebuild` (drops + reseeds the two data tabs with the new headers — same spreadsheet/URL; any team notes typed on those tabs are lost, so warn first).

Each row is a **join**: `<comp>_enriched.csv` (the per-ad spine) ⋈ `master/<comp>.csv` (links/copy, canonical creative) ⋈ the transcript sidecar (angle/duration/price). Everything trimmed out stays in git/R2 and is surfaced on request.

**Upsert, not rewrite:** changed rows update in place, new ads append at the bottom — it **never reorders rows or touches columns you add to the right** (your manual notes survive), and the sheet's URL/tabs never change.

## One-time setup
1. **Enable the Google Sheets API** in the same GCP project as the service-account key (`gdrive-sa.json`):
   console.cloud.google.com → APIs & Services → Library → **Google Sheets API** → **Enable**. (The
   service account + Shared Drive from the Google-Docs feature are reused — nothing else to create.)
2. Verify: `python3.13 facebook/scripts/preflight.py --check-sheets --skip-gemini` → expect a green `sheets` line.
3. Seed once (creates the spreadsheet + `sheet_id.json`): `python3.13 tools/csv-sync/sync_to_sheets.py --competitor mysivi` (then open the printed URL).
4. Install the schedule (run from the canonical **MAIN clone**, the single writer):
   `zsh tools/csv-sync/install.sh` → runs twice daily; test now with
   `launchctl kickstart -k gui/$(id -u)/live.gosupernova.csv-sync && sleep 3 && tail -n 8 "$HOME/Library/Application Support/SupernovaCsvSync/sync.log"`.

## Usage
```
python3.13 tools/csv-sync/sync_to_sheets.py --all              # sync every competitor
python3.13 tools/csv-sync/sync_to_sheets.py --competitor mysivi
python3.13 tools/csv-sync/sync_to_sheets.py --competitor mysivi --dry-run   # offline; no Sheets calls
```

## Notes
- **Single writer:** install on the canonical MAIN clone only (like `daily-sync`) so two machines don't race the same sheet. The spreadsheet id lives in the git-tracked `sheet_id.json`, so every clone resolves the same sheet.
- **Change the times:** edit `Hour`/`Minute` in `live.gosupernova.csv-sync.plist.template`, then re-run `install.sh`.
- **Remove:** `zsh tools/csv-sync/uninstall.sh` (leaves the sheet + log untouched).
- **Analysis-first:** a competitor with no `<comp>_enriched.csv` yet contributes nothing (logged) until it's enriched.

## Files
`_gsheets.py` (Sheets v4 client + spreadsheet/tab lifecycle, reuses `facebook/scripts/_gdrive.py`) ·
`sync_to_sheets.py` (the join + upsert engine) · `sync.sh` / `install.sh` / `uninstall.sh` /
`live.gosupernova.csv-sync.plist.template` (the launchd job) · `sheet_id.json` (git-tracked spreadsheet id).
