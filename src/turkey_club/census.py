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
from turkey_club.detect import bbox_foot_in_polygon, detect_persons
from turkey_club.identify import compute_crop_histogram, crop_upper_back


def run_census(
    video_path: str | Path,
    venue: VenueCalibration,
    output_dir: Path,
    interval_seconds: float = 10.0,
    person_confidence_threshold: float = 0.5,
    person_min_height_pixels: int = 80,
    model_name: str = "yolov8n.pt",
    device: str = "cpu",
) -> list[CensusRecord]:
    """Extract frames at ``interval_seconds`` and run person detection + identity feature extraction.

    Returns a list of CensusRecord for frames where at least one person was detected
    in an approach zone. Frame images and JSON sidecars are written to ``output_dir``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

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

        persons = detect_persons(
            frame,
            confidence_threshold=person_confidence_threshold,
            min_height_pixels=person_min_height_pixels,
            model_name=model_name,
            device=device,
        )

        census_persons: list[CensusPersonRecord] = []
        for bbox in persons:
            lane = _find_approach_lane(bbox, venue.lanes)
            if lane is None:
                continue

            crop = crop_upper_back(frame, bbox)
            if crop.size == 0:
                continue

            hist = compute_crop_histogram(crop)
            census_persons.append(CensusPersonRecord(
                bbox=bbox,
                lane_name=lane.name,
                histogram=hist.flatten().tolist(),
            ))

        if census_persons:
            record = CensusRecord(
                frame_number=frame_number,
                persons=census_persons,
            )
            records.append(record)

            frame_filename = f"{frame_number:06d}.jpg"
            sidecar_filename = f"{frame_number:06d}.json"
            cv2.imwrite(str(output_dir / frame_filename), frame)
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


def _find_approach_lane(
    bbox: tuple[int, int, int, int],
    lanes: list[LaneCalibration],
) -> LaneCalibration | None:
    """Return the lane whose approach zone contains the person's foot, or None."""

    for lane in lanes:
        if bbox_foot_in_polygon(bbox, lane.approach_zone):
            return lane
    return None
