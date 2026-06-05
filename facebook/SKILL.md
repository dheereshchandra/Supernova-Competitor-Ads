---
name: facebook-ad-downloader
description: >-
  Bulk-download videos from the Facebook Ad Library. Use this skill whenever the
  user provides Facebook ad library IDs, Ad Library page links
  (facebook.com/ads/library/?id=...), signed fbcdn.net video URLs, or a Google
  Sheet / spreadsheet of Facebook ads and wants the creative videos downloaded,
  re-downloaded, saved, or organized into a folder. Trigger on requests like
  "download these Facebook ads", "grab the videos for these library IDs",
  "re-download these ad creatives", "pull the videos from this sheet of FB ads",
  or "save these competitor ads" — and trigger even when the user just pastes a
  batch of long numeric IDs (often messy, with suffixes like _1, _2, .mp4.part,
  or Excel scientific notation such as 1.97587E+15) and asks for the videos.
  Also use for collecting competitor ad creatives from Meta / Facebook ads.
---

# Facebook Ad Library Downloader

## What this does

Takes a set of Facebook ad references — library IDs, Ad Library page links, a
Google Sheet, or a spreadsheet — and downloads every ad video into one folder
with a consistent naming scheme. The heavy lifting is done by the bundled
script `scripts/download_fb_ads.py`; your job is to prepare its input, run it,
and report the results clearly.

## The one thing to understand first

A Facebook ad video lives on the CDN behind a **signed, short-lived URL** —
note the `oh` (HMAC signature) and `oe` (hex expiry) query parameters on any
`fbcdn.net` link. The signature is cryptographically bound to the file path
and expires within hours, so a bare CDN path or a stale link will always
return HTTP 403, and there is **no way to forge or transplant a signature**.

The reliable input is therefore the **Ad Library page URL**:
`https://www.facebook.com/ads/library/?id=<libraryId>`. It is stable, and
`yt-dlp`'s `facebook:ads` extractor re-resolves it to a fresh signed CDN URL
on every run. So: whenever you have a library ID, build the page URL — don't
chase CDN links. Don't waste effort trying to "fix" an unsigned `mediaUrl`.

## Workflow

### 1. Make sure the environment is ready

The script needs Python 3.10+, `yt-dlp`, and (for sheets) `requests` /
`openpyxl`. Install once:

```
python3 -m pip install --upgrade --break-system-packages yt-dlp requests openpyxl
```

If `yt-dlp` is not on `PATH` afterwards, it is still callable as
`python3 -m yt_dlp` — the script auto-detects this, so don't get stuck here.
A current `yt-dlp` matters: the `facebook:ads` extractor breaks and gets fixed
often, so an upgrade is always worth doing before a big run.

### 2. Collect the ad references into one input file

The user's input is almost always messy. Gather every reference and write a
plain text file, **one entry per line**, e.g. `ids.txt`. The script accepts and
auto-cleans all of these forms, so you do not need to perfect them by hand:

- bare library IDs — `1816385469321451`
- IDs with version suffixes — `1816385469321451_1`, `..._2`, `..._v2`
- filename-style entries — `1816385469321451.mp4`, `..._1.mp4.part`
- Ad Library page links — `https://www.facebook.com/ads/library/?id=...`
- signed CDN links — `https://video.xx.fbcdn.net/...mp4?oh=...&oe=...`

The script strips suffixes/extensions, reduces each entry to its numeric ID,
de-duplicates, and builds the page URLs. You can also pass a Google Sheet URL,
a `.csv`, or an `.xlsx` directly instead of a text file (see step 4).

### 3. Recover Excel scientific-notation IDs — do this before running

This is the single most common data-quality trap. When ad IDs are pasted out
of Excel or Google Sheets, 16+ digit numbers get mangled into scientific
notation like `1.97587E+15` or `2.09017E+15`. **The exact ID cannot be
recovered from that displayed form** — it has been rounded to ~6 significant
figures.

If you see scientific-notation entries:

1. If you have the **source spreadsheet / sheet** the IDs came from, recover
   each one by matching it against the full-precision IDs there. A value like
   `1.97587E+15` means "a 16-digit ID whose first 6 significant digits round
   to 197587" — usually exactly one ID in the source matches, which makes
   recovery unambiguous.
2. If you have **no source to match against**, you cannot recover the ID.
   Tell the user plainly, list the mangled entries, and ask them to re-export
   that column **formatted as Text** so the digits survive.

The script will detect and warn about scientific-notation entries it can't use,
but recovering them is your job, not the script's. Also advise the user, once,
to format ID columns as Text in future exports — it prevents the whole problem.

### 4. Run the downloader

For a prepared text file of IDs:

```
python3 scripts/download_fb_ads.py ids.txt --out ./fb_ad_videos --batch-size 10
```

Straight from a public Google Sheet (no file prep needed):

```
python3 scripts/download_fb_ads.py "https://docs.google.com/spreadsheets/d/SHEET_ID/edit" \
    --out ./fb_ad_videos --column ad_link
```

`--column` is only for sheets/spreadsheets; it auto-detects `ad_link`-style
columns, so usually you can omit it. Other useful flags: `--limit N` /
`--offset N` to process a chunk at a time, `--ytdlp PATH` for an explicit
binary, `--summary PATH` to relocate the summary CSV.

Keep `--batch-size` modest (around 10). `yt-dlp` fetches a verification cookie
once per invocation, so batching amortizes that cost — but very large batches
and high concurrency trip Facebook's HTTP 429 rate limiting, which makes the
run slower overall, not faster. Don't try to parallelize aggressively.

**Time-limited or sandboxed environments:** if a single invocation would run
longer than the environment allows, process the list in chunks with
`--limit`/`--offset`, or simply re-run the same command. The script is
**resumable** — any ad whose `<libraryId>.mp4` already exists is skipped — so
re-running only ever picks up what is still missing.

### 5. Report results to the user

The script writes, into the output folder:

- the `.mp4` files (see naming below),
- `download_summary.csv` — every entry with its status, version count, detail,
- `failed_ads.txt` — the library IDs that could not be downloaded.

Give the user the **output folder path** and a short tally: how many ads
downloaded, how many video files (multi-version ads produce several), and how
many failed. If anything failed, explain why (see below) rather than just
listing IDs.

## Output naming

A single ad can run several creative variants under one library ID. Files are
named so variants stay grouped:

```
<libraryId>.mp4       primary creative
<libraryId>_v2.mp4    second variant
<libraryId>_v3.mp4    third variant, etc.
```

## Understanding failures

The common failure is `Unable to extract ad data`. Interpret it correctly:

- **Usually permanent.** The ad is no longer published — the advertiser ended
  or deleted it, or Facebook removed it. The Ad Library page then returns no
  creative payload, and no tool (yt-dlp or otherwise) can extract a video.
  Re-running will not help, and forging a CDN URL is not possible.
- **Occasionally transient.** The `facebook:ads` extractor is genuinely flaky:
  the *same* ad can succeed, then fail with this error minutes later, then
  succeed again. The script already does one automatic retry pass per run. For
  ads still failing afterward, a re-run later (different time, updated yt-dlp)
  sometimes recovers a handful more.

So describe leftover failures honestly: "could not extract — most are ads
Facebook no longer publishes, but the extractor is flaky so a later re-run may
recover a few." Don't over-promise recovery, and don't declare every failure
permanently dead either. If the user needs a specific failed ad badly, suggest
they pull it from the advertiser's own Meta Ads account if they have access.

## Don'ts

- Don't try to download from bare/unsigned `fbcdn.net` URLs or rebuild `oh`/`oe`
  signatures — it cannot work, the signature is path-bound and expires.
- Don't crank batch size or concurrency to "go faster" — 429 rate limiting
  makes it slower. ~10 per batch, sequential, is the sweet spot.
- Don't guess at Excel scientific-notation IDs — recover them from the source
  or tell the user you can't.
- Don't ZIP or TAR the output unless the user asks — leave the `.mp4`s loose
  in the folder so they're immediately usable.
