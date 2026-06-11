# Strategic view — loora (facebook)

*Generated from 71 ads, latest 2026-06-11.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-27 | 51 | 51 | 39 | 0.765 |
| 2026-06-04 | 34 | 9 | 29 | 0.853 |
| 2026-06-11 | 39 | 11 | 28 | 0.718 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| ai_plus_human | 42 | 26 | 0.619 |
| ai_plus_ai | 26 | 20 | 0.769 |
| other | 3 | 0 | 0.0 |
| split_screen | 42 | 26 | 0.619 |
| TOTAL | 71 | 46 | 0.648 |

*split-screen ads (captured both above and in `loora_raw_format_counts.csv`): 42.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| split-screen | 42 | 26 | 0.619 |
| app-demo | 26 | 20 | 0.769 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 51 | 36 | 0.706 |
| understand-cant-speak | 13 | 6 | 0.462 |
| habit-aspiration | 3 | 3 | 1.0 |
| fear-shame | 1 | 1 | 1.0 |

*Price / offer hook present in 0 of 71 ads. Split-screen role split in `loora_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 68 | 0.676 |
| human_only | 0 | 0.0 |
| paper_translation | 0 | 0.0 |
| other | 3 | 0.0 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 25 | 2 | 51 | 39 | 0.765 |
| 2026-06-01 | 3 | 0 | 9 | 4 | 0.444 |
| 2026-06-08 | 1 | 0 | 11 | 3 | 0.273 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| exact_replica | 30 | 0.0 | 3.5 | 0 | 15 |
| reworded_replica | 3 | 0 | 5 | 0 | 15 |
| translation_replica | 6 | 0.0 | 2.5 | 0 | 15 |
| ALL | 39 | 0 | 3.5 | 0 | 15 |

*Fastest replicated group: `loora-g0000` — replica `1923073918386349` (translation_replica) appeared 0 day(s) after the original `1466680661478322`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| loora-g0000 | 8 | 8 | 6 | 0.75 | exact_replica;original;translation_replica |
| loora-g0001 | 7 | 7 | 5 | 0.714 | exact_replica;original;reworded_replica |
| loora-g0002 | 7 | 7 | 5 | 0.714 | exact_replica;original |
| loora-g0003 | 5 | 5 | 4 | 0.8 | exact_replica;original |
| loora-g0004 | 4 | 4 | 1 | 0.25 | exact_replica;original |
| loora-g0005 | 3 | 3 | 3 | 1.0 | exact_replica;original |
| loora-g0006 | 3 | 3 | 2 | 0.667 | exact_replica;original |
| loora-g0007 | 3 | 3 | 3 | 1.0 | exact_replica;original |
| loora-g0008 | 3 | 3 | 1 | 0.333 | exact_replica;original;reworded_replica |
| loora-g0009 | 2 | 2 | 2 | 1.0 | exact_replica;original |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `loora_by_language.csv` and `loora_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `loora_by_replication.csv` and the new `loora_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `loora_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

