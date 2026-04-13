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

        self.step("인터랙티브 브라우저 요소 (direct click)")
        button_elem = {
            "control_type": "Button",
            "name": "Submit",
            "automation_id": "submitBtn",
            "class_name": "button",
            "rect": {"left": 100, "top": 200, "width": 80, "height": 30},
            "parent_window_title": "Chrome",
            "is_browser": True,
            "browser_type": "Chrome",
        }
        text = inspector.get_element_info_text(button_elem)
        self.assert_contains(text, "find_and_click", "Button은 find_and_click 패턴이어야 합니다")

        self.step("비인터랙티브 브라우저 요소 (JS click)")
        text_elem = {
            "control_type": "Text",
            "name": "메뉴항목",
            "automation_id": "",
            "class_name": "span",
            "rect": {"left": 50, "top": 100, "width": 60, "height": 20},
            "parent_window_title": "Chrome",
            "is_browser": True,
            "browser_type": "Chrome",
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


if __name__ == "__main__":
    from tests.test_runner import TestRunner
    runner = TestRunner(suite_name="core")
    runner.add_test_class(CoreTest)
    result = runner.run()
    runner.save_results(result)
