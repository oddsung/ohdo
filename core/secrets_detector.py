# SPDX-License-Identifier: AGPL-3.0-or-later
"""사용자 텍스트 / 생성 코드에서 비밀 정보 후보 감지.

[ADR 0003](../docs/saas/decisions/0003-secrets-handling.md) Phase 1 의 공유 모듈.

쓰는 곳:
  - C2 (code_validator.validate_step_code) — AI 가 생성한 코드의 문자열 리터럴
    스캔. 평문 박힌 토큰 (JWT/AWS/GH PAT/OpenAI/...) 발견 시
    ValidationIssue(kind='hardcoded_secret') 발행 → 카드에 ⚠ 표시 + 재생성 prompt.
  - A1 (ui_v2._on_send_message, Phase 2) — 사용자 입력 텍스트 스캔. detect()
    결과로 ⚠ 모달 띄워 시크릿 입력 UI 로 유도.

설계 원칙:
  - 정규식은 **명확한 시크릿 포맷 우선** (false-positive 최소화). 길이/엔트로피
    기반 generic 매칭은 confidence 낮춤.
  - 한국어 / 영어 hint 키워드 양쪽 커버.
  - 호출자가 confidence 로 필터링 — 본 모듈은 모두 반환.
  - 결정적 (동일 입력 → 동일 출력). 학습 / 외부 호출 없음.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

__all__ = [
    "SecretMatch",
    "detect",
    "detect_with_elements",
    "is_password_field_element",
    "PATTERN_KINDS",
]


# ─────────────────────────────────────────────────────────
# 매칭 결과
# ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SecretMatch:
    """단일 매칭. UI / 정적 분석기 양쪽이 공유."""

    span: tuple[int, int]
    """원문 안 위치 (start, end). end 는 exclusive."""

    kind: str
    """매칭 종류 — `PATTERN_KINDS` 중 하나."""

    value: str
    """매칭된 부분 텍스트 (마스킹 / 라벨 자동 생성용)."""

    confidence: float
    """0.0~1.0. 0.9+ 는 고정 포맷, 0.5~0.85 는 entropy 기반."""

    suggested_label: str
    """vault 등록 시 기본 label 제안. UI 가 사용자에게 보여주고 편집 가능."""


PATTERN_KINDS: frozenset[str] = frozenset(
    {
        "password_hint",
        "jwt",
        "aws_key",
        "github_pat",
        "openai_key",
        "anthropic_key",
        "google_api_key",
        "slack_token",
        "high_entropy",
        "quoted_literal",
        "password_field_element",
    }
)


# ─────────────────────────────────────────────────────────
# 명시 패턴 (높은 confidence)
# ─────────────────────────────────────────────────────────

# password / 비밀번호 / 비번 / api_key 등 키워드 + 값. ASCII-only 짧은 값도 잡되,
# 너무 짧으면 ('pw: 1' 같은 false 사례) 무시. 값은 공백/줄바꿈/따옴표 전까지.
_PASSWORD_HINT = re.compile(
    r"(?P<key>비밀번호|비번|패스워드|password|passwd|pwd|pw|api[_-]?key|secret|token)"
    r"\s*(?:[:=은는])\s*['\"]?(?P<val>[^\s'\"<>]{4,256})['\"]?",
    re.IGNORECASE,
)

# JSON Web Token — 3 segment base64url
_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")

# AWS access key — AKIA + 16 uppercase alnum
_AWS_KEY = re.compile(r"AKIA[0-9A-Z]{16}")

# GitHub personal access token — ghp_ + 36 alnum
_GH_PAT = re.compile(r"ghp_[A-Za-z0-9]{36}")

# OpenAI API key — sk- 또는 sk-proj- prefix
_OPENAI = re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}")

# Anthropic API key — sk-ant- + 길이가 더 김
_ANTHROPIC = re.compile(r"sk-ant-[A-Za-z0-9_\-]{30,}")

# Google API key — AIza + 35 alnum + url-safe
_GOOGLE = re.compile(r"AIza[0-9A-Za-z_\-]{35}")

# Slack token — xox[abprs]- + 길이
_SLACK = re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}")

# 일반 high-entropy 후보. 길이 20+ 의 url-safe / hex 토큰. entropy 검사로 통과해야 match.
# 너무 짧은 영숫자 (변수명, 클래스명) false-positive 회피.
_GENERIC_TOKEN = re.compile(r"[A-Za-z0-9_\-/+=]{20,}")


# 따옴표 안 사용자 입력값 패턴 — RPA 자연어에서 가장 흔한 PW 박힘 케이스.
# 예: "...클릭하고 '@06dhentjd%@%^' 입력" — 사용자가 명시적 "비밀번호" 키워드 없이
# 그냥 따옴표 안 값을 적는 패턴.
# 영문 single quote, double quote, 한글 따옴표 ('') 모두 매칭.
_QUOTED_LITERAL = re.compile(r"""(?:['"‘“])(?P<val>[^'"‘’“”\n\r]{6,128})(?:['"’”])""")

# RPA 입력 동사 — 따옴표 값 인접 (앞 50자 이내) 에 있으면 confidence boost.
# 사용자가 "입력", "타이핑", "write" 같은 동사로 RPA 입력 의도 명시 = 값이
# placeholder 가 아니라 실제 데이터 (잠재 시크릿).
_RPA_INPUT_VERBS = re.compile(
    r"(입력|타이핑|타이프|쳐|입렦|보내|전송|write|type|enter|fill|paste|복붙|붙여|paste|send)",
    re.IGNORECASE,
)

# Skip list — false-positive 회피. 따옴표 안에 이런 값이면 시크릿으로 간주 X.
# UI 라벨, 키 이름, 흔한 명령어, element name 메타 문자.
_SKIP_QUOTED_LITERALS: frozenset[str] = frozenset(
    {
        # UI 라벨 (한국어)
        "확인",
        "취소",
        "닫기",
        "저장",
        "열기",
        "시작",
        "종료",
        "적용",
        "다음",
        "이전",
        "확정",
        "선택",
        "삭제",
        "추가",
        "편집",
        "복사",
        "붙여넣기",
        "잘라내기",
        "되돌리기",
        "다시",
        "찾기",
        "바꾸기",
        "로그인",
        "로그아웃",
        "회원가입",
        "내보내기",
        "가져오기",
        "인쇄",
        "예",
        "아니오",
        "네",
        "아니요",
        # UI 라벨 (영문)
        "ok",
        "cancel",
        "close",
        "save",
        "open",
        "exit",
        "apply",
        "next",
        "previous",
        "submit",
        "confirm",
        "select",
        "delete",
        "add",
        "edit",
        "copy",
        "paste",
        "cut",
        "undo",
        "redo",
        "find",
        "replace",
        "login",
        "logout",
        "signup",
        "export",
        "import",
        "yes",
        "no",
        "back",
        "home",
        # 키 이름
        "enter",
        "tab",
        "esc",
        "escape",
        "space",
        "backspace",
        "delete",
        "shift",
        "ctrl",
        "alt",
        "win",
        "cmd",
        "return",
        # element-name 메타 / placeholder
        "￼",  # object replacement character
        "none",
        "null",
        "todo",
        "fixme",
        "empty",
        "default",
        "placeholder",
    }
)


def _has_special_chars(s: str) -> bool:
    """문자열에 PW-style 특수문자 (`!@#$%^&*+=`) 가 포함되어 있는지."""
    return any(c in "!@#$%^&*+=~`<>?,;|\\:" for c in s)


def _is_pure_word(s: str) -> bool:
    """순수 영문 단어 (특수문자 / 숫자 없음). 'doosung' 같은 평범한 식별자.

    PW 후보에서 제외 — 사용자 ID / 영문 이름 등은 시크릿이 아닌 경우 많음.
    한글이나 다른 문자가 포함되면 False (단순 영문만 검사).
    """
    if not s:
        return False
    return all(c.isalpha() and ord(c) < 128 for c in s)


def _is_natural_language(s: str) -> bool:
    """일반 자연어(문장/단어)로 보이면 True — 자격증명 아님.

    비밀번호·토큰은 공백 없는 단일 토큰이고 보통 숫자/특수문자를 섞는다.
    반면 RPA 명령의 따옴표 값이
      (a) 내부 공백을 포함한 다중 단어 구절 ('안녕하세요 테스트입니다'), 또는
      (b) 숫자·특수문자 없이 글자(한글/영문 등)로만 이뤄진 단어
    면 입력하려는 일반 텍스트일 뿐 시크릿이 아니다.

    devloop #5 오탐 가드: 메모장 등에 일반 문장을 따옴표로 적어 RPA 입력할 때
    quoted_literal 이 0.55~0.75 로 잡혀 평문-시크릿 confirm 모달이 자동화를
    차단하던 문제. 명시 키워드(password_hint)/named token 경로는 별도라 영향 X.
    """
    # (a) 내부 공백 = 다중 단어 자연어 구절
    if any(c.isspace() for c in s):
        return True
    # (b) 숫자·특수문자 없이 글자로만 (스크립트 무관 — _is_pure_word 의 ASCII 한정
    #     을 한글 등 유니코드 글자까지 일반화). 자격증명은 entropy 위해 보통 숫자/
    #     특수문자를 섞으므로 순수 글자 단어는 라벨/텍스트로 본다.
    if s and all(c.isalpha() for c in s):
        return True
    return False


def _is_email_like(s: str) -> bool:
    """간단한 email/도메인 패턴 — name@host 또는 host.tld."""
    if "@" in s and "." in s.split("@", 1)[-1]:
        # name@host.tld
        local, host = s.split("@", 1)
        if local and host and "." in host and all(c.isalnum() or c in "._-" for c in s):
            return True
    # foo.bar.baz (URL/도메인) — 영숫자 + . - _
    if "." in s and all(c.isalnum() or c in ".-_" for c in s):
        # 적어도 한 segment 가 영문 시작이고 길이 2+
        parts = s.split(".")
        if len(parts) >= 2 and all(p and p[0].isalpha() for p in parts):
            return True
    return False


_NAMED_PATTERNS: tuple[tuple[str, re.Pattern[str], float, str], ...] = (
    # (kind, pattern, confidence, suggested_label_prefix)
    ("jwt", _JWT, 0.95, "jwt"),
    ("aws_key", _AWS_KEY, 0.99, "aws"),
    ("github_pat", _GH_PAT, 0.99, "github_pat"),
    ("anthropic_key", _ANTHROPIC, 0.97, "anthropic"),
    ("openai_key", _OPENAI, 0.95, "openai"),
    ("google_api_key", _GOOGLE, 0.95, "google_api"),
    ("slack_token", _SLACK, 0.95, "slack"),
)


# ─────────────────────────────────────────────────────────
# Entropy
# ─────────────────────────────────────────────────────────


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return not (a[1] <= b[0] or b[1] <= a[0])


# ─────────────────────────────────────────────────────────
# 공용 helper — 영어 단어 / Python 식별자처럼 보이는 토큰 skip
# ─────────────────────────────────────────────────────────


# 의미 있는 영어 단어로 보이는 토큰은 false-positive — entropy 높아도 skip.
# 모든 lower / 모든 upper / camelCase / snake_case 등 사람이 쓰는 식별자 패턴.
_LIKELY_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _looks_like_identifier(s: str) -> bool:
    """변수명 / 모듈 경로 / URL fragment 등 식별자 형태로 보이면 True.

    secrets 는 보통 영숫자 mix + 특수문자 (-, _, /, +, =) 와 무작위 분포.
    """
    if not _LIKELY_IDENTIFIER.match(s):
        return False
    # ohdo / mainwindow 처럼 사전적 단어 가능 — 자모 비율로 더 거름.
    # 자모 (영문) 비율 70% 이상 + 길이 30 이하면 identifier 로 판단.
    letters = sum(1 for c in s if c.isalpha())
    return letters / len(s) >= 0.7 and len(s) <= 30


# ─────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────


def detect(text: str, *, entropy_threshold: float = 4.5) -> list[SecretMatch]:
    """텍스트에서 비밀 정보 후보 반환. confidence 내림차순으로 정렬.

    Args:
        text: 검사 대상 (사용자 입력 또는 코드 문자열 리터럴).
        entropy_threshold: generic high-entropy 임계. 낮추면 false-positive 증가.

    Returns:
        list[SecretMatch] — span 이 겹치면 더 구체적 패턴 우선 (overlap drop).
    """
    if not text:
        return []

    matches: list[SecretMatch] = []

    # 1) 명시 토큰 패턴 (높은 confidence)
    for kind, pat, conf, label_prefix in _NAMED_PATTERNS:
        for m in pat.finditer(text):
            matches.append(
                SecretMatch(
                    span=m.span(),
                    kind=kind,
                    value=m.group(),
                    confidence=conf,
                    suggested_label=f"{label_prefix}_token",
                )
            )

    # 2) password / api_key 등 hint 키워드 (값 부분만 매칭)
    for m in _PASSWORD_HINT.finditer(text):
        span = m.span("val")
        if any(_overlaps(span, x.span) for x in matches):
            continue
        val = m.group("val")
        # 너무 짧거나 placeholder 같으면 skip
        if len(val) < 4 or val.lower() in {"none", "null", "empty", "todo", "fixme"}:
            continue
        key_lower = m.group("key").lower().replace(" ", "_")
        # 한글 키 ("비밀번호" 등) 도 ASCII label 로 정규화
        if any(ord(c) > 127 for c in key_lower):
            key_lower = "password"
        matches.append(
            SecretMatch(
                span=span,
                kind="password_hint",
                value=val,
                confidence=0.9,
                suggested_label=f"{key_lower}_value",
            )
        )

    # 3) 따옴표 안 사용자 입력값 — RPA 자연어의 가장 흔한 PW 박힘 패턴.
    #    "...클릭하고 '@06dhentjd%@%^' 입력" 같은 케이스.
    for m in _QUOTED_LITERAL.finditer(text):
        # val 캡처는 따옴표 안쪽만 (따옴표 자체 제외)
        val_span = m.span("val")
        if any(_overlaps(val_span, x.span) for x in matches):
            continue
        val = m.group("val")

        # skip list — UI 라벨, 키 이름, element-name 메타 등
        if val.lower() in _SKIP_QUOTED_LITERALS:
            continue
        # placeholder 자체 (다른 룰이 처리) — `{{secret:...}}` 형식 등
        if val.startswith("{{") and val.endswith("}}"):
            continue
        # email / URL / 도메인 모양 — 단순 식별자 (사용자 ID 등) skip
        if _is_email_like(val):
            continue
        # 순수 영문 단어 (특수문자 / 숫자 없음) — 'doosung' 같은 식별자 skip
        if _is_pure_word(val):
            continue
        # devloop #5 — 따옴표 안 일반 자연어(다중 단어 구절 / 순수 글자 단어)는
        # 시크릿 아님. 자격증명은 공백 없는 단일 토큰(보통 숫자/특수문자 mix).
        # '안녕하세요 테스트입니다' 같은 메모장 입력 텍스트 오탐 방지.
        if _is_natural_language(val):
            continue
        # 너무 짧으면 (PW 추정 임계 6자 미만) skip — _QUOTED_LITERAL 정규식이
        # 이미 6+ 강제하지만 안전망
        if len(val) < 6:
            continue

        # confidence — PW 특징에 따라 가중
        # 기본 0.55 (애매), 특수문자 mix +0.15, RPA 입력 동사 인접 +0.15
        conf = 0.55
        if _has_special_chars(val) and any(c.isalnum() for c in val):
            conf += 0.15
        # RPA 동사 인접성 — 따옴표 앞뒤 50자 윈도우에 동사 등장.
        # 한국어 "값 'X' 입력" (동사 뒤) + 영문 "type 'X'" (동사 앞) 양쪽 커버.
        pre_start = max(0, val_span[0] - 50)
        post_end = min(len(text), val_span[1] + 50)
        ctx = text[pre_start : val_span[0]] + " " + text[val_span[1] : post_end]
        if _RPA_INPUT_VERBS.search(ctx):
            conf += 0.15
        # 엔트로피가 높으면 추가 가중 (랜덤 토큰성)
        ent = _shannon_entropy(val)
        if ent >= 3.5:
            conf += 0.05

        matches.append(
            SecretMatch(
                span=val_span,
                kind="quoted_literal",
                value=val,
                confidence=round(min(conf, 0.85), 3),
                suggested_label="password",
            )
        )

    # 4) high-entropy generic (낮은 confidence). 위 패턴에 잡힌 영역은 skip.
    for m in _GENERIC_TOKEN.finditer(text):
        span = m.span()
        if any(_overlaps(span, x.span) for x in matches):
            continue
        val = m.group()
        if _looks_like_identifier(val):
            continue
        ent = _shannon_entropy(val)
        if ent < entropy_threshold:
            continue
        # confidence 는 entropy 기반 sliding — threshold 에서 0.5, 5.5+ 에서 0.85
        conf = min(0.5 + (ent - entropy_threshold) / 4.0, 0.85)
        matches.append(
            SecretMatch(
                span=span,
                kind="high_entropy",
                value=val,
                confidence=round(conf, 3),
                suggested_label="token",
            )
        )

    matches.sort(key=lambda x: (-x.confidence, x.span[0]))
    return matches


# ─────────────────────────────────────────────────────────
# Element-based detection (ADR 0003 PR-7)
# ─────────────────────────────────────────────────────────


# HTML input.name / input.id 또는 UIA automation_id 가 이 패턴과 매치되면 password field 로 추정.
# 너무 약한 패턴 ('p', 'ps' 단독 등) 은 false-positive 비용 큼 — 명확한 prefix 한정.
_PASSWORD_HINT_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])(passwd|password|userps|pswd|pwd|userpassword|"
    r"loginpassword|currentpassword|newpassword|confirmpassword)(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# 짧은 약어 hint — automation_id 짧은 케이스 ('ps' 같은) catch.
# 길이 가 정확히 패턴과 일치하는 경우만 (e.g. id="pw" 통째로).
_PASSWORD_SHORT_HINTS: frozenset[str] = frozenset({"pw", "ps", "pwd", "pswd", "pass"})

# Element 가 password 같은 입력 필드여도 사용자 ID/이메일/검색은 시크릿 아님.
# 이런 hint 가 name/id 에 있으면 password_field 가 아니라고 판정.
_NON_SECRET_FIELD_HINTS: frozenset[str] = frozenset(
    {
        "user",
        "username",
        "userid",
        "user_id",
        "userid_input",
        "loginid",
        "login_id",
        "email",
        "mail",
        "search",
        "query",
        "q",
        "input_search",
    }
)


def is_password_field_element(element_info: dict) -> tuple[bool, str]:
    """element_info 가 password 입력 필드를 가리키는지 판정.

    Returns:
        ``(is_password, reason)`` — reason 은 UI 안내용 (e.g. "HTML type=password",
        "UIA Edit + automation_id 'userPs'"). is_password=False 면 reason 은 "".

    판정 우선순위:
      1. **HTML `type="password"`** (Selenium dom_context.attributes) — 결정적
      2. HTML name / id 가 password-hint 패턴 — high
      3. UIA control_type="Edit" + automation_id 가 password-hint — medium
      4. 그 외 — False
    """
    if not element_info:
        return False, ""

    # 1) DOM HTML type="password" — 가장 결정적
    dom_ctx = element_info.get("dom_context") or {}
    if dom_ctx.get("cdp_available"):
        attrs = dom_ctx.get("attributes") or {}
        if isinstance(attrs, dict):
            html_type = (attrs.get("type") or "").lower().strip()
            if html_type == "password":
                return True, 'HTML type="password"'

            # 2) HTML name / id 가 명시 password-hint
            for attr_name in ("name", "id"):
                val = attrs.get(attr_name)
                if not isinstance(val, str) or not val:
                    continue
                lower = val.lower()
                if lower in _NON_SECRET_FIELD_HINTS:
                    return False, ""
                if _PASSWORD_HINT_TOKEN.search(val):
                    return True, f'HTML {attr_name}="{val}"'
                if lower in _PASSWORD_SHORT_HINTS:
                    return True, f'HTML {attr_name}="{val}"'

    # 3) UIA Edit + automation_id 가 password-hint
    ctrl_type = (element_info.get("control_type") or "").strip()
    auto_id = element_info.get("automation_id") or ""
    name = element_info.get("name") or ""

    if ctrl_type in {"Edit", "Document"} and isinstance(auto_id, str) and auto_id:
        if auto_id.lower() in _NON_SECRET_FIELD_HINTS:
            return False, ""
        if _PASSWORD_HINT_TOKEN.search(auto_id):
            return True, f'UIA Edit + automation_id="{auto_id}"'
        if auto_id.lower() in _PASSWORD_SHORT_HINTS:
            return True, f'UIA Edit + automation_id="{auto_id}"'

    # name 도 검사 (id 없을 때 fallback) — Korean 'password' 라벨 catch
    # name 은 단순 hint token + 한글 키워드 둘 다 시도
    if ctrl_type in {"Edit", "Document"} and isinstance(name, str) and name:
        lower = name.lower()
        if lower in _NON_SECRET_FIELD_HINTS:
            return False, ""
        if _PASSWORD_HINT_TOKEN.search(name):
            return True, f'UIA Edit + name="{name}"'
        # 한글 라벨
        if any(kw in name for kw in ("비밀번호", "비번", "패스워드", "암호")):
            return True, f'UIA Edit + name="{name}"'

    return False, ""


def detect_with_elements(
    text: str,
    elements: list[dict] | None = None,
    *,
    entropy_threshold: float = 4.5,
) -> list[SecretMatch]:
    """text-based detect() + element_info 기반 hint 결합.

    elements 중 하나라도 password field 면, text 안 따옴표 안 값은 (기존 룰에서
    skip 됐어도) 시크릿 후보로 surface. 사용자 자연어에 PW 라고 명시 안 해도,
    클릭한 element 가 password field 이면 그 다음 입력값은 시크릿일 가능성 매우 높음.

    Args:
        text: 사용자 메시지.
        elements: ohdo element picker 로 잡은 dict 리스트 (control_type, name,
            automation_id, dom_context 등 포함).

    Returns:
        list[SecretMatch] — text-based + element-driven 합본, confidence 내림차순.
    """
    # 기본 detect (text-only)
    matches = detect(text, entropy_threshold=entropy_threshold)

    has_pw_field = False
    pw_reasons: list[str] = []
    for e in elements or []:
        is_pw, reason = is_password_field_element(e)
        if is_pw:
            has_pw_field = True
            pw_reasons.append(reason)

    if not has_pw_field or not text:
        return matches

    # password field 감지됨 — text 안 따옴표 안 값을 강한 시크릿 후보로 surface.
    # 기존 detect() 가 quoted_literal 로 잡았으면 confidence boost.
    # 아예 못 잡았으면 (UI 라벨 skip 된 케이스 등 제외) 새로 추가.
    existing_quoted_spans = {m.span: m for m in matches if m.kind == "quoted_literal"}

    for m in _QUOTED_LITERAL.finditer(text):
        val_span = m.span("val")
        val = m.group("val")

        # skip list 는 element-driven 에서도 존중 — 'OK' / '확인' 같은 라벨이 PW field
        # 옆에 와도 그건 PW 아님 (사용자가 그냥 라벨을 따옴표로 감싼 거)
        if val.lower() in _SKIP_QUOTED_LITERALS:
            continue
        if len(val) < 4:
            continue
        # placeholder 자체 제외
        if val.startswith("{{") and val.endswith("}}"):
            continue
        # email / pure word 도 element 가 PW field 일 땐 OK (사용자가 ID 를 PW
        # 칸에 입력하는 시나리오는 드물고, surface 해도 사용자가 'send anyway' 가능).
        # 단 _SKIP_QUOTED_LITERALS 와 placeholder 만 제외.

        if val_span in existing_quoted_spans:
            # 기존 매치 — confidence boost (element 결정적 신호로 cap)
            old = existing_quoted_spans[val_span]
            new_conf = min(max(old.confidence + 0.15, 0.85), 0.95)
            # 새 match 로 교체 (in-place 수정 불가 — frozen dataclass)
            matches = [x for x in matches if x.span != val_span]
            matches.append(
                SecretMatch(
                    span=val_span,
                    kind="password_field_element",
                    value=val,
                    confidence=new_conf,
                    suggested_label=old.suggested_label,
                )
            )
        else:
            # 신규 — element 가 PW field 라는 결정적 신호로 surface
            matches.append(
                SecretMatch(
                    span=val_span,
                    kind="password_field_element",
                    value=val,
                    confidence=0.9,
                    suggested_label="password",
                )
            )

    matches.sort(key=lambda x: (-x.confidence, x.span[0]))
    return matches
