"""사용자 모델.

M1.1 에서는 필드 최소 구성. M1.2 에서 Device Flow 로 실제로 채워지고,
M4 의 결제/팀 기능 도입 시 확장된다.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
