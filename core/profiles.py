"""Student profiles and class-mode session history for 02GeoQuest."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from pathlib import Path

from qgis.core import QgsSettings


_PROFILES_KEY = "zero2geoquest/profiles"
_SESSIONS_KEY = "zero2geoquest/class_sessions"

AVATARS = ["🗺️", "🏙️", "🌍", "🧭", "📍", "🏔️", "🌊", "🌿", "⭐", "🔥"]


@dataclass
class Profile:
    name: str
    avatar: str = "🗺️"
    created: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))


class ProfileManager:
    """Persist and retrieve student profiles and session results via QgsSettings."""

    # ── Profiles ─────────────────────────────────────────────────────────────

    def load_profiles(self) -> list[Profile]:
        raw = str(QgsSettings().value(_PROFILES_KEY, "[]"))
        try:
            items = json.loads(raw)
            return [Profile(**item) for item in items if "name" in item]
        except Exception:
            return []

    def save_profiles(self, profiles: list[Profile]) -> None:
        data = [{"name": p.name, "avatar": p.avatar, "created": p.created}
                for p in profiles]
        QgsSettings().setValue(_PROFILES_KEY, json.dumps(data))

    def add_profile(self, name: str, avatar: str = "🗺️") -> Profile:
        name = name.strip()
        if not name:
            raise ValueError("Profile name cannot be empty.")
        profiles = self.load_profiles()
        if any(p.name == name for p in profiles):
            raise ValueError(f"A profile named '{name}' already exists.")
        profile = Profile(name=name, avatar=avatar)
        profiles.append(profile)
        self.save_profiles(profiles)
        return profile

    def remove_profile(self, name: str) -> None:
        profiles = [p for p in self.load_profiles() if p.name != name]
        self.save_profiles(profiles)

    # ── Sessions ─────────────────────────────────────────────────────────────

    def load_sessions(self) -> list[dict]:
        raw = str(QgsSettings().value(_SESSIONS_KEY, "[]"))
        try:
            return json.loads(raw)
        except Exception:
            return []

    def save_session(self, profile_name: str, avatar: str,
                     summary: dict, quest_title: str, difficulty: str) -> None:
        sessions = self.load_sessions()
        sessions.append({
            "player": profile_name,
            "avatar": avatar,
            "quest": quest_title,
            "difficulty": difficulty,
            "score": int(summary.get("score", 0)),
            "accuracy": round(float(summary.get("accuracy", 0)), 4),
            "best_streak": int(summary.get("best_streak", 0)),
            "correct": int(summary.get("correct", 0)),
            "rounds": int(summary.get("rounds", 0)),
            "duration_s": round(float(summary.get("duration", 0)), 1),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        QgsSettings().setValue(_SESSIONS_KEY, json.dumps(sessions[-300:]))

    def clear_sessions(self) -> None:
        QgsSettings().setValue(_SESSIONS_KEY, "[]")

    def export_csv(self, path: str) -> int:
        sessions = self.load_sessions()
        if not sessions:
            return 0
        buf = StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(sessions[0].keys()))
        writer.writeheader()
        writer.writerows(sessions)
        Path(path).write_text(buf.getvalue(), encoding="utf-8-sig")
        return len(sessions)
