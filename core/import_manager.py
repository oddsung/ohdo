# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Import 관리 모듈

코드에서 import 문을 추출/병합/조합하는 유틸리티.
스텝별 코드 분리와 export 시 import 중복 제거에 사용됩니다.
"""

import re

# Python 표준 라이브러리 목록 (import 분류용)
STDLIB_MODULES = frozenset(
    {
        "os",
        "sys",
        "time",
        "json",
        "pathlib",
        "subprocess",
        "re",
        "datetime",
        "collections",
        "functools",
        "itertools",
        "typing",
        "dataclasses",
        "abc",
        "io",
        "logging",
        "shutil",
        "tempfile",
        "threading",
        "queue",
        "uuid",
        "hashlib",
        "base64",
        "glob",
        "math",
        "random",
        "string",
        "traceback",
        "copy",
        "enum",
        "csv",
        "sqlite3",
        "http",
        "urllib",
        "email",
        "html",
        "xml",
        "ctypes",
        "struct",
        "socket",
        "ssl",
        "asyncio",
        "multiprocessing",
        "concurrent",
        "contextlib",
        "inspect",
        "unittest",
        "pprint",
        "textwrap",
        "warnings",
        "signal",
        "platform",
        "getpass",
        "configparser",
        "argparse",
        "pickle",
        "shelve",
        "zipfile",
        "tarfile",
        "gzip",
        "bz2",
        "lzma",
        "webbrowser",
        "tkinter",
        "codecs",
        "locale",
        "struct",
        "operator",
        "heapq",
        "bisect",
        "array",
        "decimal",
        "fractions",
        "statistics",
        "secrets",
        "hmac",
        "difflib",
        "fileinput",
    }
)


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

    lines = code.split("\n")
    import_lines = []
    body_start = 0
    in_header = True

    for i, line in enumerate(lines):
        stripped = line.strip()

        if in_header:
            # 상단 영역: import문, 빈 줄, 주석, docstring 시작/끝 허용
            if stripped.startswith(("import ", "from ")):
                import_lines.append(line.rstrip())
                body_start = i + 1
            elif stripped == "" or stripped.startswith("#"):
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
    body_code = "\n".join(body_lines).strip()

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
        match = re.match(r"^(?:from\s+(\w+)|import\s+(\w+))", imp)
        module = (match.group(1) or match.group(2)) if match else ""
        is_stdlib = 0 if module.lower() in STDLIB_MODULES else 1
        is_from = 1 if imp.startswith("from") else 0
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
        parts.append("\n".join(imports))
        parts.append("")  # import와 코드 사이 빈 줄

    # 스텝 코드 순서대로 결합
    for entry in step_entries:
        if isinstance(entry, tuple):
            step_id, task_name, code = entry
            code = code.strip()
            if not code:
                continue
            # task_name 정규화: 줄바꿈 → 공백, 50자 제한
            task_name = " ".join(task_name.splitlines()).strip()
            if len(task_name) > 50:
                task_name = task_name[:47] + "..."
            parts.append(f"# === Step {step_id}: {task_name} (시작) ===")
            parts.append(code)
            parts.append(f"# === Step {step_id}: {task_name} (끝) ===")
        else:
            code = entry.strip()
            if code:
                parts.append(code)

    return "\n\n".join(parts)


def extract_initial_block(session) -> str:
    """모듈 레벨 변수/상수 정의 추출 — Initial 블럭용.

    세션의 **첫 step (step_id=1)** 의 generated_code 만 사용 — step 1 이 보통
    setup (driver, options 등) 정의 + 첫 액션 위주라 initial 추출에 적합.
    마지막 step 의 generated_code 는 step 별 element_pwa_4, rect_pwa_5 같은
    누적 변수가 다 들어가서 부적합.

    추출 대상:
    - 모듈 레벨 ast.Assign (URL, CONFIG, 등 상수 정의)
    - 모듈 레벨 try 블록 안 ast.Assign (driver, options, app 등 setup)

    제외: 함수/클래스 정의 (= library_block), if/while/for 블록 안 변수.

    Args:
        session: Session 객체. session.steps[0] (첫 step) 의 generated_code 사용.

    Returns:
        Assign 들을 한 줄씩 concatenate. AST 파싱 실패 / step 없음 / Assign 없으면
        빈 문자열.
    """
    if not session or not session.steps:
        return ""
    first_step = session.steps[0]
    generated_code = first_step.get("generated_code", "") if isinstance(first_step, dict) else ""
    if not generated_code or not generated_code.strip():
        return ""
    # def main() 패턴이면 먼저 unwrap (변수가 함수 안에 있을 수 있음)
    code = _unwrap_main_function(generated_code)
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ""
    initial_lines: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            try:
                initial_lines.append(ast.unparse(node))
            except Exception:
                continue
        elif isinstance(node, ast.Try):
            # 모듈 레벨 try 블록 — 안의 Assign 도 setup (driver, options, app 등)
            for sub in node.body:
                if isinstance(sub, ast.Assign):
                    try:
                        initial_lines.append(ast.unparse(sub))
                    except Exception:
                        continue
    return "\n".join(initial_lines).strip()


def _unwrap_main_function(code: str) -> str:
    """AI 가 ``def main(): ... ; if __name__ == "__main__": main()`` 패턴으로
    감싸서 작성한 경우 main 함수 본문을 module-level 로 unwrap.

    Jupyter 모드 호환: driver, app 같은 변수가 main 함수 local scope 면 다음
    step 에서 못 씀 (NameError). 본문을 module-level 로 펼쳐 _globals 에 노출.

    AST 기반 — `ast.parse` 실패 (syntax error) 시 원본 그대로 반환.
    main 함수 없으면 원본 그대로.

    Returns:
        unwrap 된 코드 (main 함수 정의 + if __name__ 블록 제거, main 본문이
        그 자리에 module-level 로 삽입). 실패 시 원본.
    """
    if not code or not code.strip():
        return code
    if "def main(" not in code:
        return code  # 빠른 path — main 함수 없으면 처리 불필요

    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code

    main_func = None
    new_body: list = []
    for node in tree.body:
        # def main(): 함수 정의 — 본문만 따로 보관
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            main_func = node
            continue
        # if __name__ == "__main__": 블록 제거 (main() 호출 라인 자동 제거)
        if isinstance(node, ast.If):
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
            ):
                continue
        new_body.append(node)

    if main_func is None:
        return code  # main 함수 없으면 unwrap 대상 아님

    # main 함수 본문을 module-level 로 추가
    new_body.extend(main_func.body)
    tree.body = new_body

    try:
        return ast.unparse(tree)
    except Exception:
        return code


def _smart_dedent(code: str) -> str:
    """code 의 공통 indent 제거 — 코드 라인 (주석/빈 줄 제외) 의 최소 indent 기준.

    delta 추출 시 try/except 블록 안의 라인들만 추출되면 들여쓰기 4 칸이
    그대로 남아 module-level 실행 시 IndentationError. 이 함수가 자동 정리.

    Args:
        code: 추출된 delta 또는 코드 블록.

    Returns:
        공통 indent 제거된 코드. indent 가 이미 0 이면 그대로 반환.
    """
    if not code or not code.strip():
        return code
    lines = code.split("\n")
    code_lines = [ln for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]
    if not code_lines:
        return code
    common_indent = min(len(ln) - len(ln.lstrip()) for ln in code_lines)
    if common_indent == 0:
        return code
    result = []
    for line in lines:
        if len(line) - len(line.lstrip()) >= common_indent:
            result.append(line[common_indent:])
        else:
            # indent 가 common_indent 보다 적은 라인 (boundary 주석 등) — 그대로
            result.append(line)
    return "\n".join(result)


def extract_code_delta(new_body: str, prev_body: str) -> str:
    """
    새 누적 코드 body에서 이전 body 이후에 추가된 부분만 추출합니다.

    AI는 매번 전체 누적 코드를 생성하므로, 이번 스텝에서 새로 추가된 코드를
    얻으려면 두 가지 path:
      1. **prefix 매칭** (빠른 path): 이전 코드가 새 코드의 prefix 와 정확히
         일치하면 그 뒤가 delta.
      2. **SequenceMatcher diff** (fallback): AI 가 이전 코드를 약간 다듬은
         경우 (들여쓰기, try 위치 등) prefix 매칭 실패. line-level diff 로
         새/변경된 라인만 추출.

    Args:
        new_body: 이번 스텝의 전체 body (import 제외)
        prev_body: 이전 스텝의 전체 body (import 제외)

    Returns:
        이번 스텝에서 새로 추가된 코드. 모든 추출 실패 시 new_body 전체 반환.
    """
    if not prev_body or not prev_body.strip():
        return _smart_dedent(_unwrap_main_function(new_body))  # 첫 스텝

    new_lines = new_body.split("\n")
    prev_lines = prev_body.rstrip().split("\n")

    # ── 1) prefix 매칭 (빠른 path) ──
    n = len(prev_lines)
    if len(new_lines) >= n:
        prev_stripped = [line.rstrip() for line in prev_lines]
        new_prefix_stripped = [line.rstrip() for line in new_lines[:n]]

        if prev_stripped == new_prefix_stripped:
            delta_lines = new_lines[n:]
            while delta_lines and not delta_lines[0].strip():
                delta_lines.pop(0)
            result = "\n".join(delta_lines).strip()
            if result:
                return _smart_dedent(_unwrap_main_function(result))
            return _smart_dedent(_unwrap_main_function(new_body))

    # ── 2) SequenceMatcher diff (fallback) ──
    # AI 가 이전 코드를 약간 변경해서 prefix 매칭 실패한 경우.
    # opcodes 의 'insert' / 'replace' 의 b 측 (= 새 코드) 만 추출.
    import difflib

    prev_stripped = [line.rstrip() for line in prev_lines]
    new_stripped = [line.rstrip() for line in new_lines]
    sm = difflib.SequenceMatcher(
        a=prev_stripped,
        b=new_stripped,
        autojunk=False,
    )
    # ratio 가 너무 낮으면 (거의 다른 코드) diff 의미 없음 → 전체 반환
    if sm.ratio() < 0.3:
        return _smart_dedent(_unwrap_main_function(new_body))

    delta_lines: list[str] = []
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            delta_lines.extend(new_lines[j1:j2])

    # 앞뒤 빈 줄 정리
    while delta_lines and not delta_lines[0].strip():
        delta_lines.pop(0)
    while delta_lines and not delta_lines[-1].strip():
        delta_lines.pop()

    # SequenceMatcher 위치 기반 매칭의 한계 — prev 에 동일 라인이 있으면 제거.
    # except 블록 안의 print 같은 stale 단편 방지.
    # 단, 컨트롤 헤더 (try:, except, else:, if:, for:, etc.) 는 prev 에 같은 패턴이
    # 있어도 새 try/if/for 블록의 일부일 수 있음 — 헤더만 제거되면 본문이 module-level
    # 로 평면화되어 try/except 의 의미가 깨지는 버그가 발생 (5/4 발견).
    _control_header_re = re.compile(
        r"^(try|except|else|elif|finally|if|for|while|with|def|class)\b"
    )
    prev_set = {ln.strip() for ln in prev_stripped if ln.strip()}
    filtered: list[str] = []
    for line in delta_lines:
        s = line.strip()
        if not s or s.startswith("#"):
            filtered.append(line)
            continue
        if s in prev_set and not _control_header_re.match(s):
            continue
        filtered.append(line)
    delta_lines = filtered

    # except 캡처 변수 (e, ex, exc 등) 가 prev 에만 있고 delta 에 except 가 없는데
    # delta 에서 그 변수를 참조하면 NameError. 그 라인 제거.
    # 예: prev 에 `except Exception as e:`, delta 에 `print(f"오류: {e}")` 만 있음.
    import re as _re

    delta_has_except = any(_re.search(r"\bexcept\b", ln) for ln in delta_lines)
    if not delta_has_except:
        # prev 의 except 캡처 변수명 모두 추출
        captured_vars: set[str] = set()
        for ln in prev_lines:
            for m in _re.finditer(
                r"\bexcept\s+[\w\s,()]+?\s+as\s+(\w+)\s*:",
                ln,
            ):
                captured_vars.add(m.group(1))
        if captured_vars:
            cleaned: list[str] = []
            for line in delta_lines:
                s = line.strip()
                if not s or s.startswith("#"):
                    cleaned.append(line)
                    continue
                # 캡처 변수명을 word boundary 로 참조하는 라인이면 제거
                if any(_re.search(rf"\b{_re.escape(v)}\b", line) for v in captured_vars):
                    continue
                cleaned.append(line)
            delta_lines = cleaned

    # .strip() 사용 안 함 — 첫 라인의 indent 가 잘리면 _smart_dedent 가 못 풀어줌.
    # 빈 줄 정리는 위 while loop 에서 이미 처리됨.
    result = "\n".join(delta_lines)
    # diff 결과 비어있거나 거의 전체 (90%+) 면 신뢰 못 함 → 전체 반환 (경계 주석으로 감쌈)
    if not result.strip() or len(result) >= len(new_body) * 0.9:
        return _smart_dedent(_unwrap_main_function(new_body))

    return _smart_dedent(_unwrap_main_function(result))


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
        match = re.match(r"^(?:from\s+(\w+)|import\s+(\w+))", imp.strip())
        if match:
            pkg = match.group(1) or match.group(2)
            if pkg.lower() not in STDLIB_MODULES:
                packages.add(pkg)

    return sorted(packages)
