from zero2geoquest.core.exporter import build_html


def test_export_is_standalone_and_escapes_script_terminators():
    records = [{"fid": 1, "label": "</script><b>x</b>", "value": 2,
                "area": 3, "centroid": [1, 2], "outline": [[0, 0], [1, 0], [0, 1]]}]
    output = build_html("Quest </script>", records, ["bigger"], 5, "en")
    assert "https://" not in output
    assert "<\\/script>" in output
    assert output.count("</script>") == 1
    assert "<!doctype html>" in output.lower()
    assert '"rounds":5' in output
