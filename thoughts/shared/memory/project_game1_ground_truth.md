---
name: project-game1-ground-truth
description: Ground truth for Game 1 validation — Talon Clemons scored 213 on 16 shots, Row D on the right overhead monitor
metadata:
  type: project
---

## Game 1 ground truth — Talon Clemons

**Video:** `Sample Videos/2026 PBA Colony Park Lanes Games Challenge - Non-Champion Event - Game 1.mp4`

**Bowler:** Talon Clemons (target file `clemons.json`). Row D on the right overhead monitor.

**Final score:** 213, **16 shots**

| Frame | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|-------|---|---|---|---|---|---|---|---|---|-----|
| Marks | 9/ | 9/ | 9/ | X | X | X | X | 7 2 | X | 8/ X |
| Running | 19 | 38 | 58 | 88 | 118 | 145 | 164 | 173 | 193 | 213 |
| Shots | 2 | 2 | 2 | 1 | 1 | 1 | 1 | 2 | 1 | 3 |

Three spares to open, four-bagger (F4-F7), open 7-2 in the 8th, strike in the 9th, spare-strike in the 10th.

**Why:** The prior assumption of 18-21 shots was wrong — strikes reduce the shot count. 16 is the exact count confirmed from the overhead scoreboard at video frame 72000. This is the acceptance criterion for the multipass pipeline.

**How to apply:** Pipeline validation target is exactly 16 shots. Any pipeline run producing more than 16 has false positives; fewer has missed shots.

## All bowlers on the pair (from scoreboards)

**Left monitor (A, B, C):** A=237, B=~158, C=178
**Right monitor (D, E):** D=213 (Talon), E=~226

## Pipeline validation status (2026-08-31)

Multipass run #2 found 19 shots (3 false positives). The clustering merged multiple bowlers into one cluster (bowler_01: 99/140 appearances). HSV histogram discrimination is insufficient — confirmed different-bowler Bhattacharyya distances go as low as 0.44, overlapping with same-bowler distances (0.30-0.73). See [[project-identification-strategy]] for the threshold discussion.
