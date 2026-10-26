# -*- coding: utf-8 -*-
"""Convert QGIS vector layers into compact, game-ready records."""
from __future__ import annotations

import math

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsWkbTypes,
)


def _first_outline(geometry: QgsGeometry, limit: int = 240,
                   x_scale: float = 1.0) -> list[list[float]]:
    """Return a simplified exterior ring in layer coordinates.

    ``x_scale`` compresses longitudes for geographic layers (cos of the
    latitude), otherwise a degree-based silhouette is stretched east-west.
    """
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
    return [[float(point.x()) * x_scale, float(point.y())] for point in ring[::step]]


def _field_request(layer, *field_names: str) -> QgsFeatureRequest:
    """Fetch geometry plus only the attributes the quest needs."""
    request = QgsFeatureRequest()
    names = [name for name in field_names if name]
    if names:
        request.setSubsetOfAttributes(names, layer.fields())
    else:
        request.setNoAttributes()
    return request


def records_from_layer(layer, label_field: str = "", value_field: str = "",
                       maximum: int = 500) -> list[dict]:
    """Snapshot non-empty features without retaining QGIS feature objects.

    Layers larger than ``maximum`` are thinned with an even stride over the
    whole layer, so a quest from 20,000 parcels is not just the first 500
    rows of the table (usually one corner of the map).
    """
    if layer is None or not layer.isValid():
        raise ValueError("Choose a valid vector layer.")
    project = QgsProject.instance()
    distance = QgsDistanceArea()
    distance.setSourceCrs(layer.crs(), project.transformContext())
    distance.setEllipsoid(project.ellipsoid() or "WGS84")
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    to_wgs84 = QgsCoordinateTransform(layer.crs(), wgs84, project.transformContext())
    geographic = layer.crs().isGeographic()

    total = layer.featureCount()
    thin = bool(total and total > maximum)

    records: list[dict] = []
    for index, feature in enumerate(layer.getFeatures(
            _field_request(layer, label_field, value_field))):
        # Fractional stride: keep feature i when floor(i * maximum / total)
        # advances, which spreads exactly `maximum` picks over the table.
        if thin and index and (index * maximum) // total == ((index - 1) * maximum) // total:
            continue
        geometry = feature.geometry()
        if not geometry or geometry.isEmpty():
            continue
        label_value = feature[label_field] if label_field else feature.id()
        label = str(label_value).strip() if label_value is not None else ""
        if not label or label == "NULL":
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
        anchor = geometry.pointOnSurface()
        if not anchor or anchor.isEmpty():
            anchor = geometry.centroid()
        if not anchor or anchor.isEmpty():
            continue
        centroid = anchor.asPoint()
        try:
            point = to_wgs84.transform(centroid)
            lon_lat = [float(point.x()), float(point.y())]
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
        x_scale = math.cos(math.radians(centroid.y())) if geographic else 1.0
        outline = _first_outline(geometry, x_scale=max(0.05, x_scale))
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
    """Combine records from two layers (up to maximum total).

    Picking the same layer twice adds nothing but duplicate features, so the
    second copy is ignored.
    """
    if layer_b is None or layer_b.id() == layer_a.id():
        return records_from_layer(layer_a, label_a, value_a, maximum)
    half = maximum // 2
    records_a = records_from_layer(layer_a, label_a, value_a, half)
    records_b = records_from_layer(layer_b, label_b, value_b, maximum - len(records_a))
    return records_a + records_b


def features_at_point(layer, point, tolerance: float) -> list[int]:
    """Return feature ids hit by a click: containing features first, then by distance.

    Uses a spatial filter, so a click on a 100,000-feature layer does not scan
    every geometry. Overlapping polygons all count as hit.
    """
    if layer is None:
        return []
    tolerance = max(float(tolerance), 0.0)
    rect = QgsRectangle(point.x() - tolerance, point.y() - tolerance,
                        point.x() + tolerance, point.y() + tolerance)
    request = QgsFeatureRequest().setFilterRect(rect)
    request.setNoAttributes()
    click = QgsGeometry.fromPointXY(QgsPointXY(point.x(), point.y()))
    containing: list[int] = []
    near: list[tuple[float, int]] = []
    for feature in layer.getFeatures(request):
        geometry = feature.geometry()
        if not geometry or geometry.isEmpty():
            continue
        if geometry.intersects(click):
            containing.append(int(feature.id()))
            continue
        gap = geometry.distance(click)
        if gap <= tolerance:
            near.append((gap, int(feature.id())))
    return containing + [fid for _, fid in sorted(near)]


def feature_at_point(layer, point, tolerance: float) -> int | None:
    """Return the containing or nearest feature id around a canvas point."""
    hits = features_at_point(layer, point, tolerance)
    return hits[0] if hits else None
