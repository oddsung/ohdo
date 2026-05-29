# SPDX-License-Identifier: AGPL-3.0-or-later
"""step 실행 + live 로그 스트리밍 (handoff §40 #1, WebSocket)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api_server.deps import drop_kernel, get_app_service, get_kernel, step_result_dict

router = APIRouter()


@router.websocket("/ws/execute")
async def ws_execute(ws: WebSocket) -> None:
    """step 실행 + live 로그 스트리밍.

    쿼리 파라미터:
    - ``token``      : 인증 토큰 (브라우저 WebSocket 은 헤더 설정이 어려워 쿼리로).
    - ``session_id`` : 대상 세션.
    - ``mode``       : ``all`` | ``from`` | ``single`` (기본 all).
    - ``step_id``    : ``from``/``single`` 모드의 대상 step.

    서버 → 클라이언트 메시지 (JSON):
    - ``{"type":"log","message":str}``
    - ``{"type":"step_done","step_id":int,"result":{...}}``
    - ``{"type":"done"}`` | ``{"type":"error","message":str}``

    ``run_blocks`` 는 executor 스레드에서 동작하므로, on_log/on_step_complete 콜백은
    ``loop.call_soon_threadsafe`` 로 asyncio 큐에 넣고 별도 소비 루프가 WS 로 전송한다.
    """
    app = ws.app

    # 인증 — 쿼리 토큰. 빈 토큰(개발/테스트)이면 통과.
    expected = app.state.api_token
    supplied = ws.query_params.get("token", "")
    if expected and supplied != expected:
        await ws.close(code=4401)  # 4401 = 앱 레벨 unauthorized
        return

    await ws.accept()
    session_id = ws.query_params.get("session_id", "")
    mode = ws.query_params.get("mode", "all")
    step_id_raw = ws.query_params.get("step_id")
    step_id = int(step_id_raw) if step_id_raw and step_id_raw.isdigit() else None

    service = get_app_service(app)
    try:
        session = service.get_session(session_id)
    except FileNotFoundError:
        await ws.send_json({"type": "error", "message": f"session not found: {session_id}"})
        await ws.close()
        return

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _emit(msg: dict) -> None:
        # executor 스레드 → asyncio 큐 (thread-safe).
        loop.call_soon_threadsafe(queue.put_nowait, msg)

    kernel = get_kernel(app, service, session_id)

    # mode → run_blocks 인자 매핑 (ui_v2 _on_run_* 패턴):
    #   all    : 전체 (start=1, stop=None)
    #   from   : step_id 부터 끝까지
    #   single : step_id 단독 (start=stop=step_id)
    if mode == "single" and step_id is not None:
        start_from, stop_after = step_id, step_id
    elif mode == "from" and step_id is not None:
        start_from, stop_after = step_id, None
    else:
        start_from, stop_after = 1, None

    async def _run() -> None:
        try:
            await service.run_blocks(
                session=session,
                kernel=kernel,
                start_from_step_id=start_from,
                stop_after_step_id=stop_after,
                on_step_start=lambda sid: _emit(
                    {"type": "log", "message": f"▶ STEP {sid} 실행 중…"}
                ),
                on_step_complete=lambda sid, r: _emit(
                    {"type": "step_done", "step_id": sid, "result": step_result_dict(r)}
                ),
                on_log=lambda m: _emit({"type": "log", "message": str(m)}),
            )
            _emit({"type": "done"})
        except Exception as exc:  # noqa: BLE001 — 사용자에게 전달
            _emit({"type": "error", "message": str(exc)})
        finally:
            _emit({"type": "__end__"})  # 소비 루프 종료 신호

    run_task = asyncio.create_task(_run())

    # 클라이언트가 "stop" 을 보내면 실행 중단.
    async def _listen_stop() -> None:
        try:
            while True:
                data = await ws.receive_text()
                if '"stop"' in data or data.strip() == "stop":
                    service.stop_blocks()
                    drop_kernel(app, session_id)
        except WebSocketDisconnect:
            service.stop_blocks()

    stop_task = asyncio.create_task(_listen_stop())

    try:
        while True:
            msg = await queue.get()
            if msg.get("type") == "__end__":
                break
            await ws.send_json(msg)
    except WebSocketDisconnect:
        service.stop_blocks()
    finally:
        stop_task.cancel()
        run_task.cancel()
        try:
            await ws.close()
        except Exception:
            pass
