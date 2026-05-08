# SPDX-License-Identifier: AGPL-3.0-or-later
"""AI 호출 controller (메인 윈도우 분해 Step 4).

main_window.py 가 1538 줄로 비대해 영역별 분리. 이 모듈은:
- 사용자 메시지 → AI 호출 트리거 (on_user_message)
- 백그라운드 스레드에서 AI 어댑터 호출 + prompt 구성 (call_ai_thread)
- AI 응답 수신 → 코드 추출 + step 누적 (on_ai_response)
- step 실행 결과 표시 (on_step_executed)
- AI 코드 변조에 대한 수동 편집 / send_keys 공백 자동 복원 (apply_manual_edit_patches)
- AI 취소 (on_cancel_ai)

main_window 에 위임 stub 메서드는 유지 (signal connect 호환 + 테스트 grep 호환).
회귀 테스트는 AICallHandler 의 source 를 검사하도록 갱신됨.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from core.session_manager import Step
from core.win_inspector import format_element_label

if TYPE_CHECKING:
    from ui.main_window import MainWindow

logger = logging.getLogger(__name__)


class AICallHandler:
    """AI 어댑터 호출 + 응답 처리 + step 누적 핸들러.

    main_window 의 widget/attribute 에 접근하기 위해 인스턴스 보유 (`self.mw`).
    멤버 메서드 추출만, 동작 변경 없음 (회귀 위험 최소화).
    """

    def __init__(self, main_window: "MainWindow") -> None:
        self.mw = main_window

    # ── AI 취소 ─────────────────────────────────────────────────

    def on_cancel_ai(self) -> None:
        """AI 생성 중지 요청 처리"""
        mw = self.mw
        mw.console_panel.log("사용자가 AI 요청을 취소했습니다.", "INFO")
        mw.statusBar().showMessage("취소 중...")
        mw.ai_engine.cancel()

    # ── 사용자 메시지 → AI 호출 트리거 ─────────────────────────

    def on_user_message(self, message: str) -> None:
        """사용자가 대화 패널에서 메시지를 전송"""
        mw = self.mw
        if not message.strip() and not mw.pending_images:
            return
        if mw.is_processing:
            return
        if not mw.current_session:
            QMessageBox.information(mw, "안내", "먼저 새 세션을 생성해주세요. (Ctrl+N)")
            return

        mw.is_processing = True
        mw.chat_panel.set_generating(True)
        mw.statusBar().showMessage("AI 응답 대기 중...")
        mw.console_panel.log(f"사용자 요청: {message[:100]}...", "INFO")

        # 백그라운드 스레드에서 AI 호출
        images = list(mw.pending_images)
        mw.pending_images.clear()
        mw.chat_panel.clear_capture_status()

        thread = threading.Thread(target=self.call_ai_thread, args=(message, images), daemon=True)
        thread.start()

    # ── 백그라운드: AI 어댑터 호출 + prompt 구성 ───────────────

    def call_ai_thread(self, user_message: str, images: list[str]) -> None:
        """백그라운드 스레드: AI 프롬프트 전송 및 응답 수신"""
        mw = self.mw
        try:
            # 방어 코드 추가
            if not mw.current_session:
                raise ValueError("세션이 초기화되지 않았습니다.")

            # 프롬프트 구성 (윈도우/요소 컨텍스트 포함)
            window_ctx = mw.pending_window_context if mw.pending_window_context else None
            mw.pending_window_context = ""  # 사용 후 초기화

            pending_elems = mw.chat_panel.get_pending_elements()
            element_summary = ""  # 세션 기록용 요소 요약
            if pending_elems:
                parts = [mw.win_inspector.get_element_info_text(e) for e in pending_elems]
                element_ctx: str | None = "\n\n---\n\n".join(parts)
                # 세션 기록용 요소 요약 생성
                summaries = [format_element_label(e) for e in pending_elems]
                element_summary = "📌 선택된 요소: " + ", ".join(summaries) + "\n"
                mw.chat_panel.clear_pending_elements()
            else:
                element_ctx = None

            # Selenium DOM 경로는 picker 가 CDP 로 실제 DOM 정보를 수집했을 때만.
            # WinInspector.should_use_selenium 으로 단일 기준 적용 (하드코딩 0).
            is_browser_elem = (
                any(mw.win_inspector.should_use_selenium(e) for e in pending_elems)
                if pending_elems
                else False
            )
            prompt = mw.prompt_builder.build_step_prompt(
                session=mw.current_session,
                user_request=user_message,
                image_paths=images if images else None,
                window_context=window_ctx,
                element_context=element_ctx,
                project_type=mw.current_session.project_type,
                is_browser_element=is_browser_elem,
            )

            mw.signals.log_message.emit(f"[PROMPT] 프롬프트 전송 ({len(prompt)}자)")

            # AI 호출 (비동기를 동기로 래핑)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(mw.ai_engine.generate(prompt, images))
            loop.close()

            mw.signals.log_message.emit(
                f"[AI] 응답 수신 ({response.response_time_ms}ms, 코드 {len(response.code)}자)"
            )

            # AI 원본 응답 로깅 (디버깅용)
            raw_preview = response.raw_response[:300] if response.raw_response else "(응답 없음)"
            mw.signals.log_message.emit(f"[AI] 원본 응답 미리보기: {raw_preview}")

            # 결과 전달 (요소 정보 포함)
            display_message = element_summary + user_message if element_summary else user_message
            mw.signals.ai_response_ready.emit(
                {
                    "user_message": user_message,
                    "display_message": display_message,  # 세션 기록용 (요소 정보 포함)
                    "images": images,
                    "response": {
                        "text": response.text,
                        "code": response.code,
                        "description": response.description,
                        "packages": response.packages,
                        "raw_response": response.raw_response,
                        "tokens_used": response.tokens_used,
                        "response_time_ms": response.response_time_ms,
                        "success": response.success,
                        "error": response.error,
                        "cancelled": response.cancelled,
                    },
                    "prompt": prompt,
                }
            )

        except Exception as e:
            mw.signals.error_occurred.emit(f"AI 호출 실패: {str(e)}")

    # ── AI 응답 수신 처리 (메인 스레드) ────────────────────────

    def on_ai_response(self, data: dict) -> None:
        """AI 응답 수신 처리 (메인 스레드)"""
        mw = self.mw
        response = data["response"]

        # 프롬프트 탭에 상세 로그 기록
        element_info = ""
        display_msg = data.get("display_message", "")
        if display_msg.startswith("📌"):
            # 요소 정보 추출
            lines = display_msg.split("\n", 1)
            element_info = lines[0] if lines else ""

        mw.console_panel.log_prompt_detail(
            user_message=data["user_message"],
            full_prompt=data.get("prompt", ""),
            ai_response=response.get("description") or response.get("text", ""),
            code=response.get("code", ""),
            tokens_used=response.get("tokens_used", 0),
            response_time_ms=response.get("response_time_ms", 0),
            ai_engine=mw.ai_engine.current_engine
            if hasattr(mw.ai_engine, "current_engine")
            else "",
            has_images=bool(data.get("images")),
            element_info=element_info,
        )

        # 취소된 경우: 안내 메시지만 표시하고 세션 기록 없이 종료
        if response.get("cancelled"):
            mw.chat_panel.add_system_message("요청이 취소되었습니다.")
            mw.is_processing = False
            mw.chat_panel.set_generating(False)
            mw.statusBar().showMessage("취소됨")
            return

        # AI 응답을 대화 패널에 표시
        if response["success"]:
            ai_text = response["description"] or response["text"]
            mw.chat_panel.add_ai_message(ai_text.strip())

            # 코드가 있으면 코드 뷰어에 추가
            if response["code"]:
                # 수동 편집된 값이 AI에 의해 되돌아가지 않도록 강제 복원
                patched_code = self.apply_manual_edit_patches(response["code"])
                if patched_code != response["code"]:
                    mw.console_panel.log(
                        "[편집 복원] 수동 수정된 값이 AI 코드에 자동 복원되었습니다.", "INFO"
                    )
                    response["code"] = patched_code

                mw.current_code = response["code"]
                step_id = len(mw.current_session.steps) + 1
                # 캡처 이미지가 있으면 첫 번째 이미지를 함께 표시
                images = data.get("images", [])
                capture_path = images[0] if images else None
                mw.code_viewer.add_step(step_id, response["code"], capture_path)
                mw.console_panel.log(f"코드 추출 완료 ({len(response['code'])}자)", "INFO")
            else:
                # 코드가 없는 경우 안내 (단, 역질문 등 정상적인 응답일 수도 있음)
                mw.console_panel.log("[INFO] 코드 추출 없음. 보조 텍스트 출력됨.", "INFO")
        else:
            mw.chat_panel.add_system_message(f"AI 응답 실패: {response['error']}")

        # 세션에 스텝 추가 (요소 정보 포함된 메시지 사용)
        recorded_message = data.get("display_message", data["user_message"])
        # import/코드 분리
        full_code = response.get("code", "")
        from core.import_manager import extract_code_delta, extract_import_delta, extract_imports

        separated_imports, separated_body = extract_imports(full_code)

        # 이전 스텝의 누적 코드에서 이번 스텝에서 새로 추가된 부분만 추출
        prev_body = ""
        prev_imports: list = []
        if mw.current_session and mw.current_session.steps:
            last_step = mw.current_session.steps[-1]
            s = last_step if isinstance(last_step, dict) else {}
            prev_full_code = s.get("generated_code", "")
            prev_imports = s.get("step_imports", [])
            if prev_full_code:
                _, prev_body = extract_imports(prev_full_code)

        delta_body = extract_code_delta(separated_body, prev_body)
        delta_imports = extract_import_delta(separated_imports, prev_imports)

        step = Step(
            status="completed" if response["success"] else "failed",
            conversation=[
                {
                    "role": "user",
                    "content": recorded_message,
                    "timestamp": datetime.now().isoformat(),
                },
                {
                    "role": "assistant",
                    "content": response.get("description", response["text"]),
                    "timestamp": datetime.now().isoformat(),
                },
            ],
            generated_code=full_code,
            required_packages=response.get("packages", []),
            captures=[
                {"type": "screen", "path": img, "timestamp": datetime.now().isoformat()}
                for img in data.get("images", [])
            ],
            prompt_log={
                "full_prompt": data.get("prompt", ""),
                "raw_response": response.get("raw_response", ""),
                "tokens_used": response.get("tokens_used", 0),
                "response_time_ms": response.get("response_time_ms", 0),
            },
            execution_result=None,
            step_code=delta_body,
            step_imports=delta_imports,
        )
        mw.session_manager.add_step(mw.current_session, step)

        # 블럭 뷰 갱신 — add_step 이후에 호출해야 step_code가 포함됨
        if response.get("code"):
            mw._refresh_block_view()

        # 상태 복원
        mw.is_processing = False
        mw.chat_panel.set_generating(False)
        mw.statusBar().showMessage("준비 완료")

    # ── step 실행 결과 표시 ───────────────────────────────────

    def on_step_executed(self, data: dict) -> None:
        """스텝 실행 완료 처리.

        signal slot 으로 호출되어 코드 뷰 path 의 단일 step 실행 완료 시점에 도달.
        execute_code_thread 의 finally 가 QTimer.singleShot 으로 set_running(False) 를
        호출하지만 timing/race 로 누락되는 회귀 (5/4 사용자 보고: 실행 후 stop 버튼이
        활성화된 채 / run 버튼이 비활성화된 채 남음) 방지를 위해 catch-all 로 명시적
        리셋. CodeViewer.set_running 은 멱등 — 중복 호출해도 무해.
        """
        mw = self.mw
        success = data.get("success")
        step_id = data.get("step_id")
        mw.console_panel.log(
            f"스텝 #{step_id} 실행 완료: {'성공' if success else '실패'}",
            "INFO" if success else "ERROR",
        )
        if success and data.get("output"):
            mw.console_panel.log(f"  출력: {data['output'][:500]}", "DEBUG")
        elif not success and data.get("error"):
            # 에러 전체 내용을 줄별로 분리해서 빨간색으로 표시
            mw.console_panel.log("─" * 50, "ERROR")
            for line in data["error"].splitlines():
                if line.strip():
                    mw.console_panel.log(f"  {line}", "ERROR")
            mw.console_panel.log("─" * 50, "ERROR")
        mw.statusBar().showMessage("실행 완료" if success else "실행 실패")
        # Catch-all 안전망: 양쪽 탭 (코드 뷰 + 블럭 뷰) run/stop 버튼 명시적 리셋.
        # CodeViewer.set_running 이 block_view 까지 갱신해 양쪽 동시 처리.
        mw.code_viewer.set_running(False)

    # ── 수동 편집 / AI 변조 자동 복원 ─────────────────────────

    def apply_manual_edit_patches(self, code: str) -> str:
        """
        AI가 생성한 코드에서 값이 변조되지 않도록 두 단계로 복원합니다.

        Phase 1 - 수동 편집 복원:
            사용자가 '수정' 버튼으로 직접 편집한 줄을 강제 복원합니다.

        Phase 2 - AI 공백 변조 자동 복원:
            수동 편집 없이도, AI가 이전 스텝의 send_keys() 등 인자를
            공백만 다르게 변경했으면 이전 값으로 자동 복원합니다.
        """
        import re as _re

        mw = self.mw
        if not mw.current_session:
            return code

        # ── Phase 1: 수동 편집(manually_edited) 복원 ──
        for step_data in mw.current_session.steps:
            step = step_data if isinstance(step_data, dict) else {}
            if not step.get("manually_edited"):
                continue
            old_code = step.get("edit_original_code", "")
            edited_code = step.get("generated_code", "")
            if not old_code or not edited_code:
                continue

            changed_map: dict[str, str] = {}
            for ol, el in zip(old_code.splitlines(), edited_code.splitlines()):
                ol_s, el_s = ol.strip(), el.strip()
                if ol_s != el_s and ol_s:
                    changed_map[ol_s] = el_s

            if not changed_map:
                continue

            patched = []
            for line in code.splitlines():
                stripped = line.strip()
                if stripped in changed_map:
                    indent = len(line) - len(line.lstrip())
                    patched.append(" " * indent + changed_map[stripped])
                    mw.console_panel.log(
                        f"  [수동복원] '{stripped}' → '{changed_map[stripped]}'", "DEBUG"
                    )
                else:
                    patched.append(line)
            code = "\n".join(patched)

        # ── Phase 2: AI 공백 변조 자동 복원 ──
        # 이전 스텝 코드에서 send_keys 인자 목록 추출
        prev_code = ""
        for step_data in reversed(mw.current_session.steps):
            s = step_data if isinstance(step_data, dict) else {}
            c = s.get("generated_code", "")
            if c.strip():
                prev_code = c
                break

        if prev_code:
            # 패턴: variable.send_keys("value") 또는 variable.send_keys('value')
            send_keys_pat = _re.compile(r'([ \t]*)(\w+)\.send_keys\((["\'])(.*?)\3\)')

            # 이전 코드의 send_keys 값 수집: {변수명: (따옴표, 값)}
            prev_sends: dict[str, tuple[str, str]] = {}
            for m in send_keys_pat.finditer(prev_code):
                _, varname, quote, value = m.groups()
                prev_sends[varname] = (quote, value)

            # 새 코드에서 변수명이 같은 send_keys 호출의 값이 공백만 다르면 복원
            def _restore(m: _re.Match) -> str:
                indent, varname, quote, value = m.groups()
                if varname in prev_sends:
                    old_quote, old_value = prev_sends[varname]
                    # 공백 제거 후 동일한 경우 → AI가 공백을 추가/삭제한 것으로 판단
                    if value.strip() == old_value.strip() and value != old_value:
                        mw.console_panel.log(
                            f"  [AI변조복원] {varname}.send_keys({repr(value)}) "
                            f"→ send_keys({repr(old_value)})",
                            "DEBUG",
                        )
                        return f"{indent}{varname}.send_keys({old_quote}{old_value}{old_quote})"
                return m.group(0)

            code = send_keys_pat.sub(_restore, code)

        return code
