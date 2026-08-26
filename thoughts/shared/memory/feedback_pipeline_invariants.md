---
name: feedback-pipeline-invariants
description: Hard-learned invariants from session 2026-05-25 — flush prints on long-running tasks, validate output paths upfront, strict-forward-progress in probe loops, tuple-coerce after JSON.
metadata:
  type: feedback
---

Four invariants the game.to.frames pipeline relies on, each learned the hard way during the initial validation session 2026-05-25:

1. **Always pass `flush=True` to `print()` in long-running pipelines.**
   - Python's default block buffering on a non-TTY file pipe is ~8 KB. For sparse progress prints, the buffer never flushes during a multi-hour run.
   - The first linear-scan attempt produced 2 lines of output and then nothing for ~2 hours. Process was alive and working the whole time but invisible. Wasted hours on "is it stuck?" speculation.
   - Audit any new pipeline.py `print` call: pass `flush=True`.

2. **Validate user-provided output paths upfront, before expensive work.**
   - First interactive calibration run lost 6 zones (~5 minutes of click work) because the `--out` argument had a newline-in-quotes from PowerShell paste-wrapping. The `out_path.parent.mkdir(...)` happened at the END of the interactive flow, after all the clicks.
   - Always validate paths at the TOP of any interactive collector. `calibrate.run_interactive_calibration` now does `out_path.parent.mkdir(parents=True, exist_ok=True)` before opening the OpenCV window.

3. **Strict forward progress in any "search-then-deeper-look" loop.**
   - Probe-then-range had an infinite loop where the inner search produced a shot with `end_frame == probe_frame - 1`, causing the outer loop to set `probe_frame = end_frame + 1 = probe_frame` and never advance.
   - Fix: `probe_frame = max(inner_result_end + 1, probe_frame + min_step)`. See [[project-search-strategy]].

4. **JSON deserialization turns tuples into lists. Coerce on load if you need hashable.**
   - `BowlerTarget.shirt_color_samples` is typed as `list[tuple[int, int, int]]` but JSON has no tuple type — lists come back. `lru_cache` requires hashable keys → unhashable-type errors.
   - `BowlerTarget.load` now does `data["shirt_color_samples"] = [tuple(s) for s in data.get("shirt_color_samples", [])]` before the dataclass constructor.

**Why:** All four bit during the session. The flush issue alone cost ~2 hours of confused diagnosis. The mkdir issue lost manual click work. The infinite loop produced 14 duplicate shot entries before manual kill. The tuple/list issue caused the first probe-pipeline run to crash inside the first range-expand.

**How to apply:** Treat these as project-wide rules, not local fixes. Before submitting any new pipeline-touching code: audit `print` calls for `flush=True`, audit interactive collectors for upfront path validation, audit any sparse-then-dense search loop for `max(inner_end, current + min_step)` advance, audit any JSON-load of a dataclass-with-tuples for explicit tuple coercion. Related: [[project-search-strategy]].
