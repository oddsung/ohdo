# SPDX-License-Identifier: AGPL-3.0-or-later
"""설정 레이어 — Phase 1 sub-task 4 (5/8).

ROADMAP §3 Phase 1 (4) — ``config/settings.json`` 의 dict 기반 설정을 Pydantic v2
``Settings`` 모델로 승격. ``.env`` 환경변수 병합. UI/core 가 타입 안전한
객체로 접근 가능.

**비파괴 도입 정책**:

- 기존 callers (``_load_settings() -> dict`` 패턴) 는 유지. ``load_settings_dict``
  helper 가 동일한 dict 를 반환하므로 점진적 migration 가능.
- 새 코드는 ``load_settings() -> Settings`` (typed) 사용 권장.
- Phase 2 (backend) 는 같은 ``Settings`` 모델을 FastAPI 의존성 주입에 활용.

**환경변수 override 규칙** (Pydantic Settings):

- Prefix: ``OHDO_``
- Nested: ``__`` (double underscore)
- 예: ``OHDO_AI__SELECTED=openai_compat`` → ``settings.ai.selected``
- 예: ``OHDO_EXECUTION__STEP_DELAY_MS=2000`` → ``settings.execution.step_delay_ms``

JSON 파일의 값보다 환경변수가 우선. ``.env`` 파일도 자동 로드.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# 섹션별 모델 — settings.json 의 각 top-level 키
# ─────────────────────────────────────────────────────────


class AIEngineConfig(BaseModel):
    """단일 AI 엔진 설정 — gemini_cli, openai_compat 등 다양한 형태 cover.

    공통 필드는 명시, 엔진별 추가 필드는 ``extra="allow"`` 로 보존.
    """

    # 공통
    timeout_seconds: int = 180
    max_retries: int = 3
    model: str = ""
    # gemini_cli 전용
    command: Optional[str] = None
    flags: Optional[str] = None
    # openai_compat 전용
    preset: Optional[str] = None
    base_url: Optional[str] = None
    api_key: str = ""
    api_key_env: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None

    model_config = {"extra": "allow"}


class AISettings(BaseModel):
    selected: str = "gemini_cli"
    available_engines: dict[str, AIEngineConfig] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class ImageSettings(BaseModel):
    capture_quality: int = 60
    max_width: int = 1280
    format: str = "jpeg"
    grayscale_for_ai: bool = False

    model_config = {"extra": "allow"}


class RecognitionSettings(BaseModel):
    preferred_methods: list[str] = Field(
        default_factory=lambda: ["dom", "automation_id", "ocr", "image_match"]
    )
    ocr_language: str = "kor+eng"
    image_match_confidence: float = 0.8

    model_config = {"extra": "allow"}


class ExecutionSettings(BaseModel):
    step_delay_ms: int = 1000
    max_retry_count: int = 3
    retry_delay_ms: int = 1000
    screenshot_on_error: bool = True
    sandbox_mode: bool = True

    model_config = {"extra": "allow"}


class VisualFeedbackSettings(BaseModel):
    enabled: bool = True

    model_config = {"extra": "allow"}


class UISettings(BaseModel):
    theme: str = "light"
    console_visible: bool = False
    font_size: int = 13
    language: str = "ko"
    sidebar_collapsed: bool = False
    onboarding_done: bool = True

    model_config = {"extra": "allow"}


class OutputProjectSettings(BaseModel):
    default_output_dir: str = ""
    auto_readme: bool = True
    auto_requirements: bool = True
    auto_venv_guide: bool = True
    include_run_script: bool = True
    readme_language: str = "ko"

    model_config = {"extra": "allow"}


class LoggingSettings(BaseModel):
    level: str = "INFO"
    file_enabled: bool = True
    max_log_size_mb: int = 50
    rotation_days: int = 30

    model_config = {"extra": "allow"}


class HintsSettings(BaseModel):
    cdp_browser_hint_dismissed: bool = False

    model_config = {"extra": "allow"}


class ElementPickerSettings(BaseModel):
    uia_max_depth: int = 10
    uia_time_budget_ms: int = 150
    cdp_enabled: bool = False

    model_config = {"extra": "allow"}


# ─────────────────────────────────────────────────────────
# 최상위 Settings 모델
# ─────────────────────────────────────────────────────────


class Settings(BaseSettings):
    """ohdo 전체 설정 — JSON + .env + 환경변수 병합.

    우선순위 (높음 → 낮음):

    1. 환경변수 (``OHDO_AI__SELECTED`` 등)
    2. ``.env`` 파일
    3. JSON 초기값 (``Settings(**json_data)`` 의 init kwargs)
    4. 모델 default

    Pydantic Settings v2 의 기본은 init_kwargs > env_vars 이지만, ohdo 는
    "런타임에 env var 로 settings.json 을 override 가능" 정책이라 source 순서 swap.
    """

    ai: AISettings = Field(default_factory=AISettings)
    image: ImageSettings = Field(default_factory=ImageSettings)
    recognition: RecognitionSettings = Field(default_factory=RecognitionSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    visual_feedback: VisualFeedbackSettings = Field(default_factory=VisualFeedbackSettings)
    ui: UISettings = Field(default_factory=UISettings)
    output_project: OutputProjectSettings = Field(default_factory=OutputProjectSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    hints: HintsSettings = Field(default_factory=HintsSettings)
    element_picker: ElementPickerSettings = Field(default_factory=ElementPickerSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="OHDO_",
        env_nested_delimiter="__",
        extra="allow",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,  # noqa: ARG003
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """source 우선순위: env > dotenv > init (JSON) > secrets > defaults.

        Pydantic Settings v2 default 인 init > env 를 swap — settings.json 의
        값이 ``OHDO_*`` 환경변수로 override 가능해야 함 (CI, Docker, 사용자 .env).
        """
        return (env_settings, dotenv_settings, init_settings, file_secret_settings)


# ─────────────────────────────────────────────────────────
# Loaders
# ─────────────────────────────────────────────────────────


_DEFAULT_SETTINGS_PATH = Path(__file__).parent.parent / "config" / "settings.json"


def load_settings(
    settings_path: Optional[Path] = None,
    *,
    env_file: Optional[Path] = None,
) -> Settings:
    """JSON 파일 + 환경변수 병합한 ``Settings`` 인스턴스 반환.

    Args:
        settings_path: ``settings.json`` 경로. ``None`` 이면 ``config/settings.json``.
            파일 없으면 default 값으로 ``Settings()`` 반환.
        env_file: ``.env`` 경로 (override). ``None`` 이면 model_config 의 default.

    Returns:
        ``Settings`` 인스턴스 (typed access).
    """
    path = settings_path if settings_path is not None else _DEFAULT_SETTINGS_PATH

    json_data: dict[str, Any] = {}
    if path.exists():
        try:
            json_data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("settings.json 로드 실패 (%s): %s — default 값 사용", path, e)

    # Pydantic Settings 가 환경변수를 자동으로 우선 적용. JSON 값은 init kwargs.
    if env_file is not None:
        # env_file override — 테스트에서 임시 .env 사용 시
        return Settings(_env_file=str(env_file), **json_data)  # type: ignore[call-arg]
    return Settings(**json_data)


def load_settings_dict(settings_path: Optional[Path] = None) -> dict[str, Any]:
    """레거시 호환 — dict 반환.

    기존 ``_load_settings()`` 패턴을 점진 마이그레이션할 때 사용.
    내부적으로는 ``Settings`` 모델로 검증한 후 ``model_dump()`` 로 dict 변환.
    """
    return load_settings(settings_path).model_dump()


def save_settings(settings: Settings, settings_path: Optional[Path] = None) -> None:
    """``Settings`` 인스턴스를 JSON 파일로 저장 (디스크에 영속).

    환경변수 override 는 영속화 X — JSON 에는 모델 값만 기록. ``.env`` 는 사용자가
    별도 관리.
    """
    path = settings_path if settings_path is not None else _DEFAULT_SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = settings.model_dump()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.debug("settings.json 저장: %s", path)
