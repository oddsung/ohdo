# SPDX-License-Identifier: AGPL-3.0-or-later
"""multimon pick 보조 — 계산기를 DPI 가 다른 보조모니터로 옮겨 hover/click/스크린샷.

handoff §76(브리지 DPI awareness)/§77(디스플레이별 hover 오버레이) 실측용.
picker armed 상태에서 실제 OS 마우스로 hover/click 을 날리고, 전 모니터를
각각 캡처해 붉은 박스가 "요소가 있는 디스플레이에만, 요소 위에 정확히"
그려지는지 눈으로 검증할 수 있게 한다.

사용 (모두 물리 픽셀 좌표, PER_MONITOR_AWARE_V2):
  python multimon_target.py setup             # 계산기 실행+보조모니터로 이동, TARGET 좌표 출력
  python multimon_target.py locate num7Button # 버튼 중심/rect 출력
  python multimon_target.py hover X Y         # 마우스 이동만 (클릭 X)
  python multimon_target.py click X Y         # 실제 좌클릭 (picker 캡처용)
  python multimon_target.py shot NAME         # 전 모니터 crop PNG 저장 (MULTIMON_SHOT_DIR)
  python multimon_target.py teardown          # 계산기 종료
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

user32 = ctypes.windll.user32
shcore = ctypes.windll.shcore


def _dpi() -> None:
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
        return
    except Exception:
        pass
    try:
        shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def monitors() -> list[dict]:
    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM
    )

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wt.DWORD),
            ("rcMonitor", wt.RECT),
            ("rcWork", wt.RECT),
            ("dwFlags", wt.DWORD),
            ("szDevice", wt.WCHAR * 32),
        ]

    out: list[dict] = []

    def cb(hmon, hdc, lprect, lparam):
        r = lprect.contents
        dx = ctypes.c_uint()
        dy = ctypes.c_uint()
        shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dx), ctypes.byref(dy))
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
        user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        out.append(
            {
                "device": mi.szDevice,
                "primary": bool(mi.dwFlags & 1),
                "rect": (r.left, r.top, r.right, r.bottom),
                "dpi": dx.value,
            }
        )
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    return out


def pick_secondary() -> dict:
    """주모니터와 DPI 차이가 가장 큰 비주(非主) 모니터를 고른다."""
    mons = monitors()
    primary = next(m for m in mons if m["primary"])
    secondaries = [m for m in mons if not m["primary"]]
    if not secondaries:
        raise RuntimeError("no secondary monitor")
    return max(secondaries, key=lambda m: abs(m["dpi"] - primary["dpi"]))


def _connect(timeout: float = 20.0):
    from pywinauto import Application

    app = Application(backend="uia").connect(
        title_re=r".*(계산기|Calculator).*", timeout=timeout, found_index=0
    )
    return app.window(title_re=r".*(계산기|Calculator).*", found_index=0)


def _btn_center(win, auto_id: str) -> tuple[int, int, tuple[int, int, int, int]]:
    btn = win.child_window(auto_id=auto_id, control_type="Button")
    btn.wait("visible", timeout=5)
    r = btn.rectangle()
    return (r.left + r.right) // 2, (r.top + r.bottom) // 2, (r.left, r.top, r.right, r.bottom)


def cmd_setup() -> int:
    mon = pick_secondary()
    ml, mt, mr, mb = mon["rect"]
    try:
        win = _connect(timeout=3.0)
    except Exception:
        subprocess.Popen(["calc.exe"], shell=False)
        win = _connect(timeout=25.0)
    win.wait("visible", timeout=10)
    time.sleep(0.5)
    # 보조모니터 안쪽으로 이동 (물리 픽셀). UIA 백엔드엔 move_window 가 없어
    # hwnd 로 Win32 MoveWindow 직접 호출. 이동 후 DPI 재스케일 안정화 대기.
    w = min(620, mr - ml - 160)
    h = min(820, mb - mt - 160)
    hwnd = win.wrapper_object().handle
    user32.MoveWindow(hwnd, ml + 80, mt + 80, w, h, True)
    time.sleep(1.2)
    win.set_focus()
    time.sleep(0.3)
    x, y, rect = _btn_center(win, "num7Button")
    print(f"MONITOR {mon['device']} {ml} {mt} {mr} {mb} dpi={mon['dpi']}")
    print(f"TARGET num7Button {x} {y} rect={rect[0]},{rect[1]},{rect[2]},{rect[3]}")
    return 0


def cmd_locate(auto_id: str) -> int:
    win = _connect()
    x, y, rect = _btn_center(win, auto_id)
    print(f"TARGET {auto_id} {x} {y} rect={rect[0]},{rect[1]},{rect[2]},{rect[3]}")
    return 0


def cmd_hover(x: int, y: int) -> int:
    import pyautogui

    pyautogui.FAILSAFE = False
    pyautogui.moveTo(x, y, duration=0.5)
    print(f"HOVER {x} {y}")
    return 0


def cmd_click(x: int, y: int) -> int:
    import pyautogui

    pyautogui.FAILSAFE = False
    pyautogui.moveTo(x, y, duration=0.4)
    time.sleep(0.25)
    pyautogui.click(x, y)
    print(f"CLICKED {x} {y}")
    return 0


def cmd_shot(name: str) -> int:
    from PIL import ImageGrab

    d = os.environ.get("MULTIMON_SHOT_DIR") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "runs"
    )
    os.makedirs(d, exist_ok=True)
    vx = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
    vy = user32.GetSystemMetrics(77)
    img = ImageGrab.grab(all_screens=True)
    for i, m in enumerate(monitors()):
        left, top, right, bottom = m["rect"]
        crop = img.crop((left - vx, top - vy, right - vx, bottom - vy))
        tag = "primary" if m["primary"] else f"sec{i}"
        path = os.path.join(d, f"{name}_{tag}_dpi{m['dpi']}.png")
        crop.save(path)
        print(f"SHOT {path}")
    return 0


def cmd_teardown() -> int:
    subprocess.run(
        ["taskkill", "/f", "/im", "CalculatorApp.exe"],
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["taskkill", "/f", "/im", "Calculator.exe"],
        capture_output=True,
        check=False,
    )
    print("TEARDOWN done")
    return 0


def main() -> int:
    _dpi()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "setup"
    try:
        if cmd == "setup":
            return cmd_setup()
        if cmd == "locate":
            return cmd_locate(sys.argv[2])
        if cmd == "hover":
            return cmd_hover(int(sys.argv[2]), int(sys.argv[3]))
        if cmd == "click":
            return cmd_click(int(sys.argv[2]), int(sys.argv[3]))
        if cmd == "shot":
            return cmd_shot(sys.argv[2] if len(sys.argv) > 2 else "shot")
        if cmd == "teardown":
            return cmd_teardown()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR {cmd}: {exc}", file=sys.stderr)
        return 1
    print(f"ERROR unknown cmd: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
