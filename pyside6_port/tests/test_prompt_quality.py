# SPDX-License-Identifier: AGPL-3.0-or-later
"""
프롬프트 품질 테스트

AI에게 전달되는 프롬프트와 컨텍스트의 품질을 검증합니다.
AI 호출 없이 프롬프트 구조와 내용만 검증하므로 빠르게 실행됩니다.

테스트 대상:
- 프롬프트에 필수 지침이 포함되는지
- 윈도우/요소 컨텍스트가 올바르게 삽입되는지
- 누적 코드가 정확하게 유지되는지
- 에러 복구 프롬프트가 적절한지
- 브라우저/데스크톱 분기가 올바른지
- 수동 편집 diff가 보존되는지

실행:
    cd ai_rpa_solution
    python -m tests.test_runner --suite prompt_quality
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_runner import TestCase


class PromptQualityTest(TestCase):
    suite = "prompt_quality"

    def _make_session(self, steps=None, project_type="desktop"):
        """테스트용 세션 객체 생성 헬퍼"""
        from core.session_manager import Session

        session = Session(session_id="test", title="테스트 세션", project_type=project_type)
        if steps:
            session.steps = steps
        return session

    def _make_builder(self):
        from core.prompt_builder import PromptBuilder

        return PromptBuilder(prompts_config={})

    # ──────────────────────────────────────────
    # 1. 기본 프롬프트 구조 검증
    # ──────────────────────────────────────────

    def test_01_user_request_at_top(self):
        """사용자 요청이 프롬프트 최상단에 위치하는지 확인"""
        builder = self._make_builder()
        session = self._make_session()

        prompt = builder.build_step_prompt(session=session, user_request="메모장을 열어줘")

        lines = prompt.strip().split("\n")
        first_line = lines[0]
        self.assert_contains(
            first_line,
            "메모장을 열어줘",
            "사용자 요청이 프롬프트 첫 줄에 있어야 합니다 (AI가 무시하지 못하도록)",
        )

    def test_02_code_block_rule_present(self):
        """```python 코드블록 생성 규칙이 포함되는지"""
        builder = self._make_builder()
        session = self._make_session()

        prompt = builder.build_step_prompt(session=session, user_request="버튼을 클릭해줘")

        self.assert_contains(prompt, "```python", "코드블록 형식 지시가 있어야 합니다")
        self.assert_contains(prompt, "즉시 실행 가능", "실행 가능한 코드 요구가 있어야 합니다")
        self.assert_contains(prompt, "import", "import문 포함 규칙이 있어야 합니다")

    def test_03_automation_guides_present(self):
        """pywinauto / Selenium / pyautogui 가이드가 모두 포함되는지"""
        builder = self._make_builder()
        session = self._make_session()

        prompt = builder.build_step_prompt(session=session, user_request="앱을 자동화해줘")

        self.assert_contains(prompt, "pywinauto", "pywinauto 가이드가 포함되어야 합니다")
        self.assert_contains(prompt, "Selenium", "Selenium 가이드가 포함되어야 합니다")
        self.assert_contains(prompt, "pyautogui", "pyautogui 가이드가 포함되어야 합니다")
        self.assert_contains(prompt, "subprocess", "subprocess 가이드가 포함되어야 합니다")

    def test_04_uwp_app_guidance(self):
        """UWP 앱 (Windows 11 메모장 등) 연결 가이드가 있는지"""
        builder = self._make_builder()
        session = self._make_session()

        prompt = builder.build_step_prompt(session=session, user_request="메모장 열어줘")

        self.assert_contains(prompt, "Desktop", "Desktop() 사용 가이드가 있어야 합니다 (UWP 앱)")
        self.assert_contains(prompt, "found_index=0", "found_index=0 필수 규칙이 있어야 합니다")
        self.assert_contains(prompt, "visible_only=True", "visible_only=True 규칙이 있어야 합니다")

    def test_05_selenium_best_practices(self):
        """Selenium 핵심 규칙 (script 제외, JS click, detach 등)이 포함되는지"""
        builder = self._make_builder()
        session = self._make_session()

        prompt = builder.build_step_prompt(session=session, user_request="웹 자동화 해줘")

        self.assert_contains(prompt, "detach", "detach=True 규칙이 있어야 합니다")
        self.assert_contains(
            prompt, "not(self::script)", "XPath에서 script 태그 제외 규칙이 있어야 합니다"
        )
        self.assert_contains(
            prompt, "visibility_of_element_located", "visibility 대기 규칙이 있어야 합니다"
        )
        self.assert_contains(prompt, "execute_script", "JS click 가이드가 있어야 합니다")

    # ──────────────────────────────────────────
    # 2. 누적 코드 컨텍스트 검증
    # ──────────────────────────────────────────

    def test_06_accumulated_code_preserved(self):
        """이전 스텝의 코드가 프롬프트에 정확히 포함되는지"""
        builder = self._make_builder()
        prev_code = (
            "import subprocess\n"
            "import time\n"
            "subprocess.Popen('notepad.exe')\n"
            "time.sleep(2)\n"
            "print('메모장 열림')"
        )
        session = self._make_session(
            steps=[{"step_id": 1, "status": "completed", "generated_code": prev_code}]
        )

        prompt = builder.build_step_prompt(session=session, user_request="텍스트 입력해줘")

        self.assert_contains(
            prompt, "subprocess.Popen('notepad.exe')", "이전 스텝의 코드가 그대로 포함되어야 합니다"
        )
        self.assert_contains(
            prompt, "print('메모장 열림')", "이전 코드의 마지막 줄까지 포함되어야 합니다"
        )
        self.assert_contains(prompt, "누적 코드", "누적 코드 안내가 있어야 합니다")
        self.assert_contains(prompt, "삭제하거나", "코드 삭제 금지 규칙이 있어야 합니다")

    def test_07_multi_step_code_chain(self):
        """여러 스텝의 코드 중 마지막 누적 코드만 포함되는지"""
        builder = self._make_builder()
        session = self._make_session(
            steps=[
                {"step_id": 1, "status": "completed", "generated_code": "print('step1')"},
                {
                    "step_id": 2,
                    "status": "completed",
                    "generated_code": "print('step1')\nprint('step2')",
                },
                {
                    "step_id": 3,
                    "status": "completed",
                    "generated_code": "print('step1')\nprint('step2')\nprint('step3')",
                },
            ]
        )

        prompt = builder.build_step_prompt(session=session, user_request="다음 작업")

        # 마지막 스텝의 누적 코드 (step1+step2+step3)가 포함되어야 함
        self.assert_contains(prompt, "print('step3')", "마지막 스텝의 코드가 포함되어야 합니다")

    def test_08_no_code_first_step(self):
        """첫 스텝 (이전 코드 없음)일 때 누적 코드 섹션이 없는지"""
        builder = self._make_builder()
        session = self._make_session(steps=[])

        prompt = builder.build_step_prompt(session=session, user_request="메모장 열어줘")

        self.assert_true("누적 코드" not in prompt, "첫 스텝에서는 누적 코드 섹션이 없어야 합니다")

    # ──────────────────────────────────────────
    # 3. 윈도우/요소 컨텍스트 삽입 검증
    # ──────────────────────────────────────────

    def test_09_window_context_injection(self):
        """WindowInspector 결과가 프롬프트에 정확히 삽입되는지"""
        builder = self._make_builder()
        session = self._make_session()

        window_ctx = (
            "## 대상 윈도우: 메모장\n"
            "### UI 컨트롤 목록:\n"
            '- [Edit] "" (id=15)\n'
            '- [Button] "파일" (id=menuFile)'
        )
        prompt = builder.build_step_prompt(
            session=session, user_request="텍스트 입력해줘", window_context=window_ctx
        )

        self.assert_contains(
            prompt, "대상 윈도우: 메모장", "윈도우 컨텍스트가 프롬프트에 포함되어야 합니다"
        )
        self.assert_contains(prompt, "menuFile", "UI 컨트롤 정보가 포함되어야 합니다")
        self.assert_contains(prompt, "활용하여", "컨트롤 정보 활용 지시가 있어야 합니다")

    def test_10_element_context_desktop(self):
        """데스크톱 요소 선택 시 pywinauto 지시가 삽입되는지"""
        builder = self._make_builder()
        session = self._make_session()

        element_ctx = "## 선택된 UI 요소 (데스크톱 앱)\n- **타입**: Button\n- **이름**: 확인"
        prompt = builder.build_step_prompt(
            session=session,
            user_request="이 버튼을 클릭해줘",
            element_context=element_ctx,
            is_browser_element=False,
        )

        self.assert_contains(
            prompt, "pywinauto 코드를 작성", "데스크톱 요소일 때 pywinauto 지시가 있어야 합니다"
        )

    def test_11_element_context_browser(self):
        """브라우저 요소 선택 시 Selenium 지시가 삽입되는지"""
        builder = self._make_builder()
        session = self._make_session()

        element_ctx = "## 선택된 UI 요소 (브라우저: Chrome)\n- **타입**: Button\n- **이름**: 로그인"
        prompt = builder.build_step_prompt(
            session=session,
            user_request="이 버튼을 클릭해줘",
            element_context=element_ctx,
            is_browser_element=True,
        )

        self.assert_contains(
            prompt, "Selenium 코드를 작성", "브라우저 요소일 때 Selenium 지시가 있어야 합니다"
        )

    # ──────────────────────────────────────────
    # 4. 에러 복구 프롬프트 검증
    # ──────────────────────────────────────────

    def test_12_error_recovery_contains_all_parts(self):
        """에러 복구 프롬프트에 에러/코드/수정 지시가 모두 포함되는지"""
        builder = self._make_builder()

        error_msg = "ElementNotFoundError: Button '확인' not found"
        code = "from pywinauto import Application\napp = Application().connect(title='앱')\nwin = app.top_window()\nwin.child_window(title='확인').click()"

        prompt = builder.build_error_recovery_prompt(error_msg, code)

        self.assert_contains(prompt, "ElementNotFoundError", "에러 메시지가 포함되어야 합니다")
        self.assert_contains(prompt, "child_window", "현재 코드가 포함되어야 합니다")
        self.assert_contains(prompt, "```python", "수정된 코드 형식 지시가 있어야 합니다")
        self.assert_contains(prompt, "수정", "수정 요청 지시가 있어야 합니다")

    def test_13_error_context_in_step_prompt(self):
        """스텝 프롬프트에 에러 컨텍스트가 올바르게 삽입되는지"""
        builder = self._make_builder()
        session = self._make_session()

        prompt = builder.build_step_prompt(
            session=session,
            user_request="다시 시도해줘",
            error_context="TimeoutError: 윈도우를 찾을 수 없습니다",
        )

        self.assert_contains(prompt, "TimeoutError", "에러 메시지가 프롬프트에 포함되어야 합니다")
        self.assert_contains(prompt, "수정", "에러 해결 요청이 있어야 합니다")

    # ──────────────────────────────────────────
    # 5. 수동 편집 보존 검증
    # ──────────────────────────────────────────

    def test_14_manual_edit_preservation(self):
        """사용자가 수동 편집한 코드가 보존되도록 프롬프트에 경고가 포함되는지"""
        builder = self._make_builder()
        session = self._make_session(
            steps=[
                {
                    "step_id": 1,
                    "status": "completed",
                    "generated_code": "login('user123', 'new_password')",
                    "manually_edited": True,
                    "edit_original_code": "login('user123', 'old_password')",
                }
            ]
        )

        prompt = builder.build_step_prompt(session=session, user_request="다음 단계 진행")

        self.assert_contains(prompt, "직접 수정", "수동 편집 안내가 있어야 합니다")
        self.assert_contains(prompt, "유지", "변경사항 유지 지시가 있어야 합니다")

    def test_15_manual_edit_diff_included(self):
        """수동 편집 diff가 프롬프트에 포함되는지"""
        builder = self._make_builder()
        session = self._make_session(
            steps=[
                {
                    "step_id": 1,
                    "status": "completed",
                    "generated_code": "url = 'https://correct-site.com'",
                    "manually_edited": True,
                    "edit_original_code": "url = 'https://wrong-site.com'",
                }
            ]
        )

        prompt = builder.build_step_prompt(session=session, user_request="로그인해줘")

        # diff에 이전값과 새값이 모두 표시되어야 함
        self.assert_contains(prompt, "wrong-site.com", "diff에 이전 값이 표시되어야 합니다")
        self.assert_contains(prompt, "correct-site.com", "diff에 새 값이 표시되어야 합니다")

    # ──────────────────────────────────────────
    # 6. 코드 생성 규칙 완성도 검증
    # ──────────────────────────────────────────

    def test_16_no_question_rule(self):
        """'질문하지 말고 코드를 생성하라'는 규칙이 있는지"""
        builder = self._make_builder()
        session = self._make_session()

        prompt = builder.build_step_prompt(session=session, user_request="뭔가 해줘")

        self.assert_contains(
            prompt, "질문하지 말고", "'질문하지 말고 코드 생성' 규칙이 있어야 합니다"
        )

    def test_17_korean_output_rule(self):
        """한국어 출력 규칙이 있는지"""
        builder = self._make_builder()
        session = self._make_session()

        prompt = builder.build_step_prompt(session=session, user_request="테스트")

        self.assert_contains(prompt, "한국어", "한국어 출력 규칙이 있어야 합니다")

    def test_18_previous_code_keep_rule_with_existing_code(self):
        """이전 코드가 있을 때 '삭제/주석 금지' 규칙이 강화되는지"""
        builder = self._make_builder()
        session = self._make_session(
            steps=[{"step_id": 1, "status": "completed", "generated_code": "print('existing')"}]
        )

        prompt = builder.build_step_prompt(session=session, user_request="새 기능 추가")

        self.assert_contains(
            prompt, "이전 스텝의 모든 코드", "이전 코드 유지 규칙이 강화되어야 합니다"
        )
        self.assert_contains(
            prompt, "별도 함수로 분리하지 마세요", "별도 함수 분리 금지 규칙이 있어야 합니다"
        )

    # ──────────────────────────────────────────
    # 7. WindowInspector 코드 템플릿 품질
    # ──────────────────────────────────────────

    def test_19_inspector_dpi_awareness_in_code(self):
        """생성되는 pywinauto 코드에 DPI Awareness 설정이 포함되는지"""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        element = {
            "control_type": "Button",
            "name": "OK",
            "automation_id": "btnOK",
            "class_name": "Button",
            "rect": {"left": 100, "top": 200, "width": 80, "height": 30},
            "parent_window_title": "앱",
            "is_browser": False,
            "detected_backend": "uia",
            "recommended_backend": "uia",
        }
        code = inspector.get_element_info_text(element)

        self.assert_contains(
            code, "SetProcessDpiAwareness", "DPI Awareness 설정이 코드에 포함되어야 합니다"
        )
        self.assert_contains(
            code, "FAILSAFE = False", "pyautogui FAILSAFE 비활성화가 포함되어야 합니다"
        )

    def test_20_inspector_admin_privilege_warning(self):
        """관리자 권한 앱에 대한 경고와 pyautogui 폴백이 포함되는지"""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        element = {
            "control_type": "Button",
            "name": "저장",
            "automation_id": "btnSave",
            "class_name": "Button",
            "rect": {"left": 200, "top": 300, "width": 60, "height": 25},
            "parent_window_title": "관리자 앱",
            "is_browser": False,
            "detected_backend": "uia",
            "recommended_backend": "uia",
        }
        code = inspector.get_element_info_text(element)

        self.assert_contains(code, "관리자", "관리자 권한 경고가 있어야 합니다")
        self.assert_contains(code, "pyautogui.click", "pyautogui 폴백 코드가 있어야 합니다")
        self.assert_contains(
            code, "SetForegroundWindow", "창을 전면으로 가져오는 코드가 있어야 합니다"
        )

    def test_21_inspector_dynamic_coordinates(self):
        """생성 코드가 하드코딩 좌표가 아닌 동적 좌표를 사용하는지"""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        element = {
            "control_type": "Button",
            "name": "확인",
            "automation_id": "btnOK",
            "class_name": "Button",
            "rect": {"left": 350, "top": 450, "width": 80, "height": 30},
            "parent_window_title": "설정",
            "is_browser": False,
            "detected_backend": "uia",
            "recommended_backend": "uia",
        }
        code = inspector.get_element_info_text(element)

        self.assert_contains(
            code,
            "element.rectangle()",
            "실행 시점에 동적으로 좌표를 가져와야 합니다 (하드코딩 금지)",
        )
        self.assert_contains(code, "center_x", "중심 좌표 계산이 있어야 합니다")

    def test_22_inspector_click_target_verification(self):
        """클릭 전 대상 창 확인 코드가 포함되는지"""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        element = {
            "control_type": "Button",
            "name": "실행",
            "automation_id": "btnRun",
            "class_name": "Button",
            "rect": {"left": 100, "top": 100, "width": 80, "height": 30},
            "parent_window_title": "앱",
            "is_browser": False,
            "detected_backend": "uia",
            "recommended_backend": "uia",
        }
        code = inspector.get_element_info_text(element)

        self.assert_contains(
            code, "WindowFromPoint", "클릭 좌표에 올바른 창이 있는지 확인하는 코드가 있어야 합니다"
        )

    # ──────────────────────────────────────────
    # 8. 코드 추출기 품질 검증
    # ──────────────────────────────────────────

    def test_23_extract_code_from_markdown(self):
        """AI 응답에서 ```python 블록 추출이 정확한지"""
        from core.adapters.base_adapter import BaseAIAdapter

        response = """메모장을 여는 코드입니다.

```python
import subprocess
subprocess.Popen('notepad.exe')
print('열림')
```

위 코드를 실행하면 메모장이 열립니다."""

        code = BaseAIAdapter.extract_code_from_response(response)
        self.assert_contains(code, "subprocess.Popen", "코드 추출이 정확해야 합니다")
        self.assert_true("열림" in code, "print문도 포함되어야 합니다")
        self.assert_true("메모장을 여는" not in code, "설명 텍스트는 제외되어야 합니다")

    def test_24_extract_code_multiple_blocks(self):
        """여러 코드 블록이 있을 때 마지막(최종) 블록을 추출하는지"""
        from core.adapters.base_adapter import BaseAIAdapter

        response = """첫 번째 시도:
```python
print('old code')
```

수정된 코드:
```python
import time
print('new code')
time.sleep(1)
```"""

        code = BaseAIAdapter.extract_code_from_response(response)
        self.assert_contains(code, "new code", "마지막 코드 블록이 추출되어야 합니다")
        self.assert_true("old code" not in code, "이전 코드 블록은 제외되어야 합니다")

    def test_25_extract_packages_accuracy(self):
        """import문에서 패키지 추출이 정확한지"""
        from core.adapters.base_adapter import BaseAIAdapter

        code = """import pyautogui
import time
from pywinauto import Application
from selenium.webdriver.common.by import By
import os
import subprocess
"""
        packages = BaseAIAdapter.extract_packages_from_code(code)
        self.assert_true("pyautogui" in packages, "pyautogui가 추출되어야 합니다")
        self.assert_true("pywinauto" in packages, "pywinauto가 추출되어야 합니다")
        self.assert_true("selenium" in packages, "selenium이 추출되어야 합니다")
        # 표준 라이브러리는 제외
        self.assert_true("time" not in packages, "time은 표준 라이브러리이므로 제외되어야 합니다")
        self.assert_true("os" not in packages, "os는 표준 라이브러리이므로 제외되어야 합니다")

    # ──────────────────────────────────────────
    # 6. WinInspector.should_use_selenium 라우팅 결정 (브라우저 chrome vs DOM)
    # ──────────────────────────────────────────

    def test_26_selenium_routing_matrix(self):
        """should_use_selenium 의 라우팅 매트릭스 검증.

        | browser? | CDP? | tagName? | 결정     |
        |----------|------|----------|----------|
        | No       | -    | -        | False    |
        | Yes      | Yes  | 있음     | True     |
        | Yes      | Yes  | 없음     | False    |
        | Yes      | No   | -        | False    |  ← Selenium 으로 가면 새 Chrome 띄워 기존 페이지 못 찾음

        Selenium 은 CDP 가 실제 응답하고 DOM 까지 있을 때만 사용. 그 외는 모두 pywinauto
        (사용자가 본 그 윈도우에 connect 가능 + pyautogui 좌표 클릭으로 HTML 콘텐츠도 OK).
        """
        from core.win_inspector import WindowInspector

        # 케이스 A: Chrome 페이지 button + CDP+DOM → Selenium
        page_dom_elem = {
            "is_browser": True,
            "browser_type": "Chrome",
            "control_type": "Button",
            "name": "검색",
            "automation_id": "search-btn",
            "dom_context": {
                "cdp_available": True,
                "tagName": "button",
                "attributes": {"id": "real-html-id", "class": "btn-primary"},
            },
        }
        self.assert_true(
            WindowInspector.should_use_selenium(page_dom_elem),
            "CDP+DOM 있는 페이지 요소는 Selenium 경로",
        )

        # 케이스 B: Chrome 탭 + CDP 있지만 tagName 없음 → pywinauto (chrome UI)
        chrome_tab_elem = {
            "is_browser": True,
            "browser_type": "Chrome",
            "control_type": "TabItem",
            "name": "typing.works - Chrome",
            "automation_id": "view_20",
            "class_name": "Tab",
            "dom_context": {"cdp_available": True, "tagName": ""},
        }
        self.assert_equal(
            WindowInspector.should_use_selenium(chrome_tab_elem),
            False,
            "CDP 응답이 tagName 없음 = browser chrome 확정 → pywinauto",
        )

        # 케이스 C: Chrome + CDP 미연결 → pywinauto
        # (Selenium 은 attach 불가하니 새 Chrome 띄워 사용자 보던 페이지 못 찾음.
        #  pywinauto + pyautogui 가 사용자가 본 그 윈도우/element 를 정확히 클릭.)
        chrome_no_cdp = {
            "is_browser": True,
            "browser_type": "Chrome",
            "control_type": "Button",
            "name": "버튼",
            "dom_context": {"cdp_available": False},
        }
        self.assert_equal(
            WindowInspector.should_use_selenium(chrome_no_cdp),
            False,
            "CDP 없으면 Selenium attach 불가 → pywinauto + pyautogui",
        )

        # 케이스 D: 데스크톱 앱 → pywinauto
        desktop_elem = {
            "is_browser": False,
            "control_type": "Edit",
            "name": "메모장 본문",
        }
        self.assert_equal(
            WindowInspector.should_use_selenium(desktop_elem),
            False,
            "비-브라우저 데스크톱 앱은 항상 pywinauto",
        )

        # 케이스 E: dom_context 키 자체 없음 → False (안전한 default)
        legacy_elem = {"browser_type": "Chrome", "control_type": "Button", "name": "x"}
        self.assert_equal(
            WindowInspector.should_use_selenium(legacy_elem),
            False,
            "dom_context 정보 자체 없음 → Selenium 으로 보내는 건 위험 (pywinauto)",
        )

        # 케이스 F: 비-브라우저 + dom_context 도 없음 → False
        plain_desktop = {"control_type": "Button", "name": "확인"}
        self.assert_equal(
            WindowInspector.should_use_selenium(plain_desktop),
            False,
            "browser_type 자체가 없으면 항상 pywinauto",
        )

    def test_27_browser_chrome_with_cdp_routes_to_pywinauto(self):
        """CDP 가 응답했지만 tagName 없으면 (= browser chrome UI 확정) pywinauto path"""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        # CDP 가 응답했지만 (cdp_available=True) tagName 이 비어있음 → 탭/메뉴 같은 chrome UI
        chrome_tab_with_cdp = {
            "is_browser": True,
            "browser_type": "Chrome",
            "control_type": "TabItem",
            "name": "typing.works - Chrome",
            "automation_id": "view_20",
            "class_name": "Tab",
            "rect": {"left": 906, "top": 77, "width": 149, "height": 41},
            "parent_window_title": "snipaste 요소 - Google 검색 - Chrome",
            "parent_window_class": "Chrome_WidgetWin_1",
            "dom_context": {"cdp_available": True, "tagName": ""},
            "screen_x": 980,
            "screen_y": 97,
        }
        text = inspector.get_element_info_text(chrome_tab_with_cdp)

        self.assert_contains(text, "데스크톱", "CDP 확정한 chrome UI 는 desktop path")
        self.assert_contains(text, "pywinauto", "pywinauto 자동화 방식")
        self.assert_contains(
            text,
            "snipaste 요소 - Google 검색 - Chrome",
            "parent_window_title runtime 값 사용 (하드코딩 0)",
        )
        self.assert_true("HTML ID" not in text, "auto_id 를 'HTML ID' 로 잘못 라벨링하면 안 됨")

    def test_29_browser_no_cdp_routes_to_pywinauto_with_pyautogui_primary(self):
        """browser + CDP 미연결 → desktop path (pywinauto). 코드 템플릿이 pyautogui PRIMARY.

        Selenium 으로 가면 새 Chrome 띄워 사용자가 보던 페이지/탭 못 찾음.
        pywinauto 는 picker 의 parent_title 로 기존 윈도우에 connect 해서
        사용자가 본 element 를 정확히 찾고, pyautogui 좌표 클릭으로 GPU compositor
        영역까지 확실히 전달.
        """
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        # 사용자 세션 시나리오: Chrome 탭 클릭, CDP 미연결
        chrome_tab_no_cdp = {
            "is_browser": True,
            "browser_type": "Chrome",
            "control_type": "TabItem",
            "name": "typing.works - 메모리 사용량 - 94.1MB",
            "automation_id": "view_20",
            "class_name": "Tab",
            "rect": {"left": 867, "top": 142, "width": 149, "height": 41},
            "parent_window_title": "snipaste 요소 - Google 검색 - Chrome",
            "parent_window_class": "Chrome_WidgetWin_1",
            "dom_context": {"cdp_available": False},
        }
        text = inspector.get_element_info_text(chrome_tab_no_cdp)

        # desktop path 로 가야 함 (Selenium 새 Chrome 회피)
        self.assert_contains(text, "데스크톱", "browser+no-CDP 는 desktop path 헤더로")
        self.assert_contains(text, "pywinauto", "pywinauto 자동화 방식")

        # picker 의 parent_title 이 그대로 connect 에 사용 (사용자가 본 그 윈도우)
        self.assert_contains(
            text, "snipaste 요소 - Google 검색 - Chrome", "기존 Chrome 윈도우 title 로 connect"
        )

        # 핵심: 클릭 코드가 pyautogui 를 PRIMARY 로 사용해야 함
        # (Selenium 새 Chrome 안 띄움 + HTML 콘텐츠도 pyautogui 좌표 클릭으로 OK)
        self.assert_contains(text, "pyautogui PRIMARY", "browser process 라 pyautogui 가 PRIMARY")
        self.assert_contains(
            text,
            "pyautogui.click(center_x, center_y)",
            "코드 템플릿이 pyautogui.click 을 우선 호출",
        )

        # 새 브라우저 띄우는 webdriver.Chrome() 코드는 절대 안 들어감
        self.assert_true(
            "webdriver.Chrome" not in text,
            "browser+no-CDP 면 절대 새 webdriver.Chrome 띄우지 말 것",
        )

    def test_31_desktop_app_keeps_wm_click_primary(self):
        """비-브라우저 데스크톱 앱은 element.click() 을 PRIMARY 로 유지 (속도/정확성)."""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        notepad_btn = {
            "is_browser": False,
            "control_type": "Button",
            "name": "확인",
            "automation_id": "okBtn",
            "rect": {"left": 50, "top": 100, "width": 60, "height": 24},
            "parent_window_title": "메모장",
        }
        text = inspector.get_element_info_text(notepad_btn)

        # 데스크톱 앱은 WM 메시지 클릭이 빠르고 정확
        self.assert_contains(text, "element.click()", "데스크톱 앱은 element.click() PRIMARY")
        self.assert_true("pyautogui PRIMARY" not in text, "데스크톱 앱은 pyautogui PRIMARY 가 아님")

    # ──────────────────────────────────────────
    # 7. 회귀 방지 — 사용자 실제 세션 fixture 기반
    # ──────────────────────────────────────────

    def test_32_regression_chrome_tab_session_ce6aa624(self):
        """**회귀 방지** — 사용자 세션 ce6aa624 step 1 의 Chrome 탭 element_info.

        이 케이스는 여러 번 깨졌다 고쳐졌다를 반복했음. picker 가 Chrome 탭 (CDP 미연결) 을
        고를 때:
          1. **pywinauto 경로** 로 가야 함 (Selenium 새 browser 회피)
          2. picker 의 parent_window_title 로 기존 Chrome 윈도우에 connect
          3. 탭 name + TabItem control_type 으로 child_window
          4. **pyautogui PRIMARY** 로 클릭 (HTML 콘텐츠도 일관 동작)
        이 모든 항목이 깨지면 즉시 회귀 — 변경 후 반드시 prompt_quality 테스트 통과 확인.
        """
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        # 실제 사용자 세션 ce6aa624 (2026-04-28 21:30) step 1 의 element_info
        chrome_tab = {
            "is_browser": True,
            "browser_type": "Chrome",
            "control_type": "TabItem",
            "name": "typing.works - 메모리 사용량 - 94.1MB",
            "automation_id": "view_20",
            "class_name": "Tab",
            "rect": {"left": 872, "top": 26, "width": 149, "height": 41},
            "parent_window_title": "snipaste 요소 - Google 검색 - Chrome",
            "parent_window_class": "Chrome_WidgetWin_1",
            "dom_context": {"cdp_available": False},
            "screen_x": 946,
            "screen_y": 46,
        }

        # (1) 라우팅: should_use_selenium=False (pywinauto 경로)
        self.assert_equal(
            WindowInspector.should_use_selenium(chrome_tab),
            False,
            "[회귀] Chrome 탭 (CDP 미연결) 은 pywinauto 경로로 가야 함",
        )

        text = inspector.get_element_info_text(chrome_tab)

        # (2) 절대 새 webdriver.Chrome() 띄우는 코드가 안 들어가야 함
        self.assert_true(
            "webdriver.Chrome" not in text,
            "[회귀] Chrome 탭 picker 시 새 webdriver.Chrome() 코드 생성 금지",
        )

        # (3) pywinauto Application connect (기존 Chrome 윈도우에)
        self.assert_contains(text, "pywinauto", "[회귀] pywinauto 자동화 방식")
        self.assert_contains(text, "Application", "[회귀] Application connect")
        self.assert_contains(
            text,
            'title="snipaste 요소 - Google 검색 - Chrome"',
            "[회귀] picker 의 parent_window_title 로 기존 Chrome 에 connect",
        )

        # (4) 탭 element selector (UIA 정보 그대로 사용 — 하드코딩 0)
        self.assert_contains(
            text,
            'title="typing.works - 메모리 사용량 - 94.1MB"',
            "[회귀] 탭 name 으로 child_window selector 구성",
        )
        self.assert_contains(
            text,
            'control_type="TabItem"',
            "[회귀] 탭 control_type 으로 child_window selector 구성",
        )

        # (5) browser process 라 pyautogui PRIMARY 클릭
        self.assert_contains(
            text,
            "pyautogui.click(center_x, center_y)",
            "[회귀] browser process element 는 pyautogui PRIMARY 클릭",
        )

    def test_33_regression_html_text_session_ce6aa624(self):
        """**회귀 방지** — 사용자 세션 ce6aa624 step 2 의 HTML 페이지 Text element.

        Chrome 안 페이지의 'TYPING SETTING' Text element. CDP 미연결 케이스.
        직전 fix 들 사이에서 여러 번 라우팅이 흔들림. 동일 원칙 검증:
        pywinauto + pyautogui PRIMARY (Selenium 새 browser 안 띄움).
        """
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        page_text = {
            "is_browser": True,
            "browser_type": "Chrome",
            "control_type": "Text",
            "name": "TYPING SETTING",
            "rect": {"left": 913, "top": 365, "width": 92, "height": 18},
            "parent_window_title": "typing.works - Chrome",
            "parent_window_class": "Chrome_WidgetWin_1",
            "dom_context": {"cdp_available": False},
        }

        self.assert_equal(
            WindowInspector.should_use_selenium(page_text),
            False,
            "[회귀] Chrome 페이지 Text (CDP 미연결) 도 pywinauto 경로",
        )

        text = inspector.get_element_info_text(page_text)
        self.assert_true(
            "webdriver.Chrome" not in text,
            "[회귀] HTML 콘텐츠 picker 도 새 webdriver.Chrome() 금지",
        )
        self.assert_contains(
            text, 'title="typing.works - Chrome"', "[회귀] picker 의 parent_window_title 로 connect"
        )
        self.assert_contains(
            text, 'title="TYPING SETTING"', "[회귀] HTML 텍스트 element name 으로 selector"
        )
        self.assert_contains(
            text,
            "pyautogui.click(center_x, center_y)",
            "[회귀] browser process 는 pyautogui PRIMARY",
        )

    def test_30_desktop_app_no_browser_specific_guidance(self):
        """비-브라우저 데스크톱 앱은 브라우저 특화 가이드가 안 떠야 한다."""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        notepad_btn = {
            "is_browser": False,
            "control_type": "Button",
            "name": "확인",
            "automation_id": "okBtn",
            "rect": {"left": 50, "top": 100, "width": 60, "height": 24},
            "parent_window_title": "메모장",
        }
        text = inspector.get_element_info_text(notepad_btn)

        self.assert_true(
            "pyautogui PRIMARY" not in text,
            "비-브라우저 element 는 pyautogui PRIMARY 가 아니어야 함",
        )
        self.assert_true(
            "GPU compositor" not in text, "비-브라우저 element 에는 브라우저 한계 설명이 없어야 함"
        )

    def test_28_page_dom_with_cdp_uses_selenium_path(self):
        """CDP DOM 수집된 페이지 요소는 Selenium path 로"""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        page_button = {
            "is_browser": True,
            "browser_type": "Chrome",
            "control_type": "Button",
            "name": "Submit",
            "automation_id": "ui-button-42",
            "rect": {"left": 100, "top": 200, "width": 80, "height": 30},
            "parent_window_title": "Login - example.com - Chrome",
            "dom_context": {
                "cdp_available": True,
                "tagName": "button",
                "attributes": {"id": "submitBtn", "class": "primary"},
                "page_url": "https://example.com/login",
            },
        }
        text = inspector.get_element_info_text(page_button)

        self.assert_contains(text, "브라우저", "DOM 페이지 요소는 브라우저 path 헤더로")
        self.assert_contains(text, "Selenium", "Selenium 자동화 방식")
        self.assert_contains(text, "AutomationID", "auto_id 는 'AutomationID' 로 정확히 라벨")
        self.assert_true(
            "HTML ID" not in text or "HTML id 있음" in text,
            "auto_id 를 'HTML ID' 로 잘못 라벨링하면 안 됨",
        )


if __name__ == "__main__":
    from tests.test_runner import TestRunner

    runner = TestRunner(suite_name="prompt_quality")
    runner.add_test_class(PromptQualityTest)
    result = runner.run()
    runner.save_results(result)
