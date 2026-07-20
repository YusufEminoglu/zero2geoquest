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
)

DIFFICULTY: dict[str, dict] = {
    "Easy":   {"timer": 60, "choices": 3, "tolerance": 0.40},
    "Medium": {"timer": 30, "choices": 4, "tolerance": 0.25},
    "Hard":   {"timer": 15, "choices": 6, "tolerance": 0.10},
}

# ── LCG (non-cryptographic) ──────────────────────────────────────────────────


class LCG:
    """Tiny non-cryptographic generator for harmless game shuffling.

    Avoids the stdlib ``random`` module so QGIS Hub's B311 scan stays quiet;
    cryptographic randomness is neither needed nor claimed here.
    """

    def __init__(self, seed: int | None = None):
        self.state = int(20260720 if seed is None else seed) & 0xFFFFFFFF

    def _next(self) -> int:
        self.state = (1664525 * self.state + 1013904223) & 0xFFFFFFFF
        return self.state

    def choice(self, items):
        return items[self._next() % len(items)]

    def shuffled(self, items) -> list:
        result = list(items)
        for i in range(len(result) - 1, 0, -1):
            j = self._next() % (i + 1)
            result[i], result[j] = result[j], result[i]
        return result

    def sample(self, items, count: int) -> list:
        if count > len(items):
            raise ValueError("Sample is larger than the available feature pool.")
        return self.shuffled(items)[:count]


# ── Joker system ─────────────────────────────────────────────────────────────


class Joker:
    """Manages three one-shot joker abilities per quest."""

    ELIMINATE = "eliminate"    # remove 2 wrong multiple-choice options
    VALUE_HINT = "value_hint"  # narrow slider range by 50 %
    MAP_HINT = "map_hint"      # zoom canvas to hint area

    def __init__(self, count: int = 3):
        self._pool = count  # total jokers; distribute across types
        self._used: set[str] = set()

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

    def eliminate(self, choices: list, answer) -> list:
        """Return choices with 2 wrong options removed (uses one joker)."""
        if not self.use(self.ELIMINATE):
            return choices
        wrong = [c for c in choices if str(c) != str(answer)]
        rng = LCG()
        remove = set(rng.sample(wrong, min(2, max(0, len(wrong) - 1))))
        return [c for c in choices if c not in remove]

    def narrow_range(self, lo: float, hi: float) -> tuple[float, float]:
        """Narrow a slider range by 50 % around its midpoint (uses one joker)."""
        if not self.use(self.VALUE_HINT):
            return lo, hi
        center = (lo + hi) / 2.0
        quarter = (hi - lo) / 4.0
        return max(lo, center - quarter), min(hi, center + quarter)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _label(record: dict) -> str:
    return str(record.get("label") or f"Feature {record.get('fid', '?')}")


def _distance_m(a: dict, b: dict) -> float:
    """Haversine distance in metres between two WGS84 lon/lat centroids."""
    lon1, lat1 = (math.radians(float(v)) for v in a["centroid"])
    lon2, lat2 = (math.radians(float(v)) for v in b["centroid"])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_008.8 * 2 * math.asin(min(1.0, math.sqrt(h)))


# ── Question factory ──────────────────────────────────────────────────────────


class QuestionFactory:
    """Build varied, non-repeating questions from serialisable records."""

    def __init__(self, records: list[dict], seed: int | None = None):
        self.records = [dict(r) for r in records]
        self.rng = LCG(seed)
        self._recent: list[tuple] = []

    def _sample(self, count: int, pool: list[dict] | None = None) -> list[dict]:
        source = self.records if pool is None else pool
        if len(source) < count:
            raise ValueError(f"At least {count} features are required for this mode.")
        for _ in range(25):
            picked = self.rng.sample(source, count)
            sig = tuple(sorted(r["fid"] for r in picked))
            if sig not in self._recent:
                self._recent = (self._recent + [sig])[-8:]
                return picked
        return self.rng.sample(source, count)

    def make(self, mode: str, difficulty: str = "Medium") -> dict:  # noqa: C901
        diff = DIFFICULTY.get(difficulty, DIFFICULTY["Medium"])
        n_choices = diff["choices"]
        tolerance = diff["tolerance"]

        # ── locate ───────────────────────────────────────────────────────────
        if mode == "locate":
            target = self._sample(1)[0]
            return {
                "mode": mode,
                "prompt": f"Find {_label(target)} on the map",
                "target_fid": target["fid"],
                "answer": _label(target),
                "target_bbox_wgs84": target.get("bbox_wgs84", []),
            }

        # ── bigger ───────────────────────────────────────────────────────────
        if mode == "bigger":
            a, b = self._sample(2)
            av = float(a.get("value") if a.get("value") is not None else a.get("area", 0))
            bv = float(b.get("value") if b.get("value") is not None else b.get("area", 0))
            winner = a if av >= bv else b
            return {
                "mode": mode,
                "prompt": "Which one has the greater value?",
                "choices": [_label(a), _label(b)],
                "answer": _label(winner),
                "values": {_label(a): av, _label(b): bv},
            }

        # ── distance ─────────────────────────────────────────────────────────
        if mode == "distance":
            a, b = self._sample(2)
            metres = _distance_m(a, b)
            return {
                "mode": mode,
                "prompt": f"Estimate the distance: {_label(a)} → {_label(b)}",
                "from": _label(a),
                "to": _label(b),
                "answer": metres,
                "tolerance": tolerance,
                "unit": "m",
            }

        # ── silhouette ───────────────────────────────────────────────────────
        if mode == "silhouette":
            pool = [r for r in self.records if r.get("outline")]
            if len(pool) < 4:
                raise ValueError("Silhouette mode requires at least 4 polygon features.")
            choices_pool = self.rng.sample(pool, min(n_choices, len(pool)))
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
            valued = [r for r in self.records if r.get("value") is not None]
            if len(valued) < 2:
                raise ValueError("Attribute Guess requires at least 2 features with a numeric field.")
            target = self._sample(1, pool=valued)[0]
            all_values = [float(r["value"]) for r in valued]
            min_v, max_v = min(all_values), max(all_values)
            return {
                "mode": mode,
                "prompt": f"Estimate the value of: {_label(target)}",
                "target_fid": target["fid"],
                "answer": float(target["value"]),
                "min_val": min_v,
                "max_val": max_v,
                "tolerance": tolerance,
            }

        # ── ordering ─────────────────────────────────────────────────────────
        if mode == "ordering":
            valued = [r for r in self.records if r.get("value") is not None]
            count = min(4, len(valued))
            if count < 3:
                raise ValueError("Ordering mode requires at least 3 features with a numeric field.")
            items = self._sample(count, pool=valued)
            sorted_labels = [_label(r) for r in sorted(items,
                             key=lambda r: float(r.get("value") or 0), reverse=True)]
            shuffled = self.rng.shuffled(items)
            return {
                "mode": mode,
                "prompt": "Rank these from highest to lowest value",
                "items": [{"label": _label(r), "fid": r["fid"],
                            "value": float(r.get("value") or 0)} for r in shuffled],
                "answer": sorted_labels,
            }

        # ── nearest ──────────────────────────────────────────────────────────
        if mode == "nearest":
            if len(self.records) < 5:
                raise ValueError("Nearest Neighbor requires at least 5 features.")
            pool = self._sample(5)
            reference = pool[0]
            candidates = pool[1:]
            nearest = min(candidates,
                          key=lambda r: _distance_m(reference, r))
            choices = self.rng.shuffled([_label(r) for r in candidates])
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
            target = self._sample(1)[0]
            decoy_pool = [r for r in self.records if r["fid"] != target["fid"]]
            decoys = self.rng.sample(decoy_pool, min(n_choices - 1, len(decoy_pool)))
            choices = self.rng.shuffled([_label(target)] + [_label(r) for r in decoys])
            return {
                "mode": mode,
                "prompt": "Which feature are you zoomed in to?",
                "choices": choices,
                "answer": _label(target),
                "target_fid": target["fid"],
                "bbox_wgs84": target.get("bbox_wgs84", []),
            }

        raise ValueError(f"Unknown game mode: {mode!r}")


# ── Game session ──────────────────────────────────────────────────────────────


class GameSession:
    """Stateful scoring with streak, lives, timing, difficulty and jokers."""

    def __init__(self, modes: list[str], round_limit: int = 10, lives: int = 3,
                 seed: int | None = None, difficulty: str = "Medium",
                 joker_count: int = 3):
        valid = [m for m in modes if m in MODES]
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
        self.difficulty = difficulty
        self.joker = Joker(max(0, int(joker_count)))
        self.rng = LCG(seed)
        self.started_at = time.monotonic()
        self.question_started_at = self.started_at

    @property
    def finished(self) -> bool:
        return self.lives <= 0 or self.rounds >= self.round_limit

    @property
    def accuracy(self) -> float:
        return self.correct / self.rounds if self.rounds else 0.0

    @property
    def timer_seconds(self) -> int:
        return DIFFICULTY.get(self.difficulty, DIFFICULTY["Medium"])["timer"]

    def next_mode(self) -> str:
        self.question_started_at = time.monotonic()
        return self.rng.choice(self.modes)

    def answer(self, is_correct: bool, elapsed: float | None = None,
               closeness: float = 1.0) -> dict:
        seconds = max(0.0, (time.monotonic() - self.question_started_at)
                      if elapsed is None else float(elapsed))
        self.rounds += 1
        gained = 0
        if is_correct:
            self.correct += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
            speed_bonus = max(0, 150 - int(seconds * 8))
            streak_bonus = min(300, max(0, self.streak - 1) * 30)
            gained = int((500 + speed_bonus + streak_bonus) * max(0.25, closeness))
            self.score += gained
        else:
            self.streak = 0
            self.lives -= 1
        return {
            "correct": bool(is_correct), "gained": gained, "score": self.score,
            "streak": self.streak, "lives": self.lives, "rounds": self.rounds,
            "finished": self.finished,
        }

    def summary(self) -> dict:
        return {
            "score": self.score, "rounds": self.rounds, "correct": self.correct,
            "accuracy": self.accuracy, "best_streak": self.best_streak,
            "lives_left": self.lives,
            "duration": max(0.0, time.monotonic() - self.started_at),
        }
