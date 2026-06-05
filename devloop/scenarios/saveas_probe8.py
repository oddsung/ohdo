# SPDX-License-Identifier: AGPL-3.0-or-later
"""Save As probe8 — 완전한 동작 레시피 검증: 영문강제→Ctrl+S→다이얼로그→경로입력→저장→파일확인.

이게 파일을 실제로 저장하면 = ohdo codegen 수정의 정확한 근거(IME 강제 + 견고한 다이얼로그 처리)."""

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

TARGET = r"C:\Users\doosung.oh\My_Projects\ohdo\tmp\ohdo_probe8.txt"


def _dpi() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def force_english(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    hkl = user32.LoadKeyboardLayoutW("00000409", 0x00000001)  # KLF_ACTIVATE
    user32.PostMessageW(hwnd, 0x0050, 0, hkl)  # WM_INPUTLANGCHANGEREQUEST
    time.sleep(0.3)
    try:
        imm = ctypes.windll.imm32
        himc = imm.ImmGetContext(hwnd)
        if himc:
            imm.ImmSetConversionStatus(himc, 0, 0)  # ALPHANUMERIC
            imm.ImmReleaseContext(hwnd, himc)
    except Exception:
        pass


def force_foreground(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    fg = user32.GetForegroundWindow()
    a, b, c = (
        user32.GetWindowThreadProcessId(fg, None),
        kernel32.GetCurrentThreadId(),
        user32.GetWindowThreadProcessId(hwnd, None),
    )
    user32.AttachThreadInput(c, a, True)
    user32.AttachThreadInput(c, b, True)
    try:
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
    finally:
        user32.AttachThreadInput(c, a, False)
        user32.AttachThreadInput(c, b, False)


def main() -> int:
    _dpi()
    import pyautogui
    import pyperclip
    from pywinauto import Application

    pyautogui.FAILSAFE = False
    if os.path.exists(TARGET):
        os.remove(TARGET)

    subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    app = Application(backend="uia").connect(
        title_re=r".*(메모장|Notepad).*", timeout=10, found_index=0
    )
    win = app.window(title_re=r".*(메모장|Notepad).*", found_index=0)
    nphwnd = win.handle
    force_foreground(nphwnd)
    time.sleep(0.3)
    force_english(nphwnd)
    time.sleep(0.3)
    r = win.rectangle()
    pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    time.sleep(0.3)
    pyperclip.copy("probe8 저장 검증 텍스트")
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.4)

    # 영문 강제 후 Ctrl+S → Save As.
    force_english(nphwnd)
    time.sleep(0.2)
    print("Ctrl+S (영문강제 후)…", flush=True)
    pyautogui.hotkey("ctrl", "s")
    time.sleep(2.0)

    # foreground = Save As 다이얼로그(모달)로 잡기.
    user32 = ctypes.windll.user32
    dlg_hwnd = user32.GetForegroundWindow()
    print(
        f"foreground hwnd after Ctrl+S = {dlg_hwnd} (notepad={nphwnd}, 다름={dlg_hwnd != nphwnd})",
        flush=True,
    )
    shotdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runs")
    pyautogui.screenshot(os.path.join(shotdir, "probe8_dialog.png"))

    if dlg_hwnd == nphwnd:
        print("❌ 다이얼로그가 foreground 아님 — 안 열렸을 수 있음", flush=True)
    else:
        from pywinauto import Application as App2

        try:
            dapp = App2(backend="uia").connect(handle=dlg_hwnd, timeout=5)
            dlg = dapp.window(handle=dlg_hwnd)
            print(
                f"다이얼로그 title='{dlg.window_text()}' class={dlg.element_info.class_name}",
                flush=True,
            )
            # 파일명 Edit 에 경로 입력 (combobox 안 Edit 우선).
            typed = False
            for ct, idx in (("Edit", 0), ("ComboBox", 0)):
                try:
                    edit = dlg.child_window(control_type=ct, found_index=idx)
                    edit.wait("visible", timeout=2)
                    rr = edit.rectangle()
                    pyautogui.click((rr.left + rr.right) // 2, (rr.top + rr.bottom) // 2)
                    time.sleep(0.2)
                    pyautogui.hotkey("ctrl", "a")
                    time.sleep(0.1)
                    pyperclip.copy(TARGET)
                    pyautogui.hotkey("ctrl", "v")
                    typed = True
                    print(f"  경로 입력 via {ct}", flush=True)
                    break
                except Exception:
                    continue
            if not typed:
                # 폴백: 다이얼로그 포커스 상태에서 바로 붙여넣기.
                pyperclip.copy(TARGET)
                pyautogui.hotkey("ctrl", "v")
            time.sleep(0.4)
            pyautogui.press("enter")
            time.sleep(1.5)
            # 덮어쓰기 확인 모달 → y/enter.
            pyautogui.press("enter")
            time.sleep(1.0)
        except Exception as e:
            print(f"다이얼로그 처리 실패: {e}", flush=True)

    saved = os.path.exists(TARGET)
    print(f"\n=== 파일 저장됨: {'✅ ' + TARGET if saved else '❌ 없음'} ===", flush=True)
    if saved:
        print(f"내용: {open(TARGET, encoding='utf-8').read()[:60]}", flush=True)

    time.sleep(0.5)
    try:
        win.close()
        time.sleep(0.5)
        pyautogui.press("n")
    except Exception:
        pass
    return 0 if saved else 2


if __name__ == "__main__":
    sys.exit(main())
