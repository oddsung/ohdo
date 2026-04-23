"""Device Flow — Agent 가 호출하는 public 엔드포인트.

- ``POST /v0/agents/device_code`` — 새 device_code + user_code 발급
- ``POST /v0/agents/device_token`` — Agent 가 폴링. 승인되면 agent_token 발급.

자세한 설계: docs/saas/architecture/04-m1.2-device-flow.md
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import (
    generate_agent_token,
    generate_device_code,
    generate_user_code,
    hash_token,
)
from ..config import settings
from ..db import get_session
from ..models import Agent, DeviceCode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v0/agents", tags=["device-flow"])


class DeviceCodeRequest(BaseModel):
    agent_name: str | None = None
    hostname: str | None = None
    platform: str | None = None
    agent_version: str | None = None


class DeviceCodeResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int = Field(description="device_code 유효시간 (초)")
    interval: int = Field(description="Agent 권장 폴링 간격 (초)")


class DeviceTokenRequest(BaseModel):
    device_code: str


class DeviceTokenResponse(BaseModel):
    agent_token: str
    agent_id: str
    user_id: str


def _resolve_public_base_url(request: Request) -> str:
    """verification_uri 의 base 로 쓸 URL.

    우선순위: Settings.PUBLIC_BASE_URL > request.base_url.
    프록시 뒤 (Railway) 에서는 env 로 명시하는 것이 가장 안전.
    """
    if settings.PUBLIC_BASE_URL:
        return settings.PUBLIC_BASE_URL.rstrip("/")
    return str(request.base_url).rstrip("/")


async def _generate_unique_user_code(session: AsyncSession) -> str:
    """유일한 user_code 를 반환. 충돌은 극히 드물지만 (32^8 공간) 안전하게 재시도."""
    for _ in range(10):
        candidate = generate_user_code()
        existing = await session.execute(
            select(DeviceCode.id).where(DeviceCode.user_code == candidate)
        )
        if existing.scalar_one_or_none() is None:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="failed to allocate user_code",
    )


@router.post(
    "/device_code",
    response_model=DeviceCodeResponse,
    status_code=status.HTTP_200_OK,
)
async def create_device_code(
    body: DeviceCodeRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> DeviceCodeResponse:
    """Agent 의 Device Flow 시작 요청."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.DEVICE_CODE_TTL_SECONDS)

    user_code = await _generate_unique_user_code(session)
    device_code = generate_device_code()

    row = DeviceCode(
        device_code=device_code,
        user_code=user_code,
        status="pending",
        agent_name=body.agent_name,
        hostname=body.hostname,
        platform=body.platform,
        agent_version=body.agent_version,
        expires_at=expires_at,
        interval_seconds=settings.DEVICE_CODE_INTERVAL_SECONDS,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        # device_code 충돌은 사실상 불가능하지만 발생 시 500 대신 재시도 힌트.
        await session.rollback()
        logger.exception("device_code insert integrity error")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="please retry",
        )

    base = _resolve_public_base_url(request)
    verification_uri = f"{base}/link"
    verification_uri_complete = f"{verification_uri}?code={user_code}"

    return DeviceCodeResponse(
        device_code=device_code,
        user_code=user_code,
        verification_uri=verification_uri,
        verification_uri_complete=verification_uri_complete,
        expires_in=settings.DEVICE_CODE_TTL_SECONDS,
        interval=settings.DEVICE_CODE_INTERVAL_SECONDS,
    )


def _error(code: str) -> HTTPException:
    """RFC 8628 §3.5 에러 표준 형식으로 HTTPException 생성."""
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error": code},
    )


@router.post(
    "/device_token",
    response_model=DeviceTokenResponse,
    status_code=status.HTTP_200_OK,
)
async def exchange_device_token(
    body: DeviceTokenRequest,
    session: AsyncSession = Depends(get_session),
) -> DeviceTokenResponse:
    """Agent 가 폴링. 승인되었으면 agent_token 을 1 회 발급."""
    result = await session.execute(
        select(DeviceCode).where(DeviceCode.device_code == body.device_code)
    )
    dc: DeviceCode | None = result.scalar_one_or_none()

    if dc is None:
        raise _error("invalid_grant")

    now = datetime.now(timezone.utc)

    # SQLite 는 naive datetime 으로 돌아오는 경우가 있어 tz 보정.
    expires_at = dc.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if dc.status == "denied":
        raise _error("access_denied")

    if dc.consumed_at is not None:
        # 이미 한 번 교환됨 → 재사용 차단.
        raise _error("invalid_grant")

    if now >= expires_at:
        if dc.status != "expired":
            dc.status = "expired"
            await session.commit()
        raise _error("expired_token")

    if dc.status == "pending":
        raise _error("authorization_pending")

    if dc.status != "approved" or dc.user_id is None:
        raise _error("invalid_grant")

    # 승인됨 → agent_token 발급 + agents row 생성.
    token_plain = generate_agent_token()
    token_h = hash_token(token_plain)
    agent = Agent(
        user_id=dc.user_id,
        name=dc.agent_name,
        hostname=dc.hostname,
        platform=dc.platform,
        agent_version=dc.agent_version,
        token_hash=token_h,
    )
    session.add(agent)
    dc.consumed_at = now
    await session.commit()
    await session.refresh(agent)

    return DeviceTokenResponse(
        agent_token=token_plain,
        agent_id=str(agent.id),
        user_id=str(dc.user_id),
    )
