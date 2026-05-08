# SPDX-License-Identifier: AGPL-3.0-or-later
"""
AI 통합 테스트 (End-to-End)

실제 AI(Gemini CLI)를 호출하여 프롬프트 → 코드 생성 → 실행 → 검증까지
전체 파이프라인을 테스트합니다.

테스트 흐름:
    PromptBuilder가 프롬프트 구성
        ↓
    AI(Gemini)가 Python 코드 생성
        ↓
    코드에서 기본 품질 검증 (import, try/except 등)
        ↓
    CodeSandbox에서 실행
        ↓
    실행 결과 검증 (성공/실패, 출력 내용)

주의사항:
- Gemini CLI가 설치되어 있어야 합니다 (gemini 명령어)
- AI 호출 비용과 시간이 발생합니다 (테스트당 약 10~30초)
- 네트워크 연결이 필요합니다

실행:
    cd ai_rpa_solution
    python -m tests.test_runner --suite ai_integration
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_runner import SkipTest, TestCase


class AIIntegrationTest(TestCase):
    suite = "ai_integration"

    def _check_gemini_available(self):
        """Gemini CLI 사용 가능 여부 확인"""
        import shutil

        if not shutil.which("gemini"):
            raise SkipTest("Gemini CLI가 설치되어 있지 않습니다 (gemini 명령어 필요)")

    def _make_session(self, steps=None, project_type="desktop"):
        from core.session_manager import Session

        session = Session(session_id="ai_test", title="AI 통합 테스트", project_type=project_type)
        if steps:
            session.steps = steps
        return session

    def _make_builder(self):
        from core.prompt_builder import PromptBuilder

        return PromptBuilder()  # prompts.json에서 실제 시스템 컨텍스트 로드

    def _make_adapter(self):
        from core.adapters.gemini_cli_adapter import GeminiCLIAdapter

        return GeminiCLIAdapter({"command": "gemini", "timeout_seconds": 120})

    def _make_sandbox(self):
        from core.workflow_engine import CodeSandbox

        return CodeSandbox(timeout=30)

    def _run_async(self, coro):
        """비동기 함수를 동기적으로 실행"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(asyncio.run, coro).result()
            return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    def _validate_generated_code(self, code: str, context: str = ""):
        """생성된 코드의 기본 품질 검증"""
        self.assert_true(
            len(code) > 10, f"코드가 충분히 생성되어야 합니다 (현재 {len(code)}자) {context}"
        )

        # import 포함 확인 — trivial 코드 (예: sum(range(1,11))) 는 필요 없으므로
        # 하드 assertion 이 아닌 soft warning. 외부 라이브러리 사용 테스트는
        # 별도 assert_contains 로 강제 (test_02 의 'subprocess' 등).
        has_import = "import" in code
        if has_import:
            self.log(f"[PASS] import문이 포함됨 {context}")
        else:
            self.log(f"[INFO] import문이 없음 - trivial 코드일 수 있음 {context}")

        # try/except 포함 확인 (권장이지만 필수는 아닐 수 있음)
        has_error_handling = "try:" in code or "except" in code
        if has_error_handling:
            self.log(f"[PASS] 에러 처리(try/except) 포함됨 {context}")
        else:
            self.log(f"[WARN] 에러 처리(try/except)가 없음 - 개선 필요 {context}")

        # print문 포함 확인
        has_print = "print(" in code
        if has_print:
            self.log(f"[PASS] 결과 출력(print) 포함됨 {context}")
        else:
            self.log(f"[WARN] 결과 출력(print)이 없음 - 개선 필요 {context}")

        return {
            "has_import": has_import,
            "has_error_handling": has_error_handling,
            "has_print": has_print,
        }

    def setup(self):
        self._check_gemini_available()

    # ──────────────────────────────────────────
    # 1. 기본 코드 생성 테스트
    # ──────────────────────────────────────────

    def test_01_simple_code_generation(self):
        """간단한 요청 → AI 코드 생성 → 코드 품질 검증"""
        builder = self._make_builder()
        adapter = self._make_adapter()
        session = self._make_session()

        self.step("프롬프트 생성")
        prompt = builder.build_step_prompt(
            session=session, user_request="현재 날짜와 시간을 출력하는 코드를 만들어줘"
        )
        self.log(f"프롬프트 길이: {len(prompt)}자")

        self.step("AI 호출")
        response = self._run_async(adapter.generate(prompt))
        self.assert_true(response.success, f"AI 응답 성공: {response.error}")
        self.log(f"응답 시간: {response.response_time_ms}ms")

        self.step("코드 추출 및 품질 검증")
        self.assert_true(
            len(response.code) > 0, f"코드가 추출되어야 합니다. 원본 응답: {response.text[:200]}"
        )
        self._validate_generated_code(response.code, "(날짜 출력)")

        self.step("코드 실행")
        sandbox = self._make_sandbox()
        result = sandbox.execute(response.code)
        self.assert_true(result.success, f"코드 실행 성공해야 합니다. 에러: {result.error}")
        self.log(f"실행 출력: {result.output[:200]}")

    def test_02_subprocess_code_generation(self):
        """프로그램 실행 요청 → subprocess 코드 생성 확인"""
        builder = self._make_builder()
        adapter = self._make_adapter()
        session = self._make_session()

        self.step("프롬프트 생성: 프로그램 실행")
        prompt = builder.build_step_prompt(
            session=session,
            user_request="파이썬 버전을 확인하는 코드를 만들어줘 (subprocess로 python --version 실행)",
        )

        self.step("AI 호출")
        response = self._run_async(adapter.generate(prompt))
        self.assert_true(response.success, f"AI 응답 성공: {response.error}")

        self.step("코드 검증")
        self.assert_true(len(response.code) > 0, "코드가 생성되어야 합니다")
        self.assert_contains(response.code, "subprocess", "subprocess가 사용되어야 합니다")
        self._validate_generated_code(response.code, "(subprocess)")

        self.step("코드 실행")
        sandbox = self._make_sandbox()
        result = sandbox.execute(response.code)
        self.assert_true(result.success, f"실행 성공: {result.error}")
        self.log(f"출력: {result.output[:200]}")

    # ──────────────────────────────────────────
    # 2. 누적 코드 유지 테스트
    # ──────────────────────────────────────────

    def test_03_accumulated_code_preservation(self):
        """이전 스텝 코드가 있을 때 AI가 기존 코드를 유지하는지"""
        builder = self._make_builder()
        adapter = self._make_adapter()

        prev_code = "import os\ncurrent_dir = os.getcwd()\nprint(f'현재 디렉토리: {current_dir}')"
        session = self._make_session(
            steps=[{"step_id": 1, "status": "completed", "generated_code": prev_code}]
        )

        self.step("누적 코드 + 새 요청 프롬프트")
        prompt = builder.build_step_prompt(
            session=session, user_request="현재 디렉토리의 파일 목록도 출력해줘"
        )

        self.step("AI 호출")
        response = self._run_async(adapter.generate(prompt))
        self.assert_true(response.success, f"AI 응답 성공: {response.error}")
        self.assert_true(len(response.code) > 0, "코드가 생성되어야 합니다")

        self.step("이전 코드 유지 확인")
        self.assert_contains(
            response.code, "os.getcwd()", "이전 스텝의 os.getcwd()가 유지되어야 합니다"
        )
        self.assert_contains(
            response.code, "현재 디렉토리", "이전 스텝의 print 내용이 유지되어야 합니다"
        )

        self.step("새 기능 추가 확인")
        has_listdir = (
            "listdir" in response.code or "scandir" in response.code or "glob" in response.code
        )
        self.assert_true(has_listdir, "파일 목록 기능이 추가되어야 합니다 (listdir/scandir/glob)")

        self.step("누적 코드 실행")
        sandbox = self._make_sandbox()
        result = sandbox.execute(response.code)
        self.assert_true(result.success, f"누적 코드 실행 성공: {result.error}")
        self.log(f"출력: {result.output[:300]}")

    # ──────────────────────────────────────────
    # 3. 에러 복구 테스트
    # ──────────────────────────────────────────

    def test_04_error_recovery_code_generation(self):
        """에러 발생 → 에러 컨텍스트 → AI가 수정된 코드 생성"""
        builder = self._make_builder()
        adapter = self._make_adapter()
        session = self._make_session()

        # 의도적으로 에러가 있는 코드
        broken_code = (
            "import os\n"
            "# 존재하지 않는 디렉토리 읽기 시도\n"
            "files = os.listdir('/this_directory_does_not_exist_12345')\n"
            "print(files)"
        )
        error_msg = "FileNotFoundError: [WinError 3] 지정된 경로를 찾을 수 없습니다: '/this_directory_does_not_exist_12345'"

        self.step("에러 복구 프롬프트 생성")
        prompt = builder.build_step_prompt(
            session=session, user_request="에러를 수정해줘", error_context=error_msg
        )
        # 이전 코드도 프롬프트에 포함
        session.steps = [{"step_id": 1, "status": "failed", "generated_code": broken_code}]
        prompt = builder.build_step_prompt(
            session=session,
            user_request="이 에러를 수정해서 현재 디렉토리의 파일 목록을 출력해줘",
            error_context=error_msg,
        )

        self.step("AI 호출 (수정된 코드 요청)")
        response = self._run_async(adapter.generate(prompt))
        self.assert_true(response.success, f"AI 응답 성공: {response.error}")
        self.assert_true(len(response.code) > 0, "수정된 코드가 생성되어야 합니다")

        self.step("수정된 코드에 에러 원인이 해결되었는지")
        # AI가 주석으로 원래 경로를 설명할 수 있으므로, 실행 가능한 코드 라인에서만 확인
        executable_lines = [
            line
            for line in response.code.split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]
        executable_code = "\n".join(executable_lines)
        has_broken_path = "/this_directory_does_not_exist_12345" in executable_code
        if has_broken_path:
            self.log("[WARN] 실행 코드에 잘못된 경로가 남아있지만, 실행 결과로 판단합니다")

        self.step("수정된 코드 실행")
        sandbox = self._make_sandbox()
        result = sandbox.execute(response.code)
        self.assert_true(
            result.success, f"수정된 코드는 실행 성공해야 합니다. 에러: {result.error}"
        )
        self.log(f"출력: {result.output[:300]}")

    # ──────────────────────────────────────────
    # 4. 윈도우 컨텍스트 활용 테스트
    # ──────────────────────────────────────────

    def test_05_window_context_code_generation(self):
        """윈도우 UI 정보를 제공했을 때 AI가 정확한 자동화 코드를 생성하는지"""
        builder = self._make_builder()
        adapter = self._make_adapter()
        session = self._make_session()

        # 가상의 윈도우 컨텍스트 (WindowInspector 출력 시뮬레이션)
        window_ctx = """## 대상 윈도우: 메모장
클래스: Notepad
컨트롤 수: 5

### UI 컨트롤 목록:
- [Edit] "" (id=15) @ (0,50) 800×500
- [MenuBar] "" @ (0,0)
  - [MenuItem] "파일" @ (0,0)
  - [MenuItem] "편집" @ (40,0)
- [StatusBar] "Ln 1, Col 1" @ (0,550)"""

        self.step("윈도우 컨텍스트 + 요청 프롬프트")
        prompt = builder.build_step_prompt(
            session=session,
            user_request="메모장의 Edit 컨트롤에 '안녕하세요'를 입력하는 코드를 만들어줘",
            window_context=window_ctx,
        )

        self.step("AI 호출")
        response = self._run_async(adapter.generate(prompt))
        self.assert_true(response.success, f"AI 응답 성공: {response.error}")
        self.assert_true(len(response.code) > 0, "코드가 생성되어야 합니다")

        self.step("자동화 코드 품질 검증")
        code = response.code
        # pywinauto 사용 확인
        has_pywinauto = "pywinauto" in code or "Application" in code
        has_pyautogui = "pyautogui" in code
        self.assert_true(
            has_pywinauto or has_pyautogui,
            "자동화 라이브러리 (pywinauto 또는 pyautogui)가 사용되어야 합니다",
        )

        # 메모장 연결 시도
        has_notepad_connect = "메모장" in code or "Notepad" in code or "notepad" in code
        self.assert_true(has_notepad_connect, "메모장에 연결하는 코드가 있어야 합니다")

        # 텍스트 입력
        has_text_input = (
            "안녕하세요" in code or "set_text" in code or "type_keys" in code or "send_keys" in code
        )
        self.assert_true(has_text_input, "텍스트 입력 코드가 있어야 합니다")

        self._validate_generated_code(code, "(메모장 자동화)")
        self.log(f"생성된 코드 길이: {len(code)}자")

    # ──────────────────────────────────────────
    # 5. 요소 선택 → 코드 생성 → 실행 통합 테스트
    # ──────────────────────────────────────────

    def test_06_element_context_code_generation(self):
        """요소 피커 정보 → AI 코드 생성 시 정확한 요소 접근 코드가 나오는지"""
        builder = self._make_builder()
        adapter = self._make_adapter()
        session = self._make_session()

        # WindowInspector가 생성하는 요소 컨텍스트 시뮬레이션
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        element_info = {
            "control_type": "Button",
            "name": "확인",
            "automation_id": "btnOK",
            "class_name": "Button",
            "rect": {"left": 350, "top": 400, "width": 80, "height": 30},
            "parent_window_title": "설정",
            "parent_window_class": "DialogWnd",
            "screen_x": 390,
            "screen_y": 415,
            "is_browser": False,
            "detected_backend": "uia",
            "recommended_backend": "uia",
        }
        element_ctx = inspector.get_element_info_text(element_info)

        self.step("요소 컨텍스트 + 요청 프롬프트")
        prompt = builder.build_step_prompt(
            session=session,
            user_request="이 확인 버튼을 클릭해줘",
            element_context=element_ctx,
            is_browser_element=False,
        )

        self.step("AI 호출")
        response = self._run_async(adapter.generate(prompt))
        self.assert_true(response.success, f"AI 응답 성공: {response.error}")
        self.assert_true(len(response.code) > 0, "코드가 생성되어야 합니다")

        self.step("생성 코드에 요소 정보 반영 확인")
        code = response.code
        # btnOK auto_id 또는 "확인" 이름 사용
        has_element_ref = "btnOK" in code or "확인" in code
        self.assert_true(
            has_element_ref, "요소의 automation_id 또는 이름이 코드에 반영되어야 합니다"
        )

        # pywinauto 또는 pyautogui 클릭 코드
        has_click = "click" in code.lower()
        self.assert_true(has_click, "클릭 동작 코드가 있어야 합니다")

        self._validate_generated_code(code, "(요소 클릭)")

    def test_07_browser_element_generates_selenium(self):
        """브라우저 요소 → AI가 Selenium 코드를 생성하는지"""
        builder = self._make_builder()
        adapter = self._make_adapter()
        session = self._make_session()

        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        element_info = {
            "control_type": "Button",
            "name": "로그인",
            "automation_id": "loginBtn",
            "class_name": "button",
            "rect": {"left": 500, "top": 300, "width": 100, "height": 40},
            "parent_window_title": "Chrome - 로그인 페이지",
            "is_browser": True,
            "browser_type": "Chrome",
        }
        element_ctx = inspector.get_element_info_text(element_info)

        self.step("브라우저 요소 컨텍스트 프롬프트")
        prompt = builder.build_step_prompt(
            session=session,
            user_request="이 로그인 버튼을 클릭해줘",
            element_context=element_ctx,
            is_browser_element=True,
        )

        self.step("AI 호출")
        response = self._run_async(adapter.generate(prompt))
        self.assert_true(response.success, f"AI 응답 성공: {response.error}")
        self.assert_true(len(response.code) > 0, "코드가 생성되어야 합니다")

        self.step("Selenium 코드 생성 확인")
        code = response.code
        has_selenium = "selenium" in code or "webdriver" in code
        self.assert_true(has_selenium, "브라우저 요소에 대해 Selenium 코드가 생성되어야 합니다")

        # pywinauto가 아닌 Selenium을 사용하는지
        has_pywinauto = "pywinauto" in code and "Application" in code
        if has_pywinauto:
            self.log("[WARN] 브라우저 요소인데 pywinauto가 사용됨 — 프롬프트 개선 필요")

        self._validate_generated_code(code, "(Selenium)")

    # ──────────────────────────────────────────
    # 6. 전체 파이프라인 통합 테스트
    # ──────────────────────────────────────────

    def test_08_full_pipeline_safe_code(self):
        """전체 파이프라인: 프롬프트 → AI → 코드 추출 → 실행 → 출력 검증"""
        builder = self._make_builder()
        adapter = self._make_adapter()
        sandbox = self._make_sandbox()
        session = self._make_session()

        self.step("1단계: 프롬프트 생성")
        prompt = builder.build_step_prompt(
            session=session,
            user_request="1부터 10까지의 합을 계산하고 결과를 출력하는 코드를 만들어줘",
        )

        self.step("2단계: AI 코드 생성")
        response = self._run_async(adapter.generate(prompt))
        self.assert_true(response.success, f"AI 응답 성공: {response.error}")
        self.assert_true(len(response.code) > 0, "코드 추출 성공")
        self.log(f"생성된 코드:\n{response.code}")

        self.step("3단계: 코드 품질 검증")
        self._validate_generated_code(response.code, "(1~10 합)")

        self.step("4단계: 코드 실행")
        result = sandbox.execute(response.code)
        self.assert_true(result.success, f"실행 성공: {result.error}")

        self.step("5단계: 출력 결과 검증")
        self.assert_contains(result.output, "55", "1부터 10까지의 합 55가 출력되어야 합니다")
        self.log(f"최종 출력: {result.output}")

    def test_09_multi_step_pipeline(self):
        """다단계 파이프라인: 스텝1 → 스텝2 (누적 코드 유지 검증)"""
        builder = self._make_builder()
        adapter = self._make_adapter()
        sandbox = self._make_sandbox()

        # ── 스텝 1: 리스트 생성 ──
        self.step("스텝1: 리스트 생성 코드")
        session = self._make_session()
        prompt1 = builder.build_step_prompt(
            session=session,
            user_request="fruits = ['사과', '바나나', '딸기'] 리스트를 만들고 출력해줘",
        )

        response1 = self._run_async(adapter.generate(prompt1))
        self.assert_true(response1.success, f"스텝1 AI 성공: {response1.error}")
        self.assert_true(len(response1.code) > 0, "스텝1 코드 생성")

        result1 = sandbox.execute(response1.code)
        self.assert_true(result1.success, f"스텝1 실행 성공: {result1.error}")
        self.log(f"스텝1 출력: {result1.output}")

        # ── 스텝 2: 기존 코드에 기능 추가 ──
        self.step("스텝2: 기존 리스트에 '포도' 추가")
        session.steps = [{"step_id": 1, "status": "completed", "generated_code": response1.code}]
        prompt2 = builder.build_step_prompt(
            session=session,
            user_request="위 리스트에 '포도'를 추가하고 전체 리스트를 다시 출력해줘",
        )

        response2 = self._run_async(adapter.generate(prompt2))
        self.assert_true(response2.success, f"스텝2 AI 성공: {response2.error}")
        self.assert_true(len(response2.code) > 0, "스텝2 코드 생성")

        # 기존 코드 유지 확인
        self.assert_contains(response2.code, "사과", "스텝1의 리스트 내용이 유지되어야 합니다")

        result2 = sandbox.execute(response2.code)
        self.assert_true(result2.success, f"스텝2 실행 성공: {result2.error}")
        self.assert_contains(
            result2.output, "포도", "스텝2에서 '포도'가 추가되어 출력되어야 합니다"
        )
        self.log(f"스텝2 출력: {result2.output}")


if __name__ == "__main__":
    from tests.test_runner import TestRunner

    runner = TestRunner(suite_name="ai_integration")
    runner.add_test_class(AIIntegrationTest)
    result = runner.run()
    runner.save_results(result)
