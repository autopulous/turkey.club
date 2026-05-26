"""Smoke tests: CLI loads, modules import, resolve_source handles local files."""
from pathlib import Path

from typer.testing import CliRunner

from turkey_club.cli import app
from turkey_club.source import resolve_source


def test_cli_help_loads() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "calibrate" in result.stdout
    assert "extract" in result.stdout
    assert "preview" in result.stdout
    assert "fetch" in result.stdout
    assert "merge" in result.stdout


def test_module_imports() -> None:
    import turkey_club.calibrate  # noqa: F401
    import turkey_club.config  # noqa: F401
    import turkey_club.detect  # noqa: F401
    import turkey_club.downscale  # noqa: F401
    import turkey_club.export  # noqa: F401
    import turkey_club.identify  # noqa: F401
    import turkey_club.merge  # noqa: F401
    import turkey_club.pipeline  # noqa: F401
    import turkey_club.segment  # noqa: F401
    import turkey_club.source  # noqa: F401


def test_resolve_source_local_file(tmp_path: Path) -> None:
    local = tmp_path / "fake.mp4"
    local.write_bytes(b"\x00")
    assert resolve_source(str(local)) == local.resolve()
