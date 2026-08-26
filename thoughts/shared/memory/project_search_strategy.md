---
name: project-search-strategy
description: Probe-then-range default search strategy and the invariants (strict forward progress, dedup) needed to avoid infinite loops.
metadata:
  type: project
---

The pipeline supports two search strategies, with `probe` as the default:

**`linear`** (oracle): every-frame scan from 0 to N. Simple, correct. ~6× real-time on CPU YOLO (41-min video takes ~4 hours).

**`probe`** (production): sparse probes at `probe_interval_seconds` (default 10s, must be < min shot duration), range-expand on hits. Speedup ~3-5× depending on shot density. On PBA qualifying (~21 shots / 41 min), about 85% of frames are dead-time and get skipped.

**Probe-then-range loop:**
1. Seek to `probe_frame`, run one-frame bowler check (person detection + identify in approach zones).
2. No hit → advance `probe_frame += probe_interval_frames`.
3. Hit → range-expand window `[probe - lookback, probe + forward]` (default `[-15s, +25s]`). Process every frame in window. Run `find_shot_boundaries`.
4. Append NEW shots only (deduped against existing by `start_frame + lane_name`).
5. Advance `probe_frame = max(last_shot_end + 1, probe_frame + probe_interval_frames)`.

**Critical invariants (broken in first implementation, fixed mid-session 2026-05-25):**
- **Strict forward progress** required: `probe_frame` must advance by `>= probe_interval_frames` per iteration even when a shot ends just before `probe_frame`. Without the `max()`, a shot ending at frame N-1 and the bowler still in approach at frame N creates an infinite loop (`probe_frame = N` → hit → expand → same shot ending at N-1 → `probe_frame = N` again …). Observed in a real run at frame 9846; 14 duplicate entries before manual kill.
- **Dedup by (start_frame, lane_name)**: overlapping windows can re-find the same shot. Filter before extending `all_shots`.

**Why:** The state machine in `segment.py` is deterministic on the same signal window. Without these invariants, the loop revisits the same window endlessly and the output gets flooded with duplicates.

**How to apply:** Don't reorder the `probe_frame` advance logic without preserving both invariants. If implementing the queued downscale optimization (see [[project-performance-constraints]]), the search-strategy contract is unchanged — only the YOLO input changes. Related: [[project-identification-strategy]], [[feedback-pipeline-invariants]].
