# SPDX-License-Identifier: AGPL-3.0-or-later
"""AI 코드 생성 진행상황 스트리밍 (handoff §44, WebSocket).

POST /sessions/{id}/generate 의 스트리밍 버전. core 의 ``generate_step`` 은 완성된
응답만 반환하고 토큰 스트리밍 인터페이스가 없으므로(그리고 agy CLI(PTY)는 토큰 단위
스트리밍 구조적 불가), **토큰** 대신 ``on_progress`` 콜백이 emit 하는 **진행상황**
("프롬프트 구성 중…", "AI 호출 중 N자…")을 실시간 WS 로 전송한다. core/ 무수정.

서버 → 클라이언트 메시지:
- ``{"type":"progress","message":str}``
- ``{"type":"done","success":bool, step?, session?, description?, error?}``
- ``{"type":"error","message":str}``
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api_server.deps import get_app_service, to_dict

router = APIRouter()


@router.websocket("/ws/generate")
async def ws_generate(ws: WebSocket) -> None:
    """자연어 요청 → AI 코드 생성 (진행상황 스트리밍).

    쿼리 파라미터: ``token`` (인증), ``session_id`` (대상 세션).
    첫 클라이언트 메시지(JSON 텍스트):
        ``{"user_request": str, "element_context"?: str, "is_browser_element"?: bool}``
    """
    app = ws.app

    # 인증 — 쿼리 토큰 (execute WS 와 동일 패턴).
    expected = app.state.api_token
    if expected and ws.query_params.get("token", "") != expected:
        await ws.close(code=4401)
        return

    await ws.accept()
    session_id = ws.query_params.get("session_id", "")

    service = get_app_service(app)
    if service.ai_manager is None:
        await ws.send_json(
            {
                "type": "error",
                "message": "AI 엔진이 구성되지 않았습니다 (config/settings.json 의 ai 섹션 확인).",
            }
        )
        await ws.close()
        return

    try:
        session = service.get_session(session_id)
    except FileNotFoundError:
        await ws.send_json({"type": "error", "message": f"session not found: {session_id}"})
        await ws.close()
        return

    # 요청 본문 수신 (user_request 가 길 수 있어 query 대신 첫 메시지로).
    try:
        req = await ws.receive_json()
    except WebSocketDisconnect:
        return
    user_request = (req or {}).get("user_request", "")
    element_context = (req or {}).get("element_context")
    is_browser_element = bool((req or {}).get("is_browser_element", False))
    if not user_request:
        await ws.send_json({"type": "error", "message": "user_request 가 비어 있습니다."})
        await ws.close()
        return

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _emit(msg: dict) -> None:
        # on_progress 는 어댑터 실행 컨텍스트에서 불릴 수 있어 thread-safe 로 큐잉
        # (execution WS 와 동일 패턴).
        loop.call_soon_threadsafe(queue.put_nowait, msg)

    async def _run() -> None:
        try:
            step, response = await service.generate_step(
                session=session,
                user_request=user_request,
                prompt_builder=service.prompt_builder,
                element_context=element_context,
                is_browser_element=is_browser_element,
                on_progress=lambda m: _emit({"type": "progress", "message": str(m)}),
            )
            if step is None or not response.success:
                _emit(
                    {
                        "type": "done",
                        "success": False,
                        "error": response.error or "AI 응답 실패",
                        "partial": getattr(response, "partial", False),
                    }
                )
            else:
                fresh = service.get_session(session_id)
                _emit(
                    {
                        "type": "done",
                        "success": True,
                        "step": to_dict(step),
                        "session": to_dict(fresh),
                        "description": response.description or "",
                    }
                )
        except Exception as exc:  # noqa: BLE001 — 사용자에게 전달
            _emit({"type": "error", "message": str(exc)})
        finally:
            _emit({"type": "__end__"})

    run_task = asyncio.create_task(_run())

    try:
        while True:
            msg = await queue.get()
            if msg.get("type") == "__end__":
                break
            await ws.send_json(msg)
    except WebSocketDisconnect:
        pass
    finally:
        run_task.cancel()
        try:
            await ws.close()
        except Exception:
            pass
