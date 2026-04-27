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
        font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif;
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
        background-color: #1a1a1e;
        color: #e8e8ed;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px;
        padding: 6px;
    }
    QMenu::item {
        padding: 6px 18px;
        border-radius: 6px;
    }
    QMenu::item:selected {
        background-color: rgba(139,92,246,0.2);
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
"""


# BrowserWindow stylesheet must NOT include rules that paint QMainWindow or
# QWidget itself, otherwise the embedded QWebEngineView fails to composite on
# macOS. Only style the inner controls (nav buttons, URL bar, status bar).
BROWSER_STYLE_SHEET = """
    QPushButton {
        background-color: #8b5cf6;
        color: #ffffff;
        border: none;
        border-radius: 10px;
        padding: 8px 20px;
        font-weight: 600;
        font-size: 13px;
    }
    QPushButton:hover { background-color: #7c3aed; }
    QPushButton:pressed { background-color: #6d28d9; }
    QPushButton:disabled {
        background-color: rgba(255,255,255,0.08);
        color: rgba(255,255,255,0.25);
    }
    QPushButton.secondary {
        background-color: rgba(255,255,255,0.08);
        color: #e8e8ed;
    }
    QPushButton.secondary:hover { background-color: rgba(255,255,255,0.14); }

    QLineEdit#urlBar {
        background-color: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px;
        padding: 6px 12px;
        color: #e8e8ed;
        font-size: 13px;
    }
    QLineEdit#urlBar:focus { border-color: rgba(139,92,246,0.5); }

    QPushButton.navBtn {
        background-color: rgba(255,255,255,0.06);
        color: #c4b5fd;
        border: none;
        border-radius: 6px;
        font-size: 16px;
    }
    QPushButton.navBtn:hover { background-color: rgba(139,92,246,0.25); }

    QStatusBar {
        background-color: #241f38;
        color: rgba(255,255,255,0.55);
    }
    QStatusBar::item { border: none; }
"""


def create_app() -> QApplication:
    # Required by QtWebEngine when embedded in a QApplication.
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)
    app.setApplicationName("Physalis")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("Physalis")

    # Set app icon (dock icon on macOS)
    icon_path = Path(__file__).parent / "Biberry.icns"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    app.setStyle("Fusion")
    _ensure_download_dir()

    return app


def _ensure_download_dir():
    config = Config()
    config.download_dir.mkdir(parents=True, exist_ok=True)
