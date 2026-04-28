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


def _create_hq_pixmap(size: int) -> QPixmap:
    """Create a High-DPI aware transparent pixmap."""
    from PyQt6.QtWidgets import QApplication
    # Use 2.0 as a standard multiplier for Retina/High-DPI
    dpr = 2.0 
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def _make_download_icon() -> QIcon:
    """Downward arrow."""
    pixmap = _create_hq_pixmap(_ICON_SZ)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    p.drawLine(_ICON_SZ // 2, 2, _ICON_SZ // 2, _ICON_SZ - 4)
    p.drawLine(_ICON_SZ // 2, _ICON_SZ - 4, _ICON_SZ // 2 - 4, _ICON_SZ // 2)
    p.drawLine(_ICON_SZ // 2, _ICON_SZ - 4, _ICON_SZ // 2 + 4, _ICON_SZ // 2)
    p.end()
    return QIcon(pixmap)


def _make_info_icon() -> QIcon:
    """Circled 'i'."""
    pixmap = _create_hq_pixmap(_ICON_SZ)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    p.drawEllipse(2, 2, _ICON_SZ - 4, _ICON_SZ - 4)
    p.drawPoint(_ICON_SZ // 2, 5)
    p.drawLine(_ICON_SZ // 2, 7, _ICON_SZ // 2, _ICON_SZ - 6)
    p.end()
    return QIcon(pixmap)


def _make_cookie_icon() -> QIcon:
    """Simplified cookie icon."""
    pixmap = _create_hq_pixmap(_ICON_SZ)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#a78bfa"))
    p.drawEllipse(2, 2, _ICON_SZ - 4, _ICON_SZ - 4)
    p.setBrush(QColor("#2d2640"))
    p.drawEllipse(5, 6, 2, 2)
    p.drawEllipse(9, 5, 2, 2)
    p.drawEllipse(7, 10, 2, 2)
    p.end()
    return QIcon(pixmap)


def _make_rule_icon() -> QIcon:
    """List/Rules icon."""
    pixmap = _create_hq_pixmap(_ICON_SZ)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#a78bfa"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    for y in (5, 8, 11):
        p.drawEllipse(3, y - 1, 2, 2)
        p.drawLine(7, y, _ICON_SZ - 3, y)
    p.end()
    return QIcon(pixmap)


def _make_panel_toggle_icon(active=True) -> QIcon:
    """Sidebar layout icon."""
    pixmap = _create_hq_pixmap(_ICON_SZ)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#a78bfa") if active else QColor("rgba(255,255,255,0.3)"))
    pen.setWidthF(1.2)
    p.setPen(pen)
    p.drawRect(2, 3, _ICON_SZ - 4, _ICON_SZ - 6)
    p.drawLine(_ICON_SZ - 7, 3, _ICON_SZ - 7, _ICON_SZ - 4)
    if active:
        p.setBrush(QColor("rgba(167,139,250,0.4)"))
        p.drawRect(_ICON_SZ - 6, 4, 3, _ICON_SZ - 8)
    p.end()
    return QIcon(pixmap)


def _make_list_view_icon() -> QIcon:
    """Standard list icon."""
    pixmap = _create_hq_pixmap(_ICON_SZ)
    p = QPainter(pixmap)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    for y in (4, 8, 12):
        p.drawLine(3, y, _ICON_SZ - 3, y)
    p.end()
    return QIcon(pixmap)


def _make_grid_view_icon() -> QIcon:
    """2x2 grid icon."""
    pixmap = _create_hq_pixmap(_ICON_SZ)
    p = QPainter(pixmap)
    p.setBrush(QColor("#c4b5fd"))
    p.setPen(Qt.PenStyle.NoPen)
    for x in (3, 9):
        for y in (3, 9):
            p.drawRect(x, y, 4, 4)
    p.end()
    return QIcon(pixmap)


def _make_close_icon() -> QIcon:
    """Simple 'X' icon."""
    pixmap = _create_hq_pixmap(_ICON_SZ)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("rgba(255,255,255,0.4)"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    p.drawLine(5, 5, _ICON_SZ - 5, _ICON_SZ - 5)
    p.drawLine(_ICON_SZ - 5, 5, 5, _ICON_SZ - 5)
    p.end()
    return QIcon(pixmap)


def _make_download_all_icon() -> QIcon:
    """Download all icon: Box with arrow."""
    pixmap = _create_hq_pixmap(_ICON_SZ)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#ffffff"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    p.drawLine(3, 10, 3, 13)
    p.drawLine(3, 13, _ICON_SZ - 3, 13)
    p.drawLine(_ICON_SZ - 3, 13, _ICON_SZ - 3, 10)
    p.drawLine(_ICON_SZ // 2, 2, _ICON_SZ // 2, 9)
    p.drawLine(_ICON_SZ // 2, 9, _ICON_SZ // 2 - 3, 6)
    p.drawLine(_ICON_SZ // 2, 9, _ICON_SZ // 2 + 3, 6)
    p.end()
    return QIcon(pixmap)


def _make_trash_icon() -> QIcon:
    """Trash/Clear icon."""
    pixmap = _create_hq_pixmap(_ICON_SZ)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("rgba(255,255,255,0.4)"))
    pen.setWidthF(1.2)
    p.setPen(pen)
    p.drawRect(5, 5, 6, 8)
    p.drawLine(3, 5, 13, 5)
    p.drawLine(7, 3, 9, 3)
    p.drawLine(7, 7, 7, 11)
    p.drawLine(9, 7, 9, 11)
    p.end()
    return QIcon(pixmap)


def get_video_display_name(url: str) -> str:
    """Extract a short unique identifier from a video URL."""
    parsed = urlparse(url)
    params = {}
    if parsed.query:
        for pair in parsed.query.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k] = v
    uid = params.get("video_id") or params.get("vid") or params.get("id") or ""
    if uid:
        return uid
    segs = [s for s in parsed.path.split("/") if s]
    for s in reversed(segs):
        if len(s) > 6:
            return s
    if segs:
        return segs[-1]
    return url[:40]


def _uri_label(url: str) -> str:
    return get_video_display_name(url)


def _format_size(bytes_: int) -> str:
    """Format byte count into human-readable string."""
    if bytes_ <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_ < 1024:
            return f"{bytes_:.1f} {unit}"
        bytes_ /= 1024
    return f"{bytes_:.1f} TB"


class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(ev)


class _VideoDetailDialog(QDialog):
    def __init__(self, video: SniffedVideo, parent=None):
        super().__init__(parent)
        self._video = video
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("视频详情")
        self.setMinimumSize(500, 360)
        self.setStyleSheet("""
            QDialog { background-color: #2d2640; color: #e8e8ed; }
            QLabel { color: #c4b5fd; font-size: 12px; font-weight: 600; }
            QTextEdit { background-color: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; color: #ddd6fe; font-size: 12px; padding: 6px; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)
        title = QLabel("视频详情")
        title.setStyleSheet("font-size: 17px; font-weight: 700; color: #ffffff;")
        layout.addWidget(title)
        v = self._video
        layout.addWidget(QLabel("URL"))
        url_edit = QTextEdit()
        url_edit.setPlainText(v.url)
        url_edit.setFixedHeight(56)
        url_edit.setReadOnly(True)
        layout.addWidget(url_edit)
        info_layout = QHBoxLayout()
        info_layout.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(QLabel("类型"))
        type_lbl = QLabel(f"  {v.format_hint} ({v.content_type or '未知'})")
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
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(64, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("QPushButton { background: rgba(255,255,255,0.08); color: #e8e8ed; border: none; border-radius: 6px; font-size: 12px; font-weight: 600; } QPushButton:hover { background: rgba(255,255,255,0.14); }")
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
        self.setFixedHeight(64)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            _MediaRow { background: transparent; border-bottom: 1px solid rgba(255,255,255,0.04); }
            _MediaRow:hover { background: rgba(255, 255, 255, 0.03); }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)

        # 0. Thumbnail with Action Overlay
        self._thumb_container = QWidget()
        self._thumb_container.setFixedSize(80, 45)

        # The actual image
        self._thumb_label = QLabel(self._thumb_container)
        self._thumb_label.setFixedSize(80, 45)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet("""
            background-color: rgba(255,255,255,0.05); 
            border-radius: 4px; 
            border: 1px solid rgba(255,255,255,0.05); 
            color: rgba(255,255,255,0.1); 
            font-size: 14px;
        """)
        self._thumb_label.setText("▶")

        # Action Overlay (Horizontal layout at bottom right of thumb)
        overlay_layout = QHBoxLayout(self._thumb_container)
        overlay_layout.setContentsMargins(2, 2, 2, 2)
        overlay_layout.setSpacing(3)
        overlay_layout.addStretch()

        inner_btn_sz = 18
        icon_sz = 12

        self._info_btn = QPushButton()
        self._info_btn.setFixedSize(inner_btn_sz, inner_btn_sz)
        self._info_btn.setIcon(_make_info_icon())
        self._info_btn.setIconSize(QSize(icon_sz, icon_sz))
        self._info_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._info_btn.setStyleSheet("QPushButton { background: rgba(0,0,0,0.5); border-radius: 3px; } QPushButton:hover { background: rgba(0,0,0,0.8); }")
        self._info_btn.clicked.connect(lambda: self.info_clicked.emit(self._video))
        overlay_layout.addWidget(self._info_btn, 0, Qt.AlignmentFlag.AlignBottom)

        self._dl_btn = QPushButton()
        self._dl_btn.setFixedSize(inner_btn_sz, inner_btn_sz)
        self._dl_btn.setIcon(_make_download_icon())
        self._dl_btn.setIconSize(QSize(icon_sz, icon_sz))
        self._dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dl_btn.setStyleSheet("QPushButton { background: #8b5cf6; border-radius: 3px; } QPushButton:hover { background: #7c3aed; }")
        self._dl_btn.clicked.connect(lambda: self.download_clicked.emit(self._video))
        overlay_layout.addWidget(self._dl_btn, 0, Qt.AlignmentFlag.AlignBottom)

        layout.addWidget(self._thumb_container)

        # 1. Info container (Name + Meta)
        name_container = QVBoxLayout()
        name_container.setSpacing(4)
        name_container.setContentsMargins(0, 0, 0, 0)

        self._name_label = QLabel(_uri_label(self._video.url))
        self._name_label.setStyleSheet("color: #e2e8f0; font-size: 11px; font-weight: 600; background: transparent;")
        self._name_label.setMinimumWidth(10)
        self._name_label.setWordWrap(False)
        self._name_label.setToolTip(self._video.url)
        name_container.addWidget(self._name_label)

        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(6)
        self._badge = QLabel(self._video.format_hint.upper())
        self._badge.setFixedSize(34, 16)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setStyleSheet("background-color: rgba(139,92,246,0.15); color: #a78bfa; border-radius: 3px; font-size: 9px; font-weight: 800;")
        meta_layout.addWidget(self._badge)

        size_text = _format_size(self._video.content_length) if self._video.content_length > 0 else "未知大小"
        self._size_label = QLabel(size_text)
        self._size_label.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 10px;")
        meta_layout.addWidget(self._size_label)

        # 3. MIME Type Label
        self._type_label = ClickableLabel(self._video.content_type)
        self._type_label.setStyleSheet("color: rgba(139,92,246,0.5); font-size: 10px; margin-left: 4px;")
        self._type_label.setToolTip("点击复制 Content-Type")
        self._type_label.clicked.connect(self._copy_type)
        meta_layout.addWidget(self._type_label)

        meta_layout.addStretch()
        name_container.addLayout(meta_layout)
        layout.addLayout(name_container, 1)

    def _copy_type(self):
        if not self._video.content_type: return
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._video.content_type)
        orig = self._type_label.styleSheet()
        self._type_label.setStyleSheet("color: #4ade80; font-size: 10px; margin-left: 4px; font-weight: bold;")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1000, lambda: self._type_label.setStyleSheet(orig))

    def set_thumbnail(self, pixmap: QPixmap):
        try:
            scaled = pixmap.scaled(self._thumb_label.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            rounded = QPixmap(scaled.size())
            rounded.fill(Qt.GlobalColor.transparent)
            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(0, 0, scaled.width(), scaled.height(), 4, 4)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, scaled)
            painter.end()
            self._thumb_label.setPixmap(rounded)
            self._thumb_label.setText("")
        except Exception: pass

    def set_format(self, fmt: str):
        try:
            if not self.isVisible() and self.parent() is None: return
            self._video.format_hint = fmt
            if hasattr(self, "_badge"): self._badge.setText(fmt.upper())
            if hasattr(self, "_type_label"): self._type_label.setText(self._video.content_type)
            if self._video.content_length > 0 and hasattr(self, "_size_label"): self._size_label.setText(_format_size(self._video.content_length))
        except (RuntimeError, AttributeError): pass


class _MediaCard(QWidget):
    download_clicked = pyqtSignal(object)
    info_clicked = pyqtSignal(object)

    def __init__(self, video: SniffedVideo, parent=None):
        super().__init__(parent)
        self._video = video
        self.setFixedSize(112, 84)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("_MediaCard { background: rgba(255,255,255,0.04); border-radius: 6px; } _MediaCard:hover { background: rgba(255,255,255,0.09); }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        self._bg_label = QLabel(self)
        self._bg_label.setFixedSize(self.size())
        self._bg_label.lower()
        self._bg_label.hide()
        self._badge = QLabel(self._video.format_hint.upper())
        self._badge.setFixedHeight(18)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setStyleSheet("background-color: rgba(139,92,246,0.3); color: #ffffff; border-radius: 3px; font-size: 9px; font-weight: 800;")
        layout.addWidget(self._badge)
        self._name_label = QLabel(_uri_label(self._video.url))
        self._name_label.setStyleSheet("color: #ffffff; font-size: 10px; font-weight: 800; background: transparent; text-shadow: 0 1px 2px rgba(0,0,0,0.8);")
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setWordWrap(True)
        layout.addWidget(self._name_label, 1)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.addStretch()
        self._dl_btn = QPushButton()
        self._dl_btn.setIcon(_make_download_icon())
        self._dl_btn.setIconSize(QSize(_ICON_SZ, _ICON_SZ))
        self._dl_btn.setFixedSize(22, 22)
        self._dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dl_btn.setStyleSheet("QPushButton { background: rgba(139,92,246,0.4); border: none; border-radius: 3px; } QPushButton:hover { background: rgba(139,92,246,0.6); }")
        self._dl_btn.clicked.connect(lambda: self.download_clicked.emit(self._video))
        btn_row.addWidget(self._dl_btn)
        self._info_btn = QPushButton()
        self._info_btn.setIcon(_make_info_icon())
        self._info_btn.setIconSize(QSize(_ICON_SZ, _ICON_SZ))
        self._info_btn.setFixedSize(22, 22)
        self._info_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._info_btn.setStyleSheet("QPushButton { background: rgba(0,0,0,0.3); border: none; border-radius: 3px; } QPushButton:hover { background: rgba(0,0,0,0.5); }")
        self._info_btn.clicked.connect(lambda: self.info_clicked.emit(self._video))
        btn_row.addWidget(self._info_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def set_thumbnail(self, pixmap: QPixmap):
        try:
            scaled = pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            darkened = QPixmap(scaled.size())
            darkened.fill(Qt.GlobalColor.transparent)
            painter = QPainter(darkened)
            painter.setOpacity(0.4)
            painter.drawPixmap(0, 0, scaled)
            painter.end()
            self._bg_label.setPixmap(darkened)
            self._bg_label.show()
        except Exception: pass

    def set_format(self, fmt: str):
        try:
            self._video.format_hint = fmt
            if hasattr(self, "_badge"): self._badge.setText(fmt.upper())
        except (RuntimeError, AttributeError): pass


class SniffPanel(QWidget):
    download_requested = pyqtSignal(object)
    download_all_requested = pyqtSignal()
    cleared = pyqtSignal()

    VIEW_LIST = "list"
    VIEW_GRID = "grid"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(_PANEL_W)
        self.setStyleSheet("background: #241f38; border-left: 1px solid rgba(255,255,255,0.06);")
        self._videos: list[SniffedVideo] = []
        self._rows: list[_MediaRow] = []
        self._cards: list[_MediaCard] = []
        self._seen_urls: set[str] = set()
        self._probing: dict[QNetworkReply, tuple[SniffedVideo, object]] = {}
        self._nam = QNetworkAccessManager(self)
        self._nam.finished.connect(self._on_probe_finished)
        self._view_mode = self.VIEW_LIST
        self._page_thumbnail_url = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QWidget()
        header.setStyleSheet("background: rgba(255,255,255,0.02);")
        header.setFixedHeight(44)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 0, 10, 0)
        header_layout.setSpacing(6)
        self._count_label = QLabel("嗅探到 0 个资源")
        self._count_label.setStyleSheet("font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.6); background: transparent;")
        header_layout.addWidget(self._count_label)
        header_layout.addStretch()
        self._view_toggle_btn = QPushButton()
        self._view_toggle_btn.setIcon(_make_grid_view_icon())
        self._view_toggle_btn.setFixedSize(28, 28)
        self._view_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._view_toggle_btn.setStyleSheet("QPushButton { background: rgba(255,255,255,0.06); border: none; border-radius: 6px; } QPushButton:hover { background: rgba(255,255,255,0.12); }")
        self._view_toggle_btn.clicked.connect(self._toggle_view)
        header_layout.addWidget(self._view_toggle_btn)
        self._close_btn = QPushButton()
        self._close_btn.setIcon(_make_close_icon())
        self._close_btn.setFixedSize(28, 28)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet("QPushButton { background: transparent; border: none; border-radius: 6px; } QPushButton:hover { background: rgba(255,255,255,0.1); }")
        self._close_btn.clicked.connect(self.hide)
        header_layout.addWidget(self._close_btn)
        layout.addWidget(header)
        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: rgba(255,255,255,0.08);")
        layout.addWidget(divider)
        self._stack = QStackedWidget()
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()
        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollBar:vertical { background: transparent; width: 6px; } QScrollBar::handle:vertical { background: rgba(255,255,255,0.1); border-radius: 3px; min-height: 30px; margin-right: 1px; } QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.18); } QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }")
        self._list_scroll.setWidget(self._list_container)
        self._stack.addWidget(self._list_scroll)
        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(10, 10, 10, 10)
        self._grid_layout.setSpacing(8)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._grid_scroll = QScrollArea()
        self._grid_scroll.setWidgetResizable(True)
        self._grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._grid_scroll.setStyleSheet(self._list_scroll.styleSheet())
        self._grid_scroll.setWidget(self._grid_container)
        self._stack.addWidget(self._grid_scroll)
        layout.addWidget(self._stack, 1)
        bottom_divider = QWidget()
        bottom_divider.setFixedHeight(1)
        bottom_divider.setStyleSheet("background: rgba(255,255,255,0.06);")
        layout.addWidget(bottom_divider)
        bottom = QWidget()
        bottom.setStyleSheet("background: rgba(0,0,0,0.1);")
        bottom.setFixedHeight(36)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(12, 0, 10, 0)
        bottom_layout.setSpacing(6)
        self._all_btn = QPushButton()
        self._all_btn.setIcon(_make_download_all_icon())
        self._all_btn.setIconSize(QSize(_ICON_SZ, _ICON_SZ))
        self._all_btn.setFixedSize(30, 26)
        self._all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._all_btn.setStyleSheet("QPushButton { background: #8b5cf6; border: none; border-radius: 6px; } QPushButton:hover { background: #7c3aed; } QPushButton:pressed { background: #6d28d9; }")
        self._all_btn.clicked.connect(self.download_all_requested.emit)
        bottom_layout.addWidget(self._all_btn)
        bottom_layout.addStretch()
        self._clear_btn = QPushButton()
        self._clear_btn.setIcon(_make_trash_icon())
        self._clear_btn.setIconSize(QSize(_ICON_SZ, _ICON_SZ))
        self._clear_btn.setFixedSize(30, 26)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setStyleSheet("QPushButton { background: rgba(255,255,255,0.06); border: none; border-radius: 6px; } QPushButton:hover { background: rgba(239, 68, 68, 0.2); }")
        self._clear_btn.clicked.connect(self.clear)
        bottom_layout.addWidget(self._clear_btn)
        layout.addWidget(bottom)

    def _toggle_view(self):
        if self._view_mode == self.VIEW_LIST:
            self._view_mode = self.VIEW_GRID
            self._view_toggle_btn.setIcon(_make_list_view_icon())
            self._stack.setCurrentIndex(1)
        else:
            self._view_mode = self.VIEW_LIST
            self._view_toggle_btn.setIcon(_make_grid_view_icon())
            self._stack.setCurrentIndex(0)

    def add_video(self, video: SniffedVideo):
        # Normalize URL to check for duplicates that differ only by dynamic tokens
        from core.sniffer import _dedup_key
        norm_key = _dedup_key(video.url)
        
        if norm_key in self._seen_urls:
            return
            
        basename = urlparse(video.url).path.split("/")[-1].lower()
        if any(basename.endswith(s) for s in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp", ".css", ".js", ".woff2", ".woff", ".ttf")): return
        
        self._seen_urls.add(norm_key)
        self._videos.append(video)
        row = _MediaRow(video)
        row.download_clicked.connect(self.download_requested.emit)
        row.info_clicked.connect(self._show_detail)
        self._rows.append(row)
        card = _MediaCard(video)
        card.download_clicked.connect(self.download_requested.emit)
        card.info_clicked.connect(self._show_detail)
        self._cards.append(card)
        idx = self._list_layout.count() - 1
        self._list_layout.insertWidget(idx, row)
        card_idx = len(self._cards) - 1
        self._grid_layout.addWidget(card, card_idx // 2, card_idx % 2)
        self._count_label.setText(f"嗅探到 {len(self._videos)} 个资源")
        request = QNetworkRequest(QUrl(video.url))
        if video.referer: request.setRawHeader(b"Referer", video.referer.encode())
        elif video.page_url: request.setRawHeader(b"Referer", video.page_url.encode())
        request.setRawHeader(b"User-Agent", b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
        reply = self._nam.head(request)
        self._probing[reply] = (video, row)

    def update_thumbnail(self, video_url: str, pixmap: QPixmap):
        for row in self._rows:
            if row._video.url == video_url: row.set_thumbnail(pixmap); break
        for card in self._cards:
            if card._video.url == video_url: card.set_thumbnail(pixmap); break

    def set_page_thumbnail(self, thumb_url: str):
        """Compatibility API used by BrowserWindow after page load.

        Keep this method lightweight: per-video thumbnails are still driven by
        ffmpeg extraction / metadata probing via update_thumbnail().
        """
        self._page_thumbnail_url = thumb_url or ""

    def _show_detail(self, video: SniffedVideo):
        _VideoDetailDialog.show_for(video, self)

    def _on_probe_finished(self, reply: QNetworkReply):
        entry = self._probing.pop(reply, None)
        if entry is None: reply.deleteLater(); return
        video, row = entry
        
        from core.config import Config
        config = Config()
        bad_types = [t.strip().lower() for t in config.sniff_filter_types.split(",") if t.strip()]

        # 1. Capture content type from response headers (available even on error sometimes)
        content_type_raw = reply.header(QNetworkRequest.KnownHeaders.ContentTypeHeader)
        if content_type_raw:
            video.content_type = content_type_raw.split(";")[0].strip().lower()

        # 2. Filter Logic (Triggered on BOTH Success and Failure)
        should_remove = False
        if video.content_type:
            if any(bad in video.content_type for bad in bad_types):
                should_remove = True
        elif config.filter_empty_type:
            # If still no content_type after head request, it's truly empty
            should_remove = True

        if should_remove:
            self._remove_video_by_url(video.url)
            reply.deleteLater()
            return

        # 3. Handle successful metadata update
        if reply.error() == QNetworkReply.NetworkError.NoError:
            size = reply.header(QNetworkRequest.KnownHeaders.ContentLengthHeader)
            content_range = reply.rawHeader(b"Content-Range").data().decode()
            if content_range and "/" in content_range:
                try: size = int(content_range.split("/")[-1])
                except ValueError: pass
            if size is not None and int(size) > 0: video.content_length = int(size)
            
            if video.content_type:
                fmt = _CONTENT_TYPE_FORMAT.get(video.content_type, "media")
                video.format_hint = fmt
            
            row.set_format(video.format_hint)
            for card in self._cards:
                if card._video is video: card.set_format(video.format_hint); break
        
        reply.deleteLater()

    def _remove_video_by_url(self, url: str):
        """Remove a video entry from memory and UI."""
        # 1. Remove from lists
        self._videos = [v for v in self._videos if v.url != url]
        self._seen_urls.discard(url)

        # 2. Remove from UI
        for row in list(self._rows):
            if row._video.url == url:
                self._list_layout.removeWidget(row)
                row.deleteLater()
                self._rows.remove(row)
                break
        
        for card in list(self._cards):
            if card._video.url == url:
                self._grid_layout.removeWidget(card)
                card.deleteLater()
                self._cards.remove(card)
                break
        
        self._count_label.setText(f"嗅探到 {len(self._videos)} 个资源")

    def clear(self):
        for reply in list(self._probing.keys()):
            try: reply.abort(); reply.deleteLater()
            except Exception: pass
        self._probing.clear()
        self._videos.clear()
        self._seen_urls.clear()
        for row in self._rows:
            try: row.download_clicked.disconnect(); row.info_clicked.disconnect()
            except TypeError: pass
            self._list_layout.removeWidget(row); row.deleteLater()
        self._rows.clear()
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item and item.widget(): item.widget().deleteLater()
        for card in self._cards:
            try: card.download_clicked.disconnect(); card.info_clicked.disconnect()
            except TypeError: pass
            self._grid_layout.removeWidget(card); card.deleteLater()
        self._cards.clear()
        self._count_label.setText("嗅探到 0 个资源")
        self.cleared.emit()

    @property
    def videos(self) -> list[SniffedVideo]: return list(self._videos)
