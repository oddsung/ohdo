"""WebSocket 게이트웨이 — `/v0/agent` (Bearer 인증).

M1.5 범위 (핸드셰이크):
- 연결 수락 전에 ``Authorization: Bearer ag_...`` 검증 (auth 실패도 일단 accept
  후 close code 로 통지해 클라이언트가 수신 가능하도록 함).
- 연결 수락 후 ``server.hello`` 프레임 송신 (agent_id/user_id/server_version).
- 5초 내 ``agent.hello`` 수신 기대. 수신 시 ``agents.last_seen_at = now()`` 갱신.

M2.3 범위 추가:
- 핸드셰이크 성공 시 ``registry`` 에 agent_id → ws 등록.
- 이후 수신 프레임 중 ``execution.accepted`` / ``.progress`` / ``.result`` 를
  파싱해 ``executions`` row 를 상태 전이. 그 외 type 은 debug 로그.

설계: docs/saas/architecture/07-m1.5-websocket-hello.md, 10-m2.3-execution-lifecycle.md
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

from .. import __version__, registry
from ..auth import AGENT_TOKEN_PREFIX, hash_token
from ..db import get_session
from ..models import Agent, Execution, ExecutionLog

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

PROTOCOL_VERSION = 0
HELLO_TIMEOUT_SECONDS = 5.0
HEARTBEAT_SECONDS = 20

# Close codes (RFC 6455 4000-4999 = application-specific).
CLOSE_PROTOCOL_VIOLATION = 4400
CLOSE_UNAUTHORIZED = 4401
CLOSE_REVOKED = 4403


def _extract_bearer_from_headers(headers: Headers) -> str | None:
    header = headers.get("authorization") or headers.get("Authorization")
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2:
        return None
    scheme, value = parts
    if scheme.lower() != "bearer":
        return None
    token = value.strip()
    return token or None


async def _authenticate(
    headers: Headers, session: AsyncSession
) -> tuple[Agent | None, str | None]:
    """Bearer 헤더를 검증. 성공 시 ``(agent, None)``, 실패 시 ``(None, error_code)``."""
    token = _extract_bearer_from_headers(headers)
    if token is None:
        return None, "missing_token"
    if not token.startswith(AGENT_TOKEN_PREFIX):
        return None, "malformed_token"

    token_h = hash_token(token)
    result = await session.execute(select(Agent).where(Agent.token_hash == token_h))
    agent = result.scalar_one_or_none()
    if agent is None:
        return None, "invalid_token"
    if agent.revoked_at is not None:
        return None, "token_revoked"
    return agent, None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _make_frame(message_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "v": PROTOCOL_VERSION,
        "type": message_type,
        "id": str(uuid.uuid4()),
        "ts": _now_iso(),
        "payload": payload,
    }


def _is_valid_agent_hello(frame: Any) -> bool:
    return (
        isinstance(frame, dict)
        and frame.get("type") == "agent.hello"
        and isinstance(frame.get("payload"), dict)
    )


async def _close_with(ws: WebSocket, code: int, reason: str) -> None:
    """accept 가 아직 이뤄지지 않았어도 안전하게 close. 로그는 항상 남긴다."""
    try:
        await ws.close(code=code, reason=reason)
    except RuntimeError:
        # accept 가 호출되지 않은 상태에서 close 를 여러 번 시도하는 경우 등.
        logger.debug("ws close raised RuntimeError (already closed?)")


@router.websocket("/v0/agent")
async def ws_agent(
    websocket: WebSocket,
    session: AsyncSession = Depends(get_session),
) -> None:
    agent, error_code = await _authenticate(websocket.headers, session)

    # 인증 실패여도 accept 를 먼저 해야 클라이언트가 close code 를 수신할 수 있다.
    # Starlette 이 accept 전에 close 하면 HTTP 응답만 떨어져서 일부 클라이언트에선
    # close code 를 못 본다.
    await websocket.accept()

    if agent is None:
        code = CLOSE_REVOKED if error_code == "token_revoked" else CLOSE_UNAUTHORIZED
        logger.info("ws auth failed: %s", error_code)
        await _close_with(websocket, code, error_code or "unauthorized")
        return

    logger.info("ws connected: agent_id=%s user_id=%s", agent.id, agent.user_id)

    # server.hello 송신
    hello_payload = {
        "server_version": __version__,
        "agent_id": str(agent.id),
        "user_id": str(agent.user_id),
        "heartbeat_seconds": HEARTBEAT_SECONDS,
    }
    await websocket.send_json(_make_frame("server.hello", hello_payload))

    # agent.hello 수신 대기
    try:
        first = await asyncio.wait_for(
            websocket.receive_json(), timeout=HELLO_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        logger.info("ws closed: no agent.hello within %ss", HELLO_TIMEOUT_SECONDS)
        await _close_with(websocket, CLOSE_PROTOCOL_VIOLATION, "no_agent_hello")
        return
    except WebSocketDisconnect:
        logger.info("ws disconnected before agent.hello")
        return

    if not _is_valid_agent_hello(first):
        logger.info("ws closed: invalid agent.hello frame=%r", first)
        await _close_with(websocket, CLOSE_PROTOCOL_VIOLATION, "invalid_hello")
        return

    # last_seen_at 갱신 — 수신 = 생존.
    agent.last_seen_at = datetime.now(timezone.utc)
    await session.commit()
    logger.info(
        "ws handshake complete: agent_id=%s payload_keys=%s",
        agent.id, sorted((first.get("payload") or {}).keys()),
    )

    # M2.3: 핸드셰이크 성공 후 레지스트리 등록. POST /v0/executions 가
    # execution.start 프레임을 이 소켓으로 push 할 수 있게 된다.
    registry.register(agent.id, websocket)

    # M2.3 프레임 수신 루프 — execution.* 처리.
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                logger.debug("ws non-json frame (len=%d) agent_id=%s", len(raw), agent.id)
                continue
            if not isinstance(frame, dict):
                continue
            await _route_agent_frame(frame, agent=agent, session=session)
    except WebSocketDisconnect:
        logger.info("ws disconnected: agent_id=%s", agent.id)
    finally:
        registry.unregister(agent.id, websocket)


# ── 프레임 라우팅 (M2.3) ────────────────────────────────────────────────────


_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
_ALLOWED_RESULT_STATUSES = {"completed", "failed", "cancelled"}

# M2.4: 로그 프레임 관련
_ALLOWED_LOG_STREAMS = {"stdout", "stderr", "engine"}
LOG_LINE_MAX_SERVER = 4000  # 두 번째 방어선 (agent 는 2000 clamp)
LOG_ENTRIES_MAX_PER_FRAME = 500  # 단일 프레임 내 entries 상한


async def _route_agent_frame(
    frame: dict[str, Any], *, agent: Agent, session: AsyncSession
) -> None:
    ftype = frame.get("type")
    payload = frame.get("payload") if isinstance(frame.get("payload"), dict) else {}
    execution_id = payload.get("execution_id") if isinstance(payload, dict) else None

    if ftype == "execution.accepted":
        await _handle_accepted(execution_id, agent=agent, session=session)
    elif ftype == "execution.progress":
        await _handle_progress(payload, execution_id, agent=agent, session=session)
    elif ftype == "execution.result":
        await _handle_result(payload, execution_id, agent=agent, session=session)
    elif ftype == "execution.log":
        await _handle_log(payload, execution_id, agent=agent, session=session)
    else:
        logger.debug("ws unhandled frame type=%s agent_id=%s", ftype, agent.id)


async def _fetch_owned_execution(
    execution_id: str | None, *, agent: Agent, session: AsyncSession
) -> Execution | None:
    """agent 소유 execution 만 반환. 없으면 None + WARN 로그."""
    if not isinstance(execution_id, str) or not execution_id:
        return None
    stmt = select(Execution).where(
        Execution.execution_id == execution_id,
        Execution.agent_id == agent.id,
    )
    result = await session.execute(stmt)
    execution: Execution | None = result.scalar_one_or_none()
    if execution is None:
        logger.warning(
            "ws frame rejected: execution_id=%s not owned by agent_id=%s",
            execution_id, agent.id,
        )
    return execution


async def _handle_accepted(
    execution_id: str | None, *, agent: Agent, session: AsyncSession
) -> None:
    execution = await _fetch_owned_execution(execution_id, agent=agent, session=session)
    if execution is None:
        return
    if execution.status != "queued":
        logger.info(
            "execution.accepted ignored (status=%s) execution_id=%s",
            execution.status, execution_id,
        )
        return
    execution.status = "accepted"
    execution.started_at = datetime.now(timezone.utc)
    await session.commit()
    logger.info("execution accepted: execution_id=%s", execution_id)


async def _handle_progress(
    payload: dict[str, Any],
    execution_id: str | None,
    *,
    agent: Agent,
    session: AsyncSession,
) -> None:
    execution = await _fetch_owned_execution(execution_id, agent=agent, session=session)
    if execution is None:
        return
    if execution.status in _TERMINAL_STATUSES:
        logger.info(
            "execution.progress ignored (terminal status=%s) execution_id=%s",
            execution.status, execution_id,
        )
        return
    # 첫 progress 수신 시 running 으로 전이.
    if execution.status in ("queued", "accepted"):
        execution.status = "running"
        if execution.started_at is None:
            execution.started_at = datetime.now(timezone.utc)

    for col in ("executed_steps", "successful_steps", "failed_steps"):
        val = payload.get(col)
        if isinstance(val, int) and val >= 0:
            setattr(execution, col, val)

    await session.commit()


async def _handle_result(
    payload: dict[str, Any],
    execution_id: str | None,
    *,
    agent: Agent,
    session: AsyncSession,
) -> None:
    execution = await _fetch_owned_execution(execution_id, agent=agent, session=session)
    if execution is None:
        return
    if execution.status in _TERMINAL_STATUSES:
        logger.info(
            "execution.result ignored (already terminal=%s) execution_id=%s",
            execution.status, execution_id,
        )
        return

    final_status = payload.get("status")
    if final_status not in _ALLOWED_RESULT_STATUSES:
        logger.warning(
            "execution.result has invalid status=%r execution_id=%s",
            final_status, execution_id,
        )
        return

    execution.status = final_status
    execution.finished_at = datetime.now(timezone.utc)

    for col in (
        "total_steps",
        "executed_steps",
        "successful_steps",
        "failed_steps",
        "total_time_ms",
    ):
        val = payload.get(col)
        if isinstance(val, int) and val >= 0:
            setattr(execution, col, val)

    err = payload.get("error_summary")
    if isinstance(err, str):
        execution.error_summary = err[:500]  # 과대 로그 방어

    await session.commit()
    logger.info(
        "execution completed: execution_id=%s status=%s",
        execution_id, final_status,
    )


async def _handle_log(
    payload: dict[str, Any],
    execution_id: str | None,
    *,
    agent: Agent,
    session: AsyncSession,
) -> None:
    """M2.4: `execution.log` 프레임 수신 → execution_logs 에 bulk insert.

    터미널 상태 이후에도 지연 flush 수용 (거부하지 않음).
    """
    execution = await _fetch_owned_execution(execution_id, agent=agent, session=session)
    if execution is None:
        return
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        return

    rows: list[ExecutionLog] = []
    for entry in entries[:LOG_ENTRIES_MAX_PER_FRAME]:
        if not isinstance(entry, dict):
            continue
        stream = entry.get("stream")
        line = entry.get("line")
        if stream not in _ALLOWED_LOG_STREAMS:
            continue
        if not isinstance(line, str) or not line:
            continue
        seq = entry.get("seq")
        step_id = entry.get("step_id")
        rows.append(
            ExecutionLog(
                execution_id=execution_id,  # type: ignore[arg-type]
                seq=seq if isinstance(seq, int) else 0,
                step_id=step_id if isinstance(step_id, int) and step_id >= 1 else None,
                stream=stream,
                line=line[:LOG_LINE_MAX_SERVER],
            )
        )

    if rows:
        session.add_all(rows)
        await session.commit()
        logger.debug(
            "execution.log persisted: execution_id=%s rows=%d",
            execution_id, len(rows),
        )
