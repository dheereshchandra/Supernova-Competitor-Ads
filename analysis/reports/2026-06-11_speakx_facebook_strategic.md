# Strategic view — speakx (facebook)

*Generated from 378 ads, latest 2026-06-11.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-26 | 189 | 189 | 137 | 0.725 |
| 2026-06-04 | 170 | 134 | 29 | 0.171 |
| 2026-06-11 | 184 | 55 | 13 | 0.071 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| human_only | 215 | 80 | 0.372 |
| ai_plus_human | 146 | 49 | 0.336 |
| other | 10 | 4 | 0.4 |
| paper_translation | 4 | 2 | 0.5 |
| ai_plus_ai | 3 | 2 | 0.667 |
| split_screen | 136 | 52 | 0.382 |
| TOTAL | 378 | 137 | 0.362 |

*split-screen ads (captured both above and in `speakx_raw_format_counts.csv`): 136.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| skit-narrative | 161 | 53 | 0.329 |
| split-screen | 136 | 52 | 0.382 |
| app-demo | 66 | 29 | 0.439 |
| pen-and-paper | 4 | 2 | 0.5 |
| other | 3 | 0 | 0.0 |
| listicle-montage | 1 | 0 | 0.0 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| fear-shame | 129 | 43 | 0.333 |
| speak-correctly | 73 | 23 | 0.315 |
| understand-cant-speak | 58 | 26 | 0.448 |
| habit-aspiration | 55 | 20 | 0.364 |
| translation-practice | 19 | 8 | 0.421 |
| social-proof | 19 | 8 | 0.421 |
| other | 11 | 3 | 0.273 |
| feature-demo | 7 | 5 | 0.714 |

*Price / offer hook present in 175 of 378 ads. Split-screen role split in `speakx_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 149 | 0.342 |
| human_only | 215 | 0.372 |
| paper_translation | 4 | 0.5 |
| other | 10 | 0.4 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 167 | 6 | 189 | 137 | 0.725 |
| 2026-06-01 | 39 | 1 | 134 | 0 | 0.0 |
| 2026-06-08 | 10 | 0 | 55 | 0 | 0.0 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| exact_replica | 112 | 9.0 | 10.4 | 0 | 16 |
| reworded_replica | 26 | 9.0 | 5.4 | 0 | 16 |
| translation_replica | 16 | 9.0 | 5.1 | 0 | 9 |
| visual_variant | 1 | 16 | 16 | 16 | 16 |
| ALL | 155 | 9 | 9.1 | 0 | 16 |

*Fastest replicated group: `speakx-g0000` — replica `1293067956117881` (translation_replica) appeared 0 day(s) after the original `1182441817236590`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| speakx-g0000 | 9 | 9 | 3 | 0.333 | exact_replica;original;translation_replica |
| speakx-g0001 | 7 | 7 | 2 | 0.286 | exact_replica;original;reworded_replica;translation_replica |
| speakx-g0002 | 5 | 5 | 1 | 0.2 | original;reworded_replica |
| speakx-g0003 | 5 | 5 | 1 | 0.2 | exact_replica;original;reworded_replica;translation_replica |
| speakx-g0004 | 5 | 5 | 2 | 0.4 | original;reworded_replica |
| speakx-g0005 | 4 | 4 | 0 | 0.0 | exact_replica;original;reworded_replica |
| speakx-g0006 | 4 | 4 | 0 | 0.0 | exact_replica;original;reworded_replica |
| speakx-g0007 | 4 | 4 | 1 | 0.25 | exact_replica;original;translation_replica |
| speakx-g0008 | 4 | 4 | 0 | 0.0 | exact_replica;original;reworded_replica |
| speakx-g0009 | 4 | 4 | 0 | 0.0 | exact_replica;original |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `speakx_by_language.csv` and `speakx_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `speakx_by_replication.csv` and the new `speakx_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `speakx_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

