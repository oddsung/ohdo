"""FastAPI 진입점.

라우터:
- M0: `/` 루트, `/healthz`
- M1.2: `/v0/agents/device_code`, `/v0/agents/device_token`, `/link`, `/link/approve`
- M1.4: `/v0/agents/me` (Bearer 인증)
- M1.5: `WS /v0/agent` (Bearer 인증, server.hello/agent.hello 핸드셰이크)
- M2.2: `POST/GET /v0/executions` (Bearer 인증)
- M2.6: `POST/GET /v0/executions/{id}/captures`, `GET /v0/captures/{id}` (Bearer 인증)

로컬 실행:
    uvicorn app.main:app --reload --port 8000

Railway 실행: `railway.json` startCommand 에서 `alembic upgrade head && uvicorn ...`.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI

from . import __version__
from .routers import agents, captures, device_flow, executions, link, ws

app = FastAPI(
    title="ohdo Control Plane",
    description="ohdo.ai SaaS 백엔드.",
    version=__version__,
)

app.include_router(device_flow.router)
app.include_router(link.router)
app.include_router(agents.router)
app.include_router(executions.router)
app.include_router(captures.exec_captures)
app.include_router(captures.cap_router)
app.include_router(ws.router)


@app.get("/")
def root() -> dict:
    """서비스 식별용 루트. 배포 확인에 쓰임."""
    return {
        "service": "ohdo-backend",
        "version": __version__,
        "docs": "/docs",
    }


@app.get("/healthz")
def healthz() -> dict:
    """Agent 와 모니터링이 사용하는 헬스체크.

    Railway 등의 플랫폼 health check 에도 사용 가능.
    """
    return {
        "status": "ok",
        "version": __version__,
        "ts": datetime.now(timezone.utc).isoformat(),
        "env": os.getenv("OHDO_ENV", "development"),
    }
