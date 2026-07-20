# -*- coding: utf-8 -*-
"""Polished dock interface for building, playing and sharing GeoQuests."""
from __future__ import annotations

import json
import math
import os
import time
from contextlib import suppress

from qgis.PyQt.QtCore import QPointF, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDockWidget, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout,
    QWidget,
)
from qgis.core import Qgis, QgsFeatureRequest, QgsSettings
from qgis.gui import QgsFieldComboBox, QgsHighlight, QgsMapLayerComboBox

from ..core.exporter import write_html
from ..core.game import GameSession, QuestionFactory
from ..core.layer_data import feature_at_point, records_from_layer

PLUGIN_TITLE = "02GeoQuest — Playable Map Studio"
SETTINGS_KEY = "zero2geoquest/leaderboard"

TEXT = {
    "play": "Play", "build": "Build Quest", "scores": "Scores", "share": "Share",
    "ready": "Choose a layer, set the rules and launch your quest.",
    "start": "Start the quest", "next": "Next challenge", "finish": "Quest complete!",
    "locate": "Map Hunt", "bigger": "Value Duel", "distance": "Distance Guess",
    "silhouette": "Know the Shape", "correct": "Great, correct!", "wrong": "Not this time.",
    "exported": "Web game created", "choose": "Choose a layer and at least one game mode.",
}

QSS = """
#gqRoot { background: #f4f6fb; }
#gqRoot QLabel { color: #17212b; background: transparent; }
#gqRoot QScrollArea, #gqRoot QScrollArea > QWidget > QWidget { background: transparent; border: none; }
#gqRoot QPushButton { color:#263238; background:#fff; border:1px solid #d8dfeb; border-radius:8px; padding:7px 10px; font-weight:600; }
#gqRoot QPushButton:hover { border-color:#6c4cff; background:#f3f0ff; }
#gqRoot QPushButton:checked { color:#fff; background:#6c4cff; border-color:#5438d6; }
#gqRoot QPushButton[class='nav'] { border:none; border-radius:7px; padding:8px 6px; }
#gqRoot QPushButton[class='primary'] { color:#fff; background:#6c4cff; border-color:#5438d6; font-weight:800; padding:10px; }
#gqRoot QPushButton[class='primary']:hover { background:#5a3de7; }
#gqRoot QPushButton[class='answer'] { text-align:left; padding:11px; font-size:10pt; }
#gqRoot QGroupBox { color:#374151; background:#fff; border:1px solid #dce3ed; border-radius:11px; margin-top:11px; padding:12px 8px 8px; font-weight:700; }
#gqRoot QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; }
#gqRoot QComboBox, #gqRoot QSpinBox, #gqRoot QDoubleSpinBox { color:#17212b; background:#fff; border:1px solid #d5dde8; border-radius:6px; padding:5px; }
#gqRoot QListWidget { color:#263238; background:#fff; border:1px solid #dce3ed; border-radius:9px; }
#gqRoot QListWidget::item { padding:7px; border-bottom:1px solid #eef1f5; }
#gqRoot QCheckBox { color:#374151; spacing:7px; }
"""


class SilhouetteCanvas(QWidget):
    """Responsive, antialiased outline preview without web dependencies."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._outline = []
        self.setMinimumHeight(190)

    def set_outline(self, outline) -> None:
        self._outline = outline or []
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor("#4731b7"), 2))
        painter.setBrush(QColor("#6c4cff"))
        if len(self._outline) < 3:
            painter.end()
            return
        xs = [p[0] for p in self._outline]
        ys = [p[1] for p in self._outline]
        width, height = max(xs) - min(xs), max(ys) - min(ys)
        scale = min((self.width() - 32) / max(width, 1e-12),
                    (self.height() - 24) / max(height, 1e-12))
        path = QPainterPath()
        for index, (x, y) in enumerate(self._outline):
            px = (x - min(xs) - width / 2) * scale + self.width() / 2
            py = self.height() / 2 - (y - min(ys) - height / 2) * scale
            if index == 0:
                path.moveTo(QPointF(px, py))
            else:
                path.lineTo(QPointF(px, py))
        path.closeSubpath()
        painter.drawPath(path)
        painter.end()


class GeoQuestDockWidget(QDockWidget):
    locate_requested = pyqtSignal()
    locate_finished = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(PLUGIN_TITLE, parent)
        self.iface = iface
        self.records = []
        self.factory = None
        self.session = None
        self.question = None
        self._question_time = 0.0
        self._highlight = None
        self._answer_buttons = []
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.setMinimumWidth(360)
        self._build_ui()
        self._on_layer_changed(self.layer_combo.currentLayer())
        self._refresh_texts()

    def _t(self, key: str) -> str:
        return TEXT.get(key, key)

    def _build_ui(self) -> None:
        root_widget = QWidget()
        root_widget.setObjectName("gqRoot")
        root_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        root_widget.setStyleSheet(QSS)
        root = QVBoxLayout(root_widget)
        root.setContentsMargins(9, 9, 9, 9)
        root.setSpacing(8)

        header = QHBoxLayout()
        icon = QLabel()
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons", "icon.png")
        if os.path.exists(icon_path):
            icon.setPixmap(QPixmap(icon_path).scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio,
                                                     Qt.TransformationMode.SmoothTransformation))
        header.addWidget(icon)
        title = QLabel("<b style='font-size:14pt'><span style='color:#6c4cff'>02</span>GeoQuest</b><br><span style='color:#718096'>Playable Map Studio</span>")
        header.addWidget(title, 1)
        root.addLayout(header)

        nav = QHBoxLayout()
        self.nav_buttons = []
        for index, key in enumerate(("play", "build", "scores", "share")):
            button = QPushButton()
            button.setProperty("class", "nav")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page=index: self._show_page(page))
            nav.addWidget(button, 1)
            self.nav_buttons.append((key, button))
        root.addLayout(nav)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_play_page())
        self.pages.addWidget(self._build_builder_page())
        self.pages.addWidget(self._build_scores_page())
        self.pages.addWidget(self._build_share_page())
        root.addWidget(self.pages, 1)
        self.setWidget(root_widget)
        self._show_page(1)

    def _scroll(self, page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _build_builder_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.builder_intro = QLabel()
        self.builder_intro.setWordWrap(True)
        layout.addWidget(self.builder_intro)

        source = QGroupBox("1 · Source layer")
        form = QFormLayout(source)
        self.layer_combo = QgsMapLayerComboBox()
        self.layer_combo.setFilters(Qgis.LayerFilter.VectorLayer)
        self.layer_combo.layerChanged.connect(self._on_layer_changed)
        form.addRow("Layer", self.layer_combo)
        self.label_field = QgsFieldComboBox()
        self.value_field = QgsFieldComboBox()
        form.addRow("Name field", self.label_field)
        form.addRow("Numeric / score field", self.value_field)
        layout.addWidget(source)

        modes = QGroupBox("2 · Challenge mix")
        grid = QGridLayout(modes)
        self.mode_checks = {}
        descriptions = {
            "locate": "Click the requested feature on the live map",
            "bigger": "Compare a numeric field or true ground area",
            "distance": "Estimate distances between places",
            "silhouette": "Recognise polygon outlines",
        }
        for index, mode in enumerate(("locate", "bigger", "distance", "silhouette")):
            check = QCheckBox()
            check.setChecked(True)
            hint = QLabel(descriptions[mode])
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#718096;font-size:8pt")
            grid.addWidget(check, index, 0)
            grid.addWidget(hint, index, 1)
            self.mode_checks[mode] = check
        layout.addWidget(modes)

        rules = QGroupBox("3 · Quest rules")
        rule_form = QFormLayout(rules)
        self.quest_title = QComboBox()
        self.quest_title.setEditable(True)
        self.quest_title.addItems(["My Map Quest", "City Explorer", "Data Detective", "Campus Challenge"])
        self.round_count = QSpinBox()
        self.round_count.setRange(3, 50)
        self.round_count.setValue(10)
        self.lives_count = QSpinBox()
        self.lives_count.setRange(1, 10)
        self.lives_count.setValue(3)
        rule_form.addRow("Quest title", self.quest_title)
        rule_form.addRow("Rounds", self.round_count)
        rule_form.addRow("Lives", self.lives_count)
        layout.addWidget(rules)

        self.start_button = QPushButton()
        self.start_button.setProperty("class", "primary")
        self.start_button.clicked.connect(self.start_game)
        layout.addWidget(self.start_button)
        self.builder_status = QLabel()
        self.builder_status.setWordWrap(True)
        self.builder_status.setStyleSheet("color:#718096")
        layout.addWidget(self.builder_status)
        layout.addStretch(1)
        return self._scroll(page)

    def _build_play_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        stats = QHBoxLayout()
        self.score_card = QLabel("★ 0")
        self.round_card = QLabel("1 / 10")
        self.life_card = QLabel("♥ 3")
        for card in (self.score_card, self.round_card, self.life_card):
            card.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card.setStyleSheet("background:#fff;border:1px solid #dce3ed;border-radius:9px;padding:8px;font-weight:800")
            stats.addWidget(card, 1)
        layout.addLayout(stats)
        self.mode_badge = QLabel("02GeoQuest")
        self.mode_badge.setStyleSheet("color:#6c4cff;font-weight:900;text-transform:uppercase")
        layout.addWidget(self.mode_badge)
        self.prompt = QLabel()
        self.prompt.setWordWrap(True)
        self.prompt.setStyleSheet("font-size:15pt;font-weight:800")
        layout.addWidget(self.prompt)
        self.silhouette = SilhouetteCanvas()
        self.silhouette.hide()
        layout.addWidget(self.silhouette)
        self.answer_area = QWidget()
        self.answer_layout = QGridLayout(self.answer_area)
        self.answer_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.answer_area)
        self.distance_widget = QWidget()
        distance_layout = QHBoxLayout(self.distance_widget)
        self.distance_guess = QDoubleSpinBox()
        self.distance_guess.setRange(0, 50000)
        self.distance_guess.setSuffix(" km")
        self.distance_guess.setDecimals(1)
        distance_layout.addWidget(self.distance_guess, 1)
        submit = QPushButton("OK")
        submit.clicked.connect(self._submit_distance)
        distance_layout.addWidget(submit)
        self.distance_widget.hide()
        layout.addWidget(self.distance_widget)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setMinimumHeight(48)
        layout.addWidget(self.feedback)
        self.next_button = QPushButton()
        self.next_button.setProperty("class", "primary")
        self.next_button.clicked.connect(self._next_question)
        self.next_button.hide()
        layout.addWidget(self.next_button)
        layout.addStretch(1)
        return page

    def _build_scores_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        headline = QLabel("<b style='font-size:15pt'>Hall of fame</b><br><span style='color:#718096'>Best quests on this computer</span>")
        layout.addWidget(headline)
        self.score_list = QListWidget()
        layout.addWidget(self.score_list, 1)
        clear = QPushButton("Clear leaderboard")
        clear.clicked.connect(self._clear_scores)
        layout.addWidget(clear)
        self._refresh_scores()
        return page

    def _build_share_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        headline = QLabel("<b style='font-size:15pt'>Take the quest anywhere</b>")
        layout.addWidget(headline)
        copy = QLabel("Export a single HTML file with the questions, design and game engine inside. It runs offline in any modern browser and sends no data anywhere.")
        copy.setWordWrap(True)
        layout.addWidget(copy)
        box = QGroupBox("Offline web game")
        box_layout = QVBoxLayout(box)
        self.export_summary = QLabel("Build or play a quest first.")
        self.export_summary.setWordWrap(True)
        box_layout.addWidget(self.export_summary)
        self.export_button = QPushButton("Export standalone HTML…")
        self.export_button.setProperty("class", "primary")
        self.export_button.clicked.connect(self._export_html)
        box_layout.addWidget(self.export_button)
        layout.addWidget(box)
        privacy = QLabel("🔒 Privacy by design · local data stays local · no account · no API key · no CDN")
        privacy.setWordWrap(True)
        privacy.setStyleSheet("color:#13795b;background:#e9fbf3;border-radius:8px;padding:9px")
        layout.addWidget(privacy)
        layout.addStretch(1)
        return page

    def _refresh_texts(self) -> None:
        for key, button in self.nav_buttons:
            button.setText(self._t(key))
        for key, check in self.mode_checks.items():
            check.setText(self._t(key))
        self.builder_intro.setText(self._t("ready"))
        self.start_button.setText("▶  " + self._t("start"))
        self.next_button.setText(self._t("next") + "  →")
        if self.session is None:
            self.prompt.setText(self._t("ready"))

    def _show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for number, (_, button) in enumerate(self.nav_buttons):
            button.setChecked(number == index)

    def _on_layer_changed(self, layer) -> None:
        self.label_field.setLayer(layer)
        self.value_field.setLayer(layer)
        if layer is not None:
            self.quest_title.setEditText(f"{layer.name()} Quest")
            self.builder_status.setText(f"{layer.featureCount():,} features detected")

    def _selected_modes(self) -> list[str]:
        return [mode for mode, check in self.mode_checks.items() if check.isChecked()]

    def _prepare_records(self) -> bool:
        layer = self.layer_combo.currentLayer()
        modes = self._selected_modes()
        if layer is None or not modes:
            self.builder_status.setText(self._t("choose"))
            return False
        try:
            self.records = records_from_layer(layer, self.label_field.currentField(),
                                              self.value_field.currentField())
        except Exception as exc:
            self.builder_status.setText(str(exc))
            return False
        if len(self.records) < 4:
            self.builder_status.setText("At least four non-empty features are required.")
            return False
        if "silhouette" in modes and sum(bool(r["outline"]) for r in self.records) < 4:
            self.mode_checks["silhouette"].setChecked(False)
            modes.remove("silhouette")
            self.builder_status.setText("Silhouette mode was skipped: four polygons are required.")
        if not modes:
            return False
        self.factory = QuestionFactory(self.records, seed=time.time_ns())
        self.export_summary.setText(
            f"{self.quest_title.currentText()} · {len(self.records)} features · "
            f"{self.round_count.value()} rounds")
        return True

    def start_game(self) -> None:
        if not self._prepare_records():
            return
        self.session = GameSession(self._selected_modes(), self.round_count.value(),
                                   self.lives_count.value(), seed=time.time_ns())
        self._show_page(0)
        self._next_question()

    def _clear_answers(self) -> None:
        for button in self._answer_buttons:
            button.deleteLater()
        self._answer_buttons.clear()
        self.silhouette.hide()
        self.distance_widget.hide()
        self.distance_widget.setEnabled(True)
        self.next_button.hide()
        self.feedback.clear()
        self._clear_highlight()

    def _next_question(self) -> None:
        if self.session is None or self.factory is None:
            self._show_page(1)
            return
        if self.session.finished:
            self._finish_game()
            return
        self._clear_answers()
        mode = self.session.next_mode()
        try:
            self.question = self.factory.make(mode)
        except ValueError:
            fallback = next((item for item in self.session.modes if item != mode), None)
            if fallback is None:
                self._finish_game()
                return
            self.question = self.factory.make(fallback)
        self._question_time = time.monotonic()
        self.mode_badge.setText(self._t(self.question["mode"]))
        self.prompt.setText(self.question["prompt"])
        self._update_stats()
        mode = self.question["mode"]
        if mode == "locate":
            self.feedback.setText("Click the matching feature on the QGIS map canvas.")
            self.locate_requested.emit()
        elif mode == "distance":
            answer_km = float(self.question["answer"]) / 1000.0
            self.distance_guess.setRange(0, max(10.0, answer_km * 3.0))
            self.distance_guess.setValue(round(answer_km * 0.75, 1))
            self.distance_widget.show()
        else:
            if mode == "silhouette":
                self.silhouette.set_outline(self.question["outline"])
                self.silhouette.show()
            for index, choice in enumerate(self.question["choices"]):
                button = QPushButton(str(choice))
                button.setProperty("class", "answer")
                button.clicked.connect(lambda checked=False, value=choice: self._submit_choice(value))
                self.answer_layout.addWidget(button, index // 2, index % 2)
                self._answer_buttons.append(button)

    def _submit_choice(self, value) -> None:
        answer = str(self.question["answer"])
        detail = answer
        if self.question.get("mode") == "bigger":
            values = self.question.get("values", {})
            detail = " · ".join(f"{name}: {number:,.2f}" for name, number in values.items())
        self._score(str(value) == answer, detail)

    def _submit_distance(self) -> None:
        truth = float(self.question["answer"]) / 1000.0
        guess = float(self.distance_guess.value())
        error = abs(guess - truth) / max(0.001, truth)
        self._score(error <= 0.25, f"{truth:,.1f} km", closeness=max(0.25, 1.0 - error))

    def handle_map_pick(self, point) -> None:
        if not self.question or self.question.get("mode") != "locate" or self.session is None:
            return
        layer = self.layer_combo.currentLayer()
        canvas = self.iface.mapCanvas()
        tolerance = canvas.mapUnitsPerPixel() * 12.0
        layer_point = point
        layer_tolerance = tolerance
        with suppress(Exception):
            settings = canvas.mapSettings()
            layer_point = settings.mapToLayerCoordinates(layer, point)
            edge = settings.mapToLayerCoordinates(
                layer, type(point)(point.x() + tolerance, point.y()))
            layer_tolerance = math.hypot(edge.x() - layer_point.x(), edge.y() - layer_point.y())
        picked = feature_at_point(layer, layer_point, layer_tolerance)
        target = int(self.question["target_fid"])
        self._highlight_feature(target, QColor("#15a66a") if picked == target else QColor("#e94f64"))
        self._score(picked == target, str(self.question["answer"]))

    def _score(self, correct: bool, answer: str, closeness: float = 1.0) -> None:
        if self.session is None:
            return
        elapsed = time.monotonic() - self._question_time
        result = self.session.answer(correct, elapsed=elapsed, closeness=closeness)
        color = "#13795b" if correct else "#c9344f"
        lead = self._t("correct") if correct else self._t("wrong")
        gained = f" +{result['gained']}" if result["gained"] else ""
        self.feedback.setText(f"<span style='color:{color}'><b>{lead}{gained}</b></span><br>{answer}")
        for button in self._answer_buttons:
            button.setEnabled(False)
        self.distance_widget.setEnabled(False)
        self.locate_finished.emit()
        self.next_button.show()
        self.next_button.setText((self._t("finish") if result["finished"] else self._t("next")) + "  →")
        self._update_stats()

    def _update_stats(self) -> None:
        if self.session is None:
            return
        self.score_card.setText(f"★ {self.session.score:,}")
        self.round_card.setText(f"{min(self.session.rounds + 1, self.session.round_limit)} / {self.session.round_limit}")
        self.life_card.setText("♥ " + str(self.session.lives))

    def _finish_game(self) -> None:
        self.locate_finished.emit()
        summary = self.session.summary()
        self._clear_answers()
        self.mode_badge.setText(self._t("finish"))
        self.prompt.setText(f"★ {summary['score']:,}")
        self.feedback.setText(
            f"{summary['correct']} / {summary['rounds']} correct · "
            f"{summary['accuracy']:.0%} accuracy · best streak {summary['best_streak']}")
        self._save_score(summary)
        again = QPushButton("↻  " + self._t("start"))
        again.setProperty("class", "primary")
        again.clicked.connect(self.start_game)
        self.answer_layout.addWidget(again, 0, 0, 1, 2)
        self._answer_buttons.append(again)

    def _highlight_feature(self, fid: int, color: QColor) -> None:
        self._clear_highlight()
        layer = self.layer_combo.currentLayer()
        if layer is None:
            return
        feature = next(layer.getFeatures(QgsFeatureRequest(fid)), None)
        if feature is None:
            return
        self._highlight = QgsHighlight(self.iface.mapCanvas(), feature.geometry(), layer)
        self._highlight.setColor(color)
        self._highlight.setFillColor(QColor(color.red(), color.green(), color.blue(), 70))
        self._highlight.setWidth(3)
        self._highlight.show()

    def _clear_highlight(self) -> None:
        if self._highlight is not None:
            self._highlight.hide()
            self._highlight.deleteLater()
            self._highlight = None

    def _scores(self) -> list[dict]:
        try:
            return json.loads(str(QgsSettings().value(SETTINGS_KEY, "[]")))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    def _save_score(self, summary: dict) -> None:
        scores = self._scores()
        scores.append({"title": self.quest_title.currentText(), **summary})
        scores = sorted(scores, key=lambda item: int(item.get("score", 0)), reverse=True)[:20]
        QgsSettings().setValue(SETTINGS_KEY, json.dumps(scores))
        self._refresh_scores()

    def _refresh_scores(self) -> None:
        if not hasattr(self, "score_list"):
            return
        self.score_list.clear()
        for index, item in enumerate(self._scores(), 1):
            self.score_list.addItem(
                f"{index:02d}   ★ {int(item.get('score', 0)):,}   {item.get('title', 'Quest')}\n"
                f"       {float(item.get('accuracy', 0)):.0%} accuracy · {int(item.get('best_streak', 0))} streak")
        if self.score_list.count() == 0:
            self.score_list.addItem("No completed quests yet — the first crown is waiting.")

    def _clear_scores(self) -> None:
        QgsSettings().setValue(SETTINGS_KEY, "[]")
        self._refresh_scores()

    def _export_html(self) -> None:
        if not self.records and not self._prepare_records():
            self._show_page(1)
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export GeoQuest", self.quest_title.currentText().replace(" ", "_") + ".html",
            "HTML game (*.html)")
        if not filename:
            return
        if not filename.lower().endswith(".html"):
            filename += ".html"
        try:
            write_html(filename, self.quest_title.currentText(), self.records,
                       self._selected_modes(), self.round_count.value(), "en")
        except OSError as exc:
            QMessageBox.critical(self, PLUGIN_TITLE, str(exc))
            return
        self.iface.messageBar().pushSuccess(PLUGIN_TITLE, f"{self._t('exported')}: {filename}")

    def dispose(self) -> None:
        self.locate_finished.emit()
        self._clear_highlight()
