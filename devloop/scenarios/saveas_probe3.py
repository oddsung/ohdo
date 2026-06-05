# SPDX-License-Identifier: AGPL-3.0-or-later
"""Save As probe3 — 동작하는 Save As 트리거 탐색: pywinauto type_keys / 앱 메뉴(UIA)."""

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
    from pywinauto import Application

    subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    app = Application(backend="uia").connect(
        title_re=r".*(메모장|Notepad).*", timeout=10, found_index=0
    )
    win = app.window(title_re=r".*(메모장|Notepad).*", found_index=0)
    win.set_focus()
    time.sleep(0.5)
    try:
        win.type_keys("probe3 ", with_spaces=True)
    except Exception as e:
        print(f"type_keys 텍스트 실패: {e}", flush=True)

    # 방법 A: pywinauto type_keys 단축키(SendInput 기반, set_foreground).
    print("--- A: win.type_keys('^s', set_foreground=True) ---", flush=True)
    try:
        win.type_keys("^s", set_foreground=True)
    except Exception as e:
        print(f"  type_keys ^s 실패: {e}", flush=True)
    time.sleep(2.5)
    dlg = find_save_dialog()
    if dlg:
        print(f"  ✅ 열림: '{dlg}'", flush=True)
        import pyautogui

        pyautogui.press("esc")
        time.sleep(0.5)
    else:
        print("  ❌ 없음", flush=True)

    # 방법 B: 메뉴/툴바에서 'Save'/'저장' 관련 MenuItem·Button 을 UIA 로 찾아 invoke.
    if not dlg:
        print("--- B: UIA 메뉴/버튼에서 Save as 탐색 ---", flush=True)
        try:
            hits = []
            for c in win.descendants():
                try:
                    ct = c.element_info.control_type
                    name = c.window_text() or ""
                    if ct in ("MenuItem", "Button", "Custom") and (
                        "저장" in name or "Save" in name or "다른 이름" in name
                    ):
                        hits.append((ct, name))
                except Exception:
                    continue
            print(f"  Save 관련 컨트롤 {len(hits)}개: {hits[:10]}", flush=True)
        except Exception as e:
            print(f"  descendants 실패: {e}", flush=True)

    time.sleep(0.5)
    try:
        win.close()
        time.sleep(0.5)
        import pyautogui

        pyautogui.press("n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
