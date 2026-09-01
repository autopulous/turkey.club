"""Configuration dataclasses for venue calibration, bowler identity, and tuning."""
from __future__ import annotations

import enum
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

    cluster_tight_threshold: float = 0.60
    cluster_loose_threshold: float = 0.75
    cluster_margin_ratio: float = 0.05
    pin_impact_threshold: float = 1.0
    max_shot_duration_seconds: float = 20.0
    min_ball_travel_seconds: float = 3.0
    max_ball_travel_seconds: float = 12.0
    pinsetter_sweep_max_seconds: float = 8.0


class PinState(enum.Enum):
    UNKNOWN = "unknown"
    ALL_STANDING = "all_standing"
    SOME_STANDING = "some_standing"
    CLEARED = "cleared"


@dataclass
class CensusRecord:
    """Per-frame census data persisted as a JSON sidecar alongside extracted frames."""

    frame_number: int
    persons: list[CensusPersonRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "frame_number": self.frame_number,
            "persons": [p.to_dict() for p in self.persons],
        }

    @classmethod
    def from_dict(cls, data: dict) -> CensusRecord:
        return cls(
            frame_number=data["frame_number"],
            persons=[CensusPersonRecord.from_dict(p) for p in data.get("persons", [])],
        )

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> CensusRecord:
        return cls.from_dict(json.loads(Path(path).read_text()))


@dataclass
class CensusPersonRecord:
    """One detected person within a census frame."""

    bbox: tuple[int, int, int, int]
    lane_name: str
    histogram: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "bbox": list(self.bbox),
            "lane_name": self.lane_name,
            "histogram": self.histogram,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CensusPersonRecord:
        return cls(
            bbox=tuple(data["bbox"]),
            lane_name=data["lane_name"],
            histogram=data.get("histogram", []),
        )


@dataclass
class BowlerCluster:
    """A cluster of person detections believed to be the same bowler."""

    cluster_id: str
    centroid_histogram: list[float] = field(default_factory=list)
    frame_appearances: list[ClusterAppearance] = field(default_factory=list)


@dataclass
class ClusterAppearance:
    """One appearance of a clustered bowler in a census frame."""

    frame_number: int
    lane_name: str
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    confidence: float = 0.0


@dataclass
class RotationModel:
    """Per-lane bowler rotation extracted from cluster assignments."""

    lane_sequences: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    rotation_order: dict[str, list[str]] = field(default_factory=dict)
    target_position: dict[str, int] = field(default_factory=dict)
    predecessor: dict[str, str] = field(default_factory=dict)
    confident: bool = False


@dataclass
class ShotEvent:
    """A validated shot event consumed by the game state tracker."""

    bowling_frame: int
    shot_in_frame: int
    lane_name: str
    start_frame: int
    end_frame: int
    pin_state: PinState = PinState.UNKNOWN
    gutter_fallback: bool = False
    bowler_confidence: float = 0.0


@dataclass
class GameState:
    """Tracks the bowling game state as shots are consumed."""

    current_frame: int = 1
    current_shot_in_frame: int = 1
    expected_lane: str = ""
    shots: list[ShotEvent] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    complete: bool = False

    @property
    def max_shots_in_frame(self) -> int:
        if self.current_frame < 10:
            return 2
        return 3
