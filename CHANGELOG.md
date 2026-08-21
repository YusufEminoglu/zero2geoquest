# Changelog

## [1.2.0] - 2026-08-21

### Added
- Balanced shuffle-bag question rotation: every selected game mode is presented before a mode repeats, without consecutive repeats at cycle boundaries.
- Quest Pack schema validation for supported modes, difficulty, playability, finite numeric values, WGS84 coordinate bounds, duplicate feature ids, a 5 MB file limit, and a 5,000-record limit.
- Collision-free portable feature ids when exporting mixed QGIS layers.

### Changed
- Quest Pack exports now use schema version 1.2 and atomic file replacement, preventing a failed write from leaving a truncated pack.
- Challenge generation fallback now evaluates every selected mode once and surfaces a useful reason if none can be generated.

### Fixed
- Imported and built-in Quest Packs now start directly from their packaged records; starting a pack no longer reloads and substitutes the currently selected QGIS layer.
- Map Hunt is rejected in portable packs because it requires a live QGIS layer identity.
- Score closeness multipliers are clamped to the documented range, preventing malformed values from inflating a result.

## [1.1.1] - 2026-08-21

### Added
- **Ranking Reordering Controls**: Added Move Up (⬆️) and Move Down (⬇️) buttons for accessible list sorting.
- **Dynamic Rank Badge Indicators**: Added live position medals and indicators (🥇 1st Highest, 🥈 2nd, 🥉 3rd, 🔻 4th Lowest) updating dynamically during drag or button movement.

### Fixed
- **Ranking Submission & Data Mapping**: Stored raw feature labels safely in Qt item UserRole data, preventing string formatting mismatch or empty submissions.

## [1.1.0] - 2026-08-21

### Added
- **Compass Quest Mode (9th Mode)**: Forward geodetic azimuth calculation with 8-point cardinal bearing options (N, NE, E, SE, S, SW, W, NW).
- **Quest Pack Import/Export**: Portable JSON format (`.json`) with validation, metadata, and 3 bundled starter packs:
  - *World Capitals & Metropolises*
  - *European Geography & Landmarks*
  - *Global Megacities*
- **Geographic Intelligence Certificate Exporter**: Beautiful, standalone HTML achievement certificates with printable layouts and dynamic rank assessment titles based on score tiers.
- **Enhanced HTML Web Game Exporter**: Added client-side Compass Quest support, dark theme integration, and live certificate badges.

## [1.0.6] - 2026-08-07

- Added online user manual link (https://yusufeminoglu.github.io/zero2geoquest/) and GitHub repository star call-to-action.

## [1.0.5] - 2026-08-07

- Add floating Save as PDF button to reference manual

## [1.0.4] - 2026-08-07

- Add comprehensive academic reference manual

## [1.0.3] - 2026-08-03

### Changed
- Replace the hardcoded stylesheet and inline colour literals with palette-derived
  tokens so the entire dock — stats cards, silhouette canvas, feedback text, timer
  bar, privacy badge — stays readable under QGIS light, dark and high-contrast
  themes.
- The dock now listens for PaletteChange and re-applies the theme automatically.

### Added
- `dialogs/theme.py` with WCAG contrast-ratio checks, palette-aware colour tokens,
  and `apply_adaptive_theme()` entry point.

## [1.0.2] - 2026-07-20

- Fix: mixed-layer Map Hunt now evaluates clicks and highlights against the question's source layer.
- Fix: skip tied, invalid, or insufficient data before generating value, distance, ranking, and nearest-neighbour questions.
- Fix: enforce one answer per challenge, including true timeout handling and stable zero/negative attribute tolerance.
- Fix: offline HTML export now warns about QGIS-only modes, prevents invalid fallback games, and supports Ranking.

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
