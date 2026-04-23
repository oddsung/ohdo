"""Executions REST 엔드포인트 (M2.2).

- ``POST /v0/executions`` — 현재 Bearer 인증된 Agent 가 자기 자신을 위해 실행을
  큐에 올린다 (A 패턴: agent self-enqueue). 실제 WS 푸시·실행은 M2.3 이후.
- ``GET /v0/executions/{execution_id}`` — 같은 ``user_id`` 소유 row 만 조회.
  다른 사용자의 row 는 존재 여부 누설 없이 404 로 응답.
- ``GET /v0/executions`` — 같은 ``user_id`` 소유 row 리스트 (최신순).

상태는 항상 ``queued`` 로 생성된다. 전이 로직은 M2.3 (WS ``execution.*``) 에서.

상세 설계: docs/saas/architecture/09-m2.2-executions-rest.md
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..dependencies import current_agent
from ..models import Agent, Execution

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v0/executions", tags=["executions"])

EXECUTION_ID_PREFIX = "exec_"
LIST_LIMIT_DEFAULT = 50
LIST_LIMIT_MAX = 200

ALLOWED_STATUSES = {
    "queued",
    "accepted",
    "running",
    "completed",
    "failed",
    "cancelled",
}


def _new_execution_id() -> str:
    return f"{EXECUTION_ID_PREFIX}{uuid.uuid4().hex}"


# ── Schemas ─────────────────────────────────────────────────────────────────


class ExecutionCreate(BaseModel):
    """클라이언트 (Agent) 가 POST 에 싣는 body.

    ``session_snapshot`` 은 ``Session`` dataclass → dict 직렬화 결과 전체.
    M2.2 에서는 없어도 허용 (빈 row 만들어 스키마 증명 용도).
    """

    session_snapshot: dict | None = None
    from_step: int | None = Field(default=None, ge=1)
    to_step: int | None = Field(default=None, ge=1)


class ExecutionRead(BaseModel):
    """GET 응답 — ``session_snapshot`` 은 payload 크기·민감도로 포함 안 함."""

    model_config = ConfigDict(from_attributes=True)

    execution_id: str
    status: str
    agent_id: uuid.UUID
    user_id: uuid.UUID
    from_step: int | None
    to_step: int | None
    total_steps: int | None
    executed_steps: int | None
    successful_steps: int | None
    failed_steps: int | None
    total_time_ms: int | None
    error_summary: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ExecutionListResponse(BaseModel):
    items: list[ExecutionRead]


# ── Routes ──────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=ExecutionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_execution(
    body: ExecutionCreate,
    agent: Agent = Depends(current_agent),
    session: AsyncSession = Depends(get_session),
) -> ExecutionRead:
    """새 execution 을 ``queued`` 상태로 생성."""
    execution = Execution(
        execution_id=_new_execution_id(),
        agent_id=agent.id,
        user_id=agent.user_id,
        status="queued",
        session_snapshot=body.session_snapshot,
        from_step=body.from_step,
        to_step=body.to_step,
    )
    session.add(execution)
    await session.commit()
    await session.refresh(execution)
    logger.info(
        "execution created: execution_id=%s agent_id=%s user_id=%s",
        execution.execution_id, agent.id, agent.user_id,
    )
    return ExecutionRead.model_validate(execution)


@router.get("/{execution_id}", response_model=ExecutionRead)
async def get_execution(
    execution_id: str,
    agent: Agent = Depends(current_agent),
    session: AsyncSession = Depends(get_session),
) -> ExecutionRead:
    """단건 조회. 같은 ``user_id`` 의 row 만 반환, 아니면 404."""
    stmt = select(Execution).where(
        Execution.execution_id == execution_id,
        Execution.user_id == agent.user_id,
    )
    result = await session.execute(stmt)
    execution = result.scalar_one_or_none()
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "execution_not_found"},
        )
    return ExecutionRead.model_validate(execution)


@router.get("", response_model=ExecutionListResponse)
async def list_executions(
    agent: Agent = Depends(current_agent),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=LIST_LIMIT_DEFAULT, ge=1, le=LIST_LIMIT_MAX),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
) -> ExecutionListResponse:
    """같은 ``user_id`` 의 executions 를 최신순으로 리스트."""
    if status_filter is not None and status_filter not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_status_filter"},
        )

    stmt = select(Execution).where(Execution.user_id == agent.user_id)
    if status_filter is not None:
        stmt = stmt.where(Execution.status == status_filter)
    stmt = (
        stmt.order_by(Execution.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(stmt)
    rows = result.scalars().all()
    return ExecutionListResponse(
        items=[ExecutionRead.model_validate(r) for r in rows]
    )
