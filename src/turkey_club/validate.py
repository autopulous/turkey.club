"""Stages 5d-5f and 8: Temporal validation, gap probing, and game state tracking."""
from __future__ import annotations

import statistics

from turkey_club.config import (
    GameState,
    PinState,
    RotationModel,
    ShotEvent,
)
from turkey_club.formats import FormatPreset

_MAX_SPARE_GAP_SECONDS = 75.0


def validate_shot_continuity(
    appearances: list[tuple[int, str]],
    fps: float,
    probe_interval_seconds: float = 10.0,
    max_gap_factor: float = 3.0,
) -> list[list[tuple[int, str]]]:
    """Stage 5e: Group target appearances into contiguous shot events.

    Appearances within ``max_gap_factor * probe_interval_seconds`` of each other
    are grouped as a single shot. Larger gaps indicate separate shots.
    Returns a list of appearance groups, each representing one shot.
    """
    if not appearances:
        return []

    max_gap_frames = int(max_gap_factor * probe_interval_seconds * fps)
    groups: list[list[tuple[int, str]]] = [[appearances[0]]]

    for i in range(1, len(appearances)):
        prev_frame = appearances[i - 1][0]
        curr_frame = appearances[i][0]

        if curr_frame - prev_frame > max_gap_frames:
            groups.append([appearances[i]])
        else:
            groups[-1].append(appearances[i])

    return groups


def filter_cadence_violations(
    shot_groups: list[list[tuple[int, str]]],
    fps: float,
    format_preset: FormatPreset | None = None,
) -> list[list[tuple[int, str]]]:
    """Filter shot groups that violate the minimum cadence for a single bowler.

    In a cross-lane alternation format, the same bowler cannot return to the
    same lane faster than one full rotation cycle. This filter exploits that
    constraint in two steps:

    Filter A — groups consecutive same-lane shots within _MAX_SPARE_GAP_SECONDS
    into bowling frame candidates and trims any candidate with more shots than
    a single bowling frame allows (2 for frames 1-9, 3 for the 10th).

    Filter B — enforces a minimum same-lane return time equal to the expected
    cadence. When two candidates on the same lane are closer than this, the
    later one is removed (the earlier same-lane candidate is more likely to be
    the real shot — false positives appear between the target's real turns).
    """
    if not format_preset or not format_preset.expected_cadence_seconds:
        return shot_groups
    if format_preset.lane_alternation_pattern != "LR":
        return shot_groups
    if len(shot_groups) < 2:
        return shot_groups

    max_spare_gap_frames = int(_MAX_SPARE_GAP_SECONDS * fps)
    min_same_lane_return_frames = int(format_preset.expected_cadence_seconds * fps)

    # --- Filter A: group into bowling frame candidates, trim overpopulated ---

    candidates: list[list[int]] = [[0]]

    for i in range(1, len(shot_groups)):
        prev_idx = candidates[-1][-1]
        prev_group = shot_groups[prev_idx]
        curr_group = shot_groups[i]
        prev_frame = prev_group[0][0]
        curr_frame = curr_group[0][0]
        prev_lane = prev_group[0][1]
        curr_lane = curr_group[0][1]

        if curr_lane == prev_lane and (curr_frame - prev_frame) <= max_spare_gap_frames:
            candidates[-1].append(i)
        else:
            candidates.append([i])

    removed: set[int] = set()
    for ci, candidate in enumerate(candidates):
        max_shots = 3 if ci == len(candidates) - 1 else 2
        if len(candidate) > max_shots:
            for excess_idx in candidate[max_shots:]:
                removed.add(excess_idx)
            candidates[ci] = candidate[:max_shots]

    # --- Filter B: minimum same-lane return time ---

    last_per_lane: dict[str, int] = {}

    for ci, candidate in enumerate(candidates):
        if all(idx in removed for idx in candidate):
            continue

        start_frame = shot_groups[candidate[0]][0][0]
        lane = shot_groups[candidate[0]][0][1]
        total_appearances = sum(
            len(shot_groups[idx]) for idx in candidate if idx not in removed
        )

        if lane in last_per_lane:
            prev_ci = last_per_lane[lane]
            prev_candidate = candidates[prev_ci]
            prev_start = shot_groups[prev_candidate[0]][0][0]

            if (start_frame - prev_start) < min_same_lane_return_frames:
                for idx in candidate:
                    removed.add(idx)
            else:
                last_per_lane[lane] = ci
        else:
            last_per_lane[lane] = ci

    kept = [g for i, g in enumerate(shot_groups) if i not in removed]
    return kept


def compute_cadence(
    appearances: list[tuple[int, str]],
    fps: float,
) -> float | None:
    """Stage 5d: Compute the observed cadence (median inter-shot interval in seconds).

    Uses the first appearance in each shot group as the shot timestamp.
    Returns None if fewer than 3 shots are observed.
    """
    groups = validate_shot_continuity(appearances, fps)
    if len(groups) < 3:
        return None

    shot_frames = [group[0][0] for group in groups]
    intervals = [
        (shot_frames[i + 1] - shot_frames[i]) / fps
        for i in range(len(shot_frames) - 1)
    ]

    return statistics.median(intervals)


def detect_gaps(
    appearances: list[tuple[int, str]],
    fps: float,
    rotation_model: RotationModel | None = None,
    target_cluster_id: str = "",
    cadence_seconds: float | None = None,
    cadence_tolerance_low: float = 0.3,
    cadence_tolerance_high: float = 3.0,
) -> list[tuple[int, int, str]]:
    """Stage 5f: Detect gaps where the target bowler may have been missed.

    Returns a list of (gap_start_frame, gap_end_frame, reason) tuples
    indicating intervals that should be probed at finer granularity.
    """
    gaps: list[tuple[int, int, str]] = []

    groups = validate_shot_continuity(appearances, fps)
    if len(groups) < 2:
        return gaps

    shot_frames = [group[0][0] for group in groups]

    if cadence_seconds is not None:
        cadence_frames = cadence_seconds * fps
        low_bound = cadence_tolerance_low * cadence_frames
        high_bound = cadence_tolerance_high * cadence_frames

        for i in range(len(shot_frames) - 1):
            gap = shot_frames[i + 1] - shot_frames[i]
            if gap > high_bound:
                gaps.append((
                    shot_frames[i],
                    shot_frames[i + 1],
                    f"gap {gap / fps:.1f}s exceeds {cadence_tolerance_high}x cadence "
                    f"({cadence_seconds:.1f}s)",
                ))
            elif gap < low_bound:
                gaps.append((
                    shot_frames[i],
                    shot_frames[i + 1],
                    f"gap {gap / fps:.1f}s below {cadence_tolerance_low}x cadence "
                    f"({cadence_seconds:.1f}s)",
                ))

    return gaps


def advance_game_state(
    state: GameState,
    pin_state: PinState,
    lane_name: str,
    start_frame: int,
    end_frame: int,
    gutter_fallback: bool = False,
    bowler_confidence: float = 0.0,
    format_preset: FormatPreset | None = None,
) -> GameState:
    """Stage 8: Advance the game state by consuming a shot event.

    Applies bowling rules: strikes advance the frame, spare attempts stay on the
    same lane, the 10th frame allows up to 3 shots. Logs anomalies when the
    observed shot contradicts expectations.
    """
    if state.complete:
        state.anomalies.append(
            f"shot at frame {start_frame} after game complete"
        )
        return state

    if state.expected_lane and lane_name != state.expected_lane:
        state.anomalies.append(
            f"frame {state.current_frame} shot {state.current_shot_in_frame}: "
            f"expected lane {state.expected_lane}, got {lane_name}"
        )

    shot = ShotEvent(
        bowling_frame=state.current_frame,
        shot_in_frame=state.current_shot_in_frame,
        lane_name=lane_name,
        start_frame=start_frame,
        end_frame=end_frame,
        pin_state=pin_state,
        gutter_fallback=gutter_fallback,
        bowler_confidence=bowler_confidence,
    )
    state.shots.append(shot)

    if state.current_frame < 10:
        state = _advance_standard_frame(state, pin_state, lane_name, format_preset)
    else:
        state = _advance_tenth_frame(state, pin_state, lane_name, format_preset)

    return state


def _advance_standard_frame(
    state: GameState,
    pin_state: PinState,
    lane_name: str,
    format_preset: FormatPreset | None,
) -> GameState:
    """Advance game state for frames 1-9."""

    is_first_shot = state.current_shot_in_frame == 1

    if is_first_shot:
        if pin_state == PinState.CLEARED:
            state = _next_frame(state, lane_name, format_preset)
        elif pin_state in (PinState.SOME_STANDING, PinState.ALL_STANDING):
            state.current_shot_in_frame = 2
        else:
            state.current_shot_in_frame = 2
    else:
        state = _next_frame(state, lane_name, format_preset)

    return state


def _advance_tenth_frame(
    state: GameState,
    pin_state: PinState,
    lane_name: str,
    format_preset: FormatPreset | None,
) -> GameState:
    """Advance game state for the 10th frame (up to 3 shots)."""

    shot_num = state.current_shot_in_frame

    if shot_num == 1:
        if pin_state == PinState.CLEARED:
            state.current_shot_in_frame = 2
        elif pin_state in (PinState.SOME_STANDING, PinState.ALL_STANDING):
            state.current_shot_in_frame = 2
        else:
            state.current_shot_in_frame = 2

    elif shot_num == 2:
        prev_shot = state.shots[-2] if len(state.shots) >= 2 else None
        first_was_strike = prev_shot and prev_shot.pin_state == PinState.CLEARED

        if first_was_strike:
            state.current_shot_in_frame = 3
        elif pin_state == PinState.CLEARED:
            state.current_shot_in_frame = 3
        else:
            state.complete = True

    elif shot_num == 3:
        state.complete = True

    return state


def _next_frame(
    state: GameState,
    current_lane: str,
    format_preset: FormatPreset | None,
) -> GameState:
    """Move to the next bowling frame."""

    state.current_frame += 1
    state.current_shot_in_frame = 1

    if state.current_frame > 10:
        state.complete = True
        state.current_frame = 10
        return state

    if format_preset and format_preset.lane_alternation_pattern == "LR":
        state.expected_lane = _alternate_lane(current_lane)
    else:
        state.expected_lane = ""

    return state


def _alternate_lane(current_lane: str) -> str:
    """Simple left/right alternation."""

    if "left" in current_lane.lower():
        return current_lane.replace("left", "right").replace("Left", "Right")
    if "right" in current_lane.lower():
        return current_lane.replace("right", "left").replace("Right", "Left")
    return ""


def validate_game_completeness(
    state: GameState,
    format_preset: FormatPreset | None = None,
) -> list[str]:
    """Check the final game state for anomalies and return warnings."""

    warnings = list(state.anomalies)
    total_shots = len(state.shots)

    if not state.complete and state.current_frame <= 10:
        warnings.append(
            f"game incomplete: stopped at frame {state.current_frame} "
            f"shot {state.current_shot_in_frame}"
        )

    if format_preset:
        check = format_preset.check_shot_count(total_shots)
        if check:
            warnings.append(check)

    return warnings
