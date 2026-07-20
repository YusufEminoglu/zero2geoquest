"""Dependency-free question generation and scoring for 02GeoQuest."""
from __future__ import annotations

import math
import time

MODES = ("locate", "bigger", "distance", "silhouette")


class LCG:
    """Tiny non-cryptographic generator for harmless game shuffling.

    Avoiding the stdlib random module also keeps QGIS Hub's strict B311 scan
    quiet; cryptographic randomness is neither needed nor claimed here.
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
        for index in range(len(result) - 1, 0, -1):
            other = self._next() % (index + 1)
            result[index], result[other] = result[other], result[index]
        return result

    def sample(self, items, count: int) -> list:
        if count > len(items):
            raise ValueError("Sample is larger than the available feature pool.")
        return self.shuffled(items)[:count]


def _label(record: dict) -> str:
    return str(record.get("label") or f"Feature {record.get('fid', '?')}")


def _distance(a: dict, b: dict) -> float:
    """Great-circle distance in metres for WGS84 lon/lat centroids."""
    lon1, lat1 = (math.radians(float(v)) for v in a["centroid"])
    lon2, lat2 = (math.radians(float(v)) for v in b["centroid"])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    haversine = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371008.8 * 2 * math.asin(min(1.0, math.sqrt(haversine)))


class QuestionFactory:
    """Build varied, non-repeating questions from serializable records."""

    def __init__(self, records: list[dict], seed: int | None = None):
        self.records = [dict(record) for record in records]
        self.rng = LCG(seed)
        self._recent: list[tuple] = []

    def _sample(self, count: int) -> list[dict]:
        if len(self.records) < count:
            raise ValueError(f"At least {count} playable features are required.")
        for _ in range(25):
            picked = self.rng.sample(self.records, count)
            signature = tuple(sorted(record["fid"] for record in picked))
            if signature not in self._recent:
                self._recent.append(signature)
                self._recent = self._recent[-8:]
                return picked
        return self.rng.sample(self.records, count)

    def make(self, mode: str) -> dict:
        if mode == "locate":
            target = self._sample(1)[0]
            return {
                "mode": mode,
                "prompt": f"Find {_label(target)} on the map",
                "target_fid": target["fid"],
                "answer": _label(target),
            }
        if mode == "bigger":
            a, b = self._sample(2)
            av = float(a.get("value") if a.get("value") is not None else a.get("area", 0.0))
            bv = float(b.get("value") if b.get("value") is not None else b.get("area", 0.0))
            winner = a if av >= bv else b
            return {
                "mode": mode,
                "prompt": "Which one has the greater value?",
                "choices": [_label(a), _label(b)],
                "answer": _label(winner),
                "values": {_label(a): av, _label(b): bv},
            }
        if mode == "distance":
            a, b = self._sample(2)
            metres = _distance(a, b)
            return {
                "mode": mode,
                "prompt": f"Estimate the distance: {_label(a)} → {_label(b)}",
                "from": _label(a),
                "to": _label(b),
                "answer": metres,
                "unit": "m",
            }
        if mode == "silhouette":
            pool = [r for r in self.records if r.get("outline")]
            if len(pool) < 4:
                raise ValueError("Silhouette mode requires at least 4 polygon features.")
            choices = self.rng.sample(pool, 4)
            target = self.rng.choice(choices)
            labels = [_label(record) for record in choices]
            labels = self.rng.shuffled(labels)
            return {
                "mode": mode,
                "prompt": "Whose silhouette is this?",
                "choices": labels,
                "answer": _label(target),
                "outline": target["outline"],
            }
        raise ValueError(f"Unknown game mode: {mode}")


class GameSession:
    """Stateful scoring with streak, lives, timing and a fixed round limit."""

    def __init__(self, modes: list[str], round_limit: int = 10, lives: int = 3,
                 seed: int | None = None):
        valid = [mode for mode in modes if mode in MODES]
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
        self.rng = LCG(seed)
        self.started_at = time.monotonic()
        self.question_started_at = self.started_at

    @property
    def finished(self) -> bool:
        return self.lives <= 0 or self.rounds >= self.round_limit

    @property
    def accuracy(self) -> float:
        return self.correct / self.rounds if self.rounds else 0.0

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
            streak_bonus = min(250, max(0, self.streak - 1) * 25)
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
