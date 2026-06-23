# Strategic view — loora (facebook)

*Generated from 124 ads, latest 2026-06-23.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-27 | 51 | 51 | 39 | 0.765 |
| 2026-06-04 | 34 | 9 | 30 | 0.882 |
| 2026-06-11 | 39 | 11 | 35 | 0.897 |
| 2026-06-12 | 38 | 0 | 34 | 0.895 |
| 2026-06-13 | 38 | 0 | 34 | 0.895 |
| 2026-06-14 | 36 | 1 | 33 | 0.917 |
| 2026-06-15 | 45 | 12 | 30 | 0.667 |
| 2026-06-16 | 53 | 10 | 29 | 0.547 |
| 2026-06-17 | 52 | 15 | 29 | 0.558 |
| 2026-06-22 | 53 | 15 | 27 | 0.509 |
| 2026-06-23 | 53 | 0 | 27 | 0.509 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| ai_plus_human | 67 | 30 | 0.448 |
| ai_plus_ai | 54 | 23 | 0.426 |
| other | 3 | 0 | 0.0 |
| split_screen | 67 | 30 | 0.448 |
| TOTAL | 124 | 53 | 0.427 |

*split-screen ads (captured both above and in `loora_raw_format_counts.csv`): 67.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| split-screen | 67 | 30 | 0.448 |
| app-demo | 54 | 23 | 0.426 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 90 | 41 | 0.456 |
| understand-cant-speak | 25 | 8 | 0.32 |
| habit-aspiration | 5 | 3 | 0.6 |
| fear-shame | 1 | 1 | 1.0 |

*Price / offer hook present in 1 of 124 ads. Split-screen role split in `loora_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 121 | 0.438 |
| human_only | 0 | 0.0 |
| paper_translation | 0 | 0.0 |
| other | 3 | 0.0 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 25 | 2 | 51 | 39 | 0.765 |
| 2026-06-01 | 3 | 0 | 9 | 5 | 0.556 |
| 2026-06-08 | 1 | 0 | 12 | 9 | 0.75 |
| 2026-06-15 | 5 | 0 | 37 | 0 | 0.0 |
| 2026-06-22 | 2 | 0 | 15 | 0 | 0.0 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| exact_replica | 58 | 11.5 | 10.9 | 0 | 26 |
| reworded_replica | 10 | 19.5 | 15.4 | 0 | 26 |
| translation_replica | 17 | 20 | 14.5 | 0 | 26 |
| ALL | 85 | 15 | 12.1 | 0 | 26 |

*Fastest replicated group: `loora-g0000` — replica `1399715815299179` (exact_replica) appeared 0 day(s) after the original `1286341193458429`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| loora-g0000 | 18 | 18 | 5 | 0.278 | exact_replica;original;reworded_replica |
| loora-g0001 | 18 | 18 | 7 | 0.389 | exact_replica;original;translation_replica |
| loora-g0002 | 13 | 13 | 3 | 0.231 | exact_replica;original;reworded_replica |
| loora-g0003 | 11 | 11 | 6 | 0.545 | exact_replica;original |
| loora-g0004 | 5 | 5 | 3 | 0.6 | exact_replica;original;reworded_replica |
| loora-g0005 | 5 | 5 | 4 | 0.8 | exact_replica;original |
| loora-g0006 | 4 | 4 | 2 | 0.5 | exact_replica;original |
| loora-g0007 | 4 | 4 | 2 | 0.5 | exact_replica;original |
| loora-g0008 | 3 | 3 | 2 | 0.667 | exact_replica;original |
| loora-g0009 | 3 | 3 | 1 | 0.333 | exact_replica;original;reworded_replica |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `loora_by_language.csv` and `loora_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `loora_by_replication.csv` and the new `loora_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `loora_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

