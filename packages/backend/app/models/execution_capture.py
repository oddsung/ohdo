"""ExecutionCapture 모델 — 스텝 실패 시 저장된 스크린샷 등 캡처 바이너리 메타 (M2.6).

바이너리 자체는 로컬 파일시스템 ``{backend_root}/data/captures/{execution_id}/{id}.{ext}``
에 저장된다. 향후 S3/R2 로 교체 시 ``storage_key`` 해석만 바꾸면 됨.

상세 설계: docs/saas/architecture/13-m2.6-captures-upload.md
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ExecutionCapture(Base):
    __tablename__ = "execution_captures"
    __table_args__ = (
        Index("execution_captures_execution_id_idx", "execution_id"),
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
    step_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, default="error_screenshot",
        server_default="error_screenshot",
    )
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
