# SPDX-License-Identifier: AGPL-3.0-or-later
"""작업 녹화 (Action Recording) raw events → Step 변환.

[ADR 0004 + architecture/25-recording-phase-r1-r2.md §"PR-13"] RawEvent
리스트를 의미 단위로 묶어 ohdo Step 리스트로 압축한다.

핵심:
1. 노이즈 필터 (drop_self_window_clicks, drop_empty_space_clicks)
2. 자동 경계 4 신호 (사용자 추가 요청 §7):
   (a) 창 포커스 전환 (R2 — PR-12 에서 window_focus event 미캡처)
   (b) F8 수동 marker
   (c) 동일 element 연속 키입력 group 종료 — click 만나면 group 종료
   (d) idle_boundary_ms 휴지 — 이전 event 후 N초 (기본 3초) 휴지면 새 step
3. element_meta → Python 코드 (pywinauto / Selenium / pyautogui 좌표)
4. user_request 자동 생성 (control_type + name)
5. ADR 0003 통합: PW field key 시퀀스 → get_secret('label')

PR-13 의 코드 생성은 minimal viable — 사용자가 PR-15 review dialog 에서
직접 편집. 정교한 코드는 PR-15 에서 AI 후처리 (R3) 또는 win_inspector
helper 와 통합 검토.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from core.pywinauto_codegen import build_pywinauto_click_code
from core.recorder_models import RawEvent, RecordingSession, TransformOptions
from core.session_manager import Step

logger = logging.getLogger(__name__)


_VK_CHAR_MAP: dict[int, str] = {
    # 영문 — lowercase (shift 상태 추적 안 함, PR-13 minimal)
    0x41: "a", 0x42: "b", 0x43: "c", 0x44: "d", 0x45: "e",
    0x46: "f", 0x47: "g", 0x48: "h", 0x49: "i", 0x4A: "j",
    0x4B: "k", 0x4C: "l", 0x4D: "m", 0x4E: "n", 0x4F: "o",
    0x50: "p", 0x51: "q", 0x52: "r", 0x53: "s", 0x54: "t",
    0x55: "u", 0x56: "v", 0x57: "w", 0x58: "x", 0x59: "y", 0x5A: "z",
    # 숫자
    0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4",
    0x35: "5", 0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
    # 특수 (텍스트로 합칠 수 있는 것만)
    0x20: " ",  # SPACE
}  # fmt: skip

_VK_SPECIAL_KEYS: dict[int, str] = {
    0x0D: "enter",
    0x09: "tab",
    0x08: "backspace",
    0x1B: "esc",
    0x71: "f2", 0x72: "f3", 0x73: "f4", 0x74: "f5",
    0x76: "f7", 0x77: "f8", 0x78: "f9",
    0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down",
    0x2E: "delete", 0x2D: "insert", 0x24: "home", 0x23: "end",
    0x21: "pageup", 0x22: "pagedown",
}  # fmt: skip

# PR-19b (2026-05-24): 빠른 double-click 감지 threshold. Windows GetDoubleClickTime
# default (500ms) 와 동일. 같은 element + 같은 button + ts delta < 이 값 → 두 click
# 을 단일 RawEvent (click_count=2) 로 merge → _emit_click 이 pyautogui.doubleClick
# 변환. 천천히 두 번 click (이 값 초과) 은 별개 click 유지.
_DOUBLE_CLICK_THRESHOLD_MS = 500


# PR-19f (2026-05-24): modifier 자체 키 VK codes. _emit_key_group 가 이 키들을
# 단독 emit 안 함 — 다음 char/special 키의 RawEvent.modifiers 정보로 활용됨.
# 양쪽 modifier (LCtrl/RCtrl 등) + 일반 modifier 모두 포함.
_MODIFIER_VK_CODES: frozenset[int] = frozenset(
    {
        0x10,
        0x11,
        0x12,  # VK_SHIFT, VK_CONTROL, VK_MENU(Alt)
        0x5B,
        0x5C,  # VK_LWIN, VK_RWIN
        0xA0,
        0xA1,
        0xA2,
        0xA3,  # VK_LSHIFT, VK_RSHIFT, VK_LCONTROL, VK_RCONTROL
        0xA4,
        0xA5,  # VK_LMENU, VK_RMENU
    }
)


def transform(
    session: RecordingSession,
    opts: Optional[TransformOptions] = None,
    self_window_titles: Optional[list[str]] = None,
) -> list[Step]:
    """raw events → Step 리스트.

    Args:
        session: 녹화 종료된 RecordingSession (events 시간순).
        opts: 변환 옵션. None 이면 TransformOptions 기본값.
        self_window_titles: ohdo 자체 창 title 리스트 (drop_self_window_clicks).
            예: ["ohdo", "ohdo - "].
    """
    opts = opts or TransformOptions()
    self_titles = self_window_titles or []

    filtered = _filter_noise(session.events, opts, self_titles)
    batches = _split_into_batches(filtered, opts)

    steps: list[Step] = []
    for batch in batches:
        step = _batch_to_step(batch, opts)
        if step is not None:
            steps.append(step)

    for i, step in enumerate(steps, start=1):
        step.step_id = i

    return steps


def _is_uwp_popup_dismiss_overlay(meta: Optional[dict]) -> bool:
    """[PR-19g 2026-05-24] UWP popup overlay 의 invisible click receptor 감지.

    Win11 메모장 등 UWP/WinUI 앱은 popup (메뉴/dialog/toast) 이 떠 있을 때
    popup 영역 밖에 화면 전체를 덮는 invisible click receptor 를 깔아둠.
    사용자가 popup 외부 클릭 시 popup 을 닫는 ("light dismiss") 용도. EFP
    (ElementFromPoint) 가 이 invisible element 를 잡으면 element_meta 는:

        automation_id = "Light Dismiss"
        class_name = "PopupRoot"
        name = "닫기" (또는 빈 문자열)
        control_type = "Button"

    사용자가 의도하지 않은 무관한 click 이므로 transform 단계에서 drop.
    재생성 시 fallback chain 의 ``title="닫기"`` 매칭이 메모장의 진짜 X 버튼을
    찾아 클릭 → 메모장 종료 → 후속 step 모두 connect 실패 회귀 (사용자 실측
    v2-새세션-005917 Step 2). 시그니처 정확 매칭만 — 일반 "닫기" 라벨 버튼
    (다른 class_name) 은 그대로 통과.
    """
    if not meta:
        return False
    auto_id = (meta.get("automation_id") or "").strip().lower()
    cls = (meta.get("class_name") or "").strip().lower()
    return auto_id == "light dismiss" or cls == "popuproot"


def _filter_noise(
    events: list[RawEvent], opts: TransformOptions, self_titles: list[str]
) -> list[RawEvent]:
    out: list[RawEvent] = []
    dropped_overlay = 0
    for ev in events:
        if opts.drop_self_window_clicks and ev.kind == "click":
            wt = (ev.element_meta or {}).get("window_title") or ev.window_title or ""
            if any(t and t in wt for t in self_titles):
                continue
        if opts.drop_empty_space_clicks and ev.kind == "click" and ev.element_meta is None:
            continue
        # PR-19g: UWP popup overlay invisible click receptor drop
        if ev.kind == "click" and _is_uwp_popup_dismiss_overlay(ev.element_meta):
            dropped_overlay += 1
            continue
        out.append(ev)
    if dropped_overlay:
        logger.info(
            "recorder_transform: UWP popup Light Dismiss / PopupRoot click %d 개 drop "
            "(재생성 시 메모장 등 종료 회귀 차단)",
            dropped_overlay,
        )
    return out


def _split_into_batches(events: list[RawEvent], opts: TransformOptions) -> list[list[RawEvent]]:
    """자동 경계 4 신호로 events 를 batch (=Step) 단위로 분할.

    경계 신호:
    - marker (F8) → 그 자체 drop + 그 다음부터 새 batch
    - window_focus → 새 batch (PR-13 단계 처리; R2 캡처 활성 후 동작)
    - idle_boundary_ms 휴지 → 새 batch
    - 이전 event 가 key 이고 현재가 click → 새 batch (key group 종료)
    - 이전 event 가 click 이고 현재가 click 이면 같은 element 가 아니면 새 batch
      (같은 element 면 double click → 같은 batch)
    """
    batches: list[list[RawEvent]] = []
    current: list[RawEvent] = []

    for ev in events:
        if ev.kind == "marker":
            if opts.enable_f8_marker and current:
                batches.append(current)
                current = []
            continue

        if ev.kind == "window_focus":
            if opts.auto_window_focus_boundary and current:
                batches.append(current)
                current = []
            continue

        if not current:
            current.append(ev)
            continue

        prev = current[-1]
        new_batch = False

        if opts.idle_boundary_ms > 0:
            delta_ms = (ev.ts - prev.ts).total_seconds() * 1000
            if delta_ms > opts.idle_boundary_ms:
                new_batch = True

        if not new_batch and prev.kind == "key" and ev.kind == "click":
            new_batch = True

        if not new_batch and prev.kind == "click" and ev.kind == "click":
            # 같은 element (또는 둘 다 element_meta=None 이고 좌표 ± 5px) 면 같은
            # batch — PR-19b 의 _merge_consecutive_clicks 가 batch 안 빠른 double-click
            # merge 처리. 다른 element / 다른 좌표면 새 batch.
            same_target = _same_click_target(prev, ev)
            if not same_target:
                new_batch = True

        if new_batch:
            batches.append(current)
            current = [ev]
        else:
            current.append(ev)

    if current:
        batches.append(current)

    return batches


def _same_element(a: Optional[dict], b: Optional[dict]) -> bool:
    if a is None or b is None:
        return False
    for key in ("automation_id", "name", "control_type"):
        va = a.get(key)
        vb = b.get(key)
        if va and vb and va == vb:
            continue
        if va != vb:
            return False
    return True


def _same_click_target(a: RawEvent, b: RawEvent) -> bool:
    """[PR-19b 2026-05-24] 두 click event 가 같은 target 인가 — element_meta 우선,
    둘 다 None 이면 좌표 (± 5px) 비교. ``_split_into_batches`` 의 click→click
    경계 판단 + ``_merge_consecutive_clicks`` 의 double-click merge 판단 공통.
    """
    if a.element_meta is not None and b.element_meta is not None:
        return _same_element(a.element_meta, b.element_meta)
    if a.element_meta is None and b.element_meta is None:
        return (
            a.x is not None
            and b.x is not None
            and abs(a.x - b.x) <= 5
            and a.y is not None
            and b.y is not None
            and abs(a.y - b.y) <= 5
        )
    return False


def _merge_consecutive_clicks(batch: list[RawEvent]) -> list[RawEvent]:
    """[PR-19b 2026-05-24] 빠른 double-click 감지 — 같은 element + 같은 button +
    ts delta < ``_DOUBLE_CLICK_THRESHOLD_MS`` 면 두 click 을 단일 RawEvent
    (``click_count`` 누적) 로 merge.

    천천히 두 번 click (threshold 초과) 은 별개 click 유지 — 사용자 의도가
    double-click 아닌 두 개의 별개 single-click 일 가능성. handoff §25 F-6 의
    "별개 batch 분리" 시나리오는 이 함수 영향 X (이미 다른 batch). 이 함수는
    같은 batch 안 인접 click 만 처리.

    pydantic ``RawEvent`` 는 immutable — ``model_copy(update=...)`` 로 새 인스턴스
    반환.
    """
    out: list[RawEvent] = []
    for ev in batch:
        if ev.kind == "click" and out:
            prev = out[-1]
            if prev.kind == "click" and prev.button == ev.button and _same_click_target(prev, ev):
                delta_ms = (ev.ts - prev.ts).total_seconds() * 1000
                if delta_ms < _DOUBLE_CLICK_THRESHOLD_MS:
                    merged = prev.model_copy(
                        update={"click_count": (prev.click_count or 1) + 1, "ts": ev.ts}
                    )
                    out[-1] = merged
                    continue
        out.append(ev)
    return out


def _batch_to_step(batch: list[RawEvent], opts: TransformOptions) -> Optional[Step]:
    if not batch:
        return None

    # PR-19b: batch 안 빠른 double-click merge (click_count 누적).
    batch = _merge_consecutive_clicks(batch)

    code_lines: list[str] = []
    desc_parts: list[str] = []

    click_event: Optional[RawEvent] = None
    first_click_meta: Optional[dict] = None
    key_buffer: list[RawEvent] = []

    for ev in batch:
        if ev.kind == "click":
            if key_buffer:
                _emit_key_group(key_buffer, click_event, code_lines, desc_parts, opts)
                key_buffer = []
            _emit_click(ev, code_lines, desc_parts)
            click_event = ev
            # PR-19d: batch 의 첫 click 의 element_meta 를 Step.element_meta 에 보존
            # 보존. AI 재생성 시 element_context 변환에 사용. 같은 batch 내 후속 click
            # 은 동일 element (또는 같은 흐름) 이므로 첫 click 으로 대표.
            if first_click_meta is None and ev.element_meta:
                first_click_meta = dict(ev.element_meta)
        elif ev.kind == "key":
            key_buffer.append(ev)
        elif ev.kind == "scroll":
            _emit_scroll(ev, code_lines, desc_parts)

    if key_buffer:
        _emit_key_group(key_buffer, click_event, code_lines, desc_parts, opts)

    if not code_lines:
        return None

    user_request = " 후 ".join(desc_parts) if opts.auto_user_request else ""
    generated_code = "\n".join(code_lines)

    step = Step(
        step_id=0,
        status="pending",
        created_at=datetime.now().isoformat(),
        user_request=user_request,
        generated_code=generated_code,
        step_code=generated_code,
        element_meta=first_click_meta,
    )
    step.conversation = [
        {
            "role": "system",
            "content": "[recording] 작업 녹화로 자동 생성된 step",
            "timestamp": datetime.now().isoformat(),
        },
    ]
    if user_request:
        step.conversation.append(
            {
                "role": "user",
                "content": user_request,
                "timestamp": datetime.now().isoformat(),
            }
        )
    return step


def _emit_click(ev: RawEvent, code_lines: list[str], desc_parts: list[str]) -> None:
    meta = ev.element_meta
    btn = ev.button or "left"
    # PR-19b: click_count >= 2 면 double-click. right 는 double 미지원 (helper 가 ignore).
    is_double = (ev.click_count or 1) >= 2 and btn != "right"
    click_desc = "더블 클릭" if is_double else "클릭"

    if meta is None:
        # R2 PR-18 — 좌표 fallback 시 모니터 DPI 코멘트 첨부 (재생 환경 진단용)
        dpi_comment = ""
        if ev.monitor_dpi is not None and ev.monitor_dpi != 96:
            scale_pct = round(ev.monitor_dpi / 96 * 100)
            dpi_comment = f"  # captured at DPI={ev.monitor_dpi} ({scale_pct}%)"
        click_fn = "doubleClick" if is_double else "click"
        code_lines.append(f"pyautogui.{click_fn}({ev.x}, {ev.y}, button='{btn}'){dpi_comment}")
        desc_parts.append(f"({ev.x}, {ev.y}) {btn} {click_desc}")
        return

    if _is_browser_element(meta):
        code_lines.append(_browser_click_code(meta, double=is_double))
        desc_parts.append(_browser_desc(meta, click_desc))
        return

    code_lines.append(_pywinauto_click_code(meta, btn, double=is_double))
    desc_parts.append(_desktop_desc(meta, f"{btn} {click_desc}"))


def _emit_key_group(
    key_events: list[RawEvent],
    last_click: Optional[RawEvent],
    code_lines: list[str],
    desc_parts: list[str],
    opts: TransformOptions,
) -> None:
    if not key_events:
        return

    is_password = False
    label: Optional[str] = None
    if last_click is not None and last_click.element_meta:
        is_password = bool(last_click.element_meta.get("is_password_field")) or (
            (last_click.element_meta.get("control_type") or "").lower() == "edit"
            and "password" in (last_click.element_meta.get("automation_id") or "").lower()
        )
        label = last_click.element_meta.get("_ohdo_label")

    text_chars: list[str] = []

    def _flush_text() -> None:
        nonlocal text_chars
        if text_chars:
            _emit_text(text_chars, is_password, label, opts, code_lines, desc_parts)
            text_chars = []

    for ev in key_events:
        vk = ev.vk_code or 0

        # PR-19f: modifier 자체 키 (Ctrl/Shift/Alt/Win) 는 단독 emit 안 함.
        # 다음 char/special 키의 RawEvent.modifiers 로 활용됨.
        if vk in _MODIFIER_VK_CODES:
            continue

        modifiers = [m for m in (ev.modifiers or []) if m]

        # PR-19f: modifier + char/special → pyautogui.hotkey(...) 변환
        if modifiers:
            _flush_text()
            char = _VK_CHAR_MAP.get(vk)
            special = _VK_SPECIAL_KEYS.get(vk)
            key_name = char or special
            if key_name is None:
                # 인식 안 되는 vk + modifier — skip (예: 특수 키)
                continue
            # hotkey 인자: modifier 들 순서대로 + 최종 키
            hotkey_parts = modifiers + [key_name]
            args_repr = ", ".join(f"'{p}'" for p in hotkey_parts)
            code_lines.append(f"pyautogui.hotkey({args_repr})")
            desc_parts.append(f"단축키 {'+'.join(hotkey_parts)}")
            continue

        # modifier 없음 — 기존 text/special 로직
        char = _VK_CHAR_MAP.get(vk)
        if char is not None:
            text_chars.append(char)
            continue

        special = _VK_SPECIAL_KEYS.get(vk)
        if special is not None:
            _flush_text()
            code_lines.append(f"pyautogui.press('{special}')")
            desc_parts.append(f"키 '{special}' 입력")

    _flush_text()


def _emit_text(
    chars: list[str],
    is_password: bool,
    label: Optional[str],
    opts: TransformOptions,
    code_lines: list[str],
    desc_parts: list[str],
) -> None:
    text = "".join(chars)
    if is_password and opts.integrate_secrets:
        used_label = label or "password"
        code_lines.append(f"pyautogui.write(get_secret('{used_label}'))")
        desc_parts.append(f"비밀번호 입력 (get_secret('{used_label}'))")
    else:
        code_lines.append(f"pyautogui.write({text!r})")
        desc_parts.append(f"텍스트 입력 {text!r}")


def _emit_scroll(ev: RawEvent, code_lines: list[str], desc_parts: list[str]) -> None:
    code_lines.append(f"pyautogui.scroll({ev.wheel_delta}, x={ev.x}, y={ev.y})")
    desc_parts.append(f"({ev.x}, {ev.y}) 스크롤 {ev.wheel_delta:+d}")


def _is_browser_element(meta: dict) -> bool:
    return any(k in meta for k in ("css_selector", "xpath", "browser_role", "tag_name"))


def _browser_click_code(meta: dict, double: bool = False) -> str:
    css = meta.get("css_selector") or ""
    xpath = meta.get("xpath") or ""
    # PR-19b: Selenium 은 단일 element 에 대해 ActionChains.double_click 사용.
    if double:
        if css:
            return (
                f"_el = driver.find_element(By.CSS_SELECTOR, {css!r}); "
                "ActionChains(driver).double_click(_el).perform()"
            )
        if xpath:
            return (
                f"_el = driver.find_element(By.XPATH, {xpath!r}); "
                "ActionChains(driver).double_click(_el).perform()"
            )
        return 'driver.execute_script("/* selector 없음 (double-click) */")'
    if css:
        return f"driver.find_element(By.CSS_SELECTOR, {css!r}).click()"
    if xpath:
        return f"driver.find_element(By.XPATH, {xpath!r}).click()"
    return 'driver.execute_script("/* selector 없음 */")'


def _pywinauto_click_code(meta: dict, btn: str, double: bool = False) -> str:
    """pywinauto click 코드 생성.

    [PR-19a — 2026-05-23] ``core.pywinauto_codegen.build_pywinauto_click_code``
    helper 로 위임. 이전엔 minimal 3줄 (``title_re=".*<full_title>.*"`` hardcode)
    이었는데 메모장처럼 문서 내용이 title 에 들어가는 앱 재실행 시 매칭 실패
    회귀 — helper 가 ``program_name`` (`` - `` 마지막 segment) ``.*<프로그램명>``
    로 안전 매칭 + DPI Awareness + selector fallback chain + 창 활성화 +
    pyautogui PRIMARY click 까지 포함한 robust 코드 생성.

    `Application(...)` (unqualified) — essential imports
    ``from pywinauto import Application`` 매치 (test_182 회귀 가드).

    [PR-19b — 2026-05-24] ``double=True`` 면 ``pyautogui.doubleClick`` +
    ``click_input(double=True)`` fallback emit (transform 의
    ``_merge_consecutive_clicks`` 가 빠른 double-click 감지).
    """
    return build_pywinauto_click_code(meta, button=btn, double=double)


def _browser_desc(meta: dict, verb: str) -> str:
    tag = meta.get("tag_name") or "?"
    name = meta.get("name") or meta.get("id") or ""
    if name:
        return f"<{tag}> '{name}' {verb}"
    return f"<{tag}> {verb}"


def _desktop_desc(meta: dict, verb: str) -> str:
    ctrl_type = meta.get("control_type") or "?"
    name = meta.get("name") or meta.get("automation_id") or ""
    if name:
        return f"{ctrl_type} '{name}' {verb}"
    return f"{ctrl_type} {verb}"
