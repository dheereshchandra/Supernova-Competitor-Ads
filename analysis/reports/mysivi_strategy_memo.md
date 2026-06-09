# MySivi — Competitive Ad Strategy Teardown (Facebook)

*Senior-analyst synthesis · generated 2026-06-09 · 2,005 ads · 1,937 transcripts*

> **Read this caveat first.** "Win" here = ad **longevity + Ad-Library rank** (a revealed-preference proxy — "MySivi kept funding this and Facebook kept surfacing it"). There is **no CTR / conversion / spend** data in the Meta Ad Library, so nothing below is proof of ROAS. It is strong signal about what MySivi *believes* works, not measured performance. "win ratio" = winners / ads in that slice; "winner" = verdict ∈ {winner, strong_winner}.

## Thesis
MySivi runs an **industrialized "translate-and-clone" machine**: a *small* core of proven scripts, blasted **same-day** into 8 Indian languages with cheap AI+human production, discount-led. The machine genuinely **de-risks** (reusing a validated script ~doubles win rate vs inventing fresh). Its two exploitable flaws: it is **misallocated** (pours volume into safe-average defaults, starves its own proven winners) and **blind** (scales on upfront *conviction*, not performance signal). That misallocation + blindness is the opening for Supernova.

---

## The 6 insights that matter

**1. Market > creative — Marathi is the single biggest lever, and it's an *audience* effect.**
Marathi wins **0.545** vs Gujarati **0.199** (z=7.2, p≈0); 14.5% of volume but **23.3% of winners**. Marathi has nearly the same creative/replication mix as Hindi yet wins 0.545 vs Hindi 0.336 — the lift is the **audience, not the script**. *Every* angle and format wins more in Marathi. Tamil is the mirror image — 320 ads (2nd-biggest bet) at a weak 0.263, their largest single misallocation.

**2. *How* you reuse matters — translation beats photocopying.**
Reusing any script (0.35) beats net-new "unique" creative (0.20). Within reuse: **translation_replica 0.41 ≫ exact_replica 0.25**. Exact-copy is their **#2 budget sink** (28% of volume, lowest yield). Light reworking (reworded/character/visual ≈0.42–0.46) beats verbatim cloning. Winning motion = **port a proven ad to a new language**, not run it again.

**3. The machine compounds — but selects blindly. This is the gap.**
Replicas of a *winning* original win **0.443 vs 0.301** when the original lost (+14pts, robust to recency check). Concept quality propagates. **But 83% of replicas launch the same day as the original** — before any signal exists. They bet on the seed at creation and spray 5–100 variants instantly. **Supernova's counter:** cheap small-batch launch → read 48–72h of signal → scale only proven seeds — capture the +14pt compounding *without* funding the ~61% of losing seeds.

**4. fear-shame is underused gold — but language-conditional.**
fear-shame is the **best angle** (0.508 win / 0.82 decided win-share) yet only **7% of volume**; speak-correctly dominates at **54%** but only matches baseline (0.32). The catch: fear-shame over-delivers in **Hindi/Marathi/Malayalam** but **backfires in Telugu (0.125) and Tamil (0.25)** — an angle×language interaction. Lead with it selectively; don't blanket it.

**5. AI-presenter is *cheaper AND better*; human-only is the waste.**
human-only presenters are the worst large slice (**0.23**, -48 winners) — and it's the presenter, not the script (stays weak across replication types). AI formats win ~2× (voiceover-only 0.46, ai-avatar 0.47). Trend confirms it: AI+human "mixed" production climbed **47%→64%** of recent launches.

**6. The machine is shifting — read the trajectory.**
- **English fully abandoned** (8%→0% of recent launches) despite being their *highest*-win segment (0.571) → all-vernacular now.
- **Telugu is the breakout** (0%→20%, now #1 recent language); Gujarati being re-opened (0%→13%) *despite being their worst market* — visible over-extension.
- **Price/offer now near-universal** (73%→95%) + shorter creative → CAC pressure / thin-margin discount-buying.
- **app-screencast scaling** (1.4%→8.4%, "show the app"); **talking-head killed** (11%→2%).
- Just flipped from **explore** (1,530 new scripts in late May) to **harvest** (reusing > new-script ads).

---

## Surprises (flag / pressure-test these)
- **Discounts don't help.** No-offer ads win *more* (0.418 vs 0.333); the "**1 crore users**" claim correlates with a **10-pt lower** win rate (reads generic/spammy). What lifts: "**AI teacher**" framing + "**download**" CTA. → *Sell the mechanism, not the rupee.* **Caveat: the no-offer slice is small (n=189), likely confounded with angle — a hypothesis to test, not proof.**
- **Hook syntax is saturated.** Winners and losers open identically (~73% a question, ~67% "you"). The win is in the **angle/scenario**, not the opening line.
- **Duration is U-shaped.** The common **30–40s middle is the *worst* zone** (0.69); 20–30s (0.84) and 50–90s narrative both win. Median (43s) hides this.
- **Conviction ≠ calibration.** Bigger script groups don't win more per-ad (r=0.03); they keep feeding 34-ad groups that win 20%.

---

## The Supernova playbook

**COPY their proven mechanics:**
- Replication-first: a *small* library of proven angles × wide translation (out-translate, don't out-create).
- AI+human production (cheaper *and* higher-win); dense bilingual karaoke subtitles (sound-off feed); split-screen for comparison angles.

**DIFFERENTIATE where they're weak:**
- **Test-then-scale discipline** — the single biggest edge (capture +14pt compounding, skip the losing-seed tax).
- **Match format to angle**: skit-narrative for emotional/proof (fear-shame), split-screen for comparison/comprehension. Their flat "split-screen everywhere" leaves wins on the table.
- **Lead with fear-shame** (Hindi/Marathi/Malayalam) + feature-demo; sell the **AI-teacher** mechanism.

**Attack the whitespace they're vacating / failing:**
- **English** (0.571 win, they're abandoning it → uncontested).
- **Gujarati / Bengali / Tamil** (they over-invest for weak returns → out-execute).
- **Value-led / longer-form** creative (contrarian vs their 95%-discount short-form → margin-pressure tell).

**Avoid their known dead-ends:** Telugu fear-shame · 30–40s length · "1-crore" claims · human-only talking-head.

---

## Forward question bank (what to ask next)

**Answerable now with committed data:**
- For the *same* hero script, what differs between its winning vs losing languages (the Marathi-wins-where-Bengali-loses puzzle)?
- Is the price-offer penalty real or confounded by angle? (price × angle cross-tab)
- Is fear-shame fatiguing as they scale it? (split by launch-date cohort)
- The exact 20–30s winning recipe — shame cold-open vs correction-skit?

**Need more scrapes over time:**
- Can we **predict a winning original from its first 48–72h** of rank movement — front-run their spray? (needs rank-timeline across more scrape dates)
- Is the explore→harvest cycle predictable? (track new-script velocity weekly)

**Need data we don't have yet (gaps):**
- **Spend/impression-weighted performance** — ad-count overweights cheap clones; the Ad Library gives no impressions (a standing blind spot).
- **Where did English go** — to Google/YouTube? → run the Google scrape + `fb_google_overlap`.
- **How does Supernova compare?** → scrape our own ads to benchmark (currently all competitor, no self-baseline).

---

## Where the numbers come from (reproduce / verify)
- **Per-ad table:** `analysis/derived/facebook/mysivi_enriched.csv` (language, presenter_type, device_format, production_type, replication_type, variant_role, script_group_id, run_days, verdict, …).
- **Creative fields** (message_angle, has_price_offer, duration_s, hooks): per-ad transcripts in `analysis/enrichment/facebook/transcripts/mysivi/<ad_id>.json` — join by `ad_id`.
- **Pre-computed rollups:** `analysis/derived/facebook/mysivi_*.csv`. **Auto report:** `analysis/reports/2026-06-09_mysivi_facebook_strategic.md`.
- The cross-cuts above (angle×language interactions, replication-ROI, portfolio mismatch, language depth, temporal shift, creative hooks) are computed by joining the per-ad table + transcripts; re-runnable offline (no API) by any teammate with the repo.
