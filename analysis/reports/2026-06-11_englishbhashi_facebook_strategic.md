# Strategic view — englishbhashi (facebook)

*Generated from 2 ads, latest 2026-06-11.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-28 | 1 | 1 | 0 | 0.0 |
| 2026-06-11 | 1 | 1 | 0 | 0.0 |

*Only a couple of scrape dates so far, so daily volume is sparse; it densifies as history accrues.*

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| human_only | 2 | 0 | 0.0 |
| split_screen | 0 | 0 | 0.0 |
| TOTAL | 2 | 0 | 0.0 |

*split-screen ads (captured both above and in `englishbhashi_raw_format_counts.csv`): 0.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| app-demo | 2 | 0 | 0.0 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| feature-demo | 2 | 0 | 0.0 |

*Price / offer hook present in 2 of 2 ads. Split-screen role split in `englishbhashi_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 0 | 0.0 |
| human_only | 2 | 0.0 |
| paper_translation | 0 | 0.0 |
| other | 0 | 0.0 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 1 | 1 | 1 | 0 | 0.0 |
| 2026-06-08 | 0 | 0 | 1 | 0 | 0.0 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| exact_replica | 1 | 14 | 14 | 14 | 14 |
| ALL | 1 | 14 | 14 | 14 | 14 |

*Fastest replicated group: `englishbhashi-g0000` — replica `1010725401375687` (exact_replica) appeared 14 day(s) after the original `2009720539619107`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| englishbhashi-g0000 | 2 | 2 | 0 | 0.0 | exact_replica;original |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `englishbhashi_by_language.csv` and `englishbhashi_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `englishbhashi_by_replication.csv` and the new `englishbhashi_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `englishbhashi_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

