# SPDX-License-Identifier: AGPL-3.0-or-later
"""
일반 CLI AI 어댑터 — 2026-05-24 (handoff §36).

이전 ``gemini_cli_adapter`` 의 일반화 버전. preset 선택 또는 custom command 로
다양한 CLI AI 도구 지원: Agy (구 Gemini), Claude Code, OpenAI Codex CLI 등.

특징:
- ``subprocess`` 로 직접 호출 (PowerShell 우회)
- stdin pipe 로 프롬프트 전달 + 짧은 프롬프트는 prompt-as-arg fallback
- 이미지 첨부 (``@"path"`` 참조 prepend, Agy 호환 — 다른 preset 도 시도)
- model flag 가변 (``-m`` / ``--model`` 등 preset 별 다름)

기존 ``GeminiCLIAdapter`` 는 본 클래스의 alias 로 유지 (back-compat).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base_adapter import AIResponse, BaseAIAdapter

# ── CLI AI 프리셋 ─────────────────────────────────────────────
#
# 각 preset 은 명령어 + 모델 flag 형식 + 기본 모델 + 표시 라벨 정의. 사용자는
# Settings 다이얼로그에서 preset 선택 → command / model 자동 채움 (수동 override
# 가능). custom preset 은 사용자가 직접 command/args 입력.
#
# 추가하려면 새 preset entry 만 등록 — 어댑터 코드 수정 불필요.

CLI_AI_PRESETS: dict[str, dict] = {
    "agy": {
        "display_name": "Agy CLI (구 Gemini)",
        "command": "agy",
        "model_arg": "-m",
        "model": "agy-3.1-pro",
        "prompt_arg": "-p",  # 짧은 prompt 인자 모드 fallback
        "supports_images": True,  # @"path" 참조 prepend 시도
    },
    "claude_code": {
        "display_name": "Claude Code (Anthropic)",
        "command": "claude",
        "model_arg": "--model",
        "model": "claude-opus-4-7",
        "prompt_arg": "-p",
        "supports_images": False,
    },
    "codex": {
        "display_name": "OpenAI Codex CLI",
        "command": "codex",
        "model_arg": "--model",
        "model": "gpt-5-codex",
        "prompt_arg": None,  # stdin 만 — prompt-as-arg 미지원
        "supports_images": False,
    },
}

_DEFAULT_PRESET = "agy"


def migrate_ai_settings(ai_settings: dict) -> dict:
    """[handoff §36 2026-05-24] 구 settings 를 새 구조로 자동 마이그레이션.

    - ``selected="gemini_cli"`` → ``"cli_ai"`` (새 default 엔진 키)
    - ``available_engines["gemini_cli"]`` → ``available_engines["cli_ai"]`` (없을 때만 신규)
    - ``command="gemini"`` → ``"agy"`` (Google rename)
    - ``preset`` 미명시 시 ``"agy"`` 채움

    원본 변형 X — 새 dict 반환. UI / AIEngineManager 양쪽에서 호출 가능 (UI 가
    ``core.ai_engine`` 직접 import 못 함 — ui-core KPI). 본 모듈 (``core.adapters.*``)
    은 banned 목록 제외.
    """
    import logging as _logging

    logger = _logging.getLogger(__name__)

    migrated = dict(ai_settings)
    engines = dict(migrated.get("available_engines", {}))

    legacy = engines.get("gemini_cli")
    if legacy and "cli_ai" not in engines:
        cli_cfg = dict(legacy)
        if cli_cfg.get("command") == "gemini":
            logger.info("AI settings migration: command 'gemini' → 'agy' (handoff §36)")
            cli_cfg["command"] = "agy"
        cli_cfg.setdefault("preset", "agy")
        engines["cli_ai"] = cli_cfg
        migrated["available_engines"] = engines

    if migrated.get("selected") == "gemini_cli":
        logger.info("AI settings migration: selected 'gemini_cli' → 'cli_ai' (handoff §36)")
        migrated["selected"] = "cli_ai"

    return migrated


def _resolve_preset_config(config: dict) -> dict:
    """config 의 ``preset`` 키 기준으로 CLI_AI_PRESETS 의 default 값을 채움.

    사용자가 명시한 값 (config 의 ``command`` / ``model`` 등) 이 preset default 보다
    우선. ``preset == "custom"`` 또는 unknown 이면 default 채움 안 함.

    **Back-compat 정책** (handoff §36): ``preset`` 키가 config 에 명시 안 됨 → preset
    defaults 적용 안 함 (raw config 그대로). 이전 ``GeminiCLIAdapter({"command":
    "gemini"})`` 같이 model 미명시 호출을 그대로 보존 (model="" → ``-m`` flag 미추가).
    Settings UI 는 항상 ``preset`` 키를 명시 전달 → 신규 path 는 preset default 활용.
    """
    if "preset" not in config:
        # 명시 preset 없음 → raw config 그대로 (GeminiCLIAdapter back-compat)
        return dict(config)
    preset_name = (config.get("preset") or "").strip().lower()
    if not preset_name or preset_name == "custom":
        return dict(config)
    preset = CLI_AI_PRESETS.get(preset_name)
    if preset is None:
        # unknown preset — config 그대로 사용 (사용자 입력 보존)
        return dict(config)
    merged = dict(preset)
    merged.update({k: v for k, v in config.items() if v not in (None, "")})
    return merged


class CliAIAdapter(BaseAIAdapter):
    """일반 CLI AI 어댑터.

    Config 필드:
    - ``preset``: ``"agy" | "claude_code" | "codex" | "custom"``. preset 선택 시
      command / model / model_arg / prompt_arg 자동 채움 (config 명시값이 override).
    - ``command``: 실행 binary 이름 (예: ``"agy"``, ``"claude"``, ``"codex"``).
    - ``model``: 모델 이름 (preset default 사용 가능).
    - ``model_arg``: 모델 전달 flag (예: ``"-m"`` 또는 ``"--model"``).
    - ``prompt_arg``: 짧은 prompt 를 인자로 전달할 flag (None 이면 stdin 만).
    - ``timeout_seconds`` (default 180), ``max_retries`` (default 3).
    - ``extra_args``: ``list[str]`` — 사용자 추가 flag (preset 후 append).
    """

    def __init__(self, config: dict):
        super().__init__(config)
        merged = _resolve_preset_config(config)
        self.preset = (config.get("preset") or _DEFAULT_PRESET).strip().lower()
        self.command = merged.get("command", "agy")
        self.timeout = int(merged.get("timeout_seconds", 180))
        self.max_retries = int(merged.get("max_retries", 3))
        self.model = merged.get("model", "")
        self.model_arg = merged.get("model_arg", "-m")
        self.prompt_arg = merged.get("prompt_arg", "-p")
        self.extra_args = list(merged.get("extra_args", []) or [])
        self.supports_images = bool(merged.get("supports_images", False))
        self._proc: Optional[subprocess.Popen] = None
        self._cancelled: bool = False

    def _build_args(self, cli_exec: str, *extra: str) -> list:
        """CLI 실행 인자 빌드. model + extra_args + 호출자 추가 인자 합본."""
        args = [cli_exec]
        if self.model and self.model_arg:
            args.extend([self.model_arg, self.model])
        if self.extra_args:
            args.extend(self.extra_args)
        args.extend(extra)
        return args

    def cancel(self) -> None:
        """진행 중인 CLI 프로세스 강제 종료."""
        self._cancelled = True
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    def get_name(self) -> str:
        preset_meta = CLI_AI_PRESETS.get(self.preset)
        if preset_meta:
            return preset_meta["display_name"]
        return f"CLI AI ({self.command})"

    def is_available(self) -> bool:
        """command 가 PATH 에 존재하는지 확인 (실 호출 없음)."""
        return shutil.which(self.command) is not None

    async def generate(
        self,
        prompt: str,
        images: Optional[list[str]] = None,
        system: Optional[str] = None,
    ) -> AIResponse:
        """CLI AI 호출 → AIResponse 반환.

        - system role 있으면 prompt 앞에 prepend (대부분 CLI 가 role 분리 미지원).
        - 이미지: ``supports_images=True`` preset 만 ``@"path"`` 참조 prepend 시도.
        - stdin pipe 우선, 실패 시 ``prompt_arg`` 가 있으면 prompt-as-arg fallback.
        """
        self._cancelled = False
        start_time = time.time()
        if system:
            prompt = system + "\n\n" + prompt

        cli_exec = shutil.which(self.command)
        if not cli_exec:
            return AIResponse(
                success=False,
                error=(
                    f"'{self.command}' 명령어를 찾을 수 없습니다. "
                    f"해당 CLI AI 도구를 설치하고 PATH 에 등록해주세요."
                ),
            )

        sandbox_dir = None

        try:
            sandbox_dir = (
                Path(tempfile.gettempdir())
                / f"cliai_rpa_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            )
            sandbox_dir.mkdir(parents=True, exist_ok=True)

            full_prompt = prompt
            if images and self.supports_images:
                img_refs = []
                for img_path in images:
                    if os.path.exists(img_path):
                        normalized = img_path.replace("\\", "/")
                        img_refs.append(f'@"{normalized}"')
                if img_refs:
                    full_prompt = " ".join(img_refs) + "\n\n" + prompt

            prompt_file = None
            raw_output = ""
            stderr_output = ""
            returncode = -1

            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8", dir=str(sandbox_dir)
                ) as f:
                    f.write(full_prompt)
                    prompt_file = f.name

                self._proc = subprocess.Popen(
                    self._build_args(cli_exec),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    encoding="utf-8",
                    cwd=str(sandbox_dir),
                )
                try:
                    stdout, stderr = self._proc.communicate(input=full_prompt, timeout=self.timeout)
                    returncode = self._proc.returncode
                    raw_output = (stdout or "").strip()
                    stderr_output = (stderr or "").strip()
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.communicate()
                    raise
                finally:
                    self._proc = None

            finally:
                if prompt_file and os.path.exists(prompt_file):
                    try:
                        os.unlink(prompt_file)
                    except OSError:
                        pass

            if self._cancelled:
                return AIResponse(
                    success=False, cancelled=True, error="사용자가 요청을 취소했습니다."
                )

            elapsed_ms = int((time.time() - start_time) * 1000)

            # stdin 실패 (또는 interactive 로 빠짐) + prompt_arg 가 있으면 인자 모드 fallback
            if (not raw_output or returncode != 0) and self.prompt_arg and len(full_prompt) < 8000:
                self._proc = subprocess.Popen(
                    self._build_args(cli_exec, self.prompt_arg, full_prompt),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    encoding="utf-8",
                    cwd=str(sandbox_dir),
                )
                try:
                    stdout, stderr = self._proc.communicate(timeout=self.timeout)
                    returncode = self._proc.returncode
                    raw_output = (stdout or "").strip()
                    stderr_output = (stderr or "").strip()
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.communicate()
                    raise
                finally:
                    self._proc = None

                if self._cancelled:
                    return AIResponse(
                        success=False, cancelled=True, error="사용자가 요청을 취소했습니다."
                    )
                elapsed_ms = int((time.time() - start_time) * 1000)

            if raw_output and returncode == 0:
                code = self.extract_code_from_response(raw_output)
                if code:
                    code = self.restore_user_strings(code, full_prompt)
                description = self.extract_description_from_response(raw_output)
                packages = self.extract_packages_from_code(code) if code else []
                is_partial = self.detect_partial_response(raw_output)

                return AIResponse(
                    text=raw_output,
                    code=code,
                    description=description,
                    packages=packages,
                    raw_response=raw_output,
                    response_time_ms=elapsed_ms,
                    success=True,
                    partial=is_partial,
                )
            else:
                error_msg = stderr_output or raw_output or "응답 없음"
                return AIResponse(
                    raw_response=error_msg,
                    response_time_ms=elapsed_ms,
                    success=False,
                    error=f"{self.command} 오류 (코드 {returncode}): {error_msg[:500]}",
                )

        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return AIResponse(
                response_time_ms=elapsed_ms,
                success=False,
                error=f"{self.command} 응답 시간 초과 ({self.timeout}초)",
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return AIResponse(
                response_time_ms=elapsed_ms,
                success=False,
                error=f"{self.command} 실행 중 예외: {str(e)}",
            )

        finally:
            if sandbox_dir and sandbox_dir.exists():
                try:
                    shutil.rmtree(sandbox_dir, ignore_errors=True)
                except OSError:
                    pass


# Back-compat — 기존 import 경로 유지.
# 2026-05-24: GeminiCLIAdapter 는 CliAIAdapter 의 alias. 기존 config 의
# selected="gemini_cli" + command="gemini" 는 ai_engine 의 alias 매핑 +
# 자동 마이그레이션으로 처리.
GeminiCLIAdapter = CliAIAdapter
