# SPDX-License-Identifier: AGPL-3.0-or-later
"""[Deprecated 2026-05-24] back-compat shim — ``core.adapters.cli_ai_adapter``
의 ``CliAIAdapter`` 가 본 어댑터의 후계자입니다.

이전 ``GeminiCLIAdapter`` 는 Gemini CLI 전용이었으나, Google 이 ``gemini`` 명령어
를 ``agy`` 로 rename + 사용자 요청으로 일반화 (handoff §36) → ``CliAIAdapter``
+ ``CLI_AI_PRESETS`` (agy / claude_code / codex / custom) 로 통합.

기존 import 경로 (``from core.adapters.gemini_cli_adapter import
GeminiCLIAdapter``) 는 그대로 동작 — 본 모듈이 alias 만 re-export.
"""

from __future__ import annotations

from .cli_ai_adapter import CliAIAdapter as GeminiCLIAdapter

__all__ = ["GeminiCLIAdapter"]
