# Physalis Project Overview

Physalis is a cross-platform video downloader built with **PyQt6** and **PyQt6-WebEngine**. It leverages `yt-dlp` as its core download engine and provides an embedded browser for sniffing video URLs from web pages and managing cookies.

## Technology Stack
- **Language:** Python 3.x
- **UI Framework:** PyQt6, PyQt6-WebEngine
- **Download Backend:** `yt-dlp` (external dependency)
- **Styling:** Custom Vanilla CSS (applied per-window to avoid macOS WebEngine issues)
- **Target OS:** Windows, macOS, Linux

## Key Architecture & Components

### Core Logic (`core/`)
- **`config.py`**: Singleton configuration manager (`Config`) that persists settings to `config.json`.
- **`downloader.py`**: `yt-dlp` wrapper using `QProcess`. Handles URL probing (`--flat-playlist`) and downloading.
- **`task.py`**: Defines the `DownloadTask` dataclass and `TaskStatus` enum.
- **`sniffer.py`**: `QWebEngineUrlRequestInterceptor` that identifies media URLs on the Chromium IO thread.
- **`cookie_manager.py`**: Manages browser cookie persistence and exports them to Netscape format for `yt-dlp`.
- **`title_rules.py`**: Domain-specific CSS selectors for extracting page titles via JavaScript injection.

### User Interface (`ui/`)
- **`main_window.py`**: The primary dashboard containing the download list and status monitoring.
- **`browser_window.py`**: An embedded browser instance used for navigation and sniffing. It is reused (hidden/shown) to prevent WebEngine crashes.
- **`sniff_panel.py`**: A side panel within the browser window that displays sniffed media resources.
- **`download_list.py`**: Custom widgets for displaying and managing individual download tasks.

## Building and Running

### Prerequisites
- Python 3.10+
- `yt-dlp` must be available in your system `PATH` or located at `bin/yt-dlp` relative to the project root.

### Setup & Execution
```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

## Development Conventions

### Coding Style
- **Qt Patterns:** Heavy use of signals and slots for inter-component communication.
- **Threading:** Heavy lifting (yt-dlp) is done via `QProcess`; sniffing occurs on the Chromium IO thread.
- **Persistence:** JSON-based persistence for config, tasks, cookies, and title rules.

### UI & Styling
- **Theme:** Dark theme (Catppuccin-like palette) defined in `app.py`.
- **macOS Compatibility:** Do **NOT** use `QApplication.setStyleSheet()`. Global styles must be applied to individual `QMainWindow` or `QDialog` instances to avoid breaking `QWebEngineView` compositing on macOS.
- **Localization:** Current UI language is `zh_CN`.

### Common Workflows
- **Adding Settings:** Update `core.config.Config` properties and add controls to `ui.settings_dialog.SettingsDialog`.
- **New Task Phases:** Modify `TaskStatus` in `core/task.py` and update UI logic in `ui/download_list.py`.
- **Title Extraction:** Add rules via `TitleRuleDialog` or modify `core/title_rules.py`.

## Project Structure
```
├── core/           # Business logic and backends
├── ui/             # PyQt6 window and widget definitions
├── utils/          # Helper utilities
├── docs/           # Design documents and plans
├── app.py          # App initialization and styles
└── main.py         # Entry point
```
