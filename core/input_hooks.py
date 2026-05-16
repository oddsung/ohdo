# SPDX-License-Identifier: AGPL-3.0-or-later
"""LL hook (WH_MOUSE_LL / WH_KEYBOARD_LL) 통합 관리 — multi-callback dispatch.

[ADR 0004] 작업 녹화 (Action Recording) 기능을 위해 여러 callback 이 동일
hook 을 공유할 수 있도록 한다. callback 한 개라도 True 반환 시 이벤트 차단.
모든 callback 해제 시 hook 자동 제거.

element_picker 의 inline hook 코드는 별도 — Phase R2/R3 에서 점진 통합 예정
([architecture/25-recording-phase-r1-r2.md] PR-11 §"설계 결정" 참조).

non-Windows 환경에서는 install/uninstall 모두 silent noop.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import time
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Literal, Optional

logger = logging.getLogger(__name__)


WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105


MouseEventType = Literal[
    "move",
    "lbutton_down",
    "lbutton_up",
    "rbutton_down",
    "rbutton_up",
    "mbutton_down",
    "mbutton_up",
    "wheel",
]

KeyboardEventType = Literal["keydown", "keyup", "syskeydown", "syskeyup"]


@dataclass
class MouseEvent:
    """LL hook 으로 들어온 마우스 이벤트."""

    type: MouseEventType
    x: int
    y: int
    wheel_delta: int = 0
    timestamp_ms: int = 0


@dataclass
class KeyboardEvent:
    """LL hook 으로 들어온 키보드 이벤트."""

    type: KeyboardEventType
    vk_code: int
    scan_code: int
    timestamp_ms: int = 0


MouseCallback = Callable[[MouseEvent], bool]
KeyboardCallback = Callable[[KeyboardEvent], bool]


class InputHookManager:
    """단일 instance 가 WH_MOUSE_LL / WH_KEYBOARD_LL 설치 + multi-callback dispatch.

    여러 callback 등록 가능. 한 callback 이라도 True 반환하면 이벤트 차단
    (CallNextHookEx 호출 안 함). 모든 callback 해제 시 hook 자동 해제.

    callback 안에서 예외 발생해도 다른 callback dispatch 에 영향 없음
    (try/except 로 격리).

    callback 안에서 직접 unregister 호출해도 안전 (snapshot 기반 dispatch).

    non-Windows 환경에서는 install/uninstall 이 silent noop. is_*_hook_installed
    는 항상 False 반환.
    """

    def __init__(self) -> None:
        self._mouse_callbacks: dict[int, MouseCallback] = {}
        self._keyboard_callbacks: dict[int, KeyboardCallback] = {}
        self._next_id = 1
        self._lock = Lock()

        self._mouse_hook: Optional[int] = None
        self._keyboard_hook: Optional[int] = None

        self._mouse_proc_ref = None
        self._keyboard_proc_ref = None

        if sys.platform == "win32":
            self._user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        else:
            self._user32 = None

    def install_mouse_callback(self, callback: MouseCallback) -> int:
        """callback 등록 + (필요 시) hook 설치. 등록 ID 반환."""
        with self._lock:
            cb_id = self._next_id
            self._next_id += 1
            self._mouse_callbacks[cb_id] = callback
            if self._mouse_hook is None:
                self._install_mouse_hook_locked()
            return cb_id

    def install_keyboard_callback(self, callback: KeyboardCallback) -> int:
        """callback 등록 + (필요 시) hook 설치. 등록 ID 반환."""
        with self._lock:
            cb_id = self._next_id
            self._next_id += 1
            self._keyboard_callbacks[cb_id] = callback
            if self._keyboard_hook is None:
                self._install_keyboard_hook_locked()
            return cb_id

    def uninstall_mouse_callback(self, cb_id: int) -> None:
        """callback 해제. 마지막 callback 해제 시 hook 자동 제거."""
        with self._lock:
            self._mouse_callbacks.pop(cb_id, None)
            if not self._mouse_callbacks and self._mouse_hook is not None:
                self._uninstall_mouse_hook_locked()

    def uninstall_keyboard_callback(self, cb_id: int) -> None:
        with self._lock:
            self._keyboard_callbacks.pop(cb_id, None)
            if not self._keyboard_callbacks and self._keyboard_hook is not None:
                self._uninstall_keyboard_hook_locked()

    def uninstall_all(self) -> None:
        """모든 callback + hook 해제."""
        with self._lock:
            self._mouse_callbacks.clear()
            self._keyboard_callbacks.clear()
            if self._mouse_hook is not None:
                self._uninstall_mouse_hook_locked()
            if self._keyboard_hook is not None:
                self._uninstall_keyboard_hook_locked()

    @property
    def is_mouse_hook_installed(self) -> bool:
        return self._mouse_hook is not None

    @property
    def is_keyboard_hook_installed(self) -> bool:
        return self._keyboard_hook is not None

    @property
    def mouse_callback_count(self) -> int:
        return len(self._mouse_callbacks)

    @property
    def keyboard_callback_count(self) -> int:
        return len(self._keyboard_callbacks)

    def _install_mouse_hook_locked(self) -> None:
        if self._user32 is None:
            return

        HOOKPROC = ctypes.CFUNCTYPE(
            ctypes.c_long,
            ctypes.c_int,
            ctypes.c_ulonglong,
            ctypes.c_ulonglong,
        )

        def _proc(nCode, wParam, lParam):
            return self._mouse_hook_dispatch(nCode, wParam, lParam)

        self._mouse_proc_ref = HOOKPROC(_proc)
        handle = self._user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc_ref, None, 0)
        if not handle:
            logger.warning("InputHookManager: WH_MOUSE_LL 설치 실패")
            self._mouse_proc_ref = None
        else:
            self._mouse_hook = handle

    def _install_keyboard_hook_locked(self) -> None:
        if self._user32 is None:
            return

        HOOKPROC = ctypes.CFUNCTYPE(
            ctypes.c_long,
            ctypes.c_int,
            ctypes.c_ulonglong,
            ctypes.c_ulonglong,
        )

        def _proc(nCode, wParam, lParam):
            return self._keyboard_hook_dispatch(nCode, wParam, lParam)

        self._keyboard_proc_ref = HOOKPROC(_proc)
        handle = self._user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._keyboard_proc_ref, None, 0)
        if not handle:
            logger.warning("InputHookManager: WH_KEYBOARD_LL 설치 실패")
            self._keyboard_proc_ref = None
        else:
            self._keyboard_hook = handle

    def _uninstall_mouse_hook_locked(self) -> None:
        if self._user32 is not None and self._mouse_hook:
            self._user32.UnhookWindowsHookEx(self._mouse_hook)
        self._mouse_hook = None
        self._mouse_proc_ref = None

    def _uninstall_keyboard_hook_locked(self) -> None:
        if self._user32 is not None and self._keyboard_hook:
            self._user32.UnhookWindowsHookEx(self._keyboard_hook)
        self._keyboard_hook = None
        self._keyboard_proc_ref = None

    def _mouse_hook_dispatch(self, nCode, wParam, lParam) -> int:
        if self._user32 is None:
            return 0
        if nCode < 0:
            return self._user32.CallNextHookEx(None, nCode, wParam, lParam)

        try:
            point = ctypes.cast(lParam, ctypes.POINTER(ctypes.c_long * 4))[0]
            x, y = point[0], point[1]
            mouse_data_raw = point[2]
        except Exception:
            x, y, mouse_data_raw = 0, 0, 0

        event_type = self._wparam_to_mouse_type(wParam)
        if event_type is None:
            return self._user32.CallNextHookEx(None, nCode, wParam, lParam)

        wheel_delta = 0
        if event_type == "wheel":
            mouse_data_unsigned = mouse_data_raw & 0xFFFFFFFF
            wheel_delta = (mouse_data_unsigned >> 16) & 0xFFFF
            if wheel_delta >= 0x8000:
                wheel_delta -= 0x10000

        event = MouseEvent(
            type=event_type,
            x=x,
            y=y,
            wheel_delta=wheel_delta,
            timestamp_ms=int(time.time() * 1000),
        )

        callbacks = list(self._mouse_callbacks.values())
        block = False
        for cb in callbacks:
            try:
                if cb(event):
                    block = True
            except Exception:
                logger.exception("InputHookManager: mouse callback 예외 (격리됨)")

        if block:
            return 1
        return self._user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _keyboard_hook_dispatch(self, nCode, wParam, lParam) -> int:
        if self._user32 is None:
            return 0
        if nCode < 0:
            return self._user32.CallNextHookEx(None, nCode, wParam, lParam)

        try:
            kbd = ctypes.cast(lParam, ctypes.POINTER(ctypes.c_ulong * 2))[0]
            vk_code = kbd[0]
            scan_code = kbd[1]
        except Exception:
            vk_code, scan_code = 0, 0

        event_type = self._wparam_to_keyboard_type(wParam)
        if event_type is None:
            return self._user32.CallNextHookEx(None, nCode, wParam, lParam)

        event = KeyboardEvent(
            type=event_type,
            vk_code=vk_code,
            scan_code=scan_code,
            timestamp_ms=int(time.time() * 1000),
        )

        callbacks = list(self._keyboard_callbacks.values())
        block = False
        for cb in callbacks:
            try:
                if cb(event):
                    block = True
            except Exception:
                logger.exception("InputHookManager: keyboard callback 예외 (격리됨)")

        if block:
            return 1
        return self._user32.CallNextHookEx(None, nCode, wParam, lParam)

    @staticmethod
    def _wparam_to_mouse_type(wParam) -> Optional[MouseEventType]:
        return {
            WM_MOUSEMOVE: "move",
            WM_LBUTTONDOWN: "lbutton_down",
            WM_LBUTTONUP: "lbutton_up",
            WM_RBUTTONDOWN: "rbutton_down",
            WM_RBUTTONUP: "rbutton_up",
            WM_MBUTTONDOWN: "mbutton_down",
            WM_MBUTTONUP: "mbutton_up",
            WM_MOUSEWHEEL: "wheel",
        }.get(wParam)

    @staticmethod
    def _wparam_to_keyboard_type(wParam) -> Optional[KeyboardEventType]:
        return {
            WM_KEYDOWN: "keydown",
            WM_KEYUP: "keyup",
            WM_SYSKEYDOWN: "syskeydown",
            WM_SYSKEYUP: "syskeyup",
        }.get(wParam)


_singleton: Optional[InputHookManager] = None


def get_hook_manager() -> InputHookManager:
    """모듈 레벨 싱글톤 반환. recorder + 향후 element_picker 통합 시 공유."""
    global _singleton
    if _singleton is None:
        _singleton = InputHookManager()
    return _singleton
