from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QSpinBox,
    QComboBox,
    QLineEdit,
    QPushButton,
    QDialogButtonBox,
)

from core.config import Config


_DIALOG_STYLE = """
QDialog {
    background-color: #2d2640;
    color: #e8e8ed;
}
QLabel {
    color: #e8e8ed;
    font-size: 13px;
}
QLineEdit {
    background-color: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 6px 10px;
    color: #e8e8ed;
}
QLineEdit:focus {
    border-color: rgba(139,92,246,0.5);
}
QSpinBox, QComboBox {
    background-color: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 6px 10px;
    color: #e8e8ed;
    min-height: 20px;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #1a1a1e;
    color: #e8e8ed;
    selection-background-color: rgba(139,92,246,0.2);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
}
QPushButton {
    background-color: #8b5cf6;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 6px 16px;
    font-weight: 600;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #7c3aed;
}
QPushButton:pressed {
    background-color: #6d28d9;
}
"""


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = Config()
        self.setWindowTitle("设置")
        self.setMinimumWidth(450)
        self.setStyleSheet(_DIALOG_STYLE)
        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 下载路径
        path_layout = QHBoxLayout()
        self._path_input = QLineEdit(str(self._config.download_dir))
        self._path_input.setReadOnly(True)
        self._path_input.setStyleSheet("background-color: rgba(255,255,255,0.04); color: rgba(255,255,255,0.4);")
        browse_btn = QPushButton("浏览…")
        browse_btn.setFixedSize(72, 30)
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.clicked.connect(self._browse_dir)
        path_layout.addWidget(self._path_input)
        path_layout.addWidget(browse_btn)
        layout.addRow("下载目录:", path_layout)

        # 并发数
        self._concurrent_spin = QSpinBox()
        self._concurrent_spin.setRange(1, 10)
        self._concurrent_spin.setValue(self._config.max_concurrent)
        self._concurrent_spin.setToolTip("同时下载的任务数量，数值越大占用带宽越多")
        layout.addRow("最大并发数:", self._concurrent_spin)

        # 画质偏好
        self._quality_combo = QComboBox()
        self._quality_combo.addItems(["best", "2160p", "1440p", "1080p", "720p", "480p", "360p"])
        current = self._config.preferred_quality
        idx = self._quality_combo.findText(current)
        if idx >= 0:
            self._quality_combo.setCurrentIndex(idx)
        self._quality_combo.setToolTip("best = 自动选择最佳可用画质")
        layout.addRow("画质偏好:", self._quality_combo)

        layout.addSpacing(12)

        # 确定/取消
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择下载目录")
        if path:
            self._path_input.setText(path)

    def _save_and_accept(self):
        self._config.download_dir = Path(self._path_input.text())
        self._config.max_concurrent = self._concurrent_spin.value()
        self._config.preferred_quality = self._quality_combo.currentText()
        self.accept()
