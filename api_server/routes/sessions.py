# SPDX-License-Identifier: AGPL-3.0-or-later
"""세션 CRUD + AI 생성 (handoff §38/§39/§40)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from api_server.deps import (
    CreateSessionRequest,
    GenerateRequest,
    RenameSessionRequest,
    drop_kernel,
    get_app_service,
    require_token,
    to_dict,
)

router = APIRouter()


@router.get("/sessions")
def list_sessions(request: Request, _: None = Depends(require_token)) -> dict:
    """세션 목록 반환 — ``AppService.list_sessions`` 위임."""
    service = get_app_service(request.app)
    sessions = [to_dict(s) for s in service.list_sessions()]
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request, _: None = Depends(require_token)) -> dict:
    """세션 상세 (steps 포함) 반환 — ``AppService.get_session`` 위임."""
    service = get_app_service(request.app)
    try:
        session = service.get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    return {"session": to_dict(session)}


@router.post("/sessions")
def create_session(
    body: CreateSessionRequest, request: Request, _: None = Depends(require_token)
) -> dict:
    """새 세션 생성 — ``AppService.create_session`` 위임."""
    service = get_app_service(request.app)
    session = service.create_session(
        title=body.title,
        project_type=body.project_type,
        description=body.description,
    )
    return {"session": to_dict(session)}


@router.patch("/sessions/{session_id}")
def rename_session(
    session_id: str,
    body: RenameSessionRequest,
    request: Request,
    _: None = Depends(require_token),
) -> dict:
    """세션 이름변경 (handoff §47 백로그 #9) — title 만 갱신 후 ``save_session``."""
    service = get_app_service(request.app)
    try:
        session = service.get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title 이 비어 있습니다.")
    session.title = title
    service.save_session(session)
    return {"success": True, "session": to_dict(service.get_session(session_id))}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, request: Request, _: None = Depends(require_token)) -> dict:
    """세션 삭제 (handoff §47 백로그 #8) — ``AppService.delete_session`` 위임.

    캐시된 kernel 도 함께 정리한다.
    """
    app = request.app
    service = get_app_service(app)
    try:
        service.get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    service.delete_session(session_id)
    drop_kernel(app, session_id)
    return {"success": True, "session_id": session_id}


@router.post("/sessions/{session_id}/generate")
async def generate(
    session_id: str, body: GenerateRequest, request: Request, _: None = Depends(require_token)
) -> dict:
    """자연어 요청 → AI 코드 생성 → step 추가.

    ``AppService.generate_step`` 위임 (async). AI 엔진 미구성 시 503,
    세션 없으면 404, AI 응답 실패 시 success=False + error 반환.
    """
    service = get_app_service(request.app)
    if service.ai_manager is None:
        raise HTTPException(
            status_code=503,
            detail="AI 엔진이 구성되지 않았습니다 (config/settings.json 의 ai 섹션 확인).",
        )
    try:
        session = service.get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")

    step, response = await service.generate_step(
        session=session,
        user_request=body.user_request,
        prompt_builder=service.prompt_builder,
        element_context=body.element_context,
        is_browser_element=body.is_browser_element,
    )

    if step is None or not response.success:
        return {
            "success": False,
            "error": response.error or "AI 응답 실패",
            "partial": getattr(response, "partial", False),
        }

    # step 은 generate_step 내부에서 이미 session 에 추가+저장됨.
    # 갱신된 세션 상세를 함께 반환해 renderer 가 즉시 반영하도록.
    fresh = service.get_session(session_id)
    return {
        "success": True,
        "step": to_dict(step),
        "session": to_dict(fresh),
        "description": response.description or "",
    }
