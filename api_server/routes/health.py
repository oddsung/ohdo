# SPDX-License-Identifier: AGPL-3.0-or-later
"""헬스 체크 (handoff §38). 인증 불필요 — Electron 부팅 readiness 폴링용."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict:
    """인증 불필요. Electron 부팅 readiness 폴링 + 헬스 체크."""
    return {
        "status": "ok",
        "service": "ohdo-desktop_v3-bridge",
        "version": "0.2.0",
        "auth_required": bool(request.app.state.api_token),
    }
