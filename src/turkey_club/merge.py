"""Concatenate per-shot clips into a single merged video via ffmpeg."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from turkey_club.export import _run_ffmpeg_streamed


def merge_clips(
    clips_dir: Path,
    out_path: Path,
    pattern: str = "shot_*.mp4",
    reencode: bool = False,
) -> None:
    """Concatenate every clip in ``clips_dir`` matching ``pattern`` into ``out_path``.

    Clips are sorted lexicographically by filename (the ``shot_NN_<lane>.mp4`` naming
    from ``extract`` sorts chronologically because NN is zero-padded). Defaults to
    stream-copy (fast, no quality loss); pass ``reencode=True`` if clips have varying
    codec parameters and concat fails.
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not on PATH.")

    clips = sorted(clips_dir.glob(pattern))
    if not clips:
        raise RuntimeError(f"No clips matching {pattern!r} found in {clips_dir}.")

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
        list_path = Path(handle.name)
        for clip in clips:
            escaped = str(clip.resolve()).replace("\\", "/").replace("'", "\\'")
            handle.write(f"file '{escaped}'\n")

    try:
        cmd = ["ffmpeg", "-loglevel", "error", "-stats", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path)]
        if reencode:
            cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-b:a", "128k"]
        else:
            cmd += ["-c", "copy"]
        cmd += [str(out_path)]

        out_path.parent.mkdir(parents=True, exist_ok=True)
        _run_ffmpeg_streamed(cmd, context=f"concat -> {out_path}")
        print(f"merged {len(clips)} clip(s) -> {out_path}", flush=True)
    finally:
        list_path.unlink(missing_ok=True)
