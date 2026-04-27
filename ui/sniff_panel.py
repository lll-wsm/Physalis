from urllib.parse import urlparse

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QUrl
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.sniffer import SniffedVideo

# Content-Type → format_hint mapping for probing unknown media URLs
_CONTENT_TYPE_FORMAT = {
    "video/mp4": "mp4",
    "video/x-flv": "flv",
    "video/webm": "webm",
    "video/quicktime": "mp4",
    "video/MP2T": "ts",
    "application/vnd.apple.mpegurl": "m3u8",
    "application/x-mpegurl": "m3u8",
    "application/dash+xml": "dash",
    "audio/mp4": "m4a",
    "audio/aac": "aac",
    "audio/mpeg": "mp3",
}

_PANEL_W = 260

_ICON_SZ = 16


def _make_download_icon() -> QIcon:
    """Downward arrow."""
    pixmap = QPixmap(_ICON_SZ, _ICON_SZ)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    # Arrow shaft
    p.drawLine(_ICON_SZ // 2, 1, _ICON_SZ // 2, _ICON_SZ - 4)
    # Arrowhead
    p.drawLine(_ICON_SZ // 2, _ICON_SZ - 4, _ICON_SZ // 2 - 5, _ICON_SZ // 2)
    p.drawLine(_ICON_SZ // 2, _ICON_SZ - 4, _ICON_SZ // 2 + 5, _ICON_SZ // 2)
    p.end()
    return QIcon(pixmap)


def _make_info_icon() -> QIcon:
    """Circled 'i'."""
    pixmap = QPixmap(_ICON_SZ, _ICON_SZ)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    # Circle
    margin = 1.5
    r = (_ICON_SZ - 2 * margin) / 2
    cx = cy = _ICON_SZ / 2
    p.drawEllipse(int(cx - r), int(cy - r), int(2 * r), int(2 * r))
    # Dot
    p.drawEllipse(int(cx - 1), int(cy - r + 4), 2, 2)
    # Stem
    p.drawLine(int(cx), int(cy - r + 8), int(cx), int(cy + r - 4))
    p.end()
    return QIcon(pixmap)


def _make_download_icon_white() -> QIcon:
    """Downward arrow in white (for grid card hover/use)."""
    pixmap = QPixmap(_ICON_SZ, _ICON_SZ)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#ffffff"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    p.drawLine(_ICON_SZ // 2, 1, _ICON_SZ // 2, _ICON_SZ - 4)
    p.drawLine(_ICON_SZ // 2, _ICON_SZ - 4, _ICON_SZ // 2 - 5, _ICON_SZ // 2)
    p.drawLine(_ICON_SZ // 2, _ICON_SZ - 4, _ICON_SZ // 2 + 5, _ICON_SZ // 2)
    p.end()
    return QIcon(pixmap)


def _uri_label(url: str) -> str:
    """Extract a short unique identifier from a video URL."""
    parsed = urlparse(url)
    params = {}
    if parsed.query:
        for pair in parsed.query.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k] = v
    uid = (
        params.get("video_id")
        or params.get("vid")
        or params.get("id")
        or ""
    )
    if uid:
        return uid
    segs = [s for s in parsed.path.split("/") if s]
    for s in reversed(segs):
        if len(s) > 6:
            return s
    if segs:
        return segs[-1]
    return url[:40]


def _format_size(bytes_: int) -> str:
    """Format byte count into human-readable string."""
    if bytes_ <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_ < 1024:
            return f"{bytes_:.1f} {unit}"
        bytes_ /= 1024
    return f"{bytes_:.1f} TB"


class _VideoDetailDialog(QDialog):
    """Dialog showing full details of a sniffed video."""

    def __init__(self, video: SniffedVideo, parent=None):
        super().__init__(parent)
        self._video = video
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("视频详情")
        self.setMinimumSize(500, 360)
        self.setStyleSheet("""
            QDialog {
                background-color: #2d2640;
                color: #e8e8ed;
            }
            QLabel {
                color: #c4b5fd;
                font-size: 12px;
                font-weight: 600;
            }
            QTextEdit {
                background-color: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 6px;
                color: #ddd6fe;
                font-size: 12px;
                padding: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)

        title = QLabel("视频详情")
        title.setStyleSheet("font-size: 17px; font-weight: 700; color: #ffffff;")
        layout.addWidget(title)

        v = self._video

        # URL
        layout.addWidget(QLabel("URL"))
        url_edit = QTextEdit()
        url_edit.setPlainText(v.url)
        url_edit.setFixedHeight(56)
        url_edit.setReadOnly(True)
        layout.addWidget(url_edit)

        # Info grid
        info_layout = QHBoxLayout()
        info_layout.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(QLabel("类型"))
        type_lbl = QLabel(f"  {v.format_hint}")
        type_lbl.setStyleSheet("color: #ddd6fe; font-size: 13px;")
        left.addWidget(type_lbl)
        if v.content_length > 0:
            left.addWidget(QLabel("大小"))
            size_lbl = QLabel(f"  {_format_size(v.content_length)}")
            size_lbl.setStyleSheet("color: #ddd6fe; font-size: 13px;")
            left.addWidget(size_lbl)
        info_layout.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(4)
        if v.page_url:
            right.addWidget(QLabel("页面 URL"))
            page_lbl = QLabel(f"  {v.page_url}")
            page_lbl.setStyleSheet("color: #ddd6fe; font-size: 12px;")
            page_lbl.setWordWrap(True)
            right.addWidget(page_lbl)
        if v.referer:
            right.addWidget(QLabel("Referer"))
            ref_lbl = QLabel(f"  {v.referer}")
            ref_lbl.setStyleSheet("color: #ddd6fe; font-size: 12px;")
            ref_lbl.setWordWrap(True)
            right.addWidget(ref_lbl)
        info_layout.addLayout(right)

        layout.addLayout(info_layout)
        layout.addStretch()

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(64, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08);
                color: #e8e8ed;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background: rgba(255,255,255,0.14); }
        """)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    @staticmethod
    def show_for(video: SniffedVideo, parent=None):
        dialog = _VideoDetailDialog(video, parent)
        dialog.exec()


class _MediaRow(QWidget):
    download_clicked = pyqtSignal(object)
    info_clicked = pyqtSignal(object)

    def __init__(self, video: SniffedVideo, parent=None):
        super().__init__(parent)
        self._video = video
        self.setFixedHeight(48)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # Format badge
        self._badge = QLabel(self._video.format_hint)
        self._badge.setFixedSize(36, 18)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setStyleSheet("""
            background-color: rgba(139,92,246,0.15);
            color: #a78bfa;
            border-radius: 3px;
            font-size: 9px;
            font-weight: 600;
        """)
        layout.addWidget(self._badge)

        # URI-derived name
        self._name_label = QLabel(_uri_label(self._video.url))
        self._name_label.setStyleSheet(
            "color: #ddd6fe; font-size: 11px; font-weight: 600; background: transparent;"
        )
        self._name_label.setWordWrap(False)
        self._name_label.setToolTip(self._video.url)
        layout.addWidget(self._name_label, 1)

        # Download icon button
        self._dl_btn = QPushButton()
        self._dl_btn.setIcon(_make_download_icon())
        self._dl_btn.setIconSize(QSize(_ICON_SZ, _ICON_SZ))
        self._dl_btn.setFixedSize(24, 24)
        self._dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dl_btn.setToolTip("下载")
        self._dl_btn.setStyleSheet("""
            QPushButton {
                background: rgba(139,92,246,0.2);
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: rgba(139,92,246,0.35);
            }
        """)
        self._dl_btn.clicked.connect(lambda: self.download_clicked.emit(self._video))
        layout.addWidget(self._dl_btn)

        # Info icon button
        self._info_btn = QPushButton()
        self._info_btn.setIcon(_make_info_icon())
        self._info_btn.setIconSize(QSize(_ICON_SZ, _ICON_SZ))
        self._info_btn.setFixedSize(24, 24)
        self._info_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._info_btn.setToolTip("详情")
        self._info_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.08);
            }
        """)
        self._info_btn.clicked.connect(lambda: self.info_clicked.emit(self._video))
        layout.addWidget(self._info_btn)

    def set_format(self, fmt: str):
        self._video.format_hint = fmt
        self._badge.setText(fmt)


class _MediaCard(QWidget):
    """Grid view card — compact card with badge, name, icon buttons."""
    download_clicked = pyqtSignal(object)
    info_clicked = pyqtSignal(object)

    def __init__(self, video: SniffedVideo, parent=None):
        super().__init__(parent)
        self._video = video
        self.setFixedSize(112, 84)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(
            "_MediaCard { background: rgba(255,255,255,0.04); border-radius: 6px; }"
            "_MediaCard:hover { background: rgba(255,255,255,0.09); }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Format badge
        self._badge = QLabel(self._video.format_hint)
        self._badge.setFixedHeight(18)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setStyleSheet("""
            background-color: rgba(139,92,246,0.15);
            color: #a78bfa;
            border-radius: 3px;
            font-size: 9px;
            font-weight: 600;
        """)
        layout.addWidget(self._badge)

        # URI name
        name = _uri_label(self._video.url)
        self._name_label = QLabel(name)
        self._name_label.setStyleSheet(
            "color: #ddd6fe; font-size: 10px; font-weight: 600; background: transparent;"
        )
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setWordWrap(True)
        self._name_label.setToolTip(self._video.url)
        layout.addWidget(self._name_label, 1)

        # Icon buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.addStretch()

        self._dl_btn = QPushButton()
        self._dl_btn.setIcon(_make_download_icon())
        self._dl_btn.setIconSize(QSize(_ICON_SZ, _ICON_SZ))
        self._dl_btn.setFixedSize(22, 22)
        self._dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dl_btn.setToolTip("下载")
        self._dl_btn.setStyleSheet("""
            QPushButton {
                background: rgba(139,92,246,0.2);
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background: rgba(139,92,246,0.35);
            }
        """)
        self._dl_btn.clicked.connect(lambda: self.download_clicked.emit(self._video))
        btn_row.addWidget(self._dl_btn)

        self._info_btn = QPushButton()
        self._info_btn.setIcon(_make_info_icon())
        self._info_btn.setIconSize(QSize(_ICON_SZ, _ICON_SZ))
        self._info_btn.setFixedSize(22, 22)
        self._info_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._info_btn.setToolTip("详情")
        self._info_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.08);
            }
        """)
        self._info_btn.clicked.connect(lambda: self.info_clicked.emit(self._video))
        btn_row.addWidget(self._info_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    def set_format(self, fmt: str):
        self._video.format_hint = fmt
        self._badge.setText(fmt)


class SniffPanel(QWidget):
    download_requested = pyqtSignal(object)
    download_all_requested = pyqtSignal()
    cleared = pyqtSignal()

    VIEW_LIST = "list"
    VIEW_GRID = "grid"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(_PANEL_W)
        self.setStyleSheet(
            "background: #241f38; border-left: 1px solid rgba(255,255,255,0.06);"
        )
        self._videos: list[SniffedVideo] = []
        self._rows: list[_MediaRow] = []
        self._cards: list[_MediaCard] = []
        self._seen_urls: set[str] = set()
        self._probing: dict[QNetworkReply, tuple[SniffedVideo, object]] = {}
        self._nam = QNetworkAccessManager(self)
        self._nam.finished.connect(self._on_probe_finished)
        self._view_mode = self.VIEW_LIST
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        header.setFixedHeight(36)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 0, 8, 0)
        header_layout.setSpacing(4)

        self._count_label = QLabel("嗅探到 0 个资源")
        self._count_label.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: rgba(255,255,255,0.5); background: transparent;"
        )
        header_layout.addWidget(self._count_label)
        header_layout.addStretch()

        # View toggle
        self._view_toggle_btn = QPushButton("☰")
        self._view_toggle_btn.setFixedSize(24, 24)
        self._view_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._view_toggle_btn.setToolTip("切换网格视图")
        self._view_toggle_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06);
                color: #c4b5fd;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.12); }
        """)
        self._view_toggle_btn.clicked.connect(self._toggle_view)
        header_layout.addWidget(self._view_toggle_btn)

        # Close
        self._close_btn = QPushButton("×")
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setToolTip("关闭面板")
        self._close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(255,255,255,0.3);
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.1); color: #ffffff; }
        """)
        self._close_btn.clicked.connect(self._close_panel)
        header_layout.addWidget(self._close_btn)

        layout.addWidget(header)

        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: rgba(255,255,255,0.06);")
        layout.addWidget(divider)

        # ── Stacked widget: list / grid ──
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")

        # List view (index 0)
        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 2, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()

        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._list_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent;
                width: 4px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.08);
                border-radius: 2px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255,255,255,0.15);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        self._list_scroll.setWidget(self._list_container)
        self._stack.addWidget(self._list_scroll)

        # Grid view (index 1)
        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(6, 6, 6, 6)
        self._grid_layout.setSpacing(6)
        self._grid_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )

        self._grid_scroll = QScrollArea()
        self._grid_scroll.setWidgetResizable(True)
        self._grid_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._grid_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent;
                width: 4px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.08);
                border-radius: 2px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255,255,255,0.15);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        self._grid_scroll.setWidget(self._grid_container)
        self._stack.addWidget(self._grid_scroll)

        layout.addWidget(self._stack, 1)

        # ── Bottom bar ──
        bottom = QWidget()
        bottom.setFixedHeight(32)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(10, 0, 8, 0)

        self._all_btn = QPushButton("全部下载")
        self._all_btn.setFixedSize(64, 22)
        self._all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._all_btn.setStyleSheet("""
            QPushButton {
                background: rgba(139,92,246,0.2);
                color: #ffffff;
                border: none;
                border-radius: 4px;
                font-size: 10px;
                font-weight: 600;
            }
            QPushButton:hover { background: rgba(139,92,246,0.35); }
        """)
        self._all_btn.clicked.connect(self.download_all_requested.emit)
        bottom_layout.addWidget(self._all_btn)

        bottom_layout.addStretch()

        self._clear_btn = QPushButton("清除")
        self._clear_btn.setFixedSize(48, 22)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.05);
                color: rgba(255,255,255,0.6);
                border: none;
                border-radius: 4px;
                font-size: 10px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.1); color: #ffffff; }
        """)
        self._clear_btn.clicked.connect(self.clear)
        bottom_layout.addWidget(self._clear_btn)
        layout.addWidget(bottom)

    def _toggle_view(self):
        if self._view_mode == self.VIEW_LIST:
            self._view_mode = self.VIEW_GRID
            self._view_toggle_btn.setText("≡")
            self._view_toggle_btn.setToolTip("切换列表视图")
            self._stack.setCurrentIndex(1)
        else:
            self._view_mode = self.VIEW_LIST
            self._view_toggle_btn.setText("☰")
            self._view_toggle_btn.setToolTip("切换网格视图")
            self._stack.setCurrentIndex(0)

    def _close_panel(self):
        self.hide()

    def add_video(self, video: SniffedVideo):
        if video.url in self._seen_urls:
            return
        basename = urlparse(video.url).path.split("/")[-1].lower()
        if any(
            basename.endswith(s)
            for s in (
                ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp",
                ".css", ".js", ".woff2", ".woff", ".ttf",
            )
        ):
            return
        self._seen_urls.add(video.url)
        self._videos.append(video)

        # List row
        row = _MediaRow(video)
        row.download_clicked.connect(self.download_requested.emit)
        row.info_clicked.connect(self._show_detail)
        self._rows.append(row)

        # Grid card
        card = _MediaCard(video)
        card.download_clicked.connect(self.download_requested.emit)
        card.info_clicked.connect(self._show_detail)
        self._cards.append(card)

        # Add to list layout (before stretch)
        idx = self._list_layout.count() - 1
        self._list_layout.insertWidget(idx, row)
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.04);")
        self._list_layout.insertWidget(idx + 1, sep)

        # Add to grid layout (2 columns)
        card_idx = len(self._cards) - 1
        self._grid_layout.addWidget(card, card_idx // 2, card_idx % 2)

        self._count_label.setText(f"嗅探到 {len(self._videos)} 个资源")

        # Probe unknown format via HEAD request
        if video.format_hint == "media":
            request = QNetworkRequest(QUrl(video.url))
            request.setRawHeader(b"Range", b"bytes=0-0")
            reply = self._nam.head(request)
            self._probing[reply] = (video, row)

    def _show_detail(self, video: SniffedVideo):
        _VideoDetailDialog.show_for(video, self)

    def _on_probe_finished(self, reply: QNetworkReply):
        entry = self._probing.pop(reply, None)
        if entry is None:
            reply.deleteLater()
            return
        video, row = entry

        if reply.error() == QNetworkReply.NetworkError.NoError:
            content_type = reply.header(
                QNetworkRequest.KnownHeaders.ContentTypeHeader
            )
            content_length = reply.header(
                QNetworkRequest.KnownHeaders.ContentLengthHeader
            )
            if content_length is not None and content_length > 0:
                video.content_length = int(content_length)
            if content_type:
                mime = content_type.split(";")[0].strip().lower()
                fmt = _CONTENT_TYPE_FORMAT.get(mime, "media")
                if fmt != "media":
                    row.set_format(fmt)
                    for card in self._cards:
                        if card._video is video:
                            card.set_format(fmt)
                            break
        reply.deleteLater()

    def clear(self):
        self._videos.clear()
        self._seen_urls.clear()

        for row in self._rows:
            try:
                row.download_clicked.disconnect()
            except TypeError:
                pass
            try:
                row.info_clicked.disconnect()
            except TypeError:
                pass
            self._list_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        while self._list_layout.count() > 0:
            item = self._list_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._list_layout.addStretch()

        for card in self._cards:
            try:
                card.download_clicked.disconnect()
            except TypeError:
                pass
            try:
                card.info_clicked.disconnect()
            except TypeError:
                pass
            self._grid_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        self._count_label.setText("嗅探到 0 个资源")
        self.cleared.emit()

    @property
    def videos(self) -> list[SniffedVideo]:
        return list(self._videos)
