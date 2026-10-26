# -*- coding: utf-8 -*-
"""Polished dock interface for building, playing and sharing GeoQuests."""
from __future__ import annotations

import html
import json
import math
import os
import time
from contextlib import suppress

from qgis.PyQt.QtCore import QEvent, QPointF, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QKeySequence, QPainter, QPainterPath, QPen, QPixmap
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

try:
    from qgis.PyQt.QtWidgets import QShortcut
except ImportError:  # pragma: no cover - Qt6
    from qgis.PyQt.QtGui import QShortcut

from ..core.certificate import generate_certificate_html
from ..core.exporter import HTML_MODES, write_html
from ..core.game import DIFFICULTY, MODES, GameSession, Joker, QuestionFactory
from ..core.layer_data import features_at_point, merge_layers, records_from_layer
from ..core.profiles import AVATARS, ProfileManager
from ..core.quest_pack import STARTER_PACKS, export_pack, import_pack, validate_pack
from .theme import apply_adaptive_theme, dock_color_tokens

PLUGIN_TITLE = "02GeoQuest — Playable Map Studio"
SETTINGS_KEY = "zero2geoquest/leaderboard"
# Smallest canvas window (degrees, ~300 m) for point features in Blind Zoom / Map Hint.
MIN_ZOOM_SPAN_DEG = 0.003

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
    "direction":  "Compass Quest 🧭",
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
    "direction":  "Estimate compass direction / bearing between two places",
}

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
        t = dock_color_tokens()
        painter.fillRect(self.rect(), QColor(t["card"]))
        painter.setPen(QPen(QColor(t["accent"]), 2))
        painter.setBrush(QColor(t["accent"]))
        if len(self._outline) < 3:
            painter.end()
            return
        xs = [p[0] for p in self._outline]
        ys = [p[1] for p in self._outline]
        min_x, min_y = min(xs), min(ys)
        w, h = max(xs) - min_x, max(ys) - min_y
        scale = min((self.width() - 40) / max(w, 1e-12),
                    (self.height() - 30) / max(h, 1e-12))
        path = QPainterPath()
        for i, (x, y) in enumerate(self._outline):
            px = (x - min_x - w / 2) * scale + self.width() / 2
            py = self.height() / 2 - (y - min_y - h / 2) * scale
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
        # A loaded Quest Pack stays the quest source until the user picks a
        # layer or starts from the builder; replay and export then reuse it.
        self._pack_data: dict | None = None
        self._value_label = "value"
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
        self._install_shortcuts()
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
        self._apply_theme()

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
            card.setObjectName("statCard")
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

        # Page 1: Ordering (drag-and-drop & button reordering list)
        ordering_page = QWidget()
        ordering_v = QVBoxLayout(ordering_page)
        ordering_v.setContentsMargins(0, 0, 0, 0)
        ordering_v.setSpacing(6)
        self.ordering_hint = QLabel("💡 Rank items from HIGHEST (top) ↓ to LOWEST (bottom):")
        self.ordering_hint.setStyleSheet("color:#7c3aed;font-weight:700;font-size:9pt;")
        self.ordering_hint.setWordWrap(True)
        ordering_v.addWidget(self.ordering_hint)

        self.ordering_list = QListWidget()
        self.ordering_list.setObjectName("orderingList")
        self.ordering_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.ordering_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.ordering_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.ordering_list.setAcceptDrops(True)
        self.ordering_list.setDragEnabled(True)
        self.ordering_list.setDropIndicatorShown(True)
        self.ordering_list.setMinimumHeight(150)
        self.ordering_list.model().rowsMoved.connect(self._on_ordering_rows_moved)
        ordering_v.addWidget(self.ordering_list, 1)

        move_btn_row = QHBoxLayout()
        self.order_up_btn = QPushButton("⬆️ Move Up")
        self.order_up_btn.setToolTip("Move selected item higher in rank (towards 1st)")
        self.order_up_btn.clicked.connect(self._move_ordering_item_up)
        self.order_down_btn = QPushButton("⬇️ Move Down")
        self.order_down_btn.setToolTip("Move selected item lower in rank (towards lowest)")
        self.order_down_btn.clicked.connect(self._move_ordering_item_down)
        move_btn_row.addWidget(self.order_up_btn)
        move_btn_row.addWidget(self.order_down_btn)
        ordering_v.addLayout(move_btn_row)

        self.ordering_submit = QPushButton("✓ Submit ranking")
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
        self.distance_guess.setGroupSeparatorShown(True)
        self.distance_guess.setToolTip("Type your estimate, then press Enter or Submit")
        dist_v.addWidget(self.distance_guess, 1)
        self.distance_submit = QPushButton("Submit estimate")
        self.distance_submit.setProperty("class", "primary")
        self.distance_submit.clicked.connect(self._submit_distance)
        dist_v.addWidget(self.distance_submit)
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
        cert_btn = QPushButton("📜 Export Certificate (HTML)…")
        cert_btn.clicked.connect(self._export_certificate)
        clear = QPushButton("Clear leaderboard")
        clear.clicked.connect(self._clear_scores)
        btns.addWidget(cert_btn, 1)
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

        # Quest Packs section
        pack_box = QGroupBox("Quest Packs & Curated Trivia")
        pack_v = QVBoxLayout(pack_box)
        pack_desc = QLabel("Export current layer snapshot as a portable trivia bundle, or load curated starter packs.")
        pack_desc.setWordWrap(True)
        pack_desc.setStyleSheet("color:#718096;font-size:8pt")
        pack_v.addWidget(pack_desc)

        starter_row = QHBoxLayout()
        self.starter_pack_combo = QComboBox()
        for p_name in STARTER_PACKS:
            self.starter_pack_combo.addItem(p_name)
        starter_row.addWidget(self.starter_pack_combo, 1)
        load_starter_btn = QPushButton("Load Starter")
        load_starter_btn.clicked.connect(self._load_starter_pack)
        starter_row.addWidget(load_starter_btn)
        pack_v.addLayout(starter_row)

        pack_btn_row = QHBoxLayout()
        export_pack_btn = QPushButton("💾 Export Pack (.geoquest.json)…")
        export_pack_btn.clicked.connect(self._export_quest_pack)
        import_pack_btn = QPushButton("📂 Import Pack…")
        import_pack_btn.clicked.connect(self._import_quest_pack)
        pack_btn_row.addWidget(export_pack_btn)
        pack_btn_row.addWidget(import_pack_btn)
        pack_v.addLayout(pack_btn_row)
        layout.addWidget(pack_box)

        privacy = QLabel("🔒 Privacy by design · local data · no account · no CDN")
        privacy.setWordWrap(True)
        privacy.setObjectName("privacyLabel")
        layout.addWidget(privacy)

        # Class mode
        class_box = QGroupBox("Class mode — student profiles")
        class_v = QVBoxLayout(class_box)

        profile_row = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(130)
        self.profile_combo.currentIndexChanged.connect(self._profile_selected)
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
        self._pack_data = None
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
        """Snapshot the builder's layer(s) and choose the playable modes."""
        layer_a = self.layer_combo.currentLayer()
        modes = self._selected_modes()
        if layer_a is None or not modes:
            self.builder_status.setText(self._t("choose"))
            return False
        label_a = self.label_field.currentField()
        value_a = self.value_field.currentField()
        layer_b = self.layer_combo_b.currentLayer() if self.use_second_layer.isChecked() else None
        value_b = self.value_field_b.currentField() if layer_b is not None else ""
        try:
            if layer_b is not None:
                records = merge_layers(
                    layer_a, label_a, value_a,
                    layer_b, self.label_field_b.currentField(), value_b)
            else:
                records = records_from_layer(layer_a, label_a, value_a)
        except Exception as exc:
            self.builder_status.setText(str(exc))
            return False

        if len(records) < 4:
            self.builder_status.setText("At least four non-empty features are required.")
            return False

        names = [self._field_display_name(layer_a, value_a)]
        if layer_b is not None:
            names.append(self._field_display_name(layer_b, value_b))
        names = list(dict.fromkeys(name for name in names if name))
        self._value_label = names[0] if len(names) == 1 else "value"

        notes = []
        source_count = layer_a.featureCount() + (
            layer_b.featureCount() if layer_b is not None and layer_b.id() != layer_a.id() else 0)
        if source_count > len(records):
            notes.append(f"Sampled {len(records):,} of {source_count:,} features evenly.")
        if not (value_a or value_b):
            dropped = [MODE_LABELS[m] for m in modes if m in ("attr_guess", "ordering")]
            if dropped:
                notes.append(", ".join(dropped) + " need a numeric field — skipped.")
            modes = [m for m in modes if m not in ("attr_guess", "ordering")]
            if not modes:
                self.builder_status.setText(" ".join(notes))
                return False

        factory = QuestionFactory(records, seed=time.time_ns(), value_label=self._value_label)
        active = factory.available_modes(modes)
        if not active:
            self.builder_status.setText(
                " ".join(notes + ["Selected modes need more suitable or more varied feature data."]))
            return False
        skipped = [MODE_LABELS[mode] for mode in modes if mode not in active]
        if skipped:
            notes.append("Skipped (not enough suitable data): " + ", ".join(skipped))

        self._pack_data = None
        self.records, self.factory, self._active_modes = records, factory, active
        self.builder_status.setText(" ".join(notes) or f"{len(records):,} features ready.")
        self._update_export_summary()
        return True

    def start_game(self) -> None:
        if not self._prepare_records():
            return
        self._launch_game()

    def _launch_game(self) -> None:
        """Start a session from the records and modes already prepared."""
        modes = list(self._active_modes)
        if self.factory is None or not modes:
            self.builder_status.setText("No playable challenge modes are available.")
            self._show_page(1)
            return
        self.session = GameSession(
            modes, self.round_count.value(), self.lives_count.value(),
            seed=time.time_ns(), difficulty=self._difficulty,
            joker_count=self.joker_count.value())
        self._update_stats()
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
        self._set_inputs_enabled(True)
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
        candidate_modes = [mode] + [item for item in self.session.modes if item != mode]
        last_error = ""
        for candidate in candidate_modes:
            try:
                self.question = self.factory.make(candidate, self._difficulty)
                break
            except ValueError as exc:
                last_error = str(exc)
        else:
            self.builder_status.setText(
                "Quest stopped because no challenge could be generated. " + last_error)
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
            repick = QPushButton("🎯 Pick on map")
            repick.setToolTip("Re-activate the picking tool if you switched to pan or zoom")
            repick.clicked.connect(self.locate_requested.emit)
            self.answer_layout.addWidget(repick, 0, 0, 1, 2)
            self._answer_buttons.append(repick)
            self.locate_requested.emit()

        elif mode in ("bigger", "silhouette", "nearest", "blind_zoom", "direction"):
            self._show_choices(self.question["choices"])
            if mode == "silhouette":
                self.silhouette.set_outline(self.question["outline"])
                self.silhouette.show()
            elif mode == "blind_zoom":
                self._zoom_to_question_area()

        elif mode == "distance":
            self.input_stack.setCurrentIndex(2)
            unit = self.question.get("unit", "km")
            maximum = float(self.question.get("input_max", 50_000))
            # Range and start value come from the whole quest, never from the
            # answer — the old 0.75 × answer start value passed Easy and Medium.
            self.distance_guess.setDecimals(0 if unit == "m" else 2)
            self.distance_guess.setSuffix(f" {unit}")
            self.distance_guess.setRange(0, maximum)
            self.distance_guess.setSingleStep(max(maximum / 100.0, 0.01))
            self.distance_guess.setValue(0)
            self.distance_guess.setFocus()
            self.distance_guess.selectAll()

        elif mode == "attr_guess":
            self.input_stack.setCurrentIndex(3)
            self._setup_attr_slider(self.question)

        elif mode == "ordering":
            self.input_stack.setCurrentIndex(1)
            self.ordering_list.clear()
            for item_data in self.question.get("items", []):
                label = item_data.get("label", "")
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, label)
                self.ordering_list.addItem(item)
            self._refresh_ordering_display()
            if self.ordering_list.count() > 0:
                self.ordering_list.setCurrentRow(0)

    def _show_choices(self, choices: list) -> None:
        self.input_stack.setCurrentIndex(0)
        for idx, choice in enumerate(choices):
            # "&" would become a keyboard mnemonic and vanish from the label.
            btn = QPushButton(f"{idx + 1}  {str(choice).replace('&', '&&')}")
            btn.setProperty("class", "answer")
            btn.setProperty("choice", str(choice))
            btn.setToolTip(f"Press {idx + 1} to choose")
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
        xmin, ymin, xmax, ymax = (float(v) for v in bbox[:4])
        # Points have an empty box; keep at least ~300 m of context around them.
        pad_x = max((xmax - xmin) * 0.20, MIN_ZOOM_SPAN_DEG / 2)
        pad_y = max((ymax - ymin) * 0.20, MIN_ZOOM_SPAN_DEG / 2)
        self._set_canvas_extent_wgs84(xmin - pad_x, ymin - pad_y, xmax + pad_x, ymax + pad_y)

    def _restore_extent(self) -> None:
        if self._saved_extent is not None:
            with suppress(Exception):
                self.canvas.setExtent(self._saved_extent)
                self.canvas.refresh()
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
        t = dock_color_tokens()
        if pct > 0.5:
            chunk_color = t["accent"]
        elif pct > 0.25:
            chunk_color = "#f59e0b"
        else:
            chunk_color = t["wrong_color"]
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
        if not self.question or "choices" not in self.question:
            return
        answer = str(self.question["answer"])
        detail = answer
        if self.question.get("mode") == "bigger":
            vals = self.question.get("values", {})
            detail = " · ".join(f"{n}: {v:,.2f}" for n, v in vals.items())
        self._score(str(value) == answer, detail)

    def _submit_distance(self) -> None:
        if not self.question or self.question.get("mode") != "distance":
            return
        factor = float(self.question.get("unit_factor", 1000.0))
        truth = float(self.question["answer"])
        guess = float(self.distance_guess.value()) * factor
        error = abs(guess - truth) / max(1e-9, abs(truth))
        tol = float(self.question.get("tolerance", 0.25))
        self._score(error <= tol,
                    f"Answer: {self._format_distance(truth)} · your estimate: "
                    f"{self._format_distance(guess)}",
                    closeness=max(0.25, 1.0 - error))

    def _submit_attr_guess(self) -> None:
        if not self.question or self.question.get("mode") != "attr_guess":
            return
        actual = self._attr_slider_min + self.attr_slider.value() * self._attr_slider_scale
        truth = float(self.question["answer"])
        tol = float(self.question.get("tolerance", 0.25))
        scale = float(self.question.get("tolerance_scale") or max(1.0, abs(truth)))
        error = abs(actual - truth) / max(1e-9, scale)
        self._score(error <= tol, f"Answer: {truth:,.2f} · your guess: {actual:,.2f}",
                    closeness=max(0.25, 1.0 - error))

    def _on_ordering_rows_moved(self, _parent=None, _start=0, _end=0, _dest=None, _row=0) -> None:
        self._refresh_ordering_display()

    def _refresh_ordering_display(self) -> None:
        rank_badges = ["🥇 1st (Highest)", "🥈 2nd", "🥉 3rd", "🔻 4th (Lowest)", "5th", "6th", "7th"]
        count = self.ordering_list.count()
        for i in range(count):
            item = self.ordering_list.item(i)
            raw_label = item.data(Qt.ItemDataRole.UserRole)
            if not raw_label:
                raw_label = item.text()
                for prefix in ("🥇 ", "🥈 ", "🥉 ", "🔻 "):
                    if raw_label.startswith(prefix):
                        if ":  " in raw_label:
                            raw_label = raw_label.split(":  ", 1)[1]
                        break
                item.setData(Qt.ItemDataRole.UserRole, raw_label)

            badge = rank_badges[i] if i < len(rank_badges) else f"#{i+1}"
            if count == 3 and i == 2:
                badge = "🔻 3rd (Lowest)"
            item.setText(f"{badge}:  {raw_label}")

    def _move_ordering_item_up(self) -> None:
        row = self.ordering_list.currentRow()
        if row > 0:
            item = self.ordering_list.takeItem(row)
            self.ordering_list.insertItem(row - 1, item)
            self.ordering_list.setCurrentRow(row - 1)
            self._refresh_ordering_display()

    def _move_ordering_item_down(self) -> None:
        row = self.ordering_list.currentRow()
        if 0 <= row < self.ordering_list.count() - 1:
            item = self.ordering_list.takeItem(row)
            self.ordering_list.insertItem(row + 1, item)
            self.ordering_list.setCurrentRow(row + 1)
            self._refresh_ordering_display()

    def _submit_ordering(self) -> None:
        if not self.question or self.session is None or not self.session.awaiting_answer:
            return
        submitted = []
        for i in range(self.ordering_list.count()):
            item = self.ordering_list.item(i)
            label = item.data(Qt.ItemDataRole.UserRole)
            if not label:
                txt = item.text()
                if ":  " in txt:
                    label = txt.split(":  ", 1)[1]
                else:
                    label = txt
            submitted.append(str(label).strip())

        correct = [str(x).strip() for x in self.question.get("answer", [])]
        items_dict = {str(it["label"]).strip(): it.get("value") for it in self.question.get("items", [])}

        detail_parts = []
        for rank_idx, c_label in enumerate(correct, 1):
            val = items_dict.get(c_label)
            val_str = f" ({val:,.2f})" if val is not None else ""
            detail_parts.append(f"{rank_idx}. {c_label}{val_str}")
        detail_msg = "  >  ".join(detail_parts)

        is_correct = (submitted == correct)
        self._score(is_correct, detail_msg)

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
        with suppress(Exception):
            settings = canvas.mapSettings()
            layer_point = settings.mapToLayerCoordinates(layer, point)
            edge = settings.mapToLayerCoordinates(
                layer, type(point)(point.x() + tolerance, point.y()))
            layer_tol = math.hypot(edge.x() - layer_point.x(), edge.y() - layer_point.y())
        # Every feature under (or within 12 px of) the click counts, so a
        # target overlapped by another polygon is still found.
        hits = features_at_point(layer, layer_point, layer_tol)
        target = int(self.question["target_fid"])
        correct = target in hits
        self._highlight_feature(target, QColor("#15a66a") if correct else QColor("#e94f64"), layer_id)
        extra = "" if correct or hits else "Nothing was under the click."
        self._score(correct, str(self.question["answer"]), extra_feedback=extra)

    # ── Scoring ───────────────────────────────────────────────────────────────

    def _score(self, correct: bool, answer: str, closeness: float = 1.0,
               extra_feedback: str = "") -> None:
        if self.session is None or not self.session.awaiting_answer:
            return
        self._countdown_timer.stop()
        elapsed = time.monotonic() - self._question_time
        result = self.session.answer(correct, elapsed=elapsed, closeness=closeness)
        correct = result["correct"]
        t = dock_color_tokens()
        color = t["correct_color"] if correct else t["wrong_color"]
        lead = self._t("correct") if correct else self._t("wrong")
        gained = f" +{result['gained']}" if result["gained"] else ""
        text = f"<span style='color:{color}'><b>{lead}{gained}</b></span>"
        if result.get("timed_out") and not extra_feedback:
            extra_feedback = "⏱ Time's up!"
        if extra_feedback:
            text = f"<span style='color:{t['subtle']}'>{html.escape(extra_feedback)}</span> {text}"
        text += f"<br>{html.escape(str(answer))}"
        self.feedback.setText(text)
        self.feedback.setStyleSheet("")

        self._set_inputs_enabled(False)
        answer_text = str(self.question.get("answer", "")) if self.question else ""
        for btn in self._answer_buttons:
            if btn.property("choice") == answer_text:
                btn.setStyleSheet(
                    f"border:2px solid {t['correct_color']};font-weight:800;")
        self.locate_finished.emit()
        for jbtn in (self.joker_eliminate, self.joker_value, self.joker_map):
            jbtn.setEnabled(False)

        self.next_button.show()
        fin_text = self._t("finish") if result["finished"] else self._t("next")
        self.next_button.setText(fin_text + "  →")
        self.next_button.setFocus()
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
            with suppress(Exception):
                self._profiles.save_session(
                    name, avatar, summary,
                    self.quest_title.currentText(), self._difficulty)
                self._refresh_sessions()
        again = QPushButton("↻  Play again")
        again.setProperty("class", "primary")
        again.clicked.connect(self._play_again)
        self.answer_layout.addWidget(again, 0, 0, 1, 2)
        self._answer_buttons.append(again)

    # ── Joker actions ─────────────────────────────────────────────────────────

    def _update_joker_buttons(self) -> None:
        if not self.session or not self.question:
            return
        joker = self.session.joker
        mode = self.question["mode"]
        can_eliminate = (mode in ("bigger", "silhouette", "nearest", "blind_zoom", "direction")
                         and Joker.can_eliminate(self.question.get("choices", []),
                                                 self.question.get("answer")))
        has_value = mode in ("attr_guess", "distance")
        has_map = mode in ("locate", "blind_zoom")
        self.joker_eliminate.setEnabled(can_eliminate and joker.available(joker.ELIMINATE))
        self.joker_value.setEnabled(has_value and joker.available(joker.VALUE_HINT))
        self.joker_map.setEnabled(has_map and joker.available(joker.MAP_HINT))

    def _use_eliminate_joker(self) -> None:
        if not self.session or not self.question or not self.session.awaiting_answer:
            return
        joker = self.session.joker
        choices = [btn.property("choice") for btn in self._answer_buttons
                   if btn.property("choice") is not None and btn.isVisible()]
        answer = str(self.question.get("answer", ""))
        remaining = set(joker.eliminate(choices, answer))
        for btn in self._answer_buttons:
            if btn.property("choice") is not None and btn.property("choice") not in remaining:
                btn.hide()
        self.joker_eliminate.setEnabled(False)

    def _use_value_joker(self) -> None:
        if not self.session or not self.question or not self.session.awaiting_answer:
            return
        joker = self.session.joker
        mode = self.question["mode"]
        truth = float(self.question["answer"])
        if mode == "attr_guess":
            lo = self._attr_slider_min
            hi = lo + self._attr_slider_scale * 200
            new_lo, new_hi = joker.narrow_range(lo, hi, truth=truth)
            self._attr_slider_min = new_lo
            self._attr_slider_scale = (new_hi - new_lo) / 200.0
            self.attr_range_hint.setText(f"Narrowed: {new_lo:,.2f} – {new_hi:,.2f}")
            self._update_attr_label(self.attr_slider.value())
        elif mode == "distance":
            factor = float(self.question.get("unit_factor", 1000.0))
            lo, hi = joker.narrow_range(0.0, self.distance_guess.maximum(), truth=truth / factor)
            self.distance_guess.setRange(lo, hi)
            self.distance_guess.setValue((lo + hi) / 2.0)
            self.feedback.setText(
                f"📊 The answer lies between {self._format_distance(lo * factor)} "
                f"and {self._format_distance(hi * factor)}.")
        self.joker_value.setEnabled(False)

    def _use_map_joker(self) -> None:
        if not self.session or not self.question or not self.session.awaiting_answer:
            return
        joker = self.session.joker
        bbox = self.question.get("target_bbox_wgs84") or self.question.get("bbox_wgs84", [])
        if bbox and len(bbox) >= 4 and joker.use(joker.MAP_HINT):
            xmin, ymin, xmax, ymax = (float(v) for v in bbox[:4])
            width = max(xmax - xmin, MIN_ZOOM_SPAN_DEG) * 4.0
            height = max(ymax - ymin, MIN_ZOOM_SPAN_DEG) * 4.0
            # Off-centre window: the target is inside, but not in the middle.
            rng = self.session.rng
            cx = (xmin + xmax) / 2 + (rng.uniform() - 0.5) * width * 0.5
            cy = (ymin + ymax) / 2 + (rng.uniform() - 0.5) * height * 0.5
            self._set_canvas_extent_wgs84(cx - width / 2, cy - height / 2,
                                          cx + width / 2, cy + height / 2)
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

    def _refresh_profiles(self, select: str | None = None) -> None:
        """Rebuild the profile list, keeping (or moving to) the active profile."""
        keep = select or (self._active_profile[0] if self._active_profile else None)
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem("— no profile —", None)
        index = 0
        for p in self._profiles.load_profiles():
            self.profile_combo.addItem(f"{p.avatar} {p.name}", (p.name, p.avatar))
            if p.name == keep:
                index = self.profile_combo.count() - 1
        self.profile_combo.setCurrentIndex(index)
        self.profile_combo.blockSignals(False)
        self._profile_selected(index)

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
            self._refresh_profiles(select=name)
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
        if not self._ensure_quest_source():
            self._show_page(1)
            return
        web_modes = [mode for mode in self._active_modes if mode in HTML_MODES]
        skipped_modes = [mode for mode in self._active_modes if mode not in HTML_MODES]
        if not web_modes:
            QMessageBox.warning(
                self, PLUGIN_TITLE,
                "Offline HTML supports Value Duel, Distance Guess, Know the Shape, "
                "Attribute Guess, Ranking, Nearest Neighbour and Compass Quest. "
                "Map Hunt and Blind Zoom need QGIS.")
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
                       self.records, web_modes, self.round_count.value(),
                       difficulty=self._difficulty, lives=self.lives_count.value(),
                       value_label=self._value_label)
        except ValueError as exc:
            QMessageBox.warning(self, PLUGIN_TITLE, str(exc))
            return
        except OSError as exc:
            QMessageBox.critical(self, PLUGIN_TITLE, str(exc))
            return
        self.iface.messageBar().pushSuccess(
            PLUGIN_TITLE, f"{self._t('exported')}: {filename}")

    def _export_certificate(self) -> None:
        best, quest, player_name = None, "Spatial Quest", "Master Explorer"
        if self._active_profile:
            name, avatar = self._active_profile
            player_name = f"{avatar} {name}"
            mine = [s for s in self._profiles.load_sessions() if s.get("player") == name]
            if mine:
                best = max(mine, key=lambda s: int(s.get("score", 0)))
                quest = str(best.get("quest") or quest)
        if best is None:
            scores = self._scores()
            if not scores:
                QMessageBox.information(self, PLUGIN_TITLE, "Play and complete at least one quest first!")
                return
            best = scores[0]
            quest = str(best.get("title") or quest)
        html_content = generate_certificate_html(best, player_name=player_name, quest_title=quest)
        safe_name = "".join(ch if ch.isalnum() else "_" for ch in player_name).strip("_") or "Explorer"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Certificate", f"GeoQuest_Certificate_{safe_name}.html",
            "HTML Certificate (*.html)")
        if not filename:
            return
        if not filename.lower().endswith(".html"):
            filename += ".html"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(html_content)
            self.iface.messageBar().pushSuccess(
                PLUGIN_TITLE, f"Certificate exported: {filename}")
        except OSError as exc:
            QMessageBox.critical(self, PLUGIN_TITLE, str(exc))

    def _export_quest_pack(self) -> None:
        if not self._ensure_quest_source():
            self._show_page(1)
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Quest Pack",
            self.quest_title.currentText().replace(" ", "_") + ".geoquest.json",
            "Quest Pack (*.geoquest.json *.json)")
        if not filename:
            return
        if not filename.lower().endswith(".json"):
            filename += ".geoquest.json"
        description = (str(self._pack_data.get("description", "")) if self._pack_data
                       else f"Exported from {self.layer_combo.currentText()}")
        try:
            export_pack(
                filename,
                title=self.quest_title.currentText(),
                description=description,
                records=self.records,
                modes=self._active_modes,
                difficulty=self._difficulty,
                value_label=self._value_label,
            )
            self.iface.messageBar().pushSuccess(
                PLUGIN_TITLE, f"Quest Pack saved: {filename}")
        except Exception as exc:
            QMessageBox.critical(self, PLUGIN_TITLE, f"Failed to export pack: {exc}")

    def _import_quest_pack(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import Quest Pack", "", "Quest Pack (*.geoquest.json *.json)")
        if not filename:
            return
        try:
            pack_data = import_pack(filename)
            self._apply_pack_data(pack_data)
        except Exception as exc:
            QMessageBox.critical(self, PLUGIN_TITLE, f"Failed to import pack: {exc}")

    def _load_starter_pack(self) -> None:
        pack_name = self.starter_pack_combo.currentText()
        pack_data = STARTER_PACKS.get(pack_name)
        if not pack_data:
            return
        self._apply_pack_data(pack_data)

    def _apply_pack_data(self, pack_data: dict, announce: bool = True) -> None:
        valid, message = validate_pack(pack_data)
        if not valid:
            raise ValueError(f"Invalid Quest Pack: {message}")
        title = str(pack_data.get("title", "Custom Quest"))
        self.quest_title.setCurrentText(title)
        self.records = list(pack_data.get("records", []))
        self._value_label = str(pack_data.get("value_label") or "value")
        self.factory = QuestionFactory(self.records, seed=time.time_ns(),
                                       value_label=self._value_label)
        diff = str(pack_data.get("difficulty", "Medium"))
        if diff in self.diff_buttons:
            self._set_difficulty(diff)
        modes = list(pack_data.get("modes", []))
        for mode, check in self.mode_checks.items():
            check.setChecked(mode in modes)
        self._active_modes = self.factory.available_modes(modes)
        self._pack_data = pack_data
        self._update_export_summary()
        if announce:
            source = pack_data.get("source")
            self.iface.messageBar().pushSuccess(
                PLUGIN_TITLE, f"Loaded Quest Pack '{title}' ({len(self.records)} features)"
                + (f" · data: {source}" if source else ""))
        # Do not call start_game(): it prepares the currently selected QGIS
        # layer and would overwrite the imported pack records.
        self._launch_game()

    def _field_display_name(self, layer, field_name: str) -> str:
        """Return a field's alias (or name) for prompts such as 'greater population'."""
        if layer is None or not field_name:
            return ""
        index = layer.fields().indexOf(field_name)
        return layer.fields().at(index).displayName() if index >= 0 else field_name

    def _update_export_summary(self) -> None:
        source = "Quest Pack" if self._pack_data is not None else "layer snapshot"
        self.export_summary.setText(
            f"{self.quest_title.currentText()} · {len(self.records)} features ({source}) · "
            f"{self.round_count.value()} rounds · {self._difficulty}")

    def _play_again(self) -> None:
        """Replay the same source: the loaded Quest Pack, or the builder's layer."""
        if self._pack_data is not None:
            self._apply_pack_data(self._pack_data, announce=False)
        else:
            self.start_game()

    def _set_inputs_enabled(self, enabled: bool) -> None:
        """Enable or lock every answer input. Scoring locks them; a new round unlocks."""
        for widget in (self.ordering_submit, self.order_up_btn, self.order_down_btn,
                       self.ordering_list, self.attr_submit, self.attr_slider,
                       self.distance_submit, self.distance_guess):
            widget.setEnabled(enabled)
        for btn in self._answer_buttons:
            btn.setEnabled(enabled)

    def _set_canvas_extent_wgs84(self, xmin: float, ymin: float,
                                 xmax: float, ymax: float) -> None:
        """Zoom the canvas to a WGS84 box, remembering the extent to restore."""
        if self._saved_extent is None:
            self._saved_extent = self.canvas.extent()
        with suppress(Exception):
            transform = QgsCoordinateTransform(
                QgsCoordinateReferenceSystem("EPSG:4326"),
                self.canvas.mapSettings().destinationCrs(), QgsProject.instance())
            self.canvas.setExtent(transform.transformBoundingBox(
                QgsRectangle(xmin, ymin, xmax, ymax)))
            self.canvas.refresh()

    def _format_distance(self, metres: float) -> str:
        unit = self.question.get("unit", "km") if self.question else "km"
        factor = float(self.question.get("unit_factor", 1000.0)) if self.question else 1000.0
        value = metres / factor
        return f"{value:,.0f} {unit}" if unit == "m" or value >= 100 else f"{value:,.2f} {unit}"

    def _install_shortcuts(self) -> None:
        """Keys 1–9 pick an answer and Enter submits or continues while the dock has focus."""
        self._shortcuts = []
        for number in range(1, 10):
            shortcut = QShortcut(QKeySequence(str(number)), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda n=number: self._press_choice(n))
            self._shortcuts.append(shortcut)
        for key in ("Return", "Enter"):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(self._press_enter)
            self._shortcuts.append(shortcut)

    def _press_choice(self, number: int) -> None:
        if self.pages.currentIndex() != 0 or self.session is None or not self.session.awaiting_answer:
            return
        visible = [btn for btn in self._answer_buttons
                   if btn.property("choice") is not None and btn.isVisible() and btn.isEnabled()]
        if 0 < number <= len(visible):
            visible[number - 1].click()

    def _press_enter(self) -> None:
        if self.pages.currentIndex() != 0:
            return
        if self.next_button.isVisible():
            self.next_button.click()
            return
        if not self.question or self.session is None or not self.session.awaiting_answer:
            return
        submit = {"distance": self.distance_submit, "attr_guess": self.attr_submit,
                  "ordering": self.ordering_submit}.get(self.question.get("mode"))
        if submit is not None and submit.isEnabled():
            submit.click()

    def _ensure_quest_source(self) -> bool:
        """Use the loaded Quest Pack if there is one, otherwise snapshot the layer."""
        if self._pack_data is not None and self.records and self._active_modes:
            return True
        return self._prepare_records()

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        ):
            self._apply_theme()

    def _apply_theme(self) -> None:
        root = self.widget()
        if root is None or getattr(self, "_theme_refreshing", False):
            return
        self._theme_refreshing = True
        try:
            apply_adaptive_theme(root)
        finally:
            self._theme_refreshing = False

    def dispose(self) -> None:
        self._countdown_timer.stop()
        self.locate_finished.emit()
        self._clear_highlight()
        self._restore_extent()
