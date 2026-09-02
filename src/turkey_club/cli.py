"""Typer CLI entry point for turkey-club."""
from __future__ import annotations

from pathlib import Path

import click
import cv2
import typer
import typer.core

_COMMAND_ORDER = [
    "fetch",
    "detect-format",
    "calibrate",
    "preview",
    "build-bowler",
    "extract",
    "merge",
    "debug-clustering",
    "help",
]


class NoBuiltinHelp(typer.core.TyperGroup):
    """Suppress Click's built-in --help flag so the ``help`` subcommand is the only entry point."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        registered = set(super().list_commands(ctx))
        ordered = [name for name in _COMMAND_ORDER if name in registered]
        ordered += sorted(registered - set(ordered))
        return ordered

    def get_params(self, ctx: click.Context) -> list[click.Parameter]:
        return [p for p in super().get_params(ctx)
                if not (isinstance(p, click.Option) and "--help" in (p.opts or []))]

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        cmd = super().get_command(ctx, cmd_name)
        if cmd is not None:
            cmd.add_help_option = False
        return cmd

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if "--help" in args or "-h" in args:
            remaining = [a for a in args if a not in ("--help", "-h")]
            args = ["help"] + remaining
        ctx.help_option_names = []
        return super().parse_args(ctx, args)

    def resolve_command(self, ctx: click.Context, args: list[str]) -> tuple:
        cmd_name, cmd, rest = super().resolve_command(ctx, args)
        if rest and ("--help" in rest or "-h" in rest):
            rest = [a for a in rest if a not in ("--help", "-h")]
            return "help", self.get_command(ctx, "help"), [cmd_name] + rest
        return cmd_name, cmd, rest

app = typer.Typer(
    cls=NoBuiltinHelp,
    no_args_is_help=False,
    help="Extract per-shot clips of a target bowler from a fixed-camera match video.",
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Extract per-shot clips of a target bowler from a fixed-camera match video."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(help_command, command="")


@app.command()
def calibrate(
    video: str | None = typer.Option(
        None,
        help="Local video path OR a remote URL (YouTube, direct MP4, any yt-dlp-supported source).",
    ),
    out: Path | None = typer.Option(None, help="Output path for the venue calibration JSON. Defaults to <video-dir>/<video-stem>/venue.json."),
    lane: list[str] = typer.Option(
        ["left", "right"],
        "--lane",
        help="Lane name to calibrate. Pass multiple times for multiple lanes (order = calibration order).",
    ),
    frame: str | None = typer.Option(
        None,
        "--frame",
        help="Starting frame number for the picker. Opens at the beginning of the video when omitted.",
    ),
    cache_dir: Path | None = typer.Option(None, help="Override download cache directory for remote sources."),
) -> None:
    """Interactively mark approach, lane, and pin zones for each lane on a still frame."""
    from turkey_club.calibrate import run_interactive_calibration
    from turkey_club.source import resolve_source

    initial_frame = 0
    if frame is not None:
        try:
            initial_frame = int(frame)
        except ValueError:
            if video is None:
                typer.echo(
                    f"--frame now accepts a frame number, not an image path.\n\n"
                    "Pass the video with --video and the picker will open for "
                    "frame selection:\n\n"
                    "  turkey-club calibrate --video <video> --out <venue.json>",
                    err=True,
                )
                raise typer.Exit(code=2)
            typer.echo(
                f"Invalid --frame value: {frame}\n\n"
                "--frame accepts a frame number (integer) to set the picker's "
                "starting position.",
                err=True,
            )
            raise typer.Exit(code=2)

    if video is None:
        typer.echo(
            "Missing required option: --video\n\n"
            "  turkey-club calibrate --video <video> --out <venue.json>",
            err=True,
        )
        raise typer.Exit(code=2)

    video_path = Path(resolve_source(video, cache_dir=cache_dir))
    typer.echo(f"Using video: {video_path}")

    if out is None:
        data_dir = video_path.parent / video_path.stem
        data_dir.mkdir(parents=True, exist_ok=True)
        out = data_dir / "venue.json"

    from turkey_club.pick_frame import pick_video_frame

    typer.echo("Opening frame picker — navigate to a frame where both lanes are visible.")
    selected_frame = pick_video_frame(video_path, initial_frame=initial_frame)
    if selected_frame is None:
        typer.echo("Frame selection canceled.", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Selected frame {selected_frame}")

    data_dir = video_path.parent / video_path.stem
    data_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, selected_frame)
    ret, img = cap.read()
    cap.release()
    if not ret:
        typer.echo(f"Could not read frame {selected_frame} from {video_path}", err=True)
        raise typer.Exit(code=2)

    frame_path = data_dir / "calibration_frame.jpg"
    cv2.imwrite(str(frame_path), img)
    typer.echo(f"Saved calibration frame: {frame_path}")

    frames = [frame_path] * len(lane)
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
        help="BowlerTarget JSON (built ahead of time with sampled shirt colors).",
    ),
    calibration: Path = typer.Option(..., help="Venue calibration JSON from `calibrate`."),
    out: Path = typer.Option(..., help="Output directory for per-shot clips."),
    format: str | None = typer.Option(
        None,
        "--format",
        help=(
            "Bowling format preset. Bundles census interval + lane policy + expected shot count. "
            "Presets: pba-qualifying, doubles, scotch-doubles, league, baker, singles-practice, open-bowling. "
            "Explicit --probe-interval and --bowler-lane still override the preset."
        ),
    ),
    strategy: str = typer.Option("multipass", "--strategy", help="Search strategy: 'multipass' (census, cluster, rotation, binary-search boundaries) or 'linear' (every-frame scan)."),
    bowler_lane: str | None = typer.Option(None, "--bowler-lane", help="Restrict search to a single calibrated lane (e.g. for Baker format). Default: search all calibrated lanes."),
    probe_interval_seconds: float | None = typer.Option(None, "--probe-interval", help="Census interval in seconds. Default: 10.0, or the format preset's value."),
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

    if not calibration.exists():
        typer.echo(
            f"Venue calibration not found: {calibration}\n\n"
            "The calibration file defines approach, lane, and pin zones for each lane. "
            "Create one with:\n\n"
            f"  turkey-club calibrate --frame <still-image> --out \"{calibration}\"",
            err=True,
        )
        raise typer.Exit(code=2)

    if not bowler_target.exists():
        video_dir = calibration.parent
        typer.echo(
            f"Bowler target not found: {bowler_target}\n\n"
            "The bowler target file identifies the bowler by shirt color histogram. "
            "Create one with:\n\n"
            f"  turkey-club build-bowler --video \"{video}\"",
            err=True,
        )
        raise typer.Exit(code=2)

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
        format_preset=preset,
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
    name: str | None = typer.Option(None, "--name", help="Bowler's name. Entered in the GUI when omitted."),
    video: str = typer.Option(
        ...,
        help="Local video path OR a remote URL (YouTube, direct MP4, any yt-dlp-supported source).",
    ),
    frame: int | None = typer.Option(
        None,
        "--frame",
        help="Frame number where the bowler is on the approach. Opens an interactive picker when omitted.",
    ),
    device: str = typer.Option("auto", "--device", help="Detection device: 'auto', 'cpu', or 'cuda'."),
    cache_dir: Path | None = typer.Option(None, help="Override download cache directory for remote sources."),
) -> None:
    """Build a BowlerTarget from a video frame where the bowler is on the approach.

    All files live in a subdirectory named after the video (e.g. ``game1.mp4``
    produces ``game1/venue.json``, ``game1/bowler.json``, ``game1/bowler.jpg``).
    The subdirectory is created automatically.  ``venue.json`` is located there
    first, falling back to the video's own directory for backward compatibility.
    """
    from turkey_club.config import VenueCalibration
    from turkey_club.identify import build_bowler_target_from_video_frame
    from turkey_club.source import resolve_source

    if frame is not None and name is None:
        typer.echo("--name is required when --frame is specified (no GUI to enter it).", err=True)
        raise typer.Exit(code=2)

    video_path = resolve_source(video, cache_dir=cache_dir)
    typer.echo(f"Using video: {video_path}")

    video_file = Path(video_path)
    data_dir = video_file.parent / video_file.stem
    data_dir.mkdir(parents=True, exist_ok=True)

    calibration = data_dir / "venue.json"
    if not calibration.exists():
        fallback = video_file.parent / "venue.json"
        if fallback.exists():
            calibration = fallback
        else:
            typer.echo(
                f"No venue.json found in {data_dir} or {video_file.parent}. "
                f"Run `calibrate` first.",
                err=True,
            )
            raise typer.Exit(code=2)

    venue = VenueCalibration.load(calibration)

    if frame is None:
        from turkey_club.pick_frame import pick_reference_frame

        typer.echo("Opening frame picker — navigate to a frame where the bowler is on the approach.")
        result = pick_reference_frame(video_path, venue, initial_name=name or "")
        if result is None:
            typer.echo("Frame selection canceled.", err=True)
            raise typer.Exit(code=1)
        frame, picker_name = result
        if name is None:
            name = picker_name
        typer.echo(f"Selected frame {frame}")

    if not name or not name.strip():
        typer.echo("Bowler name is required. Provide --name or enter it in the picker.", err=True)
        raise typer.Exit(code=2)
    name = name.strip()

    target = build_bowler_target_from_video_frame(
        name=name,
        video_path=video_path,
        frame_number=frame,
        venue=venue,
        output_dir=data_dir,
    )
    out = data_dir / "bowler.json"
    target.save(out)
    typer.echo(f"BowlerTarget saved to {out}")
    if target.source_image_paths:
        typer.echo(f"Reference image saved to {target.source_image_paths[0]}")


@app.command()
def merge(
    clips_dir: Path = typer.Option(..., "--clips-dir", exists=True, help="Directory containing the per-shot clip files."),
    out: Path = typer.Option(..., help="Output merged video path."),
    pattern: str = typer.Option("[0-9][0-9][0-9]_*.mp4", help="Glob pattern for clips to merge (sorted lexicographically)."),
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


@app.command("debug-clustering")
def debug_clustering(
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
    out: Path = typer.Option(..., help="Working directory for census cache and debug output."),
    format_preset: str = typer.Option(
        "",
        "--format",
        help="Bowling format preset name (e.g. 'pba-qualifying'). Optional, used for display context.",
    ),
    downscale_factor: float = typer.Option(0.5, "--downscale-factor", help="Detection-time downscale."),
    device: str = typer.Option("auto", "--device", help="Detection device: 'auto', 'cpu', or 'cuda'."),
    cache_dir: Path | None = typer.Option(None, help="Override download cache directory for remote sources."),
) -> None:
    """Replay Stages 1-4 with an interactive side-by-side visualization of each clustering comparison."""
    from turkey_club.census import load_census_records, run_census
    from turkey_club.config import BowlerTarget as BowlerTargetConfig
    from turkey_club.config import LaneCalibration, SegmentationParameters, VenueCalibration
    from turkey_club.debug_clustering import replay_clustering, run_debug_viewer
    from turkey_club.downscale import ensure_downscaled_video
    from turkey_club.source import resolve_source

    video_path = resolve_source(video, cache_dir=cache_dir)
    typer.echo(f"Using video: {video_path}")

    venue = VenueCalibration.load(calibration)
    target_obj = BowlerTargetConfig.load(bowler_target)
    params = SegmentationParameters()

    detect_video = ensure_downscaled_video(video_path, scale_factor=downscale_factor)
    scale = downscale_factor if detect_video != video_path else 1.0
    typer.echo(f"detection: {detect_video.name}")

    actual_device = device
    if device == "auto":
        try:
            import torch
            actual_device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            actual_device = "cpu"
    typer.echo(f"device={actual_device}")

    census_dir = out / "_census"
    if list(census_dir.glob("*.json")):
        typer.echo(f"Loading cached census from {census_dir}")
        records = load_census_records(census_dir)
    else:
        typer.echo("Running Stage 1: Sparse frame census ...")

        def _scale_poly(poly: list[tuple[int, int]]) -> list[tuple[int, int]]:
            return [(int(x * scale), int(y * scale)) for x, y in poly]

        scaled_venue = VenueCalibration(
            lanes=[
                LaneCalibration(
                    name=lane.name,
                    approach_zone=_scale_poly(lane.approach_zone),
                    lane_zone=_scale_poly(lane.lane_zone),
                    pin_zone=_scale_poly(lane.pin_zone),
                )
                for lane in venue.lanes
            ],
            frame_width=int(venue.frame_width * scale),
            frame_height=int(venue.frame_height * scale),
        )
        records = run_census(
            video_path=detect_video,
            venue=scaled_venue,
            output_dir=census_dir,
            interval_seconds=10.0,
            device=actual_device,
        )
    typer.echo(f"Census: {len(records)} frames with persons")

    if not records:
        typer.echo("No persons detected — nothing to visualize.")
        raise typer.Exit()

    typer.echo("Replaying clustering (Stages 2-3) ...")
    steps = replay_clustering(records, params, target_obj)
    typer.echo(f"Recorded {len(steps)} comparison steps. Opening viewer ...")

    run_debug_viewer(steps, census_dir, target_obj)


def _suppress_help_option(cmd: click.Command) -> None:
    """Prevent the --help option from appearing in rendered help."""
    cmd.add_help_option = False


@app.command("help")
def help_command(
    command: str = typer.Argument("", help="Command name, or 'all' to show every command's options."),
) -> None:
    """Show help for a command, or for all commands at once."""
    cli = typer.main.get_command(app)
    ctx = click.Context(cli, info_name="turkey-club")

    if not command:
        typer.echo(ctx.get_help())
        raise typer.Exit()

    if command == "all":
        typer.echo(ctx.get_help())
        typer.echo("")
        for name in cli.list_commands(ctx):
            if name == "help":
                continue
            cmd = cli.get_command(ctx, name)
            _suppress_help_option(cmd)
            typer.echo("=" * 72)
            typer.echo(f"  {name}")
            typer.echo("=" * 72)
            sub_ctx = click.Context(cmd, info_name=name, parent=ctx)
            typer.echo(sub_ctx.get_help())
            typer.echo("")
        raise typer.Exit()

    commands = ctx.command.commands
    if command not in commands:
        typer.echo(f"Unknown command: {command!r}. Available: {', '.join(sorted(commands))}", err=True)
        raise typer.Exit(code=2)

    cmd = commands[command]
    _suppress_help_option(cmd)
    sub_ctx = click.Context(cmd, info_name=command, parent=ctx)
    typer.echo(sub_ctx.get_help())


if __name__ == "__main__":
    app()
