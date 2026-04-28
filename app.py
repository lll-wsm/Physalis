import sys

from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtGui import QIcon, QPixmap

from core.config import Config


# Stylesheet is applied per-window (MainWindow, BrowserWindow) rather than to
# the QApplication. On macOS, an app-level QtWebEngine + QApplication.setStyleSheet
# combination prevents QWebEngineView from compositing its rendered frames.
MAIN_STYLE_SHEET = """
    /* === Base === */
    QMainWindow {
        background-color: #2d2640;
    }
    QWidget {
        color: #e8e8ed;
        font-family: "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif;
        font-size: 13px;
    }

    /* === Input === */
    QLineEdit {
        background-color: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px;
        padding: 8px 14px;
        color: #e8e8ed;
        font-size: 14px;
    }
    QLineEdit:focus {
        border-color: rgba(139,92,246,0.5);
        background-color: rgba(255,255,255,0.09);
    }
    QLineEdit::placeholder {
        color: rgba(255,255,255,0.25);
    }

    /* === Primary Button === */
    QPushButton {
        background-color: #8b5cf6;
        color: #ffffff;
        border: none;
        border-radius: 10px;
        padding: 8px 20px;
        font-weight: 600;
        font-size: 13px;
    }
    QPushButton:hover {
        background-color: #7c3aed;
    }
    QPushButton:pressed {
        background-color: #6d28d9;
    }
    QPushButton:disabled {
        background-color: rgba(255,255,255,0.08);
        color: rgba(255,255,255,0.25);
    }

    /* === Secondary Button === */
    QPushButton.secondary {
        background-color: rgba(255,255,255,0.08);
        color: #e8e8ed;
    }
    QPushButton.secondary:hover {
        background-color: rgba(255,255,255,0.14);
    }

    /* === Table === */
    QTableWidget {
        background-color: transparent;
        border: none;
        border-radius: 12px;
        gridline-color: transparent;
    }
    QTableWidget::item {
        padding: 6px;
        border-bottom: 1px solid rgba(255,255,255,0.04);
    }
    QTableWidget::item:selected {
        background-color: rgba(139,92,246,0.15);
        color: #e8e8ed;
    }
    QHeaderView::section {
        background-color: transparent;
        color: rgba(255,255,255,0.4);
        border: none;
        border-bottom: 1px solid rgba(255,255,255,0.08);
        padding: 8px 6px;
        font-weight: 600;
        font-size: 12px;
    }
    QHeaderView::section:first {
        padding-left: 12px;
    }

    /* === Progress === */
    QProgressBar {
        background-color: rgba(255,255,255,0.08);
        border: none;
        border-radius: 6px;
        text-align: center;
        color: transparent;
        height: 6px;
    }
    QProgressBar::chunk {
        background-color: #8b5cf6;
        border-radius: 6px;
    }

    /* === Status & Menu === */
    QStatusBar {
        background-color: #241f38;
        color: rgba(255,255,255,0.35);
    }
    QStatusBar::item {
        border: none;
    }
    QMenuBar {
        background-color: transparent;
        color: #e8e8ed;
    }
    QMenuBar::item:selected {
        background-color: rgba(255,255,255,0.08);
        border-radius: 6px;
    }
    QMenu {
        background-color: #241f38;
        color: #e8e8ed;
        border: 1px solid rgba(139,92,246,0.3);
        border-radius: 10px;
        padding: 6px;
    }
    QMenu::item {
        padding: 8px 24px;
        border-radius: 6px;
        margin: 2px 4px;
    }
    QMenu::item:selected {
        background-color: rgba(139,92,246,0.25);
        color: #ffffff;
    }
    QMenu::separator {
        height: 1px;
        background: rgba(255,255,255,0.06);
        margin: 4px 10px;
    }

    /* === Dialog === */
    QDialog {
        background-color: #2d2640;
    }

    /* === Spin & Combo === */
    QSpinBox, QComboBox {
        background-color: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px;
        padding: 6px 10px;
        color: #e8e8ed;
    }
    QComboBox QAbstractItemView {
        background-color: #1a1a1e;
        color: #e8e8ed;
        selection-background-color: rgba(139,92,246,0.2);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px;
    }
    QComboBox::drop-down {
        border: none;
        width: 24px;
    }

    /* === ScrollBar === */
    QScrollBar:vertical {
        background: transparent;
        width: 8px;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical {
        background: rgba(255,255,255,0.12);
        border-radius: 4px;
        min-height: 30px;
    }
    QScrollBar::handle:vertical:hover {
        background: rgba(255,255,255,0.2);
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }

    /* === ToolTip === */
    QToolTip {
        background-color: #0f0d1a; /* Darker, solid color */
        color: #ffffff;
        border: 1px solid #8b5cf6; /* Solid purple border */
        border-radius: 6px;
        padding: 8px;
    }
"""


# BrowserWindow stylesheet must NOT include rules that paint QMainWindow or
# QWidget itself, otherwise the embedded QWebEngineView fails to composite on
# macOS. Only style the inner controls (nav buttons, URL bar, status bar).
BROWSER_STYLE_SHEET = """
    /* === Navigation Buttons === */
    QPushButton.navBtn {
        background-color: rgba(255,255,255,0.05);
        color: #c4b5fd;
        border: 1px solid rgba(255,255,255,0.03);
        border-radius: 6px;
        font-size: 15px;
        font-weight: bold;
    }
    QPushButton.navBtn:hover {
        background-color: rgba(139,92,246,0.15);
        color: #ffffff;
        border-color: rgba(139,92,246,0.1);
    }
    QPushButton.navBtn:pressed {
        background-color: rgba(139,92,246,0.25);
    }

    /* === Tool Buttons (Cookie, Rules etc) === */
    QPushButton.toolBtn {
        background: rgba(255,255,255,0.06);
        color: #a78bfa;
        border: none;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 600;
        padding: 0 8px;
    }
    QPushButton.toolBtn:hover {
        background: rgba(255,255,255,0.12);
        color: #ffffff;
    }

    /* === URL Bar === */
    QLineEdit#urlBar {
        background-color: rgba(0,0,0,0.2);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px;
        padding: 6px 14px;
        color: #e2e8f0;
        font-size: 13px;
        selection-background-color: #8b5cf6;
    }
    QLineEdit#urlBar:focus {
        border-color: rgba(139,92,246,0.5);
        background-color: rgba(0,0,0,0.3);
    }

    /* === Status Bar === */
    QStatusBar {
        background-color: #241f38;
        color: rgba(255,255,255,0.45);
        font-size: 11px;
    }
    QStatusBar::item { border: none; }
"""


def create_app() -> QApplication:
    import os
    from pathlib import Path
    
    # Fix PATH for macOS bundled app (ensure ffmpeg/yt-dlp are found)
    if sys.platform == "darwin":
        extra_paths = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
        current_path = os.environ.get("PATH", "")
        for p in extra_paths:
            if p not in current_path:
                current_path = f"{p}:{current_path}"
        os.environ["PATH"] = current_path

    # Set Qt WebEngine path for packaged app
    if getattr(sys, 'frozen', False):
        # In onedir bundle, _MEIPASS points to Contents/Frameworks
        # The actual path structure is: Contents/Frameworks/PyQt6/...
        meipass = Path(sys._MEIPASS)  # This is Contents/Frameworks
        app_contents = meipass.parent  # This is Contents
        frameworks_dir = app_contents / "Frameworks"

        # QtWebEngineProcess is located in the PyQt6 framework bundle
        webengine_process_path = (
            frameworks_dir / "PyQt6" / "Qt6" / "lib" / "QtWebEngineCore.framework"
            / "Versions" / "Resources" / "Helpers" / "QtWebEngineProcess.app" / "Contents" / "MacOS" / "QtWebEngineProcess"
        )
        if webengine_process_path.exists():
            os.environ["QTWEBENGINE_PROCESS_PATH"] = str(webengine_process_path.parent)

        # Also set library path so Qt can find frameworks
        os.environ["DYLD_FRAMEWORK_PATH"] = str(frameworks_dir) + ":" + os.environ.get("DYLD_FRAMEWORK_PATH", "")

    # Set Chromium flags BEFORE QApplication is created
    # --disable-blink-features=AutomationControlled: Hides the "navigator.webdriver" flag
    # --enable-features=NetworkServiceInProcess: Improves stability
    # --ignore-gpu-blocklist: Forces hardware acceleration
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--ignore-gpu-blocklist "
        "--enable-gpu-rasterization "
        "--enable-zero-copy "
        "--disable-blink-features=AutomationControlled "
        "--enable-features=WebRTCPipeWireCapturer,Vulkan"
    )

    # Required by QtWebEngine when embedded in a QApplication.
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)
    app.setApplicationName("Physalis")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("Physalis")

    # Set app icon (dock icon on macOS)
    icon_path = Path(__file__).parent / "Physalis.icns"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    app.setStyle("Fusion")
    _ensure_download_dir()

    return app


def _ensure_download_dir():
    config = Config()
    config.download_dir.mkdir(parents=True, exist_ok=True)
