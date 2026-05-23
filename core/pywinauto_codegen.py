# SPDX-License-Identifier: AGPL-3.0-or-later
"""pywinauto + pyautogui 데스크톱 element click 코드 생성 (pure helper).

[PR-19a — 2026-05-23] win_inspector (AI 프롬프트 컨텍스트) 와 recorder_transform
(녹화 step 코드) 의 공통 deterministic 코드 생성 로직. 이전엔 win_inspector
의 ``_get_desktop_element_info_text`` 가 markdown 안 ```python 블럭에 70여 줄
인라인 emit 했고, recorder_transform 의 ``_pywinauto_click_code`` 는 별도로
6줄 minimal 만 emit (메모장처럼 문서 내용이 title 에 들어가는 앱 재실행 시
matching 실패 회귀). 이 helper 로 단일 source of truth.

핵심:
- DPI Awareness 설정 (pywinauto ↔ pyautogui 좌표 일치 보장)
- ``Application.connect`` — 비브라우저는 ``program_name`` (예: ``.*메모장``)
  정규식 매칭 → 동적 title (예: ``"*hello world - 메모장"``) 변화에도 안정.
  브라우저는 full title + ``found_index=0`` (페이지별 식별).
- selector fallback chain (control_type+title 1차, title only 2차, title_re 3차,
  control_type only 4차)
- 창 활성화 (``IsIconic`` → SW_RESTORE/SHOW, BringWindowToTop, SetForegroundWindow)
- walk_up to clickable parent (Button / MenuItem / Edit 등)
- 동적 ``rect`` → center 좌표 (창 활성화 후 최신 좌표 사용)
- pyautogui PRIMARY click + ``element.click_input()`` fallback
  (UWP/XAML/Win32 모두 좌표 hit-test 가 가장 안정 — 사용자 보고 5/5)

호출자가 imports 를 prepend 책임 (``extract_library_block`` essential
imports 가 ``ctypes / time / pyautogui / pywinauto.Application`` 자동 prepend).
이 helper 는 markdown / AI 프롬프트 wrap 안 함 — 순수 Python 코드만 반환.

`Application(...)` (unqualified) 형태 — essential imports
``from pywinauto import Application`` 매치. ``pywinauto.Application(...)``
(fully qualified) 금지 (test_182 회귀).

PR-19a 시점 분리 결정: ``core/win_inspector.py`` 의
``_get_desktop_element_info_text`` 가 동일 logic 을 inline 으로 emit 하는 상태
(AI 학습용 commentary + ``WindowFromPoint`` 디버그 체크 포함). 단순 helper
호출로 교체 시 AI 코드 생성 품질 회귀 risk 가 있어 win_inspector 리팩은
별도 PR (19a') 로 분리. 둘 사이 divergence 방지는 sentinel 회귀 가드
(``test_187_pywinauto_codegen_sentinel_consistency``) 가 책임 — helper 와
win_inspector 가 공통으로 emit 해야 할 핵심 패턴 (program_name title_re,
DPI Awareness, Application unqualified, fallback chain, walk_up) 의 sentinel
일치 검증.
"""

from __future__ import annotations

import json
import re
from typing import Optional

__all__ = ["build_pywinauto_click_code"]


def _safe_str_literal(s: str) -> str:
    """user-data string → 안전한 Python string literal (double quote).

    [PR-19e 2026-05-24] 사용자 GUI 실측 발견: element name 에 CR (``\\r``) 같은
    control char 포함 시 (Win11 메모장 Document name = ``"1111\\r2222\\r3333\\r"``)
    raw f-string interpolation 하면 SyntaxError (unterminated string literal).

    ``json.dumps(s, ensure_ascii=False)`` 사용:
    - 항상 double quote 형식 (기존 test sentinel ``title="검색"`` 호환)
    - 모든 control char (CR/LF/tab/backslash/quote) 안전 escape
    - 한국어 등 unicode literal 그대로 유지 (escape 안 함)
    """
    return json.dumps(s, ensure_ascii=False)


_CLICKABLE_PARENT_TYPES = (
    "Button",
    "MenuItem",
    "MenuBarItem",
    "TabItem",
    "ListItem",
    "CheckBox",
    "RadioButton",
    "Hyperlink",
    "Edit",
    "ComboBox",
    "SplitButton",
    "TreeItem",
)


def build_pywinauto_click_code(meta: dict, button: str = "left") -> str:
    """element 메타 → 실행 가능한 pywinauto + pyautogui click 코드.

    Args:
        meta: element 메타 dict. 인식 필드 (모두 옵션):

            - ``control_type`` (권장 — selector / fallback 양쪽 사용)
            - ``name``, ``automation_id``, ``class_name``
            - ``window_title`` — top-level window title. ``parent_window_title``
              (win_inspector picker 필드명) 도 동일 의미로 fallback.
            - ``is_browser_process`` (기본 False) — True 면 full title hardcode
              (페이지별 식별 중요). ``is_browser`` 도 동일 의미로 fallback.
            - ``recommended_backend`` (``'uia'`` | ``'win32'``, 기본 ``'uia'``)
        button: ``'left'`` / ``'right'`` / ``'middle'`` (기본 ``'left'``).

    Returns:
        Python 코드 (multi-line, 끝 newline 없음). imports 미포함 — 호출자가
        essential imports 를 prepend.
    """
    ctrl_type = (meta.get("control_type") or "").strip()
    name = (meta.get("name") or "").strip()
    auto_id = (meta.get("automation_id") or "").strip()
    class_name = (meta.get("class_name") or "").strip()
    window_title = (meta.get("window_title") or meta.get("parent_window_title") or "").strip()
    is_browser_process = bool(meta.get("is_browser_process") or meta.get("is_browser"))
    recommended_backend = (meta.get("recommended_backend") or "uia").strip() or "uia"

    element_selector = _build_element_selector(
        ctrl_type=ctrl_type,
        name=name,
        auto_id=auto_id,
        class_name=class_name,
        recommended_backend=recommended_backend,
    )
    # PR-19e: process_id 우선 connect + title fallback (Win11 메모장 등 element_inspect
    # 가 탭 이름만 잡고 진짜 top-level window title 못 잡는 케이스 회피).
    process_id_raw = meta.get("process_id")
    try:
        process_id = int(process_id_raw) if process_id_raw else None
    except (TypeError, ValueError):
        process_id = None
    connect_block_lines = _build_connect_block(
        window_title=window_title,
        is_browser_process=is_browser_process,
        recommended_backend=recommended_backend,
        process_id=process_id,
    )
    fallback_lambdas = _build_fallback_lambdas(ctrl_type=ctrl_type, name=name)

    btn = (button or "left").lower()
    if btn not in ("left", "right", "middle"):
        btn = "left"
    pyautogui_btn_arg = "" if btn == "left" else f", button={btn!r}"
    element_click_method = {
        "left": "click_input",
        "right": "right_click_input",
        "middle": "click_input",
    }[btn]

    clickable_types_repr = "{" + ", ".join(f"'{t}'" for t in _CLICKABLE_PARENT_TYPES) + "}"

    lines: list[str] = []

    # 1. DPI Awareness
    lines.append("# DPI Awareness - pywinauto/pyautogui 좌표 일치 보장")
    lines.append("try:")
    lines.append("    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))")
    lines.append("except Exception:")
    lines.append("    try:")
    lines.append("        ctypes.windll.shcore.SetProcessDpiAwareness(2)")
    lines.append("    except Exception:")
    lines.append("        pass")
    lines.append("pyautogui.FAILSAFE = False")
    lines.append("")

    # 2. Application connect (PR-19e: process_id 우선 chain 또는 기존 title 단일 path)
    lines.extend(connect_block_lines)

    # 3. Element resolution with fallback chain
    lines.append("")
    lines.append("def _resolve_element():")
    lines.append(f"    _selectors = [lambda: {element_selector}]")
    for lam in fallback_lambdas:
        lines.append(f"    _selectors.append(lambda: {lam})")
    lines.append("    for _build in _selectors:")
    lines.append("        try:")
    lines.append("            _cand = _build()")
    lines.append("            _ = _cand.element_info.control_type")
    lines.append("            return _cand")
    lines.append("        except Exception:")
    lines.append("            continue")
    lines.append(f"    return {element_selector}")
    lines.append("element = _resolve_element()")
    lines.append("")

    # 4. Window activation
    lines.append("# 창 활성화 (maximized 보존 - SW_RESTORE 는 minimized 일 때만)")
    lines.append("user32 = ctypes.windll.user32")
    lines.append("hwnd = win.handle")
    lines.append("if user32.IsIconic(hwnd):")
    lines.append("    user32.ShowWindow(hwnd, 9)  # SW_RESTORE")
    lines.append("else:")
    lines.append("    user32.ShowWindow(hwnd, 5)  # SW_SHOW")
    lines.append("user32.BringWindowToTop(hwnd)")
    lines.append("try:")
    lines.append("    user32.SetForegroundWindow(hwnd)")
    lines.append("except Exception:")
    lines.append("    pass")
    lines.append("time.sleep(0.5)")
    lines.append("")

    # 5. Walk up to clickable parent
    lines.append("# 클릭 가능한 부모 (Button/MenuItem 등) 까지 walk up")
    lines.append(f"_clickable_types = {clickable_types_repr}")
    lines.append("click_target = element")
    lines.append("try:")
    lines.append("    if element.element_info.control_type not in _clickable_types:")
    lines.append("        _cur = element")
    lines.append("        for _ in range(6):")
    lines.append("            _cur = _cur.parent()")
    lines.append("            if _cur is None or _cur.handle == win.handle:")
    lines.append("                break")
    lines.append("            if _cur.element_info.control_type in _clickable_types:")
    lines.append("                click_target = _cur")
    lines.append("                break")
    lines.append("except Exception:")
    lines.append("    pass")
    lines.append("")

    # 6. Dynamic rect → center
    lines.append("# 활성화 후 최신 rect 로 center 좌표 산출")
    lines.append("rect = click_target.rectangle()")
    lines.append("center_x = (rect.left + rect.right) // 2")
    lines.append("center_y = (rect.top + rect.bottom) // 2")
    lines.append("")

    # 7. Click — pyautogui PRIMARY + element fallback
    lines.append(
        f"# {btn} 클릭 - pyautogui PRIMARY (UWP/XAML/Win32 좌표 hit-test 안정) + element fallback"
    )
    lines.append("try:")
    lines.append(f"    pyautogui.click(center_x, center_y{pyautogui_btn_arg})")
    lines.append("except Exception:")
    lines.append("    try:")
    lines.append(f"        click_target.{element_click_method}()")
    lines.append("    except Exception:")
    lines.append("        raise")

    return "\n".join(lines)


# ── 내부 helper ──────────────────────────────────────────


def _build_element_selector(
    *,
    ctrl_type: str,
    name: str,
    auto_id: str,
    class_name: str,
    recommended_backend: str,
) -> str:
    """element 식별 selector 문자열 (예: ``win.child_window(...)``).

    우선순위 (uia):
    1. name + auto_id (non-dynamic) + control_type - 결합 (가장 discriminating, recorder baseline)
    2. name + control_type
    3. auto_id (non-dynamic) + control_type
    4. class_name + control_type
    5. class_name
    6. name
    7. auto_id (동적 포함 - 마지막 수단)
    8. control_type only

    PR-19e 2026-05-24: 모든 user-data string 은 ``_safe_str_literal`` 로 escape
    (CR/quote 안전 처리). Win11 메모장 Document name = ``"1111\\r2222\\r3333\\r"``
    같은 multi-line text 가 element name 으로 잡혀도 SyntaxError 회피.
    """
    auto_id_is_dynamic = bool(auto_id) and auto_id.isdigit()
    auto_id_safe = auto_id and not auto_id_is_dynamic

    name_lit = _safe_str_literal(name)
    auto_id_lit = _safe_str_literal(auto_id)
    class_name_lit = _safe_str_literal(class_name)
    ctrl_type_lit = _safe_str_literal(ctrl_type)

    if recommended_backend == "win32":
        if name and class_name:
            return f"win.child_window(title={name_lit}, class_name={class_name_lit})"
        if class_name:
            return f"win.child_window(class_name={class_name_lit}, found_index=0)"
        if name:
            return f"win.child_window(title={name_lit})"
        return "win.child_window(found_index=0)"

    if name and auto_id_safe and ctrl_type:
        return (
            f"win.child_window(title={name_lit}, auto_id={auto_id_lit}, "
            f"control_type={ctrl_type_lit}, found_index=0)"
        )
    if name and ctrl_type:
        return f"win.child_window(title={name_lit}, control_type={ctrl_type_lit}, found_index=0)"
    if auto_id_safe:
        return f"win.child_window(auto_id={auto_id_lit}, control_type={ctrl_type_lit})"
    if class_name and ctrl_type:
        return (
            f"win.child_window(class_name={class_name_lit}, "
            f"control_type={ctrl_type_lit}, found_index=0)"
        )
    if class_name:
        return f"win.child_window(class_name={class_name_lit}, found_index=0)"
    if name:
        return f"win.child_window(title={name_lit}, found_index=0)"
    if auto_id:
        return f"win.child_window(auto_id={auto_id_lit}, control_type={ctrl_type_lit})"
    return f"win.child_window(control_type={ctrl_type_lit}, found_index=0)"


def _build_connect_block(
    *,
    window_title: str,
    is_browser_process: bool,
    recommended_backend: str,
    process_id: Optional[int] = None,
) -> list[str]:
    """``Application(...).connect(...)`` + ``app.window(...)`` 로 이어지는 코드 lines.

    PR-19e 2026-05-24: process_id 가 있으면 process 우선 connect + title fallback
    chain. Win11 메모장처럼 element_inspect 가 top-level title 못 잡고 탭 이름
    ("데스크톱 1") 만 캡처해 connect 실패하는 케이스 회피. process_id 는 녹화
    시점의 PID — 재실행 시 다른 PID 가 떠 있을 가능성 높아 fallback 필수.

    - process_id 있음: ``_connect_app()`` 함수로 try process → except title fallback
    - process_id 없음 + window_title 있음: 기존 title_re 단일 connect
    - 둘 다 없음: placeholder + ``app.top_window()``

    비브라우저: ``program_name`` (`` - `` 마지막 segment) 만 ``.*<프로그램명>`` 정규식
    매칭 → 동적 title (메모장 ``*hello - 메모장`` 등) 변화에도 안정.
    브라우저: full title hardcode + ``found_index=0`` (페이지별 식별 중요).

    `Application(...)` (unqualified) — essential imports
    ``from pywinauto import Application`` 매치 (test_182 회귀 가드).
    """
    title_connect, title_window = _build_title_connect_pair(
        window_title=window_title,
        is_browser_process=is_browser_process,
        recommended_backend=recommended_backend,
    )

    # process_id 없으면 기존 단일 connect 로직
    if not process_id:
        return [
            f"app = {title_connect}",
            f"win = {title_window}",
        ]

    # process_id 있으면 fallback chain — process 우선 (timeout 짧게), title fallback
    proc_connect = (
        f'Application(backend="{recommended_backend}").connect('
        f"process={int(process_id)}, timeout=2)"
    )
    return [
        "def _connect_app():",
        "    try:",
        f"        return {proc_connect}",
        "    except Exception:",
        "        pass",
        f"    return {title_connect}",
        "app = _connect_app()",
        # process 매칭 시 win 은 top_window 로 — title_window 의 title_re 매칭이 다른 인스턴스 잡을 위험.
        "try:",
        "    win = app.top_window()",
        "except Exception:",
        f"    win = {title_window}",
    ]


def _build_title_connect_pair(
    *,
    window_title: str,
    is_browser_process: bool,
    recommended_backend: str,
) -> tuple[str, str]:
    """``Application(...).connect(...)`` + ``app.window(...)`` 한 줄 쌍 (title 기반).

    ``_build_connect_block`` 의 process_id 없는 path / fallback path 양쪽에서 호출.
    """
    if not window_title:
        return (
            f'Application(backend="{recommended_backend}").connect('
            f'title="...", timeout=10, found_index=0)',
            "app.top_window()",
        )

    if is_browser_process:
        connect = (
            f'Application(backend="{recommended_backend}").connect('
            f"title={_safe_str_literal(window_title)}, timeout=10, found_index=0)"
        )
        window = f"app.window(title={_safe_str_literal(window_title)}, found_index=0)"
        return connect, window

    program_name = window_title.split(" - ")[-1].strip() or window_title
    escaped = re.escape(program_name)
    title_re_literal = _safe_str_literal(".*" + escaped)
    connect = (
        f'Application(backend="{recommended_backend}").connect('
        f"title_re={title_re_literal}, timeout=10, found_index=0)"
    )
    window = f"app.window(title_re={title_re_literal}, found_index=0)"
    return connect, window


def _build_fallback_lambdas(*, ctrl_type: str, name: str) -> list[str]:
    """primary selector 가 fail 시 시도할 lambda body 들.

    - title 만 (1차 relax — control_type 잘못 분류 케이스)
    - title_re 정규식 (2차 relax)
    - control_type only (3차 — 다른 인스턴스 / 다중 윈도우)

    PR-19e: user-data string 모두 ``_safe_str_literal`` escape (CR/quote 안전).
    """
    out: list[str] = []
    if name:
        out.append(f"win.child_window(title={_safe_str_literal(name)}, found_index=0)")
        esc_name = re.escape(name)
        out.append(
            f"win.child_window(title_re={_safe_str_literal('.*' + esc_name)}, found_index=0)"
        )
    if ctrl_type:
        out.append(f"win.child_window(control_type={_safe_str_literal(ctrl_type)}, found_index=0)")
    return out
