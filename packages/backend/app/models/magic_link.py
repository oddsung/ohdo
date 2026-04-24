"""MagicLink 모델 — 일회성 이메일 로그인 토큰 (M3.1.1).

``POST /v0/auth/magic-link`` 시 row 생성. raw 토큰은 서버 로그 (dev stub) 또는
이메일 (M3.2+) 로 사용자에게 전달되고, 여기엔 hash 만 저장.

``GET /auth/verify`` 에서 hash 조회 → 만료/사용여부 체크 → 성공 시
``consumed_at`` 세팅 → user 생성/조회 + user_session 생성.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MagicLink(Base):
    __tablename__ = "magic_links"
    __table_args__ = (
        Index("magic_links_token_hash_idx", "token_hash", unique=True),
        Index("magic_links_email_idx", "email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
