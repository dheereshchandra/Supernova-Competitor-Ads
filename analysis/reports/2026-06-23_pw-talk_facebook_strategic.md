# Strategic view — pw-talk (facebook)

*Generated from 161 ads, latest 2026-06-23.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-06-15 | 23 | 23 | 23 | 1.0 |
| 2026-06-16 | 130 | 107 | 91 | 0.7 |
| 2026-06-17 | 102 | 11 | 81 | 0.794 |
| 2026-06-22 | 120 | 20 | 79 | 0.658 |
| 2026-06-23 | 22 | 0 | 22 | 1.0 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| human_only | 96 | 60 | 0.625 |
| other | 41 | 25 | 0.61 |
| ai_plus_human | 19 | 11 | 0.579 |
| ai_plus_ai | 5 | 1 | 0.2 |
| split_screen | 33 | 23 | 0.697 |
| TOTAL | 161 | 97 | 0.602 |

*split-screen ads (captured both above and in `pw-talk_raw_format_counts.csv`): 33.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| skit-narrative | 60 | 33 | 0.55 |
| split-screen | 33 | 23 | 0.697 |
| app-demo | 23 | 15 | 0.652 |
| text-on-screen-only | 12 | 6 | 0.5 |
| other | 4 | 2 | 0.5 |
| listicle-montage | 2 | 0 | 0.0 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 36 | 28 | 0.778 |
| understand-cant-speak | 22 | 8 | 0.364 |
| habit-aspiration | 22 | 14 | 0.636 |
| fear-shame | 20 | 9 | 0.45 |
| feature-demo | 15 | 8 | 0.533 |
| other | 13 | 8 | 0.615 |
| social-proof | 5 | 3 | 0.6 |
| translation-practice | 1 | 1 | 1.0 |

*Price / offer hook present in 55 of 161 ads. Split-screen role split in `pw-talk_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 24 | 0.5 |
| human_only | 96 | 0.625 |
| paper_translation | 0 | 0.0 |
| other | 41 | 0.61 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-06-15 | 65 | 7 | 141 | 97 | 0.688 |
| 2026-06-22 | 13 | 0 | 20 | 0 | 0.0 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| character_variant | 2 | 0.0 | 0 | 0 | 0 |
| exact_replica | 19 | 1 | 0.7 | 0 | 2 |
| reworded_replica | 23 | 0 | 0.5 | 0 | 2 |
| visual_variant | 11 | 1 | 0.5 | 0 | 1 |
| ALL | 55 | 1 | 0.6 | 0 | 2 |

*Fastest replicated group: `pw-talk-g0001` — replica `1281960683918283` (visual_variant) appeared 0 day(s) after the original `1271072245182250`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| pw-talk-g0000 | 7 | 7 | 3 | 0.429 | exact_replica;original;reworded_replica;visual_variant |
| pw-talk-g0001 | 6 | 6 | 6 | 1.0 | original;visual_variant |
| pw-talk-g0002 | 6 | 6 | 4 | 0.667 | original;reworded_replica;visual_variant |
| pw-talk-g0003 | 4 | 4 | 0 | 0.0 | original;reworded_replica |
| pw-talk-g0004 | 3 | 3 | 3 | 1.0 | original;reworded_replica |
| pw-talk-g0005 | 3 | 3 | 3 | 1.0 | original;reworded_replica |
| pw-talk-g0006 | 3 | 3 | 3 | 1.0 | exact_replica;original |
| pw-talk-g0007 | 3 | 3 | 3 | 1.0 | original;reworded_replica |
| pw-talk-g0008 | 3 | 3 | 2 | 0.667 | exact_replica;original |
| pw-talk-g0009 | 3 | 3 | 2 | 0.667 | exact_replica;original |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `pw-talk_by_language.csv` and `pw-talk_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `pw-talk_by_replication.csv` and the new `pw-talk_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `pw-talk_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

