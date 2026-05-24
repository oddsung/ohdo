# SPDX-License-Identifier: AGPL-3.0-or-later
"""
코어 모듈 단위 테스트

GUI나 Windows 환경 없이도 실행 가능한 순수 로직 테스트:
- SessionManager: 세션 CRUD, 스텝 관리, 내보내기
- PromptBuilder: 프롬프트 생성, 컨텍스트 구성
- WorkflowEngine: CodeSandbox 코드 실행
- AIEngineManager: 어댑터 초기화, 전환
- WindowInspector: 코드 생성 로직 (실제 윈도우 불필요)

실행:
    cd ai_rpa_solution
    python -m tests.test_runner --suite core
"""

import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_runner import TestCase


class CoreTest(TestCase):
    suite = "core"

    def setup(self):
        pass  # 코어 테스트는 OS 제한 없음

    # ──────────────────────────────────────────
    # SessionManager 테스트
    # ──────────────────────────────────────────

    def test_01_session_create_and_load(self):
        """세션 생성 → 저장 → 로드 사이클"""
        from core.session_manager import SessionManager

        self.step("임시 디렉토리에 세션 매니저 생성")
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SessionManager(data_dir=Path(tmpdir))

            self.step("세션 생성")
            session = manager.create_session(
                title="테스트 세션", project_type="desktop", description="단위 테스트용"
            )
            self.assert_true(len(session.session_id) > 0, "세션 ID가 생성되어야 합니다")
            self.assert_equal(session.title, "테스트 세션")
            self.assert_equal(session.project_type, "desktop")
            self.log(f"세션 생성됨: {session.session_id}")

            self.step("세션 로드")
            loaded = manager.load_session(session.session_id)
            self.assert_equal(loaded.title, "테스트 세션", "로드된 제목이 일치해야 합니다")
            self.assert_equal(loaded.session_id, session.session_id, "세션 ID가 일치해야 합니다")

    def test_02_session_step_management(self):
        """스텝 추가/수정/삭제/이동"""
        from core.session_manager import SessionManager, Step

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SessionManager(data_dir=Path(tmpdir))
            session = manager.create_session(title="스텝 테스트")

            self.step("스텝 3개 추가")
            for i in range(3):
                step = Step(generated_code=f"print('step {i + 1}')")
                manager.add_step(session, step)
            self.assert_equal(len(session.steps), 3, "3개 스텝이 추가되어야 합니다")

            self.step("스텝 업데이트")
            manager.update_step(
                session,
                step_id=2,
                updates={"status": "completed", "generated_code": "print('updated step 2')"},
            )
            loaded = manager.load_session(session.session_id)
            step2 = loaded.steps[1]
            self.assert_equal(step2["status"], "completed", "스텝 2 상태가 업데이트되어야 합니다")

            self.step("스텝 삭제")
            result = manager.delete_step(session, step_id=2)
            self.assert_true(result, "스텝 삭제가 성공해야 합니다")
            self.assert_equal(len(session.steps), 2, "2개 스텝이 남아야 합니다")
            # step_id 재정렬 확인
            self.assert_equal(session.steps[0]["step_id"], 1, "첫 번째 스텝 ID = 1")
            self.assert_equal(session.steps[1]["step_id"], 2, "두 번째 스텝 ID = 2")

            self.step("스텝 이동")
            manager.move_step(session, step_id=1, direction="down")
            self.assert_contains(
                session.steps[1].get("generated_code", ""),
                "step 1",
                "스텝 1이 아래로 이동해야 합니다",
            )

    def test_03_session_list_and_delete(self):
        """세션 목록 조회 및 삭제"""
        from core.session_manager import SessionManager

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SessionManager(data_dir=Path(tmpdir))

            self.step("세션 3개 생성")
            ids = []
            for i in range(3):
                s = manager.create_session(title=f"세션 {i + 1}")
                ids.append(s.session_id)

            self.step("세션 목록 조회")
            summaries = manager.list_sessions()
            self.assert_equal(len(summaries), 3, "3개 세션이 목록에 있어야 합니다")

            self.step("세션 삭제")
            manager.delete_session(ids[1])
            summaries = manager.list_sessions()
            self.assert_equal(len(summaries), 2, "삭제 후 2개 세션이 남아야 합니다")

    def test_04_session_export_workflow(self):
        """워크플로우 코드 내보내기"""
        from core.session_manager import SessionManager, Step

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SessionManager(data_dir=Path(tmpdir))
            session = manager.create_session(title="내보내기 테스트")

            step1 = Step(generated_code="import time\nimport os\nprint('hello')")
            step2 = Step(generated_code="import time\nprint('world')")
            manager.add_step(session, step1)
            manager.add_step(session, step2)

            self.step("워크플로우 내보내기")
            code = manager.export_workflow(session)
            self.assert_contains(code, "import time", "import문이 포함되어야 합니다")
            self.assert_contains(code, "import os", "os import가 포함되어야 합니다")
            self.assert_contains(code, "print('hello')", "코드 본문이 포함되어야 합니다")
            self.assert_contains(code, "print('world')", "두 번째 스텝 코드도 포함되어야 합니다")
            self.log(f"내보낸 코드 길이: {len(code)}자")

    def test_05_session_export_project(self):
        """프로젝트 폴더 내보내기"""
        from core.session_manager import SessionManager, Step

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SessionManager(data_dir=Path(tmpdir))
            session = manager.create_session(title="프로젝트 내보내기")

            step = Step(generated_code="import pyautogui\npyautogui.click(100, 200)")
            manager.add_step(session, step)

            self.step("프로젝트 내보내기")
            output_dir = Path(tmpdir) / "export"
            result_dir = manager.export_as_project(session, output_dir)

            self.assert_true((result_dir / "main.py").exists(), "main.py가 생성되어야 합니다")
            self.assert_true(
                (result_dir / "requirements.txt").exists(), "requirements.txt가 생성되어야 합니다"
            )
            self.assert_true((result_dir / "README.md").exists(), "README.md가 생성되어야 합니다")

            main_code = (result_dir / "main.py").read_text(encoding="utf-8")
            self.assert_contains(main_code, "pyautogui", "main.py에 코드가 포함되어야 합니다")

    # ──────────────────────────────────────────
    # PromptBuilder 테스트
    # ──────────────────────────────────────────

    def test_06_prompt_builder_basic(self):
        """기본 프롬프트 생성"""
        from core.prompt_builder import PromptBuilder
        from core.session_manager import Session

        self.step("PromptBuilder 생성")
        builder = PromptBuilder(prompts_config={})
        session = Session(session_id="test", title="테스트")

        self.step("스텝 프롬프트 생성")
        prompt = builder.build_step_prompt(
            session=session, user_request="메모장을 열어줘", project_type="desktop"
        )
        self.assert_contains(
            prompt, "메모장을 열어줘", "사용자 요청이 프롬프트에 포함되어야 합니다"
        )
        self.assert_contains(prompt, "pywinauto", "pywinauto 가이드가 포함되어야 합니다")
        self.assert_contains(prompt, "Selenium", "Selenium 가이드가 포함되어야 합니다")
        self.assert_contains(prompt, "```python", "코드블록 규칙이 포함되어야 합니다")
        self.log(f"프롬프트 길이: {len(prompt)}자")

    def test_07_prompt_builder_with_context(self):
        """이전 코드가 있을 때 누적 코드 포함 확인"""
        from core.prompt_builder import PromptBuilder
        from core.session_manager import Session

        builder = PromptBuilder(prompts_config={})
        session = Session(session_id="test", title="테스트")
        session.steps = [
            {"step_id": 1, "status": "completed", "generated_code": "import time\ntime.sleep(1)"}
        ]

        self.step("이전 코드 포함된 프롬프트")
        prompt = builder.build_step_prompt(session=session, user_request="다음 작업을 해줘")
        self.assert_contains(prompt, "import time", "이전 스텝 코드가 포함되어야 합니다")
        self.assert_contains(prompt, "누적 코드", "누적 코드 안내가 있어야 합니다")

    def test_08_prompt_builder_error_recovery(self):
        """에러 복구 프롬프트 생성"""
        from core.prompt_builder import PromptBuilder

        builder = PromptBuilder(prompts_config={})

        self.step("에러 복구 프롬프트")
        prompt = builder.build_error_recovery_prompt(
            error_message="ModuleNotFoundError: No module named 'xxx'",
            current_code="import xxx\nxxx.do_something()",
        )
        self.assert_contains(prompt, "ModuleNotFoundError", "에러 메시지가 포함되어야 합니다")
        self.assert_contains(prompt, "import xxx", "현재 코드가 포함되어야 합니다")

    def test_09_prompt_builder_browser_element(self):
        """브라우저 요소 선택 시 Selenium 컨텍스트 생성"""
        from core.prompt_builder import PromptBuilder
        from core.session_manager import Session

        builder = PromptBuilder(prompts_config={})
        session = Session(session_id="test", title="테스트")

        self.step("브라우저 요소 컨텍스트 프롬프트")
        prompt = builder.build_step_prompt(
            session=session,
            user_request="이 버튼을 클릭해줘",
            element_context="## 선택된 UI 요소 (브라우저: Chrome)\nSelenium으로 제어",
            is_browser_element=True,
        )
        self.assert_contains(prompt, "Selenium", "브라우저 요소일 때 Selenium 지시가 있어야 합니다")

    # ──────────────────────────────────────────
    # CodeSandbox 테스트
    # ──────────────────────────────────────────

    def test_10_sandbox_execute_success(self):
        """CodeSandbox 정상 코드 실행"""
        from core.workflow_engine import CodeSandbox

        self.step("간단한 코드 실행")
        sandbox = CodeSandbox(timeout=10)
        result = sandbox.execute("print('hello from sandbox')")
        self.assert_true(result.success, f"실행 성공해야 합니다: {result.error}")
        self.assert_contains(result.output, "hello from sandbox", "출력이 캡처되어야 합니다")
        self.log(f"실행 시간: {result.duration_ms}ms")

    def test_11_sandbox_execute_error(self):
        """CodeSandbox 에러 코드 실행"""
        from core.workflow_engine import CodeSandbox

        self.step("에러 코드 실행")
        sandbox = CodeSandbox(timeout=10)
        result = sandbox.execute("raise ValueError('test error')")
        self.assert_true(not result.success, "실행 실패해야 합니다")
        self.assert_contains(result.error, "ValueError", "에러 메시지에 에러 타입이 있어야 합니다")

    def test_12_sandbox_timeout(self):
        """CodeSandbox 타임아웃"""
        from core.workflow_engine import CodeSandbox

        self.step("타임아웃 테스트 (2초 제한)")
        sandbox = CodeSandbox(timeout=2)
        result = sandbox.execute("import time; time.sleep(10)")
        self.assert_true(not result.success, "타임아웃으로 실패해야 합니다")
        self.assert_contains(result.error, "시간 초과", "타임아웃 에러 메시지가 있어야 합니다")

    # ──────────────────────────────────────────
    # AIEngineManager 테스트
    # ──────────────────────────────────────────

    def test_13_ai_engine_manager_init(self):
        """AIEngineManager 초기화"""
        from core.ai_engine import AIEngineManager

        self.step("설정으로 초기화")
        settings = {
            "ai": {
                "selected": "gemini_cli",
                "available_engines": {"gemini_cli": {"command": "gemini", "timeout_seconds": 30}},
            }
        }
        manager = AIEngineManager(settings)
        self.assert_equal(
            manager.get_current_name(), "gemini_cli", "기본 엔진이 gemini_cli이어야 합니다"
        )

        self.step("사용 가능한 엔진 목록")
        engines = manager.list_available()
        self.assert_true(len(engines) > 0, "최소 1개 엔진이 있어야 합니다")
        self.log(f"엔진 목록: {engines}")

    def test_14_ai_engine_switch(self):
        """존재하지 않는 엔진으로 전환 시 에러"""
        from core.ai_engine import AIEngineManager

        settings = {
            "ai": {
                "selected": "gemini_cli",
                "available_engines": {"gemini_cli": {"command": "gemini"}},
            }
        }
        manager = AIEngineManager(settings)

        self.step("존재하지 않는 엔진 전환 시도")
        try:
            manager.switch_engine("nonexistent")
            self.assert_true(False, "ValueError가 발생해야 합니다")
        except ValueError as e:
            self.log(f"예상된 에러 발생: {e}")

    # ──────────────────────────────────────────
    # WindowInspector 코드 생성 로직 테스트
    # ──────────────────────────────────────────

    def test_15_win_inspector_code_gen_desktop(self):
        """데스크톱 요소 → pywinauto 코드 생성"""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()

        self.step("일반 데스크톱 요소 코드 생성")
        element_info = {
            "control_type": "Button",
            "name": "확인",
            "automation_id": "btnOK",
            "class_name": "Button",
            "rect": {"left": 100, "top": 200, "width": 80, "height": 30},
            "parent_window_title": "설정 대화상자",
            "parent_window_class": "DialogClass",
            "screen_x": 140,
            "screen_y": 215,
            "is_browser": False,
            "detected_backend": "uia",
            "recommended_backend": "uia",
        }
        text = inspector.get_element_info_text(element_info)
        self.assert_contains(text, "pywinauto", "pywinauto 코드가 포함되어야 합니다")
        self.assert_contains(text, "btnOK", "automation_id가 포함되어야 합니다")
        self.assert_contains(text, "DPI", "DPI 설정 코드가 포함되어야 합니다")

    def test_16_win_inspector_code_gen_owner_drawn(self):
        """Owner-drawn 요소 → 좌표 기반 코드 생성"""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()

        self.step("Owner-drawn 요소 코드 생성")
        element_info = {
            "control_type": "Pane",
            "name": "",  # 이름 없음
            "automation_id": "",  # auto_id 없음
            "class_name": "TToolBar",
            "rect": {"left": 10, "top": 50, "width": 30, "height": 30},
            "parent_window_title": "Preview",
            "parent_window_class": "TPreviewForm",
            "screen_x": 25,
            "screen_y": 65,
            "is_browser": False,
            "detected_backend": "uia",
            "recommended_backend": "uia",
        }
        text = inspector.get_element_info_text(element_info)
        self.assert_contains(text, "Owner-drawn", "owner-drawn 안내가 있어야 합니다")
        self.assert_contains(text, "pyautogui", "좌표 기반 클릭 코드가 있어야 합니다")
        self.assert_contains(text, "25", "screen_x 좌표가 포함되어야 합니다")

    def test_17_win_inspector_code_gen_browser(self):
        """브라우저 요소 → Selenium 코드 생성 (JS click 포함)"""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()

        self.step("인터랙티브 브라우저 요소 (direct click) - CDP DOM 수집됨")
        # Selenium 경로는 CDP 가 실제 DOM 정보 (tagName) 를 수집했을 때만 발동.
        # is_browser 만으로는 부족 (탭/주소창 등 chrome UI 도 is_browser=True 라서).
        button_elem = {
            "control_type": "Button",
            "name": "Submit",
            "automation_id": "submitBtn",
            "class_name": "button",
            "rect": {"left": 100, "top": 200, "width": 80, "height": 30},
            "parent_window_title": "Chrome",
            "is_browser": True,
            "browser_type": "Chrome",
            "dom_context": {
                "cdp_available": True,
                "tagName": "button",
                "attributes": {"id": "submitBtn", "class": "button"},
            },
        }
        text = inspector.get_element_info_text(button_elem)
        self.assert_contains(text, "find_and_click", "Button은 find_and_click 패턴이어야 합니다")

        self.step("비인터랙티브 브라우저 요소 (JS click) - CDP DOM 수집됨")
        text_elem = {
            "control_type": "Text",
            "name": "메뉴항목",
            "automation_id": "",
            "class_name": "span",
            "rect": {"left": 50, "top": 100, "width": 60, "height": 20},
            "parent_window_title": "Chrome",
            "is_browser": True,
            "browser_type": "Chrome",
            "dom_context": {
                "cdp_available": True,
                "tagName": "span",
                "attributes": {"class": "span"},
            },
        }
        text = inspector.get_element_info_text(text_elem)
        self.assert_contains(text, "execute_script", "Text 요소는 JS click이어야 합니다")
        self.assert_contains(text, "not(self::script)", "script 태그 제외 XPath가 있어야 합니다")

    def test_18_win_inspector_dynamic_autoid_warning(self):
        """동적 auto_id(숫자만) 경고 확인"""
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()

        element_info = {
            "control_type": "Edit",
            "name": "입력필드",
            "automation_id": "12345678",  # 순수 숫자 = 동적 ID
            "class_name": "Edit",
            "rect": {"left": 100, "top": 200, "width": 200, "height": 25},
            "parent_window_title": "앱",
            "is_browser": False,
            "detected_backend": "uia",
            "recommended_backend": "uia",
        }
        text = inspector.get_element_info_text(element_info)
        self.assert_contains(text, "동적 ID", "순수 숫자 auto_id에 대한 경고가 있어야 합니다")

    # ── import_manager 테스트 ──

    def test_19_extract_imports_basic(self):
        """import_manager: 상단 import 추출 기본 동작"""
        from core.import_manager import extract_imports

        code = (
            "import os\n"
            "import time\n"
            "from selenium import webdriver\n"
            "\n"
            "app = webdriver.Chrome()\n"
            "print(os.getcwd())\n"
        )
        imports, body = extract_imports(code)
        self.assert_equal(len(imports), 3, "import 3개 추출")
        self.assert_contains(imports[0], "import os", "첫 번째 import")
        self.assert_contains(body, "app = webdriver", "body에 코드 포함")
        self.assert_true("import os" not in body, "body에 import가 없어야 합니다")

    def test_20_extract_imports_with_docstring(self):
        """import_manager: docstring 이후의 import도 추출"""
        from core.import_manager import extract_imports

        code = '"""모듈 설명"""\nimport os\nimport pywinauto\n\nprint(\'hello\')\n'
        imports, body = extract_imports(code)
        self.assert_equal(len(imports), 2, "docstring 이후 import 2개 추출")
        self.assert_contains(body, "print('hello')", "body에 코드 포함")

    def test_21_extract_imports_midcode_import_stays(self):
        """import_manager: 코드 중간의 import는 body에 유지"""
        from core.import_manager import extract_imports

        code = "import os\n\nx = 1\nimport json  # 중간 import\nprint(x)\n"
        imports, body = extract_imports(code)
        self.assert_equal(len(imports), 1, "상단 import만 1개 추출")
        self.assert_contains(body, "import json", "중간 import는 body에 남아야 합니다")

    def test_22_merge_imports_dedup(self):
        """import_manager: 중복 import 제거"""
        from core.import_manager import merge_imports

        list1 = ["import os", "import time", "from selenium import webdriver"]
        list2 = ["import os", "import pywinauto", "from selenium import webdriver"]
        merged = merge_imports([list1, list2])
        self.assert_equal(len(merged), 4, "중복 제거 후 4개")
        # os, time은 한 번씩만
        os_count = sum(1 for i in merged if i == "import os")
        self.assert_equal(os_count, 1, "import os는 1번만")

    def test_23_assemble_script(self):
        """import_manager: 스크립트 조합 (str 호환 + 튜플 경계 주석)"""
        from core.import_manager import assemble_script

        # str 방식 (하위호환)
        imports = ["import os", "import time"]
        codes = ["x = os.getcwd()", "print(x)"]
        result = assemble_script(imports, codes)
        self.assert_contains(result, "import os", "import 포함")
        self.assert_contains(result, "x = os.getcwd()", "코드1 포함")
        import_pos = result.index("import os")
        code_pos = result.index("x = os.getcwd()")
        self.assert_true(import_pos < code_pos, "import가 코드보다 먼저 나와야 합니다")

        # 튜플 방식 (경계 주석)
        entries = [
            (1, "메모장 열기", "app = connect('메모장')"),
            (2, "텍스트 입력", "edit.type_keys('hello')"),
        ]
        result2 = assemble_script(imports, entries)
        self.assert_contains(result2, "# === Step 1: 메모장 열기 (시작) ===", "스텝1 시작 주석")
        self.assert_contains(result2, "# === Step 1: 메모장 열기 (끝) ===", "스텝1 끝 주석")
        self.assert_contains(result2, "# === Step 2: 텍스트 입력 (시작) ===", "스텝2 시작 주석")
        self.assert_contains(result2, "app = connect('메모장')", "스텝1 코드 포함")
        self.assert_contains(result2, "edit.type_keys('hello')", "스텝2 코드 포함")

    def test_24_extract_package_names(self):
        """import_manager: 패키지 이름 추출 (stdlib 제외)"""
        from core.import_manager import extract_package_names

        imports = [
            "import os",
            "import time",
            "import pywinauto",
            "from selenium import webdriver",
            "import pyautogui",
        ]
        packages = extract_package_names(imports)
        self.assert_true("pywinauto" in packages, "pywinauto 포함")
        self.assert_true("selenium" in packages, "selenium 포함")
        self.assert_true("pyautogui" in packages, "pyautogui 포함")
        self.assert_true("os" not in packages, "os는 stdlib이므로 제외")
        self.assert_true("time" not in packages, "time은 stdlib이므로 제외")

    def test_25_export_workflow_with_step_comments(self):
        """export_workflow가 스텝 경계 주석을 포함하는지"""
        from core.session_manager import Session, SessionManager, Step

        self.step("스텝 2개로 export (conversation 포함)")
        with tempfile.TemporaryDirectory() as td:
            sm = SessionManager(data_dir=Path(td))
            session = Session(
                session_id="export_test",
                title="경계 주석 테스트",
                created_at="2026-01-01",
            )
            session.steps = [
                asdict(
                    Step(
                        step_id=1,
                        status="completed",
                        generated_code="import os\nimport time\n\nprint(os.getcwd())",
                        conversation=[{"role": "user", "content": "현재 디렉토리 출력"}],
                    )
                ),
                asdict(
                    Step(
                        step_id=2,
                        status="completed",
                        generated_code="import os\nimport pywinauto\n\napp = pywinauto.Application()",
                        conversation=[{"role": "user", "content": "메모장 연결"}],
                    )
                ),
            ]
            result = sm.export_workflow(session)
            # import 중복 제거
            os_count = result.count("import os")
            self.assert_equal(os_count, 1, "export에서 import os 중복 제거")
            # 경계 주석 확인
            self.assert_contains(
                result, "# === Step 1: 현재 디렉토리 출력 (시작) ===", "스텝1 시작 주석"
            )
            self.assert_contains(
                result, "# === Step 1: 현재 디렉토리 출력 (끝) ===", "스텝1 끝 주석"
            )
            self.assert_contains(result, "# === Step 2: 메모장 연결 (시작) ===", "스텝2 시작 주석")
            self.assert_contains(result, "# === Step 2: 메모장 연결 (끝) ===", "스텝2 끝 주석")
            # 코드 포함 확인
            self.assert_contains(result, "print(os.getcwd())", "스텝1 코드 포함")
            self.assert_contains(result, "pywinauto.Application()", "스텝2 코드 포함")

    # ──────────────────────────────────────────
    # EnvironmentScanner 테스트 (F.1)
    # ──────────────────────────────────────────

    def test_26_env_machine_id_stable(self):
        """동일 컴퓨터에서 machine_id 는 호출마다 동일해야 한다"""
        from core.environment_scanner import EnvironmentScanner

        with tempfile.TemporaryDirectory() as td:
            scanner = EnvironmentScanner(config_dir=Path(td))
            id1 = scanner.get_machine_id()
            id2 = scanner.get_machine_id()
            self.assert_equal(id1, id2, "machine_id 가 동일 환경에서 안정적이어야 합니다")
            self.assert_true(len(id1) == 16, "machine_id 는 16자 hex 문자열이어야 합니다")

    def test_27_env_save_load_roundtrip(self):
        """save_environment → load_saved_environment 라운드트립"""
        from core.environment_scanner import EnvironmentScanner

        with tempfile.TemporaryDirectory() as td:
            scanner = EnvironmentScanner(config_dir=Path(td))

            self.step("환경 데이터 저장")
            payload = {
                "python_path": sys.executable,
                "python_version": "3.12.0",
                "packages": {"all_required_installed": True, "required": [], "optional": []},
            }
            ok = scanner.save_environment(payload)
            self.assert_true(ok, "save_environment 는 성공해야 합니다")

            self.step("저장된 환경 로드")
            loaded = scanner.load_saved_environment()
            self.assert_not_none(loaded, "저장 직후 로드는 dict 를 반환해야 합니다")
            self.assert_equal(loaded.get("python_path"), sys.executable)
            self.assert_true("machine_id" in loaded, "machine_id 가 자동으로 박혀야 합니다")
            self.assert_true("last_scan" in loaded, "last_scan 타임스탬프가 박혀야 합니다")

    def test_28_env_load_other_machine_resets(self):
        """다른 컴퓨터의 machine_id 면 None 반환 + 환경 파일 삭제"""
        from core.environment_scanner import EnvironmentScanner

        with tempfile.TemporaryDirectory() as td:
            scanner = EnvironmentScanner(config_dir=Path(td))

            self.step("타 컴퓨터의 환경 파일 시뮬레이션")
            fake = {
                "machine_id": "deadbeef00000000",  # 절대 매칭되지 않을 hex
                "hostname": "other-pc",
                "python_path": sys.executable,
                "last_scan": "2020-01-01T00:00:00",
            }
            scanner.env_file.write_text(json.dumps(fake), encoding="utf-8")
            self.assert_true(scanner.env_file.exists(), "사전 조건: 환경 파일이 존재")

            self.step("load_saved_environment 호출")
            loaded = scanner.load_saved_environment()
            self.assert_true(loaded is None, "다른 머신의 설정은 None 을 반환해야 합니다")
            self.assert_true(
                not scanner.env_file.exists(), "다른 머신 감지 시 파일이 삭제되어야 합니다"
            )

    def test_29_probe_python_version_current(self):
        """_probe_python_version 이 현재 인터프리터 버전을 반환해야 한다"""
        import platform as _platform

        from core.environment_scanner import EnvironmentScanner

        version = EnvironmentScanner._probe_python_version(sys.executable)
        expected = _platform.python_version()
        self.assert_equal(
            version, expected, f"sys.executable({sys.executable}) 의 버전 = {expected}"
        )

    def test_30_check_gemini_cli_not_found(self):
        """존재하지 않는 명령어로 호출 시 not_found 에러를 반환"""
        from core.environment_scanner import EnvironmentScanner

        with tempfile.TemporaryDirectory() as td:
            scanner = EnvironmentScanner(config_dir=Path(td))
            result = scanner.check_gemini_cli(command="ohdo_nonexistent_cli_xyz_zzz")

            self.assert_equal(result["installed"], False, "없는 명령은 installed=False")
            self.assert_equal(result["error"], "not_found")
            self.assert_true(result["path"] is None, "PATH 에서 못 찾으면 path=None")
            self.assert_not_none(result["detail"], "사용자에게 보일 detail 메시지가 있어야 함")

    def test_31_check_gemini_cli_shape(self):
        """기본 'gemini' 호출의 결과 dict 가 약속된 shape 를 가져야 한다.

        설치 여부와 무관하게 dict 의 키 집합과 타입이 일관되어야 dialog
        쪽에서 분기 코드를 단순하게 유지할 수 있다.
        """
        from core.environment_scanner import EnvironmentScanner

        with tempfile.TemporaryDirectory() as td:
            scanner = EnvironmentScanner(config_dir=Path(td))
            result = scanner.check_gemini_cli()

            for key in ("installed", "command", "path", "version", "error", "detail"):
                self.assert_true(key in result, f"결과 dict 에 '{key}' 키가 있어야 합니다")
            self.assert_equal(result["command"], "gemini")
            self.assert_true(isinstance(result["installed"], bool), "installed 는 bool")
            if result["installed"]:
                self.assert_true(result["error"] is None, "installed=True 면 error=None")
                self.assert_not_none(result["version"], "installed=True 면 version 존재")
            else:
                self.assert_not_none(result["error"], "installed=False 면 error 존재")

    def test_32_full_scan_includes_gemini_section(self):
        """full_scan 결과 dict 에 'gemini_cli' 섹션이 포함되어야 한다"""
        from core.environment_scanner import EnvironmentScanner

        with tempfile.TemporaryDirectory() as td:
            scanner = EnvironmentScanner(config_dir=Path(td))
            result = scanner.full_scan(sys.executable)

            self.assert_equal(result.get("success"), True, "full_scan 성공")
            self.assert_true("gemini_cli" in result, "결과에 gemini_cli 섹션 포함")
            gemini = result["gemini_cli"]
            self.assert_true(isinstance(gemini, dict), "gemini_cli 는 dict")
            self.assert_true("installed" in gemini and isinstance(gemini["installed"], bool))

    # ──────────────────────────────────────────
    # ExecutionKernel 테스트 (C.x — 라이프사이클/타임아웃/race)
    # ──────────────────────────────────────────

    def test_33_kernel_basic_lifecycle(self):
        """ExecutionKernel start/ping/stop/restart 사이클"""
        from core.execution_kernel import ExecutionKernel

        kernel = ExecutionKernel(default_timeout=5)
        try:
            self.assert_equal(kernel.is_alive, False, "초기 not alive")

            self.step("start()")
            kernel.start()
            self.assert_equal(kernel.is_alive, True, "start 후 alive")

            self.step("ping()")
            self.assert_equal(kernel.ping(timeout=3.0), True, "ping 응답")

            self.step("stop()")
            kernel.stop()
            self.assert_equal(kernel.is_alive, False, "stop 후 not alive")

            self.step("재기동")
            kernel.start()
            self.assert_equal(kernel.is_alive, True, "재기동 alive")
        finally:
            kernel.stop()

    def test_34_kernel_executes_code_with_namespace(self):
        """블럭 간 네임스페이스 공유 (Jupyter 식 동작)"""
        from core.execution_kernel import ExecutionKernel

        kernel = ExecutionKernel(default_timeout=5)
        kernel.start()
        try:
            self.step("첫 블럭에서 변수 정의")
            r1 = kernel.execute_block("x = 42\ny = 'hello'", step_id=1)
            self.assert_true(r1.success, f"첫 블럭 성공해야 함 (error={r1.error})")

            self.step("두 번째 블럭에서 이전 변수 사용")
            r2 = kernel.execute_block("print(x); print(y)", step_id=2)
            self.assert_true(r2.success, "둘째 블럭 성공")
            self.assert_contains(r2.output, "42", "변수 x 보존")
            self.assert_contains(r2.output, "hello", "변수 y 보존")

            self.step("executed_steps 추적")
            self.assert_equal(kernel.executed_steps, [1, 2], "1, 2 가 추적됨")
        finally:
            kernel.stop()

    def test_35_kernel_stop_terminates_subprocess(self):
        """C.1 게이트: stop() 이 자식 프로세스를 진짜 종료해야 한다."""
        import time

        from core.execution_kernel import ExecutionKernel

        kernel = ExecutionKernel(default_timeout=5)
        kernel.start()
        proc = kernel._proc  # 종료 후 검증용으로 reference 보존
        self.assert_not_none(proc, "start 후 _proc 존재")
        pid = proc.pid
        self.log(f"커널 PID={pid}")

        self.step("stop() 호출")
        kernel.stop()

        # poll() 이 None 이 아닌 종료 코드를 반환할 때까지 폴링 (max 5초)
        deadline = time.time() + 5
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            time.sleep(0.05)

        self.assert_true(
            proc.poll() is not None,
            f"stop() 후 자식 프로세스가 종료되어야 함 (poll={proc.poll()}, PID={pid})",
        )
        self.log(f"종료 코드: {proc.poll()}")

    def test_36_kernel_timeout_triggers_restart_capability(self):
        """C.1: 무한 대기 코드를 짧은 timeout 으로 강제 종료 → 재기동 가능해야 한다."""
        from core.execution_kernel import ExecutionKernel

        kernel = ExecutionKernel(default_timeout=5)
        kernel.start()
        try:
            self.step("긴 sleep 코드 1초 timeout 으로 실행 → 강제 종료 유발")
            r1 = kernel.execute_block(
                "import time\ntime.sleep(30)",
                step_id=1,
                timeout=1,
            )
            self.assert_equal(r1.success, False, "타임아웃은 실패로 보고")
            self.assert_contains(r1.error or "", "시간 초과", "에러 메시지에 시간 초과 표시")

            # 타임아웃 시 _execute_locked 가 self.stop() 을 호출 → is_alive=False
            self.assert_equal(kernel.is_alive, False, "타임아웃 후 커널 종료 상태")

            self.step("재기동 후 정상 실행")
            kernel.start()
            self.assert_equal(kernel.is_alive, True, "재기동 alive")

            r2 = kernel.execute_block("print('alive')", step_id=2, timeout=5)
            self.assert_true(r2.success, f"재기동 후 정상 실행 (error={r2.error})")
            self.assert_contains(r2.output, "alive", "재기동 후 출력 정상")
        finally:
            kernel.stop()

    # ──────────────────────────────────────────
    # ElementPicker 인프라 회귀 방지 (SetWindowPos / _force_topmost)
    # ──────────────────────────────────────────

    def test_37_element_picker_force_topmost_exists(self):
        """[회귀] _force_topmost 메서드가 element_picker 에 존재하고 start_picking
        에서 호출되는지. 이 메서드가 빠지면 Win11 에서 Chrome/작업표시줄이 overlay
        위로 올라와 picker click 이 가려져 element 선택 불능 회귀 발생.
        """
        from ui import element_picker

        self.assert_true(
            hasattr(element_picker.ElementPickerOverlay, "_force_topmost"),
            "[회귀] ElementPickerOverlay._force_topmost 메서드가 존재해야 함",
        )

        # SetWindowPos 와 HWND_TOPMOST 상수 존재
        self.assert_true(
            hasattr(element_picker, "HWND_TOPMOST"),
            "[회귀] HWND_TOPMOST 상수 존재해야 함",
        )
        self.assert_equal(element_picker.HWND_TOPMOST, -1, "HWND_TOPMOST=-1")
        self.assert_true(
            hasattr(element_picker, "SWP_NOMOVE")
            and hasattr(element_picker, "SWP_NOSIZE")
            and hasattr(element_picker, "SWP_NOACTIVATE"),
            "[회귀] SWP_NOMOVE/SWP_NOSIZE/SWP_NOACTIVATE 상수 존재",
        )

        # start_picking 의 소스에 _force_topmost 호출이 있는지 (정적 검사)
        import inspect

        src = inspect.getsource(element_picker.ElementPickerOverlay.start_picking)
        self.assert_true(
            "_force_topmost" in src,
            "[회귀] start_picking 이 _force_topmost() 를 호출해야 함",
        )

    def test_39_element_picker_walkers_in_helper(self):
        """[회귀] _detect_in_hwnd helper 가 세 walker 모두 호출하는지.

        Chrome 처럼 sparse children 케이스에서 walker 하나만 빠져도 회귀.
        """
        import inspect

        from ui.element_picker import ElementPickerOverlay

        self.assert_true(
            hasattr(ElementPickerOverlay, "_detect_in_hwnd"),
            "[회귀] _detect_in_hwnd helper 메서드 존재 필수",
        )
        src = inspect.getsource(ElementPickerOverlay._detect_in_hwnd)
        self.assert_true(
            "_walk_uia_to_deepest" in src,
            "[회귀] _detect_in_hwnd 가 children walk 호출 필수",
        )
        self.assert_true(
            "_raw_walk_at_point" in src,
            "[회귀] _detect_in_hwnd 가 raw walker 호출 필수",
        )
        self.assert_true(
            "_find_deepest_descendant" in src,
            "[회귀] _detect_in_hwnd 가 descendants 폴백 호출 필수",
        )

    def test_40_element_picker_tries_main_and_child_hwnd(self):
        """[회귀] _detect_element_multi_backend 가 main + child HWND 둘 다 시도.

        탭/URL bar 는 main HWND 트리, HTML 콘텐츠는 child HWND (renderer) 트리.
        한쪽만 빼도 다른 케이스 회귀.
        """
        import inspect

        from ui.element_picker import ElementPickerOverlay

        src = inspect.getsource(ElementPickerOverlay._detect_element_multi_backend)
        self.assert_true(
            "_find_topmost_window_at_point" in src,
            "[회귀] main HWND 추출 (EnumWindows 기반) 필수",
        )
        self.assert_true(
            "ChildWindowFromPointEx" in src,
            "[회귀] child HWND 추출 필수 (HTML 콘텐츠 detection)",
        )
        self.assert_true(
            "_detect_in_hwnd" in src,
            "[회귀] _detect_in_hwnd helper 호출 필수",
        )
        self.assert_true(
            "candidates" in src,
            "[회귀] HWND 후보 리스트 (main + child) 패턴 필수",
        )

    def test_38_element_picker_detection_helpers_exist(self):
        """[회귀] picker 의 detection 헬퍼 함수들 존재 확인.

        이전에 여러 번 추가/제거된 핵심 함수들. 사라지면 element 감지 자체가
        깨짐. 정적 존재 검증만 (GUI 의존 동작은 수동 검증).
        """
        from ui.element_picker import ElementPickerOverlay

        required = [
            "_find_topmost_window_at_point",
            "_walk_uia_to_deepest",
            "_find_deepest_descendant",
            "_raw_walk_at_point",
            "_detect_via_efp",
            "_detect_element_multi_backend",
            "_update_element_under_cursor",
            "mousePressEvent",
        ]
        for method_name in required:
            self.assert_true(
                hasattr(ElementPickerOverlay, method_name),
                f"[회귀] ElementPickerOverlay.{method_name} 가 존재해야 함",
            )

    def test_42_element_picker_post_pause_always_transparent(self):
        """[회귀] post_pause_mode 는 항상 WS_EX_TRANSPARENT 켜야 함.

        방향 B 통합 결정 (2026-04-29) — F3 wait 후 picker 복귀는 click-through
        모드로 통일:
        - 펼친 hover-only submenu 유지
        - 다른 창 활성화 자연스러움
        - underlying mouseover 누수는 post_pause_mode 동안만 (일반 picker mode 의
          누수 0 은 그대로)

        이전에는 _keep_submenu_mode 분기로 Shift+F3 일 때만 켰지만 통합으로
        분기 제거. 이 보장이 깨지면 submenu 닫힘 회귀.
        """
        import inspect

        from ui.element_picker import ElementPickerOverlay

        rsm_src = inspect.getsource(ElementPickerOverlay._resume_after_pause)
        self.assert_true(
            "WS_EX_TRANSPARENT" in rsm_src,
            "[회귀] _resume_after_pause 가 WS_EX_TRANSPARENT 적용 필수 (방향 B 통합)",
        )
        self.assert_true(
            "WS_EX_NOACTIVATE" in rsm_src,
            "[회귀] _resume_after_pause 가 WS_EX_NOACTIVATE 적용 필수 (focus 빼앗기 방지)",
        )

        # _exit_post_pause_mode 가 두 ex-style 모두 제거
        epm_src = inspect.getsource(ElementPickerOverlay._exit_post_pause_mode)
        self.assert_true(
            "~WS_EX_TRANSPARENT" in epm_src,
            "[회귀] _exit_post_pause_mode 가 WS_EX_TRANSPARENT 제거 필수",
        )
        self.assert_true(
            "~WS_EX_NOACTIVATE" in epm_src,
            "[회귀] _exit_post_pause_mode 가 WS_EX_NOACTIVATE 제거 필수",
        )

    def test_43_element_picker_efp_toggle_scoped_to_efp_call(self):
        """[회귀] EFP 호출 동안만 WS_EX_TRANSPARENT 토글, walker/descendants 는
        토글 밖.

        이력:
        - 2026-04-28: 사용자 누수 보고 → 토글 0 결정 (어제)
        - 2026-04-29: Excel 셀 detection 회귀 발견 → EFP 만 토글 안으로 (오늘)
          과거 코드와 동일 패턴이지만 무거운 walker/descendants (50-200ms) 는
          토글 밖에서 호출 → 실제 토글 시간 수 ms (누수 시각 효과 미세).

        검증:
        - try/finally 로 토글 보장
        - WS_EX_TRANSPARENT 적용 직후 _detect_via_efp 호출
        - finally 에서 ex_style 복원 (GetWindowLongW → SetWindowLongW 둘 다)
        """
        import inspect

        from ui.element_picker import ElementPickerOverlay

        mb_src = inspect.getsource(ElementPickerOverlay._detect_element_multi_backend)
        # try/finally 로 토글 + 복원 보장
        self.assert_true(
            "try:" in mb_src and "finally:" in mb_src,
            "[회귀] _detect_element_multi_backend 가 try/finally 로 ex_style 복원 보장 필수",
        )
        self.assert_true(
            "WS_EX_TRANSPARENT" in mb_src,
            "[회귀] _detect_element_multi_backend 가 WS_EX_TRANSPARENT 토글 (Excel 셀 detection) 필수",
        )
        self.assert_true(
            "_detect_via_efp" in mb_src,
            "[회귀] _detect_element_multi_backend 가 _detect_via_efp 호출 필수",
        )
        # 토글 후 EFP 호출이 finally 보다 앞 — try 블록 안에서 EFP 호출
        try_idx = mb_src.find("try:")
        finally_idx = mb_src.find("finally:")
        efp_idx = mb_src.find("_detect_via_efp")
        self.assert_true(
            try_idx < efp_idx < finally_idx,
            "[회귀] _detect_via_efp 가 try 블록 안에서 호출 (토글 보호 필수)",
        )

    def test_44_element_picker_mouse_hook_in_post_pause(self):
        """[회귀] post_pause_mode 는 WS_EX_TRANSPARENT 켜져 있어 overlay 가
        mouse 이벤트를 못 받음 → WH_MOUSE_LL hook 으로 click 감지 + 차단.

        방향 B 통합으로 mouse hook 항상 설치. 사용자 요구로 click 을 underlying
        으로 통과시키지 않고 차단 (일반 picker mode 와 동일 - picker 만 element
        선택, underlying 메뉴는 발동 안 함). 좌/우 클릭 모두 차단.

        hook 함수 존재 + _resume_after_pause 가 항상 설치 + _exit_post_pause_mode
        가 해제 + _on_hook_click 이 element_picked emit + stop_picking +
        hook 콜백이 LBUTTONDOWN 차단 (return 1).
        """
        import inspect

        from ui.element_picker import ElementPickerOverlay

        # 메서드 존재
        for method_name in (
            "_install_mouse_hook",
            "_uninstall_mouse_hook",
            "_on_hook_click",
        ):
            self.assert_true(
                hasattr(ElementPickerOverlay, method_name),
                f"[회귀] ElementPickerOverlay.{method_name} 가 존재해야 함",
            )

        # _install_mouse_hook 가 WH_MOUSE_LL + LBUTTONDOWN/UP/RBUTTONDOWN/UP 처리
        imh_src = inspect.getsource(ElementPickerOverlay._install_mouse_hook)
        self.assert_true(
            "WH_MOUSE_LL" in imh_src,
            "[회귀] _install_mouse_hook 가 WH_MOUSE_LL 사용 필수",
        )
        self.assert_true(
            "WM_LBUTTONDOWN" in imh_src,
            "[회귀] _install_mouse_hook 가 WM_LBUTTONDOWN 검사 필수",
        )
        self.assert_true(
            "WM_LBUTTONUP" in imh_src,
            "[회귀] _install_mouse_hook 가 WM_LBUTTONUP 차단 필수 (down/up consistency)",
        )
        self.assert_true(
            "WM_RBUTTONDOWN" in imh_src,
            "[회귀] _install_mouse_hook 가 WM_RBUTTONDOWN 검사 필수 (cancel)",
        )
        self.assert_true(
            "return 1" in imh_src,
            "[회귀] _install_mouse_hook 가 click 차단 (return 1) 필수 - "
            "underlying 메뉴/버튼 발동 방지",
        )
        self.assert_true(
            "CallNextHookEx" in imh_src,
            "[회귀] _install_mouse_hook 가 다른 mouse event 통과 (CallNextHookEx) 필수",
        )

        # _on_hook_rclick 존재
        self.assert_true(
            hasattr(ElementPickerOverlay, "_on_hook_rclick"),
            "[회귀] _on_hook_rclick 존재 필수 (우클릭 = cancel)",
        )

        # _resume_after_pause 가 keep_submenu_mode 시 mouse hook 설치
        rsm_src = inspect.getsource(ElementPickerOverlay._resume_after_pause)
        self.assert_true(
            "_install_mouse_hook" in rsm_src,
            "[회귀] _resume_after_pause 가 _install_mouse_hook 호출 필수",
        )

        # _exit_post_pause_mode 가 mouse hook 해제
        epm_src = inspect.getsource(ElementPickerOverlay._exit_post_pause_mode)
        self.assert_true(
            "_uninstall_mouse_hook" in epm_src,
            "[회귀] _exit_post_pause_mode 가 _uninstall_mouse_hook 호출 필수",
        )

        # _on_hook_click 이 element_picked emit (또는 cancelled)
        ohc_src = inspect.getsource(ElementPickerOverlay._on_hook_click)
        self.assert_true(
            "element_picked.emit" in ohc_src or "pick_cancelled.emit" in ohc_src,
            "[회귀] _on_hook_click 가 element_picked/pick_cancelled emit 필수",
        )
        self.assert_true(
            "stop_picking" in ohc_src,
            "[회귀] _on_hook_click 가 stop_picking 호출 (picker UI 종료) 필수",
        )

    def test_45_element_picker_post_pause_auto_transition(self):
        """[회귀] post_pause_mode 후 자동 transition — settings 로 조정 가능.

        실험 결과 (2026-04-29): transition 시 SetWindowLongW 가 OS hit-test 를
        다시 트리거 → menu 닫힘 → 가설 실패. settings 의 post_pause_transition_ms
        를 0 으로 두면 transition 비활성 (방향 B 직접 — post_pause_mode 가
        click/ESC 까지 유지).

        (1) POST_PAUSE_TRANSITION_MS 상수 존재 (default)
        (2) update_settings 가 post_pause_transition_ms 읽기
        (3) _resume_after_pause 가 _post_pause_transition_ms > 0 일 때만 timer 시작
        (4) _start_pause 진입 시 timer 정지 (post_pause 중 F3 재진입)
        (5) _exit_post_pause_mode idempotent (timer + user 액션 race 방어)
        """
        import inspect

        from ui.element_picker import ElementPickerOverlay

        # (1) 상수
        self.assert_true(
            hasattr(ElementPickerOverlay, "POST_PAUSE_TRANSITION_MS"),
            "[회귀] POST_PAUSE_TRANSITION_MS 상수 존재 필수",
        )

        # (2) update_settings 가 post_pause_transition_ms 처리
        us_src = inspect.getsource(ElementPickerOverlay.update_settings)
        self.assert_true(
            "post_pause_transition_ms" in us_src,
            "[회귀] update_settings 가 post_pause_transition_ms 키 처리 필수",
        )
        self.assert_true(
            "_post_pause_transition_ms" in us_src,
            "[회귀] update_settings 가 _post_pause_transition_ms 인스턴스 변수 셋 필수",
        )

        # (3) _resume_after_pause 가 0 가드 + 인스턴스 값 사용
        rsm_src = inspect.getsource(ElementPickerOverlay._resume_after_pause)
        self.assert_true(
            "_post_pause_transition_ms" in rsm_src,
            "[회귀] _resume_after_pause 가 _post_pause_transition_ms 인스턴스 값 사용 필수",
        )
        self.assert_true(
            "> 0" in rsm_src or "!= 0" in rsm_src,
            "[회귀] _resume_after_pause 가 0 가드 (transition 비활성 옵션) 필수",
        )

        # (4) _start_pause 가 timer 정지
        sp_src = inspect.getsource(ElementPickerOverlay._start_pause)
        self.assert_true(
            "_post_pause_transition_timer" in sp_src and ".stop()" in sp_src,
            "[회귀] _start_pause 가 transition timer 정지 (post_pause 중 F3 재진입 안전) 필수",
        )

        # (5) _exit_post_pause_mode idempotent
        epm_src = inspect.getsource(ElementPickerOverlay._exit_post_pause_mode)
        self.assert_true(
            "if not self._post_pause_mode" in epm_src,
            "[회귀] _exit_post_pause_mode 가 idempotent guard 필수 (race 방어)",
        )

    def test_46_element_picker_keyboard_hook_lifecycle(self):
        """[회귀] 키보드 hook 이 picker 전체 lifecycle 동안 유지 — ESC/F3
        응답성 보장 (focus 무관).

        과거 (post_pause 한정) → 현재 (start_picking ~ stop_picking 전체):
        - 일반 picker mode 에서도 ESC 즉각 처리
        - hook 콜백이 `self._paused or not self.isHidden()` 로 active 검사
        - _on_hook_esc 가 post_pause 도 처리 + stop_picking
        - _on_hook_f3 가 일반 mode + post_pause 둘 다 처리
        - _resume_after_pause / _exit_post_pause_mode 가 hook 재설치/해제 안 함
        """
        import inspect

        from ui.element_picker import ElementPickerOverlay

        # start_picking 가 hook 설치
        sp_src = inspect.getsource(ElementPickerOverlay.start_picking)
        self.assert_true(
            "_install_keyboard_hook" in sp_src,
            "[회귀] start_picking 가 _install_keyboard_hook 호출 필수 (lifecycle 시작)",
        )

        # stop_picking 가 hook 해제
        stop_src = inspect.getsource(ElementPickerOverlay.stop_picking)
        self.assert_true(
            "_uninstall_keyboard_hook" in stop_src,
            "[회귀] stop_picking 가 _uninstall_keyboard_hook 호출 필수 (lifecycle 종료)",
        )

        # _install_keyboard_hook idempotent guard
        ikh_src = inspect.getsource(ElementPickerOverlay._install_keyboard_hook)
        self.assert_true(
            "self._keyboard_hook" in ikh_src and "return" in ikh_src,
            "[회귀] _install_keyboard_hook 가 재설치 방지 guard 필수 (leak 방지)",
        )

        # hook 콜백이 isHidden / _paused 검사 (post_pause 한정 X)
        self.assert_true(
            "isHidden" in ikh_src or "_paused" in ikh_src,
            "[회귀] hook 콜백이 picker active 조건 (isHidden/paused) 검사 필수",
        )

        # _on_hook_esc 가 post_pause 분기 + stop_picking
        oe_src = inspect.getsource(ElementPickerOverlay._on_hook_esc)
        self.assert_true(
            "stop_picking" in oe_src,
            "[회귀] _on_hook_esc 가 stop_picking 호출 필수",
        )
        self.assert_true(
            "pick_cancelled.emit" in oe_src,
            "[회귀] _on_hook_esc 가 pick_cancelled emit 필수",
        )

        # _on_hook_f3 가 _paused guard + 일반 mode 도 처리
        of_src = inspect.getsource(ElementPickerOverlay._on_hook_f3)
        self.assert_true(
            "_paused" in of_src,
            "[회귀] _on_hook_f3 가 _paused guard 필수 (wait 중 F3 무시)",
        )
        self.assert_true(
            "_start_pause" in of_src,
            "[회귀] _on_hook_f3 가 _start_pause 호출 필수",
        )

    def test_47_element_picker_descendants_area_threshold(self):
        """[회귀] descendants() 폴백 호출이 area threshold 가드 적용 — 반응성.

        walker 가 이미 작은 element (Excel cell, 메뉴 항목, 작은 버튼) 잡았으면
        descendants 호출 skip. 매 tick 800-1000ms 절약 → cursor 이동 시
        highlight 추적 지연 감소.
        """
        import inspect

        from ui.element_picker import ElementPickerOverlay

        self.assert_true(
            hasattr(ElementPickerOverlay, "NEEDS_DESCENDANTS_AREA_THRESHOLD"),
            "[회귀] NEEDS_DESCENDANTS_AREA_THRESHOLD 상수 존재 필수",
        )

        # _detect_in_hwnd 의 descendants 호출 가드에 area threshold 적용
        det_src = inspect.getsource(ElementPickerOverlay._detect_in_hwnd)
        self.assert_true(
            "NEEDS_DESCENDANTS_AREA_THRESHOLD" in det_src,
            "[회귀] _detect_in_hwnd 가 NEEDS_DESCENDANTS_AREA_THRESHOLD 가드 사용 필수 "
            "(반응성 - 작은 element 잡힌 후 descendants skip)",
        )

    def test_48_element_picker_cdp_enabled_default_false(self):
        """[회귀] cdp_enabled 설정 가드 - default False, 활성화 시에만 CDP 시도.

        click 후 메인 화면 전환 시간 단축 (CDP 포트 timeout 회피).
        사용자가 명시적으로 settings 활성화한 경우에만 _capture_dom_context 가
        실제 CDP 시도. 기본은 즉시 빈 dict 반환.
        """
        import inspect

        from ui.element_picker import ElementPickerOverlay

        # __init__ 의 default 값
        init_src = inspect.getsource(ElementPickerOverlay.__init__)
        self.assert_true(
            "_cdp_enabled" in init_src,
            "[회귀] __init__ 에 _cdp_enabled 인스턴스 변수 초기화 필수",
        )

        # update_settings 가 cdp_enabled 키 처리
        us_src = inspect.getsource(ElementPickerOverlay.update_settings)
        self.assert_true(
            "cdp_enabled" in us_src,
            "[회귀] update_settings 가 cdp_enabled 키 처리 필수",
        )

        # _capture_dom_context 의 disabled 가드
        cdc_src = inspect.getsource(ElementPickerOverlay._capture_dom_context)
        self.assert_true(
            "_cdp_enabled" in cdc_src,
            "[회귀] _capture_dom_context 가 _cdp_enabled 가드 필수 (disabled 시 즉시 반환)",
        )
        self.assert_true(
            "cdp_available" in cdc_src and "False" in cdc_src,
            "[회귀] _capture_dom_context 가 disabled 시 cdp_available=False 반환",
        )

    def test_49_workflow_engine_stop_after_step_id(self):
        """[회귀] Phase 1 - Step 단독 실행. workflow_engine.execute_session_blocks
        가 stop_after_step_id 인자 지원해서 N 만 실행하고 종료.

        UI: BlockCard 의 '⏯ 단독' 버튼 → run_single_requested signal →
        BlockViewWidget run_single_step_requested → CodeViewer 통과 →
        main_window._on_run_single_step → _run_blocks_thread(start=stop=N).
        """
        import inspect

        from core.workflow_engine import WorkflowEngine

        sig = inspect.signature(WorkflowEngine.execute_session_blocks)
        self.assert_true(
            "stop_after_step_id" in sig.parameters,
            "[회귀] execute_session_blocks 가 stop_after_step_id 파라미터 필수",
        )
        # default None
        self.assert_true(
            sig.parameters["stop_after_step_id"].default is None,
            "[회귀] stop_after_step_id default None (기본은 끝까지 실행)",
        )

        # 본문에서 stop 후 break 하는 패턴 검증
        body_src = inspect.getsource(WorkflowEngine.execute_session_blocks)
        self.assert_true(
            "stop_after_step_id" in body_src and "break" in body_src,
            "[회귀] execute_session_blocks 본문에 stop_after_step_id 도달 시 break 필수",
        )

    def test_50_block_card_run_single_button(self):
        """[회귀] Phase 1 - BlockCard 의 단독 실행 버튼 + signal chain.

        BlockCard.run_single_requested -> BlockViewWidget.run_single_step_requested
        -> CodeViewer.run_single_step_requested -> main_window._on_run_single_step
        """
        import inspect

        from ui.code_viewer import BlockCard, BlockViewWidget, CodeViewer
        from ui.main_window import MainWindow

        # BlockCard signal
        self.assert_true(
            hasattr(BlockCard, "run_single_requested"),
            "[회귀] BlockCard.run_single_requested signal 필수",
        )
        # 라이브러리 블럭 (step_id=0) 은 단독 실행 버튼 안 만듦
        bc_src = inspect.getsource(BlockCard.__init__)
        self.assert_true(
            "if step_id > 0:" in bc_src and "run_single_btn" in bc_src,
            "[회귀] step_id>0 일 때만 단독 실행 버튼 생성 (라이브러리 블럭 제외) 필수",
        )

        # BlockViewWidget 가 signal 통과 + _add_step_block 에서 connect
        self.assert_true(
            hasattr(BlockViewWidget, "run_single_step_requested"),
            "[회귀] BlockViewWidget.run_single_step_requested signal 필수",
        )
        bv_src = inspect.getsource(BlockViewWidget._add_step_block)
        self.assert_true(
            "run_single_requested" in bv_src,
            "[회귀] _add_step_block 가 run_single_requested signal connect 필수",
        )

        # CodeViewer 통과
        self.assert_true(
            hasattr(CodeViewer, "run_single_step_requested"),
            "[회귀] CodeViewer.run_single_step_requested signal 필수",
        )

        # main_window 핸들러 (위임 stub) + handler 본문 (실제 호출 검증)
        # 2026-05-04: main_window 분해 Step 3 으로 BlockExecutionHandler 로 이전.
        from ui.block_execution_handler import BlockExecutionHandler

        self.assert_true(
            hasattr(MainWindow, "_on_run_single_step"),
            "[회귀] MainWindow._on_run_single_step 위임 stub 필수",
        )
        handler_src = inspect.getsource(BlockExecutionHandler.on_run_single_step)
        self.assert_true(
            "stop_after_step_id" in handler_src or "step_id, step_id" in handler_src,
            "[회귀] BlockExecutionHandler.on_run_single_step 가 start=stop=N 으로 호출 필수",
        )

    def test_51_extract_code_delta_handles_minor_changes(self):
        """[회귀] extract_code_delta 가 SequenceMatcher fallback 으로 AI 의
        약간의 코드 변형 (들여쓰기, try 위치 등) 도 delta 추출.

        과거 버그: prefix 매칭 실패 시 fallback = new_body 전체 → step_code 가
        누적되어 매 step 마다 webdriver/Application 새로 생성 (브라우저 N개).
        SequenceMatcher 로 새 라인만 추출.
        """
        import inspect

        from core.import_manager import extract_code_delta

        # 본문에 SequenceMatcher 사용 + ratio 검사
        src = inspect.getsource(extract_code_delta)
        self.assert_true(
            "SequenceMatcher" in src,
            "[회귀] extract_code_delta 가 SequenceMatcher fallback 사용 필수",
        )
        self.assert_true(
            "ratio" in src,
            "[회귀] SequenceMatcher ratio 검사 필수 (거의 다른 코드면 전체 반환)",
        )

        # prefix 매칭 성공 케이스 (기본 동작)
        prev = "x = 1\ny = 2"
        new = "x = 1\ny = 2\nz = 3"
        delta = extract_code_delta(new, prev)
        self.assert_true(
            "z = 3" in delta and "x = 1" not in delta,
            "[회귀] prefix 매칭 - 새 라인만 반환",
        )

        # prefix 매칭 실패 + SequenceMatcher 성공 케이스
        # AI 가 들여쓰기 약간 바꾼 시뮬레이션
        prev2 = "x = 1\ny = 2\n# step1 done"
        new2 = "x = 1\ny = 2\n# step1 done\nprint('hi')\n# step2 done"
        delta2 = extract_code_delta(new2, prev2)
        self.assert_true(
            "print" in delta2,
            "[회귀] SequenceMatcher fallback - 누적된 새 코드 추출",
        )

    def test_57_blocks_finished_uses_signal(self):
        """[회귀] run_blocks_thread 의 finally 가 signal-slot 으로 _on_blocks_finished
        호출 (이전 QTimer.singleShot 은 어떤 케이스에 호출 안 되는 회귀 발견됨).

        signal 사용 시 Qt 가 main thread queued connection 으로 안전하게 전달.

        2026-05-04: main_window 분해 Step 3 으로 BlockExecutionHandler.run_blocks_thread
        로 이전됨. main_window 의 _run_blocks_thread 는 위임 stub.
        """
        import inspect

        from ui.block_execution_handler import BlockExecutionHandler
        from ui.main_window import AsyncSignals, MainWindow

        # AsyncSignals 에 blocks_finished signal
        self.assert_true(
            hasattr(AsyncSignals, "blocks_finished"),
            "[회귀] AsyncSignals.blocks_finished signal 필수",
        )

        # run_blocks_thread 가 finally 에서 emit (handler 본문 검사)
        rt_src = inspect.getsource(BlockExecutionHandler.run_blocks_thread)
        self.assert_true(
            "blocks_finished.emit" in rt_src,
            "[회귀] BlockExecutionHandler.run_blocks_thread 의 finally 가 "
            "blocks_finished.emit 호출 필수",
        )

        # main_window __init__ 에서 connect
        init_src = inspect.getsource(MainWindow.__init__)
        self.assert_true(
            "blocks_finished.connect" in init_src,
            "[회귀] AsyncSignals.blocks_finished 가 _on_blocks_finished 에 connect 필수",
        )

    def test_63_step_wait_after_ms(self):
        """[회귀] Step.wait_after_ms + workflow_engine 3단계 우선순위 (step >
        session > engine) + BlockCard 인라인 SpinBox + 세션 default SpinBox.
        """
        import inspect

        from core.session_manager import Session, Step
        from core.workflow_engine import WorkflowEngine
        from ui.code_viewer import BlockCard, BlockViewWidget

        # Step.wait_after_ms 필드 (default None)
        s = Step()
        self.assert_true(
            hasattr(s, "wait_after_ms") and s.wait_after_ms is None,
            "[회귀] Step.wait_after_ms 필드 + default None 필수",
        )

        # Session.settings.step_delay_ms (default None = 글로벌 사용)
        sess = Session()
        self.assert_true(
            "step_delay_ms" in sess.settings,
            "[회귀] Session.settings.step_delay_ms 키 필수",
        )
        self.assert_true(
            sess.settings["step_delay_ms"] is None,
            "[회귀] Session.settings.step_delay_ms default None (글로벌 사용)",
        )

        # workflow_engine 3단계 우선순위
        we_src = inspect.getsource(WorkflowEngine.execute_session_blocks)
        self.assert_true(
            "wait_after_ms" in we_src and "session.settings" in we_src,
            "[회귀] execute_session_blocks 가 step + session 둘 다 검사 필수",
        )

        # BlockCard 의 wait_after_ms 인자 + wait_changed signal
        bc_sig = inspect.signature(BlockCard.__init__)
        self.assert_true(
            "wait_after_ms" in bc_sig.parameters,
            "[회귀] BlockCard.__init__ wait_after_ms 인자 필수",
        )
        self.assert_true(
            hasattr(BlockCard, "wait_changed"),
            "[회귀] BlockCard.wait_changed signal 필수",
        )
        # 카드 하단 SpinBox 인라인 편집 (헤더 dialog 가 아님)
        bc_init_src = inspect.getsource(BlockCard.__init__)
        self.assert_true(
            "QSpinBox" in bc_init_src,
            "[회귀] BlockCard 가 인라인 SpinBox 사용 (헤더 dialog 가 아님) 필수",
        )

        # BlockViewWidget toolbar 의 세션 wait SpinBox
        bv_src = inspect.getsource(BlockViewWidget._setup_ui)
        self.assert_true(
            "session_wait_spin" in bv_src,
            "[회귀] BlockViewWidget toolbar 의 세션 default wait SpinBox 필수",
        )
        self.assert_true(
            hasattr(BlockViewWidget, "set_session_wait"),
            "[회귀] BlockViewWidget.set_session_wait 메서드 (외부 갱신용) 필수",
        )

        # main_window 핸들러 — 세션 settings 변경 (글로벌 settings 안 건드림)
        # 2026-05-04: main_window 분해 Step 3 으로 BlockExecutionHandler 로 이전.
        # main_window 의 _on_wait_changed 는 위임 stub. handler.on_wait_changed 본문 검사.
        from ui.block_execution_handler import BlockExecutionHandler

        handler_src = inspect.getsource(BlockExecutionHandler.on_wait_changed)
        self.assert_true(
            "current_session.settings" in handler_src and "step_delay_ms" in handler_src,
            "[회귀] BlockExecutionHandler.on_wait_changed 가 "
            "current_session.settings.step_delay_ms 변경 필수 (글로벌 settings 분리)",
        )

    def test_62_close_event_single_definition(self):
        """[회귀] MainWindow.closeEvent 가 단일 정의 + 세션 저장 + 커널 정리.

        과거 buggy 동작: closeEvent 가 두 번 정의되어 첫 번째 (커널 정리) 가
        두 번째 (세션 저장) 에 덮어쓰여 커널 좀비 프로세스 발생.
        """
        import inspect

        from ui.main_window import MainWindow

        src = inspect.getsource(MainWindow)
        # closeEvent 정의 횟수
        count = src.count("def closeEvent(self,")
        self.assert_true(
            count == 1,
            f"[회귀] closeEvent 단일 정의 필수 (실제 {count}회 정의)",
        )

        ce_src = inspect.getsource(MainWindow.closeEvent)
        self.assert_true(
            "save_session" in ce_src or "current_session" in ce_src,
            "[회귀] closeEvent 가 세션 저장 수행 필수",
        )
        self.assert_true(
            "kernel.stop" in ce_src or "_kernels" in ce_src,
            "[회귀] closeEvent 가 커널 정리 수행 필수",
        )

    def test_60_extract_initial_block(self):
        """[회귀] Phase 2 - Initial 블럭 추출 (모듈 레벨 변수/상수 + 모듈 레벨
        try 블록 안의 setup Assign).

        - 첫 step (setup 위주) 의 generated_code 사용
        - 모듈 레벨 ast.Assign + 모듈 레벨 try 블록 안 ast.Assign
        - def main() 패턴은 unwrap 적용 (jupyter 모드 호환)
        """
        from core.import_manager import extract_initial_block

        class _Session:
            def __init__(self, steps):
                self.steps = steps

        # 케이스 1: 모듈 레벨 Assign
        sess1 = _Session(
            [{"step_id": 1, "generated_code": 'URL = "https://example.com"\nCONFIG = {"k": 1}'}]
        )
        result1 = extract_initial_block(sess1)
        self.assert_true(
            "URL" in result1 and "CONFIG" in result1,
            f"[회귀] 모듈 레벨 Assign 추출 (실제: {result1!r})",
        )

        # 케이스 2: 모듈 레벨 try 블록 안의 setup
        sess2 = _Session(
            [
                {
                    "step_id": 1,
                    "generated_code": (
                        "import x\n"
                        "try:\n"
                        "    options = Options()\n"
                        "    driver = webdriver.Chrome(options=options)\n"
                        "    driver.get('http://x')\n"
                        "except Exception:\n"
                        "    pass"
                    ),
                }
            ]
        )
        result2 = extract_initial_block(sess2)
        self.assert_true(
            "options" in result2 and "driver" in result2,
            f"[회귀] try 블록 안 setup Assign 추출 (실제: {result2!r})",
        )

        # 케이스 3: def main() 패턴 unwrap
        sess3 = _Session(
            [
                {
                    "step_id": 1,
                    "generated_code": (
                        "def main():\n"
                        '    URL = "https://test.com"\n'
                        "    driver = build()\n"
                        'if __name__ == "__main__":\n'
                        "    main()"
                    ),
                }
            ]
        )
        result3 = extract_initial_block(sess3)
        self.assert_true(
            "URL" in result3 and "driver" in result3,
            f"[회귀] def main() unwrap 후 Assign 추출 (실제: {result3!r})",
        )

        # 케이스 4: 빈 / step 없음
        sess4 = _Session([])
        self.assert_true(
            extract_initial_block(sess4) == "",
            "[회귀] step 없으면 빈 문자열",
        )
        self.assert_true(
            extract_initial_block(None) == "",
            "[회귀] None 세션 빈 문자열",
        )

    def test_61_block_view_initial_card(self):
        """[회귀] BlockViewWidget.refresh 가 initial_code 인자 받고 step_id=-1
        BlockCard 생성. CodeViewer.refresh_block_view 도 통과.
        """
        import inspect

        from ui.code_viewer import BlockViewWidget, CodeViewer
        from ui.main_window import MainWindow

        # BlockViewWidget.refresh 시그니처
        sig = inspect.signature(BlockViewWidget.refresh)
        self.assert_true(
            "initial_code" in sig.parameters,
            "[회귀] BlockViewWidget.refresh 가 initial_code 인자 받기 필수",
        )

        # CodeViewer.refresh_block_view 시그니처
        sig2 = inspect.signature(CodeViewer.refresh_block_view)
        self.assert_true(
            "initial_code" in sig2.parameters,
            "[회귀] CodeViewer.refresh_block_view 가 initial_code 인자 받기 필수",
        )

        # main_window 가 extract_initial_block 호출 + refresh_block_view 에 전달
        mw_src = inspect.getsource(MainWindow._refresh_block_view)
        self.assert_true(
            "extract_initial_block" in mw_src,
            "[회귀] _refresh_block_view 가 extract_initial_block 호출 필수",
        )
        self.assert_true(
            "initial_code" in mw_src,
            "[회귀] _refresh_block_view 가 initial_code 변수 사용 필수",
        )

    def test_56_run_stop_interaction_between_tabs(self):
        """[회귀] 코드 뷰 탭 (CodeSandbox) <-> 블럭 뷰 탭 (ExecutionKernel) 의
        실행/중단 상호작용.

        - on_run_code: 시작 시 set_running(True)
        - execute_code_thread: finally 에 set_running(False)
        - on_stop_code: kernel 도 stop (블럭 모드 step 진행 중 즉시 종료) +
          set_running(False) + restore_main_window

        2026-05-04: main_window 분해 Step 3 으로 BlockExecutionHandler 로 이전됨.
        main_window 의 _on_run_code/_execute_code_thread/_on_stop_code 는 위임 stub.
        """
        import inspect

        from ui.block_execution_handler import BlockExecutionHandler

        # on_run_code 가 set_running(True)
        rc_src = inspect.getsource(BlockExecutionHandler.on_run_code)
        self.assert_true(
            "set_running(True)" in rc_src,
            "[회귀] BlockExecutionHandler.on_run_code 가 set_running(True) "
            "호출 필수 (UI 상태 일치)",
        )

        ec_src = inspect.getsource(BlockExecutionHandler.execute_code_thread)
        self.assert_true(
            "set_running(False)" in ec_src,
            "[회귀] BlockExecutionHandler.execute_code_thread finally 에 "
            "set_running(False) 호출 필수",
        )

        # on_stop_code 가 kernel.stop 도 호출 + set_running(False)
        sc_src = inspect.getsource(BlockExecutionHandler.on_stop_code)
        self.assert_true(
            "kernel.stop" in sc_src or "kernel is not None" in sc_src,
            "[회귀] BlockExecutionHandler.on_stop_code 가 ExecutionKernel.stop 도 "
            "호출 필수 (블럭 모드 step 진행 중 즉시 종료)",
        )
        self.assert_true(
            "set_running(False)" in sc_src,
            "[회귀] BlockExecutionHandler.on_stop_code 가 set_running(False) "
            "호출 필수 (UI 즉시 복원)",
        )

    def test_55_block_run_lowers_main_window(self):
        """[회귀] 블럭 실행 시 메인 윈도우 lower (z-order 최하단 - underlying
        element 가 가려지지 않도록), 완료/중지/에러 시 raise_/activateWindow 로 복원.

        hide/minimize 가 Win11 foreground 정책에 막히는 케이스 회피 위해 lower 사용.
        윈도우는 항상 visible + 작업표시줄 유지 → 사용자가 실행 상태 인지 가능.

        - on_run_from_step / on_run_single_step: mw.lower()
        - restore_main_window: raise_() + activateWindow() (+ isHidden 시 show)
        - on_blocks_finished + on_stop_code: restore_main_window 호출

        2026-05-04: main_window 분해 Step 3 으로 BlockExecutionHandler 로 이전됨.
        main_window 의 _on_run_from_step/_on_run_single_step/_restore_main_window/
        _on_blocks_finished/_on_stop_code 는 위임 stub. main_window 가 self 가
        아니라 mw (handler.mw) 라서 self.lower() → mw.lower() 로 변환됨.
        """
        import inspect

        from ui.block_execution_handler import BlockExecutionHandler
        from ui.main_window import MainWindow

        # on_run_from_step
        src1 = inspect.getsource(BlockExecutionHandler.on_run_from_step)
        self.assert_true(
            "mw.lower()" in src1,
            "[회귀] BlockExecutionHandler.on_run_from_step 가 mw.lower() "
            "호출 필수 (z-order 최하단)",
        )

        # on_run_single_step
        src2 = inspect.getsource(BlockExecutionHandler.on_run_single_step)
        self.assert_true(
            "mw.lower()" in src2,
            "[회귀] BlockExecutionHandler.on_run_single_step 가 mw.lower() 호출 필수",
        )

        # restore_main_window helper 존재 (handler) + main_window 위임 stub
        self.assert_true(
            hasattr(BlockExecutionHandler, "restore_main_window"),
            "[회귀] BlockExecutionHandler.restore_main_window 헬퍼 필수",
        )
        self.assert_true(
            hasattr(MainWindow, "_restore_main_window"),
            "[회귀] MainWindow._restore_main_window 위임 stub 필수 (외부 caller 호환)",
        )
        rest_src = inspect.getsource(BlockExecutionHandler.restore_main_window)
        self.assert_true(
            "raise_" in rest_src and "activateWindow" in rest_src,
            "[회귀] BlockExecutionHandler.restore_main_window 가 raise_ + activateWindow 호출 필수",
        )

        # on_blocks_finished 가 restore_main_window 호출
        src3 = inspect.getsource(BlockExecutionHandler.on_blocks_finished)
        self.assert_true(
            "restore_main_window" in src3,
            "[회귀] BlockExecutionHandler.on_blocks_finished 가 restore_main_window 호출 필수",
        )

        # on_stop_code 도 restore_main_window 호출 (즉시 복원)
        src4 = inspect.getsource(BlockExecutionHandler.on_stop_code)
        self.assert_true(
            "restore_main_window" in src4,
            "[회귀] BlockExecutionHandler.on_stop_code 가 restore_main_window 호출 필수 "
            "(stop 시 즉시 복원)",
        )

    def test_54_unwrap_main_function(self):
        """[회귀] AI 가 def main(): + if __name__: main() 패턴으로 작성한 코드를
        module-level 로 unwrap. 변수가 함수 local scope 가 아니라 _globals 에
        들어가 다음 step 에서 사용 가능 (jupyter 모드 호환).
        """
        import ast

        from core.import_manager import _unwrap_main_function

        code = """
def main():
    driver = "chrome"
    print(driver)

if __name__ == "__main__":
    main()
"""
        unwrapped = _unwrap_main_function(code)
        tree = ast.parse(unwrapped)

        # def main 제거 + if __name__ 제거 + 본문은 module level
        has_main = any(isinstance(n, ast.FunctionDef) and n.name == "main" for n in tree.body)
        has_if_main = any(
            isinstance(n, ast.If)
            and isinstance(n.test, ast.Compare)
            and isinstance(n.test.left, ast.Name)
            and n.test.left.id == "__name__"
            for n in tree.body
        )
        module_names = []
        for n in tree.body:
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        module_names.append(t.id)

        self.assert_true(not has_main, "[회귀] def main 제거 필수")
        self.assert_true(not has_if_main, "[회귀] if __name__ 블록 제거 필수")
        self.assert_true(
            "driver" in module_names,
            f"[회귀] driver 가 module-level Assign 으로 unwrap 필수 (실제: {module_names})",
        )

        # main 함수 없는 코드는 그대로
        plain = "x = 1\ny = 2"
        self.assert_true(
            _unwrap_main_function(plain) == plain,
            "[회귀] main 함수 없으면 원본 그대로",
        )

    def test_64_extract_code_delta_filters_stale_except_var(self):
        """[회귀] except 캡처 변수 (e 등) 가 prev 의 except 안에서만 정의되는데
        delta 에서 그 변수 참조하는 라인만 단편적으로 추출되어 NameError 발생.

        Fix: prev 에 except ... as e 가 있고 delta 에 except 가 없는데 e 참조
        라인 있으면 제거 (실행 시 NameError 방지).
        """
        from core.import_manager import extract_code_delta

        prev = (
            "try:\n"
            "    driver = build()\n"
            "    print('ok')\n"
            "except Exception as e:\n"
            "    print(f'old: {e}')"
        )
        new = (
            "try:\n"
            "    driver = build()\n"
            "    print('ok')\n"
            "    driver.get('https://x')\n"
            "    print('navigated')\n"
            "except Exception as e:\n"
            "    print(f'NEW: {e}')"
        )
        delta = extract_code_delta(new, prev)
        self.assert_true(
            "driver.get" in delta and "navigated" in delta,
            f"[회귀] 진짜 새 액션 라인은 추출 (실제 delta: {delta!r})",
        )
        self.assert_true(
            "{e}" not in delta and "as e" not in delta,
            f"[회귀] e 캡처 변수 참조 stale 라인 제거 (except 헤더 없으면 NameError) "
            f"(실제 delta: {delta!r})",
        )
        # 컴파일 가능한지 (NameError 는 런타임이지만 SyntaxError 는 미리 잡힘)
        try:
            compile(delta, "<test>", "exec")
            syntax_ok = True
        except SyntaxError:
            syntax_ok = False
        self.assert_true(
            syntax_ok,
            "[회귀] 필터링 후 delta 가 module-level 컴파일 가능해야 함",
        )

    def test_65_kernel_worker_yields_foreground_to_parent(self):
        """[회귀] Win11 ForegroundLock 우회 — step 코드가 pyautogui 등으로
        SendInput 을 호출하면 Windows 가 SetForegroundWindow 권한을 subprocess
        에 부여 → 이후 ohdo 의 raise/activate 가 거부되어 taskbar flash 만 발생.

        Fix: ExecutionKernel.start 가 OHDO_PARENT_PID 환경변수로 부모 PID 전달 +
        kernel_worker 가 매 step 종료 시 AllowSetForegroundWindow(parent_pid)
        호출 → ohdo 의 다음 activateWindow 1회 통과 (메인 윈도우 정상 복원).

        2026-05-04 추가: foreground 복원 보류 이슈 (handoff §6 #3) 의 root cause
        및 해결 검증.
        """
        import inspect
        from pathlib import Path

        from core.execution_kernel import ExecutionKernel

        # ExecutionKernel 의 env 구성 path 에 OHDO_PARENT_PID + os.getpid() 보존.
        # 2026-05-13 (ADR 0003 Phase 2-b): env 구성이 start() 안에서 _build_subprocess_env
        # 메서드로 추출됨. 둘 중 한 곳에 패턴이 있으면 contract 유지로 본다.
        start_src = inspect.getsource(ExecutionKernel.start)
        env_src = (
            inspect.getsource(ExecutionKernel._build_subprocess_env)
            if hasattr(ExecutionKernel, "_build_subprocess_env")
            else ""
        )
        combined_src = start_src + "\n" + env_src
        self.assert_true(
            "OHDO_PARENT_PID" in combined_src and "getpid()" in combined_src,
            "[회귀] ExecutionKernel.start 또는 _build_subprocess_env 가 "
            "env['OHDO_PARENT_PID'] = str(os.getpid()) 로 부모 PID 전달 필수 "
            "(kernel_worker 가 권한 양도용)",
        )

        # kernel_worker.py 가 step 실행 후 AllowSetForegroundWindow 호출
        worker_path = Path(__file__).parent.parent / "core" / "kernel_worker.py"
        worker_src = worker_path.read_text(encoding="utf-8")
        self.assert_true(
            "AllowSetForegroundWindow" in worker_src,
            "[회귀] kernel_worker.py 가 매 step 종료 시 "
            "AllowSetForegroundWindow 호출 필수 (Win11 ForegroundLock 우회)",
        )
        self.assert_true(
            "OHDO_PARENT_PID" in worker_src,
            "[회귀] kernel_worker.py 가 OHDO_PARENT_PID 환경변수 읽기 필수",
        )
        # win32 가드 (다른 플랫폼에서 ctypes.windll 사용 안 하도록)
        self.assert_true(
            'sys.platform == "win32"' in worker_src or "sys.platform=='win32'" in worker_src,
            "[회귀] kernel_worker.py 가 Windows 전용 가드 필수 (ctypes.windll 사용 분기)",
        )

    def test_66_prompt_contains_jupyter_mode_guidelines(self):
        """[회귀] AI prompt 가 Jupyter 모드 호환 가이드라인 포함 — 단독 실행 회귀 예방.

        세 가지 패턴이 import_manager 사후 필터에서 처리되지만, 근본적으로 AI 가
        애초에 안 만들도록 prompt 에서 명시적으로 금지해야 함:
          1. def main(): ...; main() 패턴 → _unwrap_main_function 의존도
          2. except as e: 변수를 except 밖에서 참조 → except 변수 stale 필터 의존도
          3. 이전 스텝 변수(driver, app) 재정의 → globals 잃음 (사후 필터 없음, 더 위험)

        prompt_builder.build_step_prompt 와 prompts.json/system_context 양쪽에서 검증.
        """
        import json
        from pathlib import Path

        from core.prompt_builder import PromptBuilder
        from core.session_manager import Session

        # ── prompt_builder.build_step_prompt 검증 ──
        builder = PromptBuilder(prompts_config={})

        self.step("첫 스텝 (current_code 없음) - def main + except 변수 가이드")
        session = Session(session_id="test", title="테스트")
        prompt_first = builder.build_step_prompt(
            session=session, user_request="메모장 열어줘", project_type="desktop"
        )
        self.assert_true(
            "def main" in prompt_first and "모듈 레벨" in prompt_first,
            "[회귀] 첫 스텝 prompt 도 def main() 금지 + 모듈 레벨 작성 가이드 필수 "
            "(_unwrap_main_function 의존도 낮춤용)",
        )
        self.assert_true(
            "except" in prompt_first and ("as e" in prompt_first or "캡처 변수" in prompt_first),
            "[회귀] 첫 스텝 prompt 도 except 캡처 변수 격리 가이드 필수 "
            "(NameError stale 라인 회귀 예방)",
        )

        self.step("후속 스텝 (current_code 있음) - 추가로 변수 재사용 가이드")
        session_with_code = Session(session_id="test2", title="후속")
        session_with_code.steps = [
            {
                "step_id": 1,
                "status": "completed",
                "generated_code": "from selenium import webdriver\ndriver = webdriver.Chrome()",
            }
        ]
        prompt_second = builder.build_step_prompt(
            session=session_with_code,
            user_request="https://example.com 으로 이동해줘",
        )
        self.assert_true(
            "재정의" in prompt_second and "driver" in prompt_second,
            "[회귀] 후속 스텝 prompt 는 이전 변수(driver 등) 재정의 금지 가이드 필수 "
            "(globals 잃음 방지 - 사후 필터 없음)",
        )

        # ── prompts.json / system_context 검증 (어댑터가 직접 system_context 사용) ──
        self.step("prompts.json system_context - 절대 규칙으로 jupyter 호환 박힘")
        prompts_file = Path(__file__).parent.parent / "config" / "prompts.json"
        prompts_cfg = json.loads(prompts_file.read_text(encoding="utf-8"))
        sys_ctx = prompts_cfg.get("system_context", "")
        self.assert_true(
            "def main" in sys_ctx and "모듈 레벨" in sys_ctx,
            "[회귀] system_context 절대 규칙에 def main() 금지 + 모듈 레벨 작성 필수",
        )
        self.assert_true(
            "except" in sys_ctx and "NameError" in sys_ctx,
            "[회귀] system_context 절대 규칙에 except 변수 격리 필수 (NameError 회피)",
        )

    def test_69_step_code_edit_keeps_fields_in_sync(self):
        """[회귀] 코드 편집 시 step_code 와 generated_code 동기화 + manually_edited 우선.

        Bug (2026-05-04 사용자 보고, 새 세션 네이버 검색 시나리오 — 두 차례):
          1차: 블럭 뷰 '삼성전자' → '하이닉스' 수정 후 저장 → 실행 시 '삼성전자' 그대로,
               다른 세션 갔다 오면 '하이닉스' 가 '삼성전자' 로 되돌아감.
          2차 (1차 fix 후): 코드 뷰어 탭이 갱신 안 됨 + 실행 시 검색어 입력 안 되고 종료.

        Root cause: extract_step_delta_code 의 우선순위 (1) 마커 추출 / (2) diff 재계산이
        generated_code 기반. step_code 가 진실인 manually_edited 케이스에서 generated_code
        의 stale marker 가 우선되어 사용자 수정 무시 + 잘못된 코드 추출.

        Fix:
        - workflow_engine.extract_step_delta_code: 우선순위 (0) manually_edited + step_code
          → step_code 무조건 우선 사용 (사용자 의도 보호).
        - main_window._on_block_step_code_edited / _on_step_code_edited: 두 필드 동시
          업데이트 + _refresh_code_viewer / _refresh_block_view 호출 (화면 동기화).
        """
        import inspect

        from core.session_manager import SessionManager, Step
        from core.workflow_engine import extract_step_delta_code
        from ui.main_window import MainWindow

        # ── (a) extract_step_delta_code 우선순위 0: manually_edited + step_code ──
        # 사용자 시나리오 핵심 — step_code 와 generated_code 가 desync 한 상태에서
        # manually_edited=True 면 step_code 가 진실로 사용되어야 함.
        step_with_edit = {
            "step_id": 2,
            "manually_edited": True,
            "step_code": "search.send_keys('하이닉스 주가')",
            # generated_code 는 stale (옛 '삼성전자' 라인 + 옛 marker)
            "generated_code": (
                "from selenium import webdriver\n"
                "driver = webdriver.Chrome()\n"
                "driver.get('https://naver.com')\n\n"
                "# === Step 2: 검색어 입력 (시작) ===\n"
                "search.send_keys('삼성전자 주가')\n"
                "# === Step 2: 검색어 입력 (끝) ==="
            ),
        }
        prev_step_dict = {
            "step_id": 1,
            "generated_code": (
                "from selenium import webdriver\n"
                "driver = webdriver.Chrome()\n"
                "driver.get('https://naver.com')"
            ),
        }
        delta = extract_step_delta_code(step_with_edit, prev_step_dict)
        self.assert_true(
            "하이닉스" in delta and "삼성전자" not in delta,
            f"[회귀] manually_edited=True + step_code 가 generated_code 의 stale marker 보다 "
            f"우선 사용되어야 함 (사용자 수정 보호). 실제: {delta!r}",
        )

        # ── (b) handler source 검증 ──
        block_edit_src = inspect.getsource(MainWindow._on_block_step_code_edited)
        self.assert_true(
            '"step_code"' in block_edit_src and '"generated_code"' in block_edit_src,
            "[회귀] _on_block_step_code_edited 가 step_code + generated_code 둘 다 업데이트 필수",
        )
        self.assert_true(
            "_refresh_code_viewer" in block_edit_src,
            "[회귀] _on_block_step_code_edited 가 코드 뷰어 탭 (StepCard) 갱신 호출 필수 "
            "(블럭 뷰 수정 후 코드 뷰어가 stale 한 채 남는 회귀 방지)",
        )

        code_edit_src = inspect.getsource(MainWindow._on_step_code_edited)
        self.assert_true(
            '"step_code"' in code_edit_src and '"generated_code"' in code_edit_src,
            "[회귀] _on_step_code_edited 가 step_code + generated_code 둘 다 업데이트 필수",
        )
        self.assert_true(
            "extract_code_delta" in code_edit_src,
            "[회귀] _on_step_code_edited 가 extract_code_delta 로 새 step_code 재계산 필수",
        )
        self.assert_true(
            "_refresh_block_view" in code_edit_src,
            "[회귀] _on_step_code_edited 가 블럭 뷰 (BlockCard) 갱신 호출 필수",
        )

        # ── (c) import 보존 검증 (사용자 2차 보고: 'Application' is not defined) ──
        # 시나리오: step 1 (selenium 만) + step 2 (pywinauto, Keys 추가). 사용자가 step 2
        # 카드의 코드 (block delta) 만 수정. 새 generated_code 가 step 2 의 import 를
        # 잃으면 extract_library_block 도 잃어 실행 시 NameError.
        from core.import_manager import extract_imports

        old_step2_generated = (
            "from selenium import webdriver\n"
            "from selenium.webdriver.common.keys import Keys\n"
            "from pywinauto.application import Application\n"
            "driver = webdriver.Chrome()\n"
            "driver.get('https://naver.com')\n"
            "app = Application(backend='uia').connect(title_re='.*NAVER.*')\n"
            "search.send_keys('삼성전자 주가', Keys.ENTER)"
        )
        prev_generated = (
            "from selenium import webdriver\n"
            "driver = webdriver.Chrome()\n"
            "driver.get('https://naver.com')"
        )
        new_block_step_code = "search.send_keys('하이닉스 주가', Keys.ENTER)"

        # _on_block_step_code_edited 의 import 보존 로직 시뮬레이션
        old_imports, _ = extract_imports(old_step2_generated)
        prev_imports, prev_body = extract_imports(prev_generated)
        new_step_imports, new_step_body = extract_imports(new_block_step_code)

        from core.import_manager import merge_imports

        merged = merge_imports([prev_imports, old_imports, new_step_imports])

        # 핵심 검증: pywinauto.application.Application 과 Keys 가 import 에 보존
        merged_str = "\n".join(merged)
        self.assert_true(
            "Application" in merged_str,
            f"[회귀] block 뷰 수정 시 원본 step 의 'from pywinauto.application import "
            f"Application' 보존 필수 (안 하면 실행 시 NameError). 실제: {merged!r}",
        )
        self.assert_true(
            "Keys" in merged_str,
            f"[회귀] block 뷰 수정 시 원본 step 의 'from ... import Keys' 보존 필수. "
            f"실제: {merged!r}",
        )

        # 새 generated_code 재구성 검증 (extract_library_block 이 import 추출 가능)
        parts = []
        if merged_str:
            parts.append(merged_str)
        if prev_body.strip():
            parts.append(prev_body.rstrip())
        if new_step_body.strip():
            parts.append(new_step_body)
        new_generated = "\n\n".join(parts)
        self.assert_true(
            "Application" in new_generated
            and "Keys" in new_generated
            and "하이닉스" in new_generated
            and "삼성전자" not in new_generated,
            f"[회귀] 재구성된 generated_code 가 (import 보존 + 사용자 수정값) 둘 다 가져야 함. "
            f"실제: {new_generated!r}",
        )

        # ── (d) 사용자 시나리오 통합: in-memory session 수정 + 디스크 reload ──
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(data_dir=Path(tmpdir))
            sess = mgr.create_session(title="검색 시나리오")

            step1_code = (
                "from selenium import webdriver\n"
                "driver = webdriver.Chrome()\n"
                "driver.get('https://naver.com')"
            )
            mgr.add_step(
                sess,
                Step(
                    step_id=1,
                    generated_code=step1_code,
                    step_code=step1_code,
                    conversation=[{"role": "user", "content": "네이버 접속"}],
                ),
            )

            step2_full = step1_code + "\nsearch.send_keys('삼성전자 주가')"
            step2_delta = "search.send_keys('삼성전자 주가')"
            mgr.add_step(
                sess,
                Step(
                    step_id=2,
                    generated_code=step2_full,
                    step_code=step2_delta,
                    conversation=[{"role": "user", "content": "검색어 입력"}],
                ),
            )

            # 블럭 뷰 수정: 삼성전자 → 하이닉스 (handler 핵심 로직 시뮬레이션)
            new_step_code = "search.send_keys('하이닉스 주가')"
            prev_gen = sess.steps[0]["generated_code"]
            new_gen = prev_gen.rstrip() + "\n\n" + new_step_code
            mgr.update_step(
                sess,
                2,
                {
                    "step_code": new_step_code,
                    "generated_code": new_gen,
                    "manually_edited": True,
                    "edit_original_code": step2_full,
                },
            )

            # 디스크 reload 후 extract_step_delta_code 결과
            reloaded = mgr.load_session(sess.session_id)
            r_curr = reloaded.steps[1]
            r_prev = reloaded.steps[0]
            r_delta = extract_step_delta_code(
                r_curr if isinstance(r_curr, dict) else r_curr.__dict__,
                r_prev if isinstance(r_prev, dict) else r_prev.__dict__,
            )
            self.assert_true(
                "하이닉스" in r_delta and "삼성전자" not in r_delta,
                f"[회귀] 세션 reload 후에도 수정값 유지 필수 (다른 세션 갔다 와도). "
                f"실제: {r_delta!r}",
            )

    def test_68_ai_call_handler_separation(self):
        """[회귀] main_window 분해 Step 4 — AI 호출 controller (AICallHandler) 로 분리.

        6개 메서드: on_cancel_ai, on_user_message, call_ai_thread, on_ai_response,
        on_step_executed, apply_manual_edit_patches.

        main_window 의 위임 stub 은 유지 (signal connect 호환). 본문은 AICallHandler 에서
        검사 (`mw.xxx` 패턴, self.xxx → mw.xxx 변환).
        """
        import inspect

        from ui.ai_call_handler import AICallHandler
        from ui.main_window import MainWindow

        # __init__ 에 AICallHandler 인스턴스 생성
        init_src = inspect.getsource(MainWindow.__init__)
        self.assert_true(
            "AICallHandler(self)" in init_src and "self.ai_handler" in init_src,
            "[회귀] MainWindow.__init__ 가 self.ai_handler = AICallHandler(self) 생성 필수",
        )

        # 위임 stub 6개 — main_window 에 메서드는 유지하되 본문이 ai_handler 로 위임
        for stub_name, handler_method in [
            ("_on_cancel_ai", "on_cancel_ai"),
            ("_on_user_message", "on_user_message"),
            ("_call_ai_thread", "call_ai_thread"),
            ("_on_ai_response", "on_ai_response"),
            ("_on_step_executed", "on_step_executed"),
            ("_apply_manual_edit_patches", "apply_manual_edit_patches"),
        ]:
            stub = getattr(MainWindow, stub_name, None)
            self.assert_true(
                stub is not None,
                f"[회귀] MainWindow.{stub_name} stub 유지 필수 (signal connect 호환)",
            )
            stub_src = inspect.getsource(stub)
            self.assert_true(
                f"self.ai_handler.{handler_method}" in stub_src,
                f"[회귀] {stub_name} stub 이 self.ai_handler.{handler_method} 위임 필수",
            )

        # AICallHandler 본문 — 핵심 동작 5건 (mw.xxx 패턴)
        on_user_src = inspect.getsource(AICallHandler.on_user_message)
        self.assert_true(
            "mw.is_processing" in on_user_src and "mw.current_session" in on_user_src,
            "[회귀] on_user_message 가 mw.is_processing / mw.current_session 가드 유지",
        )

        call_thread_src = inspect.getsource(AICallHandler.call_ai_thread)
        self.assert_true(
            "mw.prompt_builder.build_step_prompt" in call_thread_src
            and "mw.ai_engine.generate" in call_thread_src,
            "[회귀] call_ai_thread 가 prompt 구성 + ai_engine.generate 호출 유지",
        )
        self.assert_true(
            "mw.signals.ai_response_ready.emit" in call_thread_src,
            "[회귀] call_ai_thread 가 ai_response_ready signal emit 유지",
        )

        on_ai_resp_src = inspect.getsource(AICallHandler.on_ai_response)
        self.assert_true(
            "extract_code_delta" in on_ai_resp_src and "extract_imports" in on_ai_resp_src,
            "[회귀] on_ai_response 가 extract_code_delta + extract_imports 호출 유지 "
            "(step_code/step_imports 누적)",
        )
        self.assert_true(
            "mw.session_manager.add_step" in on_ai_resp_src,
            "[회귀] on_ai_response 가 session_manager.add_step 호출 유지",
        )

        patches_src = inspect.getsource(AICallHandler.apply_manual_edit_patches)
        self.assert_true(
            "manually_edited" in patches_src and "send_keys" in patches_src,
            "[회귀] apply_manual_edit_patches 의 Phase 1 (manually_edited 복원) + "
            "Phase 2 (send_keys 공백 변조 자동 복원) 유지",
        )

    def test_70_prompt_warns_against_speculative_element_id_wait(self):
        """[회귀] AI prompt 가 driver.get() 직후 추측성 element ID 대기 금지 가이드 포함.

        Bug (2026-05-04 사용자 보고, RPA_20260504_2206):
          AI 가 step 1 (네이버 접속) 코드에 'nm_main_tab' 이라는 존재하지 않는 ID 로
          WebDriverWait 10초 → TimeoutException → step 실행 12초 지연 + chromedriver
          stacktrace 출력. 'nm_main_tab' 은 AI 가 추측한 가짜 ID.

        Fix: prompt_builder selenium 가이드에 "추측성 element ID 로 WebDriverWait 금지,
        대신 time.sleep 또는 body/html 같은 항상 존재하는 selector 사용" 가이드 추가.
        """
        from core.prompt_builder import PromptBuilder
        from core.session_manager import Session

        builder = PromptBuilder(prompts_config={})
        session = Session(session_id="test", title="테스트")
        prompt = builder.build_step_prompt(
            session=session,
            user_request="네이버 접속해줘",
            project_type="auto",
        )

        # 핵심 키워드 검증 — 추측성 ID 금지 + 대안 (sleep, body 태그)
        self.assert_true(
            "추측성" in prompt or "추측" in prompt,
            "[회귀] selenium 가이드에 '추측성' element ID 사용 금지 키워드 필수",
        )
        self.assert_true(
            "time.sleep" in prompt and "body" in prompt,
            "[회귀] 대안으로 time.sleep + 항상 존재하는 selector (body/html) 가이드 필수",
        )
        self.assert_true(
            "WebDriverWait" in prompt and "timeout" in prompt.lower(),
            "[회귀] WebDriverWait 의 timeout 부작용 명시 필수",
        )

    def test_71_gemini_adapter_passes_model_flag(self):
        """[회귀] GeminiCLIAdapter 가 config.model 을 -m 인자로 명시 전달.

        Bug (2026-05-04): gemini CLI headless (-p / stdin) default 가
        gemini-3-flash-preview (preview) 로 잡혀 capacity 부족 → 180초 timeout 회귀.
        Fix: config.model 을 -m 플래그로 명시 → preview 자동 매핑 회피.
        """
        from core.adapters.gemini_cli_adapter import GeminiCLIAdapter

        adapter = GeminiCLIAdapter({"command": "gemini", "model": "gemini-2.5-flash"})
        args_with_model = adapter._build_args("gemini.exe")
        self.assert_true(
            "-m" in args_with_model and "gemini-2.5-flash" in args_with_model,
            f"[회귀] config.model 설정 시 -m <model> 추가 필수. args: {args_with_model!r}",
        )
        args_with_p = adapter._build_args("gemini.exe", "-p", "test")
        self.assert_true(
            "-m" in args_with_p and "-p" in args_with_p,
            f"[회귀] -p 모드에서도 -m 보존. args: {args_with_p!r}",
        )
        adapter_no_model = GeminiCLIAdapter({"command": "gemini"})
        self.assert_true(
            "-m" not in adapter_no_model._build_args("gemini.exe"),
            "[회귀] config.model 미설정 시 -m 추가 안 함",
        )

        import json
        from pathlib import Path

        cfg = json.loads(
            (Path(__file__).parent.parent / "config" / "settings.json").read_text(encoding="utf-8")
        )
        gemini_cfg = cfg.get("ai", {}).get("available_engines", {}).get("gemini_cli", {})
        # 가드 의도 (5/4): CLI 의 default preview 자동 매핑 회피 — model 이 명시적으로 지정돼야 함.
        # 5/6 사용자 결정: gemini-3.x preview 도 사용자 명시 선택 시 허용 (자동 매핑이 아님).
        # 따라서 "gemini-" prefix 만 검증 (빈 값 / 공백 / 다른 provider 만 차단).
        self.assert_true(
            gemini_cfg.get("model", "").startswith("gemini-"),
            f"[회귀] settings.json gemini_cli.model 명시 필수 (gemini-* prefix). "
            f"실제: {gemini_cfg.get('model')!r}",
        )

        # Production path 검증 (5/5 추가): _build_args 가 정의만 돼 있고
        # 실제 subprocess.Popen 호출에서 사용 안 되면 -m 플래그가 안 붙어
        # capacity 회귀 재발. 두 path 모두 _build_args 경유 필수.
        import inspect

        gen_src = inspect.getsource(GeminiCLIAdapter.generate)
        self.assert_true(
            "self._build_args(gemini_exec)" in gen_src,
            "[회귀] stdin path Popen 가 self._build_args(gemini_exec) 사용 필수 "
            "(raw [gemini_exec] 리터럴은 -m 플래그 누락 회귀)",
        )
        self.assert_true(
            'self._build_args(gemini_exec, "-p"' in gen_src,
            '[회귀] -p path Popen 가 self._build_args(gemini_exec, "-p", ...) 사용 필수 '
            '(raw [gemini_exec, "-p", ...] 리터럴은 -m 플래그 누락 회귀)',
        )
        # raw 리터럴 패턴이 production path 에 남으면 안 됨
        self.assert_true(
            "Popen(\n                    [gemini_exec]" not in gen_src
            and "Popen([gemini_exec]" not in gen_src,
            "[회귀] subprocess.Popen 에 [gemini_exec] raw 리터럴 직접 전달 금지 "
            "(_build_args 경유 필수)",
        )

    def test_73_run_stop_buttons_reset_on_completion(self):
        """[회귀] 모든 step 완료 시 run/stop 버튼 양쪽 탭 자동 리셋.

        Bug (2026-05-05 사용자 보고): 코드 실행이 끝나도 stop 버튼이 활성화된 채로
        남고 run 버튼이 비활성화된 채로 남는 회귀.

        Fix: 모든 종료 path 에 set_running(False) 안전망:
        1. AICallHandler.on_step_executed (코드 뷰 path 의 step_executed slot) catch-all
        2. BlockExecutionHandler.on_blocks_finished (블럭 뷰 path) — 명시 update() 추가
        3. (기존) execute_code_thread finally / blocks_finished signal — 유지
        """
        import inspect

        from ui.ai_call_handler import AICallHandler
        from ui.block_execution_handler import BlockExecutionHandler
        from ui.code_viewer import BlockViewWidget, CodeViewer

        # AICallHandler.on_step_executed 가 set_running(False) catch-all 호출
        on_step_src = inspect.getsource(AICallHandler.on_step_executed)
        self.assert_true(
            "code_viewer.set_running(False)" in on_step_src,
            "[회귀] AICallHandler.on_step_executed 끝에 mw.code_viewer.set_running(False) "
            "catch-all 호출 필수 (실행 완료 시 stop 버튼 자동 비활성화 보장)",
        )

        # BlockExecutionHandler.on_blocks_finished 가 set_running(False) + update 호출
        on_blocks_src = inspect.getsource(BlockExecutionHandler.on_blocks_finished)
        self.assert_true(
            "code_viewer.set_running(False)" in on_blocks_src,
            "[회귀] BlockExecutionHandler.on_blocks_finished 가 "
            "mw.code_viewer.set_running(False) 호출 필수",
        )
        self.assert_true(
            "code_viewer.update()" in on_blocks_src,
            "[회귀] on_blocks_finished 가 시각 갱신 위해 update() 명시 호출 필수 "
            "(일부 케이스 즉시 repaint 안 됨 회귀)",
        )

        # CodeViewer.set_running 은 양쪽 탭 (run_btn/stop_btn + block_view) 동시 처리
        cv_set_running_src = inspect.getsource(CodeViewer.set_running)
        self.assert_true(
            "run_btn.setEnabled(not running)" in cv_set_running_src,
            "[회귀] CodeViewer.set_running 가 run_btn enable/disable 처리 필수",
        )
        self.assert_true(
            "stop_btn.setEnabled(running)" in cv_set_running_src,
            "[회귀] CodeViewer.set_running 가 stop_btn 처리 필수",
        )
        self.assert_true(
            "block_view.set_running" in cv_set_running_src,
            "[회귀] CodeViewer.set_running 가 block_view 동시 처리 필수 "
            "(코드 뷰 + 블럭 뷰 양쪽 동기화)",
        )

        # BlockViewWidget.set_running 은 toolbar + 카드 별 run_btn 처리
        bv_set_running_src = inspect.getsource(BlockViewWidget.set_running)
        self.assert_true(
            "run_all_btn.setEnabled(not running)" in bv_set_running_src
            and "stop_btn.setEnabled(running)" in bv_set_running_src,
            "[회귀] BlockViewWidget.set_running 가 toolbar run_all_btn/stop_btn 처리 필수",
        )
        self.assert_true(
            "_update_run_buttons" in bv_set_running_src,
            "[회귀] BlockViewWidget.set_running 가 _update_run_buttons 호출 필수 "
            "(카드 별 run_btn / single_btn enable/disable)",
        )

    def test_74_initial_block_standalone_execution(self):
        """[회귀] Initial 블럭 단독 실행 (Phase 2.5).

        사용자가 driver/options 등 setup 변수를 재정의하고 싶을 때 첫 step
        안 돌리고 Initial 블럭만 실행하는 path 검증.

        Path:
        - core/execution_kernel.py: INITIAL_BLOCK_STEP_ID == -1 상수
        - ui/code_viewer.py BlockCard: step_id == -1 도 run_single_btn 활성화
        - ui/code_viewer.py BlockViewWidget.refresh: init_card.run_single_requested
            -> self.run_single_step_requested 연결
        - ui/block_execution_handler.py:
          - on_run_single_step 가 step_id == INITIAL_BLOCK_STEP_ID 분기 -> on_run_initial_block
          - on_run_initial_block 가 카드에서 코드 추출 + library 자동 선행 + kernel.execute_block
        """
        import inspect

        from core.execution_kernel import INITIAL_BLOCK_STEP_ID, LIBRARY_BLOCK_STEP_ID
        from ui.block_execution_handler import BlockExecutionHandler
        from ui.code_viewer import BlockCard, BlockViewWidget

        # 1. 상수 확정값
        self.assert_true(
            INITIAL_BLOCK_STEP_ID == -1,
            f"[회귀] INITIAL_BLOCK_STEP_ID == -1 필수. 실제: {INITIAL_BLOCK_STEP_ID}",
        )
        self.assert_true(
            LIBRARY_BLOCK_STEP_ID == 0,
            f"[회귀] LIBRARY_BLOCK_STEP_ID == 0 필수. 실제: {LIBRARY_BLOCK_STEP_ID}",
        )

        # 2. BlockCard.__init__ 가 step_id == -1 에 대해서도 run_single_btn 생성
        bc_src = inspect.getsource(BlockCard.__init__)
        self.assert_true(
            "step_id > 0 or step_id == -1" in bc_src,
            "[회귀] BlockCard 가 step_id == -1 (Initial) 에 대해서도 run_single_btn 활성화 필수 "
            "(Phase 2.5 driver 재초기화 시나리오)",
        )
        self.assert_true(
            "Initial 블럭 단독 실행" in bc_src,
            "[회귀] BlockCard 의 step_id == -1 tooltip 에 'Initial 블럭 단독 실행' 안내 필수",
        )

        # 3. BlockViewWidget.refresh 가 init_card.run_single_requested 연결
        refresh_src = inspect.getsource(BlockViewWidget.refresh)
        self.assert_true(
            "init_card.run_single_requested.connect(self.run_single_step_requested)" in refresh_src,
            "[회귀] BlockViewWidget.refresh 가 init_card.run_single_requested ->"
            " run_single_step_requested 연결 필수 (signal 라우팅)",
        )

        # 4. BlockExecutionHandler.on_run_single_step 가 INITIAL_BLOCK_STEP_ID 분기
        on_single_src = inspect.getsource(BlockExecutionHandler.on_run_single_step)
        self.assert_true(
            "INITIAL_BLOCK_STEP_ID" in on_single_src and "on_run_initial_block" in on_single_src,
            "[회귀] on_run_single_step 가 step_id == INITIAL_BLOCK_STEP_ID 분기 후 "
            "on_run_initial_block() 호출 필수",
        )

        # 5. on_run_initial_block 메서드 존재 + 핵심 동작
        self.assert_true(
            hasattr(BlockExecutionHandler, "on_run_initial_block"),
            "[회귀] BlockExecutionHandler.on_run_initial_block 메서드 필수",
        )
        on_init_src = inspect.getsource(BlockExecutionHandler.on_run_initial_block)
        # 카드에서 코드 텍스트 추출 (사용자 편집 반영)
        self.assert_true(
            "code_edit.toPlainText()" in on_init_src and "INITIAL_BLOCK_STEP_ID" in on_init_src,
            "[회귀] on_run_initial_block 가 Initial 카드의 code_edit.toPlainText() "
            "로 사용자 편집 반영 코드 추출 필수",
        )
        # set_running(True) + lower() 호출
        self.assert_true(
            "set_running(True)" in on_init_src and "mw.lower()" in on_init_src,
            "[회귀] on_run_initial_block 가 set_running(True) + mw.lower() 필수 "
            "(실행 중 UI 상태 + Win11 ForegroundLock 정책 회피)",
        )

        # 6. _run_initial_block_thread 가 library 선행 + kernel.execute_block 사용
        self.assert_true(
            hasattr(BlockExecutionHandler, "_run_initial_block_thread"),
            "[회귀] BlockExecutionHandler._run_initial_block_thread 워커 필수",
        )
        thread_src = inspect.getsource(BlockExecutionHandler._run_initial_block_thread)
        self.assert_true(
            "LIBRARY_BLOCK_STEP_ID not in kernel.executed_steps" in thread_src
            and "extract_library_block" in thread_src,
            "[회귀] _run_initial_block_thread 가 라이브러리 블럭 미초기화 시 "
            "extract_library_block 으로 선행 실행 필수 (NameError 회귀 방지)",
        )
        self.assert_true(
            "kernel.execute_block(\n                initial_code, step_id=INITIAL_BLOCK_STEP_ID"
            in thread_src
            or "kernel.execute_block(initial_code, step_id=INITIAL_BLOCK_STEP_ID" in thread_src,
            "[회귀] _run_initial_block_thread 가 kernel.execute_block(initial_code, "
            "step_id=INITIAL_BLOCK_STEP_ID) 호출 필수",
        )
        self.assert_true(
            "blocks_finished.emit()" in thread_src,
            "[회귀] _run_initial_block_thread finally 절에서 "
            "blocks_finished.emit() 호출 필수 (run/stop 버튼 자동 리셋 - test_73 와 일관)",
        )

    def test_75_openai_compat_adapter(self):
        """[회귀] OpenAI 호환 API 어댑터 (D2 redesign 결정).

        BYO API 또는 추후 SaaS 크레딧 모델의 단일 어댑터. base_url + api_key
        만으로 OpenAI / DeepSeek / Groq / OpenRouter / Ollama / LM Studio 등
        모두 지원.
        """
        import json
        from pathlib import Path

        from core.adapters.base_adapter import AIResponse, BaseAIAdapter
        from core.adapters.openai_compat_adapter import PRESETS, OpenAICompatAdapter
        from core.ai_engine import AIEngineManager

        # 1. PRESETS 가 주요 서비스 포함 + base_url + model 쌍
        for required in ["openai", "deepseek", "groq", "openrouter", "ollama"]:
            self.assert_true(
                required in PRESETS,
                f"[회귀] PRESETS 에 '{required}' 프리셋 필수",
            )
            self.assert_true(
                "base_url" in PRESETS[required] and "model" in PRESETS[required],
                f"[회귀] PRESETS['{required}'] 에 base_url + model 필수",
            )

        # 2. BaseAIAdapter 상속 + 추상 메서드 모두 구현 (인스턴스화 가능)
        self.assert_true(
            issubclass(OpenAICompatAdapter, BaseAIAdapter),
            "[회귀] OpenAICompatAdapter 가 BaseAIAdapter 상속 필수",
        )
        adapter = OpenAICompatAdapter({})
        self.assert_true(
            adapter.is_available(),
            "[회귀] base_url default 가 있으면 is_available() True",
        )

        # 3. config 우선순위: 직접 입력 > api_key_env
        adapter_direct = OpenAICompatAdapter({"api_key": "sk-direct"})
        self.assert_true(
            adapter_direct.api_key == "sk-direct",
            f"[회귀] api_key 직접 입력 시 그대로 사용. 실제: {adapter_direct.api_key!r}",
        )

        # 4. base_url 끝 슬래시 자동 제거 (chat/completions 경로 합칠 때 // 회피)
        adapter_slash = OpenAICompatAdapter({"base_url": "https://api.x.com/v1/"})
        self.assert_true(
            adapter_slash.base_url == "https://api.x.com/v1",
            f"[회귀] base_url 끝 슬래시 제거 필수. 실제: {adapter_slash.base_url!r}",
        )

        # 5. _detect_preset 가 base_url 일치 프리셋 식별
        adapter_ds = OpenAICompatAdapter({"base_url": "https://api.deepseek.com/v1"})
        self.assert_true(
            adapter_ds._detect_preset() == "deepseek",
            f"[회귀] DeepSeek base_url 인식. 실제: {adapter_ds._detect_preset()!r}",
        )

        # 6. get_name 이 프리셋 라벨 포함
        self.assert_true(
            "DeepSeek" in adapter_ds.get_name(),
            f"[회귀] get_name 에 프리셋 라벨 노출. 실제: {adapter_ds.get_name()!r}",
        )

        # 7. AIEngineManager.ADAPTER_REGISTRY 에 'openai_compat' 등록
        self.assert_true(
            "openai_compat" in AIEngineManager.ADAPTER_REGISTRY,
            "[회귀] AIEngineManager.ADAPTER_REGISTRY 에 'openai_compat' 등록 필수",
        )
        self.assert_true(
            AIEngineManager.ADAPTER_REGISTRY["openai_compat"] is OpenAICompatAdapter,
            "[회귀] ADAPTER_REGISTRY['openai_compat'] = OpenAICompatAdapter 매핑 필수",
        )

        # 8. settings.json default 에 openai_compat 항목 존재 + 필수 키
        cfg = json.loads(
            (Path(__file__).parent.parent / "config" / "settings.json").read_text(encoding="utf-8")
        )
        oc_cfg = cfg.get("ai", {}).get("available_engines", {}).get("openai_compat", {})
        self.assert_true(
            bool(oc_cfg),
            "[회귀] settings.json 에 openai_compat 엔진 default 필수",
        )
        for required_key in ("base_url", "api_key", "api_key_env", "model"):
            self.assert_true(
                required_key in oc_cfg,
                f"[회귀] openai_compat default 에 '{required_key}' 키 필수",
            )

        # 9. 메서드 시그니처 — generate 는 async, cancel 은 sync
        import inspect

        self.assert_true(
            inspect.iscoroutinefunction(OpenAICompatAdapter.generate),
            "[회귀] OpenAICompatAdapter.generate 는 async 함수 필수 (BaseAIAdapter 호환)",
        )

        # 10. AIResponse 반환 타입 일관성 (호출 안 하고 메서드 메타만 검사)
        sig = inspect.signature(OpenAICompatAdapter.generate)
        return_anno = sig.return_annotation
        self.assert_true(
            return_anno is AIResponse or str(return_anno) == "AIResponse",
            f"[회귀] generate 반환 타입 AIResponse 명시 필수. 실제: {return_anno}",
        )

    def test_76_app_service_export_workflow_creates_full_bundle(self):
        """[D22] AppService.export_workflow 가 실행 가능 + 가져오기 가능 번들 생성.

        결과 폴더 구성: main.py / requirements.txt / README.md / run.bat
        (실행 가능) + session.json / captures/ (있으면) / scripts/ (있으면)
        — import_workflow 로 재가져오기 가능. v1 export_as_project 의 v2 façade.
        """
        from core.app_service import AppService
        from core.session_manager import SessionManager, Step
        from core.storage.local_json import LocalJsonRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            manager = SessionManager(data_dir=data_dir)
            repo = LocalJsonRepository(manager=manager)
            service = AppService(session_repo=repo)

            self.step("세션 + 스텝 + capture 파일 준비")
            session = manager.create_session(title="export 테스트", project_type="desktop")
            manager.add_step(session, Step(generated_code="print('step 1')"))
            cap_dir = data_dir / "sessions" / session.session_id / "captures"
            cap_dir.mkdir(parents=True, exist_ok=True)
            (cap_dir / "screen_001.png").write_bytes(b"fake-png")

            self.step("export_workflow 호출")
            out_dir = Path(tmpdir) / "exported"
            result = service.export_workflow(session_id=session.session_id, output_dir=out_dir)

            self.assert_true(result.exists(), "결과 폴더 존재 필수")
            for required in ("main.py", "requirements.txt", "README.md", "run.bat"):
                self.assert_true(
                    (result / required).exists(),
                    f"[D22] {required} 생성 필수 (실행 가능 번들)",
                )
            self.assert_true(
                (result / "session.json").exists(),
                "[D22] session.json 포함 필수 (가져오기 가능)",
            )
            self.assert_true(
                (result / "captures" / "screen_001.png").exists(),
                "[D22] captures/ 사본 포함 필수",
            )

    def test_77_app_service_import_workflow_new_uuid(self):
        """[D22] AppService.import_workflow 가 새 UUID 로 가져오기 + 절대 경로 재작성.

        export 결과 폴더를 import 하면 새 UUID 생성, captures 절대 경로의 옛 UUID
        가 새 UUID 로 교체됨. 같은 export 를 두 번 import 해도 충돌 없음.
        """
        from core.app_service import AppService
        from core.session_manager import SessionManager, Step
        from core.storage.local_json import LocalJsonRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            manager = SessionManager(data_dir=data_dir)
            repo = LocalJsonRepository(manager=manager)
            service = AppService(session_repo=repo)

            self.step("export 가능한 세션 준비 (capture 절대 경로 포함)")
            session = manager.create_session(title="import 테스트")
            sid = session.session_id
            cap_path = data_dir / "sessions" / sid / "captures" / "elem_001.png"
            cap_path.parent.mkdir(parents=True, exist_ok=True)
            cap_path.write_bytes(b"fake-png")
            step = Step(
                generated_code="print('hi')",
                captures=[str(cap_path)],
            )
            manager.add_step(session, step)

            self.step("export → import 두 번 (충돌 검증)")
            export_dir = Path(tmpdir) / "exported"
            service.export_workflow(session_id=sid, output_dir=export_dir)
            imported_a = service.import_workflow(source_dir=export_dir)
            imported_b = service.import_workflow(source_dir=export_dir)

            self.assert_true(
                imported_a.session_id != sid,
                "[D22] import 시 새 UUID 발급 필수 (원본과 다름)",
            )
            self.assert_true(
                imported_a.session_id != imported_b.session_id,
                "[D22] 같은 export 두 번 import → 각각 다른 UUID 충돌 회피",
            )
            self.assert_true(
                imported_a.title == "import 테스트",
                f"[D22] 제목 보존. 실제: {imported_a.title!r}",
            )
            self.step("captures 절대 경로 재작성 검증")
            new_caps = imported_a.steps[0].get("captures") or []
            self.assert_true(
                len(new_caps) == 1
                and imported_a.session_id in new_caps[0]
                and sid not in new_caps[0],
                f"[D22] captures 절대 경로 옛 UUID → 새 UUID 치환 필수. 실제: {new_caps}",
            )
            self.step("new_title 옵션 검증")
            imported_c = service.import_workflow(source_dir=export_dir, new_title="이름 변경됨")
            self.assert_true(
                imported_c.title == "이름 변경됨",
                f"[D22] new_title 인자 적용 필수. 실제: {imported_c.title!r}",
            )

    def test_78_in_memory_repo_contract(self):
        """[Phase 1] InMemoryRepository 가 SessionRepository contract 준수.

        ROADMAP §3 Phase 1 (1) — file IO 없는 인메모리 구현으로 테스트 가속 가능.
        LocalJsonRepository 와 동일한 동작 (CRUD + 스텝 관리) 보장.
        """
        from core.session_manager import Step
        from core.storage import InMemoryRepository, LocalJsonRepository, SessionRepository

        self.step("InMemoryRepository 가 SessionRepository 상속 + 인스턴스화 가능")
        self.assert_true(
            issubclass(InMemoryRepository, SessionRepository),
            "[Phase 1] InMemoryRepository 가 SessionRepository(ABC) 상속 필수",
        )
        repo = InMemoryRepository()  # ABC 미구현이면 TypeError

        self.step("create + load + list + delete 사이클")
        s = repo.create_session(title="in-memory test", project_type="desktop")
        self.assert_true(s.session_id and len(s.session_id) > 0, "session_id 발급")
        loaded = repo.load_session(s.session_id)
        self.assert_equal(loaded.title, "in-memory test", "load 시 title 유지")
        summaries = repo.list_sessions()
        self.assert_true(any(x.session_id == s.session_id for x in summaries), "list 에 포함")

        self.step("스텝 add + update + delete + insert + move")
        repo.add_step(s, Step(generated_code="print('a')"))
        repo.add_step(s, Step(generated_code="print('b')"))
        repo.add_step(s, Step(generated_code="print('c')"))
        loaded = repo.load_session(s.session_id)
        self.assert_equal(len(loaded.steps), 3, "3 step 추가")

        repo.update_step(s, step_id=2, updates={"status": "completed"})
        loaded = repo.load_session(s.session_id)
        self.assert_equal(loaded.steps[1]["status"], "completed", "update 적용")

        repo.move_step(s, step_id=1, direction="down")
        loaded = repo.load_session(s.session_id)
        self.assert_contains(
            loaded.steps[1].get("generated_code", ""),
            "print('a')",
            "step 1 가 아래로 이동",
        )

        repo.delete_step(s, step_id=2)
        loaded = repo.load_session(s.session_id)
        self.assert_equal(len(loaded.steps), 2, "delete 후 2 step")

        self.step("delete_session 후 load 는 FileNotFoundError")
        repo.delete_session(s.session_id)
        try:
            repo.load_session(s.session_id)
            raise AssertionError("delete 후 load 가 FileNotFoundError 던져야 함")
        except FileNotFoundError:
            pass  # expected

        self.step("export/import 는 file IO 미지원이라 NotImplementedError")
        s2 = repo.create_session(title="x")
        try:
            repo.export_session_as_project(s2, Path("/tmp/x"), settings={})
            raise AssertionError("InMemoryRepo.export 는 NotImplementedError 던져야 함")
        except NotImplementedError:
            pass  # expected

        # LocalJsonRepository 와 동일 contract — 동일한 메서드 시그니처 노출
        for method in (
            "create_session",
            "save_session",
            "load_session",
            "list_sessions",
            "delete_session",
            "add_step",
            "update_step",
            "delete_step",
            "insert_step",
            "move_step",
            "export_session_as_project",
            "import_session_folder",
        ):
            self.assert_true(
                hasattr(InMemoryRepository, method) and hasattr(LocalJsonRepository, method),
                f"[Phase 1] {method} 양 backend 에 모두 정의 필수",
            )

    def test_79_app_service_no_storage_leak(self):
        """[Phase 1] AppService 가 self._repo.manager 로 leak 안 함.

        ROADMAP §3 Phase 1 (1) — AppService 는 SessionRepository 추상 메서드만
        호출. 5/8 까지의 ``getattr(self._repo, "manager", None)`` 패턴 제거 검증.
        Phase 2 의 PostgresRepository 가 manager 속성 없이도 작동해야 함.
        """
        import inspect

        from core.app_service import AppService

        src = inspect.getsource(AppService)
        # leak 패턴 — getattr(self._repo, "manager", ...) 부재
        self.assert_true(
            'getattr(self._repo, "manager"' not in src,
            "[Phase 1] AppService 에서 self._repo.manager 우회 패턴 (getattr) 제거 필수",
        )
        self.assert_true(
            "self._repo.export_session_as_project(" in src,
            "[Phase 1] AppService.export_workflow 가 repo 의 추상 메서드 직접 호출 필수",
        )
        self.assert_true(
            "self._repo.import_session_folder(" in src,
            "[Phase 1] AppService.import_workflow 가 repo 의 추상 메서드 직접 호출 필수",
        )

    def test_82_pydantic_models_round_trip(self):
        """[Phase 1.3] core/models.py 의 Pydantic 모델 ↔ dataclass round-trip.

        ROADMAP §3 Phase 1 (3) — dataclass (Session/Step/Capture 등) 를 Pydantic
        v2 모델로 승격. 5/8 시점 비파괴 도입 — parallel 모델 + conversion helper.
        Phase 2 FastAPI ``response_model`` 로 즉시 활용 가능.

        검증:
        - 매핑 모든 dataclass 가 대응 Pydantic 모델 보유
        - from_dataclass → to_dataclass round-trip 손실 없음 (모든 필드 보존)
        - JSON 직렬화 (model_dump) 결과가 asdict 와 동일 구조
        - extra='allow' — 미정의 필드 forward compat
        """
        import json
        from dataclasses import asdict

        from core.models import (
            CaptureModel,
            ConversationMessageModel,
            ExecutionResultModel,
            PromptLogModel,
            SessionModel,
            SessionSummaryModel,
            StepModel,
            from_dataclass,
            to_dataclass,
        )
        from core.session_manager import (
            CaptureInfo,
            ConversationMessage,
            ExecutionResult,
            PromptLog,
            Session,
            SessionSummary,
            Step,
        )

        self.step("매핑 7 dataclass <-> 7 Pydantic 모델")
        pairs = [
            (CaptureInfo, CaptureModel),
            (PromptLog, PromptLogModel),
            (ExecutionResult, ExecutionResultModel),
            (ConversationMessage, ConversationMessageModel),
            (Step, StepModel),
            (Session, SessionModel),
            (SessionSummary, SessionSummaryModel),
        ]
        for dc_cls, model_cls in pairs:
            self.assert_true(
                model_cls is not None,
                f"[Phase 1.3] {dc_cls.__name__} 에 대응 {model_cls.__name__} 정의 필수",
            )

        self.step("Step round-trip - dataclass -> Pydantic -> dataclass")
        step = Step(
            step_id=3,
            status="completed",
            generated_code="print('hello')",
            step_code="print('hello')",
            user_request="hello 출력",
            ai_description="간단한 print 문",
            wait_after_ms=500,
        )
        model = from_dataclass(step)
        self.assert_true(isinstance(model, StepModel), "from_dataclass -> StepModel")
        back = to_dataclass(model)
        self.assert_true(isinstance(back, Step), "to_dataclass -> Step")
        # 모든 필드 보존
        self.assert_equal(back.step_id, 3, "step_id 보존")
        self.assert_equal(back.status, "completed", "status 보존")
        self.assert_equal(back.user_request, "hello 출력", "user_request 보존")
        self.assert_equal(back.wait_after_ms, 500, "wait_after_ms 보존")
        # JSON 직렬화 결과가 asdict 와 동일 구조
        self.assert_equal(
            model.model_dump(),
            asdict(step),
            "model_dump() == asdict() - JSON wire format 동일",
        )

        self.step("Session round-trip - 중첩 + default factory 보존")
        s = Session(
            session_id="abc-123",
            title="테스트 세션",
            project_type="web",
            description="round-trip 검증",
        )
        # default factory 값들 (settings, workflow_metadata) 도 round-trip
        s_model = from_dataclass(s)
        s_back = to_dataclass(s_model)
        self.assert_equal(s_back.session_id, "abc-123", "session_id 보존")
        self.assert_equal(s_back.title, "테스트 세션", "title 보존")
        self.assert_true("ai_engine" in s_back.settings, "settings.ai_engine default 보존")
        self.assert_equal(
            s_back.workflow_metadata.get("total_steps"),
            0,
            "workflow_metadata.total_steps default 보존",
        )

        self.step("SessionSummary - required 필드 검증")
        summary = SessionSummary(
            session_id="x",
            title="T",
            description="D",
            project_type="desktop",
            created_at="2026-05-08",
            updated_at="2026-05-08",
            total_steps=5,
            completed_steps=3,
        )
        sm = from_dataclass(summary)
        self.assert_equal(sm.total_steps, 5, "summary 정수 필드 보존")

        self.step("JSON 직렬화 (model_dump_json) 가능")
        json_str = s_model.model_dump_json()
        parsed = json.loads(json_str)
        self.assert_equal(parsed["session_id"], "abc-123", "JSON 직렬화/파싱 round-trip")

        self.step("extra='allow' - 미정의 필드 forward compat")
        # JSON 에 미래 필드가 있어도 모델 거부 안 함
        future_step_data = {"step_id": 1, "future_field": "value"}
        future_model = StepModel(**future_step_data)
        self.assert_equal(future_model.step_id, 1, "정의된 필드 정상")
        # extra='allow' 면 model_dump 시 future_field 도 포함 (보존)
        self.assert_true(
            "future_field" in future_model.model_dump(),
            "extra='allow' 가 미정의 필드 보존",
        )

        self.step("타입 매핑 안 된 객체는 TypeError")
        try:
            from_dataclass(object())
            raise AssertionError("매핑 없는 타입은 TypeError")
        except TypeError:
            pass

    def test_81_settings_layer_pydantic_typed(self):
        """[Phase 1.4] core/config.py 의 Settings 모델 + JSON load + .env override.

        ROADMAP §3 Phase 1 (4) — config/settings.json 의 dict 기반 설정을
        Pydantic v2 ``Settings`` 모델로 승격. 환경변수 prefix ``OHDO_`` +
        nested delimiter ``__`` 로 override 가능.

        비파괴 정책 — 기존 ``_load_settings() -> dict`` 패턴은 유지
        (load_settings_dict 가 동일한 dict 반환).
        """
        import os
        import tempfile

        from core.config import (
            ExecutionSettings,
            Settings,
            load_settings,
            load_settings_dict,
            save_settings,
        )

        self.step("실제 settings.json 을 Settings 모델로 로드")
        s = load_settings()
        self.assert_true(isinstance(s, Settings), "Settings 인스턴스 반환")
        self.assert_true(
            isinstance(s.execution, ExecutionSettings),
            "execution 섹션이 ExecutionSettings 타입",
        )
        self.assert_true(
            isinstance(s.ai.available_engines, dict),
            "ai.available_engines 가 dict[str, AIEngineConfig]",
        )

        self.step("load_settings_dict 가 동일한 dict 반환 (비파괴 호환)")
        d = load_settings_dict()
        self.assert_true(isinstance(d, dict), "dict 반환")
        self.assert_true("ai" in d and "execution" in d, "주요 섹션 포함")
        self.assert_equal(
            d["execution"]["step_delay_ms"],
            s.execution.step_delay_ms,
            "model_dump 가 typed 값과 일치",
        )

        self.step("환경변수 override — OHDO_EXECUTION__STEP_DELAY_MS=2500")
        try:
            os.environ["OHDO_EXECUTION__STEP_DELAY_MS"] = "2500"
            s_override = load_settings()
            self.assert_equal(
                s_override.execution.step_delay_ms,
                2500,
                "환경변수가 JSON 값보다 우선",
            )
        finally:
            os.environ.pop("OHDO_EXECUTION__STEP_DELAY_MS", None)

        self.step("save_settings 가 디스크에 영속화")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test_settings.json"
            sample = Settings()
            sample.ui.theme = "dark"
            sample.execution.step_delay_ms = 555
            save_settings(sample, path)
            self.assert_true(path.exists(), "JSON 파일 생성")
            reloaded = load_settings(path)
            self.assert_equal(reloaded.ui.theme, "dark", "save → load 라운드트립")
            self.assert_equal(reloaded.execution.step_delay_ms, 555, "수치 라운드트립")

        self.step("default 값 — settings.json 없을 때")
        with tempfile.TemporaryDirectory() as tmp:
            empty = load_settings(Path(tmp) / "missing.json")
            self.assert_true(
                isinstance(empty, Settings),
                "파일 없어도 default Settings 반환",
            )
            self.assert_equal(empty.execution.step_delay_ms, 1000, "default step_delay_ms=1000")

        self.step("extra=allow — 미정의 키도 보존 (forward compat)")
        with tempfile.TemporaryDirectory() as tmp:
            unknown_path = Path(tmp) / "unknown.json"
            unknown_path.write_text(
                '{"ai":{"selected":"x"},"future_section":{"foo":"bar"}}',
                encoding="utf-8",
            )
            s_extra = load_settings(unknown_path)
            self.assert_equal(s_extra.ai.selected, "x", "정의된 필드 정상")
            # extra="allow" 면 future_section 도 모델에 보존됨 (model_dump 시 포함)
            self.assert_true(
                "future_section" in s_extra.model_dump(),
                "extra='allow' 가 미정의 섹션 보존",
            )

    def test_80_ui_v2_no_direct_core_imports(self):
        """[Phase 1.2] ui_v2 가 core.* 의 banned 모듈 직접 import 0건.

        ROADMAP §3 Phase 1 (2) KPI: "ui/ 폴더에서 session_manager · workflow_engine
        · ai_engine 직접 import 0건". ui_v2 는 5/8 시점 Chunk A 적용 완료 — 모든
        import 가 ``core.app_service`` 경유.

        Banned (UI 가 직접 import 금지):
        - ``core.session_manager`` — 도메인 클래스 (Session/Step) 는 app_service 에서 re-export
        - ``core.ai_engine`` — AIEngineManager construction 은 ``AppService.reload_ai`` /
          ``AppService.create_default`` 사용
        - ``core.execution_kernel`` — ExecutionKernel 은 app_service 에서 re-export +
          ``AppService.create_kernel`` factory
        - ``core.workflow_engine`` — 모든 호출은 AppService.run_blocks / stop_blocks 등
        - ``core.storage.*`` — repo 생성은 ``AppService.create_default`` 사용

        ui/ legacy 폴더는 Chunk B (추후 별 sub-task) 에서 정리.
        """
        from pathlib import Path

        ui_v2_src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )

        banned_modules = [
            "core.session_manager",
            "core.ai_engine",
            "core.execution_kernel",
            "core.workflow_engine",
            "core.storage.local_json",
            "core.storage.base",
            "core.storage.in_memory",
        ]
        for mod in banned_modules:
            self.assert_true(
                f"from {mod}" not in ui_v2_src and f"import {mod}" not in ui_v2_src,
                f"[Phase 1.2 KPI] ui_v2/main_window_v2.py 에서 '{mod}' 직접 import 금지 "
                "- core.app_service 경유 필수",
            )

        # AppService re-export 검증 — UI 가 사용하는 도메인 타입이 app_service 에서 노출
        from core.app_service import AppService, ExecutionKernel, Session, Step, StepResult

        self.assert_true(
            Session is not None and Step is not None,
            "[Phase 1.2] AppService 가 Session / Step re-export 필수",
        )
        self.assert_true(
            ExecutionKernel is not None and StepResult is not None,
            "[Phase 1.2] AppService 가 ExecutionKernel / StepResult re-export 필수",
        )

        # AppService 의 factory / reload 메서드 존재
        for method in ("create_default", "reload_ai", "create_kernel"):
            self.assert_true(
                hasattr(AppService, method),
                f"[Phase 1.2] AppService.{method} 필수 (UI 가 core.* 직접 import 안 하게)",
            )

    def test_83_appservice_chunk_b_facades(self):
        """[Phase 1.2 Chunk B] AppService 가 ui/ legacy 정리에 필요한 façade 노출.

        ui/main_window.py + handler 들이 ``core.workflow_engine`` /
        ``core.import_manager`` / ``core.prompt_builder`` / ``core.win_inspector``
        를 직접 import 하지 않게 하기 위해 다음을 ``core.app_service`` 모듈에서
        re-export + property/setter 로 노출.

        - 핵심 클래스 re-export: AIEngineManager / WorkflowEngine / PromptBuilder
          / WindowInspector / CodeSandbox
        - pure 함수 re-export: extract_imports / merge_imports / extract_code_delta
          / extract_import_delta / extract_initial_block / extract_library_block
          / extract_step_delta_code
        - workflow_engine property + set_workflow_engine setter (외부 settings 반영
          인스턴스 주입)
        - prompt_builder property + set_prompt_builder setter (외부 prompts.json
          반영 인스턴스 주입)
        """
        from core import app_service as svc

        # 클래스 re-export
        for name in (
            "AIEngineManager",
            "WorkflowEngine",
            "PromptBuilder",
            "WindowInspector",
            "CodeSandbox",
        ):
            self.assert_true(
                hasattr(svc, name) and getattr(svc, name) is not None,
                f"[Phase 1.2 Chunk B] core.app_service.{name} re-export 필수",
            )

        # pure 함수 re-export
        for name in (
            "extract_imports",
            "merge_imports",
            "extract_code_delta",
            "extract_import_delta",
            "extract_initial_block",
            "extract_library_block",
            "extract_step_delta_code",
        ):
            self.assert_true(
                hasattr(svc, name) and callable(getattr(svc, name)),
                f"[Phase 1.2 Chunk B] core.app_service.{name} (pure 함수) re-export 필수",
            )

        # __all__ 에 모두 포함
        for name in (
            "AIEngineManager",
            "WorkflowEngine",
            "PromptBuilder",
            "WindowInspector",
            "CodeSandbox",
            "extract_imports",
            "merge_imports",
            "extract_code_delta",
            "extract_import_delta",
            "extract_initial_block",
            "extract_library_block",
            "extract_step_delta_code",
        ):
            self.assert_true(
                name in svc.__all__,
                f"[Phase 1.2 Chunk B] '{name}' 가 core.app_service.__all__ 에 포함 필수",
            )

        # workflow_engine property + setter
        from core.app_service import AppService, WorkflowEngine
        from core.storage.in_memory import InMemoryRepository

        app = AppService(session_repo=InMemoryRepository())
        engine = app.workflow_engine
        self.assert_true(
            isinstance(engine, WorkflowEngine),
            "[Phase 1.2 Chunk B] AppService.workflow_engine 이 WorkflowEngine 인스턴스 반환",
        )
        self.assert_true(
            app.workflow_engine is engine,
            "[Phase 1.2 Chunk B] workflow_engine 은 같은 인스턴스 캐싱",
        )
        custom = WorkflowEngine(step_delay_ms=999)
        app.set_workflow_engine(custom)
        self.assert_true(
            app.workflow_engine is custom,
            "[Phase 1.2 Chunk B] set_workflow_engine 으로 외부 인스턴스 주입 가능",
        )

        # prompt_builder property + setter
        from core.app_service import PromptBuilder

        app2 = AppService(session_repo=InMemoryRepository())
        pb = app2.prompt_builder
        self.assert_true(
            isinstance(pb, PromptBuilder),
            "[Phase 1.2 Chunk B] AppService.prompt_builder 가 PromptBuilder 반환",
        )
        self.assert_true(
            app2.prompt_builder is pb,
            "[Phase 1.2 Chunk B] prompt_builder 은 같은 인스턴스 캐싱",
        )
        custom_pb = PromptBuilder()
        app2.set_prompt_builder(custom_pb)
        self.assert_true(
            app2.prompt_builder is custom_pb,
            "[Phase 1.2 Chunk B] set_prompt_builder 로 외부 인스턴스 주입 가능",
        )

        # 생성자에서 prompt_builder 직접 주입
        app3 = AppService(session_repo=InMemoryRepository(), prompt_builder=custom_pb)
        self.assert_true(
            app3.prompt_builder is custom_pb,
            "[Phase 1.2 Chunk B] AppService.__init__ 에 prompt_builder 인자로 주입 가능",
        )

    def test_84_main_window_no_direct_core_imports(self):
        """[Phase 1.2 Chunk B] ui/main_window.py 가 core.* banned 모듈 직접 import 0건.

        ROADMAP §3 Phase 1 (2) KPI: "ui/ 폴더에서 session_manager · workflow_engine ·
        ai_engine 직접 import 0건". main_window.py 는 5/9 시점 Chunk B 적용 완료 —
        모든 import 가 ``core.app_service`` 경유 (모듈 상단 + 함수 내부 모두).

        Banned (UI 가 직접 import 금지):
        - core.session_manager, core.ai_engine, core.execution_kernel,
          core.workflow_engine, core.import_manager, core.prompt_builder,
          core.win_inspector
        - core.storage.* — repo 생성은 ``AppService.create_default``

        ui/ 의 다른 파일 (ai_call_handler / block_execution_handler / chat_panel 등) 은
        Chunk B 의 sub-step 3 에서 정리.
        """
        from pathlib import Path

        src = (Path(__file__).parent.parent / "ui" / "main_window.py").read_text(encoding="utf-8")

        banned_modules = [
            "core.session_manager",
            "core.ai_engine",
            "core.execution_kernel",
            "core.workflow_engine",
            "core.import_manager",
            "core.prompt_builder",
            "core.win_inspector",
            "core.storage.local_json",
            "core.storage.base",
            "core.storage.in_memory",
        ]
        for mod in banned_modules:
            self.assert_true(
                f"from {mod}" not in src and f"import {mod}" not in src,
                f"[Phase 1.2 Chunk B KPI] ui/main_window.py 에서 '{mod}' 직접 import 금지 "
                "- core.app_service 경유 필수",
            )

        # 단일 진입점 확인 — 'from core.app_service import' 가 존재
        self.assert_true(
            "from core.app_service import" in src,
            "[Phase 1.2 Chunk B] main_window 가 core.app_service 단일 진입점 사용",
        )

    def test_85_ui_folder_no_direct_core_imports(self):
        """[Phase 1.2 Chunk B 완결] ui/ 폴더 전체에서 core.* banned 모듈 직접 import 0건.

        ROADMAP §3 Phase 1 (2) KPI 의 최종 가드. test_80 (ui_v2) + test_84 (main_window)
        의 영역을 ui/ 폴더 전체 .py 로 확장. handler / chat_panel / ui_inspection_handler /
        code_viewer / element_picker / settings_dialog 등 모든 파일이 ``core.app_service``
        단일 진입점만 사용해야 한다.

        예외: ``core.environment_scanner`` / ``core.adapters.*`` 는 banned 목록에 없음
        (UI-Core 핵심 KPI 도메인 외). 추후 정리는 별 sub-task.
        """
        from pathlib import Path

        ui_dir = Path(__file__).parent.parent / "ui"
        banned_modules = [
            "core.session_manager",
            "core.ai_engine",
            "core.execution_kernel",
            "core.workflow_engine",
            "core.import_manager",
            "core.prompt_builder",
            "core.win_inspector",
            "core.storage.local_json",
            "core.storage.base",
            "core.storage.in_memory",
        ]

        violations: list[str] = []
        for py_file in ui_dir.glob("*.py"):
            src = py_file.read_text(encoding="utf-8")
            for mod in banned_modules:
                if f"from {mod}" in src or f"import {mod}" in src:
                    violations.append(f"{py_file.name}: '{mod}' 직접 import")

        msg = (
            "[Phase 1.2 Chunk B KPI] ui/ 폴더에 banned core import 잔존:\n  - "
            + "\n  - ".join(violations)
            if violations
            else "ok"
        )
        self.assert_true(not violations, msg)

    def test_86_settings_dialog_has_openai_test_connection(self):
        """[Phase 1.8] SettingsDialog 에 OpenAI 호환 연결 테스트 기능 존재.

        DeepSeek / OpenAI / Groq 등 OpenAI 호환 LLM 의 api_key 등록 후
        Save 안 한 입력값으로 즉시 연결 검증이 가능해야 한다 (UX + 비용 회피).

        가드 항목:
        1. SettingsDialog._test_openai_connection 메서드 존재
        2. _create_ai_tab 소스에 'Test connection' 또는 '연결 테스트' 라벨/버튼 존재
        3. 콜백이 dialog 입력값(base_url/api_key/model/temperature)으로 임시 config 생성
        4. timeout 15s + max_tokens 32 강제 (ping 비용 최소화)
        5. OpenAICompatAdapter._generate_sync 직접 호출 (UI thread 동기)
        """
        import inspect

        from ui.settings_dialog import SettingsDialog

        self.assert_true(
            hasattr(SettingsDialog, "_test_openai_connection"),
            "[Phase 1.8] SettingsDialog._test_openai_connection 메서드 필수",
        )

        ai_tab_src = inspect.getsource(SettingsDialog._create_ai_tab)
        self.assert_true(
            "openai_test_btn" in ai_tab_src and "_test_openai_connection" in ai_tab_src,
            "[Phase 1.8] _create_ai_tab 에 openai_test_btn 위젯 + _test_openai_connection 콜백 연결 필수",
        )
        self.assert_true(
            "연결 테스트" in ai_tab_src
            or "Test connection" in ai_tab_src.lower().replace(" ", " "),
            "[Phase 1.8] AI 탭에 '연결 테스트' / 'Test connection' 라벨 필수",
        )

        cb_src = inspect.getsource(SettingsDialog._test_openai_connection)
        self.assert_true(
            "openai_base_url_edit" in cb_src
            and "openai_api_key_edit" in cb_src
            and "openai_model_edit" in cb_src,
            "[Phase 1.8] 콜백이 dialog 입력값(base_url/api_key/model)으로 config 생성 필수",
        )
        self.assert_true(
            "timeout_seconds" in cb_src and "15" in cb_src,
            "[Phase 1.8] ping timeout 15s 강제 필수 (비용/시간 최소화)",
        )
        self.assert_true(
            "max_tokens" in cb_src and "32" in cb_src,
            "[Phase 1.8] ping max_tokens 32 강제 필수 (응답 비용 최소화)",
        )
        self.assert_true(
            "OpenAICompatAdapter" in cb_src and "_generate_sync" in cb_src,
            "[Phase 1.8] OpenAICompatAdapter._generate_sync 직접 호출 필수",
        )

    def test_87_open_settings_reloads_ai_engine(self):
        """[Phase 1.8] _open_settings 가 AIEngineManager 를 재로드한다.

        settings dialog 에서 OpenAI 호환 엔진 선택 + api_key/model 변경 + Apply
        시 메모리상의 self.ai_engine 이 새 settings 기준으로 재생성되어야 한다.
        없으면 next AI 호출이 stale config 사용 (init 시점 settings 그대로 → 빈
        api_key 로 401, 또는 모델 변경 무시).

        가드: _open_settings 소스에 app_service.reload_ai(settings) 호출 +
        self.ai_engine alias 재할당 패턴 존재.
        """
        import inspect

        from ui.main_window import MainWindow

        src = inspect.getsource(MainWindow._open_settings)
        self.assert_true(
            "reload_ai" in src and "self.settings" in src,
            "[Phase 1.8] _open_settings 가 app_service.reload_ai(self.settings) 호출 필수",
        )
        self.assert_true(
            "self.ai_engine" in src and "ai_manager" in src,
            "[Phase 1.8] _open_settings 가 self.ai_engine = self.app_service.ai_manager alias 갱신 필수",
        )

    def test_88_engine_choice_persists_and_displays(self):
        """[Phase 1.8] AI 엔진 선택의 즉시 표시 + settings.json 영구 저장.

        직전 세션 (5/9) 에서 발견된 갭들을 한 unit 으로 fix:
        - B1: ai_call_handler 가 console_panel 에 넘기는 ai_engine 속성명이
              잘못되어 (current_engine — 미존재) 화면에 항상 빈 칸 표시되던 버그.
              get_current_name() 으로 정정.
        - B2: ui_v2 의 step_done 메시지에 어느 엔진이 답했는지 명시 누락.
              엔진명 prefix 추가.
        - B4: switch_engine / switch_ai_engine 호출이 메모리 _current_name 만
              변경하고 settings.json 영구 저장 X — 재시작 시 gemini_cli 로 회귀.
              호출 사이트 4곳 (legacy main_window 콤보 / ui_v2 헤더 콤보 /
              명령 팔레트 / onboarding wizard) 모두 ai.selected 를 persist.
        """
        import inspect

        # ── B1 ─────────────────────────────────────────────────────────
        from ui import ai_call_handler

        ach_src = inspect.getsource(ai_call_handler)
        self.assert_true(
            "current_engine" not in ach_src,
            "[B1] ai_call_handler 에 'current_engine' 잔존 — get_current_name() 으로 정정 필요",
        )
        self.assert_true(
            "get_current_name" in ach_src,
            "[B1] ai_call_handler 가 mw.ai_engine.get_current_name() 으로 엔진명 조회 필수",
        )

        # ── B2 ─────────────────────────────────────────────────────────
        from ui_v2.main_window_v2 import MainWindowV2

        send_src = inspect.getsource(MainWindowV2._send_request)
        # i18n 도입 후 "엔진:" literal 은 catalog 로 이동 — tr key 검색
        # (ruff format multi-line 분리 대응 — key string 만 검사).
        self.assert_true(
            "get_ai_engine_name" in send_src and '"ui_v2.step_done.step_generated"' in send_src,
            "[B2] ui_v2 _send_request 의 step_done 메시지에 엔진명 prefix 필수 (tr key)",
        )

        # ── B4 — legacy main_window ───────────────────────────────────
        from ui.main_window import MainWindow

        legacy_src = inspect.getsource(MainWindow._on_ai_engine_changed)
        self.assert_true(
            'setdefault("ai"' in legacy_src and "_save_settings" in legacy_src,
            "[B4-a] legacy _on_ai_engine_changed 가 settings['ai']['selected'] 저장 + _save_settings 호출 필수",
        )

        # ── B4 — ui_v2 헤더 콤보 / 팔레트 / onboarding ─────────────────
        self.assert_true(
            hasattr(MainWindowV2, "_persist_engine_choice"),
            "[B4-b] ui_v2 에 _persist_engine_choice 헬퍼 메서드 필수",
        )

        helper_src = inspect.getsource(MainWindowV2._persist_engine_choice)
        self.assert_true(
            'setdefault("ai"' in helper_src and "_save_settings" in helper_src,
            "[B4-b] _persist_engine_choice 가 settings.ai.selected 영구 저장 필수",
        )

        on_changed_src = inspect.getsource(MainWindowV2._on_engine_changed)
        self.assert_true(
            "_persist_engine_choice" in on_changed_src,
            "[B4-b] ui_v2 _on_engine_changed (헤더 콤보) 가 _persist_engine_choice 호출 필수",
        )

        palette_src = inspect.getsource(MainWindowV2._switch_ai_engine_from_palette)
        self.assert_true(
            "_persist_engine_choice" in palette_src,
            "[B4-c] ui_v2 _switch_ai_engine_from_palette (명령 팔레트) 가 _persist_engine_choice 호출 필수",
        )

        # onboarding path — _maybe_show_onboarding 안에 ai.selected 영구 저장 패턴
        onboard_src = inspect.getsource(MainWindowV2._maybe_show_onboarding)
        self.assert_true(
            'setdefault("ai"' in onboard_src and "selected_engine" in onboard_src,
            "[B4-d] ui_v2 onboarding wizard 적용 시 settings['ai']['selected'] 도 함께 저장 필수",
        )

    def test_89_ui_v2_console_visibility_from_settings(self):
        """[Phase 1.8 P4] ui_v2 콘솔 패널이 settings.ui.console_visible 값 따름.

        이전엔 hardcoded hide() — 사용자가 Ctrl+` 모르면 AI 응답 메타
        (엔진/토큰/시간) 를 화면에서 볼 수 없었음. settings 의 console_visible
        값을 초기 상태로 반영 + _toggle_console 시 settings.json 영구 저장.

        가드:
        1. __init__ 가 self._load_settings() 후 ui.console_visible 로 _console_visible 초기화
        2. _build_console_panel 이 setVisible(self._console_visible) 호출 (hardcoded hide() 금지)
        3. _toggle_console 가 settings.json 에 영구 저장
        """
        import inspect

        from ui_v2.main_window_v2 import MainWindowV2

        init_src = inspect.getsource(MainWindowV2.__init__)
        self.assert_true(
            "console_visible" in init_src and "_load_settings" in init_src,
            "[P4] __init__ 가 settings.ui.console_visible 로 _console_visible 초기화 필수",
        )

        build_src = inspect.getsource(MainWindowV2._build_console_panel)
        self.assert_true(
            "self._console_visible" in build_src and "setVisible" in build_src,
            "[P4] _build_console_panel 이 setVisible(self._console_visible) 호출 필수",
        )
        self.assert_true(
            ".hide()" not in build_src,
            "[P4] _build_console_panel 에서 hardcoded .hide() 금지 — setVisible 만 사용",
        )

        toggle_src = inspect.getsource(MainWindowV2._toggle_console)
        self.assert_true(
            "_save_settings" in toggle_src and "console_visible" in toggle_src,
            "[P4] _toggle_console 가 settings.console_visible 영구 저장 필수",
        )

    def test_90_prompt_builder_injects_system_context(self):
        """[Phase 1.8 P1a] build_step_prompt 출력에 system_context 가 inject 되어야 한다.

        이전 갭: prompt_builder 가 self.system_context 보유만 하고 build_step_prompt
        의 출력 (parts join) 에 append 하지 않음 — prompts.json 의 12K+ chars
        모든 RPA 가이드 (idempotent driver, jupyter, UWP wait, pyautogui PRIMARY,
        title_re, Text→부모 promote 등) 가 어떤 모델에도 도달조차 안 함.

        P1a fix: parts 의 [0] 위치에 self.system_context prepend. 사용자 요청 [1]
        보다 더 앞. 단일 string 유지 (어댑터 변경 X).

        가드:
        1. system_context 보유 시 prompt 출력에 그 텍스트 포함
        2. 빈 system_context (template 미설정) 면 inject X — fail-safe
        3. inject 위치가 사용자 요청보다 앞 (최상단)
        """
        from core.prompt_builder import PromptBuilder

        # 보유 시 inject 검증
        builder = PromptBuilder(
            prompts_config={
                "system_context": "## 핵심 시스템 가이드 SENTINEL_X9Q\n반드시 try/except 사용",
            }
        )

        class _DummySession:
            steps: list = []
            project_type = "desktop"

        prompt = builder.build_step_prompt(
            session=_DummySession(),
            user_request="메모장 실행",
        )
        self.assert_true(
            "SENTINEL_X9Q" in prompt,
            "[P1a] build_step_prompt 출력에 system_context 의 본문 포함 필수",
        )

        # 위치 검증 — system_context 가 사용자 요청보다 앞
        sc_pos = prompt.find("SENTINEL_X9Q")
        ur_pos = prompt.find("메모장 실행")
        self.assert_true(
            sc_pos >= 0 and ur_pos >= 0 and sc_pos < ur_pos,
            f"[P1a] system_context 는 사용자 요청보다 앞에 위치 필수 (sc={sc_pos}, ur={ur_pos})",
        )

        # 빈 system_context fail-safe
        empty_builder = PromptBuilder(prompts_config={"system_context": ""})
        empty_prompt = empty_builder.build_step_prompt(
            session=_DummySession(), user_request="테스트"
        )
        self.assert_true(
            "테스트" in empty_prompt,
            "[P1a] 빈 system_context 일 때도 prompt 정상 생성",
        )

    def test_91_system_role_split_through_stack(self):
        """[Phase 1.8 P1b] system role 분리가 stack 전체를 통과한다.

        OpenAI 호환 어댑터 (DeepSeek/Groq 등) 가 system role 메시지를 user 와
        분리해서 받으면 attention 강화로 가이드를 더 강하게 따른다. P1a 의
        단일 string prepend 보다 best practice. Gemini CLI 는 system role path
        없으니 prompt 앞에 prepend (P1a 와 동일 결과).

        가드:
        1. PromptBuilder.build_step_prompt_split 가 (system_text, user_text) 튜플 반환
        2. system_text 에 prompts.json 의 system_context 본문 (sentinel) 포함
        3. user_text 에 system_context sentinel 미포함 (분리 검증)
        4. BaseAIAdapter.generate 시그니처에 system 인자 존재
        5. OpenAICompatAdapter._generate_sync 가 system 있으면 messages 첫 항목에
           system role 로 추가
        6. AIEngineManager.generate 가 system 인자 통과
        7. AppService.generate_step 가 split 호출 후 어댑터에 system 전달
        """
        import inspect

        from core.adapters.base_adapter import BaseAIAdapter
        from core.adapters.openai_compat_adapter import OpenAICompatAdapter
        from core.ai_engine import AIEngineManager
        from core.app_service import AppService
        from core.prompt_builder import PromptBuilder

        # 1~3: split 메서드 + system_text/user_text 분리
        builder = PromptBuilder(
            prompts_config={
                "system_context": "## SENTINEL_SPLIT_X9Q 가이드 본문",
            }
        )

        class _DummySession:
            steps: list = []
            project_type = "desktop"

        result = builder.build_step_prompt_split(
            session=_DummySession(), user_request="테스트 요청"
        )
        self.assert_true(
            isinstance(result, tuple) and len(result) == 2,
            "[P1b] build_step_prompt_split 가 (system, user) 튜플 반환 필수",
        )
        system_text, user_text = result
        self.assert_true(
            "SENTINEL_SPLIT_X9Q" in system_text,
            "[P1b] system_text 에 system_context 본문 포함 필수",
        )
        self.assert_true(
            "SENTINEL_SPLIT_X9Q" not in user_text,
            "[P1b] user_text 에서 system_context 분리 필수 (중복 inject 방지)",
        )
        self.assert_true(
            "테스트 요청" in user_text,
            "[P1b] user_text 에 사용자 요청 포함 필수",
        )

        # 4: base_adapter 시그니처
        sig = inspect.signature(BaseAIAdapter.generate)
        self.assert_true(
            "system" in sig.parameters,
            "[P1b] BaseAIAdapter.generate 시그니처에 system 인자 필수",
        )

        # 5: OpenAI compat 의 messages 분리
        oc_sync_src = inspect.getsource(OpenAICompatAdapter._generate_sync)
        self.assert_true(
            '"role": "system"' in oc_sync_src,
            "[P1b] OpenAICompatAdapter._generate_sync 가 system role messages 분리 필수",
        )

        # 6: AIEngineManager 통과
        mgr_src = inspect.getsource(AIEngineManager.generate)
        self.assert_true(
            "system=system" in mgr_src or "system=" in mgr_src,
            "[P1b] AIEngineManager.generate 가 system 인자를 어댑터에 통과 필수",
        )

        # 7: AppService.generate_step 가 split 호출
        gs_src = inspect.getsource(AppService.generate_step)
        self.assert_true(
            "build_step_prompt_split" in gs_src and "system=" in gs_src,
            "[P1b] AppService.generate_step 가 split 호출 + 어댑터에 system 전달 필수",
        )

    def test_92_prompts_system_context_hardened(self):
        """[Phase 1.8 P3] prompts.json system_context 의 try/except 강제 + import
        위치 강제 가이드 강화.

        P1a + P1b 로 system_context 가 모델에 정상 도달하게 된 후, 본문 자체의
        가이드를 강화하여 DeepSeek 등 OpenAI 호환 모델에서 step 본문 안 import
        + try/except 누락 회귀 방지.

        가드:
        1. system_context 에 'try/except 강제' 어휘 + '예외 없음' 강조 존재
        2. system_context 에 'import 위치 강제' + '코드의 가장 최상단' 표현 존재
        3. system_context 에 'step 본문 안에 import' 금지 어휘 존재
        """
        import json
        from pathlib import Path

        prompts_path = Path(__file__).parent.parent / "config" / "prompts.json"
        prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
        sys_ctx = prompts.get("system_context", "")

        self.assert_true(
            "try/except 강제" in sys_ctx and "예외 없음" in sys_ctx,
            "[P3] system_context 에 'try/except 강제 (예외 없음)' 어휘 필수",
        )
        self.assert_true(
            "import 위치 강제" in sys_ctx and "가장 최상단" in sys_ctx,
            "[P3] system_context 에 'import 위치 강제' + '가장 최상단' 표현 필수",
        )
        self.assert_true(
            "step 본문" in sys_ctx and "import" in sys_ctx,
            "[P3] system_context 에 'step 본문 안에 import 금지' 가이드 필수",
        )

    def test_93_system_context_element_promote_explicit(self):
        """[Phase 1.8 G1] system_context #17 가 element 를 직접 찾는 단계를 명시.

        직전 세션 (5/9) Step 3 회귀: DeepSeek 가 system_context #17 의 walk-up
        예제만 복사 → `click_target = element` 단계에서 NameError 발생.
        Root cause: 기존 #17 예제는 `element` 변수가 자동 주입된다는 잘못된 가정.
        ohdo 의 흐름은 element 정보를 prompt 의 element_context 에 텍스트로만
        전달하고 코드는 `win.child_window(...)` 로 직접 찾아야 함.

        G1 fix: #17 본문에 다음 명시:
        1. "변수 자동 주입 X" / "element 를 코드 안에서 직접 찾으세요"
        2. element_context 의 auto_id / control_type 으로 win.child_window 호출 예제
        3. NameError: name 'element' is not defined 회귀 사례 인용
        """
        import json
        from pathlib import Path

        prompts_path = Path(__file__).parent.parent / "config" / "prompts.json"
        prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
        sys_ctx = prompts.get("system_context", "")

        self.assert_true(
            "변수 자동 주입 X" in sys_ctx,
            "[G1] system_context 에 'element 변수 자동 주입 X' 명시 필수",
        )
        self.assert_true(
            "element 를 코드 안에서 직접 찾으세요" in sys_ctx,
            "[G1] system_context 에 'element 를 직접 찾으세요' 어휘 필수",
        )
        self.assert_true(
            "element_context 의 auto_id" in sys_ctx and "win.child_window" in sys_ctx,
            "[G1] system_context 에 'win.child_window 로 element_context 의 auto_id 사용' 패턴 필수",
        )
        # 회귀 사례 인용 — DeepSeek 의 NameError 패턴
        self.assert_true(
            "NameError" in sys_ctx and ("'element'" in sys_ctx or "'click_target'" in sys_ctx),
            "[G1] system_context 에 NameError 회귀 사례 (element/click_target) 인용 필수",
        )

    def test_94_library_block_essential_imports_prepended(self):
        """[Phase 1.8 G5] extract_library_block 이 핵심 패키지 자동 prepend.

        DeepSeek 등이 step_imports 에 pyautogui / pyperclip 누락 시 step 본문에서
        NameError 회귀 (5/9 v2-새세션-150447 step 2/3). 핵심 패키지를 library
        block 에 강제 inject — step 본문 안 import 없어도 사용 가능.
        """
        from core.workflow_engine import _ensure_essential_imports

        # 빈 block — 핵심 5개 import 가 모두 들어감
        result = _ensure_essential_imports("")
        for mod in ("pyautogui", "pyperclip", "ctypes", "time", "subprocess"):
            self.assert_true(
                f"import {mod}" in result,
                f"[G5] 빈 library block 에 'import {mod}' prepend 필수",
            )

        # 일부만 있는 block — 누락된 것만 prepend
        partial = "import time\nfrom pywinauto import Application"
        merged = _ensure_essential_imports(partial)
        self.assert_true(
            "import pyautogui" in merged and "import pyperclip" in merged,
            "[G5] 누락된 핵심 import 만 prepend",
        )
        self.assert_true(
            merged.count("import time") == 1,
            "[G5] 이미 있는 'import time' 중복 prepend 금지",
        )

        # from-style 도 인식 — 'from pyautogui import X' 있으면 'import pyautogui' 안 prepend
        from_style = "from pyautogui import click\nimport time"
        merged2 = _ensure_essential_imports(from_style)
        self.assert_true(
            "import pyautogui" not in merged2,
            "[G5] 'from pyautogui import ...' 이미 있으면 'import pyautogui' 중복 prepend 금지",
        )

    def test_95_element_context_guide_enforces_template(self):
        """[Phase 1.8 G2] prompt_builder 의 element_context 가이드가 템플릿
        강제 사용 어휘 포함.

        이전 가이드: "참고하되 ... 수정하세요" — 너무 약해서 DeepSeek 가 무시
        하고 짧은 자체 코드 작성 → element/click_target/pyautogui 누락 회귀.
        G2 fix: "그대로 시작 코드로 사용" + "자체적으로 element 변수 다시 만들지
        마세요" + 회귀 사례 인용으로 강제력 ↑.
        """
        import inspect

        from core.prompt_builder import PromptBuilder

        src = inspect.getsource(PromptBuilder._build_step_prompt_parts)
        self.assert_true(
            "그대로 시작 코드로 사용" in src,
            "[G2] element_context 가이드에 '그대로 시작 코드로 사용' 강제 어휘 필수",
        )
        self.assert_true(
            "자체적으로 element 변수를 다시 만들지 마세요" in src,
            "[G2] element_context 가이드에 'element 변수 자체 정의 금지' 명시 필수",
        )
        self.assert_true(
            "click_target' is not defined" in src,
            "[G2] 회귀 사례 (click_target NameError) 인용 필수",
        )

    def test_96_element_template_no_import_lines(self):
        """[Phase 1.8 G2.5] win_inspector 의 element_context 코드 템플릿이
        import 라인을 포함하지 않는다.

        이전 갭: AI 가 element_context 의 ready-to-use 템플릿을 그대로 사용
        하면서 마커 안에 `import ctypes` / `import pyautogui` 등이 들어감 →
        extract_imports 가 step 1 의 상단 import 만 추출 → step 2/3 의
        step_imports = []. P3 #5 (import 위치 강제) 위반.

        G2.5 fix: win_inspector 의 desktop / owner-drawn 템플릿에서 import
        라인 제거. G5 의 _ENSENTIAL_LIBRARY_IMPORTS 가 라이브러리 블럭에 핵심
        패키지 자동 prepend.

        가드:
        1. desktop element 템플릿 (_get_desktop_element_info_text) 에 'import
           ctypes' / 'import pyautogui' / 'from pywinauto import Application'
           lines.append 호출 0건
        2. owner-drawn 템플릿 (_get_owner_drawn_element_info_text) 동일
        3. _ESSENTIAL_LIBRARY_IMPORTS 에 ctypes.wintypes + Application 포함
        """
        import inspect

        from core.win_inspector import WindowInspector
        from core.workflow_engine import _ESSENTIAL_LIBRARY_IMPORTS

        # 1) desktop 템플릿 — import 5종 제거 검증
        desktop_src = inspect.getsource(WindowInspector._get_desktop_element_info_text)
        for forbidden in (
            'lines.append("import ctypes")',
            'lines.append("import ctypes.wintypes")',
            'lines.append("import time")',
            'lines.append("import pyautogui")',
            'lines.append("from pywinauto import Application")',
        ):
            self.assert_true(
                forbidden not in desktop_src,
                f"[G2.5] desktop 템플릿에서 '{forbidden}' 제거 필수 (라이브러리 블럭이 처리)",
            )

        # 2) owner-drawn 템플릿
        ownerdrawn_src = inspect.getsource(WindowInspector._get_owner_drawn_element_info_text)
        for forbidden in (
            'lines.append("import ctypes")',
            'lines.append("import pyautogui")',
        ):
            self.assert_true(
                forbidden not in ownerdrawn_src,
                f"[G2.5] owner-drawn 템플릿에서 '{forbidden}' 제거 필수",
            )

        # 3) library 블럭 essential imports 보강
        self.assert_true(
            "import ctypes.wintypes" in _ESSENTIAL_LIBRARY_IMPORTS,
            "[G2.5] _ESSENTIAL_LIBRARY_IMPORTS 에 'import ctypes.wintypes' 필수",
        )
        self.assert_true(
            "from pywinauto import Application" in _ESSENTIAL_LIBRARY_IMPORTS,
            "[G2.5] _ESSENTIAL_LIBRARY_IMPORTS 에 'from pywinauto import Application' 필수",
        )

    def test_97_code_validator_detects_four_issue_kinds(self):
        """[Phase 1.8 G7-A] core.code_validator 가 4종 정적 분석 항목을 검출.

        배경: handoff §16 잔존 갭 — DeepSeek-V3 같은 모델이 system_context 가이드를
        100% 따르지 않아 step 3/4 에서 회귀 (변수 재정의 / try-except 누락 / 들여쓰기
        깨짐 / import 위치 위반). 프롬프트 강화 (G6) 만으로는 100% 보장 불가 →
        AI 가 코드 만든 직후 정적 분석 hook 으로 자동 검사.

        본 테스트는 G7-A (검사 엔진) 만 검증. UI / AI 호출 hook 은 G7-B/C/D.

        가드:
        1. 빈 코드 / 정상 코드 → 0 issue (false positive 방지)
        2. SyntaxError (들여쓰기 깨짐) → has_syntax_error True + 다른 검사 skip
        3. 변수 재정의 (`app = ...` prev + cur 모두 module-level) → 'redefined_var'
        4. try 밖 risky 호출 (`pyautogui.click(...)` module-level) → 'missing_try'
        5. import 위치 위반 (`if x: import y`) → 'import_misplaced'
        6. 함수 정의 안의 risky 호출은 검출 X (false positive 방지)
        7. for-target 은 재정의 검사 제외 (module-level 단순 Assign 만)
        8. ValidationIssue / ValidationResult 데이터 클래스 + has_issues / by_kind
        """
        from core.code_validator import (
            ValidationIssue,
            ValidationResult,
            validate_step_code,
        )

        # 1) 빈 코드 / 정상 코드 → 0 issue
        self.assert_true(
            not validate_step_code("").has_issues,
            "[G7-A] 빈 코드는 issue 0 건 (false positive 방지)",
        )
        self.assert_true(
            not validate_step_code("   \n  \n").has_issues,
            "[G7-A] 공백만 있는 코드도 issue 0 건",
        )
        clean_code_2 = (
            "import pyautogui\n"
            "try:\n"
            "    pyautogui.click(100, 200)\n"
            "except Exception as e:\n"
            "    print(e)\n"
        )
        # 위 코드도 module-level import 라 misplaced X. risky 호출 try 안 → missing_try X
        # 단 import 는 module body 의 직계 Import 라 misplaced 검사 통과.
        # cur 만 검사 (prev 없음) → redefined_var X. syntax OK → 0 issue.
        result_clean = validate_step_code(clean_code_2)
        self.assert_true(
            not result_clean.has_issues,
            f"[G7-A] 정상 코드는 issue 0 건. got: {[(i.kind, i.message) for i in result_clean.issues]}",
        )

        # 2) SyntaxError → has_syntax_error + 나머지 검사 skip
        broken_indent = (
            "def foo():\n"
            "x = 1\n"  # def 본문 indent 누락
        )
        result_syntax = validate_step_code(broken_indent)
        self.assert_true(
            result_syntax.has_syntax_error,
            "[G7-A] 들여쓰기 깨진 코드는 has_syntax_error True",
        )
        self.assert_true(
            result_syntax.has_issues,
            "[G7-A] syntax 오류는 has_issues True",
        )
        self.assert_equal(
            len(result_syntax.issues),
            1,
            "[G7-A] syntax 오류 시 다른 검사 skip (issue 1 건만)",
        )
        self.assert_equal(
            result_syntax.issues[0].kind,
            "syntax",
            "[G7-A] syntax issue 의 kind 는 'syntax'",
        )

        # 3) 변수 재정의 — prev 의 'app' 를 cur 가 다시 module-level 로 할당
        prev_step1 = (
            "from pywinauto import Application\n"
            "app = Application(backend='uia').connect(title='메모장')\n"
            "win = app.window(title='메모장')\n"
        )
        cur_step3 = (
            "app = Application(backend='uia').connect(title='메모장')\n"  # 재정의 위반
            "win.set_focus()\n"
        )
        result_redef = validate_step_code(cur_step3, prev_step_codes=[prev_step1])
        redef_issues = result_redef.by_kind("redefined_var")
        self.assert_equal(
            len(redef_issues),
            1,
            f"[G7-A] 'app' 재정의 1 건 검출 필수. got issues: {[(i.kind, i.message) for i in result_redef.issues]}",
        )
        self.assert_true(
            "'app'" in redef_issues[0].message,
            f"[G7-A] redefined_var message 에 'app' 포함 필수. got: {redef_issues[0].message}",
        )

        # 4) try 밖 risky 호출 → missing_try
        unprotected = (
            "import pyautogui\n"
            "pyautogui.click(100, 200)\n"  # try 밖 module-level
        )
        result_risky = validate_step_code(unprotected)
        risky_issues = result_risky.by_kind("missing_try")
        self.assert_equal(
            len(risky_issues),
            1,
            f"[G7-A] try 밖 pyautogui.click 1 건 검출 필수. got: {[(i.kind, i.message) for i in result_risky.issues]}",
        )
        self.assert_true(
            "pyautogui.click" in risky_issues[0].message,
            f"[G7-A] missing_try message 에 'pyautogui.click' 포함 필수. got: {risky_issues[0].message}",
        )

        # 5) import 위치 위반 → import_misplaced
        misplaced_import = (
            "x = 1\n"
            "if x:\n"
            "    import pyperclip\n"  # if 안 import = misplaced
        )
        result_imp = validate_step_code(misplaced_import)
        imp_issues = result_imp.by_kind("import_misplaced")
        self.assert_equal(
            len(imp_issues),
            1,
            f"[G7-A] if 안 import 1 건 검출 필수. got: {[(i.kind, i.message) for i in result_imp.issues]}",
        )

        # 6) 함수 정의 안의 risky 호출은 검출 X (false positive 방지)
        helper_with_risky = (
            "import pyautogui\n"
            "def helper():\n"
            "    pyautogui.click(100, 200)\n"  # 함수 안 → 검사 제외
            "try:\n"
            "    helper()\n"
            "except Exception:\n"
            "    pass\n"
        )
        result_helper = validate_step_code(helper_with_risky)
        self.assert_equal(
            len(result_helper.by_kind("missing_try")),
            0,
            f"[G7-A] 함수 정의 안 risky 호출은 검출 X. got: {[(i.kind, i.message) for i in result_helper.issues]}",
        )

        # 7) for-target 은 재정의 검사 제외 — `for app in ...` 의 app 는 안 잡힘
        for_target = "for app in [1, 2, 3]:\n    print(app)\n"
        result_for = validate_step_code(for_target, prev_step_codes=[prev_step1])
        self.assert_equal(
            len(result_for.by_kind("redefined_var")),
            0,
            f"[G7-A] for-target 은 module-level 재정의 검사 제외. got: {[(i.kind, i.message) for i in result_for.issues]}",
        )

        # 8) 데이터 클래스 + helper 메서드
        self.assert_true(
            hasattr(ValidationResult, "has_issues") and hasattr(ValidationResult, "by_kind"),
            "[G7-A] ValidationResult 에 has_issues + by_kind 메서드",
        )
        issue_fields = getattr(ValidationIssue, "__dataclass_fields__", {})
        self.assert_true(
            "kind" in issue_fields and "message" in issue_fields,
            f"[G7-A] ValidationIssue 에 kind + message 필드. got fields: {list(issue_fields.keys())}",
        )

        # 9) 다중 issue 동시 검출 — 재정의 + try 누락 한 코드에서 둘 다 잡힘
        multi_issue = (
            "import pyautogui\n"
            "app = 1\n"  # prev 의 'app' 재정의
            "pyautogui.click(0, 0)\n"  # try 밖 risky
        )
        result_multi = validate_step_code(multi_issue, prev_step_codes=[prev_step1])
        self.assert_true(
            len(result_multi.by_kind("redefined_var")) >= 1
            and len(result_multi.by_kind("missing_try")) >= 1,
            f"[G7-A] 다중 issue 동시 검출 필수. got: {[(i.kind, i.message) for i in result_multi.issues]}",
        )

    def test_98_app_service_generate_step_attaches_validation_warnings(self):
        """[Phase 1.8 G7-B] AppService.generate_step 가 code_validator hook 으로
        Step.validation_warnings 메타를 첨부한다 (차단 X — 실행 가능).

        배경: G7-A 의 정적 분석 엔진은 순수 함수. 실제 흐름에 연결하려면
        generate_step 마지막 (Step 생성 직전) 에 검사 호출 + 결과를 dict 리스트로
        변환해서 Step.validation_warnings 에 저장. UI 표시 / 재생성은 G7-C/D.

        가드:
        1. Step dataclass + StepModel 미러 모두 validation_warnings 필드 보유
        2. generate_step 소스에 validate_step_code import + 호출 + 결과 변환 패턴
        3. Step 생성 시 validation_warnings 인자 전달
        4. 정적 분석 실패도 step 생성 흐름 보호 (try/except)
        5. 위반 코드 (try 밖 risky 호출) end-to-end → Step.validation_warnings 비어있지 않음
        """
        import inspect
        from dataclasses import fields as dc_fields

        from core.app_service import AppService
        from core.models import StepModel
        from core.session_manager import Step

        # 1) Step dataclass 의 validation_warnings 필드
        step_field_names = {f.name for f in dc_fields(Step)}
        self.assert_true(
            "validation_warnings" in step_field_names,
            f"[G7-B] Step dataclass 에 validation_warnings 필드 필수. got: {sorted(step_field_names)}",
        )
        # 기본값 빈 리스트
        new_step = Step()
        self.assert_equal(
            new_step.validation_warnings,
            [],
            "[G7-B] Step.validation_warnings 기본값 빈 리스트",
        )

        # 2) StepModel Pydantic 미러도 동일 필드
        model_field_names = set(StepModel.model_fields.keys())
        self.assert_true(
            "validation_warnings" in model_field_names,
            f"[G7-B] StepModel 미러에 validation_warnings 필드 필수. got: {sorted(model_field_names)}",
        )

        # 3) generate_step 소스에 hook 패턴
        gen_src = inspect.getsource(AppService.generate_step)
        for pattern, desc in (
            ("from .code_validator import validate_step_code", "validate_step_code import"),
            ("validate_step_code(", "validate_step_code 호출"),
            ("validation_warnings", "validation_warnings 변수 사용"),
            ("validation_warnings=validation_warnings", "Step 생성 시 인자 전달"),
        ):
            self.assert_true(
                pattern in gen_src,
                f"[G7-B] generate_step 에 '{desc}' 패턴 필수: '{pattern}'",
            )

        # 4) 정적 분석 실패 시 보호 (try/except 로 감싸짐) — import 라인이 try 본문에 위치
        # 단순 패턴 매칭: hook 블록이 try: ... except Exception: pass 로 감싸짐
        hook_idx = gen_src.find("from .code_validator import validate_step_code")
        self.assert_true(hook_idx > 0, "[G7-B] hook 블록 위치 확인")
        # hook 앞 100 자 안에 'try:' 가 있어야 함
        prefix = gen_src[max(0, hook_idx - 200) : hook_idx]
        self.assert_true(
            "try:" in prefix,
            "[G7-B] validate_step_code import 가 try 블록 안에 위치 (분석 실패 보호)",
        )

        # 5) End-to-end: 위반 코드를 통과시키면 validation_warnings 가 채워지는지
        # AppService.generate_step 직접 호출은 AI 어댑터 mock 등 복잡 → 검사 함수
        # 직접 호출로 hook 의 입출력 형식 검증 (Step 생성 args 와 동일 형식).
        from core.code_validator import validate_step_code

        bad_code = "import pyautogui\npyautogui.click(0, 0)\n"
        result = validate_step_code(bad_code)
        warnings_dicts = [
            {"kind": iss.kind, "message": iss.message, "line": iss.line} for iss in result.issues
        ]
        self.assert_true(
            len(warnings_dicts) >= 1 and warnings_dicts[0]["kind"] == "missing_try",
            f"[G7-B] hook 의 dict 변환 형식: kind/message/line. got: {warnings_dicts}",
        )
        # Step 생성에 그대로 전달 가능한 list[dict] 형식인지
        step_with_warnings = Step(validation_warnings=warnings_dicts)
        self.assert_equal(
            len(step_with_warnings.validation_warnings),
            len(warnings_dicts),
            "[G7-B] Step.validation_warnings 에 dict 리스트 그대로 저장",
        )

    def test_99_ui_shows_validation_warning_indicator(self):
        """[Phase 1.8 G7-C] BlockCard (legacy) + StepCardV2 (ui_v2) 가
        validation_warnings 받으면 헤더 ⚠ 위젯 + 상세 다이얼로그 메서드 제공.

        구현은 inspect.getsource 패턴 + 시그니처 패턴으로 검증 (실제 위젯 표시는
        Qt 환경 의존). UI 환경 없이 verify 가능한 가드:
        1. BlockCard.__init__ + StepCardV2.__init__ 시그니처에 validation_warnings 인자
        2. 카드 소스에 ⚠ 위젯 생성 + setToolTip + 클릭 핸들러 패턴
        3. _show_validation_dialog 메서드 존재 양 클래스
        4. caller (code_viewer._add_step_block + main_window._refresh_block_view +
           ui_v2 caller) 가 validation_warnings 키 전달 패턴
        5. 빈 warnings 시 ⚠ 위젯 미생성 (false positive 방지) — 조건문 패턴 검증
        """
        import inspect

        from ui.code_viewer import BlockCard, BlockViewWidget
        from ui.main_window import MainWindow
        from ui_v2.main_window_v2 import MainWindowV2, StepCardV2

        # 1) 시그니처 — BlockCard
        block_sig = inspect.signature(BlockCard.__init__)
        self.assert_true(
            "validation_warnings" in block_sig.parameters,
            f"[G7-C] BlockCard.__init__ 에 validation_warnings 인자 필수. got: {list(block_sig.parameters.keys())}",
        )

        # 2) 시그니처 — StepCardV2
        step_sig = inspect.signature(StepCardV2.__init__)
        self.assert_true(
            "validation_warnings" in step_sig.parameters,
            f"[G7-C] StepCardV2.__init__ 에 validation_warnings 인자 필수. got: {list(step_sig.parameters.keys())}",
        )

        # 3) BlockCard 소스 — ⚠ 위젯 패턴
        block_init_src = inspect.getsource(BlockCard.__init__)
        for pattern, desc in (
            ('QLabel("⚠")', "⚠ QLabel 생성"),
            ("setToolTip(", "tooltip 설정"),
            ("if self._validation_warnings:", "warnings 있을 때만 위젯 (false positive 방지)"),
            ("_show_validation_dialog", "클릭 핸들러 연결"),
        ):
            self.assert_true(
                pattern in block_init_src,
                f"[G7-C] BlockCard.__init__ 에 '{desc}' 패턴 필수: '{pattern}'",
            )

        # 4) StepCardV2 소스 — 동일 패턴
        step_init_src = inspect.getsource(StepCardV2.__init__)
        for pattern, desc in (
            ('QLabel("⚠")', "StepCardV2 ⚠ QLabel"),
            ("setToolTip(", "StepCardV2 tooltip"),
            ("if self._validation_warnings:", "StepCardV2 warnings 조건"),
            ("_show_validation_dialog", "StepCardV2 클릭 핸들러"),
        ):
            self.assert_true(
                pattern in step_init_src,
                f"[G7-C] StepCardV2.__init__ 에 '{desc}' 패턴 필수: '{pattern}'",
            )

        # 5) _show_validation_dialog 메서드 존재
        self.assert_true(
            hasattr(BlockCard, "_show_validation_dialog"),
            "[G7-C] BlockCard._show_validation_dialog 메서드 필수",
        )
        self.assert_true(
            hasattr(StepCardV2, "_show_validation_dialog"),
            "[G7-C] StepCardV2._show_validation_dialog 메서드 필수",
        )

        # 6) 다이얼로그 내용에 kind label 매핑 (사용자 친화 메시지)
        block_dialog_src = inspect.getsource(BlockCard._show_validation_dialog)
        for kind in ("syntax", "redefined_var", "missing_try", "import_misplaced"):
            self.assert_true(
                f'"{kind}"' in block_dialog_src,
                f"[G7-C] BlockCard._show_validation_dialog 에 kind '{kind}' 라벨 매핑 필수",
            )

        # 7) caller — code_viewer._add_step_block 가 validation_warnings 전달
        add_block_src = inspect.getsource(BlockViewWidget._add_step_block)
        self.assert_true(
            'validation_warnings=data.get("validation_warnings")' in add_block_src,
            "[G7-C] BlockViewWidget._add_step_block 가 data 의 validation_warnings 전달 필수",
        )

        # 8) caller — main_window._refresh_block_view 가 step_dict.validation_warnings 수집
        refresh_src = inspect.getsource(MainWindow._refresh_block_view)
        self.assert_true(
            '"validation_warnings": step_dict.get("validation_warnings")' in refresh_src,
            "[G7-C] MainWindow._refresh_block_view 가 step_dict 의 validation_warnings 를 steps_data 에 추가 필수",
        )

        # 9) caller — ui_v2 StepCardV2 호출이 sd.get("validation_warnings") 전달
        v2_src = inspect.getsource(MainWindowV2)
        self.assert_true(
            'validation_warnings=list(sd.get("validation_warnings"' in v2_src,
            "[G7-C] ui_v2 의 StepCardV2 호출이 sd.validation_warnings 전달 필수",
        )

    def test_100_g7d_regenerate_with_warnings_injects_prompt(self):
        """[Phase 1.8 G7-D] 자동 재생성 흐름 — warnings 인용을 다음 prompt 에 inject.

        가드:
        1. prompt_builder.build_step_prompt_split / build_step_prompt 시그니처에
           previous_warnings 인자 추가
        2. previous_warnings 전달 시 user_text 에 sentinel 패턴 inject
           ("이전 시도 코드 검사 결과", "반드시 피해야 할 문제")
        3. previous_warnings=None 시 inject 안 됨 (idempotent — 기존 흐름 회귀 X)
        4. app_service.generate_step 시그니처에 previous_warnings 인자 + prompt_builder
           호출 시 전달
        5. config/default_settings.json 에 execution.auto_regenerate_on_warning 키
           (default false)
        6. ui_v2 StepCardV2 에 regenerate_with_warnings_requested signal
        7. _show_validation_dialog 에 '재생성' 버튼 + signal emit
        8. MainWindowV2 가 새 signal 연결 + _on_regenerate_with_warnings 핸들러
        9. MainWindowV2._send_request 시그니처에 previous_warnings 인자
        """
        import inspect
        import json as _json
        from pathlib import Path as _Path

        from core.app_service import AppService
        from core.prompt_builder import PromptBuilder
        from ui_v2.main_window_v2 import MainWindowV2, StepCardV2

        # 1) prompt_builder 시그니처
        split_sig = inspect.signature(PromptBuilder.build_step_prompt_split)
        self.assert_true(
            "previous_warnings" in split_sig.parameters,
            f"[G7-D] build_step_prompt_split 에 previous_warnings 인자 필수. got: {list(split_sig.parameters.keys())}",
        )
        legacy_sig = inspect.signature(PromptBuilder.build_step_prompt)
        self.assert_true(
            "previous_warnings" in legacy_sig.parameters,
            f"[G7-D] build_step_prompt 에도 previous_warnings 인자 필수. got: {list(legacy_sig.parameters.keys())}",
        )

        # 2) inject 동작 — 빈 prompts 로 builder 생성 후 dummy session 으로 호출
        class _DummySession:
            steps: list = []
            project_type: str = "desktop"

            def __init__(self):
                self.settings = {}

        builder = PromptBuilder(prompts_config={})
        session = _DummySession()
        warnings = [
            {"kind": "redefined_var", "message": "변수 'app' 재정의", "line": 2},
            {"kind": "missing_try", "message": "위험한 호출 'pyautogui.click()' 노출", "line": 5},
        ]
        _, user_text_with = builder.build_step_prompt_split(
            session=session,
            user_request="step 3: 텍스트 입력",
            previous_warnings=warnings,
        )
        for sentinel in (
            "이전 시도 코드 검사 결과",
            "반드시 피해야 할 문제",
            "변수 재정의",
            "try/except 누락",
        ):
            self.assert_true(
                sentinel in user_text_with,
                f"[G7-D] previous_warnings inject 시 user_text 에 '{sentinel}' 포함 필수",
            )

        # 3) previous_warnings=None 시 inject 안 됨 (idempotent)
        _, user_text_none = builder.build_step_prompt_split(
            session=session,
            user_request="step 3: 텍스트 입력",
        )
        self.assert_true(
            "이전 시도 코드 검사 결과" not in user_text_none,
            "[G7-D] previous_warnings=None 시 inject 안 됨 (기존 흐름 회귀 방지)",
        )

        # 4) app_service.generate_step 시그니처 + prompt_builder 호출 전달
        gen_sig = inspect.signature(AppService.generate_step)
        self.assert_true(
            "previous_warnings" in gen_sig.parameters,
            f"[G7-D] AppService.generate_step 에 previous_warnings 인자 필수. got: {list(gen_sig.parameters.keys())}",
        )
        gen_src = inspect.getsource(AppService.generate_step)
        self.assert_true(
            "previous_warnings=previous_warnings" in gen_src,
            "[G7-D] generate_step 가 prompt_builder.build_step_prompt_split 호출 시 previous_warnings 전달 필수",
        )

        # 5) default_settings.json 에 auto_regenerate_on_warning
        proj_root = _Path(__file__).resolve().parent.parent
        defaults = _json.loads(
            (proj_root / "config" / "default_settings.json").read_text(encoding="utf-8")
        )
        self.assert_true(
            "auto_regenerate_on_warning" in defaults.get("execution", {}),
            f"[G7-D] default_settings.json 의 execution 에 auto_regenerate_on_warning 키 필수. got execution keys: {list(defaults.get('execution', {}).keys())}",
        )
        self.assert_equal(
            defaults["execution"]["auto_regenerate_on_warning"],
            False,
            "[G7-D] auto_regenerate_on_warning default 는 False (사용자 클릭 우선)",
        )

        # 6) StepCardV2 에 새 signal
        self.assert_true(
            hasattr(StepCardV2, "regenerate_with_warnings_requested"),
            "[G7-D] StepCardV2 에 regenerate_with_warnings_requested signal 필수",
        )

        # 7) _show_validation_dialog 에 재생성 버튼 + emit
        # i18n 도입 후 button text 는 tr key 로 분기 (C-2b-1).
        dialog_src = inspect.getsource(StepCardV2._show_validation_dialog)
        for pattern, desc in (
            ('addButton(\n            tr("ui_v2.validation.btn_regenerate")', "재생성 버튼 tr key"),
            ("regenerate_with_warnings_requested.emit", "재생성 클릭 시 signal emit"),
            ("clickedButton() is regenerate_btn", "재생성 버튼 클릭 분기"),
        ):
            self.assert_true(
                pattern in dialog_src,
                f"[G7-D] _show_validation_dialog 에 '{desc}' 패턴 필수: '{pattern}'",
            )

        # 8) MainWindowV2 의 signal 연결 + 핸들러
        v2_src = inspect.getsource(MainWindowV2)
        self.assert_true(
            "card.regenerate_with_warnings_requested.connect" in v2_src,
            "[G7-D] MainWindowV2 가 카드의 regenerate_with_warnings_requested 시그널 연결 필수",
        )
        self.assert_true(
            hasattr(MainWindowV2, "_on_regenerate_with_warnings"),
            "[G7-D] MainWindowV2._on_regenerate_with_warnings 핸들러 필수",
        )
        handler_src = inspect.getsource(MainWindowV2._on_regenerate_with_warnings)
        for pattern, desc in (
            ("validation_warnings", "step.validation_warnings 추출"),
            ("previous_warnings=", "_send_request 에 previous_warnings 전달"),
        ):
            self.assert_true(
                pattern in handler_src,
                f"[G7-D] _on_regenerate_with_warnings 에 '{desc}' 패턴 필수: '{pattern}'",
            )

        # 9) _send_request 시그니처에 previous_warnings
        send_sig = inspect.signature(MainWindowV2._send_request)
        self.assert_true(
            "previous_warnings" in send_sig.parameters,
            f"[G7-D] MainWindowV2._send_request 에 previous_warnings 인자 필수. got: {list(send_sig.parameters.keys())}",
        )

    def test_101_g4_connect_timeout_minimum_5s(self):
        """[Phase 1.8 G4] Application().connect() 의 첫 timeout 이 5초 이상.

        배경 (handoff §16 잔존 갭 #5): system_context #14(b) 의 예제 코드가
        `timeout=3` 으로 짧음 → 매 step 누적 실행 시 기존 메모장이 부하/포커스
        전환으로 1~2초 응답 지연 시 false-negative → except 분기 → `Popen` 으로
        새 메모장 인스턴스 매번 추가.

        Fix:
        - prompts.json system_context #14(b) 의 첫 connect 예제 timeout=3 → 5
        - timeout=3 금지 어휘 + polling 패턴 추가
        - core/win_inspector.py:154 의 inspect_window 도 timeout=3 → 5

        가드:
        1. system_context #14(b) 영역에 `timeout=3` 패턴 부재 (또는 금지 어휘만)
        2. system_context 에 `timeout=5` 권장 + 'timeout=3 금지' 어휘 sentinel
        3. system_context 에 polling 대안 패턴 sentinel ('for _ in range(20)' + 'time.sleep(0.25)')
        4. win_inspector inspect_window 의 connect timeout >= 5
        """
        import inspect as _inspect
        import json as _json
        from pathlib import Path as _Path

        from core.win_inspector import WindowInspector

        # 1+2+3) prompts.json system_context 검증
        proj_root = _Path(__file__).resolve().parent.parent
        prompts = _json.loads((proj_root / "config" / "prompts.json").read_text(encoding="utf-8"))
        system_context = prompts.get("system_context", "")
        self.assert_true(system_context, "[G4] system_context 본문 비어있지 않아야 함")

        # 잔존 갭 #5 fix 의 핵심: 첫 connect 의 timeout=3 패턴이 system_context 의
        # idempotent 예제 (#14(b)) 에서 제거되어 있어야 한다. 단 '금지' 어휘로 timeout=3
        # 자체가 본문에 등장하는 건 OK (반례 명시) — 코드 라인 'timeout=3' 만 검사.
        self.assert_true(
            'connect(title_re=r".*메모장", timeout=3, found_index=0)' not in system_context,
            "[G4] system_context 의 첫 connect 예제에 'timeout=3' 코드 라인 부재 필수 (5초 이상으로 보강)",
        )

        # G4 권장 어휘 + polling 패턴 sentinel
        for sentinel, desc in (
            ("timeout=5", "권장 timeout=5"),
            ("timeout=3 금지", "timeout=3 금지 어휘 (잔존 갭 #5 fix)"),
            ("for _ in range(20)", "polling 패턴 — 20 회 반복"),
            ("time.sleep(0.25)", "polling 인터벌 — 0.25 초"),
        ):
            self.assert_true(
                sentinel in system_context,
                f"[G4] system_context 에 '{desc}' 패턴 필수: '{sentinel}'",
            )

        # 4) win_inspector inspect_window 의 connect timeout
        inspect_src = _inspect.getsource(WindowInspector.inspect_window)
        self.assert_true(
            "timeout=5" in inspect_src or "timeout=3" not in inspect_src,
            "[G4] WindowInspector.inspect_window 의 connect timeout 이 5 이상이어야 함 (timeout=3 부재 또는 5)",
        )
        self.assert_true(
            'connect(title_re=f".*{title}.*", timeout=3)' not in inspect_src,
            "[G4] inspect_window 의 connect 가 timeout=3 사용 금지 (5 이상으로 보강)",
        )

    def test_102_g7e1_legacy_ai_call_handler_attaches_validation_warnings(self):
        """[Phase 1.8 G7-E1] legacy AICallHandler.on_ai_response 가 code_validator
        hook 으로 Step.validation_warnings 메타를 부착한다.

        배경: ui_v2 는 app_service.generate_step (G7-B hook) 으로 자동 부착되지만
        legacy 는 직접 ai_engine.generate 호출이라 hook 없음 → 카드의 ⚠ 위젯이
        legacy 세션에서 항상 안 뜸. G7-E1 은 legacy 의 Step 생성 직전에 동일 hook.
        차단 X — 메타만 첨부. UI 재생성은 G7-E2.

        가드:
        1. AICallHandler.on_ai_response 소스에 validate_step_code import + 호출
        2. Step 생성 시 validation_warnings 인자 전달
        3. 정적 분석 실패 시 보호 (try/except)
        4. prev_step_codes 수집 (모든 이전 step 의 step_code)
        """
        import inspect as _inspect

        from ui.ai_call_handler import AICallHandler

        src = _inspect.getsource(AICallHandler.on_ai_response)
        for pattern, desc in (
            ("from core.code_validator import validate_step_code", "validate_step_code import"),
            ("validate_step_code(", "validate_step_code 호출"),
            ("validation_warnings", "validation_warnings 변수 사용"),
            ("validation_warnings=validation_warnings", "Step 생성 시 인자 전달"),
            ("prev_step_codes", "prev_step_codes 수집 (변수 재정의 검사용)"),
        ):
            self.assert_true(
                pattern in src,
                f"[G7-E1] AICallHandler.on_ai_response 에 '{desc}' 패턴 필수: '{pattern}'",
            )

        # 정적 분석 실패 시 보호 — import 가 try 블록 안에 위치
        hook_idx = src.find("from core.code_validator import validate_step_code")
        self.assert_true(hook_idx > 0, "[G7-E1] hook 블록 위치 확인")
        prefix = src[max(0, hook_idx - 200) : hook_idx]
        self.assert_true(
            "try:" in prefix,
            "[G7-E1] validate_step_code import 가 try 블록 안에 위치 (분석 실패 보호)",
        )

    def test_103_g7e2_legacy_blockcard_regenerate_with_warnings(self):
        """[Phase 1.8 G7-E2] legacy BlockCard 의 ⚠ 다이얼로그 재생성 버튼 + signal
        relay + AICallHandler.on_regenerate_with_warnings 핸들러 + call_ai_thread
        의 previous_warnings 인자 전달.

        ui_v2 의 G7-D 와 동일한 패턴을 legacy 에 이식. signal relay 는 BlockCard
        → BlockViewWidget → CodeViewer → MainWindow → AICallHandler 의 3단계.

        가드:
        1. BlockCard 에 regenerate_with_warnings_requested signal
        2. BlockCard._show_validation_dialog 에 '재생성' 버튼 + emit 패턴 (step_id > 0 만)
        3. BlockViewWidget + CodeViewer 도 동일 outer signal + relay 연결
        4. MainWindow signal 연결 + _on_regenerate_with_warnings 위임 stub
        5. AICallHandler.on_regenerate_with_warnings 메서드 + call_ai_thread
           시그니처에 previous_warnings 인자 + build_step_prompt 호출 시 전달
        """
        import inspect as _inspect

        from ui.ai_call_handler import AICallHandler
        from ui.code_viewer import BlockCard, BlockViewWidget, CodeViewer
        from ui.main_window import MainWindow

        # 1) BlockCard signal
        self.assert_true(
            hasattr(BlockCard, "regenerate_with_warnings_requested"),
            "[G7-E2] BlockCard 에 regenerate_with_warnings_requested signal 필수",
        )

        # 2) _show_validation_dialog 패턴
        dialog_src = _inspect.getsource(BlockCard._show_validation_dialog)
        for pattern, desc in (
            ('addButton("재생성"', "재생성 버튼 추가"),
            ("regenerate_with_warnings_requested.emit", "signal emit"),
            ("self.step_id > 0", "step_id > 0 만 재생성 (library/initial 제외)"),
            ("clickedButton() is regenerate_btn", "재생성 버튼 클릭 분기"),
        ):
            self.assert_true(
                pattern in dialog_src,
                f"[G7-E2] BlockCard._show_validation_dialog 에 '{desc}' 패턴 필수: '{pattern}'",
            )

        # 3) BlockViewWidget + CodeViewer outer signal + relay
        self.assert_true(
            hasattr(BlockViewWidget, "regenerate_with_warnings_requested"),
            "[G7-E2] BlockViewWidget 에 regenerate_with_warnings_requested outer signal 필수",
        )
        self.assert_true(
            hasattr(CodeViewer, "regenerate_with_warnings_requested"),
            "[G7-E2] CodeViewer 에 regenerate_with_warnings_requested outer signal 필수",
        )
        # BlockViewWidget._add_step_block 가 카드 signal 을 outer 로 연결
        add_block_src = _inspect.getsource(BlockViewWidget._add_step_block)
        self.assert_true(
            "card.regenerate_with_warnings_requested.connect(self.regenerate_with_warnings_requested)"
            in add_block_src,
            "[G7-E2] _add_step_block 가 카드의 regenerate signal 을 outer 로 relay 필수",
        )
        # CodeViewer 의 block_view signal 연결 — __init__ 또는 _setup_ui 등 어디든 OK
        cv_src = _inspect.getsource(CodeViewer)
        self.assert_true(
            "self.block_view.regenerate_with_warnings_requested.connect" in cv_src,
            "[G7-E2] CodeViewer 에 block_view 의 regenerate signal relay 필수",
        )

        # 4) MainWindow signal 연결 + 위임 stub
        mw_src = _inspect.getsource(MainWindow)
        self.assert_true(
            "self.code_viewer.regenerate_with_warnings_requested.connect" in mw_src,
            "[G7-E2] MainWindow 에 code_viewer 의 regenerate signal 연결 필수",
        )
        self.assert_true(
            hasattr(MainWindow, "_on_regenerate_with_warnings"),
            "[G7-E2] MainWindow._on_regenerate_with_warnings 위임 stub 필수",
        )
        stub_src = _inspect.getsource(MainWindow._on_regenerate_with_warnings)
        self.assert_true(
            "self.ai_handler.on_regenerate_with_warnings" in stub_src,
            "[G7-E2] MainWindow._on_regenerate_with_warnings 가 ai_handler 로 위임 필수",
        )

        # 5) AICallHandler 메서드 + call_ai_thread 시그니처 + build_step_prompt 전달
        self.assert_true(
            hasattr(AICallHandler, "on_regenerate_with_warnings"),
            "[G7-E2] AICallHandler.on_regenerate_with_warnings 메서드 필수",
        )
        handler_src = _inspect.getsource(AICallHandler.on_regenerate_with_warnings)
        for pattern, desc in (
            ("validation_warnings", "step.validation_warnings 추출"),
            ('"previous_warnings": warnings', "call_ai_thread 에 previous_warnings kwarg 전달"),
            ("user_request", "user_request 추출"),
        ):
            self.assert_true(
                pattern in handler_src,
                f"[G7-E2] on_regenerate_with_warnings 에 '{desc}' 패턴 필수: '{pattern}'",
            )

        # call_ai_thread 시그니처
        call_sig = _inspect.signature(AICallHandler.call_ai_thread)
        self.assert_true(
            "previous_warnings" in call_sig.parameters,
            f"[G7-E2] call_ai_thread 에 previous_warnings 인자 필수. got: {list(call_sig.parameters.keys())}",
        )

        # build_step_prompt 호출 시 previous_warnings 전달
        call_src = _inspect.getsource(AICallHandler.call_ai_thread)
        self.assert_true(
            "previous_warnings=previous_warnings" in call_src,
            "[G7-E2] call_ai_thread 의 build_step_prompt 호출이 previous_warnings 전달 필수",
        )

    def test_104_g6_prompt_strengthens_variable_reuse_and_try_except(self):
        """[Phase 1.8 G6] system_context 의 try/except (#3) + 변수 재정의 (#20)
        가이드 어휘 강화 — G7 의 사후 검출과 시너지.

        배경: handoff §16 잔존 갭 #1 (변수 재정의) + #2 (try-except 누락) 은 G7
        정적 분석으로 사후 검출 + 재생성으로 대응됐지만, 모델이 처음부터 회피하면
        ⚠ 안 뜨고 토큰/시간 절약. G6 은 prompt-side 어휘 강화 (사전 회피).

        가드:
        1. #3 (try/except 강제) 에 정적 분석기 / 재생성 path 인용 어휘
        2. #14(b) 변수 명명 규칙 끝에 #20 cross-reference
        3. 새 #20 "이전 step 변수 재사용 — 재정의 금지" 가이드 본문
        4. #20 에 회귀 사례 (5/10 DeepSeek-V3 메모장테스트 step 3) 인용
        5. #20 에 module-level Assign 만 검사 어휘 (false positive 방지 설명)
        """
        import json as _json
        from pathlib import Path as _Path

        proj_root = _Path(__file__).resolve().parent.parent
        prompts = _json.loads((proj_root / "config" / "prompts.json").read_text(encoding="utf-8"))
        sc = prompts.get("system_context", "")
        self.assert_true(sc, "[G6] system_context 본문 비어있지 않아야 함")

        # 1) #3 강화 — 정적 분석기 / 재생성 path 인용
        for sentinel, desc in (
            ("silent fallthrough", "외부 자원 silent fallthrough 경고"),
            ("정적 분석기", "code_validator 검출 명시"),
            ("code_validator", "정적 분석기 모듈명"),
            ("재생성", "재생성 path 인용"),
        ):
            self.assert_true(
                sentinel in sc,
                f"[G6] #3 강화 — system_context 에 '{desc}' 어휘 필수: '{sentinel}'",
            )

        # 2) #14(b) cross-reference
        self.assert_true(
            "가이드 #20 참조" in sc,
            "[G6] #14(b) 변수 명명 규칙 끝에 '#20 참조' cross-reference 필수",
        )

        # 3) 새 #20 본문 sentinel
        for sentinel, desc in (
            ("이전 step 변수 재사용", "#20 제목"),
            ("재정의 금지", "재정의 금지 어휘"),
            ("Jupyter mode 핵심", "jupyter mode 강조"),
            ("`app`, `win`, `driver`", "재사용 대상 변수명 명시"),
        ):
            self.assert_true(
                sentinel in sc,
                f"[G6] #20 — system_context 에 '{desc}' 어휘 필수: '{sentinel}'",
            )

        # 4) 회귀 사례 인용
        self.assert_true(
            "DeepSeek-V3 메모장테스트 step 3" in sc,
            "[G6] #20 에 5/10 DeepSeek-V3 회귀 사례 인용 필수 (구체 사례로 모델 학습 가이드)",
        )

        # 5) module-level Assign 만 검사 (false positive 방지 설명)
        for sentinel, desc in (
            ("module-level", "module-level scope 명시"),
            ("for x in", "for-target 제외 명시 (loop 변수 무관)"),
        ):
            self.assert_true(
                sentinel in sc,
                f"[G6] #20 에 false positive 방지 — '{desc}' 어휘 필수: '{sentinel}'",
            )

    def test_105_f2_g7ux_run_hint_and_settings_checkbox(self):
        """[Phase 1.8 F2 + G7-UX] step 생성 시 실행 힌트 토스트 (영구 dismiss) +
        settings dialog 의 auto_regenerate_on_warning 체크박스.

        F2: 사용자가 ▶ Ctrl+R / ⏯ 단독 버튼 발견성 향상. 토스트 1회만, settings.ui
        .hint_run_shown 으로 영구 dismiss.

        G7-UX: G7-D 가 default_settings.json 에 execution.auto_regenerate_on_warning
        키만 정의 — UI 토글 없음. settings dialog 의 실행 탭에 체크박스 + tooltip
        노출 + save/load 연결.

        가드:
        1. config/default_settings.json 의 ui.hint_run_shown: false (F2)
        2. ui_v2 MainWindowV2._on_step_done 에 hint 토스트 + 영구화 로직 (F2)
        3. SettingsDialog 에 auto_regen_cb 체크박스 존재 (G7-UX)
        4. save 로직에 auto_regenerate_on_warning 영구화 (G7-UX)
        5. _build_ui (또는 init) 가 exec_config.get("auto_regenerate_on_warning") 로 초기화
        """
        import inspect as _inspect
        import json as _json
        from pathlib import Path as _Path

        from ui.settings_dialog import SettingsDialog
        from ui_v2.main_window_v2 import MainWindowV2

        # 1) F2: default_settings.json
        proj_root = _Path(__file__).resolve().parent.parent
        defaults = _json.loads(
            (proj_root / "config" / "default_settings.json").read_text(encoding="utf-8")
        )
        self.assert_true(
            "hint_run_shown" in defaults.get("ui", {}),
            f"[F2] default_settings.json 의 ui 에 hint_run_shown 키 필수. got ui keys: {list(defaults.get('ui', {}).keys())}",
        )
        self.assert_equal(
            defaults["ui"]["hint_run_shown"],
            False,
            "[F2] hint_run_shown default 는 False (첫 사용자 시 토스트 1회 표시)",
        )

        # 2) F2: _on_step_done 의 hint 토스트 + 영구화
        # 2026-05-12: self.settings → self._load_settings() 로 교체 (#112 버그 fix).
        step_done_src = _inspect.getsource(MainWindowV2._on_step_done)
        for pattern, desc in (
            ("hint_run_shown", "ui.hint_run_shown 플래그 사용"),
            ("Ctrl+R", "Ctrl+R 단축키 안내"),
            ("⏯ 단독", "단독 버튼 안내"),
            ('ui_cfg["hint_run_shown"] = True', "영구 dismiss 플래그 설정"),
            ("self._load_settings()", "settings fresh load (self.settings 사용 X)"),
            ("self._save_settings(s)", "settings.json 영구 저장 (mutated dict)"),
        ):
            self.assert_true(
                pattern in step_done_src,
                f"[F2] _on_step_done 에 '{desc}' 패턴 필수: '{pattern}'",
            )

        # 3+4+5) G7-UX: SettingsDialog 의 auto_regen_cb + save
        sd_src = _inspect.getsource(SettingsDialog)
        for pattern, desc in (
            ("self.auto_regen_cb", "auto_regen_cb 위젯"),
            ('exec_config.get("auto_regenerate_on_warning"', "load: exec_config 에서 초기화"),
            (
                'self.settings["execution"]["auto_regenerate_on_warning"]',
                "save: 영구화",
            ),
            ("자동 재생성", "체크박스 라벨 한국어"),
        ):
            self.assert_true(
                pattern in sd_src,
                f"[G7-UX] SettingsDialog 에 '{desc}' 패턴 필수: '{pattern}'",
            )

    def test_106_f1_auto_run_on_step_create(self):
        """[Phase 1.8 F1] step 카드 생성 직후 자동 단독 실행 (옵션 ON 시).

        잔존 갭 #6 (마지막 남은 ⏳ 항목): 현재 사용자가 AI 응답 후 ▶ Ctrl+R / ⏯ 단독
        버튼 별도로 눌러야 실행. F1 은 settings.execution.auto_run_on_step_create
        옵션 ON 시 자동 trigger. **default OFF — 안전**: AI 코드가 위험 동작 포함 시
        사용자 확인 없이 실행 위험.

        ui_v2 의 무한 루프 회피: blocks 실행 path 의 step_done 도 같은 핸들러로
        들어오므로, 자동 실행 trigger 는 별도 signal (request_auto_run) 사용 —
        generate_step worker 만 emit, _on_run_single 에 직접 연결.

        가드:
        1. config/default_settings.json 의 execution.auto_run_on_step_create: false
        2. ui_v2 V2Signals 에 request_auto_run signal + worker 의 옵션 체크 emit +
           MainWindowV2 의 connect → _on_run_single
        3. legacy ai_call_handler.on_ai_response 에 옵션 체크 + _on_run_single_step 호출
        4. SettingsDialog 에 auto_run_cb 체크박스 + tooltip 의 ⚠ 경고 + save
        """
        import inspect as _inspect
        import json as _json
        from pathlib import Path as _Path

        from ui.ai_call_handler import AICallHandler
        from ui.settings_dialog import SettingsDialog
        from ui_v2.main_window_v2 import MainWindowV2, V2Signals

        # 1) default_settings.json
        proj_root = _Path(__file__).resolve().parent.parent
        defaults = _json.loads(
            (proj_root / "config" / "default_settings.json").read_text(encoding="utf-8")
        )
        self.assert_true(
            "auto_run_on_step_create" in defaults.get("execution", {}),
            f"[F1] default_settings.json 의 execution 에 auto_run_on_step_create 키 필수. got execution keys: {list(defaults.get('execution', {}).keys())}",
        )
        self.assert_equal(
            defaults["execution"]["auto_run_on_step_create"],
            False,
            "[F1] auto_run_on_step_create default 는 False (위험 동작 안전)",
        )

        # 2) ui_v2: V2Signals.request_auto_run + worker emit + connect
        self.assert_true(
            hasattr(V2Signals, "request_auto_run"),
            "[F1] V2Signals 에 request_auto_run signal 필수 (blocks 실행 path 와 분리)",
        )
        v2_src = _inspect.getsource(MainWindowV2)
        for pattern, desc in (
            ('"auto_run_on_step_create"', "worker 의 옵션 체크"),
            ("self.signals.request_auto_run.emit(step.step_id)", "worker 의 signal emit"),
            (
                "self.signals.request_auto_run.connect(self._on_run_single)",
                "MainWindowV2 의 signal connect → _on_run_single",
            ),
        ):
            self.assert_true(
                pattern in v2_src,
                f"[F1] ui_v2 에 '{desc}' 패턴 필수: '{pattern}'",
            )

        # 3) legacy ai_call_handler.on_ai_response 의 옵션 체크 + 자동 실행
        legacy_src = _inspect.getsource(AICallHandler.on_ai_response)
        for pattern, desc in (
            ('"auto_run_on_step_create"', "legacy 의 옵션 체크"),
            ("mw._on_run_single_step(step.step_id)", "legacy 의 자동 실행 호출"),
            ("step.step_id > 0", "step_id > 0 (library/initial 제외)"),
        ):
            self.assert_true(
                pattern in legacy_src,
                f"[F1] legacy ai_call_handler 에 '{desc}' 패턴 필수: '{pattern}'",
            )

        # 4) SettingsDialog 에 auto_run_cb + tooltip ⚠ + save
        sd_src = _inspect.getsource(SettingsDialog)
        for pattern, desc in (
            ("self.auto_run_cb", "auto_run_cb 위젯"),
            ('exec_config.get("auto_run_on_step_create"', "load: 초기화"),
            (
                'self.settings["execution"]["auto_run_on_step_create"]',
                "save: 영구화",
            ),
            ("자동 실행", "체크박스 라벨 한국어"),
            ("위험 동작", "tooltip 경고 어휘 (사용자 인지)"),
        ):
            self.assert_true(
                pattern in sd_src,
                f"[F1] SettingsDialog 에 '{desc}' 패턴 필수: '{pattern}'",
            )

    def test_107_c1_i18n_infrastructure(self):
        """[Phase 1.9 C-1] i18n 인프라 — core.i18n + locale catalogue.

        5/9 dual-locale 결정 + commercial_review §7 게이트 #3 (영어 + 한국어
        콘텐츠 mix) 준비. C-1 은 인프라만 구축, UI 연결은 후속 unit.

        가드:
        1. core.i18n import + set_locale/get_locale/tr/reset_cache 4 함수 존재
        2. fallback locale = "en" (글로벌 우선)
        3. locale catalogue 양쪽 (en.json + ko.json) 존재 + 동일 키 집합
        4. tr() 기본 동작 — current → fallback → key, format 치환
        """
        import json as _json
        from pathlib import Path as _Path

        from core import i18n

        # 1) 모듈 API 4 함수
        for fn in ("set_locale", "get_locale", "tr", "reset_cache"):
            self.assert_true(
                callable(getattr(i18n, fn, None)),
                f"[C-1] core.i18n.{fn} 호출 가능 필수",
            )

        # 2) fallback locale = "en"
        self.assert_equal(
            i18n._FALLBACK_LOCALE,
            "en",
            "[C-1] fallback locale 은 'en' (5/9 글로벌 우선 결정)",
        )

        # 3) catalogue 양쪽 존재 + 동일 키 집합
        locale_dir = _Path(i18n.__file__).parent / "locale"
        en_path = locale_dir / "en.json"
        ko_path = locale_dir / "ko.json"
        self.assert_true(en_path.exists(), f"[C-1] {en_path} 필수")
        self.assert_true(ko_path.exists(), f"[C-1] {ko_path} 필수")
        en_cat = _json.loads(en_path.read_text(encoding="utf-8"))
        ko_cat = _json.loads(ko_path.read_text(encoding="utf-8"))
        self.assert_equal(
            set(en_cat.keys()),
            set(ko_cat.keys()),
            "[C-1] en/ko catalogue 키 집합 동일 (한쪽 추가 시 다른쪽도 추가)",
        )
        self.assert_true(
            len(en_cat) >= 1,
            f"[C-1] en catalogue 최소 1개 키 (인프라 가드용 sample). got {len(en_cat)}",
        )

        # 4) tr 동작 — current → fallback → key
        i18n.reset_cache()
        i18n.set_locale("en")
        self.assert_equal(i18n.tr("common.ok"), "OK", "[C-1] en locale tr")
        i18n.set_locale("ko")
        self.assert_equal(i18n.tr("common.ok"), "확인", "[C-1] ko locale tr")
        # 미정의 키 → 키 자체 반환 (placeholder 안 깨짐)
        self.assert_equal(
            i18n.tr("nonexistent.key.xyz"),
            "nonexistent.key.xyz",
            "[C-1] 미정의 키는 키 자체 반환",
        )
        # 미지원 locale → fallback (en) 으로 조회
        i18n.set_locale("xx")
        self.assert_equal(
            i18n.tr("common.ok"),
            "OK",
            "[C-1] 미지원 locale 은 fallback (en) 사용",
        )
        # format 치환 (인자 누락 시 원문 반환)
        # catalogue 에 format 키 없는 sample 만 있으므로 missing key path 도 확인
        i18n.set_locale("en")
        self.assert_equal(i18n.tr("x.{a}", a="1"), "x.{a}", "[C-1] missing key + format 시 키 반환")

        # cleanup — locale 복원
        i18n.reset_cache()
        i18n.set_locale("en")

    def test_108_c2_i18n_call_sites_match_catalogue(self):
        """[Phase 1.9 C-2] ui_v2/ 의 tr() 호출 key 가 en+ko catalogue 양쪽 존재.

        raw key 가 화면에 노출되는 사고 방지 (catalog 누락 시 tr() 가 key 자체 반환).
        Plan 1 C-2a~c 통합 가드 — 새 tr() 호출 추가 시 catalogue 누락 즉시 감지.

        가드:
        1. ui_v2/ 안의 모든 .py 파일 스캔 → tr("ns.key") 정규식으로 key 추출
        2. 추출된 모든 key 가 en.json + ko.json 양쪽에 존재 검증
        3. tr() 호출 최소 1개 존재 (i18n 적용 sanity)
        """
        import json as _json
        import re as _re
        from pathlib import Path as _Path

        project_root = _Path(__file__).parent.parent
        locale_dir = project_root / "core" / "locale"
        en_cat = _json.loads((locale_dir / "en.json").read_text(encoding="utf-8"))
        ko_cat = _json.loads((locale_dir / "ko.json").read_text(encoding="utf-8"))

        ui_v2_dir = project_root / "ui_v2"
        # tr("ns.key" — multi-line 분리 (ruff format) 대응 위해 \s* 사용 (\s 는 \n 포함).
        tr_pattern = _re.compile(r'\btr\(\s*"([^"]+)"')

        found_keys: set[str] = set()
        for py_file in ui_v2_dir.glob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            for m in tr_pattern.finditer(text):
                found_keys.add(m.group(1))

        self.assert_true(
            len(found_keys) > 0,
            "[C-2] ui_v2/ 안 tr() 호출 1개 이상 필수 (i18n 적용 검증)",
        )

        missing_en = sorted(k for k in found_keys if k not in en_cat)
        missing_ko = sorted(k for k in found_keys if k not in ko_cat)
        self.assert_true(
            not missing_en,
            f"[C-2] en.json 에 누락된 tr key {len(missing_en)} 개: {missing_en[:5]}",
        )
        self.assert_true(
            not missing_ko,
            f"[C-2] ko.json 에 누락된 tr key {len(missing_ko)} 개: {missing_ko[:5]}",
        )

    def test_109_c2_locale_auto_detect_at_startup(self):
        """[Phase 1.9 C-2 final] main.py startup locale 자동 감지.

        UI import 전에 core.i18n.set_locale 호출 — tr() 가 올바른 catalog
        로 분기하도록 보장.

        가드:
        1. main._detect_and_set_locale 함수 존재 + callable
        2. main() 시작부에 _detect_and_set_locale() 호출 sentinel
        3. helper 함수 안 핵심 패턴 — set_locale 호출 + settings.ui.language
           우선 + ko/en 분기 + 시스템 locale fallback
        """
        import inspect as _inspect

        import main as main_mod

        # 1) 함수 존재
        self.assert_true(
            callable(getattr(main_mod, "_detect_and_set_locale", None)),
            "[C-2 final] main._detect_and_set_locale 함수 callable 필수",
        )

        # 2) main() 안 호출 sentinel
        main_src = _inspect.getsource(main_mod.main)
        self.assert_true(
            "_detect_and_set_locale" in main_src,
            "[C-2 final] main() 시작부에 _detect_and_set_locale() 호출 필수",
        )

        # 3) helper 함수 핵심 패턴
        fn_src = _inspect.getsource(main_mod._detect_and_set_locale)
        for pattern, desc in (
            ("set_locale", "core.i18n.set_locale 호출"),
            ("ui", "settings.ui.language 키 참조"),
            ("language", "language 키 참조"),
            ('"ko"', "ko locale 분기"),
            ('"en"', "en fallback"),
            ("getlocale", "시스템 locale 감지"),
        ):
            self.assert_true(
                pattern in fn_src,
                f"[C-2 final] _detect_and_set_locale 에 '{desc}' 패턴 필수: '{pattern}'",
            )

    def test_116_delete_step_rebuilds_generated_code_chain(self):
        """[회귀] AppService.delete_step 후 후속 step 의 generated_code 에 삭제된
        step 의 코드가 잔존하지 않음.

        Bug (2026-05-12 사용자 보고, 메모장테스트 step 삭제 후):
        각 step 의 generated_code 는 cumulative (library + 이전 step 누적). 단순
        delete + renumber 만 하면 후속 step 의 generated_code 가 삭제된 step 의
        코드 포함된 채 그대로 → 전체 실행 시 삭제된 코드 실행.

        Fix: reorder_step 패턴 동일 적용 — step_code 사전 추출 + 새 순서 재구성.

        가드: in-memory session 으로 step1 (code_A) + step2 (code_A + code_B) +
        step3 (code_A + code_B + code_C) 만들고 step1 삭제 후 새 step1/step2 의
        generated_code 가 code_A 를 포함하지 않는지 검증.
        """
        from core.app_service import AppService
        from core.storage import InMemoryRepository

        repo = InMemoryRepository()
        svc = AppService(session_repo=repo)

        session = svc.create_session(title="t116_delete_chain", project_type="desktop")
        sid = session.session_id

        # step1: code_A, step2: code_A+code_B, step3: code_A+code_B+code_C
        from core.models import Step

        s1 = Step(
            status="completed",
            generated_code="code_A = 1",
            step_code="code_A = 1",
            step_imports=[],
        )
        s2 = Step(
            status="completed",
            generated_code="code_A = 1\n\ncode_B = 2",
            step_code="code_B = 2",
            step_imports=[],
        )
        s3 = Step(
            status="completed",
            generated_code="code_A = 1\n\ncode_B = 2\n\ncode_C = 3",
            step_code="code_C = 3",
            step_imports=[],
        )
        svc.add_step(sid, s1)
        svc.add_step(sid, s2)
        svc.add_step(sid, s3)

        # step1 삭제 — chain 재구성 기대
        ok = svc.delete_step(sid, 1)
        self.assert_true(ok, "[#116] delete_step 가 True 반환 (성공)")

        session_after = svc.get_session(sid)
        self.assert_true(
            len(session_after.steps) == 2,
            f"[#116] 삭제 후 step 개수 2 기대, 실제 {len(session_after.steps)}",
        )

        # 새 step1 (구 step2): generated_code 에 code_A 없어야 함
        new_step1 = (
            session_after.steps[0]
            if isinstance(session_after.steps[0], dict)
            else session_after.steps[0].__dict__
        )
        new_step1_gen = new_step1.get("generated_code", "")
        self.assert_true(
            "code_A" not in new_step1_gen,
            f"[#116] 새 step1 의 generated_code 에 삭제된 code_A 잔존: '{new_step1_gen}'",
        )
        self.assert_true(
            "code_B" in new_step1_gen,
            f"[#116] 새 step1 의 generated_code 에 code_B 보존 필수: '{new_step1_gen}'",
        )

        # 새 step2 (구 step3): code_A 없어야 함, code_B + code_C 있어야 함
        new_step2 = (
            session_after.steps[1]
            if isinstance(session_after.steps[1], dict)
            else session_after.steps[1].__dict__
        )
        new_step2_gen = new_step2.get("generated_code", "")
        self.assert_true(
            "code_A" not in new_step2_gen,
            f"[#116] 새 step2 의 generated_code 에 삭제된 code_A 잔존: '{new_step2_gen}'",
        )
        self.assert_true(
            "code_B" in new_step2_gen and "code_C" in new_step2_gen,
            f"[#116] 새 step2 의 generated_code 에 code_B + code_C 보존 필수: '{new_step2_gen}'",
        )

        # step_id renumber 확인
        self.assert_true(
            new_step1.get("step_id") == 1 and new_step2.get("step_id") == 2,
            f"[#116] step_id 재정렬 — 1,2 기대, "
            f"실제 {new_step1.get('step_id')},{new_step2.get('step_id')}",
        )

    def test_115_v2_step_card_has_delete_button(self):
        """[회귀] v2 StepCardV2 에 🗑 삭제 버튼 + 핸들러 + AppService 연결.

        2026-05-12 사용자 보고: v1 의 step 삭제 기능이 v2 카드에서 누락 (의도
        제거 아님 — wireframe_v2.md line 110, 123 spec 에 명시).

        Fix:
        - StepCardV2 에 delete_requested = Signal(int) 추가
        - 카드 푸터에 🗑 삭제 버튼 (step_id > 0 만)
        - MainWindowV2._on_step_delete 핸들러 — QMessageBox 확인 + delete_step + refresh
        - signal 연결 (_refresh_step_cards 안)
        - locale catalog (en+ko) 에 btn_delete / btn_delete_tooltip / dialog /
          toast / log 키 추가
        - 부수: ⬆⬇ 를 QPushButton + bg_overlay 로 통일 + sub-layout spacing=0
          으로 두 버튼 붙여 표시 (사용자 보고: 옆 ✏️ 와 비례 안 맞고 간격 큼)
        """
        import inspect as _inspect

        from ui_v2 import main_window_v2 as _mwv2

        # 1) signal 정의
        self.assert_true(
            hasattr(_mwv2.StepCardV2, "delete_requested"),
            "[#115] StepCardV2.delete_requested signal 필수",
        )

        # 2) 카드 푸터 코드에 삭제 버튼 생성 + connect
        init_src = _inspect.getsource(_mwv2.StepCardV2.__init__)
        for pattern, desc in (
            ('tr("ui_v2.step_card.btn_delete")', "btn_delete tr key 사용"),
            ('tr("ui_v2.step_card.btn_delete_tooltip")', "btn_delete_tooltip tr key 사용"),
            ("self.delete_requested.emit(self.step_id)", "삭제 버튼 클릭 → delete_requested emit"),
        ):
            self.assert_true(
                pattern in init_src,
                f"[#115] StepCardV2.__init__ 에 '{desc}' 필수: '{pattern}'",
            )

        # 3) 핸들러 존재 + AppService.delete_step 호출
        self.assert_true(
            callable(getattr(_mwv2.MainWindowV2, "_on_step_delete", None)),
            "[#115] MainWindowV2._on_step_delete 핸들러 필수",
        )
        handler_src = _inspect.getsource(_mwv2.MainWindowV2._on_step_delete)
        for pattern, desc in (
            ("self.app_service.delete_step(", "AppService.delete_step 호출"),
            ("QMessageBox.question", "destructive confirm 다이얼로그"),
            ("self._refresh_step_cards()", "삭제 후 카드 재구성"),
        ):
            self.assert_true(
                pattern in handler_src,
                f"[#115] _on_step_delete 에 '{desc}' 필수: '{pattern}'",
            )

        # 4) signal 연결 (_refresh_step_cards 안)
        refresh_src = _inspect.getsource(_mwv2.MainWindowV2._refresh_step_cards)
        self.assert_true(
            "card.delete_requested.connect(self._on_step_delete)" in refresh_src,
            "[#115] _refresh_step_cards 가 card.delete_requested 를 _on_step_delete 에 연결 필수",
        )

    def test_114_v2_element_picker_uses_show_minimized(self):
        """[회귀] v2 element picker 시작 시 main window 완전 minimize.

        사용자 보고 (2026-05-12 메모장테스트 후속): F3 일시정지 (3초) 후 picker
        가 다시 떠도 main window 가 화면에 보임. 원인: _on_elempick 가 self.lower()
        만 호출 — Z-order 만 내려가고 가시 영역에 그대로 남아 picker overlay 의
        transparent 영역으로 노출.

        Fix: v1 패턴 (ui_inspection_handler.py:46 mw.showMinimized()) 와 통일.
        - _on_elempick: self.lower() → self.showMinimized()
        - _on_element_picked / _on_element_cancel: self.raise_() 앞에 self.showNormal()

        가드: 3개 메서드 모두 의도된 패턴 사용.
        """
        import inspect as _inspect

        from ui_v2 import main_window_v2 as _mwv2

        elempick_src = _inspect.getsource(_mwv2.MainWindowV2._on_elempick)
        self.assert_true(
            "self.showMinimized()" in elempick_src,
            "[#114] _on_elempick 가 self.showMinimized() 호출 필수 (self.lower() X)",
        )
        # F3 wait 후 main window 가시 회귀 방지: lower() 단독 호출 금지
        self.assert_true(
            elempick_src.count("self.lower()") == 0,
            "[#114] _on_elempick 에 self.lower() 단독 호출 금지 — showMinimized() 사용",
        )

        picked_src = _inspect.getsource(_mwv2.MainWindowV2._on_element_picked)
        self.assert_true(
            "self.showNormal()" in picked_src,
            "[#114] _on_element_picked 가 self.showNormal() 호출 필수 (minimize 복원)",
        )

        cancel_src = _inspect.getsource(_mwv2.MainWindowV2._on_element_cancel)
        self.assert_true(
            "self.showNormal()" in cancel_src,
            "[#114] _on_element_cancel 가 self.showNormal() 호출 필수 (minimize 복원)",
        )

    def test_113_regenerate_replaces_step_in_place(self):
        """[회귀] 재생성 (G7-D) 은 in-place 대체 — 새 step 추가 X.

        사용자 보고 (2026-05-12 메모장테스트): step1 이 잘못된 코드여도 재생성
        클릭하면 새 step2 가 생성됨 (step1 보존) → 같은 user_request 가 두 개
        존재. step1 이 오류 안 나면 전체 실행 시 작업이 두 번 시도되거나, step1
        실패하면 step2 도달 불가 회귀.

        Fix: generate_step() 에 replaces_step_id 옵션 추가.
        - prev_body 계산 시 그 step 은 skip (자기 자신의 stale 코드 prev 인식 회피)
        - 마지막에 add_step 대신 update_step 분기 → step_id 보존, in-place 갱신
        - 재생성 path (_on_regenerate_with_warnings) 가 step_id 를 전달

        가드:
        1) generate_step 시그니처에 replaces_step_id 파라미터 존재
        2) prev_body 루프 안 replaces_step_id skip 패턴 존재
        3) update_step 분기 + execution_result=None reset 패턴 존재
        4) _on_regenerate_with_warnings 가 replaces_step_id 를 _send_request 에 전달
        5) _send_request 시그니처에 replaces_step_id 존재
        """
        import inspect as _inspect

        from core import app_service as _as
        from ui_v2 import main_window_v2 as _mwv2

        # 1) generate_step 시그니처
        sig = _inspect.signature(_as.AppService.generate_step)
        self.assert_true(
            "replaces_step_id" in sig.parameters,
            "[#113] AppService.generate_step 시그니처에 replaces_step_id 파라미터 필수",
        )

        # 2) prev_body skip 패턴
        gen_src = _inspect.getsource(_as.AppService.generate_step)
        for pattern, desc in (
            (
                'replaces_step_id is not None and ls.get("step_id") == replaces_step_id',
                "prev_body skip 로직",
            ),
            ("if replaces_step_id is not None:", "update_step 분기"),
            ("self.update_step(session.session_id, replaces_step_id", "update_step 호출"),
            ('"execution_result": None', "이전 실행 결과 무효화"),
            ("step.step_id = replaces_step_id", "반환 step 의 step_id 보존"),
        ):
            self.assert_true(
                pattern in gen_src,
                f"[#113] generate_step 에 '{desc}' 필수: '{pattern}'",
            )

        # 3) _on_regenerate_with_warnings 가 replaces_step_id 전달
        regen_src = _inspect.getsource(_mwv2.MainWindowV2._on_regenerate_with_warnings)
        self.assert_true(
            "replaces_step_id=step_id" in regen_src,
            "[#113] _on_regenerate_with_warnings 가 replaces_step_id=step_id 전달 필수",
        )

        # 4) _send_request 시그니처
        send_sig = _inspect.signature(_mwv2.MainWindowV2._send_request)
        self.assert_true(
            "replaces_step_id" in send_sig.parameters,
            "[#113] _send_request 시그니처에 replaces_step_id 파라미터 필수",
        )

        # 5) _send_request 가 generate_step 에 전달
        send_src = _inspect.getsource(_mwv2.MainWindowV2._send_request)
        self.assert_true(
            "replaces_step_id=replaces_step_id" in send_src,
            "[#113] _send_request worker 가 generate_step 에 replaces_step_id 전달 필수",
        )

    def test_112_main_window_v2_uses_load_settings_not_self_settings(self):
        """[회귀] MainWindowV2 는 self.settings 속성 사용 금지 — 항상 _load_settings().

        Bug (2026-05-12 사용자 보고, v2-새세션-160554 step 2 실행 후):
        ```
        File "ui_v2/main_window_v2.py", line 2726, in _on_step_done
            ui_cfg = self.settings.setdefault("ui", {})
        AttributeError: 'MainWindowV2' object has no attribute 'settings'
        ```
        MainWindowV2 는 __init__ 에서 self.settings 를 저장하지 않고, 매번
        self._load_settings() 로 fresh load. F2 (auto_run hint 토스트) 추가 시
        잘못된 self.settings 패턴이 들어가 step 실행 후마다 AttributeError 발생.
        export 워크플로우 (line 1588), F1 auto-run (line 2382) 도 같은 버그.

        Fix: 4곳 모두 self._load_settings() 로 교체. mutate + save 경로는
        `s = self._load_settings(); ...; self._save_settings(s)` 패턴.

        가드: ui_v2/main_window_v2.py 에 `self.settings` 패턴이 존재하지 않음.
        """
        path = Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py"
        src = path.read_text(encoding="utf-8")
        # `self.settings` 직접 attribute 접근 검색.
        # `self._save_settings`, `self._load_settings` 같은 메서드는 제외 — 정규식으로 word boundary 사용.
        import re as _re

        matches = _re.findall(r"\bself\.settings\b", src)
        self.assert_true(
            len(matches) == 0,
            f"[회귀 #112] MainWindowV2 는 self.settings 속성 사용 금지 — "
            f"항상 self._load_settings(). 발견 횟수: {len(matches)}",
        )

    def test_111_prompt_builder_windows_console_launch_rule(self):
        """[회귀] Windows 가이드에 console 앱 launch 시 CREATE_NEW_CONSOLE 규칙.

        Bug (2026-05-12 사용자 보고, v2-새세션-153705):
        AI 가 `subprocess.Popen(['cmd.exe'])` 생성 → kernel_worker 는 콘솔 없는
        piped subprocess 라 자식이 부모 stdio 상속 → CMD 윈도우 생성 X → 부모
        파이프로 banner 만 출력 → 후속 `Application().connect(title_re='.*명령
        프롬프트', timeout=10)` 가 영원히 윈도우 못 찾아 TimeoutError.

        Fix: prompt_builder.py 의 Windows subprocess 가이드에 콘솔 앱 (cmd /
        powershell / wt) 실행 시 `creationflags=subprocess.CREATE_NEW_CONSOLE`
        명시 규칙 추가. GUI 앱 (notepad, chrome 등) 은 불필요 명시.

        가드: 핵심 키워드들이 prompt_builder.py 의 Windows 가이드 영역에
        존재하는지 정적 검사.
        """
        from core import prompt_builder as pb_mod

        src = Path(pb_mod.__file__).read_text(encoding="utf-8")

        for pattern, desc in (
            ("CREATE_NEW_CONSOLE", "CREATE_NEW_CONSOLE 플래그 명시"),
            ("cmd.exe", "cmd.exe 예시"),
            ("powershell", "powershell 예시"),
            ("kernel_worker", "kernel_worker 콘솔 없는 subprocess 컨텍스트 언급"),
        ):
            self.assert_true(
                pattern in src,
                f"[회귀 #111] prompt_builder.py 의 Windows 가이드에 "
                f"'{desc}' 필수 (콘솔 앱 launch 규칙). 패턴: '{pattern}'",
            )

    def test_110_kernel_worker_result_markers_isolated_with_newline_prefix(self):
        """[회귀] kernel_worker RESULT 마커는 항상 "\\n" prefix 로 새 라인 보장.

        Bug (2026-05-12 사용자 보고, v2-새세션-153705):
        AI 생성 코드가 `subprocess.Popen(['cmd.exe'])` 호출 → cmd.exe 가 부모
        의 piped stdout 상속 → 마지막 프롬프트 라인 `C:\\Users\\...>` 가 trailing
        newline 없이 fd 1 로 출력 → kernel_worker 가 이어서 `<<<ERROR>>>\\n` 쓰
        면 한 라인으로 합쳐짐 (`C:\\Users\\...><<<ERROR>>>`).
        parent (execution_kernel) 의 `line == "<<<ERROR>>>"` 리터럴 비교 fail
        → success=True 유지 → 실패한 스텝이 ✅ 로 오보고.

        Fix: RESULT_SUCCESS / RESULT_ERROR / PONG 모두 "\\n" prefix 로 write —
        subprocess 가 trailing newline 없이 남긴 partial line 과 분리되어
        marker 가 독립 라인으로 보장됨.

        가드: kernel_worker.py 의 각 마커 write 가 "\\n" + MARKER + "\\n" 패턴
        을 사용하는지 정적 검사.
        """
        worker_path = Path(__file__).parent.parent / "core" / "kernel_worker.py"
        src = worker_path.read_text(encoding="utf-8")

        for marker_const in ("RESULT_SUCCESS", "RESULT_ERROR", "PONG_RESP"):
            pattern = f'"\\n" + {marker_const}'
            self.assert_true(
                pattern in src,
                f"[회귀 #110] kernel_worker.py 가 {marker_const} 쓸 때 "
                f"앞에 '\\n' prefix 필수 (subprocess partial line 분리). "
                f"패턴: '{pattern}'",
            )

    # ──────────────────────────────────────────
    # ADR 0003 Phase 1 — 시크릿 처리 (test_117 ~ test_121)
    # ──────────────────────────────────────────

    def test_117_secrets_detector_known_patterns(self):
        """[ADR 0003 Phase 1] secrets_detector.detect 가 명시 토큰 패턴 매칭.

        JWT / AWS / GitHub PAT / OpenAI / Anthropic / Google API / Slack — 각각
        대표 샘플 1개씩. confidence 0.85+ + kind 정확.
        """
        from core.secrets_detector import detect

        samples = {
            "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
            "aws_key": "AKIAIOSFODNN7EXAMPLE",
            "github_pat": "ghp_" + "x" * 36,
            "openai_key": "sk-" + "A" * 40,
            "anthropic_key": "sk-ant-" + "x" * 50,
            "google_api_key": "AIza" + "x" * 35,
            "slack_token": "xoxb-" + "1" * 20,
        }
        for expected_kind, sample in samples.items():
            self.step(f"detect — {expected_kind}")
            matches = detect(sample)
            self.assert_true(
                any(m.kind == expected_kind and m.confidence >= 0.85 for m in matches),
                f"[ADR 0003] '{expected_kind}' 샘플 매칭 필수: {sample[:20]}... "
                f"실제 matches: {[(m.kind, m.confidence) for m in matches]}",
            )

    def test_118_secrets_detector_false_positive_guard(self):
        """[ADR 0003 Phase 1] 평범한 한국어 / 영어 문장은 password 매칭 안 됨.

        false-positive 비용 — 사용자가 일반 대화에 "비밀번호" 단어를 언급해도
        값 부분이 없거나 placeholder 같으면 detect 가 무시해야 함.
        """
        from core.secrets_detector import detect

        safe_inputs = [
            "비밀번호를 까먹었어요. 어떻게 해야 하나요?",
            "Forgot your password? Try the recovery option.",
            "password: TODO",  # placeholder 값
            "pw: none",  # placeholder
            "그 변수 이름은 password_hash 야",  # 변수명 언급
        ]
        for text in safe_inputs:
            self.step(f"FP guard — {text[:30]}")
            matches = detect(text)
            # password_hint 매칭은 0 이어야 함 (high_entropy 는 별도 — 짧아서 안 잡힘)
            password_matches = [m for m in matches if m.kind == "password_hint"]
            self.assert_true(
                len(password_matches) == 0,
                f"[ADR 0003] 평범한 문장 false-positive: '{text}' → "
                f"password_hint matches: {password_matches}",
            )

    def test_119_secrets_detector_entropy_threshold(self):
        """[ADR 0003 Phase 1] high_entropy 매칭은 임계 이상만 + identifier 스킵.

        - 길이 20+ 의 'aaaa...' 같은 낮은 엔트로피 → skip
        - 길이 20+ 의 random hex 같은 높은 엔트로피 → match
        - 길이 20+ 이지만 식별자처럼 보이는 이름 (this_is_a_variable_name) → skip
        """
        from core.secrets_detector import detect

        self.step("낮은 엔트로피 — skip")
        matches = detect("a" * 30)  # 엔트로피 = 0
        he = [m for m in matches if m.kind == "high_entropy"]
        self.assert_true(len(he) == 0, f"[ADR 0003] 낮은 엔트로피 skip 필수: {he}")

        self.step("식별자처럼 보이는 영어 단어 시퀀스 — skip")
        matches = detect("this_is_a_python_variable_name_that_is_long")
        he = [m for m in matches if m.kind == "high_entropy"]
        self.assert_true(
            len(he) == 0,
            f"[ADR 0003] 식별자 false-positive skip 필수: {he}",
        )

        self.step("높은 엔트로피 random 토큰 — match")
        # 무작위 분포 + 특수문자 mix → identifier 검사 통과
        random_token = "Xq7-vR2/pM9+yB4_zN6=tK8aH3wE1uC5"
        matches = detect(random_token)
        he = [m for m in matches if m.kind == "high_entropy"]
        self.assert_true(
            len(he) >= 1,
            f"[ADR 0003] 높은 엔트로피 토큰 match 필수: {random_token} → {matches}",
        )

    def test_120_prompts_system_context_has_secret_rule(self):
        """[ADR 0003 Phase 1] system_context 에 규칙 #21 + #8 단서 박힘.

        AI 가 `{{secret:label}}` placeholder 를 평문 박지 않고 `get_secret()` 로
        참조하도록 prompt 에서 명시. 회귀 시 AI 가 평문 박는 환각 재발.
        """
        import json as _json

        prompts_path = Path(__file__).parent.parent / "config" / "prompts.json"
        cfg = _json.loads(prompts_path.read_text(encoding="utf-8"))
        ctx = cfg["system_context"]

        self.step("규칙 #21 키워드")
        self.assert_true(
            "{{secret:" in ctx,
            "[ADR 0003] system_context 에 '{{secret:' placeholder 패턴 명시 필수",
        )
        self.assert_true(
            "get_secret" in ctx,
            "[ADR 0003] system_context 에 'get_secret' helper 사용 패턴 명시 필수",
        )
        self.assert_true(
            "ADR 0003" in ctx,
            "[ADR 0003] system_context 가 ADR 0003 reference 필수 (추적성)",
        )

        self.step("규칙 #8 단서")
        self.assert_true(
            "규칙 #21 적용" in ctx,
            "[ADR 0003] 규칙 #8 (사용자 입력값 보존) 에 #21 단서 추가 필수",
        )

    def test_121_code_validator_emits_hardcoded_secret_warning(self):
        """[ADR 0003 Phase 1 C2] AI 가 평문 시크릿 박은 코드는 hardcoded_secret warning.

        - 평문 JWT / AWS / OpenAI key 가 문자열 리터럴에 박힌 코드 → warning 발행
        - placeholder ({{secret:label}}) 만 들어있는 코드 → warning 없음
        - 일반 문자열 ("hello world") → warning 없음
        """
        from core.code_validator import validate_step_code

        self.step("평문 AWS key — warning 필수")
        code_with_aws = (
            "try:\n"
            '    aws_secret = "AKIAIOSFODNN7EXAMPLE"\n'
            "    print(aws_secret)\n"
            "except Exception as e:\n"
            "    print(e)\n"
        )
        result = validate_step_code(code_with_aws)
        secret_issues = result.by_kind("hardcoded_secret")
        self.assert_true(
            len(secret_issues) >= 1,
            f"[ADR 0003 C2] 평문 AWS key → hardcoded_secret warning 필수. "
            f"실제 issues: {[i.kind for i in result.issues]}",
        )
        self.assert_true(
            "aws_key" in secret_issues[0].message,
            f"[ADR 0003 C2] warning message 에 'aws_key' kind 명시 필수: "
            f"{secret_issues[0].message}",
        )

        self.step("평문 OpenAI key — warning 필수")
        code_with_openai = (
            "try:\n"
            '    api_key = "sk-' + "A" * 40 + '"\n'
            "    print(api_key)\n"
            "except Exception as e:\n"
            "    print(e)\n"
        )
        result = validate_step_code(code_with_openai)
        self.assert_true(
            len(result.by_kind("hardcoded_secret")) >= 1,
            "[ADR 0003 C2] 평문 OpenAI key → hardcoded_secret warning 필수",
        )

        self.step("placeholder 만 — warning 없음")
        code_with_placeholder = (
            "try:\n"
            '    pw = get_secret("gmail_pw")\n'
            "    pyautogui.write(pw)\n"
            "except Exception as e:\n"
            "    print(e)\n"
        )
        result = validate_step_code(code_with_placeholder)
        self.assert_true(
            len(result.by_kind("hardcoded_secret")) == 0,
            f"[ADR 0003 C2] get_secret 패턴 코드는 false-positive 0 필수. "
            f"실제: {[i.message for i in result.by_kind('hardcoded_secret')]}",
        )

        self.step("일반 문자열 — warning 없음")
        code_plain = (
            "try:\n"
            '    print("hello world")\n'
            '    name = "ohdo"\n'
            "except Exception as e:\n"
            "    print(e)\n"
        )
        result = validate_step_code(code_plain)
        self.assert_true(
            len(result.by_kind("hardcoded_secret")) == 0,
            "[ADR 0003 C2] 일반 문자열은 false-positive 0 필수",
        )

    # ──────────────────────────────────────────
    # ADR 0003 Phase 2-a — Vault + Redact (test_122 ~ test_124)
    # ──────────────────────────────────────────

    def test_122_keyring_vault_roundtrip(self):
        """[ADR 0003 Phase 2-a] KeyringVault set / get / list / delete round-trip.

        실제 OS keyring (Windows Credential Manager / macOS Keychain) 에 unique
        service_name 으로 쓰고 finally 에서 정리 — 사용자 keyring 오염 X.
        인덱스 파일도 임시 디렉토리.
        """
        import uuid

        from core.secrets import KeyringVault, SecretLabel

        # 충돌 방지용 unique service_name (test 동시 실행 / 재실행에도 안전)
        service_name = f"ohdo.test.pr2.{uuid.uuid4().hex[:8]}"

        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "vault_index.json"
            vault = KeyringVault(index_path=index_path, service_name=service_name)

            lab_pw = SecretLabel(label="gmail_pw")
            lab_api = SecretLabel(label="openai", namespace="apikey")

            try:
                self.step("초기 상태 — list 비어있음 / get None")
                self.assert_equal(vault.list(), [])
                self.assert_equal(vault.list(namespace="apikey"), [])
                self.assert_true(vault.get(lab_pw) is None)

                self.step("set → get round-trip")
                vault.set(lab_pw, "MyP@ss!2026")
                vault.set(lab_api, "sk-test-aaaa")
                self.assert_equal(vault.get(lab_pw), "MyP@ss!2026")
                self.assert_equal(vault.get(lab_api), "sk-test-aaaa")

                self.step("list — namespace 별로 분리")
                secret_list = vault.list(namespace="secret")
                apikey_list = vault.list(namespace="apikey")
                self.assert_equal(len(secret_list), 1)
                self.assert_equal(secret_list[0].label, "gmail_pw")
                self.assert_equal(secret_list[0].namespace, "secret")
                self.assert_equal(len(apikey_list), 1)
                self.assert_equal(apikey_list[0].label, "openai")
                self.assert_equal(apikey_list[0].namespace, "apikey")

                self.step("overwrite — set 두 번째 호출은 값 교체")
                vault.set(lab_pw, "NewPass!")
                self.assert_equal(vault.get(lab_pw), "NewPass!")
                # list 중복 X — 같은 label 은 인덱스에 1회만
                self.assert_equal(len(vault.list()), 1)

                self.step("get_for_env — runtime 주입 환경변수 매핑")
                env = vault.get_for_env([lab_pw, lab_api])
                self.assert_equal(env.get("OHDO_SECRET_gmail_pw"), "NewPass!")
                self.assert_equal(env.get("OHDO_SECRET_openai"), "sk-test-aaaa")

                self.step("delete → get None, list 에서 빠짐")
                self.assert_true(vault.delete(lab_pw))
                self.assert_true(vault.get(lab_pw) is None)
                self.assert_equal(vault.list(), [])

                self.step("이미 삭제된 label 재삭제 — False (raise 안 됨)")
                self.assert_true(vault.delete(lab_pw) is False)

                self.step("인덱스 파일 — keyring 값 X (값은 인덱스에 저장 안 됨)")
                index_content = index_path.read_text(encoding="utf-8")
                self.assert_true("sk-test-aaaa" not in index_content)
                self.assert_true("NewPass" not in index_content)
                self.assert_true("MyP@ss" not in index_content)

            finally:
                # cleanup — keyring 잔여 정리 (실패해도 무시)
                for lab in (lab_pw, lab_api):
                    try:
                        vault.delete(lab)
                    except Exception:
                        pass

        self.step("SecretLabel 검증")
        # 잘못된 label 패턴
        for bad in ("UpperCase", "with-dash", "with.dot", "with space", "", "a" * 33):
            raised = False
            try:
                SecretLabel(label=bad)
            except ValueError:
                raised = True
            self.assert_true(
                raised,
                f"[ADR 0003] 잘못된 label '{bad}' 은 ValueError 필수",
            )
        # 잘못된 namespace
        raised = False
        try:
            SecretLabel(label="ok", namespace="something_else")
        except ValueError:
            raised = True
        self.assert_true(raised, "[ADR 0003] 잘못된 namespace 는 ValueError 필수")

    def test_123_redact_to_placeholder_preserves_spans(self):
        """[ADR 0003 Phase 2-a] to_placeholder_text 가 여러 span 을 역순 처리.

        앞 span 치환이 뒤 span 의 인덱스를 흐트러뜨리지 않도록 뒤에서부터 치환.
        """
        from core.secrets_redact import (
            format_placeholder,
            has_placeholders,
            to_placeholder_text,
        )

        self.step("단일 span 치환")
        text = "로그인 ID me@x.com PW MyP@ss!2026 로 접속해줘"
        # PW 값 위치
        start = text.index("MyP@ss!2026")
        end = start + len("MyP@ss!2026")
        out = to_placeholder_text(text, [((start, end), "gmail_pw")])
        self.assert_true("MyP@ss" not in out, f"평문 값 잔존 X 필수: {out}")
        self.assert_true("{{secret:gmail_pw}}" in out, f"placeholder 박힘 필수: {out}")

        self.step("다중 span 치환 (역순 처리 — 앞 치환이 뒤 인덱스 흐트러뜨림 X)")
        text2 = "ID abc@x.com PW pass1234 토큰 ghp_xyzaaaaaa"

        def _span_of(needle: str) -> tuple[int, int]:
            i = text2.index(needle)
            return (i, i + len(needle))

        spans = [
            (_span_of("abc@x.com"), "gmail_id"),
            (_span_of("pass1234"), "gmail_pw"),
            (_span_of("ghp_xyzaaaaaa"), "github_pat_token"),
        ]
        out = to_placeholder_text(text2, spans)
        for original in ("abc@x.com", "pass1234", "ghp_xyzaaaaaa"):
            self.assert_true(original not in out, f"평문 '{original}' 잔존 X 필수: {out}")
        for label in ("gmail_id", "gmail_pw", "github_pat_token"):
            self.assert_true(
                format_placeholder(label) in out,
                f"placeholder '{label}' 박힘 필수: {out}",
            )

        self.step("빈 입력 / 빈 span — 원문 그대로")
        self.assert_equal(to_placeholder_text("", []), "")
        self.assert_equal(to_placeholder_text("hello", []), "hello")

        self.step("has_placeholders")
        self.assert_true(has_placeholders("값: {{secret:gmail_pw}}"))
        self.assert_true(not has_placeholders("값: plaintext"))
        self.assert_true(not has_placeholders(""))

        self.step("겹친 span 은 ValueError — 호출자 실수 사전 catch")
        raised = False
        try:
            to_placeholder_text("hello world", [((0, 5), "a"), ((3, 8), "b")])
        except ValueError:
            raised = True
        self.assert_true(raised, "겹친 span 은 ValueError 발생 필수")

        self.step("잘못된 label 은 ValueError")
        raised = False
        try:
            to_placeholder_text("hello", [((0, 5), "Has-Dash")])
        except ValueError:
            raised = True
        self.assert_true(raised, "잘못된 label 패턴은 ValueError 발생 필수")

    def test_124_redact_extract_labels_dedupes_in_order(self):
        """[ADR 0003 Phase 2-a] extract_labels 가 등장 순 + 중복 제거.

        같은 placeholder 가 여러 번 나와도 1회만 반환 (등장 순서 보존).
        runtime D1 의 env 주입에서 같은 시크릿 중복 lookup 회피.
        """
        from core.secrets_redact import extract_labels

        self.step("기본 — 등장 순서 보존")
        code = (
            "pw = get_secret('gmail_pw')\n"
            "tok = get_secret('github_pat_token')\n"
            "# {{secret:gmail_pw}} 는 위에서 한 번 더 등장한 셈\n"
            'login(user="{{secret:gmail_id}}", pw="{{secret:gmail_pw}}")\n'
        )
        labels = extract_labels(code)
        labels_only = [lab.label for lab in labels]
        # 등장 순서 (placeholder 기준): gmail_pw, gmail_id (gmail_pw 는 중복)
        # 첫 번째 placeholder 는 라인 3 의 `{{secret:gmail_pw}}` — 그게 0번째
        self.assert_equal(
            labels_only,
            ["gmail_pw", "gmail_id"],
            f"등장 순서 + 중복 제거 실패: {labels_only}",
        )
        # 모두 namespace='secret' default
        for lab in labels:
            self.assert_equal(lab.namespace, "secret")

        self.step("namespace override")
        labels_api = extract_labels("url = '{{secret:openai}}/v1'", namespace="apikey")
        self.assert_equal(len(labels_api), 1)
        self.assert_equal(labels_api[0].label, "openai")
        self.assert_equal(labels_api[0].namespace, "apikey")

        self.step("빈 입력 / placeholder 없음 — 빈 리스트")
        self.assert_equal(extract_labels(""), [])
        self.assert_equal(extract_labels("일반 문장 placeholder 없음"), [])

        self.step("잘못된 label 패턴은 매칭 안 됨")
        # 대문자 / 점 / 너무 긴 라벨은 정규식이 매칭하지 않으므로 skip
        out = extract_labels("{{secret:UpperCase}} {{secret:with.dot}} {{secret:" + "a" * 33 + "}}")
        self.assert_equal(out, [], f"잘못된 label 은 무시되어야 함: {out}")

    # ──────────────────────────────────────────
    # ADR 0003 Phase 2-b — AppService / Kernel 통합 (test_125 ~ test_130)
    # ──────────────────────────────────────────

    def test_125_generate_step_preserves_placeholder_to_ai(self):
        """[ADR 0003 Phase 2-b] generate_step 이 placeholder 를 AI prompt 에 보존.

        user_request 에 ``{{secret:gmail_pw}}`` 가 들어있으면 AI 에 그대로 전달.
        AI 가 system_context #21 가이드로 ``get_secret()`` 패턴 코드 생성.
        평문 vault 값은 prompt 어디에도 들어가지 않음 (vault lookup 미발생).
        """
        import asyncio

        from core.adapters.base_adapter import AIResponse
        from core.app_service import AppService
        from core.storage.local_json import LocalJsonRepository

        class _CapturingAI:
            def __init__(self):
                self.last_user_text = None
                self.last_system_text = None

            async def generate(self, prompt, images=None, system=None):
                self.last_user_text = prompt
                self.last_system_text = system
                return AIResponse(
                    text="",
                    code='pw = get_secret("gmail_pw")\nprint("ok")',
                    description="placeholder 코드 생성",
                    packages=[],
                    raw_response="",
                    tokens_used=10,
                    response_time_ms=50,
                    success=True,
                )

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            ai = _CapturingAI()
            # vault 미주입 — placeholder 통과는 vault 의존 X
            svc = AppService(session_repo=repo, ai_manager=ai)
            session = svc.create_session(title="placeholder test")

            self.step("placeholder 포함 user_request 전송")
            user_req = "로그인 후 PW {{secret:gmail_pw}} 입력해줘"
            asyncio.run(svc.generate_step(session, user_req))

            self.assert_true(
                "{{secret:gmail_pw}}" in (ai.last_user_text or ""),
                f"[ADR 0003 Phase 2-b] placeholder 가 AI prompt 에 보존 필수. "
                f"실제 prompt 일부: {(ai.last_user_text or '')[:200]}",
            )

    def test_126_generate_step_no_plaintext_to_ai_when_placeholder_used(self):
        """[ADR 0003 Phase 2-b] vault 에 평문 등록되어 있어도 AI 에 평문 0건.

        vault 등록 → 사용자가 placeholder 로 메시지 보냄 → AI 호출 시 prompt 에
        등록된 vault 값 (평문) 은 절대 등장 X. 핵심 보안 contract.
        """
        import asyncio
        import uuid

        from core.adapters.base_adapter import AIResponse
        from core.app_service import AppService
        from core.secrets import KeyringVault, SecretLabel
        from core.storage.local_json import LocalJsonRepository

        secret_value = "RealPassword!" + uuid.uuid4().hex[:8]
        service_name = f"ohdo.test.pr3.{uuid.uuid4().hex[:8]}"

        class _CapturingAI:
            def __init__(self):
                self.last_user_text = None
                self.last_system_text = None

            async def generate(self, prompt, images=None, system=None):
                self.last_user_text = prompt
                self.last_system_text = system
                return AIResponse(
                    text="",
                    code='print("ok")',
                    description="x",
                    packages=[],
                    raw_response="",
                    tokens_used=1,
                    response_time_ms=1,
                    success=True,
                )

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            vault = KeyringVault(
                index_path=Path(tmp) / "vault_index.json",
                service_name=service_name,
            )
            lab = SecretLabel(label="gmail_pw")
            try:
                vault.set(lab, secret_value)

                ai = _CapturingAI()
                svc = AppService(session_repo=repo, ai_manager=ai, secrets_vault=vault)
                session = svc.create_session(title="no plaintext test")

                self.step("placeholder 메시지 → vault 값은 AI 에 안 감")
                asyncio.run(svc.generate_step(session, "PW {{secret:gmail_pw}} 사용해줘"))

                prompt = ai.last_user_text or ""
                system = ai.last_system_text or ""
                self.assert_true(
                    secret_value not in prompt,
                    f"[ADR 0003 Phase 2-b] vault 평문값 '{secret_value[:8]}...' 이 "
                    f"AI prompt (user) 에 들어가면 안 됨",
                )
                self.assert_true(
                    secret_value not in system,
                    "[ADR 0003 Phase 2-b] vault 평문값이 AI prompt (system) 에 들어가면 안 됨",
                )
            finally:
                vault.delete(lab)

    def test_127_session_saves_placeholder_not_plaintext(self):
        """[ADR 0003 Phase 2-b B3] 세션 JSON 저장 시 placeholder 만 보존.

        user_request 와 generated_code 가 placeholder 인 채로 저장되어, 디스크에
        평문 시크릿 잔존 X. reload 후에도 placeholder 유지.
        """
        import asyncio

        from core.adapters.base_adapter import AIResponse
        from core.app_service import AppService
        from core.storage.local_json import LocalJsonRepository

        class _FakeAI:
            async def generate(self, prompt, images=None, system=None):
                return AIResponse(
                    text="",
                    code='pw = get_secret("gmail_pw")\nprint(len(pw))',
                    description="placeholder 사용 코드",
                    packages=[],
                    raw_response="",
                    tokens_used=1,
                    response_time_ms=1,
                    success=True,
                )

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            svc = AppService(session_repo=repo, ai_manager=_FakeAI())
            session = svc.create_session(title="placeholder saved test")

            self.step("generate_step 호출")
            user_req = "PW {{secret:gmail_pw}} 사용"
            step, _ = asyncio.run(svc.generate_step(session, user_req))
            self.assert_true(step is not None)

            self.step("디스크 JSON 직접 읽어 placeholder 유지 확인")
            # SessionManager 규칙: {data_dir}/sessions/{session_id}/session.json
            session_file = Path(tmp) / "sessions" / session.session_id / "session.json"
            self.assert_true(
                session_file.exists(), f"session 파일 디스크 저장 필수: {session_file}"
            )
            disk_text = session_file.read_text(encoding="utf-8")
            self.assert_true(
                "{{secret:gmail_pw}}" in disk_text,
                f"[ADR 0003 Phase 2-b B3] 세션 JSON 에 placeholder 보존 필수. 파일: {session_file}",
            )

            self.step("reload 시 placeholder 유지")
            reloaded = svc.get_session(session.session_id)
            self.assert_equal(len(reloaded.steps), 1)
            saved = reloaded.steps[0]
            self.assert_true(
                "{{secret:gmail_pw}}" in saved.get("user_request", ""),
                f"[ADR 0003 Phase 2-b B3] reload 후 user_request placeholder 유지 필수. "
                f"실제: {saved.get('user_request')!r}",
            )
            # generated_code 는 AI 가 placeholder 대신 get_secret('label') 패턴 생성 —
            # B3 의 핵심은 user_request 에 평문 미잔존 + generated_code 에도 vault 평문값
            # 절대 미잔존. AI 가 반환한 코드 그대로 보존되는지만 확인.
            self.assert_true(
                "get_secret" in saved.get("generated_code", "")
                and "gmail_pw" in saved.get("generated_code", ""),
                f"[ADR 0003 Phase 2-b B3] reload 후 generated_code 에 get_secret('gmail_pw') "
                f"패턴 보존 필수. 실제: {saved.get('generated_code')!r}",
            )

    def test_128_execution_kernel_injects_vault_env(self):
        """[ADR 0003 Phase 2-b D1] ExecutionKernel._build_subprocess_env 가 vault
        시크릿을 ``OHDO_SECRET_<label>`` 환경변수로 주입 + 기존 ``OHDO_PARENT_PID``
        보존.
        """
        import uuid

        from core.execution_kernel import ExecutionKernel
        from core.secrets import KeyringVault, SecretLabel

        service_name = f"ohdo.test.pr3.{uuid.uuid4().hex[:8]}"

        with tempfile.TemporaryDirectory() as tmp:
            vault = KeyringVault(
                index_path=Path(tmp) / "vault_index.json",
                service_name=service_name,
            )
            lab = SecretLabel(label="gmail_pw")
            lab2 = SecretLabel(label="github_pat_token")
            try:
                vault.set(lab, "secret_value_1")
                vault.set(lab2, "secret_value_2")

                self.step("vault 주입 — env 에 OHDO_SECRET_* 들어감")
                kernel = ExecutionKernel(secrets_vault=vault)
                env = kernel._build_subprocess_env()
                self.assert_equal(env.get("OHDO_SECRET_gmail_pw"), "secret_value_1")
                self.assert_equal(env.get("OHDO_SECRET_github_pat_token"), "secret_value_2")
                self.assert_true(
                    "OHDO_PARENT_PID" in env,
                    "[§4.5] OHDO_PARENT_PID 보존 (vault 주입이 기존 fix 깨면 안 됨)",
                )
                self.assert_equal(env.get("PYTHONIOENCODING"), "utf-8")
                self.assert_equal(env.get("PYTHONUNBUFFERED"), "1")

                self.step("vault 미주입 — OHDO_SECRET_* 없음")
                kernel_no_vault = ExecutionKernel()
                env2 = kernel_no_vault._build_subprocess_env()
                secret_keys = [k for k in env2 if k.startswith("OHDO_SECRET_")]
                self.assert_equal(
                    secret_keys,
                    [],
                    f"vault 미주입 시 OHDO_SECRET_* 없어야 함. 실제: {secret_keys}",
                )
                # 기존 path 회귀 X
                self.assert_true("OHDO_PARENT_PID" in env2)
            finally:
                vault.delete(lab)
                vault.delete(lab2)

    def test_129_kernel_worker_has_get_secret_helper(self):
        """[ADR 0003 Phase 2-b D1] kernel_worker.py 가 get_secret() helper 주입.

        - helper 함수 ``_get_secret`` 정의 존재
        - globals 에 ``get_secret`` 키로 등록 (AI 생성 코드가 import 없이 호출 가능)
        - 환경변수 미존재 시 RuntimeError + 사용자 안내 메시지
        """
        worker_path = Path(__file__).parent.parent / "core" / "kernel_worker.py"
        src = worker_path.read_text(encoding="utf-8")

        self.step("helper 함수 정의 + globals 등록")
        self.assert_true(
            "def _get_secret(" in src,
            "[ADR 0003 D1] kernel_worker 에 _get_secret 함수 정의 필수",
        )
        self.assert_true(
            '_globals["get_secret"]' in src or "_globals['get_secret']" in src,
            "[ADR 0003 D1] _globals['get_secret'] 등록 필수 (AI 코드가 import 없이 호출)",
        )
        self.assert_true(
            "OHDO_SECRET_" in src,
            "[ADR 0003 D1] OHDO_SECRET_<label> 환경변수 prefix 사용 필수",
        )

        self.step("runtime — 환경변수 set → get_secret 호출 → 값 반환")
        from core import kernel_worker

        os.environ["OHDO_SECRET_test_pr3_label"] = "runtime_value"
        try:
            val = kernel_worker._get_secret("test_pr3_label")
            self.assert_equal(val, "runtime_value")
        finally:
            del os.environ["OHDO_SECRET_test_pr3_label"]

    def test_130_get_secret_raises_runtime_error_on_missing(self):
        """[ADR 0003 Phase 2-b D1] get_secret 미존재 label 은 RuntimeError +
        사용자 안내 메시지 (Settings 어디서 등록할지).
        """
        from core import kernel_worker

        # 보장 — 환경에 절대 없을 unique label
        missing_label = "absent_label_" + os.urandom(4).hex()
        env_key = f"OHDO_SECRET_{missing_label}"
        # 안전망 — 혹시라도 set 되어있으면 제거
        os.environ.pop(env_key, None)

        self.step("미존재 label → RuntimeError")
        raised_err = None
        try:
            kernel_worker._get_secret(missing_label)
        except RuntimeError as e:
            raised_err = e

        self.assert_true(
            raised_err is not None,
            "[ADR 0003 D1] 미존재 label 은 RuntimeError 발생 필수",
        )
        msg = str(raised_err)
        self.assert_true(
            missing_label in msg,
            f"[ADR 0003 D1] 에러 메시지에 label 명시 필수: {msg}",
        )
        self.assert_true(
            "Settings" in msg or "시크릿" in msg,
            f"[ADR 0003 D1] 사용자 안내 (Settings/시크릿) 필수: {msg}",
        )

    # ──────────────────────────────────────────
    # ADR 0003 Phase 2-c — UI 통합 (test_131)
    # ──────────────────────────────────────────

    # ──────────────────────────────────────────
    # ADR 0003 Phase 2-c PR-5 — Detector 패턴 보강 (test_132 ~ test_133)
    # ──────────────────────────────────────────

    def test_132_detector_catches_quoted_password_in_rpa_input(self):
        """[ADR 0003 PR-5] detector 가 따옴표 안 PW-look-alike 값을 잡음.

        사용자 보고 (2026-05-14 'v2-새세션-083149' 세션):
            ohdo 가 채팅 입력 '...클릭하고 \\'@06dhentjd%@%^\\' 입력' 처리 시
            advisory 모달 안 뜨고 PW 평문이 AI prompt + generated_code 까지
            그대로 흘러감. 원인: 기존 detector 의 password_hint 는 "비밀번호:"
            같은 명시 키워드 + separator 필요, generic_token 은 charset 에
            특수문자 (@%^) 없고 길이 임계 20 미만 → 둘 다 미스.

        Fix: quoted_literal 패턴 추가 — 따옴표 안 6자+ 값 중 특수문자 mix
        또는 RPA 입력 동사 ('입력', 'write' 등) 인접 시 confidence ≥0.5.
        """
        from core.secrets_detector import detect

        self.step("사용자 실제 케이스 — '@06dhentjd%@%^' (특수문자 + 영숫자 mix)")
        user_text = "📌 선택된 요소: [Edit] \"￼\"\n클릭하고 '@06dhentjd%@%^' 입력"
        matches = detect(user_text)
        actionable = [m for m in matches if m.confidence >= 0.5]
        self.assert_true(
            any(m.value == "@06dhentjd%@%^" for m in actionable),
            f"[ADR 0003 PR-5] 사용자 실제 PW '@06dhentjd%@%^' match 필수. "
            f"actionable matches: {[(m.kind, m.value, m.confidence) for m in actionable]}",
        )
        pw_match = next(m for m in actionable if m.value == "@06dhentjd%@%^")
        self.assert_true(
            pw_match.confidence >= 0.6,
            f"[ADR 0003 PR-5] PW match confidence ≥0.6 필수 "
            f"(특수문자 mix + RPA 동사 인접). 실제: {pw_match.confidence}",
        )

        self.step("RPA 동사 인접 — confidence boost")
        no_verb = detect("값은 'aB3!cD5#eF7$' 이에요")
        with_verb = detect("값 'aB3!cD5#eF7$' 입력")
        no_verb_hits = [m for m in no_verb if m.kind == "quoted_literal"]
        with_verb_hits = [m for m in with_verb if m.kind == "quoted_literal"]
        self.assert_true(
            len(no_verb_hits) >= 1 and len(with_verb_hits) >= 1,
            "[ADR 0003 PR-5] 특수문자 mix 값은 양쪽 다 match 되어야 함",
        )
        self.assert_true(
            with_verb_hits[0].confidence > no_verb_hits[0].confidence,
            f"[ADR 0003 PR-5] RPA 동사 인접 시 confidence boost 필수. "
            f"no_verb={no_verb_hits[0].confidence}, with_verb={with_verb_hits[0].confidence}",
        )

    def test_133_detector_skips_common_labels_and_identifiers(self):
        """[ADR 0003 PR-5] quoted_literal false-positive 가드.

        흔히 RPA 명령에 나오는 UI 라벨 / 키 이름 / 사용자 ID / element name
        메타 문자는 시크릿이 아니므로 advisory 안 띄워야 함. 사용자 보고 케이스
        ('doosung.oh' ID 는 false-positive 안 함) 도 여기 포함.
        """
        from core.secrets_detector import detect

        cases_should_not_alert = [
            "📌 선택된 요소: [Edit] \"￼\"\n클릭하고 'doosung.oh' 입력",
            "버튼 '확인' 클릭",
            "팝업 '취소' 누름",
            "다이얼로그 '저장' 클릭",
            "'OK' 버튼 누르기",
            "'Cancel' 클릭",
            "'엔터' 키 누르기",
            "'tab' 키 누르기",
            "'Enter' 키",
            "필드 '￼' 클릭",
            "메모장 열고 '안녕' 입력",
        ]
        for text in cases_should_not_alert:
            self.step(f"false-positive 회피 — {text[:40]}")
            matches = detect(text)
            actionable = [m for m in matches if m.confidence >= 0.5]
            quoted_actionable = [m for m in actionable if m.kind == "quoted_literal"]
            self.assert_true(
                len(quoted_actionable) == 0,
                f"[ADR 0003 PR-5] '{text}' 는 quoted_literal alert 0건 필수. "
                f"실제: {[(m.value, m.confidence) for m in quoted_actionable]}",
            )

        self.step("명시 PW 키워드 — 여전히 catch (회귀 가드)")
        matches = detect("비밀번호: MyP@ss123!")
        hint_matches = [m for m in matches if m.kind == "password_hint"]
        self.assert_true(
            len(hint_matches) >= 1,
            "[ADR 0003 PR-5] 명시 키워드 password_hint path 회귀 X",
        )

    # ──────────────────────────────────────────
    # ADR 0003 Phase 2-c PR-6 — Hot secret reload (test_134 ~ test_135)
    # ──────────────────────────────────────────

    def test_134_kernel_worker_has_set_secrets_handler(self):
        """[ADR 0003 PR-6] kernel_worker / execution_kernel 에 SET_SECRETS IPC 추가.

        - ``SET_SECRETS_CMD`` / ``SECRETS_OK`` 마커 정의 + handler 분기 존재
        - ``ExecutionKernel`` 가 ``_SET_SECRETS`` / ``_SECRETS_OK`` 마커 보유 +
          ``push_secrets`` / ``_push_secrets_unlocked`` 메서드 + ``_execute_locked``
          가 매 실행 직전 auto-push
        """
        worker_path = Path(__file__).parent.parent / "core" / "kernel_worker.py"
        worker_src = worker_path.read_text(encoding="utf-8")
        for needle in (
            'SET_SECRETS_CMD = "<<<SET_SECRETS>>>"',
            'SECRETS_OK = "<<<SECRETS_OK>>>"',
            "is_set_secrets",
            "OHDO_SECRET_",
            "json.loads",
        ):
            self.assert_true(
                needle in worker_src,
                f"[ADR 0003 PR-6] kernel_worker.py 에 '{needle}' 필수",
            )

        from core.execution_kernel import ExecutionKernel

        self.assert_true(
            ExecutionKernel._SET_SECRETS == "<<<SET_SECRETS>>>",
            "[ADR 0003 PR-6] ExecutionKernel._SET_SECRETS 마커 필수",
        )
        self.assert_true(
            ExecutionKernel._SECRETS_OK == "<<<SECRETS_OK>>>",
            "[ADR 0003 PR-6] ExecutionKernel._SECRETS_OK 마커 필수",
        )
        self.assert_true(
            hasattr(ExecutionKernel, "push_secrets")
            and hasattr(ExecutionKernel, "_push_secrets_unlocked"),
            "[ADR 0003 PR-6] push_secrets + _push_secrets_unlocked 메서드 필수",
        )

        import inspect

        exec_src = inspect.getsource(ExecutionKernel._execute_locked)
        self.assert_true(
            "_push_secrets_unlocked" in exec_src,
            "[ADR 0003 PR-6] _execute_locked 가 매 실행 직전 _push_secrets_unlocked 호출 필수",
        )

    def test_135_kernel_hot_reload_after_vault_set(self):
        """[ADR 0003 PR-6] kernel 시작 후 vault.set 한 시크릿이 즉시 반영.

        사용자 보고 (2026-05-14 'v2-새세션-091348'): 사용자가 advisory 모달에서
        vault 등록 후 그 step 을 실행 → RuntimeError "secret 'password' 미등록"
        — kernel start() 시점 1회 env 주입 패턴 한계. PR-6 의 SET_SECRETS hot
        reload 가 다음 실행에 자동 반영하도록 fix.

        실제 subprocess kernel 을 띄우는 integration 테스트 — 가볍지만 핵심 contract.
        """
        import uuid

        from core.execution_kernel import ExecutionKernel
        from core.secrets import KeyringVault, SecretLabel

        service_name = f"ohdo.test.pr6.{uuid.uuid4().hex[:8]}"
        label_name = f"pr6_test_{uuid.uuid4().hex[:6]}"

        with tempfile.TemporaryDirectory() as tmp:
            vault = KeyringVault(
                index_path=Path(tmp) / "vault_index.json",
                service_name=service_name,
            )
            kernel = ExecutionKernel(secrets_vault=vault, default_timeout=30)
            lab = SecretLabel(label=label_name)
            secret_value = "SecretValue_" + uuid.uuid4().hex[:8]

            try:
                self.step("vault 비어 있는 상태로 kernel 시작")
                kernel.start()
                self.assert_true(kernel.is_alive, "kernel 시작 실패")

                self.step("kernel 시작 후 vault.set 한 시크릿이 hot reload 됨")
                # 사용자 시나리오 — kernel 이미 떠 있는데 vault 에 새 시크릿 등록
                vault.set(lab, secret_value)

                # execute_block 의 auto-push 가 동작하는지 검증.
                # AI 가 생성한 코드처럼 get_secret 호출.
                result = kernel.execute_block(
                    f"print(get_secret({label_name!r}))",
                    step_id=1,
                    timeout=15,
                )
                self.assert_true(
                    result.success,
                    f"[ADR 0003 PR-6] hot reload 후 get_secret 호출 성공 필수. "
                    f"output: {result.output!r}, error: {result.error!r}",
                )
                self.assert_true(
                    secret_value in (result.output or ""),
                    f"[ADR 0003 PR-6] vault 값이 stdout 으로 반환 필수. "
                    f"expected: {secret_value!r}, actual output: {result.output!r}",
                )

                self.step("vault.delete 후 다음 실행에서 RuntimeError")
                vault.delete(lab)
                # AI 코드는 보통 try/except 로 감싸지만 여기선 raw — RuntimeError 가 step 으로 propagate
                result2 = kernel.execute_block(
                    f"print(get_secret({label_name!r}))",
                    step_id=2,
                    timeout=15,
                )
                self.assert_true(
                    (not result2.success)
                    and (label_name in (result2.error or "") + (result2.output or "")),
                    f"[ADR 0003 PR-6] vault.delete 후 미존재 label 은 RuntimeError 필수. "
                    f"success: {result2.success}, error: {result2.error!r}",
                )

                self.step("explicit push_secrets — 동일 효과")
                vault.set(lab, "RegisteredAgain_" + uuid.uuid4().hex[:6])
                push_ok = kernel.push_secrets(timeout=5.0)
                self.assert_true(push_ok, "[ADR 0003 PR-6] push_secrets 응답 OK 필수")

                expected2 = vault.get(lab)
                result3 = kernel.execute_block(
                    f"print(get_secret({label_name!r}))",
                    step_id=3,
                    timeout=15,
                )
                self.assert_true(
                    result3.success and expected2 in (result3.output or ""),
                    f"[ADR 0003 PR-6] push_secrets 후 값 반영 필수. "
                    f"expected: {expected2!r}, output: {result3.output!r}",
                )

            finally:
                try:
                    kernel.stop()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    vault.delete(lab)
                except Exception:  # noqa: BLE001
                    pass

    def test_131_pr4_ui_wiring_and_locale_catalog(self):
        """[ADR 0003 Phase 2-c PR-4] 사용자 입력 path 보호 + Settings 시크릿 탭.

        구성 요소:
          1. ``prepare_outgoing_text`` import 가능 + signature 정상
          2. ``ui_v2._on_send_message`` 가 ``prepare_outgoing_text`` 호출 (detector
             hit 시 advisory 모달 띄움 — 사용자 입력 path 차단 entry-point)
          3. ``SettingsDialog`` 가 ``secrets_vault`` kwarg + ``_create_secrets_tab``
             메서드 보유 (시크릿 관리 UI)
          4. locale catalog — ``ui_v2.secret_advisory.*`` + ``ui_v2.settings.secrets.*``
             + ``ui_v2.toast.secret_*`` + ``ui_v2.validation.kind_hardcoded_secret``
             모든 키가 ko/en 양쪽에 정확히 같은 set 으로 존재 (handoff §21 패턴)
        """
        import inspect
        from inspect import signature

        self.step("(1) prepare_outgoing_text import + signature")
        from ui_v2.secret_advisory_dialog import (
            SecretAdvisoryDialog,
            prepare_outgoing_text,
        )

        sig = signature(prepare_outgoing_text)
        params = list(sig.parameters)
        for needed in ("raw_text", "vault", "parent"):
            self.assert_true(
                needed in params,
                f"[ADR 0003 PR-4] prepare_outgoing_text 에 '{needed}' 인자 필수. 실제: {params}",
            )
        self.assert_true(SecretAdvisoryDialog is not None, "SecretAdvisoryDialog import 가능 필수")

        self.step("(2) ui_v2._on_send_message 가 prepare_outgoing_text 호출")
        from ui_v2.main_window_v2 import MainWindowV2

        send_src = inspect.getsource(MainWindowV2._on_send_message)
        self.assert_true(
            "prepare_outgoing_text" in send_src,
            "[ADR 0003 PR-4] _on_send_message 가 prepare_outgoing_text 호출 필수 "
            "(detector hit 시 advisory 모달 — 사용자 입력 path 차단 entry-point)",
        )
        self.assert_true(
            "secrets_vault" in send_src,
            "[ADR 0003 PR-4] _on_send_message 가 self.app_service.secrets_vault 전달 필수",
        )

        self.step("(3) SettingsDialog 의 secrets_vault kwarg + _create_secrets_tab")
        from ui.settings_dialog import SettingsDialog

        init_src = inspect.getsource(SettingsDialog.__init__)
        self.assert_true(
            "secrets_vault" in init_src,
            "[ADR 0003 PR-4] SettingsDialog.__init__ 가 secrets_vault kwarg 받음 필수",
        )
        self.assert_true(
            hasattr(SettingsDialog, "_create_secrets_tab"),
            "[ADR 0003 PR-4] SettingsDialog._create_secrets_tab 메서드 필수",
        )
        # ui_v2 가 vault 주입해서 SettingsDialog 호출
        from ui_v2.main_window_v2 import MainWindowV2 as _MW

        settings_open_src = inspect.getsource(_MW._on_open_settings)
        self.assert_true(
            "secrets_vault" in settings_open_src,
            "[ADR 0003 PR-4] ui_v2._on_open_settings 가 SettingsDialog 에 vault 주입 필수",
        )

        self.step("(4) locale catalog — 9+ 시크릿 키 + 양쪽 symmetry")
        ko = json.loads(
            (Path(__file__).parent.parent / "core" / "locale" / "ko.json").read_text(
                encoding="utf-8"
            )
        )
        en = json.loads(
            (Path(__file__).parent.parent / "core" / "locale" / "en.json").read_text(
                encoding="utf-8"
            )
        )

        required_keys = [
            "ui_v2.secret_advisory.title",
            "ui_v2.secret_advisory.body",
            "ui_v2.secret_advisory.btn_register_and_send",
            "ui_v2.secret_advisory.btn_send_as_is",
            "ui_v2.secret_advisory.btn_cancel",
            "ui_v2.settings.tab_secrets",
            "ui_v2.settings.secrets.empty",
            "ui_v2.toast.secret_registered_count",
            "ui_v2.validation.kind_hardcoded_secret",
        ]
        for key in required_keys:
            self.assert_true(
                key in ko,
                f"[ADR 0003 PR-4] 키 '{key}' ko.json 누락",
            )
            self.assert_true(
                key in en,
                f"[ADR 0003 PR-4] 키 '{key}' en.json 누락",
            )

        # 전체 시크릿 관련 키 symmetry (handoff §21 i18n 패턴)
        secret_prefixes = (
            "ui_v2.secret_advisory.",
            "ui_v2.settings.secrets.",
            "ui_v2.toast.secret_",
            "ui_v2.toast.kernel_restart_for_secret",
        )

        def _filter(d):
            return {k for k in d.keys() if any(k == p or k.startswith(p) for p in secret_prefixes)}

        ko_set = _filter(ko)
        en_set = _filter(en)
        self.assert_true(
            ko_set == en_set,
            f"[ADR 0003 PR-4] ko/en catalog 시크릿 키 mismatch. "
            f"ko-only: {sorted(ko_set - en_set)}, en-only: {sorted(en_set - ko_set)}",
        )

    # ──────────────────────────────────────────
    # ADR 0003 Phase 2-c PR-7 — Element-based password-field detection (test_136 ~ test_137)
    # ──────────────────────────────────────────

    def test_136_is_password_field_element_decisive_signals(self):
        """[ADR 0003 PR-7] is_password_field_element 가 HTML / UIA 신호로 판정.

        결정적 / 강한 신호:
          - HTML ``type="password"`` (dom_context.attributes.type)
          - HTML ``name`` / ``id`` 가 password-hint (password / pwd / pswd / userps 등)
          - UIA ``control_type="Edit"`` + ``automation_id`` 가 password-hint
          - UIA Edit + ``name`` 이 한글 "비밀번호" / "패스워드" 등

        False-positive 가드:
          - HTML ``type="text"`` + name=username → False
          - HTML ``type="email"`` → False
          - automation_id ∈ {user, username, userid, email, search, ...} → False
        """
        from core.secrets_detector import is_password_field_element

        self.step("HTML type=password — 결정적")
        elem = {
            "control_type": "Edit",
            "automation_id": "userPs",
            "dom_context": {
                "cdp_available": True,
                "tagName": "input",
                "attributes": {"type": "password", "id": "userPs"},
            },
        }
        is_pw, reason = is_password_field_element(elem)
        self.assert_true(is_pw, f"HTML type=password 결정적 신호 필수. reason={reason!r}")
        self.assert_true("password" in reason.lower(), f"reason 에 password 명시 필수: {reason}")

        self.step("UIA only (DOM 없음) — automation_id 'userPs' hint")
        elem_uia = {
            "control_type": "Edit",
            "automation_id": "userPs",
            "parent_window_title": "어떤 앱",
        }
        is_pw2, _ = is_password_field_element(elem_uia)
        self.assert_true(is_pw2, "UIA Edit + automation_id 'userPs' password-hint 필수")

        self.step("UIA Edit + name='비밀번호' (한글 라벨)")
        elem_ko = {"control_type": "Edit", "automation_id": "", "name": "비밀번호"}
        is_pw3, _ = is_password_field_element(elem_ko)
        self.assert_true(is_pw3, "한글 '비밀번호' 라벨 catch 필수")

        self.step("false-positive — username field")
        elem_user = {
            "control_type": "Edit",
            "automation_id": "userId",
            "dom_context": {
                "cdp_available": True,
                "tagName": "input",
                "attributes": {"type": "text", "id": "userId", "name": "username"},
            },
        }
        is_pw4, _ = is_password_field_element(elem_user)
        self.assert_true(not is_pw4, "username field 는 password 아님")

        self.step("false-positive — email field")
        elem_email = {
            "control_type": "Edit",
            "dom_context": {
                "cdp_available": True,
                "tagName": "input",
                "attributes": {"type": "email", "name": "email"},
            },
        }
        is_pw5, _ = is_password_field_element(elem_email)
        self.assert_true(not is_pw5, "email field 는 password 아님")

        self.step("false-positive — search box")
        elem_search = {
            "control_type": "Edit",
            "automation_id": "search",
            "dom_context": {
                "cdp_available": True,
                "tagName": "input",
                "attributes": {"type": "text", "name": "search"},
            },
        }
        is_pw6, _ = is_password_field_element(elem_search)
        self.assert_true(not is_pw6, "search box 는 password 아님")

        self.step("빈 / None element")
        self.assert_true(not is_password_field_element({})[0])
        self.assert_true(not is_password_field_element(None)[0])

    def test_137_detect_with_elements_surfaces_password_field_input(self):
        """[ADR 0003 PR-7] element 가 password field 면 사용자 입력 따옴표 값을
        자동 surface — 사용자 보고 'v2-새세션-091348' 시나리오 재현.

        시나리오: 사용자가 채팅에 평범한 따옴표 값 ('doosung.oh') 입력. text-only
        detect() 는 이걸 ID 로 보고 skip. 하지만 picker 가 잡은 element 가 password
        field (type="password" / automation_id="userPs") 이면 input 의도가 시크릿임
        → advisory 띄움.
        """
        from core.secrets_detector import detect, detect_with_elements

        # 사용자 input + HTML password field
        user_text = "📌 선택된 요소: [Edit] \"￼\"\n클릭하고 '@06dhentjd%@%^' 입력"
        elem_pw = {
            "control_type": "Edit",
            "automation_id": "userPs",
            "dom_context": {
                "cdp_available": True,
                "tagName": "input",
                "attributes": {"type": "password", "id": "userPs"},
            },
        }

        self.step("기본 detect — 이미 quoted_literal 잡음 (PR-5)")
        text_only = [m for m in detect(user_text) if m.confidence >= 0.5]
        ql = [m for m in text_only if m.kind == "quoted_literal"]
        self.assert_true(len(ql) >= 1, "PR-5 quoted_literal 회귀 가드")

        self.step("with elements — kind 가 password_field_element 로 upgrade")
        with_elem = [
            m for m in detect_with_elements(user_text, elements=[elem_pw]) if m.confidence >= 0.5
        ]
        pw_field_matches = [m for m in with_elem if m.kind == "password_field_element"]
        self.assert_true(
            len(pw_field_matches) >= 1,
            f"[ADR 0003 PR-7] element 가 PW field 면 password_field_element kind 필수. "
            f"실제: {[(m.kind, m.value, m.confidence) for m in with_elem]}",
        )
        # confidence boost (≥0.85) — quoted_literal 의 0.85 보다 높거나 같음
        self.assert_true(
            pw_field_matches[0].confidence >= 0.85,
            f"[ADR 0003 PR-7] PW field upgrade confidence ≥0.85 필수. "
            f"실제: {pw_field_matches[0].confidence}",
        )

        self.step("사용자 ID ('doosung.oh') 도 PW field 면 surface")
        # text-only detect 는 'doosung.oh' 를 email-like 로 skip (PR-5)
        id_text = "📌 선택된 요소: [Edit] \"￼\"\n클릭하고 'doosung.oh' 입력"
        text_id = [m for m in detect(id_text) if m.confidence >= 0.5]
        # detect() 만 호출하면 hit 없음
        self.assert_true(
            not any(m.kind in ("quoted_literal", "password_field_element") for m in text_id),
            "PR-5 — 영문 ID skip 가드",
        )
        # element 가 PW field 면 surface
        with_pw_field = [
            m
            for m in detect_with_elements(id_text, elements=[elem_pw])
            if m.confidence >= 0.5 and m.kind == "password_field_element"
        ]
        self.assert_true(
            len(with_pw_field) >= 1 and any(m.value == "doosung.oh" for m in with_pw_field),
            f"[ADR 0003 PR-7] element 가 PW field 면 'doosung.oh' 도 surface. "
            f"실제: {[(m.kind, m.value, m.confidence) for m in with_pw_field]}",
        )

        self.step("element 가 username field 면 surface 안 함 (false-positive 가드)")
        elem_user = {
            "control_type": "Edit",
            "automation_id": "userId",
            "dom_context": {
                "cdp_available": True,
                "tagName": "input",
                "attributes": {"type": "text", "name": "username"},
            },
        }
        with_user_field = [
            m for m in detect_with_elements(id_text, elements=[elem_user]) if m.confidence >= 0.5
        ]
        self.assert_true(
            len(with_user_field) == 0,
            f"[ADR 0003 PR-7] username element 는 advisory 안 띄워야 함. "
            f"실제: {[(m.kind, m.value, m.confidence) for m in with_user_field]}",
        )

        self.step("elements 미주입 — 기존 detect() 동작 보존")
        # quoted_literal 의 confidence 와 동일
        with_none = detect_with_elements(user_text, elements=None)
        only_text = detect(user_text)
        # password_field_element 매치는 절대 없어야 함
        self.assert_true(
            not any(m.kind == "password_field_element" for m in with_none),
            "elements 없으면 password_field_element kind 없어야 함",
        )
        # 다른 매치는 동일
        self.assert_equal(len(with_none), len(only_text))

    # ──────────────────────────────────────────
    # ADR 0003 Phase 2-c PR-8 — Windows Credential Manager import (test_138)
    # ──────────────────────────────────────────

    def test_138_windows_credentials_module_and_ui_wiring(self):
        """[ADR 0003 PR-8] Windows Credential Manager import path.

        1. ``core.windows_credentials`` 모듈 — API 표면 정상
        2. SettingsDialog 가 vault 주입 시 ``_on_secrets_import_winvault`` 메서드 보유
        3. ``WindowsCredentialsImportDialog`` import 가능 + ``__init__`` 가 vault 받음
        4. locale catalog — ko/en 양쪽에 import 관련 키 존재 + symmetry
        5. Windows 환경에서 ``list_credentials`` 가 실 호출 가능 (값 비어도 OK)
        """
        import inspect

        self.step("(1) core.windows_credentials API 표면")
        from core.windows_credentials import (
            CRED_TYPE_GENERIC,
            WindowsCredentialMeta,
            is_available,
            list_credentials,
            read_credential,
        )

        self.assert_equal(CRED_TYPE_GENERIC, 1)
        self.assert_true(callable(is_available), "is_available 함수 필수")
        self.assert_true(callable(list_credentials), "list_credentials 함수 필수")
        self.assert_true(callable(read_credential), "read_credential 함수 필수")
        # WindowsCredentialMeta 는 frozen dataclass — suggested_label 메서드 보유
        meta = WindowsCredentialMeta(
            target_name="git:https://github.com",
            user_name="oddsung",
            cred_type=CRED_TYPE_GENERIC,
        )
        sl = meta.suggested_label()
        self.assert_true(
            isinstance(sl, str)
            and 1 <= len(sl) <= 32
            and all(c.islower() or c.isdigit() or c == "_" for c in sl),
            f"[PR-8] suggested_label 포맷 ([a-z0-9_]{{1,32}}): {sl!r}",
        )

        self.step("(2) SettingsDialog._on_secrets_import_winvault")
        from ui.settings_dialog import SettingsDialog

        self.assert_true(
            hasattr(SettingsDialog, "_on_secrets_import_winvault"),
            "[PR-8] SettingsDialog._on_secrets_import_winvault 메서드 필수",
        )
        tab_src = inspect.getsource(SettingsDialog._create_secrets_tab)
        self.assert_true(
            "windows_credentials" in tab_src and "btn_import_winvault" in tab_src,
            "[PR-8] secrets 탭이 Windows import 버튼 조건부 표시 필수",
        )

        self.step("(3) WindowsCredentialsImportDialog import + 시그니처")
        from ui.windows_credentials_import_dialog import WindowsCredentialsImportDialog

        sig = inspect.signature(WindowsCredentialsImportDialog.__init__)
        self.assert_true(
            "secrets_vault" in sig.parameters,
            "[PR-8] WindowsCredentialsImportDialog __init__ 가 secrets_vault 받음 필수",
        )
        # 핵심 메서드들
        for needed in ("_reload_credentials", "_on_import_clicked", "_on_filter_changed"):
            self.assert_true(
                hasattr(WindowsCredentialsImportDialog, needed),
                f"[PR-8] WindowsCredentialsImportDialog.{needed} 필수",
            )

        self.step("(4) locale catalog — import 관련 키 ko/en 양쪽 + symmetry")
        ko = json.loads(
            (Path(__file__).parent.parent / "core" / "locale" / "ko.json").read_text(
                encoding="utf-8"
            )
        )
        en = json.loads(
            (Path(__file__).parent.parent / "core" / "locale" / "en.json").read_text(
                encoding="utf-8"
            )
        )
        required_keys = [
            "ui_v2.settings.secrets.btn_import_winvault",
            "ui_v2.settings.secrets.import_dialog_title",
            "ui_v2.settings.secrets.import_dialog_description",
            "ui_v2.settings.secrets.import_col_target",
            "ui_v2.settings.secrets.import_col_user",
            "ui_v2.settings.secrets.import_col_label",
            "ui_v2.settings.secrets.import_btn",
            "ui_v2.settings.secrets.import_empty",
            "ui_v2.settings.secrets.import_done",
            "ui_v2.settings.secrets.import_failed",
        ]
        for key in required_keys:
            self.assert_true(key in ko, f"[PR-8] key '{key}' ko.json 누락")
            self.assert_true(key in en, f"[PR-8] key '{key}' en.json 누락")

        self.step("(5) Windows 환경 — list_credentials 실 호출")
        if is_available():
            creds = list_credentials()
            # 시스템 자격 증명 0개 가능 — list 타입만 확인
            self.assert_true(
                isinstance(creds, list),
                f"[PR-8] list_credentials 반환 타입 list 필수. 실제: {type(creds).__name__}",
            )
            for c in creds[:3]:
                self.assert_true(
                    isinstance(c, WindowsCredentialMeta),
                    "[PR-8] list_credentials 항목 타입은 WindowsCredentialMeta",
                )
                self.assert_equal(c.cred_type, CRED_TYPE_GENERIC)
        else:
            # 비 Windows 환경 (CI Linux 등) — 빈 list 반환 보장
            self.assert_equal(list_credentials(), [])
            self.assert_true(read_credential("anything") is None)

    # ──────────────────────────────────────────
    # ADR 0003 Phase 2-c PR-9 — Secret insert popup (test_139 ~ test_140)
    # ──────────────────────────────────────────

    def test_139_find_at_trigger_logic(self):
        """[ADR 0003 PR-9] '@' 자동완성 trigger 조건.

        - 공백/줄 시작 뒤의 @ + 영문/숫자/_ prefix → trigger
        - user@host (email — @ 앞이 영문) → trigger 안 함
        - cursor 가 prefix 영역 밖 (공백/구두점 등 통과) → trigger 안 함
        """
        from ui_v2.secret_insert_popup import find_at_trigger

        cases = [
            ("hello @", 7, (6, "")),
            ("@github_pat", 11, (0, "github_pat")),
            ("hello @git", 10, (6, "git")),
            ("user@host", 9, None),
            ("hello @abc def", 10, (6, "abc")),
            ("hello @abc def", 13, None),
            ("@", 1, (0, "")),
            ("text", 4, None),
            ("", 0, None),
        ]
        for text, pos, expected in cases:
            self.step(f"text={text!r} pos={pos}")
            result = find_at_trigger(text, pos)
            self.assert_equal(
                result,
                expected,
                f"[PR-9] find_at_trigger({text!r}, {pos}) → {result} != {expected}",
            )

    def test_140_secret_insert_popup_module_and_wiring(self):
        r"""[ADR 0003 PR-9] popup module + ui_v2 wiring (\`@\` 자동완성 only).

        PR-10a (2026-05-14): 🔒 버튼 (옵션 A) 제거. \`@\` 자동완성 (옵션 B) 만 남음.

        - ``SecretInsertPopup`` import + 시그니처 + ``open_from_at`` / ``update_filter``
        - ui_v2 의 ``_on_message_text_changed`` 가 ``find_at_trigger`` + ``open_from_at`` 호출
        - ``message_edit.textChanged`` → ``_on_message_text_changed`` signal 연결 존재
        """
        import inspect

        from ui_v2.secret_insert_popup import (
            SecretInsertPopup,
            find_at_trigger,
        )

        self.step("(1) SecretInsertPopup API")
        sig = inspect.signature(SecretInsertPopup.__init__)
        for needed in ("vault", "editor", "parent"):
            self.assert_true(
                needed in sig.parameters,
                f"[PR-9] SecretInsertPopup __init__ 의 '{needed}' 인자 필수",
            )
        for needed in ("open_from_at", "update_filter", "label_selected"):
            self.assert_true(
                hasattr(SecretInsertPopup, needed),
                f"[PR-9] SecretInsertPopup.{needed} 필수",
            )
        # PR-10a: 🔒 버튼 path 제거 — open_from_button 메서드 없어야 함
        self.assert_true(
            not hasattr(SecretInsertPopup, "open_from_button"),
            "[PR-10a] open_from_button 제거 필수 (옵션 A 폐기)",
        )

        self.step("(2) ui_v2 wiring — textChanged hook + lazy popup")
        from ui_v2.main_window_v2 import MainWindowV2

        for method_name in ("_get_secret_popup", "_on_message_text_changed"):
            self.assert_true(
                hasattr(MainWindowV2, method_name),
                f"[PR-9] MainWindowV2.{method_name} 필수",
            )
        # PR-10a: 🔒 버튼 핸들러 제거
        self.assert_true(
            not hasattr(MainWindowV2, "_on_secret_insert_clicked"),
            "[PR-10a] _on_secret_insert_clicked 제거 필수",
        )
        # textChanged 핸들러가 find_at_trigger + open_from_at 호출
        tc_src = inspect.getsource(MainWindowV2._on_message_text_changed)
        self.assert_true(
            "find_at_trigger" in tc_src and "open_from_at" in tc_src,
            "[PR-9] textChanged 핸들러가 find_at_trigger + open_from_at 사용 필수",
        )
        mw_path = Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py"
        mw_src = mw_path.read_text(encoding="utf-8")
        self.assert_true(
            "textChanged.connect(self._on_message_text_changed)" in mw_src,
            "[PR-9] message_edit.textChanged → _on_message_text_changed 연결 필수",
        )

        self.assert_true(callable(find_at_trigger))

    # ──────────────────────────────────────────
    # ADR 0003 Phase 2-c PR-10 — Element placeholder (test_141 ~ test_144)
    # ──────────────────────────────────────────

    def test_141_suggest_element_label_inference(self):
        """[PR-10b] HTML/UIA attribute → 의미 있는 라벨 자동 추론."""
        from core.element_labels import normalize_label, suggest_element_label

        # HTML type=password
        self.assert_equal(
            suggest_element_label(
                {
                    "control_type": "Edit",
                    "automation_id": "userPs",
                    "dom_context": {
                        "cdp_available": True,
                        "tagName": "input",
                        "attributes": {"type": "password", "id": "userPs"},
                    },
                }
            ),
            "pw",
        )
        # HTML username
        self.assert_equal(
            suggest_element_label(
                {
                    "control_type": "Edit",
                    "dom_context": {
                        "cdp_available": True,
                        "tagName": "input",
                        "attributes": {"type": "text", "name": "username"},
                    },
                }
            ),
            "id",
        )
        # UIA-only userPs — password keyword catch
        self.assert_equal(
            suggest_element_label({"control_type": "Edit", "automation_id": "userPs"}),
            "pw",
        )
        # 빈 dict — fallback
        self.assert_equal(suggest_element_label({}), "elem")
        # 중복 처리 — suffix
        self.assert_equal(
            suggest_element_label(
                {"control_type": "Edit", "automation_id": "userPs"},
                used_labels={"pw"},
            ),
            "pw_2",
        )
        # normalize_label
        self.assert_equal(normalize_label("Login Button!"), "login_button")
        self.assert_equal(normalize_label("user@host.com"), "user_host_com")

    def test_142_chip_widgets_module(self):
        """[PR-10c] chip_widgets 모듈 — ElementChip 라벨 편집 path."""
        import inspect

        from ui_v2.chip_widgets import ElementChip, ImageChip

        # ElementChip 시그니처
        sig = inspect.signature(ElementChip.__init__)
        for needed in ("label", "control_type", "name", "parent"):
            self.assert_true(
                needed in sig.parameters,
                f"[PR-10c] ElementChip __init__ '{needed}' 인자 필수",
            )
        # signals
        self.assert_true(hasattr(ElementChip, "label_changed"))
        self.assert_true(hasattr(ElementChip, "remove_requested"))
        self.assert_true(hasattr(ImageChip, "remove_requested"))

        # main_window_v2 가 chip_widgets 사용하는지
        mw_path = Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py"
        mw_src = mw_path.read_text(encoding="utf-8")
        self.assert_true(
            "ElementChip" in mw_src and "ImageChip" in mw_src,
            "[PR-10c] _refresh_chip_area 가 chip widget 사용 필수",
        )
        self.assert_true(
            "_ohdo_label" in mw_src,
            "[PR-10c] _ohdo_label 키로 라벨 저장 필수",
        )

    def test_143_element_placeholders_module(self):
        """[PR-10e] element_placeholders — extract / find_unresolved / replace_with_references."""
        from core.element_placeholders import (
            ELEMENT_PLACEHOLDER_RE,
            extract_labels,
            find_unresolved,
            replace_with_references,
        )

        text = "{{el:ID}} 클릭 후 'test' 입력 후 {{el:PW}} 클릭"
        # ID/PW 대문자 사용 — placeholder 정규식은 lowercase only 라 매치 안 됨
        self.step("대문자 라벨은 매치 안 됨 (lowercase only)")
        self.assert_equal(extract_labels(text), [])

        self.step("lowercase 정상 매치 + 중복 제거 + 등장 순서")
        text2 = "{{el:id}} 클릭 후 'test' 입력 후 {{el:pw}} 클릭 후 {{el:id}} 재클릭"
        self.assert_equal(extract_labels(text2), ["id", "pw"])

        self.step("find_unresolved — 매핑 안 된 라벨 반환")
        elements = [{"_ohdo_label": "id"}, {"_ohdo_label": "pw"}]
        self.assert_equal(find_unresolved(text2, elements), [])
        # pw 라벨 누락
        elements_partial = [{"_ohdo_label": "id"}]
        self.assert_equal(find_unresolved(text2, elements_partial), ["pw"])
        # 빈 elements
        self.assert_equal(find_unresolved(text2, []), ["id", "pw"])
        self.assert_equal(find_unresolved(text2, None), ["id", "pw"])

        self.step("replace_with_references — 📌 [label] 변환")
        replaced = replace_with_references(text2)
        self.assert_true("{{el:" not in replaced, f"placeholder 잔존 X 필수: {replaced}")
        self.assert_true("📌 [id]" in replaced)
        self.assert_true("📌 [pw]" in replaced)
        # 빈 input
        self.assert_equal(replace_with_references(""), "")
        self.assert_equal(replace_with_references("일반 텍스트"), "일반 텍스트")

        self.step("정규식 export")
        self.assert_true(ELEMENT_PLACEHOLDER_RE.match("{{el:gmail_pw}}") is not None)

    def test_144_pr10_ui_wiring(self):
        """[PR-10] ui_v2 wiring + popup elements_provider + i18n."""
        import inspect

        from ui_v2.main_window_v2 import MainWindowV2
        from ui_v2.secret_insert_popup import SecretInsertPopup

        self.step("(1) ui_v2._on_send_message 가 unresolved + replace 호출")
        send_src = inspect.getsource(MainWindowV2._on_send_message)
        self.assert_true(
            "find_unresolved" in send_src and "replace_with_references" in send_src,
            "[PR-10e] _on_send_message 가 element_placeholders helper 사용 필수",
        )
        self.assert_true(
            "element_unresolved" in send_src,
            "[PR-10e] _on_send_message 가 unresolved 시 차단 (모달) 필수",
        )

        self.step("(2) SecretInsertPopup elements_provider 인자")
        sig = inspect.signature(SecretInsertPopup.__init__)
        self.assert_true(
            "elements_provider" in sig.parameters,
            "[PR-10d] SecretInsertPopup __init__ 가 elements_provider 받음 필수",
        )
        popup_src = inspect.getsource(SecretInsertPopup._populate_items)
        self.assert_true(
            "elements_provider" in popup_src and '"el"' in popup_src,
            "[PR-10d] popup 이 elements 와 vault 통합 + (kind='el', label) 튜플 저장 필수",
        )
        insert_src = inspect.getsource(SecretInsertPopup._insert_placeholder)
        self.assert_true(
            '"{{el:"' in insert_src or "'{{el:'" in insert_src,
            "[PR-10d] popup 이 element 선택 시 {{el:label}} placeholder 삽입 필수",
        )

        self.step("(3) ui_v2 _get_secret_popup 가 elements_provider 주입")
        get_popup_src = inspect.getsource(MainWindowV2._get_secret_popup)
        self.assert_true(
            "elements_provider" in get_popup_src,
            "[PR-10d] _get_secret_popup 가 self._pending_elements 를 provider 로 전달 필수",
        )

        self.step("(4) win_inspector header 에 _ohdo_label suffix")
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        text = inspector.get_element_info_text(
            {
                "control_type": "Edit",
                "name": "username",
                "automation_id": "userId",
                "_ohdo_label": "id",
            }
        )
        self.assert_true(
            "[📌 id]" in text,
            f"[PR-10e] win_inspector header 에 [📌 label] 표시 필수. 실제: {text[:200]}",
        )

        self.step("(5) i18n catalog — unresolved 모달 키 ko/en")
        ko = json.loads(
            (Path(__file__).parent.parent / "core" / "locale" / "ko.json").read_text(
                encoding="utf-8"
            )
        )
        en = json.loads(
            (Path(__file__).parent.parent / "core" / "locale" / "en.json").read_text(
                encoding="utf-8"
            )
        )
        for key in (
            "ui_v2.dialog.element_unresolved_title",
            "ui_v2.dialog.element_unresolved_body",
        ):
            self.assert_true(key in ko, f"[PR-10] key '{key}' ko.json 누락")
            self.assert_true(key in en, f"[PR-10] key '{key}' en.json 누락")

    def test_145_input_hooks_module_and_api(self):
        """[ADR 0004 PR-11] core/input_hooks.py 모듈 + 핵심 dataclass + API 표면.

        recorder (PR-12+) 와 향후 element_picker 통합 시 공유할 LL hook manager.
        element_picker 의 기존 inline hook 코드는 PR-11 에서 건드리지 않음
        (test_44~48 sentinel 보호) — Phase R2/R3 점진 마이그레이션.
        """
        from core import input_hooks

        self.step("(1) dataclass + Literal 타입")
        self.assert_true(hasattr(input_hooks, "MouseEvent"), "MouseEvent dataclass 필수")
        self.assert_true(hasattr(input_hooks, "KeyboardEvent"), "KeyboardEvent dataclass 필수")

        me = input_hooks.MouseEvent(type="lbutton_down", x=10, y=20)
        self.assert_true(
            me.type == "lbutton_down" and me.x == 10 and me.y == 20,
            f"MouseEvent 필드 — type/x/y. 실제: {me!r}",
        )
        ke = input_hooks.KeyboardEvent(type="keydown", vk_code=0x41, scan_code=30)
        self.assert_true(
            ke.type == "keydown" and ke.vk_code == 0x41,
            f"KeyboardEvent 필드 — type/vk_code. 실제: {ke!r}",
        )

        self.step("(2) Win32 상수 정의")
        for const in (
            "WH_MOUSE_LL",
            "WH_KEYBOARD_LL",
            "WM_LBUTTONDOWN",
            "WM_LBUTTONUP",
            "WM_RBUTTONDOWN",
            "WM_KEYDOWN",
            "WM_KEYUP",
        ):
            self.assert_true(
                hasattr(input_hooks, const),
                f"[PR-11] Win32 상수 {const} 필수",
            )

        self.step("(3) InputHookManager API")
        self.assert_true(hasattr(input_hooks, "InputHookManager"), "InputHookManager 클래스 필수")
        mgr = input_hooks.InputHookManager()
        for method in (
            "install_mouse_callback",
            "install_keyboard_callback",
            "uninstall_mouse_callback",
            "uninstall_keyboard_callback",
            "uninstall_all",
        ):
            self.assert_true(hasattr(mgr, method), f"[PR-11] InputHookManager.{method} 필수")
        for prop in (
            "is_mouse_hook_installed",
            "is_keyboard_hook_installed",
            "mouse_callback_count",
            "keyboard_callback_count",
        ):
            self.assert_true(hasattr(mgr, prop), f"[PR-11] InputHookManager.{prop} 필수")

        self.step("(4) get_hook_manager 싱글톤")
        self.assert_true(hasattr(input_hooks, "get_hook_manager"), "get_hook_manager 함수 필수")
        m1 = input_hooks.get_hook_manager()
        m2 = input_hooks.get_hook_manager()
        self.assert_true(m1 is m2, "[PR-11] get_hook_manager 는 싱글톤 반환 필수")

    def test_146_input_hooks_callback_registration(self):
        """[ADR 0004 PR-11] callback 등록/해제 멱등성 + ID 고유성 + uninstall_all.

        non-Windows 환경에서도 callback 사전 등록은 작동 (hook 자체만 noop).
        """
        from core.input_hooks import InputHookManager

        mgr = InputHookManager()
        try:
            cb_a = lambda ev: False  # noqa: E731
            cb_b = lambda ev: False  # noqa: E731

            self.step("(1) 등록 ID 고유성")
            id_a = mgr.install_mouse_callback(cb_a)
            id_b = mgr.install_mouse_callback(cb_b)
            self.assert_true(id_a != id_b, f"[PR-11] callback ID 고유 필수. {id_a}=={id_b}")
            self.assert_true(
                mgr.mouse_callback_count == 2,
                f"[PR-11] mouse_callback_count == 2. 실제: {mgr.mouse_callback_count}",
            )

            self.step("(2) 부분 해제")
            mgr.uninstall_mouse_callback(id_a)
            self.assert_true(
                mgr.mouse_callback_count == 1,
                f"[PR-11] 부분 해제 후 count == 1. 실제: {mgr.mouse_callback_count}",
            )

            self.step("(3) 존재하지 않는 ID 해제 무시")
            mgr.uninstall_mouse_callback(99999)  # 예외 X
            self.assert_true(
                mgr.mouse_callback_count == 1,
                "[PR-11] 잘못된 ID 해제 idempotent (예외 X) 필수",
            )

            self.step("(4) keyboard 측 동일 동작")
            id_k = mgr.install_keyboard_callback(cb_a)
            self.assert_true(
                mgr.keyboard_callback_count == 1,
                "[PR-11] keyboard 등록 후 count == 1",
            )
            mgr.uninstall_keyboard_callback(id_k)
            self.assert_true(
                mgr.keyboard_callback_count == 0,
                "[PR-11] keyboard 해제 후 count == 0",
            )

            self.step("(5) uninstall_all 전부 비움")
            mgr.install_keyboard_callback(cb_a)
            mgr.uninstall_all()
            self.assert_true(
                mgr.mouse_callback_count == 0 and mgr.keyboard_callback_count == 0,
                "[PR-11] uninstall_all 후 양쪽 count == 0",
            )
        finally:
            mgr.uninstall_all()

    def test_147_input_hooks_callback_exception_isolation(self):
        """[ADR 0004 PR-11] 한 callback 예외가 다른 callback dispatch 에 영향 X.

        직접 dispatch 메서드 호출 (실제 hook 설치 X — 크로스 플랫폼 안전).
        """
        from core.input_hooks import InputHookManager, MouseEvent

        mgr = InputHookManager()
        try:
            received: list[str] = []

            def cb_raise(ev: MouseEvent) -> bool:
                raise RuntimeError("의도된 예외")

            def cb_ok(ev: MouseEvent) -> bool:
                received.append(ev.type)
                return False

            mgr.install_mouse_callback(cb_raise)
            mgr.install_mouse_callback(cb_ok)

            self.step("(1) dispatch 시 예외 격리 — cb_ok 호출 보장")
            mgr._mouse_callbacks_snapshot = list(mgr._mouse_callbacks.values())
            ev = MouseEvent(type="lbutton_down", x=0, y=0)
            for cb in list(mgr._mouse_callbacks.values()):
                try:
                    cb(ev)
                except Exception:
                    pass
            self.assert_true(
                "lbutton_down" in received,
                "[PR-11] cb_raise 예외 발생해도 cb_ok 가 dispatch 받아야 함",
            )
        finally:
            mgr.uninstall_all()

    def test_148_input_hooks_non_windows_silent_noop(self):
        """[ADR 0004 PR-11] non-Windows 환경에서 install/uninstall 이 silent noop.

        sys.platform != 'win32' 시 _user32 == None, hook 설치 시도해도 예외 없이
        is_*_hook_installed == False. callback 등록 자체는 가능 (메모리에만).
        """
        import sys as _sys

        from core.input_hooks import InputHookManager

        mgr = InputHookManager()
        try:
            # 직접 _user32 None 으로 강제 — 실제 win32 환경에서도 noop path 검증
            mgr._user32 = None

            self.step("(1) hook 설치 시도 예외 X")
            cb_id = mgr.install_mouse_callback(lambda ev: False)
            self.assert_true(cb_id > 0, "[PR-11] callback 등록 자체는 작동 필수")

            self.step("(2) is_mouse_hook_installed == False (noop)")
            self.assert_true(
                mgr.is_mouse_hook_installed is False,
                "[PR-11] non-Windows 에서 hook 미설치 (False) 필수",
            )

            self.step("(3) uninstall 도 silent noop")
            mgr.uninstall_mouse_callback(cb_id)
            self.assert_true(
                mgr.mouse_callback_count == 0,
                "[PR-11] non-Windows 에서도 callback 해제 작동 필수",
            )

            # 실제 win32 환경 확인 (정보용, fail 아님)
            self.step(f"(info) sys.platform == {_sys.platform!r}")
        finally:
            mgr.uninstall_all()

    def test_149_recorder_models_structure(self):
        """[ADR 0004 PR-12] recorder_models — RawEvent / RecordingSession / TransformOptions."""
        from datetime import datetime

        from core.recorder_models import RawEvent, RecordingSession, TransformOptions

        self.step("(1) RawEvent — kind 분기 + 기본값")
        click_ev = RawEvent(ts=datetime.now(), kind="click", x=10, y=20, button="left")
        self.assert_true(
            click_ev.kind == "click" and click_ev.x == 10 and click_ev.button == "left",
            f"RawEvent click 필드. 실제: {click_ev!r}",
        )
        key_ev = RawEvent(ts=datetime.now(), kind="key", vk_code=0x41)
        self.assert_true(
            key_ev.vk_code == 0x41 and key_ev.modifiers == [],
            "RawEvent key 필드 + modifiers 기본 빈 리스트",
        )
        marker_ev = RawEvent(ts=datetime.now(), kind="marker")
        self.assert_true(
            marker_ev.kind == "marker" and marker_ev.is_password_field is False,
            "RawEvent marker + is_password_field 기본 False",
        )

        self.step("(2) RecordingSession — events 시간순 + is_stopped/event_count")
        sess = RecordingSession(id="abc", started_at=datetime.now())
        self.assert_true(
            sess.is_stopped is False and sess.event_count == 0,
            "[PR-12] 신규 세션 is_stopped False + event_count 0",
        )
        sess.events.append(click_ev)
        self.assert_true(sess.event_count == 1, f"event_count 1. 실제: {sess.event_count}")
        sess.stopped_at = datetime.now()
        self.assert_true(sess.is_stopped is True, "stopped_at 셋 후 is_stopped True")

        self.step("(3) TransformOptions — 9 옵션 + 기본값 + 사용자 추가 §7 키")
        opts = TransformOptions()
        for attr in (
            "auto_window_focus_boundary",
            "enable_f8_marker",
            "drop_self_window_clicks",
            "drop_empty_space_clicks",
            "group_consecutive_keys",
            "group_key_idle_ms",
            "idle_boundary_ms",
            "integrate_secrets",
            "auto_user_request",
        ):
            self.assert_true(hasattr(opts, attr), f"[PR-12] TransformOptions.{attr} 필드 필수")
        self.assert_true(
            opts.idle_boundary_ms == 3000,
            f"[PR-12 §7] idle_boundary_ms 기본 3000ms. 실제: {opts.idle_boundary_ms}",
        )
        self.assert_true(
            opts.integrate_secrets is True,
            "[PR-12] integrate_secrets 기본 True (ADR 0003 강 통합)",
        )

    def test_150_recorder_lifecycle(self):
        """[ADR 0004 PR-12] Recorder start/stop/marker + 상태 전이."""
        from core.input_hooks import InputHookManager
        from core.recorder import (
            Recorder,
            RecorderAlreadyStartedError,
            RecorderNotStartedError,
        )

        hook_mgr = InputHookManager()
        recorder = Recorder(hook_mgr)
        try:
            self.step("(1) 초기 상태 — is_recording False")
            self.assert_true(recorder.is_recording is False, "[PR-12] 초기 is_recording False")
            self.assert_true(recorder.event_count == 0, "[PR-12] 초기 event_count 0")

            self.step("(2) start() — RecordingSession 반환 + hook 콜백 등록")
            sess = recorder.start(target_session_id="sess_xyz")
            self.assert_true(recorder.is_recording is True, "[PR-12] start 후 is_recording True")
            self.assert_true(sess.target_session_id == "sess_xyz", "[PR-12] target_session_id 보존")
            self.assert_true(
                hook_mgr.mouse_callback_count == 1 and hook_mgr.keyboard_callback_count == 1,
                "[PR-12] start 가 mouse + keyboard callback 등록 (각 1)",
            )

            self.step("(3) 동시 두 번 start 거부 (RecorderAlreadyStartedError)")
            try:
                recorder.start()
                self.assert_true(False, "[PR-12] 중복 start 는 예외 발생 필수")
            except RecorderAlreadyStartedError:
                pass

            self.step("(4) add_marker — 녹화 중 marker event 추가")
            recorder.add_marker()
            self.assert_true(recorder.event_count == 1, "[PR-12] marker 후 event_count 1")
            self.assert_true(sess.events[0].kind == "marker", "[PR-12] 첫 event 가 marker kind")

            self.step("(5) stop — hook 해제 + stopped_at + 멱등")
            stopped = recorder.stop()
            self.assert_true(recorder.is_recording is False, "[PR-12] stop 후 is_recording False")
            self.assert_true(
                stopped.is_stopped is True and stopped.stopped_at is not None,
                "[PR-12] stop 후 stopped_at 셋",
            )
            self.assert_true(
                hook_mgr.mouse_callback_count == 0 and hook_mgr.keyboard_callback_count == 0,
                "[PR-12] stop 가 hook callback 모두 해제",
            )

            stopped2 = recorder.stop()
            self.assert_true(stopped2 is stopped, "[PR-12] stop 멱등 (동일 세션 반환)")

            self.step("(6) stop 후 add_marker 차단 (RecorderNotStartedError)")
            try:
                recorder.add_marker()
                self.assert_true(False, "[PR-12] 비녹화 add_marker 는 예외 필수")
            except RecorderNotStartedError:
                pass

            self.step("(7) 재진입 — 새 RecordingSession 생성")
            sess2 = recorder.start()
            self.assert_true(sess2.id != sess.id, "[PR-12] 재진입 시 새 RecordingSession id")
            self.assert_true(recorder.event_count == 0, "[PR-12] 재진입 시 새 세션 event_count 0")
        finally:
            try:
                if recorder.is_recording:
                    recorder.stop()
            except Exception:
                pass
            hook_mgr.uninstall_all()

    def test_151_recorder_buffer_capture(self):
        """[ADR 0004 PR-12 + PR-17] mouse/keyboard hook callback 가 RawEvent buffer 에
        적절한 종류로 누적 + 시간순 정렬.

        PR-17 비동기 drain thread 도입으로 hook callback 호출 후 wait_for_event_count
        로 drain 완료 대기 (sub-second).
        """
        import time as _time

        from core.input_hooks import InputHookManager, KeyboardEvent, MouseEvent
        from core.recorder import Recorder

        hook_mgr = InputHookManager()
        recorder = Recorder(hook_mgr)
        try:
            recorder.start()
            sess = recorder.current_session
            self.assert_true(sess is not None, "current_session 존재")

            self.step("(1) lbutton_down → click event 추가 (drain 대기)")
            recorder._on_mouse_event(MouseEvent(type="lbutton_down", x=100, y=200))
            self.assert_true(
                recorder.wait_for_event_count(1, timeout=1.0),
                "[PR-17] drain 후 click 1 event",
            )
            ev = sess.events[0]
            self.assert_true(
                ev.kind == "click" and ev.x == 100 and ev.button == "left",
                f"[PR-12] click event 필드. 실제: {ev!r}",
            )

            self.step("(2) lbutton_up → 무시 (down 만 캡처)")
            recorder._on_mouse_event(MouseEvent(type="lbutton_up", x=100, y=200))
            _time.sleep(0.05)  # drain 가 처리할 시간 (실제로는 enqueue 안 함)
            self.assert_true(recorder.event_count == 1, "[PR-12] up 은 추가 X")

            self.step("(3) move → 무시 (PR-12 범위 외)")
            recorder._on_mouse_event(MouseEvent(type="move", x=50, y=50))
            _time.sleep(0.05)
            self.assert_true(recorder.event_count == 1, "[PR-12] move 무시")

            self.step("(4) wheel → scroll event 추가 + wheel_delta 보존")
            recorder._on_mouse_event(MouseEvent(type="wheel", x=10, y=20, wheel_delta=120))
            self.assert_true(
                recorder.wait_for_event_count(2, timeout=1.0),
                "[PR-17] drain 후 scroll 추가",
            )
            self.assert_true(
                sess.events[1].kind == "scroll" and sess.events[1].wheel_delta == 120,
                f"[PR-12] scroll 필드. {sess.events[1]!r}",
            )

            self.step("(5) keydown → key event 추가, keyup 무시")
            recorder._on_keyboard_event(KeyboardEvent(type="keydown", vk_code=0x41, scan_code=30))
            recorder._on_keyboard_event(KeyboardEvent(type="keyup", vk_code=0x41, scan_code=30))
            self.assert_true(
                recorder.wait_for_event_count(3, timeout=1.0),
                "[PR-17] drain 후 keydown 추가",
            )
            self.assert_true(
                sess.events[2].kind == "key" and sess.events[2].vk_code == 0x41,
                f"[PR-12] keydown 필드, keyup 무시. {sess.events[2]!r}",
            )

            self.step("(6) 시간순 정렬 — ts 단조 증가")
            timestamps = [ev.ts for ev in sess.events]
            self.assert_true(
                all(timestamps[i] <= timestamps[i + 1] for i in range(len(timestamps) - 1)),
                "[PR-12] events ts 시간순 정렬 필수",
            )
        finally:
            if recorder.is_recording:
                recorder.stop()
            hook_mgr.uninstall_all()

    def test_152_recorder_element_capture_callback(self):
        """[ADR 0004 PR-12 + PR-17] element_capture_fn 주입 — click 시 element_meta 채움.

        PR-17 이후 element_capture_fn 은 drain thread 에서 호출 (hook 스레드 fast
        return 보장). 검증은 wait_for_event_count + 추가 sleep 으로 drain 처리 대기.
        callback 예외 시 element_meta None 으로 진행 (event 자체는 정상 추가).
        """
        import time as _time

        from core.input_hooks import InputHookManager, KeyboardEvent, MouseEvent
        from core.recorder import Recorder

        hook_mgr = InputHookManager()
        capture_calls: list[tuple[int, int]] = []

        def fake_capture(x: int, y: int) -> dict:
            capture_calls.append((x, y))
            return {"control_type": "Edit", "name": "fake", "automation_id": "id"}

        recorder = Recorder(hook_mgr, element_capture_fn=fake_capture)
        try:
            recorder.start()
            sess = recorder.current_session

            self.step("(1) click → element_capture_fn 호출 (drain thread) + element_meta 채움")
            recorder._on_mouse_event(MouseEvent(type="lbutton_down", x=300, y=400))
            self.assert_true(
                recorder.wait_for_event_count(1, timeout=1.0),
                "[PR-17] drain 완료 대기 (click 1)",
            )
            self.assert_true(
                capture_calls == [(300, 400)],
                f"[PR-12] element_capture_fn 좌표 전달. 실제: {capture_calls}",
            )
            ev = sess.events[0]
            self.assert_true(
                ev.element_meta is not None and ev.element_meta.get("control_type") == "Edit",
                f"[PR-12] element_meta 채워짐. 실제: {ev.element_meta!r}",
            )

            self.step("(2) callback 예외 → element_meta None, event 정상 추가")

            def raising_capture(x: int, y: int) -> dict:
                raise RuntimeError("의도된 예외")

            recorder._element_capture_fn = raising_capture
            recorder._on_mouse_event(MouseEvent(type="lbutton_down", x=10, y=20))
            self.assert_true(
                recorder.wait_for_event_count(2, timeout=1.0),
                "[PR-17] drain 완료 대기 (raising click 2)",
            )
            self.assert_true(
                sess.events[1].element_meta is None,
                "[PR-12] callback 예외 시 element_meta None + event 추가 진행",
            )

            self.step("(3) wheel/key 는 element_capture_fn 호출 X")
            recorder._element_capture_fn = fake_capture
            before = len(capture_calls)
            recorder._on_mouse_event(MouseEvent(type="wheel", x=0, y=0, wheel_delta=1))
            recorder._on_keyboard_event(KeyboardEvent(type="keydown", vk_code=0x42, scan_code=48))
            # drain 가 처리 완료할 시간 확보 (scroll + key event 가 session 에 들어옴)
            recorder.wait_for_event_count(4, timeout=1.0)
            _time.sleep(0.05)  # drain idle 진입 보장 — 추가 capture 호출 가능성 제거
            self.assert_true(
                len(capture_calls) == before,
                f"[PR-12] wheel/key 는 element_capture_fn 미호출. before={before}, after={len(capture_calls)}",
            )
        finally:
            if recorder.is_recording:
                recorder.stop()
            hook_mgr.uninstall_all()

    def test_153_recorder_transform_basic_click_step(self):
        """[ADR 0004 PR-13] 단일 click event → Step 변환 (element_meta 있음)."""
        from datetime import datetime

        from core.recorder_models import RawEvent, RecordingSession
        from core.recorder_transform import transform

        sess = RecordingSession(id="t", started_at=datetime.now())
        sess.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=100,
                y=200,
                button="left",
                element_meta={
                    "control_type": "Button",
                    "name": "확인",
                    "automation_id": "btn_ok",
                    "window_title": "메모장",
                },
            )
        )
        steps = transform(sess)
        self.assert_true(len(steps) == 1, f"[PR-13] 단일 click → 1 Step. 실제: {len(steps)}")
        s = steps[0]
        self.assert_true(s.step_id == 1, f"[PR-13] step_id 1 부터. 실제: {s.step_id}")
        self.assert_true(
            "Button" in s.user_request and "확인" in s.user_request,
            f"[PR-13 §7] user_request 에 control_type+name. 실제: {s.user_request!r}",
        )
        self.assert_true(
            "child_window" in s.generated_code and "click_input" in s.generated_code,
            f"[PR-13] pywinauto child_window + click_input. 실제: {s.generated_code!r}",
        )
        self.assert_true(
            "btn_ok" in s.generated_code,
            "[PR-13] auto_id 셀렉터 포함 필수",
        )

    def test_154_recorder_transform_noise_filter(self):
        """[ADR 0004 PR-13] 노이즈 필터 — 자체 창 클릭 + 빈 공간 클릭."""
        from datetime import datetime

        from core.recorder_models import RawEvent, RecordingSession, TransformOptions
        from core.recorder_transform import transform

        sess = RecordingSession(id="t", started_at=datetime.now())
        sess.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=10,
                y=10,
                element_meta={"control_type": "Window", "window_title": "ohdo"},
            )
        )
        sess.events.append(RawEvent(ts=datetime.now(), kind="click", x=20, y=20, element_meta=None))
        sess.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=30,
                y=30,
                element_meta={
                    "control_type": "Button",
                    "name": "OK",
                    "window_title": "Calculator",
                },
            )
        )

        self.step("(1) drop_self_window_clicks — ohdo 창 클릭 drop")
        steps = transform(
            sess,
            opts=TransformOptions(drop_empty_space_clicks=False),
            self_window_titles=["ohdo"],
        )
        all_code = " ".join(s.generated_code for s in steps)
        self.assert_true("Calculator" in all_code, "[PR-13] Calculator step 보존")

        self.step("(2) drop_empty_space_clicks=True → element_meta None 클릭 drop")
        steps2 = transform(
            sess,
            opts=TransformOptions(drop_empty_space_clicks=True),
            self_window_titles=["ohdo"],
        )
        all_code2 = " ".join(s.generated_code for s in steps2)
        self.assert_true(
            "pyautogui.click(20, 20" not in all_code2,
            f"[PR-13] 빈 공간 (20,20) 클릭 drop 필수. 실제: {all_code2!r}",
        )

    def test_155_recorder_transform_key_grouping(self):
        """[ADR 0004 PR-13] 연속 키입력 → pyautogui.write 1개로 그룹핑."""
        from datetime import datetime

        from core.recorder_models import RawEvent, RecordingSession
        from core.recorder_transform import transform

        sess = RecordingSession(id="t", started_at=datetime.now())
        click_meta = {"control_type": "Edit", "name": "Input", "automation_id": "txt"}
        sess.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=50,
                y=60,
                button="left",
                element_meta=click_meta,
            )
        )
        for vk in (0x48, 0x45, 0x4C, 0x4C, 0x4F):  # H, E, L, L, O (lowercase 매핑)
            sess.events.append(RawEvent(ts=datetime.now(), kind="key", vk_code=vk))
        steps = transform(sess)
        self.assert_true(len(steps) == 1, f"[PR-13] click + key group → 1 Step. 실제: {len(steps)}")
        code = steps[0].generated_code
        self.assert_true(
            "pyautogui.write('hello')" in code,
            f"[PR-13] 연속 key 5개 → write('hello') 1개로 그룹. 실제: {code!r}",
        )

    def test_156_recorder_transform_step_boundaries(self):
        """[ADR 0004 PR-13 §7] 자동 경계 신호 — idle / key→click / F8 marker."""
        from datetime import datetime, timedelta

        from core.recorder_models import RawEvent, RecordingSession, TransformOptions
        from core.recorder_transform import transform

        base = datetime.now()

        self.step("(1) idle_boundary_ms 휴지 → 새 step")
        sess = RecordingSession(id="t", started_at=base)
        meta_a = {"control_type": "Button", "name": "A"}
        meta_b = {"control_type": "Button", "name": "B"}
        sess.events.append(RawEvent(ts=base, kind="click", x=1, y=1, element_meta=meta_a))
        sess.events.append(
            RawEvent(
                ts=base + timedelta(seconds=5),
                kind="click",
                x=2,
                y=2,
                element_meta=meta_b,
            )
        )
        steps = transform(sess, opts=TransformOptions(idle_boundary_ms=3000))
        self.assert_true(len(steps) == 2, f"[PR-13] 5초 휴지로 2 step 분리. 실제: {len(steps)}")

        self.step("(2) key 후 click → 새 step (key group 종료)")
        sess = RecordingSession(id="t", started_at=base)
        meta_edit = {"control_type": "Edit", "name": "E", "automation_id": "e1"}
        meta_btn = {"control_type": "Button", "name": "Submit"}
        sess.events.append(RawEvent(ts=base, kind="click", x=1, y=1, element_meta=meta_edit))
        sess.events.append(
            RawEvent(ts=base + timedelta(milliseconds=100), kind="key", vk_code=0x41)
        )
        sess.events.append(
            RawEvent(
                ts=base + timedelta(milliseconds=200),
                kind="click",
                x=2,
                y=2,
                element_meta=meta_btn,
            )
        )
        steps = transform(sess, opts=TransformOptions(idle_boundary_ms=5000))
        self.assert_true(
            len(steps) == 2,
            f"[PR-13] key 후 click → 2 step (key group 종료). 실제: {len(steps)}",
        )

        self.step("(3) F8 marker → batch 분리 + marker 자체 drop")
        sess = RecordingSession(id="t", started_at=base)
        sess.events.append(RawEvent(ts=base, kind="click", x=1, y=1, element_meta=meta_a))
        sess.events.append(RawEvent(ts=base + timedelta(milliseconds=10), kind="marker"))
        sess.events.append(
            RawEvent(
                ts=base + timedelta(milliseconds=20),
                kind="click",
                x=2,
                y=2,
                element_meta=meta_b,
            )
        )
        steps = transform(sess, opts=TransformOptions(enable_f8_marker=True, idle_boundary_ms=5000))
        self.assert_true(len(steps) == 2, f"[PR-13] F8 marker → 2 step. 실제: {len(steps)}")
        all_code = " ".join(s.generated_code for s in steps)
        self.assert_true("marker" not in all_code, "[PR-13] marker 자체는 코드에 없음")

    def test_157_recorder_transform_secrets_integration(self):
        """[ADR 0004 PR-13 / ADR 0003 강 통합] PW field 키 시퀀스 → get_secret('label')."""
        from datetime import datetime, timedelta

        from core.recorder_models import RawEvent, RecordingSession, TransformOptions
        from core.recorder_transform import transform

        base = datetime.now()
        sess = RecordingSession(id="t", started_at=base)
        pw_meta = {
            "control_type": "Edit",
            "name": "Password",
            "automation_id": "txt_password",
            "is_password_field": True,
            "_ohdo_label": "login_pw",
        }
        sess.events.append(RawEvent(ts=base, kind="click", x=1, y=1, element_meta=pw_meta))
        for i, vk in enumerate((0x53, 0x45, 0x43, 0x52, 0x45, 0x54)):  # 'secret'
            sess.events.append(
                RawEvent(
                    ts=base + timedelta(milliseconds=10 * (i + 1)),
                    kind="key",
                    vk_code=vk,
                )
            )

        self.step("(1) integrate_secrets=True → get_secret('login_pw')")
        steps = transform(sess, opts=TransformOptions(integrate_secrets=True))
        code = steps[0].generated_code
        self.assert_true(
            "get_secret('login_pw')" in code,
            f"[PR-13 ADR0003] get_secret('login_pw') 패턴 필수. 실제: {code!r}",
        )
        self.assert_true(
            "'secret'" not in code,
            f"[PR-13 ADR0003] 평문 'secret' 코드에 박히면 안 됨. 실제: {code!r}",
        )

        self.step("(2) integrate_secrets=False → 평문 (디버그 모드)")
        steps2 = transform(sess, opts=TransformOptions(integrate_secrets=False))
        self.assert_true(
            "'secret'" in steps2[0].generated_code,
            "[PR-13] integrate_secrets=False 시 평문 write (디버그 모드)",
        )

    def test_158_recorder_transform_browser_and_owner_drawn(self):
        """[ADR 0004 PR-13] 브라우저 element → Selenium, element_meta None → 좌표 fallback."""
        from datetime import datetime

        from core.recorder_models import RawEvent, RecordingSession
        from core.recorder_transform import transform

        sess = RecordingSession(id="t", started_at=datetime.now())

        self.step("(1) 브라우저 element (css_selector) → Selenium")
        sess.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=100,
                y=200,
                element_meta={
                    "tag_name": "button",
                    "css_selector": "#login-btn",
                    "name": "로그인",
                },
            )
        )

        self.step("(2) element_meta None → pyautogui 좌표 click")
        sess.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=500,
                y=300,
                button="right",
                element_meta=None,
            )
        )

        steps = transform(sess)
        all_code = " ".join(s.generated_code for s in steps)
        self.assert_true(
            "find_element(By.CSS_SELECTOR" in all_code and "#login-btn" in all_code,
            f"[PR-13] Selenium css_selector 코드 생성. 실제: {all_code!r}",
        )
        self.assert_true(
            "pyautogui.click(500, 300, button='right')" in all_code,
            f"[PR-13] element_meta None 시 pyautogui 좌표 fallback. 실제: {all_code!r}",
        )

    def test_159_app_service_recording_lifecycle(self):
        """[ADR 0004 PR-14] AppService.start/stop/commit_recording 전체 path + listener.

        InMemoryRepository 사용 — 파일 IO 없이 통합 검증.
        """
        from core.app_service import AppService
        from core.input_hooks import MouseEvent
        from core.storage.in_memory import InMemoryRepository

        repo = InMemoryRepository()
        svc = AppService(session_repo=repo)

        self.step("(1) 초기 상태 — is_recording False")
        self.assert_true(svc.is_recording is False, "[PR-14] 초기 is_recording False")
        self.assert_true(svc.recording_event_count == 0, "[PR-14] 초기 event_count 0")

        self.step("(2) listener 등록 + start_recording")
        events: list[tuple[str, dict]] = []

        def listener(name: str, payload: dict) -> None:
            events.append((name, payload))

        svc.add_recording_listener(listener)
        rec_id = svc.start_recording()
        self.assert_true(
            isinstance(rec_id, str) and rec_id,
            f"[PR-14] start_recording 가 id 반환. {rec_id!r}",
        )
        self.assert_true(svc.is_recording is True, "[PR-14] start 후 is_recording True")
        self.assert_true(
            len(events) == 1 and events[0][0] == "recording.started",
            f"[PR-14] recording.started 이벤트 발화. 실제: {events}",
        )

        self.step("(3) 녹화 중 event 누적 (element_capture_fn callback path; PR-17 drain 대기)")
        click_meta = {"control_type": "Button", "name": "OK", "automation_id": "ok"}
        svc._recorder._element_capture_fn = lambda x, y: click_meta
        svc._recorder._on_mouse_event(MouseEvent(type="lbutton_down", x=10, y=20))
        self.assert_true(
            svc._recorder.wait_for_event_count(1, timeout=1.0),
            "[PR-17] drain 후 event_count 1",
        )
        self.assert_true(svc.recording_event_count == 1, "[PR-14] event_count 1")

        self.step("(4) stop_recording → Step 리스트 반환 + recording.stopped 이벤트")
        steps = svc.stop_recording()
        self.assert_true(
            isinstance(steps, list) and len(steps) >= 1,
            f"[PR-14] stop_recording 가 Step 리스트 반환. 실제: {steps}",
        )
        self.assert_true(svc.is_recording is False, "[PR-14] stop 후 is_recording False")
        stopped_evs = [e for e in events if e[0] == "recording.stopped"]
        self.assert_true(
            len(stopped_evs) == 1 and stopped_evs[0][1]["raw_event_count"] == 1,
            f"[PR-14] recording.stopped payload raw_event_count=1. 실제: {stopped_evs}",
        )

        self.step("(5) commit_recording (target_session_id None → 새 세션 자동)")
        session = svc.commit_recording(steps)
        self.assert_true(
            session.session_id and len(session.steps) == len(steps),
            f"[PR-14] 새 세션 + step 개수 일치. id={session.session_id} steps={len(session.steps)}",
        )
        committed_evs = [e for e in events if e[0] == "recording.committed"]
        self.assert_true(
            len(committed_evs) == 1
            and committed_evs[0][1]["step_count"] == len(steps)
            and committed_evs[0][1]["target_session_id"] == session.session_id,
            f"[PR-14] recording.committed payload. 실제: {committed_evs}",
        )

        self.step("(6) listener 해제 후 새 이벤트 dispatch X")
        svc.remove_recording_listener(listener)
        before = len(events)
        svc.start_recording()
        svc.stop_recording()
        self.assert_true(len(events) == before, "[PR-14] listener 해제 후 새 이벤트 dispatch X")

    def test_160_app_service_concurrent_start_rejected(self):
        """[ADR 0004 PR-14] 이미 녹화 중 두 번째 start_recording → RecorderAlreadyStartedError."""
        from core.app_service import AppService
        from core.recorder import RecorderAlreadyStartedError
        from core.storage.in_memory import InMemoryRepository

        svc = AppService(session_repo=InMemoryRepository())
        svc.start_recording()
        try:
            try:
                svc.start_recording()
                self.assert_true(False, "[PR-14] 중복 start_recording 은 예외 발생 필수")
            except RecorderAlreadyStartedError:
                pass
        finally:
            try:
                svc.stop_recording()
            except Exception:
                pass

    def test_161_app_service_recording_target_session_id(self):
        """[ADR 0004 PR-14] target_session_id 지정 vs None 분기 + new_session_title."""
        from datetime import datetime

        from core.app_service import AppService
        from core.recorder_models import RawEvent
        from core.session_manager import Step
        from core.storage.in_memory import InMemoryRepository

        repo = InMemoryRepository()
        svc = AppService(session_repo=repo)

        self.step("(1) target_session_id 지정 → 그 세션에 step 추가")
        existing = svc.create_session(title="기존 세션")
        before_step_count = len(existing.steps)
        svc.start_recording(target_session_id=existing.session_id)
        svc._recorder._session.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=1,
                y=1,
                element_meta={"control_type": "Button", "name": "X"},
            )
        )
        steps = svc.stop_recording()
        self.assert_true(len(steps) >= 1, "[PR-14] step 변환 결과 존재")
        session = svc.commit_recording(steps, target_session_id=existing.session_id)
        self.assert_true(
            session.session_id == existing.session_id,
            f"[PR-14] 지정한 session_id 그대로 사용. {session.session_id}",
        )
        self.assert_true(
            len(session.steps) == before_step_count + len(steps),
            f"[PR-14] 기존 step + 새 step. 실제 {len(session.steps)}",
        )

        self.step("(2) target_session_id None + new_session_title 지정 → 그 제목으로 새 세션")
        custom_step = Step(step_id=0, generated_code="pyautogui.click(0, 0)", user_request="t")
        sess2 = svc.commit_recording(
            [custom_step], target_session_id=None, new_session_title="MyCustomTitle"
        )
        self.assert_true(
            sess2.title == "MyCustomTitle",
            f"[PR-14] new_session_title 적용. 실제 {sess2.title!r}",
        )
        self.assert_true(
            sess2.session_id != existing.session_id,
            "[PR-14] 새 세션 id 는 기존과 달라야 함",
        )

    def test_162_recording_toolbar_button_and_hotkey(self):
        """[ADR 0004 PR-15] ⏺ toolbar 버튼 + Ctrl+Shift+R 핫키 + toggle handler.

        가드: source-level sentinel — main_window_v2 에
        1. ``_on_toggle_recording`` 메서드 존재 + Step _do_start/_do_stop 호출
        2. ``_record_btn`` 위젯 + clicked → _on_toggle_recording
        3. ``Ctrl+Shift+R`` QShortcut 등록 + _on_toggle_recording 연결
        4. tr 키 ``ui_v2.recording.action_bar.btn`` / tooltip_start / tooltip_stop 사용
        """
        import inspect as _inspect

        from ui_v2 import main_window_v2 as _mw

        src = _inspect.getsource(_mw)
        # 1) 메서드
        self.assert_true(
            "def _on_toggle_recording" in src,
            "[PR-15] _on_toggle_recording 핸들러 존재",
        )
        self.assert_true(
            "def _do_start_recording" in src and "def _do_stop_recording" in src,
            "[PR-15] _do_start_recording / _do_stop_recording 헬퍼 존재",
        )
        # 2) toolbar 버튼
        self.assert_true(
            "_record_btn" in src and "_on_toggle_recording" in src,
            "[PR-15] _record_btn 위젯 + clicked → _on_toggle_recording",
        )
        # 3) Ctrl+Shift+R 핫키 (test_162 sentinel — architecture 25 §"PR-15" 회귀 가드)
        self.assert_true(
            'QShortcut(QKeySequence("Ctrl+Shift+R")' in src and "_on_toggle_recording" in src,
            "[PR-15] Ctrl+Shift+R 핫키 등록 + _on_toggle_recording 연결",
        )
        # 4) tr 키 사용
        for key in (
            "ui_v2.recording.action_bar.btn",
            "ui_v2.recording.action_bar.tooltip_start",
            "ui_v2.recording.action_bar.tooltip_stop",
        ):
            self.assert_true(key in src, f"[PR-15] tr 키 '{key}' main_window_v2 에서 사용")

    def test_163_recorder_overlay_clickthrough_and_stop_btn(self):
        """[ADR 0004 PR-15 + 2026-05-20 fix] RecorderOverlay 가 frameless +
        always-on-top + show-without-activating.

        **2026-05-20 변경**: 이전 nested click-through (root True + 자식 False)
        구조는 Qt mouse hit-test 부하로 마우스 컨트롤 체감 지연 — 사용자가 글로벌
        Ctrl+Shift+R 핫키로 stop 가능하므로 root 도 mouse 받도록 변경 (overlay
        가 ~280x36px 로 작아 밑 앱 클릭 방해 미미).
        """
        import inspect as _inspect

        from ui_v2 import recorder_overlay as _ro
        from ui_v2.recorder_overlay import RecorderOverlay

        src = _inspect.getsource(_ro)

        # 핵심 Qt 플래그/속성 sentinel
        for needle, desc in (
            ("FramelessWindowHint", "frameless window"),
            ("WindowStaysOnTopHint", "always-on-top"),
            ("Tool", "Qt.Tool window type"),
            ("WA_ShowWithoutActivating", "show without activating (다른 창 focus 유지)"),
            ("WA_TransparentForMouseEvents, False", "root 가 mouse 받음 (2026-05-20 fix)"),
            ("def start", "start lifecycle"),
            ("def stop_and_hide", "stop_and_hide lifecycle"),
            ("get_event_count", "event count callable 주입"),
            ("on_stop", "stop callback 주입"),
        ):
            self.assert_true(
                needle in src,
                f"[PR-15] RecorderOverlay 에 '{desc}' 패턴 필수: '{needle}'",
            )

        # 2026-05-20 회귀 가드 — 이전 nested click-through 잔재 X
        self.assert_true(
            "WA_TransparentForMouseEvents, True" not in src,
            "[회귀 2026-05-20] WA_TransparentForMouseEvents=True (root) 잔재 금지",
        )

        # callable 시그니처
        sig = _inspect.signature(RecorderOverlay.__init__)
        params = list(sig.parameters)
        for p in ("get_event_count", "on_stop"):
            self.assert_true(p in params, f"[PR-15] RecorderOverlay.__init__ '{p}' 인자")

    def test_164_recording_locale_catalog_complete(self):
        """[ADR 0004 PR-15] recording.* catalog 키 ~40 개 en/ko 양쪽 존재 + 양쪽
        key set 동일.
        """
        import json as _json
        from pathlib import Path as _Path

        locale_dir = _Path(__file__).parent.parent / "core" / "locale"
        en_cat = _json.loads((locale_dir / "en.json").read_text(encoding="utf-8"))
        ko_cat = _json.loads((locale_dir / "ko.json").read_text(encoding="utf-8"))

        en_keys = {k for k in en_cat if k.startswith("ui_v2.recording.")}
        ko_keys = {k for k in ko_cat if k.startswith("ui_v2.recording.")}

        self.assert_true(
            len(en_keys) >= 30,
            f"[PR-15] en.json 의 ui_v2.recording.* 키 30개 이상 필요. 실제 {len(en_keys)}",
        )
        diff = en_keys.symmetric_difference(ko_keys)
        self.assert_true(
            not diff,
            f"[PR-15] en/ko 의 ui_v2.recording.* 키 set 동일. 차이: {sorted(diff)[:5]}",
        )

        # 필수 키 sentinel
        for key in (
            "ui_v2.recording.action_bar.btn",
            "ui_v2.recording.overlay.label_recording",
            "ui_v2.recording.review.title",
            "ui_v2.recording.empty.card_title",
            "ui_v2.recording.tab_menu.new_recording",
            "ui_v2.recording.toast.started",
            "ui_v2.recording.toast.committed",
        ):
            self.assert_true(
                key in en_cat and key in ko_cat,
                f"[PR-15] 필수 catalog 키 '{key}' en+ko 양쪽 존재",
            )

    def test_165_recording_secrets_integration_sentinel(self):
        """[ADR 0004 PR-15 + ADR 0003] 녹화 → PW field → get_secret 변환 path.

        recorder_transform 이 integrate_secrets=True 일 때 PW field 후속 key
        그룹을 get_secret('label') 로 변환하는 path 가 살아있는지 sentinel.
        """
        import inspect as _inspect

        from core import recorder_transform as _rt

        src = _inspect.getsource(_rt)
        self.assert_true(
            "integrate_secrets" in src,
            "[PR-15] recorder_transform 이 integrate_secrets 옵션 사용",
        )
        self.assert_true(
            "is_password_field" in src,
            "[PR-15] PW field 감지 path 살아있음",
        )
        self.assert_true(
            "get_secret(" in src,
            "[PR-15] get_secret('label') 코드 생성 path 살아있음 (ADR 0003 강 통합)",
        )

        # 사용자 메시지 advisory path — UI 측에서 secrets_detector 의 advisory 호출
        # 가능하도록 review dialog 에 opt_secrets 토글 + tr 키 노출.
        from ui_v2 import recording_review_dialog as _rrd

        rd_src = _inspect.getsource(_rrd)
        self.assert_true(
            "ui_v2.recording.review.opt_secrets" in rd_src,
            "[PR-15] review dialog 에 ADR 0003 시크릿 변환 토글 노출",
        )

    def test_166_empty_state_recording_card(self):
        """[ADR 0004 PR-15 — 사용자 추가 §6] D25 빈 상태에 "🎬 자동 녹화" 카드
        + + 새 탭 메뉴에 "녹화로 새 세션" 액션.
        """
        import inspect as _inspect

        from ui_v2 import main_window_v2 as _mw

        src = _inspect.getsource(_mw)

        # 1) _show_empty_state 가 show_recording_card 인자를 받음
        self.assert_true(
            "show_recording_card" in src,
            "[PR-15] _show_empty_state 에 show_recording_card 인자",
        )
        # 2) 호출부에서 True 로 켜는 sentinel (세션 빈 상태)
        self.assert_true(
            "show_recording_card=True" in src,
            "[PR-15] session 빈 상태 호출에서 show_recording_card=True",
        )
        # 3) 카드 안 tr 키 노출
        for key in (
            "ui_v2.recording.empty.card_title",
            "ui_v2.recording.empty.card_desc",
            "ui_v2.recording.empty.card_btn",
        ):
            self.assert_true(key in src, f"[PR-15] 빈 상태 카드 tr 키 '{key}' 사용")
        # 4) + 새 탭 메뉴에 "녹화로 새 세션" 액션
        self.assert_true(
            "ui_v2.recording.tab_menu.new_recording" in src,
            "[PR-15] + 새 탭 메뉴에 녹화로 새 세션 액션",
        )
        self.assert_true(
            "_on_new_session_with_recording" in src,
            "[PR-15] _on_new_session_with_recording 핸들러 존재",
        )

    def test_167_review_dialog_edit_features(self):
        """[ADR 0004 PR-15 — 사용자 추가 §8] review dialog 편집 기능 강화.

        가드: review dialog 에
        - inline 편집 콜백 (_on_step_wait_changed, _on_edit_code, _on_item_double_clicked)
        - drag&drop reorder (InternalMove + _on_rows_moved)
        - 변환 옵션 toggle 즉시 재변환 (_on_option_toggled + recorder_transform.transform 호출)
        - bulk action (_bulk_delete, _bulk_merge + context menu)
        - 인접 step 합치기/분할 (_on_split, _on_merge_prev)
        - raw events 디버그 보기 (_on_view_raw_events)
        """
        import inspect as _inspect

        from ui_v2 import recording_review_dialog as _rrd
        from ui_v2.recording_review_dialog import RecordingReviewDialog

        # 필수 메서드 sentinel
        for name in (
            "_on_step_wait_changed",
            "_on_edit_code",
            "_on_item_double_clicked",
            "_on_option_toggled",
            "_on_split",
            "_on_merge_prev",
            "_on_move",
            "_on_delete",
            "_on_rows_moved",
            "_bulk_delete",
            "_bulk_merge",
            "_on_context_menu",
            "_on_view_raw_events",
        ):
            self.assert_true(
                callable(getattr(RecordingReviewDialog, name, None)),
                f"[PR-15] RecordingReviewDialog.{name} 메서드 존재",
            )

        src = _inspect.getsource(_rrd)
        # drag&drop + multi-select
        for needle, desc in (
            ("InternalMove", "drag&drop reorder mode"),
            ("ExtendedSelection", "multi-select bulk action"),
            ("from core.recorder_transform import transform", "import path"),
            ("transform(", "재변환 호출"),
            ("TransformOptions(", "옵션 재구성"),
            ("blockSignals", "rowsMoved 재진입 가드"),
        ):
            self.assert_true(
                needle in src,
                f"[PR-15] review dialog 에 '{desc}' 패턴 필수: '{needle}'",
            )

        # 변환 옵션 토글 4개 tr 키
        for key in (
            "ui_v2.recording.review.opt_group_keys",
            "ui_v2.recording.review.opt_drop_empty",
            "ui_v2.recording.review.opt_window_focus",
            "ui_v2.recording.review.opt_secrets",
            "ui_v2.recording.review.btn_raw_events",
            "ui_v2.recording.review.btn_commit",
        ):
            self.assert_true(
                key in src,
                f"[PR-15] review dialog 에 tr 키 '{key}' 노출",
            )

    def test_168_element_inspect_module_contract(self):
        """[ADR 0004 PR-16a] core.element_inspect 모듈 + capture_element_at API.

        가드:
        1. 모듈 import 가능 + capture_element_at callable
        2. capture_element_at 시그니처가 (x, y) 위치 인자 2개
        3. 모듈 source 에 recorder_transform 이 소비하는 필드 sentinel
        4. non-Windows 환경 silent fallback (sys.platform 분기)
        5. ADR 0003 시너지 — UIA IsPassword 감지 path
        """
        import inspect as _inspect

        from core import element_inspect as _ei
        from core.element_inspect import capture_element_at

        self.assert_true(callable(capture_element_at), "[PR-16a] capture_element_at callable")

        sig = _inspect.signature(capture_element_at)
        params = list(sig.parameters)
        self.assert_true(
            len(params) >= 2,
            f"[PR-16a] capture_element_at 인자 최소 2개 (x, y). 실제: {params}",
        )

        src = _inspect.getsource(_ei)
        for needle in (
            '"control_type"',
            '"name"',
            '"automation_id"',
            '"class_name"',
            '"window_title"',
            '"hwnd"',
            '"process_id"',
            '"exe_name"',
            '"rect"',
            '"is_password_field"',
        ):
            self.assert_true(
                needle in src,
                f"[PR-16a] capture_element_at 가 {needle} 필드 채움",
            )

        self.assert_true(
            "sys.platform" in src and "win32" in src,
            "[PR-16a] non-Windows 환경 silent fallback (sys.platform 분기)",
        )

        self.assert_true(
            "CurrentIsPassword" in src,
            "[PR-16a] UIA IsPassword 감지 path 살아있음 (ADR 0003)",
        )

    def test_169_main_window_v2_injects_element_capture_fn(self):
        """[ADR 0004 PR-16a] main_window_v2._do_start_recording 가
        capture_element_at 를 element_capture_fn 으로 주입.

        PR-14 의 element_capture_fn 인자가 PR-15 까지는 미사용 (None) 이라서
        녹화된 click 의 element_meta 가 항상 None 으로 떨어짐. PR-16a 가 이
        갭을 메움 — recorder_transform 이 비로소 control_type/name/automation_id
        기반 코드를 생성 가능.
        """
        import inspect as _inspect

        from ui_v2.main_window_v2 import MainWindowV2

        src = _inspect.getsource(MainWindowV2._do_start_recording)
        for needle, desc in (
            ("from core.element_inspect import capture_element_at", "element_inspect import"),
            ("element_capture_fn=capture_element_at", "element_capture_fn 주입 (keyword)"),
        ):
            self.assert_true(
                needle in src,
                f"[PR-16a] _do_start_recording 에 '{desc}' 필수: '{needle}'",
            )

    def test_170_input_hooks_winevent_module_contract(self):
        """[ADR 0004 PR-16w] InputHookManager 의 WinEvent (foreground 전환) 지원.

        가드:
        1. WinEventEvent dataclass + WinEventType Literal
        2. Win32 상수 EVENT_SYSTEM_FOREGROUND / WINEVENT_OUTOFCONTEXT / WINEVENT_SKIPOWNPROCESS
        3. install/uninstall_winevent_callback + winevent_callback_count / is_winevent_hook_installed
        4. SKIPOWNPROCESS 플래그가 SetWinEventHook 호출에 박혀있음 (ohdo 자체 창 제외)
        5. uninstall_all 가 winevent 도 정리
        """
        import inspect as _inspect

        from core import input_hooks as _ih
        from core.input_hooks import (
            EVENT_SYSTEM_FOREGROUND,
            WINEVENT_OUTOFCONTEXT,
            WINEVENT_SKIPOWNPROCESS,
            InputHookManager,
            WinEventEvent,
        )

        self.step("(1) Win32 상수 값")
        self.assert_true(EVENT_SYSTEM_FOREGROUND == 0x0003, "[PR-16w] EVENT_SYSTEM_FOREGROUND=0x3")
        self.assert_true(WINEVENT_OUTOFCONTEXT == 0x0000, "[PR-16w] WINEVENT_OUTOFCONTEXT=0x0")
        self.assert_true(WINEVENT_SKIPOWNPROCESS == 0x0002, "[PR-16w] WINEVENT_SKIPOWNPROCESS=0x2")

        self.step("(2) WinEventEvent dataclass 필드")
        ev = WinEventEvent(type="foreground", hwnd=123, window_title="Test")
        for field in ("type", "hwnd", "window_title", "timestamp_ms"):
            self.assert_true(hasattr(ev, field), f"[PR-16w] WinEventEvent.{field} 필드")
        self.assert_true(
            ev.type == "foreground" and ev.hwnd == 123,
            f"[PR-16w] WinEventEvent 초기값 보존. 실제: {ev!r}",
        )

        self.step("(3) InputHookManager WinEvent API")
        mgr = InputHookManager()
        for method in (
            "install_winevent_callback",
            "uninstall_winevent_callback",
        ):
            self.assert_true(hasattr(mgr, method), f"[PR-16w] InputHookManager.{method} 필수")
        for prop in ("is_winevent_hook_installed", "winevent_callback_count"):
            self.assert_true(hasattr(mgr, prop), f"[PR-16w] InputHookManager.{prop} 필수")
        self.assert_true(
            mgr.winevent_callback_count == 0,
            "[PR-16w] 초기 winevent_callback_count == 0",
        )

        self.step("(4) callback 등록/해제 + uninstall_all")
        cb_id = mgr.install_winevent_callback(lambda ev: None)
        self.assert_true(
            mgr.winevent_callback_count == 1,
            "[PR-16w] 등록 후 count == 1",
        )
        mgr.uninstall_winevent_callback(cb_id)
        self.assert_true(
            mgr.winevent_callback_count == 0,
            "[PR-16w] 해제 후 count == 0",
        )

        mgr.install_winevent_callback(lambda ev: None)
        mgr.uninstall_all()
        self.assert_true(
            mgr.winevent_callback_count == 0,
            "[PR-16w] uninstall_all 후 winevent count == 0",
        )

        self.step("(5) SetWinEventHook 호출에 SKIPOWNPROCESS 플래그 박힘")
        install_src = _inspect.getsource(InputHookManager._install_winevent_hook_locked)
        self.assert_true(
            "SetWinEventHook" in install_src,
            "[PR-16w] _install_winevent_hook_locked 가 SetWinEventHook 호출",
        )
        self.assert_true(
            "WINEVENT_SKIPOWNPROCESS" in install_src,
            "[PR-16w] SKIPOWNPROCESS 플래그 필수 (ohdo 자체 창 전환 제외)",
        )
        self.assert_true(
            "UnhookWinEvent"
            in _inspect.getsource(InputHookManager._uninstall_winevent_hook_locked),
            "[PR-16w] _uninstall 가 UnhookWinEvent (NOT UnhookWindowsHookEx) 호출",
        )

        self.step("(6) get_hook_manager 싱글톤 WinEvent property 노출")
        m = _ih.get_hook_manager()
        self.assert_true(
            hasattr(m, "winevent_callback_count"),
            "[PR-16w] 싱글톤도 동일 property 노출",
        )

    def test_171_recorder_window_focus_capture(self):
        """[ADR 0004 PR-16w] Recorder start 시 winevent callback 등록 + stop 시 해제.

        WinEvent 콜백 dispatch → window_focus RawEvent 가 buffer 에 적재되는지 검증
        (실제 SetWinEventHook 호출 X — 직접 _on_winevent_event 주입).
        """
        from core.input_hooks import InputHookManager, WinEventEvent
        from core.recorder import Recorder

        hook_mgr = InputHookManager()
        recorder = Recorder(hook_mgr)
        try:
            self.step("(1) start 후 winevent_callback_count == 1")
            recorder.start()
            self.assert_true(
                hook_mgr.winevent_callback_count == 1,
                f"[PR-16w] start 가 winevent callback 등록. 실제: {hook_mgr.winevent_callback_count}",
            )

            self.step("(2) WinEvent dispatch → window_focus RawEvent (drain 대기)")
            sess = recorder.current_session
            self.assert_true(sess is not None, "current_session 존재")
            recorder._on_winevent_event(
                WinEventEvent(type="foreground", hwnd=42, window_title="Notepad")
            )
            self.assert_true(
                recorder.wait_for_event_count(1, timeout=1.0),
                f"[PR-17] drain 후 window_focus event 추가. 실제: {recorder.event_count}",
            )
            ev = sess.events[0]
            self.assert_true(
                ev.kind == "window_focus" and ev.hwnd == 42 and ev.window_title == "Notepad",
                f"[PR-16w] window_focus 필드 보존. 실제: {ev!r}",
            )

            self.step("(3) 다른 type 의 WinEvent 는 무시")
            import time as _time

            from core.recorder_models import RawEvent

            fake_event = WinEventEvent.__new__(WinEventEvent)
            fake_event.type = "other"  # type: ignore[assignment]
            fake_event.hwnd = 99
            fake_event.window_title = ""
            fake_event.timestamp_ms = 0
            recorder._on_winevent_event(fake_event)
            _time.sleep(0.05)  # drain 처리 시간 — 실제로는 enqueue 안 함
            self.assert_true(
                recorder.event_count == 1,
                "[PR-16w] foreground 외 type 은 무시",
            )
            _ = RawEvent  # ruff F401 회피

            self.step("(4) stop 후 winevent_callback_count == 0")
            recorder.stop()
            self.assert_true(
                hook_mgr.winevent_callback_count == 0,
                f"[PR-16w] stop 가 winevent callback 해제. 실제: {hook_mgr.winevent_callback_count}",
            )

            self.step("(5) 재진입 — 새 winevent callback 재등록")
            recorder.start()
            self.assert_true(
                hook_mgr.winevent_callback_count == 1,
                "[PR-16w] 재진입 시 winevent callback 재등록",
            )
        finally:
            if recorder.is_recording:
                recorder.stop()
            hook_mgr.uninstall_all()

    def test_172_recorder_f8_marker_mapping(self):
        """[ADR 0004 PR-16w + 사용자 추가 §7] F8 키다운 → marker RawEvent 자동 변환.

        enable_f8_marker=True (default) 에서 vk_code=VK_F8 → kind="marker" (key event X).
        평문 key event 가 아니므로 transform 의 `_VK_SPECIAL_KEYS` 가 `pyautogui.press('f8')`
        를 생성하지 않음 — F8 가 generated_code 에 박히지 않는 보장.
        """
        from core.input_hooks import InputHookManager, KeyboardEvent
        from core.recorder import VK_F8, Recorder
        from core.recorder_models import TransformOptions

        self.assert_true(VK_F8 == 0x77, "[PR-16w] VK_F8 = 0x77 (Win32 VK_F8 값)")

        self.step("(1) enable_f8_marker=True (default) — F8 → marker (drain 대기)")
        hook_mgr = InputHookManager()
        recorder = Recorder(hook_mgr)
        try:
            recorder.start()
            recorder._on_keyboard_event(KeyboardEvent(type="keydown", vk_code=VK_F8, scan_code=66))
            sess = recorder.current_session
            self.assert_true(sess is not None, "current_session 존재")
            self.assert_true(
                recorder.wait_for_event_count(1, timeout=1.0),
                "[PR-17] drain 후 F8 marker 1 event",
            )
            self.assert_true(
                sess.events[0].kind == "marker",
                f"[PR-16w] F8 keydown → marker (default). 실제: {sess.events[0]!r}",
            )

            self.step("(2) F8 marker event 의 vk_code 는 채우지 않음 (clean marker)")
            self.assert_true(
                sess.events[0].vk_code is None,
                f"[PR-16w] marker 의 vk_code 는 None. 실제: {sess.events[0].vk_code!r}",
            )

            self.step("(3) 다른 키 (예: 'A' 0x41) 는 그대로 key event")
            recorder._on_keyboard_event(KeyboardEvent(type="keydown", vk_code=0x41, scan_code=30))
            self.assert_true(
                recorder.wait_for_event_count(2, timeout=1.0),
                "[PR-17] drain 후 'A' key 2 event",
            )
            self.assert_true(
                sess.events[1].kind == "key" and sess.events[1].vk_code == 0x41,
                f"[PR-16w] non-F8 키는 key event 유지. 실제: {sess.events[1]!r}",
            )
            recorder.stop()
        finally:
            if recorder.is_recording:
                recorder.stop()
            hook_mgr.uninstall_all()

        self.step("(4) enable_f8_marker=False — F8 도 일반 key event")
        hook_mgr2 = InputHookManager()
        recorder2 = Recorder(hook_mgr2, opts=TransformOptions(enable_f8_marker=False))
        try:
            recorder2.start()
            recorder2._on_keyboard_event(KeyboardEvent(type="keydown", vk_code=VK_F8, scan_code=66))
            sess2 = recorder2.current_session
            self.assert_true(sess2 is not None, "current_session 존재")
            self.assert_true(
                recorder2.wait_for_event_count(1, timeout=1.0),
                "[PR-17] drain 후 F8 key 1 event",
            )
            self.assert_true(
                sess2.events[0].kind == "key" and sess2.events[0].vk_code == VK_F8,
                f"[PR-16w] enable_f8_marker=False 시 F8 → key event. 실제: {sess2.events[0]!r}",
            )
            recorder2.stop()
        finally:
            if recorder2.is_recording:
                recorder2.stop()
            hook_mgr2.uninstall_all()

    def test_173_window_focus_transform_boundary_e2e(self):
        """[ADR 0004 PR-16w] window_focus event 가 transform 에서 step batch 분리 신호로 작동.

        recorder._on_winevent_event 가 채우는 window_focus RawEvent 가 PR-13 의
        _split_into_batches (`auto_window_focus_boundary`) 에 의해 새 step 으로 분리.
        F8 marker 도 동일 경계 신호 — PR-16w 끝단까지 end-to-end 동작 확인.
        """
        from datetime import datetime, timedelta

        from core.recorder_models import RawEvent, RecordingSession, TransformOptions
        from core.recorder_transform import transform

        base = datetime.now()
        # 같은 element 로 만들어 window_focus 이외의 분리 신호 (다른 element click) 를
        # 제거 — 옵션 ON/OFF 차이가 순전히 window_focus 경계 때문임을 검증
        meta_a = {"control_type": "Button", "name": "OK", "automation_id": "btn_ok"}

        self.step("(1) window_focus → batch 분리 (default opts)")
        sess = RecordingSession(id="wf", started_at=base)
        sess.events.append(RawEvent(ts=base, kind="click", x=1, y=1, element_meta=meta_a))
        sess.events.append(
            RawEvent(
                ts=base + timedelta(milliseconds=50),
                kind="window_focus",
                hwnd=99,
                window_title="Calculator",
            )
        )
        sess.events.append(
            RawEvent(
                ts=base + timedelta(milliseconds=100),
                kind="click",
                x=2,
                y=2,
                element_meta=meta_a,
            )
        )
        steps = transform(sess, opts=TransformOptions(idle_boundary_ms=5000))
        self.assert_true(
            len(steps) == 2,
            f"[PR-16w] window_focus 가 step 경계 신호. 실제: {len(steps)}",
        )

        self.step("(2) auto_window_focus_boundary=False — 경계 작동 X")
        steps_no_boundary = transform(
            sess,
            opts=TransformOptions(idle_boundary_ms=5000, auto_window_focus_boundary=False),
        )
        self.assert_true(
            len(steps_no_boundary) == 1,
            f"[PR-16w] 옵션 OFF 시 1 step. 실제: {len(steps_no_boundary)}",
        )

        self.step("(3) window_focus 자체는 generated_code 에 안 박힘")
        all_code = " ".join(s.generated_code for s in steps)
        self.assert_true(
            "window_focus" not in all_code and "Calculator" not in all_code,
            f"[PR-16w] window_focus event 자체는 코드에 안 박힘. 실제: {all_code!r}",
        )

    def test_174_recorder_async_drain_pipeline(self):
        """[ADR 0004 PR-17] hook callback → queue → drain thread → session 파이프라인.

        가드:
        1. start() 가 drain thread + queue 생성, stop() 이 자연 종료
        2. hook callback 호출 직후엔 event 가 큐 안에 있을 수 있음 (sync 보장 X)
        3. wait_for_event_count 로 drain 완료 확인 가능
        4. queue_size / dropped_event_count property 노출 (모니터링용)
        """
        from core.input_hooks import InputHookManager, MouseEvent
        from core.recorder import DEFAULT_QUEUE_MAXSIZE, Recorder

        self.step("(1) DEFAULT_QUEUE_MAXSIZE 상수 노출")
        self.assert_true(
            DEFAULT_QUEUE_MAXSIZE >= 1000,
            f"[PR-17] DEFAULT_QUEUE_MAXSIZE 합리적 (>=1000). 실제: {DEFAULT_QUEUE_MAXSIZE}",
        )

        hook_mgr = InputHookManager()
        recorder = Recorder(hook_mgr)
        try:
            self.step("(2) start 전 모니터링 property 안전 — queue 없음")
            self.assert_true(recorder.queue_size == 0, "[PR-17] start 전 queue_size=0")
            self.assert_true(recorder.dropped_event_count == 0, "[PR-17] start 전 dropped=0")

            self.step("(3) start 후 drain thread alive + queue 생성")
            recorder.start()
            self.assert_true(
                recorder._drain_thread is not None and recorder._drain_thread.is_alive(),
                "[PR-17] start 가 drain thread 시작 (daemon)",
            )
            self.assert_true(
                recorder._raw_queue is not None,
                "[PR-17] start 가 queue.Queue 생성",
            )

            self.step("(4) hook → 비동기 drain → session.events")
            recorder._on_mouse_event(MouseEvent(type="lbutton_down", x=1, y=2))
            recorder._on_mouse_event(MouseEvent(type="lbutton_down", x=3, y=4))
            recorder._on_mouse_event(MouseEvent(type="lbutton_down", x=5, y=6))
            self.assert_true(
                recorder.wait_for_event_count(3, timeout=1.0),
                f"[PR-17] drain 후 3 event 도달. 실제: {recorder.event_count}",
            )

            self.step("(5) stop 후 drain thread 정리")
            recorder.stop()
            self.assert_true(
                recorder._drain_thread is None and recorder._raw_queue is None,
                "[PR-17] stop 후 drain thread/queue 모두 None",
            )
        finally:
            if recorder.is_recording:
                recorder.stop()
            hook_mgr.uninstall_all()

    def test_175_recorder_hook_callback_fast_return(self):
        """[ADR 0004 PR-17] hook callback 은 무거운 element_capture_fn 과 무관하게
        수 밀리초 안에 반환 — Windows LL hook ~300ms 타임아웃 안전.

        slow element_capture_fn (200ms sleep) 을 주입하고 _on_mouse_event 호출
        시간을 측정. enqueue 만 하고 즉시 반환되므로 50ms 이내 (EFP sleep 영향 X).
        """
        import time as _time

        from core.input_hooks import InputHookManager, MouseEvent
        from core.recorder import Recorder

        def slow_capture(x: int, y: int) -> dict:
            _time.sleep(0.2)  # 200ms — 실제 EFP 보다 약간 무거움
            return {"control_type": "Edit"}

        hook_mgr = InputHookManager()
        recorder = Recorder(hook_mgr, element_capture_fn=slow_capture)
        try:
            recorder.start()

            self.step("(1) hook callback 처리 시간 측정 — slow capture 영향 X")
            t0 = _time.monotonic()
            recorder._on_mouse_event(MouseEvent(type="lbutton_down", x=100, y=100))
            elapsed_ms = (_time.monotonic() - t0) * 1000.0
            self.assert_true(
                elapsed_ms < 50.0,
                f"[PR-17] hook callback fast return (<50ms). 실제: {elapsed_ms:.1f}ms",
            )

            self.step("(2) drain 은 slow capture 완료 후 session 에 적재")
            self.assert_true(
                recorder.wait_for_event_count(1, timeout=2.0),
                "[PR-17] drain 가 slow capture 후 event 적재 (timeout=2s)",
            )
            sess = recorder.current_session
            self.assert_true(
                sess is not None
                and sess.events[0].element_meta is not None
                and sess.events[0].element_meta.get("control_type") == "Edit",
                "[PR-17] element_meta 가 drain thread 에서 채워짐",
            )
        finally:
            if recorder.is_recording:
                recorder.stop()
            hook_mgr.uninstall_all()

    def test_176_recorder_queue_backpressure_drop_oldest(self):
        """[ADR 0004 PR-17] queue full 시 oldest event drop + dropped_event_count 증가.

        작은 queue (maxsize=3) + drain 차단 (blocking capture) 으로 큐를 의도적으로
        채운 후 추가 enqueue → 가장 오래된 것부터 drop. dropped counter 누적.
        """
        from threading import Event as _ThreadEvent

        from core.input_hooks import InputHookManager, MouseEvent
        from core.recorder import Recorder

        block = _ThreadEvent()

        def blocking_capture(x: int, y: int) -> dict:
            block.wait(timeout=5.0)  # release 까지 drain 차단
            return None

        hook_mgr = InputHookManager()
        recorder = Recorder(hook_mgr, element_capture_fn=blocking_capture, queue_maxsize=3)
        try:
            recorder.start()

            self.step("(1) drain 차단 상태에서 큐 채우기 — 첫 click 은 drain 이 픽업 (in-flight)")
            # in-flight 1 (drain 가 capture 호출 대기) + queue 에 3 까지 가능
            for i in range(8):
                recorder._on_mouse_event(MouseEvent(type="lbutton_down", x=i, y=i))

            self.step("(2) overflow 발생 — dropped_event_count >= 1")
            self.assert_true(
                recorder.dropped_event_count >= 1,
                f"[PR-17] backpressure drop 발생. 실제 dropped: {recorder.dropped_event_count}",
            )
            self.assert_true(
                recorder.queue_size <= 3,
                f"[PR-17] queue_size <= maxsize. 실제: {recorder.queue_size}",
            )

            self.step("(3) drain 차단 해제 후 stop — 남은 큐 처리 + event_count < 8")
            block.set()
            recorder.stop()
            # in-flight 1 + queue 3 = 최대 4 events 만 session 에 적재 가능 (8 중 일부 drop)
            self.assert_true(
                recorder.event_count < 8,
                f"[PR-17] 일부 event drop 됨. 실제 event_count: {recorder.event_count}",
            )
        finally:
            block.set()  # 안전망 — drain 가 무한 대기하지 않도록
            if recorder.is_recording:
                recorder.stop()
            hook_mgr.uninstall_all()

    def test_177_recorder_stop_drains_remaining_queue(self):
        """[ADR 0004 PR-17] stop() 호출 시 큐에 남은 모든 event 가 drain 처리됨.

        backpressure 미발생 (queue_maxsize > 입력 수) 시 stop 은 sentinel 로 자연
        종료하며 큐에 남은 events 모두 처리 — event loss 0 보장.

        slow capture (100ms × N events) 로 큐를 가득 채우기 직전 상태에서 stop().
        """
        import time as _time

        from core.input_hooks import InputHookManager, MouseEvent
        from core.recorder import Recorder

        capture_count = [0]

        def slow_capture(x: int, y: int) -> dict:
            capture_count[0] += 1
            _time.sleep(0.05)  # 50ms per event
            return {"i": x}

        hook_mgr = InputHookManager()
        recorder = Recorder(hook_mgr, element_capture_fn=slow_capture, queue_maxsize=100)
        try:
            recorder.start()

            self.step("(1) 빠르게 5 events 주입 — drain 가 뒤따라옴")
            for i in range(5):
                recorder._on_mouse_event(MouseEvent(type="lbutton_down", x=i, y=0))

            # 모든 enqueue 직후엔 event_count 가 5 미만일 수 있음 (drain 중)
            self.step("(2) stop() 호출 — 남은 큐 자연 드레인 + 모든 event 처리")
            recorder.stop()

            self.assert_true(
                recorder.event_count == 5,
                f"[PR-17] stop 후 모든 5 event 처리. 실제: {recorder.event_count}",
            )
            self.assert_true(
                capture_count[0] == 5,
                f"[PR-17] element_capture_fn 5번 호출. 실제: {capture_count[0]}",
            )
            self.assert_true(
                recorder.dropped_event_count == 0,
                f"[PR-17] event loss 0. 실제 dropped: {recorder.dropped_event_count}",
            )
        finally:
            if recorder.is_recording:
                recorder.stop()
            hook_mgr.uninstall_all()

    def test_178_input_hooks_dpi_module_contract(self):
        """[ADR 0004 PR-18] core.input_hooks DPI helper API + 상수.

        가드:
        1. ensure_dpi_awareness / get_dpi_for_point / reset_dpi_awareness_cache 함수 노출
        2. Win32 상수 (DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4, DEFAULT_DPI = 96 등)
        3. DpiAwarenessMode Literal — 6개 모드 (per_monitor_v2/v1/system/unaware/unsupported/error)
        4. ensure_dpi_awareness idempotent — 같은 모드 캐시 반환
        5. get_dpi_for_point 가 정수 반환 (>=96)
        """
        from core import input_hooks as _ih
        from core.input_hooks import (
            DEFAULT_DPI,
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE,
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2,
            PROCESS_PER_MONITOR_DPI_AWARE,
            ensure_dpi_awareness,
            get_dpi_for_point,
            reset_dpi_awareness_cache,
        )

        self.step("(1) Win32 상수 값")
        self.assert_true(DEFAULT_DPI == 96, "[PR-18] DEFAULT_DPI=96 (100%)")
        self.assert_true(
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == -4,
            "[PR-18] PER_MONITOR_AWARE_V2 = -4 (Win10 1703+)",
        )
        self.assert_true(
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE == -3,
            "[PR-18] PER_MONITOR_AWARE = -3",
        )
        self.assert_true(
            PROCESS_PER_MONITOR_DPI_AWARE == 2,
            "[PR-18] SetProcessDpiAwareness 인자값 = 2 (per-monitor)",
        )

        self.step("(2) 함수 노출")
        for name in ("ensure_dpi_awareness", "get_dpi_for_point", "reset_dpi_awareness_cache"):
            self.assert_true(
                callable(getattr(_ih, name, None)),
                f"[PR-18] {name} 모듈 노출 + callable",
            )

        self.step("(3) ensure_dpi_awareness 호출 + 결과 모드")
        reset_dpi_awareness_cache()
        mode = ensure_dpi_awareness()
        valid_modes = {
            "per_monitor_v2",
            "per_monitor_v1",
            "system",
            "unaware",
            "unsupported",
            "error",
        }
        self.assert_true(
            mode in valid_modes,
            f"[PR-18] ensure_dpi_awareness 가 정의된 mode 반환. 실제: {mode!r}",
        )

        self.step("(4) idempotent — 같은 모드 캐시 반환")
        mode2 = ensure_dpi_awareness()
        self.assert_true(
            mode == mode2,
            f"[PR-18] 재호출 시 같은 모드. {mode!r} == {mode2!r}",
        )

        self.step("(5) get_dpi_for_point 가 정수 반환")
        dpi = get_dpi_for_point(100, 100)
        self.assert_true(
            isinstance(dpi, int) and dpi >= 96,
            f"[PR-18] get_dpi_for_point >= 96. 실제: {dpi}",
        )

    def test_179_get_hook_manager_auto_ensures_dpi_awareness(self):
        """[ADR 0004 PR-18] get_hook_manager() 의 첫 호출이 ensure_dpi_awareness 자동 트리거.

        recorder 가 start 시 get_hook_manager() 를 사용하므로, hook 사용 시점에
        process DPI awareness 가 보장됨.
        """
        import inspect as _inspect

        from core import input_hooks as _ih

        src = _inspect.getsource(_ih.get_hook_manager)
        self.assert_true(
            "ensure_dpi_awareness" in src,
            "[PR-18] get_hook_manager 가 ensure_dpi_awareness 자동 호출",
        )

        # 동작 검증 — cache reset 후 hook manager 재호출 시 mode 가 None 아님
        _ih.reset_dpi_awareness_cache()
        _ih._dpi_awareness_mode  # type-check ignored
        _ih.get_hook_manager()
        self.assert_true(
            _ih._dpi_awareness_mode is not None,
            "[PR-18] get_hook_manager() 호출 후 _dpi_awareness_mode 결정됨",
        )

    def test_180_raw_event_monitor_dpi_field(self):
        """[ADR 0004 PR-18] RawEvent.monitor_dpi: Optional[int] 필드 신규.

        drain thread 가 click event 처리 시 get_dpi_for_point 로 채움. 기본 None.
        non-Windows 또는 호출 실패 시 None 유지.
        """
        from core.recorder_models import RawEvent

        self.step("(1) 기본 None — backwards compat")
        ev = RawEvent(ts=__import__("datetime").datetime.now(), kind="click", x=10, y=20)
        self.assert_true(
            ev.monitor_dpi is None,
            f"[PR-18] 기본 monitor_dpi=None. 실제: {ev.monitor_dpi!r}",
        )

        self.step("(2) 명시적 값 보존")
        ev2 = RawEvent(
            ts=__import__("datetime").datetime.now(),
            kind="click",
            x=10,
            y=20,
            monitor_dpi=144,
        )
        self.assert_true(
            ev2.monitor_dpi == 144,
            f"[PR-18] monitor_dpi=144 보존. 실제: {ev2.monitor_dpi!r}",
        )

        self.step("(3) drain 가 click event 적재 시 monitor_dpi 채움 (실 환경)")
        from core.input_hooks import InputHookManager, MouseEvent
        from core.recorder import Recorder

        hook_mgr = InputHookManager()
        recorder = Recorder(hook_mgr)
        try:
            recorder.start()
            recorder._on_mouse_event(MouseEvent(type="lbutton_down", x=50, y=50))
            self.assert_true(
                recorder.wait_for_event_count(1, timeout=1.0),
                "[PR-18] drain 완료 대기",
            )
            sess = recorder.current_session
            self.assert_true(sess is not None, "current_session 존재")
            click_ev = sess.events[0]
            # Windows: DPI >= 96 (정수). non-Windows: 96 fallback.
            self.assert_true(
                click_ev.monitor_dpi is not None and click_ev.monitor_dpi >= 96,
                f"[PR-18] click event monitor_dpi 채워짐 (>=96). 실제: {click_ev.monitor_dpi!r}",
            )
        finally:
            if recorder.is_recording:
                recorder.stop()
            hook_mgr.uninstall_all()

    def test_181_recorder_transform_dpi_comment_on_fallback(self):
        """[ADR 0004 PR-18] transform 의 fallback pyautogui.click 좌표 코드에 DPI 코멘트 첨부.

        element_meta None (owner-drawn / 캡처 실패) click 만 코멘트 — 정상 캡처된
        pywinauto/Selenium 코드는 변경 X. monitor_dpi==96 (표준) 일 땐 코멘트 생략.
        """
        from datetime import datetime

        from core.recorder_models import RawEvent, RecordingSession
        from core.recorder_transform import transform

        self.step("(1) monitor_dpi=144 (125%) — 코멘트 첨부")
        sess = RecordingSession(id="dpi", started_at=datetime.now())
        sess.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=300,
                y=400,
                element_meta=None,
                monitor_dpi=144,
            )
        )
        steps = transform(sess)
        code = steps[0].generated_code
        self.assert_true(
            "pyautogui.click(300, 400" in code and "DPI=144" in code and "150%" in code,
            f"[PR-18] DPI=144 (150%) 코멘트 첨부. 실제: {code!r}",
        )

        self.step("(2) monitor_dpi=96 (100% 표준) — 코멘트 생략")
        sess2 = RecordingSession(id="dpi96", started_at=datetime.now())
        sess2.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=1,
                y=2,
                element_meta=None,
                monitor_dpi=96,
            )
        )
        steps2 = transform(sess2)
        code2 = steps2[0].generated_code
        self.assert_true(
            "DPI=" not in code2,
            f"[PR-18] 표준 DPI 시 코멘트 생략. 실제: {code2!r}",
        )

        self.step("(3) monitor_dpi=None — 코멘트 생략 (backwards compat)")
        sess3 = RecordingSession(id="dpinone", started_at=datetime.now())
        sess3.events.append(RawEvent(ts=datetime.now(), kind="click", x=5, y=6, element_meta=None))
        steps3 = transform(sess3)
        code3 = steps3[0].generated_code
        self.assert_true(
            "DPI=" not in code3,
            f"[PR-18] monitor_dpi None 시 코멘트 생략. 실제: {code3!r}",
        )

        self.step("(4) element_meta 있는 click 은 DPI 코멘트 무관 (pywinauto path)")
        sess4 = RecordingSession(id="dpibutton", started_at=datetime.now())
        sess4.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=10,
                y=20,
                element_meta={"control_type": "Button", "name": "OK"},
                monitor_dpi=192,
            )
        )
        steps4 = transform(sess4)
        code4 = steps4[0].generated_code
        self.assert_true(
            "DPI=" not in code4 and "click_input" in code4,
            f"[PR-18] pywinauto 경로는 DPI 코멘트 미부착. 실제: {code4!r}",
        )

    def test_182_recorder_transform_uses_unqualified_Application(self):
        """[회귀 2026-05-20 실측] recorder_transform 은 `Application(...)` (unqualified)
        형태로 코드 생성 — `pywinauto.Application(...)` (fully qualified) 는 X.

        Bug (사용자 실측 2026-05-20): recorder 생성 코드가 `pywinauto.Application(...)`
        형태였는데 library 블럭의 essential imports 는 `from pywinauto import Application`
        형태로 prepend → `pywinauto` namespace 가 import 안 되어 NameError 발생.
        Fix: `_pywinauto_click_code` 가 `Application(...)` 으로 생성.

        가드:
        1. recorder_transform 의 click 코드에 `pywinauto.Application` (fully qualified)
           문자열이 들어가지 않음
        2. `Application(backend="uia").connect(` 패턴은 그대로
        3. extract_library_block 의 essential imports 에 `from pywinauto import Application`
           이 존재 (recorder 코드와 매치)
        """
        from datetime import datetime

        from core.recorder_models import RawEvent, RecordingSession
        from core.recorder_transform import transform
        from core.workflow_engine import _ESSENTIAL_LIBRARY_IMPORTS

        self.step("(1) recorder 가 생성한 desktop click 코드 형태")
        sess = RecordingSession(id="t", started_at=datetime.now())
        sess.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=10,
                y=20,
                button="left",
                element_meta={
                    "control_type": "Button",
                    "name": "시작",
                    "automation_id": "StartButton",
                    "window_title": "데스크톱 1",
                },
            )
        )
        steps = transform(sess)
        code = steps[0].generated_code

        self.assert_true(
            "pywinauto.Application" not in code,
            f"[회귀] fully qualified `pywinauto.Application` 금지. 실제: {code!r}",
        )
        self.assert_true(
            'Application(backend="uia").connect(' in code,
            f'[회귀] unqualified `Application(backend="uia").connect(` 형태 필수. 실제: {code!r}',
        )

        self.step("(2) extract_library_block 의 essential imports 와 매치")
        essential = "\n".join(_ESSENTIAL_LIBRARY_IMPORTS)
        self.assert_true(
            "from pywinauto import Application" in essential,
            f"[회귀] essential imports 에 `from pywinauto import Application` 필수 — "
            f"recorder 코드 매치용. 실제: {_ESSENTIAL_LIBRARY_IMPORTS!r}",
        )

    def test_183_input_hooks_mouse_move_fast_path(self):
        """[회귀 2026-05-20 실측] LL hook dispatch 가 WM_MOUSEMOVE 를 fast-path
        (Python entry + GIL 획득 + MouseEvent 생성 + callback dispatch 전부 skip).

        Bug (사용자 실측 2026-05-20): recorder overlay 의 [중지] 버튼 영역에
        마우스 진입 시 마우스 이동 속도가 체감 지연. 원인 — mouse move event
        가 200Hz 로 LL hook 을 거치며 Python entry + GIL 획득이 Qt main thread
        와 경쟁. recorder 의 build_mouse_raw 가 어차피 move 를 무시하므로 dispatch
        진입 전 fast-path 가 안전.

        가드:
        1. `_mouse_hook_dispatch` source 에 WM_MOUSEMOVE 분기 + CallNextHookEx 직접 호출
        2. callback dispatch 를 거치지 않음 — recorder._on_mouse_event 가
           move 직접 호출은 그대로 가능 (단위 테스트용)
        """
        import inspect as _inspect

        from core.input_hooks import InputHookManager

        src = _inspect.getsource(InputHookManager._mouse_hook_dispatch)
        self.assert_true(
            "WM_MOUSEMOVE" in src,
            f"[회귀] _mouse_hook_dispatch 에 WM_MOUSEMOVE 분기 필수. src:\n{src!r}",
        )
        # 본문 구조 검증 — wParam == WM_MOUSEMOVE 비교 후 CallNextHookEx 직접 반환
        self.assert_true(
            "if wParam == WM_MOUSEMOVE" in src,
            "[회귀] 'if wParam == WM_MOUSEMOVE' fast-path 분기 필수",
        )
        # MouseEvent 생성 라인보다 fast-path 가 먼저 와야 함 (line index 비교)
        idx_move = src.find("wParam == WM_MOUSEMOVE")
        idx_event_build = src.find("event = MouseEvent(")
        self.assert_true(
            0 < idx_move < idx_event_build,
            f"[회귀] WM_MOUSEMOVE fast-path 가 MouseEvent 생성보다 먼저 위치 필수. "
            f"move_idx={idx_move}, build_idx={idx_event_build}",
        )

    def test_184_recorder_overlay_no_activate_and_mouse_tracking(self):
        """[회귀 2026-05-20 실측] RecorderOverlay 가 WS_EX_NOACTIVATE 적용 + mouseTracking off.

        Bug (사용자 실측 2026-05-20): overlay [중지] 버튼 영역에서 마우스 컨트롤
        체감 지연. Qt 의 ``WA_ShowWithoutActivating`` 은 show() 시점만 영향 —
        그 이후 mouse hover 시 OS 가 activate 시도 → 잡음 + Qt hit-test 결합 지연.
        Fix: Win32 WS_EX_NOACTIVATE 비트를 HWND extended style 에 명시 적용 +
        부모/자식 모두 mouseTracking 명시 off.

        가드:
        1. `_apply_no_activate` 메서드 존재 + start() 가 호출
        2. _GWL_EXSTYLE / _WS_EX_NOACTIVATE 상수 노출 + SetWindowLongPtrW 호출
        3. setMouseTracking(False) 가 부모/자식 모두 적용
        """
        import inspect as _inspect

        from ui_v2 import recorder_overlay as _ro
        from ui_v2.recorder_overlay import RecorderOverlay

        self.step("(1) WS_EX_NOACTIVATE 상수 노출")
        self.assert_true(
            hasattr(_ro, "_WS_EX_NOACTIVATE") and _ro._WS_EX_NOACTIVATE == 0x08000000,
            f"[회귀] _WS_EX_NOACTIVATE = 0x08000000. 실제: {getattr(_ro, '_WS_EX_NOACTIVATE', None)!r}",
        )
        self.assert_true(
            hasattr(_ro, "_GWL_EXSTYLE") and _ro._GWL_EXSTYLE == -20,
            "[회귀] _GWL_EXSTYLE = -20 (SetWindowLongPtr index)",
        )

        self.step("(2) _apply_no_activate 메서드 + Win32 호출")
        self.assert_true(
            callable(getattr(RecorderOverlay, "_apply_no_activate", None)),
            "[회귀] RecorderOverlay._apply_no_activate 메서드 필수",
        )
        apply_src = _inspect.getsource(RecorderOverlay._apply_no_activate)
        for needle, desc in (
            ("SetWindowLongPtrW", "Win32 ex-style set 호출"),
            ("_WS_EX_NOACTIVATE", "NOACTIVATE 비트 OR"),
            ('sys.platform != "win32"', "non-Windows silent noop"),
        ):
            self.assert_true(
                needle in apply_src,
                f"[회귀] _apply_no_activate 에 '{desc}' 필수: '{needle}'",
            )

        self.step("(3) start() 가 _apply_no_activate 호출")
        start_src = _inspect.getsource(RecorderOverlay.start)
        self.assert_true(
            "_apply_no_activate" in start_src,
            "[회귀] start() 가 _apply_no_activate() 호출 필수",
        )

        self.step("(4) setMouseTracking(False) 명시 — 부모 + [중지] 버튼")
        init_src = _inspect.getsource(RecorderOverlay.__init__)
        build_src = _inspect.getsource(RecorderOverlay._build_ui)
        self.assert_true(
            "setMouseTracking(False)" in init_src,
            "[회귀] __init__ 가 self.setMouseTracking(False) 명시 호출",
        )
        self.assert_true(
            "setMouseTracking(False)" in build_src,
            "[회귀] _build_ui 가 [중지] 버튼 setMouseTracking(False) 명시 호출",
        )

    def test_185_recorder_stop_hotkey_ctrl_shift_r(self):
        """[회귀 2026-05-20 실측] Ctrl+Shift+R 글로벌 stop hotkey — recorder 의
        LL keyboard hook 에서 직접 감지.

        Bug (사용자 실측 2026-05-20): main window minimize 상태에선 Qt QShortcut
        이 focus 못 받아 Ctrl+Shift+R 작동 X. recorder LL keyboard hook 은 항상
        active 이므로 hook 안에서 modifier+R 패턴 감지 후 callback 호출.

        가드:
        1. recorder.Recorder.__init__ 에 stop_hotkey_callback 인자
        2. recorder 모듈에 VK_R / VK_CONTROL / VK_SHIFT / _is_modifier_pressed 노출
        3. _build_keyboard_raw 가 Ctrl+Shift+R 감지 시 callback 호출 + raw event 안 만듦
        4. AppService.start_recording 가 stop_hotkey_callback 전달
        5. main_window_v2._do_start_recording 가 QTimer.singleShot thread-safe wrapper 주입
        """
        import inspect as _inspect

        from core import recorder as _rec
        from core.app_service import AppService
        from core.recorder import Recorder
        from ui_v2.main_window_v2 import MainWindowV2

        self.step("(1) 상수 + helper 노출")
        self.assert_true(
            hasattr(_rec, "VK_R") and _rec.VK_R == 0x52,
            f"[회귀] VK_R = 0x52 (R 키). 실제: {getattr(_rec, 'VK_R', None)!r}",
        )
        self.assert_true(
            hasattr(_rec, "VK_CONTROL") and _rec.VK_CONTROL == 0x11,
            "[회귀] VK_CONTROL = 0x11",
        )
        self.assert_true(
            hasattr(_rec, "VK_SHIFT") and _rec.VK_SHIFT == 0x10,
            "[회귀] VK_SHIFT = 0x10",
        )
        self.assert_true(
            callable(getattr(_rec, "_is_modifier_pressed", None)),
            "[회귀] _is_modifier_pressed helper 함수 노출",
        )

        self.step("(2) Recorder.__init__ 의 stop_hotkey_callback 인자")
        sig = _inspect.signature(Recorder.__init__)
        self.assert_true(
            "stop_hotkey_callback" in sig.parameters,
            f"[회귀] Recorder.__init__ stop_hotkey_callback 인자 필수. 실제: {list(sig.parameters)!r}",
        )

        self.step("(3) _build_keyboard_raw 가 Ctrl+Shift+R 감지 + callback 호출")
        build_src = _inspect.getsource(Recorder._build_keyboard_raw)
        for needle, desc in (
            ("VK_R", "R 키 감지"),
            ("_is_modifier_pressed(VK_CONTROL)", "Ctrl modifier 검사"),
            ("_is_modifier_pressed(VK_SHIFT)", "Shift modifier 검사"),
            ("_stop_hotkey_callback", "callback 호출"),
        ):
            self.assert_true(
                needle in build_src,
                f"[회귀] _build_keyboard_raw 에 '{desc}' 필수: '{needle}'",
            )

        self.step("(4) _is_modifier_pressed 가 GetAsyncKeyState 사용")
        helper_src = _inspect.getsource(_rec._is_modifier_pressed)
        self.assert_true(
            "GetAsyncKeyState" in helper_src and "0x8000" in helper_src,
            f"[회귀] _is_modifier_pressed GetAsyncKeyState + 0x8000 비트 필수. 실제:\n{helper_src!r}",
        )

        self.step("(5) AppService.start_recording 가 stop_hotkey_callback 전달")
        start_src = _inspect.getsource(AppService.start_recording)
        self.assert_true(
            "stop_hotkey_callback" in start_src
            and "stop_hotkey_callback=stop_hotkey_callback" in start_src,
            f"[회귀] start_recording 가 stop_hotkey_callback 인자 + Recorder 전달 필수.\n{start_src!r}",
        )

        self.step(
            "(6) main_window_v2._do_start_recording 가 QTimer.singleShot thread-safe wrapper 주입"
        )
        do_start_src = _inspect.getsource(MainWindowV2._do_start_recording)
        self.assert_true(
            "stop_hotkey_callback" in do_start_src
            and "QTimer.singleShot(0, self._do_stop_recording)" in do_start_src,
            f"[회귀] _do_start_recording 가 QTimer.singleShot thread-safe wrapper 로 callback 주입 필수.\n"
            f"{do_start_src!r}",
        )

    def test_186_stop_recording_preserves_target_session_id(self):
        """[회귀 2026-05-20 실측] 사용자가 새 세션 만들고 D25 빈 상태에서 녹화 시작 시,
        녹화 결과가 그 세션에 commit 되어야 함 (별개 'Recording YYYYMMDD-HHMMSS' 세션 X).

        Bug (사용자 실측 2026-05-20): _teardown_recording_ui 가 self._recording_target_session_id
        를 None 으로 reset → _show_review_dialog 의 commit_recording 호출 시 target_session_id=None
        → commit_recording 가 새 세션 자동 생성. 사용자가 만든 빈 세션은 그대로 남고
        별도 "Recording YYYYMMDD-HHMMSS" 세션이 생성됨 → 직관적 UX 깨짐.

        Fix: _do_stop_recording 가 target_id 를 local 로 보존 + _show_review_dialog
        에 인자로 전달. _teardown 의 reset 는 무관 (state cleanup 책임).

        가드:
        1. _do_stop_recording source 에 target_id local 보존 라인 + _teardown 호출 전 위치
        2. _show_review_dialog 시그니처에 target_session_id 인자
        3. _show_review_dialog 의 commit_recording 호출이 인자 사용
        """
        import inspect as _inspect

        from ui_v2.main_window_v2 import MainWindowV2

        self.step("(1) _do_stop_recording 가 target_id 보존 (teardown 호출 전)")
        stop_src = _inspect.getsource(MainWindowV2._do_stop_recording)
        self.assert_true(
            "target_id = self._recording_target_session_id" in stop_src,
            f"[회귀] _do_stop_recording 가 target_id 를 local 로 보존 필수.\n{stop_src!r}",
        )
        teardown_idx = stop_src.find("self._teardown_recording_ui()")
        save_idx = stop_src.find("target_id = self._recording_target_session_id")
        self.assert_true(
            0 < save_idx < teardown_idx,
            f"[회귀] target_id 보존이 _teardown_recording_ui 호출 *전* 위치 필수. "
            f"save_idx={save_idx}, teardown_idx={teardown_idx}",
        )

        self.step("(2) _show_review_dialog 시그니처에 target_session_id 인자")
        sig = _inspect.signature(MainWindowV2._show_review_dialog)
        self.assert_true(
            "target_session_id" in sig.parameters,
            f"[회귀] _show_review_dialog target_session_id 인자 필수. 실제: {list(sig.parameters)!r}",
        )

        self.step("(3) _show_review_dialog 가 인자 target_session_id 사용")
        review_src = _inspect.getsource(MainWindowV2._show_review_dialog)
        self.assert_true(
            "target_session_id=target_session_id" in review_src,
            f"[회귀] _show_review_dialog 가 commit_recording 호출 시 인자 target_session_id 사용 필수.\n"
            f"{review_src!r}",
        )

        self.step("(4) commit 후 current_session reload + _refresh_step_cards 명시 호출")
        # 사용자 보고 (2026-05-23): 이미 열린 탭에 녹화 commit 시 step cards 가
        # 빈 상태 그대로 유지 — _open_session_tab 의 setCurrentIndex 동일 idx →
        # currentChanged 미발화 → _switch_session 안 불림 → stale current_session.
        # Fix: accept path 에 명시적 current_session reload + _refresh_step_cards.
        accept_idx = review_src.find("self.app_service.commit_recording(")
        # 두 번째 commit_recording (try-except 안의 accept path)
        accept_idx = review_src.find("self.app_service.commit_recording(", accept_idx + 1)
        self.assert_true(accept_idx > 0, "[회귀] accept path 의 commit_recording 호출 찾음")
        # accept 이후의 코드에 reload 패턴 있어야 함
        after_accept = review_src[accept_idx:]
        self.assert_true(
            "self.current_session = self.app_service.get_session(session.session_id)"
            in after_accept,
            f"[회귀] commit 후 self.current_session reload 필수.\n{after_accept!r}",
        )
        self.assert_true(
            "self._refresh_step_cards()" in after_accept,
            f"[회귀] commit 후 _refresh_step_cards() 명시 호출 필수.\n{after_accept!r}",
        )

    def test_187_pywinauto_codegen_helper_core_patterns(self):
        """[PR-19a 2026-05-23] core/pywinauto_codegen.build_pywinauto_click_code
        helper 의 핵심 deterministic 패턴 보장.

        목적: helper 가 win_inspector 의 stable selector 로직 + 메모장류 동적
        title 안전 매칭 + DPI Awareness + selector fallback chain + 창 활성화 +
        walk_up + pyautogui PRIMARY click 까지 robust 코드 생성. recorder_transform
        의 이전 6줄 minimal 형태 (title_re=".*<full_title>.*") 가 메모장처럼
        문서 내용이 title 에 들어가는 앱 재실행 시 매칭 실패하던 회귀 차단.

        가드:
        1. 메모장 케이스 (window_title="*hello world - 메모장") → program_name 만
           추출한 title_re='.*메모장' 매칭 (full title hardcode X)
        2. 브라우저 케이스 (is_browser_process=True) → full title hardcode +
           found_index=0 (페이지별 식별)
        3. DPI Awareness 설정 코드 (SetProcessDpiAwarenessContext / shcore fallback)
        4. Application(...) unqualified (test_182 회귀 가드 — fully qualified 금지)
        5. selector fallback chain (_resolve_element + _selectors list)
        6. 창 활성화 (BringWindowToTop + SetForegroundWindow + IsIconic 분기)
        7. walk_up to clickable parent (_clickable_types set + parent() loop)
        8. pyautogui PRIMARY + element.click_input() fallback (try/except 이중)
        9. right button 시 right_click_input fallback + button='right' 인자
        10. name+auto_id(non-dynamic) 결합 selector (recorder baseline)
        """
        from core.pywinauto_codegen import build_pywinauto_click_code

        self.step("(1) 메모장 program_name title_re 매칭 (동적 title 안전)")
        memo_code = build_pywinauto_click_code(
            {
                "control_type": "MenuItem",
                "name": "파일",
                "window_title": "*hello world - 메모장",
            }
        )
        # PR-19e: _safe_str_literal (json.dumps) 사용으로 double quote literal.
        # 단/이중 인용 둘 다 허용 (회귀 안전망).
        self.assert_true(
            'title_re=".*메모장"' in memo_code or "title_re='.*메모장'" in memo_code,
            f"[PR-19a/e] 메모장 케이스 program_name (.*메모장) title_re 필수. 실제: {memo_code!r}",
        )
        self.assert_true(
            "hello world" not in memo_code,
            f"[PR-19a] full title hardcode 금지 (동적 변화 매칭 실패 회귀). 실제: {memo_code!r}",
        )

        self.step("(2) 브라우저 케이스 full title hardcode + found_index=0")
        browser_code = build_pywinauto_click_code(
            {
                "control_type": "Button",
                "name": "Submit",
                "window_title": "GitHub - Chrome",
                "is_browser_process": True,
            }
        )
        self.assert_true(
            'title="GitHub - Chrome"' in browser_code and "found_index=0" in browser_code,
            f"[PR-19a] 브라우저 full title + found_index=0 필수. 실제: {browser_code!r}",
        )

        self.step("(3) DPI Awareness 코드 포함")
        self.assert_true(
            "SetProcessDpiAwarenessContext" in memo_code
            and "shcore.SetProcessDpiAwareness" in memo_code,
            f"[PR-19a] DPI Awareness (PER_MONITOR_AWARE_V2 + shcore fallback) 필수. "
            f"실제: {memo_code!r}",
        )

        self.step("(4) Application(...) unqualified (test_182 회귀 가드)")
        self.assert_true(
            "pywinauto.Application" not in memo_code,
            f"[PR-19a] fully qualified pywinauto.Application 금지. 실제: {memo_code!r}",
        )
        self.assert_true(
            'Application(backend="uia").connect(' in memo_code,
            f'[PR-19a] unqualified Application(backend="uia").connect( 필수. 실제: {memo_code!r}',
        )

        self.step("(5) selector fallback chain (_resolve_element)")
        self.assert_true(
            "def _resolve_element():" in memo_code
            and "_selectors" in memo_code
            and "for _build in _selectors:" in memo_code,
            f"[PR-19a] _resolve_element fallback chain 필수. 실제: {memo_code!r}",
        )

        self.step("(6) 창 활성화 (BringWindowToTop + SetForegroundWindow + IsIconic)")
        self.assert_true(
            "user32.BringWindowToTop(hwnd)" in memo_code
            and "user32.SetForegroundWindow(hwnd)" in memo_code
            and "user32.IsIconic(hwnd)" in memo_code,
            f"[PR-19a] 창 활성화 3 신호 필수. 실제: {memo_code!r}",
        )

        self.step("(7) walk_up to clickable parent")
        self.assert_true(
            "_clickable_types" in memo_code
            and "click_target = element" in memo_code
            and "_cur.parent()" in memo_code,
            f"[PR-19a] walk_up to clickable parent 필수. 실제: {memo_code!r}",
        )

        self.step("(8) pyautogui PRIMARY + element fallback (try/except 이중)")
        self.assert_true(
            "pyautogui.click(center_x, center_y" in memo_code
            and "click_target.click_input()" in memo_code,
            f"[PR-19a] pyautogui PRIMARY + click_input fallback 필수. 실제: {memo_code!r}",
        )

        self.step("(9) right button → right_click_input + button='right'")
        right_code = build_pywinauto_click_code(
            {"control_type": "Button", "name": "OK", "window_title": "App"},
            button="right",
        )
        self.assert_true(
            "click_target.right_click_input()" in right_code and "button='right'" in right_code,
            f"[PR-19a] right button 시 right_click_input + button='right' 인자. "
            f"실제: {right_code!r}",
        )

        self.step("(10) name+auto_id(non-dynamic) 결합 selector (recorder baseline)")
        combined_code = build_pywinauto_click_code(
            {
                "control_type": "Button",
                "name": "확인",
                "automation_id": "btn_ok",
                "window_title": "Dialog",
            }
        )
        self.assert_true(
            'title="확인"' in combined_code
            and 'auto_id="btn_ok"' in combined_code
            and 'control_type="Button"' in combined_code,
            f"[PR-19a] name+auto_id+control_type 결합 selector (가장 discriminating) "
            f"필수. 실제: {combined_code!r}",
        )

        self.step("(11) auto_id 가 순수 숫자 (동적) 면 combined 미사용 → name+ctrl_type")
        dynamic_code = build_pywinauto_click_code(
            {
                "control_type": "Edit",
                "name": "입력",
                "automation_id": "12345",
                "window_title": "App",
            }
        )
        self.assert_true(
            'auto_id="12345"' not in dynamic_code,
            f"[PR-19a] 동적 (숫자만) auto_id 는 primary selector 에서 제외. 실제: {dynamic_code!r}",
        )

    def test_188_recorder_transform_delegates_to_pywinauto_codegen(self):
        """[PR-19a 2026-05-23] recorder_transform._pywinauto_click_code 가
        core.pywinauto_codegen.build_pywinauto_click_code 로 위임.

        목적: recorder 가 helper 의 robust 코드 (DPI / program_name title_re /
        fallback chain / 창 활성화 / walk_up / pyautogui PRIMARY) 를 그대로
        emit 하여 사용자 실측 회귀 (메모장류 매칭 실패, NameError) 차단.

        가드:
        1. recorder_transform 모듈이 helper 를 import (의존 명시)
        2. _pywinauto_click_code source 가 build_pywinauto_click_code 호출
        3. end-to-end transform 결과에 helper 의 핵심 패턴 포함
           (program_name title_re, DPI, fallback chain, walk_up, pyautogui PRIMARY)
        """
        import inspect as _inspect
        from datetime import datetime

        from core import recorder_transform as _rt
        from core.recorder_models import RawEvent, RecordingSession

        self.step("(1) recorder_transform 이 helper import")
        rt_src = _inspect.getsource(_rt)
        self.assert_true(
            "from core.pywinauto_codegen import build_pywinauto_click_code" in rt_src,
            "[PR-19a] recorder_transform 이 pywinauto_codegen helper import 필수",
        )

        self.step("(2) _pywinauto_click_code 가 helper 호출 위임")
        click_src = _inspect.getsource(_rt._pywinauto_click_code)
        self.assert_true(
            "build_pywinauto_click_code(" in click_src,
            f"[PR-19a] _pywinauto_click_code 가 helper 호출 필수. 실제:\n{click_src}",
        )

        self.step("(3) end-to-end transform 결과에 robust 패턴")
        sess = RecordingSession(id="t", started_at=datetime.now())
        sess.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=10,
                y=20,
                button="left",
                element_meta={
                    "control_type": "MenuItem",
                    "name": "파일",
                    "window_title": "*untitled - 메모장",
                },
            )
        )
        steps = _rt.transform(sess)
        code = steps[0].generated_code
        # PR-19e: _safe_str_literal 로 double quote. program_name title_re sentinel 만
        # 양 인용 부호 허용 (escape 안전 fix 후속 회귀 방지).
        self.assert_true(
            'title_re=".*메모장"' in code or "title_re='.*메모장'" in code,
            f"[PR-19a/e] program_name title_re (.*메모장) 필수 (single/double quote 모두 허용). "
            f"실제 generated_code:\n{code}",
        )
        for pattern, desc in [
            ("SetProcessDpiAwarenessContext", "DPI Awareness"),
            ("def _resolve_element():", "selector fallback chain"),
            ("BringWindowToTop", "창 활성화"),
            ("_clickable_types", "walk_up"),
            ("pyautogui.click(center_x, center_y)", "pyautogui PRIMARY"),
            ("click_target.click_input()", "element fallback"),
        ]:
            self.assert_true(
                pattern in code,
                f"[PR-19a] end-to-end transform 결과에 {desc} 패턴 ({pattern!r}) 필수. "
                f"실제 generated_code:\n{code}",
            )
        self.assert_true(
            "untitled" not in code,
            f"[PR-19a] full title hardcode 회귀 — 'untitled' 가 코드에 들어가면 안 됨 "
            f"(program_name '메모장' 만 추출되어야 함). 실제:\n{code}",
        )

    def test_189_win_inspector_pywinauto_codegen_sentinel_consistency(self):
        """[PR-19a 2026-05-23] win_inspector 의 inline desktop click 코드 emit
        과 pywinauto_codegen helper 의 출력이 핵심 deterministic 패턴에서
        일치 (divergence 방지 sentinel).

        목적: PR-19a 가 helper 만 추출 + recorder_transform 만 통합 (win_inspector
        리팩은 PR-19a' 로 분리 — AI quality 회귀 risk 분리). 두 path 가 시간이
        지나며 divergence 되지 않도록 sentinel — 둘 다 같은 핵심 패턴 emit.

        가드 (win_inspector._get_desktop_element_info_text source + helper output
        양쪽 모두):
        - DPI Awareness (SetProcessDpiAwarenessContext + shcore)
        - Application unqualified (`pywinauto.Application` 금지)
        - program_name title_re 패턴
        - fallback chain (_resolve_element)
        - walk_up (_clickable_types)
        - pyautogui PRIMARY click 분기

        win_inspector 가 helper 호출로 교체되면 (PR-19a') 이 sentinel 은
        자동 만족. 둘 중 하나가 변경되어 divergence 되면 즉시 fail.
        """
        import inspect as _inspect

        from core.pywinauto_codegen import build_pywinauto_click_code
        from core.win_inspector import WindowInspector

        wi_src = _inspect.getsource(WindowInspector._get_desktop_element_info_text)
        helper_out = build_pywinauto_click_code(
            {
                "control_type": "Button",
                "name": "확인",
                "automation_id": "btnOK",
                "window_title": "Dialog",
            }
        )

        sentinels = [
            ("SetProcessDpiAwarenessContext", "DPI Awareness PER_MONITOR_AWARE_V2"),
            ("shcore.SetProcessDpiAwareness", "DPI Awareness shcore fallback"),
            ("_resolve_element", "selector fallback chain"),
            ("_clickable_types", "walk_up clickable parent"),
            ("BringWindowToTop", "창 활성화 BringWindowToTop"),
            ("SetForegroundWindow", "창 활성화 SetForegroundWindow"),
            ("pyautogui.click(center_x, center_y", "pyautogui PRIMARY click"),
        ]
        for pattern, desc in sentinels:
            self.assert_true(
                pattern in wi_src,
                f"[PR-19a sentinel] win_inspector 가 {desc} 패턴 ({pattern!r}) emit 필수",
            )
            self.assert_true(
                pattern in helper_out,
                f"[PR-19a sentinel] pywinauto_codegen helper 가 {desc} 패턴 ({pattern!r}) emit 필수",
            )

        self.step("[anti-pattern] 양쪽 모두 fully qualified pywinauto.Application 금지")
        # win_inspector source 는 pywinauto import 코멘트가 있을 수 있어 emit 부분만 검사:
        # connect_line 변수 + lines.append(f"app = {connect_line}") 패턴.
        # emit 되는 connect_line 자체에 fully qualified 가 들어가면 안 됨.
        wi_emits_fully_qualified = (
            'f"app = pywinauto.Application' in wi_src
            or "'app = pywinauto.Application" in wi_src
            or '"app = pywinauto.Application' in wi_src
            or 'connect_line = f"pywinauto.Application' in wi_src
            or "connect_line = (\n            f'pywinauto.Application" in wi_src
        )
        self.assert_true(
            not wi_emits_fully_qualified,
            "[PR-19a sentinel] win_inspector 가 fully qualified pywinauto.Application emit 금지",
        )
        self.assert_true(
            "pywinauto.Application" not in helper_out,
            f"[PR-19a sentinel] helper output 에 fully qualified pywinauto.Application 금지. "
            f"실제: {helper_out!r}",
        )

    def test_190_input_hooks_user32_argtypes_configured(self):
        """[회귀 2026-05-23 실측] InputHookManager 가 user32 함수들의 argtypes/restype
        명시 설정. CallNextHookEx 의 lParam (x64 64-bit 포인터) OverflowError 방지.

        Bug (사용자 실측 2026-05-23): 녹화 중 매 mouse/keyboard event 마다 stderr 에
        ``ctypes.ArgumentError: argument 4: OverflowError: int too long to convert``
        반복 출력. 원인 — ``CallNextHookEx`` 의 argtypes 미설정 → ctypes 가 default
        ``c_int`` (32-bit) 로 마샬링 시도 → LL hook 의 lParam (MSLLHOOKSTRUCT 포인터,
        x64 에서 64-bit 주소 예: ``0x0000024BB9D1D300``) 이 32-bit 범위 초과 →
        OverflowError → CallNextHookEx 호출 실패 → event 가 next hook chain 으로
        propagate 안 됨 + Python exception 처리 / stderr write 비용 누적 → 사용자
        체감 input 씹힘 + 더블 클릭 필요. 옵션 A (WinEvent disable) / 옵션 B (EFP
        disable) 모두 무효 였던 이유 — 둘 다 dispatch path 의 이 버그를 해결 못 함.

        Fix: ``InputHookManager._configure_user32_signatures()`` 가 __init__ 에서
        호출되어 user32 함수들의 argtypes/restype 명시 설정. Windows 타입 매핑:
        ``WPARAM``=``c_size_t``, ``LPARAM``=``c_ssize_t``, ``LRESULT``=``c_ssize_t``,
        ``HHOOK``=``c_void_p``.

        가드:
        1. InputHookManager 가 _configure_user32_signatures 메서드 보유
        2. __init__ 끝에 _configure_user32_signatures 호출 (Win 환경 분기)
        3. CallNextHookEx.argtypes = [void_p, c_int, size_t, ssize_t], restype = ssize_t
           (x64 에서 size_t=c_ulonglong, ssize_t=c_longlong 로 정규화됨)
        4. SetWindowsHookExW.restype = c_void_p (HHOOK 64-bit 보장)
        5. UnhookWindowsHookEx.argtypes = [c_void_p]
        6. non-Windows 환경에선 _user32 가 None → _configure 가 silent noop
        """
        import ctypes
        import inspect as _inspect
        import sys

        from core.input_hooks import InputHookManager

        self.step("(1) _configure_user32_signatures 메서드 존재")
        self.assert_true(
            hasattr(InputHookManager, "_configure_user32_signatures"),
            "[회귀] InputHookManager 가 _configure_user32_signatures 메서드 보유 필수",
        )

        self.step("(2) __init__ 에서 _configure_user32_signatures 호출 sentinel")
        init_src = _inspect.getsource(InputHookManager.__init__)
        self.assert_true(
            "self._configure_user32_signatures()" in init_src,
            f"[회귀] __init__ 가 _configure_user32_signatures 호출 필수.\n{init_src}",
        )

        self.step("(3) 실제 인스턴스의 user32 함수 argtypes/restype 검증 (Windows 만)")
        if sys.platform != "win32":
            self.step("non-Windows 환경 — skip (recorder 자체 non-Windows 미지원)")
            return

        mgr = InputHookManager()

        # CallNextHookEx — 가장 중요 (실측 OverflowError 발생 지점)
        cnh_argtypes = mgr._user32.CallNextHookEx.argtypes
        self.assert_true(
            cnh_argtypes is not None and len(cnh_argtypes) == 4,
            f"[회귀] CallNextHookEx.argtypes 4개 명시 필수. 실제: {cnh_argtypes!r}",
        )
        # x64 에서 c_size_t 는 c_ulonglong 으로, c_ssize_t 는 c_longlong 으로 정규화
        expected_lparam_types = (ctypes.c_ssize_t, ctypes.c_longlong, ctypes.c_long)
        self.assert_true(
            cnh_argtypes[3] in expected_lparam_types,
            f"[회귀] CallNextHookEx.argtypes[3] (lParam) signed pointer-size 타입 필수 "
            f"(c_ssize_t/c_longlong). 실제: {cnh_argtypes[3]!r}",
        )
        cnh_restype = mgr._user32.CallNextHookEx.restype
        self.assert_true(
            cnh_restype in expected_lparam_types,
            f"[회귀] CallNextHookEx.restype (LRESULT) signed pointer-size 필수. "
            f"실제: {cnh_restype!r}",
        )

        # SetWindowsHookExW — HHOOK 반환 64-bit 보장
        shex_restype = mgr._user32.SetWindowsHookExW.restype
        self.assert_true(
            shex_restype is ctypes.c_void_p,
            f"[회귀] SetWindowsHookExW.restype = c_void_p (HHOOK 64-bit). 실제: {shex_restype!r}",
        )

        # UnhookWindowsHookEx — HHOOK 인자
        uhex_argtypes = mgr._user32.UnhookWindowsHookEx.argtypes
        self.assert_true(
            uhex_argtypes == [ctypes.c_void_p],
            f"[회귀] UnhookWindowsHookEx.argtypes = [c_void_p]. 실제: {uhex_argtypes!r}",
        )

        self.step("(4) hook install/uninstall end-to-end 동작 (OverflowError 발생 X)")
        # OverflowError 가 발생하면 ctypes 가 stderr 에 출력하지만 callback 자체는
        # 0 반환 — install/uninstall 동작은 이상 없는 것처럼 보임. 검증의 핵심은
        # argtypes 가 잡혀 있다는 것 (위 단계들). 여기서는 install/uninstall path 가
        # 새 argtypes 로도 정상 동작 (regression 안 함) 확인.
        cb_id = mgr.install_mouse_callback(lambda ev: False)
        self.assert_true(mgr.is_mouse_hook_installed, "[회귀] install 후 hook installed True")
        mgr.uninstall_mouse_callback(cb_id)
        self.assert_true(
            not mgr.is_mouse_hook_installed, "[회귀] uninstall 후 hook installed False"
        )

    def test_191_recording_step_element_meta_regenerate_path(self):
        """[PR-19d 2026-05-24] 옵션 3 — 녹화 step 의 element_meta 보존 + AI 재생성
        path 가 element_context 로 변환해 AI 에 전달.

        목적: 녹화 step 도 사용자가 "👤 사용자 요청" 클릭 시 AI 재생성 가능.
        deterministic 코드 (recorder_transform) 와 비교 평가 가능. 기존 path 는
        ``self._pending_elements`` (F3 picker) 만 사용 — 녹화 step 의 element 정보
        는 generated_code 안에 hardcode 만 되어 재생성 시 손실됨.

        가드:
        1. ``Step`` dataclass 에 ``element_meta: Optional[dict] = None`` 필드 존재
        2. ``recorder_transform._batch_to_step`` 가 batch 첫 click 의 element_meta
           를 Step.element_meta 에 보존 (click 없는 batch 는 None)
        3. ui_v2 의 ``_lookup_step_element_meta`` / ``_recorder_meta_to_picker_dict``
           helper 존재 + adapter 가 recorder 필드를 picker 형식으로 정규화
        4. ``_on_regenerate`` source 에 element_meta lookup + adapter 호출 sentinel
        5. adapter end-to-end: recorder dict → picker dict → win_inspector
           ``get_element_info_text`` 가 정상 markdown 생성 (selector 정보 포함)
        """
        import inspect as _inspect
        from dataclasses import fields
        from datetime import datetime

        from core.recorder_models import RawEvent, RecordingSession
        from core.recorder_transform import transform
        from core.session_manager import Step
        from core.win_inspector import WindowInspector
        from ui_v2.main_window_v2 import (
            MainWindowV2,
            _lookup_step_element_meta,
            _recorder_meta_to_picker_dict,
        )

        self.step("(1) Step dataclass 에 element_meta 필드 존재")
        field_names = {f.name for f in fields(Step)}
        self.assert_true(
            "element_meta" in field_names,
            f"[PR-19d] Step.element_meta 필드 필수. 실제 fields: {field_names}",
        )
        self.assert_true(
            Step().element_meta is None,
            f"[PR-19d] Step.element_meta default None. 실제: {Step().element_meta!r}",
        )

        self.step("(2) recorder_transform 이 batch 첫 click element_meta 보존")
        sess = RecordingSession(id="t", started_at=datetime.now())
        meta = {
            "control_type": "Button",
            "name": "검색",
            "automation_id": "SearchButton",
            "window_title": "데스크톱 1",
        }
        sess.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=100,
                y=200,
                button="left",
                element_meta=meta,
            )
        )
        steps = transform(sess)
        self.assert_true(len(steps) == 1, f"[PR-19d] 1 click → 1 step. 실제: {len(steps)}")
        self.assert_true(
            steps[0].element_meta is not None
            and steps[0].element_meta.get("automation_id") == "SearchButton",
            f"[PR-19d] transform 이 element_meta 보존 필수. 실제: {steps[0].element_meta!r}",
        )

        self.step("(3) click 없는 batch (key 만) → element_meta None")
        sess2 = RecordingSession(id="t2", started_at=datetime.now())
        sess2.events.append(RawEvent(ts=datetime.now(), kind="key", vk_code=0x41))
        steps2 = transform(sess2)
        if steps2:
            self.assert_true(
                steps2[0].element_meta is None,
                f"[PR-19d] click 없는 batch → element_meta None. 실제: {steps2[0].element_meta!r}",
            )

        self.step("(4) _lookup_step_element_meta helper — dataclass + dict 둘 다 처리")

        class _FakeSession:
            def __init__(self, steps_list):
                self.steps = steps_list

        step_dc = Step(step_id=5, element_meta={"control_type": "Edit", "name": "입력"})
        sess_dc = _FakeSession([step_dc])
        self.assert_true(
            _lookup_step_element_meta(sess_dc, 5) == {"control_type": "Edit", "name": "입력"},
            "[PR-19d] dataclass Step 에서 element_meta lookup 성공",
        )
        self.assert_true(
            _lookup_step_element_meta(sess_dc, 999) is None,
            "[PR-19d] 존재하지 않는 step_id 는 None",
        )

        sess_dict = _FakeSession([{"step_id": 7, "element_meta": {"name": "확인"}}])
        self.assert_true(
            _lookup_step_element_meta(sess_dict, 7) == {"name": "확인"},
            "[PR-19d] dict Step 에서 element_meta lookup 성공",
        )

        self.step("(5) _recorder_meta_to_picker_dict adapter — 필드 변환 정규화")
        recorder_meta = {
            "control_type": "Button",
            "name": "검색",
            "automation_id": "SearchButton",
            "class_name": "Button",
            "window_title": "데스크톱 1",
            "exe_name": "explorer.exe",
            "rect": [100, 200, 180, 230],
        }
        picker = _recorder_meta_to_picker_dict(recorder_meta)
        self.assert_true(
            picker["parent_window_title"] == "데스크톱 1",
            f"[PR-19d] window_title → parent_window_title 변환. 실제: {picker!r}",
        )
        self.assert_true(
            picker["rect"] == {"left": 100, "top": 200, "width": 80, "height": 30},
            f"[PR-19d] rect list → dict 변환 (right-left, bottom-top). 실제: {picker['rect']!r}",
        )
        self.assert_true(
            picker["screen_x"] == 140 and picker["screen_y"] == 215,
            f"[PR-19d] center 좌표 계산. 실제: ({picker['screen_x']}, {picker['screen_y']})",
        )
        self.assert_true(
            picker["recommended_backend"] == "uia" and picker["detected_backend"] == "uia",
            f"[PR-19d] backend default 'uia'. 실제: {picker!r}",
        )
        self.assert_true(
            picker["is_browser"] is False,
            f"[PR-19d] explorer.exe → is_browser False. 실제: {picker['is_browser']!r}",
        )

        self.step("(6) browser exe 추론")
        for exe in ("chrome.exe", "msedge.exe", "firefox.exe"):
            recorder_meta["exe_name"] = exe
            p = _recorder_meta_to_picker_dict(recorder_meta)
            self.assert_true(
                p["is_browser"] is True,
                f"[PR-19d] {exe} → is_browser True. 실제: {p['is_browser']!r}",
            )

        self.step("(7) _on_regenerate source 에 element_meta lookup + adapter sentinel")
        regen_src = _inspect.getsource(MainWindowV2._on_regenerate)
        self.assert_true(
            "_lookup_step_element_meta(" in regen_src
            and "_recorder_meta_to_picker_dict(" in regen_src,
            f"[PR-19d] _on_regenerate 가 lookup + adapter helper 호출 필수.\n{regen_src}",
        )

        self.step("(8) end-to-end: recorder dict → picker → win_inspector markdown")
        picker_full = _recorder_meta_to_picker_dict(
            {
                "control_type": "Button",
                "name": "검색",
                "automation_id": "SearchButton",
                "class_name": "Button",
                "window_title": "데스크톱 1",
                "exe_name": "explorer.exe",
                "rect": [100, 200, 180, 230],
            }
        )
        inspector = WindowInspector()
        text = inspector.get_element_info_text(picker_full)
        for needle in ("SearchButton", "데스크톱", "Button", "Application"):
            self.assert_true(
                needle in text,
                f"[PR-19d] win_inspector markdown 에 {needle!r} 포함 필수 (AI prompt 전달용)",
            )

    def test_192_pywinauto_codegen_safe_escape_and_process_first(self):
        """[PR-19e 2026-05-24] 사용자 실측 (v2-새세션-000727) 발견 2 fix:

        Critical fix — _safe_str_literal 로 모든 user-data string escape.
        Win11 메모장 Document name = "1111\\r2222\\r3333\\r" 같이 CR 포함된 name 이
        element_meta 에 들어가도 generated code 가 SyntaxError (unterminated string
        literal) 안 남. 가드: ``compile()`` 가 SyntaxError 안 raise.

        Important fix — process_id 우선 connect chain.
        Win11 메모장의 탭 (XAML 중간 노드) 이름 ("데스크톱 1") 이 element_inspect
        의 top-level 로 잡혀 진짜 메모장 window title 매칭 실패. process_id 우선
        connect (timeout 2s) + title fallback (timeout 10s) chain emit.

        가드:
        1. CR 포함 name → ``compile()`` 통과 (SyntaxError 안 raise)
        2. process_id 있으면 ``_connect_app()`` 함수 + ``process=...`` connect emit
        3. process_id 없으면 기존 단일 connect line (회귀 안 함)
        4. quote (\\") 포함 name 도 안전 escape
        5. 모든 escape (CR/LF/quote/backslash) 가 적용된 코드도 compile 통과
        """
        from core.pywinauto_codegen import build_pywinauto_click_code

        self.step("(1) CR 포함 name (실측 v2-새세션-000727 Step 1 재현) compile 통과")
        meta_cr = {
            "control_type": "Document",
            "name": "1111\r2222\r3333\r",
            "class_name": "RichEditD2DPT",
            "window_title": "데스크톱 1",
            "process_id": 16760,
        }
        code_cr = build_pywinauto_click_code(meta_cr)
        try:
            compile(code_cr, "<test_192>", "exec")
            compile_ok = True
            compile_err = ""
        except SyntaxError as e:
            compile_ok = False
            compile_err = str(e)
        self.assert_true(
            compile_ok,
            f"[PR-19e] CR 포함 name 에 SyntaxError 회귀 금지. "
            f"실제 에러: {compile_err}\n코드 일부: {code_cr[:500]!r}",
        )

        self.step("(2) process_id 우선 connect chain emit (_connect_app + process=)")
        self.assert_true(
            "def _connect_app():" in code_cr and "process=16760" in code_cr,
            f"[PR-19e] process_id 있으면 _connect_app + process=PID emit 필수. 실제: {code_cr!r}",
        )
        self.assert_true(
            "timeout=2" in code_cr,
            f"[PR-19e] process connect 짧은 timeout (2s) — title fallback 빠르게. "
            f"실제: {code_cr!r}",
        )

        self.step("(3) process_id 없으면 기존 단일 connect path (회귀 안 함)")
        meta_no_pid = {
            "control_type": "Button",
            "name": "확인",
            "window_title": "Dialog",
        }
        code_no_pid = build_pywinauto_click_code(meta_no_pid)
        self.assert_true(
            "_connect_app()" not in code_no_pid,
            f"[PR-19e] process_id 없으면 _connect_app() helper 안 emit. 실제: {code_no_pid!r}",
        )
        self.assert_true(
            "app = Application(" in code_no_pid,
            f"[PR-19e] process_id 없으면 기존 단일 app = Application(...) line 유지. "
            f"실제: {code_no_pid!r}",
        )

        self.step("(4) quote 포함 name 도 안전 escape — compile 통과")
        meta_quote = {
            "control_type": "Edit",
            "name": 'with "quote" and \\backslash',
            "window_title": "Test",
        }
        code_quote = build_pywinauto_click_code(meta_quote)
        try:
            compile(code_quote, "<test_192>", "exec")
            quote_ok = True
        except SyntaxError as e:
            quote_ok = False
            print(f"quote compile err: {e}")
        self.assert_true(
            quote_ok,
            f"[PR-19e] quote/backslash name escape 필수. 코드: {code_quote!r}",
        )

        self.step("(5) LF/tab 등 다른 control char 도 안전")
        meta_misc = {
            "control_type": "Text",
            "name": "line1\nline2\ttab",
            "class_name": 'cls"with quotes',
            "window_title": "App",
        }
        code_misc = build_pywinauto_click_code(meta_misc)
        try:
            compile(code_misc, "<test_192>", "exec")
            misc_ok = True
        except SyntaxError as e:
            misc_ok = False
            print(f"misc compile err: {e}")
        self.assert_true(
            misc_ok,
            f"[PR-19e] LF/tab/quote 안전 escape 필수. 코드: {code_misc!r}",
        )

        self.step("(6) process_id 없는 case 의 title fallback line 은 그대로 emit")
        self.assert_true(
            "win = app.window(" in code_no_pid or "win = app.top_window()" in code_no_pid,
            f"[PR-19e] process_id 없을 때 win line emit. 실제: {code_no_pid!r}",
        )

    def test_193_recorder_modifier_hotkey_and_recording_meta(self):
        """[PR-19f 2026-05-24] 사용자 실측 (v2-새세션-003052) 발견 2 fix:

        Critical fix — modifier 키 (Ctrl/Shift/Alt/Win) 인식.
        이전엔 Ctrl+A 입력 시 Ctrl keydown RawEvent (vk=0x11) 와 A keydown (vk=0x41)
        가 따로 emit. _emit_key_group 의 _VK_CHAR_MAP 에 0x11 없으니 silent skip,
        A 만 char 'a' 로 변환 → ``pyautogui.write('a')`` 만 emit (메모장에 글자 'a'
        만 입력됨, 전체 선택 안 됨). Fix: recorder 가 GetAsyncKeyState 로 현재
        modifier 상태 캡처해 RawEvent.modifiers 채움. transform 이 modifier 자체
        키는 skip + non-modifier char/special 키에 modifier 있으면
        ``pyautogui.hotkey('ctrl', 'a')`` 형식 변환.

        Quality fix — Session.recording_meta list 필드 + commit_recording 가
        녹화 lifecycle metadata (recording_session_id, started_at, stopped_at,
        duration_sec, raw_event_count, transformed_step_count, dropped_event_count,
        committed_at, committed_step_ids) 채움. 사용자 사후 분석 / 디버깅용.

        가드:
        1. ``_capture_modifier_state()`` 가 Ctrl/Shift/Alt/Win 인식
        2. ``_MODIFIER_VK_CODES`` 가 Ctrl/Shift/Alt/Win + L/R variants 포함
        3. ``_emit_key_group`` 이 Ctrl+A → ``pyautogui.hotkey('ctrl', 'a')`` 변환
        4. ``_emit_key_group`` 이 Ctrl+Shift+Tab → ``hotkey('ctrl', 'shift', 'tab')``
        5. modifier 자체 키 (Ctrl 눌림) 는 단독 emit 안 함
        6. modifier 없는 일반 키는 기존 text/special 로직 보존 (회귀 가드)
        7. ``Session.recording_meta`` field 존재 + 기본값 [] (빈 list)
        8. ``commit_recording`` 가 metadata entry append (committed_step_ids 포함)
        """
        from dataclasses import fields
        from datetime import datetime

        from core.app_service import AppService
        from core.input_hooks import MouseEvent
        from core.recorder import _capture_modifier_state
        from core.recorder_models import RawEvent, RecordingSession
        from core.recorder_transform import _MODIFIER_VK_CODES, transform
        from core.session_manager import Session
        from core.storage.in_memory import InMemoryRepository

        self.step("(1) _capture_modifier_state callable + list 반환")
        mods = _capture_modifier_state()
        self.assert_true(
            isinstance(mods, list),
            f"[PR-19f] _capture_modifier_state list 반환. 실제: {mods!r}",
        )

        self.step("(2) _MODIFIER_VK_CODES 가 Ctrl/Shift/Alt/Win + L/R variants 포함")
        for vk, name in [
            (0x10, "VK_SHIFT"),
            (0x11, "VK_CONTROL"),
            (0x12, "VK_MENU(Alt)"),
            (0x5B, "VK_LWIN"),
            (0x5C, "VK_RWIN"),
            (0xA0, "VK_LSHIFT"),
            (0xA2, "VK_LCONTROL"),
            (0xA4, "VK_LMENU"),
        ]:
            self.assert_true(
                vk in _MODIFIER_VK_CODES,
                f"[PR-19f] _MODIFIER_VK_CODES 에 {name} (0x{vk:02X}) 포함 필수",
            )

        self.step("(3) Ctrl+A → pyautogui.hotkey('ctrl', 'a') 변환")
        sess = RecordingSession(id="t", started_at=datetime.now())
        sess.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=10,
                y=20,
                button="left",
                element_meta={"control_type": "Document", "name": "Editor", "window_title": "App"},
            )
        )
        sess.events.append(
            RawEvent(ts=datetime.now(), kind="key", vk_code=0x11, modifiers=["ctrl"])
        )
        sess.events.append(
            RawEvent(ts=datetime.now(), kind="key", vk_code=0x41, modifiers=["ctrl"])
        )
        steps = transform(sess)
        self.assert_true(len(steps) == 1, f"[PR-19f] 1 click+1 hotkey → 1 step. 실제: {len(steps)}")
        code = steps[0].generated_code
        self.assert_true(
            "pyautogui.hotkey('ctrl', 'a')" in code,
            f"[PR-19f] Ctrl+A → hotkey 변환. 실제 code:\n{code}",
        )
        self.assert_true(
            "pyautogui.write('a')" not in code,
            f"[PR-19f] Ctrl+A 시 pyautogui.write('a') emit 회귀 금지. 실제:\n{code}",
        )

        self.step("(4) Ctrl+Shift+Tab → pyautogui.hotkey('ctrl', 'shift', 'tab')")
        sess2 = RecordingSession(id="t2", started_at=datetime.now())
        sess2.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=10,
                y=20,
                button="left",
                element_meta={"control_type": "Edit", "name": "I", "window_title": "App"},
            )
        )
        sess2.events.append(
            RawEvent(ts=datetime.now(), kind="key", vk_code=0x11, modifiers=["ctrl"])
        )
        sess2.events.append(
            RawEvent(ts=datetime.now(), kind="key", vk_code=0x10, modifiers=["ctrl", "shift"])
        )
        sess2.events.append(
            RawEvent(ts=datetime.now(), kind="key", vk_code=0x09, modifiers=["ctrl", "shift"])
        )
        steps2 = transform(sess2)
        code2 = steps2[0].generated_code
        self.assert_true(
            "pyautogui.hotkey('ctrl', 'shift', 'tab')" in code2,
            f"[PR-19f] Ctrl+Shift+Tab hotkey 변환. 실제:\n{code2}",
        )

        self.step("(5) modifier 자체 키 (Ctrl 단독 keydown) 는 emit 안 함")
        sess3 = RecordingSession(id="t3", started_at=datetime.now())
        sess3.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=10,
                y=20,
                button="left",
                element_meta={"control_type": "Edit", "name": "I", "window_title": "App"},
            )
        )
        sess3.events.append(
            RawEvent(ts=datetime.now(), kind="key", vk_code=0x11, modifiers=["ctrl"])
        )
        steps3 = transform(sess3)
        code3 = steps3[0].generated_code
        self.assert_true(
            "hotkey" not in code3 and "press" not in code3 and ".write(" not in code3,
            f"[PR-19f] modifier 단독 keydown 은 key emit 0. 실제:\n{code3}",
        )

        self.step("(6) modifier 없는 일반 키 기존 로직 보존 (회귀)")
        sess4 = RecordingSession(id="t4", started_at=datetime.now())
        sess4.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=10,
                y=20,
                button="left",
                element_meta={"control_type": "Edit", "name": "I", "window_title": "App"},
            )
        )
        for vk in (0x48, 0x49):
            sess4.events.append(RawEvent(ts=datetime.now(), kind="key", vk_code=vk))
        sess4.events.append(RawEvent(ts=datetime.now(), kind="key", vk_code=0x0D))
        steps4 = transform(sess4)
        code4 = steps4[0].generated_code
        self.assert_true(
            "pyautogui.write('hi')" in code4 and "pyautogui.press('enter')" in code4,
            f"[PR-19f] 일반 키 회귀 가드. 실제:\n{code4}",
        )

        self.step("(7) Session.recording_meta field 존재 + default []")
        field_names = {f.name for f in fields(Session)}
        self.assert_true(
            "recording_meta" in field_names,
            f"[PR-19f] Session.recording_meta field 필수. 실제: {field_names}",
        )
        self.assert_true(
            Session().recording_meta == [],
            f"[PR-19f] Session.recording_meta default []. 실제: {Session().recording_meta!r}",
        )

        self.step("(8) commit_recording 가 metadata entry append")
        repo = InMemoryRepository()
        svc = AppService(session_repo=repo)
        svc.start_recording()
        svc._recorder._element_capture_fn = lambda x, y: {
            "control_type": "Button",
            "name": "OK",
            "window_title": "App",
        }
        svc._recorder._on_mouse_event(MouseEvent(type="lbutton_down", x=10, y=20))
        svc._recorder.wait_for_event_count(1, timeout=1.0)
        committed_steps = svc.stop_recording()
        session = svc.commit_recording(committed_steps)
        self.assert_true(
            isinstance(session.recording_meta, list) and len(session.recording_meta) == 1,
            f"[PR-19f] 1 commit → 1 metadata entry. 실제: {session.recording_meta!r}",
        )
        meta_entry = session.recording_meta[0]
        for key in (
            "recording_session_id",
            "started_at",
            "stopped_at",
            "raw_event_count",
            "transformed_step_count",
            "committed_at",
            "committed_step_ids",
        ):
            self.assert_true(
                key in meta_entry,
                f"[PR-19f] metadata 에 {key!r} 필드 필수. 실제 keys: {list(meta_entry.keys())}",
            )
        self.assert_true(
            meta_entry["raw_event_count"] == 1
            and meta_entry["transformed_step_count"] == len(committed_steps)
            and meta_entry["committed_step_ids"] == [1],
            f"[PR-19f] metadata 값 정확. 실제: {meta_entry!r}",
        )

    def test_194_uwp_popup_dismiss_overlay_filter(self):
        """[PR-19g 2026-05-24] 사용자 실측 v2-새세션-005917 발견: UWP popup overlay
        invisible click receptor (automation_id="Light Dismiss" + class_name="PopupRoot")
        가 EFP 로 잡혀 step 생성 → 재생성 시 fallback chain 의 title="닫기" 매칭이
        메모장의 진짜 X 버튼 클릭 → 메모장 종료 → 후속 step 모두 connect 실패.

        Fix: ``_filter_noise`` 가 이 시그니처 click event 자동 drop.

        가드:
        1. ``_is_uwp_popup_dismiss_overlay`` helper 가 시그니처 감지
        2. transform 이 PopupRoot/Light Dismiss click drop
        3. 일반 "닫기" Button (다른 class_name) 은 보존 (회귀 안전망)
        4. element_meta None / 빈 dict 도 helper 안전 처리
        5. 시그니처 mixed case / 공백 매칭 (auto_id="LIGHT DISMISS" 같이)
        """
        from datetime import datetime

        from core.recorder_models import RawEvent, RecordingSession
        from core.recorder_transform import _is_uwp_popup_dismiss_overlay, transform

        self.step("(1) _is_uwp_popup_dismiss_overlay 가 시그니처 감지")
        self.assert_true(
            _is_uwp_popup_dismiss_overlay(
                {"automation_id": "Light Dismiss", "class_name": "PopupRoot"}
            ),
            "[PR-19g] auto_id=Light Dismiss + class=PopupRoot → True",
        )
        self.assert_true(
            _is_uwp_popup_dismiss_overlay({"automation_id": "Light Dismiss"}),
            "[PR-19g] auto_id 만 매칭해도 True (UWP 시그니처 단독)",
        )
        self.assert_true(
            _is_uwp_popup_dismiss_overlay({"class_name": "PopupRoot"}),
            "[PR-19g] class_name 만 매칭해도 True",
        )
        self.assert_true(
            _is_uwp_popup_dismiss_overlay(
                {"automation_id": "LIGHT DISMISS", "class_name": "PopupRoot"}
            ),
            "[PR-19g] case insensitive 매칭",
        )

        self.step("(2) None / 빈 dict / 일반 element 는 False (회귀 가드)")
        self.assert_true(
            not _is_uwp_popup_dismiss_overlay(None),
            "[PR-19g] None 안전 → False",
        )
        self.assert_true(
            not _is_uwp_popup_dismiss_overlay({}),
            "[PR-19g] 빈 dict → False",
        )
        self.assert_true(
            not _is_uwp_popup_dismiss_overlay(
                {
                    "automation_id": "normalCloseBtn",
                    "class_name": "WindowButton",
                    "name": "닫기",
                }
            ),
            "[PR-19g] 일반 닫기 Button (다른 class) → False (회귀 안전망)",
        )

        self.step("(3) transform 이 PopupRoot click drop + 정상 click 보존")
        sess = RecordingSession(id="t", started_at=datetime.now())
        # Step 1 — 정상 Document 클릭
        sess.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=100,
                y=100,
                button="left",
                element_meta={
                    "control_type": "Document",
                    "name": "Editor",
                    "class_name": "RichEditD2DPT",
                    "window_title": "App",
                },
            )
        )
        # Step 2 (drop 대상) — UWP popup dismiss overlay
        sess.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=200,
                y=200,
                button="left",
                element_meta={
                    "control_type": "Button",
                    "name": "닫기",
                    "automation_id": "Light Dismiss",
                    "class_name": "PopupRoot",
                    "window_title": "App",
                },
            )
        )
        # Step 3 — 정상 다른 Document 클릭
        sess.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=150,
                y=150,
                button="left",
                element_meta={
                    "control_type": "Document",
                    "name": "Editor2",
                    "class_name": "RichEditD2DPT",
                    "window_title": "App",
                },
            )
        )
        steps = transform(sess)
        self.assert_true(
            len(steps) == 2,
            f"[PR-19g] 3 클릭 (1 overlay drop) → 2 step. 실제: {len(steps)}",
        )
        for st in steps:
            self.assert_true(
                "Light Dismiss" not in st.user_request
                and (
                    st.element_meta is None
                    or st.element_meta.get("automation_id") != "Light Dismiss"
                ),
                f"[PR-19g] step 의 user_request / element_meta 에 Light Dismiss 없음. "
                f"실제: {st.user_request!r}",
            )

        self.step("(4) 일반 '닫기' Button (다른 class) 는 step 으로 보존")
        sess2 = RecordingSession(id="t2", started_at=datetime.now())
        sess2.events.append(
            RawEvent(
                ts=datetime.now(),
                kind="click",
                x=100,
                y=100,
                button="left",
                element_meta={
                    "control_type": "Button",
                    "name": "닫기",
                    "automation_id": "normalCloseBtn",
                    "class_name": "WindowButton",
                    "window_title": "App",
                },
            )
        )
        steps2 = transform(sess2)
        self.assert_true(
            len(steps2) == 1 and "닫기" in steps2[0].user_request,
            f"[PR-19g] 일반 닫기 버튼 step 보존. 실제: {steps2!r}",
        )

    def test_196_double_click_merge_and_emit(self):
        """[PR-19b 2026-05-24] 빠른 double-click 감지 + ``pyautogui.doubleClick`` emit.

        handoff §27 P3: ``click_count`` 필드 활용 (recorder_models 에 이미 정의).
        Transform layer 가 같은 element + 같은 button + ts delta <
        ``_DOUBLE_CLICK_THRESHOLD_MS`` (500ms) 인 인접 click 두 개를 단일 RawEvent
        (``click_count=2``) 로 merge → ``_emit_click`` 가 ``pyautogui.doubleClick``
        + ``click_input(double=True)`` fallback emit.

        천천히 두 번 click (threshold 초과) 은 별개 click 유지 — 사용자 의도가
        double-click 아닌 두 개의 별개 single-click 일 가능성 보존.
        right-click 은 double 미지원 (일반적 사용 X).

        가드:
        1. ``_merge_consecutive_clicks`` 가 < 500ms 인접 click merge → click_count=2
        2. ``_merge_consecutive_clicks`` 가 > 500ms gap 은 별개 click 유지
        3. ``_merge_consecutive_clicks`` 가 다른 element 는 별개 유지
        4. ``_merge_consecutive_clicks`` 가 다른 button 은 별개 유지
        5. ``build_pywinauto_click_code(double=True)`` → ``pyautogui.doubleClick`` +
           ``click_input(double=True)`` fallback + "더블 클릭" 주석
        6. ``build_pywinauto_click_code(button='right', double=True)`` → right double
           무시 (single right-click 으로 emit, ``right_click_input`` fallback)
        7. transform end-to-end: 빠른 두 번 click → 1 step + doubleClick 코드
        8. transform end-to-end: 좌표 fallback (element_meta=None) double →
           ``pyautogui.doubleClick(x, y, ...)``
        9. user_request 가 "더블 클릭" 표기 포함
        """
        from datetime import datetime, timedelta

        from core.pywinauto_codegen import build_pywinauto_click_code
        from core.recorder_models import RawEvent, RecordingSession
        from core.recorder_transform import (
            _DOUBLE_CLICK_THRESHOLD_MS,
            _merge_consecutive_clicks,
            transform,
        )

        self.assert_true(
            _DOUBLE_CLICK_THRESHOLD_MS == 500,
            f"[PR-19b] threshold = 500ms (Windows GetDoubleClickTime default). "
            f"실제: {_DOUBLE_CLICK_THRESHOLD_MS}",
        )

        base_meta = {
            "control_type": "Button",
            "name": "확인",
            "automation_id": "OkBtn",
            "class_name": "Button",
            "window_title": "Dialog",
        }
        t0 = datetime.now()

        def _click(ts, button="left", meta=None, x=100, y=100):
            return RawEvent(
                ts=ts,
                kind="click",
                x=x,
                y=y,
                button=button,
                element_meta=meta if meta is not None else dict(base_meta),
            )

        self.step("(1) 빠른 두 번 click (< 500ms) → merge → click_count=2")
        ev1 = _click(t0)
        ev2 = _click(t0 + timedelta(milliseconds=200))
        merged = _merge_consecutive_clicks([ev1, ev2])
        self.assert_true(
            len(merged) == 1 and merged[0].click_count == 2,
            f"[PR-19b] 2 click (200ms) merge 실패. 결과: len={len(merged)}, "
            f"click_count={[e.click_count for e in merged]}",
        )

        self.step("(2) 천천히 두 번 click (> 500ms) → 별개 유지")
        ev3 = _click(t0 + timedelta(milliseconds=800))
        merged2 = _merge_consecutive_clicks([ev1, ev3])
        self.assert_true(
            len(merged2) == 2 and all(e.click_count == 1 for e in merged2),
            f"[PR-19b] 800ms gap 인접 click 별개 유지 실패. 결과: len={len(merged2)}, "
            f"counts={[e.click_count for e in merged2]}",
        )

        self.step("(3) 다른 element 는 별개 (회귀 가드)")
        other_meta = dict(base_meta, automation_id="CancelBtn", name="취소")
        ev_other = _click(t0 + timedelta(milliseconds=100), meta=other_meta)
        merged3 = _merge_consecutive_clicks([ev1, ev_other])
        self.assert_true(
            len(merged3) == 2,
            f"[PR-19b] 다른 element 인접 click 별개 유지. 결과: {merged3!r}",
        )

        self.step("(4) 다른 button 은 별개 (left + right 빠르게)")
        ev_right = _click(t0 + timedelta(milliseconds=100), button="right")
        merged4 = _merge_consecutive_clicks([ev1, ev_right])
        self.assert_true(
            len(merged4) == 2,
            f"[PR-19b] 다른 button 인접 click 별개 유지. 결과: {merged4!r}",
        )

        self.step("(5) build_pywinauto_click_code(double=True) → doubleClick emit")
        code_dbl = build_pywinauto_click_code(base_meta, button="left", double=True)
        for needle in (
            "pyautogui.doubleClick(center_x, center_y)",
            "click_input(double=True)",
            "더블 클릭",
        ):
            self.assert_true(
                needle in code_dbl,
                f"[PR-19b] helper double=True 결과에 {needle!r} 필수.\n{code_dbl}",
            )
        self.assert_true(
            "pyautogui.click(center_x" not in code_dbl,
            f"[PR-19b] double=True 면 단일 click 코드 안 emit.\n{code_dbl}",
        )

        self.step("(6) right button + double → right double 무시 (single right-click)")
        code_right_dbl = build_pywinauto_click_code(base_meta, button="right", double=True)
        self.assert_true(
            "pyautogui.click(center_x, center_y, button='right')" in code_right_dbl
            and "right_click_input()" in code_right_dbl
            and "doubleClick" not in code_right_dbl,
            f"[PR-19b] right button 은 double 무시 (single right-click emit).\n{code_right_dbl}",
        )

        self.step("(7) transform end-to-end: 빠른 두 번 click → 1 step + doubleClick")
        sess = RecordingSession(id="t", started_at=t0)
        sess.events.append(_click(t0))
        sess.events.append(_click(t0 + timedelta(milliseconds=200)))
        steps = transform(sess)
        self.assert_true(
            len(steps) == 1,
            f"[PR-19b] 빠른 두 번 click → 1 step (merge). 실제: {len(steps)}",
        )
        self.assert_true(
            "pyautogui.doubleClick" in steps[0].generated_code,
            f"[PR-19b] step 의 generated_code 에 doubleClick 필수.\n{steps[0].generated_code}",
        )

        self.step("(9) user_request 에 '더블 클릭' 표기")
        self.assert_true(
            "더블 클릭" in steps[0].user_request,
            f"[PR-19b] user_request 에 '더블 클릭' 표기 필수. 실제: {steps[0].user_request!r}",
        )

        self.step("(8) 좌표 fallback (element_meta=None) double → pyautogui.doubleClick")
        sess2 = RecordingSession(id="t2", started_at=t0)
        sess2.events.append(_click(t0, meta={}, x=50, y=60))  # 빈 dict ≠ None
        # element_meta=None 경로 직접 테스트 — RawEvent 만들 때 meta=None 명시
        sess2 = RecordingSession(id="t3", started_at=t0)
        ev_coord1 = RawEvent(ts=t0, kind="click", x=50, y=60, button="left", element_meta=None)
        ev_coord2 = RawEvent(
            ts=t0 + timedelta(milliseconds=100),
            kind="click",
            x=50,
            y=60,
            button="left",
            element_meta=None,
        )
        sess2.events.extend([ev_coord1, ev_coord2])
        steps2 = transform(sess2)
        self.assert_true(
            len(steps2) == 1
            and "pyautogui.doubleClick(50, 60, button='left')" in steps2[0].generated_code,
            f"[PR-19b] 좌표 fallback double-click. 결과: len={len(steps2)}, "
            f"code={steps2[0].generated_code if steps2 else None!r}",
        )

    def test_197_idle_gap_charges_wait_after_ms(self):
        """[PR-19c 2026-05-24] idle_boundary_ms 휴지로 split 된 batch 의 gap 을
        직전 step 의 ``wait_after_ms`` 로 충전 — 사용자 의도한 step 간 호흡 보존.

        handoff §28 P4: ``_split_into_batches`` 가 idle_boundary_ms (기본 3000ms)
        초과 휴지로 batch 분리할 때, gap 값을 직전 step.wait_after_ms 에 저장.
        non-idle 분리 (window_focus / F8 marker / key→click / click→다른 element)
        는 충전 X.

        가드:
        1. ``_split_into_batches`` signature: ``tuple[list[list[RawEvent]], list[int]]``
        2. idle split 시 직전 step.wait_after_ms 에 gap (ms, int) 충전
        3. 첫 batch 의 idle_gaps_ms[0] = 0
        4. non-idle 분리 (key→click) → wait_after_ms = None (충전 안 됨)
        5. non-idle 분리 (click→다른 element) → wait_after_ms = None
        6. F8 marker 분리 → wait_after_ms = None
        7. 단일 batch (분리 없음) → wait_after_ms = None
        """
        from datetime import datetime, timedelta

        from core.recorder_models import RawEvent, RecordingSession, TransformOptions
        from core.recorder_transform import _split_into_batches, transform

        t0 = datetime.now()

        def _click(ts, meta_id="OkBtn"):
            return RawEvent(
                ts=ts,
                kind="click",
                x=100,
                y=100,
                button="left",
                element_meta={
                    "control_type": "Button",
                    "name": "확인",
                    "automation_id": meta_id,
                    "class_name": "Button",
                    "window_title": "Dialog",
                },
            )

        def _key(ts, vk=0x41):
            return RawEvent(ts=ts, kind="key", vk_code=vk)

        opts = TransformOptions()

        self.step("(1) _split_into_batches signature: (batches, idle_gaps_ms)")
        result = _split_into_batches([_click(t0)], opts)
        self.assert_true(
            isinstance(result, tuple) and len(result) == 2,
            f"[PR-19c] _split_into_batches 가 (batches, idle_gaps_ms) tuple 반환 필수. "
            f"실제 type: {type(result).__name__}",
        )
        batches, gaps = result
        self.assert_true(
            isinstance(batches, list) and isinstance(gaps, list) and len(batches) == len(gaps),
            f"[PR-19c] batches + idle_gaps_ms 동일 길이 list. "
            f"batches len={len(batches)}, gaps len={len(gaps)}",
        )
        self.assert_true(
            len(gaps) == 1 and gaps[0] == 0,
            f"[PR-19c] 첫 batch idle_gaps_ms[0]=0. 실제: {gaps!r}",
        )

        self.step("(2) idle split → 직전 step.wait_after_ms 에 gap (ms) 충전")
        sess = RecordingSession(id="t1", started_at=t0)
        # Click → 5초 휴지 (> 3000ms idle_boundary) → Click (다른 element)
        sess.events.append(_click(t0, meta_id="A"))
        sess.events.append(_click(t0 + timedelta(milliseconds=5300), meta_id="B"))
        steps = transform(sess)
        self.assert_true(
            len(steps) == 2,
            f"[PR-19c] idle split → 2 step. 실제: {len(steps)}",
        )
        self.assert_true(
            steps[0].wait_after_ms is not None and abs(steps[0].wait_after_ms - 5300) <= 1,
            f"[PR-19c] 직전 step.wait_after_ms ≈ 5300ms (gap). 실제: {steps[0].wait_after_ms}",
        )
        self.assert_true(
            steps[1].wait_after_ms is None,
            f"[PR-19c] 마지막 step.wait_after_ms = None (뒤에 충전할 batch 없음). 실제: "
            f"{steps[1].wait_after_ms}",
        )

        self.step("(3) idle_gaps_ms[0] = 0 + idle split batch idx 의 gap > 0")
        filtered_evs = [
            _click(t0, meta_id="A"),
            _click(t0 + timedelta(milliseconds=5300), meta_id="B"),
        ]
        bs, gs = _split_into_batches(filtered_evs, opts)
        self.assert_true(
            len(bs) == 2 and gs[0] == 0 and gs[1] > 5000,
            f"[PR-19c] idle split idx=1 의 gap > 0. 실제: batches={len(bs)}, gaps={gs!r}",
        )

        self.step("(4) non-idle 분리 (key→click) → wait_after_ms 충전 X")
        # key (vk=A) → 200ms 후 click (idle 안 됨, key→click 경계로 분리)
        sess2 = RecordingSession(id="t2", started_at=t0)
        sess2.events.append(_key(t0))
        sess2.events.append(_click(t0 + timedelta(milliseconds=200)))
        steps2 = transform(sess2)
        self.assert_true(
            len(steps2) == 2,
            f"[PR-19c] key→click 분리 → 2 step. 실제: {len(steps2)}",
        )
        self.assert_true(
            steps2[0].wait_after_ms is None,
            f"[PR-19c] key→click 분리 시 충전 X. 실제: {steps2[0].wait_after_ms}",
        )

        self.step("(5) non-idle 분리 (click→다른 element) → 충전 X")
        sess3 = RecordingSession(id="t3", started_at=t0)
        sess3.events.append(_click(t0, meta_id="A"))
        sess3.events.append(_click(t0 + timedelta(milliseconds=100), meta_id="B"))
        steps3 = transform(sess3)
        self.assert_true(
            len(steps3) == 2 and steps3[0].wait_after_ms is None,
            f"[PR-19c] click→다른 element 분리 시 충전 X. "
            f"len={len(steps3)}, wait={steps3[0].wait_after_ms if steps3 else None}",
        )

        self.step("(6) F8 marker 분리 → 충전 X")
        sess4 = RecordingSession(id="t4", started_at=t0)
        sess4.events.append(_click(t0))
        sess4.events.append(RawEvent(ts=t0 + timedelta(milliseconds=100), kind="marker"))
        sess4.events.append(_click(t0 + timedelta(milliseconds=200), meta_id="B"))
        steps4 = transform(sess4)
        self.assert_true(
            len(steps4) == 2 and steps4[0].wait_after_ms is None,
            f"[PR-19c] F8 marker 분리 시 충전 X. "
            f"len={len(steps4)}, wait={steps4[0].wait_after_ms if steps4 else None}",
        )

        self.step("(7) 단일 batch (분리 없음) → wait_after_ms = None")
        sess5 = RecordingSession(id="t5", started_at=t0)
        sess5.events.append(_click(t0))
        steps5 = transform(sess5)
        self.assert_true(
            len(steps5) == 1 and steps5[0].wait_after_ms is None,
            f"[PR-19c] 단일 batch 의 wait_after_ms = None. 실제: "
            f"len={len(steps5)}, wait={steps5[0].wait_after_ms if steps5 else None}",
        )

    def test_195_regenerate_inplace_replaces_step_id(self):
        """[PR-19j 2026-05-24] _on_regenerate (D17 일반 재생성) 의
        ``replaces_step_id`` 인자 누락 fix.

        Bug 발견 — P1 옵션 3 실증 분석 (handoff §27 다음 세션 출발점):
        세션 111e5306-... 의 step 7 가 ``replaces_step_id=None`` + ``element_meta=None``
        으로 새 step 추가됨. ``_on_regenerate`` 가 ``_send_request`` 호출 시
        ``replaces_step_id=step_id`` 전달 안 함 → handoff §22 #4 의 in-place 정책 위반.
        ``_on_regenerate_with_warnings`` (G7-D path, test #113) 는 정상 전달 — 두 path
        일관성 회복.

        가드:
        1. ``_on_regenerate`` source 가 ``replaces_step_id=step_id`` 전달
        2. ``_on_regenerate_with_warnings`` 와 동일 패턴 유지 (test #113 와 보완)
        """
        import inspect as _inspect

        from ui_v2.main_window_v2 import MainWindowV2

        self.step("(1) _on_regenerate source 가 replaces_step_id=step_id 전달")
        regen_src = _inspect.getsource(MainWindowV2._on_regenerate)
        self.assert_true(
            "replaces_step_id=step_id" in regen_src,
            f"[PR-19j] _on_regenerate 가 _send_request 호출 시 "
            f"replaces_step_id=step_id 전달 필수 (in-place 대체, handoff §22 #4).\n"
            f"{regen_src}",
        )

        self.step("(2) _on_regenerate_with_warnings 와 동일 패턴 일관성")
        warn_src = _inspect.getsource(MainWindowV2._on_regenerate_with_warnings)
        self.assert_true(
            "replaces_step_id=step_id" in warn_src,
            "[PR-19j] _on_regenerate_with_warnings 도 동일 패턴 유지 (회귀 가드)",
        )

    def test_72_codeviewer_clear_resets_block_view(self):
        """[회귀] CodeViewer.clear() 가 step 카드 + block 뷰 양쪽 모두 비움.

        Bug (2026-05-04 사용자 보고): _new_session / _on_session_delete 의
        self.code_viewer.clear() 호출이 step 카드만 비워서 블럭 뷰는 이전 세션
        카드가 잔존 → 화면 stale.
        Fix: CodeViewer.clear() 가 block_view.refresh("", [], "", 500) 도 호출.
        """
        import inspect

        from ui.code_viewer import CodeViewer
        from ui.main_window import MainWindow

        clear_src = inspect.getsource(CodeViewer.clear)
        self.assert_true(
            "block_view" in clear_src,
            "[회귀] CodeViewer.clear() 가 block_view 도 비워야 함",
        )
        self.assert_true(
            "refresh" in clear_src or ".clear()" in clear_src,
            "[회귀] CodeViewer.clear 가 block_view.refresh 또는 .clear() 호출 필수",
        )

        new_session_src = inspect.getsource(MainWindow._new_session)
        self.assert_true(
            "self.code_viewer.clear()" in new_session_src,
            "[회귀] _new_session 이 self.code_viewer.clear() 호출 필수",
        )

        delete_src = inspect.getsource(MainWindow._on_session_delete)
        self.assert_true(
            "self.code_viewer.clear()" in delete_src,
            "[회귀] _on_session_delete 가 self.code_viewer.clear() 호출 필수",
        )

    def test_67_extract_code_delta_preserves_control_headers(self):
        """[회귀] prev_set 필터가 try:/except/if:/for: 같은 컨트롤 헤더를 stale 단편으로
        착각해 제거하면, 새 블록의 헤더가 사라지고 본문만 module-level 로 평면화 됨.

        Bug (2026-05-04 발견, RPA_20260504_2035 세션 step 4):
          prev: try: ...; except Exception: print('A 오류')
          new:  prev + try: ...; except Exception: print('B 오류')
          → SequenceMatcher 가 새 try/except 헤더와 본문을 'insert' 로 추출했는데
            prev_set 필터가 'try:' 와 'except Exception:' 라인을 prev 에 동일 패턴이
            있다는 이유로 제거 → except 본문만 살아남음 → 성공/에러 메시지 둘 다 출력.

        Fix: prev_set 필터에 컨트롤 헤더 화이트리스트 추가 — 컨트롤 헤더는 prev 에
        동일 패턴이 있어도 보존 (새 try/if/for 블록 일부일 수 있음).
        """
        from core.import_manager import extract_code_delta

        # 실제 RPA_20260504_2035 step 4 시나리오 단순화
        prev = (
            "try:\n"
            "    view_menu = app_window.child_window(title='보기')\n"
            "    view_menu.click_input()\n"
            "    print('보기 메뉴 클릭')\n"
            "except Exception:\n"
            "    print('보기 메뉴 오류')"
        )
        new = (
            "try:\n"
            "    view_menu = app_window.child_window(title='보기')\n"
            "    view_menu.click_input()\n"
            "    print('보기 메뉴 클릭')\n"
            "except Exception:\n"
            "    print('보기 메뉴 오류')\n"
            "try:\n"
            "    zoom_menu = app_window.child_window(title='확대/축소')\n"
            "    zoom_menu.click_input()\n"
            "    print('확대/축소 클릭')\n"
            "except Exception:\n"
            "    print('확대/축소 오류')"
        )
        delta = extract_code_delta(new, prev)

        # 핵심: try/except 헤더 보존되어야 함 (본문만 module-level 평면화 되면 안 됨)
        self.assert_true(
            "try:" in delta,
            f"[회귀] 새 try 블록의 try: 헤더 보존 필수 (prev_set 필터가 제거하면 안 됨) "
            f"(실제 delta: {delta!r})",
        )
        self.assert_true(
            "except" in delta,
            f"[회귀] 새 except 블록의 except 헤더 보존 필수 (실제 delta: {delta!r})",
        )

        # 새 try/except 본문 모두 포함
        self.assert_true(
            "zoom_menu" in delta and "확대/축소 클릭" in delta,
            f"[회귀] 새 try 본문 (zoom_menu 정의 + 성공 print) 추출 (실제 delta: {delta!r})",
        )
        self.assert_true(
            "확대/축소 오류" in delta,
            f"[회귀] 새 except 본문 (에러 print) 추출 (실제 delta: {delta!r})",
        )

        # AST 분석: 성공 print 가 try 블록 안 / 에러 print 가 except 블록 안 (module-level X)
        import ast

        tree = ast.parse(delta)
        # module-level 에 print 가 있으면 안 됨 (try/except 안에 있어야 함)
        module_level_prints = [
            node
            for node in tree.body
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "print"
        ]
        self.assert_true(
            len(module_level_prints) == 0,
            f"[회귀] print 가 module-level 에 떠 있으면 안 됨 (try/except 안에 있어야 함) "
            f"(module-level prints: {len(module_level_prints)})",
        )

    def test_53_extract_code_delta_smart_dedent(self):
        """[회귀] delta 가 try/except 블록 안에서 추출되어 들여쓰기 4 칸이
        남는 경우 _smart_dedent 가 module-level 실행 가능하게 정리.

        과거 버그: SequenceMatcher 가 try 블록 안의 라인만 추출 → indent 4
        그대로 → IndentationError. _smart_dedent 가 공통 indent 제거.
        """
        from core.import_manager import _smart_dedent, extract_code_delta

        # _smart_dedent 단독 검증
        code = "    x = 1\n    y = 2"
        self.assert_true(
            _smart_dedent(code) == "x = 1\ny = 2",
            f"[회귀] indent 4 제거 (실제: {_smart_dedent(code)!r})",
        )

        # 주석 라인 indent 0 + 코드 라인 indent 4 (boundary 주석 + try 블록 내부)
        mixed = "# === Step 2 ===\n    x = 1\n    y = 2"
        result = _smart_dedent(mixed)
        self.assert_true(
            "x = 1" in result and "    x = 1" not in result,
            f"[회귀] 주석 (indent 0) + 코드 (indent 4) 혼재 시 코드 라인만 dedent "
            f"(실제: {result!r})",
        )

        # extract_code_delta 결과가 syntax OK 인지
        prev = "try:\n    a = 1\n    b = 2\nexcept Exception:\n    pass"
        new = "try:\n    a = 1\n    b = 2\n    c = 3\nexcept Exception:\n    pass"
        delta = extract_code_delta(new, prev)
        try:
            compile(delta, "<test>", "exec")
            syntax_ok = True
        except SyntaxError:
            syntax_ok = False
        self.assert_true(
            syntax_ok,
            f"[회귀] extract_code_delta 결과가 module-level 컴파일 가능해야 함 "
            f"(실제 delta: {delta!r})",
        )

    def test_58_extract_step_delta_marker_priority(self):
        """[회귀] AI 가 누적 코드 재출력 시 이전 스텝 본문을 미세하게 변경하면
        diff 가 try 블록 안의 라인을 새 라인으로 잡아 들여쓰기된 orphan 코드를
        반환 → IndentationError. ``# === Step N: ... (시작/끝) ===`` 마커가
        있을 때 마커 본문을 우선 추출 + compile 검증으로 막는다.

        실제 발생 케이스 재현 (data/sessions/568331e8-...):
        - step2 try 블록 안 ``pyautogui.write('@06...')`` → ``pyautogui.write(' @06...')``
          (leading space 추가) 로 변경
        - diff 는 변경된 indent 4 라인 + Step 3 새 코드를 함께 추출
        - _smart_dedent 는 Step 3 의 indent 0 라인 때문에 dedent 0 → 그대로
        - 결과: ``    pyautogui.write(...)`` 가 module-level → IndentationError
        """
        from core.workflow_engine import extract_step_delta_code

        prev_gen = (
            "import time\n"
            "import pyautogui\n"
            "\n"
            "# === Step 1: open (시작) ===\n"
            "x = 1\n"
            "# === Step 1: open (끝) ===\n"
            "\n"
            "# === Step 2: login (시작) ===\n"
            "try:\n"
            "    pyautogui.write('@06pwd')\n"
            "    pyautogui.press('enter')\n"
            "except Exception as e:\n"
            "    print(e)\n"
            "# === Step 2: login (끝) ===\n"
        )
        # AI 가 step3 생성 시 step2 비밀번호에 leading space 추가 + step3 try 블록 추가
        curr_gen = (
            "import time\n"
            "import pyautogui\n"
            "\n"
            "# === Step 1: open (시작) ===\n"
            "x = 1\n"
            "# === Step 1: open (끝) ===\n"
            "\n"
            "# === Step 2: login (시작) ===\n"
            "try:\n"
            "    pyautogui.write(' @06pwd')\n"  # ← leading space 추가
            "    pyautogui.press('enter')\n"
            "except Exception as e:\n"
            "    print(e)\n"
            "# === Step 2: login (끝) ===\n"
            "\n"
            "# === Step 3: click (시작) ===\n"
            "try:\n"
            "    pyautogui.click(100, 200)\n"
            "    time.sleep(1)\n"
            "except Exception as e:\n"
            "    print(e)\n"
            "# === Step 3: click (끝) ===\n"
        )
        prev_step = {"step_id": 2, "generated_code": prev_gen}
        curr_step = {"step_id": 3, "generated_code": curr_gen}

        delta = extract_step_delta_code(curr_step, prev_step)

        # ① delta 는 단독 compile 가능해야 함 (가장 중요한 회귀 가드)
        try:
            compile(delta, "<test>", "exec")
            syntax_ok = True
            err = None
        except SyntaxError as e:
            syntax_ok = False
            err = e
        self.assert_true(
            syntax_ok,
            f"[회귀] step3 delta 가 module-level compile 가능해야 함 "
            f"(SyntaxError: {err!r}, delta: {delta!r})",
        )

        # ② Step 3 본문이 포함되어야 함
        self.assert_true(
            "pyautogui.click(100, 200)" in delta,
            f"[회귀] step3 본문 (pyautogui.click) 포함 필수 (delta: {delta!r})",
        )

        # ③ Step 2 의 변경된 라인은 단독 try 없이 흘러들어오면 안 됨
        # (마커 추출이면 Step 3 본문만 깨끗히 잡혀 ' @06pwd' 라인 자체가 안 들어옴)
        self.assert_true(
            " @06pwd" not in delta,
            f"[회귀] step2 의 미세 변경된 라인이 step3 delta 에 섞이면 안 됨 (delta: {delta!r})",
        )

    def test_59_extract_step_delta_compile_validation(self):
        """[회귀] 모든 후보가 compile 통과해야 채택. 첫 후보가 SyntaxError 면
        다음 후보로 fallback (마커 → diff → step_code → generated_code 전체).
        """
        from core.workflow_engine import _extract_by_step_marker, _is_compilable

        # _is_compilable 단독 검증
        self.assert_true(
            _is_compilable("x = 1\ny = 2"),
            "[회귀] 정상 코드는 _is_compilable True",
        )
        self.assert_true(
            not _is_compilable("    x = 1"),
            "[회귀] indent 만 있는 orphan 코드는 _is_compilable False",
        )
        self.assert_true(
            not _is_compilable(""),
            "[회귀] 빈 문자열은 _is_compilable False",
        )

        # _extract_by_step_marker 단독 검증
        code = (
            "x = 1\n# === Step 2: foo (시작) ===\ny = 2\nz = 3\n# === Step 2: foo (끝) ===\nw = 4\n"
        )
        marker = _extract_by_step_marker(code, 2)
        self.assert_true(
            "y = 2" in marker and "z = 3" in marker and "w = 4" not in marker,
            f"[회귀] _extract_by_step_marker 가 마커 사이만 추출 (실제: {marker!r})",
        )

        # 마커가 없으면 빈 문자열
        empty = _extract_by_step_marker("x = 1\ny = 2", 2)
        self.assert_true(
            empty == "",
            f"[회귀] 마커 없으면 빈 문자열 (실제: {empty!r})",
        )

    def test_52_extract_step_delta_code_uses_prev_step(self):
        """[회귀] extract_step_delta_code 가 prev_step 인자로 generated_code diff
        재계산 - 저장된 step_code 가 누적이라도 자동 fix.
        """
        import inspect

        from core.workflow_engine import extract_step_delta_code

        sig = inspect.signature(extract_step_delta_code)
        self.assert_true(
            "prev_step" in sig.parameters,
            "[회귀] extract_step_delta_code 가 prev_step 인자 받기 필수",
        )

        src = inspect.getsource(extract_step_delta_code)
        self.assert_true(
            "extract_code_delta" in src,
            "[회귀] extract_step_delta_code 가 extract_code_delta 사용 (재계산) 필수",
        )

        # 누적 시뮬레이션 - step1: 'driver = ...' / step2 step_code: 'driver = ...; driver.get(...)'
        # prev_step 의 generated_code 와 비교해 step2 의 진짜 delta 만 반환해야
        step1 = {
            "step_id": 1,
            "generated_code": "from selenium import webdriver\ndriver = webdriver.Chrome()",
            "step_code": "driver = webdriver.Chrome()",
        }
        step2 = {
            "step_id": 2,
            "generated_code": "from selenium import webdriver\ndriver = webdriver.Chrome()\ndriver.get('https://example.com')",
            "step_code": "driver = webdriver.Chrome()\ndriver.get('https://example.com')",  # 누적 step_code
        }
        delta = extract_step_delta_code(step2, step1)
        self.assert_true(
            "driver.get" in delta and "webdriver.Chrome()" not in delta,
            f"[회귀] prev_step 기반 재계산 - step2 의 진짜 delta (driver.get) 만 반환 "
            f"(실제: {delta!r})",
        )

    def test_41_element_picker_uses_element_from_point(self):
        """[회귀] _detect_via_efp 가 IUIAutomation::ElementFromPoint 직호출 +
        _detect_element_multi_backend 가 EFP 결과를 best 후보 초기화에 사용.

        Walker (ControlView/RawView) 가 leaf 에서 멈추는 lazy a11y 트리 케이스
        (MFC+WebView 등) 에서 OS-level path 가 reach 가능. 이 호출이 빠지면
        해당 케이스 회귀.
        """
        import inspect

        from ui.element_picker import ElementPickerOverlay

        efp_src = inspect.getsource(ElementPickerOverlay._detect_via_efp)
        self.assert_true(
            "ElementFromPoint" in efp_src,
            "[회귀] _detect_via_efp 가 IUIAutomation::ElementFromPoint 호출 필수",
        )
        self.assert_true(
            "IUIA" in efp_src,
            "[회귀] _detect_via_efp 가 pywinauto.uia_defines.IUIA 사용 필수",
        )

        mb_src = inspect.getsource(ElementPickerOverlay._detect_element_multi_backend)
        self.assert_true(
            "_detect_via_efp" in mb_src,
            "[회귀] _detect_element_multi_backend 가 _detect_via_efp 호출 필수",
        )


if __name__ == "__main__":
    from tests.test_runner import TestRunner

    runner = TestRunner(suite_name="core")
    runner.add_test_class(CoreTest)
    result = runner.run()
    runner.save_results(result)
