# SPDX-License-Identifier: AGPL-3.0-or-later
"""Save As 진단 — Win11 메모장의 '다른 이름으로 저장' 다이얼로그 실제 타이틀/구조를 실측.

생성 코드가 `_find_dialog(["다른 이름으로 저장","Save As"])` 로 못 찾은 원인을 규명한다.
메모장 실행→텍스트 입력→Ctrl+Shift+S→탑레벨 창 열거 + 후보 다이얼로그 자식 컨트롤 출력.
"""

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


def main() -> int:
    _dpi()
    import pyautogui
    import pyperclip
    from pywinauto import Application, Desktop

    pyautogui.FAILSAFE = False
    subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    app = Application(backend="uia").connect(
        title_re=r".*(메모장|Notepad).*", timeout=10, found_index=0
    )
    win = app.window(title_re=r".*(메모장|Notepad).*", found_index=0)
    win.set_focus()
    time.sleep(0.5)
    pyperclip.copy("save as 진단 텍스트")
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.5)

    print("Ctrl+Shift+S 입력 → Save As 대기…", flush=True)
    pyautogui.hotkey("ctrl", "shift", "s")
    time.sleep(3.0)

    print("=== 탑레벨 창 (control_type | title | class) ===", flush=True)
    cand = None
    for w in Desktop(backend="uia").windows():
        try:
            t = w.window_text()
            ct = w.element_info.control_type
            cls = w.element_info.class_name
            if t:
                print(f"  [{ct}] '{t}'  (class={cls})", flush=True)
                if cand is None and any(k in t for k in ("저장", "Save", "이름")):
                    cand = w
        except Exception:
            continue

    if cand is not None:
        print(f"\n=== 후보 다이얼로그: '{cand.window_text()}' 의 자식 컨트롤 ===", flush=True)
        try:
            for c in cand.descendants():
                try:
                    ct = c.element_info.control_type
                    name = c.window_text()
                    aid = c.element_info.automation_id
                    if ct in ("Edit", "Button", "ComboBox", "Document") and (name or aid):
                        print(f"  [{ct}] name='{name}' auto_id='{aid}'", flush=True)
                except Exception:
                    continue
        except Exception as e:
            print(f"  descendants 실패: {e}", flush=True)
    else:
        print("\n⚠️ 저장/Save/이름 포함 다이얼로그를 찾지 못함 (생성코드와 동일 증상)", flush=True)

    # 정리: Esc 로 다이얼로그 닫고, 메모장 닫기(저장 안 함).
    time.sleep(0.5)
    pyautogui.press("esc")
    time.sleep(0.5)
    try:
        win.close()
        time.sleep(0.5)
        pyautogui.press("n")  # "변경 내용 저장?" → 저장 안 함
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
