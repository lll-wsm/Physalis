import re
import os
import sys
import json
from pathlib import Path
from datetime import datetime

from PyQt6.QtCore import Qt, QSize, QProcess
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QDialog,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.config import Config
from core.downloader import Downloader
from core.task import DownloadTask, TaskStatus
from ui.cookie_manager_dialog import CookieManagerDialog
from ui.download_list import DownloadListWidget
from ui.video_select_dialog import VideoSelectDialog
from ui.browser_window import BrowserWindow, _x_popup_landing_finishes_oauth
from app import MAIN_STYLE_SHEET

ICON_SIZE = 20


class StyledMessageBox(QDialog):
    """A custom purple, semi-transparent, and rounded confirmation dialog."""
    def __init__(self, title, text, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(340)
        self._setup_ui(title, text)

    def _setup_ui(self, title, text):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        container = QWidget()
        container.setObjectName("container")
        container.setStyleSheet("""
            QWidget#container {
                background-color: #241f38;
                border: 1px solid rgba(139,92,246,0.3);
                border-radius: 14px;
            }
            QLabel#title { color: #ffffff; font-size: 15px; font-weight: 700; }
            QLabel#text { color: rgba(255,255,255,0.7); font-size: 13px; line-height: 1.4; }
            QPushButton { 
                background: rgba(255,255,255,0.06); 
                color: #e8e8ed; 
                border-radius: 8px; 
                padding: 8px 16px; 
                font-weight: 600; 
                min-width: 80px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.12); }
            QPushButton#okBtn { background: #8b5cf6; color: #ffffff; }
            QPushButton#okBtn:hover { background: #7c3aed; }
        """)
        
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(20, 20, 20, 20)
        c_layout.setSpacing(16)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("title")
        c_layout.addWidget(title_lbl)

        text_lbl = QLabel(text)
        text_lbl.setObjectName("text")
        text_lbl.setWordWrap(True)
        c_layout.addWidget(text_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = QPushButton("确定")
        ok_btn.setObjectName("okBtn")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)

        c_layout.addLayout(btn_row)
        layout.addWidget(container)

    @classmethod
    def question(cls, parent, title, text):
        dlg = cls(title, text, parent)
        # Center relative to parent
        if parent:
            dlg.move(parent.geometry().center() - dlg.rect().center())
        return dlg.exec() == QDialog.DialogCode.Accepted


def _create_hq_pixmap(size: int) -> QPixmap:
    """Create a High-DPI aware transparent pixmap."""
    dpr = 2.0 
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def _make_browser_icon() -> QIcon:
    pixmap = _create_hq_pixmap(ICON_SIZE)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    p.drawEllipse(2, 2, 16, 16)
    p.drawEllipse(2, 4, 16, 12)
    p.drawLine(10, 2, 10, 18)
    p.drawLine(2, 10, 18, 10)
    p.end()
    return QIcon(pixmap)


def _make_paste_icon() -> QIcon:
    pixmap = _create_hq_pixmap(ICON_SIZE)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    body = QPainterPath()
    body.moveTo(6, 1)
    body.lineTo(14, 1)
    body.lineTo(18, 5)
    body.lineTo(18, 18)
    body.lineTo(6, 18)
    body.lineTo(2, 14)
    body.lineTo(2, 5)
    body.lineTo(6, 1)
    p.drawPath(body)
    p.drawLine(14, 1, 14, 5)
    p.drawLine(14, 5, 18, 5)
    p.drawLine(5, 9, 15, 9)
    p.drawLine(5, 12, 15, 12)
    p.drawLine(5, 15, 12, 15)
    p.end()
    return QIcon(pixmap)


def _make_clear_icon() -> QIcon:
    pixmap = _create_hq_pixmap(ICON_SIZE)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    body = QPainterPath()
    body.moveTo(5, 7)
    body.lineTo(15, 7)
    body.lineTo(16, 18)
    body.lineTo(4, 18)
    body.closeSubpath()
    p.drawPath(body)
    p.drawLine(3, 7, 17, 7)
    p.drawLine(8, 3, 12, 3)
    p.drawLine(8, 3, 8, 7)
    p.drawLine(12, 3, 12, 7)
    p.drawLine(8, 10, 12, 10)
    p.drawLine(7, 13, 13, 13)
    p.drawLine(8, 16, 12, 16)
    p.end()
    return QIcon(pixmap)


def _make_settings_icon() -> QIcon:
    pixmap = _create_hq_pixmap(ICON_SIZE)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    # Gear shape
    p.drawEllipse(4, 4, 12, 12)
    for i in range(8):
        p.save()
        p.translate(10, 10)
        p.rotate(i * 45)
        p.drawLine(0, -6, 0, -8)
        p.restore()
    p.end()
    return QIcon(pixmap)


_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


def _make_folder_icon() -> QIcon:
    pixmap = _create_hq_pixmap(ICON_SIZE)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    # Folder shape
    path = QPainterPath()
    path.moveTo(2, 5)
    path.lineTo(2, 17)
    path.lineTo(18, 17)
    path.lineTo(18, 7)
    path.lineTo(10, 7)
    path.lineTo(8, 5)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._downloader = Downloader(self)
        self._config = Config()
        self._browser_window: BrowserWindow | None = None
        self._setup_ui()
        self._connect_signals()
        self._restore_history()

    def _setup_ui(self):
        self.setWindowTitle("Physalis")
        self.setMinimumSize(720, 520)
        self.setWindowOpacity(0.94)
        self.setStyleSheet(MAIN_STYLE_SHEET)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(16)

        self._list_container = QWidget()
        list_layout = QVBoxLayout(self._list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)

        self._center_logo = QLabel()
        if getattr(sys, 'frozen', False):
            # _MEIPASS is Contents/Frameworks, Resources is sibling dir
            logo_path = Path(sys._MEIPASS).parent / "Resources" / "icon.iconset" / "icon_512x512@2x.png"
        else:
            logo_path = Path(__file__).parent.parent / "icon.iconset" / "icon_512x512@2x.png"
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path)).scaledToHeight(300, Qt.TransformationMode.SmoothTransformation)
            self._center_logo.setPixmap(pixmap)
        self._center_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        list_layout.addWidget(self._center_logo)

        self._download_list = DownloadListWidget()
        self._download_list.setVisible(False)
        list_layout.addWidget(self._download_list)

        layout.addWidget(self._list_container, 1)

        # ── Status Bar & Bottom Tools ──
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.setSizeGripEnabled(False)
        self._statusbar.setStyleSheet("QStatusBar::item { border: none; }")

        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(10, 0, 10, 0)
        status_layout.setSpacing(12)

        self._browser_btn = QPushButton()
        self._browser_btn.setFixedSize(28, 28)
        self._browser_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._browser_btn.setToolTip("打开浏览器")
        self._browser_btn.setIcon(_make_browser_icon())
        self._browser_btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self._browser_btn.setStyleSheet("QPushButton { background: transparent; border-radius: 6px; } QPushButton:hover { background: rgba(139,92,246,0.2); }")
        self._browser_btn.clicked.connect(self._open_browser)
        status_layout.addWidget(self._browser_btn)

        self._paste_btn = QPushButton()
        self._paste_btn.setFixedSize(28, 28)
        self._paste_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._paste_btn.setToolTip("从剪贴板添加")
        self._paste_btn.setIcon(_make_paste_icon())
        self._paste_btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self._paste_btn.setStyleSheet("QPushButton { background: transparent; border-radius: 6px; } QPushButton:hover { background: rgba(139,92,246,0.2); }")
        self._paste_btn.clicked.connect(self._on_paste_clicked)
        status_layout.addWidget(self._paste_btn)

        self._clear_done_btn = QPushButton()
        self._clear_done_btn.setFixedSize(28, 28)
        self._clear_done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_done_btn.setToolTip("删除所有已结束的任务")
        self._clear_done_btn.setVisible(False)
        self._clear_done_btn.setIcon(_make_clear_icon())
        self._clear_done_btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self._clear_done_btn.setStyleSheet("QPushButton { background: rgba(255,255,255,0.06); border-radius: 6px; } QPushButton:hover { background: rgba(239,68,68,0.15); }")
        self._clear_done_btn.clicked.connect(self._on_clear_completed)
        status_layout.addWidget(self._clear_done_btn)

        self._msg_label = QLabel()
        self._msg_label.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 11px; margin-left: 8px;")
        status_layout.addWidget(self._msg_label)

        status_layout.addStretch()

        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 11px; margin-right: 8px;")
        status_layout.addWidget(self._stats_label)

        # 5. Settings Button
        self._settings_btn = QPushButton()
        self._settings_btn.setFixedSize(28, 28)
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setToolTip("系统设置")
        self._settings_btn.setIcon(_make_settings_icon())
        self._settings_btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self._settings_btn.setStyleSheet("QPushButton { background: transparent; border-radius: 6px; } QPushButton:hover { background: rgba(255,255,255,0.1); }")
        self._settings_btn.clicked.connect(self._open_settings)
        status_layout.addWidget(self._settings_btn)

        self._statusbar.addWidget(status_widget, 1)

        self._setup_menu()
        self._setup_context_menu()

    def show_msg(self, text: str, timeout: int = 5000):
        """Display a message in the custom status label."""
        self._msg_label.setText(text)
        if timeout > 0:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(timeout, lambda: self._msg_label.setText("") if self._msg_label.text() == text else None)

    def _setup_menu(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("文件")
        settings_act = QAction("设置", self)
        settings_act.triggered.connect(self._open_settings)
        file_menu.addAction(settings_act)
        file_menu.addSeparator()
        quit_act = QAction("退出", self)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        browser_menu = mb.addMenu("浏览器")
        open_act = QAction("打开浏览器", self)
        open_act.triggered.connect(self._open_browser)
        browser_menu.addAction(open_act)
        cookie_act = QAction("管理 Cookie", self)
        cookie_act.triggered.connect(self._open_cookie_manager)
        browser_menu.addAction(cookie_act)
        clear_cookie_act = QAction("清除所有 Cookie", self)
        clear_cookie_act.triggered.connect(self._clear_browser_cookies)
        browser_menu.addAction(clear_cookie_act)

    def _setup_context_menu(self):
        # Bind context menu to the container so it works even when list is hidden (empty)
        self._list_container.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list_container.customContextMenuRequested.connect(self._on_context_menu)

    def _on_context_menu(self, pos):
        item = self._download_list.item_at(pos)
        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint)
        
        if item:
            # 1. Right click on a task item
            task = item._current_task
            
            open_act = QAction(_make_folder_icon(), "打开文件位置", self)
            # Allow opening if we have any path, or at least the download directory
            can_open = bool(task.output_path) or os.path.exists(self._config.download_dir)
            open_act.setEnabled(can_open)
            # Fallback path if output_path is not yet set
            target_path = task.output_path or str(self._config.download_dir)
            open_act.triggered.connect(lambda: self._open_file_location(target_path))
            menu.addAction(open_act)
            
            menu.addSeparator()
            
            remove_act = QAction(_make_clear_icon(), "删除任务", self)
            remove_act.triggered.connect(lambda: self._on_remove_task(task.id))
            menu.addAction(remove_act)
        else:
            # 2. Right click on empty area (or logo area)
            paste_act = QAction(_make_paste_icon(), "从剪贴板添加链接", self)
            paste_act.triggered.connect(self._on_paste_clicked)
            menu.addAction(paste_act)
            
        menu.exec(self._list_container.mapToGlobal(pos))

    def _open_file_location(self, path: str):
        if not path:
            self.show_msg("路径为空")
            return
            
        # Clean path: remove ANSI escape codes (often found in yt-dlp output)
        path = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', path).strip()
        p = Path(path)
        
        # If the specific file doesn't exist, try the parent directory
        target = p if p.exists() else p.parent
        
        if not target.exists():
            self.show_msg("文件或文件夹不存在")
            return

        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        
        # On macOS/Windows, QDesktopServices.openUrl with a local file URL 
        # is the most reliable way to "reveal" or open.
        url = QUrl.fromLocalFile(str(target.absolute()))
        QDesktopServices.openUrl(url)
        self.show_msg(f"已打开: {target.name}")

    def _connect_signals(self):
        self._downloader.task_progress.connect(self._on_task_progress)
        self._downloader.task_completed.connect(self._on_task_completed)
        self._downloader.task_failed.connect(self._on_task_failed)
        self._downloader.task_cancelled.connect(self._on_task_cancelled)
        self._downloader.task_paused.connect(self._on_task_progress) # Use progress handler to update UI
        self._downloader.task_resumed.connect(self._on_task_progress)
        
        self._downloader.probe_finished.connect(self._on_probe_finished)
        self._downloader.probe_failed.connect(self._on_probe_failed)
        
        self._download_list.cancel_requested.connect(self._on_remove_task)
        self._download_list.retry_requested.connect(self._on_retry_task)
        self._download_list.remove_requested.connect(self._on_remove_task)


    def _on_task_progress(self, task):
        self._download_list.update_task(task)
        self._update_stats()

    def _on_task_completed(self, task):
        self._download_list.update_task(task)
        self._update_stats()
        self._update_clear_done_btn()
        self.show_msg(f"下载完成: {task.title or task.id}")

    def _on_task_failed(self, task):
        self._download_list.update_task(task)
        self._update_stats()
        self._update_clear_done_btn()
        self.show_msg(f"下载失败: {task.title or task.id}")

    def _on_task_cancelled(self, task):
        self._download_list.update_task(task)
        self._update_stats()
        self._update_clear_done_btn()

    def _on_probe_finished(self, videos):
        self._paste_btn.setEnabled(True)
        if len(videos) == 1:
            self._start_download(videos[0].url, videos[0].title, videos[0].thumbnail)
        else:
            dialog = VideoSelectDialog(videos, self)
            if dialog.exec() == VideoSelectDialog.DialogCode.Accepted:
                for v in dialog.selected_videos: self._start_download(v.url, v.title, v.thumbnail)

    def _on_probe_failed(self, error):
        self._paste_btn.setEnabled(True)
        self.show_msg(f"解析失败: {error[:80]}")

    def _start_download(self, url, title, thumb):
        from core.task import DownloadTask
        task = DownloadTask(url=url, title=title, thumbnail=thumb)
        self._download_list.add_task(task)
        self._downloader.add_task(task)
        self._center_logo.setVisible(False)
        self._download_list.setVisible(True)
        self._update_stats()
        self._extract_task_thumbnail(task)

    def _on_sniffed_download(self, task):
        # 1. Check for name collisions in both list and disk
        existing_titles = [t.title for t in self._downloader.tasks]
        base_title = task.title
        counter = 1
        
        # Check list and disk
        while True:
            # Check list
            in_list = task.title in existing_titles
            # Check disk (potential final path)
            # Note: Extension is unknown yet, so we check if any file starts with this name in download dir
            download_dir = self._config.download_dir
            in_disk = any(f.stem == task.title for f in download_dir.glob("*"))
            
            if not in_list and not in_disk:
                break
                
            task.title = f"{base_title}_{counter}"
            counter += 1
            
        self._download_list.add_task(task)
        self._downloader.add_task(task)
        self._center_logo.setVisible(False)
        self._download_list.setVisible(True)
        self._update_stats()
        self.show_msg(f"已添加下载: {task.title}")
        self._extract_task_thumbnail(task)

    def _extract_task_thumbnail(self, task):
        from shutil import which
        import sys
        from core.config import _config_dir
        
        # 1. Check if local cache already exists
        thumb_dir = _config_dir() / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        
        cache_path = task.thumbnail_local or str(thumb_dir / f"{task.id}.jpg")
        if Path(cache_path).exists():
            pix = QPixmap(cache_path)
            if not pix.isNull():
                self._download_list.update_thumbnail(task.id, pix)
                task.thumbnail_local = cache_path
                return

        # 2. Extract via FFmpeg if no cache
        ffmpeg = which("ffmpeg")
        if not ffmpeg and sys.platform == "darwin":
            for p in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
                if os.path.exists(p):
                    ffmpeg = p
                    break
        
        if not ffmpeg: return
        p = QProcess(self)
        p.start(ffmpeg, ["-ss", "00:00:01", "-i", task.url, "-vframes", "1", "-q:v", "4", "-f", "image2", "pipe:1"])
        def done():
            data = p.readAllStandardOutput().data()
            if data:
                pix = QPixmap()
                if pix.loadFromData(data): 
                    self._download_list.update_thumbnail(task.id, pix)
                    # 3. Save to local cache for future use
                    pix.save(cache_path, "JPG")
                    task.thumbnail_local = cache_path
            p.deleteLater()
        p.finished.connect(done)

    def _restore_history(self):
        tasks = self._downloader.load_history()
        if not tasks: return
        for task in tasks:
            self._download_list.add_task(task)
            self._downloader._tasks[task.id] = task
            self._extract_task_thumbnail(task)
        self._center_logo.setVisible(False)
        self._download_list.setVisible(True)
        self._update_stats()
        self._update_clear_done_btn()
        self.show_msg(f"已恢复 {len(tasks)} 个历史任务")

    def _on_retry_task(self, tid):
        task = self._downloader.get_task(tid)
        if not task: return
        # Reset only transient error/status, keep size and progress for resume
        task.status = TaskStatus.PENDING
        task.error = ""
        task.speed = ""
        task.eta = ""
        self._download_list.update_task(task)
        self._downloader.add_task(task)
        self._update_stats()

    def _on_remove_task(self, tid):
        task = next((t for t in self._downloader.tasks if t.id == tid), None)
        title = task.title if task else "任务"
        if StyledMessageBox.question(self, "删除确认", f"确定要删除任务 '{title}' 吗？"):
            self._download_list.remove_task(tid)
            self._downloader.remove_task(tid)
            if not self._download_list._tasks:
                self._center_logo.setVisible(True)
                self._download_list.setVisible(False)
            self._update_stats()
            self._update_clear_done_btn()

    def _on_clear_completed(self):
        self._download_list.clear_completed()
        self._downloader.clear_finished()
        if not self._download_list._tasks:
            self._center_logo.setVisible(True)
            self._download_list.setVisible(False)
        self._update_stats()
        self._update_clear_done_btn()
        self.show_msg("已清除所有已结束的任务")

    def _update_clear_done_btn(self):
        any_done = any(t.is_finished for t in self._download_list._tasks.values())
        self._clear_done_btn.setVisible(any_done)

    def _update_stats(self):
        tasks = self._download_list._tasks.values()
        total = len(tasks)
        active = sum(1 for t in tasks if t.is_active)
        done = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        self._stats_label.setText(f"总计: {total} | 下载中: {active} | 已完成: {done}")

    def _on_paste_clicked(self):
        from PyQt6.QtWidgets import QApplication
        url = QApplication.clipboard().text().strip()
        if not url: self.show_msg("剪贴板为空")
        elif not _is_valid_url(url): self.show_msg(f"无效链接: {url[:40]}")
        else:
            self._paste_btn.setEnabled(False)
            self.show_msg("正在解析...")
            self._downloader.probe_url(url)

    def _open_browser(self):
        if self._browser_window and not self._is_bw_destroyed():
            if self._browser_window.isVisible():
                self._browser_window.raise_()
                self._browser_window.activateWindow()
                return
            self._browser_window.reset()
            self._browser_window.show()
            return
        self._browser_window = BrowserWindow(self)
        self._browser_window.download_requested.connect(self._on_sniffed_download)
        self._browser_window.show()

    def _is_bw_destroyed(self):
        try: self._browser_window.isVisible(); return False
        except RuntimeError: return True

    def _open_cookie_manager(self):
        if not self._browser_window or self._is_bw_destroyed(): self.show_msg("请先打开浏览器")
        else: CookieManagerDialog(self._browser_window._cookie_manager, self).exec()

    def _clear_browser_cookies(self):
        if not self._browser_window or self._is_bw_destroyed(): self.show_msg("浏览器未打开")
        else:
            if StyledMessageBox.question(self, "清除 Cookie", "确定要清除所有 Cookie 吗？"):
                self._browser_window._cookie_manager.clear_all()
                self.show_msg("Cookie 已清除")

    def _open_settings(self):
        from ui.settings_dialog import SettingsDialog
        SettingsDialog(self).exec()

    def closeEvent(self, e):
        self._downloader.save_history()
        if self._browser_window and not self._is_bw_destroyed(): self._browser_window.shutdown()
        e.accept()
