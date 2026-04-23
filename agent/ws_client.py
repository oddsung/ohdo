"""ohdo Agent — WebSocket 게이트웨이 클라이언트 (M1.5).

``/v0/agent`` 에 Bearer 인증으로 연결해 ``server.hello`` / ``agent.hello``
핸드셰이크를 완료하고 연결을 유지한다. 401/403 close code 수신 시
``on_unauthorized`` 콜백을 호출하고 재연결을 중단한다. 그 외 종료는 지수
백오프로 재연결.

설계: docs/saas/architecture/07-m1.5-websocket-hello.md
"""

from __future__ import annotations

import json
import logging
import platform
import socket
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

try:
    import auth as agent_auth  # type: ignore[no-redef]
except ImportError:  # pragma: no cover
    from agent import auth as agent_auth  # type: ignore[no-redef]

from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

logger = logging.getLogger("ohdo.agent.ws")

PROTOCOL_VERSION = 0
HELLO_TIMEOUT_SECONDS = 5.0
BACKOFF_INITIAL_SECONDS = 1.0
BACKOFF_CAP_SECONDS = 60.0
BACKOFF_MULTIPLIER = 2.0
NO_CREDS_WAIT_SECONDS = 10.0

# 서버가 이 코드로 close 하면 클라이언트는 재연결을 중단한다.
CLOSE_UNAUTHORIZED = 4401
CLOSE_REVOKED = 4403
CLOSE_PROTOCOL_VIOLATION = 4400


def _http_to_ws(url: str) -> str:
    """``http(s)://`` 을 ``ws(s)://`` 으로 치환. 그 외는 원본 그대로."""
    if url.startswith("https://"):
        return "wss://" + url[len("https://"):]
    if url.startswith("http://"):
        return "ws://" + url[len("http://"):]
    return url


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_agent_hello_frame(server_hello_id: str | None) -> dict:
    payload: dict = {
        "agent_version": _resolve_agent_version(),
        "hostname": _safe_hostname(),
        "platform": sys.platform,
    }
    try:
        payload["os_release"] = platform.release()
    except Exception:
        pass

    frame: dict = {
        "v": PROTOCOL_VERSION,
        "type": "agent.hello",
        "id": str(uuid.uuid4()),
        "ts": _now_iso(),
        "payload": payload,
    }
    if server_hello_id:
        frame["in_reply_to"] = server_hello_id
    return frame


def _resolve_agent_version() -> str:
    # agent/__init__.py 와 agent_main.py 가 각각 __version__ 을 선언한다. import
    # 순환을 피하려고 여기선 agent_main 을 직접 import 하지 않고 그냥 __init__
    # 의 값을 시도한다. 실패 시 기본값.
    try:
        from agent import __version__  # type: ignore[attr-defined]
        return str(__version__)
    except Exception:
        return "0.0.0"


def _safe_hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return "unknown"


class WebSocketClient:
    """데몬 스레드에서 WS 연결을 유지하는 워커.

    - credentials 없으면 ``NO_CREDS_WAIT_SECONDS`` 대기 후 재검사.
    - 연결 성공 후 ``server.hello`` 수신, ``agent.hello`` 송신, 이후 종료까지 수신 루프.
    - ``stop_event`` 가 set 되면 즉시 종료.
    """

    def __init__(
        self,
        server_url: str,
        auth_state,
        on_unauthorized: Callable[[], None] | None = None,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.ws_url = _http_to_ws(self.server_url) + "/v0/agent"
        self.auth_state = auth_state
        self.on_unauthorized = on_unauthorized
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._auth_blocked = False  # 4401/4403 수신 시 재연결 중단 플래그.

    # ── lifecycle ──
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run_forever,
            name="ohdo-ws",
            daemon=True,
        )
        self._thread.start()
        logger.info("ws client starting: url=%s", self.ws_url)

    def stop(self) -> None:
        self._stop.set()
        logger.info("ws client stop requested")

    # ── main loop ──
    def _run_forever(self) -> None:
        backoff = BACKOFF_INITIAL_SECONDS
        while not self._stop.is_set():
            if self._auth_blocked:
                logger.info("ws reconnect blocked until agent restart (auth)")
                return

            creds = self.auth_state.credentials if self.auth_state else None
            if creds is None or creds.token_server_url.rstrip("/") != self.server_url:
                # 미로그인·서버 mismatch: WS 는 시도하지 않는다. 주기적으로 재검사.
                logger.debug("ws idle — no matching credentials")
                if self._stop.wait(NO_CREDS_WAIT_SECONDS):
                    return
                continue

            ok = self._connect_once(creds.agent_token)
            if self._auth_blocked or self._stop.is_set():
                return

            if ok:
                backoff = BACKOFF_INITIAL_SECONDS  # 성공 → 백오프 리셋
            # 성공·실패 관계없이 재연결까지 대기 (짧은 drop 재연결 폭주 방지)
            wait = min(backoff, BACKOFF_CAP_SECONDS)
            logger.info("ws reconnect in %.1fs", wait)
            if self._stop.wait(wait):
                return
            backoff = min(backoff * BACKOFF_MULTIPLIER, BACKOFF_CAP_SECONDS)

    def _connect_once(self, token: str) -> bool:
        """한 번 연결 + 핸드셰이크 + 수신 루프. 정상 handshake 면 True 반환."""
        headers = [("Authorization", f"Bearer {token}")]
        try:
            ws = connect(
                self.ws_url,
                additional_headers=headers,
                open_timeout=10,
                close_timeout=5,
            )
        except InvalidStatus as exc:
            # HTTP handshake 단계에서 4xx/5xx — 서버가 ws 수락 전 거절한 경우.
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            logger.warning("ws connect rejected: status=%s", status_code)
            return False
        except (OSError, TimeoutError) as exc:
            logger.warning("ws connect failed: %s", exc)
            return False

        logger.info("ws connected: %s", self.ws_url)
        handshake_ok = False
        try:
            server_hello = self._recv_json(ws, HELLO_TIMEOUT_SECONDS)
            if not self._is_server_hello(server_hello):
                logger.warning("ws got non-server.hello first frame: %r", server_hello)
                ws.close(code=CLOSE_PROTOCOL_VIOLATION, reason="expected_server_hello")
                return False

            payload = server_hello.get("payload") or {}
            logger.info(
                "ws server.hello received: server_version=%s agent_id=%s user_id=%s hb=%ss",
                payload.get("server_version"),
                payload.get("agent_id"),
                payload.get("user_id"),
                payload.get("heartbeat_seconds"),
            )

            hello = _build_agent_hello_frame(server_hello.get("id"))
            ws.send(json.dumps(hello))
            logger.info("ws agent.hello sent: id=%s", hello["id"])
            handshake_ok = True

            # 이후 M1.5 범위에선 받는 프레임이 없다 — 서버가 close 할 때까지 대기.
            self._receive_until_closed(ws)

        except ConnectionClosed as exc:
            self._handle_connection_closed(exc)
        except Exception:  # pragma: no cover
            logger.exception("ws loop unexpected error")
        finally:
            try:
                ws.close()
            except Exception:
                pass
        return handshake_ok

    # ── helpers ──
    def _recv_json(self, ws, timeout: float) -> dict:
        raw = ws.recv(timeout=timeout)
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="replace")
        return json.loads(raw)

    def _is_server_hello(self, frame) -> bool:
        return isinstance(frame, dict) and frame.get("type") == "server.hello"

    def _receive_until_closed(self, ws) -> None:
        while not self._stop.is_set():
            try:
                msg = ws.recv(timeout=60)  # 긴 idle 허용
            except TimeoutError:
                continue  # keep-alive (protocol-level ping/pong 은 ws 가 처리)
            except ConnectionClosed as exc:
                self._handle_connection_closed(exc)
                return
            # M2 에서 execution.* 처리. 지금은 관찰만.
            if isinstance(msg, (bytes, bytearray)):
                msg = msg.decode("utf-8", errors="replace")
            logger.debug("ws recv (len=%d)", len(msg))

    def _handle_connection_closed(self, exc: ConnectionClosed) -> None:
        code = getattr(getattr(exc, "rcvd", None), "code", None)
        reason = getattr(getattr(exc, "rcvd", None), "reason", None)
        # sent 쪽으로 close 한 경우도 포함 (재시도 불필요는 아니지만 로그 정확도용).
        sent = getattr(exc, "sent", None)
        sent_code = getattr(sent, "code", None) if sent is not None else None
        logger.info(
            "ws closed: rcvd_code=%s reason=%r sent_code=%s",
            code, reason, sent_code,
        )
        if code in (CLOSE_UNAUTHORIZED, CLOSE_REVOKED):
            logger.warning("ws auth failure (code=%s reason=%r)", code, reason)
            self._auth_blocked = True
            if callable(self.on_unauthorized):
                try:
                    self.on_unauthorized()
                except Exception as cb_exc:  # pragma: no cover
                    logger.error("on_unauthorized callback raised: %s", cb_exc)
