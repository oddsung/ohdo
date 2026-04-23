"""FastAPI 공용 dependency.

M1.4: ``current_agent`` — ``Authorization: Bearer ag_...`` 를 검증해 ``Agent``
ORM row 를 반환. 실패 시 401 (RFC 6750 스타일 ``WWW-Authenticate`` 헤더 포함).

설계: docs/saas/architecture/06-m1.4-authenticated-ping.md
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import AGENT_TOKEN_PREFIX, hash_token
from .db import get_session
from .models import Agent


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
