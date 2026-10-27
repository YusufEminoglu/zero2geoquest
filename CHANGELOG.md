# Changelog

## [1.3.1] - 2026-10-27

- Hub listing text rewritten; author Geophilo; university affiliation removed; documentation links use the standard geophilo.com pages (manual.html, guide/); manual HTML no longer ships in the plugin package.

## [1.3.0] - 2026-10-26

### Fixed
- **Ranking and Attribute Guess could be answered only once per session.** Scoring disabled their submit buttons and nothing re-enabled them, so every later round of those modes was lost on the timer.
- **Compass Quest showed no answer buttons in QGIS**, so every Compass round was lost on the timer; the Eliminate joker also skipped it.
- **Distance Guess leaked its answer.** The input started at 0.75 × the true distance (and topped out at 3×), so pressing OK without typing scored as correct on Easy and Medium. The range now comes from the widest pair in the quest and starts at 0; city-scale quests (widest pair under 20 km) are asked in metres, where 1-decimal kilometres could not express the answer. The offline game had the same leak (slider at 1.25 × the answer).
- **The Value Hint joker could hide the answer**: it halved the range around its midpoint. The half-width window is now placed at a random offset that always contains the answer.
- **Eliminate was spent for nothing on Value Duel**, which only has two options; it is now offered only when two wrong options exist.
- **Play again after a Quest Pack** reloaded the selected QGIS layer instead of the pack (the 1.2.0 fix covered only the first launch). Replay and HTML/pack export now keep the pack until a layer is chosen.
- **Value Duel mixed units**: with values on only some features it compared a numeric field against square-metre area. It now uses the numeric field whenever it holds two different values, area otherwise, and the prompt says which (“greater population”, “larger area”).
- **Blind Zoom and Map Hint on point layers** zoomed to a zero-size extent; both now keep at least ~300 m of context, and Map Hint no longer centres the window exactly on the target.
- **Map Hunt with overlapping polygons** returned the first containing feature, so a correct click inside the target could score as wrong. Every feature under the click now counts, found through a spatial filter instead of a full layer scan per click.
- **Starter pack populations mixed definitions** — Paris used its 2.16 M city-proper figure while Tokyo used 37.4 M for the agglomeration, so Paris lost duels it should win. All three packs now use UN DESA *World Urbanization Prospects 2018* (urban agglomeration, 2018); *Global Megacities* is now that source’s ten largest agglomerations, and its description no longer calls population “density”.
- **Quest Packs without integer ids** collapsed every record to one identity, disabling Nearest Neighbour and Blind Zoom decoys; records now get their own internal identity.
- **Silhouettes from geographic layers** were stretched east–west by 1/cos(latitude); the offline game stretched every silhouette to fill its frame.
- **The offline HTML game used a fixed seed**, so each load and each replay asked the same questions. It is now seeded from the browser’s random source, and both engines draw from the generator’s high bits (the low bits of a power-of-two LCG alternate).
- **Attribute Guess tolerance** used `max(1, range)`, which made it far too lenient on ratio data (0–1): ±0.25 on a 0.4-wide range.
- Adding a class profile reset the active profile to none; the certificate now uses the active player’s own best session.
- Large layers were cut to their first 500 table rows; they are now sampled evenly across the whole layer, and the Builder says so.

### Added
- Offline HTML: the quest’s difficulty (timer, choices, tolerance), lives and the plugin’s scoring formula; balanced mode rotation; keyboard play (1–9, Enter); system dark mode; best streak, difficulty and a per-device personal best on the results screen; in-place replay. Only label, value, area, centroid and outline are written to the file.
- Dock: keys 1–9 pick an answer and Enter submits or continues; a **Pick on map** button re-arms Map Hunt after panning; prompts name the chosen field (or its alias).
- Compass Quest skips pairs within 5° of a sector boundary, where neighbouring answers are indistinguishable; Ranking never starts already solved; Nearest Neighbour draws closer decoys on Medium and Hard.
- Quest Packs carry an optional `value_label` and `source`.
- Tests: 21 regression tests for these fixes, and a headless QGIS test (`tests/qgis_dock_e2e.py`, both runtimes) that plays a 36-round quest through the dock’s own widgets in all nine modes.

## [1.2.3] - 2026-09-16

- Redesign plugin icon to high-end 3D tactile brand design with circular teal pedestal, zero margin, and refreshed documentation links.

## [1.2.2] - 2026-09-06

- Migrate repository and documentation URLs to GitLab and Cloudflare Pages.

## [1.2.1] - 2026-08-21

### Fixed
- Removed a literal percent character from `metadata.txt`, allowing QGIS Hub and its interpolation-enabled metadata parser to validate the release package.

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
