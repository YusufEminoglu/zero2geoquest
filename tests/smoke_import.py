"""
Headless smoke test — run with python-qgis-ltr.bat.
Validates zero2geoquest imports without a live QGIS GUI instance.
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


# 1. QgsHighlight must NOT be in qgis.core
def _core_no_highlight():
    try:
        from qgis.core import QgsHighlight  # noqa: F401
        raise AssertionError("QgsHighlight should NOT be in qgis.core")
    except ImportError:
        pass  # correct

check("qgis.core: QgsHighlight absent", _core_no_highlight)

# 2. QgsHighlight must be in qgis.gui
check("qgis.gui: QgsHighlight present",
      lambda: __import__("qgis.gui", fromlist=["QgsHighlight"]))

# 3. Plugin module imports (no widget instantiation)
check("core.layer_data",  lambda: __import__("zero2geoquest.core.layer_data",  fromlist=[""]))
check("core.game",        lambda: __import__("zero2geoquest.core.game",        fromlist=[""]))
check("core.exporter",    lambda: __import__("zero2geoquest.core.exporter",    fromlist=[""]))
check("tools.pick",       lambda: __import__("zero2geoquest.tools.pick",       fromlist=[""]))
check("dialogs.dock (module parse)",
      lambda: __import__("zero2geoquest.dialogs.dock", fromlist=[""]))
check("main_plugin (module parse)",
      lambda: __import__("zero2geoquest.main_plugin", fromlist=[""]))

app.exitQgis()
print()
print(f"Results: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
else:
    print("All smoke checks passed.")
    sys.exit(0)
