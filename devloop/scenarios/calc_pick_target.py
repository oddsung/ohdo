# SPDX-License-Identifier: AGPL-3.0-or-later
"""계산기 버튼 pick 보조 — 버튼을 UIA(auto_id)로 찾아 실제 클릭(picker armed 상태) + 결과 읽기.

사용:
  python calc_pick_target.py click num7Button   # num7Button 중심을 실제 좌클릭(picker 캡처용)
  python calc_pick_target.py locate plusButton   # 좌표만 출력
  python calc_pick_target.py result              # CalculatorResults 디스플레이 텍스트 출력
"""

from __future__ import annotations

import sys
import time


def _dpi() -> None:
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _connect():
    from pywinauto import Application

    app = Application(backend="uia").connect(
        title_re=r".*(계산기|Calculator).*", timeout=10, found_index=0
    )
    return app.window(title_re=r".*(계산기|Calculator).*", found_index=0)


def main() -> int:
    _dpi()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "result"

    # 계산기 연결 불필요한 명령(스크린샷)은 먼저 처리.
    if cmd == "shot":
        import os

        import pyautogui

        name = sys.argv[2] if len(sys.argv) > 2 else "shot"
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runs")
        os.makedirs(d, exist_ok=True)
        pyautogui.screenshot(os.path.join(d, name + ".png"))
        print(f"shot {name}")
        return 0

    try:
        win = _connect()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR connect: {exc}", file=sys.stderr)
        return 1

    if cmd == "result":
        try:
            res = win.child_window(auto_id="CalculatorResults")
            print((res.window_text() or "").strip())
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR result: {exc}", file=sys.stderr)
            return 1

    auto_id = sys.argv[2]
    try:
        win.set_focus()
        time.sleep(0.3)
        btn = win.child_window(auto_id=auto_id, control_type="Button")
        btn.wait("visible", timeout=5)
        r = btn.rectangle()
        x, y = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR find {auto_id}: {exc}", file=sys.stderr)
        return 1

    if cmd == "locate":
        print(f"{x} {y}")
        return 0

    import pyautogui

    pyautogui.FAILSAFE = False
    pyautogui.moveTo(x, y, duration=0.3)
    time.sleep(0.2)
    pyautogui.click(x, y)
    print(f"CLICKED {auto_id} {x} {y}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
