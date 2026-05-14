# SPDX-License-Identifier: AGPL-3.0-or-later
"""user_request / generated_code 의 placeholder ↔ 평문 변환.

[ADR 0003](../docs/saas/decisions/0003-secrets-handling.md) Phase 2-a.

placeholder 형식: ``{{secret:<label>}}`` (label 은 ``[a-z0-9_]{1,32}``).

쓰는 곳:
  - **사용자 입력 path (UI, PR-4)** — ``secrets_detector.detect`` 결과로 발견한
    범위를 placeholder 로 치환 (``to_placeholder_text``). vault 에는 사전 등록
    필요.
  - **export path (Phase 3)** — placeholder 가 박힌 generated_code 에서 사용된
    label 목록 추출 (``extract_labels``) → ``.env.example`` 생성.
  - **runtime path (PR-3)** — ``ExecutionKernel.start`` 가 ``extract_labels`` 로
    실행 직전 vault 에서 값 가져와 환경변수 주입. resolve() 는 runtime 외 디버깅
    / export 용 한정.
"""

from __future__ import annotations

import re

from core.secrets import SecretLabel, SecretsVault

__all__ = [
    "PLACEHOLDER_RE",
    "format_placeholder",
    "has_placeholders",
    "to_placeholder_text",
    "extract_labels",
    "resolve",
]


PLACEHOLDER_RE: re.Pattern[str] = re.compile(r"\{\{secret:([a-z0-9_]{1,32})\}\}")
"""``{{secret:label}}`` 패턴. label 은 ``SecretLabel`` 검증과 일관."""


def format_placeholder(label: str) -> str:
    """label → ``{{secret:label}}`` 문자열."""
    return "{{secret:" + label + "}}"


def has_placeholders(text: str) -> bool:
    """text 안에 placeholder 가 하나라도 있으면 True."""
    return bool(PLACEHOLDER_RE.search(text or ""))


def to_placeholder_text(
    text: str,
    spans_to_labels: list[tuple[tuple[int, int], str]],
) -> str:
    """text 의 지정된 span 들을 ``{{secret:label}}`` 로 치환.

    Args:
        text: 원문.
        spans_to_labels: ``[((start, end), label), ...]``. span 은 원문 인덱스
            기준 (end exclusive). label 은 ``[a-z0-9_]{1,32}``.

    Returns:
        placeholder 치환된 텍스트. span 들이 겹쳐있으면 ``ValueError`` (호출자가
        ``secrets_detector`` 의 overlap-drop 으로 사전 정리).

    구현:
        span 을 시작 인덱스 내림차순으로 정렬해서 뒤에서부터 치환 — 앞 치환이
        뒤 인덱스를 흐트러뜨리지 않음.
    """
    if not text or not spans_to_labels:
        return text

    sorted_spans = sorted(spans_to_labels, key=lambda x: -x[0][0])

    # overlap 사전 검증 (구현 안전 — 호출자 실수 catch)
    for i, ((s1, e1), _) in enumerate(sorted_spans):
        for (s2, e2), _ in sorted_spans[i + 1 :]:
            if not (e1 <= s2 or e2 <= s1):
                raise ValueError(
                    f"span 겹침 감지: ({s1},{e1}) vs ({s2},{e2}). "
                    "secrets_detector.detect 의 overlap-drop 으로 사전 정리 필요."
                )

    out = text
    for (start, end), label in sorted_spans:
        if not (0 <= start < end <= len(out)):
            raise ValueError(f"잘못된 span ({start},{end}) — text 길이 {len(out)}")
        # label 패턴 검증 (호출자 실수 catch — SecretLabel 생성 안 했을 수도)
        if not re.match(r"^[a-z0-9_]{1,32}$", label):
            raise ValueError(f"잘못된 label '{label}' — 허용 패턴 [a-z0-9_]{{1,32}}")
        out = out[:start] + format_placeholder(label) + out[end:]
    return out


def extract_labels(text: str, *, namespace: str = "secret") -> list[SecretLabel]:
    """text 에 등장한 placeholder label 목록 (중복 제거, 등장 순서 보존).

    Args:
        text: 검사 대상 (코드 / 사용자 메시지).
        namespace: 반환할 ``SecretLabel`` 의 namespace. runtime 주입은 'secret',
            AI api_key 마이그레이션 path 는 'apikey' 등.

    Returns:
        등장 순서대로 정렬된 ``SecretLabel`` 리스트. 중복 label 은 1회만.
    """
    if not text:
        return []
    seen: set[str] = set()
    out: list[SecretLabel] = []
    for m in PLACEHOLDER_RE.finditer(text):
        lab = m.group(1)
        if lab in seen:
            continue
        seen.add(lab)
        out.append(SecretLabel(label=lab, namespace=namespace))
    return out


def resolve(
    text: str,
    vault: SecretsVault,
    *,
    namespace: str = "secret",
) -> tuple[str, list[str]]:
    """placeholder → 평문. **export / 디버깅 한정**.

    🚨 runtime 코드 실행에선 사용 X — ``ExecutionKernel.start`` 가 환경변수로
    값을 주입하고 코드는 ``get_secret('label')`` 호출. 평문이 코드 문자열로
    들어가면 ``code_validator.hardcoded_secret`` warning 회귀 가능.

    Args:
        text: placeholder 포함 텍스트.
        vault: 값 조회용.
        namespace: vault lookup 시 사용할 namespace.

    Returns:
        ``(resolved_text, unresolved_labels)``. vault 미존재 label 은 원본
        placeholder 유지 + unresolved 리스트에 기록.
    """
    if not text:
        return text, []

    unresolved: list[str] = []

    def _sub(m: re.Match[str]) -> str:
        label = m.group(1)
        val = vault.get(SecretLabel(label=label, namespace=namespace))
        if val is None:
            unresolved.append(label)
            return m.group(0)
        return val

    return PLACEHOLDER_RE.sub(_sub, text), unresolved
