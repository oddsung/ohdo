# SPDX-License-Identifier: AGPL-3.0-or-later
"""element-pick 보조 — 대상 앱 요소를 찾아 실제 OS 마우스로 클릭한다.

ohdo picker(/pick/click)는 전역 LL 마우스 후크로 다음 좌클릭을 잡아 그 위치의 UI 요소를
캡처한다. Playwright 는 Electron 렌더러만 제어하므로, picker 가 armed 된 상태에서 이 헬퍼가
pyautogui 로 **실제 좌클릭**을 날려 대상 요소를 선택하게 한다(충실한 picker UX 검증).

좌표계: ohdo 후크는 물리 픽셀(GetCursorPos)을 쓴다. 이 프로세스도 DPI-aware 로 만들어
pywinauto rectangle()(물리)와 pyautogui.click(물리)을 일치시킨다(프로젝트 불변식: DPI 일치).

사용:
  python pick_target.py locate            # Notepad 입력창 중심 "x y how" 출력(클릭 안 함)
  python pick_target.py click             # Notepad 입력창 중심을 실제 좌클릭
"""

from __future__ import annotations

import sys
import time


def _set_dpi_aware() -> None:
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE_V2 근사
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def find_notepad_edit() -> tuple[int, int, str]:
    """메모장 입력(Edit/Document) 컨트롤 중심의 물리 픽셀 좌표를 반환."""
    from pywinauto import Application

    app = Application(backend="uia").connect(
        title_re=r".*(메모장|Notepad).*", timeout=10, found_index=0
    )
    win = app.window(title_re=r".*(메모장|Notepad).*", found_index=0)
    try:
        win.set_focus()
        time.sleep(0.3)
    except Exception:
        pass

    for ct in ("Edit", "Document"):
        try:
            ctrl = win.child_window(control_type=ct, found_index=0)
            ctrl.wait("visible", timeout=3)
            r = ctrl.rectangle()
            return (r.left + r.right) // 2, (r.top + r.bottom) // 2, f"control:{ct}"
        except Exception:
            continue

    # 폴백: 창 본문 하단 1/3 지점(탭/제목줄 회피).
    r = win.rectangle()
    cx = (r.left + r.right) // 2
    cy = r.top + (r.bottom - r.top) * 2 // 3
    return cx, cy, "window-fallback"


def main() -> int:
    _set_dpi_aware()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "click"
    try:
        x, y, how = find_notepad_edit()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR find_notepad_edit: {exc}", file=sys.stderr)
        return 1

    if cmd == "locate":
        print(f"{x} {y} {how}")
        return 0

    import pyautogui

    pyautogui.FAILSAFE = False
    pyautogui.moveTo(x, y, duration=0.4)  # 사람이 보이게 천천히 이동
    time.sleep(0.25)
    pyautogui.click(x, y)
    print(f"CLICKED {x} {y} {how}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
