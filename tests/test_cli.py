"""CLI integration tests for new subcommands."""
import re

from typer.testing import CliRunner

from turkey_club.cli import app

runner = CliRunner()

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub("", text)


def test_build_bowler_target_in_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "build-bowler-target" in result.stdout


def test_build_bowler_target_help() -> None:
    result = runner.invoke(app, ["build-bowler-target", "--help"])
    assert result.exit_code == 0
    output = _strip_ansi(result.stdout)
    assert "--name" in output
    assert "--reference" in output
    assert "--lane" in output
    assert "--calibration" in output
    assert "--samples-per-image" in output
    assert "--out" in output


def test_build_bowler_target_missing_reference(tmp_path) -> None:
    result = runner.invoke(app, [
        "build-bowler-target",
        "--name", "TestBowler",
        "--calibration", str(tmp_path / "nonexistent.json"),
        "--reference", str(tmp_path / "nonexistent.jpg"),
        "--lane", "left",
        "--out", str(tmp_path / "target.json"),
    ])
    assert 0 != result.exit_code


def test_diagnose_in_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "diagnose" in result.stdout


def test_diagnose_help() -> None:
    result = runner.invoke(app, ["diagnose", "--help"])
    assert result.exit_code == 0
    output = _strip_ansi(result.stdout)
    assert "--video" in output
    assert "--bowler-target" in output
    assert "--calibration" in output
    assert "--frames" in output


def test_extract_format_option_in_help() -> None:
    result = runner.invoke(app, ["extract", "--help"])
    output = _strip_ansi(result.stdout)
    assert "--format" in output
    assert "pba-qualifying" in output


def test_extract_invalid_format(tmp_path) -> None:
    result = runner.invoke(app, [
        "extract",
        "--video", str(tmp_path / "fake.mp4"),
        "--bowler-target", str(tmp_path / "target.json"),
        "--calibration", str(tmp_path / "venue.json"),
        "--out", str(tmp_path / "clips"),
        "--format", "nonexistent-format",
    ])
    assert 0 != result.exit_code


def test_extract_baker_requires_bowler_lane(tmp_path) -> None:
    import json
    cal = tmp_path / "venue.json"
    cal.write_text(json.dumps({
        "lanes": [{"name": "left", "approach_zone": [[0, 0], [1, 0], [1, 1]],
                    "lane_zone": [[0, 0], [1, 0], [1, 1]], "pin_zone": [[0, 0], [1, 0], [1, 1]]}],
        "frame_width": 100, "frame_height": 100,
    }))
    target = tmp_path / "target.json"
    target.write_text(json.dumps({"name": "Test", "shirt_color_samples": [[0, 0, 0]]}))

    result = runner.invoke(app, [
        "extract",
        "--video", str(tmp_path / "fake.mp4"),
        "--bowler-target", str(target),
        "--calibration", str(cal),
        "--out", str(tmp_path / "clips"),
        "--format", "baker",
    ])
    assert 0 != result.exit_code
    assert "bowler-lane" in _strip_ansi(result.stdout + (result.stderr or "")).lower()


def test_all_subcommands_in_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("calibrate", "extract", "preview", "fetch", "merge",
                    "build-bowler-target", "diagnose"):
        assert command in result.stdout, f"{command} missing from top-level help"
