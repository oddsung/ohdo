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
    response_time_ms: int = 0              # 응답 시간 (밀리초)
    success: bool = False                   # 성공 여부
    error: Optional[str] = None             # 에러 메시지
    cancelled: bool = False                 # 사용자 취소 여부


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

    def cancel(self) -> None:
        """진행 중인 AI 요청을 취소합니다. (지원하는 어댑터만 오버라이드)"""
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
    def restore_user_strings(code: str, full_prompt: str) -> str:
        """
        AI가 코드 생성 시 문자열 리터럴 내 특수문자(@, #, % 등) 앞뒤에
        공백을 잘못 삽입하는 버그를 교정합니다.

        동작:
        1. 프롬프트의 사용자 요청 섹션에서 따옴표로 감싼 원본 값을 추출합니다.
        2. 생성된 코드에 해당 값이 손상(공백 삽입)된 채로 있으면 원본으로 교체합니다.
        3. 추출 실패 시 fallback으로 문자열 리터럴 내 @ 주변 공백을 제거합니다.

        예: input_text = "doosung.oh @wooyang.co.kr"
            → input_text = "doosung.oh@wooyang.co.kr"
        """
        import re

        if not code or not full_prompt:
            return code

        # ── 1단계: 프롬프트에서 사용자 원본 따옴표 값 추출 ─────────────────────
        # 프롬프트 첫 4줄(사용자 요청 섹션)만 사용
        user_section = '\n'.join(full_prompt.splitlines()[:4])

        # 작은따옴표 또는 큰따옴표로 감싼 값 중 특수문자 포함 3자 이상만 추출
        candidates: list[str] = re.findall(r"'([^'\n]{3,})'", user_section)
        candidates += re.findall(r'"([^"\n]{3,})"', user_section)

        SPECIAL = '@#%!&'  # 공백 삽입이 자주 일어나는 특수문자

        for original in candidates:
            if not any(c in original for c in SPECIAL):
                continue  # 특수문자 없으면 건너뜀
            # 따옴표로 바로 감싼 형태로 포함되어 있으면 건너뜀
            # (단순 `original in code` 체크 금지: '@abc'는 ' @abc'의 부분 문자열이라
            #  이미 손상된 형태가 있어도 True를 반환해 교정을 건너뛰는 오류 발생)
            if re.search(r'["\']' + re.escape(original) + r'["\']', code):
                continue

            # 각 특수문자 위치마다 삽입 변형 생성 후 교체 시도
            replaced = False
            for i, ch in enumerate(original):
                if ch not in SPECIAL:
                    continue
                # 케이스 A: 특수문자 바로 앞에 공백 삽입 →  "xxx @yyy"
                before = original[:i] + ' ' + original[i:]
                if before in code:
                    code = code.replace(before, original)
                    replaced = True
                    break
                # 케이스 B: 특수문자 바로 뒤에 공백 삽입 → "xxx@ yyy"
                after = original[:i + 1] + ' ' + original[i + 1:]
                if after in code:
                    code = code.replace(after, original)
                    replaced = True
                    break
                # 케이스 C: 양쪽 모두 공백 삽입 → "xxx @ yyy"
                both = original[:i] + ' ' + original[i] + ' ' + original[i + 1:]
                if both in code:
                    code = code.replace(both, original)
                    replaced = True
                    break
            if replaced:
                continue

        # ── 2단계: Fallback — 문자열 리터럴 내 @ 주변 공백 제거 ─────────────────
        # 패턴: 단어문자 + 공백 + @ + 단어문자  →  단어문자 + @ + 단어문자
        # (단, 따옴표로 닫힌 범위 내에서만 적용 — 단순 휴리스틱)
        def _fix_at_spaces(m: re.Match) -> str:
            quote = m.group(1)  # ' or "
            content = m.group(2)
            # \w 공백 @ → \w@
            content = re.sub(r'(\w) (@\w)', r'\1\2', content)
            # \w@ 공백 \w → \w@\w
            content = re.sub(r'(\w@) (\w)', r'\1\2', content)
            return quote + content + quote

        # 단순 문자열 리터럴 (삼중따옴표 제외, 백슬래시 이스케이프 미포함)
        code = re.sub(
            r'(["\'])([^"\'\\]*@[^"\'\\]*)\1',
            _fix_at_spaces,
            code
        )

        # ── 3단계: XPath 코드 패턴 교정 ──────────────────────────────────────────
        # Bug A: AI가 XPath 술어 내 속성 참조 앞에 공백 삽입
        #   '//*[ @title=...]'       →  '//*[@title=...]'
        code = re.sub(r'\[\s+@([a-zA-Z])', r'[@\1', code)
        # Bug A2: normalize-space 함수 인자 앞에 공백 삽입
        #   'normalize-space( @title)'  →  'normalize-space(@title)'
        code = re.sub(r'normalize-space\(\s+@([a-zA-Z])', r'normalize-space(@\1', code)

        # Bug B: normalize-space(.) = "value " 패턴 — 비교값에 후행공백이 있으면 불일치
        #   normalize-space(.)="{value}"  →  normalize-space(.)=normalize-space("{value}")
        #   단방향 normalize-space를 양방향으로 교정
        code = re.sub(
            r'(normalize-space\(\.\)=")([^"]+)(")',
            lambda m: (
                f'normalize-space(.)=normalize-space("{m.group(2)}")'
                if not m.group(2).startswith('normalize-space(')
                else m.group(0)
            ),
            code
        )
        # title 속성도 동일 교정
        code = re.sub(
            r'(@title=")([^"]+)(")',
            lambda m: (
                f'normalize-space(@title)=normalize-space("{m.group(2)}")'
                if not m.group(0).startswith('normalize-space(')
                else m.group(0)
            ),
            code
        )

        # ── 4단계: driver.get() URL 프로토콜 누락 교정 ───────────────────────────
        # driver.get('example.com') → driver.get('https://example.com')
        # 프로토콜이 없으면 Selenium이 'data:' 페이지를 열어버리는 문제 방지
        def _fix_driver_get_url(m: re.Match) -> str:
            quote = m.group(1)   # ' or "
            url = m.group(2)
            if url.startswith(('http://', 'https://', 'file://', 'data:')):
                return m.group(0)  # 이미 프로토콜 있음
            return f'driver.get({quote}https://{url}{quote})'

        code = re.sub(
            r"driver\.get\((['\"])(?!https?://|file://|data:)([^'\"]+)\1\)",
            _fix_driver_get_url,
            code
        )

        # ── 5단계: TAB 후 동일 요소 변수로 send_keys 교정 ───────────────────────
        # 버그: TAB으로 포커스 이동 후 원래 요소 변수로 다시 send_keys하면 ID 필드에 입력됨
        #   var.send_keys(Keys.TAB)       →  포커스 이동
        #   var.send_keys('pw')           →  ← 여전히 ID 필드에 전송! (버그)
        # 교정: TAB 전송 바로 다음에 같은 변수명으로 send_keys하는 줄을 active_element로 변환
        def _fix_tab_then_send(m: re.Match) -> str:
            var = m.group(1)       # 변수명 (예: login_input)
            tab_line = m.group(2)  # ".send_keys(Keys.TAB)\n" 부분
            rest = m.group(3)      # 이후 같은 변수명으로 send_keys 하는 줄들
            # rest 내에서 var.send_keys(...) → driver.switch_to.active_element.send_keys(...)
            fixed = re.sub(
                re.escape(var) + r'(\.send_keys\()',
                r'driver.switch_to.active_element\1',
                rest
            )
            # var + tab_line: 원래 TAB 줄 온전히 복원
            return var + tab_line + fixed

        # 패턴: "{var}.send_keys(Keys.TAB)\n" 이후 "{var}.send_keys(" 로 시작하는 줄
        code = re.sub(
            r'(\w+)(\.send_keys\(Keys\.TAB\)\n)((?:[ \t]*\1\.send_keys\([^\n]+\n)+)',
            _fix_tab_then_send,
            code
        )

        # ── 6단계: find_and_click 내 el.click() → ActionChains 교정 ─────────────
        # 기존 생성 코드의 find_and_click 함수 본문에서
        # "else:\n    try: el.click()\n    except Exception: driver.execute_script..." 패턴을
        # ActionChains 우선 시도로 교체 (들여쓰기 수에 무관하게 처리)
        def _fix_el_click_to_actionchains(m: re.Match) -> str:
            indent = m.group(1)   # else: 줄의 들여쓰기
            inner = indent + '    '  # 한 단계 더 들여쓰기
            return (
                f"{indent}else:\n"
                f"{inner}try:\n"
                f"{inner}    from selenium.webdriver.common.action_chains import ActionChains\n"
                f"{inner}    ActionChains(driver).move_to_element(el).click().perform()\n"
                f"{inner}except Exception:\n"
                f"{inner}    try: el.click()\n"
                f"{inner}    except Exception: driver.execute_script('arguments[0].click()', el)\n"
            )

        code = re.sub(
            r'([ \t]+)else:\n\1    try: el\.click\(\)\n\1    except Exception: driver\.execute_script\(\'arguments\[0\]\.click\(\)\', el\)\n',
            _fix_el_click_to_actionchains,
            code
        )

        return code

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
