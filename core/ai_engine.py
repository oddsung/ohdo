# SPDX-License-Identifier: AGPL-3.0-or-later
"""
AI 엔진 매니저

팩토리 패턴으로 다중 AI 엔진을 관리합니다.
설정에 따라 적절한 어댑터를 선택하고 전환할 수 있습니다.
"""

import logging
from typing import Optional

from .adapters.base_adapter import AIResponse, BaseAIAdapter
from .adapters.cli_ai_adapter import CliAIAdapter, migrate_ai_settings
from .adapters.gemini_cli_adapter import GeminiCLIAdapter
from .adapters.openai_compat_adapter import OpenAICompatAdapter

logger = logging.getLogger(__name__)


# 2026-05-24 (handoff §36): _migrate_ai_settings 는 core.adapters.cli_ai_adapter
# 의 ``migrate_ai_settings`` 로 이동 (UI 가 ``core.ai_engine`` 직접 import 못 함 —
# ui-core KPI). 본 모듈에는 back-compat alias 만 유지.
_migrate_ai_settings = migrate_ai_settings


class AIEngineManager:
    """
    AI 엔진 팩토리/매니저.

    사용법:
        manager = AIEngineManager(settings)
        adapter = manager.get_adapter()
        response = await adapter.generate("코드를 생성해줘")
    """

    # 등록된 어댑터 클래스 매핑
    # 2026-05-24: "cli_ai" 신규 (CliAIAdapter, 일반 CLI AI — agy/claude_code/codex/custom)
    # "gemini_cli" 는 back-compat alias (구 settings.json 직접 로드 시) — 마이그레이션
    # 안 거친 path 에서도 안전. _migrate_ai_settings 가 settings 단계에서 변환.
    ADAPTER_REGISTRY = {
        "cli_ai": CliAIAdapter,
        "gemini_cli": GeminiCLIAdapter,  # alias of CliAIAdapter (back-compat)
        "openai_compat": OpenAICompatAdapter,
    }

    def __init__(self, settings: dict):
        """
        Args:
            settings: settings.json의 전체 설정 딕셔너리
        """
        self.settings = settings
        self.ai_settings = _migrate_ai_settings(settings.get("ai", {}))
        self._current_name = self.ai_settings.get("selected", "cli_ai")
        self._adapters: dict[str, BaseAIAdapter] = {}
        self._initialize_adapters()

    def _initialize_adapters(self):
        """등록된 모든 어댑터를 초기화합니다."""
        engines = self.ai_settings.get("available_engines", {})
        for name, adapter_cls in self.ADAPTER_REGISTRY.items():
            engine_config = engines.get(name, {})
            try:
                self._adapters[name] = adapter_cls(engine_config)
                logger.info(f"AI 어댑터 초기화: {name}")
            except Exception as e:
                logger.warning(f"AI 어댑터 초기화 실패 ({name}): {e}")

    def get_adapter(self) -> BaseAIAdapter:
        """현재 선택된 AI 어댑터를 반환합니다."""
        if self._current_name not in self._adapters:
            raise RuntimeError(
                f"AI 어댑터 '{self._current_name}'를 찾을 수 없습니다. "
                f"사용 가능: {list(self._adapters.keys())}"
            )
        return self._adapters[self._current_name]

    def get_current_name(self) -> str:
        """현재 선택된 AI 엔진 이름을 반환합니다."""
        return self._current_name

    def switch_engine(self, name: str):
        """
        다른 AI 엔진으로 전환합니다.

        Args:
            name: 전환할 엔진 이름 (예: "cli_ai", "openai_compat", legacy "gemini_cli")
        """
        if name not in self._adapters:
            raise ValueError(
                f"알 수 없는 AI 엔진: '{name}'. 사용 가능: {list(self._adapters.keys())}"
            )
        self._current_name = name
        logger.info(f"AI 엔진 전환: {name}")

    def list_available(self) -> list[dict]:
        """
        사용 가능한 AI 엔진 목록을 반환합니다.

        Returns:
            [{"name": "cli_ai", "display_name": "...", "available": True}, ...]
        """
        result = []
        for name, adapter in self._adapters.items():
            result.append(
                {
                    "name": name,
                    "display_name": adapter.get_name(),
                    "available": adapter.is_available(),
                    "is_current": name == self._current_name,
                }
            )
        return result

    def cancel(self) -> None:
        """진행 중인 AI 요청을 취소합니다."""
        try:
            self.get_adapter().cancel()
        except Exception:
            pass

    async def generate(
        self,
        prompt: str,
        images: Optional[list[str]] = None,
        system: Optional[str] = None,
    ) -> AIResponse:
        """
        현재 선택된 AI 엔진으로 코드를 생성합니다.

        Args:
            prompt: 프롬프트 텍스트 (user 메시지)
            images: 이미지 파일 경로 목록
            system: 시스템 가이드 (P1b). OpenAI 호환 어댑터는 system role 로
                분리, Gemini CLI 는 prompt 앞에 prepend.

        Returns:
            AIResponse
        """
        adapter = self.get_adapter()
        logger.debug(f"AI 요청 전송 ({adapter.get_name()}): {prompt[:100]}...")
        response = await adapter.generate(prompt, images, system=system)

        if response.success:
            logger.info(
                f"AI 응답 수신 ({response.response_time_ms}ms, 코드 {len(response.code)}자)"
            )
        else:
            logger.error(f"AI 응답 실패: {response.error}")

        return response
