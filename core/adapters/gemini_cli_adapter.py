"""
Gemini CLI 어댑터

Gemini CLI를 subprocess로 호출하여 프롬프트를 전송하고 응답을 받습니다.
PowerShell을 사용하지 않고 직접 호출하여 인코딩/따옴표 문제를 방지합니다.
"""

import os
import sys
import time
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime

from .base_adapter import BaseAIAdapter, AIResponse


class GeminiCLIAdapter(BaseAIAdapter):
    """
    Gemini CLI 기반 AI 어댑터.

    특징:
    - subprocess를 통한 직접 호출 (PowerShell 우회)
    - stdin 파이프로 프롬프트 전달 (인자 길이 제한 회피)
    - 이미지 첨부 지원
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.command = config.get("command", "gemini")
        self.timeout = config.get("timeout_seconds", 180)
        self.max_retries = config.get("max_retries", 3)

    def get_name(self) -> str:
        return "Gemini CLI"

    def is_available(self) -> bool:
        """gemini 명령어가 시스템 PATH에 존재하는지 확인합니다."""
        return shutil.which(self.command) is not None

    async def generate(
        self,
        prompt: str,
        images: Optional[list[str]] = None
    ) -> AIResponse:
        """
        Gemini CLI를 통해 프롬프트를 전송하고 응답을 받습니다.
        """
        start_time = time.time()

        gemini_exec = shutil.which(self.command)
        if not gemini_exec:
            return AIResponse(
                success=False,
                error=f"'{self.command}' 명령어를 찾을 수 없습니다. Gemini CLI를 설치해주세요."
            )

        sandbox_dir = None

        try:
            # 샌드박스 디렉터리 생성
            sandbox_dir = Path(tempfile.gettempdir()) / f"gemini_rpa_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            sandbox_dir.mkdir(parents=True, exist_ok=True)

            # 이미지 첨부가 있는 경우 프롬프트 앞에 추가
            full_prompt = prompt
            if images:
                img_refs = []
                for img_path in images:
                    if os.path.exists(img_path):
                        normalized = img_path.replace("\\", "/")
                        img_refs.append(f'@"{normalized}"')
                if img_refs:
                    full_prompt = " ".join(img_refs) + "\n\n" + prompt

            # 방법 1: 프롬프트를 임시 파일에 저장 후 쉘에서 읽기
            prompt_file = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode='w', suffix='.txt', delete=False,
                    encoding='utf-8', dir=str(sandbox_dir)
                ) as f:
                    f.write(full_prompt)
                    prompt_file = f.name

                if sys.platform == "win32":
                    # Windows: cmd로 type 명령어로 파일 내용을 gemini에 파이프
                    # 또는 직접 subprocess로 stdin 전달
                    result = subprocess.run(
                        [gemini_exec],
                        input=full_prompt,
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        timeout=self.timeout,
                        cwd=str(sandbox_dir)
                    )
                else:
                    # Linux/macOS
                    result = subprocess.run(
                        [gemini_exec],
                        input=full_prompt,
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        timeout=self.timeout,
                        cwd=str(sandbox_dir)
                    )

            finally:
                if prompt_file and os.path.exists(prompt_file):
                    try:
                        os.unlink(prompt_file)
                    except OSError:
                        pass

            elapsed_ms = int((time.time() - start_time) * 1000)

            # 결과 확인: stdin 파이프 실패 시 -p 플래그로 재시도
            raw_output = result.stdout.strip() if result.stdout else ""
            stderr_output = result.stderr.strip() if result.stderr else ""

            # stdin이 안 되면 (interactive 모드로 빠지면) -p 로 재시도
            if not raw_output or result.returncode != 0:
                # 짧은 프롬프트는 직접 인자로 전달 가능
                if len(full_prompt) < 8000:
                    result = subprocess.run(
                        [gemini_exec, "-p", full_prompt],
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        timeout=self.timeout,
                        cwd=str(sandbox_dir)
                    )
                    raw_output = result.stdout.strip() if result.stdout else ""
                    stderr_output = result.stderr.strip() if result.stderr else ""
                    elapsed_ms = int((time.time() - start_time) * 1000)

            if raw_output and result.returncode == 0:
                code = self.extract_code_from_response(raw_output)
                description = self.extract_description_from_response(raw_output)
                packages = self.extract_packages_from_code(code) if code else []

                return AIResponse(
                    text=raw_output,
                    code=code,
                    description=description,
                    packages=packages,
                    raw_response=raw_output,
                    response_time_ms=elapsed_ms,
                    success=True
                )
            else:
                error_msg = stderr_output or raw_output or "응답 없음"
                return AIResponse(
                    raw_response=error_msg,
                    response_time_ms=elapsed_ms,
                    success=False,
                    error=f"Gemini CLI 오류 (코드 {result.returncode}): {error_msg[:500]}"
                )

        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return AIResponse(
                response_time_ms=elapsed_ms,
                success=False,
                error=f"Gemini CLI 응답 시간 초과 ({self.timeout}초)"
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return AIResponse(
                response_time_ms=elapsed_ms,
                success=False,
                error=f"Gemini CLI 실행 중 예외: {str(e)}"
            )

        finally:
            if sandbox_dir and sandbox_dir.exists():
                try:
                    shutil.rmtree(sandbox_dir, ignore_errors=True)
                except OSError:
                    pass
