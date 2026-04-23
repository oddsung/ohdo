"""브라우저에서 사용자가 user_code 를 승인하는 /link 페이지.

- ``GET /link`` — 폼 렌더 (``?code=ABCD-1234`` 자동 입력)
- ``POST /link/approve`` — 제출을 받아 device_code 를 approved 로 마킹

M1.2 stub 흐름: email 만 받아 users 를 create-or-get. 이메일 소유 증명은
M2+ 에서 매직링크로 보강.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import normalize_user_code
from ..db import get_session
from ..models import DeviceCode, User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["link"])

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/link", response_class=HTMLResponse, name="link_page")
async def link_page(request: Request, code: str | None = None) -> HTMLResponse:
    """user_code 입력 폼."""
    prefilled = code or ""
    return templates.TemplateResponse(
        request,
        "link.html",
        {
            "prefilled_code": prefilled,
            "error": None,
        },
    )


async def _render_form_error(request: Request, code: str, error: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "link.html",
        {
            "prefilled_code": code,
            "error": error,
        },
        status_code=400,
    )


@router.post("/link/approve", response_class=HTMLResponse, name="link_approve")
async def link_approve(
    request: Request,
    user_code: str = Form(...),
    email: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """/link 폼 제출 처리.

    보안 메모: M1.2 stub. 이메일 소유 증명 없이 users 를 생성/매핑한다.
    M2 매직링크 도입 시 이 함수가 주요 이관 포인트.
    """
    normalized_code = normalize_user_code(user_code)
    email_clean = email.strip().lower()

    if not email_clean or "@" not in email_clean:
        return await _render_form_error(
            request, normalized_code, "올바른 이메일을 입력하세요."
        )

    result = await session.execute(
        select(DeviceCode).where(DeviceCode.user_code == normalized_code)
    )
    dc: DeviceCode | None = result.scalar_one_or_none()

    if dc is None:
        return await _render_form_error(
            request, normalized_code, "유효하지 않은 코드입니다."
        )

    now = datetime.now(timezone.utc)
    expires_at = dc.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if now >= expires_at:
        return await _render_form_error(
            request, normalized_code, "코드가 만료되었습니다. Agent 에서 다시 시도하세요."
        )
    if dc.status != "pending":
        return await _render_form_error(
            request, normalized_code, "이미 사용되었거나 사용할 수 없는 코드입니다."
        )

    # users: email 기준 get-or-create.
    user_result = await session.execute(
        select(User).where(User.email == email_clean)
    )
    user: User | None = user_result.scalar_one_or_none()
    if user is None:
        user = User(email=email_clean)
        session.add(user)
        await session.flush()  # id 확보
        logger.warning(
            "stub approval: creating user without email verification email=%s",
            email_clean,
        )
    else:
        logger.warning(
            "stub approval: linking existing user without email verification email=%s",
            email_clean,
        )

    dc.user_id = user.id
    dc.status = "approved"
    dc.approved_at = now
    await session.commit()

    return templates.TemplateResponse(
        request,
        "link_success.html",
        {
            "email": email_clean,
            "agent_name": dc.agent_name or dc.hostname or "Agent",
        },
    )
