# Changelog

## [1.0.1] - 2026-07-20

- Docs update: comprehensive README for 8 game modes, class mode, jokers, difficulty levels, and HTML web export

## [1.0.0] - 2026-07-20

- Major release: 8 game modes, countdown timer, joker system, difficulty levels, multi-layer support, class mode with profiles, premium HTML export with dark mode

## [0.9.5] - 2026-07-20

- Fix: QgsHighlight.deleteLater() AttributeError on QGIS 3.44 — QgsHighlight is a QGraphicsItem, not QObject; hide() + None release is the correct cleanup

## [0.9.4] - 2026-07-20

- Fix: Polygon vs MultiPolygon dispatch in _first_outline — OSM building layers (single Polygon type) no longer crash Silhouette mode

## [0.9.3] - 2026-07-20

- Refactor: English-only UI — remove TR/EN switcher, Turkish TEXT block, and Turkish HTML export strings

## [0.9.2] - 2026-07-20

- Fix: QgsHighlight import from qgis.core to qgis.gui (QGIS 3.44 LTR compatibility)

## [0.9.1] - 2026-07-20

- Replace the icon with a cleaner map-route quest mark

All notable changes to 02GeoQuest are documented here.

## [0.9.0] - 2026-07-20

### Added

- Complete dock-based quest builder and live play experience.
- Map Hunt, Value Duel, Distance Guess and Know the Shape modes.
- Speed bonuses, streak multipliers, configurable lives and round limits.
- Persistent, local top-20 leaderboard.
- Turkish and English interface switcher.
- Standalone offline HTML game export with responsive mobile layout.
- QGIS 3.34 and QGIS 4 / Qt 6 compatible plugin lifecycle.
- Pure-Python unit tests for question generation, scoring and export safety.
