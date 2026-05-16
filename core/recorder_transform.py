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
}  # fmt: skip


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


def _filter_noise(
    events: list[RawEvent], opts: TransformOptions, self_titles: list[str]
) -> list[RawEvent]:
    out: list[RawEvent] = []
    for ev in events:
        if opts.drop_self_window_clicks and ev.kind == "click":
            wt = (ev.element_meta or {}).get("window_title") or ev.window_title or ""
            if any(t and t in wt for t in self_titles):
                continue
        if opts.drop_empty_space_clicks and ev.kind == "click" and ev.element_meta is None:
            continue
        out.append(ev)
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
            same_element = _same_element(prev.element_meta, ev.element_meta)
            if not same_element:
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


def _batch_to_step(batch: list[RawEvent], opts: TransformOptions) -> Optional[Step]:
    if not batch:
        return None

    code_lines: list[str] = []
    desc_parts: list[str] = []

    click_event: Optional[RawEvent] = None
    key_buffer: list[RawEvent] = []

    for ev in batch:
        if ev.kind == "click":
            if key_buffer:
                _emit_key_group(key_buffer, click_event, code_lines, desc_parts, opts)
                key_buffer = []
            _emit_click(ev, code_lines, desc_parts)
            click_event = ev
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

    if meta is None:
        code_lines.append(f"pyautogui.click({ev.x}, {ev.y}, button='{btn}')")
        desc_parts.append(f"({ev.x}, {ev.y}) {btn} 클릭")
        return

    if _is_browser_element(meta):
        code_lines.append(_browser_click_code(meta))
        desc_parts.append(_browser_desc(meta, "클릭"))
        return

    code_lines.append(_pywinauto_click_code(meta, btn))
    desc_parts.append(_desktop_desc(meta, f"{btn} 클릭"))


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
    for ev in key_events:
        vk = ev.vk_code or 0
        char = _VK_CHAR_MAP.get(vk)
        if char is not None:
            text_chars.append(char)
            continue

        special = _VK_SPECIAL_KEYS.get(vk)
        if special is not None:
            if text_chars:
                _emit_text(text_chars, is_password, label, opts, code_lines, desc_parts)
                text_chars = []
            code_lines.append(f"pyautogui.press('{special}')")
            desc_parts.append(f"키 '{special}' 입력")

    if text_chars:
        _emit_text(text_chars, is_password, label, opts, code_lines, desc_parts)


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


def _browser_click_code(meta: dict) -> str:
    css = meta.get("css_selector") or ""
    xpath = meta.get("xpath") or ""
    if css:
        return f"driver.find_element(By.CSS_SELECTOR, {css!r}).click()"
    if xpath:
        return f"driver.find_element(By.XPATH, {xpath!r}).click()"
    return 'driver.execute_script("/* selector 없음 */")'


def _pywinauto_click_code(meta: dict, btn: str) -> str:
    ctrl_type = meta.get("control_type") or "Unknown"
    name = meta.get("name") or ""
    auto_id = meta.get("automation_id") or ""
    window_title = meta.get("window_title") or ""

    selectors: list[str] = []
    if auto_id and not str(auto_id).isdigit():
        selectors.append(f"auto_id={auto_id!r}")
    if name:
        selectors.append(f"title={name!r}")
    selectors.append(f"control_type={ctrl_type!r}")
    selector_args = ", ".join(selectors)

    click_method = "right_click_input" if btn == "right" else "click_input"
    return (
        f'app = pywinauto.Application(backend="uia").connect(title_re={f".*{window_title}.*"!r})\n'
        f"win = app.top_window()\n"
        f"win.child_window({selector_args}).{click_method}()"
    )


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
