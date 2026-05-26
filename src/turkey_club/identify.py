"""Bowler identification: OCR jersey name + shirt-color histogram, combined max-score."""
from __future__ import annotations

import difflib
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

import cv2
import numpy as np

from turkey_club.config import BowlerTarget, VenueCalibration
from turkey_club.detect import bbox_foot_in_polygon, detect_persons

if TYPE_CHECKING:
    from easyocr import Reader

PersonBBox = tuple[int, int, int, int]

UPPER_BACK_TOP_FRACTION = 0.18
UPPER_BACK_BOTTOM_FRACTION = 0.55

OCR_FUZZY_THRESHOLD = 0.55
HSV_HISTOGRAM_BINS = (16, 8, 8)
HSV_HISTOGRAM_RANGES = [0, 180, 0, 256, 0, 256]
COLOR_CONFIDENCE_CAP = 0.85


@lru_cache(maxsize=1)
def _load_ocr_reader() -> "Reader":
    import easyocr

    return easyocr.Reader(["en"], gpu=False, verbose=False)


def identify_bowler_in_frame(
    frame: np.ndarray,
    person_bbox: PersonBBox,
    target: BowlerTarget,
    use_ocr: bool = True,
) -> float:
    """Return a confidence in [0.0, 1.0] that the person in ``person_bbox`` is ``target``.

    Computes shirt-color-histogram match always; computes OCR-fuzzy-match when
    ``use_ocr`` is True. Returns the max of whichever signals were computed.
    Pipelines that need to score tens of thousands of frames typically pass
    ``use_ocr=False`` to skip the per-frame OCR (~600 ms) when the jersey font
    is known to defeat the recognizer.
    """
    crop = _crop_upper_back(frame, person_bbox)
    if crop.size == 0:
        return 0.0
    ocr_score = _ocr_match_confidence(crop, target.name) if use_ocr else 0.0
    color_score = (
        _color_histogram_confidence(crop, target.shirt_color_samples)
        if target.shirt_color_samples
        else 0.0
    )
    return max(ocr_score, color_score)


def _crop_upper_back(frame: np.ndarray, bbox: PersonBBox) -> np.ndarray:
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
def _samples_to_normalized_histogram(samples_key: tuple[tuple[int, int, int], ...]) -> np.ndarray:
    samples_bgr = np.array(samples_key, dtype=np.uint8).reshape(-1, 1, 3)
    samples_hsv = cv2.cvtColor(samples_bgr, cv2.COLOR_BGR2HSV).reshape(-1, 1, 3)
    hist = cv2.calcHist([samples_hsv], [0, 1, 2], None, list(HSV_HISTOGRAM_BINS), HSV_HISTOGRAM_RANGES)
    cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    return hist


def _color_histogram_confidence(crop: np.ndarray, samples: Sequence[tuple[int, int, int]]) -> float:
    """Bhattacharyya-similarity between ``crop``'s HSV histogram and the histogram built from ``samples``.

    Returns ``1 - distance`` capped at ``COLOR_CONFIDENCE_CAP``; 0 means uncorrelated, 1 means identical.
    """
    if crop.size == 0 or not samples:
        return 0.0
    reference_hist = _samples_to_normalized_histogram(tuple(samples))
    hsv_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    crop_hist = cv2.calcHist([hsv_crop], [0, 1, 2], None, list(HSV_HISTOGRAM_BINS), HSV_HISTOGRAM_RANGES)
    cv2.normalize(crop_hist, crop_hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    distance = cv2.compareHist(reference_hist, crop_hist, cv2.HISTCMP_BHATTACHARYYA)
    similarity = max(0.0, 1.0 - distance)
    return min(similarity, COLOR_CONFIDENCE_CAP)


def build_bowler_target_from_references(
    name: str,
    references: Sequence[tuple[Path, str]],
    venue: VenueCalibration,
    samples_per_image: int = 200,
    rng_seed: int = 0,
) -> BowlerTarget:
    """Build a BowlerTarget by sampling shirt colors from each ``(image_path, lane_name)`` pair.

    For each reference, the bowler is identified as the detected person whose foot lies
    in the named lane's approach zone. Up to ``samples_per_image`` random pixels are
    drawn from that person's upper-back crop and aggregated into the target's
    ``shirt_color_samples`` list.
    """
    rng = np.random.default_rng(rng_seed)
    samples: list[tuple[int, int, int]] = []
    for image_path, lane_name in references:
        img = cv2.imread(str(image_path))
        if img is None:
            raise FileNotFoundError(f"Could not read reference image: {image_path}")
        approach = venue.lane(lane_name).approach_zone
        persons = detect_persons(img, confidence_threshold=0.4, min_height_pixels=80)
        bowler = next((b for b in persons if bbox_foot_in_polygon(b, approach)), None)
        if bowler is None:
            raise RuntimeError(
                f"No person detected with foot in lane {lane_name!r} approach zone for {image_path}"
            )
        crop = _crop_upper_back(img, bowler)
        if crop.size == 0:
            continue
        flat = crop.reshape(-1, 3)
        take = min(samples_per_image, len(flat))
        idx = rng.choice(len(flat), size=take, replace=False)
        for b, g, r in flat[idx]:
            samples.append((int(b), int(g), int(r)))
    return BowlerTarget(name=name, shirt_color_samples=samples)
