"""End-to-end orchestration: video -> per-bowler shot clips.

Two search strategies:
  - linear:    scan every frame from 0 to N. Simple, correct, ~6x real-time on CPU YOLO.
  - multipass: census → cluster → rotation → validate → binary-search boundaries →
               pin state → game tracking → export. Separates bowler discovery from
               shot detection for higher precision. Default.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from turkey_club.config import (
    BowlerTarget,
    GameState,
    LaneCalibration,
    SegmentationParameters,
    VenueCalibration,
)
from turkey_club.detect import PersonDetection, bbox_foot_in_polygon, detect_device, detect_persons, frame_has_motion, pin_zone_motion
from turkey_club.downscale import ensure_downscaled_video
from turkey_club.export import export_clip
from turkey_club.identify import identify_bowler_in_frame
from turkey_club.merge import merge_clips
from turkey_club.segment import LaneFrameSignals, ShotSegment, find_shot_boundaries

Strategy = Literal["linear", "multipass"]


@dataclass
class _LaneState:
    """Mutable per-lane accumulator used during signal collection."""

    name: str
    bowler_confidence: list[float]
    pose_motion: list[float]
    pin_motion: list[float]
    ball_reached_pins: list[bool]
    previous_bowler_centroid: tuple[float, float] | None = None


def scan_prefix(
    video: Path,
    bowler_target_path: Path,
    calibration_path: Path,
    prefix_seconds: float = 30.0,
    probe_interval_seconds: float = 2.0,
    person_confidence_threshold: float = 0.4,
    person_min_height_pixels: int = 80,
    downscale_factor: float = 0.5,
    device: str = "auto",
) -> dict:
    """Scan the first ``prefix_seconds`` of video and return lane activity for format detection."""
    venue = VenueCalibration.load(calibration_path)
    target = BowlerTarget.load(bowler_target_path)

    detection_video = ensure_downscaled_video(video, scale_factor=downscale_factor)
    scaled_lanes = [_scale_lane(lane, downscale_factor) for lane in venue.lanes]
    scaled_min_height = max(20, int(person_min_height_pixels * downscale_factor))
    resolved_device = detect_device(device)
    bowler_thresh = SegmentationParameters().bowler_confidence_threshold

    capture = cv2.VideoCapture(str(detection_video))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open detection video: {detection_video}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    prefix_frames = min(total_frames, int(prefix_seconds * fps))
    probe_interval = max(1, int(probe_interval_seconds * fps))

    active_lanes: set[str] = set()
    probes = 0

    try:
        frame_index = 0
        while frame_index < prefix_frames:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok:
                break
            probes += 1
            persons = detect_persons(
                frame,
                confidence_threshold=person_confidence_threshold,
                min_height_pixels=scaled_min_height,
                device=resolved_device,
            )
            for lane in scaled_lanes:
                if lane.name in active_lanes:
                    continue
                for detection in persons:
                    if not bbox_foot_in_polygon(detection.bbox, lane.approach_zone):
                        continue
                    confidence = identify_bowler_in_frame(
                        frame, detection.bbox, target,
                        use_ocr=False, keypoints=detection.keypoints,
                    )
                    if confidence >= bowler_thresh:
                        active_lanes.add(lane.name)
                        print(f"  prefix-scan probe #{probes} @ frame {frame_index}: bowler on {lane.name!r}", flush=True)
                        break
            frame_index += probe_interval
    finally:
        capture.release()

    print(
        f"  prefix-scan: {probes} probes over {prefix_seconds:.0f}s, "
        f"active lanes: {sorted(active_lanes) or 'none'}",
        flush=True,
    )
    return {
        "active_lanes": active_lanes,
        "total_calibrated": len(venue.lanes),
        "prefix_seconds": prefix_seconds,
        "probes": probes,
    }


def extract_shots(
    video: Path,
    bowler_target_path: Path,
    calibration_path: Path,
    out_dir: Path,
    strategy: Strategy = "multipass",
    bowler_lane: str | None = None,
    lane_policy: str | None = None,
    probe_interval_seconds: float = 10.0,
    person_confidence_threshold: float = 0.4,
    person_min_height_pixels: int = 80,
    merge: bool = True,
    merge_out: Path | None = None,
    downscale_factor: float = 0.5,
    frame_skip: int = 1,
    motion_gate: bool = False,
    motion_gate_threshold: float = 3.0,
    device: str = "auto",
    format_preset: "FormatPreset | None" = None,
) -> int:
    """Find and export every shot thrown by the named bowler. Returns the shot count.

    Detection runs against a pre-downscaled cache of ``video`` (auto-created if
    absent at ``<video.stem>.detect_<scale>x.mp4`` alongside the source). Clip
    cuts use the original ``video`` for full-resolution output. Pass
    ``downscale_factor=1.0`` to disable downscaling entirely.
    """
    venue = VenueCalibration.load(calibration_path)
    target = BowlerTarget.load(bowler_target_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    detection_video = ensure_downscaled_video(video, scale_factor=downscale_factor)
    scaled_lanes = [_scale_lane(lane, downscale_factor) for lane in venue.lanes]
    scaled_params = dataclasses.replace(
        SegmentationParameters(),
        pose_motion_threshold_pixels=SegmentationParameters().pose_motion_threshold_pixels * downscale_factor,
    )
    scaled_min_height = max(20, int(person_min_height_pixels * downscale_factor))

    resolved_device = detect_device(device)
    print(f"device={resolved_device} (requested={device})", flush=True)

    if bowler_lane is not None:
        candidate_lanes = [next(lane for lane in scaled_lanes if lane.name == bowler_lane)]
    elif lane_policy == "fixed-lane":
        raise ValueError("lane_policy='fixed-lane' requires bowler_lane to be set")
    elif lane_policy == "single-lane" and len(scaled_lanes) == 1:
        candidate_lanes = scaled_lanes
        print(f"single-lane policy: using only lane {scaled_lanes[0].name!r}", flush=True)
    else:
        candidate_lanes = scaled_lanes

    capture = cv2.VideoCapture(str(detection_video))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open detection video: {detection_video}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    print(
        f"detection: {detection_video.name} — {total_frames} frames @ {fps:.2f} fps "
        f"(scale={downscale_factor}, source={video.name})",
        flush=True,
    )
    print(
        f"target={target.name!r} samples={len(target.shirt_color_samples)}, "
        f"strategy={strategy}, lanes={[lane.name for lane in candidate_lanes]}, "
        f"scaled_min_height={scaled_min_height}px, scaled_pose_threshold={scaled_params.pose_motion_threshold_pixels:.2f}px, "
        f"frame_skip={frame_skip}, motion_gate={motion_gate}",
        flush=True,
    )

    census_dir = out_dir.parent / "census"
    diagnostics_dir = out_dir.parent / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    if target.source_image_paths:
        import shutil
        ref_path = Path(target.source_image_paths[0])
        if ref_path.exists():
            shutil.copy2(str(ref_path), str(diagnostics_dir / "reference.jpg"))

    try:
        if strategy == "linear":
            shots = _extract_shots_linear(
                capture, total_frames, fps, target, candidate_lanes, scaled_params,
                person_confidence_threshold, scaled_min_height, frame_skip,
                motion_gate, motion_gate_threshold, resolved_device,
            )
        elif strategy == "multipass":
            capture.release()
            shots = _extract_shots_multipass(
                video, venue, target, candidate_lanes, scaled_params,
                probe_interval_seconds, person_confidence_threshold,
                scaled_min_height, resolved_device, census_dir,
                format_preset=format_preset,
            )
            capture = cv2.VideoCapture(str(detection_video))
        else:
            raise ValueError(f"Unknown strategy: {strategy!r}")
    finally:
        capture.release()

    gutter_count = sum(1 for shot in shots if shot.gutter_fallback)
    print(f"found {len(shots)} shot(s) ({gutter_count} gutter-fallback)", flush=True)
    for index, shot in enumerate(shots, start=1):
        clip_path = out_dir / f"{index:03d}_{shot.start_frame:05d}-{shot.end_frame:05d}.mp4"
        export_clip(video, shot, fps, clip_path)
        gutter_tag = " [gutter]" if shot.gutter_fallback else ""
        print(
            f"  {clip_path.name}: lane={shot.lane_name}{gutter_tag} "
            f"({(shot.end_frame - shot.start_frame) / fps:.2f}s) "
            f"bowler_conf={shot.bowler_confidence:.3f}",
            flush=True,
        )

    if merge and len(shots) >= 2:
        merged_path = merge_out if merge_out is not None else out_dir / "all_shots.mp4"
        print(f"merging {len(shots)} clips -> {merged_path}", flush=True)
        merge_clips(out_dir, merged_path, pattern="[0-9][0-9][0-9]_*.mp4")
    elif merge and len(shots) < 2:
        print(f"skipping merge: only {len(shots)} clip(s) produced (need >= 2)", flush=True)

    return len(shots)


def _extract_shots_linear(
    capture: cv2.VideoCapture,
    total_frames: int,
    fps: float,
    target: BowlerTarget,
    candidate_lanes: list[LaneCalibration],
    params: SegmentationParameters,
    person_confidence_threshold: float,
    person_min_height_pixels: int,
    frame_skip: int = 1,
    motion_gate: bool = False,
    motion_gate_threshold: float = 3.0,
    device: str = "cpu",
) -> list[ShotSegment]:
    """Linear single-pass scan over the entire video"""
    states = [_LaneState(name=lane.name, bowler_confidence=[], pose_motion=[], pin_motion=[], ball_reached_pins=[]) for lane in candidate_lanes]
    previous_frame = None
    gated_count = 0
    progress_every = max(1, total_frames // 50)
    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)

    for frame_index in range(total_frames):
        ok, frame = capture.read()
        if not ok:
            break
        if frame_skip > 1 and frame_index % frame_skip != 0:
            continue
        if motion_gate and not frame_has_motion(frame, previous_frame, motion_gate_threshold):
            _append_zero_signals(states, candidate_lanes, frame, previous_frame)
            previous_frame = frame
            gated_count += 1
            continue
        persons = detect_persons(frame, confidence_threshold=person_confidence_threshold, min_height_pixels=person_min_height_pixels, device=device)
        _update_lane_signals(states, candidate_lanes, frame, previous_frame, persons, target)
        previous_frame = frame
        if frame_index and frame_index % progress_every == 0:
            print(f"  linear: {frame_index}/{total_frames} ({frame_index/total_frames*100:.1f}%)", flush=True)

    if motion_gate and gated_count:
        print(f"  motion-gate skipped YOLO on {gated_count} frames", flush=True)
    effective_fps = fps / frame_skip
    return find_shot_boundaries(_states_to_signals(states), effective_fps, params)


def _scan_window(
    capture: cv2.VideoCapture,
    start_frame: int,
    end_frame: int,
    fps: float,
    target: BowlerTarget,
    candidate_lanes: list[LaneCalibration],
    params: SegmentationParameters,
    person_confidence_threshold: float,
    person_min_height_pixels: int,
    frame_skip: int = 1,
    motion_gate: bool = False,
    motion_gate_threshold: float = 3.0,
    device: str = "cpu",
) -> list[ShotSegment]:
    """Process a contiguous frame range, returning shots with VIDEO-ABSOLUTE frame indices."""
    states = [_LaneState(name=lane.name, bowler_confidence=[], pose_motion=[], pin_motion=[], ball_reached_pins=[]) for lane in candidate_lanes]
    previous_frame = None
    capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    n = end_frame - start_frame

    for i in range(n):
        ok, frame = capture.read()
        if not ok:
            break
        if frame_skip > 1 and i % frame_skip != 0:
            continue
        if motion_gate and not frame_has_motion(frame, previous_frame, motion_gate_threshold):
            _append_zero_signals(states, candidate_lanes, frame, previous_frame)
            previous_frame = frame
            continue
        persons = detect_persons(frame, confidence_threshold=person_confidence_threshold, min_height_pixels=person_min_height_pixels, device=device)
        _update_lane_signals(states, candidate_lanes, frame, previous_frame, persons, target)
        previous_frame = frame

    effective_fps = fps / frame_skip
    window_shots = find_shot_boundaries(_states_to_signals(states), effective_fps, params)
    for shot in window_shots:
        shot.start_frame = start_frame + int(shot.start_frame * frame_skip)
        shot.end_frame = start_frame + int(shot.end_frame * frame_skip)
    return window_shots


def _update_lane_signals(
    states: list[_LaneState],
    lanes: list[LaneCalibration],
    frame: np.ndarray,
    previous_frame: np.ndarray | None,
    persons: list[PersonDetection],
    target: BowlerTarget,
) -> None:
    """Append one frame's worth of signals to each lane's accumulator."""
    for state, lane in zip(states, lanes):
        persons_in_zone = [p for p in persons if bbox_foot_in_polygon(p.bbox, lane.approach_zone)]
        best_confidence = 0.0
        best_centroid: tuple[float, float] | None = None
        for person in persons_in_zone:
            confidence = identify_bowler_in_frame(
                frame, person.bbox, target,
                use_ocr=False, keypoints=person.keypoints,
            )
            if confidence > best_confidence:
                best_confidence = confidence
                x1, y1, x2, y2 = person.bbox
                best_centroid = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
        state.bowler_confidence.append(best_confidence)

        prev_centroid = state.previous_bowler_centroid
        if best_centroid is not None and prev_centroid is not None:
            dx = best_centroid[0] - prev_centroid[0]
            dy = best_centroid[1] - prev_centroid[1]
            state.pose_motion.append((dx * dx + dy * dy) ** 0.5)
        else:
            state.pose_motion.append(0.0)
        state.previous_bowler_centroid = best_centroid

        if previous_frame is not None:
            state.pin_motion.append(pin_zone_motion(frame, previous_frame, lane.pin_zone))
        else:
            state.pin_motion.append(0.0)
        state.ball_reached_pins.append(False)


def _append_zero_signals(
    states: list[_LaneState],
    lanes: list[LaneCalibration],
    frame: np.ndarray,
    previous_frame: np.ndarray | None,
) -> None:
    """Append zero-bowler signals when the motion gate skips YOLO.

    Pin-zone motion is still computed (cheap) so the settle detector stays accurate.
    """
    for state, lane in zip(states, lanes):
        state.bowler_confidence.append(0.0)
        state.pose_motion.append(0.0)
        if previous_frame is not None:
            state.pin_motion.append(pin_zone_motion(frame, previous_frame, lane.pin_zone))
        else:
            state.pin_motion.append(0.0)
        state.ball_reached_pins.append(False)


def _scale_lane(lane: LaneCalibration, scale: float) -> LaneCalibration:
    """Return a LaneCalibration with polygons scaled by ``scale`` (1.0 = no change).

    Calibration zones are authored in source-pixel coordinates; this projects them
    into detection-resolution coordinates so polygon membership tests work on the
    downscaled detection frames.
    """
    def scale_poly(poly: list[tuple[int, int]]) -> list[tuple[int, int]]:
        return [(int(x * scale), int(y * scale)) for x, y in poly]

    return LaneCalibration(
        name=lane.name,
        approach_zone=scale_poly(lane.approach_zone),
        lane_zone=scale_poly(lane.lane_zone),
        pin_zone=scale_poly(lane.pin_zone),
    )


def _states_to_signals(states: list[_LaneState]) -> list[LaneFrameSignals]:
    return [
        LaneFrameSignals(
            lane_name=state.name,
            bowler_confidence_per_frame=state.bowler_confidence,
            pose_motion_per_frame=state.pose_motion,
            pin_motion_per_frame=state.pin_motion,
            ball_reached_pins_per_frame=state.ball_reached_pins,
        )
        for state in states
    ]


def _extract_shots_multipass(
    video: Path,
    venue: VenueCalibration,
    target: BowlerTarget,
    candidate_lanes: list[LaneCalibration],
    params: SegmentationParameters,
    probe_interval_seconds: float,
    person_confidence_threshold: float,
    person_min_height_pixels: int,
    device: str,
    census_dir: Path,
    format_preset: "FormatPreset | None" = None,
) -> list[ShotSegment]:
    """Multi-pass extraction: census → cluster → rotation → boundary → pinstate → game state."""
    from turkey_club.boundary import BoundaryResult, find_shot_boundaries_binary
    from turkey_club.census import run_census
    from turkey_club.cluster import cluster_bowlers, identify_target_cluster, recover_uncertain
    from turkey_club.formats import FormatPreset
    from turkey_club.pinstate import analyze_pin_state
    from turkey_club.rotation import build_rotation_model, get_target_appearances
    from turkey_club.validate import (
        advance_game_state,
        compute_cadence,
        detect_gaps,
        filter_cadence_violations,
        validate_game_completeness,
        validate_shot_continuity,
    )

    print("=== Stage 1: Sparse frame census ===", flush=True)
    records = run_census(
        video_path=video,
        venue=venue,
        output_dir=census_dir,
        interval_seconds=probe_interval_seconds,
        person_confidence_threshold=person_confidence_threshold,
        person_min_height_pixels=person_min_height_pixels,
        device=device,
    )
    print(f"  census: {len(records)} frames with persons in approach zones", flush=True)

    if not records:
        print("  no persons detected in any approach zone — aborting", flush=True)
        return []

    print("=== Stage 2: High-confidence bowler clustering ===", flush=True)
    clusters, uncertain = cluster_bowlers(records, params)
    print(
        f"  clusters: {len(clusters)} bowler(s), "
        f"{len(uncertain)} uncertain frame(s)",
        flush=True,
    )
    for cluster in clusters:
        print(
            f"    {cluster.cluster_id}: {len(cluster.frame_appearances)} appearance(s)",
            flush=True,
        )

    print("=== Stage 3: Low-confidence recovery ===", flush=True)
    clusters = recover_uncertain(clusters, uncertain, params)
    for cluster in clusters:
        print(
            f"    {cluster.cluster_id}: {len(cluster.frame_appearances)} appearance(s) (post-recovery)",
            flush=True,
        )

    print("=== Stage 4: Target bowler identification ===", flush=True)
    target_cluster, margin = identify_target_cluster(clusters, target)
    if target_cluster is None:
        print("  could not identify target bowler in any cluster — aborting", flush=True)
        return []
    print(
        f"  target cluster: {target_cluster.cluster_id} "
        f"({len(target_cluster.frame_appearances)} appearances, margin={margin:.3f})",
        flush=True,
    )

    expected_bowlers = None
    if format_preset and format_preset.expected_bowlers_on_pair:
        expected_bowlers = format_preset.expected_bowlers_on_pair

    print("=== Stage 5: Rotation model + temporal validation ===", flush=True)
    rotation = build_rotation_model(
        clusters, target_cluster.cluster_id, expected_bowlers,
    )
    if rotation.confident:
        print("  rotation model: confident", flush=True)
        for lane_name, order in rotation.rotation_order.items():
            pos = rotation.target_position.get(lane_name, "?")
            pred = rotation.predecessor.get(lane_name, "?")
            print(
                f"    {lane_name}: {' → '.join(order)} "
                f"(target at position {pos}, predecessor={pred})",
                flush=True,
            )
    else:
        print("  rotation model: tentative (falling back to cadence)", flush=True)

    appearances = get_target_appearances(rotation, target_cluster.cluster_id)
    print(f"  target appearances: {len(appearances)}", flush=True)

    shot_groups = validate_shot_continuity(
        appearances,
        fps=_get_video_fps(video),
        probe_interval_seconds=probe_interval_seconds,
    )
    print(f"  shot groups (continuity-validated): {len(shot_groups)}", flush=True)

    cadence = compute_cadence(appearances, _get_video_fps(video))
    if cadence is not None:
        print(f"  observed cadence: {cadence:.1f}s", flush=True)

    gaps = detect_gaps(
        appearances,
        _get_video_fps(video),
        rotation_model=rotation,
        target_cluster_id=target_cluster.cluster_id,
        cadence_seconds=cadence,
    )
    if gaps:
        print(f"  gaps detected: {len(gaps)}", flush=True)
        for start, end, reason in gaps:
            print(f"    frames {start}-{end}: {reason}", flush=True)

    if format_preset:
        pre_filter_count = len(shot_groups)
        shot_groups = filter_cadence_violations(shot_groups, _get_video_fps(video), format_preset)
        if len(shot_groups) < pre_filter_count:
            print(
                f"  cadence filter: {pre_filter_count} → {len(shot_groups)} shot groups",
                flush=True,
            )

    print("=== Stage 6: Precise shot boundary detection ===", flush=True)
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    boundary_results: list[tuple[BoundaryResult, str, float]] = []
    previous_end = 0

    for group_idx, group in enumerate(shot_groups):
        probe_frame = group[0][0]
        lane_name = group[0][1]

        lane = next(
            (l for l in candidate_lanes if l.name == lane_name),
            candidate_lanes[0],
        )

        print(
            f"  boundary search {group_idx + 1}/{len(shot_groups)}: "
            f"probe frame {probe_frame}, lane {lane_name}",
            flush=True,
        )
        result = find_shot_boundaries_binary(
            cap, fps, probe_frame, previous_end,
            lane, target, params,
            person_confidence_threshold, person_min_height_pixels, device,
        )

        if result is not None:
            confidence = target_cluster.frame_appearances[0].confidence if target_cluster.frame_appearances else 0.5
            boundary_results.append((result, lane_name, confidence))
            previous_end = result.end_frame
            gutter_tag = " [gutter]" if result.gutter_fallback else ""
            print(
                f"    → frames {result.start_frame}-{result.end_frame}{gutter_tag}",
                flush=True,
            )
        else:
            print(f"    → boundary search failed", flush=True)

    print("=== Stage 7: Pin state analysis ===", flush=True)
    game_state = GameState()
    shot_segments: list[ShotSegment] = []

    for boundary, lane_name, confidence in boundary_results:
        lane = next(
            (l for l in candidate_lanes if l.name == lane_name),
            candidate_lanes[0],
        )

        pin_state = analyze_pin_state(
            cap,
            pre_shot_frame=boundary.pre_shot_frame or max(0, boundary.start_frame - int(fps)),
            post_settle_frame=boundary.settle_frame or boundary.end_frame,
            lane=lane,
            gutter_fallback=boundary.gutter_fallback,
        )
        print(
            f"  shot frames {boundary.start_frame}-{boundary.end_frame}: "
            f"pin_state={pin_state.value}",
            flush=True,
        )

        print("=== Stage 8: Game state tracking ===", flush=True)
        game_state = advance_game_state(
            game_state, pin_state, lane_name,
            boundary.start_frame, boundary.end_frame,
            gutter_fallback=boundary.gutter_fallback,
            bowler_confidence=confidence,
            format_preset=format_preset,
        )

        shot_segments.append(ShotSegment(
            lane_name=lane_name,
            start_frame=boundary.start_frame,
            end_frame=boundary.end_frame,
            bowler_confidence=confidence,
            gutter_fallback=boundary.gutter_fallback,
        ))

    cap.release()

    print("=== Game state summary ===", flush=True)
    print(
        f"  frame {game_state.current_frame}, shot {game_state.current_shot_in_frame}, "
        f"complete={game_state.complete}, total shots={len(game_state.shots)}",
        flush=True,
    )
    warnings = validate_game_completeness(game_state, format_preset)
    for warning in warnings:
        print(f"  WARNING: {warning}", flush=True)

    shot_segments.sort(key=lambda s: s.start_frame)
    return shot_segments


def _get_video_fps(video: Path) -> float:
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.release()
    return fps
