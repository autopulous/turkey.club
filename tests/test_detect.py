"""Tests for detection utilities."""
import numpy as np

from turkey_club.detect import PersonDetection, detect_device, frame_has_motion


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


def test_detect_device_explicit_cpu() -> None:
    assert detect_device("cpu") == "cpu"


def test_detect_device_explicit_cuda() -> None:
    assert detect_device("cuda") == "cuda"


def test_detect_device_auto_resolves() -> None:
    result = detect_device("auto")
    assert result in ("cpu", "cuda")


def test_person_detection_defaults() -> None:
    det = PersonDetection(bbox=(10, 20, 50, 100))
    assert det.bbox == (10, 20, 50, 100)
    assert det.keypoints is None


def test_person_detection_with_keypoints() -> None:
    kps = [(float(i), float(i * 2), 0.9) for i in range(17)]
    det = PersonDetection(bbox=(0, 0, 100, 200), keypoints=kps)
    assert det.keypoints is not None
    assert len(det.keypoints) == 17
    assert det.keypoints[5] == (5.0, 10.0, 0.9)


def test_person_detection_is_frozen() -> None:
    det = PersonDetection(bbox=(1, 2, 3, 4))
    try:
        det.bbox = (5, 6, 7, 8)  # type: ignore[misc]
        assert False, "should have raised FrozenInstanceError"
    except AttributeError:
        pass
