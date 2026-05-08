#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
AI RPA Solution - Main Entry Point

AI와 대화하면서 파이썬 RPA 자동화 코드를 단계별로 생성·실행하는 솔루션입니다.
"""

import ctypes
import os
import sys
import warnings
from pathlib import Path

# ★ pywinauto STA 경고 억제 (OleInitialize로 의도적으로 STA로 설정하기 때문)
warnings.filterwarnings("ignore", message="Revert to STA COM threading mode", category=UserWarning)

# ★ Windows 전용 초기화 (DPI Awareness, OLE)
if sys.platform == "win32":
    # DPI Awareness를 QApplication 생성 전에 미리 설정 (Qt의 중복 설정 오류 방지)
    try:
        _DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            _DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        )
    except Exception:
        pass  # 이미 설정되어 있거나 OS가 지원하지 않는 경우 무시

    # OLE 초기화를 가장 먼저 수행 (pywinauto/pywin32가 COM을 초기화하기 전에)
    # OleInitialize는 COM을 STA 모드로 초기화 + OLE 클립보드 기능 활성화
    _ole_result = ctypes.windll.ole32.OleInitialize(None)
    if _ole_result not in (0, 1):  # S_OK=0, S_FALSE=1 (이미 초기화됨)
        print(f"[WARNING] OleInitialize returned: {_ole_result}")

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def check_environment() -> bool:
    """
    환경 설정 확인 및 초기화.

    Returns:
        True: 환경이 유효하거나 사용자가 설정을 완료함
        False: 사용자가 취소함
    """
    try:
        from core.environment_scanner import get_scanner
        from ui.environment_setup_dialog import EnvironmentSetupDialog

        scanner = get_scanner()
        saved_env = scanner.load_saved_environment()

        if saved_env:
            # 저장된 환경 검증
            is_valid, message = scanner.is_environment_valid(saved_env)

            # F.2: 캐시에 Gemini CLI 정보가 없거나 미설치면 fast-path 우회 →
            # dialog 가 사용자에게 상태를 보여주고 게이트하도록 한다.
            gemini_cached = saved_env.get("gemini_cli") or {}
            cache_has_gemini_ok = bool(gemini_cached) and bool(gemini_cached.get("installed"))

            if is_valid and cache_has_gemini_ok:
                # 유효한 환경 - Python 경로 검증만 추가로 수행
                python_path = saved_env.get("python_path")
                if python_path and os.path.exists(python_path):
                    print(f"[INFO] 저장된 환경 사용: {python_path}")
                    return True

        # 새 환경이거나 유효하지 않은 경우 - 설정 다이얼로그 표시
        print("[INFO] 환경 설정이 필요합니다...")

        from PyQt6.QtWidgets import QApplication

        # 임시 QApplication (다이얼로그 표시용)
        temp_app = QApplication.instance()
        if temp_app is None:
            temp_app = QApplication(sys.argv)

        dialog = EnvironmentSetupDialog(force_scan=(saved_env is None))
        result = dialog.exec()

        if result == EnvironmentSetupDialog.DialogCode.Accepted:
            env_data = dialog.get_environment()
            if env_data:
                scanner.save_environment(env_data)
                print(f"[INFO] 환경 설정 완료: {env_data.get('python_path')}")
            return True
        else:
            # 사용자가 취소 - 기본 환경으로 진행 시도
            print("[WARNING] 환경 설정이 취소되었습니다. 기본 환경으로 진행합니다.")
            return True

    except Exception as e:
        print(f"[WARNING] 환경 확인 중 오류: {e}")
        # 오류 발생해도 계속 진행 허용
        return True


def is_admin() -> bool:
    """현재 프로세스가 관리자 권한으로 실행 중인지 확인"""
    try:
        if sys.platform == "win32":
            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        else:
            import os

            return os.getuid() == 0
    except Exception:
        return False


def request_admin_and_restart():
    """UAC를 통해 관리자 권한으로 재시작 (Windows 전용)"""
    if sys.platform != "win32":
        print("[INFO] macOS/Linux에서는 sudo로 실행하세요.")
        return
    try:
        params = " ".join(f'"{a}"' for a in sys.argv)
        ret = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None, "runas", sys.executable, params, None, 1
        )
        if ret > 32:
            sys.exit(0)
        else:
            print(f"[WARNING] 관리자 권한 재시작 실패 (코드: {ret})")
    except Exception as e:
        print(f"[WARNING] 관리자 권한 재시작 중 오류: {e}")


def main():
    """메인 진입점 - PyQt6 GUI를 실행합니다.

    `--ui v2` 인수로 redesign PoC 윈도우 (ui_v2) 를 실행할 수 있습니다.
    기본은 v1 (ui.main_window.MainWindow).
    """
    # --ui v2 분기 (UI redesign 결정 D1~D26 반영, ADR 0001 wrap-first 정책)
    use_v2 = False
    if "--ui" in sys.argv:
        idx = sys.argv.index("--ui")
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1] == "v2":
            use_v2 = True

    try:
        from PyQt6.QtWidgets import QApplication

        if use_v2:
            from ui_v2 import MainWindowV2 as MainWindow

            print("[INFO] UI v2 (redesign PoC) 실행")
        else:
            from ui.main_window import MainWindow
    except ImportError as e:
        print(f"[ERROR] 필수 패키지가 설치되지 않았습니다: {e}")
        print("다음 명령으로 설치해주세요:")
        print(f"  {sys.executable} -m pip install -r requirements.txt")
        sys.exit(1)

    # High DPI 지원
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    # 관리자 권한 상태 출력
    admin_status = is_admin()
    if admin_status:
        print("[INFO] 실행 권한: 관리자 (Administrator)")
    else:
        print("[INFO] 실행 권한: 일반 사용자")
        print("[INFO] 관리자 권한 앱 자동화 시 WM 메시지 클릭이 차단될 수 있습니다.")
        print("[INFO] '--admin' 인수로 실행하면 관리자 권한으로 재시작합니다.")

    # --admin 인수가 있으면 관리자 권한으로 재시작 시도
    if "--admin" in sys.argv and not admin_status:
        print("[INFO] 관리자 권한으로 재시작 중...")
        request_admin_and_restart()
        # 재시작 실패 시 일반 권한으로 계속

    # 환경 체크 (첫 실행 또는 새 컴퓨터인 경우)
    if not check_environment():
        print("[INFO] 프로그램을 종료합니다.")
        sys.exit(0)

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName("AI RPA Solution")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("AI RPA")

    # Win32 API 클립보드 폴백 설치 (Windows 전용)
    if sys.platform == "win32":
        _install_clipboard_fallback(app)

    # 메인 윈도우 생성 및 표시
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


def _install_clipboard_fallback(app):
    """
    Qt OLE 클립보드가 실패할 경우를 대비한 Win32 API 직접 복사 폴백.
    QApplication에 전역 이벤트 필터를 설치하여 Ctrl+C를 가로챕니다.
    """
    from PyQt6.QtCore import QEvent, QObject, Qt
    from PyQt6.QtWidgets import QApplication

    class ClipboardFallbackFilter(QObject):
        def eventFilter(self, obj, event):
            if (
                event.type() == QEvent.Type.KeyPress
                and event.key() == Qt.Key.Key_C
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            ):
                widget = QApplication.focusWidget()
                text = ""

                # QPlainTextEdit / QTextEdit
                if hasattr(widget, "textCursor"):
                    cursor = widget.textCursor()
                    text = cursor.selectedText()
                    # QTextCursor uses \u2029 as paragraph separator
                    text = text.replace("\u2029", "\n")
                # QLabel
                elif hasattr(widget, "selectedText"):
                    text = widget.selectedText()

                if text:
                    _win32_copy(text)
                    return True
            return False

    app._clipboard_filter = ClipboardFallbackFilter()
    app.installEventFilter(app._clipboard_filter)


def _win32_copy(text: str):
    """Win32 API를 직접 사용하여 텍스트를 클립보드에 복사합니다."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # 64비트 Windows에서 포인터/핸들을 주고받는 모든 함수에
    # argtypes와 restype을 명시해야 OverflowError/access violation 방지 가능
    # --- kernel32 ---
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p
    # --- user32 ---
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = ctypes.c_bool
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = ctypes.c_bool

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    if not user32.OpenClipboard(None):
        return

    try:
        user32.EmptyClipboard()

        encoded = text.encode("utf-16-le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not h_mem:
            return

        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            kernel32.GlobalFree(h_mem)
            return

        ctypes.memmove(p_mem, encoded, len(encoded))
        kernel32.GlobalUnlock(h_mem)

        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
    finally:
        user32.CloseClipboard()


if __name__ == "__main__":
    main()
