"""Tests for pin state analysis (Stage 7)."""
from __future__ import annotations

import pytest

from turkey_club.config import PinState


def test_gutter_ball_all_standing():
    """A gutter ball should always report ALL_STANDING without visual analysis."""
    from turkey_club.pinstate import analyze_pin_state
    from unittest.mock import MagicMock

    from turkey_club.config import LaneCalibration

    cap = MagicMock()
    lane = LaneCalibration(
        name="left",
        approach_zone=[(0, 0), (100, 0), (100, 100), (0, 100)],
        lane_zone=[(0, 100), (100, 100), (100, 200), (0, 200)],
        pin_zone=[(0, 200), (100, 200), (100, 250), (0, 250)],
    )

    result = analyze_pin_state(
        cap, pre_shot_frame=0, post_settle_frame=100,
        lane=lane, gutter_fallback=True,
    )
    assert result == PinState.ALL_STANDING
    cap.set.assert_not_called()


def test_pin_state_enum_values():
    """PinState enum should have the expected values."""
    assert PinState.UNKNOWN.value == "unknown"
    assert PinState.ALL_STANDING.value == "all_standing"
    assert PinState.SOME_STANDING.value == "some_standing"
    assert PinState.CLEARED.value == "cleared"
