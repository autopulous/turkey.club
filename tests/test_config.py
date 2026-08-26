"""Unit tests for config module: format presets, schema versioning."""
import json
from pathlib import Path

import pytest

from turkey_club.config import BowlerTarget, FORMAT_PRESETS, VenueCalibration

EXPECTED_PRESET_KEYS = {
    "pba-qualifying",
    "pba-match-play",
    "doubles",
    "scotch-doubles",
    "baker",
    "baker-half",
    "baker-double",
    "league",
    "singles-practice",
    "multi-bowler-practice",
    "open",
}


def test_format_presets_all_keys_present() -> None:
    assert set(FORMAT_PRESETS.keys()) == EXPECTED_PRESET_KEYS


def test_format_presets_fields() -> None:
    for name, preset in FORMAT_PRESETS.items():
        assert isinstance(preset.probe_interval_seconds, float), f"{name}: probe_interval_seconds"
        assert preset.lane_policy in ("cross-lane", "single-lane"), f"{name}: lane_policy"
        assert isinstance(preset.expected_shot_range, tuple), f"{name}: expected_shot_range type"
        assert len(preset.expected_shot_range) == 2, f"{name}: expected_shot_range length"
        low, high = preset.expected_shot_range
        assert isinstance(low, int) and isinstance(high, int), f"{name}: expected_shot_range ints"
        assert 0 < low <= high, f"{name}: expected_shot_range ordering"


def test_baker_variants_are_single_lane() -> None:
    for name in ("baker", "baker-half", "baker-double"):
        assert FORMAT_PRESETS[name].lane_policy == "single-lane", f"{name} should be single-lane"


# --- Schema versioning tests ---

SAMPLE_VENUE = {
    "lanes": [
        {
            "name": "left",
            "approach_zone": [[0, 0], [100, 0], [100, 100], [0, 100]],
            "lane_zone": [[0, 100], [100, 100], [100, 200], [0, 200]],
            "pin_zone": [[0, 200], [100, 200], [100, 250], [0, 250]],
        }
    ],
    "frame_width": 1280,
    "frame_height": 720,
}

SAMPLE_TARGET = {
    "name": "TestBowler",
    "shirt_color_samples": [[42, 38, 35], [51, 45, 41]],
}


def test_venue_save_includes_version(tmp_path: Path) -> None:
    path = tmp_path / "venue_in.json"
    path.write_text(json.dumps(SAMPLE_VENUE))
    venue = VenueCalibration.load(path)
    out = tmp_path / "venue_out.json"
    venue.save(out)
    data = json.loads(out.read_text())
    assert data["version"] == 1


def test_venue_load_without_version(tmp_path: Path) -> None:
    path = tmp_path / "venue.json"
    path.write_text(json.dumps(SAMPLE_VENUE))
    venue = VenueCalibration.load(path)
    assert len(venue.lanes) == 1


def test_venue_load_version_2_fails(tmp_path: Path) -> None:
    path = tmp_path / "venue.json"
    path.write_text(json.dumps({**SAMPLE_VENUE, "version": 2}))
    with pytest.raises(ValueError, match="version 2"):
        VenueCalibration.load(path)


def test_target_save_includes_version(tmp_path: Path) -> None:
    target = BowlerTarget(name="Test", shirt_color_samples=[(42, 38, 35)])
    out = tmp_path / "target.json"
    target.save(out)
    data = json.loads(out.read_text())
    assert data["version"] == 1


def test_target_load_without_version(tmp_path: Path) -> None:
    path = tmp_path / "target.json"
    path.write_text(json.dumps(SAMPLE_TARGET))
    target = BowlerTarget.load(path)
    assert target.name == "TestBowler"


def test_target_load_version_2_fails(tmp_path: Path) -> None:
    path = tmp_path / "target.json"
    path.write_text(json.dumps({**SAMPLE_TARGET, "version": 2}))
    with pytest.raises(ValueError, match="version 2"):
        BowlerTarget.load(path)


# --- Shot count warning logic tests ---

def test_shot_count_within_range() -> None:
    preset = FORMAT_PRESETS["pba-qualifying"]
    low, high = preset.expected_shot_range
    assert low <= 15 <= high


def test_shot_count_below_range() -> None:
    preset = FORMAT_PRESETS["pba-qualifying"]
    low, _ = preset.expected_shot_range
    assert 2 < low


def test_shot_count_above_range() -> None:
    preset = FORMAT_PRESETS["baker-double"]
    _, high = preset.expected_shot_range
    assert 10 > high
