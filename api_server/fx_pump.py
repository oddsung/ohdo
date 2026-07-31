# SPDX-License-Identifier: AGPL-3.0-or-later
"""실행 중 시각 효과용 **관찰 전용** 전역 마우스 훅 (handoff §79).

전체 실행 동안 클릭 좌표를 기록만 한다 — pick_pump(§48)와 같은 LL 훅/펌프 구조지만
**클릭을 절대 삼키지 않는다**(항상 CallNextHookEx 즉시 통과). Electron run 오버레이가
``GET /fx/clicks`` 를 폴링해 클릭 리플을 그린다. 커서 위치는 Electron 이 자체 폴링
(``screen.getCursorScreenPoint``)하므로 여기선 클릭 이벤트만 다룬다.

§42/§49 의 검증된 제약을 그대로 따른다:
- LL 훅은 SetWindowsHookEx 를 호출한 스레드에서 메시지 펌프가 돌아야 발화 → 전용
  데몬 스레드에서 설치+PeekMessage 펌프.
- CallNextHookEx argtypes 명시(§49 fix9 — 미지정 시 x64 lParam OverflowError 로
  마우스 전체 정지).
- 훅 콜백은 초경량(좌표 기록만) — UIA/COM 호출 금지.

core/ 무수정. 비-Windows 에선 start 가 조용히 실패(효과 없음)한다.
"""

from __future__ import annotations

import itertools
import sys
import threading
import time
from collections import deque

_WH_MOUSE_LL = 14
_WM_LBUTTONDOWN = 0x0201
_WM_RBUTTONDOWN = 0x0204
_WM_MBUTTONDOWN = 0x0207
_HC_ACTION = 0

_BUTTON_BY_MSG = {_WM_LBUTTONDOWN: "left", _WM_RBUTTONDOWN: "right", _WM_MBUTTONDOWN: "middle"}

_MAX_EVENTS = 256  # ring buffer — 폴링이 밀려도 무한 증식 방지

_lock = threading.Lock()
_stop_evt = threading.Event()
_thread: "threading.Thread | None" = None
_seq = itertools.count(1)
_clicks: "deque[dict]" = deque(maxlen=_MAX_EVENTS)


def _record_click(x: int, y: int, button: str) -> None:
    """클릭 1건 기록 (훅 콜백/테스트에서 호출 — 초경량)."""
    _clicks.append(
        {"seq": next(_seq), "x": int(x), "y": int(y), "button": button, "t": time.time()}
    )


def get_clicks(since: int = 0) -> dict:
    """``since`` 이후의 클릭 이벤트 반환 — {"seq": <마지막>, "clicks": [...]}.

    폴링 계약: 호출자는 응답의 ``seq`` 를 저장해 다음 폴링의 ``since`` 로 넘긴다.
    이벤트가 없으면 clicks=[] + seq=since 그대로.
    """
    items = [c for c in list(_clicks) if c["seq"] > since]
    last = items[-1]["seq"] if items else since
    return {"seq": last, "clicks": items}


def is_fx_active() -> bool:
    """관찰 훅이 동작 중인가."""
    return _thread is not None and _thread.is_alive()


def start_fx() -> bool:
    """관찰 훅 시작 (idempotent). Windows 가 아니거나 설치 실패면 False."""
    global _thread
    if sys.platform != "win32":
        return False
    with _lock:
        if is_fx_active():
            return True
        _stop_evt.clear()
        _clicks.clear()
        ready: dict = {"ok": None}
        t = threading.Thread(target=_pump, args=(ready,), name="ohdo-fx-pump", daemon=True)
        t.start()
        # 훅 설치 성공/실패 확인 (짧은 대기 — 펌프 스레드가 ready 를 채움).
        deadline = time.monotonic() + 2.0
        while ready["ok"] is None and time.monotonic() < deadline:
            time.sleep(0.01)
        if ready["ok"]:
            _thread = t
            return True
        _stop_evt.set()
        return False


def stop_fx() -> bool:
    """관찰 훅 중지 (idempotent). 반환: 실제로 동작 중이었는지."""
    global _thread
    with _lock:
        was_active = is_fx_active()
        _stop_evt.set()
        if _thread is not None:
            _thread.join(timeout=2.0)
            _thread = None
        return was_active


def _pump(ready: dict) -> None:
    """전용 스레드 — LL 훅 설치 + 메시지 펌프. 클릭은 기록만 하고 항상 통과."""
    import ctypes
    import ctypes.wintypes

    user32 = ctypes.windll.user32
    lresult = ctypes.c_ssize_t
    hookproc = ctypes.WINFUNCTYPE(
        lresult, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM
    )
    try:
        user32.CallNextHookEx.argtypes = [
            ctypes.wintypes.HHOOK,
            ctypes.c_int,
            ctypes.wintypes.WPARAM,
            ctypes.wintypes.LPARAM,
        ]
        user32.CallNextHookEx.restype = lresult
    except Exception:
        pass

    class _MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("pt", ctypes.wintypes.POINT),
            ("mouseData", ctypes.wintypes.DWORD),
            ("flags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.wintypes.WPARAM),
        ]

    def _mouse_proc(n_code, w_param, l_param):
        if n_code == _HC_ACTION and w_param in _BUTTON_BY_MSG:
            try:
                ms = ctypes.cast(l_param, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
                _record_click(ms.pt.x, ms.pt.y, _BUTTON_BY_MSG[int(w_param)])
            except Exception:
                pass
        # 관찰 전용 — 어떤 이벤트도 삼키지 않는다.
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    cb = hookproc(_mouse_proc)
    user32.SetWindowsHookExW.restype = ctypes.wintypes.HHOOK
    h = user32.SetWindowsHookExW(_WH_MOUSE_LL, cb, None, 0)
    ready["ok"] = bool(h)
    if not h:
        return
    try:
        msg = ctypes.wintypes.MSG()
        while not _stop_evt.is_set():
            while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.01)
    finally:
        user32.UnhookWindowsHookEx(h)
