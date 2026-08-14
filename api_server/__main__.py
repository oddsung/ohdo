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
    python -m api_server [--host 127.0.0.1] [--port 8765] [--data-dir DIR] [--config-dir DIR]
    토큰은 ``OHDO_API_TOKEN`` env 로만 전달 (argv 노출 회피).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys

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


def _ensure_bridge_dpi_awareness() -> str:
    """브리지 프로세스를 PER_MONITOR_AWARE_V2 로 설정 (handoff §76).

    멀티모니터(서로 다른 DPI/해상도)에서 pick/capture/LL-hook 의 좌표가 OS 에 의해
    가상화되면 ElementFromPoint 가 엉뚱한 요소를 잡고 하이라이트 박스가 어긋난다.
    v1 의 ``main.py`` 가 ``SetProcessDpiAwarenessContext`` 로 하던 것과 동등하지만,
    v3 는 브리지가 별도 프로세스라 여기서 직접 보장한다.

    실패해도 서버 기동을 막지 않는다(best-effort). 결정된 모드 문자열을 반환하되,
    예외 시 ``"error"`` 를 반환한다 (non-Windows 에선 core 가 ``"unsupported"``).
    """
    try:
        from core.input_hooks import ensure_dpi_awareness

        return str(ensure_dpi_awareness())
    except Exception:
        return "error"


def _run_as_python_runner(argv: "list[str]") -> bool:
    """frozen exe 를 파이썬 런너로 재사용하는 특수 모드 (handoff §92).

    packaged 앱에선 ``sys.executable`` 이 파이썬이 아니라 이 브리지 exe 라서,
    코드 실행 커널/샌드박스가 파이썬 서브프로세스를 띄울 수 없다. 이를 위해:

    - ``--run-kernel-worker``: 번들된 ``core.kernel_worker`` 를 __main__ 으로 실행
      (frozen 에선 kernel_worker.py 가 파일로 존재하지 않아 모듈 실행이 유일한 경로).
    - ``--run-script <path> [args...]``: 임의 스크립트 실행 (CodeSandbox 용).

    비-frozen(``python -m api_server``)에서도 동일하게 동작해 테스트 가능하다.
    처리했으면 True — 호출측은 서버 기동을 건너뛴다.
    """
    if not argv:
        return False
    import runpy

    if argv[0] == "--run-kernel-worker":
        sys.argv = ["kernel_worker", *argv[1:]]
        runpy.run_module("core.kernel_worker", run_name="__main__")
        return True
    if argv[0] == "--run-script" and len(argv) >= 2:
        sys.argv = list(argv[1:])  # 스크립트 관점의 argv (argv[0]=스크립트 경로)
        runpy.run_path(argv[1], run_name="__main__")
        return True
    return False


def main(argv: "list[str] | None" = None) -> None:
    # frozen(PyInstaller) 콘솔은 한국어 Windows 에서 cp949 라 유니코드 출력(argparse
    # help 의 → 등, 한글 로그)이 UnicodeEncodeError 로 죽을 수 있다 (handoff §84).
    # READY 마커는 ASCII 지만, 모든 stdout/stderr 출력을 안전하게 만든다.
    # line_buffering: 런너 모드(§92)의 스크립트/커널 출력이 파이프에서도 라인 단위로
    # 흐르게 (비-frozen 경로의 `python -u` 와 동등한 효과).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass  # 재구성 불가 환경(파이프 등)에선 기존 인코딩 유지

    # 파이썬 런너 모드 (handoff §92) — DPI/argparse/서버 기동 전에 분기.
    args_in = list(sys.argv[1:]) if argv is None else list(argv)
    if _run_as_python_runner(args_in):
        return

    # 멀티모니터(서로 다른 DPI/해상도)에서 pick/capture/LL-hook 좌표가 OS 에 의해
    # "가상화"되지 않도록 브리지 프로세스를 PER_MONITOR_AWARE_V2 로 설정한다(handoff §76).
    # v1 의 main.py 가 SetProcessDpiAwarenessContext 로 하던 것과 동등 — 브리지는 별도
    # 프로세스라 직접 보장해야 한다. 어떤 GUI/DPI 의존 호출보다 먼저, 1회. non-Windows
    # 환경에선 "unsupported" 반환(무해)이며 idempotent.
    _ensure_bridge_dpi_awareness()

    parser = argparse.ArgumentParser(prog="python -m api_server", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="bind host (기본 localhost)")
    parser.add_argument("--port", type=int, default=8765, help="시작 포트 (기본 8765)")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="세션 저장소 디렉터리 (기본: 프로젝트 루트 data/)",
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        help=(
            "settings.json 읽기/쓰기 디렉터리 (기본: 프로젝트/번들 config/). "
            "packaged 앱은 userData 를 넘겨 설정 변경을 업데이트에도 영속 (handoff §81)"
        ),
    )
    args = parser.parse_args(args_in)

    # 토큰은 env 로만 받는다. 없으면 random 생성 (단독 실행/테스트 시).
    token = os.environ.get("OHDO_API_TOKEN") or secrets.token_urlsafe(32)

    # uvicorn / fastapi 는 무거우므로 인자 파싱 후 import.
    import uvicorn

    from api_server.server import create_app

    sock, port = _bind_free_socket(args.host, args.port)

    app = create_app(token=token, data_dir=args.data_dir, config_dir=args.config_dir)
    config = uvicorn.Config(app, log_level="info")
    server = uvicorn.Server(config)

    # 소켓이 이미 bind+listen 상태이므로, 이 줄 이후 들어오는 연결은 큐잉되어
    # uvicorn 의 accept 루프가 곧바로 처리한다. Electron 은 이 줄을 기다린다.
    print(f"{READY_MARKER} {json.dumps({'port': port, 'token': token})}", flush=True)

    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
