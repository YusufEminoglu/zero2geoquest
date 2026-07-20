"""
Headless smoke test for zero2geoquest — run with python-qgis-ltr.bat.
Validates imports, module structure, and core game engine logic.
"""
from __future__ import annotations
import sys
import traceback

PLUGINS_ROOT = r"C:\Users\YE\PyCharmMiscProject\qgis_plugins"
if PLUGINS_ROOT not in sys.path:
    sys.path.insert(0, PLUGINS_ROOT)

from qgis.core import QgsApplication  # noqa: E402
app = QgsApplication([], False)
app.initQgis()

PASS = []
FAIL = []


def check(label: str, fn):
    try:
        fn()
        PASS.append(label)
        print(f"  PASS  {label}")
    except Exception:
        FAIL.append(label)
        print(f"  FAIL  {label}")
        traceback.print_exc()


# 1. Import guards
def _core_no_highlight():
    try:
        from qgis.core import QgsHighlight  # noqa: F401
        raise AssertionError("QgsHighlight should NOT be in qgis.core")
    except ImportError:
        pass

check("qgis.core: QgsHighlight absent", _core_no_highlight)
check("qgis.gui: QgsHighlight present",
      lambda: __import__("qgis.gui", fromlist=["QgsHighlight"]))

# 2. Core modules
check("core.layer_data",  lambda: __import__("zero2geoquest.core.layer_data",  fromlist=[""]))
check("core.game",        lambda: __import__("zero2geoquest.core.game",        fromlist=[""]))
check("core.exporter",    lambda: __import__("zero2geoquest.core.exporter",    fromlist=[""]))
check("core.profiles",    lambda: __import__("zero2geoquest.core.profiles",    fromlist=[""]))
check("tools.pick",       lambda: __import__("zero2geoquest.tools.pick",       fromlist=[""]))
check("dialogs.dock",     lambda: __import__("zero2geoquest.dialogs.dock",     fromlist=[""]))
check("main_plugin",      lambda: __import__("zero2geoquest.main_plugin",      fromlist=[""]))

# 3. Game engine unit tests
def _game_engine():
    from zero2geoquest.core.game import (
        MODES, DIFFICULTY, LCG, Joker, QuestionFactory, GameSession
    )
    assert len(MODES) == 8, f"Expected 8 modes, got {len(MODES)}"
    assert set(DIFFICULTY.keys()) == {"Easy", "Medium", "Hard"}
    # LCG determinism
    rng = LCG(42)
    first = rng._next()
    rng2 = LCG(42)
    assert rng2._next() == first, "LCG not deterministic"
    # Joker
    joker = Joker(3)
    assert joker.remaining == 3
    choices = ["A", "B", "C", "D"]
    remaining = joker.eliminate(choices, "A")
    assert "A" in remaining, "Correct answer must survive eliminate"
    assert len(remaining) == len(choices) - 2, "Eliminate should remove 2"
    # QuestionFactory — non-map modes
    records = [
        {"fid": i, "label": f"Place {i}", "value": float(i * 10),
         "area": float(i), "centroid": [float(i), float(i * 0.5)],
         "bbox_wgs84": [float(i - 0.01), float(i * 0.5 - 0.01),
                        float(i + 0.01), float(i * 0.5 + 0.01)],
         "outline": [[float(i), float(i)], [float(i + 0.1), float(i)],
                     [float(i + 0.1), float(i + 0.1)], [float(i), float(i + 0.1)]],
         "layer_id": "test"}
        for i in range(1, 11)
    ]
    factory = QuestionFactory(records, seed=42)
    for mode in ("locate", "bigger", "distance", "silhouette",
                 "attr_guess", "ordering", "nearest", "blind_zoom"):
        q = factory.make(mode, "Medium")
        assert q["mode"] == mode, f"make({mode}) returned wrong mode"
        assert "prompt" in q, f"make({mode}) missing prompt"
        assert "answer" in q, f"make({mode}) missing answer"
    # GameSession
    session = GameSession(list(MODES), round_limit=5, lives=3,
                          difficulty="Hard", joker_count=3)
    session.next_mode()
    assert session.timer_seconds == 15
    result = session.answer(True)
    session.next_mode()
    assert result["score"] > 0
    result2 = session.answer(False)
    assert result2["lives"] == 2

check("game engine unit tests", _game_engine)

# 4. Profiles unit tests
def _profiles():
    from zero2geoquest.core.profiles import ProfileManager, AVATARS
    assert len(AVATARS) >= 5
    pm = ProfileManager()
    # Just test the class loads and methods exist
    assert callable(pm.load_profiles)
    assert callable(pm.load_sessions)
    assert callable(pm.export_csv)

check("profiles unit tests", _profiles)

# 5. Exporter
def _exporter():
    from zero2geoquest.core.exporter import build_html
    records = [
        {"fid": 1, "label": "Alpha", "value": 100.0, "area": 50.0,
         "centroid": [28.0, 41.0], "bbox_wgs84": [27.9, 40.9, 28.1, 41.1], "outline": []},
        {"fid": 2, "label": "Beta", "value": 120.0, "area": 60.0,
         "centroid": [29.0, 41.0], "bbox_wgs84": [28.9, 40.9, 29.1, 41.1], "outline": []},
    ]
    html = build_html("Test Quest", records, ["bigger"], 5)
    assert "<html" in html
    assert "02GeoQuest" in html
    assert "dark" in html  # dark mode feature present

check("exporter produces valid HTML", _exporter)

app.exitQgis()
print()
print(f"Results: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
else:
    print("All smoke checks passed.")
    sys.exit(0)
