"""Cache a downscaled copy of a source video for use as the detection input."""
from __future__ import annotations

import shutil
from pathlib import Path

from turkey_club.export import _run_ffmpeg_streamed

VALID_DOWNSCALE_FACTORS: tuple[float, ...] = (1.0, 0.75, 0.5, 0.4, 0.33, 0.25)


def snap_downscale_factor(requested: float) -> float:
    """Snap ``requested`` down to the nearest equal-or-lower factor in ``VALID_DOWNSCALE_FACTORS``.

    Raises ValueError if ``requested`` is below the minimum supported value
    (pin-polygon frame-diff becomes unreliable below ~15x10 px).
    """
    minimum = min(VALID_DOWNSCALE_FACTORS)
    if requested < minimum:
        raise ValueError(
            f"downscale factor {requested} is below the minimum supported value {minimum}. "
            f"Pin-polygon detection becomes unreliable below this. "
            f"Choose from {sorted(VALID_DOWNSCALE_FACTORS, reverse=True)}."
        )
    eligible = [value for value in VALID_DOWNSCALE_FACTORS if value <= requested]
    return max(eligible)


def downscaled_cache_path(source: Path, scale_factor: float) -> Path:
    """Deterministic location of the downscaled cache for ``source``.

    Files live alongside the source as ``<stem>.detect_{scale}x.mp4``, so multiple
    bowler-extract runs against the same source share the cache transparently and
    different scale factors coexist.
    """
    scale_tag = f"{scale_factor:.2f}".rstrip("0").rstrip(".")
    return source.parent / f"{source.stem}.detect_{scale_tag}x.mp4"


def ensure_downscaled_video(source: Path, scale_factor: float = 0.5) -> Path:
    """Return a path to a downscaled copy of ``source``, creating it if absent.

    Audio is dropped (``-an``) — detection doesn't need it and it shrinks the file.
    Aspect ratio is preserved via ``scale=iw*S:ih*S``.
    """
    if scale_factor >= 1.0:
        return source
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not on PATH.")

    cache_path = downscaled_cache_path(source, scale_factor)
    if cache_path.exists():
        print(f"using cached detection video: {cache_path}", flush=True)
        return cache_path

    print(f"creating detection-resolution downscale ({scale_factor}x) at {cache_path}", flush=True)
    cmd = [
        "ffmpeg",
        "-loglevel", "error",
        "-stats",
        "-y",
        "-i", str(source),
        "-vf", f"scale=iw*{scale_factor}:ih*{scale_factor}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-an",
        str(cache_path),
    ]
    _run_ffmpeg_streamed(cmd, context=f"downscale -> {cache_path}")
    return cache_path
