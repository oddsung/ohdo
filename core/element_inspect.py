# SPDX-License-Identifier: AGPL-3.0-or-later
"""작업 녹화용 가벼운 element 캡처 — (x, y) → element_meta dict.

[ADR 0004 PR-16a] Recorder 의 ``element_capture_fn`` 으로 주입되는 함수.
``ui/element_picker.py`` 의 full pipeline 과 달리 UI overlay / signal /
hierarchy / 브라우저 CDP 까지 안 들어감 — recorder_transform 이 필요한 minimal
필드만 채워서 빠르게 반환한다.

PR-13/15 의 ``recorder_transform`` 이 소비하는 필드:
- ``control_type``, ``name``, ``automation_id``, ``class_name``
- ``window_title``, ``hwnd``, ``process_id``, ``exe_name``
- ``rect``
- ``is_password_field`` (ADR 0003 PW 필드 변환 강 통합)

브라우저 element (css_selector / xpath / tag_name) 는 R3 / PR-17 (async CDP)
에서 추가. PR-16a 는 desktop subset 만.

**스레드 안전**: 모든 호출 독립 (모듈 전역 상태 X). pywinauto/COM 의 thread
요구는 호출자 (LL hook callback thread) 의 책임. 호출 비용은 ~50~200ms 평균,
극단 lazy a11y 트리는 더 느릴 수 있음 — 그 경우 PR-17 의 async EFP 로 마이그레이션.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

logger = logging.getLogger(__name__)


__all__ = ["capture_element_at"]


# 모듈 import 비용 절감 — non-Windows / pywinauto 미설치 환경 동작 보장
_IUIA = None
_UIAWrapper = None
_UIAElementInfo = None
_user32 = None


def _ensure_initialized() -> bool:
    """pywinauto + ctypes 초기화 (지연 import). 실패 시 False."""
    global _IUIA, _UIAWrapper, _UIAElementInfo, _user32

    if sys.platform != "win32":
        return False

    if _IUIA is not None:
        return True

    try:
        import ctypes

        from pywinauto.controls.uiawrapper import UIAWrapper
        from pywinauto.uia_defines import IUIA
        from pywinauto.uia_element_info import UIAElementInfo

        _IUIA = IUIA
        _UIAWrapper = UIAWrapper
        _UIAElementInfo = UIAElementInfo
        _user32 = ctypes.windll.user32
        return True
    except Exception:  # noqa: BLE001
        logger.exception("element_inspect: pywinauto 초기화 실패 (capture_element_at 비활성)")
        return False


def capture_element_at(x: int, y: int) -> Optional[dict]:
    """클릭 좌표 → element 메타 dict (best-effort, 모든 예외 격리).

    Returns:
        dict 또는 None. None 일 때 recorder_transform 은 자동으로
        ``pyautogui.click(x, y)`` 좌표 fallback 으로 코드 생성.

    채워지는 필드 (모두 Optional):
        control_type, name, automation_id, class_name,
        window_title, hwnd, process_id, exe_name, rect,
        is_password_field

    Returns dict 가 ``recorder_transform._same_element`` 가 사용하는
    (automation_id, name, control_type) 키를 항상 채우려 노력 — 이래야 PR-13
    의 "동일 element 연속 키입력 group" 휴리스틱이 동작.
    """
    if not _ensure_initialized():
        return None

    try:
        import ctypes

        pt = ctypes.wintypes.POINT(int(x), int(y))
        iuia = _IUIA().iuia
        elem_com = iuia.ElementFromPoint(pt)
        if not elem_com:
            return None

        info = _UIAElementInfo(elem_com)
        wrapper = _UIAWrapper(info)
    except Exception:
        logger.debug("capture_element_at EFP 실패 (%s, %s)", x, y, exc_info=True)
        return None

    meta: dict = {}

    # 기본 필드
    meta["control_type"] = _safe_str(lambda: wrapper.element_info.control_type)
    meta["name"] = _safe_str(lambda: wrapper.window_text(), max_len=120)
    meta["automation_id"] = _safe_str(lambda: wrapper.element_info.automation_id)
    meta["class_name"] = _safe_str(lambda: wrapper.class_name())

    # 좌표
    try:
        r = wrapper.rectangle()
        meta["rect"] = [int(r.left), int(r.top), int(r.right), int(r.bottom)]
    except Exception:
        meta["rect"] = None

    # HWND / process
    try:
        h = wrapper.handle
        meta["hwnd"] = int(h) if h else None
    except Exception:
        meta["hwnd"] = None
    try:
        meta["process_id"] = int(wrapper.process_id()) or None
    except Exception:
        meta["process_id"] = None

    # 최상위 window_title — UIA tree 를 따라 부모로 올라가서 top-level 의 window_text
    try:
        meta["window_title"] = _resolve_top_window_title(wrapper)
    except Exception:
        meta["window_title"] = None

    # exe_name (process_id → 이미지 이름)
    if meta.get("process_id"):
        try:
            meta["exe_name"] = _resolve_exe_name(meta["process_id"])
        except Exception:
            meta["exe_name"] = None

    # is_password_field — UIA IsPassword + heuristic fallback (class/auto_id 'password')
    meta["is_password_field"] = _detect_is_password(wrapper, meta)

    return meta


# ── 내부 helper ──────────────────────────────────────────


def _safe_str(fn, max_len: Optional[int] = None) -> Optional[str]:
    try:
        v = fn()
    except Exception:
        return None
    if v is None:
        return None
    s = str(v)
    return s[:max_len] if max_len else s


def _resolve_top_window_title(wrapper) -> Optional[str]:
    """element 의 최상위 window_text 를 따라간다. 무한 루프 방지."""
    cur = wrapper
    visited: set[int] = set()
    last_text: Optional[str] = None
    while cur is not None:
        try:
            h = getattr(cur, "handle", None)
            if h:
                if h in visited:
                    break
                visited.add(int(h))
            txt = cur.window_text() if hasattr(cur, "window_text") else None
            if txt:
                last_text = txt
            parent = cur.parent()
            if parent is None or parent is cur:
                break
            cur = parent
        except Exception:
            break
    return last_text


def _resolve_exe_name(pid: int) -> Optional[str]:
    """PID → 이미지 파일명 (basename 만). 실패 시 None."""
    try:
        import ctypes
        import ctypes.wintypes as wt

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return None
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = wt.DWORD(260)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                full_path = buf.value
                # basename only — 보안상 절대 경로 노출 안 함
                idx = max(full_path.rfind("\\"), full_path.rfind("/"))
                return full_path[idx + 1 :] if idx >= 0 else full_path
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None
    return None


def _detect_is_password(wrapper, meta: dict) -> bool:
    """UIA IsPassword 직접 + heuristic fallback."""
    # 1) UIA IsPassword (가장 정확)
    try:
        elem = wrapper.element_info._element  # COM 래퍼의 IUIAutomationElement
        # CurrentIsPassword 는 BOOL property. 일부 컨트롤은 미지원 → 예외.
        val = getattr(elem, "CurrentIsPassword", None)
        if val:
            return True
    except Exception:
        pass

    # 2) 휴리스틱 — automation_id / class_name 에 'password' / 'pwd'
    auto_id = (meta.get("automation_id") or "").lower()
    cls = (meta.get("class_name") or "").lower()
    if (
        "password" in auto_id
        or "pwd" in auto_id
        or "password" in cls
        or "edit" in (meta.get("control_type") or "").lower()
        and ("pwd" in auto_id or "password" in cls)
    ):
        return True

    return False
