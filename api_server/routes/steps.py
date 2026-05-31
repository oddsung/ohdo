# SPDX-License-Identifier: AGPL-3.0-or-later
"""step 편집 저장 (handoff §40 #2 — Monaco 편집)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api_server.deps import (
    InsertStepRequest,
    MoveStepRequest,
    RegenerateRequest,
    UpdateStepRequest,
    drop_kernel,
    get_app_service,
    require_token,
    to_dict,
)


class AttachCaptureRequest(BaseModel):
    """step 에 캡처 이미지 경로 첨부 (handoff §66). path = 절대경로(§60 captures 형식)."""

    path: str


def _step_field(step, name: str):
    return step.get(name) if isinstance(step, dict) else getattr(step, name, None)


def _find_step(session, step_id: int):
    for s in session.steps:
        if _step_field(s, "step_id") == step_id:
            return s
    return None


def _has_step(session, step_id: int) -> bool:
    return _find_step(session, step_id) is not None


router = APIRouter()


@router.put("/sessions/{session_id}/steps/{step_id}")
def update_step(
    session_id: str,
    step_id: int,
    body: UpdateStepRequest,
    request: Request,
    _: None = Depends(require_token),
) -> dict:
    """step 코드 편집 저장 — ``AppService.update_step`` 위임.

    Monaco 편집 결과(generated_code)를 저장한다. step_code 도 함께 갱신해
    실행(run_blocks) 시 편집 내용이 반영되도록 한다. 갱신된 세션을 반환.
    """
    app = request.app
    service = get_app_service(app)
    try:
        session = service.get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")

    if not _has_step(session, step_id):
        raise HTTPException(status_code=404, detail=f"step not found: {step_id}")

    # generated_code 전체를 수동 편집으로 간주 — step_code(실행 delta)도 동일 코드로
    # 맞춰 workflow_engine 이 manually_edited 우선순위로 이 코드를 실행하게 한다.
    service.update_step(
        session_id,
        step_id,
        {
            "generated_code": body.generated_code,
            "step_code": body.generated_code,
            "manually_edited": True,
        },
    )
    # 편집 후 캐시된 kernel 은 stale — 다음 실행이 새 코드 반영하도록 폐기.
    drop_kernel(app, session_id)
    return {"success": True, "session": to_dict(service.get_session(session_id))}


@router.post("/sessions/{session_id}/steps/{step_id}/capture")
def attach_step_capture(
    session_id: str,
    step_id: int,
    body: AttachCaptureRequest,
    request: Request,
    _: None = Depends(require_token),
) -> dict:
    """생성된 step 에 캡처 이미지 경로를 첨부 (handoff §66 — 요소 스크린샷 표시 전용).

    pick 시 잡아 둔 요소 스크린샷 경로를 ``step.captures`` 에 병합 저장한다. **AI 에는
    전송하지 않음**(generate 의 images channel 미경유) — 순수 표시용. ``update_step`` 위임
    이라 core 0줄. 중복 경로는 무시.
    """
    service = get_app_service(request.app)
    try:
        session = service.get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")

    step = _find_step(session, step_id)
    if step is None:
        raise HTTPException(status_code=404, detail=f"step not found: {step_id}")

    existing = list(_step_field(step, "captures") or [])
    if body.path and body.path not in existing:
        existing.append(body.path)
    service.update_step(session_id, step_id, {"captures": existing})
    return {"success": True, "captures": existing}


@router.delete("/sessions/{session_id}/steps/{step_id}")
def delete_step(
    session_id: str, step_id: int, request: Request, _: None = Depends(require_token)
) -> dict:
    """step 삭제 (handoff §47 백로그 #4) — ``AppService.delete_step`` 위임.

    delete_step 이 누적 코드 체인을 재구성한다. kernel 은 stale 이므로 폐기.
    """
    app = request.app
    service = get_app_service(app)
    try:
        session = service.get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    if not _has_step(session, step_id):
        raise HTTPException(status_code=404, detail=f"step not found: {step_id}")
    ok = service.delete_step(session_id, step_id)
    drop_kernel(app, session_id)
    return {"success": bool(ok), "session": to_dict(service.get_session(session_id))}


@router.post("/sessions/{session_id}/steps/{step_id}/move")
def move_step(
    session_id: str,
    step_id: int,
    body: MoveStepRequest,
    request: Request,
    _: None = Depends(require_token),
) -> dict:
    """step 이동 (handoff §47 백로그 #5) — ``AppService.move_step`` (up/down)."""
    app = request.app
    service = get_app_service(app)
    direction = (body.direction or "").lower()
    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="direction 은 'up' 또는 'down' 이어야 합니다.")
    try:
        session = service.get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    if not _has_step(session, step_id):
        raise HTTPException(status_code=404, detail=f"step not found: {step_id}")
    ok = service.move_step(session_id, step_id, direction)
    drop_kernel(app, session_id)
    return {"success": bool(ok), "session": to_dict(service.get_session(session_id))}


@router.post("/sessions/{session_id}/steps/{step_id}/insert")
def insert_step(
    session_id: str,
    step_id: int,
    body: InsertStepRequest,
    request: Request,
    _: None = Depends(require_token),
) -> dict:
    """step 삽입 (handoff §47 백로그 #6) — step_id 뒤에 빈/주어진 step 삽입.

    ``AppService.insert_step(after_step_id=step_id)`` 위임. 새 step_id 반환.
    """
    app = request.app
    service = get_app_service(app)
    try:
        session = service.get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    if not _has_step(session, step_id):
        raise HTTPException(status_code=404, detail=f"step not found: {step_id}")
    new_id = service.insert_step(session_id, step_id, code=body.code, description=body.description)
    drop_kernel(app, session_id)
    return {
        "success": True,
        "new_step_id": new_id,
        "session": to_dict(service.get_session(session_id)),
    }


@router.post("/sessions/{session_id}/steps/{step_id}/regenerate")
async def regenerate_step(
    session_id: str,
    step_id: int,
    body: RegenerateRequest,
    request: Request,
    _: None = Depends(require_token),
) -> dict:
    """step 재생성 (handoff §47 백로그 #7) — ``generate_step(replaces_step_id=step_id)``.

    core 가 in-place 재생성을 1급 지원(replaces_step_id): 자기 자신을 컨텍스트에서 skip 하고
    동일 step_id 로 코드/설명을 갱신한다(새 step 추가 X). user_request 미지정 시 기존 값 재사용.
    """
    app = request.app
    service = get_app_service(app)
    if service.ai_manager is None:
        raise HTTPException(
            status_code=503,
            detail="AI 엔진이 구성되지 않았습니다 (config/settings.json 의 ai 섹션 확인).",
        )
    try:
        session = service.get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    step = _find_step(session, step_id)
    if step is None:
        raise HTTPException(status_code=404, detail=f"step not found: {step_id}")

    user_request = (body.user_request or "").strip() or (_step_field(step, "user_request") or "")
    if not user_request:
        raise HTTPException(status_code=400, detail="재생성할 user_request 가 없습니다.")

    new_step, response = await service.generate_step(
        session=session,
        user_request=user_request,
        prompt_builder=service.prompt_builder,
        element_context=body.element_context,
        is_browser_element=body.is_browser_element,
        replaces_step_id=step_id,
    )
    drop_kernel(app, session_id)
    if new_step is None or not response.success:
        return {
            "success": False,
            "error": response.error or "AI 응답 실패",
            "partial": getattr(response, "partial", False),
        }
    return {
        "success": True,
        "step": to_dict(new_step),
        "session": to_dict(service.get_session(session_id)),
        "description": response.description or "",
    }
