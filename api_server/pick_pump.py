# SPDX-License-Identifier: AGPL-3.0-or-later
"""클릭 시 요소 캡처 — 전역 LL 마우스 후크 (handoff §48, 절충안).

카운트다운(§40)을 대체한다: 사용자가 대상 요소를 **클릭**하면 그 좌표의 element 를
캡처한다. 하이라이트 오버레이는 없다(최소 구현).

§42 와 동일한 Windows 제약: WH_MOUSE_LL/WH_KEYBOARD_LL 훅은 ``SetWindowsHookEx`` 를
호출한 **그 스레드**에서 메시지 펌프(PeekMessage)가 돌아야 콜백이 발화한다. 이 모듈은
요청(스레드풀) 스레드를 점유한 채 직접 펌프를 돌리며 첫 좌클릭(또는 ESC/타임아웃)까지
블록한다. 선택용 클릭은 ``return 1`` 로 **삼켜서**(swallow) 대상 앱이 실제로 눌리지
않게 한다.

core/ 무수정 — element 검출은 기존 ``capture_element_at`` 재사용.
Windows 전용 ctypes 정의는 함수 내부에 둬서 비-Windows(예: CI ubuntu)에서도 import 안전.
"""

from __future__ import annotations

import threading
import time

# Win32 상수 (정수만 — import-safe).
_WH_MOUSE_LL = 14
_WH_KEYBOARD_LL = 13
_WM_LBUTTONDOWN = 0x0201
_WM_LBUTTONUP = 0x0202
_WM_KEYDOWN = 0x0100
_WM_SYSKEYDOWN = 0x0104
_VK_ESCAPE = 0x1B
_VK_F3 = 0x72  # 일시정지 토글 (v2 element_picker 와 동일 키)
_HC_ACTION = 0

# SetWindowPos — 작업표시줄(Shell_TrayWnd) 위로 z-order 강제 (handoff §49 fix2).
# Electron setAlwaysOnTop/moveTop 은 Windows 작업표시줄의 특수 topmost 를 못 이김.
_HWND_TOPMOST = -1
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010
_TOPMOST_INTERVAL_S = 0.2

_lock = threading.Lock()
_cancel = threading.Event()
_active = threading.Event()
# 일시정지 (handoff §49 fix6) — F3 토글. paused 동안 클릭이 대상 앱으로 통과(메뉴 펼침
# 등 조작 가능) + 하이라이트 끔. 다시 F3 로 재개하면 다음 클릭이 선택.
_paused = threading.Event()

# Electron 오버레이 창 HWND — main 이 /pick/overlay 로 등록. 펌프 루프가 이 창을
# SetWindowPos(HWND_TOPMOST) 로 주기적으로 최상단에 박는다 (작업표시줄 가림 회피).
_overlay_hwnd: int | None = None

# 실시간 hover 하이라이트용 — 펌프 루프가 ~50ms 마다 갱신하는 "커서 아래 element 의
# rect" (물리 픽셀, {left,top,right,bottom} 또는 None). /pick/hover 가 이 값을 읽어
# Electron 오버레이가 붉은 박스를 그린다. dict 교체는 GIL 하에 원자적이라 별도 lock 불필요.
_hover_rect: dict | None = None
_HOVER_INTERVAL_S = 0.05  # 하이라이트 샘플링 주기 (UIA EFP 는 펌프 루프에서 — 후크 proc 금지)


def is_active() -> bool:
    """클릭 캡처가 진행 중인가."""
    return _active.is_set()


def get_hover_rect() -> dict | None:
    """현재 커서 아래 element 의 rect(물리 픽셀) 반환 — 없으면 None. (오버레이 폴링용)"""
    return _hover_rect


def is_paused() -> bool:
    """일시정지(F3) 중인가 — 오버레이가 안내 배너 전환에 사용."""
    return _paused.is_set()


def set_overlay_hwnd(hwnd: int | None) -> None:
    """Electron 오버레이 창의 HWND 등록 (handoff §49 fix2).

    펌프 루프가 이 HWND 를 SetWindowPos(HWND_TOPMOST) 로 주기 재적용해 작업표시줄 위
    z-order 를 강제한다(Electron setAlwaysOnTop 으론 Shell_TrayWnd 못 이김). 0/None=해제.
    """
    global _overlay_hwnd
    _overlay_hwnd = int(hwnd) if hwnd else None


def cancel_pick() -> bool:
    """진행 중인 클릭 캡처를 취소(있으면). 반환: 취소 신호를 보냈는지."""
    if _active.is_set():
        _cancel.set()
        return True
    return False


def pick_on_click(timeout_s: float = 60.0) -> dict:
    """다음 좌클릭(또는 ESC/타임아웃)까지 블록 → 클릭 좌표의 element 캡처.

    별도 UIA 워커 스레드가 ~50ms 마다 커서 아래 element rect 를 ``_hover_rect`` 에
    갱신한다(실시간 하이라이트 — /pick/hover 가 폴링). 후크 스레드는 메시지 펌프만 돌려
    항상 즉시 반환 → 마우스 끊김 없음(§49 fix6, §42/PR-17 drain 패턴).
    F3 로 일시정지 토글(메뉴 펼친 후 선택), ESC 로 취소.

    동시 호출은 거부(이미 진행 중). 반환 dict 는 ``/pick`` 과 동일 shape + ``cancelled`` 플래그.
    """
    import ctypes
    import ctypes.wintypes

    if not _lock.acquire(blocking=False):
        return {"success": False, "error": "이미 element 선택이 진행 중입니다."}

    user32 = ctypes.windll.user32
    lresult = ctypes.c_ssize_t
    ulong_ptr = ctypes.wintypes.WPARAM
    hookproc = ctypes.WINFUNCTYPE(
        lresult, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM
    )

    # SetWindowPos argtypes 명시 — 미지정 시 ctypes 가 포인터/HWND 를 32-bit int 로
    # 취급해 x64 에서 HWND_TOPMOST 호출이 조용히 실패한다(v2 _ensure_user32_argtypes 와
    # 동일 — 작업표시줄 위 z-order 강제의 핵심). (handoff §49 fix3)
    try:
        user32.SetWindowPos.argtypes = [
            ctypes.wintypes.HWND,
            ctypes.wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.SetWindowPos.restype = ctypes.wintypes.BOOL
    except Exception:
        pass

    class _MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("pt", ctypes.wintypes.POINT),
            ("mouseData", ctypes.wintypes.DWORD),
            ("flags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ulong_ptr),
        ]

    class _KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", ctypes.wintypes.DWORD),
            ("scanCode", ctypes.wintypes.DWORD),
            ("flags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ulong_ptr),
        ]

    global _hover_rect, _overlay_hwnd
    captured: dict = {"pt": None}
    # 워커(UIA)와 펌프(후크) 스레드 간 최종 캡처 핸드오프.
    final: dict = {"pt": None, "element": None}
    final_done = threading.Event()
    worker_stop = threading.Event()
    _hover_rect = None
    _cancel.clear()
    _paused.clear()
    _active.set()

    # ── UIA 워커 스레드 (handoff §49 fix6 — 마우스 느려짐 해결) ──
    # 무거운 UIA EFP(capture_element_at)를 LL 후크 스레드에서 떼어내 별도 스레드로.
    # 후크 스레드가 EFP 로 블록되면 그동안 PeekMessage 가 안 돌아 Windows 가 전역
    # 마우스 입력을 후크에 동기 전달하려다 멈칫 → 마우스 끊김. 워커로 분리하면 후크
    # 스레드는 항상 메시지만 펌프(즉시 반환) → 마우스 부드러움. (§42/PR-17 drain 패턴)
    # 모든 capture_element_at 호출은 이 워커 한 스레드에서만 → COM apartment 일관성.
    def _uia_worker() -> None:
        global _hover_rect
        try:
            ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # STA
        except Exception:
            pass
        try:
            from core.element_inspect import capture_element_at

            wpt = ctypes.wintypes.POINT()
            while not worker_stop.is_set():
                # 1) 클릭 확정 → 그 좌표 최종(정밀) 캡처
                if final["pt"] is not None and not final_done.is_set():
                    fx, fy = final["pt"]
                    try:
                        final["element"] = capture_element_at(fx, fy)
                    except Exception:
                        final["element"] = None
                    final_done.set()
                    continue
                # 2) 일시정지 중엔 하이라이트 끔 (클릭은 대상 앱으로 통과)
                if _paused.is_set():
                    _hover_rect = None
                    time.sleep(_HOVER_INTERVAL_S)
                    continue
                # 3) 실시간 hover 샘플링
                try:
                    user32.GetCursorPos(ctypes.byref(wpt))
                    el = capture_element_at(int(wpt.x), int(wpt.y))
                    # rect 는 [l,t,r,b] 리스트 → 프런트가 키 접근하므로 dict 정규화.
                    r = el.get("rect") if el else None
                    if r and len(r) == 4:
                        _hover_rect = {"left": r[0], "top": r[1], "right": r[2], "bottom": r[3]}
                    else:
                        _hover_rect = None
                except Exception:
                    _hover_rect = None
                time.sleep(_HOVER_INTERVAL_S)
        finally:
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass

    def _mouse_proc(n_code, w_param, l_param):
        if n_code == _HC_ACTION and w_param == _WM_LBUTTONDOWN and captured["pt"] is None:
            if _paused.is_set():
                # 일시정지 — 클릭을 통과시켜 사용자가 메뉴를 펼치는 등 조작 가능.
                return user32.CallNextHookEx(None, n_code, w_param, l_param)
            ms = ctypes.cast(l_param, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
            captured["pt"] = (int(ms.pt.x), int(ms.pt.y))
            return 1  # swallow — 선택 클릭이 대상 앱에 전달되지 않게
        if n_code == _HC_ACTION and w_param == _WM_LBUTTONUP and captured["pt"] is not None:
            return 1  # 짝 맞는 up 도 삼킴
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _kbd_proc(n_code, w_param, l_param):
        if n_code == _HC_ACTION and w_param in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
            kb = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            if kb.vkCode == _VK_ESCAPE:
                _cancel.set()
                return 1  # ESC 삼킴
            if kb.vkCode == _VK_F3:
                # F3 토글 — 일시정지/재개 (메뉴 펼친 후 선택용).
                if _paused.is_set():
                    _paused.clear()
                else:
                    _paused.set()
                return 1  # F3 삼킴
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    mouse_cb = hookproc(_mouse_proc)
    kbd_cb = hookproc(_kbd_proc)
    user32.SetWindowsHookExW.restype = ctypes.wintypes.HHOOK
    h_mouse = user32.SetWindowsHookExW(_WH_MOUSE_LL, mouse_cb, None, 0)
    h_kbd = user32.SetWindowsHookExW(_WH_KEYBOARD_LL, kbd_cb, None, 0)

    worker = threading.Thread(target=_uia_worker, name="ohdo-pick-uia", daemon=True)
    worker.start()

    try:
        if not h_mouse:
            return {"success": False, "error": "마우스 훅 설치 실패"}

        from core.app_service import format_element_label

        msg = ctypes.wintypes.MSG()
        start = time.monotonic()
        last_topmost = 0.0
        # ── 후크 스레드: 메시지 펌프만 (UIA 호출 없음 → 항상 즉시 반환, 마우스 비차단) ──
        while True:
            while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):  # PM_REMOVE
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            # 클릭 확정 → 워커에 최종 캡처 요청.
            if captured["pt"] is not None and final["pt"] is None:
                final["pt"] = captured["pt"]
            if final_done.is_set():
                break
            if _cancel.is_set():
                return {"success": False, "cancelled": True}
            now = time.monotonic()
            if now - start > timeout_s:
                return {"success": False, "cancelled": True, "error": "시간 초과"}
            # ── 오버레이를 작업표시줄 위로 강제 (SetWindowPos HWND_TOPMOST 주기 재적용) ──
            # 빠른 호출이라 후크 비차단. (작업표시줄 z-order 는 §49 미해결 — 보류)
            if _overlay_hwnd and now - last_topmost >= _TOPMOST_INTERVAL_S:
                last_topmost = now
                try:
                    user32.SetWindowPos(
                        _overlay_hwnd,
                        _HWND_TOPMOST,
                        0,
                        0,
                        0,
                        0,
                        _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE,
                    )
                except Exception:
                    pass
            time.sleep(0.005)

        x, y = captured["pt"]
        element = final["element"]
        if not element:
            return {
                "success": False,
                "x": x,
                "y": y,
                "error": "해당 위치에서 element 를 찾지 못했습니다.",
            }
        is_browser = bool(element.get("is_browser") or element.get("cdp_used"))
        return {
            "success": True,
            "x": x,
            "y": y,
            "element": element,
            "label": format_element_label(element),
            "is_browser_element": is_browser,
        }
    finally:
        worker_stop.set()
        worker.join(timeout=1.0)
        if h_mouse:
            user32.UnhookWindowsHookEx(h_mouse)
        if h_kbd:
            user32.UnhookWindowsHookEx(h_kbd)
        _hover_rect = None
        _overlay_hwnd = None
        _paused.clear()
        _active.clear()
        _cancel.clear()
        _lock.release()
