# SPDX-License-Identifier: AGPL-3.0-or-later
"""
RPA 테스트 하네스 (Test Harness)

Claude Code가 실행하고 결과를 읽을 수 있는 표준화된 테스트 러너.
- 테스트 실행 → 스크린샷 캡처 → 결과 JSON 출력
- Claude Code는 results/latest_result.json과 스크린샷을 Read로 분석

사용법:
    cd ai_rpa_solution
    python -m tests.test_runner --suite notepad
    python -m tests.test_runner --suite calculator
    python -m tests.test_runner --suite browser
    python -m tests.test_runner --suite core
    python -m tests.test_runner --suite all
"""

import argparse
import json
import platform
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# Windows 콘솔 cp949 fallback — AI 응답에 em-dash (U+2014) 등 cp949 미지원 글자가
# 섞여 있어도 print 가 UnicodeEncodeError 로 죽지 않도록 stdout/stderr 의 errors
# 정책을 'replace' 로 완화. 미지원 글자는 '?' 로 표시 (테스트 결과 JSON 은 utf-8
# 로 별도 저장되어 원본 보존). ai_integration suite 의 test_01/test_08 회귀 fix.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

# 결과 저장 경로
RESULT_DIR = Path(__file__).parent / "results"
RESULT_DIR.mkdir(exist_ok=True)


# ──────────────────────────────────────────────
# 데이터 모델
# ──────────────────────────────────────────────


@dataclass
class TestStep:
    """테스트 내 개별 단계"""

    name: str = ""
    status: str = "unknown"  # pass / fail / error / skip
    message: str = ""
    screenshot: str = ""
    duration_ms: int = 0


@dataclass
class TestResult:
    """단일 테스트 결과"""

    test_name: str = ""
    suite: str = ""
    status: str = "unknown"  # pass / fail / error / skip
    timestamp: str = ""
    duration_ms: int = 0
    steps: list = field(default_factory=list)
    screenshots: list = field(default_factory=list)
    logs: list = field(default_factory=list)
    error: Optional[str] = None
    error_type: Optional[str] = None


@dataclass
class SuiteResult:
    """테스트 스위트 전체 결과"""

    suite_name: str = ""
    run_time: str = ""
    duration_ms: int = 0
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    tests: list = field(default_factory=list)
    environment: dict = field(default_factory=dict)


# ──────────────────────────────────────────────
# 스크린샷 캡처
# ──────────────────────────────────────────────


def capture_screen(name: str, region: Optional[tuple] = None) -> str:
    """
    스크린샷 캡처 후 파일 경로 반환.

    Args:
        name: 파일명 접두사
        region: (left, top, width, height) 영역 지정. None이면 전체 화면
    """
    try:
        import pyautogui

        timestamp = datetime.now().strftime("%H%M%S")
        path = str(RESULT_DIR / f"{name}_{timestamp}.png")
        if region:
            screenshot = pyautogui.screenshot(region=region)
        else:
            screenshot = pyautogui.screenshot()
        screenshot.save(path)
        return path
    except ImportError:
        return "skip:pyautogui_not_installed"
    except Exception as e:
        return f"error:{e}"


def capture_window(title_pattern: str, name: str) -> str:
    """특정 윈도우만 캡처. 실패 시 전체 화면으로 폴백."""
    try:
        import pywinauto

        app = pywinauto.Application(backend="uia").connect(title_re=title_pattern, timeout=3)
        window = app.top_window()
        rect = window.rectangle()
        region = (rect.left, rect.top, rect.width(), rect.height())
        return capture_screen(name, region=region)
    except Exception:
        return capture_screen(f"{name}_fullscreen")


# ──────────────────────────────────────────────
# 환경 정보 수집
# ──────────────────────────────────────────────


def collect_environment() -> dict:
    """현재 시스템 환경 정보 수집"""
    env = {
        "os": platform.system(),
        "os_version": platform.version(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "timestamp": datetime.now().isoformat(),
    }

    # 화면 해상도
    try:
        import pyautogui

        size = pyautogui.size()
        env["screen_width"] = size.width
        env["screen_height"] = size.height
    except Exception:
        env["screen_width"] = "unknown"
        env["screen_height"] = "unknown"

    # 주요 패키지 버전
    for pkg_name, import_name in [
        ("pyautogui", "pyautogui"),
        ("pywinauto", "pywinauto"),
        ("PyQt6", "PyQt6"),
        ("selenium", "selenium"),
        ("Pillow", "PIL"),
    ]:
        try:
            import importlib

            mod = importlib.import_module(import_name)
            env[f"pkg_{pkg_name}"] = getattr(mod, "__version__", "installed")
        except ImportError:
            env[f"pkg_{pkg_name}"] = "not_installed"

    return env


# ──────────────────────────────────────────────
# 테스트 케이스 기본 클래스
# ──────────────────────────────────────────────


class SkipTest(Exception):
    """테스트 건너뛰기 예외"""

    pass


class TestCase:
    """
    테스트 케이스 기본 클래스.

    상속 예시:
        class MyTest(TestCase):
            suite = "my_suite"

            def setup(self):
                pass  # 테스트 전 준비 (앱 실행 등)

            def teardown(self):
                pass  # 테스트 후 정리 (앱 종료 등)

            def test_something(self):
                self.log("테스트 중...")
                self.assert_true(1 + 1 == 2, "산술 검증")
                self.capture("after_test")
    """

    suite: str = "default"

    def __init__(self):
        self._current_result: Optional[TestResult] = None
        self._steps: list[TestStep] = []

    def setup(self):
        """테스트 전 준비. 오버라이드 가능."""
        pass

    def teardown(self):
        """테스트 후 정리. 오버라이드 가능."""
        pass

    # ── 어서션 헬퍼 ──

    def assert_true(self, condition: bool, message: str = ""):
        """조건이 True인지 검증"""
        if not condition:
            raise AssertionError(f"assert_true 실패: {message}")
        self.log(f"[PASS] {message}" if message else "[PASS]")

    def assert_equal(self, actual, expected, message: str = ""):
        """두 값이 같은지 검증"""
        if actual != expected:
            raise AssertionError(
                f"assert_equal 실패: {message}\n  expected: {expected!r}\n  actual:   {actual!r}"
            )
        self.log(f"[PASS] {message}" if message else f"[PASS] {actual!r} == {expected!r}")

    def assert_contains(self, text: str, substring: str, message: str = ""):
        """문자열 포함 여부 검증"""
        if substring not in text:
            raise AssertionError(
                f"assert_contains 실패: {message}\n  '{substring}' not in '{text[:200]}'"
            )
        self.log(f"[PASS] {message}" if message else f"[PASS] '{substring}' found")

    def assert_not_none(self, value, message: str = ""):
        """값이 None이 아닌지 검증"""
        if value is None:
            raise AssertionError(f"assert_not_none 실패: {message}")
        self.log(f"[PASS] {message}" if message else "[PASS] not None")

    def assert_window_exists(self, title_pattern: str, message: str = ""):
        """윈도우 존재 여부 검증 (Windows 전용)"""
        try:
            import pywinauto

            app = pywinauto.Application(backend="uia").connect(title_re=title_pattern, timeout=5)
            window = app.top_window()
            assert window.exists(), "윈도우가 존재하지 않음"
            self.log(f"[PASS] 윈도우 발견: {window.window_text()}")
            return window
        except Exception as e:
            raise AssertionError(f"assert_window_exists 실패: {message or title_pattern}\n  {e}")

    def assert_element_exists(self, window, **criteria) -> object:
        """윈도우 내 UI 요소 존재 검증 (Windows 전용)"""
        try:
            element = window.child_window(**criteria)
            assert element.exists(timeout=5), f"요소를 찾을 수 없음: {criteria}"
            self.log(f"[PASS] 요소 발견: {criteria}")
            return element
        except Exception as e:
            raise AssertionError(f"assert_element_exists 실패: {criteria}\n  {e}")

    # ── 유틸리티 ──

    def log(self, message: str):
        """테스트 로그 추가"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] {message}"
        if self._current_result:
            self._current_result.logs.append(log_entry)
        print(f"  {log_entry}")

    def capture(self, name: str, region: Optional[tuple] = None) -> str:
        """스크린샷 캡처하고 결과에 추가"""
        path = capture_screen(name, region)
        if self._current_result:
            self._current_result.screenshots.append({"stage": name, "path": path})
        return path

    def capture_target(self, title_pattern: str, name: str) -> str:
        """특정 윈도우만 캡처"""
        path = capture_window(title_pattern, name)
        if self._current_result:
            self._current_result.screenshots.append({"stage": name, "path": path})
        return path

    def wait(self, seconds: float, reason: str = ""):
        """지정 시간 대기"""
        if reason:
            self.log(f"대기 {seconds}초: {reason}")
        time.sleep(seconds)

    def step(self, name: str):
        """테스트 단계 표시 (로그용)"""
        self.log(f"── 단계: {name} ──")
        step = TestStep(name=name, status="running")
        self._steps.append(step)
        return step

    def skip(self, reason: str = ""):
        """현재 테스트 건너뛰기"""
        raise SkipTest(reason)

    def require_windows(self):
        """Windows 환경 필수 체크"""
        if platform.system() != "Windows":
            raise SkipTest("Windows 환경에서만 실행 가능")

    def require_package(self, package_name: str):
        """특정 패키지 설치 여부 체크"""
        try:
            __import__(package_name)
        except ImportError:
            raise SkipTest(f"{package_name} 패키지가 설치되어 있지 않습니다")


# ──────────────────────────────────────────────
# 테스트 러너
# ──────────────────────────────────────────────


class TestRunner:
    """
    테스트 스위트를 실행하고 결과를 수집하는 러너.

    사용법:
        runner = TestRunner()
        runner.add_test_class(MyTestClass)
        suite_result = runner.run()
        runner.save_results(suite_result)
    """

    def __init__(self, suite_name: str = "default"):
        self.suite_name = suite_name
        self._test_classes: list[type[TestCase]] = []

    def add_test_class(self, cls: type[TestCase]):
        """테스트 클래스 등록"""
        self._test_classes.append(cls)

    def _discover_test_methods(self, cls: type[TestCase]) -> list[str]:
        """test_ 로 시작하는 메서드 이름 목록 반환 (정렬순)"""
        methods = []
        for name in sorted(dir(cls)):
            if name.startswith("test_") and callable(getattr(cls, name)):
                methods.append(name)
        return methods

    def run(self, filter_test: Optional[str] = None) -> SuiteResult:
        """
        모든 등록된 테스트를 실행하고 SuiteResult 반환.

        Args:
            filter_test: 지정 시 이 이름을 포함하는 테스트만 실행
        """
        suite_start = time.time()
        suite = SuiteResult(
            suite_name=self.suite_name,
            run_time=datetime.now().isoformat(),
            environment=collect_environment(),
        )

        print(f"\n{'=' * 60}")
        print(f"  테스트 스위트: {self.suite_name}")
        print(f"  시작 시간: {suite.run_time}")
        print(f"{'=' * 60}\n")

        for cls in self._test_classes:
            instance = cls()
            methods = self._discover_test_methods(cls)

            if filter_test:
                methods = [m for m in methods if filter_test in m]

            for method_name in methods:
                result = self._run_single_test(instance, method_name)
                suite.tests.append(asdict(result))

                if result.status == "pass":
                    suite.passed += 1
                elif result.status == "fail":
                    suite.failed += 1
                elif result.status == "error":
                    suite.errors += 1
                elif result.status == "skip":
                    suite.skipped += 1
                suite.total += 1

        suite.duration_ms = int((time.time() - suite_start) * 1000)

        # 요약 출력
        print(f"\n{'=' * 60}")
        print(
            f"  결과: {suite.passed} passed / {suite.failed} failed / "
            f"{suite.errors} errors / {suite.skipped} skipped"
        )
        print(f"  소요 시간: {suite.duration_ms}ms")
        print(f"{'=' * 60}\n")

        return suite

    def _run_single_test(self, instance: TestCase, method_name: str) -> TestResult:
        """단일 테스트 메서드 실행"""
        test_name = f"{instance.__class__.__name__}.{method_name}"
        print(f"\n▶ {test_name}")

        result = TestResult(
            test_name=test_name, suite=instance.suite, timestamp=datetime.now().isoformat()
        )
        instance._current_result = result
        instance._steps = []

        start = time.time()

        # setup
        try:
            instance.setup()
        except SkipTest as e:
            result.status = "skip"
            result.error = str(e) if str(e) else "건너뜀"
            result.duration_ms = int((time.time() - start) * 1000)
            print(f"  [SKIP] {result.error}")
            return result
        except Exception as e:
            result.status = "error"
            result.error = f"setup 실패: {traceback.format_exc()}"
            result.error_type = type(e).__name__
            result.duration_ms = int((time.time() - start) * 1000)
            print(f"  [X] setup 실패: {e}")
            return result

        # 테스트 실행
        try:
            method = getattr(instance, method_name)
            method()
            result.status = "pass"
            print("  [OK] PASS")
        except SkipTest as e:
            result.status = "skip"
            result.error = str(e) if str(e) else "건너뜀"
            print(f"  [SKIP] {result.error}")
        except AssertionError as e:
            result.status = "fail"
            result.error = str(e)
            result.error_type = "AssertionError"
            capture_screen(f"fail_{method_name}")
            print(f"  [X] FAIL: {e}")
        except Exception as e:
            result.status = "error"
            result.error = traceback.format_exc()
            result.error_type = type(e).__name__
            capture_screen(f"error_{method_name}")
            print(f"  [X] ERROR: {e}")

        # teardown (항상 실행)
        try:
            instance.teardown()
        except Exception as e:
            result.logs.append(f"[WARN] teardown 실패: {e}")
            print(f"  [WARN] teardown 실패: {e}")

        result.duration_ms = int((time.time() - start) * 1000)
        return result

    def save_results(self, suite_result: SuiteResult) -> Path:
        """
        결과를 JSON으로 저장.
        - latest_result.json: Claude Code가 읽는 주요 파일
        - {suite}_{timestamp}.json: 히스토리 보관
        """
        data = asdict(suite_result)

        # 최신 결과
        latest_path = RESULT_DIR / "latest_result.json"
        latest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        # 히스토리
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        history_path = RESULT_DIR / f"{suite_result.suite_name}_{timestamp}.json"
        history_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"RESULT_FILE: {latest_path}")
        print(f"HISTORY_FILE: {history_path}")
        return latest_path


# ──────────────────────────────────────────────
# CLI 엔트리포인트
# ──────────────────────────────────────────────


def main():
    # python -m tests.test_runner 실행 시 이 모듈은 __main__으로 로드되지만,
    # 테스트 파일들은 from tests.test_runner import SkipTest로 별도 로드함.
    # 두 모듈의 SkipTest 클래스가 다른 인스턴스가 되어 except에서 못 잡는 문제 방지.
    this_module = sys.modules[__name__]
    if "tests.test_runner" not in sys.modules:
        sys.modules["tests.test_runner"] = this_module

    parser = argparse.ArgumentParser(description="AI RPA Solution 테스트 하네스")
    parser.add_argument(
        "--suite",
        "-s",
        choices=[
            "notepad",
            "calculator",
            "browser",
            "core",
            "scenarios",
            "prompt_quality",
            "ai_integration",
            "macos",
            "all",
        ],
        default="all",
        help="실행할 테스트 스위트",
    )
    parser.add_argument(
        "--test", "-t", type=str, default=None, help="특정 테스트 메서드만 실행 (예: test_open)"
    )
    args = parser.parse_args()

    suites_to_run = []

    if args.suite in ("notepad", "all"):
        try:
            from tests.test_notepad import NotepadTest

            suites_to_run.append(("notepad", [NotepadTest]))
        except ImportError as e:
            print(f"⚠ test_notepad 로드 실패: {e}")

    if args.suite in ("calculator", "all"):
        try:
            from tests.test_calculator import CalculatorTest

            suites_to_run.append(("calculator", [CalculatorTest]))
        except ImportError as e:
            print(f"⚠ test_calculator 로드 실패: {e}")

    if args.suite in ("browser", "all"):
        try:
            from tests.test_browser import BrowserTest

            suites_to_run.append(("browser", [BrowserTest]))
        except ImportError as e:
            print(f"⚠ test_browser 로드 실패: {e}")

    if args.suite in ("core", "all"):
        try:
            from tests.test_core import CoreTest

            suites_to_run.append(("core", [CoreTest]))
        except ImportError as e:
            print(f"⚠ test_core 로드 실패: {e}")

    if args.suite in ("scenarios", "all"):
        try:
            from tests.test_scenarios import ScenariosTest

            suites_to_run.append(("scenarios", [ScenariosTest]))
        except ImportError as e:
            print(f"⚠ test_scenarios 로드 실패: {e}")

    if args.suite in ("prompt_quality", "all"):
        try:
            from tests.test_prompt_quality import PromptQualityTest

            suites_to_run.append(("prompt_quality", [PromptQualityTest]))
        except ImportError as e:
            print(f"⚠ test_prompt_quality 로드 실패: {e}")

    if args.suite in ("ai_integration", "all"):
        try:
            from tests.test_ai_integration import AIIntegrationTest

            suites_to_run.append(("ai_integration", [AIIntegrationTest]))
        except ImportError as e:
            print(f"⚠ test_ai_integration 로드 실패: {e}")

    if args.suite in ("macos", "all"):
        try:
            from tests.test_macos import MacOSTest

            suites_to_run.append(("macos", [MacOSTest]))
        except ImportError as e:
            print(f"⚠ test_macos 로드 실패: {e}")

    if not suites_to_run:
        print("실행할 테스트가 없습니다.")
        sys.exit(1)

    all_passed = True
    for suite_name, test_classes in suites_to_run:
        runner = TestRunner(suite_name=suite_name)
        for cls in test_classes:
            runner.add_test_class(cls)
        result = runner.run(filter_test=args.test)
        runner.save_results(result)
        if result.failed > 0 or result.errors > 0:
            all_passed = False

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
