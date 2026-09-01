"""Tests for temporal validation and game state tracking (Stages 5d-5f, 8)."""
from __future__ import annotations

import pytest

from turkey_club.config import GameState, PinState
from turkey_club.formats import PRESETS
from turkey_club.validate import (
    advance_game_state,
    compute_cadence,
    detect_gaps,
    filter_cadence_violations,
    validate_game_completeness,
    validate_shot_continuity,
)


def test_continuity_groups_close_frames():
    """Frames within the gap threshold are grouped as one shot."""
    appearances = [
        (0, "left"),
        (300, "left"),
        (600, "left"),
    ]
    groups = validate_shot_continuity(appearances, fps=30.0, probe_interval_seconds=10.0)
    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_continuity_splits_on_large_gap():
    """A large gap between frames produces separate shot groups."""
    appearances = [
        (0, "left"),
        (300, "left"),
        (30000, "right"),
        (30300, "right"),
    ]
    groups = validate_shot_continuity(appearances, fps=30.0, probe_interval_seconds=10.0)
    assert len(groups) == 2


def test_compute_cadence_returns_median():
    """Cadence should be the median of inter-shot intervals."""
    appearances = [
        (0, "left"),
        (9000, "right"),
        (27000, "left"),
        (36000, "right"),
    ]
    cadence = compute_cadence(appearances, fps=30.0)
    assert cadence is not None
    assert cadence > 0


def test_compute_cadence_insufficient_shots():
    """Fewer than 3 shots should return None."""
    appearances = [
        (0, "left"),
        (9000, "right"),
    ]
    cadence = compute_cadence(appearances, fps=30.0)
    assert cadence is None


def test_game_state_strike_advances_frame():
    """A strike on the first shot should advance to the next bowling frame."""
    state = GameState(expected_lane="left")
    state = advance_game_state(
        state, PinState.CLEARED, "left", 0, 300,
        format_preset=PRESETS["pba-qualifying"],
    )
    assert state.current_frame == 2
    assert state.current_shot_in_frame == 1
    assert len(state.shots) == 1


def test_game_state_spare_attempt_stays():
    """Pins remaining on first shot should keep the same frame for a spare attempt."""
    state = GameState(expected_lane="left")
    state = advance_game_state(
        state, PinState.SOME_STANDING, "left", 0, 300,
    )
    assert state.current_frame == 1
    assert state.current_shot_in_frame == 2


def test_game_state_spare_advances():
    """A spare (second shot clears pins) should advance to the next frame."""
    state = GameState(expected_lane="left")
    state = advance_game_state(state, PinState.SOME_STANDING, "left", 0, 300)
    state = advance_game_state(state, PinState.CLEARED, "left", 400, 700)
    assert state.current_frame == 2
    assert state.current_shot_in_frame == 1


def test_game_state_open_frame():
    """An open frame (second shot, pins remaining) should advance to the next frame."""
    state = GameState()
    state = advance_game_state(state, PinState.SOME_STANDING, "left", 0, 300)
    state = advance_game_state(state, PinState.SOME_STANDING, "left", 400, 700)
    assert state.current_frame == 2


def test_game_state_gutter_ball_expects_spare():
    """A gutter ball should expect a spare attempt on the same lane."""
    state = GameState()
    state = advance_game_state(
        state, PinState.ALL_STANDING, "left", 0, 300,
        gutter_fallback=True,
    )
    assert state.current_frame == 1
    assert state.current_shot_in_frame == 2


def test_game_state_tenth_frame_strike_bonus():
    """A strike in the 10th frame should allow a second shot."""
    state = GameState(current_frame=10, current_shot_in_frame=1)
    state = advance_game_state(state, PinState.CLEARED, "left", 0, 300)
    assert state.current_frame == 10
    assert state.current_shot_in_frame == 2
    assert state.complete is False


def test_game_state_tenth_frame_spare_bonus():
    """A spare in the 10th frame should allow a third shot."""
    state = GameState(current_frame=10, current_shot_in_frame=1)
    state = advance_game_state(state, PinState.SOME_STANDING, "left", 0, 300)
    state = advance_game_state(state, PinState.CLEARED, "left", 400, 700)
    assert state.current_frame == 10
    assert state.current_shot_in_frame == 3
    assert state.complete is False


def test_game_state_tenth_frame_open_completes():
    """An open frame in the 10th should complete the game."""
    state = GameState(current_frame=10, current_shot_in_frame=1)
    state = advance_game_state(state, PinState.SOME_STANDING, "left", 0, 300)
    state = advance_game_state(state, PinState.SOME_STANDING, "left", 400, 700)
    assert state.complete is True


def test_game_state_wrong_lane_anomaly():
    """A shot on the wrong lane should log an anomaly."""
    state = GameState(expected_lane="left")
    state = advance_game_state(state, PinState.CLEARED, "right", 0, 300)
    assert len(state.anomalies) == 1
    assert "expected lane left" in state.anomalies[0]


def test_validate_completeness_incomplete_game():
    """An incomplete game should produce a warning."""
    state = GameState(current_frame=5, current_shot_in_frame=1)
    warnings = validate_game_completeness(state)
    assert any("incomplete" in w for w in warnings)


def test_full_game_all_strikes():
    """12 consecutive strikes should complete the game."""
    state = GameState()
    preset = PRESETS["pba-qualifying"]
    for i in range(12):
        lane = "left" if i % 2 == 0 else "right"
        state = advance_game_state(
            state, PinState.CLEARED, lane,
            i * 300, i * 300 + 200,
            format_preset=preset,
        )

    assert state.complete is True
    assert len(state.shots) == 12


# ---------- filter_cadence_violations tests ----------

PBA = PRESETS["pba-qualifying"]
FPS = 30.0


def _group(frame: int, lane: str) -> list[tuple[int, str]]:
    """Convenience: build a one-appearance shot group"""
    return [(frame, lane)]


def _groups_at(specs: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    return [_group(f, l) for f, l in specs]


def test_cadence_filter_no_preset():
    groups = _groups_at([(0, "left"), (300, "right")])
    assert filter_cadence_violations(groups, FPS, format_preset=None) == groups


def test_cadence_filter_non_alternating_format():
    groups = _groups_at([(0, "left"), (300, "left")])
    preset = PRESETS["open-bowling"]
    assert filter_cadence_violations(groups, FPS, preset) == groups


def test_cadence_filter_no_violations():
    """Well-spaced alternating groups pass through unchanged"""
    groups = _groups_at([
        (0, "left"),
        (7200, "right"),
        (14400, "left"),
        (21600, "right"),
    ])
    result = filter_cadence_violations(groups, FPS, PBA)
    assert len(result) == 4


def test_cadence_filter_a_trims_overpopulated_candidate():
    """Three consecutive same-lane groups within 75s are trimmed to 2"""
    groups = _groups_at([
        (0, "left"),
        (9000, "right"),
        (10500, "right"),
        (12000, "right"),
        (21600, "left"),
    ])
    result = filter_cadence_violations(groups, FPS, PBA)
    assert len(result) == 4
    frames = [g[0][0] for g in result]
    assert 12000 not in frames


def test_cadence_filter_b_removes_same_lane_too_close():
    """Two same-lane candidates closer than expected_cadence are pruned"""
    groups = _groups_at([
        (0, "left"),
        (9000, "right"),
        (14400, "right"),
        (21600, "left"),
    ])
    result = filter_cadence_violations(groups, FPS, PBA)
    frames = [g[0][0] for g in result]
    assert 14400 not in frames
    assert len(result) == 3


def test_cadence_filter_b_keeps_earlier_candidate():
    """When two same-lane candidates conflict, the earlier one always wins"""
    earlier = [(9000, "right")]
    later = [(14400, "right"), (14700, "right"), (15000, "right")]
    groups = [
        _group(0, "left"),
        earlier,
        later,
        _group(21600, "left"),
    ]
    result = filter_cadence_violations(groups, FPS, PBA)
    result_frames = {g[0][0] for g in result}
    assert 9000 in result_frames
    assert 14400 not in result_frames


def test_cadence_filter_game1_scenario():
    """Reproduces the Game 1 data: 19 groups → 16 after filtering"""
    groups = _groups_at([
        (2100, "left"),
        (9000, "right"),
        (10500, "right"),
        (12000, "right"),
        (15600, "right"),
        (22500, "right"),
        (26700, "left"),
        (28500, "left"),
        (34200, "right"),
        (38100, "left"),
        (39600, "left"),
        (42300, "right"),
        (43800, "right"),
        (49500, "right"),
        (51900, "left"),
        (59400, "left"),
        (62700, "left"),
        (70500, "right"),
        (72900, "left"),
    ])
    result = filter_cadence_violations(groups, FPS, PBA)
    assert len(result) == 16
