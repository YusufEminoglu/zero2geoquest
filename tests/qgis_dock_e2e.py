"""
Headless end-to-end test of the 02GeoQuest dock on real QGIS layers.

Run with C:\\OSGeo4W\\bin\\python-qgis-ltr.bat (3.44) and python-qgis.bat (4.x).
Plays complete quests through the dock's own buttons and answers every round
correctly, so any mode the player cannot answer fails the run.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PLUGINS_ROOT = str(Path(__file__).resolve().parents[2])
if PLUGINS_ROOT not in sys.path:
    sys.path.insert(0, PLUGINS_ROOT)

from qgis.core import (  # noqa: E402
    QgsApplication, QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsProject,
    QgsRectangle, QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant  # noqa: E402

app = QgsApplication([], True)
app.initQgis()

from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox  # noqa: E402
from qgis.testing.mocked import get_iface  # noqa: E402

# No modal dialog may block a headless run.
for _name in ("information", "warning", "critical", "question"):
    setattr(QMessageBox, _name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))

PASS: list[str] = []
FAIL: list[str] = []


def check(label: str, fn) -> None:
    try:
        fn()
        PASS.append(label)
        print(f"  PASS  {label}")
    except Exception:
        FAIL.append(label)
        print(f"  FAIL  {label}")
        traceback.print_exc()


def polygon_layer() -> QgsVectorLayer:
    """Ten tall rectangles at 60°N (cos 60° = 0.5) plus attribute values."""
    layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "Districts", "memory")
    provider = layer.dataProvider()
    provider.addAttributes([QgsField("name", QVariant.String), QgsField("pop", QVariant.Double)])
    layer.updateFields()
    features = []
    for i in range(10):
        x0, y0 = 10.0 + (i % 5) * 0.013 + (i // 5) * 0.004, 60.0 + (i // 5) * 0.011
        rect = QgsRectangle(x0, y0, x0 + 0.002, y0 + 0.006)
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromRect(rect))
        feature.setAttributes([f"District {i}", 1000.0 + i * 750.0])
        features.append(feature)
    # Two overlapping squares for the map-pick test
    for i, x0 in enumerate((11.0, 11.001)):
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromRect(QgsRectangle(x0, 61.0, x0 + 0.002, 61.002)))
        feature.setAttributes([f"Overlap {i}", 50.0 + i])
        features.append(feature)
    provider.addFeatures(features)
    return layer


def point_layer(count: int) -> QgsVectorLayer:
    layer = QgsVectorLayer("Point?crs=EPSG:4326", f"Points{count}", "memory")
    layer.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    layer.updateFields()
    features = []
    for i in range(count):
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(27.0 + (i % 40) * 0.001,
                                                               38.4 + (i // 40) * 0.001)))
        feature.setAttributes([f"P{i}"])
        features.append(feature)
    layer.dataProvider().addFeatures(features)
    return layer


POLY = polygon_layer()
POINTS = point_layer(1200)
QgsProject.instance().addMapLayers([POLY, POINTS])

from zero2geoquest.core.layer_data import features_at_point, records_from_layer  # noqa: E402
from zero2geoquest.core.quest_pack import STARTER_PACKS  # noqa: E402
from zero2geoquest.dialogs.dock import GeoQuestDockWidget  # noqa: E402

IFACE = get_iface()
CANVAS = IFACE.mapCanvas()
CANVAS.resize(800, 600)
CANVAS.setDestinationCrs(POLY.crs())
CANVAS.setExtent(POLY.extent())


# ── Layer snapshot ────────────────────────────────────────────────────────────

def _geographic_silhouette_aspect():
    records = records_from_layer(POLY, "name", "pop")
    outline = next(r["outline"] for r in records if r["label"] == "District 0")
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    ratio = (max(xs) - min(xs)) / (max(ys) - min(ys))
    # 0.002° wide x 0.006° tall at 60°N is 1:6 on the ground, 1:3 in raw degrees.
    assert abs(ratio - 1 / 6) < 0.01, ratio


def _overlapping_click_hits_both():
    hits = features_at_point(POLY, QgsPointXY(11.0015, 61.001), 1e-6)
    labels = {POLY.getFeature(fid)["name"] for fid in hits}
    assert labels == {"Overlap 0", "Overlap 1"}, labels


def _large_layers_are_sampled_evenly():
    records = records_from_layer(POINTS, "name", "", maximum=500)
    fids = [r["fid"] for r in records]
    assert len(fids) == 500, len(fids)
    assert max(fids) > 1000, "only the first rows of the table were used"


check("geographic silhouettes keep ground proportions", _geographic_silhouette_aspect)
check("a click on overlapping polygons hits both", _overlapping_click_hits_both)
check("large layers are sampled across the whole table", _large_layers_are_sampled_evenly)


# ── Dock: play every mode through the real widgets ────────────────────────────

def make_dock(layer=POLY) -> GeoQuestDockWidget:
    dock = GeoQuestDockWidget(IFACE, IFACE.mainWindow())
    dock.layer_combo.setLayer(layer)
    dock.label_field.setField("name")
    if layer is POLY:
        dock.value_field.setField("pop")
    return dock


def answer_correctly(dock: GeoQuestDockWidget, facts: dict) -> None:
    question = dock.question
    mode = question["mode"]
    facts.setdefault("modes", set()).add(mode)
    if mode in ("bigger", "silhouette", "nearest", "blind_zoom", "direction"):
        buttons = [b for b in dock._answer_buttons if b.property("choice") is not None]
        assert buttons, f"{mode}: no answer buttons were shown"
        if mode == "bigger":
            facts["eliminate_on_duel"] = facts.get("eliminate_on_duel", False) or dock.joker_eliminate.isEnabled()
        next(b for b in buttons if b.property("choice") == question["answer"]).click()
    elif mode == "distance":
        assert dock.distance_guess.value() == 0, "distance input must start at 0"
        assert abs(dock.distance_guess.maximum() - question["input_max"]) < 1e-9
        dock.distance_guess.setValue(question["answer"] / question["unit_factor"])
        assert dock.distance_submit.isEnabled(), "distance submit is disabled"
        dock.distance_submit.click()
    elif mode == "attr_guess":
        step = round((question["answer"] - dock._attr_slider_min) / dock._attr_slider_scale)
        dock.attr_slider.setValue(int(step))
        assert dock.attr_submit.isEnabled(), "attribute submit stayed disabled"
        facts["attr_rounds"] = facts.get("attr_rounds", 0) + 1
        dock.attr_submit.click()
    elif mode == "ordering":
        target = question["answer"]
        for index, label in enumerate(target):
            row = next(r for r in range(dock.ordering_list.count())
                       if dock.ordering_list.item(r).data(256) == label)  # Qt.UserRole
            dock.ordering_list.setCurrentRow(row)
            while dock.ordering_list.currentRow() > index:
                dock.order_up_btn.click()
        assert dock.ordering_submit.isEnabled(), "ranking submit stayed disabled"
        facts["ordering_rounds"] = facts.get("ordering_rounds", 0) + 1
        dock.ordering_submit.click()
    elif mode == "locate":
        record = next(r for r in dock.records if r["fid"] == question["target_fid"])
        dock.handle_map_pick(QgsPointXY(*record["centroid"]))
    else:
        raise AssertionError(f"unhandled mode {mode}")
    feedback = dock.feedback.text()
    assert not dock.next_button.isHidden(), f"{mode}: round did not finish"
    assert "Great, correct!" in feedback, f"{mode}: correct answer scored as wrong: {feedback}"


def _full_quest_every_mode():
    dock = make_dock()
    for check_box in dock.mode_checks.values():
        check_box.setChecked(True)
    dock.round_count.setValue(36)
    dock.lives_count.setValue(1)  # a single wrong round ends the test
    dock.start_game()
    assert dock.session is not None, dock.builder_status.text()
    assert set(dock._active_modes) == set(dock.mode_checks), dock._active_modes
    facts: dict = {}
    while not dock.session.finished:
        answer_correctly(dock, facts)
        dock.next_button.click()
    assert dock.session.correct == 36, dock.session.summary()
    assert facts["modes"] == set(dock.mode_checks), facts["modes"]
    assert facts["attr_rounds"] >= 2 and facts["ordering_rounds"] >= 2, facts
    assert not facts.get("eliminate_on_duel"), "Eliminate joker offered on a 2-choice duel"
    assert "population" not in dock.prompt.text()
    dock.dispose()


def _value_prompt_uses_field_name():
    dock = make_dock()
    for mode, check_box in dock.mode_checks.items():
        check_box.setChecked(mode == "bigger")
    dock.start_game()
    assert dock.question["prompt"] == "Which one has the greater pop?", dock.question["prompt"]
    dock.dispose()


def _pack_replay_and_export_stay_on_the_pack():
    dock = make_dock()
    pack = STARTER_PACKS["World Capitals & Metropolises"]
    dock._apply_pack_data(pack)
    assert len(dock.records) == len(pack["records"])
    while not dock.session.finished:
        answer_correctly(dock, {})
        dock.next_button.click()
    dock._play_again()
    labels = {r["label"] for r in dock.records}
    assert "Tokyo (Japan)" in labels and "District 0" not in labels, "replay switched to the layer"
    target = Path(tempfile.mkdtemp()) / "pack_game.html"
    original = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(target), ""))
    try:
        dock._export_html()
    finally:
        QFileDialog.getSaveFileName = original
    text = target.read_text(encoding="utf-8")
    assert "Tokyo (Japan)" in text and "District 0" not in text
    assert '"value_label":"population"' in text
    # Choosing a layer again ends pack mode.
    dock.layer_combo.setLayer(POINTS)
    dock.layer_combo.setLayer(POLY)
    assert dock._pack_data is None
    dock.dispose()


def _points_blind_zoom_has_a_real_extent():
    dock = make_dock(POINTS)
    for mode, check_box in dock.mode_checks.items():
        check_box.setChecked(mode == "blind_zoom")
    dock.start_game()
    assert dock.question["mode"] == "blind_zoom"
    extent = CANVAS.extent()
    assert extent.width() > 0.002 and extent.height() > 0.002, extent.toString()
    dock.dispose()


def _new_profile_becomes_active():
    dock = make_dock()
    dock.new_profile_name.setEditText("Ada")
    dock._add_profile()
    assert dock._active_profile and dock._active_profile[0] == "Ada", dock._active_profile
    dock._remove_profile()
    assert dock._active_profile is None
    dock.dispose()


check("dock plays a 36-round quest in all 9 modes, all answerable", _full_quest_every_mode)
check("Value Duel prompt names the chosen field", _value_prompt_uses_field_name)
check("Quest Pack replay and HTML export keep the pack records", _pack_replay_and_export_stay_on_the_pack)
check("Blind Zoom on a point layer zooms to a real extent", _points_blind_zoom_has_a_real_extent)
check("a newly added profile becomes the active profile", _new_profile_becomes_active)

QgsProject.instance().removeAllMapLayers()
print()
print(f"Results: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", FAIL)
    sys.stdout.flush()
    os._exit(1)
print("All dock end-to-end checks passed.")
sys.stdout.flush()
os._exit(0)
