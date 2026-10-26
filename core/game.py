"""Dependency-free question generation and scoring for 02GeoQuest."""
from __future__ import annotations

import math
import time

# ── Mode registry ─────────────────────────────────────────────────────────────

MODES = (
    "locate",       # click feature on canvas
    "bigger",       # which has the larger value?
    "distance",     # estimate distance between two features
    "silhouette",   # recognise a polygon outline
    "attr_guess",   # estimate a numeric attribute value via slider
    "ordering",     # drag 3-4 features into correct value order
    "nearest",      # which feature is closest to the reference?
    "blind_zoom",   # canvas zoomed to a feature, name it
    "direction",    # compass direction between two features
)

DIFFICULTY: dict[str, dict] = {
    "Easy":   {"timer": 60, "choices": 3, "tolerance": 0.40},
    "Medium": {"timer": 30, "choices": 4, "tolerance": 0.25},
    "Hard":   {"timer": 15, "choices": 6, "tolerance": 0.10},
}

# Compass Quest skips pairs whose bearing lies this close to a sector edge:
# 22.4° and 22.6° are different answers, and no player can tell them apart.
BEARING_MARGIN_DEG = 5.0

# Distance Guess skips pairs shorter than this share of the widest pair, so a
# continental quest never asks for a 30 m gap on a 3,000 km input range.
MIN_DISTANCE_SHARE = 0.01

# Below this widest-pair span distances are asked in metres, above it in km.
METRE_UNIT_LIMIT_M = 20_000.0


def display_records(records: list[dict]) -> list[dict]:
    """Copy records and give duplicate feature labels unambiguous display names.

    Every copy also receives a private ``_uid`` (its position), which is the
    identity the factory uses: Quest Pack ids may be missing, repeated across
    layers or not integers at all.
    """
    copied = [dict(record) for record in records]
    counts: dict[str, int] = {}
    for record in copied:
        label = str(record.get("label") or f"Feature {record.get('fid', '?')}")
        counts[label] = counts.get(label, 0) + 1

    used: set[str] = set()
    for index, record in enumerate(copied, 1):
        label = str(record.get("label") or f"Feature {record.get('fid', '?')}")
        if counts[label] > 1:
            layer_name = str(record.get("layer_name") or "Layer")
            label = f"{label} ({layer_name} #{record.get('fid', '?')})"
        candidate = label
        suffix = 2
        while candidate in used:
            candidate = f"{label} [{index}-{suffix}]"
            suffix += 1
        record["display_label"] = candidate
        record["_uid"] = index
        used.add(candidate)
    return copied


def _record_key(record: dict):
    """Return the identity assigned by :func:`display_records`."""
    return record.get("_uid", id(record))


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def comparison_metric(records: list[dict]) -> str:
    """Return the field Value Duel compares: ``"value"`` or ``"area"``.

    The numeric field wins whenever it carries two different values; area is
    only the fallback for quests without one. Mixing them per record would
    compare a population with a square-metre area.
    """
    values = {_number(record.get("value")) for record in records}
    values.discard(None)
    return "value" if len(values) >= 2 else "area"


def _centroid(record: dict) -> tuple[float, float] | None:
    """Return a finite WGS84 centroid, or ``None`` for unusable records."""
    point = record.get("centroid")
    if not isinstance(point, (list, tuple)) or len(point) < 2:
        return None
    lon, lat = _number(point[0]), _number(point[1])
    if lon is None or lat is None:
        return None
    return lon, lat


def _has_outline(record: dict) -> bool:
    """True when a record can render a polygon silhouette."""
    outline = record.get("outline")
    return isinstance(outline, (list, tuple)) and len(outline) >= 3


def _has_bbox(record: dict) -> bool:
    """True when a record carries a usable WGS84 bounding box."""
    bbox = record.get("bbox_wgs84")
    return (isinstance(bbox, (list, tuple)) and len(bbox) >= 4
            and all(_number(value) is not None for value in bbox[:4]))


def _numbers_are_distinct(first: float, second: float) -> bool:
    """Reject ties without making large values accidentally equal."""
    return not math.isclose(first, second, rel_tol=1e-12, abs_tol=1e-12)


def nice_ceiling(value: float) -> float:
    """Round up to 1, 2, 2.5 or 5 times a power of ten (an axis-friendly maximum)."""
    if not value or value <= 0 or not math.isfinite(value):
        return 1.0
    power = 10 ** math.floor(math.log10(value))
    for step in (1.0, 2.0, 2.5, 5.0, 10.0):
        if step * power >= value * (1 - 1e-12):
            return step * power
    return 10.0 * power


def bearing_margin(bearing_deg: float) -> float:
    """Degrees between a bearing and the nearest 8-point sector boundary."""
    offset = (bearing_deg - 22.5) % 45.0
    return min(offset, 45.0 - offset)


# ── LCG (non-cryptographic) ──────────────────────────────────────────────────


class LCG:
    """Tiny non-cryptographic generator for harmless game shuffling.

    Avoids the stdlib ``random`` module so QGIS Hub's B311 scan stays quiet;
    cryptographic randomness is neither needed nor claimed here. Draws use the
    *high* bits (multiply-shift): the low bits of a power-of-two LCG cycle with
    a tiny period, so ``state % 2`` would simply alternate.
    """

    def __init__(self, seed: int | None = None):
        if seed is None:
            seed = time.time_ns()
        self.state = int(seed) & 0xFFFFFFFF

    def _next(self) -> int:
        self.state = (1664525 * self.state + 1013904223) & 0xFFFFFFFF
        return self.state

    def below(self, limit: int) -> int:
        """Return an integer in ``[0, limit)``."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        return (self._next() * limit) >> 32

    def uniform(self) -> float:
        """Return a float in ``[0, 1)``."""
        return self._next() / 4294967296.0

    def choice(self, items):
        return items[self.below(len(items))]

    def shuffled(self, items) -> list:
        result = list(items)
        for i in range(len(result) - 1, 0, -1):
            j = self.below(i + 1)
            result[i], result[j] = result[j], result[i]
        return result

    def sample(self, items, count: int) -> list:
        if count > len(items):
            raise ValueError("Sample is larger than the available feature pool.")
        return self.shuffled(items)[:count]


# ── Joker system ─────────────────────────────────────────────────────────────


class Joker:
    """Manages one-shot joker abilities per quest."""

    ELIMINATE = "eliminate"    # remove wrong multiple-choice options
    VALUE_HINT = "value_hint"  # narrow the input range to a window around the answer
    MAP_HINT = "map_hint"      # zoom canvas to hint area

    def __init__(self, count: int = 3, rng: LCG | None = None):
        self._pool = count  # total jokers; each type at most once
        self._used: set[str] = set()
        self._rng = rng if rng is not None else LCG()

    @property
    def remaining(self) -> int:
        return self._pool - len(self._used)

    def available(self, jtype: str) -> bool:
        return jtype not in self._used and self.remaining > 0

    def use(self, jtype: str) -> bool:
        if not self.available(jtype):
            return False
        self._used.add(jtype)
        return True

    @staticmethod
    def can_eliminate(choices: list, answer) -> bool:
        """Eliminate only helps when two wrong options exist (one always stays)."""
        return sum(1 for choice in choices if str(choice) != str(answer)) >= 2

    def eliminate(self, choices: list, answer) -> list:
        """Return choices with up to 2 wrong options removed (uses one joker).

        At least one wrong option always survives, and a question where
        nothing can be removed does not consume the joker.
        """
        if not self.can_eliminate(choices, answer) or not self.use(self.ELIMINATE):
            return choices
        wrong = [c for c in choices if str(c) != str(answer)]
        remove = set(self._rng.sample(wrong, min(2, len(wrong) - 1)))
        return [c for c in choices if c not in remove]

    def narrow_range(self, lo: float, hi: float,
                     truth: float | None = None) -> tuple[float, float]:
        """Halve an input range (uses one joker).

        With ``truth`` the half-width window is placed at a random offset that
        always contains the answer — a window around the midpoint could exclude
        it and turn the joker into a trap.
        """
        if not self.use(self.VALUE_HINT):
            return lo, hi
        width = (hi - lo) / 2.0
        if truth is None or not math.isfinite(truth) or width <= 0:
            center = (lo + hi) / 2.0
            return max(lo, center - width / 2.0), min(hi, center + width / 2.0)
        truth = min(hi, max(lo, truth))
        start = truth - width * (0.15 + 0.7 * self._rng.uniform())
        start = min(hi - width, max(lo, start))
        return start, start + width


# ── Helpers ───────────────────────────────────────────────────────────────────


def _label(record: dict) -> str:
    return str(record.get("display_label") or record.get("label")
               or f"Feature {record.get('fid', '?')}")


def _distance_m(a: dict, b: dict) -> float:
    """Haversine distance in metres between two WGS84 lon/lat centroids."""
    lon1, lat1 = (math.radians(float(v)) for v in a["centroid"][:2])
    lon2, lat2 = (math.radians(float(v)) for v in b["centroid"][:2])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_008.8 * 2 * math.asin(min(1.0, math.sqrt(h)))


COMPASS_DIRECTIONS = (
    ("North", 0),
    ("North-East", 45),
    ("East", 90),
    ("South-East", 135),
    ("South", 180),
    ("South-West", 225),
    ("West", 270),
    ("North-West", 315),
)


def _bearing_deg(a: dict, b: dict) -> float:
    """Forward geodetic azimuth in degrees (0..360) from centroid A to centroid B."""
    lon1, lat1 = (math.radians(float(v)) for v in a["centroid"][:2])
    lon2, lat2 = (math.radians(float(v)) for v in b["centroid"][:2])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return bearing


def compass_direction(bearing_deg: float) -> tuple[str, int]:
    """Map azimuth in degrees to 8-point compass direction name and nominal angle."""
    index = int(((bearing_deg % 360.0) + 22.5) // 45.0) % 8
    return COMPASS_DIRECTIONS[index]


# ── Question factory ──────────────────────────────────────────────────────────


class QuestionFactory:
    """Build varied, non-repeating questions from serialisable records."""

    def __init__(self, records: list[dict], seed: int | None = None,
                 value_label: str = "value"):
        self.records = display_records(records)
        self.rng = LCG(seed)
        self.value_label = str(value_label or "").strip() or "value"
        self.metric = comparison_metric(self.records)
        self._recent: list[tuple] = []
        self._cache: dict[str, object] = {}

    def _cached(self, key: str, build):
        if key not in self._cache:
            self._cache[key] = build()
        return self._cache[key]

    def _valued(self) -> list[dict]:
        return self._cached("valued", lambda: [
            record for record in self.records if _number(record.get("value")) is not None])

    def _value_pairs(self) -> list[tuple[dict, dict, float, float]]:
        """Return every non-tied pair usable by Value Duel."""
        def build():
            candidates = [
                (record, value) for record in self.records
                if (value := _number(record.get(self.metric))) is not None
            ]
            return [
                (first, second, first_value, second_value)
                for index, (first, first_value) in enumerate(candidates)
                for second, second_value in candidates[index + 1:]
                if _numbers_are_distinct(first_value, second_value)
            ]
        return self._cached("value_pairs", build)

    def _distance_pairs(self) -> list[tuple[dict, dict, float]]:
        """Return feature pairs with valid, non-zero geographic separation."""
        def build():
            valid = [record for record in self.records if _centroid(record) is not None]
            pairs = []
            for index, first in enumerate(valid):
                for second in valid[index + 1:]:
                    metres = _distance_m(first, second)
                    if metres > 0.01:
                        pairs.append((first, second, metres))
            return pairs
        return self._cached("distance_pairs", build)

    def distance_scale(self) -> dict:
        """Return the unit and input maximum for Distance Guess.

        Both derive from the widest pair in the quest, never from the answer,
        so the input range cannot leak the distance being asked for.
        """
        def build():
            widest = max((metres for _, _, metres in self._distance_pairs()), default=0.0)
            unit = "m" if widest < METRE_UNIT_LIMIT_M else "km"
            factor = 1.0 if unit == "m" else 1000.0
            return {"unit": unit, "factor": factor, "widest_m": widest,
                    "input_max": nice_ceiling(widest * 1.1 / factor)}
        return self._cached("distance_scale", build)

    def _guess_pairs(self) -> list[tuple[dict, dict, float]]:
        """Distance pairs long enough to be a fair estimate at the quest's scale."""
        def build():
            pairs = self._distance_pairs()
            floor = self.distance_scale()["widest_m"] * MIN_DISTANCE_SHARE
            fair = [pair for pair in pairs if pair[2] >= floor]
            return fair or pairs
        return self._cached("guess_pairs", build)

    def _direction_pairs(self) -> list[tuple[dict, dict, float]]:
        """Directed pairs whose bearing is clearly inside one compass sector."""
        def build():
            directed = []
            for first, second, _ in self._distance_pairs():
                for origin, target in ((first, second), (second, first)):
                    bearing = _bearing_deg(origin, target)
                    if bearing_margin(bearing) >= BEARING_MARGIN_DEG:
                        directed.append((origin, target, bearing))
            if directed:
                return directed
            return [(a, b, _bearing_deg(a, b)) for a, b, _ in self._distance_pairs()]
        return self._cached("direction_pairs", build)

    def _nearest_options(self) -> list[tuple[dict, list[dict]]]:
        """Return references whose nearest candidate is objectively unique."""
        def build():
            valid = [record for record in self.records if _centroid(record) is not None]
            options: list[tuple[dict, list[dict]]] = []
            for reference in valid:
                ranked = sorted(
                    ((_distance_m(reference, record), record) for record in valid
                     if _record_key(record) != _record_key(reference)),
                    key=lambda item: item[0])
                if len(ranked) < 4 or ranked[0][0] <= 0.01:
                    continue
                if _numbers_are_distinct(ranked[0][0], ranked[1][0]):
                    options.append((reference, [record for _, record in ranked]))
            return options
        return self._cached("nearest_options", build)

    def available_modes(self, modes: list[str] | tuple[str, ...] | None = None) -> list[str]:
        """Return modes with enough valid data to create a fair question."""
        candidates = MODES if modes is None else modes
        unique_values = {_number(record.get("value")) for record in self._valued()}
        available: list[str] = []
        for mode in candidates:
            if mode == "locate":
                ok = bool(self.records)
            elif mode == "bigger":
                ok = bool(self._value_pairs())
            elif mode in ("distance", "direction"):
                ok = bool(self._distance_pairs())
            elif mode == "silhouette":
                ok = sum(_has_outline(record) for record in self.records) >= 4
            elif mode == "attr_guess":
                ok = len(unique_values) >= 2
            elif mode == "ordering":
                ok = len(unique_values) >= 3
            elif mode == "nearest":
                ok = bool(self._nearest_options())
            elif mode == "blind_zoom":
                ok = len(self.records) >= 2 and any(_has_bbox(r) for r in self.records)
            else:
                ok = False
            if ok:
                available.append(mode)
        return available

    def _sample(self, count: int, pool: list[dict] | None = None) -> list[dict]:
        source = self.records if pool is None else pool
        if len(source) < count:
            raise ValueError(f"At least {count} features are required for this mode.")
        for _ in range(25):
            picked = self.rng.sample(source, count)
            sig = tuple(sorted(_record_key(r) for r in picked))
            if sig not in self._recent:
                self._recent = (self._recent + [sig])[-8:]
                return picked
        return self.rng.sample(source, count)

    def _pick_pair(self, pairs: list, tag: str):
        """Pick a pair, avoiding the last few pairs asked."""
        for _ in range(25):
            pair = self.rng.choice(pairs)
            sig = (tag,) + tuple(sorted((_record_key(pair[0]), _record_key(pair[1]))))
            if sig not in self._recent:
                self._recent = (self._recent + [sig])[-8:]
                return pair
        return self.rng.choice(pairs)

    def make(self, mode: str, difficulty: str = "Medium") -> dict:  # noqa: C901
        if difficulty not in DIFFICULTY:
            difficulty = "Medium"
        diff = DIFFICULTY[difficulty]
        n_choices = diff["choices"]
        tolerance = diff["tolerance"]
        what = self.value_label

        # ── locate ───────────────────────────────────────────────────────────
        if mode == "locate":
            target = self._sample(1)[0]
            return {
                "mode": mode,
                "prompt": f"Find {_label(target)} on the map",
                "target_fid": target["fid"],
                "target_layer_id": target.get("layer_id"),
                "answer": _label(target),
                "target_bbox_wgs84": target.get("bbox_wgs84", []),
            }

        # ── bigger ───────────────────────────────────────────────────────────
        if mode == "bigger":
            pairs = self._value_pairs()
            if not pairs:
                raise ValueError("Value Duel requires at least two different numeric values.")
            a, b, av, bv = self._pick_pair(pairs, "bigger")
            if self.rng.below(2):
                a, b, av, bv = b, a, bv, av
            winner = a if av > bv else b
            prompt = (f"Which one has the greater {what}?" if self.metric == "value"
                      else "Which one covers the larger area?")
            return {
                "mode": mode,
                "prompt": prompt,
                "metric": self.metric,
                "choices": [_label(a), _label(b)],
                "answer": _label(winner),
                "values": {_label(a): av, _label(b): bv},
            }

        # ── distance ─────────────────────────────────────────────────────────
        if mode == "distance":
            pairs = self._guess_pairs()
            if not pairs:
                raise ValueError("Distance Guess requires two distinct feature locations.")
            a, b, metres = self._pick_pair(pairs, "distance")
            scale = self.distance_scale()
            return {
                "mode": mode,
                "prompt": f"Estimate the distance: {_label(a)} → {_label(b)}",
                "from": _label(a),
                "to": _label(b),
                "answer": metres,
                "tolerance": tolerance,
                "unit": scale["unit"],
                "unit_factor": scale["factor"],
                "input_max": scale["input_max"],
            }

        # ── silhouette ───────────────────────────────────────────────────────
        if mode == "silhouette":
            pool = [record for record in self.records if _has_outline(record)]
            if len(pool) < 4:
                raise ValueError("Silhouette mode requires at least 4 polygon features.")
            choices_pool = self._sample(min(n_choices, len(pool)), pool=pool)
            target = self.rng.choice(choices_pool)
            labels = self.rng.shuffled([_label(r) for r in choices_pool])
            return {
                "mode": mode,
                "prompt": "Whose silhouette is this?",
                "choices": labels,
                "answer": _label(target),
                "outline": target["outline"],
            }

        # ── attr_guess ───────────────────────────────────────────────────────
        if mode == "attr_guess":
            valued = self._valued()
            all_values = [_number(record["value"]) for record in valued]
            if len(set(all_values)) < 2:
                raise ValueError("Attribute Guess requires at least two different numeric values.")
            target = self._sample(1, pool=valued)[0]
            min_v, max_v = min(all_values), max(all_values)
            return {
                "mode": mode,
                "prompt": f"Estimate the {what} of {_label(target)}",
                "target_fid": target["fid"],
                "answer": _number(target["value"]),
                "min_val": min_v,
                "max_val": max_v,
                "tolerance": tolerance,
                "tolerance_scale": max_v - min_v,
            }

        # ── ordering ─────────────────────────────────────────────────────────
        if mode == "ordering":
            by_value: dict[float, list[dict]] = {}
            for record in self._valued():
                by_value.setdefault(_number(record["value"]), []).append(record)
            count = min(4, len(by_value))
            if count < 3:
                raise ValueError("Ranking requires at least 3 different numeric values.")
            values = self.rng.sample(list(by_value), count)
            items = [self.rng.choice(by_value[value]) for value in values]
            sorted_labels = [_label(r) for r in sorted(items,
                             key=lambda r: _number(r.get("value")), reverse=True)]
            shuffled = self.rng.shuffled(items)
            if [_label(r) for r in shuffled] == sorted_labels:
                shuffled = shuffled[1:] + shuffled[:1]  # never start solved
            return {
                "mode": mode,
                "prompt": f"Rank these from highest to lowest {what}",
                "items": [{"label": _label(r), "fid": r["fid"],
                           "value": _number(r.get("value"))} for r in shuffled],
                "answer": sorted_labels,
            }

        # ── nearest ──────────────────────────────────────────────────────────
        if mode == "nearest":
            options = self._nearest_options()
            if not options:
                raise ValueError("Nearest Neighbor requires a unique closest feature.")
            reference, ranked_records = self.rng.choice(options)
            choice_count = min(max(2, n_choices), len(ranked_records))
            nearest = ranked_records[0]
            others = ranked_records[1:]
            # Harder levels draw decoys from closer neighbours.
            if difficulty == "Hard":
                pool = others[:max(choice_count * 2, choice_count - 1)]
            elif difficulty == "Medium":
                pool = others[:max(len(others) // 2, choice_count - 1)]
            else:
                pool = others
            candidates = [nearest] + self.rng.sample(pool, choice_count - 1)
            choices = self.rng.shuffled([_label(record) for record in candidates])
            return {
                "mode": mode,
                "prompt": f"Which feature is closest to {_label(reference)}?",
                "choices": choices,
                "answer": _label(nearest),
                "reference_label": _label(reference),
                "reference_centroid": reference["centroid"],
            }

        # ── blind_zoom ───────────────────────────────────────────────────────
        if mode == "blind_zoom":
            pool = [record for record in self.records if _has_bbox(record)]
            if not pool or len(self.records) < 2:
                raise ValueError("Blind Zoom requires features with a known extent.")
            target = self._sample(1, pool=pool)[0]
            decoy_pool = [r for r in self.records if _record_key(r) != _record_key(target)]
            decoys = self.rng.sample(decoy_pool, min(n_choices - 1, len(decoy_pool)))
            choices = self.rng.shuffled([_label(target)] + [_label(r) for r in decoys])
            return {
                "mode": mode,
                "prompt": "Which feature are you zoomed in to?",
                "choices": choices,
                "answer": _label(target),
                "target_fid": target["fid"],
                "bbox_wgs84": target.get("bbox_wgs84", []),
                "target_layer_id": target.get("layer_id"),
            }

        # ── direction ────────────────────────────────────────────────────────
        if mode == "direction":
            pairs = self._direction_pairs()
            if not pairs:
                raise ValueError("Compass Quest requires two distinct feature locations.")
            a, b, bearing = self._pick_pair(pairs, "direction")
            ans_dir, ans_deg = compass_direction(bearing)
            ans_label = f"{ans_dir} ({ans_deg}°)"
            all_options = [f"{name} ({deg}°)" for name, deg in COMPASS_DIRECTIONS]
            decoys = [opt for opt in all_options if opt != ans_label]
            sampled_decoys = self.rng.sample(decoys, min(n_choices - 1, len(decoys)))
            choices = self.rng.shuffled([ans_label] + sampled_decoys)
            return {
                "mode": mode,
                "prompt": f"In which compass direction is {_label(b)} relative to {_label(a)}?",
                "from": _label(a),
                "to": _label(b),
                "choices": choices,
                "answer": ans_label,
                "bearing_deg": round(bearing, 1),
                "from_centroid": a.get("centroid", []),
                "to_centroid": b.get("centroid", []),
            }

        raise ValueError(f"Unknown game mode: {mode!r}")


# ── Game session ──────────────────────────────────────────────────────────────


def score_for(seconds: float, streak: int, closeness: float = 1.0) -> int:
    """Points for one correct answer: base + speed bonus + streak bonus, scaled.

    ``streak`` is the streak *including* this answer. The offline HTML game
    uses the same formula, so a score means the same thing in both places.
    """
    speed_bonus = max(0, 150 - int(seconds * 8))
    streak_bonus = min(300, max(0, streak - 1) * 30)
    return int((500 + speed_bonus + streak_bonus) * closeness)


class GameSession:
    """Stateful scoring with streak, lives, timing, difficulty and jokers."""

    def __init__(self, modes: list[str], round_limit: int = 10, lives: int = 3,
                 seed: int | None = None, difficulty: str = "Medium",
                 joker_count: int = 3):
        valid = list(dict.fromkeys(m for m in modes if m in MODES))
        if not valid:
            raise ValueError("At least one valid game mode is required.")
        self.modes = valid
        self.round_limit = max(1, int(round_limit))
        self.initial_lives = max(1, int(lives))
        self.lives = self.initial_lives
        self.score = 0
        self.streak = 0
        self.best_streak = 0
        self.rounds = 0
        self.correct = 0
        self.difficulty = difficulty if difficulty in DIFFICULTY else "Medium"
        self.rng = LCG(seed)
        self.joker = Joker(max(0, int(joker_count)), rng=LCG(self.rng._next()))
        self.started_at = time.monotonic()
        self.question_started_at = self.started_at
        self._awaiting_answer = False
        self._mode_bag: list[str] = []
        self._last_mode: str | None = None

    @property
    def finished(self) -> bool:
        return self.lives <= 0 or self.rounds >= self.round_limit

    @property
    def accuracy(self) -> float:
        return self.correct / self.rounds if self.rounds else 0.0

    @property
    def timer_seconds(self) -> int:
        return DIFFICULTY.get(self.difficulty, DIFFICULTY["Medium"])["timer"]

    @property
    def awaiting_answer(self) -> bool:
        """Whether one active challenge may still be answered."""
        return self._awaiting_answer and not self.finished

    def next_mode(self) -> str:
        if self.finished:
            raise RuntimeError("The quest has already finished.")
        if self._awaiting_answer:
            raise RuntimeError("Answer the current challenge before requesting another one.")
        self.question_started_at = time.monotonic()
        self._awaiting_answer = True
        if not self._mode_bag:
            self._mode_bag = self.rng.shuffled(self.modes)
            if (len(self._mode_bag) > 1 and self._last_mode is not None
                    and self._mode_bag[0] == self._last_mode):
                self._mode_bag[0], self._mode_bag[1] = self._mode_bag[1], self._mode_bag[0]
        mode = self._mode_bag.pop(0)
        self._last_mode = mode
        return mode

    def answer(self, is_correct: bool, elapsed: float | None = None,
               closeness: float = 1.0) -> dict:
        if self.finished:
            raise RuntimeError("The quest has already finished.")
        if not self._awaiting_answer:
            raise RuntimeError("Start a challenge before submitting an answer.")
        seconds = ((time.monotonic() - self.question_started_at)
                   if elapsed is None else _number(elapsed))
        seconds = max(0.0, seconds if seconds is not None else 0.0)
        timed_out = seconds >= self.timer_seconds
        is_correct = bool(is_correct) and not timed_out
        closeness = _number(closeness)
        closeness = min(1.0, max(0.25, closeness if closeness is not None else 0.25))
        self._awaiting_answer = False
        self.rounds += 1
        gained = 0
        if is_correct:
            self.correct += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
            gained = score_for(seconds, self.streak, closeness)
            self.score += gained
        else:
            self.streak = 0
            self.lives -= 1
        return {
            "correct": is_correct, "gained": gained, "score": self.score,
            "streak": self.streak, "lives": self.lives, "rounds": self.rounds,
            "finished": self.finished,
            "timed_out": timed_out,
        }

    def summary(self) -> dict:
        return {
            "score": self.score, "rounds": self.rounds, "correct": self.correct,
            "accuracy": self.accuracy, "best_streak": self.best_streak,
            "lives_left": self.lives,
            "duration": max(0.0, time.monotonic() - self.started_at),
        }
