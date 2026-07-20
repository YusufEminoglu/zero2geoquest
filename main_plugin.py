# -*- coding: utf-8 -*-
"""02GeoQuest QGIS lifecycle and map-tool routing."""
from __future__ import annotations

import os
from contextlib import suppress

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QMessageBox, QToolBar

try:
    from qgis.PyQt.QtWidgets import QAction
except ImportError:  # pragma: no cover - Qt6
    from qgis.PyQt.QtGui import QAction

PLUGIN_TITLE = "02GeoQuest — Playable Map Studio"


class O2GeoQuestPlugin:
    TOOLBAR_NAME = "02GeoQuest Toolbar"

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.toolbar = None
        self.actions = []
        self._dock = None
        self._pick_tool = None

    def initGui(self) -> None:  # noqa: N802 - QGIS API
        self.toolbar = QToolBar(self.TOOLBAR_NAME)
        self.toolbar.setObjectName("O2GeoQuestToolbar")
        self.iface.addToolBar(self.toolbar)
        self.panel_action = QAction(
            QIcon(os.path.join(self.plugin_dir, "icons", "icon.png")),
            PLUGIN_TITLE, self.iface.mainWindow())
        self.panel_action.setCheckable(True)
        self.panel_action.setStatusTip("Turn a QGIS layer into a playable geography challenge")
        self.panel_action.triggered.connect(self._toggle_dock)
        self.toolbar.addAction(self.panel_action)
        self.actions.append(self.panel_action)

    def _toggle_dock(self) -> None:
        created = self._dock is None
        if created:
            try:
                from .dialogs.dock import GeoQuestDockWidget
                from .tools.pick import GeoQuestPickTool

                self._dock = GeoQuestDockWidget(self.iface, self.iface.mainWindow())
                self._dock.setObjectName("O2GeoQuestDock")
                self._dock.visibilityChanged.connect(self.panel_action.setChecked)
                self._dock.locate_requested.connect(self._activate_picker)
                self._dock.locate_finished.connect(self._deactivate_picker)
                self._pick_tool = GeoQuestPickTool(self.iface.mapCanvas())
                self._pick_tool.picked.connect(self._dock.handle_map_pick)
                self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._dock)
            except Exception as exc:
                QMessageBox.critical(self.iface.mainWindow(), PLUGIN_TITLE,
                                     f"Could not create the studio:\n{exc}")
                self.panel_action.setChecked(False)
                return
        self._dock.setVisible(True if created else not self._dock.isVisible())
        if self._dock.isVisible():
            self._dock.raise_()

    def _activate_picker(self) -> None:
        if self._pick_tool is not None:
            self.iface.mapCanvas().setMapTool(self._pick_tool)

    def _deactivate_picker(self) -> None:
        canvas = self.iface.mapCanvas()
        if self._pick_tool is not None and canvas.mapTool() is self._pick_tool:
            canvas.unsetMapTool(self._pick_tool)

    def unload(self) -> None:
        self._deactivate_picker()
        if self._dock is not None:
            with suppress(Exception):
                self._dock.dispose()
            self.iface.removeDockWidget(self._dock)
            self._dock.deleteLater()
            self._dock = None
        if self.toolbar is not None:
            for action in self.actions:
                self.toolbar.removeAction(action)
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None
        self.actions.clear()
