# Contributing to turkey.club

[← Back to README](README.md)

Thanks for your interest in this project. turkey.club is a small, single-author tool today, so contribution overhead is light — the goal of this document is to make it easy to set up a working environment and submit changes that fit the existing code shape.

## Project status

Solo development, early stage. The pipeline is functional end-to-end but several optimizations and CLI features are queued (see [docs/project/implementation_plan.md](docs/project/implementation_plan.md)). Patches, bug reports, and design suggestions are all welcome.

## Development environment

Prerequisites:

- Python 3.10+ (`py -3` launcher on Windows, `python3` elsewhere)
- ffmpeg on PATH (Windows: `winget install Gyan.FFmpeg`)
- git

Clone and install in editable mode with the dev extras:

```
git clone <repo-url>
cd turkey.club
py -3 -m pip install -e .[dev]
```

This pulls opencv-python, mediapipe, easyocr, ultralytics (which brings torch), yt-dlp, typer, and pytest. The first run of `extract` will additionally download YOLOv8n weights (~6 MB) and EasyOCR detector + recognizer models (~150 MB) on demand.

## Tests

```
py -3 -m pytest tests/
```

Tests are mostly smoke-level today (CLI loads, modules import, `resolve_source` handles local paths). The synthetic-signal test for `find_shot_boundaries` (see [docs/project/implementation_plan.md](docs/project/implementation_plan.md)) is a good pattern to follow when adding state-machine logic — small canned signal arrays, exact frame-index assertions.

End-to-end validation runs against real video are tracked in `docs/implementation_plan.md`'s phased plan.

## Code style

- Python 3.10+ syntax; prefer PEP 604 unions (`int | None`) over `Optional[int]`.
- Comments are sparse — only when the WHY is non-obvious. Don't restate WHAT the code does.
- Full identifier names; no abbreviations.
- File paths in commit messages and PR descriptions should be full repo-relative paths, not bare basenames.

No formatter / linter is enforced at present. If you want to run something locally, `ruff format` matches the existing style.

## Hard invariants

A few invariants the codebase depends on — please preserve when editing:

1. **`flush=True` on long-running pipeline prints.** Block-buffered stdout/stderr hides progress for hours in background runs. *Why this matters*: the first linear-scan attempt produced 2 lines of output and then nothing for ~2 hours. The process was alive and working the whole time but invisible.
2. **Strict forward progress in probe-then-range search.** `probe_frame = max(last_shot_end + 1, probe_frame + probe_interval_frames)` — without the `max()`, an end-frame at probe-frame-minus-1 creates an infinite loop. *Why this matters*: the original probe loop hit a real-world case where the state machine produced a shot ending at frame 9845, the bowler was still in approach at frame 9846, and the loop revisited the same window 14 times before manual kill.
3. **Coerce tuples after JSON load.** `BowlerTarget.shirt_color_samples` and similar tuple-typed fields come back as lists from JSON; `lru_cache` requires hashable keys. Coercion happens in `BowlerTarget.load`.
4. **Validate output paths upfront in interactive collectors.** A path with a newline (e.g., from PowerShell paste-wrap) discovered only at save time loses all the user's intermediate click work. *Why this matters*: the first calibration run lost 6 zones of click work because `mkdir` of the output's parent only happened at the very end, after the OpenCV interactive flow.

## Submitting changes

1. **Open an issue first** for non-trivial changes — even a one-paragraph design sketch lets us avoid duplicate or conflicting work.
2. **One concern per PR.** Bug fix + unrelated refactor in the same PR is harder to review.
3. **Include a test** for state-machine or signal-computation changes (see the synthetic-signal pattern above). Pure refactors and doc updates don't need new tests.
4. **Update the relevant docs** — `README.md` quick-start if you change the CLI surface, `docs/implementation_plan.md` if you move a phase forward, `docs/requirements.md` if you add or change a requirement.
5. **PR description** should explain the WHY, not just the WHAT — see `.github/PULL_REQUEST_TEMPLATE.md`.

## Reporting issues

Use the bug-report template in `.github/ISSUE_TEMPLATE/`. Include:

- The exact CLI invocation that failed.
- Your video's frame dimensions and frame rate (from `ffprobe`).
- Any traceback or relevant log output.
- Whether the issue reproduces on the `linear` strategy as well as `probe` (this distinguishes search-strategy bugs from signal-extraction bugs).

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating you agree to abide by its terms.

## License

By contributing you agree that your contributions will be licensed under the [MIT License](LICENSE).
