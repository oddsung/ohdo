# SPDX-License-Identifier: AGPL-3.0-or-later
"""element picker — 커서 위치 UI element 캡처 (handoff §40 #3, 카운트다운 캡처)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api_server.deps import require_token

router = APIRouter()


class _OverlayHwndRequest(BaseModel):
    """Electron 오버레이 창 HWND 등록 (handoff §49 fix2)."""

    hwnd: int


@router.post("/pick")
def pick_element(request: Request, _: None = Depends(require_token)) -> dict:
    """현재 마우스 커서 위치의 UI element 를 캡처.

    프런트가 카운트다운(예: 3초) 후 호출한다. 사용자는 그 사이 대상 위에 커서를
    올려둔다. 서버가 ``GetCursorPos`` 로 좌표를 읽고 ``capture_element_at`` 로
    element 메타를 측정 → ``format_element_label`` 로 AI prompt 용 컨텍스트 문자열
    까지 만들어 반환한다. (Windows 전용 — 그 외 OS 는 501.)
    """
    import sys as _sys

    if _sys.platform != "win32":
        raise HTTPException(status_code=501, detail="element picker 는 Windows 전용입니다.")

    try:
        import ctypes
        import ctypes.wintypes

        pt = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        x, y = int(pt.x), int(pt.y)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"커서 좌표 읽기 실패: {exc}")

    from core.app_service import format_element_label
    from core.element_inspect import capture_element_at

    element = capture_element_at(x, y)
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


@router.post("/pick/click")
def pick_on_click_route(request: Request, _: None = Depends(require_token)) -> dict:
    """클릭 시 캡처 (handoff §48, 절충안) — 다음 좌클릭의 element 를 캡처.

    카운트다운(/pick) 대신 전역 LL 마우스 후크로 사용자가 대상을 클릭할 때까지 블록한다.
    선택 클릭은 삼켜서 대상 앱이 눌리지 않게 한다. ESC/타임아웃/``/pick/cancel`` 로 취소.
    하이라이트 없음. Windows 전용(그 외 501).
    """
    import sys as _sys

    if _sys.platform != "win32":
        raise HTTPException(status_code=501, detail="element picker 는 Windows 전용입니다.")

    from api_server.pick_pump import pick_on_click

    return pick_on_click()


@router.post("/pick/cancel")
def pick_cancel_route(request: Request, _: None = Depends(require_token)) -> dict:
    """진행 중인 클릭 캡처 취소 (UI Esc/취소 버튼용)."""
    from api_server.pick_pump import cancel_pick

    return {"cancelled": cancel_pick()}


@router.get("/pick/hover")
def pick_hover_route(request: Request, _: None = Depends(require_token)) -> dict:
    """현재 커서 아래 element 의 rect(물리 픽셀) 반환 — 실시간 하이라이트용 (handoff §49).

    클릭 캡처(pick_on_click)가 진행 중일 때만 의미 있는 값. 오버레이가 ~30fps 로 폴링한다.
    UIA 호출은 펌프 스레드에서만 하고 여기선 저장된 값만 읽으므로 빠르다(동시성 안전).
    """
    from api_server.pick_pump import get_hover_rect

    return {"rect": get_hover_rect()}


@router.post("/pick/overlay")
def pick_overlay_route(
    body: _OverlayHwndRequest, request: Request, _: None = Depends(require_token)
) -> dict:
    """Electron 오버레이 창 HWND 등록 (handoff §49 fix2).

    펌프 루프가 이 HWND 를 SetWindowPos(HWND_TOPMOST) 로 주기 재적용해 작업표시줄 위로
    z-order 를 강제한다(Electron setAlwaysOnTop 은 Shell_TrayWnd 를 못 이김).
    """
    from api_server.pick_pump import set_overlay_hwnd

    set_overlay_hwnd(body.hwnd)
    return {"ok": True}
