import re

from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
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
from ui.browser_window import BrowserWindow
from app import MAIN_STYLE_SHEET

ICON_SIZE = 20


def _make_browser_icon() -> QIcon:
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    # Globe: circle + meridian lines
    center = 10
    p.drawEllipse(2, 2, 16, 16)
    p.drawEllipse(2, 4, 16, 12)
    p.drawLine(center, 2, center, 18)
    p.drawLine(2, 10, 18, 10)
    p.end()
    return QIcon(pixmap)


def _make_paste_icon() -> QIcon:
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    # Document body
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
    # Fold indicator
    p.drawLine(14, 1, 14, 5)
    p.drawLine(14, 5, 18, 5)
    # Lines on document
    p.drawLine(5, 9, 15, 9)
    p.drawLine(5, 12, 15, 12)
    p.drawLine(5, 15, 12, 15)
    p.end()
    return QIcon(pixmap)


def _make_clear_icon() -> QIcon:
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(1.5)
    p.setPen(pen)
    # Trash can body
    body = QPainterPath()
    body.moveTo(5, 7)
    body.lineTo(15, 7)
    body.lineTo(16, 18)
    body.lineTo(4, 18)
    body.closeSubpath()
    p.drawPath(body)
    # Lid
    p.drawLine(3, 7, 17, 7)
    # Handle
    p.drawLine(8, 3, 12, 3)
    p.drawLine(8, 3, 8, 7)
    p.drawLine(12, 3, 12, 7)
    # Lines inside
    p.drawLine(8, 10, 12, 10)
    p.drawLine(7, 13, 13, 13)
    p.drawLine(8, 16, 12, 16)
    p.end()
    return QIcon(pixmap)


_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


def _is_valid_url(text: str) -> bool:
    return bool(_URL_RE.match(text.strip()))


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

        # 下载列表 + 中心 Logo（无任务时显示）
        self._list_container = QWidget()
        list_layout = QVBoxLayout(self._list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)

        self._center_logo = QLabel()
        logo_path = Path(__file__).parent.parent / "icon.iconset" / "icon_512x512@2x.png"
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path)).scaledToHeight(300, Qt.TransformationMode.SmoothTransformation)
            self._center_logo.setPixmap(pixmap)
            self._center_logo.setStyleSheet("padding: 40px;")
        else:
            self._center_logo.setText("Physalis")
            self._center_logo.setStyleSheet("font-size: 22px; font-weight: 700; color: #c4b5fd; padding: 40px;")
        self._center_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        list_layout.addWidget(self._center_logo)

        self._download_list = DownloadListWidget()
        self._download_list.setVisible(False)
        list_layout.addWidget(self._download_list)

        layout.addWidget(self._list_container, 1)

        # 状态栏（按钮靠左，统计居中）
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)

        status_widget = QWidget()
        status_widget.setStyleSheet("background: transparent;")
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(4, 0, 4, 0)
        status_layout.setSpacing(6)

        self._browser_btn = QPushButton()
        self._browser_btn.setFixedSize(28, 28)
        self._browser_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._browser_btn.setToolTip("打开浏览器")
        self._browser_btn.setIcon(_make_browser_icon())
        self._browser_btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self._browser_btn.setProperty("class", "iconBtn")
        self._browser_btn.setStyleSheet(
            "QPushButton { background: transparent; border-radius: 6px; }"
            "QPushButton:hover { background: rgba(139,92,246,0.2); }"
        )
        status_layout.addWidget(self._browser_btn)

        self._paste_btn = QPushButton()
        self._paste_btn.setFixedSize(28, 28)
        self._paste_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._paste_btn.setToolTip("从剪贴板添加")
        self._paste_btn.setIcon(_make_paste_icon())
        self._paste_btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self._paste_btn.setProperty("class", "iconBtn")
        self._paste_btn.setStyleSheet(
            "QPushButton { background: transparent; border-radius: 6px; }"
            "QPushButton:hover { background: rgba(139,92,246,0.2); }"
        )
        status_layout.addWidget(self._paste_btn)

        self._clear_done_btn = QPushButton()
        self._clear_done_btn.setFixedSize(28, 28)
        self._clear_done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_done_btn.setToolTip("删除所有已结束的任务")
        self._clear_done_btn.setVisible(False)
        self._clear_done_btn.setIcon(_make_clear_icon())
        self._clear_done_btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self._clear_done_btn.setProperty("class", "iconBtn")
        self._clear_done_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.06); border-radius: 6px; }"
            "QPushButton:hover { background: rgba(239,68,68,0.15); }"
        )
        self._clear_done_btn.clicked.connect(self._on_clear_completed)
        status_layout.addWidget(self._clear_done_btn)

        status_layout.addStretch()
        self._stats_label = QLabel("就绪")
        self._stats_label.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 12px; padding: 0 8px;")
        status_layout.addWidget(self._stats_label)
        status_layout.addStretch()

        self._statusbar.addWidget(status_widget, 1)

        self._setup_menu()
        self._setup_context_menu()

    def _setup_menu(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("文件")
        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        tools_menu = menu_bar.addMenu("工具")
        self._cookie_manager_action = QAction("Cookie 管理", self)
        self._cookie_manager_action.triggered.connect(self._open_cookie_manager)
        tools_menu.addAction(self._cookie_manager_action)
        self._clear_cookies_action = QAction("清除浏览器 Cookie", self)
        self._clear_cookies_action.triggered.connect(self._clear_browser_cookies)
        tools_menu.addAction(self._clear_cookies_action)

        help_menu = menu_bar.addMenu("帮助")
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_context_menu(self):
        self._list_container.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list_container.customContextMenuRequested.connect(self._show_context_menu)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        paste_action = QAction("粘贴并解析", self)
        paste_action.triggered.connect(self._on_paste_clicked)
        menu.addAction(paste_action)
        menu.exec(self._list_container.mapToGlobal(pos))

    def _connect_signals(self):
        self._paste_btn.clicked.connect(self._on_paste_clicked)

        self._downloader.task_progress.connect(self._on_task_progress)
        self._downloader.task_completed.connect(self._on_task_completed)
        self._downloader.task_failed.connect(self._on_task_failed)
        self._downloader.task_cancelled.connect(self._on_task_cancelled)

        self._downloader.probe_finished.connect(self._on_probe_finished)
        self._downloader.probe_failed.connect(self._on_probe_failed)

        self._download_list.cancel_requested.connect(self._downloader.cancel_task)
        self._download_list.retry_requested.connect(self._on_retry_task)
        self._download_list.remove_requested.connect(self._on_remove_task)

        self._browser_btn.clicked.connect(self._open_browser)

    def _restore_history(self):
        """Restore finished download tasks from previous session."""
        tasks = self._downloader.load_history()
        if not tasks:
            return
        for task in tasks:
            self._download_list.add_task(task)
            self._downloader._tasks[task.id] = task
            # Try to restore thumbnails for old tasks
            self._extract_task_thumbnail(task)

        self._center_logo.setVisible(False)
        self._download_list.setVisible(True)
        self._update_stats()
        self._update_clear_done_btn()
        self._statusbar.showMessage(f"已恢复 {len(tasks)} 个历史任务", 3000)


    def _on_paste_clicked(self):
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        url = clipboard.text().strip()
        if not url:
            self._statusbar.showMessage("剪贴板为空")
            return
        if not _is_valid_url(url):
            self._statusbar.showMessage(f"不支持的链接: {url[:60]}")
            return
        self._start_probe(url)

    def _start_probe(self, url: str):
        self._paste_btn.setEnabled(False)
        self._statusbar.showMessage("正在解析...")
        self._downloader.probe_url(url)

    def _on_probe_finished(self, videos):
        self._paste_btn.setEnabled(True)

        if len(videos) == 1:
            self._statusbar.showMessage(f"发现 1 个视频: {videos[0].title or videos[0].id}")
            self._start_download(videos[0].url, videos[0].title, videos[0].thumbnail)
        else:
            self._statusbar.showMessage(f"发现 {len(videos)} 个视频，请选择要下载的")
            dialog = VideoSelectDialog(videos, self)
            if dialog.exec() == VideoSelectDialog.DialogCode.Accepted:
                selected = dialog.selected_videos
                for v in selected:
                    self._start_download(v.url, v.title, v.thumbnail)
                self._statusbar.showMessage(f"已添加 {len(selected)} 个下载任务")
            else:
                self._statusbar.showMessage("已取消")

    def _on_probe_failed(self, error: str):
        self._paste_btn.setEnabled(True)
        self._statusbar.showMessage(f"解析失败: {error[:80]}")

    def _start_download(self, url: str, title: str = "", thumbnail: str = ""):
        task = DownloadTask(url=url, title=title, thumbnail=thumbnail)
        self._download_list.add_task(task)
        self._downloader.add_task(task)

        # 有任务后隐藏中心 Logo，显示列表
        self._center_logo.setVisible(False)
        self._download_list.setVisible(True)
        self._update_stats()

    def _on_task_progress(self, task: DownloadTask):
        self._download_list.update_task(task)

    def _on_task_completed(self, task: DownloadTask):
        self._download_list.update_task(task)
        self._update_stats()
        self._update_clear_done_btn()
        self._statusbar.showMessage(f"下载完成: {task.title or '视频'}", 5000)

    def _on_task_failed(self, task: DownloadTask):
        self._download_list.update_task(task)
        self._update_stats()
        self._update_clear_done_btn()

    def _on_task_cancelled(self, task: DownloadTask):
        self._download_list.update_task(task)
        self._update_stats()
        self._update_clear_done_btn()

    def _on_retry_task(self, task_id: str):
        task = self._downloader.get_task(task_id)
        if task is None:
            return
        # Reset to pending state
        task.status = TaskStatus.PENDING
        task.progress = 0.0
        task.error = ""
        task.speed = ""
        task.eta = ""
        task.size_total = ""
        task.size_downloaded = ""
        # Re-add to list and downloader
        self._download_list.update_task(task)
        self._downloader.add_task(task)
        self._update_stats()
        self._statusbar.showMessage(f"已重新添加下载: {task.title or task.url[:40]}")

    def _on_remove_task(self, task_id: str):
        self._download_list.remove_task(task_id)
        self._downloader.remove_task(task_id)
        # If list is empty, restore center logo
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
        self._statusbar.showMessage("已清除所有已结束的任务", 3000)

    def _update_clear_done_btn(self):
        """Show/hide the clear-completed button based on whether any tasks are done."""
        any_done = any(
            t.is_finished
            for t in self._download_list._tasks.values()
        )
        self._clear_done_btn.setVisible(any_done)

    def _update_stats(self):
        """Update the permanent status bar task statistics."""
        tasks = self._download_list._tasks.values()
        total = len(tasks)
        if total == 0:
            self._stats_label.setText("就绪")
            return
        active = sum(1 for t in tasks if t.is_active)
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
        parts = [f"共 {total} 个任务"]
        if active:
            parts.append(f"下载中 {active}")
        if completed:
            parts.append(f"已完成 {completed}")
        if failed:
            parts.append(f"失败 {failed}")
        self._stats_label.setText(" | ".join(parts))

    def _open_browser(self):
        # Guard against the wrapped C/C++ object having been deleted by Qt.
        if self._browser_window is not None:
            try:
                visible = self._browser_window.isVisible()
            except RuntimeError:
                self._browser_window = None
                visible = False

            if visible:
                self._browser_window.raise_()
                self._browser_window.activateWindow()
                return

            # Reuse existing hidden window rather than creating a new profile,
            # which can destabilize QtWebEngine on macOS.
            self._browser_window.reset()
            self._browser_window.show()
            self._browser_window.raise_()
            self._browser_window.activateWindow()
            return

        self._browser_window = BrowserWindow(self)
        self._browser_window.download_requested.connect(self._on_sniffed_download)
        self._browser_window.show()

    def _on_sniffed_download(self, task: DownloadTask):
        # Prevent title duplication by adding a timestamp if needed
        existing_titles = [t.title for t in self._downloader.tasks]
        if task.title in existing_titles:
            from datetime import datetime
            timestamp = datetime.now().strftime("_%H%M%S")
            task.title = f"{task.title}{timestamp}"

        self._download_list.add_task(task)
        self._downloader.add_task(task)
        self._center_logo.setVisible(False)
        self._download_list.setVisible(True)
        self._update_stats()
        self._statusbar.showMessage(f"已添加下载: {task.url[:60]}")
        
        # Priority: Extract frame for main UI background
        self._extract_task_thumbnail(task)

    def _extract_task_thumbnail(self, task: DownloadTask):
        """Use FFmpeg to extract a background frame for the main list item."""
        from PyQt6.QtCore import QProcess
        from PyQt6.QtGui import QPixmap
        import shutil
        
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            return

        process = QProcess(self)
        # Low quality (q:v 4) is enough for subtle background
        args = ["-ss", "00:00:01", "-i", task.url, "-vframes", "1", "-q:v", "4", "-f", "image2", "pipe:1"]
        process.start(ffmpeg_path, args)
        
        def on_finished():
            img_data = process.readAllStandardOutput().data()
            if img_data:
                pixmap = QPixmap()
                if pixmap.loadFromData(img_data):
                    self._download_list.update_thumbnail(task.id, pixmap)
            process.deleteLater()
            
        process.finished.connect(on_finished)

    def _open_cookie_manager(self):
        bw = self._browser_window
        if bw is None:
            self._statusbar.showMessage("请先打开浏览器")
            return
        try:
            if not bw.isVisible():
                self._statusbar.showMessage("请先打开浏览器")
                return
        except RuntimeError:
            self._browser_window = None
            self._statusbar.showMessage("浏览器已关闭，请重新打开")
            return

        dialog = CookieManagerDialog(bw._cookie_manager, self)
        dialog.exec()

    def _clear_browser_cookies(self):
        bw = self._browser_window
        if bw is None:
            self._statusbar.showMessage("浏览器未打开")
            return
        try:
            if not bw.isVisible():
                self._statusbar.showMessage("浏览器未打开")
                return
        except RuntimeError:
            self._browser_window = None
            self._statusbar.showMessage("浏览器已关闭")
            return

        reply = QMessageBox.question(
            self,
            "清除 Cookie",
            "确定要清除浏览器中的所有 Cookie 吗？\n此操作会使您退出已登录的网站。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            bw._cookie_manager.clear_all()
            bw._update_login_indicator()
            self._statusbar.showMessage("浏览器 Cookie 已清除")

    def closeEvent(self, event):
        """Save download history and shut down browser before quitting."""
        self._downloader.save_history()
        if self._browser_window is not None:
            try:
                self._browser_window.shutdown()
            except RuntimeError:
                pass
        event.accept()

    def _open_settings(self):
        from ui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        dialog.exec()

    def _show_about(self):
        QMessageBox.about(self, "关于 Physalis", "Physalis v0.1.0\n跨平台视频下载工具")
