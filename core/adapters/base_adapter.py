"""
AI 어댑터 기반 클래스

모든 AI 엔진 어댑터가 구현해야 하는 추상 인터페이스를 정의합니다.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AIResponse:
    """AI 엔진의 응답 데이터 구조"""
    text: str = ""                          # AI 전체 응답 텍스트
    code: str = ""                          # 추출된 코드 블록
    description: str = ""                   # AI의 설명 부분
    packages: list[str] = field(default_factory=list)  # 필요 패키지 목록
    raw_response: str = ""                  # 원본 응답
    tokens_used: int = 0                    # 사용 토큰 수
    response_time_ms: int = 0               # 응답 시간 (밀리초)
    success: bool = False                   # 성공 여부
    error: Optional[str] = None             # 에러 메시지


class BaseAIAdapter(ABC):
    """
    AI 엔진 어댑터 추상 기반 클래스.

    모든 AI 어댑터(Gemini CLI, OpenAI, Claude 등)는
    이 클래스를 상속받아 generate() 메서드를 구현해야 합니다.
    """

    def __init__(self, config: dict):
        """
        Args:
            config: settings.json의 해당 엔진 설정 딕셔너리
        """
        self.config = config

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        images: Optional[list[str]] = None
    ) -> AIResponse:
        """
        AI에게 프롬프트를 전송하고 응답을 받습니다.

        Args:
            prompt: 전송할 프롬프트 텍스트
            images: 첨부할 이미지 파일 경로 목록

        Returns:
            AIResponse 데이터 객체
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """어댑터의 표시 이름을 반환합니다."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        이 어댑터가 현재 사용 가능한지 확인합니다.
        (예: Gemini CLI가 설치되어 있는지, API 키가 설정되어 있는지)
        """
        pass

    def get_quota_status(self) -> dict:
        """API 사용량/쿼터 상태를 반환합니다. (지원하는 어댑터만 오버라이드)"""
        return {"status": "unknown"}

    @staticmethod
    def extract_code_from_response(response_text: str) -> str:
        """
        AI 응답에서 Python 코드 블록을 추출합니다.

        지원 형식:
        1. ```python ... ```
        2. ```py ... ```
        3. ``` ... ``` (코드 내용에 import/def/class가 있으면)
        4. 코드 블록 없이 직접 코드가 있는 경우 (fallback)
        """
        import re

        # 1차: ```python 또는 ```py 블록
        code_blocks = re.findall(
            r'```(?:python|py)\s*\n?(.*?)\s*```',
            response_text, re.DOTALL
        )
        if code_blocks:
            return code_blocks[-1].strip()

        # 2차: ``` 블록 중 Python 코드가 포함된 것
        generic_blocks = re.findall(
            r'```\s*\n?(.*?)\s*```',
            response_text, re.DOTALL
        )
        for block in reversed(generic_blocks):
            stripped = block.strip()
            # Python 코드 패턴 확인
            if any(stripped.startswith(kw) for kw in
                   ['import ', 'from ', 'def ', 'class ', '#', 'try:', 'if ', 'for ']):
                return stripped
            if re.search(r'\bimport\b|\bdef\b|\bclass\b|\bprint\(', stripped):
                return stripped

        # 3차: 코드 블록 없이 본문에 직접 코드가 있는 경우 (fallback)
        lines = response_text.split('\n')
        code_lines = []
        in_code = False
        for line in lines:
            stripped = line.strip()
            # 코드 시작 감지
            if not in_code and (
                stripped.startswith('import ') or
                stripped.startswith('from ') or
                stripped.startswith('def ') or
                stripped.startswith('class ') or
                stripped.startswith('#!/')
            ):
                in_code = True
            if in_code:
                # 빈줄이 아닌 비-코드 텍스트(한글 문장 등)를 만나면 종료
                if stripped and not any([
                    stripped.startswith('#'),
                    stripped.startswith('import '),
                    stripped.startswith('from '),
                    stripped.startswith('def '),
                    stripped.startswith('class '),
                    stripped.startswith('if '),
                    stripped.startswith('for '),
                    stripped.startswith('while '),
                    stripped.startswith('try:'),
                    stripped.startswith('except'),
                    stripped.startswith('finally'),
                    stripped.startswith('with '),
                    stripped.startswith('return '),
                    stripped.startswith('print('),
                    stripped.startswith('raise '),
                    stripped.startswith('assert '),
                    stripped == '',
                    line.startswith(' '),
                    line.startswith('\t'),
                    '=' in stripped,
                    '(' in stripped,
                    ')' in stripped,
                    stripped.startswith('elif'),
                    stripped.startswith('else:'),
                    stripped.startswith('pass'),
                    stripped.startswith('break'),
                    stripped.startswith('continue'),
                    stripped.startswith('yield'),
                    stripped.startswith('async '),
                    stripped.startswith('await '),
                ]):
                    break
                code_lines.append(line)

        if code_lines and len(code_lines) >= 2:
            return '\n'.join(code_lines).strip()

        return ""

    @staticmethod
    def extract_description_from_response(response_text: str) -> str:
        """AI 응답에서 코드 블록을 제외한 설명 부분을 추출합니다."""
        import re
        # 코드 블록 제거
        cleaned = re.sub(r'```.*?```', '', response_text, flags=re.DOTALL)
        return cleaned.strip()

    @staticmethod
    def extract_packages_from_code(code: str) -> list[str]:
        """코드에서 import된 패키지 목록을 추출합니다."""
        import re
        packages = set()
        # import 패키지명
        for match in re.finditer(r'^import\s+(\w+)', code, re.MULTILINE):
            packages.add(match.group(1))
        # from 패키지명 import ...
        for match in re.finditer(r'^from\s+(\w+)', code, re.MULTILINE):
            packages.add(match.group(1))
        # 표준 라이브러리 제외
        stdlib = {'os', 'sys', 'time', 'json', 'pathlib', 'subprocess', 're',
                  'datetime', 'collections', 'functools', 'itertools', 'typing',
                  'dataclasses', 'abc', 'io', 'logging', 'shutil', 'tempfile',
                  'threading', 'queue', 'uuid', 'hashlib', 'base64', 'glob',
                  'math', 'random', 'string', 'traceback', 'copy', 'enum'}
        return sorted(packages - stdlib)
