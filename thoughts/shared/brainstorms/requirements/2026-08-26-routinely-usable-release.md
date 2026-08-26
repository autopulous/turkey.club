---
name: routinely-usable-release
title: turkey.club routinely usable release — requirements
type: brainstorm-requirements
status: ready
created: 2026-08-26
updated: 2026-08-26
goal: thoughts/shared/brainstorms/goals/2026-08-26-routinely-usable-release.md
supersedes: []
related: []
session_options:
  test_strategy: default
  mermaid_graph: "on"
  coverage_check: "on"
---

# turkey.club routinely usable release — requirements

> Goal: [turkey.club routinely usable release](../goals/2026-08-26-routinely-usable-release.md) — status: ready

## Summary

|              | v0 | later |
| ------------ | -- | ----- |
| Must         | 5  | 0     |
| Should       | 5  | 0     |
| Could        | 0  | 0     |
| Won't        | 0  | 5     |

By category: FR 12 (5 Must/v0, 2 Should/v0, 5 Won't/later), NFR 1 (Should/v0), DR 1 (Should/v0), IR 0 (N/A), UX 1 (Should/v0), OR 1 (Must/v0), CR 0 (N/A).

## Functional requirements

### FR-1: Format preset CLI option
**Priority:** Must
**Phase:** v0
**Statement:** The `extract` command shall accept a `--format <preset>` option that bundles probe interval, lane policy (single-lane vs. cross-lane), and expected shot count range for the specified bowling format.
**Acceptance criteria:**
- Eleven presets are available: `pba-qualifying`, `pba-match-play`, `doubles`, `scotch-doubles`, `baker`, `baker-half`, `baker-double`, `league`, `singles-practice`, `multi-bowler-practice`, `open`
- Each preset sets probe interval, lane policy, and expected shot count range per the format taxonomy in `thoughts/shared/memory/project_bowling_format_taxonomy.md`
- When `--format` is specified, individual flags (`--probe-interval`, `--bowler-lane`) still override the preset defaults
- `--format` is optional; omitting it preserves current behavior (user threads individual flags)
- `turkey-club extract --help` lists all available preset names in the `--format` option help text
- Passing an invalid preset name produces an error listing the valid presets
**Traces to goal:** Outcome, Definition of done, Scope/in

### FR-2: `build-bowler-target` CLI subcommand
**Priority:** Must
**Phase:** v0
**Statement:** A new CLI subcommand `build-bowler-target` shall expose the existing `identify.build_bowler_target_from_references` library function so users no longer need to write a custom Python script to create a bowler target.
**Acceptance criteria:**
- Accepts `--name <bowler>`, `--calibration <venue.json>`, one or more `--reference <image>` paired by order with `--lane <lane>` (matching `calibrate`'s `--frame`/`--lane` convention), `--samples-per-image` (default 2000), and `--out <target.json>`
- A single `--reference` broadcasts to all `--lane` values; otherwise counts must match
- Produces a valid `BowlerTarget` JSON identical to what the library function produces
- Error messages follow NFR-1 (guide the user to a fix) for common failures: no person detected in approach zone, image not found, lane name mismatch
**Traces to goal:** Outcome, Definition of done

### FR-3: Cross-platform PyPI packaging
**Priority:** Must
**Phase:** v0
**Statement:** The tool shall be packaged and published on PyPI so that `pip install turkey-club` installs the tool and all runtime dependencies on Windows, macOS, and Linux.
**Acceptance criteria:**
- `pip install turkey-club` in a fresh virtual environment installs the tool and exposes the `turkey-club` entry point
- `mediapipe` is removed from runtime dependencies (unused in production code)
- All runtime dependencies have MIT-compatible licenses (MIT, BSD, Apache 2.0, PSF, ISC); no GPL/LGPL/AGPL runtime dependencies
- `pyproject.toml` metadata (description, URLs, classifiers, license) is complete for PyPI presentation
- Install works on Python 3.10, 3.11, 3.12 on all three platforms
**Traces to goal:** Definition of done, Constraints (cross-platform, MIT license)

### FR-4: Progress reporting with upfront time estimate and ongoing ETA
**Priority:** Must
**Phase:** v0
**Statement:** The `extract` command shall report an upfront estimated runtime before main processing begins and ongoing ETA updates as the run progresses.
**Acceptance criteria:**
- Before the main processing loop, the pipeline times a small sample of frames to measure per-frame YOLO cost on the current hardware
- Prints an upfront estimate within the first 60 seconds of a run: "Estimated runtime: ~XX minutes at current speed"
- Ongoing progress lines include a refining ETA
- ETA is within +/-30% of actual runtime by the halfway point of the run
- Existing per-probe and per-shot log lines are preserved; ETA is additive
**Traces to goal:** Definition of done, Risks (user impatience)

### FR-5: Documentation — dependency isolation, format preset reference, and tutorial
**Priority:** Must
**Phase:** v0
**Statement:** User documentation shall be updated with explicit dependency isolation guidance, a format preset reference, and a start-to-finish tutorial.
**Acceptance criteria:**
- `docs/user/installation.md` updated with explicit venv/virtualenv instructions per platform (Windows, macOS, Linux), positioned as the default installation path
- A format preset reference table documents each `--format` preset's bundled defaults (probe interval, lane policy, expected shot count range)
- A start-to-finish tutorial walks a new user from "I have a bowling video" to "I have per-shot clips," covering still extraction, calibration, bowler target building (using `build-bowler-target`), and extract
- Existing documentation references to planned/unimplemented features are updated to reflect v0 state
- `<repo-url>` placeholders in docs are replaced with the actual repository URL
**Traces to goal:** Definition of done, Constraints (dependency isolation)

### FR-6: Format-aware shot count sanity check
**Priority:** Should
**Phase:** v0
**Statement:** After extraction completes, if `--format` was specified, the pipeline shall compare the number of detected shots against the format's expected range and warn if the count falls outside it.
**Acceptance criteria:**
- Warning fires when the shot count is outside the preset's expected range
- Warning text includes the expected range and the actual count: "Warning: found N shots but <preset> expects X-Y. Possible missed shots or wrong format."
- No warning when the count is within the expected range
- Warning is advisory only — no hard failure, no non-zero exit code
**Traces to goal:** Scope/in

### FR-7: Performance optimization beyond existing downscale + probe
**Priority:** Won't
**Phase:** later
**Statement:** GPU acceleration, frame-skip in range-expand windows, and motion-gate YOLO are explicit follow-up optimizations, not in scope for the routinely usable release.
**Acceptance criteria:**
- _N/A — deferred_
**Traces to goal:** Scope/out

### FR-8: Automatic calibration or zone detection
**Priority:** Won't
**Phase:** later
**Statement:** Auto-detecting approach, lane, and pin zones from video content is out of scope. Manual one-time calibration remains the design.
**Acceptance criteria:**
- _N/A — deferred_
**Traces to goal:** Scope/out

### FR-9: New detection/identification approaches
**Priority:** Won't
**Phase:** later
**Statement:** Person ReID embeddings, learned bowler features, or alternative detection models are out of scope for this release.
**Acceptance criteria:**
- _N/A — deferred_
**Traces to goal:** Scope/out

### FR-10: Unusual pin-action detection
**Priority:** Won't
**Phase:** later
**Statement:** Detecting unusual pin falls, weird ball reactions, split conversions, or other notable events within a shot is a future feature.
**Acceptance criteria:**
- _N/A — deferred_
**Traces to goal:** Scope/out

### FR-11: GUI
**Priority:** Won't
**Phase:** later
**Statement:** A graphical interface is the aspirational delivery shape but is deferred unless the implementation cost is close to the CLI path. The CLI is the right vehicle for this goal.
**Acceptance criteria:**
- _N/A — deferred_
**Traces to goal:** Scope/out, Alternatives considered

### FR-12: Identification diagnostic subcommand
**Priority:** Should
**Phase:** v0
**Statement:** A new `diagnose` CLI subcommand shall let the user see bowler-confidence scores on sample frames before committing to a full extract run, enabling troubleshooting of identification at new venues.
**Acceptance criteria:**
- Accepts `--video`, `--bowler-target`, `--calibration`, and optionally `--frames <N>` (default 10) and a timestamp or frame range
- Samples N evenly-spaced frames across the video (or within the specified range)
- For each sampled frame, reports per-person confidence scores grouped by lane, with the highest-confidence match highlighted
- Prints a summary recommendation: "target bowler detected in N/M sampled frames at confidence X.XX-Y.YY" with guidance if scores are borderline (near the 0.30 threshold)
- Text output to stdout (consistent with CLI-only philosophy)
**Traces to goal:** Risks (identification fragility across venues)

## Non-functional requirements

### NFR-1: Error messages provide step-by-step diagnostic and corrective instructions
**Priority:** Should
**Phase:** v0
**Statement:** Every user-facing error path shall provide step-by-step instructions to diagnose and correct the issue, or clearly declare that the user has encountered a scenario the application is unable to support.
**Acceptance criteria:**
- Missing ffmpeg: error names the tool, provides the platform-appropriate install command, and tells the user to reopen their shell
- Missing yt-dlp: error names the tool, provides the install command, and names what the user was trying to do that requires it
- Missing or malformed calibration/bowler-target JSON: error names the file, states what is wrong, provides the exact command to regenerate the file, and names any prerequisite steps
- No person detected in reference image: error provides a numbered diagnostic sequence — [a] verify the bowler is visible in the frame, [b] verify calibration zones align using `preview`, [c] try a different reference frame
- Invalid `--format` preset name: error lists all valid preset names with one-line descriptions
- Schema version mismatch on JSON load: error names the expected version, the version found, and the exact command to regenerate the file
- Unsupported scenario (e.g., broadcast video with camera cuts, resolution below detection floor): error explicitly declares the scenario unsupported and names the constraint — not a vague "something went wrong"
- Audit: every `raise RuntimeError(...)`, `raise ValueError(...)`, and `typer.Exit(code=2)` in the codebase includes either step-by-step corrective instructions or an explicit "unsupported scenario" declaration
**Traces to goal:** Outcome ("without needing to understand the pipeline internals")

## Data requirements

### DR-1: Schema version in JSON artifacts
**Priority:** Should
**Phase:** v0
**Statement:** `VenueCalibration` and `BowlerTarget` JSON files shall include a `version` field for forward compatibility.
**Acceptance criteria:**
- Both JSON formats include a top-level `"version": 1` field when saved
- On load, the pipeline checks the version field; a missing version field is treated as version 1 (backward compatibility with existing files)
- Loading a file with a version higher than the code supports raises a clear error naming the expected version and how to regenerate
- Existing calibration and bowler-target files (version field absent) continue to load without error
**Traces to goal:** Outcome ("without needing to understand the pipeline internals"), NFR-1

## Integration requirements

_N/A — all external integrations (ffmpeg, yt-dlp, ultralytics model downloads) are subprocess calls or Python imports already covered by FR-3 (packaging) and NFR-1 (error messages). No new integration contracts are introduced by this goal._

## UX requirements

### UX-1: CLI help text discoverability
**Priority:** Should
**Phase:** v0
**Statement:** Every subcommand's `--help` output shall be self-documenting, with all options described and special values enumerated.
**Acceptance criteria:**
- `turkey-club --help` lists all subcommands with one-line descriptions
- `turkey-club extract --help` lists all available `--format` preset names in the option help text
- `turkey-club build-bowler-target --help` documents the `--reference`/`--lane` pairing convention
- `turkey-club diagnose --help` documents what the output means and how to interpret confidence scores
- Help text uses consistent terminology across subcommands
**Traces to goal:** Outcome ("without needing to understand the pipeline internals")

## Operational requirements

### OR-1: Package published on PyPI
**Priority:** Must
**Phase:** v0
**Statement:** The package shall be uploaded to PyPI so that `pip install turkey-club` resolves from the public index.
**Acceptance criteria:**
- The package is published on PyPI under the name `turkey-club`
- `pip install turkey-club` in a fresh virtual environment on each platform (Windows, macOS, Linux) succeeds
- The published package version matches the version in `pyproject.toml` and `src/turkey_club/__init__.py`
- A repeatable publication mechanism exists (manual `twine upload` or CI workflow)
**Traces to goal:** Definition of done

## Compliance requirements

_N/A — MIT licensing is already in place (`LICENSE` at project root). Dependency license compatibility is covered by FR-3's acceptance criteria. No regulatory, contractual, or policy requirements apply to this open-source tool._

## Cross-cutting acceptance criteria

- All commands and all eleven format presets work on Windows, macOS, and Linux
- All user-facing error paths provide step-by-step diagnostic and corrective instructions, or explicitly declare the scenario unsupported (NFR-1)
- JSON artifacts include a schema version field and are backward-compatible with existing version-less files (DR-1)
- `flush=True` on all pipeline `print()` calls (existing invariant from `thoughts/shared/memory/feedback_pipeline_invariants.md`)
- No interactive prompts unless `--yes` is absent and the prompt is about a non-default adjustment (existing invariant)

## Open decisions

### D-1: `diagnose` subcommand — annotated frame output
**Options considered:**
- [a] Text-only output (per-person confidence scores as a text table) — simple, consistent with CLI-only philosophy, no new dependencies
- [b] Text output plus optional annotated frame images (bounding boxes + confidence scores overlaid, written to a directory) — more useful for visual debugging but adds image-writing logic
**Chosen:** [a] Text-only output for v0
**Rationale:** The goal's constraint is CLI-only (NF4.1 in existing requirements). Text output is sufficient for threshold tuning — the user sees "target scores 0.25 at this venue, below threshold 0.30" and knows to rebuild the target or adjust. Annotated frame output is a natural v1 enhancement once the subcommand exists.
**Affects:** FR-12

### D-2: Format preset storage location
**Options considered:**
- [a] Hardcoded `FORMAT_PRESETS` dict in `config.py` — follows the existing pattern where all configuration dataclasses live in `config.py`
- [b] New `presets.py` module — separates format knowledge from core config
- [c] External TOML/JSON file — user-extensible but adds a file-discovery problem
**Chosen:** [a] `FORMAT_PRESETS` dict in `config.py`
**Rationale:** `config.py` already holds `SegmentationParameters`, `VenueCalibration`, `LaneCalibration`, `BowlerTarget`. Format presets are configuration. A new module is not warranted for a single dict. External files add complexity without clear benefit — the preset list is stable and code-owned.
**Affects:** FR-1

### D-3: easyocr remains a core dependency
**Options considered:**
- [a] Keep easyocr as a core dependency — marginal install cost is ~5 MB since torch is already required by ultralytics; OCR path remains available for block-letter jerseys via `use_ocr=True`
- [b] Move easyocr to an optional extra (`pip install turkey-club[ocr]`) — saves ~5 MB for users who will never use OCR, but introduces an import error if someone passes `use_ocr=True` without the extra
**Chosen:** [a] Keep as core dependency
**Rationale:** torch (~750 MB) is the heavy part and is already required by ultralytics. easyocr itself is ~5 MB marginal. Removing it saves negligible install size but creates a failure mode (import error on `use_ocr=True`). The OCR path is documented as a secondary signal for clear block-letter jerseys and should remain available without extra install steps.
**Affects:** FR-3

### D-4: `build-bowler-target` subcommand name
**Options considered:**
- [a] `build-bowler-target` — matches the goal artifact's wording exactly; descriptive
- [b] `build-target` — shorter; unambiguous in context since only bowler targets exist
- [c] `target` — very short; ambiguous (is it building, loading, or inspecting?)
**Chosen:** [a] `build-bowler-target`
**Rationale:** The goal artifact names it explicitly. The existing subcommands are short single words (`calibrate`, `extract`, `preview`, `fetch`, `merge`), but this subcommand's purpose is less obvious from a single word. The full name is self-documenting in `--help` output and matches the `BowlerTarget` type name from the codebase.
**Affects:** FR-2

### D-5: `--format baker` interaction with `--bowler-lane`
**Options considered:**
- [a] `--format baker` without `--bowler-lane` errors — Baker format requires a lane assignment; the user must specify
- [b] `--format baker` without `--bowler-lane` warns but searches both lanes — technically functional but defeats the purpose of the format restriction
- [c] `--format baker` without `--bowler-lane` silently searches both lanes — no guard at all
**Chosen:** [a] Error requiring `--bowler-lane` when format is Baker (any Baker variant)
**Rationale:** Baker format's defining characteristic is fixed-lane-per-bowler. Searching both lanes would find shots from other team members. A clear error ("Baker format requires --bowler-lane <name>; specify which lane this bowler is assigned to") is better than silent wrong results. This applies to `baker`, `baker-half`, and `baker-double`.
**Affects:** FR-1, FR-6

## Restatement

Get turkey.club from a working-but-manual research prototype to a routinely usable open-source package. The v0 release adds format presets that eliminate per-run flag ceremony across all eleven supported bowling formats, a `build-bowler-target` CLI subcommand that removes the need for custom Python scripts, a `diagnose` subcommand for troubleshooting identification at new venues, progress reporting with upfront time estimates and ongoing ETA, and a format-aware shot count sanity check. The tool is packaged on PyPI for cross-platform `pip install turkey-club`, documented with dependency isolation guidance and a start-to-finish tutorial for new users, and every error message provides step-by-step instructions to diagnose and correct the issue or explicitly declares the scenario unsupported. JSON artifacts carry schema versions for forward compatibility. `mediapipe` is dropped as an unused dependency; `easyocr` stays as a core dependency since its marginal cost is negligible with torch already present. Performance optimization, auto-calibration, new detection approaches, unusual pin-action detection, and a GUI are explicit later items. The value is in the output — shot clips, efficiently obtained — not the chrome.
