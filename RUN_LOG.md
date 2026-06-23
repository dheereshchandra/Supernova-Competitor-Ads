# Run Log

Append-only diary of every pipeline run — **newest at top**. Each entry is
written automatically by `tools/log_and_commit.sh` at the end of a run, and the
commit it creates is the unforgeable who/when record (git stamps the author +
timestamp). The detailed write-up for each run lives in
`{pipeline}/runs/{competitor}_{date}.md`.

Entry format:

```
## YYYY-MM-DD HH:MM TZ — <pipeline> / <competitor> — operator: <name>
- Steps run: <e.g. 2+3 (download + master merge); Creative Studio not run>.
- Result: <new / carry-forward / retired counts; master N → M>.
- R2: <links written / changed>.
- Cost: <$ for Creative Studio, else $0>.
- Full write-up: <pipeline>/runs/<competitor>_<date>.md   ·   commit: <hash>
```

---

<!-- New entries are inserted below this line, newest first. -->

## 2026-06-23 06:22 IST — facebook / zinglish — operator: daily-scrape
- daily free refresh (stages 1-4)
- Links manifest: facebook/runs/zinglish_2026-06-23_links.json


## 2026-06-23 06:20 IST — facebook / speakx — operator: daily-scrape
- daily free refresh (stages 1-4)
- Links manifest: facebook/runs/speakx_2026-06-23_links.json


## 2026-06-23 06:13 IST — facebook / mysivi — operator: daily-scrape
- daily free refresh (stages 1-4)
- Links manifest: facebook/runs/mysivi_2026-06-23_links.json


## 2026-06-22 21:41 IST — facebook / mysivi — operator: Dheeresh (Ad Studio pipeline)
- data refresh via Ad Studio (stages 1-5)
- Links manifest: facebook/runs/mysivi_2026-06-22_links.json


## 2026-06-22 21:40 IST — facebook / mysivi — operator: Dheeresh (Ad Studio pipeline)
- data refresh via Ad Studio (stages 1-5)
- Links manifest: facebook/runs/mysivi_2026-06-22_links.json


## 2026-06-22 21:40 IST — facebook / wispr-flow — operator: Dheeresh (Ad Studio pipeline)
- data refresh via Ad Studio (stages 1-5)
- Links manifest: facebook/runs/wispr-flow_2026-06-22_links.json


## 2026-06-22 20:31 IST — facebook / wispr-flow — operator: Dheeresh (Ad Studio pipeline)
- data refresh via Ad Studio (stages 1-5)
- Links manifest: facebook/runs/wispr-flow_2026-06-22_links.json


## 2026-06-22 18:30 IST — facebook / english-seekho — operator: Dheeresh (Ad Studio pipeline)
- data refresh via Ad Studio (stages 1-5)
- Links manifest: facebook/runs/english-seekho_2026-06-22_links.json


## 2026-06-22 18:15 IST — facebook / mysivi — operator: Dheeresh (Ad Studio pipeline)
- data refresh via Ad Studio (stages 1-5)
- Links manifest: facebook/runs/mysivi_2026-06-22_links.json


## 2026-06-22 15:46 IST — facebook / speakeasy — operator: Claude (on-demand)
- Steps 1-4 (scrape -> download -> R2 -> free analysis). NEW competitor (first run).
- Result: 111 ads (all video), master 0 -> 111; verdicts: 4 strong_winner, 35 winner, 72 new (win ratio 0.351).
- R2: 111 source assets uploaded (0 carried-forward, 0 errors).
- Cost: $0 (no enrichment / Creative Studio).
- Links manifest: facebook/runs/speakeasy_2026-06-22_links.json   ·   commit: (this run)
