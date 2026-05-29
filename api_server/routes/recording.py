# SPDX-License-Identifier: AGPL-3.0-or-later
"""작업 녹화 lifecycle (handoff §41/§42 #3).

LL 훅(WH_MOUSE_LL/WH_KEYBOARD_LL)은 SetWindowsHookEx 호출 스레드에서 메시지 펌프가
돌아야 콜백이 발화한다. FastAPI 브리지엔 펌프가 없으므로 (§42 실측 — 입력 0 캡처),
RecordingController 가 전용 스레드에서 start_recording(훅 설치) + PeekMessage 펌프 +
stop_recording(훅 해제) 를 모두 수행한다. commit(파일 I/O)만 엔드포인트 스레드에서.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from api_server.deps import (
    drop_kernel,
    get_app_service,
    get_recording_controller,
    require_token,
    to_dict,
)

router = APIRouter()


@router.post("/sessions/{session_id}/recording/start")
def recording_start(session_id: str, request: Request, _: None = Depends(require_token)) -> dict:
    """대상 세션에 녹화 시작 (펌프 스레드 기동). 이미 녹화 중이면 409."""
    import sys as _sys

    if _sys.platform != "win32":
        raise HTTPException(status_code=501, detail="녹화는 Windows 전용입니다.")

    app = request.app
    service = get_app_service(app)
    try:
        service.get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")

    controller = get_recording_controller(app)
    if controller.is_active() or service.is_recording:
        raise HTTPException(status_code=409, detail="이미 녹화 중입니다.")

    try:
        controller.start(session_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"녹화 시작 실패: {exc}")

    rec = getattr(service, "_recorder", None)
    rec_session = getattr(rec, "current_session", None) if rec is not None else None
    return {"success": True, "recording_session_id": getattr(rec_session, "id", None)}


@router.get("/recording/status")
def recording_status(request: Request, _: None = Depends(require_token)) -> dict:
    """녹화 진행 상태 — 프런트가 polling 으로 event_count 표시."""
    service = get_app_service(request.app)
    return {
        "is_recording": bool(service.is_recording),
        "event_count": int(service.recording_event_count),
    }


@router.post("/recording/marker")
def recording_marker(request: Request, _: None = Depends(require_token)) -> dict:
    """현재 시점에 step 경계 marker 추가. recorder 미시작이면 409.

    ``recorder.add_marker()`` 는 self._lock 으로 thread-safe — 펌프 스레드와 별개로
    엔드포인트 스레드에서 호출해도 안전 (events 리스트에 marker append).
    """
    service = get_app_service(request.app)
    if not service.is_recording:
        raise HTTPException(status_code=409, detail="녹화 중이 아닙니다.")
    recorder = getattr(service, "_recorder", None)
    if recorder is not None and hasattr(recorder, "add_marker"):
        recorder.add_marker()
        return {"success": True}
    raise HTTPException(status_code=500, detail="recorder marker 미지원")


@router.post("/sessions/{session_id}/recording/stop_commit")
def recording_stop_commit(
    session_id: str, request: Request, _: None = Depends(require_token)
) -> dict:
    """녹화 중지(펌프 스레드) → transform → 대상 세션에 step 추가 (commit).

    stop_recording(훅 해제 포함)은 RecordingController 펌프 스레드에서, commit(파일
    I/O)은 여기(엔드포인트 스레드)에서 수행한다.
    """
    app = request.app
    controller = get_recording_controller(app)
    service = get_app_service(app)
    if not controller.is_active() and not service.is_recording:
        raise HTTPException(status_code=409, detail="녹화 중이 아닙니다.")

    try:
        steps = controller.stop(mode="commit")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"녹화 종료 실패: {exc}")
    steps = steps or []
    session = service.commit_recording(edited_steps=steps, target_session_id=session_id)
    drop_kernel(app, session_id)  # 녹화로 step 추가 → 캐시 kernel stale
    return {
        "success": True,
        "step_count": len(steps),
        "session": to_dict(session),
    }


@router.post("/recording/cancel")
def recording_cancel(request: Request, _: None = Depends(require_token)) -> dict:
    """녹화 중지 + 결과 폐기 (commit 안 함)."""
    controller = get_recording_controller(request.app)
    if not controller.is_active():
        return {"success": True, "was_recording": False}
    try:
        controller.stop(mode="cancel")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"녹화 취소 실패: {exc}")
    return {"success": True, "was_recording": True}
