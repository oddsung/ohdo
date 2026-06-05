# SPDX-License-Identifier: AGPL-3.0-or-later
"""Save As probe9 — step3 경로 재현: set_focus(클릭 없음) + shim식 force_english + Ctrl+Shift+S.
foreground hwnd 확인 + 스크린샷으로 실패 원인(포그라운드 vs IME) 최종 규명."""

from __future__ import annotations

import ctypes
import os
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


def force_english_ime(hwnd=None):
    try:
        u = ctypes.windll.user32
        if not hwnd:
            hwnd = u.GetForegroundWindow()
        try:
            imm = ctypes.windll.imm32
            himc = imm.ImmGetContext(hwnd)
            if himc:
                imm.ImmSetConversionStatus(himc, 0, 0)
                imm.ImmReleaseContext(hwnd, himc)
        except Exception:
            pass
        hkl = u.LoadKeyboardLayoutW("00000409", 0x00000001)
        u.PostMessageW(hwnd, 0x0050, 0, hkl)
        time.sleep(0.3)
    except Exception:
        pass


def main() -> int:
    _dpi()
    import pyautogui
    from pywinauto import Application, Desktop

    pyautogui.FAILSAFE = False
    subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    app = Application(backend="uia").connect(
        title_re=r".*(메모장|Notepad).*", timeout=10, found_index=0
    )
    win = app.window(title_re=r".*(메모장|Notepad).*", found_index=0)
    nphwnd = win.handle

    # step3 처럼 클릭 없이 set_focus 만.
    win.set_focus()
    time.sleep(0.5)
    u = ctypes.windll.user32
    fg = u.GetForegroundWindow()
    print(f"set_focus 후: foreground={fg} notepad={nphwnd} 일치={fg == nphwnd}", flush=True)

    # shim 식: force_english_ime(None) = GetForegroundWindow 대상.
    force_english_ime(None)
    time.sleep(0.2)
    print("Ctrl+Shift+S (shim식 force_english 후)…", flush=True)
    pyautogui.hotkey("ctrl", "shift", "s")
    time.sleep(2.5)

    shotdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runs")
    pyautogui.screenshot(os.path.join(shotdir, "probe9.png"))
    fg2 = u.GetForegroundWindow()
    print(f"단축키 후 foreground={fg2} (notepad와 다름={fg2 != nphwnd})", flush=True)

    found = None
    for w in Desktop(backend="uia").windows():
        try:
            t = w.window_text()
            if t and "다른 이름으로 저장" in t and "메모장" not in t:
                found = t
                break
        except Exception:
            continue
    print(f"Save As 다이얼로그: {found or '❌ 없음'}", flush=True)

    time.sleep(0.5)
    try:
        pyautogui.press("esc")
        win.close()
        time.sleep(0.5)
        pyautogui.press("n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
