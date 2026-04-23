"""Bearer 인증이 필요한 Agent 엔드포인트.

M1.4 범위:
- ``GET /v0/agents/me`` — 현재 Agent 의 정보를 반환하고 ``last_seen_at`` 을 갱신.

device_code / device_token (익명 경로) 은 ``device_flow.py`` 에 그대로 두고
여기엔 인증된 경로만 모은다.

설계: docs/saas/architecture/06-m1.4-authenticated-ping.md
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..dependencies import current_agent
from ..models import Agent

router = APIRouter(prefix="/v0/agents", tags=["agents"])


class AgentMeResponse(BaseModel):
    agent_id: uuid.UUID
    user_id: uuid.UUID
    name: str | None = None
    hostname: str | None = None
    platform: str | None = None
    agent_version: str | None = None
    last_seen_at: datetime = Field(
        description="이 요청으로 갱신된 last_seen_at (서버 시각, UTC).",
    )


@router.get("/me", response_model=AgentMeResponse)
async def get_me(
    agent: Agent = Depends(current_agent),
    session: AsyncSession = Depends(get_session),
) -> AgentMeResponse:
    """현재 agent_token 으로 접근 가능한 Agent 정보 조회 + last_seen_at 갱신."""
    agent.last_seen_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(agent)

    return AgentMeResponse(
        agent_id=agent.id,
        user_id=agent.user_id,
        name=agent.name,
        hostname=agent.hostname,
        platform=agent.platform,
        agent_version=agent.agent_version,
        last_seen_at=agent.last_seen_at,  # type: ignore[arg-type]
    )
