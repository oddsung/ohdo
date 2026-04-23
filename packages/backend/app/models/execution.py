"""Execution 모델 — 에이전트에서 실행된 RPA 세션 단위.

한 사용자가 특정 Agent 에 대해 실행을 지시하면 서버가 ``execution_id`` 를 발급,
에이전트가 받아 실행 → 진행 상황·결과를 다시 WS 로 보고한다.

상태 머신 (M2 전체 걸쳐 전이):
    queued → accepted → running → completed | failed | cancelled

M2.1 은 테이블만 추가한다. 실제 전이 로직·API 는 M2.2 이후.

상세 설계: docs/saas/architecture/08-m2.1-executions-schema.md
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Execution(Base, TimestampMixin):
    __tablename__ = "executions"
    __table_args__ = (
        Index("executions_execution_id_idx", "execution_id", unique=True),
        Index("executions_agent_id_idx", "agent_id"),
        Index("executions_user_id_idx", "user_id"),
        Index("executions_status_idx", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    # API 에 노출될 public id (``exec_`` prefix + opaque). 발급 로직은 M2.2.
    execution_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    agent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="queued", server_default="queued"
    )

    # Session dataclass → dict 직렬화 결과 전체. Postgres 는 JSONB, SQLite 는 TEXT.
    session_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    from_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_step: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ExecutionReport 집계값. M2.3 에서 업데이트.
    total_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    executed_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    successful_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
