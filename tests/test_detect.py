"""Tests for detection utilities."""
import numpy as np

from turkey_club.detect import frame_has_motion


def test_frame_has_motion_first_frame() -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    assert frame_has_motion(frame, None) is True


def test_frame_has_motion_identical_frames() -> None:
    frame = np.full((100, 100, 3), 128, dtype=np.uint8)
    assert frame_has_motion(frame, frame.copy()) is False


def test_frame_has_motion_different_frames() -> None:
    frame_a = np.zeros((100, 100, 3), dtype=np.uint8)
    frame_b = np.full((100, 100, 3), 50, dtype=np.uint8)
    assert frame_has_motion(frame_b, frame_a, threshold=3.0) is True


def test_frame_has_motion_below_threshold() -> None:
    frame_a = np.full((100, 100, 3), 100, dtype=np.uint8)
    frame_b = np.full((100, 100, 3), 101, dtype=np.uint8)
    assert frame_has_motion(frame_b, frame_a, threshold=3.0) is False
