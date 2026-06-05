# SPDX-License-Identifier: AGPL-3.0-or-later
"""Save As probe2 — 창을 '클릭'으로 포그라운드化 후 Ctrl+S 가 Save As 를 여는지 확인.

가설: set_focus() 만으로는 Win11 포그라운드 전환이 불안정 → 단축키 미전달.
입력창을 실제 클릭하면(포커스 확보) 이후 단축키가 동작할 것."""

from __future__ import annotations

import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _dpi() -> None:
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def find_save_dialog():
    from pywinauto import Desktop

    for w in Desktop(backend="uia").windows():
        try:
            t = w.window_text()
            if t and ("저장" in t or "Save" in t) and "메모장" not in t and "Notepad" not in t:
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

    # 입력창(Document/Edit) 중심을 실제 클릭 → 포그라운드+포커스 확보.
    r = win.rectangle()
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    print(f"창 클릭으로 포그라운드化: ({cx},{cy})", flush=True)
    pyautogui.click(cx, cy)
    time.sleep(0.6)
    pyautogui.typewrite("probe2 ", interval=0.02)
    time.sleep(0.3)

    print("Ctrl+S 입력…", flush=True)
    pyautogui.hotkey("ctrl", "s")
    time.sleep(2.5)
    dlg = find_save_dialog()
    if dlg:
        print(f"✅ 클릭-포그라운드 후 Ctrl+S 로 다이얼로그 열림: '{dlg}'", flush=True)
        pyautogui.press("esc")
    else:
        print(
            "❌ 클릭 후에도 Ctrl+S 다이얼로그 없음 — 단축키 자체 미동작 가능(메뉴 방식 필요)",
            flush=True,
        )

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
