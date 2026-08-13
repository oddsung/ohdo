# SPDX-License-Identifier: AGPL-3.0-or-later
"""스크린 영역 캡처 (handoff §60, 백로그 #13) — 드래그 영역을 grab 해 세션 captures 에 저장.

Electron 캡처 오버레이가 드래그로 확정한 **물리 픽셀** 사각형을 받아 ``capture_pump`` 로
grab → 저장 경로를 반환한다. 그 경로는 generate(``images``)로 넘겨 core 가 step.captures +
AI 프롬프트에 첨부한다. core 0줄 — 저장 위치는 공개 ``get_captures_dir`` 사용.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api_server.deps import get_app_service, require_token

router = APIRouter()


class CaptureRegionRequest(BaseModel):
    """드래그한 캡처 영역(물리 픽셀, 가상 데스크톱 좌표). main 이 DIP→물리 변환해 보낸다."""

    session_id: str
    left: int
    top: int
    width: int
    height: int


def _captures_dir(service, session_id: str) -> Path | None:
    """세션 captures 폴더 경로 — 공개 SessionManager.get_captures_dir 위임(core 0줄).

    파일 기반 저장소가 아니면(manager 없음) None.
    """
    manager = getattr(getattr(service, "_repo", None), "manager", None)
    if manager is None or not hasattr(manager, "get_captures_dir"):
        return None
    return manager.get_captures_dir(session_id)


@router.post("/capture/region")
def capture_region_route(
    body: CaptureRegionRequest, request: Request, _: None = Depends(require_token)
) -> dict:
    """드래그한 영역을 grab → 세션 captures 에 PNG 저장 → 경로 반환.

    Windows 전용(mss 는 타 OS 도 되지만 v3 는 Windows 자동화 대상). 세션 없으면 404,
    저장소가 파일 기반이 아니면 501, grab 실패는 success=False.
    """
    service = get_app_service(request.app)
    try:
        service.get_session(body.session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"session not found: {body.session_id}")

    captures_dir = _captures_dir(service, body.session_id)
    if captures_dir is None:
        raise HTTPException(
            status_code=501, detail="파일 기반 저장소가 아니라 캡처를 저장할 수 없습니다."
        )

    from api_server.capture_pump import capture_region

    result = capture_region(captures_dir, body.left, body.top, body.width, body.height)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "캡처 실패"))
    return result
