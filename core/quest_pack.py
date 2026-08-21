# -*- coding: utf-8 -*-
"""Portable Quest Pack import, export and starter pack registry for 02GeoQuest."""
from __future__ import annotations

import json
from pathlib import Path


def validate_pack(data: dict) -> tuple[bool, str]:
    """Validate that a dict contains the necessary Quest Pack structure."""
    if not isinstance(data, dict):
        return False, "Quest Pack root must be a JSON object."
    if "title" not in data or not str(data["title"]).strip():
        return False, "Quest Pack must have a non-empty 'title'."
    records = data.get("records")
    if not isinstance(records, list) or len(records) < 2:
        return False, "Quest Pack must contain at least 2 feature records."
    for idx, r in enumerate(records):
        if not isinstance(r, dict):
            return False, f"Record #{idx} is not a valid JSON object."
        if "label" not in r and "display_label" not in r:
            return False, f"Record #{idx} is missing a 'label'."
    return True, "Valid"


def export_pack(file_path: str | Path, title: str, description: str,
                records: list[dict], modes: list[str] | None = None,
                difficulty: str = "Medium") -> None:
    """Save a curated Quest Pack to disk as .geoquest.json."""
    clean_records = []
    for idx, r in enumerate(records, 1):
        clean_records.append({
            "fid": r.get("fid", idx),
            "label": str(r.get("display_label") or r.get("label") or f"Feature {idx}"),
            "value": r.get("value"),
            "area": r.get("area"),
            "centroid": r.get("centroid"),
            "bbox_wgs84": r.get("bbox_wgs84"),
            "outline": r.get("outline"),
        })

    pack = {
        "version": "1.1.0",
        "title": title.strip() or "Custom Quest Pack",
        "description": description.strip(),
        "difficulty": difficulty,
        "modes": modes or ["bigger", "distance", "direction", "silhouette", "nearest"],
        "records": clean_records,
    }

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=2)


def import_pack(file_path: str | Path) -> dict:
    """Load and validate a Quest Pack from disk."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Quest pack file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    valid, msg = validate_pack(data)
    if not valid:
        raise ValueError(f"Invalid quest pack '{path.name}': {msg}")
    return data


# ── Built-in Starter Packs ───────────────────────────────────────────────────

STARTER_PACKS: dict[str, dict] = {
    "World Capitals & Metropolises": {
        "title": "World Capitals & Metropolises",
        "description": "Global capitals and major cultural hubs across 6 continents.",
        "difficulty": "Medium",
        "modes": ["bigger", "distance", "direction", "nearest", "attr_guess", "ordering"],
        "records": [
            {"fid": 1, "label": "Tokyo (Japan)", "value": 37400000, "centroid": [139.6917, 35.6895]},
            {"fid": 2, "label": "Delhi (India)", "value": 32900000, "centroid": [77.2090, 28.6139]},
            {"fid": 3, "label": "Cairo (Egypt)", "value": 22100000, "centroid": [31.2357, 30.0444]},
            {"fid": 4, "label": "London (UK)", "value": 9000000, "centroid": [-0.1278, 51.5074]},
            {"fid": 5, "label": "Paris (France)", "value": 2160000, "centroid": [2.3522, 48.8566]},
            {"fid": 6, "label": "Ankara (Türkiye)", "value": 5800000, "centroid": [32.8597, 39.9334]},
            {"fid": 7, "label": "Washington D.C. (USA)", "value": 689000, "centroid": [-77.0369, 38.9072]},
            {"fid": 8, "label": "Brasília (Brazil)", "value": 3050000, "centroid": [-47.8825, -15.7942]},
            {"fid": 9, "label": "Canberra (Australia)", "value": 456000, "centroid": [149.1300, -35.2809]},
            {"fid": 10, "label": "Ottawa (Canada)", "value": 1017000, "centroid": [-75.6972, 45.4215]},
            {"fid": 11, "label": "Seoul (South Korea)", "value": 9960000, "centroid": [126.9780, 37.5665]},
            {"fid": 12, "label": "Buenos Aires (Argentina)", "value": 15300000, "centroid": [-58.3816, -34.6037]},
        ],
    },
    "European Geography & Landmarks": {
        "title": "European Geography & Landmarks",
        "description": "Historic European cities and capitals for spatial calibration.",
        "difficulty": "Medium",
        "modes": ["bigger", "distance", "direction", "nearest", "ordering"],
        "records": [
            {"fid": 1, "label": "Berlin (Germany)", "value": 3750000, "centroid": [13.4050, 52.5200]},
            {"fid": 2, "label": "Rome (Italy)", "value": 2870000, "centroid": [12.4964, 41.9028]},
            {"fid": 3, "label": "Madrid (Spain)", "value": 3220000, "centroid": [-3.7038, 40.4168]},
            {"fid": 4, "label": "Vienna (Austria)", "value": 1930000, "centroid": [16.3738, 48.2082]},
            {"fid": 5, "label": "Athens (Greece)", "value": 3150000, "centroid": [23.7275, 37.9838]},
            {"fid": 6, "label": "Stockholm (Sweden)", "value": 975000, "centroid": [18.0686, 59.3293]},
            {"fid": 7, "label": "Warsaw (Poland)", "value": 1790000, "centroid": [21.0122, 52.2297]},
            {"fid": 8, "label": "Lisbon (Portugal)", "value": 545000, "centroid": [-9.1393, 38.7223]},
            {"fid": 9, "label": "Amsterdam (Netherlands)", "value": 872000, "centroid": [4.9041, 52.3676]},
            {"fid": 10, "label": "Dublin (Ireland)", "value": 554000, "centroid": [-6.2603, 53.3498]},
        ],
    },
    "Global Megacities": {
        "title": "Global Megacities",
        "description": "The world's highest-density urban agglomerations and population centers.",
        "difficulty": "Hard",
        "modes": ["bigger", "distance", "direction", "attr_guess", "ordering"],
        "records": [
            {"fid": 1, "label": "Tokyo-Yokohama", "value": 37400000, "centroid": [139.6917, 35.6895]},
            {"fid": 2, "label": "Jakarta", "value": 33700000, "centroid": [106.8456, -6.2088]},
            {"fid": 3, "label": "Delhi", "value": 32900000, "centroid": [77.2090, 28.6139]},
            {"fid": 4, "label": "Guangzhou-Foshan", "value": 26900000, "centroid": [113.2644, 23.1291]},
            {"fid": 5, "label": "Mumbai", "value": 24900000, "centroid": [72.8777, 19.0760]},
            {"fid": 6, "label": "Manila", "value": 24000000, "centroid": [120.9842, 14.5995]},
            {"fid": 7, "label": "Shanghai", "value": 24000000, "centroid": [121.4737, 31.2304]},
            {"fid": 8, "label": "São Paulo", "value": 23000000, "centroid": [-46.6333, -23.5505]},
            {"fid": 9, "label": "Seoul-Incheon", "value": 23000000, "centroid": [126.9780, 37.5665]},
            {"fid": 10, "label": "Mexico City", "value": 21800000, "centroid": [-99.1332, 19.4326]},
        ],
    },
}
