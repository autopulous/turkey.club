"""Stage 1: Sparse frame census — extract frames, detect persons, compute identity features."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from turkey_club.config import (
    CensusPersonRecord,
    CensusRecord,
    LaneCalibration,
    VenueCalibration,
)
from turkey_club.detect import (
    DEFAULT_PERSON_MODEL,
    KEYPOINT_LEFT_EAR,
    KEYPOINT_LEFT_EYE,
    KEYPOINT_LEFT_HIP,
    KEYPOINT_LEFT_SHOULDER,
    KEYPOINT_NOSE,
    KEYPOINT_RIGHT_EAR,
    KEYPOINT_RIGHT_EYE,
    KEYPOINT_RIGHT_HIP,
    KEYPOINT_RIGHT_SHOULDER,
    PersonDetection,
    bbox_foot_in_polygon,
    detect_persons,
)
from turkey_club.identify import compute_crop_histogram, crop_back_from_keypoints, preprocess_for_histogram

MIN_SHOULDER_CONFIDENCE = 0.5
MIN_SHOULDER_SPAN_RATIO = 0.25
FACE_CONFIDENCE_THRESHOLD = 0.5
FACE_CONFIDENCE_SUM_THRESHOLD = 1.8

SETUP_SCORE_SKIP_THRESHOLD = 3.5
SETUP_SEARCH_MAX_SECONDS = 5.0
SETUP_SEARCH_STEP_FRAMES = 10


def setup_stance_score(detection: PersonDetection) -> float:
    """Rate how likely this detection shows a bowler in their pre-delivery setup stance.

    Higher score = more setup-like.  The score combines bounding-box
    compactness (tall and narrow = upright, arms close) with shoulder
    levelness (level shoulders = no delivery-arm tilt).
    """
    x1, y1, x2, y2 = detection.bbox
    bbox_width = max(x2 - x1, 1)
    bbox_height = max(y2 - y1, 1)
    compactness = bbox_height / bbox_width

    kp = detection.keypoints
    if kp is not None:
        ls = kp[KEYPOINT_LEFT_SHOULDER]
        rs = kp[KEYPOINT_RIGHT_SHOULDER]
        if ls[2] >= MIN_SHOULDER_CONFIDENCE and rs[2] >= MIN_SHOULDER_CONFIDENCE:
            shoulder_span = abs(ls[0] - rs[0])
            if shoulder_span > 1:
                shoulder_tilt = abs(ls[1] - rs[1])
                tilt_penalty = shoulder_tilt / shoulder_span
                return compactness * max(0.0, 1.0 - tilt_penalty)

    return compactness


def find_setup_frame(
    cap: cv2.VideoCapture,
    census_frame: int,
    lane: LaneCalibration,
    person_confidence_threshold: float,
    person_min_height_pixels: int,
    model_name: str,
    device: str,
    max_search_seconds: float = SETUP_SEARCH_MAX_SECONDS,
    search_step_frames: int = SETUP_SEARCH_STEP_FRAMES,
) -> tuple[int, np.ndarray, PersonDetection] | None:
    """Search backward (then forward) for the frame with the best setup-stance score.

    Returns (frame_number, frame_image, detection) for the best candidate,
    or None if no back-facing person is found in the approach zone within
    the search window.
    """
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    max_search_frames = int(max_search_seconds * fps)

    best: tuple[float, int, np.ndarray, PersonDetection] | None = None

    def _probe(target_frame: int) -> None:
        nonlocal best
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        if not ret:
            return
        detections = detect_persons(
            frame,
            confidence_threshold=person_confidence_threshold,
            min_height_pixels=person_min_height_pixels,
            model_name=model_name,
            device=device,
        )
        for det in detections:
            if not shoulders_visible(det.keypoints, MIN_SHOULDER_CONFIDENCE):
                continue
            if not bbox_foot_in_polygon(det.bbox, lane.approach_zone):
                continue
            score = setup_stance_score(det)
            if best is None or score > best[0]:
                best = (score, target_frame, frame.copy(), det)

    for offset in range(search_step_frames, max_search_frames + 1, search_step_frames):
        target = census_frame - offset
        if target < 0:
            break
        _probe(target)

    for offset in range(search_step_frames, max_search_frames + 1, search_step_frames):
        target = census_frame + offset
        if target >= total_frames:
            break
        _probe(target)

    if best is None:
        return None
    return best[1], best[2], best[3]


def run_census(
    video_path: str | Path,
    venue: VenueCalibration,
    output_dir: Path,
    interval_seconds: float = 10.0,
    person_confidence_threshold: float = 0.5,
    person_min_height_pixels: int = 80,
    model_name: str = DEFAULT_PERSON_MODEL,
    device: str = "cpu",
) -> list[CensusRecord]:
    """Extract frames at ``interval_seconds`` and run person detection + identity feature extraction.

    Returns a list of CensusRecord for frames where at least one person was detected
    in an approach zone. Frame images and JSON sidecars are written to ``output_dir``.
    Saved JPEGs are cropped to the venue bounds; stored bbox/keypoint coordinates are
    offset accordingly so the debug viewer can draw on them directly.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    vx1, vy1, vx2, vy2 = venue.bounds_rect()
    vx1 = max(0, vx1)
    vy1 = max(0, vy1)

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    interval_frames = int(interval_seconds * fps)

    if interval_frames < 1:
        interval_frames = 1

    records: list[CensusRecord] = []
    frame_number = 0

    while frame_number < total_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ret, frame = cap.read()
        if not ret:
            frame_number += interval_frames
            continue

        frame_h, frame_w = frame.shape[:2]
        crop_x2 = min(vx2, frame_w)
        crop_y2 = min(vy2, frame_h)

        detections = detect_persons(
            frame,
            confidence_threshold=person_confidence_threshold,
            min_height_pixels=person_min_height_pixels,
            model_name=model_name,
            device=device,
        )

        census_persons: list[CensusPersonRecord] = []
        for detection in detections:
            if not shoulders_visible(detection.keypoints, MIN_SHOULDER_CONFIDENCE):
                continue

            lane = _find_approach_lane(detection.bbox, venue.lanes)
            if lane is None:
                continue

            use_frame = frame
            use_detection = detection
            setup_info = ""
            current_score = setup_stance_score(detection)

            if current_score < SETUP_SCORE_SKIP_THRESHOLD:
                result = find_setup_frame(
                    cap, frame_number, lane,
                    person_confidence_threshold, person_min_height_pixels,
                    model_name, device,
                )
                if result is not None:
                    setup_frame_num, setup_frame_img, setup_det = result
                    setup_score = setup_stance_score(setup_det)
                    if setup_score > current_score:
                        use_frame = setup_frame_img
                        use_detection = setup_det
                        setup_info = f" setup@{setup_frame_num} ({setup_score:.2f}>{current_score:.2f})"

            if setup_info:
                print(
                    f"    frame {frame_number} person in {lane.name}:{setup_info}",
                    flush=True,
                )

            crop = crop_back_from_keypoints(use_frame, use_detection.bbox, use_detection.keypoints)
            if 0 == crop.size:
                continue

            hist = compute_crop_histogram(crop)

            bx1, by1, bx2, by2 = detection.bbox
            offset_bbox = (bx1 - vx1, by1 - vy1, bx2 - vx1, by2 - vy1)

            offset_keypoints = None
            if detection.keypoints is not None:
                offset_keypoints = [
                    (kp[0] - vx1, kp[1] - vy1, kp[2])
                    for kp in detection.keypoints
                ]

            person_idx = len(census_persons)
            crop_filename = f"{frame_number:06d}_p{person_idx:02d}_crop.jpg"
            enhanced_filename = f"{frame_number:06d}_p{person_idx:02d}_enhanced.jpg"
            cv2.imwrite(str(output_dir / crop_filename), crop)
            cv2.imwrite(str(output_dir / enhanced_filename), preprocess_for_histogram(crop))

            census_persons.append(CensusPersonRecord(
                bbox=offset_bbox,
                lane_name=lane.name,
                histogram=hist.flatten().tolist(),
                keypoints=offset_keypoints,
            ))

        if census_persons:
            record = CensusRecord(
                frame_number=frame_number,
                persons=census_persons,
            )
            records.append(record)

            frame_filename = f"{frame_number:06d}.jpg"
            sidecar_filename = f"{frame_number:06d}.json"
            venue_crop = frame[vy1:crop_y2, vx1:crop_x2]
            cv2.imwrite(str(output_dir / frame_filename), venue_crop)
            record.save(output_dir / sidecar_filename)

            print(
                f"  census frame {frame_number:>6d}: "
                f"{len(census_persons)} person(s) in approach zones",
                flush=True,
            )

        frame_number += interval_frames

    cap.release()
    return records


def load_census_records(output_dir: Path) -> list[CensusRecord]:
    """Load all census records from JSON sidecars in ``output_dir``."""

    records = []
    for sidecar_path in sorted(output_dir.glob("*.json")):
        records.append(CensusRecord.load(sidecar_path))
    return records


def shoulders_visible(
    keypoints: list[tuple[float, float, float]] | None,
    min_confidence: float,
) -> bool:
    """True when both shoulders are confident and the back crop would be viable.

    Rejects two failure modes:
    - **Sideways:** shoulder span too narrow relative to torso height
    - **Front-facing:** face keypoints (nose or both eyes) are confident,
      meaning the camera sees the front of the person, not the back
    """
    if keypoints is None:
        return False
    left_shoulder = keypoints[KEYPOINT_LEFT_SHOULDER]
    right_shoulder = keypoints[KEYPOINT_RIGHT_SHOULDER]
    if left_shoulder[2] < min_confidence or right_shoulder[2] < min_confidence:
        return False

    nose = keypoints[KEYPOINT_NOSE]
    left_eye = keypoints[KEYPOINT_LEFT_EYE]
    right_eye = keypoints[KEYPOINT_RIGHT_EYE]
    left_ear = keypoints[KEYPOINT_LEFT_EAR]
    right_ear = keypoints[KEYPOINT_RIGHT_EAR]
    if nose[2] >= FACE_CONFIDENCE_THRESHOLD:
        return False
    if left_eye[2] >= FACE_CONFIDENCE_THRESHOLD and right_eye[2] >= FACE_CONFIDENCE_THRESHOLD:
        return False
    face_sum = nose[2] + left_eye[2] + right_eye[2] + left_ear[2] + right_ear[2]
    if face_sum >= FACE_CONFIDENCE_SUM_THRESHOLD:
        return False

    left_hip = keypoints[KEYPOINT_LEFT_HIP]
    right_hip = keypoints[KEYPOINT_RIGHT_HIP]
    if left_hip[2] >= min_confidence and right_hip[2] >= min_confidence:
        shoulder_span = abs(left_shoulder[0] - right_shoulder[0])
        torso_height = max(left_hip[1], right_hip[1]) - min(left_shoulder[1], right_shoulder[1])
        if torso_height > 1 and shoulder_span / torso_height < MIN_SHOULDER_SPAN_RATIO:
            return False

    return True


def _find_approach_lane(
    bbox: tuple[int, int, int, int],
    lanes: list[LaneCalibration],
) -> LaneCalibration | None:
    """Return the lane whose approach zone contains the person's foot, or None"""

    for lane in lanes:
        if bbox_foot_in_polygon(bbox, lane.approach_zone):
            return lane
    return None
