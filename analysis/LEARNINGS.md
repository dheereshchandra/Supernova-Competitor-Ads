# Competitive-Intelligence Learnings

A running, shared knowledge base. Every time you discover something about a
competitor's strategy — or about the pipelines themselves — add a **dated
bullet**. Keep it terse; one insight per line. This becomes the team's
competitive memory and feeds the analysis system (see
`Supernova-Handoff-Package/03_analysis_system.md`).

Format: `- YYYY-MM-DD — [competitor or topic] insight (source).`

---

## Pipeline / operational

- 2026-06-05 — [Google] Binding rate limit is run *frequency*, not requests/min:
  one full sweep from a rested IP is fine (~600 creatives, ~37 min, 0 throttles);
  a second heavy sweep the same day poisons the IP for 24 h+. A guardrail now
  enforces 1 competitor/run + 24 h gaps (source: run logs + scrape_history.jsonl).
- 2026-06-05 — [Google] MySivi's Google/India library is ~97% HTML5 banners
  (559/574 rows `html5-banner-no-mp4`); only ~14 rows are analysable and just one
  is a real video. HTML5 capture is the bottleneck for Google MySivi coverage.
- 2026-06-05 — [Pipelines] Facebook is the source of truth; the Google CLI
  scraper (API-direct since 2026-06-01) replaced the old broken Chrome-extension
  scraper described in handoff doc 04.

## Competitor creative observations

<!-- Add dated bullets here as you learn them, e.g.:
- 2026-06-05 — [Wispr Flow] leans hard on a fear-of-mispronunciation hook (CTA analysis).
- 2026-06-05 — [Praktika] rotates creative roughly every ~2 weeks.
-->
