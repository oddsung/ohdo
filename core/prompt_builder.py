# SPDX-License-Identifier: AGPL-3.0-or-later
"""
프롬프트 빌더

세션 컨텍스트를 기반으로 AI에게 전송할 프롬프트를 구성합니다.

핵심 원칙:
- 사용자 요청을 프롬프트 최상단에 배치 (AI가 무시하지 못하도록)
- 시스템 지시문은 간결하게 맨 끝에 배치
- "코드를 반드시 생성하라"는 지시를 반복 강조
"""

import functools
import json
import logging
import platform
import re
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@functools.cache
def _build_env_info_lines() -> list[str]:
    """런타임 환경 (OS/Python/주요 라이브러리 버전) detect — 한 번만 실행 후 cache.

    AI 가 사용자의 정확한 환경을 알면 import 가능한 라이브러리만 사용하고
    버전 별 API 차이도 (학습 데이터 한도 내에서) 정확히 반영 가능.
    """
    lines = [
        "## 현재 실행 환경 (이 환경에서 import 가능한 라이브러리만 사용. 표준 라이브러리는 항상 사용 가능):",
        f"- OS: {platform.system()} {platform.release()}",
        f"- Python: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    ]
    for lib in ("pywinauto", "selenium", "pyautogui", "pyperclip"):
        try:
            mod = __import__(lib)
            ver = getattr(mod, "__version__", None) or "?"
            lines.append(f"- {lib}: {ver}")
        except ImportError:
            pass
    return lines


class PromptBuilder:
    """
    AI 프롬프트 컨텍스트 빌더.

    프롬프트 구조 (우선순위 순):
    1. 사용자 요청 (최상단 - 가장 중요)
    2. 컨텍스트 (이전 코드/스텝)
    3. 시스템 지시 (코드 생성 규칙)
    """

    def __init__(self, prompts_config: Optional[dict] = None):
        if prompts_config is None:
            prompts_file = Path(__file__).parent.parent / "config" / "prompts.json"
            if prompts_file.exists():
                with open(prompts_file, "r", encoding="utf-8") as f:
                    prompts_config = json.load(f)
            else:
                prompts_config = {}

        self.templates = prompts_config
        self.system_context = self.templates.get("system_context", "")
        self.error_recovery_template = self.templates.get("error_recovery", "")

    def build_step_prompt(
        self,
        session,
        user_request: str,
        image_paths: Optional[list[str]] = None,
        error_context: Optional[str] = None,
        window_context: Optional[str] = None,
        element_context: Optional[str] = None,
        max_history_steps: int = 5,
        project_type: str = "desktop",
        is_browser_element: bool = False,
        previous_warnings: Optional[list[dict]] = None,
    ) -> str:
        """
        단계별 대화 프롬프트를 생성합니다.

        프롬프트 구조:
          [1] 사용자 요청 (가장 먼저!)
          [2] 이전 컨텍스트 (코드/스텝)
          [3] 코드 생성 규칙 (끝에 배치)
        """
        # P1b: split 호출자가 system_text 를 별도로 받아 OpenAI 호환 어댑터의
        # system role 로 분리 가능. 단일 string 호출자는 backward compat 으로
        # system + user_text 를 합쳐 반환 (P1a 와 동일 결과).
        system_text, user_text = self._build_step_prompt_parts(
            session=session,
            user_request=user_request,
            image_paths=image_paths,
            error_context=error_context,
            window_context=window_context,
            element_context=element_context,
            max_history_steps=max_history_steps,
            project_type=project_type,
            is_browser_element=is_browser_element,
            previous_warnings=previous_warnings,
        )
        return (system_text + "\n\n" + user_text) if system_text else user_text

    def build_step_prompt_split(
        self,
        session,
        user_request: str,
        image_paths: Optional[list[str]] = None,
        error_context: Optional[str] = None,
        window_context: Optional[str] = None,
        element_context: Optional[str] = None,
        max_history_steps: int = 5,
        project_type: str = "desktop",
        is_browser_element: bool = False,
        previous_warnings: Optional[list[dict]] = None,
    ) -> tuple[str, str]:
        """P1b: build_step_prompt 의 split 버전 — (system_text, user_text) 반환.

        OpenAI 호환 어댑터가 system role 로 분리해서 messages 에 넣을 수 있게.
        Gemini CLI 어댑터는 자체적으로 prepend 하여 동일 효과.

        - system_text: prompts.json 의 system_context (idempotent driver, jupyter,
          UWP wait, pyautogui PRIMARY 등 12K+ 가이드). 비어있으면 빈 문자열.
        - user_text: 사용자 요청 + 누적 코드 + element/window context + 규칙.
        """
        return self._build_step_prompt_parts(
            session=session,
            user_request=user_request,
            image_paths=image_paths,
            error_context=error_context,
            window_context=window_context,
            element_context=element_context,
            max_history_steps=max_history_steps,
            project_type=project_type,
            is_browser_element=is_browser_element,
            previous_warnings=previous_warnings,
        )

    def _build_step_prompt_parts(
        self,
        session,
        user_request: str,
        image_paths: Optional[list[str]] = None,
        error_context: Optional[str] = None,
        window_context: Optional[str] = None,
        element_context: Optional[str] = None,
        max_history_steps: int = 5,
        project_type: str = "desktop",
        is_browser_element: bool = False,
        previous_warnings: Optional[list[dict]] = None,
    ) -> tuple[str, str]:
        """내부 빌더 — (system_text, user_text) 반환. system 은 self.system_context,
        user 는 사용자 요청 + 컨텍스트 + 규칙. 두 호출자 (build_step_prompt /
        build_step_prompt_split) 의 공통 구현."""
        system_text = self.system_context or ""

        parts = []

        # ═══════════════════════════════════════════
        # [1] 사용자 요청을 최상단에 배치 (가장 중요!)
        # ═══════════════════════════════════════════
        parts.append(f'다음 요청에 대한 Python 코드를 즉시 작성하세요: "{user_request}"')
        parts.append(
            "※ 요청에 포함된 ID, 비밀번호, 입력 텍스트 등 따옴표 안의 값은 공백 추가나 변경 없이 코드에 정확히 그대로 사용하세요. (@, #, % 등 특수문자로 시작하는 값 포함)"
        )
        parts.append(
            "※ 코드 내 주석(#으로 시작하는 줄)은 반드시 한 줄로만 작성하세요. 주석 안에 줄바꿈(\\n)을 포함하면 Python 문법 오류가 발생합니다."
        )
        parts.append("")

        # ═══════════════════════════════════════════
        # [1.5] G7-D: 이전 시도 정적 분석 경고 (재생성 흐름) — 있을 때만
        # ═══════════════════════════════════════════
        # AI 가 이전에 생성한 코드가 code_validator 의 검사를 통과 못 했을 때,
        # 사용자가 ⚠ 다이얼로그에서 "재생성" 클릭 → 이 섹션이 prompt 에 inject.
        # 이전 실수를 명시적으로 알려서 같은 패턴을 반복하지 않도록 강제.
        if previous_warnings:
            parts.append("## 🚨 이전 시도 코드 검사 결과 (반드시 피해야 할 문제)")
            parts.append(
                "이전에 생성한 코드가 정적 분석에서 아래 문제로 실패했습니다. "
                "이번 코드 생성 시 **반드시 같은 실수를 피하세요**:"
            )
            _kind_label = {
                "syntax": "문법 오류 (들여쓰기/괄호 등)",
                "redefined_var": "변수 재정의 (jupyter mode 호환 위반)",
                "missing_try": "try/except 누락 (외부 자원 호출 보호 안 됨)",
                "import_misplaced": "import 위치 위반 (try/def/if 안 import)",
            }
            for idx, w in enumerate(previous_warnings, start=1):
                kind = w.get("kind", "?")
                label = _kind_label.get(kind, kind)
                line_no = w.get("line")
                line_str = f" (line {line_no})" if line_no else ""
                msg = w.get("message", "")
                parts.append(f"  {idx}. [{label}]{line_str} {msg}")
            parts.append(
                "→ 위 문제 해결: (a) 이전 step 에서 정의한 변수 (`app`, `win`, `driver` 등) 를 "
                "다시 정의하지 말고 그대로 재사용. (b) 모든 외부 자원 호출은 try/except 로 감쌀 것. "
                "(c) 모든 import 는 코드 최상단 (라인 1~N) 에만 작성. (d) 들여쓰기/괄호 검증."
            )
            parts.append("")

        # ═══════════════════════════════════════════
        # [2] 컨텍스트 (이전 스텝/코드)
        # ═══════════════════════════════════════════
        current_code, is_manually_edited = self._get_current_code(session)
        completed_summary = self._build_steps_summary(session, max_history_steps)

        # 5/6 사용자 결정: 누적 코드 압축 — 이전 step body 마커화. 마지막 1 step body 만 keep.
        # prompt size 폭증 (35K+) 시 Gemini corrupt 응답 (`<ctrl46>`) trigger 회피.
        # manually_edited 케이스 (사용자 직접 편집) 는 압축 안 함 — 사용자 의도 보존.
        compressed_code = current_code
        summarized_count = 0
        if current_code and not is_manually_edited:
            compressed_code, summarized_count = self._compress_accumulated_code(
                current_code, keep_last_n=1
            )

        if current_code:
            if summarized_count > 0:
                parts.append("## 현재까지 작성된 누적 코드 (이전 step 본문 일부 생략 — 마커만):")
            else:
                parts.append("## 현재까지 작성된 누적 코드 (이전 모든 스텝의 동작이 담겨 있음):")
            parts.append(f"```python\n{compressed_code}\n```")
            parts.append("")
            if is_manually_edited:
                edit_diff = self._get_last_edit_diff(session)
                parts.append(
                    "## [중요] 사용자가 위 코드를 직접 수정했습니다. 아래 변경사항을 반드시 유지하세요:"
                )
                if edit_diff:
                    parts.append("```diff")
                    parts.append(edit_diff)
                    parts.append("```")
                    parts.append(
                        "위 diff의 '+' 줄이 최종 값입니다. '-' 줄(이전 값)로 절대 되돌리지 마세요."
                    )
                else:
                    parts.append(
                        "위 코드의 모든 문자열 값(send_keys 인자, 비밀번호, ID, URL 등)을 한 글자도 변경하지 말고 그대로 복사하세요."
                    )
            else:
                parts.append(
                    "⚠ 핵심 규칙: 위 코드는 이전 모든 스텝의 동작을 순서대로 포함한 누적 코드입니다."
                )
                parts.append(
                    "반드시 위 코드의 모든 동작을 그대로 유지하면서, 새 요청의 동작을 기존 흐름의 마지막에 추가하세요."
                )
                parts.append(
                    "절대로 이전 단계의 코드를 삭제하거나 주석으로 대체하거나 요약하지 마세요."
                )
            if summarized_count > 0:
                parts.append("")
                parts.append(
                    f"⚠ **압축 안내 — `# === Step N: <task> (본문 생략 ...) ===` 마커 ({summarized_count}개)**: "
                    "이전 step 본문은 prompt size 절약을 위해 생략됨. 그러나 그 step 들은 **이미 실행 완료** 되었고, "
                    "정의한 변수 (`app`, `win`, `text` 등) 와 import 들은 **누적 효과로 보존** 되어 새 step 에서 그대로 참조 가능. "
                    "마지막 1개 step body 는 그대로 보여줌 (가장 가까운 context 유지)."
                )
                parts.append(
                    "✗ 금지: 생략된 step body 를 추측해서 다시 작성 / 마커 라인 변경 / "
                    "이미 정의된 변수의 재정의."
                )
                parts.append(
                    "✓ 응답 형식: import 영역과 마커들은 그대로 두고, 새 사용자 요청에 해당하는 "
                    "**새 step 마커 + 본문** 만 마지막에 추가 (다음 step 번호로)."
                )
            parts.append(
                "새 기능은 기존 코드가 완전히 실행된 후 이어서 실행되도록 추가해야 합니다."
            )
            # 사용자 보고 (5/6): AI 가 같은 요청 반복 시 (예: ctrl+shift+s 두 번째) 새 step
            # 마커 안 만들고 응답에 누적 코드만 반환 → extract_step_delta_code 가 fallback
            # 으로 generated_code 전체를 step_code 로 저장 → 단독 실행 시 import + 메모장
            # 실행 코드까지 통째 실행되는 회귀.
            parts.append(
                "⚠ **새 step 추가 강제 (절대 위반 금지)**: 새 요청이 이전 step 의 코드와 동일해 보여도 "
                "**반드시 별도 step 마커 + 본문으로 추가**. 다음 3가지 모두 응답에 포함:"
            )
            parts.append("  1. `# === Step <N>: <설명> (시작) ===` 마커 (N = 다음 step 번호)")
            parts.append("  2. 새 요청에 해당하는 본문 코드 (단 한 줄이라도, 같은 코드 반복이라도)")
            parts.append("  3. `# === Step <N>: <설명> (끝) ===` 마커")
            parts.append(
                "✗ 금지: 응답에 새 step 마커 없이 누적 코드만 반환 / 빈 step 반환 / "
                '"이미 같은 코드 있음" 같은 사유로 step 생략.'
            )
            parts.append("")

        is_macos = platform.system() == "Darwin"

        if project_type == "auto" and not current_code:
            parts.append("## 통합 코드 생성 규칙 (매우 중요):")
            if is_macos:
                parts.append(
                    "하나의 자동화 세션 안에서 데스크톱 제어(AppleScript/pyautogui)와 웹 브라우저 제어(Selenium)를 얼마든지 섞어서 자유롭게 파이썬 코드를 작성하세요."
                )
            else:
                parts.append(
                    "하나의 자동화 세션 안에서 데스크톱 제어(pywinauto)와 웹 브라우저 제어(Selenium)를 얼마든지 섞어서 자유롭게 파이썬 코드를 작성하세요."
                )
            parts.append(
                "만약 사용자의 첫 요청 의도가 너무 모호하여(예: '클릭해줘') 자동화 대상을 명확히 알 수 없다면, Python 코드를 전혀 생성하지 말고 의도를 묻는 질문(답변)만 하세요."
            )
            parts.append("요청이 명확하다면 즉시 파이썬 코드를 작성하세요.")
            parts.append("")

        if completed_summary:
            parts.append(f"## 이전 스텝 요약:\n{completed_summary}")
            parts.append("")

        # 이미지 첨부
        if image_paths:
            parts.append(f"## 첨부 이미지 ({len(image_paths)}장)")
            parts.append("화면 캡처를 참고하여 코드를 작성하세요.")
            parts.append("")

        # UI 자동화 가이드 (OS별 분기)
        # 환경 정보 (OS + Python + 주요 라이브러리 버전) — AI 가 정확한 라이브러리 시그니처 사용하도록
        parts.extend(_build_env_info_lines())
        parts.append("")
        parts.extend(self._build_automation_guide(is_macos))
        parts.append("")

        # 브라우저(Selenium) 세션 일관성 강제 (devloop 실측 2026-06-06):
        # 자동화 가이드가 pywinauto 를 "최우선"으로 제시해, 브라우저 세션에서도 '버튼 클릭' 같은
        # 일반 요청이 pywinauto Desktop 으로 잘못 라우팅 → `name 'Desktop' is not defined` NameError.
        # 이전 누적코드가 이미 Selenium(driver 생성 완료)일 때만 — 즉 2번째 step 이후에만 발동.
        # (project_type=browser 만으로 첫 step 에 발동하면 driver 가 없는데 "재사용"하라고 해서 실패.)
        _browser_session = bool(current_code) and (
            "webdriver" in current_code or "selenium" in current_code.lower()
        )
        if _browser_session and not is_macos:
            parts.append(
                "🚨 **브라우저(Selenium) 세션입니다**: 이 세션은 Selenium 으로 브라우저를 제어합니다"
                "(이전 step 에서 `driver` 생성). 모든 요소 조작(클릭/입력/읽기)을 반드시 **Selenium "
                "`driver.find_element(By...)`** 로 하고 이전 step 의 `driver` 변수를 재사용하세요. "
                "**pywinauto(Application/Desktop/child_window)·`win` 변수·pyautogui 좌표 클릭을 절대 "
                "섞지 마세요** — `name 'Desktop' is not defined` / `name 'win' is not defined` 오류가 납니다. "
                "버튼 클릭도 `driver.find_element(By.XPATH, \"//button[contains(text(),'전송')]\").click()` 처럼 Selenium 으로."
            )
            parts.append("")

        # 윈도우 컨트롤 정보 (있을 경우)
        if window_context:
            parts.append(window_context)
            parts.append("")
            parts.append("위 컨트롤 정보를 활용하여 pywinauto로 자동화 코드를 작성하세요.")
            parts.append("")

        # 선택된 UI 요소 정보 (피커로 선택한 경우)
        if element_context:
            parts.append(element_context)
            parts.append("")
            if is_browser_element:
                parts.append(
                    "위 선택된 UI 요소 정보를 활용하여 해당 요소를 조작하는 Selenium 코드를 작성하세요."
                )
                parts.append(
                    "⚠️ 웹 요소 클릭 시 반드시 find_and_click() 함수를 정의하고 사용하세요."
                )
                parts.append(
                    "   - off-canvas(화면 밖, x<0) 요소는 element.click()이 ElementClickInterceptedException을 발생시킵니다."
                )
                parts.append(
                    "   - find_and_click()은 뷰포트 좌표를 확인하여 off-canvas 요소를 JS click으로 자동 처리합니다."
                )
                parts.append(
                    "   - 대기 조건은 visibility_of_element_located가 아닌 presence_of_element_located를 사용하세요."
                )
                parts.append(
                    "     (off-canvas 요소는 visibility 조건을 영원히 만족하지 못해 TimeoutException 발생)"
                )
            else:
                # G2: 가이드 강화 — DeepSeek 등이 ready-to-use 템플릿을 무시하고 짧은
                # 자체 코드 작성 → element/click_target/pyautogui 누락 회귀 (5/9). 강제력 ↑.
                parts.append(
                    "🚨 **위 ## 선택된 UI 요소 섹션의 ```python 코드 템플릿을 그대로 시작 코드로 사용하세요**:"
                )
                parts.append(
                    "  - 템플릿 안에서 `app`, `win`, `element` (= `_resolve_element()` 결과), `click_target` "
                    "변수가 자동 정의됨. **자체적으로 element 변수를 다시 만들지 마세요** — 5/9 회귀: "
                    "`name 'click_target' is not defined` / `name 'element' is not defined`."
                )
                parts.append(
                    "  - 템플릿의 DPI Awareness + Application().connect + win + _resolve_element + "
                    "ShowWindow(IsIconic 분기) + walk-up to clickable parent 단계를 **그대로 유지**하세요. "
                    "한 줄도 빼지 마세요."
                )
                parts.append(
                    "  - **import 는 코드 안에 작성하지 마세요** — 핵심 패키지 (ctypes / ctypes.wintypes / "
                    "time / pyautogui / pyperclip / pywinauto.Application) 는 라이브러리 블럭에 이미 자동 "
                    "prepend 되어 있음. 마커 안에 `import X` 작성 시 P3 #5 (import 위치 강제) 위반 + "
                    "step_imports 분리 실패."
                )
                parts.append(
                    "  - 사용자 요청 (클릭 / 텍스트 입력 / 키 누름 등) 에 해당하는 **동작 코드만 템플릿 끝에 추가**. "
                    "예: 클릭만 요청 → `pyautogui.click(center_x, center_y)` 가 이미 템플릿에 있으면 수정 X. "
                    "텍스트 입력 추가 요청 → 클릭 코드 다음에 `pyautogui.write` 또는 클립보드 paste 추가."
                )
                parts.append(
                    "  - 동작 추가 시 가이드 #13 의 ASCII/CJK 분기 + 가이드 #19 의 표준 키 이름 (`'ctrl'` NOT `'control'`) 준수."
                )
                parts.append(
                    "⚠️ pywinauto API 정확한 키워드: `auto_id=` (NOT `automation_id=`), `class_name=`, `control_type=`."
                )
                parts.append(
                    "   - selenium 의 `find_element(By.ID, ...)` 와 혼동 금지 — pywinauto 는 `child_window(auto_id=...)` 만."
                )
            parts.append("")

        # 에러 복구
        if error_context:
            parts.append("## 에러 발생 - 수정된 코드 필요:")
            parts.append(f"```\n{error_context}\n```")
            parts.append("이 에러를 해결하는 수정된 전체 코드를 작성하세요.")
            parts.append("")

        # ═══════════════════════════════════════════
        # [3] 코드 생성 규칙 (간결하게)
        # ═══════════════════════════════════════════
        parts.append("## 규칙:")
        parts.append("- 반드시 ```python 코드블록을 포함하세요")
        parts.append("- 코드는 즉시 실행 가능한 완전한 형태로 작성하세요")
        parts.append("- import문, try/except, print()를 포함하세요")
        parts.append("- 설명은 2~3줄로 짧게, 한국어로 작성하세요")
        parts.append("- 질문하지 말고 바로 코드를 생성하세요")
        # ── Jupyter 모드 호환 (블럭 단독 실행) ──
        # 각 스텝은 같은 Python 프로세스에서 차례로 exec() 됩니다. 변수가 module-level
        # 에 노출되어야 다음 스텝에서 재사용 가능. 아래 규칙은 단독 실행 회귀 방지용.
        parts.append(
            "- [Jupyter 호환] 절대 `def main(): ...; main()` 패턴으로 코드를 감싸지 마세요. 모든 코드를 모듈 레벨(들여쓰기 0)에 직접 작성하세요. 함수 안에 정의된 변수(driver, app 등)는 다음 스텝에서 NameError 가 됩니다."
        )
        parts.append(
            '- [Jupyter 호환] try/except 의 캡처 변수(`except Exception as e:` 의 `e` 등)는 반드시 그 except 블록 안에서만 사용하세요. except 블록 밖에서 `print(f"...{e}")` 처럼 참조하면 다음 스텝 단독 실행 시 NameError 가 발생합니다.'
        )
        if current_code:
            parts.append(
                "- [중요] 이전 스텝의 모든 코드(함수 호출, 변수, 로직)를 빠짐없이 유지하세요"
            )
            parts.append(
                "- [중요] 새 동작은 기존 함수 내 마지막 실행 순서에 추가하세요. 별도 함수로 분리하지 마세요"
            )
            parts.append(
                "- [Jupyter 호환] 이전 스텝에서 정의된 변수(driver, app, dlg, options 등)는 재정의하지 말고 그대로 사용하세요. `driver = webdriver.Chrome(...)` 같은 초기화는 첫 스텝에서만 — 이후 스텝은 기존 driver 변수를 그대로 참조합니다."
            )

        user_text = "\n".join(parts)
        logger.debug(f"프롬프트 생성 완료 (system {len(system_text)}자, user {len(user_text)}자)")
        return system_text, user_text

    def _build_automation_guide(self, is_macos: bool) -> list[str]:
        """OS별 UI 자동화 가이드를 생성합니다."""
        parts = []
        parts.append("## UI 자동화 접근법 (우선순위 순):")

        if is_macos:
            # ── macOS 가이드 ──
            parts.append("1. **AppleScript (osascript)** (최우선): macOS 앱 제어")
            parts.append("   - subprocess.run(['osascript', '-e', script])로 AppleScript 실행")
            parts.append('   - 앱 실행: tell application "앱이름" to activate')
            parts.append('   - 텍스트 입력: tell application "System Events" to keystroke "텍스트"')
            parts.append(
                '   - 메뉴 클릭: tell application "System Events" to click menu item "항목" of menu "메뉴" of menu bar 1 of process "앱"'
            )
            parts.append(
                "   - 🌟중요: AppleScript에서 한글 입력 시 keystroke를 사용하세요 (pyautogui.typewrite는 IME 영향을 받음)"
            )
            parts.append("2. **Selenium** (웹 자동화): Chrome 브라우저 제어")
            self._append_selenium_guide(parts)
            parts.append("3. **pyautogui** (대안): 이미지 매칭 또는 좌표 클릭")
            parts.append("   - pyautogui.click(x, y) 또는 locateOnScreen('image.png')")
            parts.append(
                "   - 🌟중요: macOS에서 pyautogui.typewrite()는 한글 IME가 활성화되면 한글로 입력됩니다."
            )
            parts.append("     영문 입력이 필요하면 AppleScript keystroke를 사용하세요.")
            parts.append("4. **subprocess**: 프로그램 실행")
            parts.append("   - subprocess.Popen(['open', '-a', '앱이름'])으로 앱 실행")
            parts.append(
                "   - subprocess.Popen(['open', 'https://url'])으로 기본 브라우저에서 URL 열기"
            )
        else:
            # ── Windows 가이드 ──
            # ⚠ system_context 의 가이드 #14(b)/#14(c)/#11 과 모순되지 않도록 align.
            # 5/6 사용자 보고: Desktop().window() 사용 시 변수 type 혼동으로 후속 step 에서
            # 0 windows found 회귀 발생 → idempotent Application.connect() 권장으로 통일.
            parts.append(
                "1. **pywinauto** (최우선): 윈도우 컨트롤 제어 (버튼 클릭, 메뉴 선택, 텍스트 입력)"
            )
            parts.append(
                "   - 🌟중요(앱 실행/연결): **`Application().connect()` 사용** (Win11 메모장/UWP 포함). idempotent try/except 패턴 (system_context 의 가이드 #14(b) 참조):"
            )
            parts.append("     ```python")
            parts.append("     try:")
            parts.append(
                "         app = Application(backend='uia').connect(title_re=r'.*메모장', timeout=3, found_index=0)"
            )
            parts.append("     except Exception:")
            parts.append("         subprocess.Popen(['notepad.exe'])")
            parts.append("         time.sleep(1.5)")
            parts.append(
                "         app = Application(backend='uia').connect(title_re=r'.*메모장', timeout=10, found_index=0)"
            )
            parts.append("     win = app.window(title_re=r'.*메모장', found_index=0)")
            parts.append("     ```")
            parts.append(
                "   - 🌟중요(변수 명명 — type 혼동 방지): `app` = `Application` 객체 (`Application().connect()` 결과). `win` = `WindowSpecification` (`app.window()` 결과 — 본 윈도우 spec). **❌ `app = Desktop().window(...)` 절대 금지** — 이건 변수명만 `app` 이지 실제는 `WindowSpecification` 이라 후속 step 의 `app.window(...)` 호출이 자식 검색이 되어 0 windows found 에러 발생. `Desktop().window(...)` 가 반환하는 객체는 `win` (또는 다른 이름) 으로 명명할 것."
            )
            parts.append(
                "   - 🌟중요(UWP wait): Win11 메모장/계산기 등은 `app.wait('ready', timeout=N)` 가 timeout 되는 경우 잦음. `win.wait('visible', timeout=N)` 또는 polling 사용 (system_context 의 가이드 #14(c))."
            )
            parts.append(
                "   - 🌟중요: UWP 앱(메모장 등) 내부의 메뉴나 버튼을 찾을 때 child_window()에 여러 요소가 매칭되는 오류가 잦습니다. 항상 child_window(title='...', control_type='...', found_index=0).invoke() 또는 click_input() 형태로 found_index=0을 필수로 넣으세요."
            )
            parts.append("2. **Selenium** (웹 자동화): Chrome 브라우저 제어")
            self._append_selenium_guide(parts)
            parts.append("3. **pyautogui** (대안): 이미지 매칭 또는 좌표 클릭")
            parts.append("   - pyautogui.click(x, y) 또는 locateOnScreen('image.png')")
            parts.append("4. **subprocess**: 프로그램 실행")
            parts.append(
                "   - 🌟중요(작업 디렉토리): Program Files 등에 설치된 프로그램은 반드시 cwd 파라미터를 사용하세요:"
            )
            parts.append("     ```python")
            parts.append("     import subprocess, os")
            parts.append("     exe_path = r'C:\\Program Files\\...\\program.exe'")
            parts.append("     subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))")
            parts.append("     ```")
            parts.append(
                "   - cwd를 설정하지 않으면 프로그램이 DLL이나 설정 파일을 찾지 못해 실행되지 않을 수 있습니다."
            )
            parts.append(
                "   - 메모장(notepad.exe) 같은 Windows 기본 프로그램은 cwd 없이도 실행 가능합니다."
            )
            parts.append(
                "   - 🌟중요(콘솔 앱 — cmd.exe / powershell.exe / pwsh.exe / wt.exe): ohdo 의 kernel_worker 는 콘솔 없는 piped subprocess 이므로 `subprocess.Popen(['cmd.exe'])` 만 호출하면 자식이 부모의 stdio 를 상속 → **윈도우가 생성되지 않고** banner 만 부모 파이프에 출력됩니다. pywinauto/`Application().connect()` 가 영원히 못 찾으니 반드시 `creationflags=subprocess.CREATE_NEW_CONSOLE` 을 추가하세요:"
            )
            parts.append("     ```python")
            parts.append("     import subprocess")
            parts.append(
                "     subprocess.Popen(['cmd.exe'], creationflags=subprocess.CREATE_NEW_CONSOLE)"
            )
            parts.append(
                "     # PowerShell: subprocess.Popen(['powershell.exe'], creationflags=subprocess.CREATE_NEW_CONSOLE)"
            )
            parts.append("     ```")
            parts.append(
                "   - GUI 앱 (notepad, calc, mspaint, chrome 등) 은 자체 윈도우를 생성하므로 이 플래그 불필요."
            )

        return parts

    def _append_selenium_guide(self, parts: list[str]):
        """Selenium 웹 자동화 가이드 (공통)"""
        parts.append(
            "   - 🌟중요(URL 접속): driver.get()에 반드시 프로토콜(https://)을 포함하세요:"
        )
        parts.append(
            "     잘못된 예: driver.get('work.example.com')       ← 프로토콜 없으면 'data:' 페이지 열림!"
        )
        parts.append(
            "     올바른 예: driver.get('https://work.example.com')  ← 반드시 https:// 또는 http:// 포함"
        )
        parts.append(
            "   - 🌟중요(페이지 로드 대기 — 추측성 ID 금지): driver.get() 직후 페이지 로드 대기를 위해"
        )
        parts.append("     실존 여부가 확실하지 않은 element ID 로 WebDriverWait 사용하지 마세요.")
        parts.append(
            "     잘못된 예: WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'nm_main_tab')))"
        )
        parts.append(
            "                ← 'nm_main_tab' 같은 추측성 ID 가 페이지에 없으면 10초 timeout + Exception 발생"
        )
        parts.append("     올바른 예 (단순 대기): time.sleep(2)  ← 짧은 명시적 sleep")
        parts.append(
            "     올바른 예 (확실한 selector): WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))"
        )
        parts.append(
            "     올바른 예 (사용자가 명시한 다음 동작 element): 다음 단계에서 클릭할 element 가 명확히 알려진 경우만"
        )
        parts.append(
            "     원칙: 페이지 로드 직후의 generic 대기는 sleep 또는 'body'/'html' 같은 항상 존재하는 selector 사용."
        )
        parts.append(
            "           특정 element 대기는 그 element 의 ID/CSS 가 사용자/요소피커에서 확인된 경우에만."
        )
        parts.append("   - 🌟중요(브라우저 유지): 반드시 detach 옵션을 사용하세요:")
        parts.append("     ```python")
        parts.append("     from selenium.webdriver.chrome.options import Options")
        parts.append("     options = Options()")
        parts.append(
            "     options.add_experimental_option('detach', True)  # 스크립트 종료 후 브라우저 유지"
        )
        parts.append(
            "     driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)"
        )
        parts.append("     ```")
        parts.append("   - detach=True가 없으면 스크립트가 끝날 때 Chrome이 자동으로 닫힙니다.")
        parts.append(
            "   - 다음 스텝에서 이미 열린 브라우저를 재사용하려면 driver 객체를 유지하거나,"
        )
        parts.append(
            "     Chrome 실행 시 --remote-debugging-port=9222 옵션 추가 후 connect로 재연결하세요."
        )
        parts.append("   - 🌟중요(요소 찾기 핵심 규칙 — 모든 웹 환경 공통):")
        parts.append("     ① XPath로 텍스트 검색 시 반드시 script/style 태그 제외하세요:")
        parts.append(
            "        잘못된 예: //*[contains(text(), 'RPA')]  ← <script> 태그의 JS 문자열도 매칭되어 클릭 실패!"
        )
        parts.append(
            "        올바른 예: //*[not(self::script)][not(self::style)][contains(text(), 'RPA')]"
        )
        parts.append(
            "     ② 드롭다운/서브메뉴 클릭 시 반드시 find_and_click(..., visible_only=True)를 사용하세요."
        )
        parts.append(
            "        presence_of_element_located: DOM에 존재하면 즉시 반환 — 사이드바 등 화면 밖 요소도 반환!"
        )
        parts.append(
            "        visibility_of_element_located: CSS hidden만 확인 — x<0 위치 요소도 '보임'으로 통과!"
        )
        parts.append(
            "        ✅ 올바른 방법: find_and_click(..., visible_only=True) — getBoundingClientRect()로 뷰포트 내 요소만 선택"
        )
        parts.append(
            "     ③ 비인터랙티브 텍스트 요소(<span>, <div>, <li> 등) 클릭 시 JavaScript click을 사용하세요:"
        )
        parts.append(
            "        element = wait.until(EC.visibility_of_element_located((By.XPATH, '//*[not(self::script)][not(self::style)][contains(text(), \"메뉴명\")]')))"
        )
        parts.append(
            '        driver.execute_script("arguments[0].click()", element)  # JS click으로 안정적 클릭'
        )
        parts.append(
            "     ④ <button>, <a>, <input> 같은 인터랙티브 요소는 element_to_be_clickable + .click()을 사용하세요:"
        )
        parts.append(
            "        element = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), \"확인\")]')))"
        )
        parts.append("        element.click()")
        parts.append(
            "     ⑤ 로케이터 안정성 우선순위: id속성 > 결합 XPath(title+text) > aria-label > 텍스트내용"
        )
        parts.append(
            "        - ⚠️ 일부 SPA 요소는 HTML @title 속성이 없으므로 ('title','...') 단독 전략은 10초 타임아웃 후 실패합니다."
        )
        parts.append(
            "          title과 text를 OR로 묶은 XPath를 사용해야 어느 경우에도 즉시 매칭됩니다:"
        )
        parts.append(
            '          //*[contains(normalize-space(@title),"메뉴명") or ./text()[contains(normalize-space(),"메뉴명")]]'
        )
        parts.append(
            "     ⑥ 웹 요소 클릭 표준 함수: 모든 웹 자동화 코드에 아래 find_and_click()을 항상 포함하세요."
        )
        parts.append("        이 함수는 범용으로 설계되어 어떤 웹사이트에서도 동작합니다:")
        parts.append("        - off-canvas(x<0) 요소 → JS click 자동 처리")
        parts.append(
            "        - 아이콘 폰트 PUA 문자(\\uE000~\\uF8FF) 포함 텍스트 → contains()로 자동 매칭"
        )
        parts.append("        - 새 탭/창으로 열리는 콘텐츠 → window_handles 자동 전환")
        parts.append("        - iframe 내부 요소 → switch_to.frame() 자동 탐색")
        parts.append("        ```python")
        parts.append(
            "        def find_and_click(driver, locators, timeout=10, visible_only=False):"
        )
        parts.append('            """범용 웹 요소 클릭 함수.')
        parts.append(
            '            새 탭/창·iframe 자동 탐색, PUA 아이콘 문자 자동 처리, off-canvas JS click 지원."""'
        )
        parts.append("            import time as _t, re as _re")
        parts.append("            from selenium.webdriver.support.ui import WebDriverWait")
        parts.append("            from selenium.webdriver.support import expected_conditions as EC")
        parts.append("            from selenium.webdriver.common.by import By")
        parts.append("            from selenium.webdriver.common.action_chains import ActionChains")
        parts.append("            def _bv(strat, val):")
        parts.append(
            "                bm = {'id': By.ID, 'css': By.CSS_SELECTOR, 'xpath': By.XPATH}"
        )
        parts.append("                if strat == 'title':")
        parts.append("                    v = _re.sub(r'[\\uE000-\\uF8FF]', '', val).strip()")
        parts.append(
            "                    return By.XPATH, f'//*[contains(normalize-space(@title),\"{v}\")]'"
        )
        parts.append("                if strat == 'text':")
        parts.append("                    v = _re.sub(r'[\\uE000-\\uF8FF]', '', val).strip()")
        parts.append(
            "                    return By.XPATH, f'//*[not(self::script)][not(self::style)][./text()[contains(normalize-space(),\"{v}\")]]'"
        )
        parts.append(
            "                if strat == 'xpath':  # xpath 전략: contains() 내부 값 앞뒤 공백 자동 제거"
        )
        parts.append('                    val = _re.sub(r\'contains\\(([^,]+),"([^"]+)"\\)\',')
        parts.append(
            "                                  lambda m: f'contains({m.group(1)},\"{m.group(2).strip()}\")', val)"
        )
        parts.append("                return bm.get(strat, By.XPATH), val")
        parts.append("            def _click(ctx, by, val, vis, t):")
        parts.append("                if vis:")
        parts.append("                    dl = _t.time()+t; el = None")
        parts.append("                    while _t.time() < dl:")
        parts.append("                        for _c in ctx.find_elements(by, val):")
        parts.append("                            try:")
        parts.append(
            "                                _r = ctx.execute_script('var r=arguments[0].getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};', _c)"
        )
        parts.append(
            "                                if _r['w']>0 and _r['h']>0 and _r['x']>-10 and _r['y']>-10: el=_c; break"
        )
        parts.append("                            except Exception: continue")
        parts.append("                        if el: break")
        parts.append("                        _t.sleep(0.1)")
        parts.append("                    if el is None: raise Exception(f'visible 없음: {val}')")
        parts.append("                else:")
        parts.append(
            "                    el = WebDriverWait(ctx, t).until(EC.presence_of_element_located((by, val)))"
        )
        parts.append(
            "                r = ctx.execute_script('var r=arguments[0].getBoundingClientRect();return {x:r.x,y:r.y};', el)"
        )
        parts.append(
            "                if r['x']<0 or r['y']<0: ctx.execute_script('arguments[0].click()',el)"
        )
        parts.append("                else:")
        parts.append(
            "                    try: ActionChains(ctx).move_to_element(el).click().perform()"
        )
        parts.append("                    except Exception:")
        parts.append("                        try: el.click()")
        parts.append(
            "                        except Exception: ctx.execute_script('arguments[0].click()',el)"
        )
        parts.append("                return el")
        parts.append("            last_err = None")
        parts.append("            orig = None")
        parts.append("            try: orig = driver.current_window_handle")
        parts.append("            except Exception: pass")
        parts.append("            for strat, val in locators:")
        parts.append("                by, bval = _bv(strat, val)")
        parts.append(
            "                try: return _click(driver, by, bval, visible_only, timeout)  # 현재 컨텍스트"
        )
        parts.append("                except Exception as e: last_err = e")
        parts.append("                try:  # 새 탭/창 탐색")
        parts.append("                    for h in driver.window_handles:")
        parts.append("                        if h == orig: continue")
        parts.append("                        try:")
        parts.append("                            driver.switch_to.window(h)")
        parts.append(
            "                            return _click(driver, by, bval, visible_only, min(timeout,4))"
        )
        parts.append("                        except Exception:")
        parts.append("                            try: driver.switch_to.window(orig)")
        parts.append("                            except Exception: pass")
        parts.append("                    try: driver.switch_to.window(orig)")
        parts.append("                    except Exception: pass")
        parts.append("                except Exception as e: last_err = e")
        parts.append("                try:  # iframe 탐색")
        parts.append("                    driver.switch_to.default_content()")
        parts.append("                    for _f in driver.find_elements(By.TAG_NAME,'iframe'):")
        parts.append("                        try:")
        parts.append("                            driver.switch_to.frame(_f)")
        parts.append(
            "                            return _click(driver, by, bval, visible_only, min(timeout,4))"
        )
        parts.append("                        except Exception: driver.switch_to.default_content()")
        parts.append("                except Exception as e:")
        parts.append("                    last_err = e")
        parts.append("                    try: driver.switch_to.default_content()")
        parts.append("                    except Exception: pass")
        parts.append("            raise Exception(f'클릭 실패: {locators} / {last_err}')")
        parts.append("        ```")
        parts.append(
            "        사용 예 — 일반/상위 메뉴: find_and_click(driver, [('xpath', '//*[contains(normalize-space(@title),\"공통업무\") or ./text()[contains(normalize-space(),\"공통업무\")]]')])"
        )
        parts.append(
            "        사용 예 — 서브메뉴:       find_and_click(driver, [('xpath', '//*[./text()[contains(normalize-space(),\"실패사례\")]]')], visible_only=True)"
        )
        parts.append(
            "        사용 예 — id로 찾기:     find_and_click(driver, [('id', 'year')])  # iframe/새탭 자동 탐색"
        )
        parts.append("     ⑥-1 🌟필수(XPath 텍스트 매칭 규칙 — 모든 웹사이트 공통):")
        parts.append("        XPath에서 텍스트/타이틀로 요소를 찾을 때 올바른 패턴을 사용하세요.")
        parts.append('        ① @title 매칭: contains(normalize-space(@title),"버튼명")')
        parts.append(
            "           이유: @title에 PUA 아이콘 문자(\\uE000~\\uF8FF)가 앞에 붙을 수 있음"
        )
        parts.append('        ② 텍스트 매칭: ./text()[contains(normalize-space(),"버튼명")]')
        parts.append(
            "           이유: normalize-space(.)는 자식 요소의 텍스트까지 포함하여 조상 요소도 매칭됨."
        )
        parts.append("                ./text()는 직접 텍스트 노드만 확인하므로 정확한 요소를 찾음.")
        parts.append("        ```")
        parts.append("        # ❌ 절대 사용 금지")
        parts.append(
            '        normalize-space(@title)="조회"                     # PUA 문자로 인해 실패'
        )
        parts.append(
            '        contains(normalize-space(.),"버튼명")              # 조상 div/nav도 매칭 → 잘못된 요소 클릭'
        )
        parts.append("        # ✅ 올바른 패턴")
        parts.append('        contains(normalize-space(@title),"조회")           # @title PUA 대응')
        parts.append(
            '        ./text()[contains(normalize-space(),"사례등록")]   # 직접 텍스트 노드만 매칭'
        )
        parts.append("        ```")
        parts.append("        XPath 작성 시 전체 패턴:")
        parts.append(
            '        \'//*[contains(normalize-space(@title),"버튼명") or ./text()[contains(normalize-space(),"버튼명")]]\''
        )
        parts.append(
            "     ⑦ 🌟중요(드롭다운·서브메뉴·팝업 클릭): 클릭 후 나타나는 모든 하위 항목은 반드시"
        )
        parts.append(
            "        visible_only=True를 사용하세요. 많은 웹 앱이 사이드바/다른 메뉴의 항목을"
        )
        parts.append(
            "        DOM에 미리 생성해 두기 때문에, XPath가 뷰포트 밖(x<0) 숨겨진 요소를 먼저 찾고"
        )
        parts.append("        JS click으로 잘못 클릭하는 버그가 발생합니다 (아무 일도 안 일어남):")
        parts.append("        ```python")
        parts.append(
            "        # ❌ 잘못된 예: XPath가 사이드바의 숨겨진 요소(x=-220)를 먼저 반환 → JS click → 아무 변화 없음"
        )
        parts.append(
            "        find_and_click(driver, [('xpath', '//*[./text()[contains(normalize-space(),\"메뉴명\")]]')])"
        )
        parts.append(
            "        # ✅ 올바른 예: visible_only=True → getBoundingClientRect로 뷰포트 안 요소만 선택"
        )
        parts.append(
            "        find_and_click(driver, [('xpath', '//*[./text()[contains(normalize-space(),\"상위메뉴\")]]')])"
        )
        parts.append(
            "        find_and_click(driver, [('xpath', '//*[./text()[contains(normalize-space(),\"하위항목\")]]')], visible_only=True)"
        )
        parts.append("        ```")
        parts.append(
            "        적용 범위: 드롭다운 메뉴, 팝업 내 버튼, 탭 전환 후 항목, 아코디언 하위 항목 등"
        )
        parts.append(
            "        최초 페이지 로드 요소(헤더, 로그인 버튼 등)는 visible_only=False(기본값) 유지"
        )
        parts.append("     ⑩ 🌟중요(DOM 컨텍스트 활용 — 최적 로케이터 결정): 요소 선택 시 제공되는")
        parts.append(
            "        outerHTML/CSS 클래스/XPath/부모 HTML을 분석해 최적 전략을 선택하세요:"
        )
        parts.append("        1. HTML id 있음 → By.ID 최우선 (가장 안정적)")
        parts.append("        2. CSS 클래스 있음 → 클래스+텍스트 조합 XPath 또는 CSS selector 활용")
        parts.append("        3. <span>/<i>/<em> 등 비인터랙티브 태그 → 부모 HTML 분석 후")
        parts.append("           실제 클릭 핸들러가 있는 요소(<button>/<a>/<div data-*> 등)를 클릭")
        parts.append(
            "        4. DOM에 동일 텍스트의 숨겨진 요소가 여럿 존재할 때(SPA 드롭다운/아코디언 등):"
        )
        parts.append("           CSS selector + getBoundingClientRect()로 실제 보이는 요소만 찾고,")
        parts.append("           .closest()로 클릭 핸들러가 있는 조상 요소를 반환하세요.")
        parts.append("        ```python")
        parts.append("        import time")
        parts.append(
            "        def click_visible_element(driver, css_selector, text, parent_selector=None, timeout=10):"
        )
        parts.append('            """CSS 선택자로 후보를 좁히고, 화면에 보이는 요소만 클릭.')
        parts.append(
            "            parent_selector: 클릭 핸들러가 있는 조상 CSS 선택자 (예: '.menu-item', 'li')"
        )
        parts.append(
            '            DOM 컨텍스트의 CSS 클래스와 부모 HTML을 참고해 인자를 채우세요."""'
        )
        parts.append("            from selenium.webdriver.common.action_chains import ActionChains")
        parts.append("            deadline = time.time() + timeout")
        parts.append("            while time.time() < deadline:")
        parts.append("                el = driver.execute_script('''")
        parts.append("                    var items = document.querySelectorAll(arguments[0]);")
        parts.append("                    for (var i = 0; i < items.length; i++) {")
        parts.append("                        if (items[i].textContent.trim() === arguments[1]) {")
        parts.append("                            var r = items[i].getBoundingClientRect();")
        parts.append("                            if (r.width > 0 && r.height > 0 && r.top >= 0) {")
        parts.append("                                var target = arguments[2]")
        parts.append(
            "                                    ? items[i].closest(arguments[2]) : items[i];"
        )
        parts.append("                                return target || items[i];")
        parts.append("                            }")
        parts.append("                        }")
        parts.append("                    }")
        parts.append("                    return null;")
        parts.append("                ''', css_selector, text, parent_selector)")
        parts.append("                if el:")
        parts.append(
            "                    ActionChains(driver).move_to_element(el).click().perform()"
        )
        parts.append("                    return el")
        parts.append("                time.sleep(0.2)")
        parts.append(
            "            raise Exception(f'{text} 요소를 찾지 못했습니다 ({css_selector})')"
        )
        parts.append(
            "        # 사용 예: 제공된 DOM 컨텍스트(CSS 클래스·부모 HTML)를 참고해 인자 결정"
        )
        parts.append(
            "        # css_selector  → 선택된 요소의 CSS 클래스 (예: '.menu-label', '.item-text')"
        )
        parts.append(
            "        # parent_selector → 클릭 핸들러가 있는 부모 선택자 (예: '.menu-item', 'li')"
        )
        parts.append(
            "        click_visible_element(driver, '.menu-label', '메뉴명', parent_selector='.menu-item')"
        )
        parts.append("        ```")
        parts.append(
            "     ⑧ 🌟중요(TAB 키 후 입력): TAB으로 포커스를 이동한 다음에는 원래 요소 변수가 아닌"
        )
        parts.append(
            "        반드시 driver.switch_to.active_element로 현재 포커스 요소에 입력하세요."
        )
        parts.append(
            "        원래 요소 변수는 포커스 이동과 무관하게 그 요소에만 전송되므로 다음 필드에 입력이 안 됩니다:"
        )
        parts.append("        ```python")
        parts.append("        # ❌ 잘못된 예: TAB 후에도 login_input(ID 필드)에 PW가 입력됨")
        parts.append("        login_input.send_keys('아이디')")
        parts.append("        login_input.send_keys(Keys.TAB)")
        parts.append("        login_input.send_keys('비밀번호')  # ← ID 필드에 입력됨! 버그!")
        parts.append("        # ✅ 올바른 예: TAB 후 active_element로 현재 포커스 요소에 입력")
        parts.append("        login_input.send_keys('아이디')")
        parts.append("        login_input.send_keys(Keys.TAB)")
        parts.append(
            "        driver.switch_to.active_element.send_keys('비밀번호')  # PW 필드에 정확히 입력"
        )
        parts.append("        driver.switch_to.active_element.send_keys(Keys.ENTER)")
        parts.append("        ```")
        parts.append(
            "     ⑨ 🌟중요(로그인·폼 제출 후 대기): Enter/클릭으로 로그인하거나 페이지가 이동하면"
        )
        parts.append(
            "        반드시 다음 요소가 나타날 때까지 기다린 후 클릭하세요. 즉시 클릭하면 요소를 찾지 못합니다:"
        )
        parts.append("        ```python")
        parts.append("        # 로그인 Enter 전송 후 — 다음 페이지의 특정 요소 대기")
        parts.append("        element.send_keys(Keys.ENTER)")
        parts.append(
            "        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, '//*[@title=\"메뉴명\"]')))"
        )
        parts.append("        # 또는 URL 변경 대기")
        parts.append("        WebDriverWait(driver, 15).until(EC.url_changes(driver.current_url))")
        parts.append("        time.sleep(1)  # SPA 프레임워크 메뉴 렌더링 추가 대기")
        parts.append("        ```")

    def build_object_analysis_prompt(self, image_description: str = "") -> str:
        """객체 분석용 프롬프트를 생성합니다."""
        template = self.templates.get("object_analysis", "")
        parts = [template]
        if image_description:
            parts.append(f"\n추가 정보: {image_description}")
        return "\n".join(parts)

    def build_error_recovery_prompt(self, error_message: str, current_code: str) -> str:
        """에러 복구용 프롬프트를 생성합니다."""
        parts = [
            "코드 실행 중 오류가 발생했습니다. 수정된 전체 코드를 ```python 블록으로 작성하세요.",
            "",
            "## 에러:",
            f"```\n{error_message}\n```",
            "",
            "## 현재 코드:",
            f"```python\n{current_code}\n```",
            "",
            "## 규칙:",
            "- 반드시 ```python 코드블록을 포함하세요",
            "- 에러를 해결한 전체 코드를 반환하세요",
        ]
        return "\n".join(parts)

    def build_project_export_prompt(
        self,
        project_name: str,
        project_description: str,
        project_type: str,
        full_code: str,
        packages_list: str,
    ) -> str:
        """프로젝트 내보내기용 README 생성 프롬프트"""
        template = self.templates.get("project_export", "")
        if template:
            return template.format(
                project_name=project_name,
                project_description=project_description,
                project_type=project_type,
                full_code=full_code,
                packages_list=packages_list,
            )
        return ""

    def _build_steps_summary(self, session, max_steps: int = 5) -> str:
        """이전 스텝들의 요약 텍스트를 생성합니다."""
        steps = session.steps
        if not steps:
            return ""

        recent_steps = steps[-max_steps:]
        summary_lines = []

        for step_data in recent_steps:
            step = step_data if isinstance(step_data, dict) else {}
            step_id = step.get("step_id", "?")
            status = step.get("status", "unknown")
            conv = step.get("conversation", [])

            user_msg = ""
            for msg in conv:
                m = msg if isinstance(msg, dict) else {}
                if m.get("role") == "user":
                    user_msg = m.get("content", "")[:100]
                    break

            status_icon = "✅" if status == "completed" else "❌" if status == "failed" else "⏳"
            summary_lines.append(f"- 스텝 {step_id} {status_icon}: {user_msg}")

        return "\n".join(summary_lines)

    def _get_current_code(self, session) -> tuple[str, bool]:
        """
        세션의 누적 코드와 수동 편집 여부를 반환합니다.

        step_code가 진짜 delta(새로 추가된 코드만)인 경우에만 경계 주석 조합을 사용합니다.
        step_code가 누적 코드(전체 반복 저장)인 경우에는 마지막 generated_code를 그대로 반환합니다.
        """
        steps = session.steps
        if not steps:
            return "", False

        # 마지막 스텝의 수동 편집 여부 확인
        manually_edited = False
        for step_data in reversed(steps):
            step = step_data if isinstance(step_data, dict) else {}
            if step.get("generated_code", "").strip():
                manually_edited = bool(step.get("manually_edited", False))
                break

        # step_code가 delta인지 누적 코드인지 판단:
        # step_code 총합이 마지막 generated_code보다 50% 이상 크면 누적 코드로 판단
        from core.import_manager import assemble_script, extract_imports, merge_imports

        last_gc = ""
        for step_data in reversed(steps):
            s = step_data if isinstance(step_data, dict) else {}
            if s.get("generated_code", "").strip():
                last_gc = s["generated_code"]
                break

        total_step_code_len = sum(
            len((s if isinstance(s, dict) else {}).get("step_code", "")) for s in steps
        )
        last_gc_len = len(last_gc)
        step_codes_are_deltas = last_gc_len == 0 or total_step_code_len <= last_gc_len * 1.5

        if step_codes_are_deltas:
            all_imports = []
            step_entries = []

            for step_data in steps:
                step = step_data if isinstance(step_data, dict) else {}
                step_imports = step.get("step_imports", [])
                step_code = step.get("step_code", "")

                if not step_code:
                    code = step.get("generated_code", "")
                    if code:
                        step_imports, step_code = extract_imports(code)
                    else:
                        continue

                all_imports.append(step_imports)

                task_name = ""
                for msg in step.get("conversation", []):
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        task_name = msg.get("content", "")
                        break
                if not task_name:
                    task_name = f"작업 {step.get('step_id', '?')}"

                step_entries.append((step.get("step_id", 0), task_name, step_code))

            if step_entries:
                merged = merge_imports(all_imports)
                return assemble_script(merged, step_entries), manually_edited

        # 폴백: step_code가 누적 코드이거나 없는 경우 → 마지막 generated_code 반환
        if last_gc.strip():
            return last_gc, manually_edited

        return "", False

    def _compress_accumulated_code(self, code: str, keep_last_n: int = 1) -> tuple[str, int]:
        """누적 코드의 이전 step body 를 마커만 남기고 압축. 마지막 N step body 만 keep.

        5/6 사용자 결정: prompt size 폭증 (35K+) 시 Gemini corrupt 응답 (`<ctrl46>`) trigger.
        이전 step body 는 사용자 요청별로 독립적이므로 (try/except 본문) AI 새 step 생성 시
        대부분 불필요. import + 마지막 1 step body 는 keep — 변수 시그니처 + 가장 가까운 context.

        Args:
            code: 누적 코드 (assemble_script 결과 — `# === Step N: ... (시작/끝) ===` 마커 포함)
            keep_last_n: 마지막 N step body 는 그대로 keep (default 1)

        Returns:
            (compressed_code, num_summarized_steps): 압축된 코드 + 생략된 step 수
        """
        if not code:
            return code, 0
        # `# === Step N: <task> (시작) === ... # === Step N: <task> (끝) ===` 매칭
        pattern = re.compile(
            r"(# === Step (\d+): (.*?) \(시작\) ===)(.*?)(# === Step \2: .*? \(끝\) ===)",
            re.DOTALL,
        )
        matches = list(pattern.finditer(code))
        if len(matches) <= keep_last_n:
            return code, 0
        summarize_until = len(matches) - keep_last_n
        # 뒤에서 앞으로 replace — offset 깨짐 방지
        out = code
        for i in range(summarize_until - 1, -1, -1):
            m = matches[i]
            step_id = m.group(2)
            task_name = m.group(3).strip()
            replacement = (
                f"# === Step {step_id}: {task_name} "
                f"(본문 생략 — 이미 실행됨, 정의된 변수/import 는 그대로 사용 가능) ==="
            )
            out = out[: m.start()] + replacement + out[m.end() :]
        return out, summarize_until

    def _get_last_edit_diff(self, session) -> str:
        """
        수동 편집된 마지막 스텝의 변경 내역을 diff 형태로 반환합니다.
        변경된 줄만 '- 이전값' / '+ 새값' 형식으로 표시합니다.
        """
        for step_data in reversed(session.steps):
            step = step_data if isinstance(step_data, dict) else {}
            if not step.get("manually_edited"):
                continue
            old_code = step.get("edit_original_code", "")
            new_code = step.get("generated_code", "")
            if not old_code or not new_code:
                return ""

            old_lines = old_code.splitlines()
            new_lines = new_code.splitlines()
            diff_lines = []
            for old_line, new_line in zip(old_lines, new_lines):
                if old_line != new_line:
                    diff_lines.append(f"- {old_line.rstrip()}")
                    diff_lines.append(f"+ {new_line.rstrip()}")
            # 줄 수 차이가 나는 경우 추가/삭제된 줄 표시
            for line in old_lines[len(new_lines) :]:
                diff_lines.append(f"- {line.rstrip()}")
            for line in new_lines[len(old_lines) :]:
                diff_lines.append(f"+ {line.rstrip()}")

            return "\n".join(diff_lines)

        return ""
