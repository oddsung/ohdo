# SPDX-License-Identifier: AGPL-3.0-or-later
"""Save As probe10 — 완전 레시피: foreground 다이얼로그 + 자동포커스 파일명필드(클릭 없음) → 저장."""

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

TARGET = r"C:\Users\doosung.oh\My_Projects\ohdo\tmp\ohdo_probe10.txt"


def _dpi() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def force_english(hwnd: int) -> None:
    try:
        u = ctypes.windll.user32
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
    import pyperclip
    from pywinauto import Application

    pyautogui.FAILSAFE = False
    if os.path.exists(TARGET):
        os.remove(TARGET)
    shotdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runs")

    subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    app = Application(backend="uia").connect(
        title_re=r".*(메모장|Notepad).*", timeout=10, found_index=0
    )
    win = app.window(title_re=r".*(메모장|Notepad).*", found_index=0)
    nphwnd = win.handle
    r = win.rectangle()
    pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)  # 포그라운드+edit 포커스
    time.sleep(0.4)
    force_english(nphwnd)
    pyperclip.copy("probe10 저장 검증")
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.4)

    # Save As 트리거.
    force_english(nphwnd)
    pyautogui.hotkey("ctrl", "shift", "s")
    time.sleep(2.0)

    u = ctypes.windll.user32
    dlg = u.GetForegroundWindow()
    print(f"다이얼로그 hwnd={dlg} (notepad={nphwnd}, 다름={dlg != nphwnd})", flush=True)
    pyautogui.screenshot(os.path.join(shotdir, "probe10_dialog.png"))

    if dlg == nphwnd:
        print("❌ 다이얼로그 안 열림", flush=True)
    else:
        # 파일명 필드는 다이얼로그 오픈 시 자동 포커스 — 클릭하지 말 것.
        force_english(dlg)
        pyautogui.hotkey("ctrl", "a")  # 기본 파일명 전체선택
        time.sleep(0.2)
        pyperclip.copy(TARGET)
        pyautogui.hotkey("ctrl", "v")  # 전체 경로 붙여넣기
        time.sleep(0.4)
        pyautogui.press("enter")  # 저장
        time.sleep(1.2)
        pyautogui.screenshot(os.path.join(shotdir, "probe10_after_enter.png"))
        # 덮어쓰기 확인 모달이면 Enter.
        pyautogui.press("enter")
        time.sleep(1.0)

    saved = os.path.exists(TARGET)
    print(f"=== 파일 저장됨: {'✅ ' + TARGET if saved else '❌ 없음'} ===", flush=True)
    if saved:
        print(f"내용: {open(TARGET, encoding='utf-8').read()[:60]}", flush=True)

    time.sleep(0.3)
    try:
        win.close()
        time.sleep(0.5)
        pyautogui.press("n")
    except Exception:
        pass
    return 0 if saved else 2


if __name__ == "__main__":
    sys.exit(main())
