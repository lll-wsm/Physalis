from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.downloader import VideoInfo


_DIALOG_STYLE = """
QDialog {
    background-color: #2d2640;
    color: #e8e8ed;
}
QTableWidget {
    background-color: transparent;
    border: none;
    border-radius: 10px;
}
QTableWidget::item {
    padding: 8px 6px;
    border-bottom: 1px solid rgba(255,255,255,0.04);
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
QPushButton {
    background-color: #8b5cf6;
    color: #ffffff;
    border: none;
    border-radius: 8px;
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
"""


class VideoSelectDialog(QDialog):
    def __init__(self, videos: list[VideoInfo], parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择要下载的视频")
        self.setMinimumSize(680, 440)
        self.setStyleSheet(_DIALOG_STYLE)
        self._videos = videos
        self._selected: list[VideoInfo] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(16)

        # 标题
        title_layout = QHBoxLayout()
        title_label = QLabel("选择视频")
        title_label.setStyleSheet("font-size: 18px; font-weight: 700; color: #ffffff; background: transparent;")
        title_layout.addWidget(title_label)

        count_label = QLabel(f"发现 {len(self._videos)} 个视频")
        count_label.setStyleSheet("color: rgba(255,255,255,0.4); background: transparent;")
        title_layout.addWidget(count_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 表格
        self._table = QTableWidget(len(self._videos), 4)
        self._table.setHorizontalHeaderLabels(["选择", "序号", "标题", "时长"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)

        for i, v in enumerate(self._videos):
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check_item.setCheckState(Qt.CheckState.Checked)
            self._table.setItem(i, 0, check_item)

            idx = v.playlist_index or str(i + 1)
            self._table.setItem(i, 1, QTableWidgetItem(idx))

            title = v.title or v.id or v.url
            self._table.setItem(i, 2, QTableWidgetItem(title))

            duration = v.duration
            if duration:
                try:
                    secs = int(float(duration))
                    if secs >= 3600:
                        duration = f"{secs // 3600}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"
                    else:
                        duration = f"{secs // 60}:{secs % 60:02d}"
                except (ValueError, TypeError):
                    pass
            self._table.setItem(i, 3, QTableWidgetItem(duration or "--"))

        layout.addWidget(self._table)

        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        select_all_btn = QPushButton("全选")
        select_all_btn.setMinimumHeight(32)
        select_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        select_all_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08); color: #e8e8ed; }"
            "QPushButton:hover { background: rgba(255,255,255,0.14); }"
        )
        select_all_btn.clicked.connect(self._select_all)
        btn_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("全不选")
        deselect_all_btn.setMinimumHeight(32)
        deselect_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        deselect_all_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08); color: #e8e8ed; }"
            "QPushButton:hover { background: rgba(255,255,255,0.14); }"
        )
        deselect_all_btn.clicked.connect(self._deselect_all)
        btn_layout.addWidget(deselect_all_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumHeight(36)
        cancel_btn.setMinimumWidth(80)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08); color: #e8e8ed; }"
            "QPushButton:hover { background: rgba(255,255,255,0.14); }"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        download_btn = QPushButton("下载选中")
        download_btn.setMinimumHeight(36)
        download_btn.setMinimumWidth(100)
        download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        download_btn.clicked.connect(self._accept_selected)
        btn_layout.addWidget(download_btn)

        layout.addLayout(btn_layout)

    def _select_all(self):
        for i in range(self._table.rowCount()):
            self._table.item(i, 0).setCheckState(Qt.CheckState.Checked)

    def _deselect_all(self):
        for i in range(self._table.rowCount()):
            self._table.item(i, 0).setCheckState(Qt.CheckState.Unchecked)

    def _accept_selected(self):
        self._selected = []
        for i in range(self._table.rowCount()):
            if self._table.item(i, 0).checkState() == Qt.CheckState.Checked:
                self._selected.append(self._videos[i])
        if self._selected:
            self.accept()
        else:
            self.reject()

    @property
    def selected_videos(self) -> list[VideoInfo]:
        return self._selected
