"""User 정보 라우터 (M3.1.1).

현재: ``GET /v0/users/me`` — 쿠키 기반 인증된 사용자의 기본 정보 반환.

향후 확장 (M3.1.2+): 프로필 수정, 이메일 변경, etc.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from ..dependencies import current_user
from ..models import User

router = APIRouter(prefix="/v0/users", tags=["users"])


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    created_at: datetime


@router.get("/me", response_model=UserRead)
async def get_me(user: User = Depends(current_user)) -> UserRead:
    return UserRead.model_validate(user)
