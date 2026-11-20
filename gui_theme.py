"""Fluent Design 主题令牌与全局样式。"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Tokens:
    bg_solid: str
    sidebar: str
    card: str
    card_hover: str
    text: str
    text_secondary: str
    text_tertiary: str
    accent: str
    accent_hover: str
    accent_pressed: str
    on_accent: str
    stroke: str
    stroke_strong: str
    control: str
    control_hover: str
    control_pressed: str
    input_bg: str
    selection: str
    scroll: str
    scroll_hover: str
    danger: str
    danger_hover: str
    success: str
    popup: str
    scrim: str
    image_bg: str
    is_dark: bool = False


LIGHT = Tokens(
    bg_solid="#F3F3F3",
    sidebar="#70FFFFFF",
    card="#96FFFFFF",
    card_hover="#D0FFFFFF",
    text="#1A1A1A",
    text_secondary="#5C5C5C",
    text_tertiary="#7A7A7A",
    accent="#005FB8",
    accent_hover="#1A6FC4",
    accent_pressed="#004C92",
    on_accent="#FFFFFF",
    stroke="#1A000000",
    stroke_strong="#34000000",
    control="#B4FFFFFF",
    control_hover="#EBFFFFFF",
    control_pressed="#C0EFEFEF",
    input_bg="#CDFFFFFF",
    selection="#1E005FB8",
    scroll="#46000000",
    scroll_hover="#78000000",
    danger="#C42B1C",
    danger_hover="#B02419",
    success="#0F7B0F",
    popup="#FBFBFB",
    scrim="#5A000000",
    image_bg="#16000000",
)

DARK = Tokens(
    bg_solid="#202020",
    sidebar="#0AFFFFFF",
    card="#10FFFFFF",
    card_hover="#1CFFFFFF",
    text="#FFFFFF",
    text_secondary="#C7C7C7",
    text_tertiary="#9A9A9A",
    accent="#60CDFF",
    accent_hover="#7ED6FF",
    accent_pressed="#4BB4E6",
    on_accent="#062B3D",
    stroke="#16FFFFFF",
    stroke_strong="#30FFFFFF",
    control="#12FFFFFF",
    control_hover="#1EFFFFFF",
    control_pressed="#0CFFFFFF",
    input_bg="#0EFFFFFF",
    selection="#2C60CDFF",
    scroll="#46FFFFFF",
    scroll_hover="#78FFFFFF",
    danger="#FF99A4",
    danger_hover="#FFB3BC",
    success="#6CCB5F",
    popup="#2C2C2C",
    scrim="#78000000",
    image_bg="#3C000000",
    is_dark=True,
)

ACCENT = "#005FB8"

_CURRENT: Tokens = LIGHT


def tokens(dark: bool) -> Tokens:
    return DARK if dark else LIGHT


def current() -> Tokens:
    return _CURRENT


def set_current(t: Tokens) -> None:
    global _CURRENT
    _CURRENT = t


def system_dark() -> bool:
    try:
        return QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def resolve_dark(mode: str) -> bool:
    if mode == "dark":
        return True
    if mode == "light":
        return False
    return system_dark()


def app_font() -> QFont:
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei"])
    font.setPointSizeF(10.0)
    font.setHintingPreference(QFont.HintingPreference.PreferDefaultHinting)
    return font


def _palette(t: Tokens) -> QPalette:
    p = QPalette()
    window = QColor(t.bg_solid)
    text = QColor(t.text)
    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, QColor(t.popup))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(t.card_hover if not t.is_dark else "#2A2A2A"))
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, QColor(t.bg_solid))
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.Highlight, QColor(t.accent))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(t.on_accent))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(t.popup))
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(t.text_tertiary))
    p.setColor(QPalette.ColorRole.Link, QColor(t.accent))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(t.text_tertiary))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(t.text_tertiary))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(t.text_tertiary))
    return p


def build_qss(t: Tokens) -> str:
    return f"""
QWidget {{
    color: {t.text};
}}
QMainWindow, QWidget#Root, QWidget#Page, QWidget#PageBody, QScrollArea#PageScroll,
QScrollArea#PageScroll > QWidget > QWidget {{
    background: transparent;
    border: none;
}}
QWidget#Sidebar {{
    background: {t.sidebar};
    border-right: 1px solid {t.stroke};
}}
QLabel#PageTitle {{
    font-size: 27px;
    font-weight: 600;
    color: {t.text};
}}
QLabel#PageSubtitle, QLabel#Secondary {{
    color: {t.text_secondary};
    font-size: 12px;
}}
QLabel#SectionTitle {{
    font-size: 15px;
    font-weight: 600;
    color: {t.text};
}}
QLabel#Caption {{
    color: {t.text_tertiary};
    font-size: 11px;
}}
QLabel#AppTitle {{
    font-size: 12px;
    color: {t.text_secondary};
}}
QLabel#LargeNumber {{
    font-size: 20px;
    font-weight: 600;
}}
QFrame#Card {{
    background: {t.card};
    border: 1px solid {t.stroke};
    border-radius: 8px;
}}
QFrame#Divider {{
    background: {t.stroke};
    border: none;
    max-height: 1px;
}}
QPushButton {{
    background: {t.control};
    border: 1px solid {t.stroke};
    border-radius: 4px;
    padding: 5px 13px;
    color: {t.text};
    min-height: 20px;
}}
QPushButton:hover {{
    background: {t.control_hover};
    border-color: {t.stroke_strong};
}}
QPushButton:pressed {{
    background: {t.control_pressed};
    color: {t.text_secondary};
}}
QPushButton:focus {{
    border: 1px solid {t.accent};
}}
QPushButton:disabled {{
    color: {t.text_tertiary};
    background: {t.control_pressed};
    border-color: {t.stroke};
}}
QPushButton[accent="true"] {{
    background: {t.accent};
    border-color: {t.accent};
    color: {t.on_accent};
    font-weight: 600;
}}
QPushButton[accent="true"]:hover {{
    background: {t.accent_hover};
    border-color: {t.accent_hover};
}}
QPushButton[accent="true"]:pressed {{
    background: {t.accent_pressed};
    border-color: {t.accent_pressed};
}}
QPushButton[danger="true"] {{
    color: {t.danger};
}}
QPushButton[subtle="true"] {{
    background: transparent;
    border-color: transparent;
}}
QPushButton[subtle="true"]:hover {{
    background: {t.control_hover};
}}
QPushButton[subtle="true"]:pressed {{
    background: {t.control_pressed};
}}
QLineEdit, QPlainTextEdit, QTextEdit {{
    background: {t.input_bg};
    border: 1px solid {t.stroke};
    border-bottom: 2px solid {t.stroke_strong};
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: {t.selection};
    selection-color: {t.text};
}}
QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover {{
    border-color: {t.stroke_strong};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-bottom: 2px solid {t.accent};
    background: {t.input_bg};
}}
QLineEdit:disabled {{
    color: {t.text_tertiary};
}}
QComboBox {{
    background: {t.input_bg};
    border: 1px solid {t.stroke};
    border-bottom: 2px solid {t.stroke_strong};
    border-radius: 4px;
    padding: 5px 8px;
}}
QComboBox:hover {{
    border-color: {t.stroke_strong};
}}
QComboBox:focus {{
    border-bottom: 2px solid {t.accent};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
}}
QComboBox QAbstractItemView {{
    background: {t.popup};
    border: 1px solid {t.stroke};
    border-radius: 8px;
    padding: 4px;
    outline: 0;
    selection-background-color: {t.selection};
    selection-color: {t.text};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 14px;
    margin: 2px 2px 2px 4px;
}}
QScrollBar::handle:vertical {{
    background: {t.scroll};
    border-radius: 3px;
    min-height: 36px;
    margin: 0 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t.scroll_hover};
}}
QScrollBar::handle:vertical:pressed {{
    background: {t.accent};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    background: none;
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 14px;
    margin: 4px 2px 2px 2px;
}}
QScrollBar::handle:horizontal {{
    background: {t.scroll};
    border-radius: 3px;
    min-width: 36px;
    margin: 2px 0;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t.scroll_hover};
}}
QScrollBar::handle:horizontal:pressed {{
    background: {t.accent};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    background: none;
    width: 0;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
QListWidget {{
    background: transparent;
    border: none;
    outline: 0;
}}
QListWidget::item {{
    border-radius: 4px;
    padding: 4px 6px;
}}
QListWidget::item:hover {{
    background: {t.control_hover};
}}
QListWidget::item:selected {{
    background: {t.selection};
    color: {t.text};
}}
QProgressBar {{
    background: {t.control_pressed};
    border: none;
    border-radius: 2px;
    max-height: 4px;
    min-height: 4px;
}}
QProgressBar::chunk {{
    background: {t.accent};
    border-radius: 2px;
}}
QToolTip {{
    background: {t.popup};
    color: {t.text};
    border: 1px solid {t.stroke};
    padding: 4px 8px;
}}
QCheckBox {{
    spacing: 8px;
    color: {t.text};
}}
QLabel[chip="true"] {{
    background: {t.selection};
    border-radius: 4px;
    padding: 2px 7px;
    color: {t.text_secondary};
    font-size: 11px;
}}
QLabel[badge="true"] {{
    background: {t.control_hover};
    border-radius: 4px;
    padding: 1px 6px;
    color: {t.text_secondary};
    font-size: 11px;
}}
QFrame#DialogCard {{
    background: {t.popup};
    border: 1px solid {t.stroke_strong};
    border-radius: 12px;
}}
QFrame#LoginBar {{
    background: {t.card};
    border: 1px solid {t.stroke};
    border-radius: 10px;
}}
QMenu {{
    background: {t.popup};
    border: 1px solid {t.stroke};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 18px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: {t.selection};
}}
"""


def apply_theme(app: QApplication, dark: bool) -> Tokens:
    t = tokens(dark)
    set_current(t)
    app.setPalette(_palette(t))
    app.setStyleSheet(build_qss(t))
    return t


# --------------------------------------------------------------------------- #
# Fluent 线性图标（用 QPainter 绘制，避免混用图标包与 emoji）
# --------------------------------------------------------------------------- #


def _draw_gear(path_pen: QPainter, rect: QRectF, color: QColor, width: float) -> None:
    import math

    cx, cy = rect.center().x(), rect.center().y()
    radius = min(rect.width(), rect.height()) / 2
    points = []
    for i in range(16):
        angle = math.radians(i * 22.5 - 90)
        r = radius * (0.94 if i % 2 == 0 else 0.70)
        points.append(QPointF(cx + math.cos(angle) * r, cy + math.sin(angle) * r))
    gear = QPainterPath(points[0])
    for point in points[1:]:
        gear.lineTo(point)
    gear.closeSubpath()
    path_pen.strokePath(gear, QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    inner = QPainterPath()
    inner.addEllipse(QPointF(cx, cy), radius * 0.3, radius * 0.3)
    path_pen.strokePath(inner, QPen(color, width))


def paint_icon(painter: QPainter, name: str, rect: QRectF, color: QColor, width: float = 1.5) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    r = rect.adjusted(width / 2, width / 2, -width / 2, -width / 2)
    x, y, w, h = r.x(), r.y(), r.width(), r.height()

    def line(x1, y1, x2, y2):
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    if name in ("discover", "compass"):
        painter.drawEllipse(r)
        path = QPainterPath(QPointF(x + w * 0.62, y + h * 0.34))
        path.lineTo(x + w * 0.54, y + h * 0.56)
        path.lineTo(x + w * 0.38, y + h * 0.66)
        path.lineTo(x + w * 0.46, y + h * 0.44)
        path.closeSubpath()
        painter.strokePath(path, pen)
    elif name == "search":
        painter.drawEllipse(QRectF(x + w * 0.06, y + h * 0.06, w * 0.64, h * 0.64))
        line(x + w * 0.66, y + h * 0.66, x + w * 0.94, y + h * 0.94)
    elif name == "heart":
        path = QPainterPath(QPointF(x + w * 0.5, y + h * 0.85))
        path.cubicTo(x + w * 0.05, y + h * 0.55, x + w * 0.05, y + h * 0.12, x + w * 0.5, y + h * 0.3)
        path.cubicTo(x + w * 0.95, y + h * 0.12, x + w * 0.95, y + h * 0.55, x + w * 0.5, y + h * 0.85)
        painter.strokePath(path, pen)
    elif name == "heart_filled":
        path = QPainterPath(QPointF(x + w * 0.5, y + h * 0.85))
        path.cubicTo(x + w * 0.05, y + h * 0.55, x + w * 0.05, y + h * 0.12, x + w * 0.5, y + h * 0.3)
        path.cubicTo(x + w * 0.95, y + h * 0.12, x + w * 0.95, y + h * 0.55, x + w * 0.5, y + h * 0.85)
        painter.fillPath(path, color)
    elif name == "shield":
        path = QPainterPath(QPointF(x + w * 0.5, y + h * 0.06))
        path.lineTo(x + w * 0.88, y + h * 0.2)
        path.lineTo(x + w * 0.84, y + h * 0.56)
        path.cubicTo(x + w * 0.8, y + h * 0.76, x + w * 0.66, y + h * 0.9, x + w * 0.5, y + h * 0.96)
        path.cubicTo(x + w * 0.34, y + h * 0.9, x + w * 0.2, y + h * 0.76, x + w * 0.16, y + h * 0.56)
        path.lineTo(x + w * 0.12, y + h * 0.2)
        path.closeSubpath()
        painter.strokePath(path, pen)
        line(x + w * 0.32, y + h * 0.5, x + w * 0.68, y + h * 0.5)
    elif name in ("settings", "gear"):
        _draw_gear(painter, r, color, width)
    elif name == "user":
        painter.drawEllipse(QRectF(x + w * 0.32, y + h * 0.08, w * 0.36, h * 0.36))
        path = QPainterPath(QPointF(x + w * 0.12, y + h * 0.94))
        path.cubicTo(x + w * 0.12, y + h * 0.58, x + w * 0.88, y + h * 0.58, x + w * 0.88, y + h * 0.94)
        painter.strokePath(path, pen)
    elif name == "download":
        line(x + w * 0.5, y + h * 0.1, x + w * 0.5, y + h * 0.66)
        line(x + w * 0.24, y + h * 0.42, x + w * 0.5, y + h * 0.68)
        line(x + w * 0.76, y + h * 0.42, x + w * 0.5, y + h * 0.68)
        line(x + w * 0.12, y + h * 0.9, x + w * 0.88, y + h * 0.9)
    elif name == "refresh":
        path = QPainterPath()
        path.arcMoveTo(QRectF(x + w * 0.12, y + h * 0.12, w * 0.76, h * 0.76), 40)
        path.arcTo(QRectF(x + w * 0.12, y + h * 0.12, w * 0.76, h * 0.76), 40, 285)
        painter.strokePath(path, pen)
        line(x + w * 0.74, y + h * 0.1, x + w * 0.86, y + h * 0.3)
        line(x + w * 0.62, y + h * 0.22, x + w * 0.86, y + h * 0.3)
    elif name == "back":
        line(x + w * 0.68, y + h * 0.12, x + w * 0.28, y + h * 0.5)
        line(x + w * 0.28, y + h * 0.5, x + w * 0.68, y + h * 0.88)
    elif name == "chevron_down":
        line(x + w * 0.24, y + h * 0.38, x + w * 0.5, y + h * 0.64)
        line(x + w * 0.76, y + h * 0.38, x + w * 0.5, y + h * 0.64)
    elif name == "external":
        line(x + w * 0.5, y + h * 0.1, x + w * 0.9, y + h * 0.1)
        line(x + w * 0.9, y + h * 0.1, x + w * 0.9, y + h * 0.5)
        line(x + w * 0.9, y + h * 0.1, x + w * 0.46, y + h * 0.54)
        path = QPainterPath(QPointF(x + w * 0.72, y + h * 0.58))
        path.lineTo(x + w * 0.72, y + h * 0.92)
        path.lineTo(x + w * 0.08, y + h * 0.92)
        path.lineTo(x + w * 0.08, y + h * 0.28)
        path.lineTo(x + w * 0.42, y + h * 0.28)
        painter.strokePath(path, pen)
    elif name == "login":
        line(x + w * 0.48, y + h * 0.1, x + w * 0.1, y + h * 0.1)
        line(x + w * 0.1, y + h * 0.1, x + w * 0.1, y + h * 0.9)
        line(x + w * 0.1, y + h * 0.9, x + w * 0.48, y + h * 0.9)
        line(x + w * 0.38, y + h * 0.5, x + w * 0.9, y + h * 0.5)
        line(x + w * 0.68, y + h * 0.28, x + w * 0.9, y + h * 0.5)
        line(x + w * 0.68, y + h * 0.72, x + w * 0.9, y + h * 0.5)
    elif name == "logout":
        line(x + w * 0.32, y + h * 0.1, x + w * 0.1, y + h * 0.1)
        line(x + w * 0.1, y + h * 0.1, x + w * 0.1, y + h * 0.9)
        line(x + w * 0.1, y + h * 0.9, x + w * 0.32, y + h * 0.9)
        line(x + w * 0.44, y + h * 0.5, x + w * 0.92, y + h * 0.5)
        line(x + w * 0.7, y + h * 0.28, x + w * 0.92, y + h * 0.5)
        line(x + w * 0.7, y + h * 0.72, x + w * 0.92, y + h * 0.5)
    elif name == "folder":
        path = QPainterPath(QPointF(x + w * 0.08, y + h * 0.24))
        path.lineTo(x + w * 0.4, y + h * 0.24)
        path.lineTo(x + w * 0.5, y + h * 0.34)
        path.lineTo(x + w * 0.92, y + h * 0.34)
        path.lineTo(x + w * 0.92, y + h * 0.86)
        path.lineTo(x + w * 0.08, y + h * 0.86)
        path.closeSubpath()
        painter.strokePath(path, pen)
    elif name == "plus":
        line(x + w * 0.5, y + h * 0.18, x + w * 0.5, y + h * 0.82)
        line(x + w * 0.18, y + h * 0.5, x + w * 0.82, y + h * 0.5)
    elif name == "minus":
        line(x + w * 0.18, y + h * 0.5, x + w * 0.82, y + h * 0.5)
    elif name == "close":
        line(x + w * 0.2, y + h * 0.2, x + w * 0.8, y + h * 0.8)
        line(x + w * 0.8, y + h * 0.2, x + w * 0.2, y + h * 0.8)
    elif name == "check":
        line(x + w * 0.16, y + h * 0.52, x + w * 0.42, y + h * 0.78)
        line(x + w * 0.42, y + h * 0.78, x + w * 0.86, y + h * 0.22)
    elif name == "info":
        painter.drawEllipse(r)
        line(x + w * 0.5, y + h * 0.44, x + w * 0.5, y + h * 0.74)
        painter.drawEllipse(QRectF(x + w * 0.46, y + h * 0.24, w * 0.08, h * 0.08))
    elif name == "warning":
        path = QPainterPath(QPointF(x + w * 0.5, y + h * 0.08))
        path.lineTo(x + w * 0.96, y + h * 0.9)
        path.lineTo(x + w * 0.04, y + h * 0.9)
        path.closeSubpath()
        painter.strokePath(path, pen)
        line(x + w * 0.5, y + h * 0.4, x + w * 0.5, y + h * 0.64)
        painter.drawEllipse(QRectF(x + w * 0.46, y + h * 0.72, w * 0.08, h * 0.08))
    elif name == "image":
        painter.drawRoundedRect(r, 3, 3)
        painter.drawEllipse(QRectF(x + w * 0.18, y + h * 0.2, w * 0.16, h * 0.16))
        path = QPainterPath(QPointF(x + w * 0.12, y + h * 0.82))
        path.lineTo(x + w * 0.36, y + h * 0.5)
        path.lineTo(x + w * 0.54, y + h * 0.7)
        path.lineTo(x + w * 0.68, y + h * 0.56)
        path.lineTo(x + w * 0.88, y + h * 0.82)
        painter.strokePath(path, pen)
    elif name == "sun":
        painter.drawEllipse(QRectF(x + w * 0.3, y + h * 0.3, w * 0.4, h * 0.4))
        for dx, dy in ((0.5, 0.04), (0.5, 0.96), (0.04, 0.5), (0.96, 0.5), (0.18, 0.18), (0.82, 0.82), (0.18, 0.82), (0.82, 0.18)):
            cx, cy = x + w * dx, y + h * dy
            line(cx + (0.5 - dx) * w * 0.12, cy + (0.5 - dy) * h * 0.12, cx, cy)
    elif name == "moon":
        path = QPainterPath()
        path.addEllipse(QRectF(x + w * 0.1, y + h * 0.1, w * 0.8, h * 0.8))
        cut = QPainterPath()
        cut.addEllipse(QRectF(x + w * 0.38, y + h * 0.02, w * 0.8, h * 0.8))
        painter.strokePath(path.subtracted(cut), pen)
    elif name == "monitor":
        painter.drawRoundedRect(QRectF(x + w * 0.08, y + h * 0.12, w * 0.84, h * 0.6), 3, 3)
        line(x + w * 0.5, y + h * 0.72, x + w * 0.5, y + h * 0.9)
        line(x + w * 0.3, y + h * 0.9, x + w * 0.7, y + h * 0.9)
    elif name == "trash":
        line(x + w * 0.14, y + h * 0.22, x + w * 0.86, y + h * 0.22)
        line(x + w * 0.38, y + h * 0.1, x + w * 0.62, y + h * 0.1)
        path = QPainterPath(QPointF(x + w * 0.22, y + h * 0.22))
        path.lineTo(x + w * 0.3, y + h * 0.92)
        path.lineTo(x + w * 0.7, y + h * 0.92)
        path.lineTo(x + w * 0.78, y + h * 0.22)
        painter.strokePath(path, pen)
        line(x + w * 0.42, y + h * 0.38, x + w * 0.42, y + h * 0.76)
        line(x + w * 0.58, y + h * 0.38, x + w * 0.58, y + h * 0.76)
    elif name == "play":
        path = QPainterPath(QPointF(x + w * 0.34, y + h * 0.18))
        path.lineTo(x + w * 0.82, y + h * 0.5)
        path.lineTo(x + w * 0.34, y + h * 0.82)
        path.closeSubpath()
        painter.fillPath(path, color)
    else:
        painter.drawEllipse(r)
    painter.restore()


def make_icon(name: str, color: str, size: int = 18) -> QIcon:
    icon = QIcon()
    for scale in (1, 2):
        pm = QPixmap(size * scale, size * scale)
        pm.setDevicePixelRatio(scale)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        paint_icon(p, name, QRectF(0, 0, size, size), QColor(color), 1.5)
        p.end()
        icon.addPixmap(pm)
    return icon
