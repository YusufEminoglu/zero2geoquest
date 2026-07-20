# -*- coding: utf-8 -*-
"""Convert QGIS vector layers into compact, game-ready records."""
from __future__ import annotations

import math

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsGeometry,
    QgsPointXY,
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
    # Dispatch on actual flat type — asMultiPolygon() raises on single Polygon in QGIS 3.34+
    _MULTI = getattr(QgsWkbTypes, "MultiPolygon",
                     getattr(QgsWkbTypes.Type, "MultiPolygon", 6))
    if QgsWkbTypes.flatType(geom.wkbType()) == _MULTI:
        parts = geom.asMultiPolygon()
        rings = [part[0] for part in parts if part] if parts else []
    else:
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
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    to_wgs84 = QgsCoordinateTransform(
        layer.crs(), wgs84, QgsProject.instance().transformContext())
    records: list[dict] = []
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
        # Bounding box in WGS84 — needed for blind_zoom canvas extent
        try:
            raw_bbox = geometry.boundingBox()
            sw = to_wgs84.transform(QgsPointXY(raw_bbox.xMinimum(), raw_bbox.yMinimum()))
            ne = to_wgs84.transform(QgsPointXY(raw_bbox.xMaximum(), raw_bbox.yMaximum()))
            bbox_wgs84 = [float(sw.x()), float(sw.y()), float(ne.x()), float(ne.y())]
        except Exception:
            cx, cy = lon_lat
            buf = 0.002
            bbox_wgs84 = [cx - buf, cy - buf, cx + buf, cy + buf]
        outline = _first_outline(geometry)
        records.append({
            "fid": int(feature.id()),
            "label": label,
            "value": value,
            "area": area,
            "centroid": lon_lat,
            "bbox_wgs84": bbox_wgs84,
            "outline": outline,
            "layer_id": layer.id(),
            "layer_name": layer.name(),
        })
        if len(records) >= maximum:
            break
    return records


def merge_layers(layer_a, label_a: str, value_a: str,
                 layer_b, label_b: str, value_b: str,
                 maximum: int = 500) -> list[dict]:
    """Combine records from two layers (up to maximum total)."""
    half = maximum // 2
    records_a = records_from_layer(layer_a, label_a, value_a, half)
    records_b = records_from_layer(layer_b, label_b, value_b, maximum - len(records_a))
    return records_a + records_b


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
