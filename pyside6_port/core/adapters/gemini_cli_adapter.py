# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Gemini CLI 어댑터

Gemini CLI를 subprocess로 호출하여 프롬프트를 전송하고 응답을 받습니다.
PowerShell을 사용하지 않고 직접 호출하여 인코딩/따옴표 문제를 방지합니다.
"""

import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base_adapter import AIResponse, BaseAIAdapter


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
        # config 의 model 필드를 -m 인자로 명시 전달 (5/4 사용자 보고: headless 모드
        # default 가 preview 모델로 잡혀 capacity 부족 회귀).
        self.model = config.get("model", "")
        self._proc: Optional[subprocess.Popen] = None  # 실행 중인 서브프로세스
        self._cancelled: bool = False  # 사용자 취소 플래그

    def _build_args(self, gemini_exec: str, *extra: str) -> list:
        """gemini 실행 인자 빌드 — model 설정 시 -m 추가."""
        args = [gemini_exec]
        if self.model:
            args.extend(["-m", self.model])
        args.extend(extra)
        return args

    def cancel(self) -> None:
        """진행 중인 Gemini CLI 프로세스를 강제 종료합니다."""
        self._cancelled = True
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    def get_name(self) -> str:
        return "Gemini CLI"

    def is_available(self) -> bool:
        """gemini 명령어가 시스템 PATH에 존재하는지 확인합니다."""
        return shutil.which(self.command) is not None

    async def generate(
        self,
        prompt: str,
        images: Optional[list[str]] = None,
        system: Optional[str] = None,
    ) -> AIResponse:
        """
        Gemini CLI를 통해 프롬프트를 전송하고 응답을 받습니다.

        P1b: Gemini CLI 는 system role 분리 path 가 없음 (stdin 단일 입력).
        system 있으면 prompt 앞에 prepend 하여 동일 효과 — P1a 의 prompt_builder
        prepend 와 결과 동일.
        """
        self._cancelled = False
        start_time = time.time()
        # P1b: system 있으면 prompt 앞에 prepend (CLI 가 role 분리 미지원)
        if system:
            prompt = system + "\n\n" + prompt

        gemini_exec = shutil.which(self.command)
        if not gemini_exec:
            return AIResponse(
                success=False,
                error=f"'{self.command}' 명령어를 찾을 수 없습니다. Gemini CLI를 설치해주세요.",
            )

        sandbox_dir = None

        try:
            # 샌드박스 디렉터리 생성
            sandbox_dir = (
                Path(tempfile.gettempdir())
                / f"gemini_rpa_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            )
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

            # 프롬프트를 stdin으로 전달 (Popen → communicate로 취소 가능)
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
                    self._build_args(gemini_exec),
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

            # 취소된 경우 즉시 반환
            if self._cancelled:
                return AIResponse(
                    success=False, cancelled=True, error="사용자가 요청을 취소했습니다."
                )

            elapsed_ms = int((time.time() - start_time) * 1000)

            # 결과 확인: stdin 파이프 실패 시 -p 플래그로 재시도
            # stdin이 안 되면 (interactive 모드로 빠지면) -p 로 재시도
            if not raw_output or returncode != 0:
                # 짧은 프롬프트는 직접 인자로 전달 가능
                if len(full_prompt) < 8000:
                    self._proc = subprocess.Popen(
                        self._build_args(gemini_exec, "-p", full_prompt),
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

            # result 호환 객체 대신 변수 직접 사용
            if raw_output and returncode == 0:
                code = self.extract_code_from_response(raw_output)
                # AI가 문자열 리터럴 내 특수문자 앞뒤에 공백을 삽입하는 버그 교정
                if code:
                    code = self.restore_user_strings(code, full_prompt)
                description = self.extract_description_from_response(raw_output)
                packages = self.extract_packages_from_code(code) if code else []
                # partial 감지 (사용자 보고 5/5: AI 응답 도중 잘림)
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
                    error=f"Gemini CLI 오류 (코드 {returncode}): {error_msg[:500]}",
                )

        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return AIResponse(
                response_time_ms=elapsed_ms,
                success=False,
                error=f"Gemini CLI 응답 시간 초과 ({self.timeout}초)",
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return AIResponse(
                response_time_ms=elapsed_ms,
                success=False,
                error=f"Gemini CLI 실행 중 예외: {str(e)}",
            )

        finally:
            if sandbox_dir and sandbox_dir.exists():
                try:
                    shutil.rmtree(sandbox_dir, ignore_errors=True)
                except OSError:
                    pass
