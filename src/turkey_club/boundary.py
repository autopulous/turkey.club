"""Stage 6: Precise shot boundary detection via binary search against the source video."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from turkey_club.config import LaneCalibration, SegmentationParameters
from turkey_club.detect import bbox_foot_in_polygon, detect_persons, pin_zone_motion
from turkey_club.identify import BowlerTarget, identify_bowler_in_frame
from turkey_club.segment import ShotSegment, _find_settle


@dataclass
class BoundaryResult:
    """Result of a precise boundary search for one shot."""

    start_frame: int
    end_frame: int
    impact_frame: int | None = None
    settle_frame: int | None = None
    pinsetter_start_frame: int | None = None
    pinsetter_settle_frame: int | None = None
    gutter_fallback: bool = False
    pre_shot_frame: int | None = None


def find_shot_boundaries_binary(
    cap: cv2.VideoCapture,
    fps: float,
    probe_frame: int,
    previous_end_frame: int,
    lane: LaneCalibration,
    target: BowlerTarget,
    params: SegmentationParameters,
    person_confidence_threshold: float = 0.5,
    person_min_height_pixels: int = 80,
    device: str = "cpu",
) -> BoundaryResult | None:
    """Find precise start and end boundaries for a shot using binary search.

    ``probe_frame``: a frame where the target bowler IS in the approach zone.
    ``previous_end_frame``: a frame where the bowler is NOT (start of search range).
    """
    approach_start = _find_approach_start(
        cap, fps, probe_frame, previous_end_frame,
        lane, target, params,
        person_confidence_threshold, person_min_height_pixels, device,
    )
    if approach_start is None:
        return None

    pre_shot_frame = max(0, approach_start - int(fps))

    shot_end_result = _find_shot_end(
        cap, fps, approach_start, lane, params,
    )

    return BoundaryResult(
        start_frame=approach_start,
        end_frame=shot_end_result.end_frame,
        impact_frame=shot_end_result.impact_frame,
        settle_frame=shot_end_result.settle_frame,
        pinsetter_start_frame=shot_end_result.pinsetter_start_frame,
        pinsetter_settle_frame=shot_end_result.pinsetter_settle_frame,
        gutter_fallback=shot_end_result.gutter_fallback,
        pre_shot_frame=pre_shot_frame,
    )


@dataclass
class _ShotEndResult:
    end_frame: int
    impact_frame: int | None = None
    settle_frame: int | None = None
    pinsetter_start_frame: int | None = None
    pinsetter_settle_frame: int | None = None
    gutter_fallback: bool = False


def _find_approach_start(
    cap: cv2.VideoCapture,
    fps: float,
    probe_frame: int,
    previous_end_frame: int,
    lane: LaneCalibration,
    target: BowlerTarget,
    params: SegmentationParameters,
    person_confidence_threshold: float,
    person_min_height_pixels: int,
    device: str,
) -> int | None:
    """Binary search backward from probe_frame to find when the bowler first enters the approach zone.

    Uses coarse-to-fine: binary search at 1-second granularity, then linear scan
    within the final 1-second window for frame-level precision.
    """
    coarse_step = int(fps)
    low = max(0, previous_end_frame)
    high = probe_frame

    last_true = probe_frame

    while high - low > coarse_step:
        mid = (low + high) // 2
        if _bowler_in_approach(
            cap, mid, lane, target, params,
            person_confidence_threshold, person_min_height_pixels, device,
        ):
            last_true = mid
            high = mid
        else:
            low = mid

    fine_start = max(low, last_true - coarse_step)
    fine_end = last_true

    for frame_num in range(fine_start, fine_end):
        if _bowler_in_approach(
            cap, frame_num, lane, target, params,
            person_confidence_threshold, person_min_height_pixels, device,
        ):
            return frame_num

    return last_true


def _find_shot_end(
    cap: cv2.VideoCapture,
    fps: float,
    approach_start: int,
    lane: LaneCalibration,
    params: SegmentationParameters,
) -> _ShotEndResult:
    """Find the shot end by detecting pin impact, settle, and pinsetter sweep.

    Handles both normal shots (impact → settle → pinsetter) and gutter balls
    (no impact → skip to pinsetter sweep).
    """
    min_ball_travel = int(params.min_ball_travel_seconds * fps)
    max_ball_travel = int(params.max_ball_travel_seconds * fps)
    max_shot = int(params.max_shot_duration_seconds * fps)
    pin_threshold = params.pin_impact_threshold
    settle_threshold = params.pin_motion_threshold
    settle_frames = params.pin_settle_frames
    pinsetter_max = int(params.pinsetter_sweep_max_seconds * fps)

    impact_search_start = approach_start + min_ball_travel
    impact_search_end = approach_start + max_ball_travel
    shot_end_limit = approach_start + max_shot

    impact_frame = _find_pin_impact(
        cap, impact_search_start, impact_search_end,
        lane.pin_zone, pin_threshold,
    )

    if impact_frame is not None:
        settle_search_end = min(
            impact_frame + int(params.max_impact_to_settle_seconds * fps),
            shot_end_limit,
        )
        motion_values = _read_pin_motion_range(
            cap, impact_frame, settle_search_end, lane.pin_zone,
        )
        settle_offset = _find_settle_in_values(
            motion_values, settle_threshold, settle_frames,
        )

        if settle_offset is not None:
            settle_frame = impact_frame + settle_offset
        else:
            settle_frame = min(settle_search_end, shot_end_limit)

        pinsetter_start = _find_next_motion_spike(
            cap, settle_frame, min(settle_frame + pinsetter_max, shot_end_limit),
            lane.pin_zone, pin_threshold,
        )

        pinsetter_settle = None
        if pinsetter_start is not None:
            pinsetter_search_end = min(pinsetter_start + pinsetter_max, shot_end_limit)
            ps_motion = _read_pin_motion_range(
                cap, pinsetter_start, pinsetter_search_end, lane.pin_zone,
            )
            ps_settle_offset = _find_settle_in_values(
                ps_motion, settle_threshold, settle_frames,
            )
            if ps_settle_offset is not None:
                pinsetter_settle = pinsetter_start + ps_settle_offset
            else:
                pinsetter_settle = pinsetter_search_end

        end_frame = pinsetter_settle or settle_frame
        return _ShotEndResult(
            end_frame=end_frame,
            impact_frame=impact_frame,
            settle_frame=settle_frame,
            pinsetter_start_frame=pinsetter_start,
            pinsetter_settle_frame=pinsetter_settle,
        )

    pinsetter_start = _find_next_motion_spike(
        cap, impact_search_end, shot_end_limit,
        lane.pin_zone, pin_threshold,
    )

    if pinsetter_start is not None:
        pinsetter_search_end = min(pinsetter_start + pinsetter_max, shot_end_limit)
        ps_motion = _read_pin_motion_range(
            cap, pinsetter_start, pinsetter_search_end, lane.pin_zone,
        )
        ps_settle_offset = _find_settle_in_values(
            ps_motion, settle_threshold, settle_frames,
        )
        pinsetter_settle = None
        if ps_settle_offset is not None:
            pinsetter_settle = pinsetter_start + ps_settle_offset
        else:
            pinsetter_settle = pinsetter_search_end

        return _ShotEndResult(
            end_frame=pinsetter_settle,
            pinsetter_start_frame=pinsetter_start,
            pinsetter_settle_frame=pinsetter_settle,
            gutter_fallback=True,
        )

    gutter_end = approach_start + int(params.gutter_fallback_seconds_after_onset * fps)
    return _ShotEndResult(
        end_frame=min(gutter_end, shot_end_limit),
        gutter_fallback=True,
    )


def _bowler_in_approach(
    cap: cv2.VideoCapture,
    frame_number: int,
    lane: LaneCalibration,
    target: BowlerTarget,
    params: SegmentationParameters,
    person_confidence_threshold: float,
    person_min_height_pixels: int,
    device: str,
) -> bool:
    """Check whether the target bowler is in the approach zone at ``frame_number``."""

    frame = read_frame(cap, frame_number)
    if frame is None:
        return False

    persons = detect_persons(
        frame,
        confidence_threshold=person_confidence_threshold,
        min_height_pixels=person_min_height_pixels,
        device=device,
    )

    for detection in persons:
        if not bbox_foot_in_polygon(detection.bbox, lane.approach_zone):
            continue
        confidence = identify_bowler_in_frame(
            frame, detection.bbox, target,
            use_ocr=False, keypoints=detection.keypoints,
        )
        if confidence >= params.bowler_confidence_threshold:
            return True

    return False


def _find_pin_impact(
    cap: cv2.VideoCapture,
    search_start: int,
    search_end: int,
    pin_polygon: list[tuple[int, int]],
    threshold: float,
) -> int | None:
    """Binary search for the first frame with pin zone motion above threshold."""

    low = search_start
    high = search_end
    result = None

    while low < high:
        mid = (low + high) // 2
        motion = _read_pin_motion_at(cap, mid, pin_polygon)
        if motion > threshold:
            result = mid
            high = mid
        else:
            low = mid + 1

    if result is not None:
        return result

    for frame_num in range(search_start, min(search_end, search_start + 30)):
        motion = _read_pin_motion_at(cap, frame_num, pin_polygon)
        if motion > threshold:
            return frame_num

    return None


def _find_next_motion_spike(
    cap: cv2.VideoCapture,
    search_start: int,
    search_end: int,
    pin_polygon: list[tuple[int, int]],
    threshold: float,
) -> int | None:
    """Linear scan for the next motion spike above threshold after a quiet period."""

    step = max(1, (search_end - search_start) // 60)
    for frame_num in range(search_start, search_end, step):
        motion = _read_pin_motion_at(cap, frame_num, pin_polygon)
        if motion > threshold:
            fine_start = max(search_start, frame_num - step)
            for fine_frame in range(fine_start, min(frame_num + step, search_end)):
                fine_motion = _read_pin_motion_at(cap, fine_frame, pin_polygon)
                if fine_motion > threshold:
                    return fine_frame
            return frame_num
    return None


def _read_pin_motion_at(
    cap: cv2.VideoCapture,
    frame_number: int,
    pin_polygon: list[tuple[int, int]],
) -> float:
    """Read two consecutive frames and compute pin zone motion."""

    prev_frame = read_frame(cap, max(0, frame_number - 1))
    curr_frame = read_frame(cap, frame_number)
    if prev_frame is None or curr_frame is None:
        return 0.0
    return pin_zone_motion(curr_frame, prev_frame, pin_polygon)


def _read_pin_motion_range(
    cap: cv2.VideoCapture,
    start: int,
    end: int,
    pin_polygon: list[tuple[int, int]],
) -> list[float]:
    """Read pin zone motion values for a range of frames."""

    values = []
    prev_frame = read_frame(cap, max(0, start - 1))
    for frame_num in range(start, end):
        curr_frame = read_frame(cap, frame_num)
        if prev_frame is not None and curr_frame is not None:
            values.append(pin_zone_motion(curr_frame, prev_frame, pin_polygon))
        else:
            values.append(0.0)
        prev_frame = curr_frame
    return values


def _find_settle_in_values(
    motion_values: list[float],
    threshold: float,
    required_consecutive: int,
) -> int | None:
    """Find settle point within a pre-computed motion value list. Returns offset from start."""

    consecutive = 0
    for i, val in enumerate(motion_values):
        if val < threshold:
            consecutive += 1
            if consecutive >= required_consecutive:
                return i
        else:
            consecutive = 0
    return None


def read_frame(cap: cv2.VideoCapture, frame_number: int) -> np.ndarray | None:
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    ret, frame = cap.read()
    if not ret:
        return None
    return frame


def boundary_results_to_segments(
    results: list[tuple[BoundaryResult, str, float]],
) -> list[ShotSegment]:
    """Convert BoundaryResult tuples to ShotSegment list."""

    segments = []
    for boundary, lane_name, confidence in results:
        segments.append(ShotSegment(
            lane_name=lane_name,
            start_frame=boundary.start_frame,
            end_frame=boundary.end_frame,
            bowler_confidence=confidence,
            gutter_fallback=boundary.gutter_fallback,
        ))
    segments.sort(key=lambda s: s.start_frame)
    return segments
