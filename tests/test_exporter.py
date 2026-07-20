import pytest

from zero2geoquest.core.exporter import available_html_modes, build_html


def test_export_is_standalone_and_escapes_script_terminators():
    records = [{"fid": 1, "label": "</script><b>x</b>", "value": 2, "area": 3, "centroid": [1, 2], "outline": [[0, 0], [1, 0], [0, 1]]}, {"fid": 2, "label": "Beta", "value": 3, "area": 4, "centroid": [2, 2], "outline": [[0, 0], [2, 0], [0, 2]]}, {"fid": 3, "label": "Gamma", "value": 4, "area": 5, "centroid": [3, 2], "outline": [[0, 0], [3, 0], [0, 3]]}, {"fid": 4, "label": "Delta", "value": 5, "area": 6, "centroid": [4, 2], "outline": [[0, 0], [4, 0], [0, 4]]}, {"fid": 5, "label": "Epsilon", "value": 6, "area": 7, "centroid": [5, 2], "outline": [[0, 0], [5, 0], [0, 5]]}]
    # Source records are fully declared above.
    output = build_html("Quest </script>", records, ["bigger"], 5)
    assert "https://" not in output
    assert "<\\/script>" in output
    assert output.count("</script>") == 1
    assert "<!doctype html>" in output.lower()
    assert '"rounds":5' in output


def test_export_rejects_qgis_only_modes_instead_of_falling_back():
    with pytest.raises(ValueError, match="Offline HTML needs"):
        build_html("Map-only quest", [], ["locate", "blind_zoom"], 5)


def test_ranking_is_exported_when_the_data_is_valid():
    records = [
        {"fid": 1, "label": "Low", "value": -1},
        {"fid": 2, "label": "Mid", "value": 0},
        {"fid": 3, "label": "High", "value": 1},
    ]
    assert available_html_modes(records, ["locate", "ordering"]) == ["ordering"]
    output = build_html("Ranking quest", records, ["ordering"], 3)
    assert '"modes":["ordering"]' in output
    assert "function rankChoices" in output
