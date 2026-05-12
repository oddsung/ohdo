# SPDX-License-Identifier: AGPL-3.0-or-later
"""ohdo UI v2 — 메인 윈도우 PoC (단일 파일).

[docs/wireframes_v2.md](../docs/wireframes_v2.md) 의 메인 윈도우 v2 구조 구현.
실제 운영 코드 아님 — design 검증용 PoC. 후속 슬라이스에서 파일 분리.

**원칙**:
- ``core.app_service.AppService`` 만 의존. ``core.session_manager`` 등 직접 import 금지.
- ``ui/`` v1 과 같은 ``data/`` 디렉토리 공유 — 세션 호환.

**구현된 결정**:
- D1: 코드 + 블럭 뷰 통합 (단일 스크롤, 블럭 베이스)
- D3: 요청-코드 step 매칭 (각 카드 안에 사용자 요청 + AI 설명 + 코드)
- D5: 콘솔 토글 (현재는 stub — 상태바 인디케이터만)
- D6: 인라인 요소 칩 (입력창 위 + step 카드 안)
- D7: 단축키 (Ctrl+Enter 전송, F9 중지)
- D11: Initial 블럭 "여기서 실행" 제거 (⏯ 단독 만)
- D19: AI 설명 1~2줄 preview + ▼ 펼침
- D24: Initial 블럭 자동 추출 결과 비어있지 않을 때만 표시

**미구현 (후속 슬라이스)**:
- D4 다중 세션 탭, D8 Command palette, D9 토스트, D10 시스템 테마,
  D14 onboarding, D17 토스트 confirm, D20 사이드바 last state,
  D21 + 탭 메뉴, D22 우클릭 메뉴, D23 drag reorder, D25 빈 상태 일러스트.
"""

from __future__ import annotations

import asyncio
import re
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QMimeData, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QDrag,
    QFont,
    QKeySequence,
    QPixmap,
    QShortcut,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# 절대 import — core.app_service 만 사용 (ADR 0001 + ROADMAP §3 Phase 1 (2) KPI)
# 도메인 타입 (Session, Step, ExecutionKernel) + factory (AppService.create_default 등)
# 모두 app_service 에서 re-export. ai_engine / session_manager / execution_kernel /
# storage 직접 import 금지.
from core.app_service import AppService, ExecutionKernel, Session, Step
from core.i18n import tr

# ── 디자인 토큰 (wireframes_v2.md §8) ────────────────────────────────

COLORS = {
    "bg_base": "#1e1e2e",
    "bg_surface": "#181825",
    "bg_overlay": "#313244",
    "text_base": "#cdd6f4",
    "text_muted": "#6c7086",
    "primary": "#89b4fa",
    "success": "#a6e3a1",
    "warning": "#f9e2af",
    "error": "#f38ba8",
    "info": "#cba6f7",
}

GLOBAL_QSS = f"""
    QMainWindow, QWidget {{
        background-color: {COLORS["bg_base"]};
        color: {COLORS["text_base"]};
        font-family: 'Malgun Gothic', 'Inter', sans-serif;
        font-size: 13px;
    }}
    QPushButton {{
        background-color: {COLORS["bg_overlay"]};
        color: {COLORS["text_base"]};
        border: 1px solid {COLORS["bg_overlay"]};
        border-radius: 4px;
        padding: 4px 10px;
    }}
    QPushButton:hover {{
        background-color: #45475a;
    }}
    QPushButton:disabled {{
        color: {COLORS["text_muted"]};
        background-color: {COLORS["bg_surface"]};
    }}
    QToolButton {{
        background-color: transparent;
        color: {COLORS["text_base"]};
        border: none;
        padding: 4px;
    }}
    QToolButton:hover {{
        background-color: {COLORS["bg_overlay"]};
        border-radius: 4px;
    }}
    QListWidget {{
        background-color: {COLORS["bg_surface"]};
        color: {COLORS["text_base"]};
        border: 1px solid {COLORS["bg_overlay"]};
        border-radius: 6px;
    }}
    QListWidget::item:selected {{
        background-color: {COLORS["bg_overlay"]};
        color: {COLORS["primary"]};
    }}
    QPlainTextEdit {{
        background-color: {COLORS["bg_surface"]};
        color: {COLORS["text_base"]};
        border: 1px solid {COLORS["bg_overlay"]};
        border-radius: 4px;
        font-family: 'Consolas', 'JetBrains Mono', monospace;
    }}
    QComboBox {{
        background-color: {COLORS["bg_overlay"]};
        color: {COLORS["text_base"]};
        border: 1px solid {COLORS["bg_overlay"]};
        border-radius: 4px;
        padding: 3px 8px;
    }}
    QSpinBox {{
        background-color: {COLORS["bg_surface"]};
        color: {COLORS["text_base"]};
        border: 1px solid {COLORS["bg_overlay"]};
        border-radius: 4px;
        padding: 3px 6px;
    }}
    QToolTip {{
        background-color: {COLORS["bg_overlay"]};
        color: {COLORS["text_base"]};
        border: 1px solid #45475a;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
    }}
"""


# ── 시그널 허브 (스레드 → main thread) ──────────────────────────────


class V2Signals(QObject):
    log = Signal(str)
    step_done = Signal(int, bool, str)  # step_id, success, message
    refresh_view = Signal()
    # F1: generate_step worker 가 옵션 체크 후 emit — _on_run_single 로 연결
    # (blocks 실행 path 의 step_done 과 분리해서 무한 루프 회피)
    request_auto_run = Signal(int)


class MessageInput(QPlainTextEdit):
    """입력창 — Enter 전송 / Shift+Enter 줄바꿈 / Ctrl+Enter 전송 (v1 ChatPanel 패턴)."""

    send_requested = Signal()

    def keyPressEvent(self, event):  # noqa: N802
        key = event.key()
        mods = event.modifiers()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if mods == Qt.KeyboardModifier.NoModifier or (
                mods & Qt.KeyboardModifier.ControlModifier
            ):
                # Enter 또는 Ctrl+Enter → 전송
                self.send_requested.emit()
                return
            # Shift+Enter / Alt+Enter / 기타 → 기본 (줄바꿈)
        super().keyPressEvent(event)


# ── Python 구문 강조 (v1 PythonHighlighter 재사용) ────────────────────


class PythonHighlighter(QSyntaxHighlighter):
    """Python 구문 색상 강조 — Catppuccin Mocha 팔레트.

    v1 ui/code_viewer.py PythonHighlighter 의 재사용 (디자인 토큰 일관).
    keyword/string/number/comment/function 5 카테고리.
    """

    KEYWORDS = [
        "and",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "try",
        "while",
        "with",
        "yield",
        "True",
        "False",
        "None",
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.rules: list[tuple] = []

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor(COLORS["info"]))  # 보라
        kw_fmt.setFontWeight(QFont.Weight.Bold)
        for w in self.KEYWORDS:
            self.rules.append((re.compile(rf"\b{w}\b"), kw_fmt))

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor(COLORS["success"]))  # 초록
        self.rules.append((re.compile(r"\".*?\""), str_fmt))
        self.rules.append((re.compile(r"\'.*?\'"), str_fmt))

        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#fab387"))  # 주황
        self.rules.append((re.compile(r"\b\d+\.?\d*\b"), num_fmt))

        cmt_fmt = QTextCharFormat()
        cmt_fmt.setForeground(QColor(COLORS["text_muted"]))  # 회색
        cmt_fmt.setFontItalic(True)
        self.rules.append((re.compile(r"#.*$", re.MULTILINE), cmt_fmt))

        func_fmt = QTextCharFormat()
        func_fmt.setForeground(QColor(COLORS["primary"]))  # 파랑
        self.rules.append((re.compile(r"\b\w+(?=\()"), func_fmt))

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ── Toast (D9) — 모달 아닌 floating 알림 ─────────────────────────────


class Toast(QFrame):
    """단일 토스트 알림. 우하단 stack 의 한 요소.

    types: info / success / warning / error
    auto-dismiss: 4초 (정보) / 8초 (action 있는 confirm)
    """

    closed = Signal(object)  # ToastManager 가 stack 정리용으로 받음

    _COLORS = {
        "info": COLORS["info"],
        "success": COLORS["success"],
        "warning": COLORS["warning"],
        "error": COLORS["error"],
    }
    _ICONS = {
        "info": "ℹ",
        "success": "✅",
        "warning": "⚠",
        "error": "❌",
    }

    def __init__(
        self,
        message: str,
        level: str = "info",
        action_label: Optional[str] = None,
        action_callback: Optional[Callable[[], None]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        accent = self._COLORS.get(level, COLORS["info"])
        icon = self._ICONS.get(level, "ℹ")

        self.setStyleSheet(f"""
            Toast {{
                background-color: {COLORS["bg_surface"]};
                border-left: 4px solid {accent};
                border-top: 1px solid {COLORS["bg_overlay"]};
                border-right: 1px solid {COLORS["bg_overlay"]};
                border-bottom: 1px solid {COLORS["bg_overlay"]};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(360)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 8, 10)
        layout.setSpacing(8)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"color: {accent}; border: none; font-size: 18px;")
        layout.addWidget(icon_label)

        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet(f"color: {COLORS['text_base']}; border: none; font-size: 12px;")
        msg_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(msg_label, stretch=1)

        # action 버튼 (optional — D17 confirm path)
        if action_label and action_callback:
            action_btn = QPushButton(action_label)
            action_btn.setStyleSheet(
                f"background-color: {accent}; color: {COLORS['bg_base']}; "
                f"font-weight: bold; padding: 4px 10px; border: none; border-radius: 4px;"
            )

            def _on_action():
                try:
                    action_callback()
                finally:
                    self.dismiss()

            action_btn.clicked.connect(_on_action)
            layout.addWidget(action_btn)

        # 닫기 버튼 (×)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            f"background: transparent; color: {COLORS['text_muted']}; "
            f"border: none; font-size: 14px;"
        )
        close_btn.clicked.connect(self.dismiss)
        layout.addWidget(close_btn)

        # 자동 사라짐 타이머
        timeout_ms = 8000 if (action_label and action_callback) else 4000
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._timer.start(timeout_ms)

    def dismiss(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        self.closed.emit(self)
        self.deleteLater()


class ToastManager(QObject):
    """우하단 토스트 stack 관리 — 새 토스트가 위로 쌓임."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self._host = host
        self._toasts: list[Toast] = []
        # host resize 시 위치 갱신
        host.installEventFilter(self)

    def show_toast(
        self,
        message: str,
        level: str = "info",
        action_label: Optional[str] = None,
        action_callback: Optional[Callable[[], None]] = None,
    ) -> Toast:
        toast = Toast(message, level, action_label, action_callback, parent=self._host)
        toast.closed.connect(self._on_toast_closed)
        self._toasts.append(toast)
        toast.show()
        toast.adjustSize()
        self._reposition()
        return toast

    def _on_toast_closed(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        self._reposition()

    def _reposition(self) -> None:
        margin = 16
        host = self._host
        x_right = host.width() - margin
        y_bottom = host.height() - margin
        for toast in reversed(self._toasts):
            toast.adjustSize()
            x = x_right - toast.width()
            y = y_bottom - toast.height()
            toast.move(x, y)
            y_bottom = y - 8

    def eventFilter(self, obj, event):  # noqa: N802 (Qt naming)
        from PySide6.QtCore import QEvent

        if obj is self._host and event.type() == QEvent.Type.Resize:
            self._reposition()
        return False


# ── D23 drag-drop: cards_container subclass ──────────────────────────

# step drag mime type — drag start 시 step_id 를 bytes 로 인코딩
_STEP_MIME = "application/x-ohdo-step"


class CardDropContainer(QWidget):
    """카드 스크롤 컨테이너 — step drag-drop reorder 의 drop target.

    drop y 위치를 기준으로 target_step_id 결정 → step_reorder_drop signal emit.
    """

    step_reorder_drop = Signal(int, int)  # from_step_id, target_step_id

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(_STEP_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(_STEP_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        if not event.mimeData().hasFormat(_STEP_MIME):
            return
        try:
            from_step_id = int(bytes(event.mimeData().data(_STEP_MIME)).decode())
        except Exception:  # noqa: BLE001
            return
        pos = event.position().toPoint()
        target_step_id = self._step_id_at_y(pos.y(), exclude=from_step_id)
        if target_step_id is None or target_step_id == from_step_id:
            return
        self.step_reorder_drop.emit(from_step_id, target_step_id)
        event.acceptProposedAction()

    def _step_id_at_y(self, y: int, exclude: int) -> Optional[int]:
        """drop y 위치의 StepCardV2 step_id (step_id > 0 만, exclude 제외)."""
        for child in self.findChildren(StepCardV2):
            if child.step_id <= 0 or child.step_id == exclude:
                continue
            geo = child.geometry()
            if geo.top() <= y <= geo.bottom():
                return child.step_id
        return None


# ── Step 카드 v2 (D1+D3 통합) ────────────────────────────────────────


class StepCardV2(QFrame):
    """라이브러리/Initial/Step 통합 카드 (D3 사용자 요청 + AI 설명 + 코드)."""

    run_single_requested = Signal(int)
    run_from_here_requested = Signal(int)
    # D17: 사용자 요청 영역 클릭 → MainWindow 가 toast confirm → 재생성 path
    regenerate_requested = Signal(int, str)  # step_id, user_request
    # D23: step 순서 변경 (⬆⬇ 버튼 fallback). drag-drop 은 후속 슬라이스.
    reorder_requested = Signal(int, str)  # step_id, "up" | "down"
    # 코드 직접 수정 (v1 BlockCard.block_code_edited 패턴 재사용)
    code_edited = Signal(int, str)  # step_id, new_code
    # G7-D: ⚠ 다이얼로그의 재생성 버튼 → MainWindow 가 step lookup + warnings 인용 prompt
    # 으로 generate_step 재호출. (regenerate_requested 와 분리 — warnings 인용 path 명시)
    regenerate_with_warnings_requested = Signal(int)  # step_id

    def __init__(
        self,
        step_id: int,
        title: str,
        code: str,
        user_request: str = "",
        ai_description: str = "",
        status: str = "",
        captures: Optional[list[str]] = None,
        expanded: bool = False,
        validation_warnings: Optional[list[dict]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.step_id = step_id
        self._captures = list(captures or [])
        # G7-C: code_validator 정적 분석 결과. 빈 리스트/None 이면 ⚠ 미표시.
        self._validation_warnings: list[dict] = list(validation_warnings or [])

        # 테두리 색 — wireframes_v2.md §1
        if step_id == 0:
            border = COLORS["primary"]
            icon = "📦"
        elif step_id == -1:
            border = COLORS["warning"]
            icon = "🎬"
        else:
            border = COLORS["bg_overlay"]
            icon = "📋"

        self.setStyleSheet(f"""
            StepCardV2 {{
                background-color: {COLORS["bg_surface"]};
                border: 1px solid {border};
                border-radius: 8px;
                margin: 4px 8px;
            }}
        """)
        # 카드 자체가 컨테이너 폭 따라가도록 — 자식 sizeHint 가 카드를 넓히지 못하게.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # 헤더 — clickable frame: 클릭 시 코드 영역 접기/펼치기
        self._expanded: bool = bool(expanded)
        self._header_frame = QFrame()
        self._header_frame.setStyleSheet("QFrame { background: transparent; }")
        self._header_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header_frame.setToolTip(tr("ui_v2.step_card.header_tooltip"))
        header = QHBoxLayout(self._header_frame)
        header.setContentsMargins(0, 0, 0, 0)

        # ▼/▶ expand 아이콘
        self._expand_icon = QLabel("▼" if self._expanded else "▶")
        self._expand_icon.setStyleSheet(
            f"color: {COLORS['text_muted']}; border: none; font-size: 10px;"
        )
        header.addWidget(self._expand_icon)

        title_label = QLabel(f"{icon}  {title}")
        title_label.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        title_label.setStyleSheet(f"color: {border}; border: none;")
        header.addWidget(title_label)
        header.addStretch()
        if status:
            status_label = QLabel(status)
            status_label.setStyleSheet(f"color: {COLORS['success']}; border: none;")
            header.addWidget(status_label)

        # G7-C: 정적 분석 경고 표시 — issues 있을 때만 ⚠ 위젯. 클릭 시 상세 다이얼로그.
        self.validation_warning_label: Optional[QLabel] = None
        if self._validation_warnings:
            self.validation_warning_label = QLabel("⚠")
            self.validation_warning_label.setStyleSheet(
                f"color: {COLORS['warning']}; border: none; font-size: 14px; font-weight: bold;"
            )
            self.validation_warning_label.setCursor(Qt.CursorShape.PointingHandCursor)
            tooltip_lines = [
                tr(
                    "ui_v2.step_card.validation_tooltip_header",
                    count=len(self._validation_warnings),
                )
            ]
            for w in self._validation_warnings[:3]:
                line_str = f" (line {w.get('line')})" if w.get("line") else ""
                tooltip_lines.append(f"- [{w.get('kind', '?')}]{line_str} {w.get('message', '')}")
            if len(self._validation_warnings) > 3:
                tooltip_lines.append(f"... 외 {len(self._validation_warnings) - 3}건")
            self.validation_warning_label.setToolTip("\n".join(tooltip_lines))
            self.validation_warning_label.mousePressEvent = lambda _e: (
                self._show_validation_dialog()
            )
            header.addWidget(self.validation_warning_label)

        # 헤더 영역 클릭 → 토글 (drag-drop 의 mousePressEvent 와 충돌 회피 위해
        # frame 자체에 mousePressEvent 부착)
        self._header_frame.mousePressEvent = self._on_header_click
        layout.addWidget(self._header_frame)

        # D3: 사용자 요청 (있을 때만) — D17: 클릭 시 재생성 confirm
        self._user_request_text = user_request
        if user_request and step_id > 0:
            req_header = QHBoxLayout()
            req_label = QLabel("👤 사용자 요청  (클릭: 재생성)")
            req_label.setStyleSheet(
                f"color: {COLORS['text_muted']}; border: none; font-size: 11px;"
            )
            req_header.addWidget(req_label)
            req_header.addStretch()
            layout.addLayout(req_header)
            req_edit = QPlainTextEdit(user_request)
            req_edit.setReadOnly(True)
            req_edit.setMaximumHeight(60)
            self._tame_text_widget(req_edit)
            req_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            req_edit.setToolTip(tr("ui_v2.step_card.req_edit_tooltip"))
            req_edit.setStyleSheet(f"""
                QPlainTextEdit {{
                    background-color: {COLORS["bg_overlay"]};
                    color: {COLORS["text_base"]};
                    border: none;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-family: 'Malgun Gothic';
                    font-size: 12px;
                }}
            """)
            # D17: 클릭 → regenerate_requested emit
            req_edit.mousePressEvent = lambda _e, sid=step_id, ur=user_request: (
                self.regenerate_requested.emit(sid, ur)
            )
            layout.addWidget(req_edit)

        # D3 + D19: AI 설명 (1~2줄 preview, ▼ 클릭 펼침)
        if ai_description and step_id > 0:
            preview_lines = ai_description.strip().splitlines()[:2]
            preview = " ".join(line.strip() for line in preview_lines)
            if len(preview) > 80:
                preview = preview[:80] + "..."
            elif len(ai_description) > len(preview):
                preview = preview + "..."
            # QToolButton 은 wordWrap 안 됨 → QLabel + clickable 로 교체
            ai_preview = QLabel(f"🤖  {preview}")
            ai_preview.setWordWrap(True)
            ai_preview.setStyleSheet(
                f"color: {COLORS['info']}; padding: 4px 0; "
                f"font-size: 12px; background: transparent; border: none;"
            )
            ai_preview.setCursor(Qt.CursorShape.PointingHandCursor)
            ai_preview.setToolTip(tr("ui_v2.step_card.ai_preview_tooltip"))
            ai_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            ai_preview.setMinimumWidth(0)

            ai_full = QPlainTextEdit(ai_description)
            ai_full.setReadOnly(True)
            ai_full.setMaximumHeight(120)
            ai_full.hide()
            self._tame_text_widget(ai_full)
            ai_full.setStyleSheet(f"""
                QPlainTextEdit {{
                    background-color: {COLORS["bg_overlay"]};
                    color: {COLORS["text_base"]};
                    border: none;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-family: 'Malgun Gothic';
                    font-size: 12px;
                }}
            """)
            ai_preview.mousePressEvent = lambda _e, w=ai_full: w.setVisible(not w.isVisible())
            layout.addWidget(ai_preview)
            layout.addWidget(ai_full)

        # 코드/캡처 영역 — content_widget 으로 wrap 후 expand 토글로 hide/show
        self._content_widget = QWidget()
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)

        # 캡처 thumbnail 들 (코드 위에 작게 표시 — v1 패턴)
        if self._captures:
            for cap_path in self._captures:
                thumb = self._build_capture_thumbnail(cap_path)
                if thumb is not None:
                    content_layout.addWidget(thumb)

        # 코드 영역
        code_edit = QPlainTextEdit(code)
        code_edit.setReadOnly(True)
        code_edit.setFont(QFont("Consolas", 10))
        self._readonly_height = 180 if step_id > 0 else 140
        self._editing_height = 320  # 편집 모드 높이 (v1 BlockCard 패턴)
        code_edit.setFixedHeight(self._readonly_height)
        # 코드는 줄바꿈 NoWrap (가독성 위해) — 내부 가로 스크롤바 사용. 카드 폭은 영향 X.
        code_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        code_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        code_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        code_edit.setMinimumWidth(0)
        # Python 구문 강조 (v1 PythonHighlighter 재사용) — 인스턴스 보유 필수 (GC 방지)
        self._highlighter = PythonHighlighter(code_edit.document())
        # 편집 모드 스타일 분리
        self._readonly_style = f"""
            QPlainTextEdit {{
                background-color: {COLORS["bg_base"]};
                color: {COLORS["text_base"]};
                border: 1px solid {COLORS["bg_overlay"]};
                border-radius: 4px;
                font-family: 'Consolas', 'JetBrains Mono', monospace;
            }}
        """
        self._editing_style = f"""
            QPlainTextEdit {{
                background-color: {COLORS["bg_base"]};
                color: {COLORS["text_base"]};
                border: 2px solid {COLORS["primary"]};
                border-radius: 4px;
                font-family: 'Consolas', 'JetBrains Mono', monospace;
            }}
        """
        code_edit.setStyleSheet(self._readonly_style)
        content_layout.addWidget(code_edit)
        self._code_edit = code_edit
        self._editing: bool = False

        layout.addWidget(self._content_widget)
        # default 접힘 상태 적용
        self._content_widget.setVisible(self._expanded)

        # 푸터 — wait + 액션 버튼
        footer = QHBoxLayout()

        if step_id > 0:
            wait_label = QLabel("⏱")
            wait_label.setStyleSheet(f"color: {COLORS['text_muted']}; border: none;")
            footer.addWidget(wait_label)
            self.wait_combo = QComboBox()
            self.wait_combo.addItems(
                [
                    "0",
                    "200",
                    tr("ui_v2.step_card.wait_default_suffix"),
                    "1000",
                    "2000",
                    tr("ui_v2.step_card.wait_custom"),
                ]
            )
            self.wait_combo.setCurrentIndex(2)
            self.wait_combo.setMaximumWidth(120)
            footer.addWidget(self.wait_combo)

            # D23: ⬆⬇ 버튼 (drag-drop fallback / 접근성)
            reorder_style = (
                f"background: transparent; color: {COLORS['text_muted']}; "
                f"border: none; padding: 2px 6px;"
            )
            up_btn = QToolButton()
            up_btn.setText("⬆")
            up_btn.setToolTip(tr("ui_v2.step_card.btn_up_tooltip"))
            up_btn.setStyleSheet(reorder_style)
            up_btn.clicked.connect(lambda: self.reorder_requested.emit(self.step_id, "up"))
            footer.addWidget(up_btn)

            down_btn = QToolButton()
            down_btn.setText("⬇")
            down_btn.setToolTip(tr("ui_v2.step_card.btn_down_tooltip"))
            down_btn.setStyleSheet(reorder_style)
            down_btn.clicked.connect(lambda: self.reorder_requested.emit(self.step_id, "down"))
            footer.addWidget(down_btn)

        # ✏️ 수정 버튼 — Library (step_id == 0) 제외, Initial/Step 모두 편집 가능
        if step_id != 0:
            self.edit_btn = QPushButton(tr("ui_v2.step_card.btn_edit"))
            self.edit_btn.setStyleSheet(
                f"background-color: {COLORS['bg_overlay']}; color: {COLORS['text_base']}; "
                f"padding: 4px 10px;"
            )
            self.edit_btn.setToolTip(tr("ui_v2.step_card.btn_edit_tooltip"))
            self.edit_btn.clicked.connect(self._toggle_edit)
            footer.addWidget(self.edit_btn)

        footer.addStretch()

        # D11: Initial 은 "▶ 여기서" 버튼 제거, "⏯ 단독" 만
        if step_id == -1:
            run_single_btn = QPushButton(tr("ui_v2.step_card.btn_run_initial_alone"))
            run_single_btn.setStyleSheet(
                f"background-color: {COLORS['info']}; color: {COLORS['bg_base']}; "
                f"font-weight: bold; padding: 4px 12px;"
            )
            run_single_btn.clicked.connect(lambda: self.run_single_requested.emit(self.step_id))
            footer.addWidget(run_single_btn)
        elif step_id > 0:
            run_single_btn = QPushButton(tr("ui_v2.step_card.btn_run_alone"))
            run_single_btn.clicked.connect(lambda: self.run_single_requested.emit(self.step_id))
            footer.addWidget(run_single_btn)

        if step_id == 0:
            # 라이브러리: ▶ 재초기화
            run_btn = QPushButton(tr("ui_v2.step_card.btn_run_reinit"))
            run_btn.clicked.connect(lambda: self.run_from_here_requested.emit(0))
            footer.addWidget(run_btn)
        elif step_id > 0:
            run_btn = QPushButton(tr("ui_v2.step_card.btn_run_here"))
            run_btn.setStyleSheet(
                f"background-color: {COLORS['success']}; color: {COLORS['bg_base']}; "
                f"font-weight: bold;"
            )
            run_btn.clicked.connect(lambda: self.run_from_here_requested.emit(self.step_id))
            footer.addWidget(run_btn)

        layout.addLayout(footer)

    def get_code(self) -> str:
        return self._code_edit.toPlainText()

    # ── 접기/펼치기 (v1 BlockCard._toggle_expand 패턴) ─────────────

    def _on_header_click(self, _event=None) -> None:
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        """카드 코드/캡처 영역 펼침 상태 설정 (외부에서 일괄 펼치기/접기 호출용)."""
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self._content_widget.setVisible(expanded)
        self._expand_icon.setText("▼" if expanded else "▶")

    def _show_validation_dialog(self) -> None:
        """G7-C/D: ⚠ 아이콘 클릭 → 정적 분석 경고 상세 다이얼로그.

        각 issue 의 kind / line / message 를 한 줄씩 표시. 사용자가 한눈에 보고
        "재생성" 버튼으로 warnings 인용 prompt 로 AI 재호출 (G7-D), 또는 닫기.
        """
        lines = [
            tr(
                "ui_v2.validation.header_line",
                step_id=self.step_id,
                count=len(self._validation_warnings),
            )
            + "\n"
        ]
        kind_label = {
            "syntax": tr("ui_v2.validation.kind_syntax"),
            "redefined_var": tr("ui_v2.validation.kind_redefined_var"),
            "missing_try": tr("ui_v2.validation.kind_missing_try"),
            "import_misplaced": tr("ui_v2.validation.kind_import_misplaced"),
        }
        for idx, w in enumerate(self._validation_warnings, start=1):
            kind = w.get("kind", "?")
            label = kind_label.get(kind, kind)
            line_no = w.get("line")
            line_str = f" (line {line_no})" if line_no else ""
            msg = w.get("message", "")
            lines.append(f"{idx}. [{label}]{line_str} {msg}")
        lines.append("")
        lines.append(tr("ui_v2.validation.regenerate_hint"))

        # G7-D: Retry 버튼 — 클릭 시 새 signal emit (MainWindow 가 받아서 재생성).
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(tr("ui_v2.validation.dialog_title", step_id=self.step_id))
        msg_box.setText("\n".join(lines))
        regenerate_btn = msg_box.addButton(
            tr("ui_v2.validation.btn_regenerate"), QMessageBox.ButtonRole.ActionRole
        )
        msg_box.addButton(tr("ui_v2.validation.btn_close"), QMessageBox.ButtonRole.RejectRole)
        msg_box.exec()
        if msg_box.clickedButton() is regenerate_btn:
            self.regenerate_with_warnings_requested.emit(self.step_id)

    def _build_capture_thumbnail(self, path: str) -> Optional[QLabel]:
        """캡처 이미지를 카드 폭에 맞게 리사이즈해 thumbnail QLabel 반환.

        v1 StepCard 패턴 — `QPixmap.scaledToWidth(min(360, w), Smooth)`.
        파일 없거나 로드 실패 시 None.
        """
        try:
            from pathlib import Path as _P

            if not _P(path).exists():
                return None
            pixmap = QPixmap(path)
            if pixmap.isNull():
                return None
            target_w = min(360, pixmap.width())
            scaled = pixmap.scaledToWidth(target_w, Qt.TransformationMode.SmoothTransformation)
            label = QLabel()
            label.setPixmap(scaled)
            label.setStyleSheet(
                f"border: 1px solid {COLORS['bg_overlay']}; border-radius: 4px; padding: 2px;"
            )
            label.setToolTip(f"{_P(path).name} ({pixmap.width()}x{pixmap.height()})")
            return label
        except Exception:  # noqa: BLE001
            return None

    # ── 코드 편집 토글 (v1 BlockCard 패턴) ─────────────────────────

    def _toggle_edit(self) -> None:
        if self._editing:
            self._exit_edit_mode()
        else:
            self._enter_edit_mode()

    def _enter_edit_mode(self) -> None:
        self._editing = True
        self._code_edit.setReadOnly(False)
        self._code_edit.setStyleSheet(self._editing_style)
        self._code_edit.setFixedHeight(self._editing_height)
        self.edit_btn.setText(tr("ui_v2.step_card.btn_save"))
        self.edit_btn.setStyleSheet(
            f"background-color: {COLORS['success']}; color: {COLORS['bg_base']}; "
            f"font-weight: bold; padding: 4px 10px;"
        )
        self._code_edit.setFocus()

    def _exit_edit_mode(self) -> None:
        self._editing = False
        new_code = self._code_edit.toPlainText()
        self._code_edit.setReadOnly(True)
        self._code_edit.setStyleSheet(self._readonly_style)
        self._code_edit.setFixedHeight(self._readonly_height)
        self.edit_btn.setText(tr("ui_v2.step_card.btn_edit"))
        self.edit_btn.setStyleSheet(
            f"background-color: {COLORS['bg_overlay']}; color: {COLORS['text_base']}; "
            f"padding: 4px 10px;"
        )
        # signal emit — MainWindowV2 가 받아 AppService.update_step 위임
        self.code_edited.emit(self.step_id, new_code)

    # ── D23 drag-drop: drag source ────────────────────────────────

    def mousePressEvent(self, event):  # noqa: N802
        # step_id > 0 카드만, 헤더 영역 (~36px) 에서만 drag 시작 — 코드/푸터 click 보존
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.step_id > 0
            and event.position().y() <= 36
        ):
            self._drag_start_pos = event.position().toPoint()
        else:
            self._drag_start_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        start = getattr(self, "_drag_start_pos", None)
        if start is None:
            return
        from PySide6.QtWidgets import QApplication

        if (
            event.position().toPoint() - start
        ).manhattanLength() < QApplication.startDragDistance():
            return
        # 드래그 시작 — mime data: step_id
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_STEP_MIME, str(self.step_id).encode("ascii"))
        drag.setMimeData(mime)
        # 드래그 중 미니 미리보기 (header 텍스트만)
        try:
            pixmap = self.grab(self.rect()).scaledToHeight(40)
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(20, 20))
        except Exception:  # noqa: BLE001
            pass
        self._drag_start_pos = None
        drag.exec(Qt.DropAction.MoveAction)

    @staticmethod
    def _tame_text_widget(edit: QPlainTextEdit) -> None:
        """QPlainTextEdit 의 sizeHint 가 카드 폭을 키우지 못하게 일괄 설정.

        - WidgetWidth wrap (긴 한 줄도 부모 폭에서 줄바꿈)
        - 가로 스크롤바 끔 (혹시 wrap 안 먹어도 카드 안 넓어지게)
        - minimumWidth 0 (sizeHint 무시)
        - sizePolicy Expanding+Preferred (부모 폭에 맞게 펼치되 demand 안 함)
        """
        edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        edit.setMinimumWidth(0)


# ── 메인 윈도우 v2 ──────────────────────────────────────────────────


class MainWindowV2(QMainWindow):
    """ohdo UI v2 메인 윈도우 PoC."""

    def __init__(self, app_service: Optional[AppService] = None) -> None:
        super().__init__()

        # AppService 주입 — 외부에서 미주입 시 default 생성 (Repo + AI 일괄 셋업).
        if app_service is None:
            data_dir = Path(__file__).parent.parent / "data"
            settings = self._load_settings()
            self.app_service = AppService.create_default(data_dir=data_dir, settings=settings)
        else:
            self.app_service = app_service

        self.signals = V2Signals()
        self.signals.log.connect(self._append_log)
        self.signals.step_done.connect(self._on_step_done)
        self.signals.refresh_view.connect(self._refresh_step_cards)
        # F1: generate_step worker 가 옵션 ON 시 emit → _on_run_single 직접 연결
        self.signals.request_auto_run.connect(self._on_run_single)

        self.current_session: Optional[Session] = None
        # D4: 세션별 커널 (탭마다 별도 인스턴스)
        self._kernels: dict[str, ExecutionKernel] = {}
        # P4: settings.ui.console_visible 값 따름. 사용자가 토글한 상태 유지.
        # 이전엔 hardcoded False — Ctrl+` 모르면 AI 응답 메타 (엔진/토큰/시간) 못 봄.
        try:
            _settings_for_console = self._load_settings()
        except Exception:  # noqa: BLE001
            _settings_for_console = {}
        self._console_visible = bool(
            _settings_for_console.get("ui", {}).get("console_visible", False)
        )
        # AI 호출 시 첨부할 pending 데이터 (D6) — 활성 탭의 것만 보유,
        # 탭 전환 시 _save/load_active_tab_state 로 _tabs_state 와 swap
        self._pending_images: list[str] = []
        self._pending_elements: list[dict] = []
        # D4: 탭별 임시 상태 (pending data + 입력창 텍스트). key = session_id
        self._tabs_state: dict[str, dict] = {}
        # D4: 열린 탭의 session_id 순서 (QTabBar 인덱스와 매칭)
        self._tab_session_ids: list[str] = []
        # 탭 전환 중 재진입 가드
        self._switching_tab: bool = False
        # v1 overlay 인스턴스 (재사용 — UI 컴포넌트는 ADR 우회 OK)
        self._capture_overlay = None
        self._element_overlay = None
        # D20: 사이드바 last state (settings.ui.sidebar_collapsed)
        ui_cfg = self._load_settings().get("ui", {})
        self._sidebar_collapsed: bool = bool(ui_cfg.get("sidebar_collapsed", False))

        self.setWindowTitle("ohdo — UI v2 PoC")
        self.resize(1400, 900)
        self.setStyleSheet(GLOBAL_QSS)

        self._build_layout()
        self._install_shortcuts()
        self._refresh_session_list()

        # 첫 세션 자동 로드 — D4: 첫 탭으로 엶
        summaries = self.app_service.list_sessions()
        if summaries:
            self._open_session_tab(summaries[0].session_id)

        # D14: 첫 실행 시 onboarding wizard
        QTimer.singleShot(0, self._maybe_show_onboarding)

    # ── D14 Onboarding ───────────────────────────────────────

    def _maybe_show_onboarding(self) -> None:
        """settings.ui.onboarding_done 미설정 시 wizard 띄움 (첫 실행).

        결과 처리:
        - 엔진 선택 → AppService.switch_ai_engine
        - 시나리오 선택 → 새 세션 생성 + 입력창 자동 채움
        - 완료/건너뛰기 모두 settings.ui.onboarding_done = True 저장
        """
        from .onboarding import OnboardingWizard

        settings = self._load_settings()
        if not OnboardingWizard.should_show(settings):
            return

        wizard = OnboardingWizard(settings, parent=self)
        accepted = wizard.exec()

        # 결과 적용
        try:
            if accepted and not wizard.skipped:
                if wizard.selected_engine:
                    try:
                        self.app_service.switch_ai_engine(wizard.selected_engine)
                        # B4: ai.selected 도 settings dict 에 반영 — finally 의
                        # _save_settings 가 함께 영구 저장 (ai.selected + onboarding_done).
                        settings.setdefault("ai", {})["selected"] = wizard.selected_engine
                        # 액션바 콤보 갱신
                        self.engine_combo.blockSignals(True)
                        self.engine_combo.setCurrentText(wizard.selected_engine)
                        self.engine_combo.blockSignals(False)
                    except Exception:  # noqa: BLE001
                        pass
                if wizard.selected_scenario is not None:
                    # 새 세션 + 입력창 채움
                    self._on_new_session()
                    if wizard.selected_scenario.strip():
                        self._fill_message_input(wizard.selected_scenario)
        finally:
            # 한 번 띄웠으면 다음부터 스킵
            settings.setdefault("ui", {})["onboarding_done"] = True
            try:
                self._save_settings(settings)
            except Exception:  # noqa: BLE001
                pass
            self._toast(
                "Onboarding 완료 — 환영합니다!",
                "success" if accepted and not wizard.skipped else "info",
            )

    # ── Setup helpers ─────────────────────────────────────────

    def _load_settings(self) -> dict:
        import json

        settings_path = Path(__file__).parent.parent / "config" / "settings.json"
        if settings_path.exists():
            return json.loads(settings_path.read_text(encoding="utf-8"))
        return {}

    def _load_prompts(self) -> dict:
        import json

        prompts_path = Path(__file__).parent.parent / "config" / "prompts.json"
        if prompts_path.exists():
            return json.loads(prompts_path.read_text(encoding="utf-8"))
        return {}

    def _save_settings(self, settings: dict) -> None:
        import json

        settings_path = Path(__file__).parent.parent / "config" / "settings.json"
        settings_path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _build_layout(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 액션 바 (상단)
        action_bar = self._build_action_bar()
        outer.addLayout(action_bar)

        # D4: 탭바 + 새 탭 버튼 (액션바 아래)
        tab_row = self._build_tab_row()
        outer.addLayout(tab_row)

        # Splitter: 좌 (사이드바) | 우 (메인 영역)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter = splitter

        # 사이드바 — 세션 목록
        self._sidebar = self._build_sidebar()
        splitter.addWidget(self._sidebar)

        # 메인: 카드 스크롤 + 입력
        main_area = self._build_main_area()
        splitter.addWidget(main_area)

        splitter.setSizes([220, 1180])
        # D20: 저장된 사이드바 last state 적용
        if self._sidebar_collapsed:
            self._sidebar.hide()
        outer.addWidget(splitter, stretch=1)

        # D9: 토스트 매니저 (central widget 위에 floating)
        self.toast_manager = ToastManager(central)

        # 콘솔 (D5: 토글, default hidden)
        self._build_console_panel(outer)

        # 상태바
        self._status_bar = QStatusBar()
        self._status_bar.setStyleSheet(
            f"background-color: {COLORS['bg_surface']}; color: {COLORS['text_muted']};"
        )
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage(tr("ui_v2.action_bar.status_ready"))
        # 콘솔 토글 버튼 — 사용자 보고 (5/5): 기본 회색이라 안 보임. 명확한 텍스트 + 색상.
        self._toggle_console_btn = QPushButton(tr("ui_v2.action_bar.btn_toggle_console"))
        self._toggle_console_btn.setToolTip(tr("ui_v2.action_bar.tooltip_console_toggle"))
        self._toggle_console_btn.setStyleSheet(
            f"background-color: {COLORS['bg_overlay']}; color: {COLORS['text_base']}; "
            f"border: 1px solid #45475a; border-radius: 4px; "
            f"padding: 2px 10px; font-size: 11px;"
        )
        self._toggle_console_btn.clicked.connect(self._toggle_console)
        self._status_bar.addPermanentWidget(self._toggle_console_btn)

    def _build_action_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setContentsMargins(8, 6, 8, 6)
        bar.setSpacing(8)

        # D20: 사이드바 toggle (Ctrl+B)
        self.sidebar_toggle_btn = QToolButton()
        self.sidebar_toggle_btn.setText("☰")
        self.sidebar_toggle_btn.setToolTip(tr("ui_v2.action_bar.tooltip_sidebar_toggle"))
        self.sidebar_toggle_btn.clicked.connect(self._toggle_sidebar)
        bar.addWidget(self.sidebar_toggle_btn)

        run_all_btn = QPushButton(tr("ui_v2.action_bar.btn_run_all"))
        run_all_btn.setStyleSheet(
            f"background-color: {COLORS['success']}; color: {COLORS['bg_base']}; "
            f"font-weight: bold; padding: 4px 14px;"
        )
        run_all_btn.clicked.connect(self._on_run_all)
        bar.addWidget(run_all_btn)

        stop_btn = QPushButton("⏹")
        stop_btn.setToolTip(tr("ui_v2.action_bar.tooltip_stop"))
        stop_btn.clicked.connect(self._on_stop)
        bar.addWidget(stop_btn)

        kernel_btn = QPushButton(tr("ui_v2.action_bar.btn_kernel"))
        kernel_btn.setToolTip(tr("ui_v2.action_bar.tooltip_kernel_restart"))
        kernel_btn.clicked.connect(self._on_kernel_reset)
        bar.addWidget(kernel_btn)

        # 전체 펼치기/접기 — 모든 카드 코드 영역 일괄 토글
        expand_all_btn = QToolButton()
        expand_all_btn.setText(tr("ui_v2.action_bar.btn_expand_all"))
        expand_all_btn.setToolTip(tr("ui_v2.action_bar.tooltip_expand_all"))
        expand_all_btn.setStyleSheet(
            f"color: {COLORS['text_muted']}; background: transparent; "
            f"border: none; padding: 4px 8px;"
        )
        expand_all_btn.clicked.connect(lambda: self._set_all_cards_expanded(True))
        bar.addWidget(expand_all_btn)

        collapse_all_btn = QToolButton()
        collapse_all_btn.setText(tr("ui_v2.action_bar.btn_collapse_all"))
        collapse_all_btn.setToolTip(tr("ui_v2.action_bar.tooltip_collapse_all"))
        collapse_all_btn.setStyleSheet(
            f"color: {COLORS['text_muted']}; background: transparent; "
            f"border: none; padding: 4px 8px;"
        )
        collapse_all_btn.clicked.connect(lambda: self._set_all_cards_expanded(False))
        bar.addWidget(collapse_all_btn)

        bar.addSpacing(20)

        bar.addWidget(QLabel(tr("ui_v2.action_bar.label_engine")))
        self.engine_combo = QComboBox()
        engines = self.app_service.list_ai_engines()
        for e in engines:
            self.engine_combo.addItem(e["name"])
        self.engine_combo.setCurrentText(self.app_service.get_ai_engine_name() or "")
        self.engine_combo.currentTextChanged.connect(self._on_engine_changed)
        bar.addWidget(self.engine_combo)

        bar.addStretch()

        new_session_btn = QPushButton(tr("ui_v2.action_bar.btn_new_session"))
        new_session_btn.clicked.connect(self._on_new_session)
        bar.addWidget(new_session_btn)

        return bar

    # ── D4 탭바 + D21/D22 메뉴 ───────────────────────────────

    def _build_tab_row(self) -> QHBoxLayout:
        """탭바 + 새 탭 (+) 버튼 한 줄 — 액션바 바로 아래."""
        row = QHBoxLayout()
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(4)

        self._tab_bar = QTabBar()
        self._tab_bar.setTabsClosable(True)
        self._tab_bar.setMovable(True)  # D4: 탭 순서 drag 변경
        self._tab_bar.setExpanding(False)
        self._tab_bar.setStyleSheet(f"""
            QTabBar {{
                background: transparent;
            }}
            QTabBar::tab {{
                background-color: {COLORS["bg_surface"]};
                color: {COLORS["text_muted"]};
                border: 1px solid {COLORS["bg_overlay"]};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 6px 12px;
                margin-right: 2px;
                font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background-color: {COLORS["bg_overlay"]};
                color: {COLORS["primary"]};
                font-weight: bold;
            }}
            QTabBar::tab:hover {{
                color: {COLORS["text_base"]};
            }}
            QTabBar::close-button {{
                subcontrol-position: right;
            }}
        """)
        self._tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tab_bar.customContextMenuRequested.connect(self._on_tab_context_menu)
        self._tab_bar.tabCloseRequested.connect(self._on_tab_close)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        # D4: drag 후 순서 변경 동기화
        self._tab_bar.tabMoved.connect(self._on_tab_moved)
        row.addWidget(self._tab_bar, stretch=1)

        # D21: + 새 탭 버튼 → 메뉴 (새로 만들기 / 불러오기 / 템플릿)
        plus_btn = QToolButton()
        plus_btn.setText("+")
        plus_btn.setToolTip(tr("ui_v2.tab.tooltip_new"))
        plus_btn.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 16px; "
            f"background: transparent; border: none; padding: 4px 10px;"
        )
        plus_btn.clicked.connect(self._on_plus_tab)
        row.addWidget(plus_btn)

        return row

    # ── D4 탭 관리 ────────────────────────────────────────────

    def _open_session_tab(self, session_id: str) -> None:
        """세션을 탭으로 엶 — 이미 열려있으면 그 탭으로 전환.

        주의 (사용자 보고 5/5): addTab 가 첫 탭일 때 자동 currentChanged(0) 발동 →
        _on_tab_changed 가 _tab_session_ids 보는데 비어있으면 빈 상태로 처리됨.
        반드시 _tab_session_ids.append 를 addTab 앞에 두어야 첫 탭 컨텐츠가 즉시 표시됨.
        """
        if session_id in self._tab_session_ids:
            idx = self._tab_session_ids.index(session_id)
            self._tab_bar.setCurrentIndex(idx)
            return
        try:
            session = self.app_service.get_session(session_id)
        except Exception as e:  # noqa: BLE001
            self._toast(tr("ui_v2.toast.session_load_failed", error=str(e)), "error")
            return
        title = session.title[:24] if session.title else tr("ui_v2.tab.untitled_session")
        # 1) state 먼저 동기화 (_on_tab_changed 가 즉시 정상 처리하도록)
        self._tab_session_ids.append(session_id)
        # 2) addTab — 첫 탭이면 currentChanged(0) 자동 발동 → _on_tab_changed 정상 동작
        new_idx = self._tab_bar.addTab(title)
        # 3) 첫 탭이 아니었으면 currentChanged 안 발동 → 명시 setCurrent
        if self._tab_bar.currentIndex() != new_idx:
            self._tab_bar.setCurrentIndex(new_idx)

    def _on_tab_changed(self, index: int) -> None:
        if self._switching_tab:
            return
        if 0 <= index < len(self._tab_session_ids):
            sid = self._tab_session_ids[index]
            self._switch_session(sid)
        else:
            # 모든 탭 닫힘
            self._save_active_tab_state()
            self.current_session = None
            self._pending_images = []
            self._pending_elements = []
            if hasattr(self, "message_edit"):
                self.message_edit.clear()
            self._refresh_step_cards()
            self._refresh_chip_area()

    def _switch_session(self, session_id: str) -> None:
        """탭 전환 — pending 데이터 + message 입력 swap."""
        self._switching_tab = True
        try:
            self._save_active_tab_state()
            try:
                self.current_session = self.app_service.get_session(session_id)
            except Exception as e:  # noqa: BLE001
                self._toast(tr("ui_v2.toast.session_load_failed", error=str(e)), "error")
                self.current_session = None
                return
            self._load_active_tab_state(session_id)
            self._refresh_step_cards()
            self._refresh_chip_area()
            self._status_bar.showMessage(
                tr("ui_v2.sidebar.status_session", title=self.current_session.title)
            )
            # 사이드바 highlight 동기화
            self._highlight_sidebar_session(session_id)
        finally:
            self._switching_tab = False

    def _save_active_tab_state(self) -> None:
        """현재 활성 세션의 pending 상태 + 입력창 텍스트 저장."""
        if self.current_session is None:
            return
        sid = self.current_session.session_id
        msg = self.message_edit.toPlainText() if hasattr(self, "message_edit") else ""
        self._tabs_state[sid] = {
            "pending_images": list(self._pending_images),
            "pending_elements": list(self._pending_elements),
            "message": msg,
        }

    def _load_active_tab_state(self, session_id: str) -> None:
        state = self._tabs_state.get(session_id, {})
        self._pending_images = list(state.get("pending_images", []))
        self._pending_elements = list(state.get("pending_elements", []))
        if hasattr(self, "message_edit"):
            self.message_edit.setPlainText(state.get("message", ""))

    def _on_tab_close(self, index: int) -> None:
        """탭 닫기 — UI에서만 제거 (세션 자체는 보존, 사이드바에서 다시 열기 가능).
        해당 세션의 커널은 정리 (자원 해제)."""
        if not (0 <= index < len(self._tab_session_ids)):
            return
        sid = self._tab_session_ids[index]
        # 커널 정리
        if sid in self._kernels:
            try:
                self._kernels[sid].stop()
            except Exception:
                pass
            del self._kernels[sid]
        # 탭 state 정리
        self._tabs_state.pop(sid, None)
        # 탭 bar 에서 제거 (currentChanged 가 이어서 발동됨)
        self._tab_bar.removeTab(index)
        del self._tab_session_ids[index]

    def _on_tab_moved(self, from_idx: int, to_idx: int) -> None:
        """드래그로 탭 순서 변경 시 _tab_session_ids 동기화."""
        if 0 <= from_idx < len(self._tab_session_ids) and 0 <= to_idx < len(self._tab_session_ids):
            sid = self._tab_session_ids.pop(from_idx)
            self._tab_session_ids.insert(to_idx, sid)

    # D22: 탭 우클릭 메뉴
    def _on_tab_context_menu(self, pos) -> None:
        index = self._tab_bar.tabAt(pos)
        if index < 0:
            return
        sid = self._tab_session_ids[index]
        menu = QMenu(self)
        menu.addAction(tr("ui_v2.tab.menu_close"), lambda: self._on_tab_close(index))
        menu.addAction(tr("ui_v2.tab.menu_rename"), lambda: self._on_tab_rename(sid))
        menu.addAction(tr("ui_v2.tab.menu_duplicate"), lambda: self._on_tab_duplicate(sid))
        menu.addAction(tr("ui_v2.tab.menu_export"), lambda: self._on_tab_export(sid))
        menu.addSeparator()
        menu.addAction(tr("ui_v2.tab.menu_delete"), lambda: self._on_session_delete(sid))
        menu.exec(self._tab_bar.mapToGlobal(pos))

    def _on_tab_rename(self, session_id: str) -> None:
        try:
            session = self.app_service.get_session(session_id)
        except Exception as e:  # noqa: BLE001
            self._toast(tr("ui_v2.toast.session_load_failed", error=str(e)), "error")
            return
        new_title, ok = QInputDialog.getText(
            self,
            tr("ui_v2.session.rename_title"),
            tr("ui_v2.session.rename_label"),
            text=session.title,
        )
        if not ok or not new_title.strip():
            return
        session.title = new_title.strip()
        try:
            self.app_service.save_session(session)
        except Exception as e:  # noqa: BLE001
            self._toast(tr("ui_v2.toast.save_failed", error=str(e)), "error")
            return
        # 탭 라벨 갱신
        if session_id in self._tab_session_ids:
            idx = self._tab_session_ids.index(session_id)
            self._tab_bar.setTabText(idx, session.title[:24])
        self._refresh_session_list()
        self._toast(tr("ui_v2.toast.session_renamed", title=session.title), "success")

    def _on_tab_duplicate(self, session_id: str) -> None:
        try:
            src = self.app_service.get_session(session_id)
        except Exception as e:  # noqa: BLE001
            self._toast(tr("ui_v2.toast.session_load_failed", error=str(e)), "error")
            return
        dup = self.app_service.create_session(
            title=tr("ui_v2.session.duplicate_title", original=src.title),
            project_type=src.project_type,
            description=src.description,
        )
        # step 들 복사 — Step 은 모듈 상단 from core.app_service import 로 노출됨
        for s in src.steps:
            sd = s if isinstance(s, dict) else {}
            self.app_service.add_step(
                dup.session_id,
                Step(
                    step_id=0,  # add_step 가 자동 할당
                    status=sd.get("status", "pending"),
                    generated_code=sd.get("generated_code", ""),
                    step_code=sd.get("step_code", ""),
                    step_imports=list(sd.get("step_imports", [])),
                    user_request=sd.get("user_request", ""),
                    ai_description=sd.get("ai_description", ""),
                    wait_after_ms=sd.get("wait_after_ms"),
                ),
            )
        self._refresh_session_list()
        self._open_session_tab(dup.session_id)
        self._toast(tr("ui_v2.toast.session_duplicated", title=dup.title), "success")

    def _on_session_delete(self, session_id: str) -> None:
        """세션 영구 삭제 — confirm 후 AppService.delete_session.

        탭에 열려있으면 먼저 탭 닫음 (커널 정리). 사이드바 갱신. destructive 라
        QMessageBox modal confirm (D9 결정 따름).
        """
        try:
            session = self.app_service.get_session(session_id)
            title = session.title
        except Exception:  # noqa: BLE001
            title = session_id[:8]

        reply = QMessageBox.question(
            self,
            tr("ui_v2.session.delete_title"),
            tr("ui_v2.session.delete_confirm", title=title),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 탭 열려있으면 먼저 닫음 (커널 정리 + state 제거)
        if session_id in self._tab_session_ids:
            idx = self._tab_session_ids.index(session_id)
            self._on_tab_close(idx)

        # AppService 통해 영구 삭제
        try:
            self.app_service.delete_session(session_id)
        except Exception as e:  # noqa: BLE001
            self._toast(tr("ui_v2.toast.delete_failed", error=str(e)), "error")
            return

        self._refresh_session_list()
        self._toast(tr("ui_v2.toast.session_deleted", title=title), "warning")

    def _on_sidebar_context_menu(self, pos) -> None:
        """사이드바 세션 우클릭 — 열기 / 이름 변경 / 복제 / 내보내기 / 삭제."""
        item = self.session_list.itemAt(pos)
        if item is None:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if not sid:
            return
        menu = QMenu(self)
        menu.addAction(tr("ui_v2.sidebar.menu_open"), lambda: self._open_session_tab(sid))
        menu.addSeparator()
        menu.addAction(tr("ui_v2.tab.menu_rename"), lambda: self._on_tab_rename(sid))
        menu.addAction(tr("ui_v2.tab.menu_duplicate"), lambda: self._on_tab_duplicate(sid))
        menu.addAction(tr("ui_v2.tab.menu_export"), lambda: self._on_tab_export(sid))
        menu.addSeparator()
        # 삭제 액션 — 빨간 텍스트로 destructive 표시
        del_action = menu.addAction(tr("ui_v2.sidebar.menu_delete"))
        del_action.triggered.connect(lambda: self._on_session_delete(sid))
        menu.exec(self.session_list.mapToGlobal(pos))

    def _on_tab_export(self, session_id: str) -> None:
        """워크플로우 내보내기 — AppService.export_workflow (D22 정식판).

        결과 폴더에 main.py / requirements.txt / README.md / run.bat (실행 가능)
        + session.json / captures/ / scripts/ (가져오기 가능) 모두 포함.
        """
        out_path = QFileDialog.getExistingDirectory(self, tr("ui_v2.workflow.export_dir_title"), "")
        if not out_path:
            return
        try:
            import re as _re
            from pathlib import Path as _P

            session = self.app_service.get_session(session_id)
            safe_name = _re.sub(r'[<>:"/\\|?*]', "_", session.title or "ohdo_export")
            target = _P(out_path) / f"{safe_name}_{session_id[:8]}"
            output_settings = (self.settings or {}).get("output_project", {})
            project_dir = self.app_service.export_workflow(
                session_id=session_id,
                output_dir=target,
                settings=output_settings,
            )
            self._toast(tr("ui_v2.toast.export_done", name=project_dir.name), "success")
        except Exception as e:  # noqa: BLE001
            self._toast(tr("ui_v2.toast.export_failed", error=str(e)), "error")

    def _on_import_workflow(self) -> None:
        """워크플로우 가져오기 — AppService.import_workflow (D22 가져오기 짝).

        ``export_workflow`` 결과 폴더 (또는 같은 구조 — session.json 필수) 를 받아
        새 UUID 로 ``data/sessions/`` 에 복사. 사이드바 갱신 + 새 탭으로 열기.
        """
        src_path = QFileDialog.getExistingDirectory(self, tr("ui_v2.workflow.import_dir_title"), "")
        if not src_path:
            return
        try:
            session = self.app_service.import_workflow(source_dir=src_path)
            self._refresh_session_list()
            self._open_session_tab(session.session_id)
            self._toast(tr("ui_v2.toast.import_done", title=session.title), "success")
        except FileNotFoundError as e:  # noqa: BLE001
            self._toast(tr("ui_v2.toast.import_no_session_json", error=str(e)), "error")
        except Exception as e:  # noqa: BLE001
            self._toast(tr("ui_v2.toast.import_failed", error=str(e)), "error")

    # D21: + 탭 버튼 메뉴
    def _on_plus_tab(self) -> None:
        menu = QMenu(self)
        menu.addAction(tr("ui_v2.tab.menu_new_empty"), self._on_new_session)
        menu.addAction(tr("ui_v2.tab.menu_load_from_sidebar"), self._focus_sidebar_search)
        menu.addAction(tr("ui_v2.tab.menu_import_workflow"), self._on_import_workflow)
        menu.addSeparator()
        sub = menu.addMenu(tr("ui_v2.tab.menu_templates"))
        sub.addAction(
            tr("ui_v2.scenarios.notepad_label"),
            lambda: self._new_session_with_scenario(
                tr("ui_v2.scenarios.notepad_title"),
                tr("ui_v2.scenarios.notepad_prompt"),
            ),
        )
        sub.addAction(
            tr("ui_v2.scenarios.browser_label"),
            lambda: self._new_session_with_scenario(
                tr("ui_v2.scenarios.browser_title"),
                tr("ui_v2.scenarios.browser_prompt"),
                project_type="web",
            ),
        )
        menu.exec(QCursor.pos())

    def _new_session_with_scenario(
        self, title: str, prompt: str, project_type: str = "desktop"
    ) -> None:
        session = self.app_service.create_session(title=title, project_type=project_type)
        self._refresh_session_list()
        self._open_session_tab(session.session_id)
        if prompt:
            self._fill_message_input(prompt)

    def _focus_sidebar_search(self) -> None:
        """사이드바가 접혀있으면 펼치고 검색 안내 토스트."""
        if self._sidebar_collapsed:
            self._toggle_sidebar()
        self._toast(tr("ui_v2.toast.sidebar_double_click_hint"), "info")

    def _highlight_sidebar_session(self, session_id: str) -> None:
        """활성 세션을 사이드바 목록에서 select."""
        for i in range(self.session_list.count()):
            item = self.session_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == session_id:
                self.session_list.setCurrentRow(i)
                break

    def _build_sidebar(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 4, 8)

        title = QLabel(tr("ui_v2.sidebar.title"))
        title.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        layout.addWidget(title)

        self.session_list = QListWidget()
        self.session_list.itemDoubleClicked.connect(self._on_session_dblclick)
        # 우클릭 컨텍스트 메뉴 — 열기 / 이름 변경 / 복제 / 내보내기 / 삭제
        self.session_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.session_list.customContextMenuRequested.connect(self._on_sidebar_context_menu)
        layout.addWidget(self.session_list)

        return widget

    def _build_main_area(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 카드 스크롤 영역
        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        # 카드는 컨테이너 폭에만 따라가야 함 — 자식 sizeHint 가 카드 폭 키워서
        # 가로 스크롤바 생기는 회귀 방지 (PoC 사용자 보고).
        self.cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards_scroll.setStyleSheet("border: none;")
        # D23: drop target subclass — step drag-drop reorder 받음
        self.cards_container = CardDropContainer()
        self.cards_container.step_reorder_drop.connect(self._on_step_reorder_to)
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(8, 8, 8, 8)
        self.cards_layout.setSpacing(0)
        self.cards_layout.addStretch()
        self.cards_scroll.setWidget(self.cards_container)
        layout.addWidget(self.cards_scroll, stretch=1)

        # 입력 영역 (D6: 인라인 칩 + 채팅 입력)
        input_frame = QFrame()
        input_frame.setStyleSheet(
            f"background-color: {COLORS['bg_surface']}; "
            f"border-top: 1px solid {COLORS['bg_overlay']};"
        )
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 8, 12, 8)

        chip_row = QHBoxLayout()
        self.chip_area = QLabel("(요소 칩 영역 — 선택 시 표시)")
        self.chip_area.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        self.chip_area.hide()
        chip_row.addWidget(self.chip_area)
        chip_row.addStretch()
        input_layout.addLayout(chip_row)

        input_row = QHBoxLayout()
        # 입력 영역 도구 버튼 — 사용자 보고 (5/5): 기본 transparent 라 안 보임.
        # 명확한 배경/테두리/크기/이모지 폰트 사이즈 적용.
        attach_btn_style = f"""
            QToolButton {{
                background-color: {COLORS["bg_overlay"]};
                color: {COLORS["text_base"]};
                border: 1px solid #45475a;
                border-radius: 6px;
                font-size: 18px;
                padding: 4px;
            }}
            QToolButton:hover {{
                background-color: #45475a;
                border-color: {COLORS["primary"]};
                color: {COLORS["primary"]};
            }}
        """

        capture_btn = QToolButton()
        capture_btn.setText("📷")
        capture_btn.setToolTip(tr("ui_v2.chat.tooltip_capture"))
        capture_btn.setFixedSize(40, 40)
        capture_btn.setStyleSheet(attach_btn_style)
        capture_btn.clicked.connect(self._on_capture)
        input_row.addWidget(capture_btn)

        elempick_btn = QToolButton()
        elempick_btn.setText("🎯")
        elempick_btn.setToolTip(tr("ui_v2.chat.tooltip_elempick"))
        elempick_btn.setFixedSize(40, 40)
        elempick_btn.setStyleSheet(attach_btn_style)
        elempick_btn.clicked.connect(self._on_elempick)
        input_row.addWidget(elempick_btn)

        self.message_edit = MessageInput()
        self.message_edit.setPlaceholderText(tr("ui_v2.chat.placeholder"))
        self.message_edit.setMaximumHeight(70)
        # Enter / Ctrl+Enter → 전송 (Shift+Enter 는 기본 줄바꿈 유지)
        self.message_edit.send_requested.connect(self._on_send_message)
        input_row.addWidget(self.message_edit)

        # 전송 / 중지 토글 버튼 — _set_send_state 가 텍스트/색상 변환
        self.send_btn = QPushButton(tr("ui_v2.chat.btn_send"))
        self.send_btn.setMinimumWidth(80)
        self.send_btn.clicked.connect(self._on_send_message)
        input_row.addWidget(self.send_btn)
        self._is_generating: bool = False
        self._set_send_state(False)

        input_layout.addLayout(input_row)
        layout.addWidget(input_frame)

        return widget

    def _build_console_panel(self, outer_layout: QVBoxLayout) -> None:
        self.console_panel = QPlainTextEdit()
        self.console_panel.setReadOnly(True)
        self.console_panel.setFont(QFont("Consolas", 9))
        self.console_panel.setMaximumHeight(220)
        # P4: __init__ 의 _console_visible (settings.ui.console_visible 반영) 따름
        self.console_panel.setVisible(self._console_visible)
        outer_layout.addWidget(self.console_panel)

    def _install_shortcuts(self) -> None:
        # D7: 단축키 5종
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._on_run_all)
        QShortcut(QKeySequence("F5"), self, activated=self._on_run_all)
        QShortcut(QKeySequence("F9"), self, activated=self._on_stop)
        QShortcut(QKeySequence("Ctrl+`"), self, activated=self._toggle_console)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._on_send_message)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self._on_open_settings)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self._on_command_palette)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_new_session)
        QShortcut(QKeySequence("Ctrl+B"), self, activated=self._toggle_sidebar)

    # ── 세션 ─────────────────────────────────────────────────

    def _refresh_session_list(self) -> None:
        self.session_list.clear()
        for s in self.app_service.list_sessions():
            item = QListWidgetItem(f"  {s.title}\n  ({s.completed_steps}/{s.total_steps} steps)")
            item.setData(Qt.ItemDataRole.UserRole, s.session_id)
            self.session_list.addItem(item)

    def _on_session_dblclick(self, item: QListWidgetItem) -> None:
        """D4: 사이드바 더블클릭 → 새 탭으로 엶 (이미 열려있으면 그 탭 활성)."""
        sid = item.data(Qt.ItemDataRole.UserRole)
        if sid:
            self._open_session_tab(sid)

    def _load_session(self, session_id: str) -> None:
        """레거시 호환 + 단축 path — 새 탭으로 엶."""
        self._open_session_tab(session_id)

    def _on_new_session(self) -> None:
        from datetime import datetime

        title = f"v2-새세션-{datetime.now().strftime('%H%M%S')}"
        session = self.app_service.create_session(title=title)
        self._refresh_session_list()
        # D4: 새 탭으로 엶 (currentChanged → _switch_session 자동 호출)
        self._open_session_tab(session.session_id)

    def _refresh_step_cards(self) -> None:
        # 기존 카드 제거
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.cards_layout.addStretch()

        if not self.current_session:
            self._show_empty_state(
                tr("ui_v2.empty.no_session_title"),
                tr("ui_v2.empty.no_session_desc"),
            )
            return

        if not self.current_session.steps:
            # D25: 빈 상태 안내 + 예시 요청 3개
            self._show_empty_state(
                tr("ui_v2.empty.session_start_title", title=self.current_session.title),
                tr("ui_v2.empty.session_start_desc"),
                examples=[
                    tr("ui_v2.empty.example_notepad"),
                    tr("ui_v2.empty.example_browser"),
                    tr("ui_v2.empty.example_window_title"),
                ],
            )
            return

        # 라이브러리 카드 (코드 있을 때만) — default 펼침 (사용자 default 접힘은 Step 만)
        lib_code = self.app_service.get_library_block_code(self.current_session)
        if lib_code.strip():
            lib_card = StepCardV2(
                step_id=0,
                title=tr("ui_v2.card.library_title"),
                code=lib_code,
                expanded=True,
            )
            lib_card.run_from_here_requested.connect(self._on_kernel_reset)
            self._insert_card(lib_card)

        # Initial 카드 (D24: 추출 결과 비어있지 않을 때만) — default 펼침
        init_code = self.app_service.get_initial_block_code(self.current_session)
        if init_code.strip():
            init_card = StepCardV2(
                step_id=-1,
                title=tr("ui_v2.card.initial_title"),
                code=init_code,
                expanded=True,
            )
            init_card.run_single_requested.connect(self._on_run_initial)
            init_card.code_edited.connect(self._on_block_code_edited)
            self._insert_card(init_card)

        # Step 카드
        prev_step = None
        for s in self.current_session.steps:
            sd = s if isinstance(s, dict) else None
            if sd is None:
                continue
            sid = sd.get("step_id", 0)
            delta = self.app_service.get_step_delta_code(sd, prev_step)
            prev_step = sd
            if not delta.strip():
                continue
            user_req = sd.get("user_request", "") or self._extract_user_msg(
                sd.get("conversation", [])
            )
            ai_desc = sd.get("ai_description", "") or self._extract_ai_desc(
                sd.get("conversation", [])
            )
            status_str = (
                "✅"
                if sd.get("status") == "completed"
                else "❌"
                if sd.get("status") == "failed"
                else ""
            )
            card = StepCardV2(
                step_id=sid,
                title=f"Step {sid}",
                code=delta,
                user_request=user_req,
                ai_description=ai_desc,
                status=status_str,
                captures=list(sd.get("captures", []) or []),
                expanded=False,  # 사용자 요청: 코드 영역 default 접힘
                # G7-C: 정적 분석 경고 메타 (code_validator). 헤더 ⚠ 표시.
                validation_warnings=list(sd.get("validation_warnings", []) or []),
            )
            card.run_single_requested.connect(self._on_run_single)
            card.run_from_here_requested.connect(self._on_run_from)
            card.regenerate_requested.connect(self._on_regenerate)
            card.regenerate_with_warnings_requested.connect(self._on_regenerate_with_warnings)
            card.reorder_requested.connect(self._on_step_reorder)
            card.code_edited.connect(self._on_block_code_edited)
            self._insert_card(card)

    def _insert_card(self, card: QWidget) -> None:
        # stretch 앞에 삽입
        idx = max(0, self.cards_layout.count() - 1)
        self.cards_layout.insertWidget(idx, card)

    def _set_all_cards_expanded(self, expanded: bool) -> None:
        """모든 카드 코드 영역 일괄 펼치기/접기 (액션바 전체 토글 버튼)."""
        for card in self.cards_container.findChildren(StepCardV2):
            card.set_expanded(expanded)

    def _show_empty_state(
        self,
        title: str,
        description: str,
        examples: Optional[list[str]] = None,
    ) -> None:
        """D25: 세션이 비었을 때 일러스트 + 안내 + 예시 카드 (PoC: 텍스트 only).

        예시 카드 클릭 시 입력창에 자동 채움 — 첫 사용자 진입 장벽 ↓.
        """
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        v = QVBoxLayout(wrapper)
        v.setContentsMargins(40, 60, 40, 40)
        v.setSpacing(16)

        title_label = QLabel(f"✨  {title}")
        title_label.setFont(QFont("Malgun Gothic", 14, QFont.Weight.Bold))
        title_label.setStyleSheet(f"color: {COLORS['text_base']}; border: none;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title_label)

        desc_label = QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(f"color: {COLORS['text_muted']}; border: none; font-size: 12px;")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(desc_label)

        if examples:
            v.addSpacing(8)
            ex_title = QLabel(tr("ui_v2.empty.examples_section_title"))
            ex_title.setStyleSheet(f"color: {COLORS['text_muted']}; border: none; font-size: 11px;")
            ex_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(ex_title)

            for ex in examples:
                btn = QPushButton(f"💡  {ex}")
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {COLORS["bg_surface"]};
                        color: {COLORS["primary"]};
                        border: 1px solid {COLORS["bg_overlay"]};
                        border-radius: 6px;
                        padding: 8px 12px;
                        text-align: left;
                        font-size: 12px;
                    }}
                    QPushButton:hover {{
                        background-color: {COLORS["bg_overlay"]};
                    }}
                """)
                btn.clicked.connect(lambda _checked=False, t=ex: self._fill_message_input(t))
                v.addWidget(btn)

        idx = max(0, self.cards_layout.count() - 1)
        self.cards_layout.insertWidget(idx, wrapper)

    def _fill_message_input(self, text: str) -> None:
        """예시 카드 클릭 시 입력창에 자동 채움."""
        self.message_edit.setPlainText(text)
        self.message_edit.setFocus()

    @staticmethod
    def _extract_user_msg(conversation: list) -> str:
        for msg in conversation:
            if isinstance(msg, dict) and msg.get("role") == "user":
                return msg.get("content", "")
        return ""

    @staticmethod
    def _extract_ai_desc(conversation: list) -> str:
        for msg in reversed(conversation):
            if isinstance(msg, dict) and msg.get("role") in ("assistant", "ai"):
                return msg.get("content", "")
        return ""

    # ── 액션 핸들러 ──────────────────────────────────────────

    def _on_run_all(self) -> None:
        self._start_run(start_from=1, stop_after=None, label=tr("ui_v2.run.label_all"))

    def _on_stop(self) -> None:
        self.app_service.stop_blocks()
        self._log("⏹ 중지 요청")

    def _on_kernel_reset(self, *args) -> None:
        """현재 활성 세션의 커널만 재시작 (D4: 다른 세션 커널은 유지)."""
        if self.current_session is None:
            return
        sid = self.current_session.session_id
        if sid in self._kernels:
            try:
                self._kernels[sid].stop()
            except Exception:
                pass
            del self._kernels[sid]
        self._log("🔄 커널 재시작")

    def _on_run_initial(self, _step_id: int) -> None:
        """Initial 단독 실행 — AppService.run_initial_block_sync 사용 (Phase 2.5 contract)."""
        if not self.current_session:
            QMessageBox.information(
                self, tr("ui_v2.dialog.info_title"), tr("ui_v2.dialog.no_session")
            )
            return
        # 카드 텍스트 가져오기
        init_code = ""
        for i in range(self.cards_layout.count()):
            w = self.cards_layout.itemAt(i).widget()
            if isinstance(w, StepCardV2) and w.step_id == -1:
                init_code = w.get_code()
                break
        if not init_code.strip():
            QMessageBox.information(
                self,
                tr("ui_v2.dialog.info_title"),
                tr("ui_v2.dialog.no_initial_code"),
            )
            return

        kernel = self._get_or_create_kernel()
        if kernel is None:
            QMessageBox.warning(
                self,
                tr("ui_v2.dialog.error_title"),
                tr("ui_v2.dialog.kernel_create_failed"),
            )
            return

        self._log("⏯ Initial 블럭 단독 실행 시작")
        self.lower()  # Win11 ForegroundLock 우회 패턴

        def worker():
            try:
                result = self.app_service.run_initial_block_sync(
                    self.current_session,
                    init_code,
                    kernel,
                    on_log=lambda m: self.signals.log.emit(m),
                )
                self.signals.step_done.emit(
                    -1,
                    result.success,
                    f"Initial ({result.duration_ms}ms)"
                    if result.success
                    else f"Initial 실패: {result.error}",
                )
            except Exception as e:
                self.signals.step_done.emit(-1, False, f"Initial 예외: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_run_single(self, step_id: int) -> None:
        self._start_run(
            start_from=step_id,
            stop_after=step_id,
            label=tr("ui_v2.run.label_step_alone", step_id=step_id),
        )

    def _on_run_from(self, step_id: int) -> None:
        self._start_run(
            start_from=step_id,
            stop_after=None,
            label=tr("ui_v2.run.label_step_from", step_id=step_id),
        )

    def _start_run(self, start_from: int, stop_after: Optional[int], label: str) -> None:
        """run_blocks 백그라운드 실행 — _on_run_all / _on_run_single / _on_run_from 공통.

        per-step status 는 _on_block_step_complete 가 카드에 직접 반영. 전체
        완료 후에만 카드 재구성 (_refresh_step_cards) — 매 step rebuild 회피.
        """
        if not self.current_session:
            QMessageBox.information(
                self, tr("ui_v2.dialog.info_title"), tr("ui_v2.dialog.no_session")
            )
            return
        if not self.current_session.steps:
            QMessageBox.information(
                self,
                tr("ui_v2.dialog.info_title"),
                tr("ui_v2.dialog.no_steps"),
            )
            return

        kernel = self._get_or_create_kernel()
        if kernel is None:
            QMessageBox.warning(
                self,
                tr("ui_v2.dialog.error_title"),
                tr("ui_v2.dialog.kernel_create_failed"),
            )
            return

        self._log(f"▶ {label} 실행 시작")
        self._status_bar.showMessage(tr("ui_v2.run.status_running", label=label))
        self.lower()

        def worker():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                report = loop.run_until_complete(
                    self.app_service.run_blocks(
                        session=self.current_session,
                        kernel=kernel,
                        start_from_step_id=start_from,
                        stop_after_step_id=stop_after,
                        on_step_start=lambda sid: self.signals.log.emit(f"▶ Step {sid} 실행 중..."),
                        on_step_complete=lambda sid, result: self.signals.log.emit(
                            f"{'✅' if result.success else '❌'} Step {sid} "
                            f"({result.duration_ms}ms)"
                            + (f" — {result.error}" if result.error else "")
                        ),
                        on_log=lambda m: self.signals.log.emit(m),
                    )
                )
                loop.close()
                msg = (
                    tr(
                        "ui_v2.run.status_done_summary",
                        ok=report.successful_steps,
                        total=report.executed_steps,
                    )
                    if hasattr(report, "successful_steps")
                    else tr("ui_v2.run.status_done_simple")
                )
                # step_done 으로 input 재활성화 + 카드 재구성 + 윈도우 복원 트리거
                self.signals.step_done.emit(0, True, msg)
            except Exception as e:
                self.signals.step_done.emit(0, False, f"실행 예외: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_engine_changed(self, name: str) -> None:
        try:
            self.app_service.switch_ai_engine(name)
            # B4: settings.json 영구 저장 — switch_ai_engine 은 메모리 _current_name
            # 만 변경. 재시작 시 일관성 유지를 위해 ai.selected 도 persist.
            self._persist_engine_choice(name)
            self._log(f"AI 엔진 전환: {name}")
        except Exception as e:
            self._log(f"엔진 전환 실패: {e}")

    def _persist_engine_choice(self, name: str) -> None:
        """settings.json 의 ai.selected 를 영구 저장. switch_ai_engine 호출
        사이트 (헤더 콤보 / 명령 팔레트 / onboarding) 공통 헬퍼."""
        try:
            s = self._load_settings()
            s.setdefault("ai", {})["selected"] = name
            self._save_settings(s)
        except Exception as e:  # noqa: BLE001
            self._log(f"settings.ai.selected 저장 실패: {e}")

    def _on_send_message(self) -> None:
        """사용자 메시지 → AppService.generate_step 호출 → Step 추가 → 카드 갱신.

        AppService.generate_step 가 PromptBuilder + AIEngineManager + Step 생성
        + 세션 저장을 모두 처리. ui_v2 는 thread + UI 갱신만 담당.

        generating 중에는 같은 버튼이 '⏹ 중지' — 클릭 시 AI 호출 cancel.
        """
        # AI 응답 대기 중 — 같은 버튼이 '중지' 역할
        if self._is_generating:
            try:
                self.app_service.cancel_ai()
            except Exception:  # noqa: BLE001
                pass
            self._toast("AI 응답 중지 요청", "warning")
            # 버튼 상태는 worker 가 cancelled response 받으면 step_done → 자동 복원
            return

        text = self.message_edit.toPlainText().strip()
        if not text:
            return
        if not self.current_session:
            QMessageBox.information(
                self,
                tr("ui_v2.dialog.info_title"),
                tr("ui_v2.dialog.create_session_first"),
            )
            return
        # 요소 컨텍스트가 있으면 user_request 앞에 prefix
        element_prefix = ""
        if self._pending_elements:
            summaries = []
            for e in self._pending_elements:
                ctype = e.get("control_type", "")
                name = e.get("name", "")
                if name:
                    summaries.append(f'[{ctype}] "{name}"')
                else:
                    summaries.append(f"[{ctype}]")
            element_prefix = "📌 선택된 요소: " + ", ".join(summaries) + "\n"

        full_request = element_prefix + text
        images = list(self._pending_images)  # 복사 후 비움
        elements = list(self._pending_elements)  # 복사 후 비움 — 사용자 보고 (5/5):
        # _send_request 가 self._pending_elements 다시 읽으면 비어있어 element_ctx
        # 만들어지지 않음 → AI 가 path 결정 컨텍스트 없이 selenium 으로 감 → 실패.

        self.message_edit.clear()
        # pending 비움 (전송 후)
        self._pending_images = []
        self._pending_elements = []
        self._refresh_chip_area()
        self._send_request(
            full_request,
            images=images if images else None,
            elements=elements if elements else None,
        )

    def _send_request(
        self,
        full_request: str,
        images: Optional[list[str]] = None,
        elements: Optional[list[dict]] = None,
        previous_warnings: Optional[list[dict]] = None,
    ) -> None:
        """AI 호출 worker — _on_send_message + _on_regenerate (D17) 공통.

        v1 AICallHandler 패턴 동등: elements 가 있으면 win_inspector 로
        element_context (상세 정보 텍스트) + is_browser_element 판정해 prompt 에
        전달. 누락 시 AI 가 path (Selenium vs pywinauto) 결정 컨텍스트 부족 →
        잘못된 코드 생성 (사용자 보고 5/5 RPA_20260502_1454 step 2 / v2-새세션
        step 2 같은 케이스).

        주의 (사용자 보고 5/5): 호출자 (_on_send_message) 가 self._pending_elements
        를 비운 후 호출하므로, **인자로 명시 전달 필수** — self._pending_elements
        다시 읽으면 빈 list 라 element_ctx 만들어지지 않음.
        """
        if not self.current_session:
            QMessageBox.information(
                self,
                tr("ui_v2.dialog.info_title"),
                tr("ui_v2.dialog.create_session_first"),
            )
            return

        # element 컨텍스트 + browser/desktop 판정 (v1 AICallHandler.call_ai_thread 와 동등)
        element_ctx: Optional[str] = None
        is_browser_elem: bool = False
        elements_for_prompt = list(elements) if elements else []
        if elements_for_prompt:
            try:
                from core.win_inspector import WindowInspector

                inspector = WindowInspector()
                parts = [inspector.get_element_info_text(e) for e in elements_for_prompt]
                element_ctx = "\n\n---\n\n".join(parts)
                is_browser_elem = any(
                    WindowInspector.should_use_selenium(e) for e in elements_for_prompt
                )
            except Exception as e:  # noqa: BLE001
                self._log(f"element 컨텍스트 구성 실패 (무시): {e}")

        preview = full_request.replace("📌 선택된 요소:", "").strip().splitlines()
        preview = preview[0][:120] if preview else ""
        self._log(f"사용자: {preview}")
        if images:
            self._log(f"  + 이미지 {len(images)}개 첨부")
        if element_ctx:
            self._log(f"  + element 컨텍스트 {len(element_ctx)}자, browser_path={is_browser_elem}")
        self._set_input_enabled(False)
        self._set_send_state(True)  # 전송 → ⏹ 중지 토글

        session_id = self.current_session.session_id

        def worker():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                step, response = loop.run_until_complete(
                    self.app_service.generate_step(
                        self.current_session,
                        full_request,
                        images=images if images else None,
                        on_progress=lambda m: self.signals.log.emit(m),
                        element_context=element_ctx,
                        is_browser_element=is_browser_elem,
                        previous_warnings=previous_warnings,
                    )
                )
                loop.close()

                if response.cancelled:
                    self.signals.step_done.emit(0, False, tr("ui_v2.step_done.user_canceled"))
                    return
                if not response.success or step is None:
                    self.signals.step_done.emit(
                        0,
                        False,
                        tr(
                            "ui_v2.step_done.ai_failed",
                            error=response.error or tr("ui_v2.step_done.no_response"),
                        ),
                    )
                    return

                # 세션 다시 로드 (add_step 가 repo 에 저장했으므로)
                self.current_session = self.app_service.get_session(session_id)
                # B2: 어느 엔진이 답했는지 화면에 명시 — 헤더 콤보 변경 후
                # 사용자가 실제 호출된 엔진을 콘솔에서 즉시 확인 가능.
                engine_name = self.app_service.get_ai_engine_name() or "?"
                # partial response 경고 — 응답이 도중에 잘렸음 (사용자 보고 5/5)
                if getattr(response, "partial", False):
                    self.signals.step_done.emit(
                        step.step_id,
                        True,
                        tr(
                            "ui_v2.toast.ai_partial",
                            engine=engine_name,
                            step_id=step.step_id,
                        ),
                    )
                else:
                    self.signals.step_done.emit(
                        step.step_id,
                        True,
                        tr(
                            "ui_v2.step_done.step_generated",
                            step_id=step.step_id,
                            engine=engine_name,
                            code_chars=len(response.code),
                            tokens=response.tokens_used,
                            ms=response.response_time_ms,
                        ),
                    )
                    # F1: 옵션 ON 시 step 생성 직후 자동 단독 실행 trigger.
                    # blocks 실행 path 의 step_done 과 분리된 별도 signal 사용 —
                    # 실행 완료 후 또 자동 실행되는 무한 루프 회피.
                    if (
                        self.settings.get("execution", {}).get("auto_run_on_step_create", False)
                        and step.step_id > 0
                    ):
                        self.signals.request_auto_run.emit(step.step_id)
            except Exception as e:
                self.signals.step_done.emit(0, False, f"AI 호출 예외: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _set_input_enabled(self, enabled: bool) -> None:
        """AI 호출 중 입력 비활성화 (간단한 가드)."""
        self.message_edit.setEnabled(enabled)

    def _set_send_state(self, generating: bool) -> None:
        """전송 ↔ 중지 토글 — AI 호출 중에는 빨간 '⏹ 중지' 버튼.

        클릭 동작은 _on_send_message 안에서 _is_generating 분기로 처리.
        """
        self._is_generating = generating
        if generating:
            self.send_btn.setText(tr("ui_v2.chat.btn_stop"))
            self.send_btn.setStyleSheet(
                f"background-color: {COLORS['error']}; color: {COLORS['bg_base']}; "
                f"font-weight: bold; padding: 6px 16px;"
            )
            self.send_btn.setToolTip(tr("ui_v2.chat.tooltip_stop"))
        else:
            self.send_btn.setText(tr("ui_v2.chat.btn_send"))
            self.send_btn.setStyleSheet(
                f"background-color: {COLORS['primary']}; color: {COLORS['bg_base']}; "
                f"font-weight: bold; padding: 6px 16px;"
            )
            self.send_btn.setToolTip(tr("ui_v2.chat.tooltip_send"))

    def _on_capture(self) -> None:
        """v1 ScreenCaptureOverlay 재사용 — UI 컴포넌트는 ADR 우회 OK."""
        from ui.screen_capture import ScreenCaptureOverlay

        self.lower()
        self._capture_overlay = ScreenCaptureOverlay()
        self._capture_overlay.capture_completed.connect(self._on_capture_done)
        self._capture_overlay.capture_cancelled.connect(self._on_capture_cancel)
        QTimer.singleShot(300, self._capture_overlay.start_capture)

    def _on_capture_done(self, pil_image) -> None:
        """ScreenCaptureOverlay → PIL Image 저장 + pending images 추가."""
        from datetime import datetime

        try:
            captures_dir = Path(__file__).parent.parent / "data" / "captures"
            captures_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = captures_dir / f"v2_capture_{ts}.png"
            pil_image.save(str(path))
            self._pending_images.append(str(path))
            self._log(f"📷 캡처 저장: {path.name} ({pil_image.size[0]}x{pil_image.size[1]})")
            self._toast(
                tr(
                    "ui_v2.toast.capture_saved",
                    name=path.name,
                    w=pil_image.size[0],
                    h=pil_image.size[1],
                ),
                "success",
            )
            self._refresh_chip_area()
        except Exception as e:
            self._log(f"캡처 저장 실패: {e}")
            self._toast(tr("ui_v2.toast.capture_save_failed", error=str(e)), "error")
        finally:
            self._capture_overlay = None
            self.raise_()
            self.activateWindow()

    def _on_capture_cancel(self) -> None:
        self._capture_overlay = None
        self.raise_()
        self.activateWindow()
        self._log("캡처 취소")

    def _on_elempick(self) -> None:
        """v1 ElementPickerOverlay 재사용. settings 통째로 전달 (overlay 내부에서
        element_picker 섹션 추출). 사용자 보고 (5/5): kwarg 로 잘못 전달해 강제종료.
        """
        from ui.element_picker import ElementPickerOverlay

        self.lower()
        try:
            self._element_overlay = ElementPickerOverlay(settings=self._load_settings())
        except Exception as e:  # noqa: BLE001 — overlay 생성 실패 시 안전 복구
            self._toast(tr("ui_v2.toast.elempick_reset_failed", error=str(e)), "error")
            self.raise_()
            self.activateWindow()
            return
        self._element_overlay.element_picked.connect(self._on_element_picked)
        self._element_overlay.pick_cancelled.connect(self._on_element_cancel)
        QTimer.singleShot(300, self._element_overlay.start_picking)

    def _on_element_picked(self, element_info: dict) -> None:
        """요소 선택 + element rect 영역 자동 캡처 (v1 패턴).

        rect 가 유효하면 mss 로 그 영역 + padding 만 잘라 저장 → pending_images 에 추가.
        다음 메시지 전송 시 step.captures 로 보존, 카드 thumbnail 표시.
        """
        self._pending_elements.append(element_info)
        ctype = element_info.get("control_type", "?")
        name = element_info.get("name", "")
        self._log(f"🎯 요소 선택: [{ctype}] {name[:40]}")
        self._toast(
            tr("ui_v2.toast.elempick_done", ctype=ctype, name=name[:40]),
            "success",
        )

        # element rect 영역 자동 캡처
        try:
            rect = element_info.get("rect", {}) or {}
            w = int(rect.get("width", 0) or 0)
            h = int(rect.get("height", 0) or 0)
            if w > 0 and h > 0:
                from datetime import datetime

                import mss
                from PIL import Image as PilImage

                padding = 20
                cap_left = max(0, int(rect.get("left", 0) or 0) - padding)
                cap_top = max(0, int(rect.get("top", 0) or 0) - padding)
                cap_w = w + padding * 2
                cap_h = h + padding * 2
                with mss.mss() as sct:
                    sct_img = sct.grab(
                        {
                            "left": cap_left,
                            "top": cap_top,
                            "width": cap_w,
                            "height": cap_h,
                        }
                    )
                    img = PilImage.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                # 저장 위치 — 세션 captures 폴더 (있으면) 또는 data/captures fallback
                if self.current_session is not None:
                    captures_dir = (
                        Path(__file__).parent.parent
                        / "data"
                        / "sessions"
                        / self.current_session.session_id
                        / "captures"
                    )
                else:
                    captures_dir = Path(__file__).parent.parent / "data" / "captures"
                captures_dir.mkdir(parents=True, exist_ok=True)
                filename = f"element_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
                filepath = captures_dir / filename
                img.save(str(filepath))
                self._pending_images.append(str(filepath))
                self._log(f"  + 요소 영역 캡처: {filename} ({w}x{h})")
        except Exception as e:  # noqa: BLE001
            self._log(f"  요소 캡처 실패 (무시): {e}")

        self._refresh_chip_area()
        self._element_overlay = None
        self.raise_()
        self.activateWindow()

    def _on_element_cancel(self) -> None:
        self._element_overlay = None
        self.raise_()
        self.activateWindow()
        self._log("요소 선택 취소")

    def _refresh_chip_area(self) -> None:
        """pending images + elements 를 chip 영역에 텍스트로 표시 (PoC 단순)."""
        parts = []
        if self._pending_images:
            parts.append(f"📷 {len(self._pending_images)} 이미지")
        if self._pending_elements:
            elem_summaries = []
            for e in self._pending_elements:
                ctype = e.get("control_type", "?")
                name = e.get("name", "")[:20]
                elem_summaries.append(f"[{ctype}]{':' + name if name else ''}")
            parts.append(f"🎯 {' '.join(elem_summaries)}")
        if parts:
            self.chip_area.setText("  |  ".join(parts) + "    (전송 후 자동 비움)")
            self.chip_area.show()
        else:
            self.chip_area.hide()

    def _on_open_settings(self) -> None:
        """v1 SettingsDialog 재사용. apply 후 새 설정으로 AIEngineManager 재초기화."""
        from ui.settings_dialog import SettingsDialog

        settings = self._load_settings()
        prompts = self._load_prompts()
        dialog = SettingsDialog(settings, prompts, self)
        if dialog.exec():
            new_settings = dialog.get_settings()
            self._save_settings(new_settings)
            self._log("설정 저장 완료. AI 엔진 재초기화...")
            try:
                # AppService 의 ai_manager 교체 (BYO 모델 변경 등 즉시 반영)
                self.app_service.reload_ai(new_settings)
                # 액션바 콤보 갱신
                self.engine_combo.blockSignals(True)
                self.engine_combo.clear()
                for e in self.app_service.list_ai_engines():
                    self.engine_combo.addItem(e["name"])
                self.engine_combo.setCurrentText(self.app_service.get_ai_engine_name() or "")
                self.engine_combo.blockSignals(False)
                self._log("✅ 설정 적용 완료")
                self._toast(tr("ui_v2.toast.settings_saved"), "success")
            except Exception as e:
                self._log(f"설정 적용 중 오류: {e}")
                self._toast(tr("ui_v2.toast.settings_apply_error", error=str(e)), "error")

    def _on_command_palette(self) -> None:
        """D8: Ctrl+K → CommandPalette 띄움.

        items: 명령 + 세션 + AI 엔진 카테고리.
        """
        from .command_palette import CommandPalette

        items: list[dict] = []

        # 명령
        cmd_group = tr("ui_v2.command_palette.group_commands")
        items.extend(
            [
                {
                    "label": tr("ui_v2.command_palette.cmd_run_all"),
                    "group": cmd_group,
                    "shortcut": "Ctrl+R",
                    "callback": self._on_run_all,
                },
                {
                    "label": tr("ui_v2.command_palette.cmd_stop"),
                    "group": cmd_group,
                    "shortcut": "F9",
                    "callback": self._on_stop,
                },
                {
                    "label": tr("ui_v2.command_palette.cmd_kernel_restart"),
                    "group": cmd_group,
                    "callback": self._on_kernel_reset,
                },
                {
                    "label": tr("ui_v2.command_palette.cmd_new_session"),
                    "group": cmd_group,
                    "shortcut": "Ctrl+N",
                    "callback": self._on_new_session,
                },
                {
                    "label": tr("ui_v2.command_palette.cmd_settings"),
                    "group": cmd_group,
                    "shortcut": "Ctrl+,",
                    "callback": self._on_open_settings,
                },
                {
                    "label": tr("ui_v2.command_palette.cmd_capture"),
                    "group": cmd_group,
                    "callback": self._on_capture,
                },
                {
                    "label": tr("ui_v2.command_palette.cmd_elempick"),
                    "group": cmd_group,
                    "callback": self._on_elempick,
                },
                {
                    "label": tr("ui_v2.command_palette.cmd_toggle_sidebar"),
                    "group": cmd_group,
                    "shortcut": "Ctrl+B",
                    "callback": self._toggle_sidebar,
                },
                {
                    "label": tr("ui_v2.command_palette.cmd_toggle_console"),
                    "group": cmd_group,
                    "shortcut": "Ctrl+`",
                    "callback": self._toggle_console,
                },
            ]
        )

        # 세션
        sessions_group = tr("ui_v2.command_palette.group_sessions")
        try:
            for s in self.app_service.list_sessions():
                items.append(
                    {
                        "label": f"  {s.title}  ({s.completed_steps}/{s.total_steps})",
                        "group": sessions_group,
                        "callback": (lambda sid=s.session_id: self._load_session(sid)),
                    }
                )
        except Exception:  # noqa: BLE001
            pass

        # AI 엔진
        engines_group = tr("ui_v2.command_palette.group_engines")
        for e in self.app_service.list_ai_engines():
            mark = "✓" if e.get("is_current") else "  "
            items.append(
                {
                    "label": f"{mark} {e.get('display_name', e['name'])}",
                    "group": engines_group,
                    "callback": (lambda n=e["name"]: self._switch_ai_engine_from_palette(n)),
                }
            )

        palette = CommandPalette(items, parent=self)
        palette.exec()

    def _switch_ai_engine_from_palette(self, name: str) -> None:
        """Palette → 엔진 변경 + 액션바 콤보 갱신."""
        try:
            self.app_service.switch_ai_engine(name)
            self._persist_engine_choice(name)  # B4
            self.engine_combo.blockSignals(True)
            self.engine_combo.setCurrentText(name)
            self.engine_combo.blockSignals(False)
            self._toast(tr("ui_v2.toast.engine_switched", name=name), "success")
        except Exception as e:  # noqa: BLE001
            self._toast(tr("ui_v2.toast.engine_switch_failed", error=str(e)), "error")

    def _on_step_done(self, step_id: int, success: bool, message: str) -> None:
        icon = "✅" if success else "❌"
        self._log(f"{icon} {message}")
        self._toast(message, "success" if success else "error")
        self.signals.refresh_view.emit()
        # 입력 재활성화 + 전송 버튼 복원 (AI / run_blocks 양쪽 path 공통)
        self._set_input_enabled(True)
        self._set_send_state(False)
        # 윈도우 복원
        self.raise_()
        self.activateWindow()

        # F2: step 첫 생성 시 실행 방법 힌트 토스트 — 영구 dismiss
        if success and step_id > 0:
            ui_cfg = self.settings.setdefault("ui", {})
            if not ui_cfg.get("hint_run_shown", False):
                self._toast(
                    "💡 ▶ Ctrl+R 또는 카드의 ⏯ 단독 버튼으로 실행 (다시 안 보임)",
                    level="info",
                )
                ui_cfg["hint_run_shown"] = True
                try:
                    self._save_settings(self.settings)
                except Exception:
                    # 영구화 실패해도 토스트 동작은 유지
                    pass

    # ── 콘솔 / 로그 ───────────────────────────────────────────

    def _toggle_console(self) -> None:
        self._console_visible = not self._console_visible
        self.console_panel.setVisible(self._console_visible)
        # P4: settings.json 영구 저장 — 재시작 시 마지막 상태 유지
        try:
            s = self._load_settings()
            s.setdefault("ui", {})["console_visible"] = self._console_visible
            self._save_settings(s)
        except Exception:  # noqa: BLE001
            pass

    # ── D9 토스트 헬퍼 + D20 사이드바 + D17 재생성 ─────────────────

    def _toast(
        self,
        message: str,
        level: str = "info",
        action_label: Optional[str] = None,
        action_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        """ToastManager 경유 floating 알림. D9 결정."""
        if hasattr(self, "toast_manager"):
            self.toast_manager.show_toast(message, level, action_label, action_callback)

    def _toggle_sidebar(self) -> None:
        """D20: 사이드바 펼침/접힘 + settings.ui.sidebar_collapsed 저장."""
        self._sidebar_collapsed = not self._sidebar_collapsed
        self._sidebar.setVisible(not self._sidebar_collapsed)
        # settings 갱신
        try:
            settings = self._load_settings()
            settings.setdefault("ui", {})["sidebar_collapsed"] = self._sidebar_collapsed
            self._save_settings(settings)
        except Exception as e:
            self._log(f"사이드바 상태 저장 실패: {e}")

    def _on_regenerate(self, step_id: int, user_request: str) -> None:
        """D17: 사용자 요청 클릭 → 토스트 confirm → AppService.generate_step 재호출.

        주의: 5초 안에 사용자 응답 없으면 토스트 자동 사라짐 = cancel (D17 결정).
        """
        preview = user_request[:60] + ("..." if len(user_request) > 60 else "")

        def do_regenerate():
            self._log(f"Step {step_id} 재생성: {preview}")
            # 재생성 시점엔 pending elements 가 비어있을 가능성 — None 그대로.
            # 사용자가 새 element 선택했으면 self._pending_elements 사용.
            elems = list(self._pending_elements) if self._pending_elements else None
            self._send_request(user_request, images=None, elements=elems)

        self._toast(
            tr("ui_v2.toast.regenerate_confirm", preview=preview),
            level="warning",
            action_label=tr("ui_v2.validation.btn_regenerate"),
            action_callback=do_regenerate,
        )

    def _on_regenerate_with_warnings(self, step_id: int) -> None:
        """G7-D: ⚠ 다이얼로그의 '재생성' 버튼 → step 의 user_request + validation_warnings
        를 함께 prompt 에 inject 해서 generate_step 재호출.

        흐름:
          1. 현재 세션에서 step_id 의 user_request 와 validation_warnings 추출
          2. _send_request 에 previous_warnings 전달 → prompt_builder 가 사용자
             요청 직후에 "이전 시도 실패 원인" 섹션 prepend.
          3. AI 가 같은 실수 반복 회피.
        """
        if not self.current_session:
            return
        target_step: Optional[dict] = None
        for sd in self.current_session.steps:
            sd_dict = sd if isinstance(sd, dict) else {}
            if sd_dict.get("step_id") == step_id:
                target_step = sd_dict
                break
        if target_step is None:
            self._toast(tr("ui_v2.toast.step_not_found", step_id=step_id), "error")
            return
        user_request = target_step.get("user_request", "") or self._extract_user_msg(
            target_step.get("conversation", [])
        )
        if not user_request:
            self._toast(tr("ui_v2.toast.empty_user_request", step_id=step_id), "warning")
            return
        warnings = list(target_step.get("validation_warnings", []) or [])
        self._log(f"Step {step_id} 재생성 (코드 검사 경고 {len(warnings)}건 인용)")
        elems = list(self._pending_elements) if self._pending_elements else None
        self._send_request(
            user_request,
            images=None,
            elements=elems,
            previous_warnings=warnings,
        )

    def _on_step_reorder(self, step_id: int, direction: str) -> None:
        """D23: ⬆⬇ 버튼 → AppService.move_step → 세션 다시 로드 + 카드 재구성."""
        if not self.current_session:
            return
        sid = self.current_session.session_id
        try:
            ok = self.app_service.move_step(sid, step_id, direction)
        except Exception as e:  # noqa: BLE001
            self._toast(tr("ui_v2.toast.move_failed", error=str(e)), "error")
            return
        if not ok:
            self._toast(tr("ui_v2.toast.move_not_possible"), "warning")
            return
        try:
            self.current_session = self.app_service.get_session(sid)
        except Exception as e:  # noqa: BLE001
            self._toast(tr("ui_v2.toast.session_reload_failed", error=str(e)), "error")
            return
        self._refresh_step_cards()
        arrow = "⬆" if direction == "up" else "⬇"
        self._log(f"{arrow} Step {step_id} {direction}")

    def _on_block_code_edited(self, step_id: int, new_code: str) -> None:
        """카드 ✏️ 수정 → ✅ 저장 시 호출. AppService.update_step 위임.

        Library (step_id == 0) 는 카드 자체에 수정 버튼 없음. Initial (step_id == -1) 은
        실 step 이 아니라 update_step 가 처리 못 함 — 토스트로 안내만 (PoC 한계).
        """
        if not self.current_session:
            return
        if step_id == -1:
            self._toast(tr("ui_v2.toast.initial_edit_unsupported"), "warning")
            return
        sid = self.current_session.session_id
        try:
            # manually_edited=True + step_code 우선 (extract_step_delta_code 우선순위 0)
            self.app_service.update_step(
                sid,
                step_id,
                {
                    "step_code": new_code,
                    "manually_edited": True,
                },
            )
        except Exception as e:  # noqa: BLE001
            self._toast(tr("ui_v2.toast.code_save_failed", error=str(e)), "error")
            return
        # 세션 재로드 → 카드 재구성 (다른 위젯들과 동기화)
        try:
            self.current_session = self.app_service.get_session(sid)
        except Exception:  # noqa: BLE001
            pass
        self._refresh_step_cards()
        self._toast(tr("ui_v2.toast.step_code_saved", step_id=step_id), "success")

    def _on_step_reorder_to(self, from_step_id: int, target_step_id: int) -> None:
        """D23 drag-drop: from_step_id 를 target_step_id 위치로 이동."""
        if not self.current_session:
            return
        sid = self.current_session.session_id
        try:
            ok = self.app_service.reorder_step(sid, from_step_id, target_step_id)
        except Exception as e:  # noqa: BLE001
            self._toast(tr("ui_v2.toast.move_failed", error=str(e)), "error")
            return
        if not ok:
            return
        try:
            self.current_session = self.app_service.get_session(sid)
        except Exception as e:  # noqa: BLE001
            self._toast(tr("ui_v2.toast.session_reload_failed", error=str(e)), "error")
            return
        self._refresh_step_cards()
        self._log(f"Step {from_step_id} → Step {target_step_id} 자리로 이동")

    def _append_log(self, msg: str) -> None:
        from datetime import datetime

        ts = datetime.now().strftime("%H:%M:%S")
        self.console_panel.appendPlainText(f"[{ts}] {msg}")

    def _log(self, msg: str) -> None:
        self.signals.log.emit(msg)

    # ── 커널 ─────────────────────────────────────────────────

    def _get_or_create_kernel(self) -> Optional[ExecutionKernel]:
        """현재 활성 세션의 커널 (D4: 세션별 분리)."""
        if self.current_session is None:
            return None
        sid = self.current_session.session_id
        existing = self._kernels.get(sid)
        if existing is not None and existing.is_alive:
            return existing
        try:
            kernel = self.app_service.create_kernel()
            kernel.start()
            self._kernels[sid] = kernel
            return kernel
        except Exception as e:
            self._log(f"커널 생성 실패: {e}")
            return None

    def closeEvent(self, event) -> None:
        # D4: 모든 세션 커널 정리
        for kernel in list(self._kernels.values()):
            try:
                kernel.stop()
            except Exception:
                pass
        self._kernels.clear()
        # 현재 활성 탭 상태 저장 + 세션 저장
        try:
            self._save_active_tab_state()
        except Exception:
            pass
        if self.current_session is not None:
            try:
                self.app_service.save_session(self.current_session)
            except Exception:
                pass
        super().closeEvent(event)


# ── Standalone 실행 (디버깅용) ──────────────────────────────────────


def main() -> None:
    """python -m ui_v2.main_window_v2 로 직접 실행 가능."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindowV2()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
