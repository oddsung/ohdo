"""웹 사용자 인증 (매직링크 + 세션 쿠키) 라우터 (M3.1.1).

- ``POST /v0/auth/magic-link``: 이메일로 로그인 요청 → 서버가 magic_links row
  생성 후 dev stub 으로 INFO 로그에 verify URL 출력. 실 이메일 발송은 M3.2+.
- ``GET /auth/verify?token=...``: 매직링크 클릭 → 토큰 검증 → user get-or-create
  → user_sessions 생성 → httpOnly 쿠키 Set → ``/`` 로 302 redirect.
- ``POST /v0/auth/logout``: 쿠키의 세션을 revoke + 쿠키 clear (idempotent).

설계: docs/saas/architecture/18-m3.1.1-web-auth.md
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# 매우 느슨한 이메일 패턴 (RFC 완전 검증은 email-validator 필요; 여기선 XSS·빈값만 걸러냄).
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

from ..auth import generate_magic_token, generate_session_token, hash_token
from ..db import get_session
from ..dependencies import SESSION_COOKIE_NAME
from ..models import MagicLink, User, UserSession

logger = logging.getLogger(__name__)

# dev/prod 구분 — Secure 쿠키는 HTTPS 에서만. OHDO_ENV=production 일 때만 Secure.
_ENV = os.getenv("OHDO_ENV", "development").lower()
_COOKIE_SECURE = _ENV == "production"

MAGIC_TTL_SECONDS = 15 * 60
SESSION_TTL_DAYS = 30

router = APIRouter(tags=["auth"])

# /v0/auth/* 용 (JSON API)
v0_router = APIRouter(prefix="/v0/auth", tags=["auth"])


# ── 스키마 ──────────────────────────────────────────────────────────────────


class MagicLinkRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email")
        return v


class MagicLinkResponse(BaseModel):
    email: str
    expires_in: int


# ── 헬퍼 ────────────────────────────────────────────────────────────────────


def _normalize_email(raw: str) -> str:
    return raw.strip().lower()


def _resolve_public_base_url(request: Request) -> str:
    """verify 링크의 호스트를 결정. Railway 환경에서 자동 주입되는
    RAILWAY_PUBLIC_DOMAIN 을 우선 참고 (M1.2 와 동일 폴백 체인)."""
    public = os.getenv("PUBLIC_BASE_URL")
    if public:
        return public.rstrip("/")
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if railway_domain:
        scheme = "https" if not railway_domain.startswith("localhost") else "http"
        return f"{scheme}://{railway_domain}"
    return str(request.base_url).rstrip("/")


def _set_session_cookie(response: Response, raw_token: str, max_age_seconds: int) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=max_age_seconds,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )


# ── 라우트 ──────────────────────────────────────────────────────────────────


@v0_router.post(
    "/magic-link",
    response_model=MagicLinkResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_magic_link(
    body: MagicLinkRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> MagicLinkResponse:
    """매직링크 요청. dev 에선 INFO 로그에 verify URL 출력."""
    email = _normalize_email(body.email)
    raw_token = generate_magic_token()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=MAGIC_TTL_SECONDS)

    link = MagicLink(
        email=email,
        token_hash=hash_token(raw_token),
        expires_at=expires_at,
    )
    session.add(link)
    await session.commit()

    base = _resolve_public_base_url(request)
    verify_url = f"{base}/auth/verify?token={raw_token}"
    logger.warning(
        "[MAGIC LINK] dev stub — deliver this to user %s:\n%s",
        email, verify_url,
    )

    return MagicLinkResponse(email=email, expires_in=MAGIC_TTL_SECONDS)


@router.get("/auth/verify")
async def verify_magic_link(
    token: str | None = None,
    session: AsyncSession = Depends(get_session),
    request: Request = None,  # type: ignore[assignment]
):
    """매직링크 클릭 시 호출되는 엔드포인트. user 생성/조회 + 세션 쿠키 발급."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "missing_token"},
        )

    token_h = hash_token(token)
    now = datetime.now(timezone.utc)

    stmt = select(MagicLink).where(MagicLink.token_hash == token_h)
    link: MagicLink | None = (await session.execute(stmt)).scalar_one_or_none()
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_or_expired_token"},
        )
    if link.consumed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_or_expired_token"},
        )
    expires_at = link.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_or_expired_token"},
        )

    # users get-or-create
    u_stmt = select(User).where(User.email == link.email)
    user: User | None = (await session.execute(u_stmt)).scalar_one_or_none()
    if user is None:
        user = User(email=link.email)
        session.add(user)
        await session.flush()
        logger.info("magic-link: created new user email=%s", link.email)
    else:
        logger.info("magic-link: existing user email=%s", link.email)

    # 세션 토큰 발급
    raw_session = generate_session_token()
    us = UserSession(
        user_id=user.id,
        token_hash=hash_token(raw_session),
        expires_at=now + timedelta(days=SESSION_TTL_DAYS),
        user_agent=(request.headers.get("user-agent") if request else None),
    )
    session.add(us)

    # 매직링크 소모 마킹
    link.consumed_at = now

    await session.commit()

    # 302 redirect + 쿠키 Set
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    _set_session_cookie(response, raw_session, SESSION_TTL_DAYS * 24 * 3600)
    return response


@v0_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """쿠키가 있으면 세션 revoke. 없어도 204 (idempotent)."""
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if raw:
        token_h = hash_token(raw)
        stmt = select(UserSession).where(UserSession.token_hash == token_h)
        us: UserSession | None = (await session.execute(stmt)).scalar_one_or_none()
        if us is not None and us.revoked_at is None:
            us.revoked_at = datetime.now(timezone.utc)
            await session.commit()
    _clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
