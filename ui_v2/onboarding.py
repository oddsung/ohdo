# SPDX-License-Identifier: AGPL-3.0-or-later
"""D14 Onboarding Wizard — 3단계 첫 실행 가이드.

[wireframes_v2.md §4](../docs/wireframes_v2.md#4-onboarding-wizard-d14-첫-실행).

3 페이지:
1. 환경 점검 — Python 경로/패키지/Gemini CLI 상태 (요약, EnvironmentSetupDialog 의 일부 표시)
2. AI 엔진 선택 — Gemini CLI / OpenAI 호환 API 라디오
3. 첫 자동화 만들기 — 추천 시나리오 3개 (메모장 / 네이버 / 빈 세션)

각 단계 우하단 [건너뛰기] 가능.

완료 시 settings.ui.onboarding_done = True 저장 → 다음 실행부터 스킵.
호출자가 결과 (선택된 엔진 / 추천 시나리오) 를 받아 첫 세션 생성 + 입력창에 채움.

PoC 단순화 (후속 확장):
- 환경 점검 페이지: 간단한 상태 라벨만. 실 스캔은 EnvironmentSetupDialog 가 담당.
- AI 엔진 페이지: 라디오 선택만. 실 키 등록은 Settings 다이얼로그로 유도.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr

_COLORS = {
    "bg_base": "#1e1e2e",
    "bg_surface": "#181825",
    "bg_overlay": "#313244",
    "text_base": "#cdd6f4",
    "text_muted": "#6c7086",
    "primary": "#89b4fa",
    "success": "#a6e3a1",
}


class OnboardingWizard(QDialog):
    """첫 실행 시 사용자 가이드. settings.ui.onboarding_done=True 면 스킵."""

    @staticmethod
    def _scenarios() -> list[tuple[str, str]]:
        # locale 변경 후 첫 인스턴스화 시점에 평가되도록 method 로 노출 (class attr 회피).
        return [
            (
                tr("ui_v2.onboarding.scenario_notepad_label"),
                tr("ui_v2.onboarding.scenario_notepad_prompt"),
            ),
            (
                tr("ui_v2.onboarding.scenario_browser_label"),
                tr("ui_v2.onboarding.scenario_browser_prompt"),
            ),
            (tr("ui_v2.onboarding.scenario_empty_label"), ""),
        ]

    def __init__(self, settings: dict, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        # 결과 — 호출자가 dialog.exec() 후 읽음
        self.selected_engine: Optional[str] = None
        self.selected_scenario: Optional[str] = None  # 시나리오의 user_request 텍스트
        self.skipped: bool = False

        self.setWindowTitle(tr("ui_v2.onboarding.window_title"))
        self.setMinimumSize(560, 440)
        self.setStyleSheet(f"""
            OnboardingWizard, QWidget {{
                background-color: {_COLORS["bg_base"]};
                color: {_COLORS["text_base"]};
                font-family: 'Malgun Gothic';
            }}
            QPushButton {{
                background-color: {_COLORS["bg_overlay"]};
                color: {_COLORS["text_base"]};
                border: 1px solid {_COLORS["bg_overlay"]};
                border-radius: 4px;
                padding: 6px 14px;
            }}
            QPushButton:hover {{
                background-color: #45475a;
            }}
            QRadioButton {{
                color: {_COLORS["text_base"]};
                font-size: 13px;
                padding: 6px 0;
            }}
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(12)

        # 진행 표시 (1/3, 2/3, 3/3)
        self.step_label = QLabel("1 / 3")
        self.step_label.setStyleSheet(f"color: {_COLORS['text_muted']}; font-size: 11px;")
        self.step_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        outer.addWidget(self.step_label)

        # 스택
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_page_env())  # 0
        self.stack.addWidget(self._build_page_engine())  # 1
        self.stack.addWidget(self._build_page_first())  # 2
        outer.addWidget(self.stack, stretch=1)

        # 푸터 — 건너뛰기 / 이전 / 다음 / 시작
        footer = QHBoxLayout()
        skip_btn = QPushButton(tr("ui_v2.onboarding.btn_skip"))
        skip_btn.clicked.connect(self._on_skip)
        footer.addWidget(skip_btn)
        footer.addStretch()

        self.prev_btn = QPushButton(tr("ui_v2.onboarding.btn_prev"))
        self.prev_btn.clicked.connect(self._on_prev)
        self.prev_btn.setEnabled(False)
        footer.addWidget(self.prev_btn)

        self.next_btn = QPushButton(tr("ui_v2.onboarding.btn_next"))
        self.next_btn.setStyleSheet(
            f"background-color: {_COLORS['primary']}; color: {_COLORS['bg_base']}; "
            f"font-weight: bold;"
        )
        self.next_btn.clicked.connect(self._on_next)
        footer.addWidget(self.next_btn)
        outer.addLayout(footer)

    # ── 페이지 빌더 ───────────────────────────────────────

    def _build_page_env(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(16)

        title = QLabel(tr("ui_v2.onboarding.page_env_title"))
        title.setFont(QFont("Malgun Gothic", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)

        v.addSpacing(8)

        # 간단 상태 — 자세한 스캔은 Settings 다이얼로그
        status = QLabel(tr("ui_v2.onboarding.page_env_description"))
        status.setStyleSheet(f"color: {_COLORS['text_muted']}; font-size: 12px;")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status.setWordWrap(True)
        v.addWidget(status)

        v.addStretch()
        return w

    def _build_page_engine(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(12)

        title = QLabel(tr("ui_v2.onboarding.page_engine_title"))
        title.setFont(QFont("Malgun Gothic", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)

        v.addSpacing(8)

        sub = QLabel(tr("ui_v2.onboarding.page_engine_sub"))
        sub.setStyleSheet(f"color: {_COLORS['text_muted']}; font-size: 11px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        v.addWidget(sub)
        v.addSpacing(8)

        self._engine_group = QButtonGroup(self)

        # 사용 가능한 엔진 동적 표시 (settings.ai.available_engines 기준)
        # 2026-05-24 (handoff §36): "gemini_cli" → "cli_ai" rename. legacy 키도
        # 같이 노출해 기존 settings.json 호환.
        engines_cfg = self._settings.get("ai", {}).get("available_engines", {})
        current_selected = self._settings.get("ai", {}).get("selected", "cli_ai")

        engine_options = [
            ("cli_ai", tr("ui_v2.onboarding.engine_cli_ai")),
            ("gemini_cli", tr("ui_v2.onboarding.engine_gemini_cli")),  # legacy alias
            ("openai_compat", tr("ui_v2.onboarding.engine_openai_compat")),
        ]
        for key, label in engine_options:
            if key not in engines_cfg:
                continue
            rb = QRadioButton(label)
            rb.setProperty("engine_name", key)
            if key == current_selected:
                rb.setChecked(True)
            self._engine_group.addButton(rb)
            v.addWidget(rb)

        v.addStretch()
        return w

    def _build_page_first(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(12)

        title = QLabel(tr("ui_v2.onboarding.page_first_title"))
        title.setFont(QFont("Malgun Gothic", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)

        v.addSpacing(8)

        sub = QLabel(tr("ui_v2.onboarding.page_first_sub"))
        sub.setStyleSheet(f"color: {_COLORS['text_muted']}; font-size: 11px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        v.addWidget(sub)
        v.addSpacing(8)

        self._scenario_group = QButtonGroup(self)
        for label, prompt_text in self._scenarios():
            display = label if not prompt_text else f"{label} — {prompt_text}"
            rb = QRadioButton(display)
            rb.setProperty("scenario_prompt", prompt_text)
            self._scenario_group.addButton(rb)
            v.addWidget(rb)

        # 첫 옵션 default
        if self._scenario_group.buttons():
            self._scenario_group.buttons()[0].setChecked(True)

        v.addStretch()
        return w

    # ── 핸들러 ────────────────────────────────────────────

    def _on_prev(self) -> None:
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
        self._update_buttons()

    def _on_next(self) -> None:
        idx = self.stack.currentIndex()
        if idx < self.stack.count() - 1:
            self.stack.setCurrentIndex(idx + 1)
            self._update_buttons()
        else:
            # 마지막 페이지 → 결과 수집 + accept
            self._collect_results()
            self.accept()

    def _on_skip(self) -> None:
        self.skipped = True
        self.reject()

    def _update_buttons(self) -> None:
        idx = self.stack.currentIndex()
        last = self.stack.count() - 1
        self.prev_btn.setEnabled(idx > 0)
        self.next_btn.setText(
            tr("ui_v2.onboarding.btn_start") if idx == last else tr("ui_v2.onboarding.btn_next")
        )
        self.step_label.setText(f"{idx + 1} / {self.stack.count()}")

    def _collect_results(self) -> None:
        # 엔진
        for btn in self._engine_group.buttons():
            if btn.isChecked():
                self.selected_engine = btn.property("engine_name")
                break
        # 시나리오
        for btn in self._scenario_group.buttons():
            if btn.isChecked():
                self.selected_scenario = btn.property("scenario_prompt") or ""
                break

    # ── public helper ────────────────────────────────────

    @staticmethod
    def should_show(settings: dict) -> bool:
        """settings.ui.onboarding_done=True 가 아니면 첫 실행으로 간주."""
        return not bool(settings.get("ui", {}).get("onboarding_done", False))
