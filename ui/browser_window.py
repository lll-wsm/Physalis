import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtNetwork import QNetworkCookie, QNetworkReply
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineScript


def _x_popup_landing_finishes_oauth(url: QUrl) -> bool:
    """Whether an X/Twitter popup URL looks like OAuth/post-auth landing (safe to close).

    Closing on every x.com navigation breaks flows where the popup still runs inside
    /i/flow/ (login wizard, SSO). Reloading the opener then resets username/password UI.
    """
    host = url.host().lower()
    if host not in ("x.com", "twitter.com"):
        return False
    path = url.path().lower()
    if "/i/flow/" in path:
        return False
    if path.rstrip("/").endswith("/login"):
        return False
    return True


class _PopupWebPage(QWebEnginePage):
    """QWebEnginePage subclass that opens popup windows (OAuth, etc.)
    in a separate dialog so the opener page stays alive and can receive
    postMessage / callback tokens from the popup."""

    def __init__(self, profile, parent_browser, parent=None):
        super().__init__(profile, parent)
        self._parent_browser = parent_browser

    def createWindow(self, window_type):
        # print(f"[POPUP] createWindow called, type={window_type}")
        from PyQt6.QtWidgets import QDialog, QVBoxLayout
        dialog = QDialog(self._parent_browser)
        dialog.setWindowTitle("登录")
        dialog.setMinimumSize(480, 640)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        popup_page = _PopupWebPage(self.profile(), self._parent_browser, dialog)
        popup_view = QWebEngineView(dialog)
        popup_view.setPage(popup_page)

        # Auto-close only when popup likely finished OAuth (not during /i/flow/ wizard).
        def on_popup_url_changed(url):
            # print(f"[POPUP] popup URL: {url.toString()}")
            if _x_popup_landing_finishes_oauth(url):
                dialog.accept()
                self._parent_browser._view.reload()

        popup_view.urlChanged.connect(on_popup_url_changed)
        layout.addWidget(popup_view)
        dialog.show()
        return popup_page
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

from core.config import Config
from core.cookie_manager import CookieManager
from core.sniffer import NetworkSniffer, SniffedVideo
from core.task import DownloadTask
from core.title_rules import TitleRuleManager
from ui.cookie_manager_dialog import CookieManagerDialog
from ui.sniff_panel import (
    SniffPanel,
    _make_cookie_icon,
    _make_rule_icon,
    _make_panel_toggle_icon,
    _make_close_icon,
    get_video_display_name,
)
from ui.title_rule_dialog import TitleRuleDialog
from app import BROWSER_STYLE_SHEET


def _create_hq_pixmap(size: int) -> QPixmap:
    """Create a High-DPI aware transparent pixmap."""
    dpr = 2.0 
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def _make_nav_back_icon() -> QIcon:
    size = 24
    pixmap = _create_hq_pixmap(size)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(2.0)
    p.setPen(pen)
    p.drawLine(15, 6, 9, 12)
    p.drawLine(9, 12, 15, 18)
    p.end()
    return QIcon(pixmap)


def _make_nav_forward_icon() -> QIcon:
    size = 24
    pixmap = _create_hq_pixmap(size)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(2.0)
    p.setPen(pen)
    p.drawLine(9, 6, 15, 12)
    p.drawLine(15, 12, 9, 18)
    p.end()
    return QIcon(pixmap)


def _make_nav_reload_icon() -> QIcon:
    size = 24
    pixmap = _create_hq_pixmap(size)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#c4b5fd"))
    pen.setWidthF(1.8)
    p.setPen(pen)
    p.drawArc(6, 6, 12, 12, 40 * 16, 280 * 16)
    p.drawLine(15, 6, 18, 6)
    p.drawLine(18, 6, 18, 9)
    p.end()
    return QIcon(pixmap)


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
        nav_container.setStyleSheet("background: #241f38; border-bottom: 1px solid rgba(255,255,255,0.06);")
        nav = QHBoxLayout(nav_container)
        nav.setContentsMargins(12, 8, 12, 8)
        nav.setSpacing(8)

        # Back/Forward/Reload group
        self._back_btn = QPushButton()
        self._back_btn.setIcon(_make_nav_back_icon())
        self._back_btn.setFixedSize(30, 30)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(self._go_back)
        self._back_btn.setProperty("class", "navBtn")
        nav.addWidget(self._back_btn)

        self._fwd_btn = QPushButton()
        self._fwd_btn.setIcon(_make_nav_forward_icon())
        self._fwd_btn.setFixedSize(30, 30)
        self._fwd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fwd_btn.clicked.connect(self._go_forward)
        self._fwd_btn.setProperty("class", "navBtn")
        nav.addWidget(self._fwd_btn)

        self._reload_btn = QPushButton()
        self._reload_btn.setIcon(_make_nav_reload_icon())
        self._reload_btn.setFixedSize(30, 30)
        self._reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reload_btn.clicked.connect(self._reload)
        self._reload_btn.setProperty("class", "navBtn")
        nav.addWidget(self._reload_btn)

        # URL bar (centered, expanding)
        self._url_bar = QLineEdit()
        self._url_bar.setObjectName("urlBar")
        self._url_bar.setPlaceholderText("输入网址...")
        self._url_bar.returnPressed.connect(self._navigate)
        nav.addWidget(self._url_bar, 1)

        # Tools group
        self._cookie_btn = QPushButton()
        self._cookie_btn.setIcon(_make_cookie_icon())
        self._cookie_btn.setFixedSize(32, 28)
        self._cookie_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cookie_btn.setToolTip("Cookie 管理")
        self._cookie_btn.setProperty("class", "toolBtn")
        self._cookie_btn.clicked.connect(self._show_cookie_manager)
        nav.addWidget(self._cookie_btn)

        self._title_rule_btn = QPushButton()
        self._title_rule_btn.setIcon(_make_rule_icon())
        self._title_rule_btn.setFixedSize(32, 28)
        self._title_rule_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title_rule_btn.setToolTip("标题提取规则")
        self._title_rule_btn.setProperty("class", "toolBtn")
        self._title_rule_btn.clicked.connect(self._show_title_rules)
        nav.addWidget(self._title_rule_btn)

        self._sniff_toggle_btn = QPushButton()
        self._sniff_toggle_btn.setIcon(_make_panel_toggle_icon(True))
        self._sniff_toggle_btn.setFixedSize(32, 28)
        self._sniff_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sniff_toggle_btn.setToolTip("隐藏嗅探面板")
        self._sniff_toggle_btn.setProperty("class", "toolBtn")
        self._sniff_toggle_btn.clicked.connect(self._toggle_sniff_panel)
        nav.addWidget(self._sniff_toggle_btn)

        # Settings group
        self._settings_btn = QPushButton()
        from ui.main_window import _make_settings_icon
        self._settings_btn.setIcon(_make_settings_icon())
        self._settings_btn.setFixedSize(30, 28)
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setToolTip("系统设置")
        self._settings_btn.setProperty("class", "toolBtn")
        self._settings_btn.clicked.connect(self._open_settings)
        nav.addWidget(self._settings_btn)

        left_layout.addWidget(nav_container)

        # --- Web view ---
        self._profile = QWebEngineProfile(self)
        _web_root = Path(Config()._path).parent / "webengine"
        _web_root.mkdir(parents=True, exist_ok=True)
        self._profile.setPersistentStoragePath(str(_web_root / "persistent"))
        self._profile.setCachePath(str(_web_root / "cache"))

        # Minimal injection: real Chrome reports webdriver === false; undefined can trip checks.
        # FedCM: QtWebEngine throws sync TypeError on identity credential requests; reject so GSI falls back.
        # Do NOT wrap fetch/XHR (x.com login can call XHR.send multiple times; extra load listeners break state).
        compatibility_script = QWebEngineScript()
        compatibility_script.setSourceCode("""
            (function() {
                try {
                    Object.defineProperty(navigator, 'webdriver', { get: function() { return false; } });
                } catch (e) {}

                if (navigator.credentials && navigator.credentials.get) {
                    var _origCredGet = navigator.credentials.get.bind(navigator.credentials);
                    navigator.credentials.get = function(options) {
                        if (options && options.identity) {
                            return Promise.reject(
                                new DOMException('FedCM not supported', 'NotAllowedError')
                            );
                        }
                        return _origCredGet(options);
                    };
                }
            })();
        """)
        compatibility_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        compatibility_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        compatibility_script.setRunsOnSubFrames(True)
        self._profile.scripts().insert(compatibility_script)

        # Use a Chromebook (ChromeOS) User-Agent to trick sites (Bilibili/YouTube/X) 
        # into serving VP9 or AV1 streams instead of H.264, allowing video playback 
        # without proprietary codecs.
        self._profile.setHttpUserAgent("Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

        settings = self._profile.settings()
        settings.setAttribute(settings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(settings.WebAttribute.FullScreenSupportEnabled, True)
        settings.setAttribute(settings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(settings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(settings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(settings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(settings.WebAttribute.WebGLEnabled, True)
        # Added features
        settings.setAttribute(settings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(settings.WebAttribute.DnsPrefetchEnabled, True)
        settings.setAttribute(settings.WebAttribute.JavascriptCanOpenWindows, True)
        settings.setAttribute(settings.WebAttribute.PdfViewerEnabled, False) # Conserve resources

        self._sniffer = NetworkSniffer(self)
        self._profile.setUrlRequestInterceptor(self._sniffer)
        self._cookie_store = self._profile.cookieStore()
        self._cookie_store.cookieAdded.connect(self._on_cookie_added)
        self._cookie_store.cookieRemoved.connect(self._on_cookie_removed)

        self._page = _PopupWebPage(self._profile, self, self)
        # Enable console message logging for debugging
        self._page.javaScriptConsoleMessage = self._on_js_console
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

    def _on_js_console(self, level, message, line, source_id):
        """Log JS console messages to Python stdout for debugging."""
        # level_map = {0: "INFO", 1: "WARN", 2: "ERROR", 3: "DEBUG"}
        # tag = level_map.get(level, str(level))
        # src = source_id.split("/")[-1] if source_id else ""
        # print(f"[JS:{tag}] {message}  ({src}:{line})")
        pass

    def _on_url_changed(self, url: QUrl):
        url_str = url.toString()
        self._url_bar.setText(url_str)
        # print(f"[NAV] {url_str}")
        # Clear sniffer's dedup so new page requests aren't filtered out (SPA fix)
        if self._sniffer is not None:
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
        
        # Priority 1: Real-time Frame Extraction via FFmpeg (Accurate & from URL)
        # This solves "getting thumbnail from mp4 response data"
        self._extract_frame_via_ffmpeg(video.url)

    def _extract_frame_via_ffmpeg(self, video_url: str):
        """Use ffmpeg to grab a single frame from the remote URL without downloading the whole file."""
        from PyQt6.QtCore import QProcess
        import shutil
        import sys
        
        ffmpeg_path = shutil.which("ffmpeg")
        # macOS specialized search if shutil.which fails
        if not ffmpeg_path and sys.platform == "darwin":
            for p in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
                if os.path.exists(p):
                    ffmpeg_path = p
                    break
        
        if not ffmpeg_path:
            # Fallback to metadata probe if ffmpeg is missing
            self._probe_thumbnail_via_ytdlp(video_url)
            return

        process = QProcess(self)
        # -ss 00:00:01: Seek to 1 second
        # -i: Input URL
        # -vframes 1: Grab 1 frame
        # -f image2 pipe:1: Output as image data to stdout pipe
        args = [
            "-ss", "00:00:01",
            "-i", video_url,
            "-vframes", "1",
            "-q:v", "2",
            "-f", "image2",
            "pipe:1"
        ]
        process.start(ffmpeg_path, args)
        
        def on_finished():
            img_data = process.readAllStandardOutput().data()
            if img_data:
                pixmap = QPixmap()
                if pixmap.loadFromData(img_data):
                    self._sniff_panel.update_thumbnail(video_url, pixmap)
            process.deleteLater()
            
        process.finished.connect(on_finished)

    def _probe_thumbnail_via_ytdlp(self, video_url: str):
        """Use yt-dlp to extract the real thumbnail URL for a given video URL."""
        from PyQt6.QtCore import QProcess
        from core.downloader import _find_ytdlp
        
        ytdlp = _find_ytdlp()
        process = QProcess(self)
        # --get-thumbnail is very fast as it only fetches metadata
        process.start(ytdlp, ["--no-warnings", "--get-thumbnail", video_url])
        
        def on_finished():
            out = process.readAllStandardOutput().data().decode().strip()
            if out.startswith("http"):
                self._load_remote_thumbnail(video_url, out)
            process.deleteLater()
            
        process.finished.connect(on_finished)

    def _load_remote_thumbnail(self, video_url: str, thumb_url: str):
        """Fetch thumbnail image from URL with proper headers."""
        if not hasattr(self, "_thumb_nam"):
            from PyQt6.QtNetwork import QNetworkAccessManager
            self._thumb_nam = QNetworkAccessManager(self)
        
        from PyQt6.QtNetwork import QNetworkRequest
        from PyQt6.QtCore import QUrl
        
        req = QNetworkRequest(QUrl(thumb_url))
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute, True)
        # Crucial for bypassing hotlink protection
        req.setRawHeader(b"Referer", self._view.url().toString().encode())
        req.setRawHeader(b"User-Agent", self._profile.httpUserAgent().encode())
        
        reply = self._thumb_nam.get(req)
        reply.finished.connect(lambda: self._on_thumb_downloaded(video_url, reply))

    def _on_thumb_downloaded(self, video_url: str, reply: QNetworkReply):
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pixmap = QPixmap()
            if pixmap.loadFromData(reply.readAll()):
                self._sniff_panel.update_thumbnail(video_url, pixmap)
        reply.deleteLater()

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
        # domain = cookie.domain() or ""
        # name = bytes(cookie.name()).decode("utf-8", errors="replace")
        # print(f"[COOKIE+] {domain} {name}")
        self._cookie_manager.add_cookie(cookie)

    def _on_cookie_removed(self, cookie: QNetworkCookie):
        # domain = cookie.domain() or ""
        # name = bytes(cookie.name()).decode("utf-8", errors="replace")
        # print(f"[COOKIE-] {domain} {name}")
        self._cookie_manager.remove_cookie(cookie)

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
        # Use the same display name as in the SniffPanel list
        display_name = get_video_display_name(video.url)
        task.title = display_name
        self.download_requested.emit(task)

    def _on_download_all(self):
        for video in self._sniff_panel.videos:
            task = self._build_task_for_video(video)
            display_name = get_video_display_name(video.url)
            task.title = display_name
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
        if self._sniffer is not None:
            self._sniffer.clear()
        self._sniff_panel.clear()
        self._view.load(QUrl("about:blank"))

    def showEvent(self, event):
        super().showEvent(event)
        self._cookie_manager.load()
        self._restore_cookies_to_store()

    def closeEvent(self, event):
        """Window close only hides it to avoid expensive WebEngineProfile recreation."""
        event.ignore()
        try:
            if hasattr(self, "_view") and self._view:
                self._view.load(QUrl("about:blank"))
        except (RuntimeError, AttributeError):
            pass
        self._cookie_manager.save()
        self.hide()

    def shutdown(self):
        """Clean up web engine resources before app quit."""
        # 1. Disconnect signals to stop callbacks
        try:
            if hasattr(self, "_view"):
                self._view.urlChanged.disconnect(self._on_url_changed)
        except (TypeError, RuntimeError, AttributeError):
            pass

        self._cookie_manager.save()
        
        # 2. Safely destroy Sniffer
        if self._sniffer is not None:
            try:
                self._sniffer.clear()
            except Exception:
                pass
            self._profile.setUrlRequestInterceptor(None)
            self._sniffer.deleteLater()
            self._sniffer = None
            
        # 3. Safely destroy WebEngine core objects
        try:
            self._view.stop()
            self._view.load(QUrl("about:blank"))
            self._page.deleteLater()
            self._view.deleteLater()
        except (RuntimeError, AttributeError):
            pass

    def _show_cookie_manager(self):
        dialog = CookieManagerDialog(self._cookie_manager, self)
        dialog.exec()

    def _show_title_rules(self):
        """Open the title rule configuration dialog for the current page."""
        url = self._view.url().toString()
        dialog = TitleRuleDialog(self._page, url, self._title_rule_manager, self)
        dialog.exec()

    def _open_settings(self):
        from ui.settings_dialog import SettingsDialog
        SettingsDialog(self).exec()

    def _toggle_sniff_panel(self):
        """Show or hide the sniff panel and update toggle button appearance."""
        hidden = self._sniff_panel.isHidden()
        self._sniff_panel.setVisible(hidden)
        self._sniff_toggle_btn.setIcon(_make_panel_toggle_icon(hidden))
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
