# -*- coding: utf-8 -*-
"""Polished dock interface for building, playing and sharing GeoQuests."""
from __future__ import annotations

import json
import math
import os
import time

from qgis.PyQt.QtCore import QPointF, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDockWidget, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSlider, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)
from qgis.core import (
    Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsFeatureRequest, QgsProject, QgsRectangle, QgsSettings,
)
from qgis.gui import QgsFieldComboBox, QgsHighlight, QgsMapLayerComboBox

from ..core.exporter import HTML_MODES, write_html
from ..core.game import DIFFICULTY, MODES, GameSession, QuestionFactory
from ..core.layer_data import feature_at_point, merge_layers, records_from_layer
from ..core.profiles import AVATARS, ProfileManager

PLUGIN_TITLE = "02GeoQuest — Playable Map Studio"
SETTINGS_KEY = "zero2geoquest/leaderboard"

# ── Mode metadata ──────────────────────────────────────────────────────────────
MODE_LABELS = {
    "locate":     "Map Hunt",
    "bigger":     "Value Duel",
    "distance":   "Distance Guess",
    "silhouette": "Know the Shape",
    "attr_guess": "Attribute Guess ✦",
    "ordering":   "Ranking ✦",
    "nearest":    "Nearest Neighbour",
    "blind_zoom": "Blind Zoom",
}
MODE_DESC = {
    "locate":     "Click the requested feature on the live map",
    "bigger":     "Choose the feature with the larger value or area",
    "distance":   "Estimate the distance between two places",
    "silhouette": "Recognise a polygon from its outline",
    "attr_guess": "Estimate a numeric attribute with a slider  ← needs value field",
    "ordering":   "Rank 3–4 features by value  ← needs value field",
    "nearest":    "Which feature is closest to the reference?",
    "blind_zoom": "Canvas zooms to a feature — name it",
}

QSS = """
#gqRoot { background: #f4f6fb; }
#gqRoot QLabel { color: #17212b; background: transparent; }
#gqRoot QScrollArea, #gqRoot QScrollArea > QWidget > QWidget { background: transparent; border: none; }
#gqRoot QPushButton {
    color:#263238; background:#fff; border:1px solid #d8dfeb;
    border-radius:8px; padding:7px 10px; font-weight:600;
}
#gqRoot QPushButton:hover { border-color:#6c4cff; background:#f3f0ff; }
#gqRoot QPushButton:checked { color:#fff; background:#6c4cff; border-color:#5438d6; }
#gqRoot QPushButton[class='nav'] { border:none; border-radius:7px; padding:8px 6px; }
#gqRoot QPushButton[class='primary'] {
    color:#fff; background:#6c4cff; border-color:#5438d6;
    font-weight:800; padding:10px;
}
#gqRoot QPushButton[class='primary']:hover { background:#5a3de7; }
#gqRoot QPushButton[class='primary']:disabled { background:#a0a0b0; border-color:#888; }
#gqRoot QPushButton[class='answer'] { text-align:left; padding:11px; font-size:10pt; }
#gqRoot QPushButton[class='joker'] {
    color:#7c3aed; background:#f5f3ff; border:1px solid #c4b5fd;
    border-radius:8px; padding:6px 8px; font-size:9pt; font-weight:700;
}
#gqRoot QPushButton[class='joker']:hover { background:#ede9fe; border-color:#7c3aed; }
#gqRoot QPushButton[class='joker']:disabled { opacity: 0.4; }
#gqRoot QPushButton[class='diff'] { padding:8px 14px; border-radius:8px; }
#gqRoot QGroupBox {
    color:#374151; background:#fff; border:1px solid #dce3ed;
    border-radius:11px; margin-top:11px; padding:12px 8px 8px; font-weight:700;
}
#gqRoot QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; }
#gqRoot QComboBox, #gqRoot QSpinBox, #gqRoot QDoubleSpinBox {
    color:#17212b; background:#fff; border:1px solid #d5dde8; border-radius:6px; padding:5px;
}
#gqRoot QListWidget {
    color:#263238; background:#fff; border:1px solid #dce3ed; border-radius:9px;
}
#gqRoot QListWidget::item { padding:7px; border-bottom:1px solid #eef1f5; }
#gqRoot QCheckBox { color:#374151; spacing:7px; }
#gqRoot QProgressBar {
    border:none; border-radius:4px; background:#e9ecf0;
    text-align:center; font-weight:700; font-size:9pt; color:#374151;
}
#gqRoot QProgressBar::chunk { border-radius:4px; background:#6c4cff; }
#gqRoot QSlider::groove:horizontal {
    border-radius:3px; height:6px; background:#dce3ed;
}
#gqRoot QSlider::handle:horizontal {
    background:#6c4cff; border-radius:8px;
    width:16px; height:16px; margin:-5px 0;
}
#gqRoot QSlider::sub-page:horizontal { background:#6c4cff; border-radius:3px; }
"""


# ── Silhouette preview widget ─────────────────────────────────────────────────

class SilhouetteCanvas(QWidget):
    """Antialiased polygon outline preview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._outline: list = []
        self.setMinimumHeight(200)

    def set_outline(self, outline) -> None:
        self._outline = outline or []
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#f8f7ff"))
        painter.setPen(QPen(QColor("#4731b7"), 2))
        painter.setBrush(QColor("#6c4cff"))
        if len(self._outline) < 3:
            painter.end()
            return
        xs = [p[0] for p in self._outline]
        ys = [p[1] for p in self._outline]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        scale = min((self.width() - 40) / max(w, 1e-12),
                    (self.height() - 30) / max(h, 1e-12))
        path = QPainterPath()
        for i, (x, y) in enumerate(self._outline):
            px = (x - min(xs) - w / 2) * scale + self.width() / 2
            py = self.height() / 2 - (y - min(ys) - h / 2) * scale
            if i == 0:
                path.moveTo(QPointF(px, py))
            else:
                path.lineTo(QPointF(px, py))
        path.closeSubpath()
        painter.drawPath(path)
        painter.end()


# ── Main dock widget ──────────────────────────────────────────────────────────

class GeoQuestDockWidget(QDockWidget):
    locate_requested = pyqtSignal()
    locate_finished = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(PLUGIN_TITLE, parent)
        self.iface = iface
        self.canvas = iface.mapCanvas()

        # Game state
        self.records: list[dict] = []
        self.factory: QuestionFactory | None = None
        self.session: GameSession | None = None
        self.question: dict | None = None
        self._question_time = 0.0
        self._answer_buttons: list[QPushButton] = []
        self._highlight: QgsHighlight | None = None
        self._saved_extent = None  # restored after blind_zoom

        self._active_modes: list[str] = []
        # Difficulty
        self._difficulty = "Medium"

        # Countdown timer
        self._countdown_ms = 0
        self._countdown_max_ms = 30_000
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(100)
        self._countdown_timer.timeout.connect(self._tick_timer)

        # Profile manager
        self._profiles = ProfileManager()
        self._active_profile: tuple[str, str] | None = None  # (name, avatar)

        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.setMinimumWidth(380)
        self._build_ui()
        self._on_layer_changed(self.layer_combo.currentLayer())
        self._refresh_texts()

    # ── Text helpers ──────────────────────────────────────────────────────────

    def _t(self, key: str) -> str:
        return {
            "play": "Play", "build": "Build Quest", "scores": "Scores", "share": "Share",
            "ready": "Choose a layer, set the rules and launch your quest.",
            "start": "Start the quest", "next": "Next challenge", "finish": "Quest complete!",
            "locate": "Map Hunt", "bigger": "Value Duel", "distance": "Distance Guess",
            "silhouette": "Know the Shape", "attr_guess": "Attribute Guess",
            "ordering": "Ranking", "nearest": "Nearest Neighbour", "blind_zoom": "Blind Zoom",
            "correct": "Great, correct!", "wrong": "Not this time.",
            "exported": "Web game created",
            "choose": "Choose a layer and at least one game mode.",
        }.get(key, key)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root_widget = QWidget()
        root_widget.setObjectName("gqRoot")
        root_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        root_widget.setStyleSheet(QSS)
        root = QVBoxLayout(root_widget)
        root.setContentsMargins(9, 9, 9, 9)
        root.setSpacing(8)

        # Header
        header = QHBoxLayout()
        icon_lbl = QLabel()
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons", "icon.png")
        if os.path.exists(icon_path):
            icon_lbl.setPixmap(QPixmap(icon_path).scaled(
                28, 28, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        header.addWidget(icon_lbl)
        title = QLabel("<b style='font-size:14pt'><span style='color:#6c4cff'>02</span>"
                       "GeoQuest</b><br><span style='color:#718096'>Playable Map Studio</span>")
        header.addWidget(title, 1)
        root.addLayout(header)

        # Navigation
        nav = QHBoxLayout()
        self.nav_buttons: list[tuple[str, QPushButton]] = []
        for idx, key in enumerate(("play", "build", "scores", "share")):
            btn = QPushButton()
            btn.setProperty("class", "nav")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, p=idx: self._show_page(p))
            nav.addWidget(btn, 1)
            self.nav_buttons.append((key, btn))
        root.addLayout(nav)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_play_page())
        self.pages.addWidget(self._build_builder_page())
        self.pages.addWidget(self._build_scores_page())
        self.pages.addWidget(self._build_share_page())
        root.addWidget(self.pages, 1)
        self.setWidget(root_widget)
        self._show_page(1)

    # ── Play page ─────────────────────────────────────────────────────────────

    def _build_play_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(6)

        # Stats row
        stats = QHBoxLayout()
        self.score_card = QLabel("★ 0")
        self.round_card = QLabel("1 / 10")
        self.life_card = QLabel("♥ 3")
        self.streak_card = QLabel("")
        for card in (self.score_card, self.round_card, self.life_card, self.streak_card):
            card.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card.setStyleSheet("background:#fff;border:1px solid #dce3ed;border-radius:9px;"
                               "padding:6px;font-weight:800;font-size:10pt")
            stats.addWidget(card, 1)
        layout.addLayout(stats)

        # Timer bar
        self.timer_bar = QProgressBar()
        self.timer_bar.setRange(0, 1000)
        self.timer_bar.setValue(1000)
        self.timer_bar.setFormat("")
        self.timer_bar.setFixedHeight(10)
        layout.addWidget(self.timer_bar)

        # Mode badge + prompt
        self.mode_badge = QLabel("02GeoQuest")
        self.mode_badge.setStyleSheet("color:#6c4cff;font-weight:900;text-transform:uppercase;font-size:9pt")
        layout.addWidget(self.mode_badge)
        self.prompt = QLabel()
        self.prompt.setWordWrap(True)
        self.prompt.setStyleSheet("font-size:13pt;font-weight:800")
        layout.addWidget(self.prompt)

        # Silhouette
        self.silhouette = SilhouetteCanvas()
        self.silhouette.hide()
        layout.addWidget(self.silhouette)

        # ── Answer area: stacked inputs ───────────────────────────────────────
        self.input_stack = QStackedWidget()

        # Page 0: Multiple-choice buttons
        choice_page = QWidget()
        self.answer_layout = QGridLayout(choice_page)
        self.answer_layout.setContentsMargins(0, 0, 0, 0)
        self.input_stack.addWidget(choice_page)

        # Page 1: Ordering (drag-and-drop list)
        ordering_page = QWidget()
        ordering_v = QVBoxLayout(ordering_page)
        ordering_v.setContentsMargins(0, 0, 0, 0)
        hint = QLabel("Drag items to rank from highest ↓ to lowest:")
        hint.setStyleSheet("color:#6b7280;font-size:9pt")
        ordering_v.addWidget(hint)
        self.ordering_list = QListWidget()
        self.ordering_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.ordering_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.ordering_list.setMinimumHeight(120)
        ordering_v.addWidget(self.ordering_list, 1)
        self.ordering_submit = QPushButton("Submit ranking")
        self.ordering_submit.setProperty("class", "primary")
        self.ordering_submit.clicked.connect(self._submit_ordering)
        ordering_v.addWidget(self.ordering_submit)
        self.input_stack.addWidget(ordering_page)

        # Page 2: Distance guess
        dist_page = QWidget()
        dist_v = QHBoxLayout(dist_page)
        dist_v.setContentsMargins(0, 0, 0, 0)
        self.distance_guess = QDoubleSpinBox()
        self.distance_guess.setRange(0, 50_000)
        self.distance_guess.setSuffix(" km")
        self.distance_guess.setDecimals(1)
        dist_v.addWidget(self.distance_guess, 1)
        submit_dist = QPushButton("OK")
        submit_dist.clicked.connect(self._submit_distance)
        dist_v.addWidget(submit_dist)
        self.input_stack.addWidget(dist_page)

        # Page 3: Attribute guess slider
        attr_page = QWidget()
        attr_v = QVBoxLayout(attr_page)
        attr_v.setContentsMargins(0, 0, 0, 0)
        self.attr_value_label = QLabel("0")
        self.attr_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.attr_value_label.setStyleSheet("font-size:22pt;font-weight:900;color:#6c4cff")
        attr_v.addWidget(self.attr_value_label)
        self._attr_slider_min = 0.0
        self._attr_slider_scale = 1.0
        self.attr_slider = QSlider(Qt.Orientation.Horizontal)
        self.attr_slider.setRange(0, 200)
        self.attr_slider.valueChanged.connect(self._update_attr_label)
        attr_v.addWidget(self.attr_slider)
        self.attr_range_hint = QLabel("")
        self.attr_range_hint.setStyleSheet("color:#9ca3af;font-size:8pt")
        self.attr_range_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        attr_v.addWidget(self.attr_range_hint)
        self.attr_submit = QPushButton("Submit guess")
        self.attr_submit.setProperty("class", "primary")
        self.attr_submit.clicked.connect(self._submit_attr_guess)
        attr_v.addWidget(self.attr_submit)
        self.input_stack.addWidget(attr_page)

        layout.addWidget(self.input_stack)

        # ── Joker buttons ─────────────────────────────────────────────────────
        joker_row = QHBoxLayout()
        joker_label = QLabel("🃏 Jokers:")
        joker_label.setStyleSheet("font-weight:700;font-size:9pt;color:#7c3aed")
        joker_row.addWidget(joker_label)
        self.joker_eliminate = QPushButton("✂️ Eliminate")
        self.joker_eliminate.setProperty("class", "joker")
        self.joker_eliminate.setToolTip("Remove 2 wrong choices")
        self.joker_eliminate.clicked.connect(self._use_eliminate_joker)
        self.joker_value = QPushButton("📊 Value Hint")
        self.joker_value.setProperty("class", "joker")
        self.joker_value.setToolTip("Narrow the slider range by 50%")
        self.joker_value.clicked.connect(self._use_value_joker)
        self.joker_map = QPushButton("🗺️ Map Hint")
        self.joker_map.setProperty("class", "joker")
        self.joker_map.setToolTip("Zoom canvas to a hint area")
        self.joker_map.clicked.connect(self._use_map_joker)
        for jbtn in (self.joker_eliminate, self.joker_value, self.joker_map):
            joker_row.addWidget(jbtn)
            jbtn.setEnabled(False)
        layout.addLayout(joker_row)

        # Feedback + next button
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setMinimumHeight(44)
        layout.addWidget(self.feedback)
        self.next_button = QPushButton()
        self.next_button.setProperty("class", "primary")
        self.next_button.clicked.connect(self._next_question)
        self.next_button.hide()
        layout.addWidget(self.next_button)
        layout.addStretch(1)
        return page

    # ── Builder page ──────────────────────────────────────────────────────────

    def _build_builder_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.builder_intro = QLabel()
        self.builder_intro.setWordWrap(True)
        layout.addWidget(self.builder_intro)

        # Source layer A
        source_a = QGroupBox("1 · Source layer")
        form_a = QFormLayout(source_a)
        self.layer_combo = QgsMapLayerComboBox()
        self.layer_combo.setFilters(Qgis.LayerFilter.VectorLayer)
        self.layer_combo.layerChanged.connect(self._on_layer_changed)
        form_a.addRow("Layer", self.layer_combo)
        self.label_field = QgsFieldComboBox()
        self.value_field = QgsFieldComboBox()
        self.value_field.setAllowEmptyFieldName(True)
        form_a.addRow("Name field", self.label_field)
        form_a.addRow("Numeric field", self.value_field)
        layout.addWidget(source_a)

        # Second layer (optional)
        source_b = QGroupBox("2 · Second layer (optional — mix two layers)")
        source_b_v = QVBoxLayout(source_b)
        self.use_second_layer = QCheckBox("Enable second layer")
        self.use_second_layer.toggled.connect(self._toggle_second_layer)
        source_b_v.addWidget(self.use_second_layer)
        self.second_layer_widget = QWidget()
        form_b = QFormLayout(self.second_layer_widget)
        form_b.setContentsMargins(0, 0, 0, 0)
        self.layer_combo_b = QgsMapLayerComboBox()
        self.layer_combo_b.setFilters(Qgis.LayerFilter.VectorLayer)
        self.label_field_b = QgsFieldComboBox()
        self.value_field_b = QgsFieldComboBox()
        self.value_field_b.setAllowEmptyFieldName(True)
        self.layer_combo_b.layerChanged.connect(lambda lyr: (
            self.label_field_b.setLayer(lyr), self.value_field_b.setLayer(lyr)))
        form_b.addRow("Layer B", self.layer_combo_b)
        form_b.addRow("Name field B", self.label_field_b)
        form_b.addRow("Numeric field B", self.value_field_b)
        source_b_v.addWidget(self.second_layer_widget)
        self.second_layer_widget.hide()
        layout.addWidget(source_b)

        # Game modes
        modes_box = QGroupBox("3 · Challenge mix")
        modes_grid = QGridLayout(modes_box)
        self.mode_checks: dict[str, QCheckBox] = {}
        for idx, mode in enumerate(MODES):
            check = QCheckBox(MODE_LABELS[mode])
            check.setChecked(mode in ("locate", "bigger", "distance", "silhouette"))
            hint = QLabel(MODE_DESC[mode])
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#718096;font-size:8pt")
            modes_grid.addWidget(check, idx, 0)
            modes_grid.addWidget(hint, idx, 1)
            self.mode_checks[mode] = check
        layout.addWidget(modes_box)

        # Difficulty
        diff_box = QGroupBox("4 · Difficulty")
        diff_h = QHBoxLayout(diff_box)
        self.diff_buttons: dict[str, QPushButton] = {}
        for label, color in (("Easy", "#22c55e"), ("Medium", "#6c4cff"), ("Hard", "#ef4444")):
            btn = QPushButton(label)
            btn.setProperty("class", "diff")
            btn.setCheckable(True)
            btn.setChecked(label == "Medium")
            btn.setStyleSheet(
                f"QPushButton:checked {{background:{color};color:#fff;border-color:{color};}}")
            btn.clicked.connect(lambda _=False, d=label: self._set_difficulty(d))
            diff_h.addWidget(btn, 1)
            self.diff_buttons[label] = btn
        diff_h.addSpacing(8)
        timer_note = QLabel("Timer: 30s")
        timer_note.setStyleSheet("color:#718096;font-size:8pt")
        self.timer_note_label = timer_note
        diff_h.addWidget(timer_note)
        layout.addWidget(diff_box)

        # Quest rules
        rules = QGroupBox("5 · Quest rules")
        rule_form = QFormLayout(rules)
        self.quest_title = QComboBox()
        self.quest_title.setEditable(True)
        self.quest_title.addItems(["My Map Quest", "City Explorer", "Data Detective",
                                    "Campus Challenge", "Heritage Hunt"])
        self.round_count = QSpinBox()
        self.round_count.setRange(3, 60)
        self.round_count.setValue(10)
        self.lives_count = QSpinBox()
        self.lives_count.setRange(1, 10)
        self.lives_count.setValue(3)
        self.joker_count = QSpinBox()
        self.joker_count.setRange(0, 9)
        self.joker_count.setValue(3)
        self.joker_count.setToolTip("Total joker uses available per quest")
        rule_form.addRow("Quest title", self.quest_title)
        rule_form.addRow("Rounds", self.round_count)
        rule_form.addRow("Lives", self.lives_count)
        rule_form.addRow("Jokers", self.joker_count)
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

    # ── Scores page ───────────────────────────────────────────────────────────

    def _build_scores_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        headline = QLabel("<b style='font-size:15pt'>Hall of fame</b><br>"
                          "<span style='color:#718096'>Best quests on this device</span>")
        layout.addWidget(headline)
        self.score_list = QListWidget()
        layout.addWidget(self.score_list, 1)
        btns = QHBoxLayout()
        clear = QPushButton("Clear leaderboard")
        clear.clicked.connect(self._clear_scores)
        btns.addWidget(clear)
        layout.addLayout(btns)
        self._refresh_scores()
        return page

    # ── Share / class-mode page ───────────────────────────────────────────────

    def _build_share_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        # Export section
        export_box = QGroupBox("Offline web game")
        export_v = QVBoxLayout(export_box)
        self.export_summary = QLabel("Build or play a quest first.")
        self.export_summary.setWordWrap(True)
        export_v.addWidget(self.export_summary)
        self.export_button = QPushButton("Export standalone HTML…")
        self.export_button.setProperty("class", "primary")
        self.export_button.clicked.connect(self._export_html)
        export_v.addWidget(self.export_button)
        layout.addWidget(export_box)

        privacy = QLabel("🔒 Privacy by design · local data · no account · no CDN")
        privacy.setWordWrap(True)
        privacy.setStyleSheet("color:#13795b;background:#e9fbf3;border-radius:8px;padding:9px")
        layout.addWidget(privacy)

        # Class mode
        class_box = QGroupBox("Class mode — student profiles")
        class_v = QVBoxLayout(class_box)

        profile_row = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(130)
        profile_row.addWidget(QLabel("Active profile:"))
        profile_row.addWidget(self.profile_combo, 1)
        self.avatar_combo = QComboBox()
        for av in AVATARS:
            self.avatar_combo.addItem(av)
        profile_row.addWidget(self.avatar_combo)
        class_v.addLayout(profile_row)

        new_profile_row = QHBoxLayout()
        self.new_profile_name = QComboBox()
        self.new_profile_name.setEditable(True)
        self.new_profile_name.setPlaceholderText("New student name…")
        new_profile_row.addWidget(self.new_profile_name, 1)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_profile)
        rm_btn = QPushButton("Remove")
        rm_btn.clicked.connect(self._remove_profile)
        new_profile_row.addWidget(add_btn)
        new_profile_row.addWidget(rm_btn)
        class_v.addLayout(new_profile_row)

        class_v.addWidget(QLabel("Session history:"))
        self.session_list = QListWidget()
        self.session_list.setMaximumHeight(120)
        class_v.addWidget(self.session_list)

        csv_row = QHBoxLayout()
        export_csv_btn = QPushButton("Export all sessions to CSV…")
        export_csv_btn.clicked.connect(self._export_csv)
        clear_sessions_btn = QPushButton("Clear sessions")
        clear_sessions_btn.clicked.connect(self._clear_sessions)
        csv_row.addWidget(export_csv_btn, 1)
        csv_row.addWidget(clear_sessions_btn)
        class_v.addLayout(csv_row)

        layout.addWidget(class_box)
        layout.addStretch(1)

        self._refresh_profiles()
        self._refresh_sessions()
        return self._scroll(page)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _scroll(self, page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for num, (_, btn) in enumerate(self.nav_buttons):
            btn.setChecked(num == index)

    def _refresh_texts(self) -> None:
        for key, btn in self.nav_buttons:
            btn.setText(self._t(key))
        self.builder_intro.setText(self._t("ready"))
        self.start_button.setText("▶  " + self._t("start"))
        self.next_button.setText(self._t("next") + "  →")
        if self.session is None:
            self.prompt.setText(self._t("ready"))

    def _toggle_second_layer(self, checked: bool) -> None:
        self.second_layer_widget.setVisible(checked)

    def _set_difficulty(self, diff: str) -> None:
        self._difficulty = diff
        for name, btn in self.diff_buttons.items():
            btn.setChecked(name == diff)
        secs = DIFFICULTY.get(diff, DIFFICULTY["Medium"])["timer"]
        self.timer_note_label.setText(f"Timer: {secs}s")

    def _on_layer_changed(self, layer) -> None:
        self.label_field.setLayer(layer)
        self.value_field.setLayer(layer)
        if layer is not None:
            self.quest_title.setEditText(f"{layer.name()} Quest")
            self.builder_status.setText(f"{layer.featureCount():,} features detected")

    def _selected_modes(self) -> list[str]:
        return [m for m, cb in self.mode_checks.items() if cb.isChecked()]

    def _layer_for_id(self, layer_id: str | None):
        """Return the configured source layer matching a record layer id."""
        candidates = (self.layer_combo.currentLayer(), self.layer_combo_b.currentLayer())
        for layer in candidates:
            if layer is not None and layer.id() == layer_id:
                return layer
        return None


    # ── Game lifecycle ────────────────────────────────────────────────────────

    def _prepare_records(self) -> bool:
        layer_a = self.layer_combo.currentLayer()
        modes = self._selected_modes()
        if layer_a is None or not modes:
            self.builder_status.setText(self._t("choose"))
            return False
        label_a = self.label_field.currentField()
        value_a = self.value_field.currentField()
        try:
            if self.use_second_layer.isChecked():
                layer_b = self.layer_combo_b.currentLayer()
                if layer_b is not None:
                    self.records = merge_layers(
                        layer_a, label_a, value_a,
                        layer_b,
                        self.label_field_b.currentField(),
                        self.value_field_b.currentField())
                else:
                    self.records = records_from_layer(layer_a, label_a, value_a)
            else:
                self.records = records_from_layer(layer_a, label_a, value_a)
        except Exception as exc:
            self.builder_status.setText(str(exc))
            return False

        if len(self.records) < 4:
            self.builder_status.setText("At least four non-empty features are required.")
            return False

        # Auto-filter modes that need conditions we can't meet
        has_value = bool(value_a) or (
            self.use_second_layer.isChecked() and bool(self.value_field_b.currentField()))
        if not has_value:
            removed = [m for m in modes if m in ("attr_guess", "ordering")]
            if removed:
                modes = [m for m in modes if m not in ("attr_guess", "ordering")]
                self.builder_status.setText(
                    "Attribute Guess and Ordering need a numeric field — skipped.")
                if not modes:
                    return False

        if "silhouette" in modes:
            poly_count = sum(1 for r in self.records if r.get("outline"))
            if poly_count < 4:
                modes.remove("silhouette")
                self.builder_status.setText("Silhouette skipped: need 4+ polygon features.")

        if not modes:
            return False

        self.factory = QuestionFactory(self.records, seed=time.time_ns())
        self._active_modes = self.factory.available_modes(modes)
        if not self._active_modes:
            self.builder_status.setText(
                "Selected modes need more suitable or more varied feature data.")
            return False
        if len(self._active_modes) != len(modes):
            skipped = [MODE_LABELS[mode] for mode in modes if mode not in self._active_modes]
            self.builder_status.setText("Skipped unavailable modes: " + ", ".join(skipped))

        self.export_summary.setText(
            f"{self.quest_title.currentText()} · {len(self.records)} features · "
            f"{self.round_count.value()} rounds · {self._difficulty}")
        return True

    def start_game(self) -> None:
        if not self._prepare_records():
            return
        modes = self._active_modes
        self.session = GameSession(
            modes, self.round_count.value(), self.lives_count.value(),
            seed=time.time_ns(), difficulty=self._difficulty,
            joker_count=self.joker_count.value())
        self._show_page(0)
        self._next_question()

    def _clear_answers(self) -> None:
        for btn in self._answer_buttons:
            btn.deleteLater()
        self._answer_buttons.clear()
        # Clear choice grid
        while self.answer_layout.count():
            item = self.answer_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self.silhouette.hide()
        self.ordering_list.clear()
        self.input_stack.setCurrentIndex(0)
        for jbtn in (self.joker_eliminate, self.joker_value, self.joker_map):
            jbtn.setEnabled(False)
        self.next_button.hide()
        self.feedback.clear()
        self._clear_highlight()
        self._restore_extent()
        self._countdown_timer.stop()
        self.timer_bar.setValue(self.timer_bar.maximum())
        self.timer_bar.setStyleSheet("")

    def _next_question(self) -> None:
        if self.session is None or self.factory is None:
            self._show_page(1)
            return
        if self.session.finished:
            self._finish_game()
            return
        self._clear_answers()
        mode = self.session.next_mode()
        for _ in range(len(self.session.modes)):
            try:
                self.question = self.factory.make(mode, self._difficulty)
                break
            except ValueError:
                other_modes = [m for m in self.session.modes if m != mode]
                if not other_modes:
                    self._finish_game()
                    return
                mode = self.session.rng.choice(other_modes)
        else:
            self._finish_game()
            return

        self._question_time = time.monotonic()
        self.mode_badge.setText(MODE_LABELS.get(self.question["mode"], self.question["mode"]))
        self.prompt.setText(self.question["prompt"])
        self._show_question_input()
        self._update_joker_buttons()
        self._start_countdown()

    def _show_question_input(self) -> None:  # noqa: C901
        mode = self.question["mode"]
        if mode == "locate":
            self.input_stack.setCurrentIndex(0)
            self.feedback.setText("Click the matching feature on the QGIS map.")
            self.feedback.setStyleSheet("color:#6c4cff;padding:4px")
            self.locate_requested.emit()

        elif mode in ("bigger", "silhouette", "nearest", "blind_zoom"):
            self._show_choices(self.question["choices"])
            if mode == "silhouette":
                self.silhouette.set_outline(self.question["outline"])
                self.silhouette.show()
            elif mode == "blind_zoom":
                self._zoom_to_question_area()

        elif mode == "distance":
            self.input_stack.setCurrentIndex(2)
            answer_km = float(self.question["answer"]) / 1000.0
            self.distance_guess.setRange(0, max(10.0, answer_km * 3.0))
            self.distance_guess.setValue(round(answer_km * 0.75, 1))

        elif mode == "attr_guess":
            self.input_stack.setCurrentIndex(3)
            self._setup_attr_slider(self.question)

        elif mode == "ordering":
            self.input_stack.setCurrentIndex(1)
            self.ordering_list.clear()
            for item_data in self.question["items"]:
                self.ordering_list.addItem(item_data["label"])

    def _show_choices(self, choices: list) -> None:
        self.input_stack.setCurrentIndex(0)
        for idx, choice in enumerate(choices):
            btn = QPushButton(str(choice))
            btn.setProperty("class", "answer")
            btn.clicked.connect(lambda _=False, v=choice: self._submit_choice(v))
            self.answer_layout.addWidget(btn, idx // 2, idx % 2)
            self._answer_buttons.append(btn)

    def _setup_attr_slider(self, q: dict) -> None:
        min_v = float(q["min_val"])
        max_v = float(q["max_val"])
        rng = max_v - min_v or 1.0
        self._attr_slider_min = min_v
        self._attr_slider_scale = rng / 200.0
        self.attr_slider.setValue(100)  # start at midpoint
        self.attr_range_hint.setText(
            f"Range: {min_v:,.2f} – {max_v:,.2f}")
        self._update_attr_label(100)

    def _update_attr_label(self, value: int) -> None:
        actual = self._attr_slider_min + value * self._attr_slider_scale
        self.attr_value_label.setText(f"{actual:,.2f}")

    # ── Canvas / zoom ─────────────────────────────────────────────────────────

    def _zoom_to_question_area(self) -> None:
        bbox = self.question.get("bbox_wgs84", [])
        if not bbox or len(bbox) < 4:
            return
        self._saved_extent = self.canvas.extent()
        try:
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            canvas_crs = self.canvas.mapSettings().destinationCrs()
            tr = QgsCoordinateTransform(wgs84, canvas_crs, QgsProject.instance())
            xmin, ymin, xmax, ymax = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
            # Add 20% buffer
            dx = (xmax - xmin) * 0.20
            dy = (ymax - ymin) * 0.20
            sw = tr.transform(xmin - dx, ymin - dy)
            ne = tr.transform(xmax + dx, ymax + dy)
            self.canvas.setExtent(QgsRectangle(sw.x(), sw.y(), ne.x(), ne.y()))
            self.canvas.refresh()
        except Exception as exc:
            _ = exc

    def _restore_extent(self) -> None:
        if self._saved_extent is not None:
            try:
                self.canvas.setExtent(self._saved_extent)
                self.canvas.refresh()
            except Exception as exc:
                _ = exc
            self._saved_extent = None

    # ── Countdown timer ───────────────────────────────────────────────────────

    def _start_countdown(self) -> None:
        secs = self.session.timer_seconds if self.session else 30
        self._countdown_ms = secs * 1000
        self._countdown_max_ms = secs * 1000
        self.timer_bar.setRange(0, self._countdown_max_ms)
        self.timer_bar.setValue(self._countdown_max_ms)
        self._countdown_timer.start()

    def _tick_timer(self) -> None:
        self._countdown_ms = max(0, self._countdown_ms - 100)
        self.timer_bar.setValue(self._countdown_ms)
        pct = self._countdown_ms / max(1, self._countdown_max_ms)
        if pct > 0.5:
            chunk_color = "#6c4cff"
        elif pct > 0.25:
            chunk_color = "#f59e0b"
        else:
            chunk_color = "#ef4444"
        self.timer_bar.setStyleSheet(
            f"QProgressBar::chunk {{background:{chunk_color};border-radius:4px;}}")
        if self._countdown_ms <= 0:
            self._countdown_timer.stop()
            self._on_timeout()

    def _on_timeout(self) -> None:
        if self.question and not self.next_button.isVisible():
            self._score(False, str(self.question.get("answer", "")),
                        extra_feedback="⏱ Time's up!")

    # ── Submissions ───────────────────────────────────────────────────────────

    def _submit_choice(self, value) -> None:
        answer = str(self.question["answer"])
        detail = answer
        if self.question.get("mode") == "bigger":
            vals = self.question.get("values", {})
            detail = " · ".join(f"{n}: {v:,.2f}" for n, v in vals.items())
        self._score(str(value) == answer, detail)

    def _submit_distance(self) -> None:
        truth = float(self.question["answer"]) / 1000.0
        guess = float(self.distance_guess.value())
        error = abs(guess - truth) / max(0.001, abs(truth))
        tol = float(self.question.get("tolerance", 0.25))
        self._score(error <= tol, f"{truth:,.1f} km",
                    closeness=max(0.25, 1.0 - error))

    def _submit_attr_guess(self) -> None:
        actual = self._attr_slider_min + self.attr_slider.value() * self._attr_slider_scale
        truth = float(self.question["answer"])
        tol = float(self.question.get("tolerance", 0.25))
        scale = float(self.question.get("tolerance_scale", max(1.0, abs(truth))))
        error = abs(actual - truth) / max(1e-9, scale)
        self._score(error <= tol, f"{truth:,.2f}",
                    closeness=max(0.25, 1.0 - error))

    def _submit_ordering(self) -> None:
        submitted = [self.ordering_list.item(i).text()
                     for i in range(self.ordering_list.count())]
        correct = list(self.question["answer"])
        self._score(submitted == correct, " > ".join(correct))

    def handle_map_pick(self, point) -> None:
        if not self.question or self.question.get("mode") != "locate" or self.session is None:
            return
        layer_id = self.question.get("target_layer_id")
        layer = self._layer_for_id(layer_id)
        if layer is None:
            self._score(False, str(self.question["answer"]),
                        extra_feedback="The target layer is no longer available.")
            return
        canvas = self.iface.mapCanvas()
        tolerance = canvas.mapUnitsPerPixel() * 12.0
        layer_point, layer_tol = point, tolerance
        try:
            settings = canvas.mapSettings()
            layer_point = settings.mapToLayerCoordinates(layer, point)
            edge = settings.mapToLayerCoordinates(
                layer, type(point)(point.x() + tolerance, point.y()))
            layer_tol = math.hypot(edge.x() - layer_point.x(), edge.y() - layer_point.y())
        except Exception as exc:
            _ = exc
        picked = feature_at_point(layer, layer_point, layer_tol)
        target = int(self.question["target_fid"])
        correct = picked == target
        self._highlight_feature(target, QColor("#15a66a") if correct else QColor("#e94f64"), layer_id)
        self._score(correct, str(self.question["answer"]))

    # ── Scoring ───────────────────────────────────────────────────────────────

    def _score(self, correct: bool, answer: str, closeness: float = 1.0,
               extra_feedback: str = "") -> None:
        if self.session is None or not self.session.awaiting_answer:
            return
        self._countdown_timer.stop()
        elapsed = time.monotonic() - self._question_time
        result = self.session.answer(correct, elapsed=elapsed, closeness=closeness)
        correct = result["correct"]
        color = "#13795b" if correct else "#c9344f"
        lead = self._t("correct") if correct else self._t("wrong")
        gained = f" +{result['gained']}" if result["gained"] else ""
        text = f"<span style='color:{color}'><b>{lead}{gained}</b></span>"
        if extra_feedback:
            text = f"<span style='color:#6b7280'>{extra_feedback}</span> {text}"
        text += f"<br>{answer}"
        self.feedback.setText(text)
        self.feedback.setStyleSheet("")

        # Disable all inputs
        for btn in self._answer_buttons:
            btn.setEnabled(False)
        self.ordering_submit.setEnabled(False)
        self.attr_submit.setEnabled(False)
        self.locate_finished.emit()
        for jbtn in (self.joker_eliminate, self.joker_value, self.joker_map):
            jbtn.setEnabled(False)

        self.next_button.show()
        fin_text = self._t("finish") if result["finished"] else self._t("next")
        self.next_button.setText(fin_text + "  →")
        self._update_stats(result)

    def _update_stats(self, result: dict | None = None) -> None:
        if self.session is None:
            return
        self.score_card.setText(f"★ {self.session.score:,}")
        self.round_card.setText(
            f"{min(self.session.rounds + 1, self.session.round_limit)} / {self.session.round_limit}")
        self.life_card.setText("♥ " + str(self.session.lives))
        streak = self.session.streak
        if streak >= 3:
            self.streak_card.setText(f"🔥 ×{streak}")
        elif streak > 0:
            self.streak_card.setText(f"🔥 ×{streak}")
        else:
            self.streak_card.setText("")

    def _finish_game(self) -> None:
        self._countdown_timer.stop()
        self.locate_finished.emit()
        summary = self.session.summary()
        self._clear_answers()
        self.mode_badge.setText(self._t("finish"))
        self.prompt.setText(f"★ {summary['score']:,}")
        self.feedback.setText(
            f"{summary['correct']} / {summary['rounds']} correct · "
            f"{summary['accuracy']:.0%} accuracy · best streak {summary['best_streak']}")
        self._save_score(summary)
        # Save to class profile if active
        if self._active_profile:
            name, avatar = self._active_profile
            try:
                self._profiles.save_session(
                    name, avatar, summary,
                    self.quest_title.currentText(), self._difficulty)
                self._refresh_sessions()
            except Exception as exc:
                _ = exc
        again = QPushButton("↻  " + self._t("start"))
        again.setProperty("class", "primary")
        again.clicked.connect(self.start_game)
        self.answer_layout.addWidget(again, 0, 0, 1, 2)
        self._answer_buttons.append(again)

    # ── Joker actions ─────────────────────────────────────────────────────────

    def _update_joker_buttons(self) -> None:
        if not self.session or not self.question:
            return
        joker = self.session.joker
        mode = self.question["mode"]
        has_choices = mode in ("bigger", "silhouette", "nearest", "blind_zoom")
        has_value = mode in ("attr_guess", "distance")
        has_map = mode in ("locate", "blind_zoom")
        self.joker_eliminate.setEnabled(has_choices and joker.available(joker.ELIMINATE))
        self.joker_value.setEnabled(has_value and joker.available(joker.VALUE_HINT))
        self.joker_map.setEnabled(has_map and joker.available(joker.MAP_HINT))

    def _use_eliminate_joker(self) -> None:
        if not self.session or not self.question:
            return
        joker = self.session.joker
        choices = [btn.text() for btn in self._answer_buttons]
        answer = str(self.question.get("answer", ""))
        remaining = joker.eliminate(choices, answer)
        remaining_set = set(remaining)
        for btn in self._answer_buttons:
            if btn.text() not in remaining_set:
                btn.hide()
        self.joker_eliminate.setEnabled(False)

    def _use_value_joker(self) -> None:
        if not self.session or not self.question:
            return
        joker = self.session.joker
        mode = self.question["mode"]
        if mode == "attr_guess":
            min_v = self._attr_slider_min
            max_v = min_v + self._attr_slider_scale * 200
            new_lo, new_hi = joker.narrow_range(min_v, max_v)
            self._attr_slider_min = new_lo
            self._attr_slider_scale = (new_hi - new_lo) / 200.0
            self.attr_range_hint.setText(
                f"Narrowed: {new_lo:,.2f} – {new_hi:,.2f}")
            self._update_attr_label(self.attr_slider.value())
        elif mode == "distance":
            cur = float(self.distance_guess.value())
            lo = max(0, cur * 0.6)
            hi = cur * 1.4
            if joker.use(joker.VALUE_HINT):
                self.distance_guess.setRange(lo, hi)
        self.joker_value.setEnabled(False)

    def _use_map_joker(self) -> None:
        if not self.session or not self.question:
            return
        joker = self.session.joker
        bbox = self.question.get("target_bbox_wgs84") or self.question.get("bbox_wgs84", [])
        if bbox and len(bbox) == 4 and joker.use(joker.MAP_HINT):
            # Zoom to 2.5× the feature's bounding box (hint without pinpointing)
            cx = (bbox[0] + bbox[2]) / 2
            cy = (bbox[1] + bbox[3]) / 2
            w = (bbox[2] - bbox[0]) * 2.5
            h = (bbox[3] - bbox[1]) * 2.5
            self._zoom_to_question_area.__func__  # reuse with wider bbox
            try:
                wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
                canvas_crs = self.canvas.mapSettings().destinationCrs()
                tr = QgsCoordinateTransform(wgs84, canvas_crs, QgsProject.instance())
                sw = tr.transform(cx - w / 2, cy - h / 2)
                ne = tr.transform(cx + w / 2, cy + h / 2)
                if self._saved_extent is None:
                    self._saved_extent = self.canvas.extent()
                self.canvas.setExtent(QgsRectangle(sw.x(), sw.y(), ne.x(), ne.y()))
                self.canvas.refresh()
            except Exception as exc:
                _ = exc
        self.joker_map.setEnabled(False)

    # ── Highlight ─────────────────────────────────────────────────────────────

    def _highlight_feature(self, fid: int, color: QColor, layer_id: str | None = None) -> None:
        self._clear_highlight()
        layer = self._layer_for_id(layer_id) if layer_id else self.layer_combo.currentLayer()
        if layer is None:
            return
        feature = next(layer.getFeatures(QgsFeatureRequest(fid)), None)
        if feature is None:
            return
        self._highlight = QgsHighlight(self.canvas, feature.geometry(), layer)
        self._highlight.setColor(color)
        self._highlight.setFillColor(QColor(color.red(), color.green(), color.blue(), 70))
        self._highlight.setWidth(3)
        self._highlight.show()

    def _clear_highlight(self) -> None:
        if self._highlight is not None:
            self._highlight.hide()
            self._highlight = None

    # ── Leaderboard ───────────────────────────────────────────────────────────

    def _scores(self) -> list[dict]:
        try:
            return json.loads(str(QgsSettings().value(SETTINGS_KEY, "[]")))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    def _save_score(self, summary: dict) -> None:
        scores = self._scores()
        scores.append({
            "title": self.quest_title.currentText(),
            "difficulty": self._difficulty,
            **summary,
        })
        scores = sorted(scores, key=lambda s: int(s.get("score", 0)), reverse=True)[:20]
        QgsSettings().setValue(SETTINGS_KEY, json.dumps(scores))
        self._refresh_scores()

    def _refresh_scores(self) -> None:
        if not hasattr(self, "score_list"):
            return
        self.score_list.clear()
        for idx, item in enumerate(self._scores(), 1):
            diff = item.get("difficulty", "")
            self.score_list.addItem(
                f"{idx:02d}   ★ {int(item.get('score', 0)):,}   "
                f"{item.get('title', 'Quest')}  [{diff}]\n"
                f"       {float(item.get('accuracy', 0)):.0%} accuracy · "
                f"{int(item.get('best_streak', 0))} streak")
        if self.score_list.count() == 0:
            self.score_list.addItem("No completed quests yet — the first crown is waiting.")

    def _clear_scores(self) -> None:
        QgsSettings().setValue(SETTINGS_KEY, "[]")
        self._refresh_scores()

    # ── Class mode / profiles ─────────────────────────────────────────────────

    def _refresh_profiles(self) -> None:
        self.profile_combo.clear()
        self.profile_combo.addItem("— no profile —", None)
        for p in self._profiles.load_profiles():
            self.profile_combo.addItem(f"{p.avatar} {p.name}", (p.name, p.avatar))
        self.profile_combo.currentIndexChanged.connect(self._profile_selected)

    def _profile_selected(self, idx: int) -> None:
        data = self.profile_combo.itemData(idx)
        self._active_profile = data  # None or (name, avatar)

    def _add_profile(self) -> None:
        name = self.new_profile_name.currentText().strip()
        avatar = self.avatar_combo.currentText()
        if not name:
            return
        try:
            self._profiles.add_profile(name, avatar)
            self._refresh_profiles()
            self.new_profile_name.clearEditText()
        except ValueError as exc:
            QMessageBox.warning(self, PLUGIN_TITLE, str(exc))

    def _remove_profile(self) -> None:
        data = self.profile_combo.currentData()
        if data is None:
            return
        name, _ = data
        self._profiles.remove_profile(name)
        self._active_profile = None
        self._refresh_profiles()

    def _refresh_sessions(self) -> None:
        if not hasattr(self, "session_list"):
            return
        self.session_list.clear()
        for s in reversed(self._profiles.load_sessions()[-20:]):
            self.session_list.addItem(
                f"{s.get('avatar','')} {s.get('player','?')}  ★{s.get('score',0):,}  "
                f"{s.get('quest','')}  [{s.get('difficulty','')}]  {s.get('date','')}")
        if self.session_list.count() == 0:
            self.session_list.addItem("No class sessions yet.")

    def _clear_sessions(self) -> None:
        self._profiles.clear_sessions()
        self._refresh_sessions()

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export sessions", "geoquest_sessions.csv", "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            count = self._profiles.export_csv(path)
            self.iface.messageBar().pushSuccess(
                PLUGIN_TITLE, f"Exported {count} session(s) to {path}")
        except OSError as exc:
            QMessageBox.critical(self, PLUGIN_TITLE, str(exc))

    # ── HTML export ───────────────────────────────────────────────────────────

    def _export_html(self) -> None:
        if not self._prepare_records():
            self._show_page(1)
            return
        web_modes = [mode for mode in self._active_modes if mode in HTML_MODES]
        skipped_modes = [mode for mode in self._active_modes if mode not in HTML_MODES]
        if not web_modes:
            QMessageBox.warning(
                self, PLUGIN_TITLE,
                "Offline HTML supports Value Duel, Distance Guess, Know the Shape, "
                "Attribute Guess, Ranking, and Nearest Neighbour. Map Hunt and Blind Zoom need QGIS.")
            return
        if skipped_modes:
            QMessageBox.information(
                self, PLUGIN_TITLE,
                "The HTML game will omit QGIS-only modes: " +
                ", ".join(MODE_LABELS[mode] for mode in skipped_modes))
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export GeoQuest",
            self.quest_title.currentText().replace(" ", "_") + ".html",
            "HTML game (*.html)")
        if not filename:
            return
        if not filename.lower().endswith(".html"):
            filename += ".html"
        try:
            write_html(filename, self.quest_title.currentText(),
                       self.records, web_modes, self.round_count.value())
        except ValueError as exc:
            QMessageBox.warning(self, PLUGIN_TITLE, str(exc))
            return
        except OSError as exc:
            QMessageBox.critical(self, PLUGIN_TITLE, str(exc))
            return
        self.iface.messageBar().pushSuccess(
            PLUGIN_TITLE, f"{self._t('exported')}: {filename}")

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def dispose(self) -> None:
        self._countdown_timer.stop()
        self.locate_finished.emit()
        self._clear_highlight()
        self._restore_extent()
