# SPDX-License-Identifier: AGPL-3.0-or-later
"""step 편집 저장 (handoff §40 #2 — Monaco 편집)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from api_server.deps import UpdateStepRequest, drop_kernel, get_app_service, require_token, to_dict

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

    if not any(
        (s.get("step_id") if isinstance(s, dict) else getattr(s, "step_id", None)) == step_id
        for s in session.steps
    ):
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
