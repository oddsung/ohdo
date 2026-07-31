# SPDX-License-Identifier: AGPL-3.0-or-later
"""실행 중 시각 효과(run FX) — 클릭 관찰 훅 lifecycle + 폴링 (handoff §79).

Electron 이 전체 실행 시작 시 ``POST /fx/start`` 로 관찰 전용 LL 훅(fx_pump)을 armed,
run 오버레이가 ``GET /fx/clicks?since=N`` 을 폴링해 클릭 리플을 그리고, 종료 시
``POST /fx/stop``. 훅은 클릭을 절대 삼키지 않는다(자동화 무간섭).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from api_server.deps import require_token
from api_server.fx_pump import get_clicks, is_fx_active, start_fx, stop_fx

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/fx/start")
def fx_start(_: None = Depends(require_token)) -> dict:
    """클릭 관찰 훅 시작 (idempotent). 비-Windows/설치 실패 시 active=False (무효과)."""
    ok = start_fx()
    return {"success": True, "active": ok}


@router.post("/fx/stop")
def fx_stop(_: None = Depends(require_token)) -> dict:
    """클릭 관찰 훅 중지 (idempotent)."""
    was = stop_fx()
    return {"success": True, "was_active": was}


@router.get("/fx/clicks")
def fx_clicks(since: int = 0, _: None = Depends(require_token)) -> dict:
    """``since`` 이후 클릭 이벤트 (물리 픽셀 좌표). 응답 seq 를 다음 since 로 사용."""
    data = get_clicks(since)
    data["active"] = is_fx_active()
    return data
