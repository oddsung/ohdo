"""ExecutionLog 모델 — 한 execution 의 로그 라인 한 줄 (M2.4).

에이전트가 ``execution.log`` 프레임으로 묶어 보낸 entries 가 여기서 row-per-line
으로 저장된다. ``execution_id`` 로 조인 (Text FK, executions.execution_id 는
unique).

상세 설계: docs/saas/architecture/11-m2.4-execution-log.md
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ExecutionLog(Base):
    __tablename__ = "execution_logs"
    __table_args__ = (
        Index("execution_logs_execution_id_idx", "execution_id"),
        Index(
            "execution_logs_execution_id_seq_idx",
            "execution_id",
            "seq",
        ),
        Index("execution_logs_stream_idx", "stream"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    execution_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("executions.execution_id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    step_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stream: Mapped[str] = mapped_column(Text, nullable=False)
    line: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
