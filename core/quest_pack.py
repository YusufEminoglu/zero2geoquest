# -*- coding: utf-8 -*-
"""Portable Quest Pack import, export and starter pack registry for 02GeoQuest."""
from __future__ import annotations

from contextlib import suppress
import json
from pathlib import Path

from .game import DIFFICULTY, MODES, QuestionFactory


PACK_VERSION = "1.2"
MAX_PACK_BYTES = 5 * 1024 * 1024
MAX_PACK_RECORDS = 5_000
PORTABLE_MODES = tuple(mode for mode in MODES if mode != "locate")


def _finite_number(value) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number == number and abs(number) != float("inf")


def validate_pack(data: dict) -> tuple[bool, str]:
    """Validate that a dict contains the necessary Quest Pack structure."""
    if not isinstance(data, dict):
        return False, "Quest Pack root must be a JSON object."
    if "title" not in data or not str(data["title"]).strip():
        return False, "Quest Pack must have a non-empty 'title'."
    difficulty = data.get("difficulty", "Medium")
    if difficulty not in DIFFICULTY:
        return False, f"Unsupported difficulty: {difficulty!r}."
    modes = data.get("modes")
    if not isinstance(modes, list) or not modes:
        return False, "Quest Pack must declare at least one game mode."
    unknown_modes = [mode for mode in modes if mode not in MODES]
    if unknown_modes:
        return False, "Unknown game mode(s): " + ", ".join(map(str, unknown_modes))
    if "locate" in modes:
        return False, "Map Hunt cannot be stored in a portable Quest Pack because it needs a live QGIS layer."
    if len(set(modes)) != len(modes):
        return False, "Quest Pack modes must not contain duplicates."
    records = data.get("records")
    if not isinstance(records, list) or len(records) < 2:
        return False, "Quest Pack must contain at least 2 feature records."
    if len(records) > MAX_PACK_RECORDS:
        return False, f"Quest Pack exceeds the {MAX_PACK_RECORDS:,}-record safety limit."
    seen_ids: set[str] = set()
    for idx, r in enumerate(records):
        if not isinstance(r, dict):
            return False, f"Record #{idx} is not a valid JSON object."
        label = str(r.get("display_label") or r.get("label") or "").strip()
        if not label:
            return False, f"Record #{idx} has an empty 'label'."
        record_id = str(r.get("fid", idx))
        if record_id in seen_ids:
            return False, f"Record #{idx} duplicates feature id {record_id!r}."
        seen_ids.add(record_id)
        for field in ("value", "area"):
            if r.get(field) is not None and not _finite_number(r[field]):
                return False, f"Record #{idx} has a non-finite '{field}'."
        centroid = r.get("centroid")
        if centroid is not None:
            if (not isinstance(centroid, (list, tuple)) or len(centroid) < 2
                    or not _finite_number(centroid[0]) or not _finite_number(centroid[1])):
                return False, f"Record #{idx} has an invalid centroid."
            lon, lat = float(centroid[0]), float(centroid[1])
            if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                return False, f"Record #{idx} centroid is outside WGS84 bounds."
    available = QuestionFactory(records).available_modes(modes)
    unavailable = [mode for mode in modes if mode not in available]
    if unavailable:
        return False, "Mode(s) are not playable with these records: " + ", ".join(unavailable)
    return True, "Valid"


def export_pack(file_path: str | Path, title: str, description: str,
                records: list[dict], modes: list[str] | None = None,
                difficulty: str = "Medium") -> None:
    """Save a curated Quest Pack to disk as .geoquest.json."""
    clean_records = []
    for idx, r in enumerate(records, 1):
        clean_records.append({
            # Portable packs use their own stable ids; source-layer ids may
            # collide when a quest mixes two QGIS layers.
            "fid": idx,
            "label": str(r.get("display_label") or r.get("label") or f"Feature {idx}"),
            "value": r.get("value"),
            "area": r.get("area"),
            "centroid": r.get("centroid"),
            "bbox_wgs84": r.get("bbox_wgs84"),
            "outline": r.get("outline"),
        })

    pack = {
        "version": PACK_VERSION,
        "title": title.strip() or "Custom Quest Pack",
        "description": description.strip(),
        "difficulty": difficulty,
        "modes": list(dict.fromkeys(mode for mode in (
            modes or ["bigger", "distance", "direction", "silhouette", "nearest"]
        ) if mode in PORTABLE_MODES)),
        "records": clean_records,
    }

    valid, message = validate_pack(pack)
    if not valid:
        raise ValueError(f"Cannot export Quest Pack: {message}")

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


def import_pack(file_path: str | Path) -> dict:
    """Load and validate a Quest Pack from disk."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Quest pack file not found: {path}")
    if path.stat().st_size > MAX_PACK_BYTES:
        raise ValueError(f"Quest pack exceeds the {MAX_PACK_BYTES // (1024 * 1024)} MB safety limit.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Quest pack contains invalid JSON at line {exc.lineno}.") from exc
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
