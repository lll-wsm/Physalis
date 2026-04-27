from urllib.parse import urlparse

from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
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


def _info_label(text: str = "", color: str = "rgba(255,255,255,0.55)") -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"font-size: 12px; color: {color};")
    lbl.setWordWrap(False)
    return lbl


class DownloadItemWidget(QWidget):
    cancel_clicked = pyqtSignal(str)  # task_id
    retry_clicked = pyqtSignal(str)   # task_id
    remove_clicked = pyqtSignal(str)  # task_id

    def __init__(self, task: DownloadTask, parent=None):
        super().__init__(parent)
        self._task_id = task.id
        self._current_task = task
        self._pixmap: QPixmap | None = None
        self._setup_ui(task)

    def _setup_ui(self, task: DownloadTask):
        self.setFixedHeight(80)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        # 左侧信息区
        left_layout = QVBoxLayout()
        left_layout.setSpacing(6)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._title = QLabel(task.title or task.url)
        self._title.setStyleSheet("font-size: 14px; font-weight: 600; color: #ddd6fe;")
        self._title.setWordWrap(False)
        self._title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._title.setToolTip(task.title or task.url)
        left_layout.addWidget(self._title)

        # 信息行：大小 | 速度 | 百分比 | 类型
        info_row = QHBoxLayout()
        info_row.setSpacing(16)
        info_row.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._size_lbl = _info_label("--")
        self._size_lbl.setMinimumWidth(80)
        info_row.addWidget(self._size_lbl)

        self._speed_lbl = _info_label("--")
        self._speed_lbl.setMinimumWidth(70)
        info_row.addWidget(self._speed_lbl)

        self._pct_lbl = _info_label("0%")
        self._pct_lbl.setMinimumWidth(50)
        info_row.addWidget(self._pct_lbl)

        self._type_lbl = _info_label(_format_type(task.url, task.format_hint))
        info_row.addWidget(self._type_lbl)

        info_row.addStretch()
        left_layout.addLayout(info_row)

        layout.addLayout(left_layout, 1)

        # 操作按钮（根据状态变化，初始为取消）
        self._action_btn = QPushButton("取消")
        self._action_btn.setFixedSize(52, 28)
        self._action_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0,0,0,0.35);
                color: rgba(255,255,255,0.85);
                border: none;
                border-radius: 6px;
                padding: 0px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(0,0,0,0.5);
            }
            QPushButton:disabled {
                background-color: rgba(0,0,0,0.2);
                color: rgba(255,255,255,0.35);
            }
        """)
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.clicked.connect(self._on_action_clicked)
        layout.addWidget(self._action_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Initialize button state for the initial task status
        self.update_task(task)

    def _on_action_clicked(self):
        task = self._current_task
        if not task:
            return
        if task.status == TaskStatus.COMPLETED:
            self.remove_clicked.emit(self._task_id)
        elif task.status == TaskStatus.FAILED:
            self.retry_clicked.emit(self._task_id)
        elif task.status == TaskStatus.CANCELLED:
            self.remove_clicked.emit(self._task_id)
        else:
            self.cancel_clicked.emit(self._task_id)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                rect.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (scaled.width() - rect.width()) // 2
            y = (scaled.height() - rect.height()) // 2
            painter.drawPixmap(-x, -y, scaled)
            # Dark overlay so text remains readable over thumbnail
            painter.fillRect(rect, QColor(0, 0, 0, 160))
        else:
            painter.fillRect(rect, QColor("#2d2640"))

        painter.end()
        super().paintEvent(event)

    def set_thumbnail(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.update()

    def update_task(self, task: DownloadTask):
        self._current_task = task
        self._title.setText(task.title or task.url)
        self._title.setToolTip(task.title or task.url)
        self._pct_lbl.setText(f"{int(task.progress)}%")

        if task.status == TaskStatus.PENDING:
            self._size_lbl.setText("--")
            self._speed_lbl.setText("--")
            self._pct_lbl.setText("等待中")
            self._size_lbl.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.55);")
            self._speed_lbl.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.55);")
            self._pct_lbl.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.55);")
            self._action_btn.setText("取消")
            self._action_btn.setEnabled(True)
        elif task.status == TaskStatus.DOWNLOADING:
            self._size_lbl.setText(task.size_downloaded or task.size_total or "--")
            self._speed_lbl.setText(task.speed or "--")
            if task.progress > 0:
                self._pct_lbl.setText(f"{int(task.progress)}%")
            else:
                self._pct_lbl.setText("下载中")
            self._size_lbl.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.55);")
            self._speed_lbl.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.55);")
            self._pct_lbl.setStyleSheet("font-size: 12px; color: #a78bfa; font-weight: 600;")
            self._action_btn.setText("取消")
            self._action_btn.setEnabled(True)
        elif task.status == TaskStatus.MERGING:
            self._size_lbl.setText(task.size_total or "--")
            self._speed_lbl.setText("--")
            self._pct_lbl.setText("合并中")
            self._pct_lbl.setStyleSheet("font-size: 12px; color: #fbbf24; font-weight: 600;")
            self._action_btn.setText("取消")
            self._action_btn.setEnabled(True)
        elif task.status == TaskStatus.COMPLETED:
            self._size_lbl.setText(task.size_total or "--")
            self._speed_lbl.setText("--")
            self._pct_lbl.setText("已完成")
            self._pct_lbl.setStyleSheet("font-size: 12px; color: #34d399; font-weight: 600;")
            self._action_btn.setText("删除")
            self._action_btn.setEnabled(True)
        elif task.status == TaskStatus.FAILED:
            self._pct_lbl.setText("失败")
            self._pct_lbl.setStyleSheet("font-size: 12px; color: #f87171; font-weight: 600;")
            self._action_btn.setText("重试")
            self._action_btn.setEnabled(True)
        elif task.status == TaskStatus.CANCELLED:
            self._pct_lbl.setText("已取消")
            self._pct_lbl.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.35);")
            self._action_btn.setText("删除")
            self._action_btn.setEnabled(True)


class DownloadListWidget(QWidget):
    cancel_requested = pyqtSignal(str)  # task_id
    retry_requested = pyqtSignal(str)   # task_id
    remove_requested = pyqtSignal(str)  # task_id

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
                border-radius: 4px;
            }
            QScrollBar:handle:vertical {
                background: rgba(255,255,255,0.12);
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar:handle:vertical:hover {
                background: rgba(255,255,255,0.2);
            }
            QScrollBar:add-line:vertical, QScrollBar:sub-line:vertical {
                height: 0px;
            }
        """)

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_widget)
        layout.addWidget(self._scroll)

    def add_task(self, task: DownloadTask):
        self._tasks[task.id] = task

        item_widget = DownloadItemWidget(task)
        item_widget.cancel_clicked.connect(self.cancel_requested.emit)
        item_widget.retry_clicked.connect(self.retry_requested.emit)
        item_widget.remove_clicked.connect(self.remove_requested.emit)
        self._item_widgets[task.id] = item_widget

        # Insert before the stretch
        self._list_layout.insertWidget(self._list_layout.count() - 1, item_widget)

        if task.thumbnail:
            self._load_thumbnail(task.id, task.thumbnail)

    def remove_task(self, task_id: str):
        """Remove a task widget from the list."""
        widget = self._item_widgets.pop(task_id, None)
        if widget:
            try:
                widget.cancel_clicked.disconnect()
            except TypeError:
                pass
            try:
                widget.retry_clicked.disconnect()
            except TypeError:
                pass
            try:
                widget.remove_clicked.disconnect()
            except TypeError:
                pass
            self._list_layout.removeWidget(widget)
            widget.deleteLater()
        self._tasks.pop(task_id, None)

    def clear_completed(self):
        """Remove all finished tasks (completed, failed, or cancelled)."""
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
                if widget:
                    widget.set_thumbnail(pixmap)
        reply.deleteLater()

    def update_task(self, task: DownloadTask):
        if task.id not in self._tasks:
            return
        self._tasks[task.id] = task

        widget = self._item_widgets.get(task.id)
        if widget:
            widget.update_task(task)

    def update_thumbnail(self, task_id: str, pixmap: QPixmap):
        """Update the background thumbnail for a specific task widget."""
        widget = self._item_widgets.get(task_id)
        if widget:
            widget.set_thumbnail(pixmap)

    def item_at(self, pos) -> DownloadItemWidget | None:
        """Find the task widget at a specific local position."""
        child = self._list_widget.childAt(self._list_widget.mapFrom(self, pos))
        while child:
            if isinstance(child, DownloadItemWidget):
                return child
            child = child.parentWidget()
        return None
