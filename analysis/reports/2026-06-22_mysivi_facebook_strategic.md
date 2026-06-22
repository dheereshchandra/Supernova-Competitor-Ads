# Strategic view — mysivi (facebook)

*Generated from 2431 ads, latest 2026-06-22.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-26 | 1596 | 1596 | 709 | 0.444 |
| 2026-05-27 | 871 | 0 | 242 | 0.278 |
| 2026-05-28 | 853 | 0 | 514 | 0.603 |
| 2026-06-04 | 1417 | 242 | 584 | 0.412 |
| 2026-06-08 | 155 | 142 | 71 | 0.458 |
| 2026-06-09 | 1467 | 25 | 599 | 0.408 |
| 2026-06-10 | 1118 | 81 | 513 | 0.459 |
| 2026-06-11 | 1117 | 0 | 513 | 0.459 |
| 2026-06-12 | 370 | 21 | 275 | 0.743 |
| 2026-06-13 | 1112 | 48 | 509 | 0.458 |
| 2026-06-14 | 471 | 3 | 340 | 0.722 |
| 2026-06-15 | 1125 | 25 | 507 | 0.451 |
| 2026-06-16 | 1229 | 133 | 497 | 0.404 |
| 2026-06-17 | 1167 | 7 | 497 | 0.426 |
| 2026-06-22 | 1157 | 108 | 481 | 0.416 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| ai_plus_human | 1414 | 490 | 0.347 |
| human_only | 527 | 140 | 0.266 |
| other | 284 | 111 | 0.391 |
| ai_plus_ai | 145 | 67 | 0.462 |
| paper_translation | 61 | 24 | 0.393 |
| split_screen | 1310 | 463 | 0.353 |
| TOTAL | 2431 | 832 | 0.342 |

*split-screen ads (captured both above and in `mysivi_raw_format_counts.csv`): 1310.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| split-screen | 1310 | 463 | 0.353 |
| skit-narrative | 681 | 224 | 0.329 |
| app-demo | 284 | 93 | 0.327 |
| pen-and-paper | 61 | 24 | 0.393 |
| other | 13 | 5 | 0.385 |
| text-on-screen-only | 10 | 4 | 0.4 |
| listicle-montage | 4 | 1 | 0.25 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 1300 | 447 | 0.344 |
| habit-aspiration | 252 | 75 | 0.298 |
| translation-practice | 195 | 66 | 0.338 |
| social-proof | 193 | 71 | 0.368 |
| understand-cant-speak | 163 | 47 | 0.288 |
| fear-shame | 160 | 70 | 0.438 |
| feature-demo | 56 | 24 | 0.429 |
| other | 44 | 14 | 0.318 |

*Price / offer hook present in 2146 of 2431 ads. Split-screen role split in `mysivi_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 1559 | 0.357 |
| human_only | 527 | 0.266 |
| paper_translation | 61 | 0.393 |
| other | 284 | 0.391 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 355 | 8 | 1596 | 709 | 0.444 |
| 2026-06-01 | 23 | 0 | 242 | 53 | 0.219 |
| 2026-06-08 | 94 | 0 | 320 | 68 | 0.212 |
| 2026-06-15 | 56 | 0 | 165 | 0 | 0.0 |
| 2026-06-22 | 15 | 0 | 108 | 2 | 0.019 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| character_variant | 26 | 0.0 | 2.9 | 0 | 27 |
| exact_replica | 677 | 0 | 1.5 | 0 | 17 |
| reworded_replica | 100 | 0.0 | 5.7 | 0 | 27 |
| translation_replica | 956 | 0.0 | 4.5 | 0 | 27 |
| visual_variant | 61 | 0 | 7.0 | 0 | 21 |
| ALL | 1820 | 0.0 | 3.5 | 0 | 27 |

*Fastest replicated group: `mysivi-g0000` — replica `1845750346108706` (translation_replica) appeared 0 day(s) after the original `1023669149983656`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| mysivi-g0000 | 114 | 114 | 49 | 0.43 | character_variant;original;reworded_replica;translation_replica |
| mysivi-g0001 | 112 | 112 | 64 | 0.571 | exact_replica;original;translation_replica;visual_variant |
| mysivi-g0002 | 100 | 100 | 48 | 0.48 | exact_replica;original;reworded_replica;translation_replica |
| mysivi-g0003 | 67 | 67 | 33 | 0.493 | character_variant;exact_replica;original;translation_replica |
| mysivi-g0004 | 44 | 44 | 25 | 0.568 | exact_replica;original;reworded_replica;translation_replica;visual_variant |
| mysivi-g0005 | 38 | 38 | 10 | 0.263 | character_variant;exact_replica;original;reworded_replica;translation_replica;visual_variant |
| mysivi-g0006 | 36 | 36 | 8 | 0.222 | exact_replica;original;reworded_replica;translation_replica |
| mysivi-g0007 | 35 | 35 | 13 | 0.371 | exact_replica;original;translation_replica |
| mysivi-g0008 | 34 | 34 | 15 | 0.441 | exact_replica;original;translation_replica |
| mysivi-g0009 | 31 | 31 | 11 | 0.355 | exact_replica;original;translation_replica |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `mysivi_by_language.csv` and `mysivi_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `mysivi_by_replication.csv` and the new `mysivi_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `mysivi_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

