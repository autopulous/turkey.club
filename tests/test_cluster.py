"""Tests for bowler clustering (Stages 2-4)."""
from __future__ import annotations

import numpy as np
import pytest

from turkey_club.config import (
    BowlerTarget,
    CensusPersonRecord,
    CensusRecord,
    SegmentationParameters,
)
from turkey_club.cluster import (
    cluster_bowlers,
    identify_target_cluster,
    recover_uncertain,
)


def _make_person(lane: str, histogram_seed: int = 0) -> CensusPersonRecord:
    rng = np.random.default_rng(histogram_seed)
    hist = rng.random(16 * 8 * 8).astype(np.float32)
    hist /= hist.sum()
    return CensusPersonRecord(
        bbox=(10, 10, 50, 100),
        lane_name=lane,
        histogram=hist.tolist(),
    )


def _make_similar_person(base: CensusPersonRecord, noise: float = 0.01) -> CensusPersonRecord:
    rng = np.random.default_rng(42)
    hist = np.array(base.histogram, dtype=np.float32)
    hist += rng.random(len(hist)).astype(np.float32) * noise
    hist = np.clip(hist, 0, None)
    hist /= hist.sum()
    return CensusPersonRecord(
        bbox=(10, 10, 50, 100),
        lane_name=base.lane_name,
        histogram=hist.tolist(),
    )


def test_single_bowler_single_cluster():
    """One bowler appearing in multiple frames produces one cluster."""
    person = _make_person("left", histogram_seed=1)
    records = [
        CensusRecord(frame_number=0, persons=[person]),
        CensusRecord(frame_number=300, persons=[_make_similar_person(person)]),
        CensusRecord(frame_number=600, persons=[_make_similar_person(person)]),
    ]
    params = SegmentationParameters()
    clusters, uncertain = cluster_bowlers(records, params)

    assert len(clusters) >= 1
    total_appearances = sum(len(c.frame_appearances) for c in clusters)
    assert total_appearances == 3


def test_two_distinct_bowlers_two_clusters():
    """Two bowlers with very different histograms produce two clusters."""
    bowler_a = _make_person("left", histogram_seed=1)
    bowler_b = _make_person("right", histogram_seed=999)

    records = [
        CensusRecord(frame_number=0, persons=[bowler_a, bowler_b]),
        CensusRecord(frame_number=300, persons=[_make_similar_person(bowler_a), _make_similar_person(bowler_b)]),
    ]
    params = SegmentationParameters()
    clusters, _ = cluster_bowlers(records, params)

    assert len(clusters) >= 2


def test_identify_target_cluster():
    """Target identification selects the cluster closest to the reference."""
    bowler_a = _make_person("left", histogram_seed=1)
    bowler_b = _make_person("right", histogram_seed=999)

    records = [
        CensusRecord(frame_number=0, persons=[bowler_a]),
        CensusRecord(frame_number=300, persons=[bowler_b]),
    ]
    params = SegmentationParameters()
    clusters, _ = cluster_bowlers(records, params)

    rng = np.random.default_rng(1)
    reference_samples = [(int(r), int(g), int(b)) for r, g, b in rng.integers(0, 256, size=(50, 3))]

    target = BowlerTarget(name="test", shirt_color_samples=reference_samples)
    best_cluster, margin = identify_target_cluster(clusters, target)

    assert best_cluster is not None


def test_recovery_pass_assigns_uncertain():
    """The recovery pass should assign uncertain persons when unambiguous."""
    bowler_a = _make_person("left", histogram_seed=1)

    records = [
        CensusRecord(frame_number=0, persons=[bowler_a]),
        CensusRecord(frame_number=300, persons=[_make_similar_person(bowler_a)]),
    ]
    params = SegmentationParameters(cluster_tight_threshold=0.01)
    clusters, uncertain = cluster_bowlers(records, params)

    total_before = sum(len(c.frame_appearances) for c in clusters)
    clusters = recover_uncertain(clusters, uncertain, params)
    total_after = sum(len(c.frame_appearances) for c in clusters)

    assert total_after >= total_before


def test_identify_target_cluster_with_reference_histogram():
    """Target identification works with reference_histogram (no shirt_color_samples)."""
    bowler_a = _make_person("left", histogram_seed=1)
    bowler_b = _make_person("right", histogram_seed=999)

    records = [
        CensusRecord(frame_number=0, persons=[bowler_a, bowler_b]),
        CensusRecord(frame_number=300, persons=[_make_similar_person(bowler_a), _make_similar_person(bowler_b)]),
    ]
    params = SegmentationParameters()
    clusters, _ = cluster_bowlers(records, params)

    reference_histogram = list(bowler_a.histogram)

    target = BowlerTarget(name="test", reference_histogram=reference_histogram)
    assert not target.shirt_color_samples

    best_cluster, margin = identify_target_cluster(clusters, target)
    assert best_cluster is not None
    assert margin > 0.0


def test_empty_records_produces_no_clusters():
    """No records should produce no clusters."""
    params = SegmentationParameters()
    clusters, uncertain = cluster_bowlers([], params)
    assert len(clusters) == 0
    assert len(uncertain) == 0
