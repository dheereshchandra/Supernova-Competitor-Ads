# Strategic view — mysivi (facebook)

*Generated from 2507 ads, latest 2026-06-26.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-26 | 1596 | 1596 | 715 | 0.448 |
| 2026-05-27 | 871 | 0 | 244 | 0.28 |
| 2026-05-28 | 853 | 0 | 518 | 0.607 |
| 2026-06-04 | 1417 | 242 | 592 | 0.418 |
| 2026-06-08 | 155 | 142 | 71 | 0.458 |
| 2026-06-09 | 1467 | 25 | 607 | 0.414 |
| 2026-06-10 | 1118 | 81 | 529 | 0.473 |
| 2026-06-11 | 1117 | 0 | 529 | 0.474 |
| 2026-06-12 | 370 | 21 | 305 | 0.824 |
| 2026-06-13 | 1112 | 48 | 546 | 0.491 |
| 2026-06-14 | 471 | 3 | 375 | 0.796 |
| 2026-06-15 | 1125 | 25 | 545 | 0.484 |
| 2026-06-16 | 1229 | 133 | 536 | 0.436 |
| 2026-06-17 | 1167 | 7 | 536 | 0.459 |
| 2026-06-22 | 1157 | 108 | 520 | 0.449 |
| 2026-06-23 | 1150 | 27 | 509 | 0.443 |
| 2026-06-24 | 1169 | 24 | 509 | 0.435 |
| 2026-06-25 | 1177 | 16 | 509 | 0.432 |
| 2026-06-26 | 1163 | 9 | 504 | 0.433 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| ai_plus_human | 1460 | 523 | 0.358 |
| human_only | 548 | 146 | 0.266 |
| other | 292 | 110 | 0.377 |
| ai_plus_ai | 146 | 69 | 0.473 |
| paper_translation | 61 | 25 | 0.41 |
| split_screen | 1354 | 488 | 0.36 |
| TOTAL | 2507 | 873 | 0.348 |

*split-screen ads (captured both above and in `mysivi_raw_format_counts.csv`): 1354.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| split-screen | 1354 | 488 | 0.36 |
| skit-narrative | 700 | 238 | 0.34 |
| app-demo | 291 | 94 | 0.323 |
| pen-and-paper | 61 | 25 | 0.41 |
| text-on-screen-only | 17 | 4 | 0.235 |
| other | 13 | 6 | 0.462 |
| listicle-montage | 4 | 1 | 0.25 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 1338 | 475 | 0.355 |
| habit-aspiration | 261 | 76 | 0.291 |
| translation-practice | 200 | 72 | 0.36 |
| social-proof | 199 | 73 | 0.367 |
| fear-shame | 170 | 70 | 0.412 |
| understand-cant-speak | 167 | 50 | 0.299 |
| feature-demo | 61 | 24 | 0.393 |
| other | 44 | 16 | 0.364 |

*Price / offer hook present in 2221 of 2507 ads. Split-screen role split in `mysivi_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 1606 | 0.369 |
| human_only | 548 | 0.266 |
| paper_translation | 61 | 0.41 |
| other | 292 | 0.377 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 355 | 8 | 1596 | 715 | 0.448 |
| 2026-06-01 | 23 | 0 | 242 | 55 | 0.227 |
| 2026-06-08 | 94 | 0 | 320 | 99 | 0.309 |
| 2026-06-15 | 56 | 0 | 165 | 0 | 0.0 |
| 2026-06-22 | 37 | 0 | 184 | 4 | 0.022 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| character_variant | 26 | 0.0 | 2.9 | 0 | 27 |
| exact_replica | 706 | 0.0 | 1.5 | 0 | 17 |
| reworded_replica | 113 | 0 | 7.5 | 0 | 30 |
| translation_replica | 969 | 0 | 4.7 | 0 | 30 |
| visual_variant | 61 | 0 | 7.0 | 0 | 21 |
| ALL | 1875 | 0 | 3.7 | 0 | 30 |

*Fastest replicated group: `mysivi-g0000` — replica `1845750346108706` (translation_replica) appeared 0 day(s) after the original `1023669149983656`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| mysivi-g0000 | 116 | 116 | 55 | 0.474 | character_variant;original;reworded_replica;translation_replica |
| mysivi-g0001 | 112 | 112 | 66 | 0.589 | exact_replica;original;translation_replica;visual_variant |
| mysivi-g0002 | 100 | 100 | 51 | 0.51 | exact_replica;original;reworded_replica;translation_replica |
| mysivi-g0003 | 67 | 67 | 33 | 0.493 | character_variant;exact_replica;original;translation_replica |
| mysivi-g0004 | 48 | 48 | 26 | 0.542 | exact_replica;original;reworded_replica;translation_replica;visual_variant |
| mysivi-g0005 | 38 | 38 | 10 | 0.263 | character_variant;exact_replica;original;reworded_replica;translation_replica;visual_variant |
| mysivi-g0006 | 36 | 36 | 9 | 0.25 | exact_replica;original;reworded_replica;translation_replica |
| mysivi-g0007 | 35 | 35 | 13 | 0.371 | exact_replica;original;translation_replica |
| mysivi-g0008 | 34 | 34 | 16 | 0.471 | exact_replica;original;translation_replica |
| mysivi-g0009 | 33 | 33 | 13 | 0.394 | exact_replica;original;reworded_replica;translation_replica |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `mysivi_by_language.csv` and `mysivi_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `mysivi_by_replication.csv` and the new `mysivi_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `mysivi_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

