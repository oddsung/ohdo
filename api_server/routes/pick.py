# SPDX-License-Identifier: AGPL-3.0-or-later
"""element picker — 커서 위치 UI element 캡처 (handoff §40 #3, 카운트다운 캡처)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from api_server.deps import require_token

router = APIRouter()


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
