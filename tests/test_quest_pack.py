# -*- coding: utf-8 -*-
"""Unit tests for Quest Pack validation and serialization."""
from pathlib import Path

import pytest

from zero2geoquest.core.quest_pack import (
    PACK_VERSION, STARTER_PACKS, export_pack, import_pack, validate_pack,
)


def test_starter_packs_are_valid():
    assert len(STARTER_PACKS) >= 3
    for name, pack in STARTER_PACKS.items():
        valid, msg = validate_pack(pack)
        assert valid, f"Starter pack '{name}' is invalid: {msg}"
        assert len(pack["records"]) >= 5


def test_export_and_import_quest_pack(tmp_path):
    records = [
        {"fid": 1, "label": "Alpha", "centroid": [10.0, 20.0], "value": 100},
        {"fid": 2, "label": "Beta", "centroid": [15.0, 25.0], "value": 200},
    ]
    pack_file = Path(tmp_path) / "test.geoquest.json"
    export_pack(pack_file, "Test Quest", "A description", records, ["bigger", "distance"])
    assert pack_file.is_file()
    assert not (pack_file.parent / f".{pack_file.name}.tmp").exists()

    loaded = import_pack(pack_file)
    assert loaded["version"] == PACK_VERSION
    assert loaded["title"] == "Test Quest"
    assert len(loaded["records"]) == 2
    assert loaded["records"][0]["label"] == "Alpha"
    assert loaded["records"][1]["value"] == 200


def test_export_assigns_portable_ids_for_mixed_layer_fid_collisions(tmp_path):
    records = [
        {"fid": 7, "layer_id": "a", "label": "Alpha", "value": 1},
        {"fid": 7, "layer_id": "b", "label": "Beta", "value": 2},
    ]
    pack_file = tmp_path / "mixed.geoquest.json"
    export_pack(pack_file, "Mixed", "", records, ["bigger"])
    loaded = import_pack(pack_file)
    assert [record["fid"] for record in loaded["records"]] == [1, 2]


@pytest.mark.parametrize("mutator, expected", [
    (lambda pack: pack.update(modes=["locate"]), "live QGIS layer"),
    (lambda pack: pack.update(modes=["unknown"]), "Unknown game mode"),
    (lambda pack: pack["records"][0].update(centroid=[181, 20]), "WGS84 bounds"),
    (lambda pack: pack["records"][0].update(value=float("inf")), "non-finite"),
])
def test_pack_validation_rejects_unsafe_or_unplayable_data(mutator, expected):
    pack = {
        "title": "Safe pack",
        "difficulty": "Medium",
        "modes": ["bigger"],
        "records": [
            {"fid": 1, "label": "Alpha", "value": 1, "centroid": [10, 20]},
            {"fid": 2, "label": "Beta", "value": 2, "centroid": [11, 21]},
        ],
    }
    mutator(pack)
    valid, message = validate_pack(pack)
    assert not valid
    assert expected in message


def test_pack_validation_reports_modes_without_suitable_data():
    pack = {
        "title": "Tied values",
        "difficulty": "Easy",
        "modes": ["bigger"],
        "records": [
            {"fid": 1, "label": "Alpha", "value": 5},
            {"fid": 2, "label": "Beta", "value": 5},
        ],
    }
    valid, message = validate_pack(pack)
    assert not valid
    assert "not playable" in message
