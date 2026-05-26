"""Configuration dataclasses for venue calibration, bowler identity, and tuning."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

Point = tuple[int, int]
Polygon = list[Point]


@dataclass
class LaneCalibration:
    """Per-lane zones — approach (where bowler sets up), lane (ball travel), pin (where pins fall)."""

    name: str
    approach_zone: Polygon
    lane_zone: Polygon
    pin_zone: Polygon


@dataclass
class VenueCalibration:
    """Fixed-camera calibration for one or more lanes visible in the same frame."""

    lanes: list[LaneCalibration]
    frame_width: int
    frame_height: int

    def lane(self, name: str) -> LaneCalibration:
        for lane in self.lanes:
            if lane.name == name:
                return lane
        raise KeyError(f"No lane named {name!r}. Known: {[lane.name for lane in self.lanes]}")

    @classmethod
    def load(cls, path: Path) -> "VenueCalibration":
        data = json.loads(Path(path).read_text())
        lanes = [LaneCalibration(**lane_data) for lane_data in data["lanes"]]
        return cls(
            lanes=lanes,
            frame_width=data["frame_width"],
            frame_height=data["frame_height"],
        )

    def save(self, path: Path) -> None:
        payload = {
            "lanes": [asdict(lane) for lane in self.lanes],
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
        }
        Path(path).write_text(json.dumps(payload, indent=2))


@dataclass
class BowlerTarget:
    """Identity of the bowler whose shots we want to extract."""

    name: str
    shirt_color_samples: list[tuple[int, int, int]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "BowlerTarget":
        data = json.loads(Path(path).read_text())
        data["shirt_color_samples"] = [tuple(s) for s in data.get("shirt_color_samples", [])]
        return cls(**data)

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2))


@dataclass
class SegmentationParameters:
    """Tunable thresholds for shot start/end detection."""

    bowler_confidence_threshold: float = 0.30
    stationary_pose_frames: int = 8
    pose_motion_threshold_pixels: float = 4.0
    forward_motion_lookback_seconds: float = 0.5
    pin_settle_frames: int = 12
    pin_motion_threshold: float = 1.5
    end_pad_seconds: float = 0.3
    max_setup_to_release_seconds: float = 10.0
    max_release_to_impact_seconds: float = 8.0
    max_impact_to_settle_seconds: float = 5.0
    gutter_fallback_seconds_after_onset: float = 4.0
