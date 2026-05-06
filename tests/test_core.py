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
        from ui.element_picker import ElementPickerOverlay
        import inspect

        mb_src = inspect.getsource(
            ElementPickerOverlay._detect_element_multi_backend
        )
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

    def test_47_element_picker_descendants_area_threshold(self):
        """[회귀] descendants() 폴백 호출이 area threshold 가드 적용 — 반응성.

        walker 가 이미 작은 element (Excel cell, 메뉴 항목, 작은 버튼) 잡았으면
        descendants 호출 skip. 매 tick 800-1000ms 절약 → cursor 이동 시
        highlight 추적 지연 감소.
        """
        from ui.element_picker import ElementPickerOverlay
        import inspect

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
        from ui.element_picker import ElementPickerOverlay
        import inspect

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
            'cdp_available' in cdc_src and 'False' in cdc_src,
            "[회귀] _capture_dom_context 가 disabled 시 cdp_available=False 반환",
        )

    def test_49_workflow_engine_stop_after_step_id(self):
        """[회귀] Phase 1 - Step 단독 실행. workflow_engine.execute_session_blocks
        가 stop_after_step_id 인자 지원해서 N 만 실행하고 종료.

        UI: BlockCard 의 '⏯ 단독' 버튼 → run_single_requested signal →
        BlockViewWidget run_single_step_requested → CodeViewer 통과 →
        main_window._on_run_single_step → _run_blocks_thread(start=stop=N).
        """
        from core.workflow_engine import WorkflowEngine
        import inspect

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
        from ui.code_viewer import BlockCard, BlockViewWidget, CodeViewer
        from ui.main_window import MainWindow
        import inspect

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
            "[회귀] BlockExecutionHandler.on_run_single_step 가 start=stop=N "
            "으로 호출 필수",
        )

    def test_51_extract_code_delta_handles_minor_changes(self):
        """[회귀] extract_code_delta 가 SequenceMatcher fallback 으로 AI 의
        약간의 코드 변형 (들여쓰기, try 위치 등) 도 delta 추출.

        과거 버그: prefix 매칭 실패 시 fallback = new_body 전체 → step_code 가
        누적되어 매 step 마다 webdriver/Application 새로 생성 (브라우저 N개).
        SequenceMatcher 로 새 라인만 추출.
        """
        from core.import_manager import extract_code_delta
        import inspect

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
        from ui.main_window import MainWindow, AsyncSignals
        from ui.block_execution_handler import BlockExecutionHandler
        import inspect

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
        from core.session_manager import Step, Session
        from core.workflow_engine import WorkflowEngine
        from ui.code_viewer import BlockCard, BlockViewWidget, CodeViewer
        from ui.main_window import MainWindow
        import inspect

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
            "current_session.settings" in handler_src
            and "step_delay_ms" in handler_src,
            "[회귀] BlockExecutionHandler.on_wait_changed 가 "
            "current_session.settings.step_delay_ms 변경 필수 (글로벌 settings 분리)",
        )

    def test_62_close_event_single_definition(self):
        """[회귀] MainWindow.closeEvent 가 단일 정의 + 세션 저장 + 커널 정리.

        과거 buggy 동작: closeEvent 가 두 번 정의되어 첫 번째 (커널 정리) 가
        두 번째 (세션 저장) 에 덮어쓰여 커널 좀비 프로세스 발생.
        """
        from ui.main_window import MainWindow
        import inspect

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
            def __init__(self, steps): self.steps = steps

        # 케이스 1: 모듈 레벨 Assign
        sess1 = _Session([
            {"step_id": 1, "generated_code": 'URL = "https://example.com"\nCONFIG = {"k": 1}'}
        ])
        result1 = extract_initial_block(sess1)
        self.assert_true(
            "URL" in result1 and "CONFIG" in result1,
            f"[회귀] 모듈 레벨 Assign 추출 (실제: {result1!r})",
        )

        # 케이스 2: 모듈 레벨 try 블록 안의 setup
        sess2 = _Session([
            {"step_id": 1, "generated_code": (
                "import x\n"
                "try:\n"
                "    options = Options()\n"
                "    driver = webdriver.Chrome(options=options)\n"
                "    driver.get('http://x')\n"
                "except Exception:\n"
                "    pass"
            )}
        ])
        result2 = extract_initial_block(sess2)
        self.assert_true(
            "options" in result2 and "driver" in result2,
            f"[회귀] try 블록 안 setup Assign 추출 (실제: {result2!r})",
        )

        # 케이스 3: def main() 패턴 unwrap
        sess3 = _Session([
            {"step_id": 1, "generated_code": (
                'def main():\n'
                '    URL = "https://test.com"\n'
                '    driver = build()\n'
                'if __name__ == "__main__":\n'
                '    main()'
            )}
        ])
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
        from ui.code_viewer import BlockViewWidget, CodeViewer
        from ui.main_window import MainWindow
        import inspect

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
        from ui.block_execution_handler import BlockExecutionHandler
        import inspect

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
        from ui.main_window import MainWindow
        from ui.block_execution_handler import BlockExecutionHandler
        import inspect

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
            "[회귀] BlockExecutionHandler.restore_main_window 가 raise_ + "
            "activateWindow 호출 필수",
        )

        # on_blocks_finished 가 restore_main_window 호출
        src3 = inspect.getsource(BlockExecutionHandler.on_blocks_finished)
        self.assert_true(
            "restore_main_window" in src3,
            "[회귀] BlockExecutionHandler.on_blocks_finished 가 restore_main_window "
            "호출 필수",
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
        from core.import_manager import _unwrap_main_function
        import ast

        code = '''
def main():
    driver = "chrome"
    print(driver)

if __name__ == "__main__":
    main()
'''
        unwrapped = _unwrap_main_function(code)
        tree = ast.parse(unwrapped)

        # def main 제거 + if __name__ 제거 + 본문은 module level
        has_main = any(
            isinstance(n, ast.FunctionDef) and n.name == "main" for n in tree.body
        )
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
            f"[회귀] 필터링 후 delta 가 module-level 컴파일 가능해야 함",
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
        from core.execution_kernel import ExecutionKernel
        from pathlib import Path
        import inspect

        # ExecutionKernel.start 가 OHDO_PARENT_PID 환경변수에 os.getpid() 전달
        start_src = inspect.getsource(ExecutionKernel.start)
        self.assert_true(
            "OHDO_PARENT_PID" in start_src and "getpid()" in start_src,
            "[회귀] ExecutionKernel.start 가 env['OHDO_PARENT_PID'] = "
            "str(os.getpid()) 로 부모 PID 전달 필수 (kernel_worker 가 권한 양도용)",
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
            'sys.platform == "win32"' in worker_src
            or "sys.platform=='win32'" in worker_src,
            "[회귀] kernel_worker.py 가 Windows 전용 가드 필수 "
            "(ctypes.windll 사용 분기)",
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
        from core.prompt_builder import PromptBuilder
        from core.session_manager import Session
        import json
        from pathlib import Path

        # ── prompt_builder.build_step_prompt 검증 ──
        builder = PromptBuilder(prompts_config={})

        self.step("첫 스텝 (current_code 없음) - def main + except 변수 가이드")
        session = Session(session_id="test", title="테스트")
        prompt_first = builder.build_step_prompt(
            session=session,
            user_request="메모장 열어줘",
            project_type="desktop"
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
            {"step_id": 1, "status": "completed",
             "generated_code": "from selenium import webdriver\ndriver = webdriver.Chrome()"}
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
        from core.session_manager import SessionManager, Session, Step
        from core.workflow_engine import extract_step_delta_code
        import inspect
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
            "Application" in new_generated and "Keys" in new_generated
            and "하이닉스" in new_generated and "삼성전자" not in new_generated,
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
            mgr.add_step(sess, Step(
                step_id=1, generated_code=step1_code, step_code=step1_code,
                conversation=[{"role": "user", "content": "네이버 접속"}],
            ))

            step2_full = step1_code + "\nsearch.send_keys('삼성전자 주가')"
            step2_delta = "search.send_keys('삼성전자 주가')"
            mgr.add_step(sess, Step(
                step_id=2, generated_code=step2_full, step_code=step2_delta,
                conversation=[{"role": "user", "content": "검색어 입력"}],
            ))

            # 블럭 뷰 수정: 삼성전자 → 하이닉스 (handler 핵심 로직 시뮬레이션)
            new_step_code = "search.send_keys('하이닉스 주가')"
            prev_gen = sess.steps[0]["generated_code"]
            new_gen = prev_gen.rstrip() + "\n\n" + new_step_code
            mgr.update_step(sess, 2, {
                "step_code": new_step_code,
                "generated_code": new_gen,
                "manually_edited": True,
                "edit_original_code": step2_full,
            })

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
        from ui.main_window import MainWindow
        from ui.ai_call_handler import AICallHandler
        import inspect

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
            (Path(__file__).parent.parent / "config" / "settings.json")
            .read_text(encoding="utf-8")
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
            "[회귀] -p path Popen 가 self._build_args(gemini_exec, \"-p\", ...) 사용 필수 "
            "(raw [gemini_exec, \"-p\", ...] 리터럴은 -m 플래그 누락 회귀)",
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
        from ui.ai_call_handler import AICallHandler
        from ui.block_execution_handler import BlockExecutionHandler
        from ui.code_viewer import CodeViewer, BlockViewWidget
        import inspect

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
        from core.execution_kernel import INITIAL_BLOCK_STEP_ID, LIBRARY_BLOCK_STEP_ID
        from ui.code_viewer import BlockCard, BlockViewWidget
        from ui.block_execution_handler import BlockExecutionHandler
        import inspect

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
            "init_card.run_single_requested.connect(self.run_single_step_requested)"
            in refresh_src,
            "[회귀] BlockViewWidget.refresh 가 init_card.run_single_requested ->"
            " run_single_step_requested 연결 필수 (signal 라우팅)",
        )

        # 4. BlockExecutionHandler.on_run_single_step 가 INITIAL_BLOCK_STEP_ID 분기
        on_single_src = inspect.getsource(BlockExecutionHandler.on_run_single_step)
        self.assert_true(
            "INITIAL_BLOCK_STEP_ID" in on_single_src
            and "on_run_initial_block" in on_single_src,
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
            "code_edit.toPlainText()" in on_init_src
            and "INITIAL_BLOCK_STEP_ID" in on_init_src,
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
            or "kernel.execute_block(initial_code, step_id=INITIAL_BLOCK_STEP_ID"
            in thread_src,
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
        from core.adapters.openai_compat_adapter import OpenAICompatAdapter, PRESETS
        from core.adapters.base_adapter import BaseAIAdapter, AIResponse
        from core.ai_engine import AIEngineManager
        import json
        from pathlib import Path

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
            (Path(__file__).parent.parent / "config" / "settings.json")
            .read_text(encoding="utf-8")
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

    def test_72_codeviewer_clear_resets_block_view(self):
        """[회귀] CodeViewer.clear() 가 step 카드 + block 뷰 양쪽 모두 비움.

        Bug (2026-05-04 사용자 보고): _new_session / _on_session_delete 의
        self.code_viewer.clear() 호출이 step 카드만 비워서 블럭 뷰는 이전 세션
        카드가 잔존 → 화면 stale.
        Fix: CodeViewer.clear() 가 block_view.refresh("", [], "", 500) 도 호출.
        """
        from ui.code_viewer import CodeViewer
        from ui.main_window import MainWindow
        import inspect

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
            f"[회귀] 새 except 블록의 except 헤더 보존 필수 "
            f"(실제 delta: {delta!r})",
        )

        # 새 try/except 본문 모두 포함
        self.assert_true(
            "zoom_menu" in delta and "확대/축소 클릭" in delta,
            f"[회귀] 새 try 본문 (zoom_menu 정의 + 성공 print) 추출 "
            f"(실제 delta: {delta!r})",
        )
        self.assert_true(
            "확대/축소 오류" in delta,
            f"[회귀] 새 except 본문 (에러 print) 추출 "
            f"(실제 delta: {delta!r})",
        )

        # AST 분석: 성공 print 가 try 블록 안 / 에러 print 가 except 블록 안 (module-level X)
        import ast
        tree = ast.parse(delta)
        # module-level 에 print 가 있으면 안 됨 (try/except 안에 있어야 함)
        module_level_prints = [
            node for node in tree.body
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
        from core.import_manager import extract_code_delta, _smart_dedent

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
            f"[회귀] step2 의 미세 변경된 라인이 step3 delta 에 섞이면 안 됨 "
            f"(delta: {delta!r})",
        )

    def test_59_extract_step_delta_compile_validation(self):
        """[회귀] 모든 후보가 compile 통과해야 채택. 첫 후보가 SyntaxError 면
        다음 후보로 fallback (마커 → diff → step_code → generated_code 전체).
        """
        from core.workflow_engine import _is_compilable, _extract_by_step_marker

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
            "x = 1\n"
            "# === Step 2: foo (시작) ===\n"
            "y = 2\n"
            "z = 3\n"
            "# === Step 2: foo (끝) ===\n"
            "w = 4\n"
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
        from core.workflow_engine import extract_step_delta_code
        import inspect

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
