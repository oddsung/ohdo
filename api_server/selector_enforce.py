# SPDX-License-Identifier: AGPL-3.0-or-later
"""picker 로 고른 요소의 셀렉터를 생성 코드에 결정적으로 강제 (handoff §72).

문제(사용자 실측): 연속 클릭 step 이 쌓이면 프롬프트가 직전 step 의 클릭 대상(예: Document)
으로 도배되어, AI 가 새로 픽한 요소(예: auto_id=CloseButton)를 무시하고 엉뚱한 셀렉터를 생성한다
(신호 대 잡음 문제 — 엔진 무능이 아님: 첫 클릭 step 은 정확히 auto_id 를 씀). picker 는 정확한
요소를 이미 알므로, 생성 **후** api_server 가 그 step 의 element 셀렉터를 픽한 요소로 교정한다.

순수 텍스트 후처리(core 무관). 마커/주석은 보존하고, 대상 step 의 ``element = win.child_window(...)``
호출의 인자만 픽 요소의 auto_id(또는 title) + control_type 으로 치환한다. 실패/모호하면 원본 유지.
"""

from __future__ import annotations

import ast
import re

# get_element_info_text(_get_desktop_element_info_text) 가 만드는 element_context 포맷에서
# 픽 요소의 식별자를 파싱. (예: "- **Automation ID**: CloseButton", '- **이름**: "탭 닫기"')
_AUTO_ID_RE = re.compile(r"Automation ID\*\*:\s*([^\s⚠]+)")
_NAME_RE = re.compile(r"\*\*이름\*\*:\s*\"([^\"]+)\"")
_TYPE_RE = re.compile(r"\*\*타입\*\*:\s*([^\s]+)")

# step 본문 내 element 를 찾는 child_window/descendants 호출 (중첩 괄호 없음 가정 — kwargs 만).
_ELEMENT_CALL_RE = re.compile(
    r"(element\s*=\s*win\.(?:child_window|descendants)\()([^()]*?)(\))", re.S
)


def parse_picked_selector(element_context: str) -> "dict | None":
    """element_context 텍스트 → {auto_id?|title?, control_type} 셀렉터. 식별 불가 시 None.

    - auto_id 가 숫자만이면 동적 ID(윈도우 핸들 — 매번 변경)라 사용 금지 → title 로 폴백.
    - auto_id/title 둘 다 없으면 None(강제 불가, AI 출력 유지).
    """
    if not element_context:
        return None
    ctrl_m = _TYPE_RE.search(element_context)
    control_type = ctrl_m.group(1).strip() if ctrl_m else None

    auto_id_m = _AUTO_ID_RE.search(element_context)
    auto_id = auto_id_m.group(1).strip() if auto_id_m else ""
    if auto_id and not auto_id.isdigit():
        return {"auto_id": auto_id, "control_type": control_type}

    name_m = _NAME_RE.search(element_context)
    name = name_m.group(1).strip() if name_m else ""
    if name:
        return {"title": name, "control_type": control_type}
    return None


def _selector_kwargs(sel: dict) -> str:
    """치환할 child_window kwargs 문자열(들여쓰기 포함)."""
    lines = []
    if sel.get("auto_id"):
        lines.append(f'auto_id="{sel["auto_id"]}"')
    elif sel.get("title"):
        lines.append(f'title="{sel["title"]}"')
    if sel.get("control_type"):
        lines.append(f'control_type="{sel["control_type"]}"')
    lines.append("found_index=0")
    body = ",\n        ".join(lines)
    return f"\n        {body}\n    "


def _step_region(code: str, step_id: int) -> "tuple[int, int] | None":
    """generated_code 에서 step_id 의 ``# === Step N: ... (시작) === ~ (끝) ===`` 영역 [start,end)."""
    start = re.search(rf"#\s*===\s*Step\s+{step_id}\s*:.*?\(\s*시작\s*\)\s*===", code)
    if not start:
        return None
    end = re.search(rf"#\s*===\s*Step\s+{step_id}\s*:.*?\(\s*끝\s*\)\s*===", code[start.end() :])
    end_idx = start.end() + end.end() if end else len(code)
    return (start.start(), end_idx)


def enforce_picked_selector(
    generated_code: str, step_id: int, element_context: str
) -> "tuple[str, bool]":
    """대상 step 의 element 셀렉터를 픽 요소로 교정. 반환 (코드, 변경여부).

    변경 조건: 픽 셀렉터 파싱 성공 + 해당 step 영역에 element child_window 호출 존재 +
    그 호출이 아직 픽 식별자(auto_id/title)를 안 씀 + 치환 결과가 compile 됨.
    하나라도 불충족이면 원본 그대로 반환(best-effort, AI 출력 보존).
    """
    sel = parse_picked_selector(element_context or "")
    if not sel:
        return generated_code, False
    region = _step_region(generated_code, step_id)
    if not region:
        return generated_code, False
    s, e = region
    body = generated_code[s:e]

    ident = sel.get("auto_id") or sel.get("title")
    if ident and ident in body:
        return generated_code, False  # 이미 그 요소를 타겟함 — 손대지 않음

    if not _ELEMENT_CALL_RE.search(body):
        return generated_code, False  # element 호출 패턴 없음(예: _resolve_element 사용) — 유지

    kwargs = _selector_kwargs(sel)
    new_body = _ELEMENT_CALL_RE.sub(lambda m: m.group(1) + kwargs + m.group(3), body)
    new_code = generated_code[:s] + new_body + generated_code[e:]

    try:
        ast.parse(new_code)
    except SyntaxError:
        return generated_code, False  # 치환이 깨지면 원본 유지
    return new_code, True
