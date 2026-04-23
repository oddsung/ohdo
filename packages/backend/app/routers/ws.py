"""WebSocket 게이트웨이 — `/v0/agent` (Bearer 인증).

M1.5 범위:
- 연결 수락 전에 ``Authorization: Bearer ag_...`` 검증 (auth 실패도 일단 accept
  후 close code 로 통지해 클라이언트가 수신 가능하도록 함).
- 연결 수락 후 ``server.hello`` 프레임 송신 (agent_id/user_id/server_version).
- 5초 내 ``agent.hello`` 수신 기대. 수신 시 ``agents.last_seen_at = now()`` 갱신.
- 이후 프레임은 M1.5 에서 처리하지 않음 (M2 에서 ``execution.*`` 추가 예정).

설계: docs/saas/architecture/07-m1.5-websocket-hello.md
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

from .. import __version__
from ..auth import AGENT_TOKEN_PREFIX, hash_token
from ..db import get_session
from ..models import Agent

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

    # M1.5 는 여기까지. 추가 프레임은 조용히 소비만. 연결이 끊길 때까지 대기.
    try:
        while True:
            msg = await websocket.receive_text()
            # M2 에서 execution.* 파싱 추가. 지금은 소비 후 debug 로그만.
            logger.debug(
                "ws unhandled frame (len=%d) agent_id=%s", len(msg), agent.id
            )
    except WebSocketDisconnect:
        logger.info("ws disconnected: agent_id=%s", agent.id)
