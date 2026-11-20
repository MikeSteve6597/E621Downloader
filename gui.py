"""E6Dler 图形界面（Windows Fluent Design）。"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import traceback
from pathlib import Path

import requests

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    QStringListModel,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QIcon,
    QIntValidator,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCompleter,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyleFactory,
    QVBoxLayout,
    QWidget,
)

import e6core
import gui_theme as theme
from gui_widgets import (
    SMOKE,
    CaptionButton,
    ContentDialog,
    EmptyState,
    FluentCheckBox,
    FluentComboBox,
    FlowLayout,
    ImageLoader,
    InfoBar,
    NavItem,
    PostCard,
    SegmentedControl,
    ToggleSwitch,
    chip,
    confirm,
    refresh_icons,
    section_card,
    set_icon,
)

APP_TITLE = "E621Downloader"
NAV_ITEMS = [
    ("discover", "发现", "discover"),
    ("search", "搜索下载", "search"),
    ("favorites", "我的收藏", "heart"),
    ("blacklist", "黑名单", "shield"),
    ("settings", "设置", "settings"),
]


def resource_path(name: str) -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / name
    return Path(__file__).resolve().parent / name


def friendly_error(exc: Exception) -> str:
    if isinstance(exc, e6core.OfflineModeError):
        return "当前为单机模式，已禁用联网。请在「设置 › 运行模式」切换为在线模式。"
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        if code == 401:
            return "登录状态已失效，请在左下角账户菜单重新登录。"
        if code == 403:
            return "没有权限执行该操作。"
        if code == 404:
            return "请求的内容不存在。"
        if code == 429:
            return "请求过于频繁（HTTP 429），请稍后再试。"
        if code >= 500:
            return "e621 服务器暂时不可用，请稍后再试。"
        return f"请求失败（HTTP {code}）。"
    if isinstance(exc, requests.Timeout):
        return "网络请求超时，请检查网络后重试。"
    if isinstance(exc, requests.ConnectionError):
        return "无法连接到 e621，请检查网络或代理设置。"
    return str(exc) or "未知错误"


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def page_header(title: str, subtitle: str, actions: list[QWidget] | None = None) -> QWidget:
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    col = QVBoxLayout()
    col.setSpacing(2)
    title_label = QLabel(title)
    title_label.setObjectName("PageTitle")
    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("PageSubtitle")
    col.addWidget(title_label)
    col.addWidget(subtitle_label)
    lay.addLayout(col)
    lay.addStretch(1)
    for action in actions or []:
        lay.addWidget(action, 0, Qt.AlignmentFlag.AlignVCenter)
    return box


def labeled(text: str, widget: QWidget, stretch: int = 0) -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    label = QLabel(text)
    label.setObjectName("Caption")
    widget.setParent(box)
    lay.addWidget(label)
    lay.addWidget(widget)
    if stretch:
        lay.setStretch(1, stretch)
    return box


def make_scroll(content: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName("PageScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(content)
    return scroll


def icon_button(name: str, tooltip: str, role: str = "text", size: int = 16) -> QPushButton:
    btn = QPushButton()
    btn.setProperty("subtle", True)
    btn.setFixedSize(32, 32)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip(tooltip)
    btn.setAccessibleName(tooltip)
    set_icon(btn, name, role, size)
    return btn


def text_button(text: str, icon: str = "", accent: bool = False, subtle: bool = False) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if accent:
        btn.setProperty("accent", True)
    if subtle:
        btn.setProperty("subtle", True)
    if icon:
        set_icon(btn, icon, "accent" if accent else "text")
    return btn


# --------------------------------------------------------------------------- #
# 后台任务
# --------------------------------------------------------------------------- #


class ApiWorker(QThread):
    ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self) -> None:
        try:
            self.ok.emit(self.fn())
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(friendly_error(exc))


class DownloadWorker(QThread):
    status = Signal(str)
    page_started = Signal(int, int, int)
    item_progress = Signal(int)
    item_failed = Signal(str, str)
    done = Signal(int, int, bool)
    failed = Signal(str)

    def __init__(
        self,
        session: requests.Session,
        tags: list[str],
        blacklist: list[str],
        quality: str,
        pages: int,
        limit: int,
        min_score: int,
        directory: Path,
        remember: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.session = session
        self.tags = tags
        self.blacklist = blacklist
        self.quality = quality
        self.pages = pages
        self.limit = limit
        self.min_score = min_score
        self.directory = directory
        self.remember = remember
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"无法创建下载目录：{exc}")
            return

        seen = e6core.read_seen_md5(self.directory) if self.remember else set()
        downloaded = 0
        skipped = 0

        for page in range(1, self.pages + 1):
            if self.cancel_event.is_set():
                self.done.emit(downloaded, skipped, True)
                return
            self.status.emit(f"正在请求第 {page}/{self.pages} 页…")
            try:
                posts = e6core.fetch_posts(
                    self.session,
                    self.tags,
                    limit=self.limit,
                    page=page,
                    min_score=self.min_score,
                    blacklist=self.blacklist,
                )
            except Exception as exc:  # noqa: BLE001
                self.failed.emit(friendly_error(exc))
                return

            if not posts:
                self.status.emit(f"第 {page} 页没有更多结果。")
                break

            self.page_started.emit(page, self.pages, len(posts))
            for index, post in enumerate(posts, 1):
                if self.cancel_event.is_set():
                    self.done.emit(downloaded, skipped, True)
                    return

                url = e6core.get_image_url(post, self.quality)
                ext = e6core.guess_ext(post)
                if not url or ext in e6core.VIDEO_EXTS:
                    skipped += 1
                    self.item_progress.emit(index)
                    continue

                md5 = e6core.post_md5(post)
                if md5 in seen:
                    skipped += 1
                    self.item_progress.emit(index)
                    continue

                filename = e6core.target_filename(post)
                target = self.directory / filename
                if target.exists():
                    seen.add(md5)
                    skipped += 1
                    self.item_progress.emit(index)
                    continue

                self.status.emit(f"正在下载 {filename}")
                err = e6core.download_image(
                    self.session,
                    url,
                    target,
                    cancelled=lambda: self.cancel_event.is_set(),
                )
                if err is None:
                    downloaded += 1
                    seen.add(md5)
                    if self.remember:
                        e6core.append_seen_md5(self.directory, md5)
                else:
                    skipped += 1
                    self.item_failed.emit(filename, err)
                    if self.cancel_event.is_set():
                        self.done.emit(downloaded, skipped, True)
                        return
                self.item_progress.emit(index)

            e6core.wait_cancel(self.cancel_event, e6core.DELAY_BETWEEN_REQUESTS)

        self.done.emit(downloaded, skipped, False)


class SingleDownloadWorker(QThread):
    ok = Signal(str)
    failed = Signal(str)

    def __init__(self, session, post: dict, quality: str, directory: Path, parent=None):
        super().__init__(parent)
        self.session = session
        self.post = post
        self.quality = quality
        self.directory = directory

    def run(self) -> None:
        try:
            url = e6core.get_image_url(self.post, self.quality)
            if not url:
                self.failed.emit("该作品没有可下载的图片地址。")
                return
            self.directory.mkdir(parents=True, exist_ok=True)
            target = self.directory / e6core.target_filename(self.post)
            if target.exists():
                self.ok.emit(str(target))
                return
            err = e6core.download_image(self.session, url, target)
            if err is None:
                self.ok.emit(str(target))
            else:
                self.failed.emit(f"下载失败：{err}")
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(friendly_error(exc))


# --------------------------------------------------------------------------- #
# 标题栏
# --------------------------------------------------------------------------- #


class TitleBar(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.window_ref = window
        self.setFixedHeight(48)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 8, 0)
        lay.setSpacing(10)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(18, 18)
        icon = window.windowIcon()
        if not icon.isNull():
            self.icon_label.setPixmap(icon.pixmap(18, 18))
        lay.addWidget(self.icon_label)
        title = QLabel(APP_TITLE)
        title.setObjectName("AppTitle")
        lay.addWidget(title)
        lay.addStretch(1)
        self.min_btn = CaptionButton("min")
        self.max_btn = CaptionButton("max")
        self.close_btn = CaptionButton("close")
        self.min_btn.clicked.connect(window.showMinimized)
        self.max_btn.clicked.connect(self.toggle_max)
        self.close_btn.clicked.connect(window.close)
        for btn in (self.min_btn, self.max_btn, self.close_btn):
            btn.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            lay.addWidget(btn)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window_ref.windowHandle()
            if handle is not None and hasattr(handle, "startSystemMove"):
                handle.startSystemMove()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_max()
            return
        super().mouseDoubleClickEvent(event)

    def toggle_max(self) -> None:
        if self.window_ref.isMaximized():
            self.window_ref.showNormal()
        else:
            self.window_ref.showMaximized()

    def sync_max(self) -> None:
        self.max_btn.kind = "restore" if self.window_ref.isMaximized() else "max"
        self.max_btn.setAccessibleName("最大化 / 还原" if not self.window_ref.isMaximized() else "还原")
        self.max_btn.update()

    def buttons_global_rects(self) -> list[QRect]:
        rects = []
        for btn in (self.min_btn, self.max_btn, self.close_btn):
            top_left = btn.mapToGlobal(QPoint(0, 0))
            rects.append(QRect(top_left, btn.size()))
        return rects


# --------------------------------------------------------------------------- #
# 头像
# --------------------------------------------------------------------------- #


class Avatar(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.initial = "?"
        self.setFixedSize(32, 32)

    def set_initial(self, text: str) -> None:
        self.initial = (text or "?")[:1].upper()
        self.update()

    def paintEvent(self, _event):  # noqa: N802
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(QColor(t.accent))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(self.rect())
        p.setPen(QColor(t.on_accent))
        f = self.font()
        f.setPointSizeF(10.5)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.initial)
        p.end()


# --------------------------------------------------------------------------- #
# 发现页
# --------------------------------------------------------------------------- #

DISCOVER_ORDERS = [
    ("order:score", "热门"),
    ("order:newest", "最新"),
    ("order:random", "随机"),
]


class DiscoverPage(QWidget):
    PAGE_LIMIT = 24

    def __init__(self, main: "MainWindow"):
        super().__init__()
        self.main = main
        self.order = "order:score"
        self.keyword = ""
        self.page_index = 0
        self.posts: list[dict] = []
        self.cards: list[PostCard] = []
        self.loading = False
        self.reached_end = False
        self._worker: ApiWorker | None = None
        self.select_mode = False
        self.selected: dict[int, dict] = {}
        self._dl_queue: list[dict] = []
        self._dl_done = 0
        self._dl_failed = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(14)

        refresh = icon_button("refresh", "刷新推荐")
        refresh.clicked.connect(self.reload)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索标签，如 wolf solo")
        self.search_edit.setMinimumWidth(240)
        self.search_edit.returnPressed.connect(self._on_search)
        self.search_btn = text_button("搜索", "search", accent=True)
        self.search_btn.clicked.connect(self._on_search)
        self.clear_btn = text_button("清除", subtle=True)
        self.clear_btn.clicked.connect(self._clear_search)
        self._keyword_model = QStringListModel([], self)
        self.completer = QCompleter(self._keyword_model, self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.search_edit.setCompleter(self.completer)
        root.addWidget(
            page_header(
                "发现",
                "来自 e621 的公开推荐，点击卡片查看大图",
                [self.search_edit, self.search_btn, self.clear_btn, refresh],
            )
        )

        self.orders = SegmentedControl(DISCOVER_ORDERS, self.order)
        self.orders.setMaximumWidth(300)
        self.orders.changed.connect(self._on_order)
        self.select_btn = text_button("选择", "check")
        self.select_btn.clicked.connect(lambda: self._set_select_mode(not self.select_mode))
        order_row = QHBoxLayout()
        order_row.addWidget(self.orders)
        order_row.addStretch(1)
        order_row.addWidget(self.select_btn)
        root.addLayout(order_row)

        self.info = InfoBar()
        root.addWidget(self.info)

        self.bulk_label = QLabel("已选 0 项")
        self.bulk_label.setObjectName("Secondary")
        self.bulk_all = text_button("全选")
        self.bulk_fav = text_button("收藏", "heart", accent=True)
        self.bulk_black = text_button("拉黑", "shield")
        self.bulk_dl = text_button("下载", "download")
        self.bulk_exit = text_button("退出选择", subtle=True)
        self.bulk_bar = QFrame()
        self.bulk_bar.setObjectName("Card")
        bulk_lay = QHBoxLayout(self.bulk_bar)
        bulk_lay.setContentsMargins(12, 8, 12, 8)
        bulk_lay.setSpacing(8)
        bulk_lay.addWidget(self.bulk_label)
        bulk_lay.addWidget(self.bulk_all)
        bulk_lay.addWidget(self.bulk_fav)
        bulk_lay.addWidget(self.bulk_black)
        bulk_lay.addWidget(self.bulk_dl)
        bulk_lay.addStretch(1)
        bulk_lay.addWidget(self.bulk_exit)
        self.bulk_all.clicked.connect(self._bulk_select_all)
        self.bulk_fav.clicked.connect(self._bulk_favorite)
        self.bulk_black.clicked.connect(self._bulk_blacklist)
        self.bulk_dl.clicked.connect(self._bulk_download)
        self.bulk_exit.clicked.connect(lambda: self._set_select_mode(False))
        root.addWidget(self.bulk_bar)
        self.bulk_bar.hide()

        self.grid_host = QWidget()
        self.grid = FlowLayout(self.grid_host, 0, 16)
        self.grid_host.setLayout(self.grid)
        self.scroll = make_scroll(self.grid_host)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        root.addWidget(self.scroll, 1)

        self.footer = QLabel("")
        self.footer.setObjectName("Caption")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.footer)

        self.empty = EmptyState(
            "discover", "暂无推荐内容", "检查网络连接后重试，或切换推荐排序。"
        )
        self.empty.set_action("重新加载", self.reload)
        root.addWidget(self.empty)
        self.empty.hide()

    def _on_order(self, value: str) -> None:
        if value == self.order:
            return
        self.order = value
        self.reload()

    def refresh_keyword_completer(self) -> None:
        self._keyword_model.setStringList(e6core.get_recent_keywords(self.main.config))

    def _on_search(self) -> None:
        word = self.search_edit.text().strip().replace(" ", "_")
        if word:
            e6core.add_recent_keyword(self.main.config, word)
            e6core.save_config(self.main.config)
            self.refresh_keyword_completer()
            self.main.search_page.refresh_keywords()
        self.keyword = word
        self.reload()

    def _clear_search(self) -> None:
        had = bool(self.keyword or self.search_edit.text().strip())
        self.search_edit.clear()
        self.keyword = ""
        if had:
            self.reload()

    def _footer_text(self, text: str) -> str:
        if not self.keyword:
            return text
        return f"关键词：{self.keyword}" + (f" · {text}" if text else "")

    def _set_select_mode(self, on: bool) -> None:
        on = bool(on)
        if self.select_mode == on:
            return
        self.select_mode = on
        self.selected.clear()
        for card in self.cards:
            card.set_selectable(on)
        self.select_btn.setText("取消选择" if on else "选择")
        self.bulk_label.setText("已选 0 项")
        self.bulk_bar.setVisible(on)

    def _on_card_checked(self, post: dict, checked: bool) -> None:
        pid = int(post.get("id", 0) or 0)
        if checked:
            self.selected[pid] = post
        else:
            self.selected.pop(pid, None)
        self.bulk_label.setText(f"已选 {len(self.selected)} 项")

    def _bulk_select_all(self) -> None:
        for card in self.cards:
            card.set_checked(True)
            self.selected[int(card.post.get("id", 0) or 0)] = card.post
        self.bulk_label.setText(f"已选 {len(self.selected)} 项")

    def _bulk_favorite(self) -> None:
        if not self.selected:
            self.info.show_message("请先选择要收藏的作品。", "warning")
            return
        if not self.main.logged_in:
            self.info.show_message("批量收藏需要先登录账号。", "warning")
            return
        if not e6core.is_online():
            self.info.show_message("单机模式下无法收藏，请切换为在线模式。", "warning")
            return
        session = self.main.api_session()
        ids = list(self.selected.keys())
        self.bulk_fav.setEnabled(False)

        def work():
            ok = 0
            for pid in ids:
                try:
                    e6core.add_favorite(session, pid)
                    ok += 1
                except Exception:  # noqa: BLE001
                    continue
            return ok

        worker = ApiWorker(work, self)
        worker.ok.connect(self._on_bulk_favorite_done)
        worker.failed.connect(self._on_bulk_favorite_failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_bulk_favorite_done(self, count: int) -> None:
        self.bulk_fav.setEnabled(True)
        self.info.show_message(f"已收藏 {count} 项作品", "success")
        self.main.favorites_page.mark_dirty()
        self._set_select_mode(False)
        self.reload()

    def _on_bulk_favorite_failed(self, message: str) -> None:
        self.bulk_fav.setEnabled(True)
        self.info.show_message(message, "error")

    def _bulk_blacklist(self) -> None:
        if not self.selected:
            self.info.show_message("请先选择要拉黑的作品。", "warning")
            return
        tags: list[str] = []
        for post in self.selected.values():
            for tag in e6core.post_tags(post):
                if tag not in tags:
                    tags.append(tag)
        if not tags:
            self.info.show_message("所选作品没有可加入黑名单的标签。", "warning")
            return
        if not confirm(
            self,
            "批量拉黑",
            f"将把 {len(tags)} 个标签加入黑名单，含这些标签的作品不再出现。",
            "加入黑名单",
            danger=True,
        ):
            return
        blacklist = self.main.config.setdefault("blacklist", [])
        for tag in tags:
            if tag not in blacklist:
                blacklist.append(tag)
        e6core.save_config(self.main.config)
        self.main.notify_blacklist_changed()
        self._set_select_mode(False)
        self.info.show_message(f"已加入 {len(tags)} 个标签到黑名单", "success")

    def _bulk_download(self) -> None:
        if not self.selected:
            self.info.show_message("请先选择要下载的作品。", "warning")
            return
        if not e6core.is_online():
            self.info.show_message("单机模式下无法下载，请切换为在线模式。", "warning")
            return
        self._dl_queue = list(self.selected.values())
        self._dl_done = 0
        self._dl_failed = 0
        self.bulk_dl.setEnabled(False)
        self.info.show_message(f"开始下载 {len(self._dl_queue)} 项…", "info")
        self._next_bulk_download()

    def _next_bulk_download(self) -> None:
        if not self._dl_queue:
            self.bulk_dl.setEnabled(True)
            self.info.show_message(
                f"下载结束：成功 {self._dl_done} 项，失败 {self._dl_failed} 项",
                "success" if self._dl_failed == 0 else "warning",
            )
            self._set_select_mode(False)
            return
        post = self._dl_queue.pop(0)
        worker = SingleDownloadWorker(
            self.main.api_session(),
            post,
            self.main.config.get("quality", "2"),
            self.main.download_dir(),
            self,
        )
        worker.ok.connect(self._on_bulk_download_one_ok)
        worker.failed.connect(self._on_bulk_download_one_failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_bulk_download_one_ok(self, _path: str) -> None:
        self._dl_done += 1
        self._next_bulk_download()

    def _on_bulk_download_one_failed(self, _message: str) -> None:
        self._dl_failed += 1
        self._next_bulk_download()

    def ensure_loaded(self) -> None:
        if SMOKE:
            self.reached_end = True
            self.footer.setText("冒烟测试模式：已禁用网络图片")
            return
        if not self.posts and not self.loading and not self.reached_end:
            self._load_page()

    def reload(self) -> None:
        if self.loading:
            return
        self._set_select_mode(False)
        self.page_index = 0
        self.reached_end = False
        self.posts.clear()
        self._clear_cards()
        self.empty.hide()
        self.info.hide()
        self.footer.setText(self._footer_text(""))
        self._load_page()

    def _clear_cards(self) -> None:
        for card in self.cards:
            self.grid.removeWidget(card)
            card.deleteLater()
        self.cards.clear()

    def _on_scroll(self, value: int) -> None:
        bar = self.scroll.verticalScrollBar()
        if bar.maximum() - value < 280:
            self._load_page()

    def _load_page(self) -> None:
        if self.loading or self.reached_end or SMOKE:
            return
        if not e6core.is_online():
            self.loading = False
            self.footer.setText(self._footer_text(""))
            self.info.show_message(
                "单机模式：发现页需要联网，请在「设置 › 运行模式」切换为在线模式。",
                "warning",
            )
            if not self.posts:
                self.empty.show()
            return
        self.loading = True
        self.footer.setText(self._footer_text("正在加载…"))
        page = self.page_index + 1
        session = self.main.api_session()
        tags = " ".join(x for x in (self.order, self.keyword) if x)

        def work():
            return e6core.fetch_posts(session, tags, limit=self.PAGE_LIMIT, page=page)

        self._worker = ApiWorker(work, self)
        self._worker.ok.connect(lambda posts: self._on_posts(page, posts))
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_posts(self, page: int, posts: list) -> None:
        self.loading = False
        self.page_index = page
        if not posts:
            self.reached_end = True
            self.footer.setText(self._footer_text("已经到底了" if self.posts else ""))
            if not self.posts:
                self.empty.show()
            return

        blacklist = list(self.main.config.get("blacklist", [])) if self.main.logged_in else []
        added = 0
        for post in posts:
            if e6core.is_blocked(post, blacklist):
                continue
            card = PostCard(post, self.main.loader, self.grid_host)
            card.set_selectable(self.select_mode)
            card.clicked.connect(lambda data: self.main.open_detail(data))
            card.checkedChanged.connect(self._on_card_checked)
            self.grid.addWidget(card)
            self.cards.append(card)
            self.posts.append(post)
            added += 1

        if len(posts) < self.PAGE_LIMIT:
            self.reached_end = True

        if added == 0 and not self.reached_end:
            QTimer.singleShot(0, self._load_page)
            return

        self.footer.setText(self._footer_text("已经到底了" if self.reached_end else ""))
        self.empty.hide()
        if self.scroll.verticalScrollBar().maximum() < 10 and not self.reached_end:
            QTimer.singleShot(200, self._load_page)

    def _on_failed(self, message: str) -> None:
        self.loading = False
        self.footer.setText(self._footer_text(""))
        self.info.show_message(message, "error")
        if not self.posts:
            self.empty.show()

    def refresh_theme(self) -> None:
        self.empty.refresh_theme()
        refresh_icons(self)
        self.grid_host.update()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self.ensure_loaded()


# --------------------------------------------------------------------------- #
# 大图与详情页
# --------------------------------------------------------------------------- #


class ImageView(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._pix: QPixmap | None = None
        self._loading = True
        self._error = ""
        self.setMinimumSize(360, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_loading(self) -> None:
        self._pix = None
        self._loading = True
        self._error = ""
        self.update()

    def set_pixmap(self, pix: QPixmap) -> None:
        self._pix = pix
        self._loading = False
        self._error = ""
        self.update()

    def set_error(self, message: str) -> None:
        self._pix = None
        self._loading = False
        self._error = message
        self.update()

    def paintEvent(self, _event):  # noqa: N802
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setBrush(QColor(t.image_bg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), 8, 8)
        inner = self.rect().adjusted(12, 12, -12, -12)
        if self._pix is not None:
            scaled = self._pix.scaled(
                inner.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = inner.x() + (inner.width() - scaled.width()) // 2
            y = inner.y() + (inner.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
        else:
            p.setPen(QColor(t.text_tertiary))
            f = self.font()
            f.setPointSizeF(10.0)
            p.setFont(f)
            text = "正在加载大图…" if self._loading else (self._error or "暂无预览")
            p.drawText(inner, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)
        p.end()


class DetailPage(QWidget):
    def __init__(self, post: dict, main: "MainWindow"):
        super().__init__()
        self.post = post
        self.main = main
        self._busy = False
        self._image_reply = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 14, 28, 20)
        root.setSpacing(12)

        back = QPushButton("返回")
        back.setProperty("subtle", True)
        set_icon(back, "back", "text")
        back.clicked.connect(main.close_detail)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(back)
        title = QLabel(f"作品 #{post.get('id', '?')}")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        top.addWidget(title)
        top.addStretch(1)
        open_btn = text_button("在浏览器中打开", "external", subtle=True)
        open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(f"https://e621.net/posts/{post.get('id', '')}"))
        )
        top.addWidget(open_btn)
        root.addLayout(top)

        self.info = InfoBar()
        root.addWidget(self.info)

        body = QHBoxLayout()
        body.setSpacing(20)
        root.addLayout(body, 1)

        self.image_frame = QFrame()
        self.image_frame.setObjectName("Card")
        image_lay = QVBoxLayout(self.image_frame)
        image_lay.setContentsMargins(10, 10, 10, 10)
        image_lay.setSpacing(8)
        self.image = ImageView()
        image_lay.addWidget(self.image, 1)
        self.meta = QLabel()
        self.meta.setObjectName("Caption")
        self.meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_lay.addWidget(self.meta)
        body.addWidget(self.image_frame, 1)

        side = QWidget()
        side.setFixedWidth(340)
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(0, 0, 0, 0)
        side_lay.setSpacing(12)
        body.addWidget(side)

        stats = QFrame()
        stats.setObjectName("Card")
        stats_lay = QHBoxLayout(stats)
        stats_lay.setContentsMargins(16, 12, 16, 12)
        score = e6core.score_total(post)
        self.score_label = QLabel(f"评分 {score}")
        self.score_label.setObjectName("SectionTitle")
        self.fav_label = QLabel(f"收藏 {post.get('fav_count', 0)}")
        self.fav_label.setObjectName("Secondary")
        stats_lay.addWidget(self.score_label)
        stats_lay.addStretch(1)
        stats_lay.addWidget(self.fav_label)
        side_lay.addWidget(stats)

        rating = QLabel(f"分级：{e6core.rating_label(post.get('rating', ''))}")
        rating.setObjectName("Secondary")
        side_lay.addWidget(rating)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.download_btn = text_button("下载", "download", accent=True)
        self.download_btn.clicked.connect(self.download)
        self.fav_btn = text_button("收藏", "heart")
        self.fav_btn.clicked.connect(self.toggle_favorite)
        actions.addWidget(self.download_btn)
        actions.addWidget(self.fav_btn)
        side_lay.addLayout(actions)

        sep = QFrame()
        sep.setObjectName("Divider")
        sep.setFixedHeight(1)
        side_lay.addWidget(sep)

        tags_title = QLabel("标签")
        tags_title.setObjectName("SectionTitle")
        side_lay.addWidget(tags_title)
        tag_host = QWidget()
        self.tag_flow = FlowLayout(tag_host, 0, 6)
        tag_host.setLayout(self.tag_flow)
        tags_scroll = make_scroll(tag_host)
        side_lay.addWidget(tags_scroll, 1)
        for tag in e6core.post_tags(post)[:80]:
            self.tag_flow.addWidget(chip(tag))

        self.notes = QLabel()
        self.notes.setObjectName("Caption")
        self.notes.setWordWrap(True)
        side_lay.addWidget(self.notes)

        self._update_fav_button()
        self._load_image()

    # ------------------------------------------------------------------ #
    def _load_image(self) -> None:
        file_info = self.post.get("file") or {}
        ext = (file_info.get("ext") or "").lower()
        url = (self.post.get("sample") or {}).get("url")
        if not url:
            url = (self.post.get("preview") or {}).get("url")
        if not url:
            url = e6core.get_image_url(self.post, "2")
        width = file_info.get("width")
        height = file_info.get("height")
        size = file_info.get("size")
        chunks = []
        if width and height:
            chunks.append(f"{width}×{height}")
        if size:
            chunks.append(e6core.human_size(size))
        if ext:
            chunks.append(ext.upper())
        self.meta.setText(" · ".join(chunks) or "—")
        if ext in e6core.VIDEO_EXTS:
            self.notes.setText("这是视频作品，界面中显示预览帧，完整内容请在浏览器中打开。")
        else:
            self.notes.setText("大图按屏幕自适应显示；下载时使用设置中的默认画质。")
        if not url:
            self.image.set_error("该作品没有可显示的预览图。")
            return
        self.image.set_loading()
        self._image_reply = self.main.loader.load(url, self._on_image, self)

    def _on_image(self, pix: QPixmap | None, error: str | None) -> None:
        if pix is not None and not pix.isNull():
            self.image.set_pixmap(pix)
        else:
            self.image.set_error("大图加载失败，请检查网络后重试。")

    def _update_fav_button(self) -> None:
        favorited = bool(self.post.get("is_favorited"))
        self.fav_btn.setText("已收藏" if favorited else "收藏")
        set_icon(self.fav_btn, "heart_filled" if favorited else "heart", "text")
        self.fav_btn.setToolTip("点击取消收藏" if favorited else "添加到我的收藏")

    def download(self) -> None:
        if self._busy:
            return
        quality = self.main.config.get("quality", "2")
        directory = self.main.download_dir()
        self._busy = True
        self.download_btn.setEnabled(False)
        self.download_btn.setText("下载中…")
        worker = SingleDownloadWorker(self.main.api_session(), self.post, quality, directory, self)
        worker.ok.connect(self._on_downloaded)
        worker.failed.connect(self._on_download_failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_downloaded(self, path: str) -> None:
        self._busy = False
        self.download_btn.setEnabled(True)
        self.download_btn.setText("下载")
        self.info.show_message(f"已保存到 {path}", "success")

    def _on_download_failed(self, message: str) -> None:
        self._busy = False
        self.download_btn.setEnabled(True)
        self.download_btn.setText("下载")
        self.info.show_message(message, "error")

    def toggle_favorite(self) -> None:
        if self._busy:
            return
        if not self.main.logged_in:
            if not self.main.open_login_dialog():
                return
        adding = not bool(self.post.get("is_favorited"))
        post_id = int(self.post.get("id", 0))
        self._busy = True
        self.fav_btn.setEnabled(False)

        def work():
            if adding:
                return e6core.add_favorite(self.main.api_session(), post_id)
            return e6core.remove_favorite(self.main.api_session(), post_id)

        worker = ApiWorker(work, self)
        worker.ok.connect(lambda _r: self._on_favorite_done(adding))
        worker.failed.connect(self._on_favorite_failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_favorite_done(self, adding: bool) -> None:
        self._busy = False
        self.fav_btn.setEnabled(True)
        self.post["is_favorited"] = adding
        if adding:
            self.post["fav_count"] = int(self.post.get("fav_count", 0)) + 1
        else:
            self.post["fav_count"] = max(0, int(self.post.get("fav_count", 0)) - 1)
        self.fav_label.setText(f"收藏 {self.post.get('fav_count', 0)}")
        self._update_fav_button()
        self.main.favorites_page.mark_dirty()
        self.info.show_message("已添加到收藏" if adding else "已取消收藏", "success")

    def _on_favorite_failed(self, message: str) -> None:
        self._busy = False
        self.fav_btn.setEnabled(True)
        self.info.show_message(message, "error")

    def refresh_theme(self) -> None:
        self.image.update()
        refresh_icons(self)


# --------------------------------------------------------------------------- #
# 搜索下载页
# --------------------------------------------------------------------------- #


class SearchPage(QWidget):
    def __init__(self, main: "MainWindow"):
        super().__init__()
        self.main = main
        self.worker: DownloadWorker | None = None
        self._dl_fail_count = 0
        cfg = main.config

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(14)

        root.addWidget(page_header("搜索下载", "按标签搜索 e621，批量保存到本地"))

        self.info = InfoBar()
        root.addWidget(self.info)

        form_card, form = section_card()
        form.addWidget(self._section_title("搜索条件"))

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("例如：wolf, solo（多个标签用英文逗号分隔）")
        form.addWidget(labeled("关键词", self.tags_edit))

        self.black_edit = QLineEdit()
        self.black_edit.setPlaceholderText("要排除的标签，多个用英文逗号分隔；留空则使用黑名单页设置")
        form.addWidget(labeled("本次黑名单", self.black_edit))

        numbers = QHBoxLayout()
        numbers.setSpacing(14)
        self.quality = FluentComboBox()
        for key, label in e6core.QUALITY_LABELS.items():
            self.quality.addItem(label, key)
        self._select_combo(self.quality, cfg.get("quality", "2"))
        self.pages_edit = self._number_field(str(cfg.get("max_pages", e6core.DEFAULT_MAX_PAGES)), 1, 50)
        self.limit_edit = self._number_field(str(cfg.get("limit", e6core.DEFAULT_LIMIT)), 1, 320)
        self.score_edit = self._number_field(str(cfg.get("min_score", e6core.DEFAULT_MIN_SCORE)), -1000, 100000)
        numbers.addWidget(labeled("画质", self.quality), 1)
        numbers.addWidget(labeled("页数", self.pages_edit), 1)
        numbers.addWidget(labeled("每页数量", self.limit_edit), 1)
        numbers.addWidget(labeled("最低评分", self.score_edit), 1)
        form.addLayout(numbers)

        dir_row = QWidget()
        dir_lay = QHBoxLayout(dir_row)
        dir_lay.setContentsMargins(0, 0, 0, 0)
        dir_lay.setSpacing(8)
        self.dir_edit = QLineEdit(str(cfg.get("download_dir") or e6core.DOWNLOAD_DIR))
        browse = text_button("浏览…")
        browse.clicked.connect(self._browse)
        open_dir = icon_button("folder", "打开下载目录")
        open_dir.clicked.connect(self._open_dir)
        dir_lay.addWidget(self.dir_edit, 1)
        dir_lay.addWidget(browse)
        dir_lay.addWidget(open_dir)
        form.addWidget(labeled("下载目录", dir_row))

        save_row = QHBoxLayout()
        self.save_history = ToggleSwitch(bool(cfg.get("remember_history", True)))
        self.save_history_label = QLabel("登录后保存搜索历史与下载记录")
        self.save_history_label.setObjectName("Secondary")
        save_row.addWidget(self.save_history)
        save_row.addWidget(self.save_history_label)
        save_row.addStretch(1)
        form.addLayout(save_row)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.start_btn = text_button("开始下载", "download", accent=True)
        self.start_btn.clicked.connect(self.start_download)
        self.cancel_btn = text_button("取消")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_download)
        actions.addWidget(self.start_btn)
        actions.addWidget(self.cancel_btn)
        actions.addStretch(1)
        form.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        form.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setObjectName("Secondary")
        self.status.setWordWrap(True)
        form.addWidget(self.status)
        root.addWidget(form_card)

        history_card, history_lay = section_card()
        head = QHBoxLayout()
        head.addWidget(self._section_title("搜索历史"))
        head.addStretch(1)
        self.clear_history_btn = text_button("清空", subtle=True)
        self.clear_history_btn.clicked.connect(self.clear_history)
        head.addWidget(self.clear_history_btn)
        history_lay.addLayout(head)
        self.history_host = QWidget()
        self.history_box = QVBoxLayout(self.history_host)
        self.history_box.setContentsMargins(0, 0, 0, 0)
        self.history_box.setSpacing(6)
        history_lay.addWidget(self.history_host)
        root.addWidget(history_card)

        keyword_card, keyword_lay = section_card()
        keyword_lay.addWidget(self._section_title("最近关键词"))
        self.keyword_host = QWidget()
        self.keyword_box = FlowLayout(self.keyword_host, 0, 6)
        self.keyword_host.setLayout(self.keyword_box)
        keyword_lay.addWidget(self.keyword_host)
        self.keyword_note = QLabel("点击关键词填入搜索框；条数可在「设置 › 搜索关键词记忆」调整。")
        self.keyword_note.setObjectName("Caption")
        self.keyword_note.setWordWrap(True)
        keyword_lay.addWidget(self.keyword_note)
        root.addWidget(keyword_card)
        root.addStretch(1)

        outer.addWidget(make_scroll(content))
        self.refresh_history()
        self.refresh_keywords()

    @staticmethod
    def _section_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    def set_logged_in(self, logged_in: bool) -> None:
        self.save_history.setEnabled(logged_in)
        self.save_history_label.setText(
            "登录后保存搜索历史与下载记录"
            if logged_in
            else "未登录：本次下载不会保存搜索历史与下载记录"
        )

    @staticmethod
    def _select_combo(combo: FluentComboBox, value: str) -> None:
        idx = combo.findData(value)
        combo.setCurrentIndex(max(0, idx))

    @staticmethod
    def _number_field(value: str, minimum: int, maximum: int) -> QLineEdit:
        edit = QLineEdit(value)
        edit.setValidator(QIntValidator(minimum, maximum, edit))
        edit.setFixedWidth(96)
        return edit

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择下载目录", self.dir_edit.text() or str(Path.home()))
        if path:
            self.dir_edit.setText(path)

    def _open_dir(self) -> None:
        target = Path(self.dir_edit.text() or e6core.DOWNLOAD_DIR)
        try:
            target.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def refresh_history(self) -> None:
        clear_layout(self.history_box)
        history = self.main.config.get("history", [])
        if not history:
            empty = QLabel("暂无搜索历史。")
            empty.setObjectName("Caption")
            self.history_box.addWidget(empty)
            return
        for record in history:
            row = QFrame()
            row.setObjectName("Card")
            lay = QHBoxLayout(row)
            lay.setContentsMargins(12, 8, 8, 8)
            lay.setSpacing(10)
            col = QVBoxLayout()
            col.setSpacing(1)
            tags = ", ".join(record.get("tags", []))
            tags_label = QLabel(tags or "（空）")
            tags_label.setStyleSheet("font-weight: 600;")
            black = ", ".join(record.get("blacklist", []))
            caption = QLabel(f"{record.get('time', '')}" + (f" · 黑名单：{black}" if black else ""))
            caption.setObjectName("Caption")
            col.addWidget(tags_label)
            col.addWidget(caption)
            lay.addLayout(col, 1)
            use = text_button("使用", subtle=True)
            use.clicked.connect(lambda _=False, r=record: self._use_history(r))
            lay.addWidget(use)
            self.history_box.addWidget(row)

    def _use_history(self, record: dict) -> None:
        self.tags_edit.setText(", ".join(record.get("tags", [])))
        self.black_edit.setText(", ".join(record.get("blacklist", [])))
        self.status.setText("已填入历史搜索条件。")

    def refresh_keywords(self) -> None:
        clear_layout(self.keyword_box)
        keywords = e6core.get_recent_keywords(self.main.config)
        if not keywords:
            empty = QLabel("暂无最近关键词。")
            empty.setObjectName("Caption")
            self.keyword_box.addWidget(empty)
            return
        for word in keywords:
            btn = chip(word)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, w=word: self._use_keyword(w))
            self.keyword_box.addWidget(btn)

    def _use_keyword(self, word: str) -> None:
        self.tags_edit.setText(word)
        self.status.setText("已填入最近关键词。")

    def clear_history(self) -> None:
        if not self.main.config.get("history"):
            return
        if confirm(self, "清空搜索历史", "将删除全部搜索历史记录，此操作不可撤销。", "清空", danger=True):
            self.main.config["history"] = []
            e6core.save_config(self.main.config)
            self.refresh_history()
            self.info.show_message("搜索历史已清空。", "success")

    def is_busy(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def _parse_tags(self, text: str) -> list[str]:
        return [part.strip().replace(" ", "_") for part in text.split(",") if part.strip()]

    def start_download(self) -> None:
        if self.is_busy():
            return
        tags = self._parse_tags(self.tags_edit.text())
        if not tags:
            self.info.show_message("请输入至少一个关键词。", "warning")
            return
        blacklist = self._parse_tags(self.black_edit.text())
        if not blacklist:
            blacklist = list(self.main.config.get("blacklist", []))
        quality = self.quality.currentData() or "2"
        try:
            pages = int(self.pages_edit.text() or e6core.DEFAULT_MAX_PAGES)
            limit = int(self.limit_edit.text() or e6core.DEFAULT_LIMIT)
            min_score = int(self.score_edit.text() or e6core.DEFAULT_MIN_SCORE)
        except ValueError:
            self.info.show_message("页数、每页数量与最低评分必须是整数。", "warning")
            return
        e6core.add_recent_keyword(self.main.config, " ".join(tags))
        e6core.save_config(self.main.config)
        self.refresh_keywords()
        self.main.discover_page.refresh_keyword_completer()
        directory = Path(self.dir_edit.text().strip() or e6core.DOWNLOAD_DIR)

        guest = False
        if not self.main.logged_in:
            choice = self.main.ask_download_mode()
            if choice is None:
                return
            if choice == "login":
                if not self.main.open_login_dialog():
                    return
            else:
                guest = True

        remember = self.main.logged_in and self.save_history.is_checked() and not guest
        try:
            session = e6core.make_session(self.main.config, guest=guest)
        except e6core.OfflineModeError:
            self.info.show_message(
                "当前为单机模式，已禁用联网。请在「设置 › 运行模式」切换为在线模式。",
                "warning",
            )
            return

        cfg = self.main.config
        cfg["quality"] = quality
        cfg["max_pages"] = pages
        cfg["limit"] = limit
        cfg["min_score"] = min_score
        cfg["download_dir"] = str(directory)
        cfg["remember_history"] = self.save_history.is_checked()
        e6core.save_config(cfg)
        if remember:
            e6core.add_to_history(cfg, tags, blacklist)
            self.refresh_history()

        self.info.hide()
        self.start_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status.setText("正在准备下载…")

        self.worker = DownloadWorker(
            session, tags, blacklist, quality, pages, limit, min_score, directory, remember, self
        )
        self._dl_fail_count = 0
        self.worker.status.connect(self.status.setText)
        self.worker.page_started.connect(self._on_page)
        self.worker.item_progress.connect(self._on_item)
        self.worker.item_failed.connect(self._on_item_failed)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _on_page(self, page: int, pages: int, total: int) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(0)
        self.status.setText(f"第 {page}/{pages} 页，共 {total} 个作品")

    def _on_item(self, value: int) -> None:
        self.progress.setValue(value)

    def _on_item_failed(self, filename: str, err: str) -> None:
        self._dl_fail_count += 1
        self.status.setText(f"下载失败：{filename}（{err}）")

    def _on_done(self, downloaded: int, skipped: int, cancelled: bool) -> None:
        self._finish()
        fail_note = f"，其中 {self._dl_fail_count} 项下载失败" if self._dl_fail_count else ""
        if cancelled:
            self.info.show_message(f"已取消，本次下载 {downloaded} 张，跳过 {skipped} 张{fail_note}。", "warning")
        else:
            self.info.show_message(f"下载完成：成功 {downloaded} 张，跳过 {skipped} 张{fail_note}。", "success")
        self.status.setText(f"保存目录：{self.dir_edit.text()}")

    def _on_failed(self, message: str) -> None:
        self._finish()
        self.info.show_message(message, "error")

    def _finish(self) -> None:
        self.start_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.progress.setVisible(False)
        self.progress.setRange(0, 0)
        self.worker = None

    def cancel_download(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.status.setText("正在取消，请稍候…")

    def refresh_theme(self) -> None:
        refresh_icons(self)

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self.refresh_history()
        self.refresh_keywords()
        self.cancel_btn.setEnabled(True)


# --------------------------------------------------------------------------- #
# 收藏页
# --------------------------------------------------------------------------- #


class FavoritesPage(QWidget):
    def __init__(self, main: "MainWindow"):
        super().__init__()
        self.main = main
        self.cards: list[PostCard] = []
        self.loaded = False
        self.dirty = True
        self._worker: ApiWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(14)

        self.refresh_btn = icon_button("refresh", "刷新收藏")
        self.refresh_btn.clicked.connect(self.reload)
        root.addWidget(
            page_header("我的收藏", "登录后在这里浏览与管理 e621 收藏", [self.refresh_btn])
        )

        self.info = InfoBar()
        root.addWidget(self.info)

        self.grid_host = QWidget()
        self.grid = FlowLayout(self.grid_host, 0, 16)
        self.grid_host.setLayout(self.grid)
        self.scroll = make_scroll(self.grid_host)
        root.addWidget(self.scroll, 1)

        self.empty = EmptyState("heart", "尚未登录", "登录 e621 账号后即可查看并管理你的收藏。")
        self.empty.set_action("登录", self.main.open_login_dialog)
        root.addWidget(self.empty)

        self.no_fav = EmptyState("heart", "还没有收藏", "在作品详情页点击“收藏”即可加入这里。")
        root.addWidget(self.no_fav)
        self.no_fav.hide()

    def mark_dirty(self) -> None:
        self.dirty = True
        if self.isVisible():
            self.reload()

    def set_logged_in(self, logged_in: bool) -> None:
        if not logged_in:
            self.loaded = False
            self.dirty = True
            self._clear_cards()
            self.scroll.hide()
            self.no_fav.hide()
            self.empty.show()
        else:
            self.empty.hide()
            self.scroll.show()
            self.dirty = True
            if self.isVisible():
                self.reload()

    def _clear_cards(self) -> None:
        for card in self.cards:
            self.grid.removeWidget(card)
            card.deleteLater()
        self.cards.clear()

    def reload(self) -> None:
        if not self.main.logged_in:
            self.set_logged_in(False)
            return
        if not e6core.is_online():
            self.info.show_message(
                "单机模式：收藏页需要联网，请在「设置 › 运行模式」切换为在线模式。",
                "warning",
            )
            if not self.cards:
                self.scroll.hide()
                self.empty.show()
                self.empty.set_text("单机模式", "收藏页需要联网，请切换为在线模式后重试。")
            return
        if self._worker is not None and self._worker.isRunning():
            return
        self.info.hide()
        self.empty.hide()
        self.no_fav.hide()
        self.scroll.show()
        self.refresh_btn.setEnabled(False)
        session = self.main.api_session()

        worker = ApiWorker(lambda: e6core.fetch_all_favorites(session, 200), self)
        self._worker = worker
        worker.ok.connect(self._on_favorites)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(lambda: self.refresh_btn.setEnabled(True))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_favorites(self, posts: list) -> None:
        self.loaded = True
        self.dirty = False
        self._clear_cards()
        blacklist = self.main.config.get("blacklist", [])
        visible = 0
        for post in posts:
            post["is_favorited"] = True
            if e6core.is_blocked(post, blacklist):
                continue
            card = PostCard(post, self.main.loader, self.grid_host)
            card.clicked.connect(lambda data: self.main.open_detail(data))
            self.grid.addWidget(card)
            self.cards.append(card)
            visible += 1
        if not posts:
            self.no_fav.show()
        else:
            self.no_fav.setVisible(visible == 0)

    def _on_failed(self, message: str) -> None:
        self.info.show_message(message, "error")
        if not self.cards:
            self.no_fav.hide()
            self.empty.show()
            self.empty.set_text("无法加载收藏", message)

    def ensure_loaded(self) -> None:
        if not self.main.logged_in:
            self.set_logged_in(False)
            return
        self.empty.hide()
        if not self.loaded or self.dirty:
            self.reload()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self.ensure_loaded()

    def refresh_theme(self) -> None:
        self.empty.refresh_theme()
        self.no_fav.refresh_theme()
        refresh_icons(self)
        self.grid_host.update()


# --------------------------------------------------------------------------- #
# 黑名单页
# --------------------------------------------------------------------------- #


class BlacklistPage(QWidget):
    def __init__(self, main: "MainWindow"):
        super().__init__()
        self.main = main

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(14)

        root.addWidget(page_header("黑名单", "这些标签会从搜索、发现与收藏中隐藏"))
        self.info = InfoBar()
        root.addWidget(self.info)

        card, lay = section_card()
        lay.addWidget(self._title("添加标签"))
        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setPlaceholderText("输入要屏蔽的标签，例如：gore")
        self.input.returnPressed.connect(self.add_tag)
        add = text_button("添加", "plus", accent=True)
        add.clicked.connect(self.add_tag)
        add_row.addWidget(self.input, 1)
        add_row.addWidget(add)
        lay.addLayout(add_row)
        hint = QLabel("标签使用英文并以下划线连接空格；黑名单只保存在本机配置文件中。")
        hint.setObjectName("Caption")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        root.addWidget(card)

        list_card, list_lay = section_card()
        head = QHBoxLayout()
        head.addWidget(self._title("已屏蔽的标签"))
        head.addStretch(1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Caption")
        head.addWidget(self.count_label)
        list_lay.addLayout(head)
        self.list_host = QWidget()
        self.list_box = QVBoxLayout(self.list_host)
        self.list_box.setContentsMargins(0, 0, 0, 0)
        self.list_box.setSpacing(6)
        list_lay.addWidget(self.list_host)
        root.addWidget(list_card)
        root.addStretch(1)

        outer.addWidget(make_scroll(content))
        self.rebuild()

    @staticmethod
    def _title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    def add_tag(self) -> None:
        raw = self.input.text().strip().lower().replace(" ", "_")
        if not raw:
            return
        tags = self.main.config.setdefault("blacklist", [])
        if raw in tags:
            self.info.show_message("该标签已在黑名单中。", "warning")
            return
        tags.append(raw)
        e6core.save_config(self.main.config)
        self.input.clear()
        self.rebuild()
        self.main.notify_blacklist_changed()
        self.info.show_message(f"已屏蔽标签：{raw}", "success")

    def remove_tag(self, tag: str) -> None:
        tags = self.main.config.get("blacklist", [])
        if tag in tags:
            tags.remove(tag)
            e6core.save_config(self.main.config)
            self.rebuild()
            self.main.notify_blacklist_changed()
            self.info.show_message(f"已移除标签：{tag}", "success")

    def rebuild(self) -> None:
        clear_layout(self.list_box)
        tags = self.main.config.get("blacklist", [])
        self.count_label.setText(f"共 {len(tags)} 个")
        if not tags:
            empty = QLabel("暂无屏蔽标签。添加后，相关内容不会出现在列表里。")
            empty.setObjectName("Caption")
            self.list_box.addWidget(empty)
            return
        for tag in tags:
            row = QFrame()
            row.setObjectName("Card")
            lay = QHBoxLayout(row)
            lay.setContentsMargins(12, 6, 6, 6)
            label = QLabel(tag)
            lay.addWidget(label, 1)
            remove = icon_button("close", f"移除 {tag}")
            remove.clicked.connect(lambda _=False, t=tag: self.remove_tag(t))
            lay.addWidget(remove)
            self.list_box.addWidget(row)

    def refresh_theme(self) -> None:
        refresh_icons(self)

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self.rebuild()


# --------------------------------------------------------------------------- #
# 设置页
# --------------------------------------------------------------------------- #


class SettingsPage(QWidget):
    def __init__(self, main: "MainWindow"):
        super().__init__()
        self.main = main
        cfg = main.config

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(14)
        root.addWidget(page_header("设置", "外观、下载、账号与本地数据"))

        self.info = InfoBar()
        root.addWidget(self.info)

        mode_card, mode_lay = section_card()
        mode_lay.addWidget(self._title("运行模式"))
        self.mode_control = SegmentedControl(
            [("offline", "单机模式"), ("online", "在线模式")],
            e6core.current_mode(),
        )
        self.mode_control.setMaximumWidth(320)
        self.mode_control.changed.connect(self._on_mode_change)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_control)
        mode_row.addStretch(1)
        mode_lay.addLayout(mode_row)
        self.mode_note = QLabel("")
        self.mode_note.setObjectName("Caption")
        self.mode_note.setWordWrap(True)
        mode_lay.addWidget(self.mode_note)
        root.addWidget(mode_card)

        theme_card, theme_lay = section_card()
        theme_lay.addWidget(self._title("外观"))
        self.theme_control = SegmentedControl(
            [("system", "跟随系统"), ("light", "浅色"), ("dark", "深色")],
            cfg.get("ui", {}).get("theme", "system"),
        )
        self.theme_control.setMaximumWidth(320)
        self.theme_control.changed.connect(main.set_theme_mode)
        theme_lay.addWidget(self.theme_control)
        root.addWidget(theme_card)

        download_card, download_lay = section_card()
        download_lay.addWidget(self._title("下载"))
        quality_row = QHBoxLayout()
        self.quality = FluentComboBox()
        for key, label in e6core.QUALITY_LABELS.items():
            self.quality.addItem(label, key)
        idx = self.quality.findData(cfg.get("quality", "2"))
        self.quality.setCurrentIndex(max(0, idx))
        self.quality.currentIndexChanged.connect(self._save_download)
        quality_row.addWidget(QLabel("默认画质"))
        quality_row.addWidget(self.quality, 1)
        download_lay.addLayout(quality_row)

        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit(str(cfg.get("download_dir") or e6core.DOWNLOAD_DIR))
        self.dir_edit.editingFinished.connect(self._save_download)
        browse = text_button("浏览…")
        browse.clicked.connect(self._browse)
        open_dir = icon_button("folder", "打开下载目录")
        open_dir.clicked.connect(self._open_dir)
        dir_row.addWidget(QLabel("下载目录"))
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(browse)
        dir_row.addWidget(open_dir)
        download_lay.addLayout(dir_row)
        root.addWidget(download_card)

        kw_card, kw_lay = section_card()
        kw_lay.addWidget(self._title("搜索关键词记忆"))
        limit = e6core.keywords_limit(cfg)
        preset = str(limit) if limit in (0, 3, 5, 10) else "custom"
        self.kw_control = SegmentedControl(
            [
                ("0", "不记忆"),
                ("3", "3 条"),
                ("5", "5 条"),
                ("10", "10 条"),
                ("custom", "自定义"),
            ],
            preset,
        )
        self.kw_control.setMaximumWidth(420)
        self.kw_control.changed.connect(self._on_keyword_limit_change)
        kw_row = QHBoxLayout()
        kw_row.addWidget(self.kw_control)
        self.kw_spin = QSpinBox()
        self.kw_spin.setRange(1, e6core.MAX_KEYWORD_MEMORY)
        self.kw_spin.setSuffix(" 条")
        self.kw_spin.setValue(limit if limit > 0 else 10)
        self.kw_spin.setFixedWidth(110)
        self.kw_spin.setEnabled(preset == "custom")
        self.kw_spin.valueChanged.connect(self._apply_keyword_limit)
        kw_row.addWidget(self.kw_spin)
        kw_row.addStretch(1)
        kw_lay.addLayout(kw_row)
        kw_note = QLabel("保留最近搜索过的关键词条数，0 表示不记忆。仅保存在本机配置中。")
        kw_note.setObjectName("Caption")
        kw_note.setWordWrap(True)
        kw_lay.addWidget(kw_note)
        root.addWidget(kw_card)

        account_card, self.account_lay = section_card()
        self.account_lay.addWidget(self._title("账号"))
        root.addWidget(account_card)

        data_card, data_lay = section_card()
        data_lay.addWidget(self._title("本地数据"))
        data_row = QHBoxLayout()
        data_row.setSpacing(8)
        clear_history = text_button("清空搜索历史", subtle=True)
        clear_history.clicked.connect(self._clear_history)
        clear_cache = text_button("清空图片缓存", subtle=True)
        clear_cache.clicked.connect(self._clear_cache)
        open_cfg = text_button("打开配置文件夹")
        open_cfg.clicked.connect(self._open_config_dir)
        data_row.addWidget(clear_history)
        data_row.addWidget(clear_cache)
        data_row.addWidget(open_cfg)
        data_row.addStretch(1)
        data_lay.addLayout(data_row)
        path_label = QLabel(str(e6core.CONFIG_FILE))
        path_label.setObjectName("Caption")
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        data_lay.addWidget(path_label)
        root.addWidget(data_card)

        about_card, about_lay = section_card()
        about_lay.addWidget(self._title("关于"))
        about = QLabel(
            f"{APP_TITLE} {e6core.APP_VERSION} · PySide6 + Fluent Design\n"
            "预览图与大图来自 e621，账号信息仅保存在本机配置文件中。"
        )
        about.setObjectName("Secondary")
        about.setWordWrap(True)
        about_lay.addWidget(about)
        link = QLabel('<a href="https://e621.net/help/api">如何获取 e621 API Key</a>')
        link.setOpenExternalLinks(True)
        about_lay.addWidget(link)
        root.addWidget(about_card)
        root.addStretch(1)

        outer.addWidget(make_scroll(content))
        self.refresh_account()

    @staticmethod
    def _title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    def _save_download(self) -> None:
        cfg = self.main.config
        cfg["quality"] = self.quality.currentData() or "2"
        cfg["download_dir"] = self.dir_edit.text().strip() or str(e6core.DOWNLOAD_DIR)
        e6core.save_config(cfg)

    def _on_mode_change(self, value: str) -> None:
        current = e6core.current_mode()
        if value == current:
            return
        if not self.main.set_run_mode(value):
            self.mode_control.set_value(current)
            return
        self.refresh_mode()

    def _on_keyword_limit_change(self, value: str) -> None:
        if value == "custom":
            limit = self.kw_spin.value()
            self.kw_spin.setEnabled(True)
        else:
            limit = int(value)
            self.kw_spin.setEnabled(False)
            self.kw_spin.blockSignals(True)
            self.kw_spin.setValue(limit if limit > 0 else 1)
            self.kw_spin.blockSignals(False)
        self._write_keyword_limit(limit)

    def _apply_keyword_limit(self, value: int) -> None:
        preset = str(value) if value in (0, 3, 5, 10) else "custom"
        self.kw_control.set_value(preset)
        self._write_keyword_limit(int(value))

    def _write_keyword_limit(self, limit: int) -> None:
        cfg = self.main.config
        ui = cfg.setdefault("ui", {})
        ui["keyword_memory"] = int(limit)
        e6core.save_config(cfg)
        self.main.search_page.refresh_keywords()
        self.main.discover_page.refresh_keyword_completer()
        self.info.show_message(f"关键词记忆已设为 {int(limit)} 条。", "success")

    def refresh_mode(self) -> None:
        mode = e6core.current_mode()
        self.mode_control.set_value(mode)
        current = "单机模式" if mode == e6core.MODE_OFFLINE else "在线模式"
        self.mode_note.setText(
            f"当前：{current}。单机模式完全禁用联网，为开发阶段默认值；"
            "在线模式允许访问 e621 接口，需手动开启。"
        )
        self.refresh_account()

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择下载目录", self.dir_edit.text())
        if path:
            self.dir_edit.setText(path)
            self._save_download()

    def _open_dir(self) -> None:
        target = Path(self.dir_edit.text() or e6core.DOWNLOAD_DIR)
        try:
            target.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _open_config_dir(self) -> None:
        e6core.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(e6core.CONFIG_FILE.parent)))

    def _clear_history(self) -> None:
        if not self.main.config.get("history"):
            return
        if confirm(self, "清空搜索历史", "将删除全部搜索历史记录，此操作不可撤销。", "清空", danger=True):
            self.main.config["history"] = []
            e6core.save_config(self.main.config)
            self.main.search_page.refresh_history()

    def _clear_cache(self) -> None:
        if confirm(self, "清空图片缓存", "将删除本机缓存的预览图与大图，下次浏览会重新下载。", "清空", danger=True):
            self.main.loader.clear_cache()

    def refresh_account(self) -> None:
        clear_layout(self.account_lay)
        title = self._title("账号")
        self.account_lay.addWidget(title)
        if self.main.logged_in:
            row = QHBoxLayout()
            avatar = Avatar()
            avatar.set_initial(self.main.username)
            row.addWidget(avatar)
            col = QVBoxLayout()
            col.setSpacing(1)
            name = QLabel(self.main.username)
            name.setStyleSheet("font-weight: 600;")
            masked = "*" * min(12, len(self.main.config.get("api_key", ""))) or "（未保存到本机）"
            caption = QLabel(f"API Key：{masked}")
            caption.setObjectName("Caption")
            col.addWidget(name)
            col.addWidget(caption)
            row.addLayout(col)
            row.addStretch(1)
            logout = text_button("退出登录", "logout")
            logout.clicked.connect(self.main.logout)
            row.addWidget(logout)
            self.account_lay.addLayout(row)
        else:
            row = QHBoxLayout()
            label = QLabel("当前未登录，登录后可管理收藏。")
            label.setObjectName("Secondary")
            row.addWidget(label, 1)
            login = text_button("登录", "login", accent=True)
            login.clicked.connect(self.main.open_login_dialog)
            login.setEnabled(e6core.is_online())
            row.addWidget(login)
            self.account_lay.addLayout(row)
            if not e6core.is_online():
                hint = QLabel("需切换为在线模式后才能登录。")
                hint.setObjectName("Caption")
                hint.setWordWrap(True)
                self.account_lay.addWidget(hint)

    def refresh_theme(self) -> None:
        refresh_icons(self)

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self.refresh_mode()


# --------------------------------------------------------------------------- #
# 登录对话框
# --------------------------------------------------------------------------- #


class LoginDialog(ContentDialog):
    def __init__(self, main: "MainWindow"):
        super().__init__(main, "登录 e621", 420)
        self.main = main
        self.result_data: tuple[str, str, bool] | None = None
        self._worker: ApiWorker | None = None

        hint = QLabel("使用 e621 用户名与 API Key 登录。API Key 仅用于本机请求，不会上传到其他服务。")
        hint.setObjectName("Secondary")
        hint.setWordWrap(True)
        self.content.addWidget(hint)

        self.username = QLineEdit(main.config.get("username", ""))
        self.username.setPlaceholderText("e621 用户名")
        self.content.addWidget(labeled("用户名", self.username))

        self.api_key = QLineEdit(main.config.get("api_key", ""))
        self.api_key.setPlaceholderText("API Key")
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.content.addWidget(labeled("API Key", self.api_key))

        self.show_key = FluentCheckBox("显示 API Key")
        self.show_key.toggled.connect(
            lambda checked: self.api_key.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        self.content.addWidget(self.show_key)

        self.remember = FluentCheckBox("在本机保存登录信息")

        self.remember.setChecked(bool(main.config.get("username") and main.config.get("api_key")))
        self.content.addWidget(self.remember)

        self.info = InfoBar()
        self.content.addWidget(self.info)

        link = QLabel('<a href="https://e621.net/help/api">在哪里找到 API Key？</a>')
        link.setOpenExternalLinks(True)
        self.content.addWidget(link)

        self.add_action("取消", on_click=self.reject)
        self.login_btn = self.add_action("登录", primary=True, on_click=self.submit)
        self.username.returnPressed.connect(self.api_key.setFocus)
        self.api_key.returnPressed.connect(self.submit)

    def submit(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        username = self.username.text().strip()
        api_key = self.api_key.text().strip()
        if not username or not api_key:
            self.info.show_message("用户名与 API Key 不能为空。", "warning")
            return
        self.login_btn.setEnabled(False)
        self.login_btn.setText("验证中…")
        self.info.hide()
        self._worker = ApiWorker(lambda: e6core.validate_login(username, api_key), self)
        self._worker.ok.connect(lambda result: self._on_validated(username, api_key, result))
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_validated(self, username: str, api_key: str, result) -> None:
        self.login_btn.setEnabled(True)
        self.login_btn.setText("登录")
        ok, _code, message = result
        if ok:
            self.result_data = (username, api_key, self.remember.isChecked())
            self.accept()
        else:
            self.info.show_message(message, "error")

    def _on_failed(self, message: str) -> None:
        self.login_btn.setEnabled(True)
        self.login_btn.setText("登录")
        self.info.show_message(message, "error")


# --------------------------------------------------------------------------- #
# 主窗口
# --------------------------------------------------------------------------- #


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = e6core.load_config()
        e6core.sync_mode_from_config(self.config)
        self.logged_in = bool(self.config.get("username") and self.config.get("api_key"))
        self.username = self.config.get("username", "") if self.logged_in else ""
        self.session = None
        self._anon_session = None
        if self.logged_in:
            try:
                self.session = e6core.make_session(self.config)
            except e6core.OfflineModeError:
                self.session = None
        if e6core.is_online():
            try:
                self._anon_session = e6core.make_session(guest=True)
            except e6core.OfflineModeError:
                self._anon_session = None
        self._workers: set[QThread] = set()
        self._theme_overlay = None
        self._theme_anim = None

        self.setWindowTitle(APP_TITLE)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        icon_path = resource_path("icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(1040, 680)
        self.resize(1220, 820)

        self.loader = ImageLoader(self)
        if self.logged_in:
            self.loader.set_user_agent(e6core.user_agent(self.username))

        self.root = RootWidget()
        self.root.setAutoFillBackground(False)
        self.setCentralWidget(self.root)
        self.setStyleSheet("QMainWindow { background: transparent; }")
        root_lay = QVBoxLayout(self.root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        self.titlebar = TitleBar(self)
        root_lay.addWidget(self.titlebar)

        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)
        root_lay.addWidget(body, 1)

        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(232)
        side_lay = QVBoxLayout(self.sidebar)
        side_lay.setContentsMargins(10, 10, 10, 12)
        side_lay.setSpacing(2)
        body_lay.addWidget(self.sidebar)

        self.nav_items: dict[str, NavItem] = {}
        nav_groups = [("浏览", ["discover", "search"]), ("我的", ["favorites", "blacklist"]), ("应用", ["settings"])]
        for group, keys in nav_groups:
            caption = QLabel(group)
            caption.setObjectName("Caption")
            caption.setContentsMargins(12, 8, 0, 2)
            side_lay.addWidget(caption)
            for key in keys:
                label = next(item[1] for item in NAV_ITEMS if item[0] == key)
                icon = next(item[2] for item in NAV_ITEMS if item[0] == key)
                item = NavItem(icon, label)
                item.clicked.connect(lambda k=key: self.show_page(k))
                side_lay.addWidget(item)
                self.nav_items[key] = item
        side_lay.addStretch(1)

        self.account_host = QFrame()
        self.account_host.setObjectName("LoginBar")
        account_lay = QHBoxLayout(self.account_host)
        account_lay.setContentsMargins(10, 8, 10, 8)
        account_lay.setSpacing(8)
        self.avatar = Avatar()
        self.account_name = QLabel("未登录")
        self.account_name.setStyleSheet("font-weight: 600;")
        self.account_caption = QLabel("")
        self.account_caption.setObjectName("Caption")
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(self.account_name)
        col.addWidget(self.account_caption)
        account_lay.addWidget(self.avatar)
        account_lay.addLayout(col, 1)
        self.account_host.setCursor(Qt.CursorShape.PointingHandCursor)
        self.account_host.setToolTip("点击登录或管理账号")
        self.account_host.mouseReleaseEvent = lambda _e: self._on_account_clicked()  # type: ignore[assignment]
        side_lay.addWidget(self.account_host)

        self.stack = QStackedWidget()
        body_lay.addWidget(self.stack, 1)

        self.discover_page = DiscoverPage(self)
        self.search_page = SearchPage(self)
        self.favorites_page = FavoritesPage(self)
        self.blacklist_page = BlacklistPage(self)
        self.settings_page = SettingsPage(self)
        self.pages = {
            "discover": self.discover_page,
            "search": self.search_page,
            "favorites": self.favorites_page,
            "blacklist": self.blacklist_page,
            "settings": self.settings_page,
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        self.detail: DetailPage | None = None
        self.current_key = "discover"

        self._update_login_ui()
        self.show_page("discover", initial=True)

        app_hints = QApplication.styleHints()
        try:
            app_hints.colorSchemeChanged.connect(self._on_system_scheme)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    def api_session(self):
        if not e6core.is_online():
            return None
        if self.logged_in:
            if self.session is None:
                try:
                    self.session = e6core.make_session(self.config)
                except e6core.OfflineModeError:
                    self.session = None
            if self.session is not None:
                return self.session
        if self._anon_session is None:
            try:
                self._anon_session = e6core.make_session(guest=True)
            except e6core.OfflineModeError:
                self._anon_session = None
        return self._anon_session

    def set_run_mode(self, mode: str, confirm_online: bool = True) -> bool:
        target = e6core.MODE_ONLINE if mode == e6core.MODE_ONLINE else e6core.MODE_OFFLINE
        if target == e6core.current_mode():
            return True
        if target == e6core.MODE_ONLINE and confirm_online:
            if not confirm(
                self,
                "开启在线模式",
                "开启后程序将恢复访问 e621 接口的联网权限。开发阶段请在确认后手动开启。",
                "开启联网",
            ):
                return False
        e6core.save_mode(self.config, target)
        if target == e6core.MODE_OFFLINE:
            self.session = None
            self._anon_session = None
        else:
            try:
                self._anon_session = self._anon_session or e6core.make_session(guest=True)
                if self.logged_in and self.session is None:
                    self.session = e6core.make_session(self.config)
            except e6core.OfflineModeError:
                pass
        self.notify_mode_changed()
        return True

    def notify_mode_changed(self) -> None:
        online = e6core.is_online()
        self.settings_page.refresh_mode()
        self._update_login_ui()
        if online:
            self.settings_page.info.show_message("已切换为在线模式。", "success")
        else:
            self.settings_page.info.show_message("已切换为单机模式，联网功能已全部禁用。", "warning")
        if hasattr(self, "discover_page"):
            page = self.discover_page
            if online:
                if not page.posts and not page.loading:
                    page.reload()
            else:
                page.footer.setText(page._footer_text("单机模式 · 已停用联网"))
        if hasattr(self, "favorites_page"):
            self.favorites_page.mark_dirty()
            if self.current_key == "favorites":
                self.favorites_page.reload()

    def download_dir(self) -> Path:
        return Path(self.config.get("download_dir") or e6core.DOWNLOAD_DIR)

    def show_page(self, key: str, initial: bool = False) -> None:
        if key not in self.pages:
            return
        if self.detail is not None:
            self.close_detail()
        self.current_key = key
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        for name, item in self.nav_items.items():
            item.set_selected(name == key)
        if key == "favorites":
            self.favorites_page.ensure_loaded()
        if key == "discover":
            self.discover_page.ensure_loaded()
        if not initial:
            page.setFocus()

    def _on_account_clicked(self) -> None:
        menu = QMenu(self)
        mode_text = "在线模式" if e6core.is_online() else "单机模式"
        header = menu.addAction(f"{mode_text} · {self.username if self.logged_in else '未登录'}")
        header.setEnabled(False)
        menu.addSeparator()
        if not self.logged_in:
            act_login = menu.addAction("登录…")
            act_login.triggered.connect(self.open_login_dialog)
        else:
            act_account = menu.addAction("账号设置")
            act_account.triggered.connect(lambda: self.show_page("settings"))
            act_logout = menu.addAction("退出登录")
            act_logout.triggered.connect(self.logout)
        menu.addSeparator()
        act_settings = menu.addAction("运行模式…")
        act_settings.triggered.connect(lambda: self.show_page("settings"))
        point = self.account_host.mapToGlobal(QPoint(0, -menu.sizeHint().height()))
        menu.exec(point)

    def open_detail(self, post: dict) -> None:
        if self.detail is not None:
            self.stack.removeWidget(self.detail)
            self.detail.deleteLater()
        self.detail = DetailPage(post, self)
        self.stack.addWidget(self.detail)
        self.stack.setCurrentWidget(self.detail)

    def close_detail(self) -> None:
        if self.detail is None:
            return
        page = self.detail
        self.detail = None
        self.stack.setCurrentWidget(self.pages[self.current_key])
        self.stack.removeWidget(page)
        page.deleteLater()

    # ------------------------------------------------------------------ #
    def ask_download_mode(self) -> str | None:
        dlg = ContentDialog(self, "选择下载方式", 430)
        text = QLabel(
            "登录下载：使用账号搜索，并可按设置保存搜索历史与下载记录。\n"
            "不登录下载：以匿名身份下载，不保存任何搜索历史或下载记录。"
        )
        text.setWordWrap(True)
        text.setObjectName("Secondary")
        dlg.content.addWidget(text)
        result = {"mode": None}

        def choose(mode: str) -> None:
            result["mode"] = mode
            dlg.accept()

        dlg.add_action("取消", on_click=dlg.reject)
        dlg.add_action("不登录下载", on_click=lambda: choose("guest"))
        dlg.add_action("登录下载", primary=True, on_click=lambda: choose("login"))
        dlg.exec_dialog()
        return result["mode"]

    def open_login_dialog(self) -> bool:
        if not e6core.is_online():
            self.notify_mode_changed()
            self.settings_page.info.show_message(
                "单机模式下无法登录，请先在「设置 › 运行模式」切换为在线模式。",
                "warning",
            )
            self.show_page("settings")
            return False
        dlg = LoginDialog(self)
        if dlg.exec_dialog() == QDialog.DialogCode.Accepted and dlg.result_data:
            username, api_key, remember = dlg.result_data
            self._apply_login(username, api_key, remember)
            return True
        return False

    def _apply_login(self, username: str, api_key: str, remember: bool) -> None:
        if remember:
            self.config["username"] = username
            self.config["api_key"] = api_key
        else:
            self.config.pop("username", None)
            self.config.pop("api_key", None)
        e6core.save_config(self.config)
        self.username = username
        self.logged_in = True
        self.session = e6core.session_for(username, api_key)
        self.loader.set_user_agent(e6core.user_agent(username))
        self._update_login_ui()
        self.favorites_page.mark_dirty()
        self.discover_page.reload()
        self.settings_page.refresh_account()
        self.settings_page.info.show_message(f"已登录：{username}", "success")

    def logout(self) -> None:
        if not confirm(self, "退出登录", "将删除本机保存的用户名与 API Key。", "退出登录", danger=True):
            return
        self.config.pop("username", None)
        self.config.pop("api_key", None)
        e6core.save_config(self.config)
        self.username = ""
        self.logged_in = False
        self.session = None
        self.loader.set_user_agent(e6core.user_agent())
        self._update_login_ui()
        self.discover_page.reload()
        self.settings_page.refresh_account()

    def _update_login_ui(self) -> None:
        mode_text = "在线模式" if e6core.is_online() else "单机模式"
        if self.logged_in:
            self.account_name.setText(self.username)
            self.account_caption.setText(f"已登录 · {mode_text}")
            self.avatar.set_initial(self.username)
        else:
            self.account_name.setText("未登录")
            if e6core.is_online():
                self.account_caption.setText("点击登录")
            else:
                self.account_caption.setText("单机模式 · 点击登录")
            self.avatar.set_initial("?")
        self.favorites_page.set_logged_in(self.logged_in)
        self.search_page.set_logged_in(self.logged_in)
        self.settings_page.refresh_account()

    def notify_blacklist_changed(self) -> None:
        self.discover_page.reload()
        self.favorites_page.mark_dirty()

    # ------------------------------------------------------------------ #
    def set_theme_mode(self, mode: str) -> None:
        self.config.setdefault("ui", {})["theme"] = mode
        e6core.save_config(self.config)
        self._apply_theme(animate=True)

    def _on_system_scheme(self, *_args) -> None:
        if self.config.get("ui", {}).get("theme", "system") == "system":
            self._apply_theme(animate=True)

    def _apply_theme(self, animate: bool = False) -> None:
        dark = theme.resolve_dark(self.config.get("ui", {}).get("theme", "system"))
        snapshot = None
        if animate and self.isVisible():
            snapshot = self.root.grab()
            self._drop_theme_overlay()
        theme.apply_theme(QApplication.instance(), dark)
        self.root.update()
        self.titlebar.update()
        for item in self.nav_items.values():
            item.update()
        refresh_icons(self)
        for page in self.pages.values():
            if hasattr(page, "refresh_theme"):
                page.refresh_theme()
        if self.detail is not None:
            self.detail.refresh_theme()
        if snapshot is not None and not snapshot.isNull():
            self._play_theme_overlay(snapshot)

    def _drop_theme_overlay(self) -> None:
        if self._theme_anim is not None:
            try:
                self._theme_anim.stop()
            except Exception:
                pass
            self._theme_anim = None
        if self._theme_overlay is not None:
            self._theme_overlay.deleteLater()
            self._theme_overlay = None

    def _play_theme_overlay(self, snapshot) -> None:
        overlay = QLabel(self.root)
        overlay.setPixmap(snapshot)
        overlay.setGeometry(self.root.rect())
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        overlay.show()
        overlay.raise_()
        effect = QGraphicsOpacityEffect(overlay)
        effect.setOpacity(1.0)
        overlay.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", overlay)
        anim.setDuration(220)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(self._drop_theme_overlay)
        self._theme_overlay = overlay
        self._theme_anim = anim
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    # ------------------------------------------------------------------ #
    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)

    def changeEvent(self, event):  # noqa: N802
        if event.type() == QEvent.Type.WindowStateChange:
            self.titlebar.sync_max()
        super().changeEvent(event)

    def nativeEvent(self, event_type, message):  # noqa: N802
        if os.name == "nt" and bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            try:
                import ctypes.wintypes

                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == 0x0084:  # WM_NCHITTEST
                    # lParam 为物理像素，Qt 的坐标系统为逻辑像素，需按缩放比换算
                    dpr = self.devicePixelRatioF() or 1.0
                    gx = ctypes.c_short(msg.lParam & 0xFFFF).value
                    gy = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    lx, ly = int(round(gx / dpr)), int(round(gy / dpr))
                    geo = self.frameGeometry()
                    if not self.isMaximized() and not self.isFullScreen() and geo.contains(QPoint(lx, ly)):
                        border = 5
                        left = lx < geo.left() + border
                        right = lx > geo.right() - border
                        top = ly < geo.top() + border
                        bottom = ly > geo.bottom() - border
                        if top and left:
                            return True, 13  # HTTOPLEFT
                        if top and right:
                            return True, 14  # HTTOPRIGHT
                        if bottom and left:
                            return True, 16  # HTBOTTOMLEFT
                        if bottom and right:
                            return True, 17  # HTBOTTOMRIGHT
                        if left:
                            return True, 10  # HTLEFT
                        if right:
                            return True, 11  # HTRIGHT
                        if top:
                            return True, 12  # HTTOP
                        if bottom:
                            return True, 15  # HTBOTTOM
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def closeEvent(self, event):  # noqa: N802
        if self.search_page.is_busy():
            if not confirm(self, "退出 E621Downloader", "下载仍在进行，退出将中断当前任务。", "仍要退出", danger=True):
                event.ignore()
                return
            if self.search_page.worker is not None:
                self.search_page.worker.cancel()
        event.accept()


class RootWidget(QWidget):
    def paintEvent(self, _event):  # noqa: N802
        t = theme.current()
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(t.bg_solid))
        p.end()


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #


def install_excepthook() -> None:
    log_path = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "E6Dler" / "e6dler-error.log"

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass
        try:
            ctypes.windll.user32.MessageBoxW(0, text[-1800:], "E621Downloader 发生错误", 0x10)
        except Exception:
            pass

    sys.excepthook = hook


def main() -> int:
    install_excepthook()
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("E6Dler.App")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setOrganizationName("E6Dler")
    app.setFont(theme.app_font())
    style = QStyleFactory.create("windows11")
    if style is not None:
        app.setStyle(style)
    window = MainWindow()
    window._apply_theme()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
