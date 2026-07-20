# -*- coding: utf-8 -*-
"""Convert a QGIS vector layer into compact, game-ready records."""
from __future__ import annotations

import math

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsGeometry,
    QgsProject,
    QgsWkbTypes,
)


def _first_outline(geometry: QgsGeometry, limit: int = 240) -> list[list[float]]:
    """Return a simplified exterior ring in layer coordinates."""
    if not geometry or geometry.isEmpty():
        return []
    geom = geometry
    if QgsWkbTypes.geometryType(geom.wkbType()) != Qgis.GeometryType.Polygon:
        return []
    bbox = geom.boundingBox()
    tolerance = max(bbox.width(), bbox.height()) / 180.0
    if tolerance > 0:
        simplified = geom.simplify(tolerance)
        if simplified and not simplified.isEmpty():
            geom = simplified
    polygon = geom.asMultiPolygon()
    rings = [part[0] for part in polygon if part] if polygon else []
    if not rings:
        single = geom.asPolygon()
        rings = [single[0]] if single else []
    if not rings:
        return []
    ring = max(rings, key=len)
    step = max(1, math.ceil(len(ring) / limit))
    return [[float(point.x()), float(point.y())] for point in ring[::step]]


def records_from_layer(layer, label_field: str = "", value_field: str = "",
                       maximum: int = 500) -> list[dict]:
    """Snapshot non-empty features without retaining QGIS feature objects."""
    if layer is None or not layer.isValid():
        raise ValueError("Choose a valid vector layer.")
    distance = QgsDistanceArea()
    distance.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
    distance.setEllipsoid(QgsProject.instance().ellipsoid() or "WGS84")
    to_wgs84 = QgsCoordinateTransform(
        layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsProject.instance().transformContext())
    records = []
    for feature in layer.getFeatures():
        geometry = feature.geometry()
        if not geometry or geometry.isEmpty():
            continue
        label_value = feature[label_field] if label_field else feature.id()
        label = str(label_value).strip() if label_value is not None else ""
        if not label:
            label = f"Feature {feature.id()}"
        value = None
        if value_field:
            try:
                value = float(feature[value_field])
                if not math.isfinite(value):
                    value = None
            except (TypeError, ValueError):
                value = None
        try:
            area = abs(float(distance.measureArea(geometry)))
        except Exception:
            area = 0.0
        centroid = geometry.pointOnSurface().asPoint()
        try:
            geographic = to_wgs84.transform(centroid)
            lon_lat = [float(geographic.x()), float(geographic.y())]
        except Exception:
            lon_lat = [float(centroid.x()), float(centroid.y())]
        records.append({
            "fid": int(feature.id()), "label": label, "value": value,
            "area": area, "centroid": lon_lat,
            "outline": _first_outline(geometry),
        })
        if len(records) >= maximum:
            break
    return records


def feature_at_point(layer, point, tolerance: float) -> int | None:
    """Return the containing or nearest feature id around a canvas point."""
    if layer is None:
        return None
    best_id = None
    best_distance = float("inf")
    click = QgsGeometry.fromPointXY(point)
    for feature in layer.getFeatures():
        geometry = feature.geometry()
        if not geometry or geometry.isEmpty():
            continue
        if geometry.contains(click) or geometry.intersects(click):
            return int(feature.id())
        distance = geometry.distance(click)
        if distance < best_distance:
            best_distance = distance
            best_id = int(feature.id())
    return best_id if best_distance <= tolerance else None
