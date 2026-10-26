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
    for key, limit in (("value_label", 60), ("source", 300)):
        text = data.get(key)
        if text is not None and (not isinstance(text, str) or len(text) > limit):
            return False, f"Optional '{key}' must be text of at most {limit} characters."
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
    available = QuestionFactory(records, seed=1).available_modes(modes)
    unavailable = [mode for mode in modes if mode not in available]
    if unavailable:
        return False, "Mode(s) are not playable with these records: " + ", ".join(unavailable)
    return True, "Valid"


def export_pack(file_path: str | Path, title: str, description: str,
                records: list[dict], modes: list[str] | None = None,
                difficulty: str = "Medium", value_label: str = "") -> None:
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
        "value_label": str(value_label or "").strip()[:60] or "value",
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

# Every population uses ONE definition from ONE source. The packs once mixed
# "city proper" (Paris 2.16 M) with metropolitan figures (Tokyo 37.4 M), so
# Value Duel and Ranking marked correct answers wrong. Values are rounded to
# the nearest thousand; coordinates are city centres.
SOURCE_WUP2018 = "UN DESA, World Urbanization Prospects 2018, urban agglomeration population in 2018"

STARTER_PACKS: dict[str, dict] = {
    "World Capitals & Metropolises": {
        "title": "World Capitals & Metropolises",
        "description": "Capitals and major hubs across six continents.",
        "difficulty": "Medium",
        "value_label": "population",
        "source": SOURCE_WUP2018,
        "modes": ["bigger", "distance", "direction", "nearest", "attr_guess", "ordering"],
        "records": [
            {"fid": 1, "label": "Tokyo (Japan)", "value": 37468000, "centroid": [139.6917, 35.6895]},
            {"fid": 2, "label": "Delhi (India)", "value": 28514000, "centroid": [77.209, 28.6139]},
            {"fid": 3, "label": "Cairo (Egypt)", "value": 20076000, "centroid": [31.2357, 30.0444]},
            {"fid": 4, "label": "London (UK)", "value": 9046000, "centroid": [-0.1278, 51.5074]},
            {"fid": 5, "label": "Paris (France)", "value": 10901000, "centroid": [2.3522, 48.8566]},
            {"fid": 6, "label": "Ankara (Türkiye)", "value": 4919000, "centroid": [32.8597, 39.9334]},
            {"fid": 7, "label": "Washington D.C. (USA)", "value": 5207000, "centroid": [-77.0369, 38.9072]},
            {"fid": 8, "label": "Brasília (Brazil)", "value": 4470000, "centroid": [-47.8825, -15.7942]},
            {"fid": 9, "label": "Canberra (Australia)", "value": 448000, "centroid": [149.13, -35.2809]},
            {"fid": 10, "label": "Ottawa-Gatineau (Canada)", "value": 1363000, "centroid": [-75.6972, 45.4215]},
            {"fid": 11, "label": "Seoul (South Korea)", "value": 9963000, "centroid": [126.978, 37.5665]},
            {"fid": 12, "label": "Buenos Aires (Argentina)", "value": 14967000, "centroid": [-58.3816, -34.6037]},
        ],
    },
    "European Geography & Landmarks": {
        "title": "European Geography & Landmarks",
        "description": "Historic European capitals for spatial calibration.",
        "difficulty": "Medium",
        "value_label": "population",
        "source": SOURCE_WUP2018,
        "modes": ["bigger", "distance", "direction", "nearest", "ordering"],
        "records": [
            {"fid": 1, "label": "Berlin (Germany)", "value": 3552000, "centroid": [13.405, 52.52]},
            {"fid": 2, "label": "Rome (Italy)", "value": 4210000, "centroid": [12.4964, 41.9028]},
            {"fid": 3, "label": "Madrid (Spain)", "value": 6497000, "centroid": [-3.7038, 40.4168]},
            {"fid": 4, "label": "Vienna (Austria)", "value": 1901000, "centroid": [16.3738, 48.2082]},
            {"fid": 5, "label": "Athens (Greece)", "value": 3156000, "centroid": [23.7275, 37.9838]},
            {"fid": 6, "label": "Stockholm (Sweden)", "value": 1583000, "centroid": [18.0686, 59.3293]},
            {"fid": 7, "label": "Warsaw (Poland)", "value": 1768000, "centroid": [21.0122, 52.2297]},
            {"fid": 8, "label": "Lisbon (Portugal)", "value": 2927000, "centroid": [-9.1393, 38.7223]},
            {"fid": 9, "label": "Amsterdam (Netherlands)", "value": 1132000, "centroid": [4.9041, 52.3676]},
            {"fid": 10, "label": "Dublin (Ireland)", "value": 1201000, "centroid": [-6.2603, 53.3498]},
        ],
    },
    "Global Megacities": {
        "title": "Global Megacities",
        "description": "The ten most populous urban agglomerations of 2018.",
        "difficulty": "Hard",
        "value_label": "population",
        "source": SOURCE_WUP2018,
        "modes": ["bigger", "distance", "direction", "attr_guess", "ordering"],
        "records": [
            {"fid": 1, "label": "Tokyo", "value": 37468000, "centroid": [139.6917, 35.6895]},
            {"fid": 2, "label": "Delhi", "value": 28514000, "centroid": [77.209, 28.6139]},
            {"fid": 3, "label": "Shanghai", "value": 25582000, "centroid": [121.4737, 31.2304]},
            {"fid": 4, "label": "São Paulo", "value": 21650000, "centroid": [-46.6333, -23.5505]},
            {"fid": 5, "label": "Mexico City", "value": 21581000, "centroid": [-99.1332, 19.4326]},
            {"fid": 6, "label": "Cairo", "value": 20076000, "centroid": [31.2357, 30.0444]},
            {"fid": 7, "label": "Mumbai", "value": 19980000, "centroid": [72.8777, 19.076]},
            {"fid": 8, "label": "Beijing", "value": 19618000, "centroid": [116.3972, 39.9075]},
            {"fid": 9, "label": "Dhaka", "value": 19578000, "centroid": [90.4074, 23.7104]},
            {"fid": 10, "label": "Osaka (Kinki M.M.A.)", "value": 19281000, "centroid": [135.5538, 34.6758]},
        ],
    },
}
