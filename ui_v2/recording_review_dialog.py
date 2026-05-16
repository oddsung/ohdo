# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recording review dialog — 녹화 결과를 commit 전에 사용자가 검토 / 편집.

[ADR 0004 + architecture/25 §"PR-15" + 사용자 추가 §8] R1 의 마지막 사용자
접점. raw RecordingSession 을 보존한 채로 TransformOptions 토글 시 즉시
재변환하며, step 단위로 inline 편집 / drag&drop / bulk action 을 제공한다.

핵심 편집 기능:
- 제목 (user_request) inline 편집 (double-click)
- 대기시간 (wait_after_ms) spinbox
- 코드 (generated_code) 별도 코드 편집 다이얼로그
- drag&drop 으로 step 순서 변경 (QListWidget.InternalMove)
- multi-select bulk action (Shift/Ctrl + click) — bulk_delete / bulk_merge
- 인접 step 합치기 / step 분할
- TransformOptions 4 토글 → 즉시 retransform (raw events 는 보존)
- raw events 디버그 보기 (별도 다이얼로그)

dialog accepted() == True 시 ``edited_steps`` 가 채워져 있고, 호출자가
``AppService.commit_recording`` 으로 세션에 추가한다. reject() 시 빈 리스트.
"""

from __future__ import annotations

import json
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.app_service import Step
from core.i18n import tr
from core.recorder_models import RecordingSession, TransformOptions
from core.recorder_transform import transform

__all__ = ["RecordingReviewDialog"]


# main_window_v2 와 동일 토큰 (circular import 회피 — 직접 정의)
_BG = "#1e1e2e"
_SURFACE = "#181825"
_OVERLAY = "#313244"
_TEXT = "#cdd6f4"
_TEXT_MUTED = "#6c7086"
_PRIMARY = "#89b4fa"
_SUCCESS = "#a6e3a1"
_ERROR = "#f38ba8"


class _StepCardItemWidget(QWidget):
    """리스트의 한 step 카드. 제목 / 대기시간 / 액션 버튼.

    제목 / 대기 / 버튼은 직접 부모 dialog 의 콜백을 호출 — 카드 자체는 모델
    상태를 들고 있지 않음 (dialog 의 edited_steps 가 진실).
    """

    def __init__(self, step_no: int, step: Step, parent_dialog: "RecordingReviewDialog") -> None:
        super().__init__()
        self._dialog = parent_dialog
        self._step_no = step_no
        self._step = step

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)

        title_text = step.user_request or tr(
            "ui_v2.recording.review.step_title_placeholder", n=step_no
        )
        self._title_label = QLabel(f"<b>{step_no}.</b> {title_text}")
        self._title_label.setStyleSheet(f"color: {_TEXT};")
        self._title_label.setWordWrap(True)
        self._title_label.setToolTip(tr("ui_v2.recording.review.steps_header"))
        top.addWidget(self._title_label, stretch=1)

        wait_label = QLabel(tr("ui_v2.recording.review.wait_label"))
        wait_label.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: 11px;")
        top.addWidget(wait_label)

        self._wait_spin = QSpinBox()
        self._wait_spin.setRange(0, 60000)
        self._wait_spin.setSingleStep(100)
        self._wait_spin.setSuffix(" ms")
        self._wait_spin.setValue(int(step.wait_after_ms or 0))
        self._wait_spin.editingFinished.connect(self._on_wait_changed)
        top.addWidget(self._wait_spin)

        outer.addLayout(top)

        # 코드 preview (3줄까지) — 회색 작은 글씨
        preview_lines = (step.generated_code or step.step_code or "").splitlines()[:3]
        preview = "\n".join(preview_lines)
        if preview:
            self._code_preview = QLabel(preview)
            self._code_preview.setStyleSheet(
                f"color: {_TEXT_MUTED}; font-family: Consolas, monospace; "
                f"font-size: 11px; background: {_SURFACE}; padding: 4px; border-radius: 3px;"
            )
            self._code_preview.setWordWrap(True)
            outer.addWidget(self._code_preview)

        # 버튼 row
        btns = QHBoxLayout()
        btns.setSpacing(4)
        for text_key, callback in (
            ("ui_v2.recording.review.btn_edit_code", self._on_edit_code),
            ("ui_v2.recording.review.btn_split", self._on_split),
            ("ui_v2.recording.review.btn_merge_prev", self._on_merge_prev),
            ("ui_v2.recording.review.btn_move_up", lambda: self._on_move(-1)),
            ("ui_v2.recording.review.btn_move_down", lambda: self._on_move(+1)),
            ("ui_v2.recording.review.btn_delete", self._on_delete),
        ):
            btn = QPushButton(tr(text_key))
            btn.setStyleSheet(
                f"background-color: {_OVERLAY}; color: {_TEXT}; "
                f"border: 1px solid {_OVERLAY}; border-radius: 3px; "
                f"padding: 2px 8px; font-size: 11px;"
            )
            btn.clicked.connect(callback)
            btns.addWidget(btn)
        btns.addStretch()
        outer.addLayout(btns)

        # QSS 의 selector 는 widget 의 setObjectName 또는 class name 이어야 함.
        # 카드 자체는 transparent 로 둬서 QListWidget::item 의 hover/selected 색이
        # 깨끗하게 노출되도록.
        self.setStyleSheet("background: transparent;")

    # --- callbacks (delegate to dialog) ---

    def _on_wait_changed(self) -> None:
        self._dialog._on_step_wait_changed(self._step_no, self._wait_spin.value())

    def _on_edit_code(self) -> None:
        self._dialog._on_edit_code(self._step_no)

    def _on_split(self) -> None:
        self._dialog._on_split(self._step_no)

    def _on_merge_prev(self) -> None:
        self._dialog._on_merge_prev(self._step_no)

    def _on_move(self, delta: int) -> None:
        self._dialog._on_move(self._step_no, delta)

    def _on_delete(self) -> None:
        self._dialog._on_delete(self._step_no)


class RecordingReviewDialog(QDialog):
    """녹화 결과 검토 / 편집 dialog.

    Args:
        recording_session: stop_recording 시점의 raw RecordingSession (옵션
            toggle 시 재변환에 사용).
        initial_steps: AppService.stop_recording 가 반환한 첫 변환 결과
            (recording_session 가 None 일 때 fallback — UI 단독 테스트용).
        initial_opts: 초기 TransformOptions. None 이면 default.

    완료 후 ``edited_steps`` 에서 사용자 편집된 Step 리스트를 읽는다.
    cancel 시 빈 리스트.
    """

    # 사용자 추가 §8: 변환 옵션 toggle 즉시 재변환 시 emit
    options_changed = Signal()

    def __init__(
        self,
        recording_session: Optional[RecordingSession] = None,
        initial_steps: Optional[list[Step]] = None,
        initial_opts: Optional[TransformOptions] = None,
        self_window_titles: Optional[list[str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._recording_session = recording_session
        self._self_window_titles = self_window_titles or []
        self._opts = initial_opts or TransformOptions()
        # 변환 결과의 진실 — 사용자 편집이 누적되는 곳.
        self._steps: list[Step] = list(initial_steps or [])
        # cancel/accept 시 호출자가 읽는 결과 — accept 시 _steps 복사.
        self.edited_steps: list[Step] = []

        self.setWindowTitle(tr("ui_v2.recording.review.title"))
        self.resize(900, 700)
        self.setStyleSheet(
            f"""
            QDialog {{ background-color: {_BG}; color: {_TEXT}; }}
            QLabel {{ color: {_TEXT}; }}
            QCheckBox {{ color: {_TEXT}; spacing: 6px; }}
            QPushButton {{
                background-color: {_OVERLAY}; color: {_TEXT};
                border: 1px solid {_OVERLAY}; border-radius: 4px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{ background-color: #45475a; }}
            QListWidget {{
                background-color: {_SURFACE}; color: {_TEXT};
                border: 1px solid {_OVERLAY}; border-radius: 6px;
            }}
            QListWidget::item {{ border-bottom: 1px solid {_OVERLAY}; }}
            QListWidget::item:selected {{ background-color: {_OVERLAY}; }}
            QSpinBox, QPlainTextEdit {{
                background-color: {_SURFACE}; color: {_TEXT};
                border: 1px solid {_OVERLAY}; border-radius: 4px;
                padding: 2px 6px;
            }}
            """
        )

        self._build_ui()
        self._refresh_list()

    # ── UI 빌드 ────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        # 헤더
        raw_count = self._recording_session.event_count if self._recording_session else 0
        self._summary_label = QLabel(
            tr(
                "ui_v2.recording.review.header_summary",
                count=len(self._steps),
                raw=raw_count,
            )
        )
        self._summary_label.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        outer.addWidget(self._summary_label)

        # 변환 옵션 그룹
        opt_frame = QFrame()
        opt_frame.setStyleSheet(
            f"QFrame {{ background-color: {_SURFACE}; border: 1px solid {_OVERLAY}; border-radius: 6px; }}"
        )
        opt_layout = QVBoxLayout(opt_frame)
        opt_layout.setContentsMargins(10, 8, 10, 8)
        opt_layout.setSpacing(4)

        opt_title = QLabel(tr("ui_v2.recording.review.options_group"))
        opt_title.setStyleSheet(f"color: {_TEXT_MUTED}; border: none; font-size: 11px;")
        opt_layout.addWidget(opt_title)

        opt_row = QHBoxLayout()
        opt_row.setSpacing(16)

        # 사용자 추가 §8: 토글 4개. raw events 보존된 채로 즉시 재변환.
        self._chk_group_keys = QCheckBox(tr("ui_v2.recording.review.opt_group_keys"))
        self._chk_group_keys.setChecked(self._opts.group_consecutive_keys)
        self._chk_group_keys.toggled.connect(self._on_option_toggled)
        opt_row.addWidget(self._chk_group_keys)

        self._chk_drop_empty = QCheckBox(tr("ui_v2.recording.review.opt_drop_empty"))
        self._chk_drop_empty.setChecked(self._opts.drop_empty_space_clicks)
        self._chk_drop_empty.toggled.connect(self._on_option_toggled)
        opt_row.addWidget(self._chk_drop_empty)

        self._chk_window_focus = QCheckBox(tr("ui_v2.recording.review.opt_window_focus"))
        self._chk_window_focus.setChecked(self._opts.auto_window_focus_boundary)
        self._chk_window_focus.toggled.connect(self._on_option_toggled)
        opt_row.addWidget(self._chk_window_focus)

        self._chk_secrets = QCheckBox(tr("ui_v2.recording.review.opt_secrets"))
        self._chk_secrets.setChecked(self._opts.integrate_secrets)
        self._chk_secrets.toggled.connect(self._on_option_toggled)
        opt_row.addWidget(self._chk_secrets)

        opt_row.addStretch()
        opt_layout.addLayout(opt_row)
        outer.addWidget(opt_frame)

        # 단계 헤더
        steps_header = QLabel(tr("ui_v2.recording.review.steps_header"))
        steps_header.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: 11px;")
        outer.addWidget(steps_header)

        # 단계 리스트 — drag&drop reorder + multi-select bulk
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.model().rowsMoved.connect(self._on_rows_moved)
        outer.addWidget(self._list, stretch=1)

        # 하단 — raw events + commit + cancel
        bottom = QHBoxLayout()
        self._raw_btn = QPushButton(tr("ui_v2.recording.review.btn_raw_events"))
        self._raw_btn.clicked.connect(self._on_view_raw_events)
        bottom.addWidget(self._raw_btn)
        bottom.addStretch()

        buttons = QDialogButtonBox()
        commit_btn = buttons.addButton(
            tr("ui_v2.recording.review.btn_commit"),
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        commit_btn.setStyleSheet(f"background-color: {_SUCCESS}; color: {_BG}; font-weight: bold;")
        cancel_btn = buttons.addButton(
            tr("ui_v2.recording.review.btn_cancel"),
            QDialogButtonBox.ButtonRole.RejectRole,
        )
        cancel_btn.setStyleSheet(f"background-color: {_OVERLAY}; color: {_TEXT};")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        bottom.addWidget(buttons)
        outer.addLayout(bottom)

    # ── List rendering ───────────────────────────────────────

    def _refresh_list(self) -> None:
        # rowsMoved 가 _refresh_list 재진입 호출하는 것을 막기 위해
        # 재진입 가드 (drag/drop 중에는 _refresh 호출 X — 외부 변경만 갱신).
        self._list.blockSignals(True)
        try:
            self._list.clear()
            for i, step in enumerate(self._steps, start=1):
                item = QListWidgetItem()
                # 드래그 후에도 어떤 step 이었는지 추적 — UserRole 에 step id (메모리 주소)
                item.setData(Qt.ItemDataRole.UserRole, id(step))
                widget = _StepCardItemWidget(step_no=i, step=step, parent_dialog=self)
                # 카드의 정확한 높이를 sizeHint 로 전달
                item.setSizeHint(widget.sizeHint())
                self._list.addItem(item)
                self._list.setItemWidget(item, widget)

            if not self._steps:
                empty = QListWidgetItem(tr("ui_v2.recording.review.empty_steps"))
                empty.setFlags(Qt.ItemFlag.NoItemFlags)
                self._list.addItem(empty)
        finally:
            self._list.blockSignals(False)

        raw_count = self._recording_session.event_count if self._recording_session else 0
        self._summary_label.setText(
            tr(
                "ui_v2.recording.review.header_summary",
                count=len(self._steps),
                raw=raw_count,
            )
        )

    # ── 변환 옵션 toggle ──────────────────────────────────────

    def _on_option_toggled(self) -> None:
        """사용자 추가 §8: 옵션 toggle → 즉시 재변환.

        recording_session 이 있으면 raw events 로 다시 transform; 없으면
        그냥 옵션만 갱신 (테스트용 — initial_steps 만 주입한 경우).
        """
        self._opts = TransformOptions(
            auto_window_focus_boundary=self._chk_window_focus.isChecked(),
            enable_f8_marker=self._opts.enable_f8_marker,
            drop_self_window_clicks=self._opts.drop_self_window_clicks,
            drop_empty_space_clicks=self._chk_drop_empty.isChecked(),
            group_consecutive_keys=self._chk_group_keys.isChecked(),
            group_key_idle_ms=self._opts.group_key_idle_ms,
            idle_boundary_ms=self._opts.idle_boundary_ms,
            integrate_secrets=self._chk_secrets.isChecked(),
            auto_user_request=self._opts.auto_user_request,
        )
        if self._recording_session is not None:
            self._steps = transform(
                self._recording_session,
                opts=self._opts,
                self_window_titles=self._self_window_titles,
            )
            self._refresh_list()
        self.options_changed.emit()

    # ── Step 편집 콜백 ───────────────────────────────────────

    def _on_step_wait_changed(self, step_no: int, ms: int) -> None:
        idx = step_no - 1
        if not (0 <= idx < len(self._steps)):
            return
        self._steps[idx].wait_after_ms = ms or None

    def _on_edit_code(self, step_no: int) -> None:
        idx = step_no - 1
        if not (0 <= idx < len(self._steps)):
            return
        step = self._steps[idx]
        # 별도 코드 편집 다이얼로그 — 큰 텍스트 영역.
        edit = QDialog(self)
        edit.setWindowTitle(tr("ui_v2.recording.review.code_edit_title", n=step_no))
        edit.resize(800, 500)
        v = QVBoxLayout(edit)
        editor = QPlainTextEdit()
        editor.setPlainText(step.generated_code or step.step_code or "")
        v.addWidget(editor)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(edit.accept)
        bb.rejected.connect(edit.reject)
        v.addWidget(bb)
        if edit.exec() == QDialog.DialogCode.Accepted:
            new_code = editor.toPlainText()
            step.generated_code = new_code
            step.step_code = new_code
            self._refresh_list()

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """사용자 추가 §8: 제목 inline 편집 (QInputDialog 로 간단화)."""
        row = self._list.row(item)
        if not (0 <= row < len(self._steps)):
            return
        step = self._steps[row]
        new_title, ok = QInputDialog.getText(
            self,
            tr("ui_v2.recording.review.steps_header"),
            tr("ui_v2.recording.review.step_title_placeholder", n=row + 1),
            text=step.user_request or "",
        )
        if ok:
            step.user_request = new_title.strip()
            self._refresh_list()

    def _on_split(self, step_no: int) -> None:
        """현재 step 분할 — 코드에 줄이 2개 이상이면 절반으로 나눠 새 step 삽입."""
        idx = step_no - 1
        if not (0 <= idx < len(self._steps)):
            return
        step = self._steps[idx]
        code_lines = (step.generated_code or "").splitlines()
        if len(code_lines) < 2:
            QMessageBox.information(
                self,
                tr("ui_v2.recording.review.btn_split"),
                tr("ui_v2.recording.review.empty_steps"),
            )
            return
        mid = len(code_lines) // 2
        first_code = "\n".join(code_lines[:mid])
        second_code = "\n".join(code_lines[mid:])
        step.generated_code = first_code
        step.step_code = first_code
        new_step = Step(
            step_id=0,
            user_request=step.user_request,
            generated_code=second_code,
            step_code=second_code,
        )
        self._steps.insert(idx + 1, new_step)
        self._renumber_step_ids()
        self._refresh_list()

    def _on_merge_prev(self, step_no: int) -> None:
        idx = step_no - 1
        if idx <= 0 or idx >= len(self._steps):
            return
        prev = self._steps[idx - 1]
        cur = self._steps[idx]
        merged_code = "\n".join(c for c in (prev.generated_code, cur.generated_code) if c)
        prev.generated_code = merged_code
        prev.step_code = merged_code
        if cur.user_request and prev.user_request:
            prev.user_request = f"{prev.user_request} 후 {cur.user_request}"
        elif cur.user_request:
            prev.user_request = cur.user_request
        del self._steps[idx]
        self._renumber_step_ids()
        self._refresh_list()

    def _on_move(self, step_no: int, delta: int) -> None:
        idx = step_no - 1
        new_idx = idx + delta
        if not (0 <= idx < len(self._steps)) or not (0 <= new_idx < len(self._steps)):
            return
        self._steps[idx], self._steps[new_idx] = self._steps[new_idx], self._steps[idx]
        self._renumber_step_ids()
        self._refresh_list()

    def _on_delete(self, step_no: int) -> None:
        idx = step_no - 1
        if not (0 <= idx < len(self._steps)):
            return
        del self._steps[idx]
        self._renumber_step_ids()
        self._refresh_list()

    # ── Drag&drop reorder (사용자 추가 §8) ────────────────────

    def _on_rows_moved(self, *_args) -> None:
        """QListWidget 의 InternalMove drag 끝났을 때 _steps 도 동기화.

        item 의 UserRole 에 저장한 id(step) 로 _steps 를 재배열한다 — widget
        은 drag 후 detach 될 수 있어 신뢰 X.
        """
        id_to_step = {id(s): s for s in self._steps}
        new_order: list[Step] = []
        for i in range(self._list.count()):
            it = self._list.item(i)
            sid = it.data(Qt.ItemDataRole.UserRole)
            if sid in id_to_step:
                new_order.append(id_to_step[sid])
        if new_order and len(new_order) == len(self._steps):
            self._steps = new_order
            self._renumber_step_ids()
            self._refresh_list()

    # ── 우클릭 컨텍스트 (사용자 추가 §8 — bulk action) ────────

    def _on_context_menu(self, pos) -> None:
        selected = self._list.selectedItems()
        if not selected:
            return
        menu = QMenu(self)
        bulk_delete = menu.addAction(tr("ui_v2.recording.review.bulk_delete"))
        bulk_merge = menu.addAction(tr("ui_v2.recording.review.bulk_merge"))
        menu.addSeparator()
        menu.addAction(
            tr("ui_v2.recording.review.context_select_all"),
            self._list.selectAll,
        )
        menu.addAction(
            tr("ui_v2.recording.review.context_clear_selection"),
            self._list.clearSelection,
        )
        action = menu.exec(self._list.mapToGlobal(pos))
        if action is bulk_delete:
            self._bulk_delete(selected)
        elif action is bulk_merge:
            self._bulk_merge(selected)

    def _bulk_delete(self, items: list[QListWidgetItem]) -> None:
        indices = sorted([self._list.row(it) for it in items], reverse=True)
        if not indices:
            return
        confirm = QMessageBox.question(
            self,
            tr("ui_v2.recording.review.bulk_delete"),
            tr("ui_v2.recording.review.confirm_delete", count=len(indices)),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        for idx in indices:
            if 0 <= idx < len(self._steps):
                del self._steps[idx]
        self._renumber_step_ids()
        self._refresh_list()

    def _bulk_merge(self, items: list[QListWidgetItem]) -> None:
        indices = sorted({self._list.row(it) for it in items})
        if len(indices) < 2:
            return
        target_idx = indices[0]
        if not (0 <= target_idx < len(self._steps)):
            return
        target = self._steps[target_idx]
        code_parts = [target.generated_code or ""]
        req_parts = [target.user_request] if target.user_request else []
        # 뒤쪽 idx 부터 제거하면서 코드 누적 (역순 안 함 — 의미 순서 보존 위해 정순으로 모음)
        merged_codes = []
        merged_reqs = []
        for idx in indices[1:]:
            if 0 <= idx < len(self._steps):
                s = self._steps[idx]
                if s.generated_code:
                    merged_codes.append(s.generated_code)
                if s.user_request:
                    merged_reqs.append(s.user_request)
        new_code = "\n".join(code_parts + merged_codes)
        target.generated_code = new_code
        target.step_code = new_code
        if merged_reqs:
            target.user_request = " 후 ".join(req_parts + merged_reqs)
        # 뒤쪽부터 제거
        for idx in reversed(indices[1:]):
            if 0 <= idx < len(self._steps):
                del self._steps[idx]
        self._renumber_step_ids()
        self._refresh_list()

    # ── Raw events 디버그 보기 (사용자 추가 §8) ───────────────

    def _on_view_raw_events(self) -> None:
        events = self._recording_session.events if self._recording_session is not None else []
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("ui_v2.recording.review.raw_dialog_title", count=len(events)))
        dialog.resize(700, 500)
        v = QVBoxLayout(dialog)
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setFont(QFont("Consolas", 10))
        # event 직렬화 — Pydantic v2 model_dump 결과를 줄별 JSON 으로.
        lines: list[str] = []
        for i, ev in enumerate(events):
            try:
                d = ev.model_dump(mode="json", exclude_none=True)
            except Exception:  # noqa: BLE001
                d = {"_repr": repr(ev)}
            lines.append(f"[{i:04d}] {json.dumps(d, ensure_ascii=False)}")
        viewer.setPlainText("\n".join(lines))
        v.addWidget(viewer)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dialog.reject)
        bb.accepted.connect(dialog.accept)
        v.addWidget(bb)
        dialog.exec()

    # ── Commit (Accept) ──────────────────────────────────────

    def _on_accept(self) -> None:
        # step_id 재할당은 caller (AppService.commit_recording → repo.add_step)
        # 가 책임. 여기서는 list 순서 유지.
        self.edited_steps = list(self._steps)
        self.accept()

    # ── Helper ───────────────────────────────────────────────

    def _renumber_step_ids(self) -> None:
        """drag/split/merge 후 step_id 를 1..N 으로 재할당.

        commit 시 repo.add_step 가 다시 할당하지만, 미리 매겨두면 UI / debug 가
        깔끔.
        """
        for i, s in enumerate(self._steps, start=1):
            s.step_id = i
