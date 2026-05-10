# SPDX-License-Identifier: AGPL-3.0-or-later
"""
OpenAI 호환 Chat Completions API 어댑터.

base_url + api_key 입력으로 OpenAI 호환 API 를 사용하는 모든 LLM 서비스 지원:
- 클라우드: OpenAI, DeepSeek, Groq, Together AI, OpenRouter, Mistral, Perplexity 등
- 로컬: Ollama (localhost:11434/v1), LM Studio (localhost:1234/v1), vLLM, llama.cpp server

stdlib + requests 만 사용 (httpx/openai SDK 의존성 추가 회피). async 호환은
asyncio.to_thread 로 blocking 호출 wrap.
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
from typing import Optional

import requests

from .base_adapter import AIResponse, BaseAIAdapter

# 프리셋 — 사용자 편의용 (Settings 다이얼로그 드롭다운에서 base_url 자동 채움)
PRESETS: dict[str, dict[str, str]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o-mini",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "model": "mistral-small-latest",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    },
    "perplexity": {
        "base_url": "https://api.perplexity.ai",
        "model": "llama-3.1-sonar-small-128k-online",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.2",
    },
    "lmstudio": {
        "base_url": "http://localhost:1234/v1",
        "model": "local-model",
    },
}


class OpenAICompatAdapter(BaseAIAdapter):
    """OpenAI Chat Completions API 호환 어댑터.

    Config 필드:
    - base_url: API 엔드포인트 (기본 OpenAI)
    - api_key: 직접 입력 (비어있으면 api_key_env 시도)
    - api_key_env: 환경변수명 (기본 "OPENAI_API_KEY")
    - model: 모델 이름 (서비스마다 다름)
    - timeout_seconds: 응답 대기 시간 (기본 180)
    - max_retries: 재시도 횟수 (기본 3, 현재 미구현 — 향후 backoff 추가 시 사용)
    - temperature: 0.0~2.0 (기본 0.3)
    - max_tokens: 최대 응답 토큰 (기본 4096)
    """

    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MODEL = "gpt-4o-mini"
    DEFAULT_API_KEY_ENV = "OPENAI_API_KEY"

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = (config.get("base_url") or self.DEFAULT_BASE_URL).rstrip("/")
        # api_key 우선순위: 직접 입력 > 환경변수
        self.api_key = config.get("api_key") or os.environ.get(
            config.get("api_key_env") or self.DEFAULT_API_KEY_ENV, ""
        )
        self.model = config.get("model") or self.DEFAULT_MODEL
        self.timeout = int(config.get("timeout_seconds", 180))
        self.max_retries = int(config.get("max_retries", 3))
        self.temperature = float(config.get("temperature", 0.3))
        self.max_tokens = int(config.get("max_tokens", 4096))
        self._cancelled: bool = False

    # 프리셋 표시 라벨 (Title 케이스 자동 변환은 'DeepSeek' 같은 고유 표기 못 살림)
    _PRESET_LABELS: dict[str, str] = {
        "openai": "OpenAI",
        "deepseek": "DeepSeek",
        "groq": "Groq",
        "openrouter": "OpenRouter",
        "mistral": "Mistral",
        "together": "Together AI",
        "perplexity": "Perplexity",
        "ollama": "Ollama (local)",
        "lmstudio": "LM Studio (local)",
    }

    def get_name(self) -> str:
        preset = self._detect_preset()
        if preset:
            label = self._PRESET_LABELS.get(preset, preset)
            return f"OpenAI 호환 ({label})"
        return "OpenAI 호환 API"

    def is_available(self) -> bool:
        # base_url 만 있으면 가용 (api_key 가 없는 로컬 Ollama/LM Studio 도 허용).
        # 실 호출 안 함 — 빠른 체크.
        return bool(self.base_url)

    def cancel(self) -> None:
        # requests 는 native cancel 미지원 → 플래그만 설정. 응답 후 _cancelled 검사.
        # 실시간 중단은 향후 httpx 전환 시 강화 가능.
        self._cancelled = True

    def _detect_preset(self) -> Optional[str]:
        """현재 base_url 이 어느 프리셋과 일치하는지 (Settings UI 라벨용)."""
        for name, p in PRESETS.items():
            if self.base_url.startswith(p["base_url"].rstrip("/")):
                return name
        return None

    async def generate(
        self,
        prompt: str,
        images: Optional[list[str]] = None,
        system: Optional[str] = None,
    ) -> AIResponse:
        """asyncio.to_thread 로 blocking 호출 wrap."""
        return await asyncio.to_thread(self._generate_sync, prompt, images, system)

    def _generate_sync(
        self,
        prompt: str,
        images: Optional[list[str]] = None,
        system: Optional[str] = None,
    ) -> AIResponse:
        """동기 HTTP 호출 — POST {base_url}/chat/completions.

        P1b: system 인자 있으면 messages 의 첫 항목에 system role 분리. OpenAI
        호환 모델 (DeepSeek/Groq/OpenRouter/Mistral 등) 이 system 토큰을 user 와
        다르게 처리 — attention 강화로 가이드를 더 강하게 따름.
        """
        self._cancelled = False
        start = time.time()

        # 메시지 content 빌드 — 이미지 있으면 OpenAI multimodal 포맷 (vision 모델용).
        content: object
        if images:
            parts: list[dict] = [{"type": "text", "text": prompt}]
            for img_path in images:
                data_url = self._image_to_data_url(img_path)
                if data_url:
                    parts.append({"type": "image_url", "image_url": {"url": data_url}})
            content = parts
        else:
            content = prompt

        # P1b: system role 분리. system 있으면 messages 의 첫 항목.
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        except requests.Timeout:
            elapsed_ms = int((time.time() - start) * 1000)
            return AIResponse(
                response_time_ms=elapsed_ms,
                success=False,
                error=f"응답 시간 초과 ({self.timeout}초)",
            )
        except requests.ConnectionError as e:
            elapsed_ms = int((time.time() - start) * 1000)
            return AIResponse(
                response_time_ms=elapsed_ms,
                success=False,
                error=f"연결 실패 (base_url 또는 네트워크 확인): {e}",
            )
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            return AIResponse(
                response_time_ms=elapsed_ms,
                success=False,
                error=f"호출 실패: {e}",
            )

        elapsed_ms = int((time.time() - start) * 1000)

        if self._cancelled:
            return AIResponse(
                success=False,
                cancelled=True,
                error="사용자가 요청을 취소했습니다.",
            )

        if resp.status_code != 200:
            # 422/429/500 등 — 응답 본문에 서비스별 에러 메시지 포함.
            return AIResponse(
                response_time_ms=elapsed_ms,
                success=False,
                error=f"API 오류 (HTTP {resp.status_code}): {resp.text[:500]}",
            )

        try:
            data = resp.json()
        except Exception as e:
            return AIResponse(
                response_time_ms=elapsed_ms,
                success=False,
                error=f"JSON 파싱 실패: {e}; body={resp.text[:300]}",
            )

        choices = data.get("choices") or []
        if not choices:
            return AIResponse(
                response_time_ms=elapsed_ms,
                success=False,
                error=f"응답에 choices 없음: {data}",
            )

        msg = choices[0].get("message") or {}
        raw_text = msg.get("content") or ""
        if not isinstance(raw_text, str):
            # 일부 서비스는 content 가 list (multimodal) — text 부분만 join.
            try:
                raw_text = "\n".join(p.get("text", "") for p in raw_text if isinstance(p, dict))
            except Exception:
                raw_text = str(raw_text)

        usage = data.get("usage") or {}
        tokens = int(usage.get("total_tokens", 0) or 0)

        code = self.extract_code_from_response(raw_text)
        if code:
            code = self.restore_user_strings(code, prompt)
        description = self.extract_description_from_response(raw_text)
        packages = self.extract_packages_from_code(code) if code else []

        return AIResponse(
            text=raw_text,
            code=code,
            description=description,
            packages=packages,
            raw_response=raw_text,
            tokens_used=tokens,
            response_time_ms=elapsed_ms,
            success=True,
            partial=self.detect_partial_response(raw_text),
        )

    def _image_to_data_url(self, path: str) -> Optional[str]:
        """이미지 파일을 base64 data URL 로 변환 (OpenAI vision 포맷)."""
        if not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            ext = os.path.splitext(path)[1].lower().lstrip(".")
            if ext in ("jpg", "jpeg"):
                mime = "image/jpeg"
            elif ext == "png":
                mime = "image/png"
            elif ext in ("webp", "gif"):
                mime = f"image/{ext}"
            else:
                mime = "image/png"
            return f"data:{mime};base64,{data}"
        except Exception:
            return None
