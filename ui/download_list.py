from urllib.parse import urlparse

from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QSize
from PyQt6.QtGui import QColor, QPainter, QPixmap, QIcon, QPainterPath
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QGraphicsDropShadowEffect,
)

from core.task import DownloadTask, TaskStatus


def _format_type(url: str, format_hint: str = "") -> str:
    """优先用 format_hint，否则从 URL 文件扩展名推断。"""
    if format_hint:
        hint = format_hint.upper()
        if hint in ("M3U8", "MP4", "FLV", "WEBM", "MPD", "TS", "DASH"):
            return hint
    path = urlparse(url).path.lower()
    if "." in path:
        ext = path.rsplit(".", 1)[-1]
        if ext in ("m3u8", "mp4", "flv", "m4s", "webm", "mpd", "ts", "dash"):
            return ext.upper()
    return "未知"


def _info_label(text: str = "", color: str = "rgba(255,255,255,0.4)") -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"font-size: 10px; color: {color}; font-weight: 500; background: transparent;")
    lbl.setWordWrap(False)
    return lbl


def _make_trash_icon() -> QIcon:
    """High-res trash icon for item removal."""
    size = 18
    dpr = 2.0
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.fill(QColor(0, 0, 0, 0))
    pixmap.setDevicePixelRatio(dpr)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("rgba(255,255,255,0.4)"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    p.drawRect(5, 5, 8, 10)
    p.drawLine(3, 5, 15, 5)
    p.drawLine(7, 3, 11, 3)
    p.drawLine(8, 7, 8, 13)
    p.drawLine(10, 7, 10, 13)
    p.end()
    return QIcon(pixmap)


class DownloadItemWidget(QWidget):
    cancel_clicked = pyqtSignal(str)
    retry_clicked = pyqtSignal(str)
    remove_clicked = pyqtSignal(str)
    pause_clicked = pyqtSignal(str)
    resume_clicked = pyqtSignal(str)

    def __init__(self, task: DownloadTask, parent=None):
        super().__init__(parent)
        self._task_id = task.id
        self._current_task = task
        self._pixmap: QPixmap | None = None
        self._setup_ui(task)

    def _setup_ui(self, task: DownloadTask):
        self.setFixedHeight(100)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 6, 12, 6)
        main_layout.setSpacing(0)
        
        self._card = QWidget()
        self._card.setObjectName("card")
        self._card.setStyleSheet("""
            QWidget#card {
                background-color: #342c4d;
                border: 1px solid rgba(255,255,255,0.03);
                border-radius: 12px;
            }
            QWidget#card:hover {
                background-color: #3d345c;
                border-color: rgba(139,92,246,0.15);
            }
        """)
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 4)
        self._card.setGraphicsEffect(shadow)
        
        card_layout = QHBoxLayout(self._card)
        card_layout.setContentsMargins(16, 10, 12, 10)
        card_layout.setSpacing(12)

        # Background thumbnail label
        self._bg_label = QLabel(self._card)
        self._bg_label.lower()
        self._bg_label.hide()

        # ── Left: Info ──
        info_area = QVBoxLayout()
        info_area.setSpacing(4)
        
        self._title = QLabel(task.title or task.url)
        self._title.setStyleSheet("font-size: 13px; font-weight: 700; color: #e2e8f0; background: transparent;")
        self._title.setWordWrap(False)
        self._title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        info_area.addWidget(self._title)

        info_area.addStretch()

        # Meta Row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(14)
        meta_row.setAlignment(Qt.AlignmentFlag.AlignBottom)

        self._pct_lbl = _info_label("0%", "#a78bfa")
        self._pct_lbl.setStyleSheet("font-size: 11px; color: #a78bfa; font-weight: 800; background: transparent;")
        meta_row.addWidget(self._pct_lbl)
        self._size_lbl = _info_label("--")
        meta_row.addWidget(self._size_lbl)
        self._speed_lbl = _info_label("")
        meta_row.addWidget(self._speed_lbl)
        self._type_lbl = _info_label(_format_type(task.url, task.format_hint), "rgba(255,255,255,0.15)")
        self._type_lbl.setStyleSheet("font-size: 9px; color: rgba(255,255,255,0.15); font-weight: 900; background: transparent;")
        meta_row.addWidget(self._type_lbl)
        meta_row.addStretch()
        info_area.addLayout(meta_row)
        
        card_layout.addLayout(info_area, 1)

        # ── Right: Action Column (Trash on top, Button below) ──
        action_col = QVBoxLayout()
        action_col.setSpacing(8)
        action_col.setContentsMargins(0, 0, 0, 0)
        action_col.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._remove_btn = QPushButton()
        self._remove_btn.setFixedSize(22, 22)
        self._remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_btn.setIcon(_make_trash_icon())
        self._remove_btn.setToolTip("移除任务")
        self._remove_btn.setStyleSheet("""
            QPushButton { background: transparent; border-radius: 4px; }
            QPushButton:hover { background: rgba(239, 68, 68, 0.15); }
        """)
        self._remove_btn.clicked.connect(lambda: self.remove_clicked.emit(self._task_id))
        action_col.addWidget(self._remove_btn, 0, Qt.AlignmentFlag.AlignRight)

        action_col.addStretch()

        self._action_btn = QPushButton("暂停")
        self._action_btn.setFixedSize(44, 20)
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(139,92,246,0.12);
                color: #c4b5fd;
                border: none;
                border-radius: 6px;
                font-size: 10px;
                font-weight: 700;
            }
            QPushButton:hover { background-color: rgba(139,92,246,0.25); color: #ffffff; }
        """)
        self._action_btn.clicked.connect(self._on_action_clicked)
        action_col.addWidget(self._action_btn)

        card_layout.addLayout(action_col)
        main_layout.addWidget(self._card)

        self.update_task(task)

    def _on_action_clicked(self):
        task = self._current_task
        if not task: return
        s = task.status
        if s == TaskStatus.COMPLETED: self.remove_clicked.emit(self._task_id)
        elif s == TaskStatus.FAILED: self.retry_clicked.emit(self._task_id)
        elif s == TaskStatus.CANCELLED: self.remove_clicked.emit(self._task_id)
        elif s == TaskStatus.DOWNLOADING: self.pause_clicked.emit(self._task_id)
        elif s == TaskStatus.PAUSED: self.resume_clicked.emit(self._task_id)
        else: self.cancel_clicked.emit(self._task_id)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_card") and hasattr(self, "_bg_label"):
            self._bg_label.setFixedSize(self._card.size())
            if self._pixmap and not self._pixmap.isNull():
                self.set_thumbnail(self._pixmap)

    def set_thumbnail(self, pixmap: QPixmap):
        self._pixmap = pixmap
        try:
            target_size = self._card.size()
            if target_size.width() <= 0: return
            scaled = pixmap.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            canvas = QPixmap(target_size)
            canvas.fill(Qt.GlobalColor.transparent)
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(0, 0, target_size.width(), target_size.height(), 12, 12)
            painter.setClipPath(path)
            painter.setOpacity(0.18)
            x = (target_size.width() - scaled.width()) // 2
            y = (target_size.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.end()
            self._bg_label.setPixmap(canvas)
            self._bg_label.show()
        except Exception: pass

    def update_task(self, task: DownloadTask):
        self._current_task = task
        self._title.setText(task.title or task.url)
        
        if task.status == TaskStatus.PENDING:
            self._pct_lbl.setText("等待中")
            self._size_lbl.setText("--")
            self._speed_lbl.hide()
            self._action_btn.setText("取消")
            self._action_btn.show()
        elif task.status == TaskStatus.DOWNLOADING:
            self._pct_lbl.setText(f"{int(task.progress)}%")
            self._size_lbl.setText(task.size_downloaded or task.size_total or "--")
            self._speed_lbl.setText(task.speed or "")
            self._speed_lbl.show()
            self._action_btn.setText("暂停")
            self._action_btn.show()
        elif task.status == TaskStatus.PAUSED:
            self._pct_lbl.setText(f"{int(task.progress)}%")
            self._size_lbl.setText(task.size_downloaded or "--")
            self._speed_lbl.hide()
            self._action_btn.setText("继续")
            self._action_btn.show()
        elif task.status == TaskStatus.MERGING:
            self._pct_lbl.setText("合并中")
            self._size_lbl.setText(task.size_total or "--")
            self._speed_lbl.hide()
            self._action_btn.setText("取消")
            self._action_btn.show()
        elif task.status == TaskStatus.COMPLETED:
            self._pct_lbl.setText("已完成")
            self._pct_lbl.setStyleSheet("font-size: 11px; color: #4ade80; font-weight: 800; background: transparent;")
            self._size_lbl.setText(task.size_total or "--")
            self._speed_lbl.hide()
            self._action_btn.hide() # HIDE ACTION BUTTON WHEN DONE
        elif task.status == TaskStatus.FAILED:
            self._pct_lbl.setText("失败")
            self._pct_lbl.setStyleSheet("font-size: 11px; color: #ef4444; font-weight: 800; background: transparent;")
            self._speed_lbl.hide()
            self._action_btn.setText("重试")
            self._action_btn.show()
        elif task.status == TaskStatus.CANCELLED:
            self._pct_lbl.setText("已取消")
            self._speed_lbl.hide()
            self._action_btn.setText("重试")
            self._action_btn.show()


class DownloadListWidget(QWidget):
    cancel_requested = pyqtSignal(str)
    retry_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str)
    pause_requested = pyqtSignal(str)
    resume_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: dict[str, DownloadTask] = {}
        self._item_widgets: dict[str, DownloadItemWidget] = {}
        self._nam = QNetworkAccessManager(self)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.08);
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 10, 0, 10)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_widget)
        layout.addWidget(self._scroll)

    def add_task(self, task: DownloadTask):
        self._tasks[task.id] = task
        item_widget = DownloadItemWidget(task)
        item_widget.cancel_clicked.connect(self.cancel_requested.emit)
        item_widget.retry_clicked.connect(self.retry_requested.emit)
        item_widget.remove_clicked.connect(self.remove_requested.emit)
        item_widget.pause_clicked.connect(self.pause_requested.emit)
        item_widget.resume_clicked.connect(self.resume_requested.emit)
        self._item_widgets[task.id] = item_widget
        self._list_layout.insertWidget(self._list_layout.count() - 1, item_widget)
        if task.thumbnail: self._load_thumbnail(task.id, task.thumbnail)

    def remove_task(self, task_id: str):
        widget = self._item_widgets.pop(task_id, None)
        if widget:
            self._list_layout.removeWidget(widget)
            widget.deleteLater()
        self._tasks.pop(task_id, None)

    def clear_completed(self):
        for task_id in list(self._tasks.keys()):
            if self._tasks[task_id].is_finished:
                self.remove_task(task_id)

    def _load_thumbnail(self, task_id: str, url: str):
        request = QNetworkRequest(QUrl(url))
        reply = self._nam.get(request)
        reply.finished.connect(lambda: self._on_thumbnail_loaded(task_id, reply))

    def _on_thumbnail_loaded(self, task_id: str, reply: QNetworkReply):
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pixmap = QPixmap()
            if pixmap.loadFromData(reply.readAll()):
                widget = self._item_widgets.get(task_id)
                if widget: widget.set_thumbnail(pixmap)
        reply.deleteLater()

    def update_task(self, task: DownloadTask):
        if task.id not in self._tasks: return
        self._tasks[task.id] = task
        widget = self._item_widgets.get(task.id)
        if widget: widget.update_task(task)

    def update_thumbnail(self, task_id: str, pixmap: QPixmap):
        widget = self._item_widgets.get(task_id)
        if widget: widget.set_thumbnail(pixmap)

    def item_at(self, pos) -> DownloadItemWidget | None:
        child = self._list_widget.childAt(self._list_widget.mapFrom(self, pos))
        while child:
            if isinstance(child, DownloadItemWidget): return child
            child = child.parentWidget()
        return None
