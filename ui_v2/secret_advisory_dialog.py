# SPDX-License-Identifier: AGPL-3.0-or-later
"""사용자 채팅 입력에서 비밀 정보가 감지됐을 때 띄우는 advisory 모달.

[ADR 0003](../docs/saas/decisions/0003-secrets-handling.md) Phase 2-c (PR-4).

흐름:
  1. ui_v2 `_on_send_message` 가 `secrets_detector.detect()` 호출
  2. matches 발견 시 본 다이얼로그 띄움
  3. 사용자 선택 3 가지:
     a) [🔒 시크릿으로 등록 후 전송] — 각 매치 옆 라벨 편집 후 vault.set + 원문
        span 을 placeholder 로 치환 → 치환된 텍스트로 메시지 전송
     b) [그대로 전송] — 원문 그대로 (사용자 명시 거부 — false-positive 케이스)
     c) [취소] — 메시지 안 보냄

반환: `prepare_outgoing_text()` 정적 helper 가 다이얼로그 → 결과 (str | None) +
       vault 등록 부수효과를 처리. 호출자는 결과만 받아 `_send_request` 호출.
"""

from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.i18n import tr
from core.secrets import SecretLabel, SecretsVault
from core.secrets_detector import SecretMatch, detect_with_elements
from core.secrets_redact import to_placeholder_text

__all__ = [
    "SecretAdvisoryDialog",
    "prepare_outgoing_text",
]


# ─────────────────────────────────────────────────────────
# Dialog 결과 코드
# ─────────────────────────────────────────────────────────


class _Result:
    """다이얼로그 outcome."""

    CANCEL = 0
    """사용자가 메시지 전송 자체를 취소."""
    REGISTERED_AND_SEND = 1
    """vault 등록 + placeholder 치환된 텍스트 전송."""
    SEND_AS_IS = 2
    """원문 그대로 전송 (사용자 명시 거부 — false positive 등)."""


# 라벨 패턴 — core.secrets.SecretLabel 과 일관
_LABEL_PATTERN = re.compile(r"^[a-z0-9_]{1,32}$")


# ─────────────────────────────────────────────────────────
# Dialog
# ─────────────────────────────────────────────────────────


class SecretAdvisoryDialog(QDialog):
    """비밀 정보 감지 advisory 모달.

    호출자 (`prepare_outgoing_text`) 가 vault + matches + text 를 주입.
    사용자 선택에 따라 `outgoing_text` / `outcome` / `registered_labels` 채움.
    """

    def __init__(
        self,
        text: str,
        matches: list[SecretMatch],
        vault: Optional[SecretsVault],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._matches = matches
        self._vault = vault

        # 결과 — 다이얼로그 닫힌 후 호출자가 읽음
        self.outgoing_text: str = text
        self.outcome: int = _Result.CANCEL
        self.registered_labels: list[str] = []

        self.setWindowTitle(tr("ui_v2.secret_advisory.title"))
        self.setModal(True)
        self.setMinimumWidth(600)

        self._build_ui()

    # ── UI ──

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        body = QLabel(tr("ui_v2.secret_advisory.body"))
        body.setWordWrap(True)
        layout.addWidget(body)

        # 매치 테이블 — 종류 / 미리보기 / 사용자 라벨 입력
        self.table = QTableWidget(len(self._matches), 3, self)
        self.table.setHorizontalHeaderLabels(
            [
                tr("ui_v2.secret_advisory.table_header_kind"),
                tr("ui_v2.secret_advisory.table_header_preview"),
                tr("ui_v2.secret_advisory.table_header_label"),
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self._label_edits: list[QLineEdit] = []
        for row, m in enumerate(self._matches):
            kind_key = f"ui_v2.secret_advisory.kind_{m.kind}"
            kind_label = tr(kind_key)
            # tr() 미존재 키는 raw 반환 — fallback 으로 raw kind 표시
            if kind_label == kind_key:
                kind_label = m.kind

            kind_item = QTableWidgetItem(kind_label)
            kind_item.setFlags(kind_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, kind_item)

            preview = m.value if len(m.value) <= 8 else (m.value[:4] + "..." + m.value[-2:])
            preview_item = QTableWidgetItem(preview)
            preview_item.setFlags(preview_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, preview_item)

            edit = QLineEdit(self)
            edit.setText(m.suggested_label)
            edit.setPlaceholderText(tr("ui_v2.secret_advisory.label_placeholder"))
            edit.setMaxLength(32)
            self._label_edits.append(edit)
            self.table.setCellWidget(row, 2, edit)

        # 테이블 높이 — 매치 개수에 비례 (최대 ~6행)
        row_height = self.table.verticalHeader().defaultSectionSize()
        visible_rows = min(max(len(self._matches), 1), 6)
        # header + rows + 약간 padding
        self.table.setMinimumHeight(row_height * (visible_rows + 1) + 8)
        layout.addWidget(self.table)

        # vault 미주입 시 안내
        if self._vault is None:
            warn = QLabel(tr("ui_v2.secret_advisory.error_no_vault"))
            warn.setStyleSheet("color: #f9a826;")
            warn.setWordWrap(True)
            layout.addWidget(warn)

        # 버튼
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_register = QPushButton(tr("ui_v2.secret_advisory.btn_register_and_send"))
        self.btn_register.setEnabled(self._vault is not None)
        self.btn_register.clicked.connect(self._on_register_and_send)
        btn_row.addWidget(self.btn_register)

        self.btn_send_as_is = QPushButton(tr("ui_v2.secret_advisory.btn_send_as_is"))
        self.btn_send_as_is.clicked.connect(self._on_send_as_is)
        btn_row.addWidget(self.btn_send_as_is)

        btn_row.addStretch(1)

        self.btn_cancel = QPushButton(tr("ui_v2.secret_advisory.btn_cancel"))
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.btn_cancel)

        layout.addLayout(btn_row)

    # ── 버튼 핸들러 ──

    def _on_register_and_send(self) -> None:
        if self._vault is None:
            return

        # 라벨 검증 — 모든 입력이 패턴 매치되어야 함
        labels_for_rows: list[str] = []
        for row, edit in enumerate(self._label_edits):
            label = edit.text().strip()
            if not _LABEL_PATTERN.match(label):
                QMessageBox.warning(
                    self,
                    tr("ui_v2.secret_advisory.title"),
                    tr("ui_v2.secret_advisory.error_invalid_label").format(label=label),
                )
                edit.setFocus()
                edit.selectAll()
                return
            labels_for_rows.append(label)

        # 중복 라벨 — 다른 값에 같은 라벨이면 사용자 의도 모호 → 안내
        if len(set(labels_for_rows)) != len(labels_for_rows):
            QMessageBox.warning(
                self,
                tr("ui_v2.secret_advisory.title"),
                tr("ui_v2.secret_advisory.error_invalid_label").format(
                    label=", ".join(labels_for_rows)
                ),
            )
            return

        # vault 등록 + placeholder 치환
        spans_to_labels: list[tuple[tuple[int, int], str]] = []
        for m, label in zip(self._matches, labels_for_rows):
            self._vault.set(SecretLabel(label=label, namespace="secret"), m.value)
            spans_to_labels.append((m.span, label))
            self.registered_labels.append(label)

        # to_placeholder_text 는 overlap span 거부 — detect() 가 이미 overlap 제거함
        self.outgoing_text = to_placeholder_text(self._text, spans_to_labels)
        self.outcome = _Result.REGISTERED_AND_SEND
        self.accept()

    def _on_send_as_is(self) -> None:
        self.outgoing_text = self._text
        self.outcome = _Result.SEND_AS_IS
        self.accept()

    def _on_cancel(self) -> None:
        self.outcome = _Result.CANCEL
        self.reject()


# ─────────────────────────────────────────────────────────
# Public helper — 호출자가 한 함수로 사용
# ─────────────────────────────────────────────────────────


def prepare_outgoing_text(
    raw_text: str,
    vault: Optional[SecretsVault],
    parent=None,
    *,
    elements: Optional[list[dict]] = None,
) -> tuple[Optional[str], list[str]]:
    """원문 → (전송할 텍스트, 새로 등록된 label 목록).

    secrets_detector.detect_with_elements 호출 — text + element_context 결합:
      - text 안 PW-look-alike 값 (PR-5 quoted_literal)
      - element 가 password field (HTML type="password" / UIA Edit + password-hint
        automation_id 등 — PR-7 password_field_element)

    Returns:
        - ``(None, [])`` — 사용자가 취소함. 메시지 안 보냄.
        - ``(text, [])`` — 원문 그대로 전송 (사용자 명시 거부) 또는 detector hit 없음.
        - ``(placeholder_text, [labels])`` — vault 등록 + placeholder 치환된 텍스트 전송.
    """
    if not raw_text:
        return raw_text, []

    matches = detect_with_elements(raw_text, elements=elements)
    # 너무 약한 confidence 는 skip — 채팅 입력 단계는 0.5 이상만 안내
    matches = [m for m in matches if m.confidence >= 0.5]

    if not matches:
        return raw_text, []

    dialog = SecretAdvisoryDialog(raw_text, matches, vault, parent=parent)
    dialog.exec()

    if dialog.outcome == _Result.CANCEL:
        return None, []
    if dialog.outcome == _Result.SEND_AS_IS:
        return dialog.outgoing_text, []
    return dialog.outgoing_text, list(dialog.registered_labels)
