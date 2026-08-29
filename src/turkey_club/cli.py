"""Typer CLI entry point for turkey-club."""
from __future__ import annotations

from pathlib import Path

import typer

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
            "Bowling format preset. Bundles probe interval + lane policy + expected shot count. "
            "Presets: pba-qualifying, doubles, scotch-doubles, league, baker, singles-practice, open-bowling. "
            "Explicit --probe-interval and --bowler-lane still override the preset."
        ),
    ),
    strategy: str = typer.Option("probe", "--strategy", help="Search strategy: 'probe' (sparse probes + range-expand) or 'linear' (every-frame scan)."),
    bowler_lane: str | None = typer.Option(None, "--bowler-lane", help="Restrict search to a single calibrated lane (e.g. for Baker format). Default: search all calibrated lanes."),
    probe_interval_seconds: float | None = typer.Option(None, "--probe-interval", help="Probe interval in seconds (probe strategy only). Default: 10.0, or the format preset's value."),
    merge: bool = typer.Option(True, "--merge/--no-merge", help="After exporting per-shot clips, concatenate them into <out>/all_shots.mp4. Use --no-merge to skip."),
    merge_out: Path | None = typer.Option(None, "--merge-out", help="Override merged-video output path. Default: <out>/all_shots.mp4."),
    downscale_factor: float = typer.Option(0.5, "--downscale-factor", help="Detection-time downscale. Must be one of 1.0, 0.75, 0.5, 0.4, 0.33, 0.25; other values snap down to the closest supported and prompt for confirmation."),
    frame_skip: int = typer.Option(1, "--frame-skip", help="Process every Nth frame during scan windows. Higher values reduce YOLO inference calls proportionally. 1 = every frame (default), 2 = every other, 3 = every third."),
    motion_gate: bool = typer.Option(False, "--motion-gate/--no-motion-gate", help="Skip YOLO inference on frames with no global motion (background subtraction gate). Reduces CPU in dead-time regions."),
    motion_gate_threshold: float = typer.Option(3.0, "--motion-gate-threshold", help="Mean pixel-difference threshold for the motion gate. Lower = more sensitive (fewer skips)."),
    device: str = typer.Option("auto", "--device", help="Detection device: 'auto' (use CUDA if available), 'cpu', or 'cuda'."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-confirm any adjustment prompts (required for non-interactive runs)."),
    cache_dir: Path | None = typer.Option(None, help="Override download cache directory for remote sources."),
) -> None:
    """Detect and export every shot thrown by the named bowler."""
    from turkey_club.downscale import VALID_DOWNSCALE_FACTORS, snap_downscale_factor
    from turkey_club.formats import PRESETS, FormatPreset
    from turkey_club.pipeline import extract_shots
    from turkey_club.source import resolve_source

    preset: FormatPreset | None = None
    if format is not None:
        if format not in PRESETS:
            typer.echo(
                f"Unknown format {format!r}. Available: {', '.join(sorted(PRESETS))}",
                err=True,
            )
            raise typer.Exit(code=2)
        preset = PRESETS[format]
        try:
            preset.validate_bowler_lane(bowler_lane)
        except ValueError as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(code=2)
        typer.echo(f"Format: {preset.name} (lane_policy={preset.lane_policy})")

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

    if format is None:
        from turkey_club.formats import detect_format_from_prefix
        from turkey_club.pipeline import scan_prefix

        typer.echo("No --format given; running prefix scan to auto-detect...")
        scan_result = scan_prefix(
            video_path, bowler_target, calibration,
            downscale_factor=snapped_factor, device=device,
        )
        preset = detect_format_from_prefix(scan_result["active_lanes"], scan_result["total_calibrated"])
        if preset is not None:
            typer.echo(f"Auto-detected format: {preset.name} (lane_policy={preset.lane_policy})")
        else:
            typer.echo("Auto-detect inconclusive; proceeding without format preset")

    effective_probe_interval = (
        probe_interval_seconds
        if probe_interval_seconds is not None
        else (preset.probe_interval_seconds if preset is not None else 10.0)
    )

    if frame_skip < 1:
        typer.echo("--frame-skip must be >= 1", err=True)
        raise typer.Exit(code=2)

    shot_count = extract_shots(
        video=video_path,
        bowler_target_path=bowler_target,
        calibration_path=calibration,
        out_dir=out,
        strategy=strategy,
        bowler_lane=bowler_lane,
        lane_policy=preset.lane_policy if preset is not None else None,
        probe_interval_seconds=effective_probe_interval,
        merge=merge,
        merge_out=merge_out,
        downscale_factor=snapped_factor,
        frame_skip=frame_skip,
        motion_gate=motion_gate,
        motion_gate_threshold=motion_gate_threshold,
        device=device,
    )

    if preset is not None and shot_count is not None:
        warning = preset.check_shot_count(shot_count)
        if warning:
            typer.echo(f"Warning: {warning}", err=True)


@app.command()
def preview(
    video: str = typer.Option(
        ...,
        help="Local video path OR a remote URL (YouTube, direct MP4, any yt-dlp-supported source).",
    ),
    calibration: Path = typer.Option(..., exists=True, help="Venue calibration JSON."),
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


@app.command("build-bowler")
def build_bowler(
    name: str = typer.Option(..., "--name", help="Bowler's jersey name (used for OCR matching during extraction)."),
    calibration: Path = typer.Option(..., exists=True, help="Venue calibration JSON from `calibrate`."),
    reference: list[str] = typer.Option(
        ...,
        "--reference",
        help="Reference image paired with a lane: <image_path>=<lane_name>. Pass once per reference.",
    ),
    out: Path = typer.Option(..., help="Output path for the BowlerTarget JSON."),
    samples_per_image: int = typer.Option(200, "--samples-per-image", help="Random shirt-color pixel samples to draw from each reference image."),
    seed: int = typer.Option(0, "--seed", help="RNG seed for reproducible color sampling."),
) -> None:
    """Build a BowlerTarget JSON by sampling shirt colors from reference images."""
    from turkey_club.config import VenueCalibration
    from turkey_club.identify import build_bowler_target_from_references

    refs: list[tuple[Path, str]] = []
    for entry in reference:
        if "=" not in entry:
            typer.echo(
                f"Invalid --reference {entry!r}: expected <image_path>=<lane_name>",
                err=True,
            )
            raise typer.Exit(code=2)
        img_str, lane_name = entry.rsplit("=", 1)
        img_path = Path(img_str)
        if not img_path.exists():
            typer.echo(f"Reference image not found: {img_path}", err=True)
            raise typer.Exit(code=2)
        refs.append((img_path, lane_name))

    venue = VenueCalibration.load(calibration)
    target = build_bowler_target_from_references(
        name=name,
        references=refs,
        venue=venue,
        samples_per_image=samples_per_image,
        rng_seed=seed,
    )
    target.save(out)
    typer.echo(f"BowlerTarget saved to {out} ({len(target.shirt_color_samples)} color samples)")


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


@app.command("detect-format")
def detect_format(
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
    prefix_seconds: float = typer.Option(30.0, "--prefix-seconds", help="How many seconds of video to scan."),
    downscale_factor: float = typer.Option(0.5, "--downscale-factor", help="Detection-time downscale."),
    device: str = typer.Option("auto", "--device", help="Detection device: 'auto', 'cpu', or 'cuda'."),
    cache_dir: Path | None = typer.Option(None, help="Override download cache directory for remote sources."),
) -> None:
    """Scan the first N seconds of video to detect the bowling format from lane activity."""
    from turkey_club.formats import detect_format_from_prefix
    from turkey_club.pipeline import scan_prefix
    from turkey_club.source import resolve_source

    video_path = resolve_source(video, cache_dir=cache_dir)
    typer.echo(f"Using video: {video_path}")

    scan_result = scan_prefix(
        video_path, bowler_target, calibration,
        prefix_seconds=prefix_seconds, downscale_factor=downscale_factor, device=device,
    )
    preset = detect_format_from_prefix(scan_result["active_lanes"], scan_result["total_calibrated"])

    typer.echo(f"Scanned {scan_result['prefix_seconds']:.0f}s ({scan_result['probes']} probes)")
    typer.echo(f"Active lanes: {sorted(scan_result['active_lanes']) or 'none'}")
    typer.echo(f"Calibrated lanes: {scan_result['total_calibrated']}")
    if preset is not None:
        typer.echo(f"Detected format: {preset.name} (lane_policy={preset.lane_policy})")
    else:
        typer.echo("Format: inconclusive (no bowler activity detected in prefix)")


if __name__ == "__main__":
    app()
