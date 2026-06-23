# Strategic view — speakx (facebook)

*Generated from 511 ads, latest 2026-06-23.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-26 | 189 | 189 | 137 | 0.725 |
| 2026-06-04 | 170 | 134 | 127 | 0.747 |
| 2026-06-11 | 184 | 55 | 131 | 0.712 |
| 2026-06-12 | 223 | 47 | 132 | 0.592 |
| 2026-06-13 | 241 | 19 | 132 | 0.548 |
| 2026-06-14 | 230 | 0 | 130 | 0.565 |
| 2026-06-15 | 229 | 1 | 130 | 0.568 |
| 2026-06-16 | 228 | 0 | 131 | 0.575 |
| 2026-06-17 | 253 | 28 | 130 | 0.514 |
| 2026-06-22 | 159 | 3 | 95 | 0.597 |
| 2026-06-23 | 194 | 35 | 95 | 0.49 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| human_only | 296 | 145 | 0.49 |
| ai_plus_human | 186 | 104 | 0.559 |
| other | 21 | 4 | 0.19 |
| ai_plus_ai | 4 | 2 | 0.5 |
| paper_translation | 4 | 4 | 1.0 |
| split_screen | 166 | 102 | 0.614 |
| TOTAL | 511 | 259 | 0.507 |

*split-screen ads (captured both above and in `speakx_raw_format_counts.csv`): 166.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| skit-narrative | 235 | 102 | 0.434 |
| split-screen | 166 | 102 | 0.614 |
| app-demo | 82 | 49 | 0.598 |
| pen-and-paper | 4 | 4 | 1.0 |
| other | 4 | 1 | 0.25 |
| listicle-montage | 2 | 0 | 0.0 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| fear-shame | 181 | 83 | 0.459 |
| speak-correctly | 88 | 53 | 0.602 |
| understand-cant-speak | 79 | 46 | 0.582 |
| habit-aspiration | 63 | 33 | 0.524 |
| translation-practice | 26 | 17 | 0.654 |
| social-proof | 26 | 14 | 0.538 |
| other | 18 | 7 | 0.389 |
| feature-demo | 12 | 5 | 0.417 |

*Price / offer hook present in 250 of 511 ads. Split-screen role split in `speakx_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 190 | 0.558 |
| human_only | 296 | 0.49 |
| paper_translation | 4 | 1.0 |
| other | 21 | 0.19 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 168 | 6 | 189 | 137 | 0.725 |
| 2026-06-01 | 39 | 1 | 134 | 98 | 0.731 |
| 2026-06-08 | 36 | 0 | 121 | 23 | 0.19 |
| 2026-06-15 | 18 | 0 | 29 | 0 | 0.0 |
| 2026-06-22 | 25 | 0 | 38 | 1 | 0.026 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| character_variant | 5 | 0 | 3.2 | 0 | 8 |
| exact_replica | 126 | 9.0 | 10.8 | 0 | 27 |
| reworded_replica | 47 | 9 | 10.0 | 0 | 22 |
| translation_replica | 25 | 9 | 10.4 | 0 | 28 |
| visual_variant | 3 | 8 | 8.3 | 1 | 16 |
| ALL | 206 | 9.0 | 10.3 | 0 | 28 |

*Fastest replicated group: `speakx-g0000` — replica `1293067956117881` (translation_replica) appeared 0 day(s) after the original `1182441817236590`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| speakx-g0000 | 9 | 9 | 7 | 0.778 | exact_replica;original;translation_replica |
| speakx-g0001 | 7 | 7 | 2 | 0.286 | exact_replica;original;reworded_replica;translation_replica |
| speakx-g0002 | 5 | 5 | 3 | 0.6 | original;reworded_replica |
| speakx-g0003 | 5 | 5 | 4 | 0.8 | exact_replica;original;reworded_replica;translation_replica |
| speakx-g0004 | 5 | 5 | 3 | 0.6 | exact_replica;original;translation_replica |
| speakx-g0005 | 5 | 5 | 4 | 0.8 | original;reworded_replica |
| speakx-g0006 | 4 | 4 | 2 | 0.5 | exact_replica;original;reworded_replica |
| speakx-g0007 | 4 | 4 | 2 | 0.5 | exact_replica;original;reworded_replica |
| speakx-g0008 | 4 | 4 | 3 | 0.75 | exact_replica;original;translation_replica |
| speakx-g0009 | 4 | 4 | 0 | 0.0 | original;translation_replica |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `speakx_by_language.csv` and `speakx_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `speakx_by_replication.csv` and the new `speakx_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `speakx_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

