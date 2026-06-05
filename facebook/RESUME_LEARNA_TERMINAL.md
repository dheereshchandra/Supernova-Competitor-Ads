# Resume Learna-AI pipeline from Terminal

State at handover (2026-05-30):
- Cowork sandbox broke mid-Step-2 → resuming from Terminal
- 282/490 videos downloaded; CSV indexfixed; master not yet created
- Run all commands from `~/Desktop/fb-ad-downloader/`

## 0. One-time setup (skip if Python 3.10+ and pip already set up)

```bash
cd ~/Desktop/fb-ad-downloader

# Verify Python 3.10+
python3 --version

# Install all dependencies for Steps 2, 3, and 4 in one go
python3 -m pip install --upgrade --break-system-packages --user \
    yt-dlp requests openpyxl boto3 python-docx Pillow google-generativeai

# If pip warned about PATH, add user-scripts dir to PATH (one-time):
echo 'export PATH="$HOME/Library/Python/3.13/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# Verify
yt-dlp --version
python3 -c "import boto3, docx, PIL; print('deps ok')"
```

## 1. Resume Step 2 — download the remaining ~208 videos

The script's pre-skip logic auto-skips any `{id}.mp4` already on disk, so this resumes cleanly from 282/490. Just re-run if it stalls.

```bash
cd ~/Desktop/fb-ad-downloader

python3 scripts/download_fb_ads.py \
    inputs/fb-ads-learna-ai-2026-05-28-1230.csv \
    --out videos/learna-ai-2026-05-28/ \
    --column ad_library_url \
    --batch-size 10
```

If you hit HTTP 429 (rate limit), wait 30 min and re-run the same command.
A handful of IDs return "Unable to extract ad data" — those are deleted/private
ads that won't recover. That's expected; the pipeline tolerates partial sets.

Check progress any time:
```bash
ls videos/learna-ai-2026-05-28/*.mp4 | wc -l
cat videos/learna-ai-2026-05-28/failed_ads.txt 2>/dev/null | wc -l
```

## 2. Step 3 — upload to R2 and build master CSV

Dry-run first to see what would happen (free):

```bash
python3 scripts/upload_to_r2.py \
    --input  inputs/fb-ads-learna-ai-2026-05-28-1230.csv \
    --videos videos/learna-ai-2026-05-28/ \
    --dry-run
```

Then real run (uploads to R2, creates `master/learna-ai.csv`):

```bash
python3 scripts/upload_to_r2.py \
    --input  inputs/fb-ads-learna-ai-2026-05-28-1230.csv \
    --videos videos/learna-ai-2026-05-28/
```

Idempotent — safe to re-run if interrupted.

## 3. Step 4 — cost estimate for random-5 sample (no API calls, free)

```bash
python3 scripts/estimate_step4_cost.py \
    --competitor learna-ai \
    --random 5 \
    --seed 42
```

Review the BATCH TOTAL. Should be ~$1–2. If it looks reasonable, proceed.

## 4. Step 4 — execute the random-5 sample (this is where Gemini $ starts)

Capture the same 5 IDs once and reuse them across all stages:

```bash
# Extract the 5 selected IDs into a shell variable (uses same seed=42)
IDS=$(python3 scripts/estimate_step4_cost.py --competitor learna-ai --random 5 --seed 42 --json \
      | python3 -c "import json,sys; d=json.load(sys.stdin); print(' '.join(e['ad_library_id'] for e in d['estimates']))")
echo "Selected IDs: $IDS"
```

Then run each stage in order:

```bash
# Stage 1 — decompose videos (uploads + submits Gemini batch, then polls)
python3 scripts/step4_decompose.py upload --competitor learna-ai $IDS
python3 scripts/step4_decompose.py submit --competitor learna-ai $IDS
# Note the short_id printed by `submit`, then poll until DONE (re-run every ~60s)
python3 scripts/step4_decompose.py status                    # see active jobs
python3 scripts/step4_decompose.py poll <SHORT_ID_FROM_SUBMIT>

# Stage 2 — extract frames (ffmpeg, instant, free)
python3 scripts/step4_frames.py --competitor learna-ai $IDS

# Stage 3 — character reference sheets (Nano Banana Pro, ~38s/batch)
python3 scripts/step4_character_sheets.py --competitor learna-ai $IDS
# Re-run until output says all sheets present

# Stage 4 — clean panel imagery (Nano Banana Pro, ~38s/batch)
python3 scripts/step4_panels.py --competitor learna-ai $IDS
# Re-run until all panels present

# Stage 5 — Supernova-voice rewrite (Gemini Batch, ~3–5 min queue)
python3 scripts/step4_rewrite.py submit --competitor learna-ai $IDS
python3 scripts/step4_rewrite.py poll <SHORT_ID_FROM_REWRITE_SUBMIT>

# Stage 6 — build the .docx files (python-docx, instant, free)
python3 scripts/step4_build_docs.py --competitor learna-ai $IDS

# Stage 7+8 — upload docs to R2 and back-fill master CSV
python3 scripts/step4_upload_and_update.py --competitor learna-ai $IDS
```

## 5. Verify the final master

```bash
# Confirm every sampled ID has both docx URLs filled in master
python3 -c "
import csv
with open('master/learna-ai.csv', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))
print(f'master total rows: {len(rows)}')
have_video = sum(1 for r in rows if r.get('r2_public_url'))
have_analysis = sum(1 for r in rows if r.get('competitor_analysis_docx_r2_url'))
have_rewrite = sum(1 for r in rows if r.get('supernova_rewrite_docx_r2_url'))
print(f'with r2_public_url:                       {have_video}')
print(f'with competitor_analysis_docx_r2_url:     {have_analysis}')
print(f'with supernova_rewrite_docx_r2_url:       {have_rewrite}')
"
```

## Quick troubleshooting

| Symptom | Fix |
|---|---|
| HTTP 429 mid-Step-2 | Wait 30 min, re-run same command |
| "Unable to extract ad data" | Expected for deleted/private ads — tolerate |
| Step 4 says quota exceeded | Top up Google Cloud billing for Gemini |
| docx looks broken | Re-run `step4_build_docs.py` for that ID only |
| Stalled mid-Step-4 stage | Re-run same stage command — all stages are idempotent |
