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
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api_server.deps import get_app_service, to_dict

logger = logging.getLogger(__name__)

router = APIRouter()


def _enforce_step_selector(service, session_id: str, step, element_context: "str | None") -> None:
    """§72: 생성된 step 의 element 셀렉터를 picker 가 고른 요소로 결정적으로 교정(best-effort).

    연속 클릭 step 이 쌓이면 프롬프트가 직전 대상(예: Document)으로 도배돼 AI 가 새로 픽한
    요소를 무시하는 신호-잡음 문제 → picker 가 정확히 아는 요소(auto_id/title)로 생성 후 교정.
    generated_code(마커 영역) 교정 + step_code(델타) 마커 재추출. core 무관(텍스트 후처리).
    """
    if not element_context or not getattr(step, "generated_code", ""):
        return
    try:
        from api_server.selector_enforce import enforce_picked_selector

        new_code, changed = enforce_picked_selector(
            step.generated_code, step.step_id, element_context
        )
        if not changed:
            return
        updates: dict = {"generated_code": new_code}
        # step_code(델타)도 마커 재추출로 일관성 유지(표시/삭제·재정렬 chain).
        try:
            from core.workflow_engine import extract_step_delta_code

            sess = service.get_session(session_id)
            steps = [to_dict(s) for s in sess.steps]
            idx = next((i for i, s in enumerate(steps) if s.get("step_id") == step.step_id), None)
            if idx is not None:
                cur = dict(steps[idx])
                cur["generated_code"] = new_code
                prev = steps[idx - 1] if idx > 0 else None
                delta = extract_step_delta_code(cur, prev)
                if delta and delta.strip():
                    updates["step_code"] = delta
        except Exception:
            logger.debug("step_code 재추출 실패(generated_code 만 교정)", exc_info=True)
        service.update_step(session_id, step.step_id, updates)
        logger.info("§72 셀렉터 교정 적용 (step %s)", step.step_id)
    except Exception:
        logger.debug("셀렉터 교정 실패(무시 — AI 출력 유지)", exc_info=True)


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
    images = (req or {}).get("images") or None  # 첨부 이미지 경로 (handoff §60 #13)
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
                images=images,
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
                # §72: picker 로 고른 요소를 AI 가 무시하고 엉뚱한 셀렉터를 쓴 경우 결정적 교정.
                _enforce_step_selector(service, session_id, step, element_context)
                # §78c: 주석만 생성/이전 스텝 누락을 템플릿·체인으로 결정적 보정.
                from api_server.step_guard import apply_step_guards

                apply_step_guards(service, session_id, step, element_context)
                fresh = service.get_session(session_id)
                # 교정 후 갱신된 step dict 로 응답(없으면 원본).
                step_dict = next(
                    (to_dict(s) for s in fresh.steps if to_dict(s).get("step_id") == step.step_id),
                    to_dict(step),
                )
                _emit(
                    {
                        "type": "done",
                        "success": True,
                        "step": step_dict,
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
