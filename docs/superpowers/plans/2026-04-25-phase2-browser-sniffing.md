# Phase 2 - 浏览器嗅探 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an embedded browser window with video sniffing to Physalis, so users can navigate to video sites, auto-detect media URLs, and download them with cookies injected.

**Architecture:** Separate `BrowserWindow` (QMainWindow) owns a `QWebEngineProfile` with a `NetworkSniffer` (QWebEngineUrlRequestInterceptor). Sniffed videos appear in a `SniffPanel` at the bottom. Downloading extracts cookies from `QWebEngineCookieStore`, writes a temp Netscape file, and creates a `DownloadTask` (already supports `cookies_file`/`referer`) emitted via signal to MainWindow's Downloader.

**Tech Stack:** PyQt6, PyQt6-WebEngine, yt-dlp (existing)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `core/sniffer.py` | Create | `SniffedVideo` dataclass + `NetworkSniffer` (QWebEngineUrlRequestInterceptor) |
| `ui/sniff_panel.py` | Create | Bottom panel showing sniffed video list with download buttons |
| `ui/browser_window.py` | Create | Browser window: navbar + QWebEngineView + SniffPanel + cookie extraction |
| `ui/main_window.py` | Modify | Add "打开浏览器" button, wire BrowserWindow.download_requested → Downloader |
| `app.py` | Modify | Add styles for browser navbar, sniff panel |

Existing files NOT modified: `core/downloader.py`, `core/task.py`, `core/config.py` — they already support everything Phase 2 needs.

---

### Task 1: Create core/sniffer.py — SniffedVideo + NetworkSniffer

**Files:**
- Create: `core/sniffer.py`

- [ ] **Step 1: Write core/sniffer.py**

```python
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PyQt6.QtCore import pyqtSignal, QObject


@dataclass
class SniffedVideo:
    url: str
    page_url: str
    referer: str
    format_hint: str     # "m3u8" / "mp4" / "dash" / "flv" / "ts" / "webm" / "mpd"
    quality: str = ""
    timestamp: float = field(default_factory=time.time)


# URL suffixes that indicate media content
_MEDIA_SUFFIXES = (".m3u8", ".mp4", ".flv", ".ts", ".m4s", ".webm", ".mpd")

# Path keywords that indicate media content
_MEDIA_PATH_KEYWORDS = (
    "/video/", "/play/", "/stream/", "/manifest/",
    "/aweme/v1/", "/vod/", "/media/",
)

# Suffix → format_hint mapping
_SUFFIX_FORMAT = {
    ".m3u8": "m3u8",
    ".mp4": "mp4",
    ".flv": "flv",
    ".ts": "ts",
    ".m4s": "m4s",
    ".webm": "webm",
    ".mpd": "dash",
}

# Regex to strip .ts segment numbers for dedup: /seg-5.ts → /seg-.ts
_TS_SEGMENT_RE = re.compile(r"(seg[-_]?)\d+")


def _classify_url(url: str) -> str | None:
    """Return format_hint if URL looks like media, else None."""
    parsed = urlparse(url)
    path_lower = parsed.path.lower()

    for suffix in _MEDIA_SUFFIXES:
        if path_lower.endswith(suffix):
            return _SUFFIX_FORMAT[suffix]

    for kw in _MEDIA_PATH_KEYWORDS:
        if kw in path_lower:
            return "media"

    return None


def _dedup_key(url: str) -> str:
    """Normalize URL for dedup: strip .ts segment numbers."""
    return _TS_SEGMENT_RE.sub(r"\1N", url)


class NetworkSniffer(QWebEngineUrlRequestInterceptor):
    video_found = pyqtSignal(object)  # SniffedVideo

    def __init__(self, parent=None):
        super().__init__(parent)
        self._seen: set[str] = set()

    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        fmt = _classify_url(url)
        if fmt is None:
            return

        key = _dedup_key(url)
        if key in self._seen:
            return
        self._seen.add(key)

        page_url = info.firstPartyUrl().toString()
        referer = ""
        for header, value in info.httpHeaders():
            if header.lower() == "referer":
                referer = value.toString() if hasattr(value, "toString") else str(value)
                break

        video = SniffedVideo(
            url=url,
            page_url=page_url,
            referer=referer,
            format_hint=fmt,
        )
        self.video_found.emit(video)

    def clear(self):
        self._seen.clear()
```

- [ ] **Step 2: Run the app to verify import works**

Run: `.venv/bin/python -c "from core.sniffer import NetworkSniffer, SniffedVideo; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add core/sniffer.py
git commit -m "feat: add NetworkSniffer with URL-pattern media detection"
```

---

### Task 2: Create ui/sniff_panel.py — SniffPanel widget

**Files:**
- Create: `ui/sniff_panel.py`

- [ ] **Step 1: Write ui/sniff_panel.py**

```python
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.sniffer import SniffedVideo


class _VideoRow(QWidget):
    download_clicked = pyqtSignal(object)  # SniffedVideo

    def __init__(self, video: SniffedVideo, parent=None):
        super().__init__(parent)
        self._video = video
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # Title/URL — show path from URL as display name
        parsed = urlparse(self._video.url)
        display = parsed.path.split("/")[-1] or self._video.url
        if len(display) > 50:
            display = display[:47] + "..."
        title = QLabel(display)
        title.setToolTip(self._video.url)
        title.setStyleSheet("color: #e8e8ed; font-size: 13px;")
        layout.addWidget(title, 1)

        # Format tag
        fmt = QLabel(self._video.format_hint)
        fmt.setFixedSize(42, 22)
        fmt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fmt.setStyleSheet("""
            background-color: rgba(59,130,246,0.15);
            color: #60a5fa;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        """)
        layout.addWidget(fmt)

        # Download button
        btn = QPushButton("下载")
        btn.setFixedSize(52, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.download_clicked.emit(self._video))
        layout.addWidget(btn)


class SniffPanel(QWidget):
    download_requested = pyqtSignal(object)   # SniffedVideo
    download_all_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._videos: list[SniffedVideo] = []
        self._seen_urls: set[str] = set()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar
        top = QHBoxLayout()
        top.setContentsMargins(16, 10, 16, 10)

        self._count_label = QLabel("嗅探到 0 个视频")
        self._count_label.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: rgba(255,255,255,0.7);"
        )
        top.addWidget(self._count_label)
        top.addStretch()

        clear_btn = QPushButton("清除")
        clear_btn.setFixedSize(52, 28)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setObjectName("secondaryBtn")
        clear_btn.clicked.connect(self.clear)
        top.addWidget(clear_btn)

        all_btn = QPushButton("全部下载")
        all_btn.setFixedSize(72, 28)
        all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        all_btn.clicked.connect(self.download_all_requested.emit)
        top.addWidget(all_btn)

        layout.addLayout(top)

        # Scrollable video list
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { width: 6px; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,0.1); border-radius: 3px; }
        """)

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_widget)
        layout.addWidget(self._scroll)

    def add_video(self, video: SniffedVideo):
        if video.url in self._seen_urls:
            return
        self._seen_urls.add(video.url)
        self._videos.append(video)

        row = _VideoRow(video)
        row.download_clicked.connect(self.download_requested.emit)
        # Insert before the stretch
        self._list_layout.insertWidget(self._list_layout.count() - 1, row)

        self._count_label.setText(f"嗅探到 {len(self._videos)} 个视频")

    def clear(self):
        self._videos.clear()
        self._seen_urls.clear()
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._count_label.setText("嗅探到 0 个视频")

    @property
    def videos(self) -> list[SniffedVideo]:
        return list(self._videos)
```

- [ ] **Step 2: Verify import**

Run: `.venv/bin/python -c "from ui.sniff_panel import SniffPanel; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add ui/sniff_panel.py
git commit -m "feat: add SniffPanel with video list and download buttons"
```

---

### Task 3: Create ui/browser_window.py — BrowserWindow

**Files:**
- Create: `ui/browser_window.py`

- [ ] **Step 1: Write ui/browser_window.py**

```python
import tempfile
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.sniffer import NetworkSniffer, SniffedVideo
from core.task import DownloadTask
from ui.sniff_panel import SniffPanel


def _domain_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        # Extract registrable domain: a.bilibili.com → bilibili.com
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host
    except Exception:
        return ""


def _write_netscape_cookies(cookies: list[QNetworkCookie], path: str):
    """Write cookies in Netscape format for yt-dlp --cookies."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for c in cookies:
            domain = c.domain() if c.domain() else ""
            flag = "TRUE" if not domain.startswith(".") else "FALSE"
            path_ = c.path() if c.path() else "/"
            secure = "TRUE" if c.isSecure() else "FALSE"
            expires = str(int(c.expirationDate().toSecsSinceEpoch())) if c.expirationDate().isValid() else "0"
            name = bytes(c.name()).decode("utf-8", errors="replace")
            value = bytes(c.value()).decode("utf-8", errors="replace")
            f.write(f"{domain}\t{flag}\t{path_}\t{secure}\t{expires}\t{name}\t{value}\n")


class BrowserWindow(QMainWindow):
    download_requested = pyqtSignal(DownloadTask)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sniffer: NetworkSniffer | None = None
        self._cookie_store = None
        self._pending_downloads: list[tuple[SniffedVideo, str]] = []  # (video, domain)
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("Physalis 浏览器")
        self.setMinimumSize(960, 680)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Navigation bar ---
        nav = QHBoxLayout()
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

        self._url_bar = QLineEdit()
        self._url_bar.setPlaceholderText("输入网址...")
        self._url_bar.returnPressed.connect(self._navigate)
        nav.addWidget(self._url_bar, 1)

        layout.addLayout(nav)

        # --- Web view ---
        self._profile = QWebEngineProfile("physalis_browser", self)
        self._profile.setHttpUserAgent(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        self._sniffer = NetworkSniffer(self)
        self._profile.setUrlRequestInterceptor(self._sniffer)
        self._cookie_store = self._profile.cookieStore()

        self._page = QWebEnginePage(self._profile, self)
        self._view = QWebEngineView(self)
        self._view.setPage(self._page)
        self._view.urlChanged.connect(self._on_url_changed)
        layout.addWidget(self._view, 1)

        # --- Sniff panel ---
        self._sniff_panel = SniffPanel()
        self._sniff_panel.setMaximumHeight(260)
        self._sniffer.video_found.connect(self._sniff_panel.add_video)
        self._sniff_panel.download_requested.connect(self._on_download_video)
        self._sniff_panel.download_all_requested.connect(self._on_download_all)
        layout.addWidget(self._sniff_panel)

        # Load a blank page
        self._view.load(QUrl("about:blank"))

    def _on_url_changed(self, url: QUrl):
        self._url_bar.setText(url.toString())

    def _navigate(self):
        text = self._url_bar.text().strip()
        if not text:
            return
        if not text.startswith(("http://", "https://")):
            text = "https://" + text
        self._view.load(QUrl(text))

    def _go_back(self):
        self._view.back()

    def _go_forward(self):
        self._view.forward()

    def _reload(self):
        self._view.reload()

    def _on_download_video(self, video: SniffedVideo):
        domain = _domain_from_url(video.page_url or video.url)
        self._pending_downloads.append((video, domain))
        self._cookie_store.getAllCookies(self._on_cookies_for_download)

    def _on_download_all(self):
        for video in self._sniff_panel.videos:
            domain = _domain_from_url(video.page_url or video.url)
            self._pending_downloads.append((video, domain))
        self._cookie_store.getAllCookies(self._on_cookies_for_download)

    def _on_cookies_for_download(self, cookies: list[QNetworkCookie]):
        if not self._pending_downloads:
            return

        # Group pending by domain, process first group
        video, domain = self._pending_downloads.pop(0)
        domain_cookies = []
        for c in cookies:
            cdomain = c.domain()
            if cdomain == domain or cdomain.endswith("." + domain):
                domain_cookies.append(c)

        cookies_file = ""
        if domain_cookies:
            fd, cookies_file = tempfile.mkstemp(
                suffix=".txt", prefix=f"physalis_cookies_{domain}_"
            )
            _write_netscape_cookies(domain_cookies, cookies_file)

        task = DownloadTask(
            url=video.url,
            referer=video.referer or video.page_url,
            cookies_file=cookies_file,
        )
        self.download_requested.emit(task)

        # If more pending, request cookies again
        if self._pending_downloads:
            self._cookie_store.getAllCookies(self._on_cookies_for_download)

    def load_url(self, url: str):
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self._view.load(QUrl(url))
```

- [ ] **Step 2: Verify import**

Run: `.venv/bin/python -c "from ui.browser_window import BrowserWindow; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add ui/browser_window.py
git commit -m "feat: add BrowserWindow with web view, sniffer, and cookie extraction"
```

---

### Task 4: Modify ui/main_window.py — Add browser entry point

**Files:**
- Modify: `ui/main_window.py`

- [ ] **Step 1: Add import and browser button**

Add `from ui.browser_window import BrowserWindow` to imports at line 19.

Add a "打开浏览器" button next to the "从剪贴板添加" button in `_setup_ui()`. In the `top_layout` section, add the button before the paste button:

In `_setup_ui()`, after `top_layout.addStretch()` (line 45), insert:

```python
        self._browser_btn = QPushButton("打开浏览器")
        self._browser_btn.setMinimumHeight(36)
        self._browser_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        top_layout.addWidget(self._browser_btn)
```

- [ ] **Step 2: Add browser window management**

In `__init__`, add `self._browser_window: BrowserWindow | None = None` after `self._config = Config()`.

In `_connect_signals`, add:

```python
        self._browser_btn.clicked.connect(self._open_browser)
```

Add method `_open_browser`:

```python
    def _open_browser(self):
        if self._browser_window is not None and self._browser_window.isVisible():
            self._browser_window.raise_()
            self._browser_window.activateWindow()
            return
        self._browser_window = BrowserWindow(self)
        self._browser_window.download_requested.connect(self._on_sniffed_download)
        self._browser_window.show()

    def _on_sniffed_download(self, task: DownloadTask):
        self._download_list.add_task(task)
        self._downloader.add_task(task)
        self._empty_hint.setVisible(False)
        self._download_list.setVisible(True)
        self._statusbar.showMessage(f"已添加下载: {task.url[:60]}")
```

- [ ] **Step 3: Run the app and test**

Run: `.venv/bin/python main.py`
Expected: Main window shows with "打开浏览器" button. Clicking it opens a separate browser window. The browser window has a nav bar, web view, and sniff panel.

- [ ] **Step 4: Commit**

```bash
git add ui/main_window.py
git commit -m "feat: add browser window entry point in MainWindow"
```

---

### Task 5: Modify app.py — Add browser-related styles

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add styles for browser navbar, sniff panel**

In `_apply_style()`, add inside the stylesheet string (before the closing `""")`). Add after the `QScrollBar` section:

```css
        /* === Browser Nav === */
        QLineEdit#urlBar {
            background-color: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            padding: 6px 12px;
            color: #e8e8ed;
            font-size: 13px;
        }
        QLineEdit#urlBar:focus {
            border-color: rgba(120,160,255,0.5);
        }

        /* Nav buttons */
        QPushButton[class="navBtn"] {
            background-color: rgba(255,255,255,0.06);
            color: #e8e8ed;
            border: none;
            border-radius: 6px;
            font-size: 16px;
        }
        QPushButton[class="navBtn"]:hover {
            background-color: rgba(255,255,255,0.12);
        }
```

- [ ] **Step 2: Apply object names in BrowserWindow**

In `ui/browser_window.py`, set object names so styles apply:

After creating `_url_bar`: `self._url_bar.setObjectName("urlBar")`

After creating `_back_btn`, `_fwd_btn`, `_reload_btn`: add
```python
        for btn in (self._back_btn, self._fwd_btn, self._reload_btn):
            btn.setProperty("class", "navBtn")
```

- [ ] **Step 3: Run the app, verify browser window styling**

Run: `.venv/bin/python main.py`
Expected: Browser window has dark-themed nav bar matching the rest of the app.

- [ ] **Step 4: Commit**

```bash
git add app.py ui/browser_window.py
git commit -m "feat: add browser navbar styles to global stylesheet"
```

---

### Task 6: Integration test — Full end-to-end flow

**Files:** None (manual testing)

- [ ] **Step 1: Run the application**

Run: `.venv/bin/python main.py`

- [ ] **Step 2: Test browser opening**

Click "打开浏览器" → browser window opens. Click again → same window is raised (no duplicate).

- [ ] **Step 3: Test navigation**

Type `https://www.bilibili.com` in address bar, press Enter. Page loads, URL bar updates.

- [ ] **Step 4: Test sniffing**

Navigate to a video page on Bilibili. Sniff panel at bottom should populate with detected media URLs (m3u8, mp4, etc.). Verify no duplicate entries.

- [ ] **Step 5: Test single download**

Click "下载" on a sniffed video. Main window's download list should show a new task with progress.

- [ ] **Step 6: Test bulk download**

Click "全部下载". All sniffed videos should appear in main window's download list.

- [ ] **Step 7: Test clear**

Click "清除" in sniff panel. Video list should empty.

- [ ] **Step 8: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: integration fixes for browser sniffing flow"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- ✅ Browser window (separate QMainWindow) → Task 3
- ✅ NetworkSniffer (QWebEngineUrlRequestInterceptor) → Task 1
- ✅ SniffPanel (bottom panel with video list) → Task 2
- ✅ URL pattern matching → Task 1
- ✅ Cookie extraction (in-memory, Netscape format) → Task 3
- ✅ DownloadTask with cookies_file/referer → already exists in core/task.py
- ✅ MainWindow integration → Task 4
- ✅ Styling → Task 5

**2. Placeholder scan:** No TBDs, TODOs, or vague steps found.

**3. Type consistency:**
- `SniffedVideo` defined in Task 1, used in Task 2 (SniffPanel), Task 3 (BrowserWindow), Task 4 (signal wiring)
- `download_requested` signal on BrowserWindow emits `DownloadTask` — matches `Downloader.add_task(task: DownloadTask)` signature
- `NetworkSniffer.video_found` emits `object` → SniffPanel.add_video accepts `SniffedVideo` (compatible since SniffedVideo is an object)
- Cookie file path is `str` — matches `DownloadTask.cookies_file: str`
