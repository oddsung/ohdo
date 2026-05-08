# SPDX-License-Identifier: AGPL-3.0-or-later
"""
계산기(Calculator) RPA 테스트 케이스

Windows 계산기를 대상으로 테스트합니다:
- UWP 앱 실행/연결
- 버튼 클릭 (pywinauto UIA)
- 결과값 읽기
- pyautogui 좌표 기반 클릭 대안

실행:
    cd ai_rpa_solution
    python -m tests.test_runner --suite calculator
"""

import subprocess

from tests.test_runner import TestCase


class CalculatorTest(TestCase):
    suite = "calculator"

    def __init__(self):
        super().__init__()
        self._calc_process = None

    def _open_calculator(self):
        """계산기 실행"""
        self._calc_process = subprocess.Popen("calc.exe")
        self.wait(2.0, "계산기 시작 대기")

    def _close_calculator(self):
        """계산기 종료"""
        try:
            import pywinauto

            app = pywinauto.Application(backend="uia").connect(
                title_re=r".*계산기.*|.*Calculator.*", timeout=2
            )
            app.kill()
        except Exception:
            if self._calc_process:
                self._calc_process.terminate()

    def _get_calc_window(self):
        """계산기 윈도우 연결"""
        from pywinauto import Desktop

        window = Desktop(backend="uia").window(
            title_re=r".*계산기.*|.*Calculator.*", found_index=0, visible_only=True
        )
        return window

    def setup(self):
        self.require_windows()
        self.require_package("pywinauto")

    def teardown(self):
        try:
            self._close_calculator()
        except Exception:
            pass

    # ── 테스트 메서드 ──

    def test_01_open_calculator(self):
        """계산기 실행 및 감지"""
        self.step("계산기 실행")
        self._open_calculator()

        self.step("UWP 윈도우 감지 (Desktop 방식)")
        window = self._get_calc_window()
        self.assert_true(window.exists(timeout=5), "계산기 윈도우가 존재해야 합니다")
        title = window.window_text()
        self.log(f"윈도우 제목: {title}")
        self.capture_target(r".*계산기.*|.*Calculator.*", "calc_opened")

    def test_02_button_click_addition(self):
        """버튼 클릭으로 1+2=3 계산"""
        self._open_calculator()

        self.step("계산기 윈도우 연결")
        window = self._get_calc_window()
        window.set_focus()
        self.wait(0.5)

        self.step("Clear 버튼 (초기화)")
        try:
            clear_btn = window.child_window(auto_id="clearButton", control_type="Button")
            if clear_btn.exists(timeout=2):
                clear_btn.click_input()
                self.wait(0.3)
        except Exception:
            self.log("[WARN] Clear 버튼 없음, 건너뜀")

        self.step("1 + 2 = 입력")
        try:
            window.child_window(auto_id="num1Button", control_type="Button").click_input()
            self.wait(0.2)
            window.child_window(auto_id="plusButton", control_type="Button").click_input()
            self.wait(0.2)
            window.child_window(auto_id="num2Button", control_type="Button").click_input()
            self.wait(0.2)
            window.child_window(auto_id="equalButton", control_type="Button").click_input()
            self.wait(0.5)
        except Exception as e:
            self.log(f"[WARN] 버튼 클릭 실패: {e}")
            self.log("계산기 UI 구조가 예상과 다릅니다 (언어/버전 차이)")
            raise

        self.step("결과 검증")
        try:
            result_elem = window.child_window(auto_id="CalculatorResults")
            result_text = result_elem.window_text()
            self.log(f"결과 텍스트: {result_text}")
            self.assert_contains(result_text, "3", "1+2 결과가 3이어야 합니다")
        except Exception as e:
            self.log(f"[WARN] 결과 읽기 실패: {e}")
            raise

        self.capture_target(r".*계산기.*|.*Calculator.*", "calc_result")

    def test_03_keyboard_input(self):
        """키보드로 계산식 입력"""
        self._open_calculator()
        import pyautogui

        window = self._get_calc_window()
        window.set_focus()
        self.wait(0.5)

        self.step("키보드로 5*6= 입력")
        pyautogui.press("escape")  # Clear
        self.wait(0.2)
        pyautogui.typewrite("5*6=", interval=0.15)
        self.wait(0.5)

        self.step("결과 확인")
        try:
            result_elem = window.child_window(auto_id="CalculatorResults")
            result_text = result_elem.window_text()
            self.log(f"결과: {result_text}")
            self.assert_contains(result_text, "30", "5*6 결과가 30이어야 합니다")
        except Exception as e:
            self.log(f"결과 읽기 실패: {e}")
            raise

        self.capture_target(r".*계산기.*|.*Calculator.*", "calc_keyboard")

    def test_04_inspector_on_calculator(self):
        """WindowInspector로 계산기 컨트롤 트리 추출"""
        self._open_calculator()

        self.step("WindowInspector로 검사")
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        result = inspector.inspect_window(title="계산기", max_depth=2, max_controls=50)
        if "error" in result:
            result = inspector.inspect_window(title="Calculator", max_depth=2, max_controls=50)

        self.assert_true("error" not in result, f"계산기 검사 성공: {result.get('error', '')}")
        ctrl_count = result.get("control_count", 0)
        self.assert_true(ctrl_count > 5, f"버튼 등 컨트롤이 충분히 있어야 합니다 ({ctrl_count}개)")
        self.log(f"발견된 컨트롤: {ctrl_count}개")

        # 버튼 타입 컨트롤이 있는지 확인
        buttons = [c for c in result.get("controls", []) if c.get("control_type") == "Button"]
        self.assert_true(len(buttons) > 0, f"Button 컨트롤이 있어야 합니다 ({len(buttons)}개)")


if __name__ == "__main__":
    from tests.test_runner import TestRunner

    runner = TestRunner(suite_name="calculator")
    runner.add_test_class(CalculatorTest)
    result = runner.run()
    runner.save_results(result)
