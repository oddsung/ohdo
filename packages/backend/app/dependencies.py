"""FastAPI 공용 dependency.

M1.4: ``current_agent`` — ``Authorization: Bearer ag_...`` 를 검증해 ``Agent``
ORM row 를 반환. 실패 시 401 (RFC 6750 스타일 ``WWW-Authenticate`` 헤더 포함).

M3.1.1: ``current_user`` — ``ohdo_session`` httpOnly 쿠키를 검증해 ``User``
ORM row 를 반환. 웹 브라우저 세션용.

M3.1.3: ``current_subject`` — 쿠키 또는 Bearer 둘 중 하나로 인증. read-only
엔드포인트가 web/agent 양쪽에서 호출 가능하게. 통합 키는 ``user_id``.

설계:
- docs/saas/architecture/06-m1.4-authenticated-ping.md
- docs/saas/architecture/18-m3.1.1-web-auth.md
- docs/saas/architecture/20-m3.1.3-executions-ui.md
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import AGENT_TOKEN_PREFIX, SESSION_TOKEN_PREFIX, hash_token
from .db import get_session
from .models import Agent, User, UserSession

SESSION_COOKIE_NAME = "ohdo_session"


def _extract_bearer_token(request: Request) -> str | None:
    """``Authorization: Bearer <token>`` 에서 토큰 추출. 없으면 ``None``."""
    header = request.headers.get("Authorization") or request.headers.get("authorization")
    if not header:
        return None
    parts = header.split(None, 1)  # 공백 1회 분리 — 여러 공백/탭도 허용
    if len(parts) != 2:
        return None
    scheme, value = parts
    if scheme.lower() != "bearer":
        return None
    token = value.strip()
    return token or None


def _unauthorized(error_code: str) -> HTTPException:
    """RFC 6750 §3.1 스타일 401. ``WWW-Authenticate`` 헤더로 에러 코드 노출."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": error_code},
        headers={"WWW-Authenticate": f'Bearer error="{error_code}"'},
    )


async def current_agent(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Agent:
    """인증 통과한 Agent ORM row 반환. 401 시 즉시 raise."""
    token = _extract_bearer_token(request)
    if token is None:
        raise _unauthorized("missing_token")
    if not token.startswith(AGENT_TOKEN_PREFIX):
        raise _unauthorized("malformed_token")

    token_h = hash_token(token)
    result = await session.execute(select(Agent).where(Agent.token_hash == token_h))
    agent: Agent | None = result.scalar_one_or_none()
    if agent is None:
        raise _unauthorized("invalid_token")
    if agent.revoked_at is not None:
        raise _unauthorized("token_revoked")

    return agent


# ── M3.1.1: 웹 사용자 세션 ──────────────────────────────────────────────────


def _session_unauthorized(error_code: str) -> HTTPException:
    """쿠키 기반 401. WWW-Authenticate 는 쿠키 인증엔 관용이 아니라 생략."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": error_code},
    )


async def current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """httpOnly 쿠키 ``ohdo_session`` 으로 사용자 인증. 실패 시 401.

    성공 시 ``UserSession.last_seen_at`` 을 now 로 갱신.
    """
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw:
        raise _session_unauthorized("not_authenticated")
    if not raw.startswith(SESSION_TOKEN_PREFIX):
        raise _session_unauthorized("not_authenticated")

    token_h = hash_token(raw)
    stmt = (
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == token_h)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise _session_unauthorized("not_authenticated")
    us: UserSession = row[0]
    user: User = row[1]

    now = datetime.now(timezone.utc)
    # tz-naive (SQLite) 대응: expires_at 이 naive 면 UTC 로 간주.
    expires_at = us.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if us.revoked_at is not None:
        raise _session_unauthorized("session_revoked")
    if expires_at <= now:
        raise _session_unauthorized("session_expired")

    us.last_seen_at = now
    await session.commit()
    return user


# ── M3.1.3: 합성 인증 (쿠키 OR Bearer) ─────────────────────────────────────


@dataclass(frozen=True)
class AuthSubject:
    """인증된 호출자 (agent 또는 web user).

    user_id 가 통합 스코프 키. agent_id 는 Bearer 로 인증됐을 때만 채워짐.
    """

    user_id: uuid.UUID
    agent_id: uuid.UUID | None
    kind: str  # "agent" | "user"


async def _try_cookie_user(
    request: Request, session: AsyncSession
) -> User | None:
    """쿠키 검증 silent 버전. 인증되면 User 반환, 아니면 None."""
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw or not raw.startswith(SESSION_TOKEN_PREFIX):
        return None
    token_h = hash_token(raw)
    stmt = (
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == token_h)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    us: UserSession = row[0]
    user: User = row[1]
    expires_at = us.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if us.revoked_at is not None or expires_at <= now:
        return None
    us.last_seen_at = now
    await session.commit()
    return user


async def _try_bearer_agent(
    request: Request, session: AsyncSession
) -> Agent | None:
    """Bearer 검증 silent 버전. 인증되면 Agent 반환, 아니면 None."""
    token = _extract_bearer_token(request)
    if token is None or not token.startswith(AGENT_TOKEN_PREFIX):
        return None
    token_h = hash_token(token)
    result = await session.execute(select(Agent).where(Agent.token_hash == token_h))
    agent: Agent | None = result.scalar_one_or_none()
    if agent is None or agent.revoked_at is not None:
        return None
    return agent


async def current_subject(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AuthSubject:
    """쿠키 → Bearer 순서로 시도. 둘 다 실패면 401."""
    user = await _try_cookie_user(request, session)
    if user is not None:
        return AuthSubject(user_id=user.id, agent_id=None, kind="user")

    agent = await _try_bearer_agent(request, session)
    if agent is not None:
        return AuthSubject(user_id=agent.user_id, agent_id=agent.id, kind="agent")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "not_authenticated"},
    )
