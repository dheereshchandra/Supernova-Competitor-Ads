# Handoff 01 — Collaboration Setup: One Git Repo, Two Folders, R2 for Media

**Goal:** let two teammates work the Facebook and Google ad pipelines from separate computers
without transferring 50–60 GB folders around. Achieve this with one shared private Git repo
(the small, precious files) plus Cloudflare R2 (the heavy media, already in use).

> A longer plain-English rationale for everything here lives in `REPO-SETUP-PLAN.md`.
> This document is the executable checklist. Read both; they agree.

---

## The model

- **Git repo** holds the small source of truth: scripts, skills, prompts, the per-competitor
  **master spreadsheets** (which carry every R2 link), per-run inputs, logs, run summaries,
  and the analysis folder.
- **Cloudflare R2** holds all heavy media (videos, images, the built Word docs). These are
  *referenced by link* from the master spreadsheets — the files themselves never go in git.
- Local `videos/` / `images/` / `step4_workspace/` folders are a **rebuildable cache**, never
  committed. Pull them from R2 on demand with `tools/rehydrate.py`.

> Why this is safe for Facebook specifically: FB video CDN links **expire**, so old media
> can't be re-downloaded from old spreadsheets. R2 is the only durable home — which is exactly
> why "keep media in R2, pull on demand" is the right call.

---

## Decisions already made (do not re-litigate)

- Git stores **links, not binary files** (no .docx/.jpg/.mp4 committed). Every link is
  preserved in git; every file is reachable via R2.
- **One competitor per person at a time** (each competitor = its own master file = no clashes).
- `.gitignore` **never deletes local files** — it only controls what's shared.

---

## Target structure

```
supernova-competitor-ads/              ← ONE private Git repo
├── README.md
├── RUN_LOG.md                         ← append-only diary: every run (who/when/what)
├── .gitignore
├── facebook/                          ← move the current fb-ad-downloader folder here
│   ├── scripts/ skills/ scraper_prompt.md HANDOVER.md
│   ├── master/{competitor}.csv        ← committed (all R2 links live here)
│   ├── inputs/  step3_logs/  runs/     ← committed (text)
│   └── videos/ images/ step4_workspace/   ← NOT committed (R2 + rehydrate)
├── google/                            ← move the current Google folder here (secondary)
├── analysis/                          ← shared learnings + analysis (see handoff 03)
└── tools/
    ├── rehydrate.py
    └── log_and_commit.sh
```

---

## Steps

1. **Create a private GitHub repo** `supernova-competitor-ads`. *(The account owner does this
   — creating accounts/repos is a human action.)*

2. **Move both pipeline folders under it:** the Facebook folder → `facebook/`, the Google
   folder → `google/`. Keep each folder's own scripts and masters intact.

3. **Add the root `.gitignore`** (this is the rulebook — keeps secrets, heavy media, and old
   manual `.bak` files out, while KEEPING the link-bearing JSON sidecars):

   ```gitignore
   # Secrets
   **/.env
   # Heavy media — lives in R2, pulled on demand
   **/videos/
   **/images/
   # Step 4 working files: drop the heavy stuff, KEEP the link records (*.json, esp. r2_urls.json)
   **/step4_workspace/.gemini_uploads/
   **/step4_workspace/batches/
   **/step4_workspace/frames/
   **/step4_workspace/logs/
   **/step4_workspace/docs/
   **/step4_workspace/images/**/*.jpg
   **/step4_workspace/images/**/*.png
   # Built docs / spreadsheet locks (links preserved in master CSV)
   **/*.docx
   **/~$*
   **/.~lock.*
   # Old manual backups — git history replaces these
   **/*.bak
   **/*.bak.*
   **/*.pre-*
   **/*.savedcopy
   # OS / Python cruft
   **/.DS_Store
   **/__pycache__/
   **/*.pyc
   ```

4. **Create `RUN_LOG.md`** (empty to start) and a root `README.md` describing the daily flow.

5. **Build `tools/rehydrate.py`** — refills local `videos/`/`images/` from R2 using a master
   CSV. Spec:
   - `--pipeline {facebook|google} --competitor {slug}` → reads `{pipeline}/master/{slug}.csv`.
   - For each row with a non-empty `r2_public_url`: HTTP GET that URL (it is **public — no
     credentials needed**) and save to `videos/{slug}-{date}/` or `images/{slug}-{date}/` using
     the existing variant naming (`{id}.mp4`, `{id}_v2.mp4`, etc.); `{date}` from the row's
     `scrape_run_date` (fallback today). Skip files already present. Print a downloaded/skipped/
     failed tally.

6. **Build `tools/log_and_commit.sh`** — run at the end of every pipeline run. Spec:
   - Args: `<pipeline> <competitor> "<operator name>" "<one-line note>"`.
   - Append a dated entry to `RUN_LOG.md` (format in handoff 03 / REPO-SETUP-PLAN §3).
   - Write a per-run links manifest `{pipeline}/runs/{competitor}_{date}_links.json` collecting
     every R2 link produced this run (source asset + both docx + all Step-4 image URLs), pulled
     from the master row and any `step4_workspace/images/*/r2_urls.json` sidecars.
   - `git add` the master CSV, the run's input CSV, `runs/*`, `step3_logs/*<competitor>*`,
     `RUN_LOG.md`; `git commit --author="<operator> <email>" -m "run: <pipeline>/<competitor> by <operator> — <note>"`; print a "now run: git push" reminder.

7. **Bring every master CSV up to the full link schema** so all Step-4 image/docx links have a
   column (some older masters stop at the two docx columns — add the image-array columns).

8. **First commit + push.** Then your teammate clones the repo and adds their own local `.env`
   (the secrets file is never shared through git).

9. **From then on, the daily loop is:** `git pull` → pick an unclaimed competitor → run the
   pipeline (Step 1 in Chrome; Steps 2–4 on the Mac Terminal) → `tools/log_and_commit.sh …` →
   `git push`.

---

## Acceptance criteria

- Repo clones in seconds and is well under ~150 MB (no videos/images/docx committed).
- `git status` after a normal run shows only small text files staged (master CSV, input CSV,
  run summary, links manifest, RUN_LOG) — never `.mp4`/`.jpg`/`.docx`.
- `tools/rehydrate.py --pipeline facebook --competitor zinglish` repopulates local media from
  R2 with no credentials.
- Every R2 link a run produces appears in the committed master CSV and the run's links manifest.
- Each commit is authored by the person who ran it, with its timestamp (the who/when record).
