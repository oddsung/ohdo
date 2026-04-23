"""WebSocket 연결 레지스트리 (M2.3).

에이전트가 WS 핸드셰이크를 완료하면 ``agent_id → WebSocket`` 을 등록한다.
``POST /v0/executions`` 가 ``execution.start`` 프레임을 해당 에이전트로 push
할 때 여기서 WS 를 찾는다.

단일 프로세스·단일 이벤트 루프 (FastAPI + uvicorn) 에서 동작. 다중 워커로
확장 시 Redis pub/sub 등으로 교체 필요 (Phase 3).

같은 agent_id 로 이중 연결되는 엣지 케이스는 "나중 연결이 이긴다" — 이전 연결은
레지스트리에서 밀려나지만 실제 소켓을 여기서 close 하지는 않는다 (WS 핸들러의
finally 가 정리).

상세 설계: docs/saas/architecture/10-m2.3-execution-lifecycle.md
"""

from __future__ import annotations

import logging
import uuid

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_connections: dict[uuid.UUID, WebSocket] = {}


def register(agent_id: uuid.UUID, websocket: WebSocket) -> None:
    prior = _connections.get(agent_id)
    _connections[agent_id] = websocket
    if prior is not None and prior is not websocket:
        logger.info(
            "ws registry replaced connection: agent_id=%s", agent_id
        )


def unregister(agent_id: uuid.UUID, websocket: WebSocket) -> None:
    """등록된 소켓이 현재 ws 와 같을 때만 제거. 경쟁 상태에서 후속 연결을
    실수로 지우는 것을 막는다."""
    if _connections.get(agent_id) is websocket:
        del _connections[agent_id]


def get(agent_id: uuid.UUID) -> WebSocket | None:
    return _connections.get(agent_id)


def size() -> int:
    """테스트 편의용. 운영에서는 사용 안 함."""
    return len(_connections)
