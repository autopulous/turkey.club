"""Tests for bowler rotation model (Stage 5a-5c)."""
from __future__ import annotations

import pytest

from turkey_club.config import BowlerCluster, ClusterAppearance
from turkey_club.rotation import (
    build_rotation_model,
    get_target_appearances,
    predict_next_target_frame,
)


def _make_cluster(cluster_id: str, appearances: list[tuple[int, str]]) -> BowlerCluster:
    return BowlerCluster(
        cluster_id=cluster_id,
        centroid_histogram=[0.0] * 10,
        frame_appearances=[
            ClusterAppearance(frame_number=f, lane_name=l)
            for f, l in appearances
        ],
    )


def test_rotation_order_extracted():
    """A repeating A-B-C pattern on one lane should extract the rotation [A, B, C]."""
    clusters = [
        _make_cluster("A", [(0, "left"), (900, "left"), (1800, "left")]),
        _make_cluster("B", [(300, "left"), (1200, "left"), (2100, "left")]),
        _make_cluster("C", [(600, "left"), (1500, "left"), (2400, "left")]),
    ]

    model = build_rotation_model(clusters, "B")

    assert "left" in model.rotation_order
    order = model.rotation_order["left"]
    assert len(order) == 3
    assert "A" in order
    assert "B" in order
    assert "C" in order


def test_target_position_found():
    """The target should be found at the correct position in the rotation."""
    clusters = [
        _make_cluster("A", [(0, "left"), (900, "left")]),
        _make_cluster("B", [(300, "left"), (1200, "left")]),
        _make_cluster("C", [(600, "left"), (1500, "left")]),
    ]

    model = build_rotation_model(clusters, "B")

    assert "left" in model.target_position


def test_predecessor_found():
    """The predecessor of B in a cycle [A, B, C] should be A."""
    clusters = [
        _make_cluster("A", [(0, "left"), (900, "left"), (1800, "left")]),
        _make_cluster("B", [(300, "left"), (1200, "left"), (2100, "left")]),
        _make_cluster("C", [(600, "left"), (1500, "left"), (2400, "left")]),
    ]

    model = build_rotation_model(clusters, "B")

    assert "left" in model.predecessor
    assert model.predecessor["left"] == "A"


def test_get_target_appearances():
    """get_target_appearances should return only the target's frames, sorted."""
    clusters = [
        _make_cluster("A", [(0, "left"), (900, "right")]),
        _make_cluster("B", [(300, "left"), (1200, "right")]),
    ]

    model = build_rotation_model(clusters, "B")
    appearances = get_target_appearances(model, "B")

    assert len(appearances) == 2
    assert appearances[0] == (300, "left")
    assert appearances[1] == (1200, "right")


def test_confidence_requires_minimum_appearances():
    """Rotation should not be confident with fewer than 3 target appearances."""
    clusters = [
        _make_cluster("A", [(0, "left"), (900, "left")]),
        _make_cluster("B", [(300, "left")]),
    ]

    model = build_rotation_model(clusters, "B")
    assert model.confident is False


def test_confidence_with_sufficient_appearances():
    """Rotation should be confident with 3+ target appearances and consistent cycle."""
    clusters = [
        _make_cluster("A", [(0, "left"), (600, "left"), (1200, "left")]),
        _make_cluster("B", [(300, "left"), (900, "left"), (1500, "left")]),
    ]

    model = build_rotation_model(clusters, "B")
    assert model.confident is True


def test_empty_clusters_no_crash():
    """Empty cluster list should not crash."""
    model = build_rotation_model([], "X")
    assert model.confident is False
    assert model.lane_sequences == {}
