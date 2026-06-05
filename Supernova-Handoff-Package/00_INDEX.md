# Handoff Index — Open Work Items

*This folder contains self-contained instruction documents from a planning session on the
Supernova competitor-ads pipelines (Facebook + Google). Each document below can be handed to
a fresh Claude on its own — it carries enough context to be executed independently.*

**Background in one line:** Supernova scrapes competitor ads (Meta Ad Library + Google Ads
Transparency Center), stores media in Cloudflare R2, runs AI analysis, and tracks everything
in per-competitor master spreadsheets. Facebook is the mature, reliable pipeline; Google is
currently outdated. Two teammates collaborate across two computers.

---

## The items to resolve

| # | Item | Document | Priority | Depends on |
|---|---|---|---|---|
| 1 | **Collaboration setup** — one shared Git repo with two folders (facebook + google); heavy media stays in R2; all links + run logs in git | `01_collaboration_git_r2_repo.md` (+ long-form `REPO-SETUP-PLAN.md`) | High | — |
| 2 | **Per-page rank fix** — make the ad rank restart at 1 for each Facebook page so winners on smaller pages aren't buried below the top-100 cutoff | `02_per_page_rank_fix.md` | High | — |
| 3 | **Analysis system** — the data model (history log + enrichment columns + format taxonomy) and the metrics that answer the competitive-intelligence questions | `03_analysis_system.md` | High | 1 (storage), 2 (page_rank) |
| 4 | **Google pipeline repair** — the Google scraper is outdated and the last run failed; diagnose and decide repair vs. pause | `04_google_pipeline_repair.md` | Low | — |

---

## How to use these

- Each document is standalone. Hand the relevant one to a fresh Claude with access to the
  repo and say *"execute this handoff document."*
- **Items 1 and 2 can be done in parallel.** Item 3 (analysis) is easiest once both are done,
  because it relies on the git storage (1) and the corrected per-page rank (2).
- **Two decisions need a human before Item 3 can finish** — they're called out in that
  document: (a) the exact "winner" definition, and (b) the canonical format taxonomy.

## Decisions already settled in the planning session

- **Git holds links, R2 holds files.** Every R2 link (videos, images, both Word docs) is
  stored in git as text; the heavy files themselves live in R2 and are pulled on demand.
- **One competitor per person at a time** — each competitor has its own master file, so two
  people on different competitors never clash.
- **Facebook is the source of truth;** Google is secondary until repaired.
- **Local files are never deleted by this setup** — whoever runs a task keeps every video,
  image, and doc on their own machine; git only controls what's *shared*.

## Decisions still open (settle these with the team)

- **"Winner" definition.** Proposed starting point: an ad that is live ≥ 15 days AND reaches
  top-100 *per-page* rank in at least one weekly scrape. Longevity is the stronger signal;
  rank is secondary. (See doc 03.)
- **Format taxonomy.** Seed it from the team's own "Supernova Ad Formats" sheet (the `Type`
  column: translation micro-narrative, scrolling-text AI teaching, pen & paper, news format,
  AI tutor product explainer, etc.). Needs formalizing into a fixed list. (See doc 03.)
