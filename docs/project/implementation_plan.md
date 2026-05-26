# Implementation Plan — turkey.club

## Architecture overview

```
                       ┌──────────────────┐
   --video             │ source.py        │
   (path or URL)  ───► │ resolve_source() │ ───► local Path
                       └──────────────────┘
                                │
                                ▼
                       ┌────────────────────┐
                       │ downscale.py       │
                       │ ensure_downscaled  │ ───► <source>.detect_0.5x.mp4 (cached)
                       └────────────────────┘
                                │
                                ▼
                ┌────────────────────────────────┐
                │ pipeline.py                    │
                │  load VenueCalibration         │
                │  load BowlerTarget             │
                │  scale polygons + params       │
                │                                │
                │  _extract_shots_probe (default)│
                │   ├─ probe loop                │
                │   │   detect_persons (YOLOv8)  │
                │   │   identify_bowler          │
                │   │   ────────────────────     │
                │   │   on HIT: range-expand     │
                │   ▼                            │
                │   _scan_window                 │
                │     full per-frame signals     │
                │     ─ bowler_confidence        │
                │     ─ pose_motion              │
                │     ─ pin_motion               │
                │     ─ ball_reached_pins        │
                │                                │
                │  find_shot_boundaries          │ ──► [ShotSegment]
                │  (state machine: SETUP →       │
                │   onset → impact → settle)     │
                └────────────────────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │ export.py        │
                       │ export_clip x N  │ ───► shot_NN_<lane>.mp4
                       └──────────────────┘  (cut from original source)
                                │
                                ▼ (if --merge)
                       ┌──────────────────┐
                       │ merge.py         │
                       │ merge_clips      │ ───► all_shots.mp4
                       └──────────────────┘
```

## Module map

| Module | Purpose |
|---|---|
| `cli.py` | Typer CLI: `calibrate`, `extract`, `preview`, `fetch`, `merge`. |
| `config.py` | Dataclasses: `VenueCalibration`, `LaneCalibration`, `BowlerTarget`, `SegmentationParameters`. JSON load/save with tuple coercion. |
| `source.py` | Resolve local-path-or-URL via yt-dlp; cache resolution. |
| `downscale.py` | Snap-to-supported-factor validation; ensure cached `<source>.detect_<scale>x.mp4` exists. |
| `calibrate.py` | Interactive OpenCV polygon collector; overlay renderer. |
| `detect.py` | YOLOv8 person detection; foot-in-polygon check; pin-zone frame-diff; (stub) ball motion. |
| `identify.py` | OCR + color-histogram bowler-confidence scoring; build BowlerTarget from references. |
| `segment.py` | `LaneFrameSignals`, `ShotSegment`, `find_shot_boundaries` state machine. |
| `pipeline.py` | End-to-end orchestration; linear + probe-then-range strategies. |
| `export.py` | ffmpeg frame-accurate clip cut; streamed-stderr ffmpeg runner. |
| `merge.py` | ffmpeg concat of per-shot clips. |

## Phase plan and status

| Phase | Subject | Status | Notes |
|---|---|---|---|
| 0 | Project scaffold (pyproject.toml, src layout, CLI skeleton, stubs) | ✅ Done | `pip install -e .` exposes `turkey-club` entry point. |
| 1 | Interactive calibration (`calibrate`, `preview`) | ✅ Done | Per-lane reference images supported. |
| 2 | Video source resolution (local + yt-dlp) | ✅ Done | Smoke-test against a YouTube URL remains a TODO (Task #4 in the live task list — not blocking). |
| 3 | Person detection (YOLOv8n + foot-in-polygon) | ✅ Done | First-run downloads `yolov8n.pt`. |
| 4 | Bowler identification (HSV histogram + OCR) | ✅ Done | Color histogram is primary; OCR disabled in pipeline path. Threshold 0.30 (not 0.55) for real video. |
| 5 | Ball & pin motion primitives | ✅ Done | Pin-motion frame-diff is sufficient; ball detection stays placeholder. |
| 6 | Shot boundary state machine (`find_shot_boundaries`) | ✅ Done | Synthetic-signal smoke test verifies exact frame indices. |
| 7 | Pipeline orchestration + clip export | ✅ Done | Linear + probe strategies; ffmpeg frame-accurate cuts. |
| 8 | End-to-end validation on Game 1 | 🟨 In flight | First probe-strategy run found ground-truth shot at 1:35; full run pending after the latest threshold + downscale changes. |
| 9 | Optimization — probe-then-range search | ✅ Done | Includes the strict-forward-progress + dedup bug fix discovered during validation. |
| 10 | Optimization — downscale cache | ✅ Done | `<source>.detect_<scale>x.mp4` auto-cached + reused. CLI snap-to-supported-factor with confirmation. |
| 11 | Optimization — merge as default | ✅ Done | `--merge / --no-merge`; standalone `merge` subcommand still available. |
| 12 | Optimization — ffmpeg live stderr streaming | ✅ Done | `_run_ffmpeg_streamed`; `\r` → `\n` translation via text-mode reads. |
| 13 | Format presets (`--format <preset>`) | 🟨 Partial | `--bowler-lane` available; preset bundling not yet wired. |
| 14 | `build-bowler` CLI subcommand | ⬜ Not started | Currently invoked via small Python script using `identify.build_bowler_target_from_references`. |
| 15 | Frame-skip in range-expand windows | ⬜ Not started | Estimated additional ~3× speedup on top of downscale. Requires re-tuning `stationary_pose_frames` / `pin_settle_frames`. |
| 16 | Motion-gate YOLO via background subtraction | ⬜ Not started | Estimated ~2× speedup in dead-time regions. |
| 17 | Optional GPU acceleration (CUDA torch) | ⬜ Not started | Hardware-dependent; not required for project goals. |
| 18 | Format auto-detect from prefix scan | ⬜ Not started | Useful when `--format` isn't provided for singles-practice / open. |

## Dependencies between phases

```
0 → 1 → 7 → 8
0 → 2 → 7
0 → 3 → 4 → 7
0 → 3 → 5 → 6 → 7
7 → 9 (probe optimization)
7 → 10 (downscale optimization, refactors pipeline.extract_shots signature)
7 → 11 (merge default)
9, 10, 11 → 12 (streaming stderr)
13 ── future, depends on no completed phase
14 ── future, independent
15 ── future, depends on 10
16 ── future, depends on 10
17 ── future, independent
18 ── future, depends on 4
```

## Test strategy

- **Unit-style smoke tests** (`tests/test_smoke.py`): CLI loads + all modules import + `resolve_source` round-trips local files.
- **Synthetic-signal tests for the state machine**: feed canned per-frame signal arrays to `find_shot_boundaries` and assert exact frame indices.
- **Snap-factor validation**: `snap_downscale_factor` interactively verified against the supported set (`{1.0, 0.75, 0.5, 0.4, 0.33, 0.25}`) — automation-friendly tests should be added.
- **End-to-end validation on Game 1** (Phase 8): the primary acceptance test. Ground truth is the first-shot timestamp (~1:35) provided by the project owner; eventual expectation is 18–21 shots total.
- **Cross-game validation** (planned post-Phase 8): repeat the end-to-end on Games 2–6 of the same match set, with the same calibration and bowler target.

## Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| CPU YOLO is too slow for routine use | High | Downscale cache (done); frame-skip + motion-gate optimizations queued. GPU is the long-term fallback. |
| Color histogram drifts on lighting changes between matches | Medium | Build target from multiple reference frames per bowler; tune threshold per-video if needed. |
| Calibration becomes stale if the camera moves mid-match | Medium | The fixed-camera assumption is explicit; recalibration is a one-time per-setup cost. |
| OCR cannot read cursive jerseys reliably | Mitigated | Color histogram primary; OCR disabled in pipeline by default; documented in `project_identification_strategy` memory. |
| Probe-then-range infinite loop on premature shot end | Mitigated | Strict-forward-progress invariant added; dedup by (start_frame, lane_name). |
| Block-buffered prints hide progress on background runs | Mitigated | `flush=True` on all pipeline prints; ffmpeg `-stats` + line-streamed stderr. |
| Format auto-detect could mis-classify a singles-practice as Baker | Open | Plan to require explicit `--format` for ambiguous cases; auto-detect only when prefix scan is conclusive. |

## Definition of done (per phase)

| Phase | Done when … |
|---|---|
| 1 (calibrate) | Both reference images for Clemons (left.jpg, right.jpg) calibrated; overlay preview visually verified. |
| 4 (identify) | Clemons scores ≥ 0.30 on real-video frames where he's in approach; teammates score lower. |
| 6 (segment) | Synthetic-signal test passes with exact start/end frame indices. |
| 7 (pipeline) | First probe-strategy run on Game 1 produces at least one shot that lines up with the user-provided ground truth (1:35). |
| 8 (validate) | Game 1 produces 18-21 shots; first shot start within ±15 frames of frame 2850; manual spot-check of 3 clips confirms tight start/end. |
| 9 (probe) | No infinite loop; per-game wall time at default settings ≤ probe-estimated budget. |
| 10 (downscale) | Cached file is created on first run, reused on second; output clips have full source resolution. |
| 13 (format) | `--format baker` automatically restricts to single lane; expected-shot-count sanity warning fires when output is wildly off. |

## Open questions

- **How aggressive should the default downscale be?** Currently 0.5; 0.25 would be ~2× faster but pin polygons start to lose resolution. Decision pending end-to-end validation comparison.
- **Should we cache the YOLO model weights and PyTorch CPU model at a project-scoped path** so the per-laptop ultralytics default doesn't get rewritten by other projects? Low priority.
- **Cross-game validation**: should Games 2–6 share the same calibration as Game 1? If the camera moved at all, results will diverge. Plan to use the overlay-preview command as the first check on each new game.
- **Format auto-detect heuristic**: probe a 30-second prefix; if shots appear on both lanes → cross-lane format; if only one → Baker / singles-practice. False positive risk if the prefix is unusual.

## Maintenance & extensibility hooks

- New formats can be added to a `FORMAT_PRESETS` dict (planned) with `(probe_interval_seconds, lane_policy, expected_shot_count_range)` tuples.
- New search strategies can be added by writing a `_extract_shots_<name>` function in `pipeline.py` and adding a `Strategy = Literal[...]` member.
- New per-frame signals (e.g., MediaPipe Pose keypoints, or learned bowler-ReID embedding) can be added by extending `LaneFrameSignals` and `_update_lane_signals` — `find_shot_boundaries` only needs the four scalar streams.
- New target-identification strategies (e.g., person ReID model embeddings) plug in by modifying `identify.identify_bowler_in_frame` to combine additional scores into the max.
