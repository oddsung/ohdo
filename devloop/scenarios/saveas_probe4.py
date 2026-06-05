# SPDX-License-Identifier: AGPL-3.0-or-later
"""Save As probe4 — 메뉴(UIA) 경로로 '다른 이름으로 저장'을 여는지 확정.

키보드 가속기(Ctrl+Shift+S)가 이 환경에서 Save As 를 못 열므로, 파일 메뉴 → 다른 이름으로 저장
메뉴 항목을 UIA 로 찾아 클릭하는 방식이 동작하는지 검증한다(= codegen 의 견고한 대체 방법)."""

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
                and ("다른 이름으로 저장" in t or "Save As" in t or "저장" in t)
                and "메모장" not in t
                and "Notepad" not in t
            ):
                return t
        except Exception:
            continue
    return None


def click_center(ctrl) -> None:
    import pyautogui

    r = ctrl.rectangle()
    pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)


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
    r = win.rectangle()
    pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)  # 포그라운드
    time.sleep(0.5)
    pyautogui.typewrite("probe4 ", interval=0.02)
    time.sleep(0.3)

    # 1) 파일 메뉴 열기 — MenuItem/Button/SplitButton 중 '파일'/'File'.
    print("파일 메뉴 탐색…", flush=True)
    file_menu = None
    for c in win.descendants():
        try:
            name = (c.window_text() or "").strip()
            ct = c.element_info.control_type
            if name in ("파일", "File", "파일(F)") and ct in (
                "MenuItem",
                "Button",
                "SplitButton",
                "MenuBarItem",
            ):
                file_menu = c
                break
        except Exception:
            continue
    if file_menu is None:
        print("  ❌ 파일 메뉴 못 찾음", flush=True)
    else:
        print(
            f"  파일 메뉴: [{file_menu.element_info.control_type}] '{file_menu.window_text()}'",
            flush=True,
        )
        try:
            file_menu.invoke()
        except Exception:
            click_center(file_menu)
        time.sleep(1.0)

        # 2) '다른 이름으로 저장' 항목 클릭.
        print("'다른 이름으로 저장' 항목 탐색…", flush=True)
        save_as = None
        for c in win.descendants():
            try:
                name = (c.window_text() or "").strip()
                if "다른 이름으로 저장" in name or "Save as" in name.lower():
                    save_as = c
                    break
            except Exception:
                continue
        # 메뉴 항목이 win 자식이 아닐 수 있어 Desktop 도 탐색.
        if save_as is None:
            from pywinauto import Desktop

            for w in Desktop(backend="uia").windows():
                try:
                    for c in w.descendants():
                        name = (c.window_text() or "").strip()
                        if "다른 이름으로 저장" in name:
                            save_as = c
                            break
                    if save_as:
                        break
                except Exception:
                    continue
        if save_as is None:
            print("  ❌ '다른 이름으로 저장' 항목 못 찾음", flush=True)
        else:
            print(
                f"  항목: [{save_as.element_info.control_type}] '{save_as.window_text()}'",
                flush=True,
            )
            try:
                save_as.invoke()
            except Exception:
                click_center(save_as)
            time.sleep(2.0)

    dlg = find_save_dialog()
    if dlg:
        print(f"\n✅ 메뉴 경로로 Save As 다이얼로그 열림: '{dlg}'", flush=True)
        pyautogui.press("esc")
    else:
        print("\n❌ 메뉴 경로도 실패", flush=True)

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
