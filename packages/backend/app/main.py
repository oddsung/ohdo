"""FastAPI 진입점.

M0 범위: `/` 루트 + `/healthz` 만. 이후 마일스톤에서 라우터가 추가된다.

로컬 실행:
    uvicorn app.main:app --reload --port 8000

Railway 실행: Procfile 에서 자동 시작.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI

from . import __version__

app = FastAPI(
    title="ohdo Control Plane",
    description="ohdo.ai SaaS 백엔드. M0 는 헬스체크만 제공.",
    version=__version__,
)


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
