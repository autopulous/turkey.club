"""Tests for shot boundary detection (Stage 6)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from turkey_club.boundary import _find_settle_in_values, boundary_results_to_segments, BoundaryResult
from turkey_club.segment import ShotSegment


def test_find_settle_in_values_basic():
    """Settle should be found after required consecutive low-motion frames."""
    values = [5.0, 5.0, 5.0, 0.5, 0.5, 0.5, 0.5, 0.5]
    result = _find_settle_in_values(values, threshold=1.0, required_consecutive=4)
    assert result == 6


def test_find_settle_in_values_not_enough_consecutive():
    """No settle if low-motion frames are interrupted."""
    values = [5.0, 0.5, 0.5, 5.0, 0.5, 0.5]
    result = _find_settle_in_values(values, threshold=1.0, required_consecutive=4)
    assert result is None


def test_find_settle_in_values_empty():
    """Empty values should return None."""
    result = _find_settle_in_values([], threshold=1.0, required_consecutive=4)
    assert result is None


def test_find_settle_in_values_all_low():
    """All values below threshold should settle at required_consecutive - 1."""
    values = [0.1, 0.1, 0.1, 0.1, 0.1]
    result = _find_settle_in_values(values, threshold=1.0, required_consecutive=3)
    assert result == 2


def test_boundary_results_to_segments():
    """BoundaryResult tuples should convert to sorted ShotSegments."""
    results = [
        (BoundaryResult(start_frame=600, end_frame=900), "right", 0.8),
        (BoundaryResult(start_frame=100, end_frame=400), "left", 0.9),
    ]
    segments = boundary_results_to_segments(results)
    assert len(segments) == 2
    assert segments[0].start_frame == 100
    assert segments[0].lane_name == "left"
    assert segments[1].start_frame == 600
    assert segments[1].lane_name == "right"


def test_boundary_result_gutter_fallback():
    """Gutter fallback should propagate to ShotSegment."""
    results = [
        (BoundaryResult(start_frame=100, end_frame=400, gutter_fallback=True), "left", 0.5),
    ]
    segments = boundary_results_to_segments(results)
    assert segments[0].gutter_fallback is True
