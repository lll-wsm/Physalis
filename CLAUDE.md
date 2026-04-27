# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Physalis is a cross-platform video downloader built with PyQt6 + PyQt6-WebEngine. It wraps `yt-dlp` as the download engine and provides an embedded browser for sniffing video URLs from pages and managing cookies. The UI language is zh_CN.

Two windows coexist: `MainWindow` (the app's primary window with download list) and `BrowserWindow` (embedded QWebEngineView for browsing and video sniffing). `BrowserWindow` is owned by `MainWindow` and reused across open/close cycles to avoid QtWebEngine crash on macOS.

## Running

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

**External dependency:** `yt-dlp` must be on `$PATH` or at `bin/yt-dlp` in the project root.

There is no test suite.

## Architecture

### Files

```
main.py          → app.py → ui/main_window.py
core/
  config.py       Singleton Config (__new__-based), reads/writes config.json
  task.py         DownloadTask dataclass + TaskStatus enum
  downloader.py   QProcess-based yt-dlp wrapper, probe + download
  sniffer.py      QWebEngineUrlRequestInterceptor — intercepts HTTP requests
                   and classifies them as media URLs. Runs on Chromium IO thread.
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

### Browser & Sniff Panel

`BrowserWindow` has a horizontal split: left is nav bar + QWebEngineView, right is the `SniffPanel` (260px). The sniff panel can be hidden via a close button or a toggle button in the nav bar. It supports list/grid views via QStackedWidget.

`SniffPanel` intercepts unknown format media via HEAD HTTP requests to detect Content-Type and Content-Length. Each row/card has a download icon button and an info icon button (shows `_VideoDetailDialog` with full URL, type, size, page URL).

### Probe-then-Download

Every pasted URL goes through `Downloader.probe_url()` which runs `yt-dlp --flat-playlist`. Single video → immediate download. Multiple (playlist) → `VideoSelectDialog` for selection. There is no direct download path.

### Config Singleton

`core.config.Config` is a singleton (`__new__`-based). Every setter auto-saves to `config.json` in the platform config directory. Keys: `download_dir`, `max_concurrent`, `preferred_quality`, `language`.

### Download Engine

`core.downloader.Downloader` spawns `yt-dlp` via `QProcess` with `PYTHONUNBUFFERED=1`. Progress, speed, ETA are parsed from stdout/stderr via regex patterns. Concurrency controlled by `Config().max_concurrent`. Finished tasks are persisted to `tasks_history.json`.

`VideoInfo` (used by probe results) lives in `downloader.py`. `DownloadTask` (used by downloads) lives in `task.py`.

### Title Rule System

`core/title_rules.TitleRuleManager` loads/saves `title_rules.json` with per-domain CSS selector configurations. The manager dynamically generates JS that `QWebEnginePage.runJavaScript()` executes after page load. `ui/title_rule_dialog.py` provides an interactive dialog to test selectors against the live page.

### Cookie Persistence

`core/cookie_manager.CookieManager` (QObject) persists `QNetworkCookie` objects to `cookies.json`. Browser cookies are saved on window close and restored on show. A 2-second debounce timer batches writes. Cookies are exported to Netscape format temp files for yt-dlp.

### Styling

- `app.py:MAIN_STYLE_SHEET` — global dark Catppuccin-like palette for MainWindow
- `app.py:BROWSER_STYLE_SHEET` — browser-specific styles (must not paint QMainWindow/QWidget or macOS WebEngine breaks)
- Widgets like `DownloadItemWidget`, `SniffPanel`, and dialogs have inline styles that intentionally override global sheet

App-level `setStyleSheet` is NOT used — it breaks `QWebEngineView` rendering on macOS due to a Qt/WebEngine compositing bug.

### Task History

`Downloader.save_history()` writes finished tasks to `tasks_history.json` (max 200 entries) on task completion, cancellation, and app close. `Downloader.load_history()` restores them on startup.

## Common Tasks

### Add a new settings field
1. Add property to `core.config.Config` (getter + setter calling `_save()`).
2. Add UI control in `ui.settings_dialog.SettingsDialog`.

### Add a new task status or download phase
1. Add to `TaskStatus` enum in `core/task.py`.
2. Add `mark_*()` helper on `DownloadTask` if custom logic.
3. Handle the new status in `DownloadItemWidget.update_task()` in `ui/download_list.py`.
4. If parsed from yt-dlp output, add detection in `Downloader._on_stdout()` or `._on_stderr()`.

### Test yt-dlp manually
```bash
yt-dlp --no-warnings --newline --no-check-certificates \
  -f "bestvideo[height<=720]+bestaudio/best" \
  -o "/tmp/physalis_test/%(title)s.%(ext)s" \
  "<URL>"
```
