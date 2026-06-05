# SPDX-License-Identifier: AGPL-3.0-or-later
"""Save As probe7 — 영문 IME 강제 후 Ctrl+S / Ctrl+Shift+S 가 Save As 를 여는지(IME 가설 검증)."""

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


def force_english(hwnd: int) -> None:
    """영문(US) 키보드 레이아웃 + IME 영숫자 모드 강제."""
    user32 = ctypes.windll.user32
    KLF_ACTIVATE = 0x00000001
    hkl_eng = user32.LoadKeyboardLayoutW("00000409", KLF_ACTIVATE)
    WM_INPUTLANGCHANGEREQUEST = 0x0050
    user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, hkl_eng)
    time.sleep(0.3)
    try:
        imm32 = ctypes.windll.imm32
        himc = imm32.ImmGetContext(hwnd)
        if himc:
            imm32.ImmSetConversionStatus(himc, 0, 0)  # IME_CMODE_ALPHANUMERIC
            imm32.ImmReleaseContext(hwnd, himc)
    except Exception as e:
        print(f"  IMM 설정 실패(무시): {e}", flush=True)


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


def force_foreground(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    cur = kernel32.GetCurrentThreadId()
    tgt = user32.GetWindowThreadProcessId(hwnd, None)
    user32.AttachThreadInput(cur, fg_tid, True)
    user32.AttachThreadInput(cur, tgt, True)
    try:
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
    finally:
        user32.AttachThreadInput(cur, fg_tid, False)
        user32.AttachThreadInput(cur, tgt, False)


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
    force_foreground(hwnd)
    time.sleep(0.4)
    force_english(hwnd)
    time.sleep(0.4)
    r = win.rectangle()
    pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    time.sleep(0.3)
    pyautogui.typewrite("probe7 ", interval=0.02)
    time.sleep(0.3)

    import os

    shotdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runs")
    os.makedirs(shotdir, exist_ok=True)
    pyautogui.screenshot(os.path.join(shotdir, "probe7_before.png"))
    print("스크린샷: probe7_before.png", flush=True)

    for idx, (label, keys) in enumerate(
        (("Ctrl+S", ("ctrl", "s")), ("Ctrl+Shift+S", ("ctrl", "shift", "s")))
    ):
        force_english(hwnd)
        time.sleep(0.2)
        print(f"--- {label} (영문강제 후) ---", flush=True)
        pyautogui.hotkey(*keys)
        time.sleep(2.5)
        shot = os.path.join(
            shotdir, f"probe7_{idx}_{keys[-1]}{'_shift' if 'shift' in keys else ''}.png"
        )
        pyautogui.screenshot(shot)
        print(f"  스크린샷: {os.path.basename(shot)}", flush=True)
        dlg = find_save_dialog()
        if dlg:
            print(f"  ✅✅✅ Save As 열림: '{dlg}'  ← 트리거: {label}", flush=True)
            pyautogui.press("esc")
            time.sleep(0.5)
            break
        print("  ❌ find_save_dialog 미검출 (스크린샷으로 실제 확인)", flush=True)

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
