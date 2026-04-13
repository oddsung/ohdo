"""
Import 관리 모듈

코드에서 import 문을 추출/병합/조합하는 유틸리티.
스텝별 코드 분리와 export 시 import 중복 제거에 사용됩니다.
"""

import re
from typing import Optional


# Python 표준 라이브러리 목록 (import 분류용)
STDLIB_MODULES = frozenset({
    'os', 'sys', 'time', 'json', 'pathlib', 'subprocess', 're',
    'datetime', 'collections', 'functools', 'itertools', 'typing',
    'dataclasses', 'abc', 'io', 'logging', 'shutil', 'tempfile',
    'threading', 'queue', 'uuid', 'hashlib', 'base64', 'glob',
    'math', 'random', 'string', 'traceback', 'copy', 'enum',
    'csv', 'sqlite3', 'http', 'urllib', 'email', 'html',
    'xml', 'ctypes', 'struct', 'socket', 'ssl', 'asyncio',
    'multiprocessing', 'concurrent', 'contextlib', 'inspect',
    'unittest', 'pprint', 'textwrap', 'warnings', 'signal',
    'platform', 'getpass', 'configparser', 'argparse', 'pickle',
    'shelve', 'zipfile', 'tarfile', 'gzip', 'bz2', 'lzma',
    'webbrowser', 'tkinter', 'codecs', 'locale', 'struct',
    'operator', 'heapq', 'bisect', 'array', 'decimal', 'fractions',
    'statistics', 'secrets', 'hmac', 'difflib', 'fileinput',
})


def extract_imports(code: str) -> tuple[list[str], str]:
    """
    코드에서 상단 import 블록을 분리합니다.

    상단에 연속으로 나오는 import/from 문만 추출하고,
    코드 본문 중간에 있는 import는 body에 그대로 유지합니다.

    Args:
        code: Python 소스 코드

    Returns:
        (import_lines, body_code) 튜플
        - import_lines: 상단 import 문 리스트
        - body_code: import를 제외한 나머지 코드
    """
    if not code or not code.strip():
        return [], ""

    lines = code.split('\n')
    import_lines = []
    body_start = 0
    in_header = True

    for i, line in enumerate(lines):
        stripped = line.strip()

        if in_header:
            # 상단 영역: import문, 빈 줄, 주석, docstring 시작/끝 허용
            if stripped.startswith(('import ', 'from ')):
                import_lines.append(line.rstrip())
                body_start = i + 1
            elif stripped == '' or stripped.startswith('#'):
                # 빈 줄이나 주석은 import 블록 사이에 올 수 있음
                body_start = i + 1
            elif stripped.startswith(('"""', "'''")):
                # docstring은 건너뛰기 (모듈 docstring)
                # 한 줄 docstring
                if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                    body_start = i + 1
                else:
                    # 여러 줄 docstring: 닫는 따옴표까지 스킵
                    quote = stripped[:3]
                    for j in range(i + 1, len(lines)):
                        if quote in lines[j]:
                            body_start = j + 1
                            break
                    else:
                        body_start = len(lines)
                    # docstring 이후 다시 import 탐색 계속
                    continue
            else:
                # import도 빈 줄도 주석도 아닌 코드 → import 블록 종료
                in_header = False

    # body 구성: import 블록 이후의 모든 줄
    body_lines = lines[body_start:]

    # body 앞뒤 빈 줄 정리
    body_code = '\n'.join(body_lines).strip()

    return import_lines, body_code


def merge_imports(import_lists: list[list[str]]) -> list[str]:
    """
    여러 스텝의 import 목록을 병합/중복제거/정렬합니다.

    Args:
        import_lists: 각 스텝의 import 문 리스트들

    Returns:
        중복 제거되고 정렬된 import 문 리스트
    """
    seen = set()
    unique_imports = []

    for imports in import_lists:
        for imp in imports:
            normalized = imp.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique_imports.append(normalized)

    # 정렬: stdlib → third-party, import → from 순
    def sort_key(imp: str):
        # import X → (모듈명, 0)
        # from X import Y → (모듈명, 1)
        match = re.match(r'^(?:from\s+(\w+)|import\s+(\w+))', imp)
        module = (match.group(1) or match.group(2)) if match else ''
        is_stdlib = 0 if module.lower() in STDLIB_MODULES else 1
        is_from = 1 if imp.startswith('from') else 0
        return (is_stdlib, module.lower(), is_from)

    return sorted(unique_imports, key=sort_key)


def assemble_script(
    imports: list[str],
    step_entries: list,
) -> str:
    """
    import 헤더와 스텝 코드들을 하나의 실행 가능한 스크립트로 조합합니다.

    Args:
        imports: 병합된 import 문 리스트
        step_entries: 스텝 정보 리스트. 각 항목은:
            - str: 코드 본문만 (경계 주석 없이 결합)
            - tuple[int, str, str]: (step_id, task_name, code) (경계 주석 포함)

    Returns:
        실행 가능한 Python 스크립트 문자열
    """
    parts = []

    # import 헤더
    if imports:
        parts.append('\n'.join(imports))
        parts.append('')  # import와 코드 사이 빈 줄

    # 스텝 코드 순서대로 결합
    for entry in step_entries:
        if isinstance(entry, tuple):
            step_id, task_name, code = entry
            code = code.strip()
            if not code:
                continue
            # task_name 정규화: 줄바꿈 → 공백, 50자 제한
            task_name = ' '.join(task_name.splitlines()).strip()
            if len(task_name) > 50:
                task_name = task_name[:47] + "..."
            parts.append(f"# === Step {step_id}: {task_name} (시작) ===")
            parts.append(code)
            parts.append(f"# === Step {step_id}: {task_name} (끝) ===")
        else:
            code = entry.strip()
            if code:
                parts.append(code)

    return '\n\n'.join(parts)


def extract_code_delta(new_body: str, prev_body: str) -> str:
    """
    새 누적 코드 body에서 이전 body 이후에 추가된 부분만 추출합니다.

    AI는 매번 전체 누적 코드를 생성하므로, 이전 스텝의 body를 prefix로
    제거하면 이번 스텝에서 새로 추가된 코드를 얻을 수 있습니다.

    Args:
        new_body: 이번 스텝의 전체 body (import 제외)
        prev_body: 이전 스텝의 전체 body (import 제외)

    Returns:
        이번 스텝에서 새로 추가된 코드. prefix 매칭 실패 시 new_body 전체 반환.
    """
    if not prev_body or not prev_body.strip():
        return new_body  # 첫 스텝은 전체가 새 코드

    new_lines = new_body.split('\n')
    prev_lines = prev_body.rstrip().split('\n')

    n = len(prev_lines)
    if len(new_lines) >= n:
        prev_stripped = [line.rstrip() for line in prev_lines]
        new_prefix_stripped = [line.rstrip() for line in new_lines[:n]]

        if prev_stripped == new_prefix_stripped:
            delta_lines = new_lines[n:]
            # 앞의 빈 줄 제거
            while delta_lines and not delta_lines[0].strip():
                delta_lines.pop(0)
            result = '\n'.join(delta_lines).strip()
            return result if result else new_body

    # prefix 매칭 실패 → 전체 body 반환 (경계 주석은 전체를 감쌈)
    return new_body


def extract_import_delta(new_imports: list[str], prev_imports: list[str]) -> list[str]:
    """
    새로 추가된 import 문만 반환합니다.

    Args:
        new_imports: 이번 스텝의 전체 import 목록
        prev_imports: 이전 스텝까지의 import 목록

    Returns:
        이번 스텝에서 새로 추가된 import 문 리스트
    """
    prev_set = {imp.strip() for imp in prev_imports}
    return [imp for imp in new_imports if imp.strip() not in prev_set]


def extract_package_names(imports: list[str]) -> list[str]:
    """
    import 문 리스트에서 패키지 이름만 추출합니다 (stdlib 제외).

    Args:
        imports: import 문 리스트

    Returns:
        외부 패키지 이름 리스트 (정렬됨)
    """
    packages = set()
    for imp in imports:
        match = re.match(r'^(?:from\s+(\w+)|import\s+(\w+))', imp.strip())
        if match:
            pkg = match.group(1) or match.group(2)
            if pkg.lower() not in STDLIB_MODULES:
                packages.add(pkg)

    return sorted(packages)
