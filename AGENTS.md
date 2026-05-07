# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

Physalis is a cross-platform video downloader built with PyQt6 + PyQt6-WebEngine (Python 3.10+). It wraps `yt-dlp` as the download engine and provides an embedded browser for sniffing video URLs from pages and managing cookies. The UI language is zh_CN.

Two windows coexist: `MainWindow` (the app's primary window with download list) and `BrowserWindow` (embedded QWebEngineView for browsing and video sniffing). `BrowserWindow` is owned by `MainWindow` and reused across open/close cycles to avoid QtWebEngine crash on macOS.

**Entry point:** `main.py` → `app.create_app()` (sets Chromium flags + Qt attributes + Fusion style) → `MainWindow()` → `app.exec()`.

## Running

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

**External dependency:** `yt-dlp` must be on `$PATH` or at `bin/yt-dlp` in the project root. Resolution order (see `core/downloader.py:_find_ytdlp`): `shutil.which("yt-dlp")` → `/opt/homebrew/bin/yt-dlp` (macOS) → `/usr/local/bin/yt-dlp` (macOS) → `bin/yt-dlp` → fallback to bare `"yt-dlp"`.

There is no test suite.

## Building

```bash
# macOS app
./build_macapp.sh
# Output: dist/Physalis.app

# Linux .deb package
./build_linux.sh
# Output: dist/physalis_<version>_amd64.deb
```

Both use PyInstaller `--onedir`. The macOS build uses `Physalis.spec` and fixes PATH/symlinks for bundled apps. The Linux build packages the PyInstaller output into a `.deb` (installs to `/opt/Physalis/`, creates `/usr/bin/physalis` wrapper, `.desktop` file, icons).

## Architecture

### Files

```
main.py          → app.py (create_app, style sheets) → ui/main_window.py
core/
  config.py       Singleton Config (__new__-based), reads/writes config.json
  task.py         DownloadTask dataclass + TaskStatus enum
  downloader.py   QProcess-based yt-dlp wrapper, probe + download; also defines VideoInfo
  sniffer.py      QWebEngineUrlRequestInterceptor + SniffedVideo dataclass — intercepts
                   HTTP requests and classifies them as media URLs. Runs on Chromium IO thread.
  cookie_manager.py  CookieManager (QObject) — persists cookies to JSON
  title_rules.py  TitleRuleManager — per-domain CSS selector rules for
                   extracting page titles via injected JS
ui/
  main_window.py         MainWindow — download list + status bar + menus
  browser_window.py      BrowserWindow — embedded web engine + sniff panel
  sniff_panel.py         Right-side panel showing sniffed video resources
                         with list/grid toggle, download/info buttons
  download_list.py       DownloadListWidget + DownloadItemWidget
  video_select_dialog.py Dialog for playlist selection
  settings_dialog.py     Config editor
  title_rule_dialog.py   Interactive CSS selector tester/saver for title rules
  cookie_manager_dialog.py  Cookie viewer/editor
ui/resources/    Icons and other static assets
utils/           Helper utilities (currently empty)
docs/            Design documents and plans
```

### Signals Flow

`MainWindow` owns `Downloader`. `BrowserWindow` is a child of `MainWindow` (created on demand, reused via hide/show). Download tasks travel through signals:

```
MainWindow._start_download → Downloader.add_task
  → signal: task_progress/completed/failed/cancelled → MainWindow → DownloadListWidget
```

The sniff path:
```
BrowserWindow.webview → NetworkSniffer.interceptRequest (Chrome IO thread)
  → signal: video_found → BrowserWindow._on_video_sniffed → SniffPanel
  → user clicks download → signal → BrowserWindow._on_download_video
  → signal: download_requested → MainWindow._on_sniffed_download → Downloader
```

### Probe-then-Download

Every pasted URL goes through `Downloader.probe_url()` which runs `yt-dlp --flat-playlist`. Single video → immediate download. Multiple (playlist) → `VideoSelectDialog` for selection. There is no direct download path.

### Sniffer — IO Thread Safety

`NetworkSniffer.interceptRequest` runs on Chromium's IO thread. Any uncaught exception **aborts the entire process**, so the method wraps all logic in try/except. When modifying sniffer code, always maintain this safety net.

Dedup strategy (`_dedup_key`): segment-based formats (.ts, .m4s) deduplicate by parent directory; URLs with `video_id`/`vid`/`id` query params deduplicate by that ID; media-keyword paths extract long hex IDs (20+ chars); default strips all query strings.

Classification (`_classify_url`): checks images (respects `sniff_images` config), scripts/styles (respects `sniff_scripts`), fonts (respects `sniff_fonts`), non-media rejection, media suffix match, `.ts` segment check (directory name must be in `("stream", "seg", "segment", "chunks", "video")`), path keyword match.

### Config Singleton

`core.config.Config` is a singleton (`__new__`-based). Every setter auto-saves to `config.json` in the platform config directory (`~/Library/Application Support/Physalis` on macOS, `%APPDATA%/Physalis` on Windows, `$XDG_CONFIG_HOME/Physalis` on Linux, defaulting to `~/.config/Physalis`).

Config keys: `download_dir`, `max_concurrent` (1–10, clamped), `preferred_quality`, `language`, `sniff_filter_types`, `filter_empty_type`, `sniff_images`, `sniff_scripts`, `sniff_fonts`.

### Download Engine

`core.downloader.Downloader` spawns `yt-dlp` via `QProcess` with `PYTHONUNBUFFERED=1`. Progress, speed, ETA are parsed from stdout/stderr via regex patterns. Concurrency controlled by `Config().max_concurrent` (1–10). Finished tasks are persisted to `tasks_history.json`.

Pause/resume works by killing the QProcess (and its children via `pgrep -P`) and re-adding the task to the queue on resume.

`VideoInfo` (used by probe results) lives in `downloader.py`. `DownloadTask` (used by downloads) lives in `task.py`.

**Known gap:** `preferred_quality` config is saved and exposed in settings UI but is NOT passed to yt-dlp's `-f`/`-S` arguments in `_build_args()`. All downloads use yt-dlp's default format selection.

### Title Rule System

`core/title_rules.TitleRuleManager` loads/saves `title_rules.json` with per-domain CSS selector configurations. Built-in defaults cover: douyin.com, bilibili.com, youtube.com, weibo.com, xiaohongshu.com, kuaishou.com, tiktok.com. Selector types: `meta` (HTML meta tags), `jsonld` (JSON-LD script blocks), `dom` (CSS selector), `url_path` (pathname segment), `document_title` (with site name stripping). The manager dynamically generates JS that `QWebEnginePage.runJavaScript()` executes after page load. `ui/title_rule_dialog.py` provides an interactive dialog to test selectors against the live page.

### Cookie Persistence

`core.cookie_manager.CookieManager` (QObject) persists `QNetworkCookie` objects to `cookies.json`. Browser cookies are saved on window close and restored on show. A 2-second debounce timer batches writes. Cookies are exported to Netscape format temp files for yt-dlp.

### Styling

- `app.py:MAIN_STYLE_SHEET` — global dark Catppuccin-like palette (purple `#2d2640`/`#8b5cf6`) for MainWindow
- `app.py:BROWSER_STYLE_SHEET` — browser-specific styles (must not paint QMainWindow/QWidget or macOS WebEngine breaks)
- Widgets like `DownloadItemWidget`, `SniffPanel`, and dialogs have inline styles that intentionally override global sheet

Stylesheets are applied per-window, NOT via `QApplication.setStyleSheet()` — that breaks `QWebEngineView` compositing on macOS.

### Chromium Flags

`create_app()` sets `QTWEBENGINE_CHROMIUM_FLAGS` before `QApplication` creation: `--ignore-gpu-blocklist`, `--enable-gpu-rasterization`, `--enable-zero-copy`, `--disable-blink-features=AutomationControlled`, `--enable-features=NetworkServiceInProcess,WebRTCPipeWireCapturer,Vulkan`. Also enables `AA_ShareOpenGLContexts`. These must be set before `QApplication()` is constructed.

### Task History

`Downloader.save_history()` writes finished tasks to `tasks_history.json` on task completion, cancellation, and app close. `Downloader.load_history()` restores them on startup.

### Popup/OAuth Handling

`BrowserWindow._PopupWebPage` (inner class) handles OAuth popups by opening a QDialog with embedded QWebEngineView. For x.com/twitter.com, auto-closes when the popup URL indicates OAuth completion.

## Common Tasks

### Add a new settings field
1. Add property to `core.config.Config` (getter + setter calling `_save()`).
2. Add UI control in `ui.settings_dialog.SettingsDialog`.

### Add a new task status or download phase
1. Add to `TaskStatus` enum in `core/task.py`.
2. Add `mark_*()` helper on `DownloadTask` if custom logic.
3. Handle the new status in `DownloadItemWidget.update_task()` in `ui/download_list.py`.
4. If parsed from yt-dlp output, add detection in `Downloader._on_stdout()` or `._on_stderr()`.

### Add a new sniffed format
1. Add suffix to `_MEDIA_SUFFIXES` and mapping to `_SUFFIX_FORMAT` in `core/sniffer.py`.
2. Update `SniffedVideo.format_hint` docstring if the new format needs special handling.
3. If the format is segment-based, add to `_SEGMENT_SUFFIXES` for directory-level dedup.

### Test yt-dlp manually
```bash
yt-dlp --no-warnings --newline --no-check-certificates \
  -f "bestvideo[height<=720]+bestaudio/best" \
  -o "/tmp/physalis_test/%(title)s.%(ext)s" \
  "<URL>"
```
