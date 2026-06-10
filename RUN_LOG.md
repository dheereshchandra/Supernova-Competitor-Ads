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
