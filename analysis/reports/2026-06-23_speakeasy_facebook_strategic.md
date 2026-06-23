# Strategic view — speakeasy (facebook)

*Generated from 111 ads, latest 2026-06-23.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-06-22 | 111 | 111 | 39 | 0.351 |
| 2026-06-23 | 30 | 0 | 27 | 0.9 |

*Only a couple of scrape dates so far, so daily volume is sparse; it densifies as history accrues.*

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| ai_plus_human | 93 | 35 | 0.376 |
| ai_plus_ai | 13 | 2 | 0.154 |
| other | 3 | 1 | 0.333 |
| human_only | 2 | 1 | 0.5 |
| split_screen | 65 | 24 | 0.369 |
| TOTAL | 111 | 39 | 0.351 |

*split-screen ads (captured both above and in `speakeasy_raw_format_counts.csv`): 65.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| split-screen | 65 | 24 | 0.369 |
| skit-narrative | 23 | 10 | 0.435 |
| app-demo | 21 | 3 | 0.143 |
| other | 1 | 1 | 1.0 |
| text-on-screen-only | 1 | 1 | 1.0 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 61 | 22 | 0.361 |
| fear-shame | 20 | 9 | 0.45 |
| habit-aspiration | 14 | 3 | 0.214 |
| understand-cant-speak | 6 | 1 | 0.167 |
| social-proof | 5 | 2 | 0.4 |
| translation-practice | 4 | 2 | 0.5 |
| other | 1 | 0 | 0.0 |

*Price / offer hook present in 70 of 111 ads. Split-screen role split in `speakeasy_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 106 | 0.349 |
| human_only | 2 | 0.5 |
| paper_translation | 0 | 0.0 |
| other | 3 | 0.333 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-06-22 | 85 | 5 | 111 | 39 | 0.351 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| character_variant | 1 | 0 | 0 | 0 | 0 |
| exact_replica | 2 | 0.0 | 0 | 0 | 0 |
| reworded_replica | 22 | 0.0 | 0 | 0 | 0 |
| visual_variant | 1 | 0 | 0 | 0 | 0 |
| ALL | 26 | 0.0 | 0 | 0 | 0 |

*Fastest replicated group: `speakeasy-g0000` — replica `2513169462430169` (reworded_replica) appeared 0 day(s) after the original `1354159723277515`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| speakeasy-g0000 | 5 | 5 | 0 | 0.0 | original;reworded_replica |
| speakeasy-g0001 | 4 | 4 | 3 | 0.75 | original;reworded_replica |
| speakeasy-g0002 | 4 | 4 | 2 | 0.5 | original;reworded_replica |
| speakeasy-g0003 | 3 | 3 | 1 | 0.333 | original;reworded_replica |
| speakeasy-g0004 | 3 | 3 | 2 | 0.667 | character_variant;original;reworded_replica |
| speakeasy-g0005 | 3 | 3 | 1 | 0.333 | original;reworded_replica |
| speakeasy-g0006 | 2 | 2 | 2 | 1.0 | exact_replica;original |
| speakeasy-g0007 | 2 | 2 | 1 | 0.5 | original;reworded_replica |
| speakeasy-g0008 | 2 | 2 | 0 | 0.0 | original;reworded_replica |
| speakeasy-g0009 | 2 | 2 | 1 | 0.5 | original;reworded_replica |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `speakeasy_by_language.csv` and `speakeasy_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `speakeasy_by_replication.csv` and the new `speakeasy_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `speakeasy_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

