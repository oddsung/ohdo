# SPDX-License-Identifier: AGPL-3.0-or-later
"""``python -m api_server`` 진입점 — uvicorn 으로 브리지 서버를 실행한다.

Electron main 이 이 모듈을 subprocess 로 spawn 한다 (handoff §37 통신 디자인).

라이프사이클 계약 (Electron ↔ Python):
1. Electron 이 비어 있는 포트를 골라 ``--port`` 로 넘기고, random 토큰을
   ``OHDO_API_TOKEN`` env 로 주입한다.
2. Python 은 요청 포트부터 시작해 사용 가능한 포트에 소켓을 bind 한다
   (경합 시 +1 씩 최대 10회 fallback).
3. 서버가 listen 준비되면 stdout 에 **단 한 줄**을 출력한다::

       OHDO_API_READY {"port": <int>, "token": "<str>"}

   Electron 은 이 줄을 파싱해 실제 포트를 확정한 뒤 fetch 를 시작한다.
4. Electron 이 종료할 때 이 프로세스에 SIGTERM(→5s 후 SIGKILL)을 보낸다.

CLI:
    python -m api_server [--host 127.0.0.1] [--port 8765] [--data-dir DIR]
    토큰은 ``OHDO_API_TOKEN`` env 로만 전달 (argv 노출 회피).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket

# stdout 의 READY 마커는 Electron 이 기계 파싱하므로 절대 깨지면 안 된다.
READY_MARKER = "OHDO_API_READY"
_PORT_FALLBACK_TRIES = 10


def _bind_free_socket(host: str, start_port: int) -> "tuple[socket.socket, int]":
    """``start_port`` 부터 사용 가능한 포트를 찾아 bind 한 소켓을 반환한다.

    handoff §37 "포트 충돌 처리: 8765 점유 시 8766/8767 fallback".
    """
    last_err = None
    for candidate in range(start_port, start_port + _PORT_FALLBACK_TRIES + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # 주의: Windows 의 SO_REUSEADDR 는 포트 hijack 을 허용하므로 설정하지 않는다.
            sock.bind((host, candidate))
            sock.listen(128)
            return sock, candidate
        except OSError as exc:
            last_err = exc
            sock.close()
            continue
    raise SystemExit(
        f"[api_server] {host}:{start_port}~+{_PORT_FALLBACK_TRIES} 모두 사용 중 — "
        f"서버를 시작할 수 없습니다 ({last_err})"
    )


def main(argv: "list[str] | None" = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m api_server", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="bind host (기본 localhost)")
    parser.add_argument("--port", type=int, default=8765, help="시작 포트 (기본 8765)")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="세션 저장소 디렉터리 (기본: 프로젝트 루트 data/)",
    )
    args = parser.parse_args(argv)

    # 토큰은 env 로만 받는다. 없으면 random 생성 (단독 실행/테스트 시).
    token = os.environ.get("OHDO_API_TOKEN") or secrets.token_urlsafe(32)

    # uvicorn / fastapi 는 무거우므로 인자 파싱 후 import.
    import uvicorn

    from api_server.server import create_app

    sock, port = _bind_free_socket(args.host, args.port)

    app = create_app(token=token, data_dir=args.data_dir)
    config = uvicorn.Config(app, log_level="info")
    server = uvicorn.Server(config)

    # 소켓이 이미 bind+listen 상태이므로, 이 줄 이후 들어오는 연결은 큐잉되어
    # uvicorn 의 accept 루프가 곧바로 처리한다. Electron 은 이 줄을 기다린다.
    print(f"{READY_MARKER} {json.dumps({'port': port, 'token': token})}", flush=True)

    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
