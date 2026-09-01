"""Bowling format presets — per-format lane policies, expected shot counts, and validation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormatPreset:
    name: str
    lane_policy: str
    requires_bowler_lane: bool
    expected_shots_min: int | None
    expected_shots_max: int | None
    probe_interval_seconds: float = 10.0
    expected_cadence_seconds: float | None = None
    lane_alternation_pattern: str | None = None
    expected_bowlers_on_pair: int | None = None

    def validate_bowler_lane(self, bowler_lane: str | None) -> None:
        if self.requires_bowler_lane and bowler_lane is None:
            raise ValueError(
                f"Format {self.name!r} requires --bowler-lane (fixed-lane format)"
            )

    def check_shot_count(self, count: int) -> str | None:
        if self.expected_shots_min is None or self.expected_shots_max is None:
            return None
        if count < self.expected_shots_min:
            return (
                f"Found {count} shot(s), but {self.name} typically produces "
                f"{self.expected_shots_min}-{self.expected_shots_max} per bowler"
            )
        if count > self.expected_shots_max:
            return (
                f"Found {count} shot(s), but {self.name} typically produces "
                f"{self.expected_shots_min}-{self.expected_shots_max} per bowler — "
                f"possible false positives"
            )
        return None


def detect_format_from_prefix(
    active_lanes: set[str],
    total_calibrated: int,
) -> FormatPreset | None:
    """Infer a format preset from which lanes had bowler activity in a prefix scan.

    Returns None when the scan is inconclusive (no activity detected).
    """
    if not active_lanes:
        return None
    if len(active_lanes) > 1:
        return PRESETS["pba-qualifying"]
    if total_calibrated == 1:
        return PRESETS["singles-practice"]
    return PRESETS["baker"]


PRESETS: dict[str, FormatPreset] = {
    "pba-qualifying": FormatPreset(
        name="pba-qualifying",
        lane_policy="cross-lane",
        requires_bowler_lane=False,
        expected_shots_min=18,
        expected_shots_max=24,
        expected_cadence_seconds=240.0,
        lane_alternation_pattern="LR",
        expected_bowlers_on_pair=5,
    ),
    "doubles": FormatPreset(
        name="doubles",
        lane_policy="cross-lane",
        requires_bowler_lane=False,
        expected_shots_min=18,
        expected_shots_max=24,
        expected_cadence_seconds=120.0,
        lane_alternation_pattern="LR",
        expected_bowlers_on_pair=4,
    ),
    "scotch-doubles": FormatPreset(
        name="scotch-doubles",
        lane_policy="cross-lane",
        requires_bowler_lane=False,
        expected_shots_min=8,
        expected_shots_max=15,
        expected_cadence_seconds=120.0,
        lane_alternation_pattern="LR",
        expected_bowlers_on_pair=4,
    ),
    "league": FormatPreset(
        name="league",
        lane_policy="cross-lane",
        requires_bowler_lane=False,
        expected_shots_min=18,
        expected_shots_max=24,
        expected_cadence_seconds=180.0,
        lane_alternation_pattern="LR",
        expected_bowlers_on_pair=4,
    ),
    "baker": FormatPreset(
        name="baker",
        lane_policy="fixed-lane",
        requires_bowler_lane=True,
        expected_shots_min=2,
        expected_shots_max=12,
        expected_cadence_seconds=300.0,
        lane_alternation_pattern=None,
        expected_bowlers_on_pair=10,
    ),
    "singles-practice": FormatPreset(
        name="singles-practice",
        lane_policy="single-lane",
        requires_bowler_lane=False,
        expected_shots_min=None,
        expected_shots_max=None,
        expected_cadence_seconds=30.0,
        lane_alternation_pattern=None,
        expected_bowlers_on_pair=1,
    ),
    "open-bowling": FormatPreset(
        name="open-bowling",
        lane_policy="chaotic",
        requires_bowler_lane=False,
        expected_shots_min=None,
        expected_shots_max=None,
    ),
}
