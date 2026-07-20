# -*- coding: utf-8 -*-
"""QGIS entry point for 02GeoQuest."""


def classFactory(iface):  # noqa: N802 - QGIS API
    from .main_plugin import O2GeoQuestPlugin

    return O2GeoQuestPlugin(iface)
