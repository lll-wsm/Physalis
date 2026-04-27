import os
import tempfile
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QColor
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.cookie_manager import CookieManager
from core.sniffer import NetworkSniffer, SniffedVideo
from core.task import DownloadTask
from core.title_rules import TitleRuleManager
from ui.cookie_manager_dialog import CookieManagerDialog
from ui.sniff_panel import SniffPanel
from ui.title_rule_dialog import TitleRuleDialog
from app import BROWSER_STYLE_SHEET


def _domain_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host
    except Exception:
        return ""


def _write_netscape_cookies(cookies: list[QNetworkCookie], f):
    f.write("# Netscape HTTP Cookie File\n")
    for c in cookies:
        domain = c.domain() if c.domain() else ""
        if not domain:
            continue
        # TRUE  → domain starts with "." (subdomain-accessible cookie)
        # FALSE → host-only cookie (no leading dot)
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path_ = c.path() if c.path() else "/"
        secure = "TRUE" if c.isSecure() else "FALSE"
        expires = str(int(c.expirationDate().toSecsSinceEpoch())) if c.expirationDate().isValid() else "0"
        name = bytes(c.name()).decode("utf-8", errors="replace").replace("\t", " ").replace("\n", " ")
        value = bytes(c.value()).decode("utf-8", errors="replace").replace("\t", " ").replace("\n", " ")
        prefix = "#HttpOnly_" if c.isHttpOnly() else ""
        f.write(f"{prefix}{domain}\t{flag}\t{path_}\t{secure}\t{expires}\t{name}\t{value}\n")


class BrowserWindow(QMainWindow):
    download_requested = pyqtSignal(DownloadTask)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sniffer: NetworkSniffer | None = None
        self._cookie_manager = CookieManager(self)
        self._cookie_manager.load()
        self._current_page_title = ""
        self._title_rule_manager = TitleRuleManager()
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("Physalis 浏览器")
        self.setMinimumSize(960, 680)
        self.setWindowOpacity(0.94)
        self.setStyleSheet(BROWSER_STYLE_SHEET)

        central = QWidget()
        central.setStyleSheet("background: #2d2640;")
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Left side: nav + web view
        left = QWidget()
        left.setStyleSheet("background: #2d2640;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # --- Navigation bar ---
        nav_container = QWidget()
        nav_container.setStyleSheet("background: #241f38;")
        nav = QHBoxLayout(nav_container)
        nav.setContentsMargins(10, 8, 10, 8)
        nav.setSpacing(6)

        self._back_btn = QPushButton("◀")
        self._back_btn.setFixedSize(32, 32)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(self._go_back)
        nav.addWidget(self._back_btn)

        self._fwd_btn = QPushButton("▶")
        self._fwd_btn.setFixedSize(32, 32)
        self._fwd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fwd_btn.clicked.connect(self._go_forward)
        nav.addWidget(self._fwd_btn)

        self._reload_btn = QPushButton("↻")
        self._reload_btn.setFixedSize(32, 32)
        self._reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reload_btn.clicked.connect(self._reload)
        nav.addWidget(self._reload_btn)

        # Login status indicator
        self._login_indicator = QLabel("○ 未登录")
        self._login_indicator.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 11px; background: transparent; padding: 0 4px;")
        nav.addWidget(self._login_indicator)

        # Cookie manager button
        self._cookie_btn = QPushButton("Cookie")
        self._cookie_btn.setFixedSize(56, 26)
        self._cookie_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cookie_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06);
                color: #c4b5fd;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                padding: 0px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.12); }
        """)
        self._cookie_btn.clicked.connect(self._show_cookie_manager)
        nav.addWidget(self._cookie_btn)

        # Title rule manager button
        self._title_rule_btn = QPushButton("标题规则")
        self._title_rule_btn.setFixedSize(64, 26)
        self._title_rule_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title_rule_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06);
                color: #c4b5fd;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                padding: 0px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.12); }
        """)
        self._title_rule_btn.clicked.connect(self._show_title_rules)
        nav.addWidget(self._title_rule_btn)

        # Sniff panel toggle button
        self._sniff_toggle_btn = QPushButton("▮")
        self._sniff_toggle_btn.setFixedSize(28, 26)
        self._sniff_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sniff_toggle_btn.setToolTip("隐藏嗅探面板")
        self._sniff_toggle_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06);
                color: #c4b5fd;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background: rgba(255,255,255,0.12); }
        """)
        self._sniff_toggle_btn.clicked.connect(self._toggle_sniff_panel)
        nav.addWidget(self._sniff_toggle_btn)

        # Apply navBtn class to all nav buttons for styling
        for btn in (self._back_btn, self._fwd_btn, self._reload_btn):
            btn.setProperty("class", "navBtn")

        self._url_bar = QLineEdit()
        self._url_bar.setObjectName("urlBar")
        self._url_bar.setPlaceholderText("输入网址...")
        self._url_bar.returnPressed.connect(self._navigate)
        nav.addWidget(self._url_bar, 1)

        left_layout.addWidget(nav_container)

        # --- Web view ---
        # Off-the-record profile: cookies live in memory only.
        # Avoids "same data path" warnings if the window is reopened.
        self._profile = QWebEngineProfile(self)
        self._profile.setHttpUserAgent(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        self._sniffer = NetworkSniffer(self)
        self._profile.setUrlRequestInterceptor(self._sniffer)
        self._cookie_store = self._profile.cookieStore()
        self._cookie_store.cookieAdded.connect(self._on_cookie_added)
        self._cookie_store.cookieRemoved.connect(self._on_cookie_removed)

        self._page = QWebEnginePage(self._profile, self)
        self._page.setBackgroundColor(QColor("#2d2640"))
        self._view = QWebEngineView(self)
        self._view.setPage(self._page)
        self._view.urlChanged.connect(self._on_url_changed)
        self._view.loadStarted.connect(self._on_load_started)
        self._view.loadProgress.connect(self._on_load_progress)
        self._view.loadFinished.connect(self._on_load_finished)
        self._view.loadFinished.connect(self._on_page_loaded)
        left_layout.addWidget(self._view, 1)

        # --- Sniff panel (right side) ---
        self._sniff_panel = SniffPanel()
        self._sniffer.video_found.connect(self._on_video_sniffed)
        self._sniff_panel.download_requested.connect(self._on_download_video)
        self._sniff_panel.download_all_requested.connect(self._on_download_all)
        self._sniff_panel.cleared.connect(self._sniffer.clear)

        layout.addWidget(left, 1)
        layout.addWidget(self._sniff_panel)

        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)

        self._view.load(QUrl("about:blank"))

    def _on_url_changed(self, url: QUrl):
        self._url_bar.setText(url.toString())
        # Clear sniffer's dedup so new page requests aren't filtered out (SPA fix)
        self._sniffer.clear()

    def _on_load_started(self):
        self._statusbar.showMessage("加载中…")

    def _on_load_progress(self, p: int):
        self._statusbar.showMessage(f"加载中… {p}%")

    def _on_load_finished(self, ok: bool):
        if ok:
            self._statusbar.showMessage("加载完成", 3000)
        else:
            self._statusbar.showMessage(
                f"加载失败：{self._view.url().toString()}（请检查网址或网络）",
                8000,
            )

    def _on_page_loaded(self, ok: bool):
        """Extract page title and thumbnail after load finishes."""
        if not ok:
            return
        self._extract_page_title(self._on_page_title)
        self._extract_page_thumbnail(self._on_page_thumbnail)

    def _on_page_title(self, title: str):
        if title:
            self._current_page_title = title

    def _on_page_thumbnail(self, thumb_url: str):
        if thumb_url:
            self._sniff_panel.set_page_thumbnail(thumb_url)

    def _on_video_sniffed(self, video: SniffedVideo):
        if self._current_page_title:
            video.page_title = self._current_page_title
        self._sniff_panel.add_video(video)

    def _navigate(self):
        text = self._url_bar.text().strip()
        if not text:
            return
        if not text.startswith(("http://", "https://")):
            if "." not in text:
                self._statusbar.showMessage(
                    f"无效网址（缺少域名）：{text}", 5000
                )
                return
            text = "https://" + text
        self._view.load(QUrl(text))

    def _go_back(self):
        self._view.back()

    def _go_forward(self):
        self._view.forward()

    def _reload(self):
        self._view.reload()

    def _on_cookie_added(self, cookie: QNetworkCookie):
        self._cookie_manager.add_cookie(cookie)
        self._update_login_indicator()

    def _on_cookie_removed(self, cookie: QNetworkCookie):
        self._cookie_manager.remove_cookie(cookie)
        self._update_login_indicator()

    def _build_task_for_video(self, video: SniffedVideo) -> DownloadTask:
        domain = _domain_from_url(video.page_url or video.url)
        domain_cookies = self._cookie_manager.for_domain(domain)

        cookies_file = ""
        if domain_cookies:
            fd, cookies_file = tempfile.mkstemp(
                suffix=".txt", prefix=f"physalis_cookies_{domain}_"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                _write_netscape_cookies(domain_cookies, f)

        return DownloadTask(
            url=video.url,
            referer=video.referer or video.page_url,
            cookies_file=cookies_file,
            format_hint=video.format_hint,
        )

    def _extract_page_thumbnail(self, callback):
        """Extract og:image URL from the page DOM."""
        js = """
        (function() {
            try {
                var m = document.querySelector('meta[property="og:image"], meta[name="twitter:image"]');
                if (m && (m.content || "").trim()) return m.content.trim();
                var imgs = document.querySelectorAll('video[poster]');
                if (imgs.length > 0 && (imgs[0].poster || "").trim()) return imgs[0].poster.trim();
                return "";
            } catch(e) { return ""; }
        })();
        """
        self._page.runJavaScript(js, callback)

    def _extract_page_title(self, callback):
        """从当前页面 DOM 提取视频标题。根据域名规则动态生成 JS。"""
        url = self._view.url().toString()
        js = self._title_rule_manager.generate_js(url)
        self._page.runJavaScript(js, callback)

    def _on_download_video(self, video: SniffedVideo):
        task = self._build_task_for_video(video)
        if not task.title and video.page_title:
            task.title = self._ensure_unique_title(video.page_title, video)
        self.download_requested.emit(task)

    def _on_download_all(self):
        title = ""
        if self._current_page_title:
            title = self._current_page_title
        for video in self._sniff_panel.videos:
            task = self._build_task_for_video(video)
            if not task.title and (video.page_title or title):
                task.title = self._ensure_unique_title(video.page_title or title, video)
            self.download_requested.emit(task)

    @staticmethod
    def _ensure_unique_title(base: str, video: SniffedVideo) -> str:
        """若标题过于通用（如"抖音"），追加 page_url 路径中的视频 ID 以区分。"""
        base = base.strip()
        page_path = urlparse(video.page_url).path.strip("/")
        # If title is short/generic and page URL has a specific path, append it
        if len(base) <= 4 and page_path:
            # Take the last meaningful segment
            parts = [p for p in page_path.split("/") if p and not p.startswith("aweme")]
            suffix = parts[-1] if parts else ""
            if suffix and len(suffix) >= 8:
                return f"{base}_{suffix}"
        return base

    def reset(self):
        """Clear cookies, sniffer state and sniff panel, then load about:blank."""
        self._cookie_manager.clear_all()
        self._update_login_indicator()
        if self._sniffer is not None:
            self._sniffer.clear()
        self._sniff_panel.clear()
        self._view.load(QUrl("about:blank"))

    def showEvent(self, event):
        super().showEvent(event)
        self._cookie_manager.load()
        self._restore_cookies_to_store()
        self._update_login_indicator()

    def closeEvent(self, event):
        event.ignore()
        self._cookie_manager.save()
        self._view.load(QUrl("about:blank"))
        self.hide()

    def shutdown(self):
        """Clean up web engine resources before app quit (avoids IO thread crash)."""
        self._cookie_manager.save()
        if self._sniffer is not None:
            self._sniffer.clear()
            self._sniffer.deleteLater()
            self._sniffer = None
        self._view.load(QUrl("about:blank"))

    def _update_login_indicator(self):
        if self._cookie_manager.has_any():
            self._login_indicator.setText("● 已登录")
            self._login_indicator.setStyleSheet("color: #4ade80; font-size: 11px; background: transparent; padding: 0 4px;")
        else:
            self._login_indicator.setText("○ 未登录")
            self._login_indicator.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 11px; background: transparent; padding: 0 4px;")

    def _show_cookie_manager(self):
        dialog = CookieManagerDialog(self._cookie_manager, self)
        dialog.exec()
        self._update_login_indicator()

    def _show_title_rules(self):
        """Open the title rule configuration dialog for the current page."""
        url = self._view.url().toString()
        dialog = TitleRuleDialog(self._page, url, self._title_rule_manager, self)
        dialog.exec()

    def _toggle_sniff_panel(self):
        """Show or hide the sniff panel and update toggle button appearance."""
        hidden = self._sniff_panel.isHidden()
        self._sniff_panel.setVisible(hidden)
        self._sniff_toggle_btn.setText("▮" if hidden else "☐")
        self._sniff_toggle_btn.setToolTip(
            "隐藏嗅探面板" if hidden else "显示嗅探面板"
        )

    def _restore_cookies_to_store(self):
        """Push persisted cookies into QtWebEngine's cookie store so login persists."""
        if not self._cookie_manager.has_any():
            return
        for c in self._cookie_manager.all_cookies():
            domain = c.domain()
            if not domain:
                continue
            # Strip leading dot for URL construction (dot = subdomain-accessible flag)
            host = domain.lstrip(".")
            url = QUrl(f"https://{host}")
            self._cookie_store.setCookie(c, url)

    def load_url(self, url: str):
        if not url.startswith(("http://", "https://", "about:", "file:")):
            url = "https://" + url
        self._view.load(QUrl(url))
