# Supernova Competitor-Ads — Handoff Package

This folder contains everything needed to set up and improve Supernova's competitor-ad
pipelines (Facebook + Google). It's self-contained — hand it to a fresh Claude and say
*"read START-HERE.md and 00_INDEX.md, then help me execute these."*

## Read in this order

1. **`00_INDEX.md`** — the master list of work items, priorities, dependencies, and the
   decisions already made vs. still open. **Start here.**
2. **`01_collaboration_git_r2_repo.md`** — set up one shared Git repo (two folders: facebook +
   google) with heavy media in Cloudflare R2 and all links + run logs in git.
3. **`02_per_page_rank_fix.md`** — make ad rank restart at 1 per Facebook page so winners on
   smaller pages aren't missed.
4. **`03_analysis_system.md`** — the data model and metrics that answer the competitive-
   intelligence questions (volume, winners, format mix, script replication, FB→Google transfer).
5. **`04_google_pipeline_repair.md`** — diagnose and fix the outdated Google pipeline (low
   priority).

## Companion files

- **`REPO-SETUP-PLAN.md`** — the long-form, plain-English rationale behind item 01.
- **`Supernova-Ad-Formats-taxonomy-seed.csv`** — the team's own ad-format sheet; the seed for
  the format taxonomy used in item 03.

## Two decisions to settle with the team before item 03 finishes

- **"Winner" definition** (proposed: live ≥ 15 days AND top-100 per-page rank in any scrape).
- **Format taxonomy** (formalize a fixed list from the seed CSV above).

## Important context

- Each document is standalone and references the real files/line numbers in the pipeline repos.
- Items 01 and 02 can be done in parallel; 03 builds on both; 04 is low priority.
- Facebook is the mature, reliable pipeline; Google is currently outdated.
