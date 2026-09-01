"""Tests for frame census (Stage 1)."""
from __future__ import annotations

import json

import pytest

from turkey_club.config import CensusPersonRecord, CensusRecord


def test_census_record_round_trip(tmp_path):
    """CensusRecord should survive a save/load cycle."""
    record = CensusRecord(
        frame_number=300,
        persons=[
            CensusPersonRecord(
                bbox=(10, 20, 50, 100),
                lane_name="left",
                histogram=[0.1, 0.2, 0.3],
            ),
        ],
    )

    path = tmp_path / "test.json"
    record.save(path)
    loaded = CensusRecord.load(path)

    assert loaded.frame_number == 300
    assert len(loaded.persons) == 1
    assert loaded.persons[0].lane_name == "left"
    assert loaded.persons[0].bbox == (10, 20, 50, 100)
    assert loaded.persons[0].histogram == [0.1, 0.2, 0.3]


def test_census_record_empty_persons(tmp_path):
    """CensusRecord with no persons should round-trip correctly."""
    record = CensusRecord(frame_number=0, persons=[])
    path = tmp_path / "empty.json"
    record.save(path)
    loaded = CensusRecord.load(path)

    assert loaded.frame_number == 0
    assert len(loaded.persons) == 0


def test_census_person_record_to_dict():
    """CensusPersonRecord.to_dict should produce the expected structure."""
    person = CensusPersonRecord(
        bbox=(1, 2, 3, 4),
        lane_name="right",
        histogram=[0.5],
    )
    d = person.to_dict()
    assert d["bbox"] == [1, 2, 3, 4]
    assert d["lane_name"] == "right"
    assert d["histogram"] == [0.5]


def test_census_person_record_from_dict():
    """CensusPersonRecord.from_dict should reconstruct from a dict."""
    d = {"bbox": [10, 20, 30, 40], "lane_name": "left", "histogram": [0.1, 0.2]}
    person = CensusPersonRecord.from_dict(d)
    assert person.bbox == (10, 20, 30, 40)
    assert person.lane_name == "left"
    assert person.histogram == [0.1, 0.2]
