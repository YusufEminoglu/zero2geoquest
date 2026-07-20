# 02GeoQuest — Playable Map Studio

Turn a QGIS vector layer into a geography game, teaching activity, data-familiarisation exercise or public-engagement quest.

## What you can play

- **Map Hunt:** find a requested feature directly on the live QGIS canvas.
- **Value Duel:** choose the feature with the larger numeric value or ground area.
- **Distance Guess:** estimate the distance between two named places.
- **Know the Shape:** recognise a polygon from its silhouette.

The quest builder lets you choose the source layer, label and numeric fields, mode mix, round count and lives. Sessions include speed bonuses, streaks, accuracy, lives and a persistent local leaderboard.

## Share without a server

Export the current quest as one self-contained HTML file. The file includes its visual design, question data and game engine; it works offline in a modern browser and uses no CDN, account, API or tracking service.

## Quick start

1. Open **02GeoQuest** from its toolbar button.
2. Choose a vector layer and a field containing readable place names.
3. Optionally choose a numeric field for Value Duel.
4. Select the game modes and rules, then press **Start the quest**.
5. Use **Share** to produce the standalone web edition.

Polygon layers support all four modes. Point and line layers support Map Hunt, Value Duel and Distance Guess. A quest needs at least four non-empty features; web exports include at most the first 500 playable features to remain portable.

## Privacy and dependencies

02GeoQuest runs locally inside QGIS. It sends no layer data over the network and requires no external Python packages. It supports QGIS 3.34–4.x through `qgis.PyQt` and scoped Qt enums.

## License

GPL-3.0-or-later. Copyright © 2026 Yusuf Eminoglu.
