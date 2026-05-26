"""Clip export via ffmpeg with frame-accurate seeking + live-streamed stderr."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from turkey_club.segment import ShotSegment


def _run_ffmpeg_streamed(cmd: list[str], context: str, tail_lines: int = 50) -> None:
    """Run an ffmpeg command, streaming stderr live to stdout one line at a time.

    Python's text-mode universal-newlines translation converts ``\\r`` (which
    ``-stats`` uses for in-place progress updates) into ``\\n`` during read, so
    each progress tick appears on its own line in the log rather than overwriting.
    Keeps the last ``tail_lines`` of stderr so the RuntimeError on failure
    can quote them without the caller having to scroll back.
    """
    process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, bufsize=1)
    recent: list[str] = []
    assert process.stderr is not None
    for line in process.stderr:
        print(line, end="", flush=True)
        recent.append(line)
        if len(recent) > tail_lines:
            recent.pop(0)
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(
            f"ffmpeg failed for {context} (exit {return_code}). Last stderr lines:\n"
            + "".join(recent)
        )


def export_clip(video: Path, segment: ShotSegment, fps: float, out_path: Path) -> None:
    """Cut ``video`` from ``segment.start_frame``..``segment.end_frame`` to ``out_path``.

    Uses ffmpeg with ``-ss`` placed AFTER ``-i`` plus re-encode — the only way to land
    on specific frame indices (input-side seeking only hits keyframes). Slower than
    keyframe-aligned seeking but frame-accurate.
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not on PATH. Install (e.g. `winget install Gyan.FFmpeg`) and re-open the shell.")

    start_seconds = segment.start_frame / fps
    duration_seconds = (segment.end_frame - segment.start_frame) / fps
    cmd = [
        "ffmpeg",
        "-loglevel", "error",
        "-stats",
        "-y",
        "-i", str(video),
        "-ss", f"{start_seconds:.3f}",
        "-t", f"{duration_seconds:.3f}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "128k",
        str(out_path),
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg_streamed(cmd, context=str(out_path))
