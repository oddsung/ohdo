# SPDX-License-Identifier: AGPL-3.0-or-later
"""
메모장(Notepad) RPA 테스트 케이스

Windows 메모장을 대상으로 핵심 RPA 기능을 테스트합니다:
- 앱 실행/종료
- 텍스트 입력/읽기
- 단축키 (Ctrl+A, Ctrl+C)
- UI 요소 탐색 (pywinauto)
- WindowInspector 통합 테스트

실행:
    cd ai_rpa_solution
    python -m tests.test_runner --suite notepad
"""

import subprocess
import time

from tests.test_runner import TestCase


class NotepadTest(TestCase):
    suite = "notepad"

    def __init__(self):
        super().__init__()
        self._notepad_process = None
        self._app = None

    def _open_notepad(self):
        """메모장 실행 후 pywinauto 앱 객체 반환.
        Windows 11 UWP 메모장은 subprocess PID와 실제 윈도우 PID가 다르므로,
        실행 전후 윈도우 핸들 차이로 새 윈도우를 찾는다.
        """
        import pywinauto
        from pywinauto import Desktop

        # 현재 열린 메모장 핸들 기록
        existing_handles = set()
        for w in Desktop(backend="uia").windows():
            try:
                title = w.window_text()
                if "메모장" in title or "Notepad" in title:
                    existing_handles.add(w.handle)
            except Exception:
                pass

        self._notepad_process = subprocess.Popen("notepad.exe")
        self.wait(2.5, "메모장 시작 대기")

        # 새로 열린 메모장 윈도우 찾기
        new_handle = None
        for attempt in range(10):
            for w in Desktop(backend="uia").windows():
                try:
                    title = w.window_text()
                    if (
                        "메모장" in title or "Notepad" in title
                    ) and w.handle not in existing_handles:
                        new_handle = w.handle
                        break
                except Exception:
                    pass
            if new_handle:
                break
            time.sleep(0.5)

        if not new_handle:
            raise RuntimeError("새 메모장 윈도우를 찾을 수 없습니다")

        self._app = pywinauto.Application(backend="uia").connect(handle=new_handle, timeout=5)
        return self._app

    def _get_edit_control(self, window):
        """메모장 텍스트 편집 영역 찾기 (Win11 Document / 구 버전 Edit 모두 지원)"""
        # Windows 11 메모장: control_type="Document", class="RichEditD2DPT"
        try:
            edit = window.child_window(control_type="Document", found_index=0)
            edit.wait("exists", timeout=3)
            return edit
        except Exception:
            pass
        # 구 버전 메모장: control_type="Edit"
        edit = window.child_window(control_type="Edit", found_index=0)
        edit.wait("exists", timeout=3)
        return edit

    def _set_edit_text(self, edit, text):
        """편집 영역에 텍스트 설정 (set_text가 없는 Document 컨트롤 대응)"""
        if hasattr(edit.wrapper_object(), "set_text"):
            edit.set_text(text)
        else:
            # Win11 Document 컨트롤: 클립보드를 통해 텍스트 삽입
            import pyperclip

            edit.set_focus()
            edit.type_keys("^a", pause=0.05)  # Ctrl+A 전체 선택
            pyperclip.copy(text)
            edit.type_keys("^v", pause=0.05)  # Ctrl+V 붙여넣기

    def _get_edit_text(self, edit):
        """편집 영역 텍스트 읽기"""
        return edit.window_text()

    def _close_notepad_force(self):
        """메모장 강제 종료"""
        if self._app:
            try:
                self._app.kill()
                return
            except Exception:
                pass
        if self._notepad_process:
            try:
                self._notepad_process.terminate()
                self._notepad_process.wait(timeout=3)
            except Exception:
                pass

    def setup(self):
        self.require_windows()
        self.require_package("pywinauto")
        self.require_package("pyautogui")

    def teardown(self):
        try:
            self._close_notepad_force()
        except Exception:
            pass
        self._app = None
        self._notepad_process = None

    # ── 테스트 메서드 ──

    def test_01_open_and_detect(self):
        """메모장 실행 후 pywinauto로 윈도우 감지"""
        self.step("메모장 실행")
        app = self._open_notepad()

        self.step("윈도우 존재 확인")
        window = app.top_window()
        self.assert_true(window.exists(), "메모장 윈도우가 열려야 합니다")
        title = window.window_text()
        self.log(f"윈도우 제목: {title}")
        self.assert_true(
            "메모장" in title or "Notepad" in title,
            "윈도우 제목에 메모장/Notepad가 포함되어야 합니다",
        )

    def test_02_type_and_read_text(self):
        """텍스트 입력 후 다시 읽어서 일치 확인"""
        app = self._open_notepad()

        self.step("편집 영역에 텍스트 입력")
        window = app.top_window()
        edit = self._get_edit_control(window)

        test_text = "Hello RPA! 1234"
        self._set_edit_text(edit, test_text)
        self.wait(0.5, "입력 완료 대기")

        self.step("입력된 텍스트 검증")
        actual = edit.window_text()
        self.assert_contains(actual, "Hello RPA", "영문 포함 확인")
        self.assert_contains(actual, "1234", "숫자 포함 확인")

    def test_03_hotkey_select_copy(self):
        """Ctrl+A → Ctrl+C 단축키 동작 검증"""
        import pyautogui

        app = self._open_notepad()

        window = app.top_window()
        edit = self._get_edit_control(window)

        self.step("텍스트 입력")
        self._set_edit_text(edit, "Clipboard Test")
        self.wait(0.3)

        self.step("Ctrl+A 전체선택 -> Ctrl+C 복사")
        window.set_focus()
        self.wait(0.3)
        pyautogui.hotkey("ctrl", "a")
        self.wait(0.3)
        pyautogui.hotkey("ctrl", "c")
        self.wait(0.5)

        self.step("클립보드 내용 검증")
        try:
            import pyperclip

            clipboard = pyperclip.paste()
            self.assert_contains(clipboard, "Clipboard Test", "클립보드에 복사된 내용 확인")
        except ImportError:
            self.log("[WARN] pyperclip 미설치, 클립보드 검증 건너뜀")

    def test_04_win_inspector_integration(self):
        """WindowInspector로 메모장 UI 트리 추출 테스트"""
        app = self._open_notepad()

        self.step("WindowInspector 로드")
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()
        self.assert_true(inspector.is_available, "pywinauto 사용 가능해야 합니다")

        self.step("윈도우 목록에서 메모장 찾기")
        windows = inspector.list_windows()
        notepad_found = any(
            "메모장" in w.get("title", "") or "Notepad" in w.get("title", "") for w in windows
        )
        self.assert_true(notepad_found, "윈도우 목록에 메모장이 있어야 합니다")

        self.step("메모장 UI 트리 추출")
        # handle 기반으로 직접 연결 (여러 메모장 열려있어도 정확히 식별)
        win_handle = app.top_window().handle
        result = inspector.inspect_window(handle=win_handle, max_depth=3, max_controls=30)

        self.assert_true(
            "error" not in result, f"inspect_window 성공해야 합니다: {result.get('error', '')}"
        )
        self.assert_true(result.get("control_count", 0) > 0, "컨트롤이 1개 이상이어야 합니다")
        self.log(f"발견된 컨트롤: {result['control_count']}개")

        self.step("텍스트 변환 테스트")
        text = inspector.get_control_info_text(result)
        self.assert_contains(text, "컨트롤", "텍스트에 컨트롤 정보가 포함되어야 합니다")
        self.log(f"생성된 텍스트 길이: {len(text)}자")

    def test_05_close_without_save(self):
        """변경 후 저장하지 않고 닫기 (Alt+F4 → 저장 안 함)"""
        import pyautogui

        app = self._open_notepad()

        window = app.top_window()
        edit = self._get_edit_control(window)

        self.step("텍스트 입력 (변경사항 생성)")
        self._set_edit_text(edit, "temp text")
        self.wait(0.3)

        self.step("Alt+F4 닫기 시도")
        window.set_focus()
        pyautogui.hotkey("alt", "F4")
        self.wait(1.0, "저장 대화상자 대기")

        self.step("저장 안 함 선택")
        try:
            pyautogui.hotkey("alt", "n")
            self.wait(0.5)
        except Exception:
            self.log("저장 대화상자 처리 예외 (이미 닫힌 경우)")

        self.step("윈도우 종료 확인")
        self.wait(0.5)
        closed = self._notepad_process.poll() is not None
        if not closed:
            # 프로세스가 아직 살아있으면 한번 더 대기
            self.wait(1.0)
            closed = self._notepad_process.poll() is not None
        self.log(f"메모장 종료 여부: {closed}")
        self._notepad_process = None  # teardown에서 중복 종료 방지
        self._app = None


if __name__ == "__main__":
    from tests.test_runner import TestRunner

    runner = TestRunner(suite_name="notepad")
    runner.add_test_class(NotepadTest)
    result = runner.run()
    runner.save_results(result)
