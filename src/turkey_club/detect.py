"""Per-frame detection: persons, ball position in lane, pin-zone motion."""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

import cv2
import numpy as np

from turkey_club.config import Polygon

if TYPE_CHECKING:
    from ultralytics import YOLO

PersonBBox = tuple[int, int, int, int]

DEFAULT_PERSON_MODEL = "yolov8n.pt"


@lru_cache(maxsize=2)
def _load_person_model(model_name: str) -> "YOLO":
    from ultralytics import YOLO

    return YOLO(model_name)


def detect_persons(
    frame: np.ndarray,
    confidence_threshold: float = 0.5,
    min_height_pixels: int = 80,
    model_name: str = DEFAULT_PERSON_MODEL,
) -> list[PersonBBox]:
    """Return person bounding boxes (x1, y1, x2, y2) detected in ``frame``.

    Detections below ``confidence_threshold`` (passed through to YOLO) or shorter
    than ``min_height_pixels`` are dropped — the latter filter keeps distant
    spectators from polluting the bowler-identification step.
    """
    model = _load_person_model(model_name)
    results = model(frame, classes=[0], conf=confidence_threshold, verbose=False)
    if not results:
        return []
    boxes_tensor = results[0].boxes.xyxy
    if boxes_tensor is None or len(boxes_tensor) == 0:
        return []
    raw = boxes_tensor.cpu().numpy().astype(int)
    return [
        (int(x1), int(y1), int(x2), int(y2))
        for x1, y1, x2, y2 in raw
        if (y2 - y1) >= min_height_pixels
    ]


def bbox_foot_in_polygon(bbox: PersonBBox, polygon: Polygon) -> bool:
    """True iff the bottom-center of ``bbox`` (the person's foot position) lies in ``polygon``."""
    x1, _, x2, y2 = bbox
    cx = (x1 + x2) / 2.0
    cy = float(y2)
    pts = np.array(polygon, dtype=np.int32)
    return cv2.pointPolygonTest(pts, (cx, cy), measureDist=False) >= 0


def detect_ball_in_lane(
    frame: np.ndarray,
    prev_frame: np.ndarray,
    lane_polygon: Polygon,
    min_blob_area: int = 50,
    max_blob_area: int = 3000,
    motion_threshold: int = 25,
) -> tuple[int, int] | None:
    """Detect the bowling ball within ``lane_polygon`` via motion-blob analysis.

    Returns the (cx, cy) centroid of the largest moving blob inside the lane mask
    whose area falls in ``[min_blob_area, max_blob_area]``, or None.
    """
    if frame.shape != prev_frame.shape:
        return None
    gray_now = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray_prev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(gray_now, gray_prev)
    _, binary = cv2.threshold(diff, motion_threshold, 255, cv2.THRESH_BINARY)

    mask = np.zeros_like(binary)
    cv2.fillPoly(mask, [np.array(lane_polygon, dtype=np.int32)], 255)
    binary = cv2.bitwise_and(binary, mask)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    qualifying = [c for c in contours if min_blob_area <= cv2.contourArea(c) <= max_blob_area]
    if not qualifying:
        return None

    largest = max(qualifying, key=cv2.contourArea)
    moments = cv2.moments(largest)
    if moments["m00"] == 0:
        return None
    cx = int(moments["m10"] / moments["m00"])
    cy = int(moments["m01"] / moments["m00"])
    return (cx, cy)


def pin_zone_motion(
    frame: np.ndarray,
    prev_frame: np.ndarray,
    pin_polygon: Polygon,
) -> float:
    """Mean absolute frame difference within ``pin_polygon`` — a proxy for pin motion."""
    if frame.shape != prev_frame.shape:
        return 0.0
    gray_now = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray_prev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(gray_now, gray_prev)

    mask = np.zeros_like(diff)
    cv2.fillPoly(mask, [np.array(pin_polygon, dtype=np.int32)], 255)
    pin_pixel_count = int(np.count_nonzero(mask))
    if pin_pixel_count == 0:
        return 0.0
    masked_diff = cv2.bitwise_and(diff, mask)
    return float(masked_diff.sum()) / pin_pixel_count
