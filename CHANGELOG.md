# Changelog

[← Back to README](README.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Project management documents split from user documents (`docs/project/` and `docs/user/`).
- Open-source project artifacts: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `.editorconfig`, `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md`.
- `docs/user/performance.md` — hardware-tier runtime expectations and tuning levers.
- `docs/project/use_cases.md` — eight representative end-to-end scenarios.
- Gutter-ball fallback in `find_shot_boundaries`: when the impact search exhausts without finding pin-motion (gutter ball, Brooklyn miss, etc.), an impact is synthesized at `forward_onset + gutter_fallback_seconds_after_onset` (default 4.0 s) and the shot is still recorded. `ShotSegment.gutter_fallback` flags these; the exported clip filename gets a `_gutter` suffix (e.g. `shot_12_left_gutter.mp4`).
- Scotch Doubles added to the supported-formats taxonomy.
- Shots-per-bowler-per-game range column in the README formats table.

## [0.1.0] — 2026-05-25

### Added
- Initial release of `turkey-club`.
- CLI subcommands: `calibrate`, `extract`, `preview`, `fetch`, `merge`.
- Interactive venue calibration with per-lane polygon zones (approach, lane, pin).
- HSV histogram-distance bowler identification using sampled shirt-color references.
- OCR-based identification with six preprocessing variants and fuzzy substring matching (secondary signal; disabled by default in the pipeline path due to cursive-font defeat).
- Two search strategies:
  - `linear` — every-frame scan; the oracle for validating other strategies.
  - `probe` — sparse probes at 10s intervals with range-expand on hits (default; ~3–5× faster than linear on PBA-qualifying footage).
- State-machine shot boundary detection: `SEARCHING → SETUP → forward-motion onset → ball-impact → pin-settle`.
- Auto-cached detection-resolution downscale (`<source>.detect_<scale>x.mp4`); default factor 0.5; valid set `{1.0, 0.75, 0.5, 0.4, 0.33, 0.25}`; interactive snap-down with `--yes` for non-interactive runs.
- Frame-accurate ffmpeg clip export with live-streamed stderr (`-stats`, `\r → \n` line translation).
- Optional merged highlight reel (`--merge` default; `--no-merge` to skip; `merge` subcommand for post-hoc concatenation).
- `yt-dlp` source resolution accepting local file paths and remote URLs.
- Project documentation: `README.md`, `docs/user/{prerequisites,installation,performance}.md`, `docs/project/{goals,requirements,implementation_plan}.md`.
- MIT license.

### Known limitations
- CPU-only YOLO inference dominates runtime (~50–200 ms per frame at default 0.5× downscale).
- Cursive jersey fonts defeat the OCR path; color histogram is the production identifier.
- Single-camera, single-target-bowler per run.
- Broadcast video with shot-cut transitions is out of scope.
- Format-preset CLI (`--format <preset>`) is planned but not yet implemented; `--bowler-lane <name>` is the Baker-format workaround today.
- `build-bowler` CLI subcommand is planned but not yet implemented; use `identify.build_bowler_target_from_references` from a small Python script.

[Unreleased]: https://github.com/jhart/turkey.club/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jhart/turkey.club/releases/tag/v0.1.0
