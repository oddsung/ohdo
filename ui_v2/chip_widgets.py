# SPDX-License-Identifier: AGPL-3.0-or-later
"""채팅 입력 위 chip 영역 — pending 이미지 / element 표시.

[ADR 0003](../docs/saas/decisions/0003-secrets-handling.md) Phase 2-c PR-10.

PR-10c (2026-05-14): 단순 텍스트 라벨에서 컴포넌트화 — element chip 클릭 시
inline 라벨 편집 가능. 사용자가 chip 의 라벨을 채팅에서 ``{{el:label}}`` placeholder
로 참조함.
"""

from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QStackedWidget,
    QToolButton,
    QWidget,
)

__all__ = [
    "ImageChip",
    "ElementChip",
]


_LABEL_PATTERN = re.compile(r"^[a-z0-9_]{1,32}$")


class _BaseChip(QFrame):
    """공통 chip 외형 (border-radius + padding + 닫기 버튼)."""

    remove_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            """
            _BaseChip, ElementChip, ImageChip {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 10px;
            }
            _BaseChip:hover, ElementChip:hover, ImageChip:hover {
                border-color: #89b4fa;
            }
            QLabel {
                color: #cdd6f4;
                font-size: 11px;
            }
            QToolButton {
                background-color: transparent;
                color: #a6adc8;
                border: none;
                font-size: 11px;
                padding: 0px 2px;
            }
            QToolButton:hover {
                color: #f38ba8;
            }
            QLineEdit {
                background-color: #1e1e2e;
                color: #89b4fa;
                border: 1px solid #89b4fa;
                border-radius: 4px;
                font-size: 11px;
                padding: 1px 4px;
            }
            """
        )
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 2, 4, 2)
        self._layout.setSpacing(4)

    def _add_close_button(self) -> None:
        close_btn = QToolButton(self)
        close_btn.setText("✖")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("제거")
        close_btn.clicked.connect(self.remove_requested.emit)
        self._layout.addWidget(close_btn)


class ImageChip(_BaseChip):
    """이미지 첨부 chip — '📷 N 이미지' 텍스트 + 닫기."""

    def __init__(self, count: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        label = QLabel(f"📷 {count} 이미지", self)
        self._layout.addWidget(label)
        self._add_close_button()


class ElementChip(_BaseChip):
    """Element chip — '📌 label (control_type)' + 클릭하면 라벨 inline 편집.

    Signals:
        label_changed(str, str): (old_label, new_label) — 사용자가 라벨 편집 후 확정.
        remove_requested: 닫기 버튼.
    """

    label_changed = Signal(str, str)

    def __init__(
        self,
        label: str,
        control_type: str,
        name: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._control_type = control_type
        self._name = (name or "")[:20]

        # 라벨 / 편집 stacked widget
        self._stack = QStackedWidget(self)

        self._label_view = QLabel(self._render_label_text(), self._stack)
        self._label_view.setCursor(Qt.CursorShape.IBeamCursor)
        self._label_view.setToolTip("클릭하여 라벨 편집 — 채팅에서 '@<label>' 로 참조")
        self._label_view.mousePressEvent = self._on_label_clicked  # type: ignore[assignment]

        self._label_edit = QLineEdit(self._label, self._stack)
        self._label_edit.setMaxLength(32)
        self._label_edit.setMaximumWidth(120)
        self._label_edit.editingFinished.connect(self._on_edit_finished)
        self._label_edit.returnPressed.connect(self._on_edit_finished)

        self._stack.addWidget(self._label_view)
        self._stack.addWidget(self._label_edit)
        self._stack.setCurrentWidget(self._label_view)
        # 높이 정확히 맞추기 — label view 의 sizeHint 기반
        self._stack.setFixedHeight(self._label_view.sizeHint().height() + 4)

        self._layout.addWidget(self._stack)
        self._add_close_button()

    # ── public ─────────────────────────────────────────

    @property
    def label(self) -> str:
        return self._label

    def set_label(self, new_label: str) -> None:
        """외부에서 라벨 강제 변경 (e.g., 중복 자동 해소). signal 발생 X."""
        new_label = new_label.strip().lower()
        if not _LABEL_PATTERN.match(new_label):
            return
        self._label = new_label
        self._label_view.setText(self._render_label_text())
        self._label_edit.setText(new_label)

    # ── internal ──────────────────────────────────────

    def _render_label_text(self) -> str:
        type_part = f" ({self._control_type})" if self._control_type else ""
        return f"📌 {self._label}{type_part}"

    def _on_label_clicked(self, event) -> None:  # noqa: ARG002
        self._stack.setCurrentWidget(self._label_edit)
        self._label_edit.selectAll()
        self._label_edit.setFocus()

    def _on_edit_finished(self) -> None:
        new_label = self._label_edit.text().strip().lower()
        # editingFinished 가 returnPressed + focus loss 양쪽에서 발생 — 중복 방지
        if self._stack.currentWidget() is self._label_view:
            return

        if not _LABEL_PATTERN.match(new_label):
            # 패턴 위반 — 옛 값으로 복원 + 안내
            self._label_edit.setText(self._label)
            self._stack.setCurrentWidget(self._label_view)
            self._label_edit.setToolTip(
                "라벨 패턴 위반 — 소문자/숫자/_ 로 1~32자 (예: id, pw, search)"
            )
            return

        old_label = self._label
        if new_label != old_label:
            self._label = new_label
            self._label_view.setText(self._render_label_text())
            self.label_changed.emit(old_label, new_label)

        self._stack.setCurrentWidget(self._label_view)
