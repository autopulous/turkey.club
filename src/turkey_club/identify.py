"""Bowler identification: OCR jersey name + shirt-color histogram, combined max-score."""
from __future__ import annotations

import difflib
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

import cv2
import numpy as np

from turkey_club.config import BowlerTarget, VenueCalibration
from turkey_club.detect import (
    KEYPOINT_LEFT_HIP,
    KEYPOINT_LEFT_SHOULDER,
    KEYPOINT_RIGHT_HIP,
    KEYPOINT_RIGHT_SHOULDER,
    Keypoints,
    bbox_foot_in_polygon,
    detect_persons,
)

if TYPE_CHECKING:
    from easyocr import Reader

UPPER_BACK_TOP_FRACTION = 0.18
UPPER_BACK_BOTTOM_FRACTION = 0.55

MIN_KEYPOINT_CONFIDENCE = 0.5
SHOULDER_HORIZONTAL_PAD_FRACTION = 0.15
TORSO_VERTICAL_PAD_FRACTION = 0.05

OCR_FUZZY_THRESHOLD = 0.55
HSV_HISTOGRAM_BINS = (16, 8, 8)
HSV_HISTOGRAM_RANGES = [0, 180, 0, 256, 0, 256]
COLOR_CONFIDENCE_CAP = 0.85

PREPROCESS_EXPOSURE_GAMMA = 0.5
PREPROCESS_SHADOW_LIFT = 0.5
PREPROCESS_BRIGHTNESS_OFFSET = 50.0
PREPROCESS_CONTRAST_FACTOR = 2.0
PREPROCESS_SHARPEN_SIGMA = 2.0
PREPROCESS_SHARPEN_WEIGHT = 2.0


def preprocess_for_histogram(image: np.ndarray) -> np.ndarray:
    """Normalize a crop before histogram computation.

    Saturation, warmth, tint at -100% (full desaturation — warmth and tint
    are subsumed); brightness, exposure, contrast, shadows at +100%;
    sharpness at +100% via unsharp mask.
    """
    if 0 == image.size:
        return image

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR).astype(np.float32)

    img = np.power(img / 255.0, PREPROCESS_EXPOSURE_GAMMA) * 255.0

    img = np.where(img < 128.0, img + PREPROCESS_SHADOW_LIFT * (128.0 - img), img)

    img = img + PREPROCESS_BRIGHTNESS_OFFSET

    img = 128.0 + PREPROCESS_CONTRAST_FACTOR * (img - 128.0)

    img = np.clip(img, 0, 255).astype(np.uint8)

    blurred = cv2.GaussianBlur(img, (0, 0), sigmaX=PREPROCESS_SHARPEN_SIGMA)
    img = cv2.addWeighted(img, PREPROCESS_SHARPEN_WEIGHT, blurred, 1.0 - PREPROCESS_SHARPEN_WEIGHT, 0)

    return img


@lru_cache(maxsize=1)
def _load_ocr_reader() -> "Reader":
    import easyocr

    return easyocr.Reader(["en"], gpu=False, verbose=False)


def identify_bowler_in_frame(
    frame: np.ndarray,
    person_bbox: tuple[int, int, int, int],
    target: BowlerTarget,
    use_ocr: bool = True,
    keypoints: Keypoints | None = None,
) -> float:
    """Return a confidence in [0.0, 1.0] that the person in ``person_bbox`` is ``target``.

    Computes histogram match (via ``reference_histogram`` when available, falling
    back to ``shirt_color_samples``); computes OCR-fuzzy-match when ``use_ocr``
    is True. Returns the max of whichever signals were computed.
    """
    crop = crop_back_from_keypoints(frame, person_bbox, keypoints)
    if 0 == crop.size:
        return 0.0
    ocr_score = _ocr_match_confidence(crop, target.name) if use_ocr else 0.0

    if target.reference_histogram:
        crop_hist = compute_crop_histogram(crop)
        ref_hist = np.array(target.reference_histogram, dtype=np.float32)
        expected = HSV_HISTOGRAM_BINS[0] * HSV_HISTOGRAM_BINS[1] * HSV_HISTOGRAM_BINS[2]
        if ref_hist.size == expected:
            ref_hist = ref_hist.reshape(HSV_HISTOGRAM_BINS)
            distance = histogram_distance(crop_hist, ref_hist)
            color_score = min(max(0.0, 1.0 - distance), COLOR_CONFIDENCE_CAP)
        else:
            color_score = 0.0
    elif target.shirt_color_samples:
        color_score = color_histogram_confidence(crop, target.shirt_color_samples)
    else:
        color_score = 0.0

    return max(ocr_score, color_score)


def crop_back_from_keypoints(
    frame: np.ndarray,
    bbox: tuple[int, int, int, int],
    keypoints: Keypoints | None = None,
    min_keypoint_confidence: float = MIN_KEYPOINT_CONFIDENCE,
) -> np.ndarray:
    """Crop the back region using shoulder/hip keypoints when available.

    When all four keypoints (left/right shoulder, left/right hip) exceed
    ``min_keypoint_confidence``, the crop is bounded by the shoulder span
    (horizontal) and the shoulder-to-hip span (vertical) with padding.
    Falls back to the fixed-fraction ``crop_upper_back`` heuristic when
    keypoints are absent or low confidence.
    """
    if keypoints is not None:
        left_shoulder = keypoints[KEYPOINT_LEFT_SHOULDER]
        right_shoulder = keypoints[KEYPOINT_RIGHT_SHOULDER]
        left_hip = keypoints[KEYPOINT_LEFT_HIP]
        right_hip = keypoints[KEYPOINT_RIGHT_HIP]

        shoulders_confident = (
            left_shoulder[2] >= min_keypoint_confidence
            and right_shoulder[2] >= min_keypoint_confidence
        )
        hips_confident = (
            left_hip[2] >= min_keypoint_confidence
            and right_hip[2] >= min_keypoint_confidence
        )

        if shoulders_confident and hips_confident:
            shoulder_left_x = min(left_shoulder[0], right_shoulder[0])
            shoulder_right_x = max(left_shoulder[0], right_shoulder[0])
            shoulder_top_y = min(left_shoulder[1], right_shoulder[1])
            hip_bottom_y = max(left_hip[1], right_hip[1])

            shoulder_width = shoulder_right_x - shoulder_left_x
            torso_height = hip_bottom_y - shoulder_top_y

            if shoulder_width > 1 and torso_height > 1:
                pad_x = shoulder_width * SHOULDER_HORIZONTAL_PAD_FRACTION
                pad_y = torso_height * TORSO_VERTICAL_PAD_FRACTION

                crop_x1 = int(shoulder_left_x - pad_x)
                crop_x2 = int(shoulder_right_x + pad_x)
                crop_y1 = int(shoulder_top_y - pad_y)
                crop_y2 = int(hip_bottom_y + pad_y)

                frame_h, frame_w = frame.shape[:2]
                crop_x1 = max(0, crop_x1)
                crop_y1 = max(0, crop_y1)
                crop_x2 = min(frame_w, crop_x2)
                crop_y2 = min(frame_h, crop_y2)

                if crop_x2 > crop_x1 and crop_y2 > crop_y1:
                    return frame[crop_y1:crop_y2, crop_x1:crop_x2]

    return crop_upper_back(frame, bbox)


def crop_upper_back(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Crop the upper-back region of ``bbox`` where the jersey name typically sits."""
    x1, y1, x2, y2 = bbox
    height = y2 - y1
    top = max(0, y1 + int(UPPER_BACK_TOP_FRACTION * height))
    bottom = min(frame.shape[0], y1 + int(UPPER_BACK_BOTTOM_FRACTION * height))
    x1 = max(0, x1)
    x2 = min(frame.shape[1], x2)
    if bottom <= top or x2 <= x1:
        return np.zeros((0, 0, 3), dtype=np.uint8)
    return frame[top:bottom, x1:x2]


def _ocr_preprocess_variants(crop: np.ndarray) -> list[np.ndarray]:
    """Generate preprocessing variants to bypass cursive/low-contrast OCR failures."""
    h, w = crop.shape[:2]
    upscaled = cv2.resize(crop, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
    inverted = cv2.bitwise_not(clahe)
    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, otsu_inv = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return [
        crop,
        upscaled,
        cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR),
        cv2.cvtColor(inverted, cv2.COLOR_GRAY2BGR),
        cv2.cvtColor(otsu, cv2.COLOR_GRAY2BGR),
        cv2.cvtColor(otsu_inv, cv2.COLOR_GRAY2BGR),
    ]


def _ocr_match_confidence(crop: np.ndarray, target_name: str) -> float:
    """Highest match score for ``target_name`` across OCR preprocessing variants.

    Strict substring match returns the OCR detection's confidence directly.
    Otherwise, sequence similarity above ``OCR_FUZZY_THRESHOLD`` returns the similarity
    score (typically a soft hit like ``Clemons`` vs ``@tenons``).
    """
    reader = _load_ocr_reader()
    needle = target_name.casefold()
    best = 0.0
    for variant in _ocr_preprocess_variants(crop):
        detections = reader.readtext(variant, detail=1, paragraph=False)
        for _box, text, ocr_confidence in detections:
            text_lower = text.casefold()
            if needle in text_lower:
                best = max(best, float(ocr_confidence))
                continue
            similarity = difflib.SequenceMatcher(None, needle, text_lower).ratio()
            if similarity >= OCR_FUZZY_THRESHOLD:
                best = max(best, similarity)
    return best


@lru_cache(maxsize=8)
def samples_to_normalized_histogram(samples_key: tuple[tuple[int, int, int], ...]) -> np.ndarray:
    n = len(samples_key)
    side = int(np.ceil(np.sqrt(n)))
    padded = np.zeros((side * side, 3), dtype=np.uint8)
    for i, bgr in enumerate(samples_key):
        padded[i] = bgr
    square = padded.reshape(side, side, 3)
    preprocessed = preprocess_for_histogram(square)
    flat = preprocessed.reshape(-1, 3)[:n]
    samples_hsv = cv2.cvtColor(flat.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 1, 3)
    hist = cv2.calcHist([samples_hsv], [0, 1, 2], None, list(HSV_HISTOGRAM_BINS), HSV_HISTOGRAM_RANGES)
    cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    return hist


def color_histogram_confidence(crop: np.ndarray, samples: Sequence[tuple[int, int, int]]) -> float:
    """Bhattacharyya-similarity between ``crop``'s HSV histogram and the histogram built from ``samples``.

    Returns ``1 - distance`` capped at ``COLOR_CONFIDENCE_CAP``; 0 means uncorrelated, 1 means identical.
    """
    if 0 == crop.size or not samples:
        return 0.0
    reference_hist = samples_to_normalized_histogram(tuple(samples))
    preprocessed = preprocess_for_histogram(crop)
    hsv_crop = cv2.cvtColor(preprocessed, cv2.COLOR_BGR2HSV)
    crop_hist = cv2.calcHist([hsv_crop], [0, 1, 2], None, list(HSV_HISTOGRAM_BINS), HSV_HISTOGRAM_RANGES)
    cv2.normalize(crop_hist, crop_hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    distance = cv2.compareHist(reference_hist, crop_hist, cv2.HISTCMP_BHATTACHARYYA)
    similarity = max(0.0, 1.0 - distance)
    return min(similarity, COLOR_CONFIDENCE_CAP)


def compute_crop_histogram(crop: np.ndarray) -> np.ndarray:
    """Compute the normalized HSV histogram for a BGR crop, matching the bins used by identification."""

    if 0 == crop.size:
        return np.zeros(HSV_HISTOGRAM_BINS, dtype=np.float32)
    preprocessed = preprocess_for_histogram(crop)
    hsv_crop = cv2.cvtColor(preprocessed, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv_crop], [0, 1, 2], None, list(HSV_HISTOGRAM_BINS), HSV_HISTOGRAM_RANGES)
    cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    return hist


def histogram_distance(hist_a: np.ndarray, hist_b: np.ndarray) -> float:
    """Bhattacharyya distance between two normalized HSV histograms. Lower = more similar."""

    return float(cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_BHATTACHARYYA))


def build_bowler_target_from_references(
    name: str,
    references: Sequence[tuple[Path, str]],
    venue: VenueCalibration,
    samples_per_image: int = 200,
    rng_seed: int = 0,
) -> BowlerTarget:
    """Build a BowlerTarget from reference images.

    For each ``(image_path, lane_name)`` pair the bowler is detected as the
    person whose foot lies in the named lane's approach zone.  The back crop
    goes through the same detect → crop → preprocess → histogram pipeline
    used by the census, so the stored ``reference_histogram`` is directly
    comparable to census histograms during clustering.
    """
    histograms: list[np.ndarray] = []
    for image_path, lane_name in references:
        img = cv2.imread(str(image_path))
        if img is None:
            raise FileNotFoundError(f"Could not read reference image: {image_path}")
        approach = venue.lane(lane_name).approach_zone
        detections = detect_persons(img, confidence_threshold=0.4, min_height_pixels=80)
        bowler = next(
            (d for d in detections if bbox_foot_in_polygon(d.bbox, approach)),
            None,
        )
        if bowler is None:
            raise RuntimeError(
                f"No person detected with foot in lane {lane_name!r} approach zone for {image_path}"
            )
        crop = crop_back_from_keypoints(img, bowler.bbox, bowler.keypoints)
        if 0 == crop.size:
            continue
        hist = compute_crop_histogram(crop)
        histograms.append(hist)

    reference_histogram: list[float] = []
    if histograms:
        avg = np.mean(histograms, axis=0).astype(np.float32)
        cv2.normalize(avg, avg, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        reference_histogram = avg.flatten().tolist()

    return BowlerTarget(name=name, reference_histogram=reference_histogram)
