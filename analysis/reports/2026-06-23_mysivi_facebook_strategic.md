# Strategic view — mysivi (facebook)

*Generated from 2458 ads, latest 2026-06-23.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-26 | 1596 | 1596 | 714 | 0.447 |
| 2026-05-27 | 871 | 0 | 243 | 0.279 |
| 2026-05-28 | 853 | 0 | 518 | 0.607 |
| 2026-06-04 | 1417 | 242 | 589 | 0.416 |
| 2026-06-08 | 155 | 142 | 71 | 0.458 |
| 2026-06-09 | 1467 | 25 | 604 | 0.412 |
| 2026-06-10 | 1118 | 81 | 525 | 0.47 |
| 2026-06-11 | 1117 | 0 | 525 | 0.47 |
| 2026-06-12 | 370 | 21 | 298 | 0.805 |
| 2026-06-13 | 1112 | 48 | 533 | 0.479 |
| 2026-06-14 | 471 | 3 | 362 | 0.769 |
| 2026-06-15 | 1125 | 25 | 530 | 0.471 |
| 2026-06-16 | 1229 | 133 | 521 | 0.424 |
| 2026-06-17 | 1167 | 7 | 521 | 0.446 |
| 2026-06-22 | 1157 | 108 | 505 | 0.436 |
| 2026-06-23 | 1150 | 27 | 494 | 0.43 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| ai_plus_human | 1433 | 510 | 0.356 |
| human_only | 529 | 144 | 0.272 |
| other | 290 | 110 | 0.379 |
| ai_plus_ai | 145 | 69 | 0.476 |
| paper_translation | 61 | 25 | 0.41 |
| split_screen | 1327 | 481 | 0.362 |
| TOTAL | 2458 | 858 | 0.349 |

*split-screen ads (captured both above and in `mysivi_raw_format_counts.csv`): 1327.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| split-screen | 1327 | 481 | 0.362 |
| skit-narrative | 685 | 231 | 0.337 |
| app-demo | 284 | 93 | 0.327 |
| pen-and-paper | 61 | 25 | 0.41 |
| text-on-screen-only | 17 | 4 | 0.235 |
| other | 13 | 6 | 0.462 |
| listicle-montage | 4 | 1 | 0.25 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 1315 | 465 | 0.354 |
| habit-aspiration | 259 | 76 | 0.293 |
| translation-practice | 196 | 69 | 0.352 |
| social-proof | 193 | 72 | 0.373 |
| understand-cant-speak | 167 | 49 | 0.293 |
| fear-shame | 161 | 70 | 0.435 |
| feature-demo | 56 | 24 | 0.429 |
| other | 44 | 16 | 0.364 |

*Price / offer hook present in 2174 of 2458 ads. Split-screen role split in `mysivi_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 1578 | 0.367 |
| human_only | 529 | 0.272 |
| paper_translation | 61 | 0.41 |
| other | 290 | 0.379 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 355 | 8 | 1596 | 714 | 0.447 |
| 2026-06-01 | 23 | 0 | 242 | 53 | 0.219 |
| 2026-06-08 | 94 | 0 | 320 | 87 | 0.272 |
| 2026-06-15 | 56 | 0 | 165 | 0 | 0.0 |
| 2026-06-22 | 23 | 0 | 135 | 4 | 0.03 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| character_variant | 26 | 0.0 | 2.9 | 0 | 27 |
| exact_replica | 687 | 0 | 1.5 | 0 | 17 |
| reworded_replica | 106 | 0.0 | 6.9 | 0 | 28 |
| translation_replica | 960 | 0.0 | 4.5 | 0 | 28 |
| visual_variant | 61 | 0 | 7.0 | 0 | 21 |
| ALL | 1840 | 0.0 | 3.6 | 0 | 28 |

*Fastest replicated group: `mysivi-g0000` — replica `1845750346108706` (translation_replica) appeared 0 day(s) after the original `1023669149983656`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| mysivi-g0000 | 115 | 115 | 54 | 0.47 | character_variant;original;reworded_replica;translation_replica |
| mysivi-g0001 | 112 | 112 | 65 | 0.58 | exact_replica;original;translation_replica;visual_variant |
| mysivi-g0002 | 100 | 100 | 50 | 0.5 | exact_replica;original;reworded_replica;translation_replica |
| mysivi-g0003 | 67 | 67 | 33 | 0.493 | character_variant;exact_replica;original;translation_replica |
| mysivi-g0004 | 44 | 44 | 26 | 0.591 | exact_replica;original;reworded_replica;translation_replica;visual_variant |
| mysivi-g0005 | 38 | 38 | 10 | 0.263 | character_variant;exact_replica;original;reworded_replica;translation_replica;visual_variant |
| mysivi-g0006 | 36 | 36 | 9 | 0.25 | exact_replica;original;reworded_replica;translation_replica |
| mysivi-g0007 | 35 | 35 | 13 | 0.371 | exact_replica;original;translation_replica |
| mysivi-g0008 | 34 | 34 | 15 | 0.441 | exact_replica;original;translation_replica |
| mysivi-g0009 | 33 | 33 | 12 | 0.364 | exact_replica;original;reworded_replica;translation_replica |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `mysivi_by_language.csv` and `mysivi_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `mysivi_by_replication.csv` and the new `mysivi_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `mysivi_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

