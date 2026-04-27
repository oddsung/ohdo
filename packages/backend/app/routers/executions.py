"""Executions REST 엔드포인트.

- ``POST /v0/executions`` (M2.2) — A 패턴 agent self-enqueue, 201.
- ``GET /v0/executions/{execution_id}`` (M2.2) — user_id 스코프 단건.
- ``GET /v0/executions`` (M2.2) — user_id 스코프 리스트.
- ``GET /v0/executions/{execution_id}/logs`` (M2.4) — 로그 조회.
- ``POST /v0/executions/{execution_id}/cancel`` (M2.5) — 실행 중 취소.

상세 설계:
- M2.2: docs/saas/architecture/09-m2.2-executions-rest.md
- M2.4: docs/saas/architecture/11-m2.4-execution-log.md
- M2.5: docs/saas/architecture/12-m2.5-execution-cancel.md
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import registry
from ..db import get_session
from ..dependencies import AuthSubject, current_agent, current_subject
from ..models import Agent, Execution, ExecutionLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v0/executions", tags=["executions"])

EXECUTION_ID_PREFIX = "exec_"
LIST_LIMIT_DEFAULT = 50
LIST_LIMIT_MAX = 200
PROTOCOL_VERSION = 0

# M2.4
LOG_LIMIT_DEFAULT = 500
LOG_LIMIT_MAX = 2000
_ALLOWED_LOG_STREAMS = {"stdout", "stderr", "engine"}

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_start_frame(execution: Execution, body: "ExecutionCreate") -> dict:
    """M2.3: execution.start 프레임 빌더 (프로토콜 v0 포맷)."""
    return {
        "v": PROTOCOL_VERSION,
        "type": "execution.start",
        "id": str(uuid.uuid4()),
        "ts": _now_iso(),
        "payload": {
            "execution_id": execution.execution_id,
            "session_snapshot": body.session_snapshot,
            "from_step": body.from_step,
            "to_step": body.to_step,
        },
    }


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


class ExecutionLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    stream: str
    step_id: int | None
    line: str
    created_at: datetime


class ExecutionLogsResponse(BaseModel):
    items: list[ExecutionLogEntry]


# ── Routes ──────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=ExecutionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_execution(
    body: ExecutionCreate,
    subject: AuthSubject = Depends(current_subject),
    session: AsyncSession = Depends(get_session),
) -> ExecutionRead:
    """새 execution 을 ``queued`` 상태로 생성.

    M3.1.4: 쿠키 인증된 web user 도 호출 가능. 그 경우 사용자의 가장 최근
    ``last_seen_at`` agent 를 자동 선택 (revoked 제외). agent 가 없으면
    400 ``no_agent_available``.
    """
    if subject.agent_id is not None:
        # Bearer agent 인증 — 자기 자신 사용
        agent_id = subject.agent_id
    else:
        # Cookie 인증 — auto-select agent
        stmt = (
            select(Agent.id)
            .where(
                Agent.user_id == subject.user_id,
                Agent.revoked_at.is_(None),
            )
            .order_by(Agent.last_seen_at.desc().nulls_last())
            .limit(1)
        )
        agent_id = (await session.execute(stmt)).scalar_one_or_none()
        if agent_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "no_agent_available"},
            )

    execution = Execution(
        execution_id=_new_execution_id(),
        agent_id=agent_id,
        user_id=subject.user_id,
        status="queued",
        session_snapshot=body.session_snapshot,
        from_step=body.from_step,
        to_step=body.to_step,
    )
    session.add(execution)
    await session.commit()
    await session.refresh(execution)
    logger.info(
        "execution created: execution_id=%s agent_id=%s user_id=%s subject=%s",
        execution.execution_id, agent_id, subject.user_id, subject.kind,
    )

    # M2.3: 해당 agent 가 WS 로 붙어있으면 execution.start 를 push. 오프라인이면
    # 조용히 queued 로 유지 (catchup 은 M2.4+).
    ws = registry.get(agent_id)
    if ws is not None:
        frame = _build_start_frame(execution, body)
        try:
            await ws.send_json(frame)
            logger.info(
                "execution.start pushed: execution_id=%s agent_id=%s",
                execution.execution_id, agent_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "execution.start push failed (agent may have disconnected): %s",
                exc,
            )
    else:
        logger.info(
            "agent offline at POST time: execution_id=%s agent_id=%s — left queued",
            execution.execution_id, agent_id,
        )

    return ExecutionRead.model_validate(execution)


@router.get("/{execution_id}", response_model=ExecutionRead)
async def get_execution(
    execution_id: str,
    subject: AuthSubject = Depends(current_subject),
    session: AsyncSession = Depends(get_session),
) -> ExecutionRead:
    """단건 조회. 같은 ``user_id`` 의 row 만 반환, 아니면 404. 쿠키/Bearer 둘 다 허용."""
    stmt = select(Execution).where(
        Execution.execution_id == execution_id,
        Execution.user_id == subject.user_id,
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
    subject: AuthSubject = Depends(current_subject),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=LIST_LIMIT_DEFAULT, ge=1, le=LIST_LIMIT_MAX),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
) -> ExecutionListResponse:
    """같은 ``user_id`` 의 executions 를 최신순으로 리스트. 쿠키/Bearer 둘 다 허용."""
    if status_filter is not None and status_filter not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_status_filter"},
        )

    stmt = select(Execution).where(Execution.user_id == subject.user_id)
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


@router.get(
    "/{execution_id}/logs",
    response_model=ExecutionLogsResponse,
)
async def list_execution_logs(
    execution_id: str,
    subject: AuthSubject = Depends(current_subject),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=LOG_LIMIT_DEFAULT, ge=1, le=LOG_LIMIT_MAX),
    offset: int = Query(default=0, ge=0),
    stream: str | None = Query(default=None),
    step_id: int | None = Query(default=None, ge=1),
) -> ExecutionLogsResponse:
    """M2.4: ``execution_id`` 에 속한 로그를 ``seq ASC`` 순으로 반환.

    ``user_id`` 스코프 — execution 이 다른 user 소유면 404. 쿠키/Bearer 둘 다 허용 (M3.1.3).
    """
    if stream is not None and stream not in _ALLOWED_LOG_STREAMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_stream_filter"},
        )

    # execution 소유 검증: user_id 스코프 (detail GET 과 동일).
    owner_stmt = select(Execution).where(
        Execution.execution_id == execution_id,
        Execution.user_id == subject.user_id,
    )
    owner_result = await session.execute(owner_stmt)
    if owner_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "execution_not_found"},
        )

    stmt = select(ExecutionLog).where(ExecutionLog.execution_id == execution_id)
    if stream is not None:
        stmt = stmt.where(ExecutionLog.stream == stream)
    if step_id is not None:
        stmt = stmt.where(ExecutionLog.step_id == step_id)
    stmt = (
        stmt.order_by(ExecutionLog.seq.asc(), ExecutionLog.created_at.asc())
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(stmt)
    rows = result.scalars().all()
    return ExecutionLogsResponse(
        items=[ExecutionLogEntry.model_validate(r) for r in rows]
    )


# ── M2.5: Cancel ────────────────────────────────────────────────────────────


_TERMINAL_STATUSES_FOR_CANCEL = {"completed", "failed", "cancelled"}


class CancelResponse(BaseModel):
    execution_id: str
    accepted: bool


def _build_cancel_frame(execution_id: str) -> dict:
    return {
        "v": PROTOCOL_VERSION,
        "type": "execution.cancel",
        "id": str(uuid.uuid4()),
        "ts": _now_iso(),
        "payload": {"execution_id": execution_id},
    }


@router.post(
    "/{execution_id}/cancel",
    response_model=CancelResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_execution(
    execution_id: str,
    subject: AuthSubject = Depends(current_subject),
    session: AsyncSession = Depends(get_session),
) -> CancelResponse:
    """M2.5: 실행 중인 execution 을 에이전트에게 cancel 요청.

    서버 자체는 row 상태를 바꾸지 않는다. 에이전트가 ``execution.result`` 에
    ``status='cancelled'`` 로 응답해야 확정. 타임아웃·오프라인 등으로 에이전트가
    응답하지 않으면 row 는 running 인 채로 남는다 (이건 M2.6+ 에서 보강).

    M3.1.3: 쿠키 인증 사용자도 자기 user_id 의 execution 을 취소 가능.
    """
    stmt = select(Execution).where(
        Execution.execution_id == execution_id,
        Execution.user_id == subject.user_id,
    )
    execution = (await session.execute(stmt)).scalar_one_or_none()
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "execution_not_found"},
        )

    if execution.status in _TERMINAL_STATUSES_FOR_CANCEL:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "already_terminal", "status": execution.status},
        )

    ws = registry.get(execution.agent_id)
    if ws is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "agent_offline"},
        )

    frame = _build_cancel_frame(execution_id)
    try:
        await ws.send_json(frame)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "execution.cancel push failed: execution_id=%s agent_id=%s err=%s",
            execution_id, execution.agent_id, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "agent_offline"},
        ) from exc

    logger.info(
        "execution.cancel pushed: execution_id=%s agent_id=%s",
        execution_id, execution.agent_id,
    )
    return CancelResponse(execution_id=execution_id, accepted=True)
