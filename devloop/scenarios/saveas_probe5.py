# SPDX-License-Identifier: AGPL-3.0-or-later
"""Save As probe5 — 메뉴를 '좌표 클릭'(pyautogui)으로 여는 방식 확정(ohdo 가이드 #15 PRIMARY)."""

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


def find_ctrl(scope, names, types):
    for c in scope.descendants():
        try:
            nm = (c.window_text() or "").strip()
            ct = c.element_info.control_type
            if ct in types and any(n == nm or n in nm for n in names):
                return c
        except Exception:
            continue
    return None


def click_ctrl(ctrl) -> tuple[int, int]:
    import pyautogui

    r = ctrl.rectangle()
    x, y = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    pyautogui.click(x, y)
    return x, y


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
    r = win.rectangle()
    pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    time.sleep(0.5)
    pyautogui.typewrite("probe5 ", interval=0.02)
    time.sleep(0.3)

    # 파일 메뉴 좌표 클릭.
    fm = find_ctrl(win, ["파일", "File"], ("MenuItem", "Button", "SplitButton", "MenuBarItem"))
    if not fm:
        print("❌ 파일 메뉴 없음", flush=True)
        return 0
    fx, fy = click_ctrl(fm)
    print(f"파일 메뉴 클릭 ({fx},{fy})", flush=True)
    time.sleep(1.2)

    # 열린 메뉴에서 '다른 이름으로 저장' 좌표 클릭 (win + Desktop 둘 다 탐색).
    sa = find_ctrl(win, ["다른 이름으로 저장"], ("MenuItem", "Button", "Text", "ListItem"))
    if not sa:
        for w in Desktop(backend="uia").windows():
            sa = find_ctrl(w, ["다른 이름으로 저장"], ("MenuItem", "Button", "Text", "ListItem"))
            if sa:
                break
    if not sa:
        print("❌ '다른 이름으로 저장' 항목 없음(메뉴 안 열림?)", flush=True)
        return 0
    sx, sy = click_ctrl(sa)
    print(f"'다른 이름으로 저장' 클릭 ({sx},{sy})", flush=True)
    time.sleep(2.5)

    dlg = find_save_dialog()
    if dlg:
        print(f"\n✅✅ 좌표클릭 메뉴 경로로 Save As 열림: '{dlg}'", flush=True)
        pyautogui.press("esc")
    else:
        print("\n❌ 좌표클릭 메뉴 경로도 실패", flush=True)

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
