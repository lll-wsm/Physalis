"""Dialog for testing and saving per-domain title extraction rules."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.title_rules import TitleRuleManager, _domain_from_url, _build_test_js

_DIALOG_STYLE = """
QDialog {
    background-color: #2d2640;
    color: #e8e8ed;
}
QLabel {
    color: #e8e8ed;
    background: transparent;
}
QLineEdit, QComboBox, QSpinBox {
    background-color: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 6px;
    padding: 5px 8px;
    color: #e8e8ed;
    font-size: 13px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: rgba(139,92,246,0.5);
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background-color: #1a1a1e;
    color: #e8e8ed;
    selection-background-color: rgba(139,92,246,0.2);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 6px;
}
QPushButton {
    background-color: #8b5cf6;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton:hover { background-color: #7c3aed; }
QPushButton:disabled { background-color: rgba(139,92,246,0.3); color: rgba(255,255,255,0.4); }
QPushButton.secondary {
    background-color: rgba(255,255,255,0.08);
    color: #e8e8ed;
}
QPushButton.secondary:hover { background-color: rgba(255,255,255,0.14); }
QPushButton.danger {
    background-color: rgba(239,68,68,0.15);
    color: #fca5a5;
}
QPushButton.danger:hover { background-color: rgba(239,68,68,0.25); }
QScrollArea { background: transparent; border: none; }
"""

_SELECTOR_LABELS = {
    "dom": "CSS 选择器",
    "meta": "Meta 属性名",
    "jsonld": "JSON-LD 字段名",
    "url_path": "URL 路径",
    "document_title": "页面标题",
}

_SELECTOR_DISPLAY = {
    "dom": lambda s: f'document.querySelector("{s.get("selector","")}")',
    "meta": lambda s: f'meta[{s.get("property","") and f"property={s[property]}" or f"name={s[name]}"}]',
    "jsonld": lambda s: f"JSON-LD → {s.get('path','name')}",
    "url_path": lambda _: "URL 最后一段路径",
    "document_title": lambda _: "document.title",
}


def _format_selector_desc(sel: dict) -> str:
    stype = sel.get("type", "")
    if stype == "dom":
        return f"DOM: {sel.get('selector', '')}"
    elif stype == "meta":
        prop = sel.get("property", "") or sel.get("name", "")
        return f"meta[{prop}]"
    elif stype == "jsonld":
        return f"JSON-LD: {sel.get('path', 'name')}"
    elif stype == "url_path":
        return "URL 路径"
    elif stype == "document_title":
        return "页面标题"
    return stype


class _SelectorRow(QWidget):
    """A single row showing a selector with Test/Remove buttons."""

    def __init__(self, selector: dict, index: int, parent_dialog, parent=None):
        super().__init__(parent)
        self._selector = selector
        self._index = index
        self._dialog = parent_dialog
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        label = QLabel(f"{self._index + 1}. {_format_selector_desc(self._selector)}")
        label.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.7); padding: 0 4px;")
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(label)

        test_btn = QPushButton("测试")
        test_btn.setFixedSize(48, 24)
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.setProperty("class", "secondary")
        test_btn.setStyleSheet("background: rgba(255,255,255,0.08); color: #e8e8ed; border: none; border-radius: 4px; font-size: 11px;")
        test_btn.clicked.connect(self._on_test)
        layout.addWidget(test_btn)

        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet("background: transparent; color: rgba(255,255,255,0.3); border: none; border-radius: 4px; font-size: 14px;")
        remove_btn.clicked.connect(self._on_remove)
        layout.addWidget(remove_btn)

    def _on_test(self):
        self._dialog._run_single_test(self._selector)

    def _on_remove(self):
        self._dialog._remove_selector(self._index)


class TitleRuleDialog(QDialog):
    """Dialog to test and save title extraction rules for the current domain."""

    def __init__(self, page, current_url: str, manager: TitleRuleManager, parent=None):
        super().__init__(parent)
        self._page = page
        self._current_url = current_url
        self._domain = _domain_from_url(current_url) or "unknown"
        self._manager = manager
        self._selector_rows: list[_SelectorRow] = []
        self._setup_ui()
        self._load_current_rules()

    def _setup_ui(self):
        self.setWindowTitle("标题提取规则")
        self.setMinimumSize(520, 480)
        self.setStyleSheet(_DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # --- Header ---
        header = QLabel("标题提取规则")
        header.setStyleSheet("font-size: 17px; font-weight: 700; color: #ffffff;")
        layout.addWidget(header)

        # Domain info
        domain_row = QHBoxLayout()
        self._domain_label = QLabel(f"网站: {self._domain}")
        self._domain_label.setStyleSheet("font-size: 13px; color: #c4b5fd; font-weight: 600;")
        domain_row.addWidget(self._domain_label)
        domain_row.addStretch()

        self._rule_status = QLabel()
        self._rule_status.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.4);")
        domain_row.addWidget(self._rule_status)
        layout.addLayout(domain_row)

        # Min length
        min_row = QHBoxLayout()
        min_row.addWidget(QLabel("最少字符数:"))
        self._min_length_spin = QSpinBox()
        self._min_length_spin.setRange(1, 20)
        self._min_length_spin.setValue(4)
        self._min_length_spin.setFixedWidth(60)
        self._min_length_spin.valueChanged.connect(self._on_min_length_changed)
        min_row.addWidget(self._min_length_spin)
        min_row.addStretch()
        layout.addLayout(min_row)

        # --- Existing selectors ---
        layout.addWidget(QLabel("当前规则 (按顺序尝试):"))
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setMaximumHeight(180)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; }")

        self._selector_container = QWidget()
        self._selector_container.setStyleSheet("background: transparent;")
        self._selector_list_layout = QVBoxLayout(self._selector_container)
        self._selector_list_layout.setContentsMargins(8, 6, 8, 6)
        self._selector_list_layout.setSpacing(2)
        self._selector_list_layout.addStretch()

        self._scroll.setWidget(self._selector_container)
        layout.addWidget(self._scroll)

        # --- Separator ---
        sep = QLabel("─── 添加新选择器 ───")
        sep.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.25); padding: 4px 0;")
        layout.addWidget(sep)

        # --- New selector form ---
        form_row = QHBoxLayout()
        form_row.setSpacing(8)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["dom", "meta", "jsonld", "url_path", "document_title"])
        self._type_combo.setFixedWidth(100)
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        form_row.addWidget(self._type_combo)

        self._value_input = QLineEdit()
        self._value_input.setPlaceholderText("输入 CSS 选择器...")
        self._value_input.returnPressed.connect(self._on_test_clicked)
        form_row.addWidget(self._value_input, 1)

        layout.addLayout(form_row)

        # Test button + result
        test_row = QHBoxLayout()
        self._test_btn = QPushButton("测试")
        self._test_btn.setFixedSize(60, 30)
        self._test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._test_btn.clicked.connect(self._on_test_clicked)
        test_row.addWidget(self._test_btn)

        self._result_label = QLabel("")
        self._result_label.setStyleSheet("font-size: 13px; color: rgba(255,255,255,0.5); padding: 0 8px;")
        self._result_label.setWordWrap(True)
        test_row.addWidget(self._result_label, 1)
        layout.addLayout(test_row)

        # --- Action buttons ---
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._save_btn = QPushButton("↓ 保存此规则")
        self._save_btn.setFixedHeight(30)
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)

        btn_row.addStretch()

        reset_btn = QPushButton("重置所有为默认")
        reset_btn.setFixedHeight(30)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setProperty("class", "danger")
        reset_btn.setStyleSheet("background: rgba(239,68,68,0.12); color: #fca5a5; border: none; border-radius: 6px; font-size: 12px;")
        reset_btn.clicked.connect(self._on_reset)
        btn_row.addWidget(reset_btn)

        close_btn = QPushButton("关闭")
        close_btn.setFixedHeight(30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setProperty("class", "secondary")
        close_btn.setStyleSheet("background: rgba(255,255,255,0.08); color: #e8e8ed; border: none; border-radius: 6px; font-size: 12px;")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _load_current_rules(self):
        """Populate the selector list from the current domain's rule."""
        # Clear existing rows
        for row in self._selector_rows:
            self._selector_list_layout.removeWidget(row)
            row.deleteLater()
        self._selector_rows.clear()

        # Check if this domain has a custom rule
        rule = self._manager.rule_for_domain(self._domain)
        has_custom = self._domain in self._manager._rules
        if has_custom:
            self._rule_status.setText("使用自定义规则")
            self._rule_status.setStyleSheet("font-size: 11px; color: #34d399;")
        else:
            self._rule_status.setText("使用默认规则")
            self._rule_status.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.4);")

        selectors = rule.get("selectors", [])
        self._min_length_spin.setValue(rule.get("min_length", 4))

        for i, sel in enumerate(selectors):
            row = _SelectorRow(sel, i, self)
            self._selector_rows.append(row)
            self._selector_list_layout.insertWidget(self._selector_list_layout.count() - 1, row)

    def _on_type_changed(self, type_: str):
        """Update the placeholder text based on selector type."""
        placeholders = {
            "dom": "输入 CSS 选择器，如 .dy-title",
            "meta": "输入 meta 属性名，如 og:title",
            "jsonld": "输入 JSON-LD 字段名，如 name",
            "url_path": "无需额外参数",
            "document_title": "无需额外参数",
        }
        self._value_input.setPlaceholderText(placeholders.get(type_, ""))
        self._value_input.setEnabled(type_ not in ("url_path", "document_title"))

    def _on_test_clicked(self):
        """Run the test JS against the current page."""
        type_ = self._type_combo.currentText()
        value = self._value_input.text().strip() if self._value_input.isEnabled() else ""

        js = self._manager.generate_test_js(type_, value)

        self._last_tested_type = type_
        self._last_tested_value = value
        self._result_label.setText("测试中…")
        self._result_label.setStyleSheet("font-size: 13px; color: #fbbf24; padding: 0 8px;")

        self._page.runJavaScript(js, self._on_test_result)

    def _run_single_test(self, selector: dict):
        """Quick-test an existing selector from the list."""
        js = _build_test_js(selector)
        self._result_label.setText(f"测试: {_format_selector_desc(selector)} → …")
        self._result_label.setStyleSheet("font-size: 13px; color: #fbbf24; padding: 0 8px;")

        # Don't set last_tested — we're testing an existing selector, not a new one
        self._page.runJavaScript(js, self._on_single_test_result)

    def _on_test_result(self, result):
        """Callback when test JS finishes."""
        text = str(result or "").strip()
        if text:
            display = text[:60] + ("…" if len(text) > 60 else "")
            self._result_label.setText(f'❝{display}❞')
            self._result_label.setStyleSheet("font-size: 13px; color: #34d399; padding: 0 8px;")
            self._save_btn.setEnabled(True)
        else:
            self._result_label.setText("(空 — 未匹配到内容)")
            self._result_label.setStyleSheet("font-size: 13px; color: rgba(255,255,255,0.4); padding: 0 8px;")
            self._save_btn.setEnabled(False)

    def _on_single_test_result(self, result):
        """Callback when testing an existing selector."""
        text = str(result or "").strip()
        if text:
            display = text[:60] + ("…" if len(text) > 60 else "")
            self._result_label.setText(f'❝{display}❞')
            self._result_label.setStyleSheet("font-size: 13px; color: #34d399; padding: 0 8px;")
        else:
            self._result_label.setText("(空)")
            self._result_label.setStyleSheet("font-size: 13px; color: rgba(255,255,255,0.4); padding: 0 8px;")

    def _on_save(self):
        """Save the last-tested selector to the current domain's rule."""
        if not hasattr(self, '_last_tested_type') or not self._result_label.text():
            return

        if self._last_tested_type in ("url_path", "document_title"):
            selector = {"type": self._last_tested_type}
        elif self._last_tested_type == "meta":
            selector = {"type": "meta", "property": self._last_tested_value}
        elif self._last_tested_type == "jsonld":
            selector = {"type": "jsonld", "path": self._last_tested_value or "name"}
        elif self._last_tested_type == "dom":
            if not self._last_tested_value:
                return
            selector = {"type": "dom", "selector": self._last_tested_value}
        else:
            return

        self._manager.add_selector_to_domain(self._domain, selector)
        self._load_current_rules()
        self._save_btn.setEnabled(False)
        self._result_label.setText("✓ 已保存")
        self._result_label.setStyleSheet("font-size: 13px; color: #34d399; font-weight: 600; padding: 0 8px;")

    def _remove_selector(self, index: int):
        self._manager.remove_selector_from_domain(self._domain, index)
        self._load_current_rules()

    def _on_min_length_changed(self, value: int):
        self._manager.set_min_length(self._domain, value)

    def _on_reset(self):
        reply = QMessageBox.question(
            self,
            "重置规则",
            "确定要恢复所有标题提取规则为默认值吗？\n自定义规则将丢失。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.reset_to_defaults()
            self._load_current_rules()
            self._result_label.setText("✓ 已重置")
            self._result_label.setStyleSheet("font-size: 13px; color: #34d399; padding: 0 8px;")
