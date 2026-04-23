"""Capture 업로드·조회 엔드포인트 (M2.6).

- ``POST /v0/executions/{execution_id}/captures`` — multipart 업로드.
  Bearer agent + user_id 스코프.
- ``GET /v0/executions/{execution_id}/captures`` — 메타데이터 리스트.
- ``GET /v0/captures/{capture_id}`` — 바이너리 다운로드.

실제 파일 바이트는 로컬 파일시스템에 저장한다 (S3/R2 는 차후 교체).
Railway 컨테이너 파일시스템은 ephemeral — 재배포 시 캡처 소실.

상세 설계: docs/saas/architecture/13-m2.6-captures-upload.md
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path as FPath,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..dependencies import current_agent
from ..models import Agent, Execution, ExecutionCapture

logger = logging.getLogger(__name__)

# ── 상수 ────────────────────────────────────────────────────────────────────

CAPTURE_ROOT = (
    Path(__file__).resolve().parent.parent.parent / "data" / "captures"
).resolve()

MAX_CAPTURE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
}
ALLOWED_KINDS: set[str] = {"error_screenshot"}
LIST_LIMIT_DEFAULT = 100
LIST_LIMIT_MAX = 500

_EXECUTION_ID_RE = re.compile(r"^exec_[a-f0-9]{32}$")


# ── 스키마 ──────────────────────────────────────────────────────────────────


class CaptureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    capture_id: uuid.UUID
    execution_id: str
    step_id: int | None
    kind: str
    content_type: str
    size_bytes: int
    created_at: datetime


class CaptureList(BaseModel):
    items: list[CaptureRead]


def _row_to_read(row: ExecutionCapture) -> CaptureRead:
    return CaptureRead(
        capture_id=row.id,
        execution_id=row.execution_id,
        step_id=row.step_id,
        kind=row.kind,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
    )


# ── 헬퍼 ────────────────────────────────────────────────────────────────────


def _validate_execution_id(execution_id: str) -> None:
    if not _EXECUTION_ID_RE.match(execution_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "execution_not_found"},
        )


async def _fetch_owned_execution(
    execution_id: str, agent: Agent, session: AsyncSession
) -> Execution:
    _validate_execution_id(execution_id)
    stmt = select(Execution).where(
        Execution.execution_id == execution_id,
        Execution.user_id == agent.user_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "execution_not_found"},
        )
    return row


def _storage_path(execution_id: str, capture_id: uuid.UUID, ext: str) -> Path:
    p = (CAPTURE_ROOT / execution_id / f"{capture_id}.{ext}").resolve()
    # path traversal 방어 — CAPTURE_ROOT 하위인지 재확인.
    try:
        p.relative_to(CAPTURE_ROOT)
    except ValueError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_path"},
        ) from exc
    return p


# ── 라우터: /v0/executions/{execution_id}/captures ─────────────────────────

exec_captures = APIRouter(prefix="/v0/executions", tags=["captures"])


@exec_captures.post(
    "/{execution_id}/captures",
    response_model=CaptureRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_capture(
    execution_id: str,
    file: UploadFile = File(...),
    step_id: int | None = Form(default=None),
    kind: str = Form(default="error_screenshot"),
    agent: Agent = Depends(current_agent),
    session: AsyncSession = Depends(get_session),
) -> CaptureRead:
    """스텝 실패 스크린샷 등 바이너리 업로드.

    multipart/form-data:
    - file: binary (image/png or image/jpeg), <= 10 MB
    - step_id: int (선택)
    - kind: "error_screenshot" (기본)
    """
    await _fetch_owned_execution(execution_id, agent, session)

    if kind not in ALLOWED_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_kind"},
        )

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"error": "unsupported_content_type", "got": content_type},
        )

    content = await file.read()
    size = len(content)
    if size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "empty_file"},
        )
    if size > MAX_CAPTURE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"error": "file_too_large", "max_bytes": MAX_CAPTURE_BYTES},
        )

    capture_id = uuid.uuid4()
    ext = ALLOWED_CONTENT_TYPES[content_type]
    path = _storage_path(execution_id, capture_id, ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_bytes(content)
    except OSError as exc:
        logger.exception("capture write failed: execution_id=%s", execution_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "storage_write_failed"},
        ) from exc

    storage_key = f"{execution_id}/{capture_id}.{ext}"
    row = ExecutionCapture(
        id=capture_id,
        execution_id=execution_id,
        step_id=step_id if isinstance(step_id, int) and step_id >= 1 else None,
        kind=kind,
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=size,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    logger.info(
        "capture uploaded: capture_id=%s execution_id=%s step_id=%s size=%dB",
        capture_id, execution_id, step_id, size,
    )
    return _row_to_read(row)


@exec_captures.get(
    "/{execution_id}/captures",
    response_model=CaptureList,
)
async def list_captures(
    execution_id: str,
    agent: Agent = Depends(current_agent),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=LIST_LIMIT_DEFAULT, ge=1, le=LIST_LIMIT_MAX),
    offset: int = Query(default=0, ge=0),
    step_id: int | None = Query(default=None, ge=1),
) -> CaptureList:
    """execution 의 캡처 메타데이터 리스트. 바이트는 GET /v0/captures/{id} 로."""
    await _fetch_owned_execution(execution_id, agent, session)

    stmt = select(ExecutionCapture).where(
        ExecutionCapture.execution_id == execution_id
    )
    if step_id is not None:
        stmt = stmt.where(ExecutionCapture.step_id == step_id)
    stmt = (
        stmt.order_by(ExecutionCapture.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return CaptureList(items=[_row_to_read(r) for r in rows])


# ── 라우터: /v0/captures/{capture_id} ───────────────────────────────────────

cap_router = APIRouter(prefix="/v0/captures", tags=["captures"])


@cap_router.get("/{capture_id}")
async def get_capture_bytes(
    capture_id: uuid.UUID = FPath(...),
    agent: Agent = Depends(current_agent),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """caption_id 의 바이너리 내려주기. user_id 스코프 (execution 소유자)."""
    stmt = (
        select(ExecutionCapture, Execution)
        .join(Execution, Execution.execution_id == ExecutionCapture.execution_id)
        .where(
            ExecutionCapture.id == capture_id,
            Execution.user_id == agent.user_id,
        )
    )
    res = (await session.execute(stmt)).first()
    if res is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "capture_not_found"},
        )
    capture, _execution = res

    # storage_key → 파일 경로.
    path = (CAPTURE_ROOT / capture.storage_key).resolve()
    try:
        path.relative_to(CAPTURE_ROOT)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "invalid_storage_key"},
        )
    if not path.is_file():
        # Railway ephemeral filesystem 에서 재배포 후 유실된 경우.
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"error": "capture_bytes_missing"},
        )

    try:
        content = path.read_bytes()
    except OSError as exc:
        logger.exception("capture read failed: capture_id=%s", capture_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "storage_read_failed"},
        ) from exc

    return Response(content=content, media_type=capture.content_type)
