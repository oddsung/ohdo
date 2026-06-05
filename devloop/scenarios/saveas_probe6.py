# SPDX-License-Identifier: AGPL-3.0-or-later
"""Save As probe6 — AttachThreadInput 포그라운드 강제 후 Ctrl+Shift+S 가 Save As 를 여는지.

가설: 자동화 컨텍스트에서 SetForegroundWindow 가 막혀 가속기/메뉴가 안 먹는다. AttachThreadInput
트릭으로 진짜 포그라운드를 확보하면 키 가속기가 동작할 것. 성공 시 = codegen 의 정확한 fix."""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _dpi() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def force_foreground(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    cur_tid = kernel32.GetCurrentThreadId()
    tgt_tid = user32.GetWindowThreadProcessId(hwnd, None)
    user32.AttachThreadInput(cur_tid, fg_tid, True)
    user32.AttachThreadInput(cur_tid, tgt_tid, True)
    try:
        user32.ShowWindow(hwnd, 5)  # SW_SHOW
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
    finally:
        user32.AttachThreadInput(cur_tid, fg_tid, False)
        user32.AttachThreadInput(cur_tid, tgt_tid, False)


def find_save_dialog():
    from pywinauto import Desktop

    for w in Desktop(backend="uia").windows():
        try:
            t = w.window_text()
            if (
                t
                and ("다른 이름으로 저장" in t or "Save As" in t)
                and "메모장" not in t
                and "Notepad" not in t
            ):
                return t
        except Exception:
            continue
    return None


def main() -> int:
    _dpi()
    import pyautogui
    from pywinauto import Application

    pyautogui.FAILSAFE = False
    subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    app = Application(backend="uia").connect(
        title_re=r".*(메모장|Notepad).*", timeout=10, found_index=0
    )
    win = app.window(title_re=r".*(메모장|Notepad).*", found_index=0)
    hwnd = win.handle
    print(f"hwnd={hwnd}", flush=True)

    force_foreground(hwnd)
    time.sleep(0.6)
    fg_now = ctypes.windll.user32.GetForegroundWindow()
    print(f"강제 후 foreground hwnd={fg_now} (일치={fg_now == hwnd})", flush=True)

    pyautogui.typewrite("probe6 ", interval=0.02)
    time.sleep(0.3)

    print("Ctrl+Shift+S…", flush=True)
    pyautogui.hotkey("ctrl", "shift", "s")
    time.sleep(2.5)
    dlg = find_save_dialog()
    if dlg:
        print(f"\n✅✅✅ 포그라운드 강제 후 Ctrl+Shift+S 로 Save As 열림: '{dlg}'", flush=True)
        pyautogui.press("esc")
    else:
        print("\n❌ 포그라운드 강제 후에도 실패", flush=True)

    time.sleep(0.5)
    try:
        win.close()
        time.sleep(0.5)
        pyautogui.press("n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
