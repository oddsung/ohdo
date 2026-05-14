# SPDX-License-Identifier: AGPL-3.0-or-later
"""Element 라벨 자동 추론 + placeholder 매핑.

[ADR 0003](../docs/saas/decisions/0003-secrets-handling.md) Phase 2-c PR-10.

목적:
    사용자가 picker 로 잡은 element 에 직관적인 라벨 (``ID`` / ``PW`` /
    ``search_box`` 등) 을 자동 부여해서, 채팅 메시지에서 ``{{el:ID}}`` placeholder
    로 참조 가능하게 함.

설계 원칙:
  - **자동 추론 + 사용자 편집 가능** (D2 결정 — (B) chip 편집 + (C) 자동 추론).
    추론 실패 / 마음에 안 들면 chip 클릭으로 inline edit.
  - **결정적**: 같은 element 입력 → 같은 라벨 반환. 라벨은 ``[a-z0-9_]{1,32}``
    (placeholder 패턴과 일관).
  - **HTML attribute 우선** → UIA fallback. CDP DOM context 가 있으면 더 정확.
"""

from __future__ import annotations

import re

__all__ = [
    "suggest_element_label",
    "normalize_label",
]


# 라벨 패턴 — SecretLabel 과 일관 ([a-z0-9_]{1,32}).
_LABEL_PATTERN = re.compile(r"^[a-z0-9_]{1,32}$")

# HTML attribute / UIA automation_id 의 영문 단어를 의미별로 매핑.
# key: pattern (lowercase 정규식), value: 표준 라벨.
_HTML_TYPE_LABELS: dict[str, str] = {
    "password": "pw",
    "email": "email",
    "tel": "phone",
    "search": "search",
    "url": "url",
}

# attribute 값의 keyword → label 매핑 (substring match).
# 짧은 단어부터 매칭되면 즉시 채택 — 더 구체적 단어가 있으면 그것 우선 위해 정렬 주의.
_KEYWORD_LABELS: tuple[tuple[re.Pattern[str], str], ...] = (
    # password / userps / userpswd → pw (먼저 검사 — "userPs" 가 username 패턴
    # 의 "user" 부분으로 false-match 되지 않게)
    (re.compile(r"(?:passwd|password|userps|user_ps|user_pswd|pwd|pswd)", re.IGNORECASE), "pw"),
    # username / userid / loginid → id ('user' 단독은 매치 안 함 — 'username' 또는 'userid')
    (re.compile(r"(?:user(?:name|id)|loginid|login_id|login-id)", re.IGNORECASE), "id"),
    # email / mail → email
    (re.compile(r"(?:email|mail)", re.IGNORECASE), "email"),
    # search → search
    (re.compile(r"search", re.IGNORECASE), "search"),
    # login button / submit → submit_btn
    (re.compile(r"(?:login|signin|sign_in)[_-]?(?:btn|button)", re.IGNORECASE), "login_btn"),
    (re.compile(r"submit(?:[_-]?(?:btn|button))?", re.IGNORECASE), "submit_btn"),
)


def normalize_label(text: str) -> str:
    """임의 문자열 → ``[a-z0-9_]{1,32}`` 라벨로 정규화.

    공백/특수문자 → ``_``. 연속 ``_`` 단축. 앞뒤 ``_`` 제거. lowercase. 32자 cap.
    """
    if not text:
        return ""
    out = re.sub(r"[^A-Za-z0-9_]", "_", text.lower())
    out = re.sub(r"_+", "_", out).strip("_")
    return out[:32]


def suggest_element_label(element_info: dict, *, used_labels: set[str] | None = None) -> str:
    """element_info 의 attribute 들을 분석해 의미 있는 라벨 추론.

    우선순위:
      1. HTML attribute ``type`` (Selenium DOM) — ``password`` → ``pw`` 등
      2. HTML / UIA attribute 의 키워드 매칭 — ``userId`` → ``id``, ``userPs`` → ``pw``
      3. ``name`` / ``automation_id`` 정규화 — ``loginButton`` → ``loginbutton`` (32자 cap)
      4. ``control_type`` fallback — ``edit_1``, ``button_1``
      5. 최종 fallback — ``elem_1`` (used_labels 와 충돌 X 보장)

    Args:
        element_info: ohdo element picker dict. 키:
            ``control_type``, ``name``, ``automation_id``, ``dom_context.attributes``
            등.
        used_labels: 이미 사용된 라벨 set (중복 방지). 충돌 시 ``_2`` ``_3`` ... suffix.

    Returns:
        라벨 문자열. 항상 ``[a-z0-9_]{1,32}`` 패턴 + used_labels 와 충돌 없음.
    """
    used = set(used_labels or [])
    candidates: list[str] = []

    # 1) HTML type
    dom_ctx = element_info.get("dom_context") or {}
    if isinstance(dom_ctx, dict) and dom_ctx.get("cdp_available"):
        attrs = dom_ctx.get("attributes") or {}
        if isinstance(attrs, dict):
            html_type = (attrs.get("type") or "").lower().strip()
            if html_type in _HTML_TYPE_LABELS:
                candidates.append(_HTML_TYPE_LABELS[html_type])

            # 2a) HTML name / id 키워드 매칭
            for attr_name in ("name", "id"):
                val = attrs.get(attr_name)
                if isinstance(val, str) and val:
                    for pat, label in _KEYWORD_LABELS:
                        if pat.search(val):
                            candidates.append(label)
                            break
                    else:
                        # 키워드 매칭 안 됨 — 값 정규화 (fallback 후보)
                        normalized = normalize_label(val)
                        if normalized:
                            candidates.append(normalized)

    # 2b) UIA automation_id / name 키워드 매칭
    for attr in ("automation_id", "name"):
        val = element_info.get(attr)
        if isinstance(val, str) and val:
            for pat, label in _KEYWORD_LABELS:
                if pat.search(val):
                    candidates.append(label)
                    break
            else:
                normalized = normalize_label(val)
                if normalized:
                    candidates.append(normalized)

    # 3) control_type fallback
    ctrl = (element_info.get("control_type") or "").lower().strip()
    if ctrl:
        candidates.append(normalize_label(ctrl))

    # 4) 최종 fallback
    candidates.append("elem")

    # 첫 valid 후보 (used 와 충돌 없는 것) 선택. 충돌 시 suffix.
    for cand in candidates:
        if not cand or not _LABEL_PATTERN.match(cand):
            continue
        if cand not in used:
            return cand
        # 충돌 시 _2, _3, ... 시도
        for suffix in range(2, 100):
            cand_with_suffix = f"{cand}_{suffix}"
            if len(cand_with_suffix) > 32:
                cand_with_suffix = cand_with_suffix[:32]
            if cand_with_suffix not in used:
                return cand_with_suffix

    # 모든 후보가 invalid (이론적 unreachable — 'elem' 은 항상 valid)
    return "elem"
