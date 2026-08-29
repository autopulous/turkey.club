"""Tests for format preset validation and lane-policy enforcement."""
import pytest

from turkey_club.formats import PRESETS, FormatPreset, detect_format_from_prefix


def test_all_presets_have_required_fields() -> None:
    for name, preset in PRESETS.items():
        assert preset.name == name
        assert preset.lane_policy in ("cross-lane", "fixed-lane", "single-lane", "chaotic")
        assert isinstance(preset.probe_interval_seconds, float)


def test_baker_requires_bowler_lane() -> None:
    baker = PRESETS["baker"]
    assert baker.requires_bowler_lane is True
    with pytest.raises(ValueError, match="requires --bowler-lane"):
        baker.validate_bowler_lane(None)
    baker.validate_bowler_lane("left")


def test_cross_lane_does_not_require_bowler_lane() -> None:
    pba = PRESETS["pba-qualifying"]
    assert pba.requires_bowler_lane is False
    pba.validate_bowler_lane(None)


def test_shot_count_warning_low() -> None:
    preset = FormatPreset(
        name="test", lane_policy="cross-lane",
        requires_bowler_lane=False,
        expected_shots_min=10, expected_shots_max=20,
    )
    assert preset.check_shot_count(5) is not None
    assert "5 shot(s)" in preset.check_shot_count(5)


def test_shot_count_warning_high() -> None:
    preset = FormatPreset(
        name="test", lane_policy="cross-lane",
        requires_bowler_lane=False,
        expected_shots_min=10, expected_shots_max=20,
    )
    assert preset.check_shot_count(25) is not None
    assert "false positives" in preset.check_shot_count(25)


def test_shot_count_ok() -> None:
    preset = FormatPreset(
        name="test", lane_policy="cross-lane",
        requires_bowler_lane=False,
        expected_shots_min=10, expected_shots_max=20,
    )
    assert preset.check_shot_count(15) is None


def test_open_format_no_shot_count_bounds() -> None:
    open_bowling = PRESETS["open-bowling"]
    assert open_bowling.check_shot_count(0) is None
    assert open_bowling.check_shot_count(100) is None


def test_detect_format_no_activity() -> None:
    assert detect_format_from_prefix(set(), 2) is None


def test_detect_format_multi_lane_activity() -> None:
    result = detect_format_from_prefix({"left", "right"}, 2)
    assert result is not None
    assert result.lane_policy == "cross-lane"


def test_detect_format_single_lane_single_calibrated() -> None:
    result = detect_format_from_prefix({"left"}, 1)
    assert result is not None
    assert result.name == "singles-practice"
    assert result.lane_policy == "single-lane"


def test_detect_format_single_lane_multi_calibrated() -> None:
    result = detect_format_from_prefix({"left"}, 2)
    assert result is not None
    assert result.name == "baker"
    assert result.lane_policy == "fixed-lane"
