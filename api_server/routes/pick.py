# SPDX-License-Identifier: AGPL-3.0-or-later
"""element picker — 커서 위치 UI element 캡처 (handoff §40 #3, 카운트다운 캡처)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api_server.deps import get_app_service, require_token, session_captures_dir

logger = logging.getLogger(__name__)

router = APIRouter()


class _OverlayHwndRequest(BaseModel):
    """Electron 오버레이 창 HWND 등록 (handoff §49 fix2)."""

    hwnd: int


class PickClickRequest(BaseModel):
    """클릭 캡처 요청 — session_id 가 있으면 선택 요소의 스크린샷도 그 세션 captures 에 저장.

    session_id 가 None 이면 메타만 캡처(이미지 없음, §48 동작 그대로).
    """

    session_id: str | None = None


def _capture_element_image(app, session_id: str, result: dict) -> None:
    """선택된 요소의 rect(물리 픽셀) 영역을 스크린샷으로 grab → 세션 captures 에 저장.

    핸들러 스레드에서 호출 — 이 시점 메인 윈도우는 아직 minimize 상태(대상 가시)라
    grab 이 대상 요소를 잡는다. best-effort: 실패해도 pick 자체는 성공으로 둔다.
    AI 에는 전송하지 않고(이미지 channel 미경유) **표시 전용** — 생성된 step 에 별도
    attach 엔드포인트로 붙는다 (handoff §66).
    """
    element = result.get("element") or {}
    rect = element.get("rect")
    if not (isinstance(rect, (list, tuple)) and len(rect) == 4):
        return
    left, top, right, bottom = (int(v) for v in rect)
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0:
        return
    captures_dir = session_captures_dir(get_app_service(app), session_id)
    if captures_dir is None:
        return
    from api_server.capture_pump import capture_region

    cap = capture_region(captures_dir, left, top, w, h)
    if cap.get("success"):
        result["image"] = cap["path"]  # 절대 경로(§60 captures 형식과 동일)


def _build_element_context(element: dict) -> "str | None":
    """선택 요소 메타 → AI 프롬프트용 풍부한 "## 선택된 UI 요소" 컨텍스트 (handoff §67, v2 동등).

    core 의 공개 ``WindowInspector.get_element_info_text`` 재사용(core 0줄) — 프롬프트 가이드
    #17 이 "그대로 시작 코드로 사용"하라고 가리키는 **구조화 섹션 + 코드 템플릿**을 생성한다.
    이게 없으면(이전 v3) element_context 가 한 줄 라벨뿐이라 AI 가 가이드의 폴백 예시
    (control_type="Document")를 복제하는 약한 타겟팅이 됐다.

    ``capture_element_at`` 의 rect 는 ``[l,t,r,b]`` 리스트지만 get_element_info_text 는
    ``{left,top,width,height}`` dict 를 기대하므로 정규화(원본 element 는 안 건드림). best-effort.
    """
    try:
        from core.win_inspector import WindowInspector

        info = dict(element)
        r = info.get("rect")
        if isinstance(r, (list, tuple)) and len(r) == 4:
            left, top, right, bottom = (int(v) for v in r)
            info["rect"] = {"left": left, "top": top, "width": right - left, "height": bottom - top}
        text = WindowInspector().get_element_info_text(info)
        return text or None
    except Exception:
        logger.debug("element_context 구성 실패 (무시 — 한 줄 라벨로 폴백)", exc_info=True)
        return None


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
def pick_on_click_route(
    request: Request,
    body: PickClickRequest | None = None,
    _: None = Depends(require_token),
) -> dict:
    """클릭 시 캡처 (handoff §48, 절충안) — 다음 좌클릭의 element 를 캡처.

    카운트다운(/pick) 대신 전역 LL 마우스 후크로 사용자가 대상을 클릭할 때까지 블록한다.
    선택 클릭은 삼켜서 대상 앱이 눌리지 않게 한다. ESC/타임아웃/``/pick/cancel`` 로 취소.
    하이라이트 없음. Windows 전용(그 외 501).

    ``session_id`` 가 주어지면 선택 요소의 rect 스크린샷도 그 세션 captures 에 저장하고
    ``image`` 경로를 결과에 포함한다(표시 전용, handoff §66).
    """
    import sys as _sys

    if _sys.platform != "win32":
        raise HTTPException(status_code=501, detail="element picker 는 Windows 전용입니다.")

    from api_server.pick_pump import pick_on_click

    result = pick_on_click()
    session_id = body.session_id if body else None
    if result.get("success"):
        # 풍부한 element_context (v2 동등, §67) — AI 가 선택 요소를 정확히 타겟하도록.
        ctx = _build_element_context(result.get("element") or {})
        if ctx:
            result["element_context"] = ctx
        # 표시용 요소 스크린샷 (§66) — session_id 줬을 때만.
        if session_id:
            try:
                _capture_element_image(request.app, session_id, result)
            except Exception:
                logger.debug("요소 스크린샷 캡처 실패 (무시)", exc_info=True)
    return result


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
    from api_server.pick_pump import get_hover_rect, is_paused

    return {"rect": get_hover_rect(), "paused": is_paused()}


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
