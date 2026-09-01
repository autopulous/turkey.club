"""Tests for the simplified probe-to-clip logic in _extract_shots_probe."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from turkey_club.config import LaneCalibration, SegmentationParameters
from turkey_club.detect import PersonDetection
from turkey_club.identify import BowlerTarget
from turkey_club.segment import ShotSegment


def _make_lane(name: str = "left") -> LaneCalibration:
    return LaneCalibration(
        name=name,
        approach_zone=[(0, 0), (100, 0), (100, 100), (0, 100)],
        lane_zone=[(0, 100), (100, 100), (100, 200), (0, 200)],
        pin_zone=[(0, 200), (100, 200), (100, 250), (0, 250)],
    )


def _make_target() -> BowlerTarget:
    return BowlerTarget(
        name="test",
        shirt_color_samples=[(120, 200, 200)] * 10,
    )


def _fake_capture(total_frames: int = 3000, fps: float = 30.0) -> MagicMock:
    cap = MagicMock()
    cap.get.side_effect = lambda prop: {
        1: fps,           # CAP_PROP_FPS
        7: total_frames,  # CAP_PROP_FRAME_COUNT
    }.get(prop, 0)
    cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
    return cap


@patch("turkey_club.pipeline.identify_bowler_in_frame")
@patch("turkey_club.pipeline.bbox_foot_in_polygon", return_value=True)
@patch("turkey_club.pipeline.detect_persons")
def test_single_hit_produces_one_segment(mock_detect, mock_bbox, mock_identify):
    """A single probe HIT should produce exactly one ShotSegment."""
    from turkey_club.pipeline import _extract_shots_probe

    fps = 30.0
    total_frames = 3000
    probe_interval = 10.0
    probe_interval_frames = int(probe_interval * fps)

    hit_frame = probe_interval_frames  # second probe at frame 300

    mock_detect.return_value = [PersonDetection(bbox=(10, 10, 50, 100))]
    mock_identify.side_effect = lambda *a, **kw: (
        0.85 if _fake_capture._call_count == 1 else 0.0
    )

    call_count = 0
    def identify_side_effect(*args, **kwargs):
        nonlocal call_count
        frame_pos = mock_detect.call_count
        if frame_pos == 2:
            return 0.85
        return 0.0
    mock_identify.side_effect = identify_side_effect

    cap = _fake_capture(total_frames, fps)
    shots = _extract_shots_probe(
        cap, total_frames, fps, _make_target(), [_make_lane()],
        SegmentationParameters(),
        probe_interval_seconds=probe_interval,
        shot_lookback_seconds=2.0,
        shot_duration_seconds=10.0,
        person_confidence_threshold=0.4,
        person_min_height_pixels=40,
    )

    assert len(shots) == 1
    shot = shots[0]
    assert shot.lane_name == "left"
    assert shot.bowler_confidence == 0.85
    assert shot.gutter_fallback is False
    expected_start = hit_frame - int(2.0 * fps)
    expected_end = hit_frame + int(10.0 * fps)
    assert shot.start_frame == expected_start
    assert shot.end_frame == expected_end


@patch("turkey_club.pipeline.identify_bowler_in_frame", return_value=0.85)
@patch("turkey_club.pipeline.bbox_foot_in_polygon", return_value=True)
@patch("turkey_club.pipeline.detect_persons", return_value=[PersonDetection(bbox=(10, 10, 50, 100))])
def test_forward_progress_no_duplicate_start_frames(mock_detect, mock_bbox, mock_identify):
    """Every HIT produces a segment and no two share the same (start_frame, lane_name)."""
    from turkey_club.pipeline import _extract_shots_probe

    fps = 30.0
    total_frames = 600
    cap = _fake_capture(total_frames, fps)

    shots = _extract_shots_probe(
        cap, total_frames, fps, _make_target(), [_make_lane()],
        SegmentationParameters(),
        probe_interval_seconds=10.0,
        shot_lookback_seconds=2.0,
        shot_duration_seconds=10.0,
        person_confidence_threshold=0.4,
        person_min_height_pixels=40,
    )

    seen = set()
    for shot in shots:
        key = (shot.start_frame, shot.lane_name)
        assert key not in seen, f"duplicate segment at {key}"
        seen.add(key)


@patch("turkey_club.pipeline.identify_bowler_in_frame", return_value=0.0)
@patch("turkey_club.pipeline.bbox_foot_in_polygon", return_value=True)
@patch("turkey_club.pipeline.detect_persons", return_value=[PersonDetection(bbox=(10, 10, 50, 100))])
def test_no_hits_produces_no_segments(mock_detect, mock_bbox, mock_identify):
    """When no probe exceeds the confidence threshold, no shots are emitted."""
    from turkey_club.pipeline import _extract_shots_probe

    fps = 30.0
    total_frames = 900
    cap = _fake_capture(total_frames, fps)

    shots = _extract_shots_probe(
        cap, total_frames, fps, _make_target(), [_make_lane()],
        SegmentationParameters(),
        probe_interval_seconds=10.0,
        shot_lookback_seconds=2.0,
        shot_duration_seconds=10.0,
        person_confidence_threshold=0.4,
        person_min_height_pixels=40,
    )

    assert len(shots) == 0


@patch("turkey_club.pipeline.identify_bowler_in_frame")
@patch("turkey_club.pipeline.bbox_foot_in_polygon", return_value=True)
@patch("turkey_club.pipeline.detect_persons", return_value=[PersonDetection(bbox=(10, 10, 50, 100))])
def test_hit_on_first_probe_clips_start_to_zero(mock_detect, mock_bbox, mock_identify):
    """A HIT at frame 0 should clip the start_frame to 0 (not go negative)."""
    from turkey_club.pipeline import _extract_shots_probe

    mock_identify.return_value = 0.85

    fps = 30.0
    total_frames = 900
    cap = _fake_capture(total_frames, fps)

    shots = _extract_shots_probe(
        cap, total_frames, fps, _make_target(), [_make_lane()],
        SegmentationParameters(),
        probe_interval_seconds=10.0,
        shot_lookback_seconds=2.0,
        shot_duration_seconds=10.0,
        person_confidence_threshold=0.4,
        person_min_height_pixels=40,
    )

    assert len(shots) >= 1
    assert shots[0].start_frame == 0


@patch("turkey_club.pipeline.identify_bowler_in_frame")
@patch("turkey_club.pipeline.bbox_foot_in_polygon", return_value=True)
@patch("turkey_club.pipeline.detect_persons", return_value=[PersonDetection(bbox=(10, 10, 50, 100))])
def test_correct_lane_tracked_on_hit(mock_detect, mock_bbox, mock_identify):
    """The ShotSegment should carry the lane name where the HIT occurred."""
    from turkey_club.pipeline import _extract_shots_probe

    lanes = [_make_lane("left"), _make_lane("right")]

    call_count = 0
    def identify_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            return 0.90
        return 0.0
    mock_identify.side_effect = identify_side_effect

    fps = 30.0
    total_frames = 600
    cap = _fake_capture(total_frames, fps)

    shots = _extract_shots_probe(
        cap, total_frames, fps, _make_target(), lanes,
        SegmentationParameters(),
        probe_interval_seconds=10.0,
        shot_lookback_seconds=2.0,
        shot_duration_seconds=10.0,
        person_confidence_threshold=0.4,
        person_min_height_pixels=40,
    )

    assert len(shots) >= 1
    assert shots[0].lane_name == "right"
    assert shots[0].bowler_confidence == 0.90
