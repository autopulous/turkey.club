---
name: routinely-usable-release
title: turkey.club routinely usable release
type: brainstorm-goal
status: ready
created: 2026-08-26
updated: 2026-08-26
supersedes: []
related: []
---

# turkey.club routinely usable release

## Outcome

turkey.club reaches a state where a user can point it at a bowling video, specify a format preset and a bowler target, and get shot clips out without manual flag ceremony, without workarounds, and without needing to understand the pipeline internals. The tool is installable by a novice, documented end-to-end, and published as an open-source package.

## Definition of done

- A `--format <preset>` option on `extract` bundles per-format defaults (probe interval, lane policy, expected shot count) so the user does not need to thread individual flags for each bowling format
- A `build-bowler-target` CLI subcommand exposes the existing `identify.build_bowler_target_from_references` library function
- The tool is packaged and published so that `pip install turkey-club` (or equivalent) works cross-platform
- Documentation covers: installation with dependency isolation, per-command usage, format preset reference, and a start-to-finish tutorial for a new user
- Progress reporting during `extract` includes upfront time estimates and ongoing progress so users know the tool is working and how long it will take
- The project is licensed MIT

## Motivation

The v0 was built and validated in 2026-05-25 against real PBA footage. It works, but it is a research prototype -- using it requires knowing which flags to pass for each bowling format, invoking a library function via a manual Python script to build a bowler target, and understanding the pipeline well enough to set expectations about runtime. The goal is to close the loop: make the tool usable by someone who is not its author, and eliminate the per-run manual ceremony that makes routine use tedious even for its author. No external deadline -- the contributor has time and wants to finish what was started.

## Beneficiaries and stakeholders

- **Primary user** -- the project's author, who processes bowling footage for personal use
- **Open-source community** -- bowlers, coaches, or analysts who want to extract per-shot clips from fixed-camera match video. The CLI surface, defaults, and documentation must make sense to someone encountering the tool for the first time

## Scope

**In scope**

- Format presets (`--format <preset>`) bundling probe interval, lane policy (single vs. cross-lane), and expected shot count for: PBA qualifying/match play, doubles, Scotch doubles, Baker (traditional/half/double), league play, singles practice, multi-bowler practice, open bowling
- `build-bowler-target` CLI subcommand
- Packaging for cross-platform installation (PyPI or equivalent)
- Documentation: installation (with dependency isolation guidance for ffmpeg, yt-dlp, PyTorch/ultralytics, OpenCV), per-command reference, format preset reference, start-to-finish tutorial
- Progress reporting and upfront time estimates during `extract`
- MIT licensing

**Out of scope / non-goals**

- Performance optimization (GPU acceleration, frame-skip in range-expand windows, motion-gate YOLO) -- follow-up
- Automatic calibration or zone detection -- follow-up
- New detection/identification approaches -- follow-up
- Unusual pin-action detection (weird pin fall, weird ball reaction, split conversions) -- noted as a future feature, not pursued now
- GUI -- aspirational delivery shape, but only if the cost is close to the CLI path; otherwise the CLI is the right vehicle for this goal

## Constraints

- **Cross-platform** (hard) -- must work on Windows, macOS, and Linux
- **MIT license** (hard) -- all shipped code must be MIT-compatible; dependency licenses must not conflict
- **Dependency isolation** (hard) -- documentation must guide users to install in a way that does not pollute their system Python or break other tools. The dependency stack is heavy (PyTorch via ultralytics, OpenCV, ffmpeg, yt-dlp) and this is a load-bearing documentation requirement, not boilerplate
- **Python >=3.10** (hard) -- existing floor from pyproject.toml
- **Horizon is indeterminate** (soft) -- takes what it takes given available time and attention; no external deadline

## Alternatives considered

- **Container image** (Docker) -- would eliminate the install/isolation problem entirely, but raises the bar for novice users who may not have Docker installed and adds a different kind of complexity. Rejected in favor of native Python packaging with thorough isolation documentation
- **GUI application** -- aspirational but deferred unless the implementation cost is close to the CLI path. The value is in the output (shot clips, efficiently obtained), not the chrome
- **Subset of format presets** -- could ship with only the most common formats and add others later. Not rejected outright; the requirements phase should determine the minimum viable preset set

## Risks

- **Identification fragility across venues** -- the HSV histogram threshold (0.30 for real video) was tuned on PBA broadcast footage at one venue. Different lighting, camera quality, or jersey colors at other venues may require threshold adjustment. A novice user will not know how to diagnose or tune this. Mitigation: documentation of the threshold, a diagnostic/preview mode, or adaptive thresholding -- to be explored in requirements
- **Dependency installation complexity** -- PyTorch + OpenCV + ffmpeg + yt-dlp is a heavy, cross-platform-variable stack. Getting it right in an isolated environment on all three OSes is non-trivial. Mitigation: thorough, tested installation guides per platform; possibly a requirements-extras split so the heaviest dependencies are explicit
- **User impatience** -- CPU YOLO inference at ~200ms/frame means ~85 minutes per PBA game with probe strategy. A novice user with no context will assume the tool is broken or give up. Mitigation: upfront time estimates, ongoing progress reporting with ETA, and documentation setting expectations about runtime

## Horizon

Indeterminate -- takes what it takes given available time and attention. No external deadline.

## Restatement

Get turkey.club from a working-but-manual research prototype to a routinely usable open-source tool. The core outcome is eliminating the per-run flag ceremony through format presets, exposing the build-bowler-target function as a proper CLI command, packaging the tool for easy novice installation with thorough dependency documentation (including isolation), and writing documentation that lets someone who isn't the author use the tool end-to-end. The tool ships cross-platform under MIT. Performance optimization, auto-calibration, new detection approaches, and unusual pin-action detection are explicit follow-ups. A GUI is the aspirational delivery shape but only if the cost is close to the CLI path; otherwise the CLI is the right vehicle. The value is in the output -- shot clips, efficiently obtained -- not the chrome.
