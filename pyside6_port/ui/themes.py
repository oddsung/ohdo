# SPDX-License-Identifier: AGPL-3.0-or-later
"""기본 테마 stylesheet 모듈.

원래 ``ui/main_window.py`` 의 ``_get_default_dark_theme`` 메서드 (156줄) 였으나
파일 크기 축소 + 테마 추가 용이성 위해 별 모듈로 추출 (Phase 1.2 Sub-step 4a).

추가 테마는 별 함수로 정의하거나 ``ui/resources/styles/{theme}_theme.qss`` 파일로
배치. ``MainWindow._apply_theme`` 가 settings 의 ``ui.theme`` 키 기반으로 분기.
"""

from __future__ import annotations


def get_default_dark_theme() -> str:
    """기본 다크 테마 stylesheet — Catppuccin Mocha 팔레트 기반."""
    return """
    QMainWindow {
        background-color: #1e1e2e;
        color: #cdd6f4;
    }
    QWidget {
        background-color: #1e1e2e;
        color: #cdd6f4;
        font-family: 'Malgun Gothic', 'Segoe UI', sans-serif;
        font-size: 11px;
    }
    QMenuBar {
        background-color: #181825;
        color: #cdd6f4;
        border-bottom: 1px solid #313244;
    }
    QMenuBar::item:selected {
        background-color: #45475a;
    }
    QMenu {
        background-color: #1e1e2e;
        color: #cdd6f4;
        border: 1px solid #313244;
    }
    QMenu::item:selected {
        background-color: #45475a;
    }
    QToolBar {
        background-color: #181825;
        border-bottom: 1px solid #313244;
        spacing: 5px;
        padding: 3px;
    }
    QSplitter::handle {
        background-color: #313244;
        width: 2px;
        height: 2px;
    }
    QPushButton {
        background-color: #45475a;
        color: #cdd6f4;
        border: 1px solid #585b70;
        border-radius: 4px;
        padding: 6px 16px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #585b70;
    }
    QPushButton:pressed {
        background-color: #6c7086;
    }
    QPushButton:disabled {
        background-color: #313244;
        color: #585b70;
    }
    QLineEdit, QTextEdit, QPlainTextEdit {
        background-color: #313244;
        color: #cdd6f4;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 4px;
        selection-background-color: #585b70;
    }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
        border: 1px solid #89b4fa;
    }
    QComboBox {
        background-color: #313244;
        color: #cdd6f4;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 4px 8px;
    }
    QComboBox::drop-down {
        border: none;
    }
    QComboBox QAbstractItemView {
        background-color: #1e1e2e;
        color: #cdd6f4;
        border: 1px solid #45475a;
        selection-background-color: #45475a;
    }
    QListWidget {
        background-color: #181825;
        color: #cdd6f4;
        border: 1px solid #313244;
        border-radius: 4px;
    }
    QListWidget::item {
        padding: 8px;
        border-bottom: 1px solid #313244;
    }
    QListWidget::item:selected {
        background-color: #45475a;
        color: #cdd6f4;
    }
    QListWidget::item:hover {
        background-color: #313244;
    }
    QTabWidget::pane {
        border: 1px solid #313244;
        background-color: #1e1e2e;
    }
    QTabBar::tab {
        background-color: #181825;
        color: #a6adc8;
        border: 1px solid #313244;
        padding: 6px 16px;
        margin-right: 2px;
    }
    QTabBar::tab:selected {
        background-color: #1e1e2e;
        color: #cdd6f4;
        border-bottom: 2px solid #89b4fa;
    }
    QStatusBar {
        background-color: #181825;
        color: #a6adc8;
        border-top: 1px solid #313244;
    }
    QGroupBox {
        border: 1px solid #313244;
        border-radius: 4px;
        margin-top: 10px;
        padding-top: 10px;
        color: #cdd6f4;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
    }
    QScrollBar:vertical {
        background-color: #181825;
        width: 10px;
        margin: 0;
    }
    QScrollBar::handle:vertical {
        background-color: #45475a;
        border-radius: 5px;
        min-height: 20px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #585b70;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }
    QLabel {
        color: #cdd6f4;
    }
    """
