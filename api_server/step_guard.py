# SPDX-License-Identifier: AGPL-3.0-or-later
"""생성 step 의 결정적 실행성 가드 (handoff §78c).

문제(사용자 실측, DeepSeek): 프롬프트의 "## 선택된 UI 요소" 코드 템플릿을 "이미 실행된
코드"로 오독하고 새 스텝 블록에 **주석만** 생성(+이전 스텝 코드까지 응답에서 누락) →
step_code="" · 누적 generated_code 축소(세션 오염) · 실행 시 아무 동작 없음. 지시문
강화는 확률적 방어라, 생성 **후** 결정적으로 보정한다(§72 셀렉터 강제와 같은 철학 —
picker 가 정확한 요소를 알고 템플릿은 그 자체로 실행 가능한 클릭 코드다):

1. 새 스텝에 실행 가능한 문장이 없고(델타 빈/주석뿐) 픽 템플릿이 있으면 →
   step_code 를 템플릿 코드로 대체.
2. 이전 스텝들의 마커 블록이 누적 코드에서 사라졌으면(AI 가 이전 코드 미유지) →
   library + step_code 체인으로 generated_code 재구성(§73 rebuild 재사용).

순수 텍스트/세션 후처리 — core 0줄. 모든 보정은 best-effort(실패 시 원본 유지).
"""

from __future__ import annotations

import ast
import logging
import re

from api_server.selector_enforce import _step_region

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```python\s*\n(.*?)```", re.S)


def extract_template_code(element_context: "str | None") -> "str | None":
    """element_context 의 ```python 펜스 코드 템플릿 추출. 없거나 컴파일 불가면 None."""
    if not element_context:
        return None
    m = _FENCE_RE.search(element_context)
    if not m:
        return None
    code = m.group(1).strip()
    if not code:
        return None
    try:
        ast.parse(code)
    except SyntaxError:
        return None
    return code


def _has_executable_line(code: str) -> bool:
    """주석/빈 줄 외의 문장이 하나라도 있으면 True."""
    for line in (code or "").split("\n"):
        t = line.strip()
        if t and not t.startswith("#"):
            return True
    return False


def is_broken_step_code(step_code: str) -> bool:
    """step_code(델타)가 단독 실행 불가면 True — 실행문 전무 또는 컴파일 불가.

    실측 사례(§78f): AI 가 스텝 블록을 "요약"하며 try:/클릭 문장을 설명 주석으로 대체하고
    본문 print 는 들여쓰기 그대로 남김 → dangling indent(IndentationError). step_code 는
    jupyter 모드 단독 실행 단위라 컴파일 가능이 계약 — 깨졌으면 결정적 대체 대상.
    """
    if not _has_executable_line(step_code):
        return True
    try:
        ast.parse(step_code)
        return False
    except SyntaxError:
        return True


def block_is_comment_only(generated_code: str, step_id: int) -> bool:
    """해당 step 의 마커 영역이 존재하고 그 안에 실행 가능한 문장이 없으면 True."""
    region = _step_region(generated_code or "", step_id)
    if not region:
        return False
    s, e = region
    return not _has_executable_line(generated_code[s:e])


def missing_prior_step_ids(generated_code: str, prior_step_ids: "list[int]") -> "list[int]":
    """누적 코드에서 마커 블록이 사라진 이전 step id 목록 (AI 가 이전 코드 미유지 감지)."""
    return [sid for sid in prior_step_ids if _step_region(generated_code or "", sid) is None]


def apply_step_guards(service, session_id: str, step, element_context: "str | None") -> None:
    """생성 직후(§72 교정 뒤) 호출 — 위 가드 1/2 를 적용. best-effort.

    - 가드 1 발동 조건: 그 step 의 step_code 에 실행문이 없거나 마커 블록이 주석뿐
      + 픽 템플릿 존재. → step_code := 템플릿 코드.
    - 가드 2 발동 조건: 이전 step 의 마커가 누적 코드에 없음(또는 가드 1 발동).
      → §73 ``_rebuild_generated_code_chain`` 으로 generated_code 재구성.
    """
    try:
        from api_server.deps import to_dict
        from api_server.routes.steps import _rebuild_generated_code_chain

        sess = service.get_session(session_id)
        steps = [s if isinstance(s, dict) else to_dict(s) for s in sess.steps]
        step_id = step.step_id if not isinstance(step, dict) else step.get("step_id")
        idx = next((i for i, s in enumerate(steps) if s.get("step_id") == step_id), None)
        if idx is None:
            return
        cur = steps[idx]
        code = cur.get("generated_code") or ""
        prior_ids = [s.get("step_id") for s in steps[:idx] if s.get("step_id") is not None]

        need_rebuild = False

        # 가드 1 — 실행 불가 스텝(실행문 전무/주석뿐/컴파일 불가) → 픽 템플릿 코드로 대체.
        # §78f: "일부 문장만 주석으로 대체 + 들여쓰기 파편" 같은 부분 요약도 컴파일 검사로 잡는다.
        sc = cur.get("step_code") or ""
        if is_broken_step_code(sc) or block_is_comment_only(code, step_id):
            template = extract_template_code(element_context)
            if template:
                service.update_step(session_id, step_id, {"step_code": template})
                need_rebuild = True
                logger.info(
                    "§78c/f 가드1: step %s 실행 불가(주석뿐/비컴파일) → 픽 템플릿 대체", step_id
                )

        # 가드 2 — 이전 스텝 블록 누락(AI 가 이전 코드 미유지) → 체인 재구성.
        dropped = missing_prior_step_ids(code, prior_ids)
        if dropped:
            need_rebuild = True
            logger.info("§78c 가드2: 이전 step %s 마커 누락 → 체인 재구성", dropped)

        if need_rebuild:
            _rebuild_generated_code_chain(service, session_id)
    except Exception:
        logger.debug("§78c step guard 실패(무시 — 원본 유지)", exc_info=True)
