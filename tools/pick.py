# -*- coding: utf-8 -*-
"""Canvas click tool for Locate rounds."""
from qgis.PyQt.QtCore import pyqtSignal
from qgis.gui import QgsMapTool


class GeoQuestPickTool(QgsMapTool):
    picked = pyqtSignal(object)

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas

    def canvasReleaseEvent(self, event) -> None:  # noqa: N802 - QGIS API
        self.picked.emit(self.toMapCoordinates(event.pos()))

    def deactivate(self) -> None:
        super().deactivate()
        self.deactivated.emit()
