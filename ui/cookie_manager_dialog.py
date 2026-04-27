from collections import defaultdict

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from core.cookie_manager import CookieManager


_COLUMNS = ["域名", "名称", "值", "路径", "过期时间", "Secure", "HttpOnly"]
_MASK = "••••••"


class CookieManagerDialog(QDialog):
    def __init__(self, cookie_manager: CookieManager, parent=None):
        super().__init__(parent)
        self._cm = cookie_manager
        self._revealed: set[int] = set()  # ids of items with value revealed
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        self.setWindowTitle("Cookie 管理")
        self.setMinimumSize(800, 500)
        self.setStyleSheet("""
            QDialog { background: #2d2640; }
            QTreeWidget {
                background: #241f38;
                color: #e8e8ed;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 6px;
                font-size: 12px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 4px 2px;
                border-bottom: 1px solid rgba(255,255,255,0.04);
            }
            QTreeWidget::item:hover { background: rgba(139,92,246,0.1); }
            QTreeWidget::item:selected { background: rgba(139,92,246,0.25); }
            QHeaderView::section {
                background: #1e1a2e;
                color: #c4b5fd;
                padding: 6px;
                border: none;
                border-bottom: 1px solid rgba(255,255,255,0.08);
                font-weight: 600;
                font-size: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.setFixedSize(64, 28)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setStyleSheet("""
            QPushButton {
                background: rgba(139,92,246,0.2);
                color: #c4b5fd;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background: rgba(139,92,246,0.35); }
        """)
        self._refresh_btn.clicked.connect(self._populate)
        toolbar.addWidget(self._refresh_btn)

        toolbar.addStretch()

        self._clear_btn = QPushButton("清除全部")
        self._clear_btn.setFixedSize(80, 28)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setStyleSheet("""
            QPushButton {
                background: rgba(239,68,68,0.2);
                color: #fca5a5;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background: rgba(239,68,68,0.35); }
        """)
        self._clear_btn.clicked.connect(self._on_clear_all)
        toolbar.addWidget(self._clear_btn)

        layout.addLayout(toolbar)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setColumnCount(len(_COLUMNS))
        self._tree.setHeaderLabels(_COLUMNS)
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(False)
        self._tree.setAnimated(True)
        self._tree.setIndentation(20)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self._tree)

    def _populate(self):
        self._tree.clear()
        self._revealed.clear()

        # Group cookies by domain
        by_domain: dict[str, list] = defaultdict(list)
        for c in self._cm.all_cookies():
            domain = c.domain() or "(无域名)"
            by_domain[domain].append(c)

        for domain in sorted(by_domain.keys()):
            cookies = by_domain[domain]
            domain_item = QTreeWidgetItem([domain, "", "", "", "", "", ""])
            domain_item.setData(0, Qt.ItemDataRole.FontRole, self._bold_font())
            domain_item.setFlags(domain_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._tree.addTopLevelItem(domain_item)

            for c in cookies:
                name = bytes(c.name()).decode("utf-8", errors="replace")
                value = bytes(c.value()).decode("utf-8", errors="replace")
                path = c.path() or "/"
                expiry_dt = c.expirationDate()
                expiry = expiry_dt.toString("yyyy-MM-dd HH:mm:ss") if expiry_dt and expiry_dt.isValid() else "会话"
                secure = "✓" if c.isSecure() else ""
                httponly = "✓" if c.isHttpOnly() else ""

                child = QTreeWidgetItem([
                    "",
                    name,
                    _MASK,
                    path,
                    expiry,
                    secure,
                    httponly,
                ])
                child.setData(2, Qt.ItemDataRole.UserRole, value)  # store real value
                child.setToolTip(2, "双击显示值")
                domain_item.addChild(child)

            domain_item.setExpanded(True)

    def _on_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if not item:
            return

        # Find the top-level domain item
        domain_item = item
        while domain_item.parent():
            domain_item = domain_item.parent()

        domain = domain_item.text(0)
        if not domain:
            return

        menu = self._tree.createStandardContextMenu()
        menu.clear()

        delete_domain_action = QAction(f"删除 {domain} 的 Cookie", self)
        delete_domain_action.triggered.connect(lambda: self._on_delete_domain(domain))
        menu.addAction(delete_domain_action)

        menu.addSeparator()

        delete_all_action = QAction("清除所有 Cookie", self)
        delete_all_action.triggered.connect(self._on_clear_all)
        menu.addAction(delete_all_action)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _on_item_double_clicked(self, item, column):
        if column == 2 and not item.parent():
            return  # domain row, ignore
        if column == 2:
            value = item.data(2, Qt.ItemDataRole.UserRole)
            if value:
                item_id = id(item)
                if item_id in self._revealed:
                    item.setText(2, _MASK)
                    self._revealed.discard(item_id)
                else:
                    item.setText(2, value)
                    self._revealed.add(item_id)

    def _on_delete_domain(self, domain: str):
        self._cm.remove_domain(domain)
        self._populate()

    def _on_clear_all(self):
        reply = QMessageBox.question(
            self,
            "清除所有 Cookie",
            "确定要清除所有 Cookie 吗？\n此操作会使您退出已登录的网站。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._cm.clear_all()
            self._populate()

    @staticmethod
    def _bold_font():
        font = QFont()
        font.setBold(True)
        return font
