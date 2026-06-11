# Strategic view — mysivi (facebook)

*Generated from 2086 ads, latest 2026-06-11.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-26 | 1596 | 1596 | 682 | 0.427 |
| 2026-05-27 | 871 | 0 | 227 | 0.261 |
| 2026-05-28 | 853 | 0 | 502 | 0.589 |
| 2026-06-04 | 1417 | 242 | 539 | 0.38 |
| 2026-06-08 | 155 | 142 | 15 | 0.097 |
| 2026-06-09 | 1467 | 25 | 495 | 0.337 |
| 2026-06-10 | 1118 | 81 | 409 | 0.366 |
| 2026-06-11 | 1117 | 0 | 409 | 0.366 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| ai_plus_human | 1210 | 427 | 0.353 |
| human_only | 442 | 107 | 0.242 |
| other | 254 | 104 | 0.409 |
| ai_plus_ai | 132 | 58 | 0.439 |
| paper_translation | 48 | 24 | 0.5 |
| split_screen | 1148 | 396 | 0.345 |
| TOTAL | 2086 | 720 | 0.345 |

*split-screen ads (captured both above and in `mysivi_raw_format_counts.csv`): 1148.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| split-screen | 1148 | 396 | 0.345 |
| skit-narrative | 551 | 187 | 0.339 |
| app-demo | 245 | 86 | 0.351 |
| pen-and-paper | 48 | 24 | 0.5 |
| other | 13 | 4 | 0.308 |
| text-on-screen-only | 9 | 4 | 0.444 |
| listicle-montage | 4 | 1 | 0.25 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 1126 | 373 | 0.331 |
| habit-aspiration | 198 | 66 | 0.333 |
| social-proof | 168 | 53 | 0.315 |
| translation-practice | 160 | 61 | 0.381 |
| fear-shame | 137 | 68 | 0.496 |
| understand-cant-speak | 136 | 44 | 0.324 |
| feature-demo | 50 | 23 | 0.46 |
| other | 43 | 14 | 0.326 |

*Price / offer hook present in 1824 of 2086 ads. Split-screen role split in `mysivi_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 1342 | 0.361 |
| human_only | 442 | 0.242 |
| paper_translation | 48 | 0.5 |
| other | 254 | 0.409 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 355 | 8 | 1596 | 682 | 0.427 |
| 2026-06-01 | 23 | 0 | 242 | 33 | 0.136 |
| 2026-06-08 | 87 | 0 | 248 | 5 | 0.02 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| character_variant | 24 | 0.0 | 0.9 | 0 | 13 |
| exact_replica | 570 | 0.0 | 1.6 | 0 | 15 |
| reworded_replica | 81 | 0 | 2.8 | 0 | 15 |
| translation_replica | 829 | 0 | 2.1 | 0 | 15 |
| visual_variant | 49 | 0 | 3.8 | 0 | 15 |
| ALL | 1553 | 0 | 2.0 | 0 | 15 |

*Fastest replicated group: `mysivi-g0000` — replica `1455352729720949` (translation_replica) appeared 0 day(s) after the original `1001707738963676`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| mysivi-g0000 | 112 | 112 | 59 | 0.527 | exact_replica;original;translation_replica;visual_variant |
| mysivi-g0001 | 105 | 105 | 43 | 0.41 | character_variant;original;reworded_replica;translation_replica |
| mysivi-g0002 | 85 | 85 | 46 | 0.541 | exact_replica;original;reworded_replica;translation_replica |
| mysivi-g0003 | 67 | 67 | 27 | 0.403 | character_variant;exact_replica;original;translation_replica |
| mysivi-g0004 | 44 | 44 | 23 | 0.523 | exact_replica;original;reworded_replica;translation_replica;visual_variant |
| mysivi-g0005 | 34 | 34 | 9 | 0.265 | character_variant;exact_replica;original;reworded_replica;translation_replica;visual_variant |
| mysivi-g0006 | 31 | 31 | 12 | 0.387 | exact_replica;original;translation_replica |
| mysivi-g0007 | 31 | 31 | 7 | 0.226 | exact_replica;original;translation_replica |
| mysivi-g0008 | 25 | 25 | 9 | 0.36 | exact_replica;original;reworded_replica;translation_replica |
| mysivi-g0009 | 24 | 24 | 10 | 0.417 | exact_replica;original;translation_replica |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `mysivi_by_language.csv` and `mysivi_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `mysivi_by_replication.csv` and the new `mysivi_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `mysivi_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

