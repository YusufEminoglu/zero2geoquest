# 02GeoQuest — Playable Map Studio
[![Documentation](https://img.shields.io/badge/📖_Reference_Manual-13a0a0)](https://geophilo.com/zero2geoquest/)

Turn any QGIS vector dataset into an interactive geography game, teaching activity, data-familiarisation exercise, or public engagement quest.

---

## 📖 Documentation

**[Comprehensive Academic Reference Manual](https://geophilo.com/zero2geoquest/)** — complete documentation of every feature, parameter, and workflow. Hosted on Web Documentation.


## 🎮 What You Can Play (9 Modes)

- 📍 **Map Hunt:** Find requested features directly on the live QGIS map canvas.
- ⚖️ **Value Duel:** Compare two features by your numeric field (the prompt names it) or, without one, by area.
- 📏 **Distance Guess:** Estimate the geographic distance between two places — in metres for city-scale quests, kilometres otherwise.
- 🧩 **Know the Shape:** Identify a feature from its antialiased polygon silhouette.
- 🎯 **Attribute Guess:** Estimate a numeric attribute using a slider control.
- 📊 **Ranking:** Order 3–4 features from highest to lowest value via drag-and-drop.
- 🧭 **Nearest Neighbour:** Determine which feature is geographically closest to a reference location.
- 🔍 **Blind Zoom:** Identify a feature when the map canvas automatically zooms to it.
- 🧭 **Compass Quest:** Test forward geodetic azimuths and cardinal directions (N, NE, E, SE, S, SW, W, NW).

---

## 📦 Quest Packs & 📜 Certificates

- **Quest Pack Import/Export:** Save custom quests as portable JSON (`.json`) files with validation, or load the 3 built-in starter packs (*World Capitals*, *European Landmarks*, *Global Megacities*). Starter-pack populations all come from UN DESA *World Urbanization Prospects 2018* (urban agglomeration, 2018).
- **Reliable Portable Packs:** Imported packs play their packaged records directly, use atomic saves, validate geographic/numeric data, and reject modes that require a live QGIS layer.
- **Geographic Intelligence Certificates:** Generate printable, responsive standalone HTML achievement certificates with dynamic rank assessment badges based on score tiers.

---

## ⚡ Game Features & Rules

- **Difficulty Levels:** Easy (60s timer, 3 choices), Medium (30s timer, 4 choices), and Hard (15s timer, 6 choices).
- **Joker System:** Eliminate wrong options, narrow the input to a window that always contains the answer, or zoom to a hint area.
- **Multi-Layer Mixing:** Combine two vector layers into a single mixed quest.
- **Streak & Speed Bonuses:** Build multiplier streaks (🔥 ×3+) for high score bonuses.
- **Balanced Mode Rotation:** Every selected mode appears once before the rotation repeats, avoiding back-to-back duplicate challenge types.
- **Keyboard Play:** Keys 1–9 pick an answer and Enter submits or continues, in QGIS and in the HTML game.
- **Fair Questions:** Answer-independent input ranges, no compass pairs on a sector edge, rankings that never start solved.
- **Visual Feedback:** Live canvas highlighting and immediate answer feedback.

---

## 🎓 Class Mode & Student Profiles

- **Student Profiles:** Create and manage profiles with customizable avatars.
- **Session History:** Track individual quiz scores, accuracy percentages, and completion times.
- **CSV Export:** Export all classroom session records to a structured `.csv` report.

---

## 🌐 Serverless Web Export

Export any quest into a single, self-contained HTML file:
- **Offline & Private:** Zero external network calls, zero CDNs, no tracking, works completely offline.
- **Same Rules:** The quest's difficulty, lives and scoring formula carry over; every load asks new questions.
- **Responsive & Dark Mode:** Follows the system theme with a toggle, keyboard play, progress dots, and a personal best per device.

---

## 🚀 Quick Start

1. Open **02GeoQuest** from its QGIS toolbar button.
2. Select your vector layer(s) and readable label/numeric fields.
3. Choose your difficulty level, game modes, and quest rules.
4. Click **Start the quest** to play in QGIS, or **Export standalone HTML** to share.

---

## 🔒 Privacy & Compatibility

- Runs 100% locally inside QGIS (QGIS 3.34 – 4.x).
- Requires no third-party Python packages.
- Dual Qt 5/6 & PyQt 5/6 compatibility.

---

## 📜 License

GPL-3.0-or-later. Copyright © 2026 Yusuf Eminoglu.
