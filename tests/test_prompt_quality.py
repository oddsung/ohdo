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
        self.assert_contains(first_line, "메모장을 열어줘",
                             "사용자 요청이 프롬프트 첫 줄에 있어야 합니다 (AI가 무시하지 못하도록)")

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
        self.assert_contains(prompt, "not(self::script)",
                             "XPath에서 script 태그 제외 규칙이 있어야 합니다")
        self.assert_contains(prompt, "visibility_of_element_located",
                             "visibility 대기 규칙이 있어야 합니다")
        self.assert_contains(prompt, "execute_script",
                             "JS click 가이드가 있어야 합니다")

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
        session = self._make_session(steps=[
            {"step_id": 1, "status": "completed", "generated_code": prev_code}
        ])

        prompt = builder.build_step_prompt(session=session, user_request="텍스트 입력해줘")

        self.assert_contains(prompt, "subprocess.Popen('notepad.exe')",
                             "이전 스텝의 코드가 그대로 포함되어야 합니다")
        self.assert_contains(prompt, "print('메모장 열림')",
                             "이전 코드의 마지막 줄까지 포함되어야 합니다")
        self.assert_contains(prompt, "누적 코드", "누적 코드 안내가 있어야 합니다")
        self.assert_contains(prompt, "삭제하거나", "코드 삭제 금지 규칙이 있어야 합니다")

    def test_07_multi_step_code_chain(self):
        """여러 스텝의 코드 중 마지막 누적 코드만 포함되는지"""
        builder = self._make_builder()
        session = self._make_session(steps=[
            {"step_id": 1, "status": "completed", "generated_code": "print('step1')"},
            {"step_id": 2, "status": "completed", "generated_code": "print('step1')\nprint('step2')"},
            {"step_id": 3, "status": "completed",
             "generated_code": "print('step1')\nprint('step2')\nprint('step3')"},
        ])

        prompt = builder.build_step_prompt(session=session, user_request="다음 작업")

        # 마지막 스텝의 누적 코드 (step1+step2+step3)가 포함되어야 함
        self.assert_contains(prompt, "print('step3')", "마지막 스텝의 코드가 포함되어야 합니다")

    def test_08_no_code_first_step(self):
        """첫 스텝 (이전 코드 없음)일 때 누적 코드 섹션이 없는지"""
        builder = self._make_builder()
        session = self._make_session(steps=[])

        prompt = builder.build_step_prompt(session=session, user_request="메모장 열어줘")

        self.assert_true("누적 코드" not in prompt,
                         "첫 스텝에서는 누적 코드 섹션이 없어야 합니다")

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
            "- [Edit] \"\" (id=15)\n"
            "- [Button] \"파일\" (id=menuFile)"
        )
        prompt = builder.build_step_prompt(
            session=session,
            user_request="텍스트 입력해줘",
            window_context=window_ctx
        )

        self.assert_contains(prompt, "대상 윈도우: 메모장",
                             "윈도우 컨텍스트가 프롬프트에 포함되어야 합니다")
        self.assert_contains(prompt, "menuFile",
                             "UI 컨트롤 정보가 포함되어야 합니다")
        self.assert_contains(prompt, "활용하여",
                             "컨트롤 정보 활용 지시가 있어야 합니다")

    def test_10_element_context_desktop(self):
        """데스크톱 요소 선택 시 pywinauto 지시가 삽입되는지"""
        builder = self._make_builder()
        session = self._make_session()

        element_ctx = "## 선택된 UI 요소 (데스크톱 앱)\n- **타입**: Button\n- **이름**: 확인"
        prompt = builder.build_step_prompt(
            session=session,
            user_request="이 버튼을 클릭해줘",
            element_context=element_ctx,
            is_browser_element=False
        )

        self.assert_contains(prompt, "pywinauto 코드를 작성",
                             "데스크톱 요소일 때 pywinauto 지시가 있어야 합니다")

    def test_11_element_context_browser(self):
        """브라우저 요소 선택 시 Selenium 지시가 삽입되는지"""
        builder = self._make_builder()
        session = self._make_session()

        element_ctx = "## 선택된 UI 요소 (브라우저: Chrome)\n- **타입**: Button\n- **이름**: 로그인"
        prompt = builder.build_step_prompt(
            session=session,
            user_request="이 버튼을 클릭해줘",
            element_context=element_ctx,
            is_browser_element=True
        )

        self.assert_contains(prompt, "Selenium 코드를 작성",
                             "브라우저 요소일 때 Selenium 지시가 있어야 합니다")

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
            error_context="TimeoutError: 윈도우를 찾을 수 없습니다"
        )

        self.assert_contains(prompt, "TimeoutError", "에러 메시지가 프롬프트에 포함되어야 합니다")
        self.assert_contains(prompt, "수정", "에러 해결 요청이 있어야 합니다")

    # ──────────────────────────────────────────
    # 5. 수동 편집 보존 검증
    # ──────────────────────────────────────────

    def test_14_manual_edit_preservation(self):
        """사용자가 수동 편집한 코드가 보존되도록 프롬프트에 경고가 포함되는지"""
        builder = self._make_builder()
        session = self._make_session(steps=[
            {
                "step_id": 1,
                "status": "completed",
                "generated_code": "login('user123', 'new_password')",
                "manually_edited": True,
                "edit_original_code": "login('user123', 'old_password')",
            }
        ])

        prompt = builder.build_step_prompt(session=session, user_request="다음 단계 진행")

        self.assert_contains(prompt, "직접 수정", "수동 편집 안내가 있어야 합니다")
        self.assert_contains(prompt, "유지", "변경사항 유지 지시가 있어야 합니다")

    def test_15_manual_edit_diff_included(self):
        """수동 편집 diff가 프롬프트에 포함되는지"""
        builder = self._make_builder()
        session = self._make_session(steps=[
            {
                "step_id": 1,
                "status": "completed",
                "generated_code": "url = 'https://correct-site.com'",
                "manually_edited": True,
                "edit_original_code": "url = 'https://wrong-site.com'",
            }
        ])

        prompt = builder.build_step_prompt(session=session, user_request="로그인해줘")

        # diff에 이전값과 새값이 모두 표시되어야 함
        self.assert_contains(prompt, "wrong-site.com",
                             "diff에 이전 값이 표시되어야 합니다")
        self.assert_contains(prompt, "correct-site.com",
                             "diff에 새 값이 표시되어야 합니다")

    # ──────────────────────────────────────────
    # 6. 코드 생성 규칙 완성도 검증
    # ──────────────────────────────────────────

    def test_16_no_question_rule(self):
        """'질문하지 말고 코드를 생성하라'는 규칙이 있는지"""
        builder = self._make_builder()
        session = self._make_session()

        prompt = builder.build_step_prompt(session=session, user_request="뭔가 해줘")

        self.assert_contains(prompt, "질문하지 말고",
                             "'질문하지 말고 코드 생성' 규칙이 있어야 합니다")

    def test_17_korean_output_rule(self):
        """한국어 출력 규칙이 있는지"""
        builder = self._make_builder()
        session = self._make_session()

        prompt = builder.build_step_prompt(session=session, user_request="테스트")

        self.assert_contains(prompt, "한국어", "한국어 출력 규칙이 있어야 합니다")

    def test_18_previous_code_keep_rule_with_existing_code(self):
        """이전 코드가 있을 때 '삭제/주석 금지' 규칙이 강화되는지"""
        builder = self._make_builder()
        session = self._make_session(steps=[
            {"step_id": 1, "status": "completed", "generated_code": "print('existing')"}
        ])

        prompt = builder.build_step_prompt(session=session, user_request="새 기능 추가")

        self.assert_contains(prompt, "이전 스텝의 모든 코드",
                             "이전 코드 유지 규칙이 강화되어야 합니다")
        self.assert_contains(prompt, "별도 함수로 분리하지 마세요",
                             "별도 함수 분리 금지 규칙이 있어야 합니다")

    # ──────────────────────────────────────────
    # 7. WindowInspector 코드 템플릿 품질
    # ──────────────────────────────────────────

    def test_19_inspector_dpi_awareness_in_code(self):
        """생성되는 pywinauto 코드에 DPI Awareness 설정이 포함되는지"""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        element = {
            "control_type": "Button", "name": "OK", "automation_id": "btnOK",
            "class_name": "Button",
            "rect": {"left": 100, "top": 200, "width": 80, "height": 30},
            "parent_window_title": "앱",
            "is_browser": False,
            "detected_backend": "uia", "recommended_backend": "uia",
        }
        code = inspector.get_element_info_text(element)

        self.assert_contains(code, "SetProcessDpiAwareness",
                             "DPI Awareness 설정이 코드에 포함되어야 합니다")
        self.assert_contains(code, "FAILSAFE = False",
                             "pyautogui FAILSAFE 비활성화가 포함되어야 합니다")

    def test_20_inspector_admin_privilege_warning(self):
        """관리자 권한 앱에 대한 경고와 pyautogui 폴백이 포함되는지"""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        element = {
            "control_type": "Button", "name": "저장", "automation_id": "btnSave",
            "class_name": "Button",
            "rect": {"left": 200, "top": 300, "width": 60, "height": 25},
            "parent_window_title": "관리자 앱",
            "is_browser": False,
            "detected_backend": "uia", "recommended_backend": "uia",
        }
        code = inspector.get_element_info_text(element)

        self.assert_contains(code, "관리자", "관리자 권한 경고가 있어야 합니다")
        self.assert_contains(code, "pyautogui.click", "pyautogui 폴백 코드가 있어야 합니다")
        self.assert_contains(code, "SetForegroundWindow",
                             "창을 전면으로 가져오는 코드가 있어야 합니다")

    def test_21_inspector_dynamic_coordinates(self):
        """생성 코드가 하드코딩 좌표가 아닌 동적 좌표를 사용하는지"""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        element = {
            "control_type": "Button", "name": "확인", "automation_id": "btnOK",
            "class_name": "Button",
            "rect": {"left": 350, "top": 450, "width": 80, "height": 30},
            "parent_window_title": "설정",
            "is_browser": False,
            "detected_backend": "uia", "recommended_backend": "uia",
        }
        code = inspector.get_element_info_text(element)

        self.assert_contains(code, "element.rectangle()",
                             "실행 시점에 동적으로 좌표를 가져와야 합니다 (하드코딩 금지)")
        self.assert_contains(code, "center_x",
                             "중심 좌표 계산이 있어야 합니다")

    def test_22_inspector_click_target_verification(self):
        """클릭 전 대상 창 확인 코드가 포함되는지"""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        element = {
            "control_type": "Button", "name": "실행", "automation_id": "btnRun",
            "class_name": "Button",
            "rect": {"left": 100, "top": 100, "width": 80, "height": 30},
            "parent_window_title": "앱",
            "is_browser": False,
            "detected_backend": "uia", "recommended_backend": "uia",
        }
        code = inspector.get_element_info_text(element)

        self.assert_contains(code, "WindowFromPoint",
                             "클릭 좌표에 올바른 창이 있는지 확인하는 코드가 있어야 합니다")

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


if __name__ == "__main__":
    from tests.test_runner import TestRunner
    runner = TestRunner(suite_name="prompt_quality")
    runner.add_test_class(PromptQualityTest)
    result = runner.run()
    runner.save_results(result)
