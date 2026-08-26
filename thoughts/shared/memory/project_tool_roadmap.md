---
name: project-tool-roadmap
description: What's built, what's in-flight, and what's queued for the game.to.frames CLI tool as of session 2026-05-25.
metadata:
  type: project
---

CLI subcommands and their state as of 2026-05-25:

| Command | Status | Purpose |
|---|---|---|
| `calibrate` | done | Interactive OpenCV-window zone marking on still frames; outputs `VenueCalibration` JSON. |
| `preview` | done | Renders calibrated zones as colored polygon overlays on every video frame; visual verification. |
| `fetch` | done | Resolves a video source argument (local path OR yt-dlp-supported URL) to a local file path. |
| `extract` | done | Find and export per-shot clips. Strategies: `probe` (default) and `linear`. Merges to `<out>/all_shots.mp4` by default; `--no-merge` to skip. |
| `merge` | done | Standalone concatenation of `shot_*.mp4` files in a directory into one merged video. |

**Build-a-BowlerTarget CLI command**: not yet built. Currently invoked via a small Python script that calls `identify.build_bowler_target_from_references`. Could be exposed as `build-bowler --name X --calibration <json> --reference <img>=<lane> ... --out <json>`.

**Format-preset CLI (Task #12)**: partially done.
- Done: `--bowler-lane <name>` option that restricts search to one calibrated lane (Baker support).
- Not yet: `--format <preset>` that bundles probe interval + lane policy + expected-shot-count for `pba-qualifying`, `doubles`, `baker`, `singles-practice`, etc.

**Optimization tasks queued:**
- Downscale + frame-skip combo (estimated 6-9× speedup, no hardware needed). See [[project-performance-constraints]].
- GPU + CUDA torch (estimated 10-50× speedup if NVIDIA GPU available).

**Known issues at session end 2026-05-25:**
- CPU YOLO inference is slow (~200ms/frame). Full extract on 41-min PBA Game 1 takes ~85 min with probe strategy.
- `flush=True` was retrofitted onto pipeline prints after the first long run produced no output for hours — keep it on all long-running pipeline prints. See [[feedback-pipeline-invariants]].
- Color-match threshold for video is **0.30**, not the 0.55 that worked on still references. See [[project-identification-strategy]].

**Why:** Future sessions should be able to pick up the project state without re-reading the chat log. This memory is the single source for "what command does what, what's missing."

**How to apply:** Update this memory whenever a new CLI subcommand lands, an optimization gets implemented, or a known issue is resolved. Pair updates with the actual code change in the same turn.
