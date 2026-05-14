# SPDX-License-Identifier: AGPL-3.0-or-later
"""채팅 메시지의 ``{{el:label}}`` placeholder ↔ element reference 변환.

[ADR 0003](../docs/saas/decisions/0003-secrets-handling.md) Phase 2-c PR-10e.

D4 결정 (사용자 통찰력):
    placeholder 는 AI 에 도달하기 전 ``prompt_builder`` 가 자연어 reference 토큰
    (``📌 [label]``) 으로 자동 치환. AI 는 placeholder 문법을 전혀 안 봄 — 기존
    element_context 형식 (헤더에 ``[📌 label]`` suffix) 과 cross-reference 만 함.

장점 (vs system_context 가이드 추가):
  - AI 학습 부담 0 — 기존 element_context handling 그대로
  - ``code_validator`` 의 unresolved placeholder kind 불필요 — placeholder 가 AI 에
    안 가니까 코드에 박힐 일 없음

쓰는 곳:
  - ``ui_v2._on_send_message`` — 전송 직전 미매핑 검사 (차단)
  - ``prompt_builder._build_step_prompt_parts`` — user_request 치환 (현재는
    ui_v2 에서 사전 치환, prompt_builder 는 받은 그대로 사용)
"""

from __future__ import annotations

import re

__all__ = [
    "ELEMENT_PLACEHOLDER_RE",
    "extract_labels",
    "replace_with_references",
    "find_unresolved",
]


# placeholder 패턴 — `{{el:<label>}}`. label 은 SecretLabel 과 일관 `[a-z0-9_]{1,32}`.
ELEMENT_PLACEHOLDER_RE: re.Pattern[str] = re.compile(r"\{\{el:([a-z0-9_]{1,32})\}\}")


def extract_labels(text: str) -> list[str]:
    """text 에 등장한 ``{{el:label}}`` label 목록 (중복 제거, 등장 순서 보존)."""
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in ELEMENT_PLACEHOLDER_RE.finditer(text):
        lab = m.group(1)
        if lab in seen:
            continue
        seen.add(lab)
        out.append(lab)
    return out


def find_unresolved(text: str, elements: list[dict] | None) -> list[str]:
    """text 안 ``{{el:label}}`` 중 elements 에 매핑되는 라벨이 없는 것 반환.

    elements 의 각 dict 는 ``_ohdo_label`` 키로 라벨을 가짐 (PR-10c chip widget
    이 부여).

    Returns:
        매핑 안 된 라벨 리스트 (중복 제거, 등장 순서). 빈 리스트면 모두 OK.
    """
    used_labels = extract_labels(text)
    if not used_labels:
        return []
    elem_labels = {
        e.get("_ohdo_label")
        for e in (elements or [])
        if isinstance(e.get("_ohdo_label"), str) and e.get("_ohdo_label")
    }
    return [lab for lab in used_labels if lab not in elem_labels]


def replace_with_references(text: str) -> str:
    """``{{el:label}}`` → ``📌 [label]`` (AI 가 인식할 자연어 reference 토큰).

    element_context 의 header (``## 선택된 UI 요소 ... [📌 label]``) 와 시각적
    매칭되어 AI 가 cross-reference 가능. 호출자가 미매핑 검사 (``find_unresolved``)
    먼저 통과 후 호출 권장.
    """
    if not text:
        return text
    return ELEMENT_PLACEHOLDER_RE.sub(lambda m: f"📌 [{m.group(1)}]", text)
