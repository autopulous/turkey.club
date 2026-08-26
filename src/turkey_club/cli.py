"""Typer CLI entry point for turkey-club."""
from __future__ import annotations

from pathlib import Path

import typer

from turkey_club.config import FORMAT_PRESETS

app = typer.Typer(
    no_args_is_help=True,
    help="Extract per-shot clips of a target bowler from a fixed-camera match video.",
)


@app.command()
def calibrate(
    frame: list[Path] = typer.Option(
        ...,
        "--frame",
        exists=True,
        help=(
            "Still image. Pass once to broadcast to every lane, or once per --lane "
            "(paired with --lane by order, so you can use a different reference image per lane)."
        ),
    ),
    out: Path = typer.Option(..., help="Output path for the venue calibration JSON."),
    lane: list[str] = typer.Option(
        ["left", "right"],
        "--lane",
        help="Lane name to calibrate. Pass multiple times for multiple lanes (order = calibration order).",
    ),
) -> None:
    """Interactively mark approach, lane, and pin zones for each lane on a still frame."""
    from turkey_club.calibrate import run_interactive_calibration

    if len(frame) == 1:
        frames = list(frame) * len(lane)
    elif len(frame) == len(lane):
        frames = list(frame)
    else:
        typer.echo(
            f"Mismatch: got {len(frame)} --frame and {len(lane)} --lane. "
            "Pass either one --frame (broadcast to all lanes) or exactly one --frame per --lane.",
            err=True,
        )
        raise typer.Exit(code=2)

    run_interactive_calibration(frames, out, lane_names=lane)


_BAKER_FORMATS = {"baker", "baker-half", "baker-double"}

_FORMAT_HELP_NAMES = ", ".join(sorted(FORMAT_PRESETS.keys()))


@app.command()
def extract(
    video: str = typer.Option(
        ...,
        help="Local video path OR a remote URL (YouTube, direct MP4, any yt-dlp-supported source).",
    ),
    bowler_target: Path = typer.Option(
        ...,
        "--bowler-target",
        exists=True,
        help="BowlerTarget JSON (built ahead of time with sampled shirt colors).",
    ),
    calibration: Path = typer.Option(..., exists=True, help="Venue calibration JSON from `calibrate`."),
    out: Path = typer.Option(..., help="Output directory for per-shot clips."),
    format: str | None = typer.Option(
        None,
        "--format",
        help=(
            "Bowling format preset — bundles probe interval, lane policy, and expected shot count. "
            f"Available: {_FORMAT_HELP_NAMES}. "
            "Individual flags (--probe-interval, --bowler-lane) override preset values."
        ),
    ),
    strategy: str = typer.Option("probe", "--strategy", help="Search strategy: 'probe' (sparse probes + range-expand) or 'linear' (every-frame scan)."),
    bowler_lane: str | None = typer.Option(None, "--bowler-lane", help="Restrict search to a single calibrated lane (e.g. for Baker format). Default: search all calibrated lanes."),
    probe_interval_seconds: float | None = typer.Option(None, "--probe-interval", help="Probe interval in seconds (probe strategy only). Default: 10.0, or the preset value when --format is given."),
    merge: bool = typer.Option(True, "--merge/--no-merge", help="After exporting per-shot clips, concatenate them into <out>/all_shots.mp4. Use --no-merge to skip."),
    merge_out: Path | None = typer.Option(None, "--merge-out", help="Override merged-video output path. Default: <out>/all_shots.mp4."),
    downscale_factor: float = typer.Option(0.5, "--downscale-factor", help="Detection-time downscale. Must be one of 1.0, 0.75, 0.5, 0.4, 0.33, 0.25; other values snap down to the closest supported and prompt for confirmation."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-confirm any adjustment prompts (required for non-interactive runs)."),
    cache_dir: Path | None = typer.Option(None, help="Override download cache directory for remote sources."),
) -> None:
    """Detect and export every shot thrown by the named bowler."""
    from turkey_club.downscale import VALID_DOWNSCALE_FACTORS, snap_downscale_factor
    from turkey_club.pipeline import extract_shots
    from turkey_club.source import resolve_source

    preset = None
    if format is not None:
        if format not in FORMAT_PRESETS:
            typer.echo(
                f"Unknown format preset: {format!r}. Valid presets: {_FORMAT_HELP_NAMES}",
                err=True,
            )
            raise typer.Exit(code=2)
        preset = FORMAT_PRESETS[format]

    if preset is not None and preset.lane_policy == "single-lane" and format in _BAKER_FORMATS:
        if bowler_lane is None:
            typer.echo(
                f"Baker format ({format}) requires --bowler-lane <name> to specify which lane "
                f"this bowler is assigned to. Baker format's defining characteristic is "
                f"fixed-lane-per-bowler; searching both lanes would find shots from other "
                f"team members.",
                err=True,
            )
            raise typer.Exit(code=2)

    effective_probe_interval = probe_interval_seconds
    if effective_probe_interval is None:
        effective_probe_interval = preset.probe_interval_seconds if preset else 10.0

    if bowler_lane is None and preset is not None and preset.lane_policy == "single-lane":
        typer.echo(
            f"Note: format {format!r} uses single-lane policy. Consider using --bowler-lane "
            f"to restrict search to the relevant lane.",
            flush=True,
        )

    try:
        snapped_factor = snap_downscale_factor(downscale_factor)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2)
    if snapped_factor != downscale_factor:
        typer.echo(
            f"Note: --downscale-factor {downscale_factor} is not in the supported set "
            f"{sorted(VALID_DOWNSCALE_FACTORS, reverse=True)}. Adjusting to {snapped_factor}."
        )
        if not yes and not typer.confirm("Proceed with adjusted value?", default=True):
            raise typer.Abort()

    video_path = resolve_source(video, cache_dir=cache_dir)
    typer.echo(f"Using video: {video_path}")
    if preset:
        typer.echo(
            f"Format: {format} (probe_interval={effective_probe_interval}s, "
            f"lane_policy={preset.lane_policy}, "
            f"expected_shots={preset.expected_shot_range[0]}-{preset.expected_shot_range[1]})"
        )

    shot_count = extract_shots(
        video=video_path,
        bowler_target_path=bowler_target,
        calibration_path=calibration,
        out_dir=out,
        strategy=strategy,
        bowler_lane=bowler_lane,
        probe_interval_seconds=effective_probe_interval,
        merge=merge,
        merge_out=merge_out,
        downscale_factor=snapped_factor,
    )

    if preset is not None and shot_count is not None:
        low, high = preset.expected_shot_range
        if shot_count < low or shot_count > high:
            typer.echo(
                f"Warning: found {shot_count} shots but {format} expects {low}-{high}. "
                f"Possible missed shots or wrong format.",
            )


@app.command()
def preview(
    video: str = typer.Option(
        ...,
        help="Local video path OR a remote URL (YouTube, direct MP4, any yt-dlp-supported source).",
    ),
    calibration: Path = typer.Option(..., exists=True, help="Venue calibration JSON from `calibrate`."),
    out: Path = typer.Option(..., help="Output annotated video path."),
    cache_dir: Path | None = typer.Option(None, help="Override download cache directory for remote sources."),
) -> None:
    """Overlay calibrated zones on the video for visual verification."""
    from turkey_club.calibrate import render_zone_overlay
    from turkey_club.source import resolve_source

    video_path = resolve_source(video, cache_dir=cache_dir)
    typer.echo(f"Using video: {video_path}")

    render_zone_overlay(video_path, calibration, out)


@app.command()
def fetch(
    source: str = typer.Argument(..., help="URL to download via yt-dlp, or a local path to echo back."),
    cache_dir: Path | None = typer.Option(None, help="Override download cache directory."),
) -> None:
    """Resolve a source argument to a local file path (downloading via yt-dlp if needed). Prints the resulting path."""
    from turkey_club.source import resolve_source

    typer.echo(str(resolve_source(source, cache_dir=cache_dir)))


@app.command("build-bowler-target")
def build_bowler_target(
    name: str = typer.Option(..., "--name", help="Bowler's display name (used in identification)."),
    calibration: Path = typer.Option(
        ..., "--calibration", exists=True, help="Venue calibration JSON from `calibrate`."
    ),
    reference: list[Path] = typer.Option(
        ...,
        "--reference",
        exists=True,
        help=(
            "Reference still image showing the target bowler in the approach zone. "
            "Pass once to broadcast to every --lane, or once per --lane (paired by order)."
        ),
    ),
    lane: list[str] = typer.Option(
        ...,
        "--lane",
        help="Lane name in the calibration file where the bowler appears in the corresponding --reference image.",
    ),
    samples_per_image: int = typer.Option(
        2000, "--samples-per-image", help="Number of color samples to draw from each reference image."
    ),
    out: Path = typer.Option(..., "--out", help="Output path for the bowler target JSON."),
) -> None:
    """Build a BowlerTarget JSON from reference still images of the bowler in the approach zone."""
    from turkey_club.config import VenueCalibration
    from turkey_club.identify import build_bowler_target_from_references

    if len(reference) == 1:
        references = [(reference[0], lane_name) for lane_name in lane]
    elif len(reference) == len(lane):
        references = list(zip(reference, lane))
    else:
        typer.echo(
            f"Mismatch: got {len(reference)} --reference and {len(lane)} --lane. "
            "Pass either one --reference (broadcast to all lanes) or exactly one --reference per --lane.",
            err=True,
        )
        raise typer.Exit(code=2)

    venue = VenueCalibration.load(calibration)
    for _, lane_name in references:
        try:
            venue.lane(lane_name)
        except KeyError:
            typer.echo(
                f"Lane {lane_name!r} not found in calibration file {calibration}. "
                f"Known lanes: {[lane_cal.name for lane_cal in venue.lanes]}. "
                f"Lane names must match what was used during calibration.",
                err=True,
            )
            raise typer.Exit(code=2)

    target = build_bowler_target_from_references(
        name=name,
        references=references,
        venue=venue,
        samples_per_image=samples_per_image,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    target.save(out)
    typer.echo(
        f"Saved {target.name!r} target with {len(target.shirt_color_samples)} samples -> {out}"
    )


@app.command()
def diagnose(
    video: str = typer.Option(
        ...,
        help="Local video path OR a remote URL (YouTube, direct MP4, any yt-dlp-supported source).",
    ),
    bowler_target: Path = typer.Option(
        ..., "--bowler-target", exists=True, help="BowlerTarget JSON to test identification against."
    ),
    calibration: Path = typer.Option(
        ..., "--calibration", exists=True, help="Venue calibration JSON from `calibrate`."
    ),
    frames: int = typer.Option(
        10, "--frames", help="Number of evenly-spaced frames to sample across the video."
    ),
    start_time: float | None = typer.Option(
        None, "--start", help="Start of sample range in seconds (default: beginning of video)."
    ),
    end_time: float | None = typer.Option(
        None, "--end", help="End of sample range in seconds (default: end of video)."
    ),
    cache_dir: Path | None = typer.Option(None, help="Override download cache directory for remote sources."),
) -> None:
    """Sample frames and report per-person confidence scores by lane.

    Scores range from 0.0 (no match) to ~0.85 (strong match). A score >= 0.30
    is a MATCH -- the pipeline will treat that person as the target bowler.
    Scores between 0.25 and 0.35 are borderline; rebuild the bowler target with
    more or better reference images to improve separation.
    """
    import cv2

    from turkey_club.config import BowlerTarget as BT
    from turkey_club.config import VenueCalibration
    from turkey_club.detect import bbox_foot_in_polygon, detect_persons
    from turkey_club.identify import identify_bowler_in_frame
    from turkey_club.source import resolve_source

    video_path = resolve_source(video, cache_dir=cache_dir)
    venue = VenueCalibration.load(calibration)
    target = BT.load(bowler_target)

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        typer.echo(f"Could not open video: {video_path}", err=True)
        raise typer.Exit(code=2)

    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps

    range_start_frame = int((start_time or 0) * fps)
    range_end_frame = int((end_time or duration) * fps)
    range_end_frame = min(range_end_frame, total_frames)

    if range_start_frame >= range_end_frame:
        typer.echo("Invalid range: start >= end.", err=True)
        raise typer.Exit(code=2)

    step = max(1, (range_end_frame - range_start_frame) // frames)
    sample_frames = list(range(range_start_frame, range_end_frame, step))[:frames]

    typer.echo(
        f"Diagnosing {target.name!r} across {len(sample_frames)} sampled frames "
        f"from {video_path.name} ({duration:.1f}s, {total_frames} frames)"
    )
    typer.echo(f"Confidence threshold: {0.30:.2f}\n")

    detected_count = 0
    confidence_values: list[float] = []

    for sample_index, frame_number in enumerate(sample_frames, start=1):
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ok, frame = capture.read()
        if not ok:
            typer.echo(f"  Frame {frame_number}: could not read")
            continue

        timestamp = frame_number / fps
        persons = detect_persons(frame, confidence_threshold=0.4, min_height_pixels=80)

        typer.echo(f"  Frame {frame_number} ({timestamp:.1f}s) — {len(persons)} person(s) detected:")
        best_confidence = 0.0

        for lane in venue.lanes:
            lane_persons = [p for p in persons if bbox_foot_in_polygon(p, lane.approach_zone)]
            for person_index, person in enumerate(lane_persons):
                confidence = identify_bowler_in_frame(frame, person, target, use_ocr=False)
                marker = " <-- MATCH" if confidence >= 0.30 else ""
                typer.echo(
                    f"    lane={lane.name} person #{person_index + 1}: "
                    f"confidence={confidence:.3f}{marker}"
                )
                best_confidence = max(best_confidence, confidence)

        if best_confidence >= 0.30:
            detected_count += 1
        if 0 < best_confidence:
            confidence_values.append(best_confidence)

    capture.release()

    typer.echo("")
    if confidence_values:
        low = min(confidence_values)
        high = max(confidence_values)
        typer.echo(
            f"Summary: target bowler detected in {detected_count}/{len(sample_frames)} "
            f"sampled frames at confidence {low:.2f}-{high:.2f}"
        )
        if 0 < detected_count and low < 0.35:
            typer.echo(
                "  Note: some scores are near the 0.30 threshold. Consider rebuilding "
                "the bowler target with more or better reference images for this venue."
            )
    else:
        typer.echo(
            f"Summary: no persons detected in approach zones across {len(sample_frames)} sampled frames. "
            "Verify calibration zones with: turkey-club preview --video <video> --calibration <cal.json> --out overlay.mp4"
        )


@app.command()
def merge(
    clips_dir: Path = typer.Option(..., "--clips-dir", exists=True, help="Directory containing the per-shot clip files."),
    out: Path = typer.Option(..., help="Output merged video path."),
    pattern: str = typer.Option("shot_*.mp4", help="Glob pattern for clips to merge (sorted lexicographically)."),
    reencode: bool = typer.Option(False, "--reencode", help="Re-encode instead of stream-copy. Slower but tolerant of differing source encodings."),
) -> None:
    """Concatenate per-shot clips into a single merged highlight video."""
    from turkey_club.merge import merge_clips

    merge_clips(clips_dir, out, pattern=pattern, reencode=reencode)


if __name__ == "__main__":
    app()
