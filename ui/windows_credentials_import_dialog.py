# SPDX-License-Identifier: AGPL-3.0-or-later
"""Windows 자격 증명 관리자 → ohdo vault import 다이얼로그.

[ADR 0003](../docs/saas/decisions/0003-secrets-handling.md) Phase 2-c PR-8.

UX 흐름:
  1. Settings → 🔒 시크릿 탭에서 "📥 Windows 자격 증명에서 가져오기" 클릭
  2. 본 다이얼로그 — 일반 자격 증명 (CRED_TYPE_GENERIC) 목록 표시
  3. 사용자가 행 선택 + label 편집 → "가져오기" 클릭
  4. ``windows_credentials.read_credential`` 로 평문 read → ``vault.set`` → 표 갱신
  5. 원본 Credential Manager 항목은 그대로 (read-only import).
"""

from __future__ import annotations

import logging

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
from core.windows_credentials import (
    WindowsCredentialMeta,
    list_credentials,
    read_credential,
)

logger = logging.getLogger(__name__)

__all__ = ["WindowsCredentialsImportDialog"]


class WindowsCredentialsImportDialog(QDialog):
    """Windows 자격 증명 관리자 일반 자격 증명을 ohdo vault 로 import."""

    def __init__(self, secrets_vault: SecretsVault, parent=None) -> None:
        super().__init__(parent)
        self._vault = secrets_vault
        self._all_creds: list[WindowsCredentialMeta] = []

        self.setWindowTitle(tr("ui_v2.settings.secrets.import_dialog_title"))
        self.setModal(True)
        self.resize(700, 480)

        self._build_ui()
        self._reload_credentials()

    # ── UI ──

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        desc = QLabel(tr("ui_v2.settings.secrets.import_dialog_description"))
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #a6adc8;")
        layout.addWidget(desc)

        # 필터
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(tr("ui_v2.settings.secrets.import_filter_placeholder"))
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self.filter_edit)

        # 표 — Target / User / Label / [Import] 버튼은 별도 우측 panel
        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(
            [
                tr("ui_v2.settings.secrets.import_col_target"),
                tr("ui_v2.settings.secrets.import_col_user"),
                tr("ui_v2.settings.secrets.import_col_label"),
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        # Label 컬럼만 편집 가능
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.SelectedClicked | QTableWidget.EditTrigger.DoubleClicked
        )
        layout.addWidget(self.table)

        # 빈 상태 라벨
        self.empty_label = QLabel(tr("ui_v2.settings.secrets.import_empty"))
        self.empty_label.setStyleSheet("color: #a6adc8; padding: 12px;")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

        # 버튼
        btn_row = QHBoxLayout()
        self.btn_import = QPushButton(tr("ui_v2.settings.secrets.import_btn"))
        self.btn_import.clicked.connect(self._on_import_clicked)
        btn_row.addWidget(self.btn_import)
        btn_row.addStretch(1)
        btn_close = QPushButton(tr("common.cancel"))
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _reload_credentials(self) -> None:
        """Credential Manager 에서 일반 자격 증명 재조회 + 표 갱신."""
        self._all_creds = list_credentials()
        self._populate_table(self._all_creds)

    def _populate_table(self, creds: list[WindowsCredentialMeta]) -> None:
        self.table.setRowCount(len(creds))
        for row, c in enumerate(creds):
            target_item = QTableWidgetItem(c.target_name)
            target_item.setFlags(target_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            target_item.setData(Qt.ItemDataRole.UserRole, c)
            self.table.setItem(row, 0, target_item)

            user_item = QTableWidgetItem(c.user_name or "")
            user_item.setFlags(user_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, user_item)

            label_item = QTableWidgetItem(c.suggested_label())
            self.table.setItem(row, 2, label_item)

        is_empty = len(creds) == 0
        self.empty_label.setVisible(is_empty)
        self.table.setVisible(not is_empty)
        self.btn_import.setEnabled(not is_empty)

    # ── 핸들러 ──

    def _on_filter_changed(self, text: str) -> None:
        q = (text or "").strip().lower()
        if not q:
            self._populate_table(self._all_creds)
            return
        filtered = [
            c
            for c in self._all_creds
            if q in c.target_name.lower() or (c.user_name or "").lower().find(q) >= 0
        ]
        self._populate_table(filtered)

    def _on_import_clicked(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(
                self,
                tr("ui_v2.settings.secrets.import_dialog_title"),
                tr("ui_v2.settings.secrets.import_empty"),
            )
            return
        row = rows[0].row()
        target_item = self.table.item(row, 0)
        label_item = self.table.item(row, 2)
        if target_item is None or label_item is None:
            return
        cred: WindowsCredentialMeta = target_item.data(Qt.ItemDataRole.UserRole)
        label_text = (label_item.text() or "").strip()
        if not label_text:
            label_text = cred.suggested_label()

        # SecretLabel 검증
        try:
            sec_label = SecretLabel(label=label_text, namespace="secret")
        except ValueError as exc:
            QMessageBox.warning(
                self,
                tr("ui_v2.settings.secrets.import_dialog_title"),
                str(exc),
            )
            return

        # 평문 read — 사용자 import 확정 시점에만 메모리에 노출.
        value = read_credential(cred.target_name)
        if value is None or value == "":
            QMessageBox.warning(
                self,
                tr("ui_v2.settings.secrets.import_dialog_title"),
                tr("ui_v2.settings.secrets.import_failed").format(
                    target=cred.target_name, reason="empty/access-denied"
                ),
            )
            return

        try:
            self._vault.set(sec_label, value)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                tr("ui_v2.settings.secrets.import_dialog_title"),
                tr("ui_v2.settings.secrets.import_failed").format(
                    target=cred.target_name, reason=str(exc)
                ),
            )
            return

        QMessageBox.information(
            self,
            tr("ui_v2.settings.secrets.import_dialog_title"),
            tr("ui_v2.settings.secrets.import_done").format(
                label=label_text, target=cred.target_name
            ),
        )
        # 같은 다이얼로그에서 여러 항목 import 가능 — 닫지 않음
