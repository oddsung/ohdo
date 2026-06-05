# SPDX-License-Identifier: AGPL-3.0-or-later
"""Save As 트리거 probe — 어떤 방법이 Win11 메모장에서 '다른 이름으로 저장'을 여는지 실측."""

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
            if t and any(k in t for k in ("다른 이름으로 저장", "Save As", "저장", "Save")):
                if "메모장" in t or "Notepad" in t:
                    continue  # 메모장 본창 제외
                return t
        except Exception:
            continue
    return None


def try_trigger(label: str, keys) -> str:
    import pyautogui

    print(f"\n--- 시도: {label} ---", flush=True)
    pyautogui.hotkey(*keys)
    time.sleep(2.5)
    dlg = find_save_dialog()
    if dlg:
        print(f"  ✅ 다이얼로그 열림: '{dlg}'", flush=True)
        pyautogui.press("esc")  # 닫기
        time.sleep(0.5)
        return dlg
    print("  ❌ 다이얼로그 없음", flush=True)
    return ""


def main() -> int:
    _dpi()
    import pyautogui
    import pyperclip
    from pywinauto import Application

    pyautogui.FAILSAFE = False
    subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    app = Application(backend="uia").connect(
        title_re=r".*(메모장|Notepad).*", timeout=10, found_index=0
    )
    win = app.window(title_re=r".*(메모장|Notepad).*", found_index=0)
    win.set_focus()
    time.sleep(0.5)
    pyperclip.copy("probe 텍스트")
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.5)

    results = {}
    # 미저장 문서: Ctrl+S 가 보통 Save As 를 연다.
    results["Ctrl+S"] = try_trigger("Ctrl+S", ("ctrl", "s"))
    if not results["Ctrl+S"]:
        win.set_focus()
        time.sleep(0.3)
        results["Ctrl+Shift+S"] = try_trigger("Ctrl+Shift+S", ("ctrl", "shift", "s"))

    print("\n=== 결론 ===", flush=True)
    working = [k for k, v in results.items() if v]
    print(f"동작하는 트리거: {working or '없음'}", flush=True)

    # 정리: 메모장 닫기(저장 안 함).
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
