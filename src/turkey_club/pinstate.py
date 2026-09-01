"""Stage 7: Pin state analysis — determine whether pins remain after each shot."""
from __future__ import annotations

import cv2
import numpy as np

from turkey_club.config import LaneCalibration, PinState, Polygon


def analyze_pin_state(
    cap: cv2.VideoCapture,
    pre_shot_frame: int,
    post_settle_frame: int,
    lane: LaneCalibration,
    gutter_fallback: bool = False,
    empty_deck_reference: np.ndarray | None = None,
    ssim_strike_threshold: float = 0.15,
    ssim_change_threshold: float = 0.05,
) -> PinState:
    """Determine the pin state after a shot.

    Three cases:
    1. Gutter ball (gutter_fallback=True): all pins remain, no visual analysis needed.
    2. Normal shot: compare pre-shot vs post-settle pin zone appearance.
    3. Optionally compare against an empty deck reference for strike detection.
    """
    if gutter_fallback:
        return PinState.ALL_STANDING

    pre_crop = _extract_pin_zone_crop(cap, pre_shot_frame, lane.pin_zone)
    post_crop = _extract_pin_zone_crop(cap, post_settle_frame, lane.pin_zone)

    if pre_crop is None or post_crop is None:
        return PinState.UNKNOWN

    change_score = _compute_zone_difference(pre_crop, post_crop)

    if change_score < ssim_change_threshold:
        return PinState.ALL_STANDING

    if empty_deck_reference is not None:
        post_vs_empty = _compute_zone_difference(post_crop, empty_deck_reference)
        if post_vs_empty < ssim_strike_threshold:
            return PinState.CLEARED
        return PinState.SOME_STANDING

    if change_score > ssim_strike_threshold:
        return PinState.CLEARED

    return PinState.SOME_STANDING


def capture_empty_deck_reference(
    cap: cv2.VideoCapture,
    frame_number: int,
    lane: LaneCalibration,
) -> np.ndarray | None:
    """Capture a pin zone crop to use as the empty deck reference."""

    return _extract_pin_zone_crop(cap, frame_number, lane.pin_zone)


def _extract_pin_zone_crop(
    cap: cv2.VideoCapture,
    frame_number: int,
    pin_polygon: Polygon,
) -> np.ndarray | None:
    """Extract and mask the pin zone region from a specific frame."""

    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    ret, frame = cap.read()
    if not ret:
        return None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mask = np.zeros_like(gray)
    pts = np.array(pin_polygon, dtype=np.int32)
    cv2.fillPoly(mask, [pts], 255)

    x, y, w, h = cv2.boundingRect(pts)
    if w == 0 or h == 0:
        return None

    cropped = gray[y:y + h, x:x + w]
    cropped_mask = mask[y:y + h, x:x + w]

    return cv2.bitwise_and(cropped, cropped_mask)


def _compute_zone_difference(
    zone_a: np.ndarray,
    zone_b: np.ndarray,
) -> float:
    """Compute normalized pixel difference between two pin zone crops.

    Returns a value in [0.0, 1.0] where 0 means identical and 1 means
    completely different. Resizes to match if shapes differ.
    """
    if zone_a.shape != zone_b.shape:
        target_shape = (
            min(zone_a.shape[1], zone_b.shape[1]),
            min(zone_a.shape[0], zone_b.shape[0]),
        )
        if target_shape[0] == 0 or target_shape[1] == 0:
            return 0.0
        zone_a = cv2.resize(zone_a, target_shape)
        zone_b = cv2.resize(zone_b, target_shape)

    diff = cv2.absdiff(zone_a, zone_b)

    nonzero_count = np.count_nonzero(zone_a) + np.count_nonzero(zone_b)
    if nonzero_count == 0:
        return 0.0

    return float(diff.sum()) / (nonzero_count * 255.0 / 2.0)
