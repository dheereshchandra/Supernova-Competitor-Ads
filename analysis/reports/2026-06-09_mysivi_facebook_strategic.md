# Strategic view — mysivi (facebook)

*Generated from 2005 ads, latest 2026-06-09.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-26 | 1596 | 1596 | 670 | 0.42 |
| 2026-05-27 | 871 | 0 | 245 | 0.281 |
| 2026-05-28 | 853 | 0 | 472 | 0.553 |
| 2026-06-04 | 1417 | 242 | 500 | 0.353 |
| 2026-06-08 | 155 | 142 | 13 | 0.084 |
| 2026-06-09 | 1467 | 25 | 422 | 0.288 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| ai_plus_human | 1159 | 402 | 0.347 |
| human_only | 424 | 94 | 0.222 |
| other | 252 | 101 | 0.401 |
| ai_plus_ai | 127 | 58 | 0.457 |
| paper_translation | 43 | 23 | 0.535 |
| split_screen | 1110 | 372 | 0.335 |
| TOTAL | 2005 | 678 | 0.338 |

*split-screen ads (captured both above and in `mysivi_raw_format_counts.csv`): 1110.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| split-screen | 1110 | 372 | 0.335 |
| skit-narrative | 521 | 177 | 0.34 |
| app-demo | 239 | 81 | 0.339 |
| pen-and-paper | 43 | 23 | 0.535 |
| other | 11 | 3 | 0.273 |
| text-on-screen-only | 9 | 4 | 0.444 |
| listicle-montage | 4 | 1 | 0.25 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 1082 | 351 | 0.324 |
| habit-aspiration | 190 | 59 | 0.311 |
| social-proof | 165 | 49 | 0.297 |
| translation-practice | 145 | 56 | 0.386 |
| fear-shame | 132 | 67 | 0.508 |
| understand-cant-speak | 132 | 41 | 0.311 |
| feature-demo | 50 | 24 | 0.48 |
| other | 41 | 14 | 0.341 |

*Price / offer hook present in 1748 of 2005 ads. Split-screen role split in `mysivi_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 1286 | 0.358 |
| human_only | 424 | 0.222 |
| paper_translation | 43 | 0.535 |
| other | 252 | 0.401 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 355 | 8 | 1596 | 670 | 0.42 |
| 2026-06-01 | 23 | 0 | 242 | 6 | 0.025 |
| 2026-06-08 | 47 | 0 | 167 | 2 | 0.012 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| character_variant | 24 | 0.0 | 0.9 | 0 | 13 |
| exact_replica | 559 | 0 | 1.5 | 0 | 14 |
| reworded_replica | 73 | 0 | 1.5 | 0 | 13 |
| translation_replica | 810 | 0.0 | 1.8 | 0 | 14 |
| visual_variant | 45 | 0 | 3.2 | 0 | 13 |
| ALL | 1511 | 0 | 1.7 | 0 | 14 |

*Fastest replicated group: `mysivi-g0000` — replica `1746202000123337` (translation_replica) appeared 0 day(s) after the original `1001707738963676`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| mysivi-g0000 | 110 | 110 | 56 | 0.509 | exact_replica;original;translation_replica;visual_variant |
| mysivi-g0001 | 102 | 102 | 42 | 0.412 | character_variant;original;reworded_replica;translation_replica |
| mysivi-g0002 | 83 | 83 | 41 | 0.494 | exact_replica;original;reworded_replica;translation_replica |
| mysivi-g0003 | 67 | 67 | 26 | 0.388 | character_variant;exact_replica;original;translation_replica |
| mysivi-g0004 | 44 | 44 | 23 | 0.523 | exact_replica;original;reworded_replica;translation_replica;visual_variant |
| mysivi-g0005 | 34 | 34 | 7 | 0.206 | character_variant;exact_replica;original;reworded_replica;translation_replica;visual_variant |
| mysivi-g0006 | 31 | 31 | 11 | 0.355 | exact_replica;original;translation_replica |
| mysivi-g0007 | 30 | 30 | 6 | 0.2 | exact_replica;original;translation_replica |
| mysivi-g0008 | 25 | 25 | 9 | 0.36 | exact_replica;original;reworded_replica;translation_replica |
| mysivi-g0009 | 24 | 24 | 8 | 0.333 | exact_replica;original;translation_replica |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `mysivi_by_language.csv` and `mysivi_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `mysivi_by_replication.csv` and the new `mysivi_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `mysivi_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

