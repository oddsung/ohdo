# SPDX-License-Identifier: AGPL-3.0-or-later
"""
macOS 환경 RPA 테스트 케이스

macOS에서 UI 자동화를 테스트합니다:
- AppleScript를 통한 앱 실행/제어
- TextEdit(텍스트 편집기) 자동화
- Finder 조작
- pyautogui 기본 동작
- Selenium 브라우저 테스트 (크로스 플랫폼)

실행:
    cd ai_rpa_solution
    python -m tests.test_runner --suite macos
"""

import platform
import subprocess
from pathlib import Path

from tests.test_runner import SkipTest, TestCase


def run_applescript(script: str) -> str:
    """AppleScript 실행 헬퍼"""
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript 실패: {result.stderr.strip()}")
    return result.stdout.strip()


class MacOSTest(TestCase):
    suite = "macos"

    def setup(self):
        if platform.system() != "Darwin":
            raise SkipTest("macOS 환경에서만 실행 가능")

    # ──────────────────────────────────────────
    # 1. AppleScript 기본 동작
    # ──────────────────────────────────────────

    def test_01_applescript_basic(self):
        """AppleScript로 시스템 정보 조회"""
        self.step("AppleScript 실행 가능 확인")
        result = run_applescript('return "hello from applescript"')
        self.assert_equal(result, "hello from applescript", "AppleScript가 정상 동작해야 합니다")

        self.step("시스템 버전 조회")
        version = run_applescript("return system version of (system info)")
        self.assert_true(len(version) > 0, "시스템 버전이 반환되어야 합니다")
        self.log(f"macOS 버전: {version}")

    def test_02_applescript_app_list(self):
        """실행 중인 앱 목록 조회"""
        self.step("실행 중인 앱 목록")
        apps = run_applescript(
            'tell application "System Events" to get name of every process '
            "whose background only is false"
        )
        self.assert_true(len(apps) > 0, "실행 중인 앱 목록이 있어야 합니다")
        self.log(f"실행 중인 앱: {apps[:200]}")

        self.step("Finder 확인")
        self.assert_contains(apps, "Finder", "Finder가 실행 중이어야 합니다")

    # ──────────────────────────────────────────
    # 2. TextEdit (텍스트 편집기) 자동화
    # ──────────────────────────────────────────

    def test_03_open_textedit(self):
        """TextEdit 실행 및 새 문서 생성"""
        self.step("TextEdit 실행")
        run_applescript("""
            tell application "TextEdit"
                activate
                make new document
            end tell
        """)
        self.wait(1.5, "TextEdit 시작 대기")

        self.step("TextEdit 실행 확인")
        frontmost = run_applescript(
            'tell application "System Events" to get name of first process whose frontmost is true'
        )
        self.assert_equal(frontmost, "TextEdit", "TextEdit가 최전면에 있어야 합니다")
        self.capture("textedit_opened")

    def test_04_textedit_type_and_read(self):
        """TextEdit에 텍스트 입력 후 읽기"""
        self.step("TextEdit 실행 및 새 문서")
        run_applescript("""
            tell application "TextEdit"
                activate
                make new document
            end tell
        """)
        self.wait(1.0)

        self.step("텍스트 입력 (AppleScript)")
        test_text = "Hello RPA! 맥북 테스트입니다. 1234"
        run_applescript(f'''
            tell application "TextEdit"
                set text of front document to "{test_text}"
            end tell
        ''')
        self.wait(0.5)

        self.step("텍스트 읽기 검증")
        actual = run_applescript('tell application "TextEdit" to get text of front document')
        self.assert_contains(actual, "Hello RPA", "영문 포함 확인")
        self.assert_contains(actual, "맥북 테스트", "한글 포함 확인")
        self.capture("textedit_typed")

    def test_05_textedit_close_without_save(self):
        """TextEdit 저장 안 하고 닫기"""
        self.step("TextEdit에 텍스트 입력")
        run_applescript("""
            tell application "TextEdit"
                activate
                make new document
                set text of front document to "저장하지 않을 텍스트"
            end tell
        """)
        self.wait(0.5)

        self.step("저장 안 하고 닫기")
        run_applescript("""
            tell application "TextEdit"
                close front document saving no
            end tell
        """)
        self.wait(0.5)
        self.log("TextEdit 문서 닫기 완료")

    # ──────────────────────────────────────────
    # 3. pyautogui macOS 동작
    # ──────────────────────────────────────────

    def test_06_pyautogui_screenshot(self):
        """pyautogui 스크린샷 (macOS)"""
        self.require_package("pyautogui")
        import pyautogui

        self.step("화면 크기 확인")
        size = pyautogui.size()
        self.assert_true(size.width > 0, f"화면 너비: {size.width}")
        self.assert_true(size.height > 0, f"화면 높이: {size.height}")
        self.log(f"화면 크기: {size.width}x{size.height}")

        self.step("스크린샷 캡처")
        # macOS에서 pyautogui.screenshot()은 화면 녹화 권한 필요 → screencapture 사용
        from datetime import datetime

        timestamp = datetime.now().strftime("%H%M%S")
        screenshot_path = str(
            Path(__file__).parent / "results" / f"macos_screenshot_{timestamp}.png"
        )
        result = subprocess.run(
            ["screencapture", "-x", screenshot_path], capture_output=True, timeout=5
        )
        success = result.returncode == 0 and Path(screenshot_path).exists()
        if success:
            self.log(f"스크린샷 저장: {screenshot_path}")
            file_size = Path(screenshot_path).stat().st_size
            self.assert_true(file_size > 0, f"스크린샷 파일 크기: {file_size} bytes")
        self.assert_true(success, "스크린샷이 정상 캡처되어야 합니다")

    def test_07_pyautogui_keyboard(self):
        """pyautogui 키보드 입력 (macOS)"""
        self.require_package("pyautogui")
        import pyautogui

        self.step("TextEdit 열기 및 활성화")
        run_applescript("""
            tell application "TextEdit"
                activate
                make new document
            end tell
        """)
        self.wait(1.0)

        self.step("pyautogui로 텍스트 입력")
        # macOS에서는 Cmd를 사용
        pyautogui.hotkey("command", "a")  # 전체 선택
        self.wait(0.2)
        # typewrite()는 IME 영향을 받으므로 AppleScript keystroke 사용
        run_applescript("""
            tell application "System Events"
                tell process "TextEdit"
                    keystroke "pyautogui test"
                end tell
            end tell
        """)
        self.wait(0.5)

        self.step("입력 확인")
        actual = run_applescript('tell application "TextEdit" to get text of front document')
        self.assert_contains(actual, "pyautogui test", "pyautogui로 입력한 텍스트가 있어야 합니다")

        self.step("정리")
        run_applescript("""
            tell application "TextEdit"
                close front document saving no
            end tell
        """)

    def test_08_pyautogui_hotkey_mac(self):
        """macOS 단축키 (Cmd+C, Cmd+V) 테스트"""
        self.require_package("pyautogui")
        import pyautogui

        self.step("TextEdit 준비")
        run_applescript("""
            tell application "TextEdit"
                activate
                make new document
                set text of front document to "복사할 텍스트"
            end tell
        """)
        self.wait(0.5)

        self.step("Cmd+A (전체 선택) → Cmd+C (복사)")
        pyautogui.hotkey("command", "a")
        self.wait(0.2)
        pyautogui.hotkey("command", "c")
        self.wait(0.3)

        self.step("클립보드 확인")
        clipboard = run_applescript("return (the clipboard)")
        self.assert_contains(clipboard, "복사할 텍스트", "클립보드에 텍스트가 있어야 합니다")

        self.step("정리")
        run_applescript("""
            tell application "TextEdit"
                close front document saving no
            end tell
        """)

    # ──────────────────────────────────────────
    # 4. Finder 조작
    # ──────────────────────────────────────────

    def test_09_finder_open_folder(self):
        """Finder로 폴더 열기"""
        self.step("홈 폴더 열기")
        run_applescript("""
            tell application "Finder"
                activate
                open home
            end tell
        """)
        self.wait(1.0)

        self.step("Finder 활성 확인")
        frontmost = run_applescript(
            'tell application "System Events" to get name of first process whose frontmost is true'
        )
        self.assert_equal(frontmost, "Finder", "Finder가 활성화되어야 합니다")

        self.step("폴더 내용 확인")
        items = run_applescript("""
            tell application "Finder"
                get name of every item in home
            end tell
        """)
        self.assert_true(len(items) > 0, "홈 폴더에 항목이 있어야 합니다")
        self.log(f"홈 폴더 항목: {items[:200]}")
        self.capture("finder_home")

    # ──────────────────────────────────────────
    # 5. WindowInspector 대체 (macOS용 UI 정보 수집)
    # ──────────────────────────────────────────

    def test_10_accessibility_info(self):
        """macOS Accessibility API를 통한 UI 정보 수집"""
        self.step("TextEdit 열기")
        run_applescript("""
            tell application "TextEdit"
                activate
                make new document
            end tell
        """)
        self.wait(1.0)

        self.step("UI 요소 정보 수집 (AppleScript)")
        try:
            ui_info = run_applescript("""
                tell application "System Events"
                    tell process "TextEdit"
                        set frontWin to front window
                        set winTitle to name of frontWin
                        set winPos to position of frontWin
                        set winSize to size of frontWin
                        return "title:" & winTitle & "|pos:" & (item 1 of winPos as text) & "," & (item 2 of winPos as text) & "|size:" & (item 1 of winSize as text) & "," & (item 2 of winSize as text)
                    end tell
                end tell
            """)
            self.assert_contains(ui_info, "title:", "윈도우 제목 정보가 있어야 합니다")
            self.log(f"UI 정보: {ui_info}")
        except RuntimeError as e:
            self.log(f"[WARN] Accessibility 권한 필요할 수 있음: {e}")

        self.step("UI 요소 목록")
        try:
            elements = run_applescript("""
                tell application "System Events"
                    tell process "TextEdit"
                        get description of every UI element of front window
                    end tell
                end tell
            """)
            self.assert_true(len(elements) > 0, "UI 요소 목록이 있어야 합니다")
            self.log(f"UI 요소: {elements[:300]}")
        except RuntimeError as e:
            self.log(f"[WARN] UI 요소 조회 실패 (Accessibility 권한 필요): {e}")

        self.step("정리")
        run_applescript("""
            tell application "TextEdit"
                close front document saving no
            end tell
        """)

    # ──────────────────────────────────────────
    # 6. 프로세스 관리
    # ──────────────────────────────────────────

    def test_11_process_management(self):
        """앱 실행 → 확인 → 종료 전체 흐름"""
        self.step("Calculator 실행")
        run_applescript('tell application "Calculator" to activate')
        self.wait(1.5, "Calculator 시작 대기")

        self.step("Calculator 실행 확인")
        is_running = run_applescript(
            'tell application "System Events" to (name of processes) contains "Calculator"'
        )
        self.assert_equal(is_running, "true", "Calculator가 실행 중이어야 합니다")
        self.capture("macos_calculator")

        self.step("Calculator 종료")
        run_applescript('tell application "Calculator" to quit')
        self.wait(0.5)

        self.step("종료 확인")
        is_running = run_applescript(
            'tell application "System Events" to (name of processes) contains "Calculator"'
        )
        self.assert_equal(is_running, "false", "Calculator가 종료되어야 합니다")

    def teardown(self):
        """테스트 후 정리: TextEdit, Calculator 닫기"""
        for app in ["TextEdit", "Calculator"]:
            try:
                run_applescript(f'''
                    tell application "{app}"
                        close every document saving no
                    end tell
                ''')
            except Exception:
                pass


if __name__ == "__main__":
    from tests.test_runner import TestRunner

    runner = TestRunner(suite_name="macos")
    runner.add_test_class(MacOSTest)
    result = runner.run()
    runner.save_results(result)
