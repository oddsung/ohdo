# SPDX-License-Identifier: AGPL-3.0-or-later
"""UI 검사 (element picker + window inspector) 동작 핸들러.

main_window.py 가 1700+ 줄로 비대해져 영역별 분리. 이 모듈은:
- Element picker 콜백 (pick request / picked / cancelled / CDP 안내)
- Window inspector 콜백 (finish_inspect / auto_inspect_before_capture)

main_window 의 widget/attribute 에 접근하기 위해 인스턴스 보유 (`self.mw`).
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox

from core.win_inspector import format_element_label

if TYPE_CHECKING:
    from ui.main_window import MainWindow


class UIInspectionHandler:
    """Element picker + Window inspector 콜백 통합 핸들러.

    main_window 의 widget (console_panel, chat_panel, statusBar, settings 등) 에
    접근. 멤버 메서드 추출만, 동작 변경 없음 (회귀 위험 최소화).
    """

    def __init__(self, main_window: "MainWindow") -> None:
        self.mw = main_window

    # ── Element picker handlers ──────────────────────────────────────

    def on_pick_request(self) -> None:
        """UI 요소 선택 요청 - 요소 피커 오버레이 표시"""
        mw = self.mw
        mw.console_panel.log(
            "UI 요소 피커 시작 - 선택할 요소에 마우스를 올린 후 클릭하세요", "INFO"
        )
        mw.statusBar().showMessage("선택할 UI 요소를 클릭하세요... (ESC: 취소)")
        mw.showMinimized()
        QTimer.singleShot(400, mw.element_picker.start_picking)

    def on_picked(self, element_info: dict) -> None:
        """UI 요소 선택 완료 콜백"""
        mw = self.mw
        # 요소 영역 스크린샷 캡처를 먼저 수행 (메인 윈도우 표시 전)
        try:
            import mss
            from PIL import Image as PilImage

            rect = element_info.get("rect", {})
            w = rect.get("width", 0)
            h = rect.get("height", 0)

            if w > 0 and h > 0:
                padding = 20
                cap_left = max(0, rect["left"] - padding)
                cap_top = max(0, rect["top"] - padding)
                cap_w = w + padding * 2
                cap_h = h + padding * 2

                with mss.mss() as sct:
                    sct_img = sct.grab(
                        {
                            "left": cap_left,
                            "top": cap_top,
                            "width": cap_w,
                            "height": cap_h,
                        }
                    )
                    img = PilImage.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                if mw.current_session:
                    captures_dir = mw.session_manager.get_captures_dir(
                        mw.current_session.session_id
                    )
                else:
                    from ui.main_window import PROJECT_ROOT

                    captures_dir = PROJECT_ROOT / "data" / "captures"
                    captures_dir.mkdir(parents=True, exist_ok=True)

                filename = f"element_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                filepath = captures_dir / filename
                img.save(str(filepath))
                mw.pending_images.append(str(filepath))
                mw.console_panel.log(f"UI 요소 이미지 저장: {filepath} ({w}x{h})", "INFO")

        except Exception as e:
            mw.console_panel.log(f"요소 이미지 캡처 실패: {e}", "WARNING")

        # 캡처 완료 후 메인 윈도우 표시
        mw.showNormal()
        mw.activateWindow()

        # 요소를 대화창 칩으로 추가
        mw.chat_panel.add_element_chip(element_info)

        display = format_element_label(element_info)
        parent = element_info.get("parent_window_title", "")

        mw.statusBar().showMessage("UI 요소 선택 완료 - 다음 요청에 요소 정보가 자동 포함됩니다")
        mw.console_panel.log(
            f"요소 선택 완료: {display}"
            + (f" (창: {parent})" if parent and parent not in display else ""),
            "INFO",
        )

        # CDP 미연결 브라우저 element 감지 시 1회 안내 (suppressible)
        browser_type = element_info.get("browser_type")
        if browser_type:
            dom_ctx = element_info.get("dom_context") or {}
            if not dom_ctx.get("cdp_available"):
                self.maybe_show_cdp_hint(browser_type)

    def maybe_show_cdp_hint(self, browser_name: str) -> None:
        """브라우저 element 인데 CDP 미연결 시 사용자에게 1회 안내."""
        mw = self.mw
        hints = mw.settings.setdefault("hints", {})
        if hints.get("cdp_browser_hint_dismissed", False):
            return

        msg = QMessageBox(mw)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle(f"{browser_name} 디버그 포트 권장")
        msg.setText(
            f"{browser_name} 이(가) 디버그 포트 없이 실행 중입니다.\n\n"
            "HTML 페이지 요소 자동화는 Chrome DevTools Protocol (CDP) 가 연결돼야\n"
            "안정적으로 동작합니다. 현재는 pyautogui 좌표 클릭으로 fallback 됩니다.\n"
            "(페이지 변화 시 위치가 어긋날 수 있음)"
        )
        msg.setInformativeText(
            f"더 안정적인 자동화를 원하시면 {browser_name} 을(를) 종료한 후\n"
            "다음 명령으로 재시작하세요 (PowerShell):\n\n"
            '& "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
            "--remote-debugging-port=9222\n\n"
            "이후 picker 가 자동으로 CDP 연결 -> Selenium DOM 기반 안정 코드를 생성합니다."
        )
        btn_ok = msg.addButton("확인", QMessageBox.ButtonRole.AcceptRole)
        btn_dismiss = msg.addButton("다시 보지 않기", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_ok)
        msg.exec()

        if msg.clickedButton() is btn_dismiss:
            hints["cdp_browser_hint_dismissed"] = True
            mw._save_settings()
            mw.console_panel.log(
                "CDP 안내가 비활성화되었습니다. 설정에서 다시 켤 수 있습니다.",
                "INFO",
            )

    def on_pick_cancelled(self) -> None:
        """UI 요소 선택 취소 (ESC 또는 우클릭)"""
        mw = self.mw
        mw.showNormal()
        mw.activateWindow()
        mw.console_panel.log("UI 요소 선택이 취소되었습니다.", "INFO")
        mw.statusBar().showMessage("준비 완료")

    # ── Window inspector handlers ───────────────────────────────────

    def finish_inspect(self, window_info: dict | None) -> None:
        """검사 결과 처리 및 앱 복원"""
        mw = self.mw
        # 앱 복원
        mw.showNormal()
        mw.activateWindow()

        if window_info is None:
            mw.statusBar().showMessage("윈도우 검사 실패")
            return

        if "error" in window_info:
            mw.console_panel.log(f"윈도우 검사 실패: {window_info['error']}", "WARNING")
            mw.statusBar().showMessage("윈도우 검사 실패")
            return

        # 검사 결과를 텍스트로 변환
        context_text = mw.win_inspector.get_control_info_text(window_info)
        mw.pending_window_context = context_text

        # 로그에 표시
        title = window_info.get("window_title", "?")
        count = window_info.get("control_count", 0)
        mw.console_panel.log(f"윈도우 검사 완료: '{title}' ({count}개 컨트롤 발견)", "INFO")

        # 컨트롤 목록을 콘솔에 표시
        for ctrl in window_info.get("controls", [])[:20]:
            indent = "  " * ctrl.get("depth", 0)
            name = ctrl.get("name", "")
            ctype = ctrl.get("control_type", "")
            mw.console_panel.log(f"  {indent}[{ctype}] {name}", "DEBUG")

        mw.chat_panel.set_capture_status(f"윈도우 검사 완료: {title} ({count}개 컨트롤)")
        mw.statusBar().showMessage("윈도우 검사 완료 - 다음 요청에 컨트롤 정보가 자동 포함됩니다")

    def auto_inspect_before_capture(self) -> None:
        """캡처 전에 포그라운드 윈도우 정보를 자동 수집합니다.

        AI RPA Solution 자체는 건너뛰고 실제 타겟 앱을 검사합니다.
        """
        mw = self.mw
        if not mw.win_inspector.is_available:
            return

        try:
            if sys.platform != "win32":
                return

            import ctypes

            hwnd = ctypes.windll.user32.GetForegroundWindow()  # type: ignore
            if not hwnd:
                return

            # 먼저 포그라운드 윈도우 타이틀 확인
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)  # type: ignore
            fg_title = buf.value

            # 자기 자신이면 건너뛰기
            if "AI RPA Solution" in fg_title:
                mw.console_panel.log(
                    f"자동 검사 건너뜀: 포그라운드가 자기 자신 ('{fg_title}')",
                    "DEBUG",
                )
                # 자기 자신 다음의 윈도우를 찾기 시도
                windows = mw.win_inspector.list_windows()
                target_win = None
                for w in windows:
                    if "AI RPA Solution" not in w.get("title", ""):
                        target_win = w
                        break

                if target_win:
                    window_info = mw.win_inspector.inspect_window(
                        handle=target_win["handle"],
                        max_depth=2,
                        max_controls=30,
                    )
                    if "error" not in window_info:
                        mw.pending_window_context = mw.win_inspector.get_control_info_text(
                            window_info
                        )
                        mw.console_panel.log(
                            f"대체 윈도우 검사 완료: '{target_win['title']}'",
                            "INFO",
                        )
                return

            # 자기 자신이 아닌 경우 정상 검사
            window_info = mw.win_inspector.inspect_window(
                handle=hwnd,
                max_depth=2,
                max_controls=30,
            )
            if "error" not in window_info:
                mw.pending_window_context = mw.win_inspector.get_control_info_text(window_info)
                title = window_info.get("window_title", "?")
                mw.console_panel.log(
                    f"캡처 대상 윈도우 자동 검사: '{title}' "
                    f"({window_info.get('control_count', 0)}개 컨트롤)",
                    "INFO",
                )
        except Exception as e:
            mw.console_panel.log(f"자동 윈도우 검사 실패 (무시): {e}", "DEBUG")
