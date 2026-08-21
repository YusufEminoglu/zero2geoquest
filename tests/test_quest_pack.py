# -*- coding: utf-8 -*-
"""Unit tests for Quest Pack validation and serialization."""
import tempfile
from pathlib import Path

from zero2geoquest.core.quest_pack import (
    STARTER_PACKS, export_pack, import_pack, validate_pack,
)


def test_starter_packs_are_valid():
    assert len(STARTER_PACKS) >= 3
    for name, pack in STARTER_PACKS.items():
        valid, msg = validate_pack(pack)
        assert valid, f"Starter pack '{name}' is invalid: {msg}"
        assert len(pack["records"]) >= 5


def test_export_and_import_quest_pack():
    records = [
        {"fid": 1, "label": "Alpha", "centroid": [10.0, 20.0], "value": 100},
        {"fid": 2, "label": "Beta", "centroid": [15.0, 25.0], "value": 200},
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        pack_file = Path(tmpdir) / "test.geoquest.json"
        export_pack(pack_file, "Test Quest", "A description", records, ["bigger", "distance"])
        assert pack_file.is_file()

        loaded = import_pack(pack_file)
        assert loaded["title"] == "Test Quest"
        assert len(loaded["records"]) == 2
        assert loaded["records"][0]["label"] == "Alpha"
        assert loaded["records"][1]["value"] == 200
