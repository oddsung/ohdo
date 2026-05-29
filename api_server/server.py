# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI 앱 팩토리 — desktop_v3 의 Python 브리지.

엔드포인트는 ``routes/`` 모듈에 도메인별로 분리되어 있다 (handoff §43):
- ``routes/health.py``     : GET /health (인증 불필요)
- ``routes/sessions.py``   : 세션 목록/상세/생성 + AI generate
- ``routes/steps.py``      : PUT step 코드 편집 (Monaco)
- ``routes/pick.py``       : POST /pick (element picker)
- ``routes/recording.py``  : 작업 녹화 lifecycle (start/status/marker/stop_commit/cancel)
- ``routes/execution.py``  : WS /ws/execute (step 실행 + live 로그)

공용 의존성(get_app_service / require_token / kernel·recording helper / 스키마)은
``deps.py`` 에 있다.

토큰 인증:
- Electron main 이 앱 시작 시 random 토큰 생성 → ``OHDO_API_TOKEN`` env 로 Python
  subprocess 에 주입 → preload 가 renderer 에 전달.
- ``/health`` 를 제외한 모든 엔드포인트는 ``Authorization: Bearer <token>`` 또는
  ``X-OHDO-Token: <token>`` 헤더(WS 는 ``?token=``)를 요구한다.
- 서버는 ``127.0.0.1`` (localhost) 만 listen.

핵심 원칙 (handoff §37): ``core/`` 와 PySide6 (``ui/``, ``ui_v2/``) 는 수정하지 않고
``AppService`` 를 통해 호출만 한다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# DEFAULT_DATA_DIR 은 create_app 에서, 스키마 3종은 하위호환 re-export 용.
# §43 routes 분리 전에는 스키마가 server.py 에 있었어서, 외부/테스트(test_209)의
# ``from api_server.server import GenerateRequest`` 경로를 유지하기 위해 re-export.
from api_server.deps import (  # noqa: F401  (CreateSessionRequest/Generate/Update = re-export)
    DEFAULT_DATA_DIR,
    CreateSessionRequest,
    GenerateRequest,
    UpdateStepRequest,
)
from api_server.routes import (
    execution,
    generate,
    health,
    pick,
    recording,
    sessions,
    steps,
)

__all__ = [
    "create_app",
    "CreateSessionRequest",
    "GenerateRequest",
    "UpdateStepRequest",
]


def create_app(token: str = "", data_dir: "str | Path | None" = None) -> FastAPI:
    """FastAPI 앱 인스턴스를 생성한다.

    Args:
        token: 요청 인증 토큰. 빈 문자열이면 인증을 비활성화한다(개발/테스트용).
        data_dir: 세션 저장소 디렉터리. 기본은 프로젝트 루트의 ``data/``.

    Returns:
        구성된 ``FastAPI`` 인스턴스. ``app.state.app_service`` 로 AppService 접근.
    """
    resolved_data_dir = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR

    app = FastAPI(
        title="ohdo desktop_v3 bridge",
        version="0.2.0",
        summary="Electron + React UI 가 core/ 도메인 로직을 호출하는 localhost 브리지",
    )

    # localhost 만 listen 하지만, electron-vite dev 서버(렌더러 origin)와
    # 패키징된 file:// origin 모두에서 fetch 가능하도록 CORS 를 허용한다.
    # credentials 없이 토큰 헤더로 인증하므로 와일드카드 origin 이 안전하다.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    # ── app.state — 라우터가 request.app.state 로 접근하는 공유 상태 ──
    app.state.api_token = token
    app.state.data_dir = resolved_data_dir
    app.state.app_service = None  # lazy — 첫 도메인 호출 시 생성 (deps.get_app_service)
    # 세션별 ExecutionKernel 캐시 — run 간 상태 연속 (ui_v2 의 self._kernel 패턴).
    app.state.kernels = {}
    # 녹화 펌프 컨트롤러 (handoff §42) — lazy 생성 (deps.get_recording_controller).
    app.state.recording_controller = None

    # ── 라우터 등록 ──────────────────────────────────
    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(steps.router)
    app.include_router(pick.router)
    app.include_router(recording.router)
    app.include_router(execution.router)
    app.include_router(generate.router)

    return app
