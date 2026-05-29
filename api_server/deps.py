# SPDX-License-Identifier: AGPL-3.0-or-later
"""api_server 공용 의존성/헬퍼 (handoff §43 routes 분리).

server.py 의 거대 ``create_app`` 클로저에 흩어져 있던 공용 로직을 모듈 레벨로 추출.
라우터(``routes/*.py``)는 ``request.app.state`` / ``ws.app.state`` 를 통해 상태에
접근한다 (FastAPI 표준 패턴). **동작은 §38~§42 와 동일** — 위치만 이동.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel

# 프로젝트 루트 = api_server/ 의 부모. data/ + config/ 는 PySide6 앱과 공유한다.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = _PROJECT_ROOT / "data"
CONFIG_DIR = _PROJECT_ROOT / "config"


# ── 직렬화 헬퍼 ──────────────────────────────────────


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def to_dict(obj):
    """dataclass(또는 이미 dict) 를 JSON 직렬화 가능한 dict 로 변환."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    return obj


def step_result_dict(result) -> dict:
    """StepResult(또는 dict) 를 JSON 직렬화 가능한 dict 로 변환."""
    if hasattr(result, "to_dict"):
        try:
            return result.to_dict()
        except Exception:
            pass
    if dataclasses.is_dataclass(result) and not isinstance(result, type):
        d = dataclasses.asdict(result)
        return {k: d.get(k) for k in ("step_id", "success", "output", "error", "duration_ms")}
    return result if isinstance(result, dict) else {"result": str(result)}


# ── 요청 본문 스키마 ──────────────────────────────────


class CreateSessionRequest(BaseModel):
    title: str
    project_type: str = "desktop"
    description: str = ""


class GenerateRequest(BaseModel):
    user_request: str
    # element picker (handoff §40 #3) 로 잡은 element 컨텍스트 — 있으면 AI prompt 에 첨부.
    element_context: Optional[str] = None
    is_browser_element: bool = False


class UpdateStepRequest(BaseModel):
    """step 부분 갱신 — Monaco 편집 저장 (handoff §40 #2)."""

    generated_code: str


# ── AppService / 인증 / kernel / 녹화 컨트롤러 ─────────


def get_app_service(app):
    """AppService 를 lazy 로 생성/캐시한다 (``app.state.app_service``).

    config/settings.json (AI) + config/prompts.json (프롬프트) 를 로드해 AI 매니저 +
    PromptBuilder 를 주입한다. data/ 가 비어 있어도(첫 실행) 부팅 자체는 항상 성공한다.
    """
    if app.state.app_service is None:
        from core.app_service import AppService, PromptBuilder

        settings = load_json(CONFIG_DIR / "settings.json")
        service = AppService.create_default(data_dir=app.state.data_dir, settings=settings)
        if settings.get("ai"):
            service.reload_ai(settings)
        service.set_prompt_builder(PromptBuilder(load_json(CONFIG_DIR / "prompts.json")))
        app.state.app_service = service
    return app.state.app_service


def require_token(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_ohdo_token: Optional[str] = Header(default=None),
) -> None:
    """토큰 인증 의존성. 빈 토큰으로 생성된 앱은 인증을 건너뛴다."""
    expected = request.app.state.api_token
    if not expected:
        return  # 개발/테스트 모드 — 인증 비활성

    supplied = x_ohdo_token
    if not supplied and authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()

    if supplied != expected:
        raise HTTPException(status_code=401, detail="invalid or missing API token")


def get_recording_controller(app):
    """RecordingController lazy 생성 (메시지 펌프 전용 스레드 소유, handoff §42)."""
    if app.state.recording_controller is None:
        from api_server.recording_pump import RecordingController

        app.state.recording_controller = RecordingController(lambda: get_app_service(app))
    return app.state.recording_controller


def get_kernel(app, service, session_id: str):
    """세션별 ExecutionKernel lazy 생성 + 캐시 (ui_v2._get_or_create_kernel 패턴)."""
    kernel = app.state.kernels.get(session_id)
    if kernel is None:
        kernel = service.create_kernel()
        kernel.start()
        try:
            kernel.push_secrets()
        except Exception:
            pass
        app.state.kernels[session_id] = kernel
    return kernel


def drop_kernel(app, session_id: str) -> None:
    """캐시된 kernel 을 정리(stop)하고 제거."""
    kernel = app.state.kernels.pop(session_id, None)
    if kernel is not None:
        try:
            kernel.stop()
        except Exception:
            pass
