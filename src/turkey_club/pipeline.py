"""End-to-end orchestration: video -> per-bowler shot clips.

Two search strategies:
  - linear: scan every frame from 0 to N. Simple, correct, ~6x real-time on CPU YOLO.
  - probe:  sparse probing at < min-shot-duration interval, range-expand on hits.
            ~3-5x faster on PBA qualifying footage; preferred default.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from turkey_club.config import BowlerTarget, LaneCalibration, SegmentationParameters, VenueCalibration
from turkey_club.detect import bbox_foot_in_polygon, detect_device, detect_persons, frame_has_motion, pin_zone_motion
from turkey_club.downscale import ensure_downscaled_video
from turkey_club.export import export_clip
from turkey_club.identify import identify_bowler_in_frame
from turkey_club.merge import merge_clips
from turkey_club.segment import LaneFrameSignals, ShotSegment, find_shot_boundaries

Strategy = Literal["probe", "linear"]


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
                for person in persons:
                    if not bbox_foot_in_polygon(person, lane.approach_zone):
                        continue
                    confidence = identify_bowler_in_frame(frame, person, target, use_ocr=False)
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
    strategy: Strategy = "probe",
    bowler_lane: str | None = None,
    lane_policy: str | None = None,
    probe_interval_seconds: float = 10.0,
    shot_lookback_seconds: float = 2.0,
    shot_duration_seconds: float = 10.0,
    person_confidence_threshold: float = 0.4,
    person_min_height_pixels: int = 80,
    merge: bool = True,
    merge_out: Path | None = None,
    downscale_factor: float = 0.5,
    frame_skip: int = 1,
    motion_gate: bool = False,
    motion_gate_threshold: float = 3.0,
    device: str = "auto",
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

    try:
        if strategy == "linear":
            shots = _extract_shots_linear(
                capture, total_frames, fps, target, candidate_lanes, scaled_params,
                person_confidence_threshold, scaled_min_height, frame_skip,
                motion_gate, motion_gate_threshold, resolved_device,
            )
        elif strategy == "probe":
            shots = _extract_shots_probe(
                capture, total_frames, fps, target, candidate_lanes, scaled_params,
                probe_interval_seconds, shot_lookback_seconds, shot_duration_seconds,
                person_confidence_threshold, scaled_min_height, frame_skip,
                motion_gate, motion_gate_threshold, resolved_device,
            )
        else:
            raise ValueError(f"Unknown strategy: {strategy!r}")
    finally:
        capture.release()

    gutter_count = sum(1 for shot in shots if shot.gutter_fallback)
    print(f"found {len(shots)} shot(s) ({gutter_count} gutter-fallback)", flush=True)
    for index, shot in enumerate(shots, start=1):
        suffix = "_gutter" if shot.gutter_fallback else ""
        clip_path = out_dir / f"shot_{index:02d}_{shot.lane_name}{suffix}.mp4"
        export_clip(video, shot, fps, clip_path)
        gutter_tag = " [gutter]" if shot.gutter_fallback else ""
        print(
            f"  shot {index:02d}: lane={shot.lane_name}{gutter_tag} "
            f"frames {shot.start_frame}-{shot.end_frame} "
            f"({(shot.end_frame - shot.start_frame) / fps:.2f}s) "
            f"bowler_conf={shot.bowler_confidence:.3f} -> {clip_path.name}",
            flush=True,
        )

    if merge and len(shots) >= 2:
        merged_path = merge_out if merge_out is not None else out_dir / "all_shots.mp4"
        print(f"merging {len(shots)} clips -> {merged_path}", flush=True)
        merge_clips(out_dir, merged_path, pattern="shot_*.mp4")
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
    """Linear single-pass scan over the entire video — the oracle for validating ``probe``."""
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


def _extract_shots_probe(
    capture: cv2.VideoCapture,
    total_frames: int,
    fps: float,
    target: BowlerTarget,
    candidate_lanes: list[LaneCalibration],
    params: SegmentationParameters,
    probe_interval_seconds: float,
    shot_lookback_seconds: float,
    shot_duration_seconds: float,
    person_confidence_threshold: float,
    person_min_height_pixels: int,
    frame_skip: int = 1,
    motion_gate: bool = False,
    motion_gate_threshold: float = 3.0,
    device: str = "cpu",
) -> list[ShotSegment]:
    """Sparse probing at ``probe_interval_seconds``; each HIT becomes a fixed-duration clip."""
    probe_interval_frames = max(1, int(probe_interval_seconds * fps))
    lookback_frames = int(shot_lookback_seconds * fps)
    forward_frames = int(shot_duration_seconds * fps)
    bowler_thresh = params.bowler_confidence_threshold

    all_shots: list[ShotSegment] = []
    probe_frame = 0
    probe_count = 0
    hit_count = 0

    while probe_frame < total_frames:
        probe_count += 1
        capture.set(cv2.CAP_PROP_POS_FRAMES, probe_frame)
        ok, frame = capture.read()
        if not ok:
            break
        persons = detect_persons(frame, confidence_threshold=person_confidence_threshold, min_height_pixels=person_min_height_pixels, device=device)
        hit_lane_name: str | None = None
        hit_confidence: float = 0.0
        for lane in candidate_lanes:
            for person in persons:
                if not bbox_foot_in_polygon(person, lane.approach_zone):
                    continue
                confidence = identify_bowler_in_frame(frame, person, target, use_ocr=False)
                if confidence >= bowler_thresh:
                    hit_lane_name = lane.name
                    hit_confidence = confidence
                    break
            if hit_lane_name is not None:
                break

        if hit_lane_name is None:
            print(
                f"  probe #{probe_count} @ frame {probe_frame} of {total_frames} "
                f"({probe_frame/fps:.1f}s, {probe_frame/total_frames*100:.1f}%): no hit",
                flush=True,
            )
            probe_frame += probe_interval_frames
            continue

        start_frame = max(0, probe_frame - lookback_frames)
        end_frame = min(total_frames, probe_frame + forward_frames)
        duration = (end_frame - start_frame) / fps

        is_dup = any(
            existing.start_frame == start_frame and existing.lane_name == hit_lane_name
            for existing in all_shots
        )
        if not is_dup:
            hit_count += 1
            shot = ShotSegment(
                lane_name=hit_lane_name,
                start_frame=start_frame,
                end_frame=end_frame,
                bowler_confidence=hit_confidence,
                gutter_fallback=False,
            )
            all_shots.append(shot)
            print(
                f"  probe #{probe_count} @ frame {probe_frame} "
                f"({probe_frame/fps:.1f}s, {probe_frame/total_frames*100:.1f}%): "
                f"HIT #{hit_count} — lane={hit_lane_name} conf={hit_confidence:.3f} "
                f"-> shot [{start_frame}-{end_frame}] ({duration:.1f}s)",
                flush=True,
            )
        else:
            print(
                f"  probe #{probe_count} @ frame {probe_frame} "
                f"({probe_frame/fps:.1f}s, {probe_frame/total_frames*100:.1f}%): "
                f"HIT (dup, skipped) — lane={hit_lane_name}",
                flush=True,
            )

        probe_frame = max(end_frame + 1, probe_frame + probe_interval_frames)

    print(f"  probes: {probe_count}, hits: {hit_count}", flush=True)
    all_shots.sort(key=lambda shot: shot.start_frame)
    return all_shots


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
    persons: list[tuple[int, int, int, int]],
    target: BowlerTarget,
) -> None:
    """Append one frame's worth of signals to each lane's accumulator."""
    for state, lane in zip(states, lanes):
        persons_in_zone = [p for p in persons if bbox_foot_in_polygon(p, lane.approach_zone)]
        best_confidence = 0.0
        best_centroid: tuple[float, float] | None = None
        for person in persons_in_zone:
            confidence = identify_bowler_in_frame(frame, person, target, use_ocr=False)
            if confidence > best_confidence:
                best_confidence = confidence
                best_centroid = ((person[0] + person[2]) / 2.0, (person[1] + person[3]) / 2.0)
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
