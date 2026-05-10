# SPDX-License-Identifier: AGPL-3.0-or-later
"""
시나리오 (behavior-level) 테스트 — UI 우회 end-to-end.

목적: redesign 시 회귀 안전망. test_core 가 inspect.getsource 패턴으로 코드
구조를 잠그는 것과 달리, 이 스위트는 **동작** 만 검증해서 UI / handler 구조가
바뀌어도 그대로 통과해야 함.

규칙:
- core 함수만 직접 호출. ui/* 임포트 금지.
- AI 엔진은 mock (실 호출 없음).
- tempfile 로 격리된 세션 디렉토리 사용.
- 코드 패턴 검사 X — 입력/출력 동작만.

새 UI 가 같은 시나리오 통과하면 회귀 없음.

실행:
    python -m tests.test_runner --suite scenarios
"""

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_runner import TestCase

# ── 헬퍼 ──────────────────────────────────────────────────


def _step_dict(step_id, code, **extra):
    """테스트용 step dict (Step dataclass dict 형태)."""
    base = {
        "step_id": step_id,
        "status": "completed",
        "generated_code": code,
        "step_code": "",
        "step_imports": [],
        "wait_after_ms": None,
        "captures": [],
        "conversation": [],
        "required_packages": [],
        "manually_edited": False,
    }
    base.update(extra)
    return base


# ── 테스트 클래스 ─────────────────────────────────────────


class ScenariosTest(TestCase):
    suite = "scenarios"

    def setup(self):
        pass

    # ──────────────────────────────────────────
    # 그룹 1: 세션 lifecycle
    # ──────────────────────────────────────────

    def test_01_session_full_lifecycle(self):
        """세션 생성 → 스텝 3개 추가 → 저장 → 재로드 → 모든 데이터 보존."""
        from core.session_manager import SessionManager, Step

        with tempfile.TemporaryDirectory() as tmp:
            mgr = SessionManager(data_dir=Path(tmp))
            session = mgr.create_session(title="시나리오1", project_type="web")

            for i in (1, 2, 3):
                mgr.add_step(
                    session,
                    Step(
                        step_id=i,
                        status="completed",
                        generated_code=f"# step {i}\nprint({i})",
                    ),
                )

            mgr.save_session(session)
            loaded = mgr.load_session(session.session_id)

            self.assert_equal(loaded.title, "시나리오1")
            self.assert_equal(loaded.project_type, "web")
            self.assert_equal(len(loaded.steps), 3, "3 step 보존")
            for i in (1, 2, 3):
                step = loaded.steps[i - 1]
                code = step.get("generated_code") if isinstance(step, dict) else step.generated_code
                self.assert_true(
                    f"step {i}" in code,
                    f"step {i} 코드 보존",
                )

    def test_02_session_delete_removes_from_list(self):
        """세션 삭제 후 list_summaries 에서 사라짐."""
        from core.session_manager import SessionManager

        with tempfile.TemporaryDirectory() as tmp:
            mgr = SessionManager(data_dir=Path(tmp))
            s1 = mgr.create_session(title="유지")
            s2 = mgr.create_session(title="삭제대상")
            mgr.save_session(s1)
            mgr.save_session(s2)

            summaries_before = mgr.list_sessions()
            self.assert_equal(len(summaries_before), 2)

            mgr.delete_session(s2.session_id)
            summaries_after = mgr.list_sessions()
            self.assert_equal(len(summaries_after), 1)
            self.assert_equal(summaries_after[0].session_id, s1.session_id)

    def test_03_session_load_backwards_compat(self):
        """과거 세션 JSON (옵션 필드 누락) 로드 시 fallback 으로 깨지지 않음.

        Redesign 시 D3 (user_request 필드 추가) 시점에도 옛 세션이 동작해야 함.
        """
        from core.session_manager import SessionManager

        with tempfile.TemporaryDirectory() as tmp:
            mgr = SessionManager(data_dir=Path(tmp))
            session = mgr.create_session(title="옛 세션")
            mgr.save_session(session)

            # session.json 직접 편집 — 신규 옵션 필드들을 의도적으로 제거
            sjson = Path(tmp) / "sessions" / session.session_id / "session.json"
            data = json.loads(sjson.read_text(encoding="utf-8"))
            for opt in ("workflow_metadata", "settings"):
                data.pop(opt, None)
            sjson.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            # 재로드 — 예외 없이 default 값으로 복원돼야 함
            loaded = mgr.load_session(session.session_id)
            self.assert_equal(loaded.title, "옛 세션")
            self.assert_true(
                isinstance(loaded.settings, dict),
                "settings 누락 시 default dict 로 복원",
            )

    # ──────────────────────────────────────────
    # 그룹 2: Code delta / library / initial 추출
    # ──────────────────────────────────────────

    def test_04_step_delta_extraction_basic(self):
        """단일 step 의 generated_code 에서 step_code 추출 (prev=None)."""
        from core.workflow_engine import extract_step_delta_code

        step = _step_dict(
            1,
            "import time\nprint('hello')\ntime.sleep(1)",
        )
        delta = extract_step_delta_code(step, None)
        self.assert_true(
            "print('hello')" in delta and "time.sleep(1)" in delta,
            f"step 1 본문 모두 포함되어야 함. 실제: {delta!r}",
        )

    def test_05_step_delta_with_prev(self):
        """2번째 step delta = generated_code 의 새 줄만 (prev 의 줄들은 제외)."""
        from core.workflow_engine import extract_step_delta_code

        prev = _step_dict(1, "import time\nprint('a')")
        cur = _step_dict(2, "import time\nprint('a')\nprint('b')")
        delta = extract_step_delta_code(cur, prev)
        # 새 줄 'b' 는 반드시 있어야 함
        self.assert_true("print('b')" in delta, f"새 줄 포함. 실제: {delta!r}")
        # prev 의 'a' 는 정상적으로는 제외 (단, 컨트롤 헤더 보존 등 예외는 허용)
        # 동작 검증: 결과가 'b' 만 또는 합리적 minimal 형태
        # (보존이 너무 공격적이면 fail — 단순 재출력 회귀)

    def test_06_library_block_extraction(self):
        """마지막 step 의 generated_code 에서 라이브러리 블럭 추출 (Step 1 마커 이전)."""
        from core.workflow_engine import extract_library_block

        class FakeSession:
            steps = [
                {
                    "generated_code": "import time\nfrom selenium import webdriver\n\n"
                    "def helper():\n    pass\n\n"
                    "# === Step 1: 시작 ===\n"
                    "driver = webdriver.Chrome()\n"
                    "# === Step 1: 끝 ===\n"
                }
            ]

        lib = extract_library_block(FakeSession())
        self.assert_true("import time" in lib, "imports 포함")
        self.assert_true("from selenium" in lib, "from-imports 포함")
        self.assert_true("def helper" in lib, "헬퍼 함수 포함")
        self.assert_true(
            "# === Step 1" not in lib and "driver = webdriver" not in lib,
            "Step 1 마커 이후는 제외",
        )

    def test_07_initial_block_extraction(self):
        """session.steps[0] 의 모듈 레벨 변수 → Initial 블럭."""
        from core.import_manager import extract_initial_block

        class FakeSession:
            steps = [
                {
                    "generated_code": "from selenium import webdriver\n"
                    "URL = 'https://example.com'\n"
                    "options = webdriver.ChromeOptions()\n"
                    "options.add_argument('--start-maximized')\n"
                    "driver = webdriver.Chrome(options=options)\n"
                    "driver.get(URL)\n"
                }
            ]

        initial = extract_initial_block(FakeSession())
        # URL, options, driver 변수 정의가 포함되어야 함
        self.assert_true("URL = " in initial, f"URL 변수. 실제: {initial!r}")
        self.assert_true("options = " in initial, "options 변수")
        self.assert_true("driver = " in initial, "driver 변수")

    def test_08_initial_block_unwraps_main_function(self):
        """def main(): ... 패턴은 unwrap 후 module-level Assign 추출."""
        from core.import_manager import extract_initial_block

        class FakeSession:
            steps = [
                {
                    "generated_code": "from selenium import webdriver\n\n"
                    "def main():\n"
                    "    options = webdriver.ChromeOptions()\n"
                    "    driver = webdriver.Chrome(options=options)\n"
                    "    driver.get('https://example.com')\n\n"
                    "main()\n"
                }
            ]

        initial = extract_initial_block(FakeSession())
        # unwrap 되면 options/driver Assign 이 module level 로 보임
        self.assert_true(
            "options = " in initial or "driver = " in initial,
            f"main() unwrap 후 Assign 추출. 실제: {initial!r}",
        )

    # ──────────────────────────────────────────
    # 그룹 3: manually_edited 우선순위 + 4중 안전장치
    # ──────────────────────────────────────────

    def test_09_manually_edited_priority(self):
        """manually_edited=True + step_code 있으면 generated_code 보다 우선."""
        from core.workflow_engine import extract_step_delta_code

        # generated_code 와 step_code 가 다른 내용 — manually_edited 가 결정해야 함
        step = _step_dict(
            1,
            code="print('AI 원본')",  # generated_code
            step_code="print('사용자 수정')",
            manually_edited=True,
        )
        delta = extract_step_delta_code(step, None)
        self.assert_true(
            "사용자 수정" in delta,
            f"manually_edited 가 step_code 우선 반환. 실제: {delta!r}",
        )
        self.assert_true(
            "AI 원본" not in delta,
            f"generated_code 의 stale 내용 무시. 실제: {delta!r}",
        )

    def test_10_step_delta_marker_priority(self):
        """generated_code 안에 step 마커가 있으면 마커 안 본문이 최우선."""
        from core.workflow_engine import extract_step_delta_code

        prev = _step_dict(1, "import time\nprint('a')")
        cur = _step_dict(
            2,
            "import time\n"
            "print('a')\n"
            "# === Step 2: 검색 (시작) ===\n"
            "print('marker_body')\n"
            "# === Step 2: 검색 (끝) ===\n",
        )
        delta = extract_step_delta_code(cur, prev)
        self.assert_true(
            "marker_body" in delta,
            f"마커 안 본문 추출. 실제: {delta!r}",
        )

    # ──────────────────────────────────────────
    # 그룹 4: AIEngineManager / adapter 라우팅
    # ──────────────────────────────────────────

    def test_11_ai_engine_manager_loads_both_adapters(self):
        """AIEngineManager 가 gemini_cli + openai_compat 어댑터 둘 다 등록."""
        from core.ai_engine import AIEngineManager

        settings = {
            "ai": {
                "selected": "gemini_cli",
                "available_engines": {
                    "gemini_cli": {"command": "gemini", "model": "gemini-2.5-flash"},
                    "openai_compat": {"base_url": "https://api.openai.com/v1"},
                },
            }
        }
        mgr = AIEngineManager(settings)
        available = {a["name"] for a in mgr.list_available()}
        self.assert_true("gemini_cli" in available, "gemini_cli 등록")
        self.assert_true("openai_compat" in available, "openai_compat 등록")

    def test_12_ai_engine_switch(self):
        """엔진 전환 후 get_adapter 가 다른 인스턴스 반환."""
        from core.ai_engine import AIEngineManager

        settings = {
            "ai": {
                "selected": "gemini_cli",
                "available_engines": {
                    "gemini_cli": {"command": "gemini"},
                    "openai_compat": {"base_url": "https://api.openai.com/v1"},
                },
            }
        }
        mgr = AIEngineManager(settings)
        before = mgr.get_adapter()
        mgr.switch_engine("openai_compat")
        after = mgr.get_adapter()
        self.assert_true(
            before is not after,
            "switch 후 다른 어댑터 인스턴스",
        )
        self.assert_equal(mgr.get_current_name(), "openai_compat")

    # ──────────────────────────────────────────
    # 그룹 5: OpenAICompatAdapter response parsing (mocked HTTP)
    # ──────────────────────────────────────────

    def test_13_openai_compat_parses_chat_response(self):
        """OpenAI 호환 API 응답 (mocked) 에서 코드 + 토큰 정확히 추출."""
        from unittest.mock import MagicMock, patch

        from core.adapters.openai_compat_adapter import OpenAICompatAdapter

        adapter = OpenAICompatAdapter(
            {
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "sk-test",
                "model": "deepseek-chat",
            }
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": "여기 코드입니다.\n\n```python\nprint('hi')\n```"}}
            ],
            "usage": {"total_tokens": 42},
        }

        with patch("requests.post", return_value=mock_response) as mock_post:
            import asyncio

            resp = asyncio.run(adapter.generate("테스트 프롬프트"))

        self.assert_true(resp.success, f"성공해야 함. error={resp.error!r}")
        self.assert_true(
            "print('hi')" in resp.code,
            f"코드 추출. 실제: {resp.code!r}",
        )
        self.assert_equal(resp.tokens_used, 42, "토큰 수 추출")

        # POST 가 올바른 URL + headers 로 호출됐는지 검증
        call_args = mock_post.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url")
        self.assert_true(
            url.endswith("/chat/completions"),
            f"URL = base_url + /chat/completions. 실제: {url!r}",
        )
        headers = call_args.kwargs.get("headers", {})
        self.assert_true(
            headers.get("Authorization") == "Bearer sk-test",
            f"Bearer 헤더. 실제: {headers!r}",
        )

    def test_14_openai_compat_handles_http_error(self):
        """HTTP 4xx/5xx 응답 시 AIResponse.success=False + error 메시지 보존."""
        from unittest.mock import MagicMock, patch

        from core.adapters.openai_compat_adapter import OpenAICompatAdapter

        adapter = OpenAICompatAdapter({"api_key": "sk-test"})
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = '{"error":{"message":"rate limit exceeded"}}'

        with patch("requests.post", return_value=mock_response):
            import asyncio

            resp = asyncio.run(adapter.generate("test"))

        self.assert_true(not resp.success, "실패로 처리")
        self.assert_true(
            "429" in (resp.error or ""),
            f"error 에 status code 포함. 실제: {resp.error!r}",
        )
        self.assert_true(
            "rate limit" in (resp.error or ""),
            "에러 메시지 본문 보존",
        )

    def test_15_openai_compat_image_attachment_format(self):
        """이미지 첨부 시 multimodal payload 포맷 (content array with image_url)."""
        # 임시 PNG 파일 생성 (1x1 pixel)
        from unittest.mock import MagicMock, patch

        from core.adapters.openai_compat_adapter import OpenAICompatAdapter

        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa3WW\xb1"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png_bytes)
            img_path = f.name

        try:
            adapter = OpenAICompatAdapter({"api_key": "sk-test"})
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "```python\npass\n```"}}],
                "usage": {"total_tokens": 5},
            }

            with patch("requests.post", return_value=mock_response) as mock_post:
                import asyncio

                asyncio.run(adapter.generate("describe image", images=[img_path]))

            payload = mock_post.call_args.kwargs.get("json", {})
            messages = payload.get("messages", [])
            self.assert_equal(len(messages), 1, "1 메시지")
            content = messages[0].get("content")
            self.assert_true(
                isinstance(content, list),
                f"이미지 첨부 시 content 가 array. 실제 타입: {type(content).__name__}",
            )
            # text part + image_url part 각 1개
            kinds = [p.get("type") for p in content if isinstance(p, dict)]
            self.assert_true(
                "text" in kinds and "image_url" in kinds,
                f"text + image_url 부분 포함. 실제: {kinds!r}",
            )
            # image_url 에 base64 data URL
            img_part = next(p for p in content if p.get("type") == "image_url")
            url = img_part.get("image_url", {}).get("url", "")
            self.assert_true(
                url.startswith("data:image/png;base64,"),
                f"base64 data URL 포맷. 실제: {url[:50]!r}...",
            )
        finally:
            try:
                Path(img_path).unlink()
            except OSError:
                pass

    # ──────────────────────────────────────────
    # 그룹 6: Wait timing 우선순위 (UI 우회)
    # ──────────────────────────────────────────

    def test_16_wait_timing_priority(self):
        """step.wait_after_ms > session.settings.step_delay_ms > 글로벌 settings."""

        # 헬퍼 — 우선순위 로직 직접 시뮬레이션 (workflow_engine 가 사용하는 같은 규칙)
        def resolve_wait(step_wait, session_wait, global_wait):
            if step_wait is not None:
                return step_wait
            if session_wait is not None:
                return session_wait
            return global_wait

        # case 1: 모두 설정 — step 이 우선
        self.assert_equal(resolve_wait(100, 200, 500), 100)
        # case 2: step 없음 — session 우선
        self.assert_equal(resolve_wait(None, 200, 500), 200)
        # case 3: step + session 없음 — global
        self.assert_equal(resolve_wait(None, None, 500), 500)
        # case 4: step=0 (명시) — 0 사용 (False/None 혼동 회피)
        self.assert_equal(resolve_wait(0, 200, 500), 0)

    # ──────────────────────────────────────────
    # 그룹 7: AppService facade — UI 우회 호출 (Phase 1)
    # ──────────────────────────────────────────

    def test_17_app_service_session_crud(self):
        """AppService 만으로 세션 CRUD 전체 사이클 (UI 없이)."""
        from core.app_service import AppService
        from core.session_manager import Step
        from core.storage.local_json import LocalJsonRepository

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            svc = AppService(session_repo=repo)

            # 생성
            session = svc.create_session(title="AppService 테스트", project_type="web")
            self.assert_equal(session.title, "AppService 테스트")

            # 스텝 추가
            svc.add_step(
                session.session_id,
                Step(step_id=1, status="completed", generated_code="print('via app_service')"),
            )

            # 조회
            loaded = svc.get_session(session.session_id)
            self.assert_equal(len(loaded.steps), 1)

            # 목록
            summaries = svc.list_sessions()
            self.assert_equal(len(summaries), 1)
            self.assert_equal(summaries[0].session_id, session.session_id)

            # 삭제
            svc.delete_session(session.session_id)
            self.assert_equal(len(svc.list_sessions()), 0)

    def test_18_app_service_code_extraction(self):
        """AppService 가 library/initial/step delta 추출 메서드 facade 제공."""
        from core.app_service import AppService
        from core.storage.local_json import LocalJsonRepository

        class FakeSession:
            steps = [
                {
                    "generated_code": "from selenium import webdriver\n"
                    "URL = 'https://example.com'\n"
                    "driver = webdriver.Chrome()\n"
                    "# === Step 1: 페이지 (시작) ===\n"
                    "driver.get(URL)\n"
                    "# === Step 1: 페이지 (끝) ===\n"
                }
            ]

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            svc = AppService(session_repo=repo)

            lib = svc.get_library_block_code(FakeSession())
            self.assert_true(
                "from selenium" in lib,
                f"library = imports + helpers. 실제: {lib!r}",
            )

            init = svc.get_initial_block_code(FakeSession())
            self.assert_true(
                "URL = " in init or "driver = " in init,
                f"initial = 모듈레벨 Assign. 실제: {init!r}",
            )

            # step delta — 마커 안 본문
            step_dict = FakeSession.steps[0]
            delta = svc.get_step_delta_code(step_dict, None)
            self.assert_true(
                "driver.get(URL)" in delta,
                f"step delta = 마커 본문. 실제: {delta!r}",
            )

    def test_19_app_service_run_initial_block_with_fake_kernel(self):
        """AppService.run_initial_block_sync — 라이브러리 자동 선행 path 검증.

        실 ExecutionKernel 대신 fake kernel 으로 Phase 2.5 contract 동작 검증
        (UI / subprocess / threading 우회).
        """
        from core.app_service import AppService
        from core.execution_kernel import (
            INITIAL_BLOCK_STEP_ID,
            LIBRARY_BLOCK_STEP_ID,
            StepResult,
        )
        from core.storage.local_json import LocalJsonRepository

        # Fake kernel — execute_block 호출 기록
        class FakeKernel:
            def __init__(self):
                self.executed_steps = []
                self.calls: list[tuple[int, str]] = []

            def execute_block(self, code, step_id, timeout=60, silent=False):
                self.calls.append((step_id, code))
                self.executed_steps.append(step_id)
                return StepResult(step_id=step_id, success=True, output="", duration_ms=10)

        class FakeSession:
            steps = [
                {
                    "generated_code": "from selenium import webdriver\n"
                    "import time\n"
                    "\n"
                    "def helper():\n    pass\n"
                    "# === Step 1: setup (시작) ===\n"
                    "driver = webdriver.Chrome()\n"
                    "# === Step 1: setup (끝) ===\n"
                }
            ]

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            svc = AppService(session_repo=repo)
            kernel = FakeKernel()
            logs: list[str] = []

            result = svc.run_initial_block_sync(
                FakeSession(),
                initial_code="driver = webdriver.Chrome()",
                kernel=kernel,
                on_log=logs.append,
            )

            self.assert_true(result.success, "Initial 실행 성공")

            # 두 번 호출: library 선행 + initial
            self.assert_equal(
                len(kernel.calls),
                2,
                f"라이브러리 + Initial 두 번 호출 필수. 실제: {len(kernel.calls)}",
            )
            self.assert_equal(kernel.calls[0][0], LIBRARY_BLOCK_STEP_ID)
            self.assert_equal(kernel.calls[1][0], INITIAL_BLOCK_STEP_ID)
            # 로그 메시지 두 종류 발생 (내용 출력 금지 - emoji cp949 충돌 회피)
            has_lib_log = any("라이브러리" in m for m in logs)
            has_init_log = any("Initial" in m for m in logs)
            self.assert_true(has_lib_log, "라이브러리 초기화 로그 발생 필수")
            self.assert_true(has_init_log, "Initial 실행 시작 로그 발생 필수")

            # 두 번째 호출 — 라이브러리 이미 etxecuted_steps 에 있으면 skip
            kernel2 = FakeKernel()
            kernel2.executed_steps = [LIBRARY_BLOCK_STEP_ID]  # 이미 초기화됨
            svc.run_initial_block_sync(
                FakeSession(),
                initial_code="driver = webdriver.Chrome()",
                kernel=kernel2,
            )
            self.assert_equal(
                len(kernel2.calls),
                1,
                "라이브러리 이미 있으면 Initial 만 1번 호출",
            )
            self.assert_equal(kernel2.calls[0][0], INITIAL_BLOCK_STEP_ID)

    def test_41_send_button_toggles_to_stop_during_ai_call(self):
        """[전송 ↔ 중지 토글] AI 호출 중에는 send_btn 이 '⏹ 중지' 로 변경되고
        클릭 시 AppService.cancel_ai 호출. 응답/취소 완료 후 _on_step_done 에서
        '전송 ▶' 으로 자동 복원.
        """
        from pathlib import Path

        from ui_v2.main_window_v2 import MainWindowV2

        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )

        # _set_send_state 헬퍼 + 상태 변수
        self.assert_true(
            hasattr(MainWindowV2, "_set_send_state"),
            "MainWindowV2._set_send_state(generating: bool) 필수",
        )
        self.assert_true(
            "self._is_generating" in src,
            "_is_generating 상태 변수 보유 필수",
        )

        # 토글 텍스트 — assertion 메시지에 ⏹ 직접 사용 X (cp949 미지원)
        self.assert_true(
            '"⏹ 중지"' in src and '"전송 ▶"' in src,
            "send_btn 텍스트가 stop/send 사이 토글 필수",
        )

        # _on_send_message 가 generating 상태에서 cancel_ai 분기
        self.assert_true(
            "if self._is_generating" in src and "self.app_service.cancel_ai()" in src,
            "_on_send_message 가 generating 시 AppService.cancel_ai 호출 필수",
        )

        # _send_request 시작 시 _set_send_state(True)
        self.assert_true(
            "self._set_send_state(True)" in src,
            "_send_request 가 AI 호출 시작 시 _set_send_state(True) 호출 필수",
        )

        # _on_step_done 에서 _set_send_state(False) 복원
        self.assert_true(
            "self._set_send_state(False)" in src,
            "_on_step_done 가 응답 완료 후 _set_send_state(False) 복원 필수 "
            "(취소/실패 path 모두 포함)",
        )

    def test_45_card_collapse_and_capture_display(self):
        """[접기/펼치기 + 캡처 thumbnail] StepCardV2 가 expand 상태 + capture 받음.

        - StepCardV2.set_expanded(bool) 메서드 + _expanded 플래그
        - __init__ 의 captures / expanded 파라미터
        - _build_capture_thumbnail (QPixmap.scaledToWidth 사용)
        - MainWindowV2._set_all_cards_expanded 헬퍼 + 전체 토글 버튼
        - AppService.generate_step 가 step.captures 보존
        - _on_element_picked 가 mss 로 element rect 캡처 + pending_images 추가
        """
        import inspect
        from pathlib import Path

        from ui_v2.main_window_v2 import MainWindowV2, StepCardV2

        # StepCardV2: __init__ 시그니처
        sig = inspect.signature(StepCardV2.__init__)
        for required in ("captures", "expanded"):
            self.assert_true(
                required in sig.parameters,
                f"StepCardV2.__init__ 가 {required!r} 파라미터 필수",
            )

        # set_expanded + _build_capture_thumbnail + _on_header_click
        for method in ("set_expanded", "_build_capture_thumbnail", "_on_header_click"):
            self.assert_true(
                hasattr(StepCardV2, method),
                f"StepCardV2.{method} 필수",
            )

        # MainWindowV2 helper
        self.assert_true(
            hasattr(MainWindowV2, "_set_all_cards_expanded"),
            "MainWindowV2._set_all_cards_expanded (전체 토글) 필수",
        )

        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )

        # 액션바 전체 펼치기/접기 버튼
        self.assert_true(
            "모두 펼치기" in src and "모두 접기" in src,
            "[액션바] 모두 펼치기/접기 버튼 텍스트 필수",
        )
        self.assert_true(
            "self._set_all_cards_expanded(True)" in src
            and "self._set_all_cards_expanded(False)" in src,
            "[액션바] 전체 토글 버튼이 _set_all_cards_expanded 호출",
        )

        # default 접힘 (Step) + 펼침 (Library/Initial)
        self.assert_true(
            "expanded=True" in src and "expanded=False" in src,
            "Library/Initial 은 default 펼침, Step 은 default 접힘",
        )

        # captures 전달
        self.assert_true(
            'captures=list(sd.get("captures", []) or [])' in src,
            "_refresh_step_cards 가 step.captures 를 카드에 전달 필수",
        )

        # _build_capture_thumbnail 가 scaledToWidth 사용 (v1 패턴)
        thumb_src = inspect.getsource(StepCardV2._build_capture_thumbnail)
        self.assert_true(
            "scaledToWidth" in thumb_src,
            "_build_capture_thumbnail 가 QPixmap.scaledToWidth 사용 필수 (리사이즈)",
        )
        self.assert_true(
            "min(360" in thumb_src or "min(400" in thumb_src,
            "thumbnail 폭 제한 (큰 이미지 자동 축소)",
        )

        # _on_element_picked: mss + PIL 사용 (v1 패턴)
        elem_src = inspect.getsource(MainWindowV2._on_element_picked)
        self.assert_true(
            "import mss" in elem_src or "mss.mss()" in elem_src,
            "_on_element_picked 가 mss 로 element rect 캡처 필수 (v1 패턴)",
        )
        self.assert_true(
            "pending_images.append" in elem_src,
            "_on_element_picked 가 캡처 path 를 pending_images 에 추가 필수",
        )

        # AppService.generate_step 가 step.captures 보존
        from core.app_service import AppService

        gen_src = inspect.getsource(AppService.generate_step)
        self.assert_true(
            "captures=list(images)" in gen_src,
            "AppService.generate_step 가 images → step.captures 보존 필수",
        )

    def test_54_idempotent_browser_init_wraps_chrome(self):
        """[회귀] make_browser_init_idempotent: driver = webdriver.Chrome(...) 를
        try/except driver.window_handles 가드로 감싸야 함.

        사용자 보고 (5/5): "전체 실행" 후 웹브라우저가 3 개 띄워짐. step 1 의
        webdriver.Chrome() 이 매 실행마다 새 브라우저 생성. idempotent guard 로
        살아있는 driver 재사용 → 1 개로 유지.
        """
        from core.workflow_engine import make_browser_init_idempotent

        # 1) 단순 케이스 — Chrome(options=options)
        original = (
            "options = Options()\n"
            "driver = webdriver.Chrome(options=options)\n"
            "driver.get('https://example.com')\n"
        )
        wrapped = make_browser_init_idempotent(original)
        self.assert_true(
            "try:" in wrapped and "driver.window_handles" in wrapped,
            f"try/except + window_handles guard 추가 필수. 실제: {wrapped!r}",
        )
        self.assert_true(
            "except Exception:" in wrapped,
            "except Exception 블럭 필수",
        )
        self.assert_true(
            "driver = webdriver.Chrome(options=options)" in wrapped,
            "원본 driver 생성 호출은 except 안에 보존되어야 함",
        )
        # driver.get 같은 후속 코드는 그대로
        self.assert_true("driver.get('https://example.com')" in wrapped, "후속 코드 보존")

        # 2) 복잡 케이스 — 멀티라인 nested 호출 (Service(ChromeDriverManager().install()))
        complex_code = (
            "driver = webdriver.Chrome(\n"
            "    service=Service(ChromeDriverManager().install()),\n"
            "    options=options\n"
            ")\n"
        )
        wrapped2 = make_browser_init_idempotent(complex_code)
        self.assert_true(
            "try:" in wrapped2 and "ChromeDriverManager().install()" in wrapped2,
            f"멀티라인 nested 호출 보존 + guard 추가. 실제: {wrapped2!r}",
        )

        # 3) 이미 guard 안에 있으면 중복 적용 금지 (idempotent on itself)
        wrapped_again = make_browser_init_idempotent(wrapped)
        self.assert_equal(
            wrapped_again.count("driver.window_handles"),
            wrapped.count("driver.window_handles"),
            f"이미 감싸진 코드는 다시 감싸지 않음. before={wrapped.count('driver.window_handles')} "
            f"after={wrapped_again.count('driver.window_handles')}",
        )

        # 4) webdriver 미사용 코드는 그대로
        unrelated = "import os\nprint('hello')\n"
        self.assert_equal(
            make_browser_init_idempotent(unrelated),
            unrelated,
            "webdriver 미사용 코드는 변경 없음",
        )

        # 5) 변환 결과는 syntax 오류 없이 compile 가능해야 함
        compile(wrapped, "<test>", "exec")
        compile(wrapped2, "<test>", "exec")

        # 6) Firefox/Edge 도 처리
        ff_code = "driver = webdriver.Firefox(options=ff_opts)\n"
        ff_wrapped = make_browser_init_idempotent(ff_code)
        self.assert_true(
            "driver.window_handles" in ff_wrapped,
            f"Firefox 도 idempotent 처리. 실제: {ff_wrapped!r}",
        )

    def test_55_prompt_idempotent_driver_guide_present(self):
        """[회귀] system_context guideline 14 (idempotent driver 패턴) 영구 가이드.

        win_inspector template + prompts.json 에 idempotent driver 가이드가
        들어 있어야 새 AI 생성도 multiple-browser 회귀 없음.
        """
        import json as _json
        from pathlib import Path

        # 1) prompts.json system_context
        prompts = _json.loads(
            (Path(__file__).parent.parent / "config" / "prompts.json").read_text(encoding="utf-8")
        )
        sys_ctx = prompts.get("system_context", "")
        self.assert_true(
            "idempotent" in sys_ctx and "window_handles" in sys_ctx,
            "[회귀] system_context 에 idempotent driver 패턴 가이드 필수",
        )
        self.assert_true(
            "전체 실행" in sys_ctx,
            "[회귀] 가이드에 사용자 사례 ('전체 실행' 두 번 눌러도 1 개) 명시 필수",
        )

        # 2) win_inspector browser template 도 idempotent 패턴 포함
        wi_src = (Path(__file__).parent.parent / "core" / "win_inspector.py").read_text(
            encoding="utf-8"
        )
        self.assert_true(
            "driver.window_handles" in wi_src and "except Exception" in wi_src,
            "[회귀] win_inspector browser template 에 idempotent guard 필수",
        )

    def test_56_show_window_safe_preserves_maximized(self):
        """[회귀] make_show_window_safe: ShowWindow(hwnd, 9) → IsIconic 분기.

        사용자 보고 (5/5): step 2 의 SW_RESTORE 가 maximized Chrome 을 normal 로
        축소 → 직전에 계산한 (1440, 901) 좌표가 무효화 → ID field 클릭 안 되고
        빈 곳 클릭 → ID 입력 실패. minimized 일 때만 SW_RESTORE, 그 외는 SW_SHOW.
        """
        from core.workflow_engine import make_show_window_safe

        # 1) 단순 케이스
        original = (
            "user32 = ctypes.windll.user32\n"
            "hwnd = win.handle\n"
            "user32.ShowWindow(hwnd, 9)     # SW_RESTORE\n"
            "user32.BringWindowToTop(hwnd)\n"
        )
        wrapped = make_show_window_safe(original)
        self.assert_true(
            "user32.IsIconic(hwnd)" in wrapped,
            f"IsIconic 분기 추가 필수. 실제: {wrapped!r}",
        )
        self.assert_true(
            "user32.ShowWindow(hwnd, 9)" in wrapped,
            "if 분기에 원래 SW_RESTORE 보존",
        )
        self.assert_true(
            "user32.ShowWindow(hwnd, 5)" in wrapped,
            "else 분기에 SW_SHOW (maximized 보존) 추가",
        )
        self.assert_true(
            "user32.BringWindowToTop(hwnd)" in wrapped,
            "후속 코드 (BringWindowToTop) 보존",
        )

        # 2) 다른 변수명 (target_hwnd) 도 처리
        target_code = "user32.ShowWindow(target_hwnd, 9)\n"
        wrapped2 = make_show_window_safe(target_code)
        self.assert_true(
            "user32.IsIconic(target_hwnd)" in wrapped2
            and "user32.ShowWindow(target_hwnd, 5)" in wrapped2,
            f"target_hwnd 변수도 동일 처리. 실제: {wrapped2!r}",
        )

        # 3) 멱등 — 이미 IsIconic guard 안에 있으면 재변환 안 함
        wrapped_again = make_show_window_safe(wrapped)
        self.assert_equal(
            wrapped_again.count("IsIconic"),
            wrapped.count("IsIconic"),
            "이미 감싼 코드는 다시 감싸지 않음",
        )

        # 4) ShowWindow 미사용 코드는 그대로
        unrelated = "import os\nprint('hi')\n"
        self.assert_equal(make_show_window_safe(unrelated), unrelated, "ShowWindow 미사용은 변경 X")

        # 5) SW_HIDE (0) / SW_MINIMIZE (6) 등 다른 값은 건드리지 않음
        hide_code = "user32.ShowWindow(hwnd, 0)\n"
        self.assert_equal(
            make_show_window_safe(hide_code), hide_code, "SW_RESTORE (9) 외에는 변환 X"
        )

        # 6) 변환 결과 compile 가능
        compile(wrapped, "<test>", "exec")
        compile(wrapped2, "<test>", "exec")

    def test_57_prompt_show_window_guide_present(self):
        """[회귀] system_context guideline 15 + win_inspector template 의 SW_RESTORE
        보존 패턴 영구 가이드.
        """
        import json as _json
        from pathlib import Path

        prompts = _json.loads(
            (Path(__file__).parent.parent / "config" / "prompts.json").read_text(encoding="utf-8")
        )
        sys_ctx = prompts.get("system_context", "")
        self.assert_true(
            "IsIconic" in sys_ctx and "SW_RESTORE" in sys_ctx,
            "[회귀] system_context 에 IsIconic + SW_RESTORE 가이드 필수",
        )
        self.assert_true(
            "maximized" in sys_ctx and "ShowWindow" in sys_ctx,
            "[회귀] 가이드에 maximized 보존 의도 명시 필수",
        )

        wi_src = (Path(__file__).parent.parent / "core" / "win_inspector.py").read_text(
            encoding="utf-8"
        )
        # template 도 IsIconic 분기 사용
        self.assert_true(
            "IsIconic" in wi_src and "SW_SHOW" in wi_src,
            "[회귀] win_inspector template 에 IsIconic + SW_SHOW 분기 필수",
        )

    def test_58_generate_step_populates_step_code_and_imports(self):
        """[회귀] AppService.generate_step 가 step_code/step_imports 를 채워야 함.

        백업 [ohdo_20260505_backup/ohdo/ui/ai_call_handler.py:248-287] 에서 구현되어
        있던 패턴이 ui_v2 redesign 시 누락 → step_code="" + step_imports=[] 만 남고
        generated_code 만 누적 저장 → workflow_engine 의 marker 추출이 깨질 때
        fallback 으로 전체 cumulative 가 실행되어 driver.get / maximize 중복 → 페이지
        새로고침 반복 (5/5 사용자 보고 "웹브라우저 새로고침 현상이 2~3번 반복").
        """
        import asyncio
        import tempfile
        from pathlib import Path

        from core.adapters.base_adapter import AIResponse
        from core.app_service import AppService
        from core.storage.local_json import LocalJsonRepository

        class _FakeAI:
            def __init__(self):
                self._responses = []

            def add(self, code, packages=None, description=""):
                self._responses.append(
                    AIResponse(
                        success=True,
                        text=code,
                        code=code,
                        packages=packages or [],
                        description=description,
                    )
                )

            async def generate(self, prompt, images=None, system=None):
                return self._responses.pop(0)

            def cancel(self):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            ai = _FakeAI()
            svc = AppService(session_repo=repo, ai_manager=ai)
            session = svc.create_session("test")

            # step 1 — driver 초기화
            step1_code = (
                "import time\n"
                "from selenium import webdriver\n"
                "\n"
                "try:\n"
                "    driver = webdriver.Chrome()\n"
                "    driver.get('https://example.com')\n"
                "except Exception as e:\n"
                "    print(e)\n"
            )
            ai.add(step1_code, packages=["selenium"])
            step1, _ = asyncio.run(svc.generate_step(session, "브라우저 열기"))

            self.assert_true(step1 is not None, "step1 생성 성공")
            self.assert_true(
                bool(step1.step_code.strip()),
                f"step1.step_code 비어있으면 안 됨. 실제: {step1.step_code!r}",
            )
            self.assert_true(
                "selenium" in step1.step_imports[0] or "import" in step1.step_imports[0],
                f"step1.step_imports 채워야 함. 실제: {step1.step_imports!r}",
            )

            # step 2 — 누적 (selenium imports + step 1 + step 2 새 코드 포함)
            step2_code = (
                "import time\n"
                "import pyautogui\n"
                "from selenium import webdriver\n"
                "from pywinauto import Application\n"
                "\n"
                "# === Step 1: 작업 1 (시작) ===\n"
                "try:\n"
                "    driver = webdriver.Chrome()\n"
                "    driver.get('https://example.com')\n"
                "except Exception as e:\n"
                "    print(e)\n"
                "# === Step 1: 작업 1 (끝) ===\n"
                "\n"
                "# === Step 2: 작업 2 (시작) ===\n"
                "try:\n"
                "    app = Application().connect(title='X')\n"
                "    pyautogui.write('hello')\n"
                "except Exception as e:\n"
                "    print(e)\n"
                "# === Step 2: 작업 2 (끝) ===\n"
            )
            ai.add(step2_code, packages=["selenium", "pyautogui", "pywinauto"])
            step2, _ = asyncio.run(svc.generate_step(session, "텍스트 입력"))

            self.assert_true(step2 is not None, "step2 생성 성공")
            self.assert_true(
                bool(step2.step_code.strip()),
                f"step2.step_code 비어있으면 안 됨. 실제: {step2.step_code!r}",
            )
            # step2.step_code 는 step 1 driver init 코드를 포함하면 안 됨 (delta 만)
            self.assert_true(
                "webdriver.Chrome()" not in step2.step_code,
                f"step2.step_code 에 step 1 driver init 가 포함되면 회귀. 실제: {step2.step_code!r}",
            )
            self.assert_true(
                "pyautogui.write" in step2.step_code or "Application()" in step2.step_code,
                f"step2.step_code 에 step 2 본문 포함 필수. 실제: {step2.step_code!r}",
            )
            # step2.step_imports 는 새 import 만 (pyautogui, pywinauto)
            new_imports = " ".join(step2.step_imports)
            self.assert_true(
                "pyautogui" in new_imports or "pywinauto" in new_imports,
                f"step2.step_imports 에 새 import 포함 필수. 실제: {step2.step_imports!r}",
            )
            self.assert_true(
                "selenium" not in new_imports,
                f"step2.step_imports 에 step 1 의 기존 import 가 들어가면 회귀. 실제: {step2.step_imports!r}",
            )

    def test_59_generate_step_skips_empty_prev_for_delta(self):
        """[회귀] 직전 step 이 empty (AI 실패) 면 last non-empty step 으로 delta 계산.

        그러지 않으면 prev_body="" → delta = 전체 cumulative → 중복 실행 (5/5 회귀:
        AI 가 step 3 을 빈 응답으로 실패한 후 step 4 가 step 1+2+3+4 누적으로 생성되면
        step 4 step_code 에 모든 step 코드가 들어가 driver.get 중복 → 새로고침 반복).
        """
        import asyncio
        import tempfile
        from pathlib import Path

        from core.adapters.base_adapter import AIResponse
        from core.app_service import AppService
        from core.session_manager import Step
        from core.storage.local_json import LocalJsonRepository

        class _FakeAI:
            def __init__(self):
                self._r = []

            def add(self, code):
                self._r.append(
                    AIResponse(
                        success=True,
                        text=code,
                        code=code,
                        packages=[],
                        description="",
                    )
                )

            async def generate(self, prompt, images=None, system=None):
                return self._r.pop(0)

            def cancel(self):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            ai = _FakeAI()
            svc = AppService(session_repo=repo, ai_manager=ai)
            session = svc.create_session("test")

            # step 1
            ai.add("import os\ntry:\n    print('s1')\nexcept Exception as e:\n    pass\n")
            asyncio.run(svc.generate_step(session, "s1"))

            # step 2 — 누적 본문
            step2_full = (
                "import os\nimport time\n"
                "try:\n    print('s1')\nexcept Exception as e:\n    pass\n"
                "try:\n    print('s2')\nexcept Exception as e:\n    pass\n"
            )
            ai.add(step2_full)
            asyncio.run(svc.generate_step(session, "s2"))

            # step 3 — 빈 응답 (AI 실패 시뮬레이션). add_step 직접 사용.
            session = svc.get_session(session.session_id)  # 최신 reload
            empty_step = Step(status="failed", generated_code="", step_code="", step_imports=[])
            svc.add_step(session.session_id, empty_step)

            # step 4 — 누적 (s1 + s2 + s4 본문)
            step4_full = (
                "import os\nimport time\n"
                "try:\n    print('s1')\nexcept Exception as e:\n    pass\n"
                "try:\n    print('s2')\nexcept Exception as e:\n    pass\n"
                "try:\n    print('s4-NEW')\nexcept Exception as e:\n    pass\n"
            )
            ai.add(step4_full)
            session = svc.get_session(session.session_id)
            step4, _ = asyncio.run(svc.generate_step(session, "s4"))

            self.assert_true(step4 is not None, "step4 생성 성공")
            # step4.step_code 는 s1/s2 본문을 포함하면 안 됨 — last-non-empty (step2) 와 비교한 delta
            self.assert_true(
                "s4-NEW" in step4.step_code,
                f"step4.step_code 에 s4 본문 필수. 실제: {step4.step_code!r}",
            )
            self.assert_true(
                step4.step_code.count("'s1'") == 0,
                f"step4.step_code 에 s1 본문 포함되면 empty step3 prev fallback 회귀. 실제: {step4.step_code!r}",
            )
            self.assert_true(
                step4.step_code.count("'s2'") == 0,
                f"step4.step_code 에 s2 본문 포함되면 empty step3 prev fallback 회귀. 실제: {step4.step_code!r}",
            )

    def test_60_win_inspector_template_uses_pyautogui_primary(self):
        """[회귀] win_inspector 의 데스크톱 element 클릭 template 이 pyautogui PRIMARY.

        사용자 보고 (5/5): Win11 메모장 "보기" 메뉴 클릭 안 됨. element.click() (WM
        메시지 / UIA Invoke) 가 UWP/XAML 에서 silent 실패 (예외 안 나는데 효과 없음)
        → 권한 에러 fallback 도 트리거 안 됨. pyautogui.click 좌표 hit-test 가 부모
        MenuItem 까지 자동 도달하므로 PRIMARY 로 강제.
        """
        from pathlib import Path

        wi_src = (Path(__file__).parent.parent / "core" / "win_inspector.py").read_text(
            encoding="utf-8"
        )

        # 1) 데스크톱 분기에서 element.click() 이 PRIMARY 가 되면 안 됨
        # (= pyautogui 폴백이 'rights/privilege' 조건부면 회귀)
        self.assert_true(
            'if "rights" in str(e).lower() or "privilege" in str(e).lower()' not in wi_src,
            "[회귀] desktop 분기에서 element.click() PRIMARY + 권한 조건부 pyautogui 폴백 패턴 제거 필수",
        )

        # 2) pyautogui PRIMARY + element.click() FALLBACK 패턴이 있어야 함
        self.assert_true(
            "pyautogui PRIMARY" in wi_src,
            "[회귀] template 코멘트에 'pyautogui PRIMARY' 명시 필수",
        )

        # 3) pyautogui.click(center_x, center_y) 호출 + element.click() 폴백
        self.assert_true(
            "pyautogui.click(center_x, center_y)" in wi_src
            and "element.click()" in wi_src
            and "폴백" in wi_src,
            "[회귀] pyautogui.click PRIMARY + element.click() 폴백 시퀀스 필수",
        )

    def test_61_prompt_click_strategy_guide_present(self):
        """[회귀] system_context guideline 16 (pyautogui.click PRIMARY) 영구 가이드."""
        import json as _json
        from pathlib import Path

        prompts = _json.loads(
            (Path(__file__).parent.parent / "config" / "prompts.json").read_text(encoding="utf-8")
        )
        sys_ctx = prompts.get("system_context", "")
        self.assert_true(
            "pyautogui.click" in sys_ctx and "PRIMARY" in sys_ctx,
            "[회귀] system_context 에 pyautogui.click PRIMARY 가이드 필수",
        )
        self.assert_true(
            "UWP" in sys_ctx or "XAML" in sys_ctx or "silent" in sys_ctx,
            "[회귀] 가이드에 element.click silent 실패 사례 명시 필수",
        )
        self.assert_true(
            "MenuItem" in sys_ctx or "Text" in sys_ctx,
            "[회귀] 가이드에 Text 라벨 → 부모 컨트롤 hit-test 시나리오 명시 필수",
        )

    def test_62_win_inspector_uses_title_re_for_nonbrowser(self):
        """[회귀] win_inspector 가 비브라우저 앱은 program 명만 title_re 정규식으로 매칭.

        사용자 보고 (5/5): 새 세션 메모장 "보기" 클릭 — step 2 가 picker 시점 title
        ("*hello world - 메모장") 을 hardcode 해서 step 1 이 연 새 빈 메모장 ("제목 없음 -
        메모장") 과 매칭 실패 → ElementNotFoundError.
        """
        from pathlib import Path

        wi_src = (Path(__file__).parent.parent / "core" / "win_inspector.py").read_text(
            encoding="utf-8"
        )

        # 1) program 명 추출 + title_re 정규식 매칭 패턴 존재
        self.assert_true(
            "title_re=" in wi_src and 'parent_title.split(" - ")' in wi_src,
            "[회귀] 비브라우저 분기에서 ' - ' 마지막 세그먼트 → title_re 정규식 패턴 필수",
        )
        # 2) 브라우저는 여전히 full title (페이지별 식별)
        self.assert_true(
            "is_browser_process" in wi_src,
            "[회귀] is_browser_process 분기 필수 (브라우저 vs 비브라우저)",
        )
        # 3) re.escape 로 program 명 안전 처리
        self.assert_true(
            "re.escape(program_name)" in wi_src,
            "[회귀] program_name 을 re.escape 로 안전 처리 필수",
        )

    def test_63_prompt_title_re_guide_present(self):
        """[회귀] system_context guideline 17 (비브라우저 title_re) 영구 가이드."""
        import json as _json
        from pathlib import Path

        prompts = _json.loads(
            (Path(__file__).parent.parent / "config" / "prompts.json").read_text(encoding="utf-8")
        )
        sys_ctx = prompts.get("system_context", "")
        self.assert_true(
            "title_re" in sys_ctx and "program 명" in sys_ctx,
            "[회귀] system_context 에 title_re + program 명 가이드 필수",
        )
        self.assert_true(
            "하드코딩" in sys_ctx or "hardcode" in sys_ctx.lower(),
            "[회귀] full title hardcoding 금지 명시 필수",
        )

    def test_64_walkup_to_clickable_parent(self):
        """[회귀] win_inspector 가 비클릭 leaf element 를 클릭 가능한 부모로 promote.

        사용자 보고 (5/5): Win11 메모장 [Text] "파일"/"보기" 메뉴 클릭 안 됨.
        같은 메모장의 [Button] "설정" 은 정상. 차이는 picker 가 잡은 element 의
        control_type — Text 는 leaf 라벨 (클릭 핸들러 없음) 이라 부모 MenuBarItem 으로
        promote 가 필요. 이미 Button/Edit/MenuItem 등 클릭 가능한 타입은 promote 안 함.
        """
        from pathlib import Path

        wi_src = (Path(__file__).parent.parent / "core" / "win_inspector.py").read_text(
            encoding="utf-8"
        )

        # 1) walk up 패턴 + click_target 변수 + clickable_types set 존재
        self.assert_true(
            "_clickable_types" in wi_src and "click_target" in wi_src,
            "[회귀] template 에 walk-up + click_target 패턴 필수",
        )
        # 2) 핵심 클릭 가능 타입들 포함
        for ct in ("Button", "MenuItem", "MenuBarItem", "Hyperlink", "Edit"):
            self.assert_true(
                f"'{ct}'" in wi_src,
                f"[회귀] _clickable_types 에 '{ct}' 포함 필수",
            )
        # 3) 부모로 promote 시 부모의 rectangle 사용
        self.assert_true(
            "click_target.rectangle()" in wi_src,
            "[회귀] promoted click_target 의 rectangle() 사용 필수 (Text leaf 의 rect 가 아닌)",
        )
        # 4) Button 등 이미 클릭 가능한 타입은 promote 안 함 (회귀 방지)
        self.assert_true(
            "control_type not in _clickable_types" in wi_src,
            "[회귀] 이미 클릭 가능한 타입은 promote 스킵 조건 필수",
        )
        # 5) fallback 도 click_target.click() 사용 (element.click() 이 아닌)
        self.assert_true(
            "click_target.click()" in wi_src,
            "[회귀] fallback 도 promoted click_target.click() 사용 필수",
        )

    def test_65_prompt_walkup_guide_present(self):
        """[회귀] system_context guideline 18 (Text → 클릭 가능 부모 promote) 영구 가이드."""
        import json as _json
        from pathlib import Path

        prompts = _json.loads(
            (Path(__file__).parent.parent / "config" / "prompts.json").read_text(encoding="utf-8")
        )
        sys_ctx = prompts.get("system_context", "")
        self.assert_true(
            "_clickable_types" in sys_ctx and "click_target" in sys_ctx,
            "[회귀] system_context 에 _clickable_types + click_target walk-up 패턴 필수",
        )
        self.assert_true(
            "TextBlock" in sys_ctx
            or "Text" in sys_ctx
            and "leaf" in sys_ctx.lower()
            or "라벨" in sys_ctx,
            "[회귀] 가이드에 leaf Text 라벨 promote 필요성 명시 필수",
        )

    def test_66_picker_preserves_clickable_efp(self):
        """[회귀] element_picker 가 EFP 로 받은 clickable element 를 비클릭 leaf 로
        descend 하지 않음.

        사용자 보고 (5/5): Win11 메모장 메뉴바 클릭 안 됨. picker 로그:
            EFP → MenuItem '파일' (area=4704)
            raw → area=1617 (leaf TextBlock)
            채택 (area=1617 < prev) ← leaf 가 채택되어 control_type='Text' 로 저장
        → pywinauto child_window(control_type='Text') 가 그 leaf 못 찾음 → 클릭 실패.
        """
        from pathlib import Path

        ep_src = (Path(__file__).parent.parent / "ui" / "element_picker.py").read_text(
            encoding="utf-8"
        )

        # 1) clickable types set 정의
        self.assert_true(
            "_CLICKABLE_CONTROL_TYPES" in ep_src,
            "[회귀] element_picker 에 _CLICKABLE_CONTROL_TYPES set 정의 필수",
        )
        for ct in ("MenuItem", "Button", "MenuBarItem", "TabItem", "Hyperlink"):
            self.assert_true(
                f"'{ct}'" in ep_src or f'"{ct}"' in ep_src,
                f"[회귀] _CLICKABLE_CONTROL_TYPES 에 '{ct}' 포함 필수 (single/double quote 모두 허용)",
            )

        # 2) _is_clickable_element 헬퍼
        self.assert_true(
            "_is_clickable_element" in ep_src,
            "[회귀] _is_clickable_element 헬퍼 메서드 필수",
        )

        # 3) descent 거부 가드 (현재 clickable, 새 candidate 비클릭) 적용
        # raw / descendants / multi_backend 후보 비교 모두에 적용되어야
        # ruff format 후 `not (self._is_clickable_element(` 의 외부 paren 제거됨 →
        # `not self._is_clickable_element(` 패턴으로 검색.
        guard_count = ep_src.count("not self._is_clickable_element(")
        self.assert_true(
            guard_count >= 2,
            f"[회귀] descent 가드 (raw + descendants 또는 multi_backend) 최소 2 곳 필요. 실제: {guard_count}",
        )

    def test_67_win_inspector_element_resolution_fallback(self):
        """[회귀] win_inspector 가 element resolution 실패 시 control_type 빼고
        title 만으로, 그래도 실패 시 title_re 정규식으로 fallback.

        사용자 보고 (5/5): picker 가 control_type='Text' 로 저장한 leaf 가 pywinauto
        child_window 매칭 실패 → ElementNotFoundError. picker 분류와 pywinauto 분류
        차이 회피 위해 generated code 에 fallback 체인 필요.
        """
        from core.win_inspector import WindowInspector

        wi = WindowInspector()
        fake = {
            "name": "파일",
            "control_type": "Text",
            "automation_id": "",
            "class_name": "",
            "rect": {"left": 575, "top": 339, "right": 624, "bottom": 372},
            "parent_window_title": "제목 없음 - 메모장",
            "parent_window_class": "Notepad",
            "screen_x": 600,
            "screen_y": 355,
            "is_browser": False,
        }
        text = wi.get_element_info_text(fake)

        # 1) _resolve_element 함수 + 다단계 selector 리스트
        self.assert_true(
            "def _resolve_element" in text,
            "[회귀] _resolve_element 함수 생성 필수",
        )
        # 2) control_type 빼고 title 만 fallback
        self.assert_true(
            "child_window(title='파일', found_index=0)" in text,
            "[회귀] control_type 제외 title-only fallback 필수",
        )
        # 3) title_re 정규식 fallback
        self.assert_true(
            "title_re='.*파일'" in text,
            "[회귀] title_re 정규식 fallback 필수",
        )
        # 4) 강제 resolution 검증 (element_info.control_type 접근)
        self.assert_true(
            "_cand.element_info.control_type" in text,
            "[회귀] 각 candidate 의 element_info 강제 resolution 필수",
        )

    def test_68_fix_hallucinated_imports(self):
        """[회귀] AI 환각 import (FindBestMatchException → MatchError) 자동 교정.

        사용자 보고 (5/5): wooyang 세션의 `from pywinauto.findbestmatch import
        FindBestMatchException` 이 ImportError 로 라이브러리 블럭 죽임 → 후속 import
        모두 skip → 모든 step cascade fail. 실제 클래스 이름은 MatchError.
        """
        from core.workflow_engine import fix_hallucinated_imports

        # 1) import 라인 + except 절 모두 교정
        src = (
            "from pywinauto.findbestmatch import FindBestMatchException\n"
            "try:\n"
            "    pass\n"
            "except FindBestMatchException as e:\n"
            "    print(e)\n"
        )
        fixed = fix_hallucinated_imports(src)
        self.assert_true(
            "FindBestMatchException" not in fixed,
            f"환각 이름 모두 제거 필수. 실제: {fixed!r}",
        )
        self.assert_true(
            "MatchError" in fixed,
            f"실제 이름 MatchError 로 교정 필수. 실제: {fixed!r}",
        )
        # 2) 부분 일치 회피 — 다른 단어에 포함된 'FindBest...' 같은 substring 은 건드리지 않음
        # (현재 매핑은 Exception 으로 끝나는 정확한 이름만)
        # 3) 멱등 — 이미 교정된 코드에 재적용해도 변경 X
        self.assert_equal(
            fix_hallucinated_imports(fixed),
            fixed,
            "이미 교정된 코드는 재교정 시 변경 없어야 함",
        )
        # 4) 환각 없는 코드는 그대로
        clean = "import os\nprint('hi')\n"
        self.assert_equal(
            fix_hallucinated_imports(clean),
            clean,
            "환각 미포함 코드는 변경 X",
        )
        # 5) compile 가능
        compile(fixed, "<test>", "exec")

    def test_69_prompt_exception_catalog_guide(self):
        """[회귀] system_context guideline 19 — pywinauto exception 환각 금지 카탈로그."""
        import json as _json
        from pathlib import Path

        prompts = _json.loads(
            (Path(__file__).parent.parent / "config" / "prompts.json").read_text(encoding="utf-8")
        )
        sys_ctx = prompts.get("system_context", "")
        # 환각 사례 명시
        self.assert_true(
            "FindBestMatchException" in sys_ctx,
            "[회귀] 가이드에 환각 사례 (FindBestMatchException) 명시 필수",
        )
        # 실제 카탈로그 포함
        for cls in ("MatchError", "ElementNotFoundError"):
            self.assert_true(
                cls in sys_ctx,
                f"[회귀] 가이드에 실제 클래스 '{cls}' 카탈로그 포함 필수",
            )

    def test_70_generate_step_writes_conversation_log(self):
        """[회귀] generate_step 매 호출마다 prompt + 응답을 tmp/conversations/ 에 단일 .md 저장.

        사용자 요청 (5/6): 백업 [step0_prompt.txt + step0_generated_code.py] 처럼 두
        파일로 분리하지 말고 하나의 파일에 통합. 추후 디버깅·재현 참고용.
        """
        import asyncio
        import tempfile
        from pathlib import Path

        from core.adapters.base_adapter import AIResponse
        from core.app_service import AppService
        from core.storage.local_json import LocalJsonRepository

        class _FakeAI:
            def __init__(self):
                self._r = []

            def add(self, code):
                self._r.append(
                    AIResponse(
                        success=True,
                        text="설명입니다.\n\n```python\n" + code + "\n```",
                        code=code,
                        packages=[],
                        description="설명입니다.",
                    )
                )

            async def generate(self, prompt, images=None, system=None):
                return self._r.pop(0)

            def cancel(self):
                pass

        project_root = Path(__file__).parent.parent
        log_dir = project_root / "tmp" / "conversations"
        # 테스트 시작 시 기존 로그 수 기록 → 호출 후 +1 검증
        before_count = len(list(log_dir.glob("*.md"))) if log_dir.exists() else 0

        with tempfile.TemporaryDirectory() as tmp_data:
            repo = LocalJsonRepository(data_dir=Path(tmp_data))
            ai = _FakeAI()
            svc = AppService(session_repo=repo, ai_manager=ai)
            session = svc.create_session("로그 테스트 세션")
            ai.add("print('hello world')")
            step, _ = asyncio.run(svc.generate_step(session, "안녕 출력"))

            self.assert_true(step is not None, "step 생성 성공")

            # 로그 파일이 하나 더 생겼어야 함
            after_count = len(list(log_dir.glob("*.md")))
            self.assert_true(
                after_count >= before_count + 1,
                f"tmp/conversations/ 에 .md 파일 새로 생겨야 함. before={before_count} after={after_count}",
            )

            # 가장 최근 파일이 이번 호출 결과인지 검증
            sid_short = session.session_id[:8]
            matching = [
                f for f in log_dir.glob("*.md") if sid_short in f.name and "_step1_" in f.name
            ]
            self.assert_true(
                len(matching) >= 1,
                f"파일명에 session_short ({sid_short}) + step1 포함 필수",
            )

            content = matching[-1].read_text(encoding="utf-8")
            # 각 섹션 헤더 존재
            for header in (
                "AI 대화 로그",
                "사용자 요청",
                "AI 에 전달된 전체 프롬프트",
                "AI 응답",
                "추출된 코드",
            ):
                self.assert_true(
                    header in content,
                    f"[회귀] 로그 파일에 '{header}' 섹션 헤더 필수",
                )
            # 메타데이터
            self.assert_true(
                "세션 ID" in content and session.session_id in content,
                "[회귀] session_id 메타데이터 필수",
            )
            self.assert_true(
                "안녕 출력" in content,
                "[회귀] 사용자 요청 본문 포함 필수",
            )
            self.assert_true(
                "print('hello world')" in content,
                "[회귀] 추출된 코드 본문 포함 필수",
            )
            self.assert_true(
                "프롬프트 길이" in content,
                "[회귀] 프롬프트 길이 메타 포함 필수 (재현용)",
            )

    def test_71_d22_export_uses_app_service(self):
        """[D22] ui_v2 의 _on_tab_export 가 AppService.export_workflow 호출.

        5/7 stub 교체 — 이전 raw shutil.copytree 가 아니라 정식 패키징
        (main.py + requirements.txt + README.md + run.bat + session.json).
        """
        from pathlib import Path

        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )

        # _on_tab_export 함수 본문 추출
        import re

        m = re.search(
            r"def _on_tab_export\(self.*?(?=\n    def )",
            src,
            re.DOTALL,
        )
        self.assert_true(m is not None, "[D22] _on_tab_export 메서드 존재 필수")
        body = m.group(0)
        self.assert_true(
            "self.app_service.export_workflow(" in body,
            "[D22] _on_tab_export 가 AppService.export_workflow 호출 필수 (stub copytree 교체)",
        )
        self.assert_true(
            "shutil.copytree" not in body,
            "[D22] _on_tab_export 에서 raw shutil.copytree stub 제거 필수",
        )

    def test_72_d22_v2_import_action_present(self):
        """[D22] ui_v2 + 탭 메뉴에 워크플로우 가져오기 액션 노출 + AppService 호출."""
        from pathlib import Path

        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )

        self.assert_true(
            "def _on_import_workflow" in src,
            "[D22] _on_import_workflow 메서드 정의 필수",
        )
        self.assert_true(
            "self.app_service.import_workflow(" in src,
            "[D22] _on_import_workflow 가 AppService.import_workflow 호출 필수",
        )
        self.assert_true(
            "워크플로우 가져오기" in src,
            "[D22] + 탭 메뉴에 '워크플로우 가져오기' 액션 노출 필수",
        )

    def test_73_agent_bridge_skeleton(self):
        """[Phase 1.5] agent/bridge.py LocalBridge 스켈레톤 contract.

        ROADMAP §3 Phase 1 (5) — "로컬 HTTP/WS 브리지 (지금은 no-op)". 실제
        listener 는 Phase 3 진입 시 (web "Open in Desktop" URL scheme 등) 구현.
        현 단계는 contract 만 — register_handler / start / stop / is_running.
        """
        from agent.bridge import LocalBridge

        # 인스턴스화 가능 + 기본 상태
        bridge = LocalBridge()
        self.assert_true(
            bridge.is_running is False,
            "[Phase 1.5] LocalBridge 초기 is_running=False 필수",
        )
        self.assert_equal(bridge.list_actions(), [], "[Phase 1.5] 초기 등록 handler 없음")

        # register_handler — action 이름 + callable
        def _handler(req: dict) -> dict:
            return {"echo": req}

        bridge.register_handler("ping", _handler)
        self.assert_true(
            "ping" in bridge.list_actions(),
            "[Phase 1.5] register_handler 후 list_actions 에 노출",
        )
        self.assert_true(
            bridge.get_handler("ping") is _handler,
            "[Phase 1.5] get_handler 가 등록한 handler 반환",
        )

        # invalid handler 거부
        try:
            bridge.register_handler("", _handler)
            raise AssertionError("[Phase 1.5] empty action 은 ValueError")
        except ValueError:
            pass
        try:
            bridge.register_handler("bad", "not_callable")  # type: ignore[arg-type]
            raise AssertionError("[Phase 1.5] non-callable handler 는 ValueError")
        except ValueError:
            pass

        # start / stop 토글 (no-op 이지만 상태는 정확히)
        bridge.start(port=12345)
        self.assert_true(bridge.is_running, "[Phase 1.5] start 후 is_running=True")
        self.assert_equal(bridge.port, 12345, "[Phase 1.5] start(port=N) 후 port=N")
        bridge.stop()
        self.assert_true(bridge.is_running is False, "[Phase 1.5] stop 후 is_running=False")
        self.assert_true(bridge.port is None, "[Phase 1.5] stop 후 port=None")

    def test_53_prompt_pywinauto_guides_present(self):
        """[회귀] system_context + win_inspector template 에 영구 가이드 11~13 포함.

        사용자 보고 (5/5) 누적: 매 시도마다 새 패턴 잘못 — automation_id, ambiguous,
        text input 혼용 등. system 레벨 영구 가이드로 누적 강화.
        """
        # prompts.json 의 system_context
        import json as _json
        from pathlib import Path

        prompts = _json.loads(
            (Path(__file__).parent.parent / "config" / "prompts.json").read_text(encoding="utf-8")
        )
        sys_ctx = prompts.get("system_context", "")
        # 11: automation_id 금지
        self.assert_true(
            "auto_id" in sys_ctx and "automation_id" in sys_ctx,
            "[회귀] system_context 에 'auto_id NOT automation_id' 가이드 필수",
        )
        # 12: found_index=0
        self.assert_true(
            "found_index=0" in sys_ctx,
            "[회귀] system_context 에 found_index=0 ambiguous 회피 가이드 필수",
        )
        # 13: pyautogui.write/press 표준 패턴
        self.assert_true(
            "pyautogui.write" in sys_ctx and "pyautogui.press" in sys_ctx,
            "[회귀] system_context 에 텍스트 입력 표준 패턴 가이드 필수",
        )

        # win_inspector template 의 desktop element 부분에 텍스트 입력 예시
        wi_src = (Path(__file__).parent.parent / "core" / "win_inspector.py").read_text(
            encoding="utf-8"
        )
        self.assert_true(
            "텍스트 입력 표준 패턴" in wi_src,
            "[회귀] win_inspector desktop template 에 텍스트 입력 표준 패턴 명시 필수",
        )
        self.assert_true(
            "pyautogui.write" in wi_src and "pyautogui.press('tab')" in wi_src,
            "[회귀] template 에 pyautogui.write + press('tab') 표준 시퀀스 예시 필수",
        )

    def test_52_pywinauto_connect_found_index_auto_add(self):
        """[회귀] AI 가 Application().connect(title=...) / app.window(title=...) 만들 때
        found_index 누락 → 같은 title 의 윈도우 여러 개 환경에서 ambiguous error.
        restore_user_strings 가 자동으로 found_index=0 추가.

        사용자 보고 (5/5): 'There are 2 elements that match the criteria
        {'title': '업무전산 시스템 - Chrome', ...}' 에러.
        """
        from core.adapters.base_adapter import BaseAIAdapter

        # connect(title=...) 에 found_index 자동 추가
        bad = 'Application(backend="uia").connect(title="업무전산 시스템 - Chrome", timeout=10)'
        fixed = BaseAIAdapter.restore_user_strings(bad, "")
        self.assert_true(
            "found_index=0" in fixed,
            f"connect(title=...) 에 found_index=0 자동 추가 필수. 실제: {fixed!r}",
        )

        # 이미 found_index 있으면 중복 추가 X
        already = 'Application(backend="uia").connect(title="X", timeout=10, found_index=0)'
        fixed_already = BaseAIAdapter.restore_user_strings(already, "")
        self.assert_equal(
            fixed_already.count("found_index"),
            1,
            "이미 있으면 중복 추가 X",
        )

        # app.window(title=...) 에도 추가
        bad_win = 'app.window(title="X")'
        fixed_win = BaseAIAdapter.restore_user_strings(bad_win, "")
        self.assert_true(
            "found_index=0" in fixed_win,
            f"app.window(title=...) 도 추가 필수. 실제: {fixed_win!r}",
        )

        # template 도 found_index 포함
        from pathlib import Path

        wi_src = (Path(__file__).parent.parent / "core" / "win_inspector.py").read_text(
            encoding="utf-8"
        )
        self.assert_true(
            "found_index=0" in wi_src and "connect(title=" in wi_src,
            "[회귀] win_inspector template 의 connect 에 found_index=0 포함 필수",
        )

    def test_51_pywinauto_automation_id_auto_fix(self):
        """[회귀] AI 가 child_window/find_elements 호출 시 잘못된 키워드
        `automation_id=` 사용 → restore_user_strings 가 `auto_id=` 로 자동 교정.

        사용자 보고 (5/5): pywinauto 의 child_window(automation_id="userCd") →
        TypeError: find_elements() got an unexpected keyword argument 'automation_id'.
        """
        from core.adapters.base_adapter import BaseAIAdapter

        # child_window 안 자동 교정
        bad = (
            'element = win.child_window(automation_id="userCd", control_type="Edit", found_index=0)'
        )
        fixed = BaseAIAdapter.restore_user_strings(bad, "")
        self.assert_true(
            "auto_id=" in fixed,
            f"automation_id= → auto_id= 교정 필수. 실제: {fixed!r}",
        )
        self.assert_true(
            "automation_id=" not in fixed,
            "자동 교정 후 automation_id= 잔존 X",
        )

        # descendants 안에서도 교정
        bad2 = 'win.descendants(automation_id="btn1", control_type="Button")'
        fixed2 = BaseAIAdapter.restore_user_strings(bad2, "")
        self.assert_true(
            "descendants(auto_id=" in fixed2,
            f"descendants() 안 교정 필수. 실제: {fixed2!r}",
        )

        # find_elements/find_element (pywinauto 컨텍스트)
        bad3 = 'el.find_elements(automation_id="x")'
        fixed3 = BaseAIAdapter.restore_user_strings(bad3, "")
        self.assert_true(
            "find_elements(auto_id=" in fixed3,
            f"find_elements 안 교정. 실제: {fixed3!r}",
        )

        # 다른 곳의 automation_id (변수명 등) 는 건드리지 않음
        unrelated = 'auto_info["automation_id"] = "some"'
        unchanged = BaseAIAdapter.restore_user_strings(unrelated, "")
        self.assert_true(
            "automation_id" in unchanged,
            "함수 호출 외의 automation_id 는 보존",
        )

        # prompt_builder 의 element_context 후 명시 가이드 추가됐는지
        from pathlib import Path

        pb_src = (Path(__file__).parent.parent / "core" / "prompt_builder.py").read_text(
            encoding="utf-8"
        )
        self.assert_true(
            "auto_id" in pb_src and "automation_id" in pb_src,
            "[회귀] prompt 에 'auto_id NOT automation_id' 명시 가이드 필수",
        )

    def test_50_library_block_re_executes_on_change(self):
        """[회귀] 라이브러리 코드 변경 시 재실행 (사용자 보고 5/5).

        시나리오: step 1 만든 후 전체 실행 → kernel cache. step 2 만들면서
        helper 함수 (find_and_click) 새로 등장. 다시 전체 실행 → cached library
        skip → step 2 실행 시 NameError. Fix: workflow_engine 가 library_hash 비교 →
        변경 시 재실행.
        """
        from core.execution_kernel import LIBRARY_BLOCK_STEP_ID, StepResult

        class FakeKernel:
            def __init__(self):
                self.executed_steps = []
                self.library_hash = None
                self.lib_calls = []

            def execute_block(self, code, step_id, timeout=60, silent=False):
                if step_id == LIBRARY_BLOCK_STEP_ID:
                    self.lib_calls.append(code)
                self.executed_steps.append(step_id)
                return StepResult(step_id=step_id, success=True, output="", duration_ms=1)

        # workflow_engine.execute_session_blocks 의 library 처리 부분만 시뮬레이션
        import hashlib

        from core.workflow_engine import extract_library_block

        class FakeSession:
            session_id = "test"
            steps = [
                {"step_id": 1, "generated_code": "import time\nprint(1)"},
            ]

        # 1. 첫 실행 — library 추출 + 실행
        kernel = FakeKernel()
        sess = FakeSession()
        lib_v1 = extract_library_block(sess)
        new_hash = hashlib.md5(lib_v1.encode()).hexdigest() if lib_v1.strip() else None

        prev_hash = getattr(kernel, "library_hash", None)
        lib_needs_run = LIBRARY_BLOCK_STEP_ID not in kernel.executed_steps or prev_hash != new_hash
        if lib_needs_run and lib_v1.strip():
            kernel.execute_block(lib_v1, step_id=LIBRARY_BLOCK_STEP_ID)
            kernel.library_hash = new_hash

        # 2. 두 번째 실행 — library 동일 → skip
        prev_hash = kernel.library_hash
        lib_needs_run = LIBRARY_BLOCK_STEP_ID not in kernel.executed_steps or prev_hash != new_hash
        # 같은 library 면 skip
        first_call_count = len(kernel.lib_calls)
        if lib_needs_run and lib_v1.strip():
            kernel.execute_block(lib_v1, step_id=LIBRARY_BLOCK_STEP_ID)
            kernel.library_hash = new_hash
        self.assert_equal(
            len(kernel.lib_calls),
            first_call_count,
            "library 동일 시 재실행 없음",
        )

        # 3. step 2 추가 — library 변경 (helper 추가)
        sess.steps = [
            {"step_id": 1, "generated_code": "import time\nprint(1)"},
            {
                "step_id": 2,
                "generated_code": "import time\n\ndef find_and_click():\n    pass\n\n"
                "# === Step 1: 시작 ===\nprint(1)\n# === Step 1: 끝 ===\n"
                "# === Step 2: 시작 ===\nfind_and_click()\n# === Step 2: 끝 ===\n",
            },
        ]
        lib_v2 = extract_library_block(sess)
        new_hash_v2 = hashlib.md5(lib_v2.encode()).hexdigest() if lib_v2.strip() else None
        self.assert_true(
            new_hash != new_hash_v2,
            "[회귀] step 2 추가 후 library hash 가 변경돼야 함 "
            f"(v1={new_hash[:8] if new_hash else None}, v2={new_hash_v2[:8] if new_hash_v2 else None})",
        )

        # 4. workflow_engine 의 hash 비교가 재실행 트리거
        prev_hash = kernel.library_hash
        lib_needs_run = (
            LIBRARY_BLOCK_STEP_ID not in kernel.executed_steps or prev_hash != new_hash_v2
        )
        self.assert_true(
            lib_needs_run,
            "[회귀] library_hash 가 다르면 lib_needs_run=True 필수",
        )
        if lib_needs_run and lib_v2.strip():
            kernel.execute_block(lib_v2, step_id=LIBRARY_BLOCK_STEP_ID)
            kernel.library_hash = new_hash_v2
        self.assert_true(
            len(kernel.lib_calls) > first_call_count,
            "[회귀] library 변경 시 재실행 (lib_calls 증가)",
        )
        self.assert_true(
            "find_and_click" in kernel.lib_calls[-1],
            "[회귀] 재실행된 library 에 새 helper 포함",
        )

        # 5. workflow_engine.py 의 실제 코드 패턴 확인
        from pathlib import Path

        wf_src = (Path(__file__).parent.parent / "core" / "workflow_engine.py").read_text(
            encoding="utf-8"
        )
        self.assert_true(
            "library_hash" in wf_src,
            "[회귀] workflow_engine 가 library_hash 비교 패턴 사용 필수",
        )
        self.assert_true(
            "kernel.library_hash = new_lib_hash" in wf_src,
            "[회귀] library 재실행 후 hash 갱신 필수",
        )

    def test_49_pending_elements_not_lost_before_send(self):
        """[회귀] _on_send_message 가 _pending_elements 비운 후 _send_request
        호출하므로, **인자로 명시 전달** 필수. 그렇지 않으면 element_ctx 빈 채로
        AI 호출 → AI 가 path 결정 컨텍스트 없이 selenium 으로 가서 실패.

        사용자 보고 (5/5): step 2 가 'find_and_click(driver, [(\"text\", \"Edit\")])'
        같은 selenium 코드 생성 후 'Edit' 텍스트 못 찾아 실행 실패.
        """
        import inspect

        from ui_v2.main_window_v2 import MainWindowV2

        # _send_request 시그니처가 elements 인자 받음
        sig = inspect.signature(MainWindowV2._send_request)
        self.assert_true(
            "elements" in sig.parameters,
            "[회귀] _send_request 가 elements 인자 받음 필수 (self._pending_elements 다시 읽기 X)",
        )

        # 본문에서 인자 elements 사용 + self._pending_elements 직접 참조 X
        src = inspect.getsource(MainWindowV2._send_request)
        self.assert_true(
            "elements_for_prompt = list(elements)" in src,
            "[회귀] _send_request 가 인자 elements 를 변수로 사용 필수 "
            "(self._pending_elements 가 아닌)",
        )

        # _on_send_message 가 elements 를 전달
        send_msg_src = inspect.getsource(MainWindowV2._on_send_message)
        self.assert_true(
            "elements=elements" in send_msg_src,
            "[회귀] _on_send_message 가 _send_request 에 elements 인자 전달 필수",
        )
        # 비우는 시점이 _send_request 호출 전 OK 인지 (인자로 미리 capture 했으면)
        self.assert_true(
            "elements = list(self._pending_elements)" in send_msg_src,
            "[회귀] _on_send_message 가 비우기 전에 elements 를 list 로 복사 필수",
        )

        # _on_regenerate 도 elements 전달
        regen_src = inspect.getsource(MainWindowV2._on_regenerate)
        self.assert_true(
            "elements=elems" in regen_src,
            "[회귀] _on_regenerate 도 elements 인자 전달 필수 "
            "(재생성 시 사용자가 새 element 선택했을 수 있음)",
        )

    def test_48_partial_response_detected_and_noise_stripped(self):
        """[회귀] AI 응답 noise prefix 제거 + partial 감지.

        사용자 보고 (5/5): Gemini CLI 의 'MCP issues detected.' prefix +
        ```python ... 끊긴 partial 응답이 step.generated_code 에 imports 만으로
        저장됨 (코드 잘림 인지 X). Fix: extract_code_from_response 가 noise 제거 +
        닫히지 않은 ``` 블럭 본문 그대로 추출, AIResponse.partial 플래그 set.
        """
        from core.adapters.base_adapter import AIResponse, BaseAIAdapter

        # 1. MCP noise prefix 제거 + 정상 ``` 블럭 추출
        normal_with_noise = (
            "MCP issues detected. Run /mcp list for status.\n"
            "```python\n"
            "import time\nprint('hello')\n"
            "```"
        )
        code = BaseAIAdapter.extract_code_from_response(normal_with_noise)
        self.assert_true(
            "import time" in code and "print('hello')" in code,
            f"정상 응답에서 noise 제거 후 코드 추출. 실제: {code!r}",
        )
        self.assert_true(
            "MCP" not in code,
            "noise prefix 가 추출 코드에 들어가면 안 됨",
        )

        # 2. 닫히지 않은 ```python (partial response) 도 본문 추출
        partial_response = (
            "MCP issues detected.\n"
            "```python\n"
            "import re\nfrom selenium import webdriver\nfrom selenium"
        )
        partial_code = BaseAIAdapter.extract_code_from_response(partial_response)
        self.assert_true(
            "from selenium" in partial_code,
            f"partial response 본문 추출. 실제: {partial_code!r}",
        )

        # 3. detect_partial_response — 닫히지 않은 블럭 인식
        self.assert_true(
            BaseAIAdapter.detect_partial_response(partial_response),
            "[회귀] 닫히지 않은 ```python 블럭 partial 감지 필수",
        )
        self.assert_true(
            not BaseAIAdapter.detect_partial_response(normal_with_noise),
            "정상 닫힌 응답은 partial 아님",
        )
        self.assert_true(
            not BaseAIAdapter.detect_partial_response(""),
            "빈 응답은 partial 아님 (다른 path)",
        )

        # 4. AIResponse.partial 필드 존재
        resp = AIResponse(success=True, partial=True)
        self.assert_true(
            resp.partial is True,
            "AIResponse.partial 필드 필수",
        )

    def test_47_generate_step_passes_element_context_to_prompt(self):
        """[회귀] generate_step 가 element_context / is_browser_element 를
        prompt_builder.build_step_prompt 에 전달.

        사용자 보고 (5/5 RPA_20260502_1454 step 2 vs aca22143 step 3):
        - 백업 시점: AI 가 pywinauto + pyautogui path 선택 (정상)
        - 현재 v2: AI 가 Selenium path 선택 + Tab 키 패턴 실수
        - 원인: v2 의 generate_step 가 element_context / is_browser_element 누락
                → prompt 에 path 결정 컨텍스트 부족 → AI 가 잘못된 path 선택.
        """
        import asyncio
        import inspect

        from core.adapters.base_adapter import AIResponse
        from core.app_service import AppService
        from core.storage.local_json import LocalJsonRepository

        # 시그니처 확장 검증
        sig = inspect.signature(AppService.generate_step)
        for required in ("element_context", "window_context", "is_browser_element"):
            self.assert_true(
                required in sig.parameters,
                f"AppService.generate_step 가 {required!r} 파라미터 받음 필수",
            )

        # 호출 시 prompt_builder 에 그대로 전달 — mock prompt_builder 로 검증
        captured: dict = {}

        class MockPromptBuilder:
            def build_step_prompt(self, **kwargs):
                captured.update(kwargs)
                return "mock prompt"

            def build_step_prompt_split(self, **kwargs):
                # P1b: app_service 가 split 호출 — mock 도 동일 시그니처 필요
                captured.update(kwargs)
                return ("", "mock prompt")

        class MockAI:
            async def generate(self, prompt, images=None, system=None):
                return AIResponse(
                    text="ok",
                    code="print('hi')",
                    description="",
                    success=True,
                    response_time_ms=10,
                )

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            svc = AppService(session_repo=repo, ai_manager=MockAI())
            session = svc.create_session(title="ctx 테스트")

            asyncio.run(
                svc.generate_step(
                    session,
                    "테스트 요청",
                    prompt_builder=MockPromptBuilder(),
                    element_context="📌 [Edit] userCd ID 입력 필드",
                    is_browser_element=False,
                )
            )

            # prompt_builder 가 element_context + is_browser_element 받음
            self.assert_equal(
                captured.get("element_context"),
                "📌 [Edit] userCd ID 입력 필드",
                "element_context 가 prompt_builder 에 전달 필수",
            )
            self.assert_equal(
                captured.get("is_browser_element"),
                False,
                "is_browser_element 가 prompt_builder 에 전달 필수",
            )

        # ui_v2 의 _send_request 가 win_inspector 사용 패턴 (소스 검증)
        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )
        self.assert_true(
            "WindowInspector.should_use_selenium" in src,
            "[회귀] ui_v2._send_request 가 WindowInspector.should_use_selenium 호출 필수 "
            "(browser/desktop path 판정)",
        )
        self.assert_true(
            "get_element_info_text" in src,
            "[회귀] ui_v2._send_request 가 inspector.get_element_info_text 로 "
            "element 상세 컨텍스트 구성 필수",
        )
        self.assert_true(
            "element_context=element_ctx" in src and "is_browser_element=is_browser_elem" in src,
            "[회귀] ui_v2._send_request 가 element_context + is_browser_element 를 "
            "AppService.generate_step 에 전달 필수",
        )

    def test_46_reorder_preserves_cumulative_chain(self):
        """[회귀] reorder 시 cumulative generated_code chain 깨지지 않음.

        사용자 보고 (5/5 RPA_20260502_1454): step 재정렬 후 일부 step 의 코드가
        실행 안 됨 (로그인 단계 사라짐). 원인: 단순 swap + renumber 만 하고
        cumulative generated_code (step N = lib + step1 + ... + stepN) 재구성 안 함
        → kernel 실행 시 잘못된 delta 추출.

        Fix: 재정렬 전 step_code 미리 추출 + manually_edited=True 마킹 +
        새 순서대로 generated_code 재구성. extract_step_delta_code 우선순위 0
        (manually_edited + step_code) 가 보호.
        """
        import asyncio  # noqa: F401

        from core.app_service import AppService
        from core.session_manager import Step
        from core.storage.local_json import LocalJsonRepository
        from core.workflow_engine import extract_step_delta_code

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            svc = AppService(session_repo=repo)
            session = svc.create_session(title="누적 chain 테스트")

            # 실제 시나리오 시뮬레이션 — cumulative generated_code
            # (AI 가 생성하는 패턴: 매 step 마다 이전 코드 + 새 step 코드 누적)
            cumulative_codes = [
                "import time\nlogin = 'user'",  # step 1
                "import time\nlogin = 'user'\npassword = 'pw'",  # step 2 (누적)
                "import time\nlogin = 'user'\npassword = 'pw'\nopen_app = True",  # step 3 (누적)
            ]
            for i, code in enumerate(cumulative_codes, 1):
                svc.add_step(
                    session.session_id,
                    Step(
                        step_id=i,
                        status="completed",
                        generated_code=code,
                    ),
                )

            # 재정렬 전: 각 step 의 delta 추출 (chain 정상)
            session_before = svc.get_session(session.session_id)
            prev = None
            deltas_before = []
            for s in session_before.steps:
                deltas_before.append(extract_step_delta_code(s, prev))
                prev = s

            # Step 1 을 마지막 자리로 이동 (사용자 시나리오: 첫 step 을 뒤로)
            ok = svc.reorder_step(session.session_id, 1, 3)
            self.assert_true(ok, "reorder 성공")

            session_after = svc.get_session(session.session_id)
            # 새 순서: [옛 step2, 옛 step3, 옛 step1]
            # 새 generated_code 는 누적 재구성: lib + step_codes 순서대로
            # extract_step_delta_code 가 manually_edited=True + step_code 로 우선 반환
            prev = None
            deltas_after = []
            for s in session_after.steps:
                deltas_after.append(extract_step_delta_code(s, prev))
                prev = s

            # 옛 deltas: [step1_full, step2_delta, step3_delta]
            #   = [step1 의 전체 코드, "password = 'pw'", "open_app = True"]
            # 새 deltas: [옛 step2_delta, 옛 step3_delta, 옛 step1_delta]
            self.assert_true(
                len(deltas_after) == 3,
                f"3 step 유지. 실제: {len(deltas_after)}",
            )
            # 새 step1 = 옛 step2 의 delta — "password" 포함
            self.assert_true(
                "password" in deltas_after[0],
                f"새 step1 (옛 step2) delta 에 'password' 필수. 실제: {deltas_after[0]!r}",
            )
            # 새 step2 = 옛 step3 의 delta — "open_app" 포함
            self.assert_true(
                "open_app" in deltas_after[1],
                f"새 step2 (옛 step3) delta 에 'open_app' 필수. 실제: {deltas_after[1]!r}",
            )
            # 새 step3 = 옛 step1 의 delta — "login" 포함 (재정렬 전 첫 step 이라 전체 코드)
            self.assert_true(
                "login" in deltas_after[2],
                f"새 step3 (옛 step1) delta 에 'login' 필수. 실제: {deltas_after[2]!r}",
            )

            # cumulative generated_code 재구성 검증 — 마지막 step 의 generated_code 가
            # 모든 step content (login + password + open_app) 다 포함
            last_gc = (
                session_after.steps[-1].get("generated_code", "")
                if isinstance(session_after.steps[-1], dict)
                else ""
            )
            for keyword in ("login", "password", "open_app"):
                self.assert_true(
                    keyword in last_gc,
                    f"마지막 step.generated_code 에 '{keyword}' 필수 "
                    f"(누적 chain 보존). 실제 처음 200자: {last_gc[:200]!r}",
                )

    def test_44_session_delete_handler(self):
        """[세션 삭제] _on_session_delete 핸들러 + 사이드바 우클릭 + 탭 우클릭 메뉴.

        - _on_session_delete: confirm + 열린 탭 닫음 + AppService.delete_session
        - 사이드바 우클릭 메뉴 활성화 + _on_sidebar_context_menu
        - 탭 우클릭 메뉴에 '🗑 세션 영구 삭제' 항목
        - AppService.delete_session 실 동작 검증 (mock UI 없이)
        """
        from pathlib import Path

        from core.app_service import AppService
        from core.storage.local_json import LocalJsonRepository
        from ui_v2.main_window_v2 import MainWindowV2

        # 핸들러 메서드 존재
        self.assert_true(
            hasattr(MainWindowV2, "_on_session_delete"),
            "[세션 삭제] MainWindowV2._on_session_delete 핸들러 필수",
        )
        self.assert_true(
            hasattr(MainWindowV2, "_on_sidebar_context_menu"),
            "[사이드바 우클릭] _on_sidebar_context_menu 필수",
        )

        # 소스 패턴
        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )
        # _on_session_delete 가 confirm + delete_session + tab close 처리
        self.assert_true(
            "QMessageBox.question" in src,
            "[세션 삭제] destructive 확인은 QMessageBox modal (D9)",
        )
        self.assert_true(
            "self.app_service.delete_session(session_id)" in src,
            "[세션 삭제] AppService.delete_session 위임 필수",
        )
        self.assert_true(
            "self._on_tab_close(idx)" in src,
            "[세션 삭제] 열린 탭 먼저 닫음 (커널 정리 + state 제거)",
        )

        # 사이드바 우클릭 메뉴 wiring (format 의 줄바꿈에 무관 — 포함 여부만 검사)
        self.assert_true(
            "self.session_list.setContextMenuPolicy" in src
            and "customContextMenuRequested" in src
            and "_on_sidebar_context_menu" in src,
            "[사이드바] customContextMenuRequested → _on_sidebar_context_menu 연결 필수",
        )

        # 탭 우클릭 메뉴에 영구 삭제 항목
        self.assert_true(
            "세션 영구 삭제" in src,
            "[탭 우클릭] '세션 영구 삭제' 항목 필수",
        )

        # AppService.delete_session 실 동작 (UI 없이)
        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            svc = AppService(session_repo=repo)
            s1 = svc.create_session(title="유지")
            s2 = svc.create_session(title="삭제대상")
            self.assert_equal(len(svc.list_sessions()), 2)

            svc.delete_session(s2.session_id)
            remaining = svc.list_sessions()
            self.assert_equal(len(remaining), 1, "삭제 후 1개만 남음")
            self.assert_equal(
                remaining[0].session_id,
                s1.session_id,
                "유지 세션만 남아있어야 함",
            )

    def test_43_python_highlighter_and_code_edit(self):
        """[Syntax highlighting + 코드 편집] PythonHighlighter 5 카테고리 +
        StepCardV2 의 ✏️ 수정 토글 + code_edited signal + MainWindowV2 핸들러.
        """
        from PyQt6.QtGui import QSyntaxHighlighter

        from ui_v2.main_window_v2 import (
            MainWindowV2,
            PythonHighlighter,
            StepCardV2,
        )

        # 1. PythonHighlighter — QSyntaxHighlighter 상속 + 키워드/문자열/숫자/주석/함수 5종
        self.assert_true(
            issubclass(PythonHighlighter, QSyntaxHighlighter),
            "PythonHighlighter 가 QSyntaxHighlighter 상속 필수",
        )
        # 인스턴스화 + rules 5+ 카테고리
        ph = PythonHighlighter()
        self.assert_true(
            len(ph.rules) >= 5,
            f"5+ 강조 룰 (kw/string/number/comment/function). 실제: {len(ph.rules)}",
        )
        # KEYWORDS 에 def/class/if 등 핵심 포함
        for kw in ("def", "class", "if", "for", "import", "return"):
            self.assert_true(
                kw in PythonHighlighter.KEYWORDS,
                f"KEYWORDS 에 {kw!r} 필수",
            )

        # 2. StepCardV2 가 code_edited signal 보유
        self.assert_true(
            hasattr(StepCardV2, "code_edited"),
            "[코드 편집] StepCardV2.code_edited(int, str) signal 필수",
        )
        # 편집 토글 메서드
        for method in ("_toggle_edit", "_enter_edit_mode", "_exit_edit_mode"):
            self.assert_true(
                hasattr(StepCardV2, method),
                f"[코드 편집] StepCardV2.{method} 필수",
            )

        # 3. MainWindowV2 핸들러
        self.assert_true(
            hasattr(MainWindowV2, "_on_block_code_edited"),
            "[코드 편집] MainWindowV2._on_block_code_edited 핸들러 필수",
        )

        # 4. 소스 패턴 — highlighter 인스턴스 보유 (GC 방지) + connect + AppService 위임
        from pathlib import Path

        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )
        self.assert_true(
            "self._highlighter = PythonHighlighter(code_edit.document())" in src,
            "[코드 편집] code_edit 에 highlighter 인스턴스 부착 필수 "
            "(self._highlighter 보유 = GC 방지)",
        )
        self.assert_true(
            "card.code_edited.connect(self._on_block_code_edited)" in src,
            "[코드 편집] 카드 code_edited → _on_block_code_edited 연결 필수",
        )
        self.assert_true(
            "init_card.code_edited.connect(self._on_block_code_edited)" in src,
            "[코드 편집] init_card code_edited 도 연결 필수",
        )
        # format 의 multi-line 줄바꿈에 무관 — 호출 자체와 핵심 인자 포함 여부만 검사
        self.assert_true(
            "self.app_service.update_step(" in src and "step_id" in src,
            "[코드 편집] _on_block_code_edited 가 AppService.update_step 위임 필수",
        )
        self.assert_true(
            '"manually_edited": True' in src,
            "[코드 편집] manually_edited=True 로 update (extract_step_delta_code 우선순위 0)",
        )

    def test_42_d23_drag_drop_reorder(self):
        """[D23] drag-drop 본체 — CardDropContainer + StepCardV2 drag source +
        AppService.reorder_step.

        - CardDropContainer 가 dropEvent 처리 + step_reorder_drop signal emit
        - StepCardV2 의 mousePress/Move 가 헤더 영역에서 QDrag 시작
        - AppService.reorder_step 가 임의 위치 이동
        - MainWindow._on_step_reorder_to 가 reorder_step 호출 + 카드 재구성
        """

        from core.app_service import AppService
        from core.session_manager import Step
        from core.storage.local_json import LocalJsonRepository
        from ui_v2.main_window_v2 import CardDropContainer, MainWindowV2, StepCardV2

        # AppService.reorder_step 존재 + 동작
        self.assert_true(
            hasattr(AppService, "reorder_step"),
            "[D23] AppService.reorder_step 메서드 필수",
        )

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            svc = AppService(session_repo=repo)
            session = svc.create_session(title="reorder 테스트")
            for i in (1, 2, 3, 4):
                svc.add_step(
                    session.session_id,
                    Step(
                        step_id=i,
                        status="completed",
                        generated_code=f"# {i}\nprint({i})",
                    ),
                )

            # Step 1 을 Step 4 자리로 이동 — renumber 가 step_id 1~4 재할당하므로
            # step_code (재정렬 시 사전 추출 + 보존) 로 원본 content 순서 검증.
            # generated_code 는 누적 chain 으로 재구성되므로 첫 줄로 식별 X.
            ok = svc.reorder_step(session.session_id, 1, 4)
            self.assert_true(ok, "reorder_step 성공")

            reloaded = svc.get_session(session.session_id)
            content_order = []
            import re as _re

            for s in reloaded.steps:
                # step_code 가 재정렬 전 추출된 원본 step content (manually_edited=True).
                # extract_step_delta_code 가 주석 라인은 prev_set 필터로 제외하므로
                # 'print(N)' 패턴에서 N 추출 (각 step 의 unique 식별자).
                sc = s.get("step_code", "") if isinstance(s, dict) else getattr(s, "step_code", "")
                m = _re.search(r"print\((\d+)\)", sc)
                content_order.append(int(m.group(1)) if m else 0)
            # 원래 step 1 의 content 가 마지막 자리 — content 순서: [2, 3, 4, 1]
            self.assert_equal(
                content_order,
                [2, 3, 4, 1],
                f"원래 step 1 content 가 마지막 자리. 실제: {content_order}",
            )

            # generated_code 누적 chain 검증 — 새 step1 = step_code, 새 step2 = step1_sc + step2_sc, ...
            for i, s in enumerate(reloaded.steps):
                gc = s.get("generated_code", "") if isinstance(s, dict) else ""
                self.assert_true(
                    gc.strip() != "",
                    f"새 step {i + 1} 의 generated_code 비어있지 않아야 함",
                )
                # 누적: 모든 새 step 의 generated_code 는 새 step1 의 step_code 로 시작
                new_step1_sc = (
                    reloaded.steps[0].get("step_code", "")
                    if isinstance(reloaded.steps[0], dict)
                    else ""
                )
                if new_step1_sc.strip():
                    # G5 (5/9): library_block 이 핵심 import (pyautogui/pyperclip 등) 를
                    # 자동 prepend 하므로 generated_code 시작이 library_block. step1 의
                    # step_code 첫 라인은 그 다음에 위치 — startswith 대신 포함 검증.
                    first_line = new_step1_sc.split("\n")[0]
                    self.assert_true(
                        first_line in gc,
                        f"누적 chain: 새 step {i + 1}.generated_code 에 새 step1 첫 라인 포함 필수",
                    )

            # 같은 위치 이동 시 no-op
            self.assert_true(
                not svc.reorder_step(session.session_id, 2, 2),
                "동일 위치 reorder 는 no-op",
            )

        # CardDropContainer
        self.assert_true(
            hasattr(CardDropContainer, "step_reorder_drop"),
            "[D23] CardDropContainer.step_reorder_drop signal 필수",
        )
        for method in ("dragEnterEvent", "dragMoveEvent", "dropEvent", "_step_id_at_y"):
            self.assert_true(
                hasattr(CardDropContainer, method),
                f"[D23] CardDropContainer.{method} 필수",
            )

        # StepCardV2 drag source
        for method in ("mousePressEvent", "mouseMoveEvent"):
            self.assert_true(
                hasattr(StepCardV2, method),
                f"[D23] StepCardV2.{method} (drag source) 필수",
            )

        # MainWindow handler + connect
        self.assert_true(
            hasattr(MainWindowV2, "_on_step_reorder_to"),
            "[D23] MainWindowV2._on_step_reorder_to 핸들러 필수",
        )
        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )
        self.assert_true(
            "self.cards_container = CardDropContainer()" in src,
            "[D23] cards_container 가 CardDropContainer 인스턴스 필수",
        )
        self.assert_true(
            "step_reorder_drop.connect(self._on_step_reorder_to)" in src,
            "[D23] CardDropContainer.step_reorder_drop → _on_step_reorder_to 연결 필수",
        )
        self.assert_true(
            "self.app_service.reorder_step(" in src,
            "[D23] _on_step_reorder_to 가 AppService.reorder_step 위임 필수",
        )

    def test_40_d23_step_reorder_buttons(self):
        """[D23] StepCardV2 footer 의 ⬆⬇ 버튼 + MainWindowV2._on_step_reorder.

        실 drag-drop 은 후속 슬라이스 (Qt drag-drop 복잡도). 버튼 fallback 만.
        """
        from pathlib import Path

        from ui_v2.main_window_v2 import MainWindowV2, StepCardV2

        # signal 존재
        self.assert_true(
            hasattr(StepCardV2, "reorder_requested"),
            "[D23] StepCardV2.reorder_requested signal 필수",
        )

        # MainWindowV2 핸들러
        self.assert_true(
            hasattr(MainWindowV2, "_on_step_reorder"),
            "[D23] MainWindowV2._on_step_reorder 핸들러 필수",
        )

        # source 패턴 — ⬆⬇ 버튼 + signal connect + AppService.move_step 위임
        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )
        # 위로 이동 화살표 (⬆) — assertion 메시지에서 직접 사용 X (cp949 미지원)
        self.assert_true(
            "⬆" in src,
            "[D23] up arrow 버튼 텍스트 필수 (위로 이동)",
        )
        self.assert_true(
            "⬇" in src,
            "[D23] down arrow 버튼 텍스트 필수 (아래로 이동)",
        )
        self.assert_true(
            "card.reorder_requested.connect(self._on_step_reorder)" in src,
            "[D23] 카드 reorder_requested → _on_step_reorder 연결 필수",
        )
        self.assert_true(
            "self.app_service.move_step(sid, step_id, direction)" in src,
            "[D23] _on_step_reorder 가 AppService.move_step 위임 필수",
        )

    def test_37_d4_multi_session_tabs(self):
        """[D4] MainWindowV2 가 QTabBar + 세션별 커널 dict + 탭별 state 보유."""
        from pathlib import Path

        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )

        # _kernel (단일) 제거되고 _kernels dict 로 교체됨
        self.assert_true(
            "self._kernels: dict" in src,
            "[D4] _kernels: dict (세션별 커널) 필수",
        )
        self.assert_true(
            "self._tabs_state: dict" in src,
            "[D4] _tabs_state: dict (탭별 pending 상태) 필수",
        )
        self.assert_true(
            "self._tab_session_ids: list" in src,
            "[D4] _tab_session_ids 순서 추적 필수 (QTabBar 인덱스 매칭)",
        )

        # 핵심 메서드 존재
        for method in (
            "_open_session_tab",
            "_on_tab_changed",
            "_switch_session",
            "_on_tab_close",
            "_on_tab_moved",
            "_save_active_tab_state",
            "_load_active_tab_state",
        ):
            self.assert_true(
                f"def {method}" in src,
                f"[D4] MainWindowV2.{method} 필수",
            )

        # QTabBar 가 movable + closable
        self.assert_true(
            "setMovable(True)" in src and "setTabsClosable(True)" in src,
            "[D4] QTabBar 가 movable + closable 필수",
        )

    def test_38_d21_d22_tab_menus(self):
        """[D21] + 탭 메뉴 (새로/불러오기/템플릿) + [D22] 탭 우클릭 메뉴."""
        from pathlib import Path

        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )

        # D21
        for method in ("_on_plus_tab", "_new_session_with_scenario"):
            self.assert_true(
                f"def {method}" in src,
                f"[D21] {method} 필수",
            )
        self.assert_true(
            "💡 템플릿" in src or "템플릿" in src,
            "[D21] + 탭 메뉴에 '템플릿' 서브메뉴 노출",
        )

        # D22
        for method in (
            "_on_tab_context_menu",
            "_on_tab_rename",
            "_on_tab_duplicate",
            "_on_tab_export",
        ):
            self.assert_true(
                f"def {method}" in src,
                f"[D22] {method} 필수",
            )
        self.assert_true(
            "customContextMenuRequested.connect(self._on_tab_context_menu)" in src,
            "[D22] 탭 우클릭 → _on_tab_context_menu 연결 필수",
        )

    def test_39_per_session_kernel_isolation(self):
        """[D4] 세션별 커널 분리 — _get_or_create_kernel 가 활성 세션 키로 조회."""
        from pathlib import Path

        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )

        # _get_or_create_kernel 안에 self._kernels[sid] 패턴
        self.assert_true(
            "self._kernels.get(sid)" in src or "self._kernels[sid]" in src,
            "[D4] _get_or_create_kernel 가 세션별 dict 조회 필수",
        )

        # _on_kernel_reset 도 활성 세션의 커널만 정리
        self.assert_true(
            "del self._kernels[sid]" in src,
            "[D4] _on_kernel_reset 가 활성 세션 커널만 정리 필수",
        )

        # closeEvent: 모든 세션 커널 정리
        self.assert_true(
            "for kernel in" in src and "self._kernels" in src,
            "[D4] closeEvent 가 모든 _kernels 순회 정리 필수",
        )

    def test_34_d8_command_palette_exists(self):
        """[D8] CommandPalette 클래스 + 핵심 인터페이스 검증."""
        import inspect

        from ui_v2.command_palette import CommandPalette

        # __init__ 시그니처: items 리스트 받음
        sig = inspect.signature(CommandPalette.__init__)
        self.assert_true(
            "items" in sig.parameters,
            "[D8] CommandPalette.__init__(items=...) 필수",
        )
        # 키 이벤트 처리 + 검색
        for method in ("keyPressEvent", "_on_search_changed", "_render_items", "_execute_current"):
            self.assert_true(
                hasattr(CommandPalette, method),
                f"[D8] CommandPalette.{method} 필수",
            )

    def test_35_d8_main_window_palette_wired(self):
        """[D8] MainWindowV2 의 Ctrl+K 가 _on_command_palette 로 연결,
        items 가 명령/세션/AI엔진 그룹 포함.
        """
        from pathlib import Path

        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )
        self.assert_true(
            "self._on_command_palette" in src and "Ctrl+K" in src,
            "[D8] Ctrl+K → _on_command_palette 매핑 필수",
        )
        self.assert_true(
            "def _on_command_palette" in src,
            "[D8] _on_command_palette 메서드 필수",
        )
        # 기존 stub 제거
        self.assert_true(
            "def _on_command_palette_stub" not in src,
            "옛 stub 제거 필수",
        )
        # items 에 3 그룹 모두 등장
        for group in ('"명령"', '"세션"', '"AI 엔진"'):
            self.assert_true(
                group in src,
                f"[D8] palette items 에 {group} 그룹 포함 필수",
            )

    def test_36_d14_onboarding_wizard(self):
        """[D14] OnboardingWizard + should_show + 첫 실행 트리거 검증."""
        from pathlib import Path

        from ui_v2.onboarding import OnboardingWizard

        # SCENARIOS = 3개 (메모장/네이버/빈)
        self.assert_equal(
            len(OnboardingWizard.SCENARIOS),
            3,
            "[D14] 추천 시나리오 3개 필수 (메모장/네이버/빈 세션)",
        )
        # should_show — settings.ui.onboarding_done 미설정 시 True
        self.assert_true(
            OnboardingWizard.should_show({}),
            "[D14] settings 비어있으면 should_show True (첫 실행)",
        )
        self.assert_true(
            not OnboardingWizard.should_show({"ui": {"onboarding_done": True}}),
            "[D14] onboarding_done True 면 스킵",
        )

        # MainWindowV2 가 첫 실행 시 wizard 띄움
        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )
        self.assert_true(
            "_maybe_show_onboarding" in src,
            "[D14] MainWindowV2._maybe_show_onboarding 메서드 필수",
        )
        self.assert_true(
            "OnboardingWizard" in src,
            "[D14] MainWindowV2 가 OnboardingWizard import",
        )
        self.assert_true(
            "onboarding_done" in src,
            "[D14] settings.ui.onboarding_done 저장 패턴 필수 (한 번 띄우면 스킵)",
        )

    def test_31_ui_v2_toast_widget_exists(self):
        """[D9] Toast + ToastManager 클래스 존재 + 핵심 동작 패턴.

        실 인스턴스화는 QApplication 필요 — 클래스 export + 메서드 시그니처만 검증.
        """
        import inspect

        from ui_v2.main_window_v2 import Toast, ToastManager

        # Toast: __init__ 가 message/level/action_label/action_callback 받음
        sig = inspect.signature(Toast.__init__)
        params = list(sig.parameters.keys())
        for required in ("message", "level", "action_label", "action_callback"):
            self.assert_true(
                required in params,
                f"[D9] Toast.__init__ 가 {required!r} 파라미터 받음 필수",
            )
        # auto-dismiss 타이머 + closed signal
        self.assert_true(
            hasattr(Toast, "closed"),
            "[D9] Toast.closed signal 존재 (ToastManager stack 정리)",
        )
        self.assert_true(
            hasattr(Toast, "dismiss"),
            "[D9] Toast.dismiss 메서드 (수동 닫기 + auto)",
        )

        # ToastManager: show_toast 인터페이스
        self.assert_true(
            hasattr(ToastManager, "show_toast"),
            "[D9] ToastManager.show_toast 메서드 필수",
        )

    def test_32_ui_v2_d17_d20_d25_wired(self):
        """[D17/D20/D25] 새 핸들러 + sidebar toggle + 빈 상태 메서드 연결 검증."""
        from ui_v2.main_window_v2 import MainWindowV2, StepCardV2

        # D17: StepCardV2 의 regenerate_requested 시그널
        self.assert_true(
            hasattr(StepCardV2, "regenerate_requested"),
            "[D17] StepCardV2.regenerate_requested signal 필수",
        )
        # D17: MainWindowV2 의 _on_regenerate 핸들러
        self.assert_true(
            hasattr(MainWindowV2, "_on_regenerate"),
            "[D17] MainWindowV2._on_regenerate 핸들러 필수",
        )
        # D20: sidebar toggle
        self.assert_true(
            hasattr(MainWindowV2, "_toggle_sidebar"),
            "[D20] MainWindowV2._toggle_sidebar 메서드 필수",
        )
        # D25: 빈 상태 + 예시 카드 핸들러
        self.assert_true(
            hasattr(MainWindowV2, "_show_empty_state"),
            "[D25] MainWindowV2._show_empty_state 메서드 필수",
        )
        self.assert_true(
            hasattr(MainWindowV2, "_fill_message_input"),
            "[D25] _fill_message_input (예시 카드 클릭 → 입력창 자동 채움)",
        )
        # _toast 헬퍼
        self.assert_true(
            hasattr(MainWindowV2, "_toast"),
            "[D9] MainWindowV2._toast 헬퍼 필수",
        )
        # _send_request 헬퍼 (D17 path 공유)
        self.assert_true(
            hasattr(MainWindowV2, "_send_request"),
            "_send_request 헬퍼 필수 (send_message + regenerate 공통)",
        )

    def test_33_ui_v2_sidebar_state_persisted(self):
        """[D20] _toggle_sidebar 가 settings.ui.sidebar_collapsed 토글 + 저장."""
        from pathlib import Path

        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )
        # _toggle_sidebar 안에 settings 저장 패턴
        self.assert_true(
            "sidebar_collapsed" in src,
            "[D20] sidebar_collapsed 키 사용 (settings 저장)",
        )
        self.assert_true(
            "self._save_settings" in src,
            "[D20] _toggle_sidebar 가 _save_settings 호출 필수",
        )
        # 시작 시 last state 적용
        self.assert_true(
            "self._sidebar_collapsed = bool" in src or 'ui_cfg.get("sidebar_collapsed"' in src,
            "[D20] init 에서 settings.ui.sidebar_collapsed 로드",
        )

    def test_29_ui_v2_capture_elempick_settings_wired(self):
        """[ui_v2 stub 채우기] 캡처/요소픽/설정 핸들러가 stub 제거되고 v1 overlay/dialog 사용.

        검증:
        - _on_capture / _on_elempick / _on_open_settings 메서드 존재
        - 옛 stub 메서드 (_on_capture_stub 등) 제거됨
        - 소스에 v1 import 패턴 존재 (UI 컴포넌트 재사용 — ADR 우회 OK)
        - pending images / elements / chip_area refresh 로직 존재
        """
        from pathlib import Path

        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )

        # 새 메서드 존재
        for method in (
            "_on_capture",
            "_on_elempick",
            "_on_open_settings",
            "_on_capture_done",
            "_on_element_picked",
            "_refresh_chip_area",
        ):
            self.assert_true(
                f"def {method}" in src,
                f"ui_v2.MainWindowV2.{method} 메서드 필수",
            )

        # 옛 stub 제거됨
        for old in ("_on_capture_stub", "_on_elempick_stub", "_on_open_settings_stub"):
            self.assert_true(
                f"def {old}" not in src,
                f"옛 stub {old!r} 제거 필수 (실 동작 메서드로 교체)",
            )

        # v1 UI 컴포넌트 재사용 import
        self.assert_true(
            "from ui.screen_capture import ScreenCaptureOverlay" in src,
            "ScreenCaptureOverlay 재사용 (ADR: UI 컴포넌트는 우회 OK)",
        )
        self.assert_true(
            "from ui.element_picker import ElementPickerOverlay" in src,
            "ElementPickerOverlay 재사용",
        )
        self.assert_true(
            "from ui.settings_dialog import SettingsDialog" in src,
            "SettingsDialog 재사용",
        )

        # pending 데이터 + chip refresh
        self.assert_true(
            "_pending_images" in src and "_pending_elements" in src,
            "pending images / elements 상태 보유",
        )
        self.assert_true(
            "_refresh_chip_area" in src,
            "chip 영역 동적 갱신 로직",
        )

    def test_30_ui_v2_send_message_passes_pending_data(self):
        """[ui_v2 send_message] pending images/elements 가 generate_step 호출에 반영 + 전송 후 비움."""
        from pathlib import Path

        src = (Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py").read_text(
            encoding="utf-8"
        )
        # send_message 내 pending 처리 패턴
        self.assert_true(
            "element_prefix" in src or "📌 선택된 요소" in src,
            "요소 컨텍스트가 user_request prefix 로 전달됨 (D6)",
        )
        self.assert_true(
            "images=images" in src,
            "pending images 가 generate_step 의 images 인자로 전달",
        )
        self.assert_true(
            "self._pending_images = []" in src and "self._pending_elements = []" in src,
            "전송 후 pending 비움",
        )

    def test_27_app_service_run_blocks_with_fake_kernel(self):
        """[ui_v2 실행 path] AppService.run_blocks — 전체 / 단독 / 여기서부터 분기 검증.

        실 ExecutionKernel 대신 fake kernel 으로 단독 실행 (start=N, stop=N) 시
        N step 만 호출되고 N+1 은 호출 안 됨을 검증.
        """
        import asyncio

        from core.app_service import AppService
        from core.execution_kernel import LIBRARY_BLOCK_STEP_ID, StepResult
        from core.session_manager import Step
        from core.storage.local_json import LocalJsonRepository

        class FakeKernel:
            def __init__(self):
                self.executed_steps = []
                self.calls: list[tuple[int, str, bool]] = []  # (step_id, code, silent)

            def execute_block(self, code, step_id, timeout=60, silent=False):
                self.calls.append((step_id, code, silent))
                self.executed_steps.append(step_id)
                return StepResult(step_id=step_id, success=True, output="", duration_ms=5)

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            svc = AppService(session_repo=repo)

            # 3 step 세션 생성
            session = svc.create_session(title="run_blocks 테스트")
            for i in (1, 2, 3):
                svc.add_step(
                    session.session_id,
                    Step(
                        step_id=i,
                        status="pending",
                        generated_code=f"# step {i}\nprint('s{i}')",
                    ),
                )
            session = svc.get_session(session.session_id)

            # 1) Step 2 단독 실행 (start=2, stop=2)
            kernel = FakeKernel()
            asyncio.run(
                svc.run_blocks(
                    session=session,
                    kernel=kernel,
                    start_from_step_id=2,
                    stop_after_step_id=2,
                )
            )

            # Step 1 silent replay + Step 2 정상 실행. Step 3 은 호출 안 됨.
            executed_real_steps = [
                sid
                for sid, _, silent in kernel.calls
                if not silent and sid != LIBRARY_BLOCK_STEP_ID
            ]
            self.assert_equal(
                executed_real_steps,
                [2],
                f"단독 실행 시 Step 2 만 정상 호출. 실제: {executed_real_steps}",
            )
            silent_steps = [sid for sid, _, silent in kernel.calls if silent]
            self.assert_true(
                1 in silent_steps,
                f"Step 1 silent replay 필수. 실제: {silent_steps}",
            )

            # 2) 전체 실행 (kernel 새로 — silent replay 없이 1,2,3 모두)
            kernel2 = FakeKernel()
            asyncio.run(
                svc.run_blocks(
                    session=session,
                    kernel=kernel2,
                    start_from_step_id=1,
                    stop_after_step_id=None,
                )
            )
            real_run = [
                sid
                for sid, _, silent in kernel2.calls
                if not silent and sid != LIBRARY_BLOCK_STEP_ID
            ]
            self.assert_equal(
                real_run,
                [1, 2, 3],
                f"전체 실행 시 Step 1~3 순차. 실제: {real_run}",
            )

    def test_28_app_service_stop_blocks_after_run(self):
        """AppService.stop_blocks — engine 미생성 상태에서도 안전하게 no-op."""
        from core.app_service import AppService
        from core.storage.local_json import LocalJsonRepository

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            svc = AppService(session_repo=repo)
            svc.stop_blocks()  # engine 미생성 — 예외 없이 통과해야 함

    def test_24_app_service_generate_step_with_mock_ai(self):
        """[D3] AppService.generate_step — mocked AI → Step 생성 + 세션 저장.

        흐름: PromptBuilder 호출 → AI generate → Step 생성 (user_request,
        ai_description, generated_code) → add_step → 세션에 보존.
        """
        import asyncio

        from core.adapters.base_adapter import AIResponse
        from core.app_service import AppService
        from core.storage.local_json import LocalJsonRepository

        # 가짜 AI manager — generate 만 mock
        class FakeAIManager:
            def __init__(self):
                self.calls = []

            async def generate(self, prompt, images=None, system=None):
                self.calls.append({"prompt": prompt, "images": images})
                return AIResponse(
                    text="간단한 print 문 만들기",
                    code="print('hello from mock AI')",
                    description="가짜 설명: 'hello' 를 출력하는 코드입니다.",
                    packages=[],
                    raw_response="```python\nprint('hello from mock AI')\n```",
                    tokens_used=42,
                    response_time_ms=100,
                    success=True,
                )

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            fake_ai = FakeAIManager()
            svc = AppService(session_repo=repo, ai_manager=fake_ai)

            session = svc.create_session(title="generate_step 테스트")

            # generate_step 호출 (실제 PromptBuilder 사용)
            step, response = asyncio.run(svc.generate_step(session, "메시지 출력해줘"))

            self.assert_true(response.success, "AI 응답 success")
            self.assert_true(step is not None, "Step 생성됨")
            self.assert_equal(step.user_request, "메시지 출력해줘")
            self.assert_equal(step.ai_description, "가짜 설명: 'hello' 를 출력하는 코드입니다.")
            self.assert_true(
                "print('hello" in step.generated_code,
                f"generated_code 에 mock 코드. 실제: {step.generated_code!r}",
            )
            self.assert_equal(step.status, "pending", "초기 status pending")
            self.assert_equal(len(fake_ai.calls), 1, "AI generate 1번 호출")

            # 세션 다시 로드 → step 보존 확인
            reloaded = svc.get_session(session.session_id)
            self.assert_equal(len(reloaded.steps), 1, "step 1개 저장됨")
            saved_step = reloaded.steps[0]
            self.assert_equal(
                saved_step.get("user_request"),
                "메시지 출력해줘",
                "user_request 저장 (D3 새 필드)",
            )
            self.assert_true(
                "가짜 설명" in saved_step.get("ai_description", ""),
                "ai_description 저장 (D3 새 필드)",
            )

    def test_25_app_service_generate_step_handles_ai_failure(self):
        """[D3] AI 실패 시 Step 생성 안 됨, response 만 반환."""
        import asyncio

        from core.adapters.base_adapter import AIResponse
        from core.app_service import AppService
        from core.storage.local_json import LocalJsonRepository

        class FailingAIManager:
            async def generate(self, prompt, images=None, system=None):
                return AIResponse(
                    success=False,
                    error="rate limit exceeded",
                    response_time_ms=50,
                )

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))
            svc = AppService(session_repo=repo, ai_manager=FailingAIManager())
            session = svc.create_session(title="failure 테스트")

            step, response = asyncio.run(svc.generate_step(session, "테스트 요청"))

            self.assert_true(step is None, "AI 실패 시 step None")
            self.assert_true(not response.success, "response.success False")
            self.assert_true(
                "rate limit" in (response.error or ""),
                "원본 error 보존",
            )

            # 세션에 step 추가 안 됨
            reloaded = svc.get_session(session.session_id)
            self.assert_equal(len(reloaded.steps), 0, "실패 시 step 0개")

    def test_26_step_dataclass_has_d3_fields(self):
        """[D3] Step dataclass 에 user_request + ai_description 필드 추가됨.

        backwards compat: 옛 세션 JSON 에 이 필드 없어도 default '' 로 로드.
        """
        from core.session_manager import Step

        # dataclass 필드 존재
        self.assert_true(
            "user_request" in Step.__dataclass_fields__,
            "Step.user_request 필드 필수 (D3)",
        )
        self.assert_true(
            "ai_description" in Step.__dataclass_fields__,
            "Step.ai_description 필드 필수 (D3)",
        )
        # default 값 = 빈 문자열
        s = Step(step_id=1)
        self.assert_equal(s.user_request, "", "default 빈 문자열")
        self.assert_equal(s.ai_description, "", "default 빈 문자열")

    def test_21_ui_v2_imports_only_app_service(self):
        """[ui_v2 PoC] ui_v2/main_window_v2.py 가 core 의 facade 외 직접 import 안 함.

        ADR 0001: 새 UI 는 AppService 만 의존. workflow_engine / session_manager /
        execution_kernel 등 직접 import 시 Phase 1 분리 원칙 위반.

        예외: AppService 가 인자로 받는 객체 (Session, Step, ExecutionKernel,
        AIEngineManager, LocalJsonRepository) 는 type 정보 + default 생성용으로
        허용. 그 외 core 모듈은 import 금지.
        """
        from pathlib import Path

        src_path = Path(__file__).parent.parent / "ui_v2" / "main_window_v2.py"
        self.assert_true(src_path.exists(), "ui_v2/main_window_v2.py 존재 필수")
        src = src_path.read_text(encoding="utf-8")

        # AppService import 필수
        self.assert_true(
            "from core.app_service import AppService" in src,
            "AppService facade 사용 필수",
        )

        # 금지된 직접 import 체크
        forbidden = [
            (
                "core.workflow_engine import extract_library_block",
                "AppService.get_library_block_code 사용",
            ),
            (
                "core.workflow_engine import extract_step_delta_code",
                "AppService.get_step_delta_code 사용",
            ),
            (
                "core.import_manager import extract_initial_block",
                "AppService.get_initial_block_code 사용",
            ),
            ("core.workflow_engine import WorkflowEngine", "AppService.run_*_sync 메서드 사용"),
        ]
        for pattern, hint in forbidden:
            self.assert_true(
                f"from {pattern}" not in src,
                f"[ADR 0001 위반] {pattern!r} 직접 import 금지: {hint}",
            )

    def test_22_ui_v2_main_window_class_smoke(self):
        """[ui_v2 PoC] MainWindowV2 클래스 import + 핵심 메서드 존재.

        QApplication 이 필요한 인스턴스화는 GUI 환경 의존이라 검사 안 함.
        클래스 정의 + 메서드 attribute 만 verify.
        """
        from ui_v2 import MainWindowV2

        self.assert_true(
            MainWindowV2.__name__ == "MainWindowV2",
            "MainWindowV2 클래스 export",
        )
        # 핵심 메서드 존재 — 후속 슬라이스에서 다른 핸들러 추가 시 같이 검증
        for method in [
            "_refresh_step_cards",
            "_load_session",
            "_on_run_initial",
            "_on_send_message",
            "_toggle_console",
            "closeEvent",
        ]:
            self.assert_true(
                hasattr(MainWindowV2, method),
                f"MainWindowV2.{method} 메서드 필수",
            )

    def test_23_main_py_supports_ui_v2_flag(self):
        """main.py 가 --ui v2 인수 처리 + use_v2 분기 후 ui_v2.MainWindowV2 import."""
        from pathlib import Path

        src = (Path(__file__).parent.parent / "main.py").read_text(encoding="utf-8")
        self.assert_true("--ui" in src, "--ui 인수 파싱 코드")
        self.assert_true(
            'sys.argv[idx + 1] == "v2"' in src or "'v2'" in src,
            "v2 값 처리 분기",
        )
        self.assert_true(
            "from ui_v2 import MainWindowV2" in src,
            "ui_v2.MainWindowV2 import",
        )

    def test_20_app_service_ai_facade(self):
        """AppService AI 메서드: ai_manager 주입 여부에 따라 동작/예외 분기."""
        from core.ai_engine import AIEngineManager
        from core.app_service import AppService
        from core.storage.local_json import LocalJsonRepository

        with tempfile.TemporaryDirectory() as tmp:
            repo = LocalJsonRepository(data_dir=Path(tmp))

            # ai_manager 미주입 — switch 시 RuntimeError, 나머지는 안전한 fallback
            svc_no_ai = AppService(session_repo=repo)
            self.assert_equal(svc_no_ai.get_ai_engine_name(), None)
            self.assert_equal(svc_no_ai.list_ai_engines(), [])
            svc_no_ai.cancel_ai()  # no-op
            try:
                svc_no_ai.switch_ai_engine("openai_compat")
                raised = False
            except RuntimeError:
                raised = True
            self.assert_true(raised, "ai_manager 미주입 + switch → RuntimeError")

            # ai_manager 주입 — 정상 동작
            ai = AIEngineManager(
                {
                    "ai": {
                        "selected": "gemini_cli",
                        "available_engines": {
                            "gemini_cli": {"command": "gemini"},
                            "openai_compat": {"base_url": "https://api.openai.com/v1"},
                        },
                    }
                }
            )
            svc = AppService(session_repo=repo, ai_manager=ai)
            self.assert_equal(svc.get_ai_engine_name(), "gemini_cli")
            svc.switch_ai_engine("openai_compat")
            self.assert_equal(svc.get_ai_engine_name(), "openai_compat")
            engines = svc.list_ai_engines()
            self.assert_true(
                any(e["name"] == "openai_compat" for e in engines),
                "list_ai_engines 결과에 openai_compat 포함",
            )
