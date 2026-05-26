"""Shot start/end frame detection from per-lane per-frame signal streams."""
from __future__ import annotations

from dataclasses import dataclass

from turkey_club.config import SegmentationParameters


@dataclass
class LaneFrameSignals:
    """Per-frame signals for a single lane across the whole video."""

    lane_name: str
    bowler_confidence_per_frame: list[float]
    pose_motion_per_frame: list[float]
    pin_motion_per_frame: list[float]
    ball_reached_pins_per_frame: list[bool]


@dataclass
class ShotSegment:
    lane_name: str
    start_frame: int
    end_frame: int
    bowler_confidence: float
    gutter_fallback: bool = False


def find_shot_boundaries(
    lane_signals: list[LaneFrameSignals],
    fps: float,
    params: SegmentationParameters,
) -> list[ShotSegment]:
    """Combine per-lane signal streams into a chronologically ordered list of ShotSegment.

    Per lane the state machine is:
      SEARCHING → SETUP (bowler_confidence >= threshold & pose_motion <= threshold
        for >= stationary_pose_frames consecutive frames)
      SETUP → forward-motion onset (first frame where pose_motion exceeds threshold);
        ``start_frame = onset - forward_motion_lookback_seconds * fps``
      onset → pin impact (ball_reached_pins true OR pin_motion exceeds threshold)
      impact → settle (pin_motion below threshold for pin_settle_frames consecutive frames)
        ``end_frame = settle + end_pad_seconds * fps``

    Stalls beyond the configured ``max_*_seconds`` budgets cause that candidate to be
    abandoned and search resumes from the next frame.
    """
    shots: list[ShotSegment] = []
    for signals in lane_signals:
        shots.extend(_find_shots_one_lane(signals, fps, params))
    shots.sort(key=lambda shot: shot.start_frame)
    return shots


def _find_shots_one_lane(
    signals: LaneFrameSignals,
    fps: float,
    params: SegmentationParameters,
) -> list[ShotSegment]:
    bowler = signals.bowler_confidence_per_frame
    pose = signals.pose_motion_per_frame
    pin = signals.pin_motion_per_frame
    ball_at_pins = signals.ball_reached_pins_per_frame
    n = min(len(bowler), len(pose), len(pin), len(ball_at_pins))
    if n == 0:
        return []

    bowler_thresh = params.bowler_confidence_threshold
    pose_thresh = params.pose_motion_threshold_pixels
    pin_thresh = params.pin_motion_threshold
    stationary_n = params.stationary_pose_frames
    pin_settle_n = params.pin_settle_frames
    lookback_frames = int(fps * params.forward_motion_lookback_seconds)
    end_pad_frames = int(fps * params.end_pad_seconds)
    max_release_search = int(fps * params.max_setup_to_release_seconds)
    max_impact_search = int(fps * params.max_release_to_impact_seconds)
    max_settle_search = int(fps * params.max_impact_to_settle_seconds)

    setup_eligible = [
        bowler[i] >= bowler_thresh and pose[i] <= pose_thresh
        for i in range(n)
    ]

    shots: list[ShotSegment] = []
    i = 0
    while i < n:
        if not setup_eligible[i]:
            i += 1
            continue
        j = i
        while j < n and setup_eligible[j]:
            j += 1
        window_length = j - i
        if window_length < stationary_n:
            i = j + 1
            continue
        setup_confidence = sum(bowler[i:j]) / window_length

        forward_onset = None
        for k in range(j, min(n, j + max_release_search)):
            if pose[k] > pose_thresh:
                forward_onset = k
                break
        if forward_onset is None:
            i = j + 1
            continue

        start_frame = max(0, forward_onset - lookback_frames)

        impact_frame = None
        for k in range(forward_onset, min(n, forward_onset + max_impact_search)):
            if ball_at_pins[k] or pin[k] > pin_thresh:
                impact_frame = k
                break

        gutter_fallback = False
        if impact_frame is None:
            # No pin motion detected — likely a gutter ball or other miss-the-pins shot.
            # Synthesize an impact at forward_onset + gutter_fallback_seconds_after_onset
            # so the clip still captures the bowler's release. The clip end-framing will be
            # slightly looser than a real impact-tracked shot.
            gutter_offset = int(fps * params.gutter_fallback_seconds_after_onset)
            candidate = forward_onset + gutter_offset
            if candidate >= n:
                i = forward_onset + 1
                continue
            impact_frame = candidate
            gutter_fallback = True

        settle_frame = _find_settle(pin, impact_frame, min(n, impact_frame + max_settle_search), pin_thresh, pin_settle_n)
        if settle_frame is None:
            settle_frame = min(impact_frame + max_settle_search, n - 1)

        end_frame = min(n - 1, settle_frame + end_pad_frames)

        shots.append(
            ShotSegment(
                lane_name=signals.lane_name,
                start_frame=start_frame,
                end_frame=end_frame,
                bowler_confidence=setup_confidence,
                gutter_fallback=gutter_fallback,
            )
        )
        i = end_frame + 1

    return shots


def _find_settle(pin_motion, start, stop, pin_threshold, required_consecutive):
    consecutive_low = 0
    for k in range(start, stop):
        if pin_motion[k] < pin_threshold:
            consecutive_low += 1
            if consecutive_low >= required_consecutive:
                return k
        else:
            consecutive_low = 0
    return None
