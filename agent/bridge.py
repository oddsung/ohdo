# SPDX-License-Identifier: AGPL-3.0-or-later
"""로컬 HTTP/WS 브리지 — Phase 1 sub-task 5 (5/8) no-op 스켈레톤.

ROADMAP §3 Phase 1 (5) 의 ``agent/bridge.py`` — "로컬 HTTP/WS 브리지 (지금은
no-op)". 현 단계에서는 contract 정의만. 실제 listener / dispatch 는 Phase 3
진입 시 구현.

미래 사용 시나리오 (Phase 3+):

1. **Web → Desktop**: 사용자가 web dashboard 에서 "Open in Desktop" 버튼 클릭 →
   custom URL scheme ``ohdo://session/<id>`` → OS 가 데스크톱 앱 실행 →
   데스크톱이 로컬 bridge 에 세션 ID 전달 → bridge 가 등록된 handler 호출.
2. **Desktop UI ↔ Agent IPC**: 데스크톱 PyQt UI 와 트레이 agent 가 별개
   프로세스로 분리 운영될 때 (현재는 같은 프로세스에서 직접 호출). Phase 4+
   백그라운드 실행 모드.
3. **Agent → Other tools**: VS Code 확장, CLI 등이 agent 에 작업 명령 전달.

설계 원칙:

- ``register_handler(action, callable)`` 로 handler 등록 (Phase 3 wiring 시점).
- ``start(port)`` 호출로 localhost 바인드. ``port=None`` 이면 OS 가 free port 할당.
- HTTP/JSON-RPC 형식 — agent ↔ Web/Desktop 사이 portable.
- 인증: localhost 한정 + 임의 토큰 (config 에서 공유).
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger("ohdo.agent.bridge")


# 등록된 handler 의 시그니처 — JSON 직렬화 가능한 dict 를 받아 dict 반환.
# 예외 발생 시 bridge 가 ``{"error": str(exc)}`` 로 응답 (구현은 Phase 3).
BridgeHandler = Callable[[dict], dict]


class LocalBridge:
    """로컬 HTTP/WS 브리지 — Phase 3 진입까지 no-op.

    현 단계 (5/8): contract 만 정의. ``start()`` / ``stop()`` / ``register_handler()``
    호출은 가능하지만 실제 listener 는 등록 안 함. ``is_running`` 은 토글 동작만.

    Phase 3 구현 시 채울 부분:

    - ``aiohttp`` 또는 ``starlette`` 로 ``http://127.0.0.1:<port>/v0/bridge`` listener
    - JSON-RPC: ``POST /v0/bridge/<action>`` body 가 dict, response 가 dict
    - WebSocket: ``ws://127.0.0.1:<port>/v0/bridge/stream`` 양방향 스트림
    - 인증 토큰 검증 (config.json 의 ``bridge_token`` 과 매칭)
    """

    def __init__(self) -> None:
        self._handlers: dict[str, BridgeHandler] = {}
        self._running: bool = False
        self._port: Optional[int] = None

    def register_handler(self, action: str, handler: BridgeHandler) -> None:
        """``action`` 이름에 handler 등록. Phase 3 의 wiring 코드가 호출.

        예 (Phase 3 가정):

        ``bridge.register_handler("open_session", lambda req: {"opened": req["session_id"]})``
        """
        if not action or not callable(handler):
            raise ValueError(f"register_handler invalid: action={action!r}")
        self._handlers[action] = handler
        logger.debug("bridge handler registered: action=%s", action)

    def get_handler(self, action: str) -> Optional[BridgeHandler]:
        """등록된 handler 조회. 미등록 시 ``None``."""
        return self._handlers.get(action)

    def list_actions(self) -> list[str]:
        """등록된 action 목록."""
        return sorted(self._handlers.keys())

    def start(self, port: Optional[int] = None) -> None:
        """로컬 bridge 시작. 현재는 토글만 (실제 listener X).

        Args:
            port: localhost 바인드 포트. ``None`` 이면 OS 가 free port 할당
                (Phase 3 구현 시점에 실제 바인드).
        """
        if self._running:
            logger.debug("bridge already running, no-op")
            return
        self._port = port
        self._running = True
        logger.info("bridge start (no-op skeleton, port=%s)", port)

    def stop(self) -> None:
        """로컬 bridge 종료. 현재는 토글만."""
        if not self._running:
            return
        self._running = False
        self._port = None
        logger.info("bridge stop (no-op skeleton)")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def port(self) -> Optional[int]:
        """현재 바인드 포트. ``start(port=N)`` 후 ``N`` 반환, 미시작 시 ``None``."""
        return self._port
