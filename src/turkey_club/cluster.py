"""Stages 2-4: Bowler clustering, low-confidence recovery, and target identification."""
from __future__ import annotations

import numpy as np

from turkey_club.config import (
    BowlerCluster,
    BowlerTarget,
    CensusPersonRecord,
    CensusRecord,
    ClusterAppearance,
    SegmentationParameters,
)
from turkey_club.identify import histogram_distance, samples_to_normalized_histogram


def cluster_bowlers(
    records: list[CensusRecord],
    params: SegmentationParameters,
) -> tuple[list[BowlerCluster], list[CensusRecord]]:
    """Stage 2: High-confidence bowler clustering.

    Returns (clusters, uncertain_records). Uncertain records contain person detections
    that did not match any cluster within the tight threshold.
    """
    clusters: list[BowlerCluster] = []
    uncertain: list[CensusRecord] = []

    for record in records:
        uncertain_persons: list[CensusPersonRecord] = []

        for person in record.persons:
            person_hist = _to_hist_array(person.histogram)
            if person_hist is None:
                uncertain_persons.append(person)
                continue

            if not clusters:
                clusters.append(_create_cluster(len(clusters), record, person))
                continue

            best_cluster = None
            best_distance = float("inf")

            for cluster in clusters:
                centroid = _to_hist_array(cluster.centroid_histogram)
                if centroid is None:
                    continue
                dist = histogram_distance(person_hist, centroid)
                if dist < best_distance:
                    best_distance = dist
                    best_cluster = cluster

            if best_cluster is not None and best_distance < params.cluster_tight_threshold:
                same_frame_clusters = {
                    c.cluster_id
                    for c in clusters
                    for a in c.frame_appearances
                    if a.frame_number == record.frame_number
                }
                if best_cluster.cluster_id in same_frame_clusters:
                    new_cluster = _create_cluster(len(clusters), record, person)
                    clusters.append(new_cluster)
                    print(
                        f"    co-occurrence split: frame {record.frame_number} "
                        f"dist={best_distance:.3f} → new {new_cluster.cluster_id}",
                        flush=True,
                    )
                else:
                    _assign_to_cluster(best_cluster, record, person)
            else:
                uncertain_persons.append(person)

        if uncertain_persons:
            uncertain.append(CensusRecord(
                frame_number=record.frame_number,
                persons=uncertain_persons,
            ))

    return clusters, uncertain


def recover_uncertain(
    clusters: list[BowlerCluster],
    uncertain_records: list[CensusRecord],
    params: SegmentationParameters,
) -> list[BowlerCluster]:
    """Stage 3: Low-confidence recovery pass for uncertain person detections.

    Assigns uncertain persons to clusters when there is an unambiguous match
    (best distance < loose threshold AND margin to second-best is sufficient).
    Creates a new cluster for persons that don't match anything.
    """
    if not clusters and not uncertain_records:
        return clusters

    for record in uncertain_records:
        for person in record.persons:
            person_hist = _to_hist_array(person.histogram)
            if person_hist is None:
                continue

            if not clusters:
                clusters.append(_create_cluster(len(clusters), record, person))
                continue

            distances = []
            for cluster in clusters:
                centroid = _to_hist_array(cluster.centroid_histogram)
                if centroid is None:
                    continue
                dist = histogram_distance(person_hist, centroid)
                distances.append((dist, cluster))

            distances.sort(key=lambda x: x[0])
            if not distances:
                clusters.append(_create_cluster(len(clusters), record, person))
                continue

            best_dist, best_cluster = distances[0]

            if best_dist < params.cluster_loose_threshold:
                if len(distances) > 1:
                    margin = distances[1][0] - best_dist
                    if margin >= params.cluster_margin_ratio:
                        _assign_to_cluster(best_cluster, record, person)
                        continue

                if len(distances) == 1:
                    _assign_to_cluster(best_cluster, record, person)
                    continue

            clusters.append(_create_cluster(len(clusters), record, person))

    return clusters


def identify_target_cluster(
    clusters: list[BowlerCluster],
    target: BowlerTarget,
) -> tuple[BowlerCluster | None, float]:
    """Stage 4: Identify which cluster corresponds to the target bowler.

    Returns (best_cluster, confidence_margin). Confidence margin is the distance
    between the best and second-best match — larger means more confident.
    Returns (None, 0.0) if no clusters exist.
    """
    if not clusters or not target.shirt_color_samples:
        return None, 0.0

    reference_hist = samples_to_normalized_histogram(tuple(target.shirt_color_samples))
    distances: list[tuple[float, BowlerCluster]] = []

    for cluster in clusters:
        centroid = _to_hist_array(cluster.centroid_histogram)
        if centroid is None:
            continue
        dist = histogram_distance(reference_hist, centroid)
        distances.append((dist, cluster))

    if not distances:
        return None, 0.0

    distances.sort(key=lambda x: x[0])
    best_dist, best_cluster = distances[0]

    print(
        f"  target identification — top 5 clusters by distance to reference:",
        flush=True,
    )
    for dist, cluster in distances[:5]:
        print(
            f"    {cluster.cluster_id}: dist={dist:.3f} "
            f"({len(cluster.frame_appearances)} appearances)",
            flush=True,
        )

    margin = 0.0
    if len(distances) > 1:
        margin = distances[1][0] - best_dist

    return best_cluster, margin


def _hist_shape() -> tuple[int, int, int]:
    from turkey_club.identify import HSV_HISTOGRAM_BINS
    return HSV_HISTOGRAM_BINS


def _to_hist_array(histogram: list[float]) -> np.ndarray | None:
    """Convert a flat histogram list to a shaped numpy array for cv2.compareHist."""

    if not histogram:
        return None
    arr = np.array(histogram, dtype=np.float32)
    expected_size = 16 * 8 * 8
    if arr.size != expected_size:
        return arr.reshape(-1, 1) if arr.size > 0 else None
    return arr.reshape(_hist_shape())


def _create_cluster(
    index: int,
    record: CensusRecord,
    person: CensusPersonRecord,
) -> BowlerCluster:
    cluster_id = f"bowler_{index + 1:02d}"
    return BowlerCluster(
        cluster_id=cluster_id,
        centroid_histogram=list(person.histogram),
        frame_appearances=[ClusterAppearance(
            frame_number=record.frame_number,
            lane_name=person.lane_name,
            bbox=person.bbox,
        )],
    )


def _assign_to_cluster(
    cluster: BowlerCluster,
    record: CensusRecord,
    person: CensusPersonRecord,
) -> None:
    cluster.frame_appearances.append(ClusterAppearance(
        frame_number=record.frame_number,
        lane_name=person.lane_name,
        bbox=person.bbox,
    ))
    _update_centroid(cluster, person)


def _update_centroid(cluster: BowlerCluster, person: CensusPersonRecord) -> None:
    """Running average of the cluster centroid histogram."""

    n = len(cluster.frame_appearances)
    if n <= 1:
        cluster.centroid_histogram = list(person.histogram)
        return

    old = np.array(cluster.centroid_histogram, dtype=np.float32)
    new = np.array(person.histogram, dtype=np.float32)
    if old.shape != new.shape:
        return
    updated = old * ((n - 1) / n) + new * (1 / n)
    cluster.centroid_histogram = updated.tolist()
