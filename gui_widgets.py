"""Fluent 风格的通用控件与图片加载器。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkDiskCache,
    QNetworkReply,
    QNetworkRequest,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import e6core
import gui_theme as theme
from gui_theme import make_icon, paint_icon

SMOKE = os.environ.get("E6DL_SMOKE") == "1"
CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "E6Dler" / "image_cache"


def tok():
    return theme.current()


def cover_pixmap(pix: QPixmap, size: QSize) -> QPixmap:
    if pix.isNull():
        return pix
    scaled = pix.scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    x = max(0, (scaled.width() - size.width()) // 2)
    y = max(0, (scaled.height() - size.height()) // 2)
    return scaled.copy(x, y, size.width(), size.height())


class ImageLoader(QObject):
    """带磁盘缓存的异步图片加载器（缩略图与大图共用）。"""

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache = QNetworkDiskCache(self)
            cache.setCacheDirectory(str(CACHE_DIR))
            cache.setMaximumCacheSize(256 * 1024 * 1024)
            self.manager.setCache(cache)
        except Exception:
            pass
        self.user_agent = "E621Downloader/1.5 (anonymous)"
        self._active: set[QNetworkReply] = set()

    def set_user_agent(self, ua: str) -> None:
        self.user_agent = ua

    def load(self, url: str, callback: Callable[[Optional[QPixmap], Optional[str]], None], owner: Optional[QObject] = None):
        if not e6core.is_online():
            QTimer.singleShot(0, lambda: _safe_call(callback, None, "单机模式已禁用联网，图片不再加载"))
            return None
        if SMOKE or not url:
            QTimer.singleShot(0, lambda: _safe_call(callback, None, "smoke"))
            return None
        req = QNetworkRequest(QUrl(url))
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, self.user_agent)
        req.setAttribute(
            QNetworkRequest.Attribute.CacheLoadControlAttribute,
            QNetworkRequest.CacheLoadControl.PreferCache,
        )
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute, QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        reply = self.manager.get(req)
        if owner is not None:
            reply.setParent(owner)
        self._active.add(reply)

        def done() -> None:
            self._active.discard(reply)
            data = reply.readAll()
            if reply.error() == QNetworkReply.NetworkError.NoError:
                pix = QPixmap()
                if pix.loadFromData(data) and not pix.isNull():
                    _safe_call(callback, pix, None)
                else:
                    _safe_call(callback, None, "图片解码失败")
            else:
                _safe_call(callback, None, reply.errorString())
            reply.deleteLater()

        reply.finished.connect(done)
        return reply

    def clear_cache(self) -> None:
        cache = self.manager.cache()
        if cache:
            cache.clear()


def _safe_call(callback, *args) -> None:
    try:
        callback(*args)
    except RuntimeError:
        pass


class FlowLayout(QLayout):
    """自动换行布局，用于响应式卡片网格。"""

    def __init__(self, parent: Optional[QWidget] = None, margin: int = 0, spacing: int = 16):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._spacing = spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y = effective.x(), effective.y()
        line_height = 0
        for item in self._items:
            widget = item.widget()
            if widget is not None and widget.isHidden():
                continue
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + self._spacing
                next_x = x + hint.width() + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


class NavItem(QWidget):
    clicked = Signal()

    def __init__(self, icon_name: str, text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.text = text
        self._selected = False
        self._hover = False
        self._keyboard_focus = False
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAccessibleName(text)

    def set_selected(self, selected: bool) -> None:
        if self._selected != selected:
            self._selected = selected
            self.update()

    def is_selected(self) -> bool:
        return self._selected

    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event):  # noqa: N802
        self._keyboard_focus = event.reason() in (
            Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
        )
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):  # noqa: N802
        self._keyboard_focus = False
        self.update()
        super().focusOutEvent(event)

    def paintEvent(self, _event):  # noqa: N802
        t = tok()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(6, 2, -6, -2)
        if self._selected:
            p.setBrush(QColor(t.control_hover))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, 6, 6)
        elif self._hover:
            p.setBrush(QColor(t.control))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, 6, 6)
        if self._selected:
            p.setBrush(QColor(t.accent))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(6, rect.center().y() - 8, 3, 16), 1.5, 1.5)
        color = QColor(t.text if (self._selected or self._hover) else t.text_secondary)
        icon_rect = QRectF(24, (self.height() - 18) / 2, 18, 18)
        paint_icon(p, self.icon_name, icon_rect, color, 1.5)
        p.setPen(QPen(QColor(t.text if self._selected else t.text_secondary)))
        font = self.font()
        font.setWeight(QFont.Weight.DemiBold if self._selected else QFont.Weight.Normal)
        p.setFont(font)
        p.drawText(
            QRectF(50, 0, self.width() - 62, self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.text,
        )
        if self.hasFocus() and self._keyboard_focus:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(t.accent), 2))
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 5, 5)
        p.end()


class CaptionButton(QPushButton):
    """标题栏按钮：QPushButton 基类保证点击信号可用，外观全部自绘。"""

    def __init__(self, kind: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.kind = kind
        self._hover = False
        self.setFlat(True)
        self.setFixedSize(46, 32)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setAccessibleName({"min": "最小化", "max": "最大化 / 还原", "close": "关闭"}[kind])
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event):  # noqa: N802
        t = tok()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._hover:
            if self.kind == "close":
                p.fillRect(self.rect(), QColor("#C42B1C" if not t.is_dark else "#C42B1C"))
            else:
                p.fillRect(self.rect(), QColor(t.control_hover))
        color = QColor("#FFFFFF" if self._hover and self.kind == "close" else t.text)
        p.setPen(QPen(color, 1.0))
        cx, cy = self.width() / 2, self.height() / 2
        if self.kind == "min":
            p.drawLine(QPoint(int(cx - 5), int(cy + 0.5)), QPoint(int(cx + 5), int(cy + 0.5)))
        elif self.kind == "max":
            p.drawRect(QRect(int(cx - 5), int(cy - 5), 10, 10))
        elif self.kind == "restore":
            p.drawRect(QRect(int(cx - 5), int(cy - 3), 8, 8))
            p.drawLine(QPoint(int(cx - 1), int(cy - 5)), QPoint(int(cx + 5), int(cy - 5)))
            p.drawLine(QPoint(int(cx + 5), int(cy - 5)), QPoint(int(cx + 5), int(cy + 1)))
        else:
            p.drawLine(QPoint(int(cx - 5), int(cy - 5)), QPoint(int(cx + 5), int(cy + 5)))
            p.drawLine(QPoint(int(cx + 5), int(cy - 5)), QPoint(int(cx - 5), int(cy + 5)))
        if self.hasFocus() and self.kind != "close":
            p.setPen(QPen(QColor(t.accent), 1))
            p.drawRect(self.rect().adjusted(2, 2, -3, -3))
        p.end()


class PostCard(QWidget):
    clicked = Signal(dict)
    checkedChanged = Signal(dict, bool)

    CARD_W = 212
    CARD_H = 258
    IMAGE_H = 172

    def __init__(self, post: dict, loader: ImageLoader, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.post = post
        self.loader = loader
        self._pix: Optional[QPixmap] = None
        self._hover = False
        self.selectable = False
        self.checked = False
        self._right_inset = 0
        self.setFixedSize(self.CARD_W, self.CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAccessibleName(f"作品 {post.get('id', '')}")
        preview = (post.get("preview") or {}).get("url") or ""
        self._preview_url = preview
        if preview:
            loader.load(preview, self._on_image, self)

    def _on_image(self, pix: Optional[QPixmap], _error: Optional[str]) -> None:
        if pix is not None and not pix.isNull():
            self._pix = pix
            self.update()

    def set_selectable(self, on: bool) -> None:
        """切换批选模式：开启后右侧空出勾选区域，关闭时清空勾选状态。"""
        self.selectable = bool(on)
        self._right_inset = 26 if self.selectable else 0
        if not self.selectable:
            self.checked = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update()

    def set_checked(self, checked: bool) -> None:
        checked = bool(checked)
        if self.checked != checked:
            self.checked = checked
            self.update()

    def is_checked(self) -> bool:
        return self.checked

    def toggle_checked(self) -> None:
        self.checked = not self.checked
        self.update()

    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            if self.selectable:
                self.toggle_checked()
                self.checkedChanged.emit(self.post, self.checked)
            else:
                self.clicked.emit(self.post)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self.selectable:
                self.toggle_checked()
                self.checkedChanged.emit(self.post, self.checked)
            else:
                self.clicked.emit(self.post)
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event):  # noqa: N802
        t = tok()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        outer = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.selectable and self.checked:
            p.setBrush(QColor(t.card_hover))
            p.setPen(QPen(QColor(t.accent), 2))
        else:
            p.setBrush(QColor(t.card_hover if self._hover else t.card))
            p.setPen(QPen(QColor(t.stroke_strong if self._hover else t.stroke), 1))
        p.drawRoundedRect(outer, 8, 8)

        img_rect = QRectF(9, 9, self.width() - 18, self.IMAGE_H)
        clip = QPainterPath()
        clip.addRoundedRect(img_rect, 5, 5)
        p.save()
        p.setClipPath(clip)
        if self._pix is not None:
            p.drawPixmap(img_rect.toRect(), cover_pixmap(self._pix, img_rect.size().toSize()))
        else:
            p.fillRect(img_rect, QColor(t.image_bg))
            paint_icon(
                p,
                "image",
                QRectF(img_rect.center().x() - 13, img_rect.center().y() - 13, 26, 26),
                QColor(t.text_tertiary),
                1.4,
            )
        p.restore()

        if self.selectable:
            box = QRectF(img_rect.left() + 8, img_rect.top() + 8, 20, 20)
            if self.checked:
                p.setBrush(QColor(t.accent))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(box, 5, 5)
                paint_icon(p, "check", box.adjusted(4, 4, -4, -4), QColor(t.on_accent), 1.8)
            else:
                p.setBrush(QColor(0, 0, 0, 110))
                p.setPen(QPen(QColor(255, 255, 255, 200), 1.4))
                p.drawRoundedRect(box, 5, 5)

        rating = self.post.get("rating", "")
        if rating:
            color = {"s": t.success, "q": "#9D5D00" if not t.is_dark else "#FCE100"}.get(rating, t.danger)
            label = {"s": "安全", "q": "待定", "e": ""}.get(rating, "未知")
            if label:
                badge = QRectF(img_rect.right() - 46, img_rect.bottom() - 24, 38, 16)
                p.setBrush(QColor(0, 0, 0, 120))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(badge, 4, 4)
                p.setPen(QPen(QColor(color)))
                f = p.font()
                f.setPointSizeF(8.0)
                p.setFont(f)
                p.drawText(badge, Qt.AlignmentFlag.AlignCenter, label)
            else:
                # 明确（e）不再显示文字，仅用一个小圆点提示
                p.setBrush(QColor(color))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QRectF(img_rect.right() - 18, img_rect.bottom() - 18, 8, 8))

        if (self.post.get("file") or {}).get("ext", "").lower() in ("webm", "mp4", "swf"):
            play_x = img_rect.left() + (36 if self.selectable else 8)
            play_badge = QRectF(play_x, img_rect.top() + 8, 20, 20)
            p.setBrush(QColor(0, 0, 0, 130))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(play_badge)
            paint_icon(p, "play", play_badge.adjusted(5, 5, -5, -5), QColor("#FFFFFF"), 1)

        if self.post.get("is_favorited"):
            fav = QRectF(img_rect.right() - 30, img_rect.top() + 8, 22, 22)
            p.setBrush(QColor(0, 0, 0, 130))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(fav)
            paint_icon(p, "heart_filled", fav.adjusted(6, 6, -6, -6), QColor(t.accent), 1.2)

        text_x = 12
        text_w = self.width() - 24 - self._right_inset
        y = 9 + self.IMAGE_H + 8
        f = p.font()
        f.setPointSizeF(9.0)
        p.setFont(f)
        p.setPen(QPen(QColor(t.text_tertiary)))
        p.drawText(QRectF(text_x, y, text_w, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"#{self.post.get('id', '?')}")

        score = self.post.get("score") or {}
        total = score.get("total") if isinstance(score, dict) else score
        fav_count = self.post.get("fav_count", 0)
        f.setPointSizeF(9.5)
        p.setFont(f)
        p.setPen(QPen(QColor(t.text)))
        p.drawText(QRectF(text_x, y + 17, text_w, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"评分 {total if total is not None else '—'}")
        f.setPointSizeF(8.5)
        p.setFont(f)
        p.setPen(QPen(QColor(t.text_tertiary)))
        p.drawText(QRectF(text_x, y + 36, text_w, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"收藏 {fav_count}")

        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(t.accent), 2))
            p.drawRoundedRect(outer.adjusted(1, 1, -1, -1), 7, 7)
        p.end()


class FluentCheckBox(QCheckBox):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = QFontMetrics(self.font())
        return QSize(20 + (8 + fm.horizontalAdvance(self.text()) if self.text() else 0), max(24, fm.height() + 8))

    def paintEvent(self, _event):  # noqa: N802
        t = tok()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = QRectF(1, (self.height() - 16) / 2, 16, 16)
        checked = self.isChecked()
        p.setPen(QPen(QColor(t.accent if checked or self.hasFocus() else t.stroke_strong), 1.5))
        p.setBrush(QColor(t.accent if checked else t.input_bg))
        p.drawRoundedRect(box, 3, 3)
        if checked:
            paint_icon(p, "check", box.adjusted(2.5, 2.5, -2.5, -2.5), QColor(t.on_accent), 1.8)
        if self.text():
            p.setPen(QPen(QColor(t.text if self.isEnabled() else t.text_tertiary)))
            p.drawText(
                QRectF(28, 0, self.width() - 28, self.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                self.text(),
            )
        p.end()


class FluentComboBox(QComboBox):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(30)
        self._arrow = QLabel(self)
        self._arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._arrow.setFixedSize(16, 16)
        self.refresh_theme()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._arrow.move(self.width() - 24, (self.height() - 16) // 2)

    def refresh_theme(self) -> None:
        self._arrow.setPixmap(make_icon("chevron_down", tok().text_secondary, 14).pixmap(14, 14))


class SegmentedControl(QWidget):
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], value: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.options = options
        self.value = value or options[0][0]
        self._hover = -1
        self.setFixedHeight(34)
        self.setMinimumWidth(90 * len(options) + 8)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAccessibleName("选项切换")

    def set_value(self, value: str) -> None:
        if value != self.value:
            self.value = value
            self.update()

    def _index_at(self, pos: QPoint) -> int:
        if not self.rect().contains(pos):
            return -1
        width = (self.width() - 8) / len(self.options)
        idx = int((pos.x() - 4) // width)
        return max(0, min(len(self.options) - 1, idx))

    def mouseMoveEvent(self, event):  # noqa: N802
        idx = self._index_at(event.position().toPoint())
        if idx != self._hover:
            self._hover = idx
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        idx = self._index_at(event.position().toPoint())
        if idx >= 0:
            self.value = self.options[idx][0]
            self.changed.emit(self.value)
            self.update()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            keys = [k for k, _ in self.options]
            idx = keys.index(self.value)
            idx = (idx + (1 if event.key() == Qt.Key.Key_Right else -1)) % len(keys)
            self.value = keys[idx]
            self.changed.emit(self.value)
            self.update()
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event):  # noqa: N802
        t = tok()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor(t.control))
        p.setPen(QPen(QColor(t.stroke), 1))
        p.drawRoundedRect(outer, 6, 6)
        width = (self.width() - 8) / len(self.options)
        for i, (key, label) in enumerate(self.options):
            r = QRectF(4 + i * width, 4, width, self.height() - 8)
            selected = key == self.value
            if selected:
                p.setBrush(QColor(t.accent))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(r.adjusted(1, 0, -1, 0), 4, 4)
            elif i == self._hover:
                p.setBrush(QColor(t.control_hover))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(r.adjusted(1, 0, -1, 0), 4, 4)
            p.setPen(QPen(QColor(t.on_accent if selected else t.text)))
            f = p.font()
            f.setPointSizeF(9.0)
            f.setWeight(QFont.Weight.DemiBold if selected else QFont.Weight.Normal)
            p.setFont(f)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(t.accent), 2))
            p.drawRoundedRect(outer.adjusted(1, 1, -1, -1), 5, 5)
        p.end()


class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._checked = checked
        self._hover = False
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("开关")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, value: bool) -> None:
        if value != self._checked:
            self._checked = value
            self.update()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self.toggled.emit(self._checked)
            self.update()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._checked = not self._checked
            self.toggled.emit(self._checked)
            self.update()
            return
        super().keyPressEvent(event)

    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event):  # noqa: N802
        t = tok()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track = QRectF(2, 4, 40, 16)
        enabled = self.isEnabled()
        if not enabled:
            p.setBrush(QColor(t.control_pressed))
            p.setPen(QPen(QColor(t.stroke), 1))
        elif self._checked:
            p.setBrush(QColor(t.accent_hover if self._hover else t.accent))
            p.setPen(Qt.PenStyle.NoPen)
        else:
            p.setBrush(QColor(t.control))
            p.setPen(QPen(QColor(t.stroke_strong), 1))
        p.drawRoundedRect(track, 8, 8)
        knob = QRectF(34 if self._checked else 6, 6, 12, 12)
        if not enabled:
            p.setBrush(QColor(t.text_tertiary))
        else:
            p.setBrush(QColor(t.on_accent if self._checked else t.text_secondary))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(knob)
        if self.hasFocus() and enabled:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(t.accent), 1))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        p.end()


class InfoBar(QFrame):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setVisible(False)
        self._kind = "info"
        self._text = QLabel()
        self._text.setWordWrap(True)
        self._icon = QLabel()
        self._icon.setFixedSize(18, 18)
        self._close = QPushButton()
        self._close.setProperty("subtle", True)
        self._close.setFixedSize(24, 24)
        self._close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close.setAccessibleName("关闭提示")
        self._close.clicked.connect(self.hide)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 8, 8)
        lay.setSpacing(10)
        lay.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self._text, 1)
        lay.addWidget(self._close, 0, Qt.AlignmentFlag.AlignTop)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        t = tok()
        self._close.setIcon(make_icon("close", t.text_secondary, 12))
        self._apply_kind_style()

    def _apply_kind_style(self) -> None:
        t = tok()
        colors = {
            "info": t.accent,
            "success": t.success,
            "warning": "#9D5D00" if not t.is_dark else "#FCE100",
            "error": t.danger,
        }
        color = colors.get(self._kind, t.accent)
        self._icon.setPixmap(make_icon(self._kind if self._kind != "info" else "info", color, 16).pixmap(16, 16))
        self.setStyleSheet(
            f"QFrame {{ background: {t.card}; border: 1px solid {t.stroke}; border-left: 3px solid {color}; border-radius: 6px; }}"
        )

    def show_message(self, text: str, kind: str = "info", timeout: int = 6000) -> None:
        self._kind = kind
        self._text.setText(text)
        self._apply_kind_style()
        self.setVisible(True)
        if timeout > 0:
            self._timer.start(timeout)
        else:
            self._timer.stop()


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, description: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.icon_name = icon_name
        self._icon = QLabel()
        self._icon.setFixedSize(48, 48)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title = QLabel(title)
        self._title.setObjectName("SectionTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._desc = QLabel(description)
        self._desc.setObjectName("Secondary")
        self._desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._desc.setWordWrap(True)
        self._action = QPushButton()
        self._action.setProperty("accent", True)
        self._action.setVisible(False)
        self._action.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_cb: Optional[Callable[[], None]] = None
        self._action.clicked.connect(self._on_action_clicked)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 48, 24, 48)
        lay.setSpacing(10)
        lay.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._title)
        lay.addWidget(self._desc)
        lay.addSpacing(6)
        lay.addWidget(self._action, 0, Qt.AlignmentFlag.AlignHCenter)
        self.refresh_theme()

    def set_action(self, text: str, callback) -> None:
        self._action.setText(text)
        self._action_cb = callback
        self._action.setVisible(True)

    def _on_action_clicked(self) -> None:
        if self._action_cb is not None:
            self._action_cb()

    def set_text(self, title: str, description: str) -> None:
        self._title.setText(title)
        self._desc.setText(description)

    def refresh_theme(self) -> None:
        self._icon.setPixmap(make_icon(self.icon_name, tok().text_tertiary, 40).pixmap(40, 40))
        self._action.setIcon(make_icon("login", tok().on_accent, 15))


class Scrim(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setGeometry(parent.rect())

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(tok().scrim))
        p.end()


class ContentDialog(QDialog):
    """Fluent ContentDialog：无边框、居中、带遮罩的模态对话框。"""

    def __init__(self, parent: QWidget, title: str, width: int = 440):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self._scrim: Optional[Scrim] = None
        self._width = width
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.card = QFrame()
        self.card.setObjectName("DialogCard")
        root.addWidget(self.card)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(16)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-size: 19px; font-weight: 600;")
        self.title.setWordWrap(True)
        lay.addWidget(self.title)
        self.content = QVBoxLayout()
        self.content.setSpacing(10)
        lay.addLayout(self.content)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        self.actions.addStretch(1)
        lay.addLayout(self.actions)

    def add_action(self, text: str, primary: bool = False, danger: bool = False, on_click=None) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            btn.setProperty("accent", True)
            btn.setDefault(True)
            btn.setAutoDefault(True)
        if danger:
            btn.setProperty("danger", True)
        if on_click:
            btn.clicked.connect(on_click)
        self.actions.addWidget(btn)
        return btn

    def center_on_parent(self) -> None:
        parent = self.parentWidget()
        self.card.setMinimumWidth(self._width)
        self.adjustSize()
        if parent is not None:
            geo = parent.window().frameGeometry()
            self.move(geo.center() - self.rect().center())

    def first_focusable(self) -> Optional[QWidget]:
        """返回对话框内首个可聚焦控件，QLineEdit 优先。"""
        for edit in self.findChildren(QLineEdit):
            if edit.isEnabled() and not edit.isReadOnly() and edit.isVisibleTo(self):
                return edit
        for widget in self.findChildren(QWidget):
            if widget.isEnabled() and widget.isVisibleTo(self):
                if widget.focusPolicy() != Qt.FocusPolicy.NoFocus:
                    return widget
        return None

    def exec_dialog(self) -> int:
        parent = self.parentWidget()
        try:
            self.ensurePolished()
            self.adjustSize()
            self.setMinimumWidth(self._width + 48)
            self.resize(
                max(self.minimumWidth(), self.sizeHint().width()),
                max(self.minimumHeight(), self.sizeHint().height()),
            )
            if parent is not None:
                self._scrim = Scrim(parent.window())
                self._scrim.show()
                self._scrim.raise_()
            self.center_on_parent()
            self.show()
            self.raise_()
            self.activateWindow()
            handle = self.windowHandle()
            if handle is not None:
                handle.requestActivate()
            first = self.first_focusable()
            if first is not None:
                first.setFocus()
            return self.exec()
        finally:
            if self._scrim is not None:
                self._scrim.hide()
                self._scrim.deleteLater()
                self._scrim = None

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def refresh_theme(self) -> None:
        for btn in self.findChildren(QPushButton):
            name = btn.property("_icon_name")
            if name:
                btn.setIcon(make_icon(name, tok().text, 14))


def confirm(parent: QWidget, title: str, message: str, confirm_text: str = "确定", danger: bool = False) -> bool:
    dlg = ContentDialog(parent, title, 400)
    label = QLabel(message)
    label.setWordWrap(True)
    label.setObjectName("Secondary")
    dlg.content.addWidget(label)
    result = {"ok": False}

    def ok() -> None:
        result["ok"] = True
        dlg.accept()

    dlg.add_action("取消", on_click=dlg.reject)
    dlg.add_action(confirm_text, primary=not danger, danger=danger, on_click=ok)
    dlg.exec_dialog()
    return result["ok"]


def section_card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(12)
    return frame, lay


def chip(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("chip", True)
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return label


def set_icon(btn: QPushButton, name: str, role: str = "text", size: int = 16) -> None:
    t = tok()
    color = {"text": t.text, "secondary": t.text_secondary, "accent": t.on_accent, "danger": t.danger}.get(role, t.text)
    btn.setIcon(make_icon(name, color, size))
    btn.setProperty("_icon_name", name)
    btn.setProperty("_icon_role", role)


def refresh_icons(root: QWidget) -> None:
    t = tok()
    for btn in root.findChildren(QPushButton):
        name = btn.property("_icon_name")
        if not name:
            continue
        role = btn.property("_icon_role") or "text"
        color = {"text": t.text, "secondary": t.text_secondary, "accent": t.on_accent, "danger": t.danger}.get(role, t.text)
        btn.setIcon(make_icon(name, color, 16))
    for combo in root.findChildren(FluentComboBox):
        combo.refresh_theme()
    for bar in root.findChildren(InfoBar):
        bar.refresh_theme()
    for state in root.findChildren(EmptyState):
        state.refresh_theme()
