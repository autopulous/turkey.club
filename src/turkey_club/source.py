"""Resolve a video source argument: local file path or remote URL via yt-dlp."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "turkey-club" / "videos"


def resolve_source(src: str, cache_dir: Path | None = None) -> Path:
    """Resolve ``src`` to a local file path.

    If ``src`` is an existing local file, return its resolved path unchanged.
    Otherwise treat ``src`` as a URL and download it via yt-dlp into
    ``cache_dir`` (default ``~/.cache/turkey-club/videos/``).
    Re-runs against the same URL skip re-download when the destination exists.
    """
    local = Path(src)
    if local.exists() and local.is_file():
        return local.resolve()

    cache = cache_dir or DEFAULT_CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)

    yt_dlp = shutil.which("yt-dlp")
    if yt_dlp is None:
        raise RuntimeError(
            "yt-dlp is not on PATH. It is needed to download videos from URLs.\n"
            "Install with: pip install yt-dlp\n"
            "If you already have the video locally, pass the local file path instead of a URL."
        )

    output_template = str(cache / "%(id)s.%(ext)s")
    completed = subprocess.run(
        [
            yt_dlp,
            "--no-overwrites",
            "--no-simulate",
            "--print", "after_move:filepath",
            "-o", output_template,
            src,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"yt-dlp failed for source {src!r} (exit {completed.returncode}):\n"
            f"{completed.stderr.strip()}"
        )

    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"yt-dlp produced no output filepath for source {src!r}.")

    resolved = Path(lines[-1])
    if not resolved.exists():
        raise RuntimeError(
            f"yt-dlp reported destination {resolved} but the file does not exist."
        )
    return resolved.resolve()
