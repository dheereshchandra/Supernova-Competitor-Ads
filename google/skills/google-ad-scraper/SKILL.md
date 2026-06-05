---
name: google-ad-scraper
description: >-
  Bulk-scrape Google Ads Transparency Center for competitor research. Given one
  or more Google advertiser IDs (the AR... strings), competitor names from the
  built-in map (SpeakX, Duolingo, Busuu, Memrise, MySivi, English Seekho,
  Speak, Loora, Praktika AI), a .txt/.csv/.xlsx file, or a public Google Sheet,
  this skill pulls every creative for each advertiser, downloads the videos
  (signed googlevideo.com mp4s) and images (simgad/googlesyndication), derives
  YouTube watch IDs from the video URLs, and writes a Step-1-compatible CSV
  (`g-ads-{slug}-{date}.csv`) so the downstream Step 2 / Step 3 pipelines work
  unchanged. Trigger on requests like "scrape Google ads for these
  competitors", "pull Google Transparency Center ads", "download Google
  advertiser videos", "run the Google scraper on these AR IDs", or whenever
  the user pastes a list of `AR...` advertiser IDs and wants the assets.
  Replaces the Claude-in-Chrome scraper step — no browser automation needed.
---

# Google Ads Transparency Center Scraper

## ⛔ BEFORE YOU RUN — rate-limit guardrail (do this first)

Google block-lists an IP that scrapes too often. A guardrail enforces a cadence
policy and refuses runs that would breach it. **Before scraping, always run:**

```bash
python3 scripts/scrape_guardrail.py status
```

- Prints **ALLOWED** → proceed.
- Prints **BLOCKED** → do NOT scrape. Tell the operator when the next run is
  allowed (the command prints it) and stop. Only proceed on the operator's
  explicit, repeated confirmation — the scraper itself requires typing `yes`
  twice (or the `--force` flag) to override.

Policy defaults: **1 competitor per run, 24 h between runs, 24 h cooldown after a
429 block.** Recommended cadence: one competitor per day. The scraper calls this
guardrail automatically before any network call and records every run to
`logs/scrape_history.jsonl`, so a breach stops and asks even if you skip the
status check. Full details: `HANDOVER.md` → "Rate-limit operating policy".
Tune the constants at the top of `scripts/scrape_guardrail.py`.

## What this does

Takes a set of Google advertiser IDs (`AR...`) and, for each one, pulls every
ad it has on Google's Ads Transparency Center, downloads the videos and
images, and writes a CSV with the 28-column Step-1 schema downstream
Steps 2+3+4 expect. The work is done by `scripts/scrape_google_ads.py` (lives
alongside the other pipeline scripts at the project root); your job is to
prepare its input, run it, and report results clearly.

## The one thing to understand first

The Transparency Center has a public-but-undocumented internal API:
`POST /anji/_/rpc/SearchService/SearchCreatives` lists an advertiser's
creatives, `POST /anji/_/rpc/LookupService/GetCreativeById` returns the
detail (variants, content URLs, regions). For video ads, the detail's
content URL points at a `displayads-formats.googleusercontent.com/.../content.js`
preview file — a VAST XML body that contains a signed
`https://*.googlevideo.com/videoplayback?...id=<16-hex>&itag=22&source=youtube&...`
mp4 URL. **That URL is signed and short-lived (~5 hours)**, so the script
downloads the mp4 immediately during the same run; it never stores the URL
for later use.

The 16-hex `id` parameter on a googlevideo URL is the YouTube video ID
encoded as 8 raw bytes — base64url-encoding it gives back the standard
11-char YouTube watch ID. This is how the script populates
`youtube_video_id` and `youtube_video_url` without ever touching the rendered
SPA. Verified: `id=98fc7471cc4ff5a8` → `mPx0ccxP9ag` matches the existing
Supernova-scraped data. So Step 2/Step 3 yt-dlp metadata enrichment still
works downstream — the script just gives them a clean youtube.com URL.

Why this approach beats the Claude-in-Chrome flow: no hidden iframes, no
Angular DOM scraping, no 45-second tool-timeout dance, no probe-pass
selector matching. The data comes back as JSON, which is what we wanted all
along.

## Workflow

### 1. Confirm the environment

The script needs Python 3.10+ and the `requests` library. It auto-installs
`requests` (and `openpyxl` if you point it at an .xlsx) the first time it
runs, so you usually don't need to do anything. If you want to install
manually:

```
python3 -m pip install --break-system-packages requests openpyxl
```

No `yt-dlp` needed — the script downloads the mp4 directly off the signed
googlevideo URL. (Step 2 / Step 3 of the downstream pipeline still use
yt-dlp to enrich `youtube_video_title` / `youtube_channel_name` from the
youtube.com watch URL — that part hasn't changed.)

### 2. Pick a source

The script accepts any of:

- one or more bare AR IDs as positional args
  (`AR02221466555617640449 AR01320432650854334465`),
- a `.txt` file with one `AR...` per line (comments with `#` are ignored),
- a `.csv` / `.tsv` / `.xlsx` with an `advertiser_id` column
  (auto-detected — also tries `ar_id`, `advertiser id`),
- a public Google Sheets URL,
- the built-in `--competitor` shortcut for the 9 verified
  Supernova competitors,
- `--all-competitors` to process all 9 in one go.

The competitor map is hard-coded near the top of the script:

| Competitor      | Verified advertiser                              | Location | Advertiser ID            |
|-----------------|--------------------------------------------------|----------|--------------------------|
| MySivi          | NinjaSalary Financial Services Private Limited ⚠ | India    | AR00309923070552834049   |
| SpeakX          | Ivypods Technology Pvt. Ltd ⚠                    | India    | AR02221466555617640449   |
| English Seekho  | Keyaro Edutech Private Limited ⚠                 | India    | AR02289573295139323905   |
| Speak           | Speakeasy Labs, Inc                              | US       | AR00705977088842137601   |
| Loora           | Loora AI LTD                                     | Israel   | AR13725632235724341249   |
| Duolingo        | Duolingo Inc                                     | US       | AR01320432650854334465   |
| Busuu           | Busuu Limited                                    | UK       | AR10122694483049971713   |
| Memrise         | Memrise Ltd                                      | UK       | AR06420837225457516545   |
| Praktika AI     | PRAKTIKA.AI COMPANY                              | US       | AR10065453821808607233   |

(⚠ = brand verifies under a different operating company; confirm with the
brand team before relying on these.)

Edit `COMPETITOR_ADVERTISERS` in the script to add more, or to expand
entries like Loora and Duolingo when their additional verified entities are
confirmed.

### 3. Run

For most operator work, **don't invoke this script directly** — use the
top-level wrapper `bash run_all_competitors.sh` instead. It runs Step 1
for every competitor + Steps 2+3 + the 429 retry pass + the HTML5 capture
pass + final R2 upload, all in one command. See `../../HANDOVER.md §8`.

This script is the right entry point when you need to invoke Step 1 alone
— adding a new competitor, debugging a single advertiser's scrape, or
running with non-default flags.

```
# one competitor, India only, full scrape:
python3 scripts/scrape_google_ads.py --competitor SpeakX --region IN \
    --out ~/Desktop/google-ad-downloader

# multiple bare IDs:
python3 scripts/scrape_google_ads.py \
    AR02221466555617640449 AR01320432650854334465 \
    --slug speakx-duolingo --region IN --out ~/Desktop/google-ad-downloader

# all 9 verified competitors at once (long run — 10-60 min):
python3 scripts/scrape_google_ads.py --all-competitors --region IN \
    --out ~/Desktop/google-ad-downloader

# quick test (cap creatives per advertiser):
python3 scripts/scrape_google_ads.py --competitor Memrise --region IN \
    --limit 5 --out /tmp/gads-test

# CSV only, no asset downloads:
python3 scripts/scrape_google_ads.py --competitor Duolingo --region IN \
    --no-download --out ~/Desktop/google-ad-downloader
```

Useful flags: `--region IN` restricts to ads shown in India (default is
Anywhere); `--limit N` caps creatives per advertiser; `--no-download` skips
the asset fetch and only writes the CSV; `--slug NAME` overrides the output
folder/file naming.

### 4. Output layout

Relative to `--out`:

```
inputs/g-ads-{slug}-{YYYY-MM-DD}.csv      # 28-col CSV matching Step-1 schema
videos/{slug}-{YYYY-MM-DD}/
    {creative_id}.mp4                      # primary variant
    {creative_id}_v2.mp4                   # second variant
    ...
images/{slug}-{YYYY-MM-DD}/
    {creative_id}.jpg                      # primary
    {creative_id}_v2.png                   # variant
    ...
```

The CSV header is the canonical Supernova Step-1 schema (28 columns:
`row_rank`, `competitor_name`, `advertiser_id`, …, `error_tag`) so the
existing `scripts/download_google_ads.py`, master CSV updaters, and Step
3/4 analysis scripts work on it without changes.

### 5. Resumability

Re-runs are safe. The script:

- streams each download to a `.part` file first and renames on success, so a
  killed download doesn't leave a corrupted .mp4;
- skips any video/image whose target file already exists and is >10 KB;
- overwrites the CSV (the API is the source of truth, so this is fine).

So if a long run is interrupted (network, timeout, manual ctrl-c), just
re-run the same command. It picks up only what's missing.

### 6. Report results to the user

Give:

- the path to `inputs/g-ads-{slug}-{date}.csv`,
- the videos/ and images/ folder paths,
- a short tally: "{N} creatives across {M} advertisers, {V} videos
  downloaded, {I} images downloaded, {F} failed".

If anything failed, explain why before listing IDs (see "Failure modes"
below).

## CSV schema

The 28-column header matches what the prior pipeline expected, so the
existing Step 2 (`download_google_ads.py`) and Step 3/4 analysis scripts
read it unchanged. Notable columns and how this scraper fills them:

| Column                       | How the scraper fills it                                                       |
|------------------------------|--------------------------------------------------------------------------------|
| `creative_format`            | `YouTubeVideo` / `Image` / `Text` / `Other`, inferred from variant payload     |
| `creative_last_shown_date`   | From the detail's `4` timestamp                                                |
| `regions_shown`              | Numeric region codes from detail field `17` (e.g. `2356` = India)              |
| `variant_index` / `_count`   | One row per variant; same `(advertiser_id, creative_id)` repeated per variant  |
| `youtube_video_id`           | Derived: base64url of the 8-byte hex `id=` in the signed googlevideo URL       |
| `youtube_video_url`          | `https://www.youtube.com/watch?v={youtube_video_id}` when ID present           |
| `image_url_at_scrape`        | `tpc.googlesyndication.com/archive/simgad/...` from `<img src=>` in variant    |
| `ad_destination_url`         | First non-Google `href` from text-ad content.js (best-effort)                  |
| `youtube_video_title/desc/…` | Left blank — Step 3 enriches these via yt-dlp `--write-info-json` on the URL   |
| `error_tag`                  | Populated when the detail fetch fails — row preserved with empty media fields  |

## Region behaviour

`--region IN` actually filters server-side (the API takes a numeric
geographic targeting code; 2356 = India). The script supports the codes for
`IN, US, GB, CA, AU, DE, FR, JP, BR, ES, IT, MX, ID, PH, AE, SG, PK, BD, LK, NP`.
Add more in `REGION_CODES` if you need them — the full code list lives in
the open-source reverse-engineered library this scraper draws from.

Without `--region`, the API returns the "Anywhere" view, which can include
ads that never ran in the target market. Stay with `--region IN` for the
Supernova competitor work.

## Failure modes

- **`detail-fetch` error_tag**: the detail RPC returned a non-JSON body or a
  4xx. Usually transient. Re-run; the CSV gets rewritten and the script
  re-fetches every detail.
- **Video listed in CSV but no .mp4 in the folder**: the content.js was
  retrieved but no `googlevideo.com` URL was inside it. This happens for
  HTML5 / carousel / app-promo variants that don't use a static video.
  These rows have `youtube_video_id` empty and no local file — that's
  correct, not a bug.
- **`HTTP 429` during downloads**: Google rate-limited the run. The script
  paces itself (200 ms between downloads, 400 ms between API page calls),
  but for a 200-ad advertiser you can still hit a limit on a fresh IP.
  Wait a few minutes and re-run; resumability means only missing files
  refetch.
- **`HTTP 403` on a googlevideo URL**: the signature expired between the
  detail fetch and the download. Very rare in a single run; re-run to get
  fresh signed URLs.

## Don'ts

- Don't try to download a googlevideo URL captured in an old CSV — the
  signatures expire. Always re-run the scraper to get fresh URLs, then
  download in the same invocation.
- Don't crank concurrency to "go faster" — Google's rate-limit kicks in
  fast and a hammered run is slower overall than the paced default.
- Don't edit the script to remove the cookie-warming `GET /` in
  `TransparencyClient.__init__`. Without it, the POST sometimes returns
  `{}`.
- Don't sign into Google before running. The Transparency Center is
  public; signing in changes what's shown.
- Don't ZIP or TAR the output unless asked. Leave the `.mp4`s and images
  loose in the folders so the downstream Step 2 / Step 3 scripts find them.
