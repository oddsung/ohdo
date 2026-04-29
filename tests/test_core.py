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

import sys
import json
import tempfile
from pathlib import Path
from dataclasses import asdict

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_runner import TestCase, SkipTest


class CoreTest(TestCase):
    suite = "core"

    def setup(self):
        pass  # 코어 테스트는 OS 제한 없음

    # ──────────────────────────────────────────
    # SessionManager 테스트
    # ──────────────────────────────────────────

    def test_01_session_create_and_load(self):
        """세션 생성 → 저장 → 로드 사이클"""
        from core.session_manager import SessionManager, Session

        self.step("임시 디렉토리에 세션 매니저 생성")
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SessionManager(data_dir=Path(tmpdir))

            self.step("세션 생성")
            session = manager.create_session(
                title="테스트 세션",
                project_type="desktop",
                description="단위 테스트용"
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
                step = Step(generated_code=f"print('step {i+1}')")
                manager.add_step(session, step)
            self.assert_equal(len(session.steps), 3, "3개 스텝이 추가되어야 합니다")

            self.step("스텝 업데이트")
            manager.update_step(session, step_id=2, updates={
                "status": "completed",
                "generated_code": "print('updated step 2')"
            })
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
                "스텝 1이 아래로 이동해야 합니다"
            )

    def test_03_session_list_and_delete(self):
        """세션 목록 조회 및 삭제"""
        from core.session_manager import SessionManager

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SessionManager(data_dir=Path(tmpdir))

            self.step("세션 3개 생성")
            ids = []
            for i in range(3):
                s = manager.create_session(title=f"세션 {i+1}")
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
            self.assert_true((result_dir / "requirements.txt").exists(), "requirements.txt가 생성되어야 합니다")
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
            session=session,
            user_request="메모장을 열어줘",
            project_type="desktop"
        )
        self.assert_contains(prompt, "메모장을 열어줘", "사용자 요청이 프롬프트에 포함되어야 합니다")
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
        prompt = builder.build_step_prompt(
            session=session,
            user_request="다음 작업을 해줘"
        )
        self.assert_contains(prompt, "import time", "이전 스텝 코드가 포함되어야 합니다")
        self.assert_contains(prompt, "누적 코드", "누적 코드 안내가 있어야 합니다")

    def test_08_prompt_builder_error_recovery(self):
        """에러 복구 프롬프트 생성"""
        from core.prompt_builder import PromptBuilder

        builder = PromptBuilder(prompts_config={})

        self.step("에러 복구 프롬프트")
        prompt = builder.build_error_recovery_prompt(
            error_message="ModuleNotFoundError: No module named 'xxx'",
            current_code="import xxx\nxxx.do_something()"
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
            is_browser_element=True
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
                "available_engines": {
                    "gemini_cli": {"command": "gemini", "timeout_seconds": 30}
                }
            }
        }
        manager = AIEngineManager(settings)
        self.assert_equal(manager.get_current_name(), "gemini_cli", "기본 엔진이 gemini_cli이어야 합니다")

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
                "available_engines": {
                    "gemini_cli": {"command": "gemini"}
                }
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
            "name": "",                # 이름 없음
            "automation_id": "",        # auto_id 없음
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
            "automation_id": "12345678",   # 순수 숫자 = 동적 ID
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

        code = (
            '"""모듈 설명"""\n'
            "import os\n"
            "import pywinauto\n"
            "\n"
            "print('hello')\n"
        )
        imports, body = extract_imports(code)
        self.assert_equal(len(imports), 2, "docstring 이후 import 2개 추출")
        self.assert_contains(body, "print('hello')", "body에 코드 포함")

    def test_21_extract_imports_midcode_import_stays(self):
        """import_manager: 코드 중간의 import는 body에 유지"""
        from core.import_manager import extract_imports

        code = (
            "import os\n"
            "\n"
            "x = 1\n"
            "import json  # 중간 import\n"
            "print(x)\n"
        )
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
        from core.session_manager import SessionManager, Session, Step

        self.step("스텝 2개로 export (conversation 포함)")
        with tempfile.TemporaryDirectory() as td:
            sm = SessionManager(data_dir=Path(td))
            session = Session(
                session_id="export_test",
                title="경계 주석 테스트",
                created_at="2026-01-01",
            )
            session.steps = [
                asdict(Step(
                    step_id=1, status="completed",
                    generated_code="import os\nimport time\n\nprint(os.getcwd())",
                    conversation=[{"role": "user", "content": "현재 디렉토리 출력"}],
                )),
                asdict(Step(
                    step_id=2, status="completed",
                    generated_code="import os\nimport pywinauto\n\napp = pywinauto.Application()",
                    conversation=[{"role": "user", "content": "메모장 연결"}],
                )),
            ]
            result = sm.export_workflow(session)
            # import 중복 제거
            os_count = result.count("import os")
            self.assert_equal(os_count, 1, "export에서 import os 중복 제거")
            # 경계 주석 확인
            self.assert_contains(result, "# === Step 1: 현재 디렉토리 출력 (시작) ===", "스텝1 시작 주석")
            self.assert_contains(result, "# === Step 1: 현재 디렉토리 출력 (끝) ===", "스텝1 끝 주석")
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
                'python_path': sys.executable,
                'python_version': '3.12.0',
                'packages': {'all_required_installed': True, 'required': [], 'optional': []},
            }
            ok = scanner.save_environment(payload)
            self.assert_true(ok, "save_environment 는 성공해야 합니다")

            self.step("저장된 환경 로드")
            loaded = scanner.load_saved_environment()
            self.assert_not_none(loaded, "저장 직후 로드는 dict 를 반환해야 합니다")
            self.assert_equal(loaded.get('python_path'), sys.executable)
            self.assert_true('machine_id' in loaded, "machine_id 가 자동으로 박혀야 합니다")
            self.assert_true('last_scan' in loaded, "last_scan 타임스탬프가 박혀야 합니다")

    def test_28_env_load_other_machine_resets(self):
        """다른 컴퓨터의 machine_id 면 None 반환 + 환경 파일 삭제"""
        from core.environment_scanner import EnvironmentScanner

        with tempfile.TemporaryDirectory() as td:
            scanner = EnvironmentScanner(config_dir=Path(td))

            self.step("타 컴퓨터의 환경 파일 시뮬레이션")
            fake = {
                'machine_id': 'deadbeef00000000',  # 절대 매칭되지 않을 hex
                'hostname': 'other-pc',
                'python_path': sys.executable,
                'last_scan': '2020-01-01T00:00:00',
            }
            scanner.env_file.write_text(json.dumps(fake), encoding='utf-8')
            self.assert_true(scanner.env_file.exists(), "사전 조건: 환경 파일이 존재")

            self.step("load_saved_environment 호출")
            loaded = scanner.load_saved_environment()
            self.assert_true(loaded is None, "다른 머신의 설정은 None 을 반환해야 합니다")
            self.assert_true(not scanner.env_file.exists(), "다른 머신 감지 시 파일이 삭제되어야 합니다")

    def test_29_probe_python_version_current(self):
        """_probe_python_version 이 현재 인터프리터 버전을 반환해야 한다"""
        from core.environment_scanner import EnvironmentScanner
        import platform as _platform

        version = EnvironmentScanner._probe_python_version(sys.executable)
        expected = _platform.python_version()
        self.assert_equal(
            version, expected,
            f"sys.executable({sys.executable}) 의 버전 = {expected}"
        )

    def test_30_check_gemini_cli_not_found(self):
        """존재하지 않는 명령어로 호출 시 not_found 에러를 반환"""
        from core.environment_scanner import EnvironmentScanner

        with tempfile.TemporaryDirectory() as td:
            scanner = EnvironmentScanner(config_dir=Path(td))
            result = scanner.check_gemini_cli(command="ohdo_nonexistent_cli_xyz_zzz")

            self.assert_equal(result['installed'], False, "없는 명령은 installed=False")
            self.assert_equal(result['error'], 'not_found')
            self.assert_true(result['path'] is None, "PATH 에서 못 찾으면 path=None")
            self.assert_not_none(result['detail'], "사용자에게 보일 detail 메시지가 있어야 함")

    def test_31_check_gemini_cli_shape(self):
        """기본 'gemini' 호출의 결과 dict 가 약속된 shape 를 가져야 한다.

        설치 여부와 무관하게 dict 의 키 집합과 타입이 일관되어야 dialog
        쪽에서 분기 코드를 단순하게 유지할 수 있다.
        """
        from core.environment_scanner import EnvironmentScanner

        with tempfile.TemporaryDirectory() as td:
            scanner = EnvironmentScanner(config_dir=Path(td))
            result = scanner.check_gemini_cli()

            for key in ('installed', 'command', 'path', 'version', 'error', 'detail'):
                self.assert_true(key in result, f"결과 dict 에 '{key}' 키가 있어야 합니다")
            self.assert_equal(result['command'], 'gemini')
            self.assert_true(isinstance(result['installed'], bool), "installed 는 bool")
            if result['installed']:
                self.assert_true(result['error'] is None, "installed=True 면 error=None")
                self.assert_not_none(result['version'], "installed=True 면 version 존재")
            else:
                self.assert_not_none(result['error'], "installed=False 면 error 존재")

    def test_32_full_scan_includes_gemini_section(self):
        """full_scan 결과 dict 에 'gemini_cli' 섹션이 포함되어야 한다"""
        from core.environment_scanner import EnvironmentScanner

        with tempfile.TemporaryDirectory() as td:
            scanner = EnvironmentScanner(config_dir=Path(td))
            result = scanner.full_scan(sys.executable)

            self.assert_equal(result.get('success'), True, "full_scan 성공")
            self.assert_true('gemini_cli' in result, "결과에 gemini_cli 섹션 포함")
            gemini = result['gemini_cli']
            self.assert_true(isinstance(gemini, dict), "gemini_cli 는 dict")
            self.assert_true('installed' in gemini and isinstance(gemini['installed'], bool))


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
        from core.execution_kernel import ExecutionKernel
        import time

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
        from ui.element_picker import ElementPickerOverlay
        import inspect

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
        from ui.element_picker import ElementPickerOverlay
        import inspect

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
        from ui.element_picker import ElementPickerOverlay
        import inspect

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

    def test_43_element_picker_general_mode_no_transparent_leak(self):
        """[회귀] 일반 picker mode (F3 누르기 전) 의 mouseover 누수 0 보장.

        _detect_element_multi_backend 가 cursor tracking 을 위해 매 tick 마다
        WS_EX_TRANSPARENT 토글하면 underlying app 에 mouseover 효과 누수.
        어제 (2026-04-28) 사용자 보고로 0 토글 패턴 도입. 이 보장은 방향 B 통합
        과 무관하게 유지 — F3 누르기 전 일반 picker mode 한정.

        post_pause_mode 의 누수는 의도된 trade-off (test_42 참조).
        """
        from ui.element_picker import ElementPickerOverlay
        import inspect

        mb_src = inspect.getsource(
            ElementPickerOverlay._detect_element_multi_backend
        )
        # 일반 picker mode 의 detection 흐름은 SetWindowLongW 호출 0
        # (docstring 에 WS_EX_TRANSPARENT 멘션은 OK — 실제 토글 코드 부재만 검증)
        self.assert_true(
            "SetWindowLongW" not in mb_src,
            "[회귀] _detect_element_multi_backend 가 SetWindowLongW 호출하면 안 됨 "
            "(매 tick WS_EX_TRANSPARENT 토글로 mouseover 누수 회귀 위험)",
        )

    def test_44_element_picker_mouse_hook_in_post_pause(self):
        """[회귀] post_pause_mode 는 WS_EX_TRANSPARENT 켜져 있어 overlay 가
        mouse 이벤트를 못 받음 → WH_MOUSE_LL hook 으로 click 감지 + 통과.

        방향 B 통합으로 mouse hook 항상 설치 (이전에는 keep_submenu_mode 분기).

        hook 함수 존재 + _resume_after_pause 가 항상 설치 + _exit_post_pause_mode
        가 해제 + _on_hook_click 이 element_picked emit + stop_picking.
        """
        from ui.element_picker import ElementPickerOverlay
        import inspect

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

        # _install_mouse_hook 가 WH_MOUSE_LL + WM_LBUTTONDOWN 사용
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
            "CallNextHookEx" in imh_src,
            "[회귀] _install_mouse_hook 가 click 통과 (CallNextHookEx 호출) 필수",
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
        from ui.element_picker import ElementPickerOverlay
        import inspect

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
        from ui.element_picker import ElementPickerOverlay
        import inspect

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

    def test_41_element_picker_uses_element_from_point(self):
        """[회귀] _detect_via_efp 가 IUIAutomation::ElementFromPoint 직호출 +
        _detect_element_multi_backend 가 EFP 결과를 best 후보 초기화에 사용.

        Walker (ControlView/RawView) 가 leaf 에서 멈추는 lazy a11y 트리 케이스
        (MFC+WebView 등) 에서 OS-level path 가 reach 가능. 이 호출이 빠지면
        해당 케이스 회귀.
        """
        from ui.element_picker import ElementPickerOverlay
        import inspect

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
