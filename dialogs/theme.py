"""Palette-aware styling for the 02GeoQuest dock.

Derives every surface and text colour from the active Qt palette so the dock
stays readable under QGIS light, dark, high-contrast, and custom themes while
keeping the purple accent identity.
"""
from __future__ import annotations

from qgis.PyQt.QtGui import QColor, QPalette
from qgis.PyQt.QtWidgets import QApplication, QWidget


def _hex(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexRgb)


def _mix(first: QColor, second: QColor, amount: float) -> QColor:
    amount = max(0.0, min(1.0, float(amount)))
    return QColor(
        round(first.red() * (1.0 - amount) + second.red() * amount),
        round(first.green() * (1.0 - amount) + second.green() * amount),
        round(first.blue() * (1.0 - amount) + second.blue() * amount),
    )


def _contrast_text(background: QColor) -> QColor:
    luminance = (
        0.2126 * background.red()
        + 0.7152 * background.green()
        + 0.0722 * background.blue()
    )
    return QColor("#102019") if luminance >= 150 else QColor("#FFFFFF")


def _relative_luminance(color: QColor) -> float:
    channels = []
    for value in (color.redF(), color.greenF(), color.blueF()):
        channels.append(
            value / 12.92
            if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: QColor, second: QColor) -> float:
    """Return the WCAG relative-luminance contrast ratio."""
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def dock_color_tokens(palette: QPalette | None = None) -> dict[str, str]:
    """Return the palette-derived colours used by the dock stylesheet."""
    active = palette or QApplication.palette()
    window = active.color(QPalette.ColorRole.Window)
    base = active.color(QPalette.ColorRole.Base)
    text = active.color(QPalette.ColorRole.WindowText)
    input_text = active.color(QPalette.ColorRole.Text)
    button = active.color(QPalette.ColorRole.Button)
    button_text = active.color(QPalette.ColorRole.ButtonText)
    highlight = active.color(QPalette.ColorRole.Highlight)
    disabled = active.color(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.WindowText,
    )
    dark = window.lightness() < 128

    white = QColor("#FFFFFF")
    accent = QColor("#8B7CF6" if dark else "#6C4CFF")
    accent_hover = QColor("#A598FF" if dark else "#5438D6")
    accent_text = _contrast_text(accent)
    accent_soft = _mix(accent, window, 0.88 if dark else 0.92)

    surface = _mix(window, white, 0.07) if dark else _mix(window, base, 0.72)
    card = _mix(window, white, 0.12) if dark else base
    input_surface = _mix(base, white, 0.04) if dark else base
    border = _mix(text, surface, 0.76 if dark else 0.84)
    subtle = _mix(text, surface, 0.40 if dark else 0.37)

    privacy_bg = QColor("#0D3B2E" if dark else "#E9FBF3")
    privacy_text = QColor("#6EE7B7" if dark else "#13795B")

    correct_color = QColor("#4ADE80" if dark else "#13795B")
    wrong_color = QColor("#F87171" if dark else "#C9344F")

    if contrast_ratio(input_text, input_surface) < 4.5:
        input_text = QColor(text)
    if contrast_ratio(button_text, button) < 4.5:
        button_text = QColor(text)
    selection = highlight if highlight.isValid() else accent

    return {
        "surface": _hex(surface),
        "card": _hex(card),
        "input_surface": _hex(input_surface),
        "text": _hex(text),
        "input_text": _hex(input_text),
        "button": _hex(button),
        "button_text": _hex(button_text),
        "border": _hex(border),
        "subtle": _hex(subtle),
        "disabled": _hex(disabled),
        "accent": _hex(accent),
        "accent_hover": _hex(accent_hover),
        "accent_text": _hex(accent_text),
        "accent_soft": _hex(accent_soft),
        "privacy_bg": _hex(privacy_bg),
        "privacy_text": _hex(privacy_text),
        "correct_color": _hex(correct_color),
        "wrong_color": _hex(wrong_color),
        "selection": _hex(selection),
    }


def dock_stylesheet(palette: QPalette | None = None) -> str:
    """Build the full dock stylesheet from the current application palette."""
    t = dock_color_tokens(palette)
    return """
QWidget#gqRoot {
    background: %(surface)s;
}
QWidget#gqRoot QLabel {
    color: %(text)s;
    background: transparent;
}
QLabel#statCard {
    background: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 9px;
    padding: 6px;
    font-weight: 800;
    font-size: 10pt;
}
QWidget#gqRoot QScrollArea, QWidget#gqRoot QScrollArea > QWidget > QWidget {
    background: transparent;
    border: none;
}
QPushButton {
    color: %(text)s;
    background: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    padding: 7px 10px;
    font-weight: 600;
}
QPushButton:hover {
    border-color: %(accent)s;
    background: %(accent_soft)s;
}
QPushButton:checked {
    color: %(accent_text)s;
    background: %(accent)s;
    border-color: %(accent_hover)s;
}
QPushButton[class='nav'] {
    border: none;
    border-radius: 7px;
    padding: 8px 6px;
}
QPushButton[class='primary'] {
    color: %(accent_text)s;
    background: %(accent)s;
    border-color: %(accent_hover)s;
    font-weight: 800;
    padding: 10px;
}
QPushButton[class='primary']:hover {
    background: %(accent_hover)s;
}
QPushButton[class='primary']:disabled {
    background: %(border)s;
    border-color: %(border)s;
}
QPushButton[class='answer'] {
    text-align: left;
    padding: 11px;
    font-size: 10pt;
}
QPushButton[class='joker'] {
    color: %(accent)s;
    background: %(accent_soft)s;
    border: 1px solid %(accent_soft)s;
    border-radius: 8px;
    padding: 6px 8px;
    font-size: 9pt;
    font-weight: 700;
}
QPushButton[class='joker']:hover {
    background: %(accent_soft)s;
    border-color: %(accent)s;
}
QPushButton[class='joker']:disabled { opacity: 0.4; }
QPushButton[class='diff'] {
    padding: 8px 14px;
    border-radius: 8px;
}
QGroupBox {
    color: %(text)s;
    background: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 11px;
    margin-top: 11px;
    padding: 12px 8px 8px;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
QComboBox, QSpinBox, QDoubleSpinBox {
    color: %(input_text)s;
    background: %(input_surface)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 5px;
}
QListWidget {
    color: %(text)s;
    background: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 9px;
}
QListWidget::item {
    padding: 7px;
    border-bottom: 1px solid %(border)s;
}
QListWidget#orderingList {
    background: %(surface)s;
    color: %(text)s;
    border: 1.5px solid %(border)s;
    border-radius: 10px;
    padding: 4px;
    font-size: 10pt;
}
QListWidget#orderingList::item {
    background: %(card)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    padding: 8px 10px;
    margin: 3px 2px;
    font-weight: 600;
}
QListWidget#orderingList::item:selected {
    background: %(accent_soft)s;
    color: %(accent)s;
    border: 2px solid %(accent)s;
    font-weight: 700;
}
QListWidget#orderingList::item:hover {
    border-color: %(accent)s;
}
QLabel#privacyLabel {
    color: %(privacy_text)s;
    background: %(privacy_bg)s;
    border-radius: 8px;
    padding: 9px;
}
QCheckBox {
    color: %(text)s;
    spacing: 7px;
}
QProgressBar {
    border: none;
    border-radius: 4px;
    background: %(border)s;
    text-align: center;
    font-weight: 700;
    font-size: 9pt;
    color: %(text)s;
}
QProgressBar::chunk {
    border-radius: 4px;
    background: %(accent)s;
}
QSlider::groove:horizontal {
    border-radius: 3px;
    height: 6px;
    background: %(border)s;
}
QSlider::handle:horizontal {
    background: %(accent)s;
    border-radius: 8px;
    width: 16px;
    height: 16px;
    margin: -5px 0;
}
QSlider::sub-page:horizontal {
    background: %(accent)s;
    border-radius: 3px;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
}
QScrollBar::handle:vertical {
    background: %(border)s;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: %(accent)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip {
    background: %(card)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    padding: 4px;
}
""" % t


def apply_adaptive_theme(widget: QWidget) -> None:
    """Apply the active QGIS/Qt palette without overriding font preferences."""
    widget.setStyleSheet(dock_stylesheet(widget.palette()))
