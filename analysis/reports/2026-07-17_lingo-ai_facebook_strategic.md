# Strategic view — lingo-ai (facebook)

*Generated from 1191 ads, latest 2026-07-17.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-06-15 | 29 | 29 | 9 | 0.31 |
| 2026-06-16 | 42 | 25 | 12 | 0.286 |
| 2026-06-17 | 93 | 50 | 19 | 0.204 |
| 2026-06-22 | 53 | 35 | 27 | 0.509 |
| 2026-06-23 | 30 | 10 | 13 | 0.433 |
| 2026-06-24 | 105 | 46 | 45 | 0.429 |
| 2026-06-25 | 117 | 35 | 37 | 0.316 |
| 2026-06-26 | 147 | 41 | 49 | 0.333 |
| 2026-06-29 | 109 | 1 | 36 | 0.33 |
| 2026-06-30 | 116 | 22 | 46 | 0.397 |
| 2026-07-01 | 113 | 22 | 36 | 0.319 |
| 2026-07-02 | 159 | 42 | 47 | 0.296 |
| 2026-07-03 | 161 | 64 | 56 | 0.348 |
| 2026-07-04 | 180 | 53 | 52 | 0.289 |
| 2026-07-06 | 162 | 67 | 59 | 0.364 |
| 2026-07-07 | 154 | 55 | 39 | 0.253 |
| 2026-07-08 | 186 | 37 | 58 | 0.312 |
| 2026-07-09 | 233 | 84 | 57 | 0.245 |
| 2026-07-10 | 232 | 90 | 55 | 0.237 |
| 2026-07-11 | 171 | 23 | 56 | 0.327 |
| 2026-07-12 | 176 | 33 | 45 | 0.256 |
| 2026-07-13 | 224 | 85 | 45 | 0.201 |
| 2026-07-14 | 290 | 100 | 30 | 0.103 |
| 2026-07-15 | 179 | 43 | 23 | 0.128 |
| 2026-07-16 | 183 | 58 | 16 | 0.087 |
| 2026-07-17 | 185 | 41 | 29 | 0.157 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| other | 968 | 37 | 0.038 |
| ai_plus_ai | 216 | 34 | 0.157 |
| paper_translation | 4 | 3 | 0.75 |
| human_only | 3 | 2 | 0.667 |
| split_screen | 21 | 10 | 0.476 |
| TOTAL | 1191 | 76 | 0.064 |

*split-screen ads (captured both above and in `lingo-ai_raw_format_counts.csv`): 21.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| skit-narrative | 86 | 19 | 0.221 |
| app-demo | 86 | 10 | 0.116 |
| listicle-montage | 43 | 6 | 0.14 |
| split-screen | 21 | 10 | 0.476 |
| other | 17 | 6 | 0.353 |
| text-on-screen-only | 8 | 2 | 0.25 |
| pen-and-paper | 4 | 3 | 0.75 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 76 | 9 | 0.118 |
| habit-aspiration | 70 | 15 | 0.214 |
| other | 56 | 14 | 0.25 |
| feature-demo | 40 | 17 | 0.425 |
| translation-practice | 23 | 1 | 0.043 |

*Price / offer hook present in 0 of 1191 ads. Split-screen role split in `lingo-ai_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 216 | 0.157 |
| human_only | 3 | 0.667 |
| paper_translation | 4 | 0.75 |
| other | 968 | 0.038 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-06-15 | 83 | 7 | 104 | 21 | 0.202 |
| 2026-06-22 | 104 | 0 | 167 | 35 | 0.21 |
| 2026-06-29 | 0 | 0 | 204 | 18 | 0.088 |
| 2026-07-06 | 0 | 0 | 389 | 2 | 0.005 |
| 2026-07-13 | 0 | 0 | 327 | 0 | 0.0 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| exact_replica | 64 | 8.0 | 5.2 | 0 | 10 |
| reworded_replica | 6 | 0.5 | 2 | 0 | 9 |
| translation_replica | 2 | 0.0 | 0 | 0 | 0 |
| visual_variant | 5 | 1 | 3.4 | 0 | 8 |
| ALL | 77 | 6 | 4.7 | 0 | 10 |

*Fastest replicated group: `lingo-ai-g0000` — replica `27252840764373165` (exact_replica) appeared 0 day(s) after the original `1543351697304303`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| lingo-ai-g0000 | 9 | 9 | 0 | 0.0 | exact_replica;original;reworded_replica |
| lingo-ai-g0001 | 8 | 8 | 8 | 1.0 | exact_replica;original |
| lingo-ai-g0002 | 5 | 5 | 5 | 1.0 | exact_replica;original;visual_variant |
| lingo-ai-g0003 | 4 | 4 | 1 | 0.25 | exact_replica;original |
| lingo-ai-g0004 | 4 | 4 | 0 | 0.0 | exact_replica;original;translation_replica |
| lingo-ai-g0005 | 4 | 4 | 1 | 0.25 | exact_replica;original |
| lingo-ai-g0006 | 4 | 4 | 0 | 0.0 | exact_replica;original |
| lingo-ai-g0007 | 3 | 3 | 1 | 0.333 | exact_replica;original |
| lingo-ai-g0008 | 3 | 3 | 1 | 0.333 | exact_replica;original |
| lingo-ai-g0009 | 3 | 3 | 0 | 0.0 | exact_replica;original |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `lingo-ai_by_language.csv` and `lingo-ai_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `lingo-ai_by_replication.csv` and the new `lingo-ai_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `lingo-ai_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

