# Strategic view — speakx (facebook)

*Generated from 577 ads, latest 2026-06-26.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-26 | 189 | 189 | 137 | 0.725 |
| 2026-06-04 | 170 | 134 | 127 | 0.747 |
| 2026-06-11 | 184 | 55 | 131 | 0.712 |
| 2026-06-12 | 223 | 47 | 152 | 0.682 |
| 2026-06-13 | 241 | 19 | 154 | 0.639 |
| 2026-06-14 | 230 | 0 | 152 | 0.661 |
| 2026-06-15 | 229 | 1 | 152 | 0.664 |
| 2026-06-16 | 228 | 0 | 154 | 0.675 |
| 2026-06-17 | 253 | 28 | 153 | 0.605 |
| 2026-06-22 | 159 | 3 | 118 | 0.742 |
| 2026-06-23 | 194 | 35 | 118 | 0.608 |
| 2026-06-24 | 193 | 27 | 109 | 0.565 |
| 2026-06-25 | 191 | 0 | 108 | 0.565 |
| 2026-06-26 | 229 | 39 | 107 | 0.467 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| human_only | 335 | 157 | 0.469 |
| ai_plus_human | 218 | 111 | 0.509 |
| other | 16 | 8 | 0.5 |
| ai_plus_ai | 4 | 2 | 0.5 |
| paper_translation | 4 | 4 | 1.0 |
| split_screen | 184 | 110 | 0.598 |
| TOTAL | 577 | 282 | 0.489 |

*split-screen ads (captured both above and in `speakx_raw_format_counts.csv`): 184.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| skit-narrative | 281 | 108 | 0.384 |
| split-screen | 184 | 110 | 0.598 |
| app-demo | 88 | 54 | 0.614 |
| other | 5 | 1 | 0.2 |
| pen-and-paper | 4 | 4 | 1.0 |
| listicle-montage | 2 | 0 | 0.0 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| fear-shame | 208 | 90 | 0.433 |
| speak-correctly | 102 | 55 | 0.539 |
| understand-cant-speak | 90 | 47 | 0.522 |
| habit-aspiration | 68 | 33 | 0.485 |
| translation-practice | 32 | 19 | 0.594 |
| social-proof | 30 | 15 | 0.5 |
| other | 21 | 9 | 0.429 |
| feature-demo | 13 | 9 | 0.692 |

*Price / offer hook present in 298 of 577 ads. Split-screen role split in `speakx_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 222 | 0.509 |
| human_only | 335 | 0.469 |
| paper_translation | 4 | 1.0 |
| other | 16 | 0.5 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 168 | 6 | 189 | 137 | 0.725 |
| 2026-06-01 | 39 | 1 | 134 | 98 | 0.731 |
| 2026-06-08 | 38 | 0 | 121 | 46 | 0.38 |
| 2026-06-15 | 18 | 0 | 29 | 0 | 0.0 |
| 2026-06-22 | 42 | 0 | 104 | 1 | 0.01 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| character_variant | 10 | 1.0 | 4.2 | 0 | 22 |
| exact_replica | 148 | 9.0 | 9.9 | 0 | 31 |
| reworded_replica | 62 | 9.0 | 10.3 | 0 | 31 |
| translation_replica | 33 | 9 | 15.4 | 0 | 31 |
| visual_variant | 5 | 16 | 15.6 | 1 | 31 |
| ALL | 258 | 9.0 | 10.6 | 0 | 31 |

*Fastest replicated group: `speakx-g0000` — replica `1293067956117881` (translation_replica) appeared 0 day(s) after the original `1182441817236590`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| speakx-g0000 | 11 | 11 | 7 | 0.636 | exact_replica;original;translation_replica |
| speakx-g0001 | 7 | 7 | 2 | 0.286 | exact_replica;original;reworded_replica;translation_replica |
| speakx-g0002 | 6 | 6 | 3 | 0.5 | exact_replica;original;translation_replica |
| speakx-g0003 | 6 | 6 | 1 | 0.167 | exact_replica;original;translation_replica |
| speakx-g0004 | 5 | 5 | 3 | 0.6 | original;reworded_replica |
| speakx-g0005 | 5 | 5 | 2 | 0.4 | exact_replica;original;reworded_replica |
| speakx-g0006 | 5 | 5 | 4 | 0.8 | exact_replica;original;reworded_replica;translation_replica |
| speakx-g0007 | 5 | 5 | 3 | 0.6 | exact_replica;original;translation_replica |
| speakx-g0008 | 5 | 5 | 4 | 0.8 | original;reworded_replica |
| speakx-g0009 | 4 | 4 | 2 | 0.5 | exact_replica;original;reworded_replica |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `speakx_by_language.csv` and `speakx_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `speakx_by_replication.csv` and the new `speakx_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `speakx_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

