# Requirements — turkey.club

These requirements are validated against the scenarios in [use_cases.md](use_cases.md). When adding or revising a requirement, confirm at least one use case still works end-to-end and that any new behavior has a matching scenario described there.

## Functional requirements

### F1 — Venue calibration (one-time, per-camera setup)
- F1.1 — A CLI subcommand `calibrate` opens a still frame in an OpenCV window and lets the user mark polygon zones with mouse clicks: left-click adds a vertex, right-click or `U` undoes, `Enter` finalizes (minimum 3 vertices), `Esc` cancels.
- F1.2 — The user marks **three zones per lane**: approach (where the bowler stands), lane (where the ball travels), pin (where pins fall).
- F1.3 — The command accepts one `--frame` per `--lane` so each lane can be calibrated against a still where the bowler is visibly in that lane's approach. A single `--frame` broadcasts to all lanes.
- F1.4 — Output is a JSON file storing per-lane polygons + the source-frame width/height.
- F1.5 — A `preview` subcommand renders the calibrated polygons as colored overlays on every frame of a video, so the user can verify alignment before running the long extract.

### F2 — Bowler target (per-bowler artifact)
- F2.1 — A target JSON stores the bowler's display name and a list of BGR pixel samples from upper-back crops of one or more reference frames.
- F2.2 — Samples are drawn randomly from upper-back crops; 1,000–4,000 pixels per target is the working range.
- F2.3 — A Python helper `build_bowler_target_from_references(name, [(image, lane_name), ...], venue, samples_per_image)` builds the target file from one or more (reference_image, lane_name) pairs. Exposing this as a CLI subcommand is in scope but not yet implemented.

### F3 — Video source resolution
- F3.1 — The `extract` command accepts a `--video` argument that is **either** a local file path **or** a remote URL.
- F3.2 — Remote URLs are downloaded via yt-dlp into `~/.cache/turkey-club/videos/` and re-used across runs. Any source supported by yt-dlp is accepted (YouTube, direct MP4, ~1,800 sites).
- F3.3 — A `fetch` subcommand resolves any source argument to a local file path and prints it; useful for pre-warming the cache.

### F4 — Bowler identification

The identification pipeline arrived at HSV histogram-distance match after two earlier approaches were rejected during validation:

1. **OCR-primary** was tried first — EasyOCR with six preprocessing variants (original, upscaled, CLAHE, inverted, Otsu, Otsu-inverted) plus fuzzy sequence-similarity matching. Cursive PBA jerseys defeat the recognizer: the name `Clemons` was read as `@tenons`, `@lemtot`, `0lenora`, and similar across all variants. Fuzzy threshold 0.55 was not crossed.
2. **Color-inclusion match** (count of crop pixels within HSV tolerance of sample colors) was tried next — too permissive. All dark-shirted persons saturated at the confidence cap (0.85) with no discrimination between target and teammates.
3. **HSV histogram-distance match** (`cv2.HISTCMP_BHATTACHARYYA`, 16×8×8 bins, in `identify.py::_color_histogram_confidence`) is the production approach. It captures both presence (which colors) and distribution (how much), giving meaningful separation between target and non-target persons even when both wear dark clothing.

Cursive jersey fonts are the rule in PBA, not the exception. OCR is not a viable primary identifier; it is retained as a secondary signal for clear block-letter jerseys.

Requirements:

- F4.1 — For each frame to be analyzed, the pipeline detects persons via YOLOv8 (ultralytics).
- F4.2 — For each detected person whose foot-position falls inside any candidate-lane's approach polygon, the pipeline computes a bowler-confidence score in [0.0, 1.0] using HSV histogram-distance (Bhattacharyya) between the upper-back crop and the target's sampled colors.
- F4.3 — The default confidence threshold is **0.30** (`SegmentationParameters.bowler_confidence_threshold`). Empirical tuning data from validation on the PBA Game 1 footage:
  - **Reference-still scoring** (clear, motionless frames where the bowler is visible): target bowler scored 0.69–0.74; non-target teammate scored 0.45. Threshold 0.55 cleanly separates them.
  - **Real-video scoring** (motion blur, pose variation, lighting changes across the full match): target bowler drops to the 0.30–0.40 range; non-target persons 0.20–0.30. **Threshold must be 0.30** for the pipeline to fire on real video.
  - The smaller gap in real video (~0.05–0.10 between target and non-target) is the dominant tuning constraint. When tuning a new video, sample-test detection on 8–10 frames spread across the video before committing to a threshold change.
- F4.4 — OCR is implemented as a secondary signal (six preprocessing variants + fuzzy substring match) but disabled by default in pipeline use (`use_ocr=False`) because cursive jersey fonts defeat the recognizer and OCR cost (~600 ms per call) dominates the per-frame budget.

### F5 — Per-frame signal collection
For each frame and each candidate lane, the pipeline accumulates:
- F5.1 — `bowler_confidence_per_frame` — max identify-score among persons in that lane's approach zone; 0 when no qualifying person is present.
- F5.2 — `pose_motion_per_frame` — pixel distance between the matched bowler's bbox centroid this frame vs. last.
- F5.3 — `pin_motion_per_frame` — mean absolute frame-difference within that lane's pin polygon.
- F5.4 — `ball_reached_pins_per_frame` — placeholder, always False today; pin-motion spike is sufficient for impact detection.

### F6 — Shot boundary detection (state machine)
Per lane, applied independently to that lane's signal streams:
- F6.1 — **SEARCHING → SETUP**: trigger when bowler_confidence ≥ threshold AND pose_motion ≤ threshold for ≥ `stationary_pose_frames` consecutive frames.
- F6.2 — **SETUP → forward-motion onset**: first frame where pose_motion exceeds threshold. `start_frame = onset - forward_motion_lookback_seconds × fps`.
- F6.3 — **Onset → impact**: first frame where pin_motion > threshold OR ball_reached_pins is True.
- F6.4 — **Impact → settle**: pin_motion < threshold for ≥ `pin_settle_frames` consecutive frames. `end_frame = settle + end_pad_seconds × fps`.
- F6.5 — Per-phase budgets (`max_setup_to_release_seconds`, `max_release_to_impact_seconds`, `max_impact_to_settle_seconds`) abandon stalled candidates rather than blocking forever.
- F6.6 — Per-lane shot lists are merged and sorted by start_frame chronologically.

### F7 — Search strategies
- F7.1 — `--strategy linear` — every-frame scan; oracle for validating other strategies.
- F7.2 — `--strategy probe` (default) — sparse probes at `--probe-interval` (default 10s, must be < min shot duration), range-expand `[probe - 15s, probe + 25s]` on hits. Forward-progress invariant: `probe_frame = max(last_shot_end + 1, probe_frame + probe_interval_frames)`.
- F7.3 — Found-shot dedup: append only shots not already present by (start_frame, lane_name).

### F8 — Detection-resolution downscale (cache)
- F8.1 — The pipeline detects on a downscaled cache file `<source>.detect_<scale>x.mp4` co-located with the source. Created on first use, reused thereafter.
- F8.2 — `--downscale-factor` accepts a discrete set: {1.0, 0.75, 0.5, 0.4, 0.33, 0.25}. Out-of-set values snap down to the nearest supported, print a notice, and prompt for confirmation (or `--yes` to auto-confirm). Below 0.25 raises an error.
- F8.3 — Calibration polygons stay in source-pixel space; the pipeline scales them on-the-fly into detection-pixel-space.
- F8.4 — Clip cuts use the original full-resolution source via ffmpeg, so output clip quality is unaffected by detection downscale.

### F9 — Format-aware search
- F9.1 — `--bowler-lane <name>` restricts search to one calibrated lane (for Baker format where each bowler is fixed to a single lane).
- F9.2 — *(Planned, not yet implemented)* `--format <preset>` bundles probe interval + lane policy + expected-shot-count for: pba-qualifying, pba-match-play, doubles (alternating), league, baker, singles-practice (with `--bowler-lane` override or short-prefix auto-detect), multi-bowler-practice, open.

### F10 — Clip export
- F10.1 — Per shot, ffmpeg cuts a frame-accurate clip from the source video with `-ss` placed AFTER `-i` (precise seek + re-encode). Output: `shot_NN_<lane>.mp4` with zero-padded NN.
- F10.2 — Encoding params: `libx264 -preset fast -crf 20 -c:a aac -b:a 128k`.
- F10.3 — `-loglevel error -stats` is passed to suppress info noise; stderr is streamed live to the parent process (line-by-line, `\r` → `\n` translation via Python text-mode reads) so progress is visible during a background run.

### F11 — Merge (optional)
- F11.1 — `extract` merges per-shot clips into `<out>/all_shots.mp4` by default. `--no-merge` skips. `--merge-out <path>` overrides the destination.
- F11.2 — Standalone `merge` subcommand allows post-hoc concatenation of any directory of `shot_*.mp4` files. Defaults to stream-copy (instant); `--reencode` available for clips with varying codec parameters.

### F12 — Documentation
- F12.1 — All user-facing and project-management documentation MUST be provided in Markdown (`.md` extension) for portability and easy diffing.
- F12.2 — Documentation is split into two top-level directories:
  - **User documentation** (`docs/user/`) — for end users of the tool:
    - `docs/user/prerequisites.md` — per-platform install of Python, ffmpeg, git.
    - `docs/user/installation.md` — tool installation walkthrough with troubleshooting.
    - `docs/user/performance.md` — hardware-tier runtime expectations and tuning levers.
  - **Project management documentation** (`docs/project/`) — for designers, contributors, maintainers:
    - `docs/project/goals.md` — outcome, motivation, scope, success criteria, constraints.
    - `docs/project/requirements.md` — this document.
    - `docs/project/implementation_plan.md` — architecture, module map, phased status, risk register.
- F12.3 — `README.md` at project root provides a concise overview and links into both directories.
- F12.4 — Project meta-files at project root follow GitHub conventions:
  - `CONTRIBUTING.md` — how to set up dev environment, run tests, submit PRs.
  - `CODE_OF_CONDUCT.md` — community standards (Contributor Covenant link).
  - `SECURITY.md` — private vulnerability reporting policy.
  - `CHANGELOG.md` — release history (Keep a Changelog format).
  - `.github/ISSUE_TEMPLATE/{bug_report,feature_request}.md` and `.github/PULL_REQUEST_TEMPLATE.md`.
- F12.5 — License is a standard MIT license stored at `LICENSE` (no extension).
- F12.6 — Per-feature usage examples appear inline in `README.md` rather than as separate files until volume justifies a `docs/user/usage/` directory.
- F12.7 — Diagrams, when needed, are ASCII art (renders cleanly on GitHub and in `cat`) — no PNG / SVG dependencies in core docs.

## Non-functional requirements

### NF1 — Performance
- NF1.1 — Default `--downscale-factor 0.5 --strategy probe` should complete a 41-min PBA-qualifying game in ≤ 30 minutes on a modern Windows laptop with no GPU.
- NF1.2 — The bottleneck is YOLO CPU inference (~100–300 ms per frame). Per-frame cost target after downscale + frame-skip optimization: ≤ 80 ms.

### NF2 — Reliability
- NF2.1 — Idempotent re-runs: the same `extract` invocation produces the same shot list and clips.
- NF2.2 — Forward-progress invariant in probe-then-range prevents infinite loops on edge cases where shot end frames sit just before the probe frame.
- NF2.3 — JSON-loaded tuples must be coerced to tuples after deserialization (lists from JSON aren't hashable for `lru_cache`).
- NF2.4 — Validate output paths upfront in interactive collectors (e.g., calibrate) before doing expensive work.
- NF2.5 — All long-running pipeline `print()` calls must use `flush=True` so background runs have live progress visibility (default 8 KB block-buffering would hide everything for hours).

### NF3 — Observability
- NF3.1 — Probe lines include frame index, total frames, time in seconds, and percentage: `probe #71 @ frame 22225 of 74002 (740.8s, 30.0%): no hit`.
- NF3.2 — Hit lines show the range-expand window: `HIT — expanding [W_start-W_end]`.
- NF3.3 — Per-shot export lines summarize lane, frame range, duration, and bowler confidence.
- NF3.4 — Ffmpeg progress (frame= fps= speed=) streams live to the same log via `-stats`.

### NF4 — Operability
- NF4.1 — All commands are CLI-only. No GUI dependency beyond OpenCV's calibration window.
- NF4.2 — Calibration and bowler-target artifacts are JSON for easy hand-inspection and diffing.
- NF4.3 — Downscaled cache files are deterministically named so they're auto-discovered on subsequent runs.
- NF4.4 — `--yes` / `-y` flag auto-confirms any interactive prompts (needed for background runs where stdin is closed).

## Data requirements

### D1 — Inputs
- D1.1 — One source video per match. Resolution typically 720×1280 vertical (phone footage). H.264 in MP4 container.
- D1.2 — One venue calibration JSON per camera setup. Reusable across all matches at that venue.
- D1.3 — One bowler-target JSON per bowler. Reusable across all videos containing that bowler.
- D1.4 — One or more still reference images per bowler (extracted from match footage where the bowler is visibly in approach).

### D2 — Outputs
- D2.1 — One MP4 file per detected shot: `<out_dir>/shot_NN_<lane>.mp4`.
- D2.2 — Optional `<out_dir>/all_shots.mp4` merged highlight reel.
- D2.3 — Cached detection-resolution video at `<source_stem>.detect_<scale>x.mp4` co-located with source.

## Acceptance criteria (end-to-end test on Game 1)

- A1 — Probe-strategy run on Game 1 with `clemons.json` produces 18–21 shots (matches expected PBA-qualifying max, allowing 1 false-negative tolerance).
- A2 — Shot 1's `start_frame` is within ±15 frames of 2850 (= 95s × 30 fps; user-provided ground truth for first shot at 1:35).
- A3 — No exported clip features a non-Clemons bowler as the primary on-approach bowler.
- A4 — Total runtime ≤ 30 min on the project owner's laptop with default settings.
- A5 — Re-running the same command produces an identical shot list (deterministic).
- A6 — `--no-merge` produces only per-shot clips; with merge, `all_shots.mp4` exists and plays through all shots in chronological order.

## Operational requirements

- O1 — Tool must run under PowerShell on Windows 11 with Python 3.12.
- O2 — ffmpeg must be installed and on PATH (via winget Gyan.FFmpeg).
- O3 — All Python invocations must use `py -3` (not bare `python` — Microsoft Store App Execution Alias shim).
- O4 — Background-task-friendly: no stdin prompts unless `--yes` is set; live stdout/stderr progress.

## Open requirements (planned)

- OR1 — `--format <preset>` CLI option (Task #12).
- OR2 — `build-bowler` CLI subcommand for creating BowlerTarget JSON files non-programmatically.
- OR3 — Auto-detect Baker vs cross-lane format from a video prefix scan, when `--format` not provided.
- OR4 — Optional GPU acceleration via CUDA torch (10–50× speedup, hardware-dependent).
- OR5 — Format-aware sanity-check on shot count (warn if extracted count diverges from format's expected range).
