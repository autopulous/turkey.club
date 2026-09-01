"""Stage 5a-5c: Build per-lane bowler rotation, identify target position, predict shots."""
from __future__ import annotations

from collections import Counter

from turkey_club.config import BowlerCluster, RotationModel


def build_rotation_model(
    clusters: list[BowlerCluster],
    target_cluster_id: str,
    expected_bowlers_on_pair: int | None = None,
) -> RotationModel:
    """Build a RotationModel from cluster assignments.

    Constructs per-lane timelines, extracts the repeating rotation order,
    identifies the target bowler's position, and determines who precedes them.
    """
    model = RotationModel()

    model.lane_sequences = _build_lane_sequences(clusters)
    model.rotation_order = _extract_rotation_order(model.lane_sequences)
    model.target_position = _find_target_position(model.rotation_order, target_cluster_id)
    model.predecessor = _find_predecessor(model.rotation_order, target_cluster_id)

    model.confident = _assess_confidence(
        model, target_cluster_id, expected_bowlers_on_pair,
    )

    return model


def predict_next_target_frame(
    model: RotationModel,
    target_cluster_id: str,
    lane_name: str,
) -> int | None:
    """Predict the frame number of the target's next shot on ``lane_name``.

    Uses the predecessor's most recent appearance on that lane to estimate
    when the target should appear next. Returns None if the predecessor
    has no appearances or the rotation is not confident.
    """
    predecessor_id = model.predecessor.get(lane_name)
    if predecessor_id is None:
        return None

    lane_seq = model.lane_sequences.get(lane_name, [])
    if not lane_seq:
        return None

    pred_appearances = [
        (frame, cid) for frame, cid in lane_seq if cid == predecessor_id
    ]
    if not pred_appearances:
        return None

    last_pred_frame = pred_appearances[-1][0]

    target_appearances = [
        (frame, cid) for frame, cid in lane_seq if cid == target_cluster_id
    ]
    pred_to_target_gaps = []
    for t_frame, _ in target_appearances:
        preceding = [
            (p_frame, _) for p_frame, _ in pred_appearances if p_frame < t_frame
        ]
        if preceding:
            gap = t_frame - preceding[-1][0]
            pred_to_target_gaps.append(gap)

    if not pred_to_target_gaps:
        return None

    median_gap = sorted(pred_to_target_gaps)[len(pred_to_target_gaps) // 2]
    return last_pred_frame + median_gap


def get_target_appearances(
    model: RotationModel,
    target_cluster_id: str,
) -> list[tuple[int, str]]:
    """Return all (frame_number, lane_name) appearances of the target bowler, sorted by frame."""

    appearances = []
    for lane_name, seq in model.lane_sequences.items():
        for frame_number, cluster_id in seq:
            if cluster_id == target_cluster_id:
                appearances.append((frame_number, lane_name))
    appearances.sort(key=lambda x: x[0])
    return appearances


def _build_lane_sequences(
    clusters: list[BowlerCluster],
) -> dict[str, list[tuple[int, str]]]:
    """Build per-lane timeline: {lane_name: [(frame_number, cluster_id), ...]} sorted by frame."""

    sequences: dict[str, list[tuple[int, str]]] = {}
    for cluster in clusters:
        for appearance in cluster.frame_appearances:
            lane = appearance.lane_name
            if lane not in sequences:
                sequences[lane] = []
            sequences[lane].append((appearance.frame_number, cluster.cluster_id))

    for lane in sequences:
        sequences[lane].sort(key=lambda x: x[0])

    return sequences


def _extract_rotation_order(
    lane_sequences: dict[str, list[tuple[int, str]]],
) -> dict[str, list[str]]:
    """Extract the repeating bowler cycle for each lane.

    Uses the most common sequence of consecutive unique bowler IDs to determine
    the rotation order. Handles noise by taking the majority vote across
    all observed cycles.
    """
    rotation_order: dict[str, list[str]] = {}

    for lane_name, seq in lane_sequences.items():
        unique_sequence = _deduplicate_consecutive(
            [cluster_id for _, cluster_id in seq]
        )

        if len(unique_sequence) < 2:
            rotation_order[lane_name] = unique_sequence
            continue

        unique_bowlers = list(dict.fromkeys(unique_sequence))
        cycle_length = len(unique_bowlers)

        if cycle_length < 2:
            rotation_order[lane_name] = unique_bowlers
            continue

        successor_votes: dict[str, Counter] = {bid: Counter() for bid in unique_bowlers}
        for i in range(len(unique_sequence) - 1):
            current = unique_sequence[i]
            next_bowler = unique_sequence[i + 1]
            successor_votes[current][next_bowler] += 1

        order = [unique_sequence[0]]
        visited = {unique_sequence[0]}
        current = unique_sequence[0]
        for _ in range(cycle_length - 1):
            candidates = successor_votes.get(current, Counter())
            unvisited = {k: v for k, v in candidates.items() if k not in visited}
            if not unvisited:
                break
            next_bowler = max(unvisited, key=lambda k: unvisited[k])
            order.append(next_bowler)
            visited.add(next_bowler)
            current = next_bowler

        rotation_order[lane_name] = order

    return rotation_order


def _find_target_position(
    rotation_order: dict[str, list[str]],
    target_cluster_id: str,
) -> dict[str, int]:
    """Find the target's position (0-indexed) in each lane's rotation cycle."""

    positions: dict[str, int] = {}
    for lane_name, order in rotation_order.items():
        if target_cluster_id in order:
            positions[lane_name] = order.index(target_cluster_id)
    return positions


def _find_predecessor(
    rotation_order: dict[str, list[str]],
    target_cluster_id: str,
) -> dict[str, str]:
    """Find who throws immediately before the target on each lane."""

    predecessors: dict[str, str] = {}
    for lane_name, order in rotation_order.items():
        if target_cluster_id in order:
            idx = order.index(target_cluster_id)
            pred_idx = (idx - 1) % len(order)
            predecessors[lane_name] = order[pred_idx]
    return predecessors


def _assess_confidence(
    model: RotationModel,
    target_cluster_id: str,
    expected_bowlers_on_pair: int | None,
) -> bool:
    """Assess whether the rotation model is confident enough to use for prediction."""

    if not model.target_position:
        return False

    for lane_name, order in model.rotation_order.items():
        if len(order) < 2:
            return False

        if target_cluster_id not in order:
            return False

    if expected_bowlers_on_pair is not None:
        for order in model.rotation_order.values():
            if abs(len(order) - expected_bowlers_on_pair) > 2:
                return False

    for lane_name, seq in model.lane_sequences.items():
        target_count = sum(1 for _, cid in seq if cid == target_cluster_id)
        if target_count < 3:
            return False

    return True


def _deduplicate_consecutive(seq: list[str]) -> list[str]:
    """Remove consecutive duplicates: [A, A, B, B, A] -> [A, B, A]."""

    if not seq:
        return []
    result = [seq[0]]
    for item in seq[1:]:
        if item != result[-1]:
            result.append(item)
    return result
