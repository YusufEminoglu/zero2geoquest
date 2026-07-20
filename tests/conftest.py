"""Minimal QGIS stand-in for pure-Python core tests."""
from __future__ import annotations

import sys
import types
from pathlib import Path


PLUGINS_ROOT = Path(__file__).resolve().parents[2]
if str(PLUGINS_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGINS_ROOT))


try:
    import qgis.core  # noqa: F401
except ImportError:
    qgis = types.ModuleType("qgis")
    core = types.ModuleType("qgis.core")

    class QgsSettings:
        """Enough in-memory settings behaviour for ProfileManager imports."""

        _values: dict[str, object] = {}

        def value(self, key: str, default=None):
            return self._values.get(key, default)

        def setValue(self, key: str, value) -> None:  # noqa: N802 - QGIS API
            self._values[key] = value

    core.QgsSettings = QgsSettings
    qgis.core = core
    sys.modules["qgis"] = qgis
    sys.modules["qgis.core"] = core
