# SPDX-License-Identifier: AGPL-3.0-or-later
"""D8 Command Palette — VS Code 스타일 명령 검색 UI.

[wireframes_v2.md §5](../docs/wireframes_v2.md#5-command-palette-ctrlk-d8-신규).

호스트 윈도우의 Ctrl+K 로 호출. items 리스트를 받아 표시 + fuzzy 검색.

interaction:
- 입력창에 타이핑 → 실시간 fuzzy 필터 (substring match, PoC)
- ↑↓: 항목 이동
- Enter: 선택 항목의 callback 실행 + 닫기
- Esc: 닫기
- 마우스 클릭: 항목 선택 + 실행

PoC 단순화 (후속 확장 후보):
- 정규 fuzzy ranking 알고리즘 (현재는 substring contains)
- prefix `>` (명령) / `@` (세션) 카테고리 필터 — 현재는 group 필드로만 분류
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
)

# 디자인 토큰 (main_window_v2.py 와 일관)
_COLORS = {
    "bg_base": "#1e1e2e",
    "bg_surface": "#181825",
    "bg_overlay": "#313244",
    "text_base": "#cdd6f4",
    "text_muted": "#6c7086",
    "primary": "#89b4fa",
    "info": "#cba6f7",
}


class CommandPalette(QDialog):
    """Ctrl+K 명령 팔레트.

    Args:
        items: [{label, group, shortcut?, callback}] 리스트.
            group: "명령" / "세션" / "AI 엔진" 등 카테고리 라벨.
            shortcut: 표시용 단축키 (옵션).
            callback: 선택 시 실행할 함수.
    """

    def __init__(self, items: list[dict], parent=None) -> None:
        super().__init__(parent)
        self._items = items
        self._filtered: list[dict] = list(items)

        # 모달 + 무프레임 floating
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setFixedWidth(520)
        self.setMaximumHeight(420)

        # 컨테이너 frame (보더 + 라운딩)
        self.setStyleSheet(f"""
            CommandPalette {{
                background-color: {_COLORS["bg_surface"]};
                border: 1px solid {_COLORS["bg_overlay"]};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 검색 입력
        search_row = QHBoxLayout()
        search_icon = QLabel("🔍")
        search_icon.setStyleSheet(f"color: {_COLORS['text_muted']}; border: none; font-size: 14px;")
        search_row.addWidget(search_icon)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("세션 또는 명령 검색...")
        self.search_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: transparent;
                color: {_COLORS["text_base"]};
                border: none;
                font-size: 14px;
                padding: 4px 0;
            }}
        """)
        self.search_edit.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_edit, stretch=1)
        layout.addLayout(search_row)

        # 구분선
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {_COLORS['bg_overlay']};")
        layout.addWidget(sep)

        # 결과 리스트
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                color: {_COLORS["text_base"]};
                border: none;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {_COLORS["bg_overlay"]};
                color: {_COLORS["primary"]};
            }}
        """)
        self.list_widget.itemActivated.connect(self._execute_current)
        self.list_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.list_widget, stretch=1)

        # 하단 도움말
        help_label = QLabel("↑↓ 이동   Enter 실행   Esc 닫기")
        help_label.setStyleSheet(f"color: {_COLORS['text_muted']}; border: none; font-size: 10px;")
        help_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(help_label)

        self._render_items()

        # 부모 윈도우 중앙 (상단 1/4 위치 — VS Code 스타일)
        if parent is not None:
            geo = parent.geometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + geo.height() // 4
            self.move(x, y)

    # ── 검색 / 렌더 ───────────────────────────────────────

    def _on_search_changed(self, query: str) -> None:
        q = query.strip().lower()
        if not q:
            self._filtered = list(self._items)
        else:
            self._filtered = [
                it
                for it in self._items
                if q in it.get("label", "").lower() or q in it.get("group", "").lower()
            ]
        self._render_items()

    def _render_items(self) -> None:
        self.list_widget.clear()
        last_group = None
        for it in self._filtered:
            group = it.get("group", "")
            if group and group != last_group:
                # 그룹 헤더 (선택 불가)
                header = QListWidgetItem(group)
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                font = QFont("Malgun Gothic", 9, QFont.Weight.Bold)
                header.setFont(font)
                header.setForeground(_qcolor(_COLORS["text_muted"]))
                self.list_widget.addItem(header)
                last_group = group

            label = it.get("label", "")
            shortcut = it.get("shortcut", "")
            display = f"  {label}"
            if shortcut:
                display = f"  {label}    {shortcut}"
            qi = QListWidgetItem(display)
            qi.setData(Qt.ItemDataRole.UserRole, it)
            self.list_widget.addItem(qi)

        # 첫 선택 가능 항목 자동 선택
        for i in range(self.list_widget.count()):
            qi = self.list_widget.item(i)
            if qi.flags() & Qt.ItemFlag.ItemIsSelectable:
                self.list_widget.setCurrentRow(i)
                break

    # ── 키 이벤트 ──────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt naming)
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
            return
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            self._move_selection(1 if key == Qt.Key.Key_Down else -1)
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._execute_current()
            return
        super().keyPressEvent(event)

    def _move_selection(self, direction: int) -> None:
        count = self.list_widget.count()
        if count == 0:
            return
        current = self.list_widget.currentRow()
        # 선택 가능한 항목만 순회
        for _ in range(count):
            current = (current + direction) % count
            qi = self.list_widget.item(current)
            if qi and (qi.flags() & Qt.ItemFlag.ItemIsSelectable):
                self.list_widget.setCurrentRow(current)
                return

    def _execute_current(self, *_args) -> None:
        qi = self.list_widget.currentItem()
        if qi is None:
            return
        if not (qi.flags() & Qt.ItemFlag.ItemIsSelectable):
            return
        item_data = qi.data(Qt.ItemDataRole.UserRole)
        if not isinstance(item_data, dict):
            return
        callback: Optional[Callable] = item_data.get("callback")
        # 닫고 실행 (callback 안에서 dialog 띄우는 경우 충돌 회피)
        self.close()
        if callable(callback):
            try:
                callback()
            except Exception:  # noqa: BLE001 — palette 는 안전 무시
                pass


def _qcolor(hex_str: str):
    """헬퍼 — QColor lazy import (모듈 top-level QtGui import 가벼움)."""
    from PySide6.QtGui import QColor

    return QColor(hex_str)
