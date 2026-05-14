# SPDX-License-Identifier: AGPL-3.0-or-later
"""채팅 입력창에서 placeholder (시크릿 + element) 빠른 삽입 UI.

[ADR 0003](../docs/saas/decisions/0003-secrets-handling.md) Phase 2-c PR-9 (PR-10d 확장).

Trigger: 채팅 입력창에 ``@`` 타이핑 → popup 열림. 이어서 prefix 타이핑 시 필터링.
``@`` 가 공백/줄 시작 뒤에서만 trigger (email ``user@host`` false-positive 회피).

PR-10d (2026-05-14): popup 이 두 소스 통합 표시:
  - 🔒 vault 시크릿 (vault.list("secret") + vault.list("apikey"))
  - 📌 사용자가 picker 로 잡은 element (chip 영역에 표시된 element 들의 라벨)

선택 시 namespace 별 placeholder 삽입:
  - 시크릿 → ``{{secret:<label>}}``
  - element → ``{{el:<label>}}``

Esc 는 popup 닫고 ``@`` 그대로 유지 (email 입력 등 fall-through).
"""

from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QWidget,  # parent 타입 hint
)

from core.secrets import SecretsVault

__all__ = ["SecretInsertPopup"]


class SecretInsertPopup(QListWidget):
    """입력창 위에 떠서 시크릿 라벨을 선택할 수 있는 popup.

    독립 top-level Popup window 로 띄움 — 입력창의 z-order 위에 표시되고 ESC /
    포커스 잃음 시 자동 닫힘. parent 는 anchor 용 (위치 계산).
    """

    label_selected = Signal(str)
    """사용자가 라벨 확정 시 emit — argument 는 label 문자열."""

    def __init__(
        self,
        vault: Optional[SecretsVault],
        editor: QPlainTextEdit,
        parent: Optional[QWidget] = None,
        *,
        elements_provider=None,
    ) -> None:
        """
        Args:
            vault: 시크릿 source. None 이면 시크릿 항목 안 보임.
            editor: 메시지 입력창 — placeholder 가 삽입될 대상.
            parent: Qt parent (z-order 용).
            elements_provider: ``callable() -> list[dict]`` — pending elements 반환.
                각 element 의 ``_ohdo_label`` 키를 라벨로 사용. None 이면 element
                항목 안 보임.
        """
        super().__init__(parent)
        self._vault = vault
        self._editor = editor
        self._elements_provider = elements_provider
        # popup 발동 시 anchor — '@' 위치 (그 자리부터 cursor 까지 placeholder 로 치환)
        self._trigger_at: Optional[int] = None

        self.setWindowFlags(Qt.WindowType.Popup)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setUniformItemSizes(True)
        self.setMaximumHeight(180)
        self.setMinimumWidth(220)
        self.setStyleSheet(
            """
            QListWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 2px;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #45475a;
                color: #89b4fa;
            }
            """
        )
        self.itemActivated.connect(self._on_item_activated)
        self.itemDoubleClicked.connect(self._on_item_activated)

    # ── public ──────────────────────────────────────────

    def open_from_at(self, at_position: int, prefix: str = "") -> None:
        """``@`` trigger path — popup 을 caret 근처에 표시 + prefix 필터링.

        삽입 시 ``@<prefix>`` 영역 (at_position 부터 현재 cursor 까지) 을 통째로
        placeholder 로 교체.
        """
        if not self._populate_items(prefix):
            self.hide()
            return
        self._trigger_at = at_position

        # caret 위치 계산
        cursor_rect = self._editor.cursorRect()
        global_pos = self._editor.viewport().mapToGlobal(cursor_rect.bottomLeft())
        self.move(global_pos)
        self.show()
        if self.count() > 0:
            self.setCurrentRow(0)

    def update_filter(self, prefix: str) -> None:
        """``@`` trigger 후 사용자가 prefix 를 더 타이핑할 때 필터 갱신.

        매치 0개면 popup 자동 닫음.
        """
        if not self._populate_items(prefix):
            self.hide()
            return
        if self.count() > 0:
            self.setCurrentRow(0)

    # ── internal ───────────────────────────────────────

    def _populate_items(self, prefix: str) -> bool:
        """vault 시크릿 + pending elements 를 prefix 로 필터링해 항목 채움.

        각 item 의 UserRole 에 ``(kind, label)`` 튜플 저장 — ``kind`` 는
        ``"secret"`` / ``"apikey"`` / ``"el"``. _insert_placeholder 가 이걸로
        분기해 적절한 placeholder 생성.
        """
        self.clear()
        p = (prefix or "").lower()

        # 1) Element chips 먼저 (사용자가 방금 picker 로 잡은 거 — 가까운 작업 컨텍스트)
        if self._elements_provider is not None:
            try:
                elements = self._elements_provider() or []
            except Exception:  # noqa: BLE001
                elements = []
            for elem in elements:
                label = elem.get("_ohdo_label")
                if not isinstance(label, str) or not label:
                    continue
                if p and not label.lower().startswith(p):
                    continue
                ctype = elem.get("control_type", "?")
                item = QListWidgetItem(f"📌  {label}  ({ctype})")
                item.setData(Qt.ItemDataRole.UserRole, ("el", label))
                self.addItem(item)

        # 2) Vault 시크릿 (secret + apikey namespace)
        if self._vault is not None:
            try:
                secrets = list(self._vault.list(namespace="secret"))
                apikeys = list(self._vault.list(namespace="apikey"))
            except Exception:  # noqa: BLE001
                secrets, apikeys = [], []

            for lab in secrets:
                if p and not lab.label.lower().startswith(p):
                    continue
                item = QListWidgetItem(f"🔒  {lab.label}")
                item.setData(Qt.ItemDataRole.UserRole, ("secret", lab.label))
                self.addItem(item)
            for lab in apikeys:
                if p and not lab.label.lower().startswith(p):
                    continue
                item = QListWidgetItem(f"🔑  {lab.label}")
                item.setData(Qt.ItemDataRole.UserRole, ("apikey", lab.label))
                self.addItem(item)

        return self.count() > 0

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple) or len(data) != 2:
            return
        kind, label = data
        if not isinstance(kind, str) or not isinstance(label, str):
            return
        self._insert_placeholder(kind, label)
        self.hide()
        self.label_selected.emit(label)

    def _insert_placeholder(self, kind: str, label: str) -> None:
        """선택된 (kind, label) 을 입력창의 ``@<prefix>`` 영역에 placeholder 로 치환.

        kind 별 placeholder 형식:
          - ``secret`` / ``apikey`` → ``{{secret:label}}`` (둘 다 vault namespace 만 다름)
          - ``el`` → ``{{el:label}}`` (element placeholder)

        ``_trigger_at`` 부터 현재 cursor 까지를 placeholder 로 치환.
        """
        if kind == "el":
            placeholder = "{{el:" + label + "}}"
        else:
            # secret + apikey 모두 {{secret:...}} 사용 — prompt_builder 가 namespace
            # 자동 결정 (vault.get_secret 이 양쪽 다 시도)
            placeholder = "{{secret:" + label + "}}"

        cursor = self._editor.textCursor()
        if self._trigger_at is not None:
            # @<prefix> 영역 선택 후 치환
            anchor = self._trigger_at
            end = cursor.position()
            cursor.setPosition(anchor)
            cursor.setPosition(end, cursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            cursor.insertText(placeholder)
        else:
            cursor.insertText(placeholder)
        self._editor.setTextCursor(cursor)
        self._trigger_at = None

    # ── key handling ───────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab):
            item = self.currentItem()
            if item is not None:
                self._on_item_activated(item)
                event.accept()
                return
        if key == Qt.Key.Key_Escape:
            # popup 닫고 @ 그대로 두기 (사용자가 email 입력 등 fall-through)
            self.hide()
            self._editor.setFocus()
            event.accept()
            return
        super().keyPressEvent(event)


# ─────────────────────────────────────────────────────
# Helper — '@' trigger 조건 + prefix 추출
# ─────────────────────────────────────────────────────

_LABEL_PREFIX_CHARS = re.compile(r"[a-z0-9_]")


def find_at_trigger(text: str, cursor_pos: int) -> Optional[tuple[int, str]]:
    """현재 cursor 가 ``@<prefix>`` 영역 안인지 검사.

    조건:
      - cursor 직전 영역에 ``@`` 가 있음
      - ``@`` 직전 character 가 공백 / 줄 시작 / 빈 영역 (``user@host`` 같은 email
        은 trigger 안 함)
      - ``@`` 부터 cursor 까지 영문/숫자/_ 만 포함 (placeholder label 패턴)

    Returns:
        ``(at_position, prefix)`` 또는 None (trigger 안 함).
    """
    if cursor_pos <= 0 or cursor_pos > len(text):
        return None

    # 뒤에서부터 영문/숫자/_ 만 거쳐 가다 '@' 찾음
    i = cursor_pos - 1
    while i >= 0:
        c = text[i]
        if c == "@":
            # @ 직전이 공백/줄 시작이어야 함
            if i == 0 or text[i - 1] in (" ", "\t", "\n", "\r"):
                prefix = text[i + 1 : cursor_pos]
                return (i, prefix)
            return None
        if not _LABEL_PREFIX_CHARS.match(c.lower()):
            # @ 도 아니고 label 문자도 아니면 trigger 영역 끝
            return None
        i -= 1
    return None
