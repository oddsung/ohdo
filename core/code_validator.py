# SPDX-License-Identifier: AGPL-3.0-or-later
"""AI 가 생성한 step 코드의 정적 분석기 (Phase 1.8 G7-A).

배경 (handoff §16 잔존 갭):
    DeepSeek-V3 같은 모델이 system_context 의 가이드를 100% 따르지 않아
    메모장 step 3/4 에서 다음 회귀가 발생:
      1. ``app``/``win`` 변수 재정의 (jupyter mode 호환 위반)
      2. risky 호출 (pyautogui.click 등) 의 try/except 누락
      3. 들여쓰기 깨짐 (SyntaxError 가능)
      4. ``import pyperclip`` 이 try 블록 안 (P3 #5 위반)

    프롬프트 가이드 강화 (G6 등) 로는 100% 보장 불가 → AI 가 코드를 만든 직후,
    실행 전에 우리 측에서 자동으로 검사. 본 모듈은 검사 엔진 (순수 함수, side
    effect 없음) 만 담당 — UI 표시 / AI 재호출 hook 은 G7-B/C/D 단계.

검사 항목 5종:
    1. ``syntax``             : ``ast.parse`` 실패 (SyntaxError / IndentationError)
    2. ``redefined_var``      : 이전 step 들의 module-level 할당 변수가 현재 step
                                에서 다시 module-level 로 할당됨 (jupyter mode 깨짐)
    3. ``missing_try``        : risky 호출이 try 블록 밖 module-level 또는
                                top-level 함수 정의 밖에 있음
    4. ``import_misplaced``   : ``Import`` / ``ImportFrom`` 가 module top 이 아닌
                                try / def / class / if / for / while / with 안
    5. ``hardcoded_secret``   : 코드의 문자열 리터럴에 평문 비밀번호 / 토큰 /
                                API 키 패턴 발견 ([ADR 0003](../docs/saas/decisions/
                                0003-secrets-handling.md) Phase 1 C2)

False positive 최소화 정책:
    - 함수 정의 (``def`` / ``async def``) 내부의 risky 호출은 검사 제외 — 호출자
      측에서 try 로 wrap 하면 충분 (예: ``_resolve_element`` helper).
    - try.body / except.body / finally.body 모두 protected 로 간주.
    - module-level Assign / AnnAssign 만 변수 재정의 검사 — for-target / 함수
      안 변수는 무관.
    - dynamic dispatch (``getattr(pyautogui, 'click')(...)``) 는 정적 분석 불가
      → 못 잡음 (의도적 false negative).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

__all__ = [
    "ValidationIssue",
    "ValidationResult",
    "validate_step_code",
    "RISKY_CALL_NAMES",
    "RISKY_MODULE_ATTRS",
    "SECRET_CONFIDENCE_THRESHOLD",
]


# ─────────────────────────────────────────────────────────
# Hardcoded secret 검사 임계
# ─────────────────────────────────────────────────────────

# secrets_detector.detect 결과 중 이 값 이상 confidence 만 warning 으로 채택.
# 0.85 = JWT / AWS / GH PAT / OpenAI / 명시 password hint 만. high_entropy 일반
# 토큰은 false-positive 비율 높아 코드 스캔에선 제외 (사용자 입력 스캔 A1 에서는
# threshold 낮춰 0.5 권장 — UI 가 사용자에게 confirm 받으므로 FP 비용 낮음).
SECRET_CONFIDENCE_THRESHOLD: float = 0.85


# ─────────────────────────────────────────────────────────
# Risky 호출 화이트리스트
# ─────────────────────────────────────────────────────────

# attribute 또는 단순 호출 이름. method 호출 (x.click()) / 직접 호출 (Application())
# 양쪽 모두 매칭. dynamic 한 attribute 형태는 못 잡음 (정적 분석 한계).
RISKY_CALL_NAMES: frozenset[str] = frozenset(
    {
        # pywinauto / pywinauto.Application
        "Application",
        "connect",
        "start",
        "window",
        "child_window",
        # pywinauto control 메서드 (어떤 객체의 method 든 이 이름이면 risky)
        "click",
        "click_input",
        "double_click",
        "double_click_input",
        "right_click",
        "right_click_input",
        "send_keys",
        "type_keys",
        "set_focus",
        "set_text",
        "set_edit_text",
        "select",
        "invoke",
        "wait",
        "wait_not",
        # selenium WebDriver / WebElement
        "find_element",
        "find_elements",
        "execute_script",
        "send_keys_to_element",
        "get",
    }
)

# module.attr 호출 형식. 예: ``pyautogui.click(...)`` → ('pyautogui', 'click').
# RISKY_CALL_NAMES 와 중복인 'click' 도 명시 (모듈 호출인지 method 인지 구분 출력).
RISKY_MODULE_ATTRS: dict[str, frozenset[str]] = {
    "pyautogui": frozenset(
        {
            "click",
            "doubleClick",
            "rightClick",
            "moveTo",
            "moveRel",
            "dragTo",
            "write",
            "typewrite",
            "press",
            "hotkey",
            "keyDown",
            "keyUp",
            "screenshot",
        }
    ),
    "pyperclip": frozenset({"copy", "paste"}),
    "subprocess": frozenset(
        {
            "run",
            "Popen",
            "call",
            "check_call",
            "check_output",
        }
    ),
    "os": frozenset({"system", "startfile", "popen"}),
    "shutil": frozenset({"copy", "copytree", "move", "rmtree"}),
}


# ─────────────────────────────────────────────────────────
# 결과 데이터 클래스
# ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ValidationIssue:
    """단일 검사 위반."""

    kind: str  # "syntax" | "redefined_var" | "missing_try" | "import_misplaced"
    message: str
    line: int = 0  # 1-based source line. 0 이면 위치 정보 없음.


@dataclass
class ValidationResult:
    """``validate_step_code`` 의 반환값."""

    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)

    @property
    def has_syntax_error(self) -> bool:
        return any(i.kind == "syntax" for i in self.issues)

    def by_kind(self, kind: str) -> list[ValidationIssue]:
        return [i for i in self.issues if i.kind == kind]


# ─────────────────────────────────────────────────────────
# AST 헬퍼
# ─────────────────────────────────────────────────────────


def _extract_target_names(target: ast.expr, names: set[str]) -> None:
    """할당 대상에서 단순 변수 이름만 수집. 튜플/리스트 풀어내기."""
    if isinstance(target, ast.Name):
        names.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _extract_target_names(elt, names)
    elif isinstance(target, ast.Starred):
        _extract_target_names(target.value, names)


def _collect_module_level_assigns(tree: ast.Module) -> set[str]:
    """모듈 본문 + 모듈 본문의 try 블록까지의 단순 변수 할당 target.

    함수 / 클래스 정의 내부, for-target, with as-target 은 제외 — 이전 step 의
    module-level 변수만 jupyter mode 의 globals 에 영구 들어감.
    """
    names: set[str] = set()

    def _scan_block(stmts: list[ast.stmt]) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.Assign):
                for tgt in stmt.targets:
                    _extract_target_names(tgt, names)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                names.add(stmt.target.id)
            elif isinstance(stmt, ast.Try):
                _scan_block(stmt.body)
                for handler in stmt.handlers:
                    _scan_block(handler.body)
                _scan_block(stmt.orelse)
                _scan_block(stmt.finalbody)
            elif isinstance(stmt, ast.If):
                _scan_block(stmt.body)
                _scan_block(stmt.orelse)

    _scan_block(tree.body)
    return names


def _classify_call(call: ast.Call) -> Optional[str]:
    """호출 노드가 risky 면 표시명, 아니면 None.

    표시명 형식:
      - 모듈 호출:  ``pyautogui.click()``
      - method 호출: ``.click()``
      - 단순 호출:  ``Application()``
    """
    func = call.func
    if isinstance(func, ast.Name):
        if func.id in RISKY_CALL_NAMES:
            return f"{func.id}()"
        return None
    if isinstance(func, ast.Attribute):
        attr = func.attr
        # module.attr() 패턴 우선 (pyautogui.click 가 .click() 보다 정보 많음)
        if isinstance(func.value, ast.Name):
            mod = func.value.id
            if mod in RISKY_MODULE_ATTRS and attr in RISKY_MODULE_ATTRS[mod]:
                return f"{mod}.{attr}()"
        if attr in RISKY_CALL_NAMES:
            return f".{attr}()"
    return None


def _find_unprotected_risky_calls(tree: ast.Module) -> list[tuple[ast.Call, str]]:
    """try 블록 밖의 risky 호출 수집.

    함수 정의 (``def`` / ``async def``) 내부는 검사 제외 — 호출자가 wrap 하면
    충분. lambda 안의 호출도 동일 정책 (lambda 자체가 def 와 같이 helper).
    """
    found: list[tuple[ast.Call, str]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.try_depth = 0
            self.func_depth = 0

        def visit_Try(self, node: ast.Try) -> None:
            self.try_depth += 1
            for stmt in node.body:
                self.visit(stmt)
            for handler in node.handlers:
                for stmt in handler.body:
                    self.visit(stmt)
            for stmt in node.orelse:
                self.visit(stmt)
            for stmt in node.finalbody:
                self.visit(stmt)
            self.try_depth -= 1

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.func_depth += 1
            self.generic_visit(node)
            self.func_depth -= 1

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.func_depth += 1
            self.generic_visit(node)
            self.func_depth -= 1

        def visit_Lambda(self, node: ast.Lambda) -> None:
            self.func_depth += 1
            self.generic_visit(node)
            self.func_depth -= 1

        def visit_Call(self, node: ast.Call) -> None:
            if self.try_depth == 0 and self.func_depth == 0:
                kind = _classify_call(node)
                if kind is not None:
                    found.append((node, kind))
            self.generic_visit(node)

    Visitor().visit(tree)
    return found


def _find_misplaced_imports(tree: ast.Module) -> list[ast.stmt]:
    """모듈 최상단 외에 위치한 ``Import`` / ``ImportFrom``.

    handoff §16 P3 #5 정의: "모든 import 는 코드의 가장 최상단에만. try / except
    / 함수 / step 본문 안 import 금지". 즉 module body 의 직계 import 만 OK.
    """
    misplaced: list[ast.stmt] = []

    # 모듈 body 의 직계 Import / ImportFrom 은 OK (코드 최상단). 그 외 모든
    # 위치 (try / def / class / if / for / while / with 안) 의 import 는 위반.
    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            continue
        for sub in ast.walk(stmt):
            if isinstance(sub, (ast.Import, ast.ImportFrom)):
                misplaced.append(sub)

    return misplaced


def _find_hardcoded_secrets(
    tree: ast.Module,
) -> list[tuple[ast.AST, str, str]]:
    """AST 의 ``Constant(str)`` 리터럴에서 평문 비밀 패턴 검색.

    [ADR 0003](../docs/saas/decisions/0003-secrets-handling.md) Phase 1 C2.

    Returns:
        list[(node, secret_kind, masked_preview)] — node 는 lineno 추출용,
        secret_kind 는 `secrets_detector.SecretMatch.kind`, masked_preview 는
        UI / 메시지용 (앞 4자 + ...).

    정책:
      - ``{{secret:label}}`` placeholder 자체는 검사 통과 (정상 패턴).
      - 매우 짧은 리터럴 (< 16 char) 은 명시 토큰 prefix 가 없는 한 skip — 짧은
        문자열에 entropy/AWS 등 매칭은 사실상 false-positive.
      - confidence < ``SECRET_CONFIDENCE_THRESHOLD`` 는 skip (high_entropy 등).
    """
    from .secrets_detector import detect as _detect_secrets

    findings: list[tuple[ast.AST, str, str]] = []
    placeholder_re = re.compile(r"\{\{secret:[a-z0-9_]{1,32}\}\}")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        s = node.value
        if not s or len(s) < 4:
            continue
        # placeholder 만 들어있으면 정상
        if placeholder_re.fullmatch(s.strip()):
            continue
        for m in _detect_secrets(s):
            if m.confidence < SECRET_CONFIDENCE_THRESHOLD:
                continue
            # 너무 짧은 generic 매칭 skip (위의 명시 토큰 prefix 체크는 confidence
            # threshold 가 처리)
            preview = m.value[:4] + "..." if len(m.value) > 4 else m.value
            findings.append((node, m.kind, preview))

    return findings


# ─────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────


def validate_step_code(
    step_code: str,
    *,
    prev_step_codes: Iterable[str] = (),
) -> ValidationResult:
    """AI 가 생성한 step delta 코드를 정적 분석.

    Args:
        step_code: 이번 step 의 step_code (import 분리 후의 본문).
            ``library_block`` (essential imports 가 prepend 된 부분) 은 별도로
            처리되므로 본 함수에 넘기지 않음.
        prev_step_codes: 이전 step 들의 step_code (변수 재정의 검사용). 순서
            무관 (전부 union).

    Returns:
        ``ValidationResult`` — issues 빈 리스트면 검사 통과.
    """
    result = ValidationResult()

    if not step_code or not step_code.strip():
        return result

    try:
        tree = ast.parse(step_code)
    except SyntaxError as exc:
        result.issues.append(
            ValidationIssue(
                kind="syntax",
                message=f"문법 오류: {exc.msg}",
                line=exc.lineno or 0,
            )
        )
        return result

    # 변수 재정의 검사 — 이전 step 들의 module-level 할당 모음과 교집합
    prev_names: set[str] = set()
    for prev in prev_step_codes:
        if not prev or not prev.strip():
            continue
        try:
            prev_tree = ast.parse(prev)
        except SyntaxError:
            continue
        prev_names |= _collect_module_level_assigns(prev_tree)

    if prev_names:
        cur_names = _collect_module_level_assigns(tree)
        for name in sorted(cur_names & prev_names):
            result.issues.append(
                ValidationIssue(
                    kind="redefined_var",
                    message=(
                        f"이전 step 에서 정의된 변수 '{name}' 를 다시 정의했습니다 "
                        "(jupyter mode 호환 깨짐)."
                    ),
                )
            )

    # try/except 누락 검사
    for call_node, kind in _find_unprotected_risky_calls(tree):
        result.issues.append(
            ValidationIssue(
                kind="missing_try",
                message=f"위험한 호출 '{kind}' 가 try/except 로 보호되지 않았습니다.",
                line=getattr(call_node, "lineno", 0),
            )
        )

    # import 위치 위반 검사
    for imp in _find_misplaced_imports(tree):
        result.issues.append(
            ValidationIssue(
                kind="import_misplaced",
                message="import 가 코드 최상단이 아닌 곳에 있습니다 (try / def / if 등 안).",
                line=getattr(imp, "lineno", 0),
            )
        )

    # hardcoded_secret 검사 (ADR 0003 Phase 1 C2)
    for node, secret_kind, preview in _find_hardcoded_secrets(tree):
        result.issues.append(
            ValidationIssue(
                kind="hardcoded_secret",
                message=(
                    f"코드에 평문 비밀 정보로 보이는 값이 박혀 있습니다 "
                    f"({secret_kind}: '{preview}'). "
                    "get_secret('label') 로 vault 참조 패턴 사용 권장."
                ),
                line=getattr(node, "lineno", 0),
            )
        )

    return result
