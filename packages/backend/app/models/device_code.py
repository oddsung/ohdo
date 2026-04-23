"""Device Flow 임시 코드 저장 모델.

OAuth 2.0 Device Authorization Grant (RFC 8628) 의 간소화 구현.

- ``device_code``: Agent 가 폴링에 사용하는 opaque 토큰 (32B base32)
- ``user_code``: 사용자가 브라우저에 입력하는 짧은 코드 (``ABCD-1234``)
- ``status``: ``pending`` → ``approved`` → (``device_token`` 교환 후 ``consumed``
  상태는 ``consumed_at`` 으로 표현, 별도 값 없음) / ``expired`` / ``denied``

승인 시점에 ``user_id`` 가 채워진다. M1.2 stub 단계에서는 /link/approve 가
이메일만 받고 user 를 생성하거나 매핑한다 (상세: architecture/04-m1.2-device-flow.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class DeviceCode(Base, TimestampMixin):
    __tablename__ = "device_codes"
    __table_args__ = (
        Index("device_codes_device_code_idx", "device_code", unique=True),
        Index("device_codes_user_code_idx", "user_code", unique=True),
        Index("device_codes_status_idx", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    device_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default="pending"
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Agent 발급 요청 시 전달받는 메타 (승인 후 agents 테이블로 복사)
    agent_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    hostname: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_version: Mapped[str | None] = mapped_column(Text, nullable=True)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default="5"
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
