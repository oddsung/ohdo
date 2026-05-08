# SPDX-License-Identifier: AGPL-3.0-or-later
"""도메인 모델 — Phase 1 sub-task 3 (5/8) Pydantic v2 승격.

ROADMAP §3 Phase 1 (3) — ``core.session_manager`` 의 dataclass (Session, Step,
Capture 등) 를 Pydantic v2 모델로 승격. 서버 API 응답 스키마로 재사용.

**비파괴 도입 정책** (옵션 B — parallel):

- 기존 dataclass (``core.session_manager.Session`` 등) 는 그대로 유지. 사용자
  JSON 데이터 (``data/sessions/<id>/session.json``) 와 모든 callers 무손상.
- 이 모듈의 Pydantic 모델은 **API 경계용** — Phase 2 의 FastAPI ``response_model`` /
  Pydantic validation / JSON Schema 생성에 사용.
- ``from_dataclass()`` / ``to_dataclass()`` helper 로 양방향 변환.
- 추후 (Phase 1.6+ 또는 Phase 2 진입) consolidate 검토 — 그때까지 두 표현 병행.

**모델 명명 규칙**:

- Pydantic 모델은 suffix ``Model`` (예: ``SessionModel``).
- dataclass 는 suffix 없이 (``Session``).
- 같은 이름의 양쪽 import 시 alias 권장 — ``from core.models import SessionModel``.

**JSON 호환성**:

- 모든 모델은 dataclass 와 동일한 필드 + 기본값 — ``model_dump()`` 결과 dict 가
  dataclass 의 ``asdict()`` 결과와 동일 구조 (round-trip 검증은 test_82).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

from pydantic import BaseModel, Field

from core.session_manager import (
    CaptureInfo,
    ConversationMessage,
    ExecutionResult,
    PromptLog,
    Session,
    SessionSummary,
    Step,
)

# ─────────────────────────────────────────────────────────
# 단일 필드 모델 (Capture / PromptLog / ExecutionResult / ConversationMessage)
# ─────────────────────────────────────────────────────────


class CaptureModel(BaseModel):
    """캡처 이미지 정보 (dataclass ``CaptureInfo`` 의 Pydantic 미러)."""

    type: str = "screen"
    path: str = ""
    timestamp: str = ""
    resolution: str = ""
    selector_info: Optional[dict] = None

    model_config = {"extra": "allow"}


class PromptLogModel(BaseModel):
    """AI 프롬프트/응답 로그 (dataclass ``PromptLog`` 의 Pydantic 미러)."""

    system_prompt: str = ""
    full_prompt: str = ""
    raw_response: str = ""
    tokens_used: int = 0
    response_time_ms: int = 0

    model_config = {"extra": "allow"}


class ExecutionResultModel(BaseModel):
    """코드 실행 결과 (dataclass ``ExecutionResult`` 의 Pydantic 미러)."""

    success: bool = False
    output: str = ""
    error: Optional[str] = None
    duration_ms: int = 0
    error_screenshot: Optional[str] = None

    model_config = {"extra": "allow"}


class ConversationMessageModel(BaseModel):
    """대화 메시지 (dataclass ``ConversationMessage`` 의 Pydantic 미러)."""

    role: str = ""
    content: str = ""
    timestamp: str = ""

    model_config = {"extra": "allow"}


# ─────────────────────────────────────────────────────────
# Step / Session
# ─────────────────────────────────────────────────────────


class StepModel(BaseModel):
    """워크플로우 step (dataclass ``Step`` 의 Pydantic 미러)."""

    step_id: int = 0
    status: str = "pending"
    created_at: str = ""
    conversation: list = Field(default_factory=list)
    generated_code: str = ""
    required_packages: list = Field(default_factory=list)
    captures: list = Field(default_factory=list)
    prompt_log: Optional[dict] = None
    execution_result: Optional[dict] = None
    step_code: str = ""
    step_imports: list = Field(default_factory=list)
    wait_after_ms: Optional[int] = None
    user_request: str = ""
    ai_description: str = ""

    model_config = {"extra": "allow"}


def _default_session_settings() -> dict:
    return {
        "ai_engine": "gemini_cli",
        "image_quality": 60,
        "step_delay_ms": None,
    }


def _default_workflow_metadata() -> dict:
    return {
        "total_steps": 0,
        "completed_steps": 0,
        "total_execution_time_ms": 0,
        "ai_total_tokens": 0,
        "run_count": 0,
    }


class SessionModel(BaseModel):
    """RPA 세션 (dataclass ``Session`` 의 Pydantic 미러).

    Phase 2 FastAPI 의 ``response_model=SessionModel`` 로 직접 사용 가능.
    JSON Schema 자동 생성 → OpenAPI 문서화 + 클라이언트 코드 생성에도 활용.
    """

    session_id: str = ""
    version: str = "2.0"
    created_at: str = ""
    updated_at: str = ""
    title: str = ""
    description: str = ""
    project_type: str = "desktop"
    settings: dict = Field(default_factory=_default_session_settings)
    steps: list = Field(default_factory=list)
    workflow_metadata: dict = Field(default_factory=_default_workflow_metadata)

    model_config = {"extra": "allow"}


class SessionSummaryModel(BaseModel):
    """세션 목록 요약 (dataclass ``SessionSummary`` 의 Pydantic 미러).

    dataclass 와 달리 default 없는 모든 필드가 Required — 목록 조회 응답 스키마
    로 활용 시 누락 차단.
    """

    session_id: str
    title: str
    description: str
    project_type: str
    created_at: str
    updated_at: str
    total_steps: int
    completed_steps: int

    model_config = {"extra": "allow"}


# ─────────────────────────────────────────────────────────
# Conversion helpers
# ─────────────────────────────────────────────────────────


# dataclass 클래스 → 대응하는 Pydantic 모델 매핑
_DATACLASS_TO_MODEL: dict[type, type[BaseModel]] = {
    CaptureInfo: CaptureModel,
    PromptLog: PromptLogModel,
    ExecutionResult: ExecutionResultModel,
    ConversationMessage: ConversationMessageModel,
    Step: StepModel,
    Session: SessionModel,
    SessionSummary: SessionSummaryModel,
}


# Pydantic 모델 → 대응하는 dataclass 매핑 (역방향)
_MODEL_TO_DATACLASS: dict[type[BaseModel], type] = {v: k for k, v in _DATACLASS_TO_MODEL.items()}


def from_dataclass(instance: Any) -> BaseModel:
    """dataclass 인스턴스 → 대응하는 Pydantic 모델 인스턴스 변환.

    Args:
        instance: ``Session`` / ``Step`` / ``CaptureInfo`` 등 dataclass 인스턴스.

    Returns:
        대응하는 Pydantic 모델 (``SessionModel`` 등).

    Raises:
        TypeError: ``instance`` 의 타입에 매핑된 모델이 없을 때.
    """
    cls = type(instance)
    model_cls = _DATACLASS_TO_MODEL.get(cls)
    if model_cls is None:
        raise TypeError(
            f"from_dataclass: {cls.__name__} 에 매핑된 Pydantic 모델 없음 — "
            f"core/models.py 에 추가 필요"
        )
    return model_cls(**asdict(instance))


def to_dataclass(model: BaseModel) -> Any:
    """Pydantic 모델 → 대응하는 dataclass 인스턴스 변환.

    내부 storage 가 dataclass 인 callers (``SessionManager`` 등) 와 호환되게
    Pydantic 모델을 다시 dataclass 로.
    """
    cls = type(model)
    dc_cls = _MODEL_TO_DATACLASS.get(cls)
    if dc_cls is None:
        raise TypeError(
            f"to_dataclass: {cls.__name__} 에 매핑된 dataclass 없음 — core/models.py 에 추가 필요"
        )
    return dc_cls(**model.model_dump())
