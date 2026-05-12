# SPDX-License-Identifier: AGPL-3.0-or-later
"""블럭/코드 실행 controller (메인 윈도우 분해 Step 3).

main_window.py 가 1880 줄로 비대해져 영역별 분리. 이 모듈은:
- 코드 뷰어 탭 ▶ 실행 (CodeSandbox 서브프로세스 path)
- 블럭 뷰 탭 ▶ N부터 실행 / ⏯ 단독 실행 (ExecutionKernel path)
- F9 강제 중지 (3 path 모두 처리)
- 메인 윈도우 lower / restore (raise_/activateWindow)
- 커널 상태 / 블럭 step 진행 표시
- Step wait 변경 핸들러 (글로벌 vs 세션 vs step 우선순위)
- 유효 Python 실행 경로 결정 (venv → scanner → sys.executable 폴백)

main_window 에 위임 stub 메서드는 유지 (signal connect 호환 + 테스트 grep 호환).
회귀 테스트 test_55/56/57 은 BlockExecutionHandler 의 source 를 검사하도록 갱신됨.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

# UI-Core 분리 (Phase 1.2 Chunk B): core.app_service 단일 진입점 경유.
from core.app_service import (
    INITIAL_BLOCK_STEP_ID,
    LIBRARY_BLOCK_STEP_ID,
    CodeSandbox,
    ExecutionKernel,
    extract_library_block,
)

if TYPE_CHECKING:
    from ui.main_window import MainWindow

PROJECT_ROOT = Path(__file__).parent.parent
logger = logging.getLogger(__name__)


class BlockExecutionHandler:
    """블럭/코드 실행 path + 메인 윈도우 lower/restore 통합 핸들러.

    main_window 의 widget/attribute 에 접근하기 위해 인스턴스 보유 (`self.mw`).
    멤버 메서드 추출만, 동작 변경 없음 (회귀 위험 최소화).
    """

    def __init__(self, main_window: "MainWindow") -> None:
        self.mw = main_window

    # ── 코드 뷰어 탭 실행 (CodeSandbox path) ────────────────────────────

    def on_run_code(self, code: str) -> None:
        """코드 실행 요청 (코드 뷰어 탭의 ▶ 실행 버튼)"""
        mw = self.mw
        if not code.strip():
            QMessageBox.warning(mw, "경고", "실행할 코드가 없습니다.")
            return

        mw.console_panel.log("코드 실행 시작...", "INFO")
        mw.statusBar().showMessage("코드 실행 중...")

        # UI 상태 - 실행 중 표시 (run_btn 비활성, stop_btn 활성)
        mw.code_viewer.set_running(True)

        thread = threading.Thread(target=self.execute_code_thread, args=(code,), daemon=True)
        thread.start()

    def execute_code_thread(self, code: str) -> None:
        """코드를 백그라운드에서 실행"""
        mw = self.mw
        try:
            cwd = None
            if mw.current_session:
                cwd = str(mw.session_manager.get_scripts_dir(mw.current_session.session_id))

            # Python 실행 경로 결정 (유효성 검증 포함)
            python_exe = self.get_valid_python_exe()
            sandbox = CodeSandbox(python_exe=python_exe, timeout=60)
            mw._current_sandbox = sandbox  # F9 강제 중지용 참조 보관

            # UI 자동화 코드 실행 시 우리 창이 대상 창을 가리지 않도록 최소화
            if sys.platform == "win32":
                import ctypes as _ctypes

                is_admin = bool(_ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
                if not is_admin:
                    logger.info(
                        "주의: 현재 프로세스가 일반 권한으로 실행 중입니다. "
                        "대상 앱이 관리자 권한이면 WM 메시지 클릭이 차단됩니다."
                    )

            def _minimize_self():
                """스크립트 실행 전 RPA 창 최소화 (대상 창이 가려지지 않도록)"""
                try:
                    import ctypes as ct

                    hwnd = int(mw.winId())
                    ct.windll.user32.ShowWindow(
                        hwnd, 2
                    )  # SW_MINIMIZE  # type: ignore[attr-defined]
                except Exception:
                    pass

            def _restore_self():
                """스크립트 실행 후 RPA 창 복원"""
                try:
                    import ctypes as ct

                    hwnd = int(mw.winId())
                    ct.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE  # type: ignore[attr-defined]
                except Exception:
                    pass

            result = sandbox.execute(
                code, cwd, pre_exec_callback=_minimize_self, post_exec_callback=_restore_self
            )

            mw.signals.step_executed.emit(
                {
                    "step_id": len(mw.current_session.steps) if mw.current_session else 0,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                }
            )

        except Exception as e:
            mw.signals.error_occurred.emit(f"코드 실행 오류: {str(e)}")
        finally:
            mw._current_sandbox = None  # 실행 완료 후 참조 해제
            # UI 복원 (메인 스레드로) — run_btn 다시 활성, stop_btn 비활성
            QTimer.singleShot(0, lambda: mw.code_viewer.set_running(False))

    # ── 블럭 기반 실행 (Colab-style) ──────────────────────────────────

    def get_or_create_kernel(self) -> Optional[ExecutionKernel]:
        """현재 세션의 ExecutionKernel을 반환합니다 (없으면 생성)."""
        mw = self.mw
        if not mw.current_session:
            return None
        sid = mw.current_session.session_id
        if sid not in mw._kernels or not mw._kernels[sid].is_alive:
            kernel = ExecutionKernel(python_exe=self.get_valid_python_exe(), default_timeout=60)
            kernel.start()
            mw._kernels[sid] = kernel
            logger.info("세션 %s 용 ExecutionKernel 생성", sid)
        return mw._kernels[sid]

    def on_run_from_step(self, start_step_id: int) -> None:
        """블럭 뷰: N번 스텝부터 실행 요청 (N부터 끝까지)"""
        mw = self.mw
        if not mw.current_session:
            QMessageBox.warning(mw, "경고", "세션이 없습니다.")
            return
        if not mw.current_session.steps:
            QMessageBox.warning(mw, "경고", "실행할 스텝이 없습니다.")
            return

        mw.console_panel.log(f"블럭 실행 시작 (Step {start_step_id}부터)...", "INFO")
        mw.code_viewer.set_running(True)
        mw.statusBar().showMessage(f"블럭 실행 중 (Step {start_step_id}~)...")

        kernel = self.get_or_create_kernel()
        if kernel is None:
            mw.signals.error_occurred.emit("커널 생성 실패")
            return

        # 실행 중 메인 윈도우를 z-order 최하단으로 보냄 (lower).
        # hide/minimize 와 달리 visible 유지 + 작업표시줄에 남음 → 사용자가
        # 실행 상태 확인 가능. 자동화 코드가 자기 윈도우 띄우면 자연스럽게 위로.
        # 복원 시 raise_/activateWindow 가 안정적 (Win11 정책 회피).
        mw.lower()

        thread = threading.Thread(
            target=self.run_blocks_thread, args=(kernel, start_step_id, None), daemon=True
        )
        thread.start()

    def on_run_initial_block(self) -> None:
        """블럭 뷰: Initial 블럭 단독 실행 (Phase 2.5).

        사용자가 driver/options 등 setup 변수를 재정의하고 싶을 때 첫 step 안
        돌려도 되도록 Initial 블럭 (변수/초기값) 만 커널에 실행. 다른 step 들의
        실행 상태 (kernel.executed_steps) 는 건드리지 않음.

        실행 코드 = (라이브러리 블럭 코드 — 커널에 미초기화 시) + Initial 카드
        현재 텍스트. 라이브러리 코드는 카드의 import/helper 가 빠져 NameError
        나는 회귀 방지용. Initial 코드는 카드 텍스트를 직접 사용 (사용자 편집 반영).
        """
        mw = self.mw
        if not mw.current_session:
            QMessageBox.warning(mw, "경고", "세션이 없습니다.")
            return

        # Initial 블럭 카드에서 현재 텍스트 추출 (사용자 편집 반영)
        initial_code = ""
        block_view = getattr(mw.code_viewer, "block_view", None)
        if block_view is not None:
            for card in getattr(block_view, "_block_cards", []):
                if card.step_id == INITIAL_BLOCK_STEP_ID:
                    initial_code = card.code_edit.toPlainText()
                    break
        if not initial_code.strip():
            QMessageBox.information(
                mw,
                "안내",
                "Initial 블럭 코드가 비어 있습니다. 첫 step 의 setup 코드가 "
                "있어야 Initial 블럭이 추출됩니다.",
            )
            return

        kernel = self.get_or_create_kernel()
        if kernel is None:
            mw.signals.error_occurred.emit("커널 생성 실패")
            return

        mw.console_panel.log("⏯ Initial 블럭 단독 실행...", "INFO")
        mw.code_viewer.set_running(True)
        mw.statusBar().showMessage("Initial 블럭 단독 실행 중...")
        mw.lower()

        thread = threading.Thread(
            target=self._run_initial_block_thread,
            args=(kernel, initial_code),
            daemon=True,
        )
        thread.start()

    def _run_initial_block_thread(self, kernel: ExecutionKernel, initial_code: str) -> None:
        """Initial 블럭 단독 실행 워커 (백그라운드)."""
        mw = self.mw
        try:
            # 라이브러리 블럭이 커널에 없으면 먼저 실행 (imports/helpers 보장).
            # NameError 회귀 방지 — 카드는 imports 표시 안 함.
            if LIBRARY_BLOCK_STEP_ID not in kernel.executed_steps:
                lib_block = extract_library_block(mw.current_session)
                if lib_block.strip():
                    mw.signals.log_message.emit("📦 라이브러리 블럭 초기화 중...")
                    lib_result = kernel.execute_block(
                        lib_block, step_id=LIBRARY_BLOCK_STEP_ID, timeout=30
                    )
                    if not lib_result.success:
                        mw.signals.log_message.emit(
                            f"⚠️ 라이브러리 블럭 실행 오류: {lib_result.error}"
                        )

            mw.signals.log_message.emit("🎬 Initial 블럭 실행 시작...")
            result = kernel.execute_block(initial_code, step_id=INITIAL_BLOCK_STEP_ID)
            if result.success:
                mw.signals.log_message.emit(f"✅ Initial 블럭 완료 ({result.duration_ms}ms)")
                if result.output:
                    mw.signals.log_message.emit(f"  출력: {result.output[:300]}")
            else:
                mw.signals.log_message.emit(f"❌ Initial 블럭 실패 ({result.duration_ms}ms)")
                if result.error:
                    for line in result.error.splitlines():
                        if line.strip():
                            mw.signals.log_message.emit(f"  {line}")
        except Exception as e:
            mw.signals.error_occurred.emit(f"Initial 블럭 실행 오류: {e}")
        finally:
            mw.signals.log_message.emit("Initial 블럭 실행 완료")
            mw.signals.blocks_finished.emit()

    def on_run_single_step(self, step_id: int) -> None:
        """블럭 뷰: N번 스텝 단독 실행 (다음 step 으로 진행 안 함).

        이전 step (1..N-1) 들이 커널에 이미 실행됐으면 skip,
        없으면 silent replay 후 step N 만 실행하고 종료.

        step_id == INITIAL_BLOCK_STEP_ID (-1) 은 Initial 블럭 단독 실행 분기 (Phase 2.5).
        """
        # Phase 2.5: Initial 블럭 단독 실행 분기
        if step_id == INITIAL_BLOCK_STEP_ID:
            self.on_run_initial_block()
            return

        mw = self.mw
        if not mw.current_session:
            QMessageBox.warning(mw, "경고", "세션이 없습니다.")
            return
        if not mw.current_session.steps:
            QMessageBox.warning(mw, "경고", "실행할 스텝이 없습니다.")
            return

        mw.console_panel.log(f"⏯ Step {step_id} 단독 실행...", "INFO")
        mw.code_viewer.set_running(True)
        mw.statusBar().showMessage(f"Step {step_id} 단독 실행 중...")

        kernel = self.get_or_create_kernel()
        if kernel is None:
            mw.signals.error_occurred.emit("커널 생성 실패")
            return

        # 실행 중 메인 윈도우를 z-order 최하단으로 보냄 (lower).
        # hide/minimize 와 달리 visible 유지 + 작업표시줄에 남음 → 사용자가
        # 실행 상태 확인 가능. 자동화 코드가 자기 윈도우 띄우면 자연스럽게 위로.
        # 복원 시 raise_/activateWindow 가 안정적 (Win11 정책 회피).
        mw.lower()

        thread = threading.Thread(
            target=self.run_blocks_thread,
            args=(kernel, step_id, step_id),  # start = stop = step_id
            daemon=True,
        )
        thread.start()

    def on_wait_changed(self, step_id: int, new_wait) -> None:
        """Wait 변경 — 우선순위 (step > session > 글로벌 settings).

        - step_id == 0 (sentinel): 세션의 default 변경.
            new_wait None: Session.settings.step_delay_ms = None (글로벌 사용)
            new_wait int: Session.settings.step_delay_ms = int
            글로벌 settings 는 안 건드림 (settings_dialog 만 글로벌 변경).
        - step_id > 0: 그 step 의 wait_after_ms 만 변경 (개별 override).
        """
        mw = self.mw
        if not mw.current_session:
            return

        if step_id == 0:
            # 세션 default 변경 — 글로벌 settings 는 그대로
            mw.current_session.settings["step_delay_ms"] = new_wait
            mw.session_manager.save_session(mw.current_session)
            label = f"{new_wait}ms" if new_wait is not None else "글로벌 사용"
            mw.console_panel.log(f"⏱ 세션 default 대기시간 -> {label}", "INFO")
            # 세션 default 변경 시에는 모든 카드의 effective default 표시 갱신 필요.
            # _refresh_block_view 대신 set_session_wait 만 호출 — 카드 재생성 회피.
            global_default = mw.settings.get("execution", {}).get("step_delay_ms", 500)
            effective = new_wait if new_wait is not None else global_default
            mw.code_viewer.block_view._default_wait_ms = effective
            mw.code_viewer.block_view.set_session_wait(new_wait)
        else:
            # 개별 step 변경 — session 저장만 (UI 재생성 안 함, 포커스 유지).
            for step in mw.current_session.steps:
                if isinstance(step, dict) and step.get("step_id") == step_id:
                    step["wait_after_ms"] = new_wait
                    break
            mw.session_manager.save_session(mw.current_session)
            label = f"{new_wait}ms (개별 override)" if new_wait is not None else "기본값 사용"
            mw.console_panel.log(f"⏱ Step {step_id} 대기시간 -> {label}", "INFO")

    def on_kernel_reset(self) -> None:
        """커널 재시작 요청"""
        mw = self.mw
        if not mw.current_session:
            return
        sid = mw.current_session.session_id
        if sid in mw._kernels:
            mw._kernels[sid].stop()
            del mw._kernels[sid]
        mw.console_panel.log("커널 재시작 완료 — 변수 상태가 초기화되었습니다.", "INFO")
        mw.signals.kernel_status_changed.emit()

    def run_blocks_thread(
        self,
        kernel: ExecutionKernel,
        start_step_id: int,
        stop_after_step_id: Optional[int] = None,
    ) -> None:
        """블럭 기반 실행을 백그라운드 스레드에서 실행.

        stop_after_step_id 가 None 이 아니면 그 step 까지만 실행 (단독 실행 모드).
        """
        import asyncio

        mw = self.mw

        def on_step_start(step_id):
            mw.signals.block_step_started.emit(step_id)
            mw.signals.log_message.emit(f"▶ 블럭 스텝 #{step_id} 실행 중...")

        def on_step_complete(step_id, result):
            mw.signals.block_step_done.emit(
                {
                    "step_id": step_id,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                }
            )

        def on_error(step_id, error_msg):
            mw.signals.log_message.emit(f"❌ 스텝 #{step_id} 실패: {error_msg}")

        def on_log(msg):
            mw.signals.log_message.emit(msg)

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                mw.workflow_engine.execute_session_blocks(
                    session=mw.current_session,
                    kernel=kernel,
                    start_from_step_id=start_step_id,
                    stop_after_step_id=stop_after_step_id,
                    silent_replay=True,
                    on_step_start=on_step_start,
                    on_step_complete=on_step_complete,
                    on_error=on_error,
                    on_log=on_log,
                )
            )
        except Exception as e:
            mw.signals.error_occurred.emit(f"블럭 실행 오류: {e}")
        finally:
            mw.signals.log_message.emit("블럭 실행 완료")
            # signal 로 UI 복원 (Qt 가 main thread queued connection 으로 전달).
            # 이전엔 QTimer.singleShot 썼지만 어떤 케이스에서 호출 안 되는 회귀 발견됨.
            mw.signals.blocks_finished.emit()

    def on_blocks_finished(self) -> None:
        """블럭 실행 완료 후 UI 복원 (signals.blocks_finished slot).

        모든 step 완료 시 자동으로 stop 버튼 비활성화 + run 버튼 활성화 보장.
        CodeViewer.set_running(False) 는 양쪽 탭 (코드 뷰 + 블럭 뷰) 의 run/stop 버튼
        + 카드 별 run_btn 까지 일괄 처리. 시각 갱신 보장 위해 update() 명시 호출.
        """
        mw = self.mw
        mw.console_panel.log("✅ 블럭 실행 완료 - UI 복원", "INFO")
        mw.code_viewer.set_running(False)
        # 시각 갱신 강제 — 일부 케이스에서 Qt 가 즉시 repaint 안 하는 회귀 방지
        mw.code_viewer.update()
        mw.statusBar().showMessage("블럭 실행 완료")
        self.on_kernel_status_changed()
        self.restore_main_window()

    def restore_main_window(self) -> None:
        """lower() 로 z-order 최하단에 있던 메인 윈도우를 다시 위로 + active.

        lower() 후 raise_/activateWindow 패턴 — 메인 윈도우는 항상 visible
        상태였으므로 hide/show cycle 의 OS-side 이슈 (작업표시줄 사라짐 등) 없음.
        멱등 — 이미 위에 있는 상태에서 호출해도 무해.
        """
        mw = self.mw
        mw.raise_()
        mw.activateWindow()
        # 만약 hide 상태였다면 (이전 버전 호환) show 도 호출
        if mw.isHidden():
            mw.show()

    def on_block_step_started(self, step_id: int) -> None:
        """블럭 스텝 시작 — UI 상태 표시"""
        self.mw.code_viewer.update_block_step_status(step_id, "🔄")

    def on_block_step_done(self, data: dict) -> None:
        """블럭 스텝 완료 — UI 상태 갱신 및 콘솔 출력"""
        mw = self.mw
        step_id = data.get("step_id", 0)
        success = data.get("success", False)
        output = data.get("output", "")
        error = data.get("error", "")
        duration = data.get("duration_ms", 0)

        status = "✅" if success else "❌"
        mw.code_viewer.update_block_step_status(step_id, status)

        if success:
            mw.console_panel.log(f"✅ 블럭 Step #{step_id} 완료 ({duration}ms)", "SUCCESS")
            if output:
                mw.console_panel.log(f"  출력: {output[:300]}", "INFO")
        else:
            mw.console_panel.log(f"❌ 블럭 Step #{step_id} 실패 ({duration}ms)", "ERROR")
            if error:
                for line in error.splitlines():
                    if line.strip():
                        mw.console_panel.log(f"  {line}", "ERROR")

        self.on_kernel_status_changed()

    def on_kernel_status_changed(self) -> None:
        """커널 상태를 블럭 뷰 UI에 반영"""
        mw = self.mw
        if not mw.current_session:
            mw.code_viewer.update_kernel_status(False, [])
            return
        sid = mw.current_session.session_id
        kernel = mw._kernels.get(sid)
        if kernel and kernel.is_alive:
            mw.code_viewer.update_kernel_status(True, kernel.executed_steps)
        else:
            mw.code_viewer.update_kernel_status(False, [])

    def stop_session_kernels(self) -> None:
        """현재 세션의 커널을 정지합니다 (세션 전환 시 호출)."""
        mw = self.mw
        if not mw.current_session:
            return
        sid = mw.current_session.session_id
        if sid in mw._kernels:
            mw._kernels[sid].stop()
            del mw._kernels[sid]

    def get_valid_python_exe(self) -> str:
        """유효한 Python 실행 경로 반환 (실행 가능 여부 검증)"""
        # 1. 프로젝트 venv 확인
        venv_python = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            try:
                # 실제로 실행 가능한지 테스트
                result = subprocess.run(
                    [str(venv_python), "--version"], capture_output=True, timeout=5
                )
                if result.returncode == 0:
                    return str(venv_python)
            except Exception:
                pass  # 실행 불가 - 다음 옵션으로

        # 2. 환경 스캐너에서 저장된 Python 경로 확인
        try:
            from core.environment_scanner import get_scanner

            scanner = get_scanner()
            saved_env = scanner.load_saved_environment()
            if saved_env:
                python_path = saved_env.get("python_path")
                if python_path and os.path.exists(python_path):
                    try:
                        result = subprocess.run(
                            [python_path, "--version"], capture_output=True, timeout=5
                        )
                        if result.returncode == 0:
                            return python_path
                    except Exception:
                        pass
        except Exception:
            pass

        # 3. 기본 Python (현재 실행 중인 Python)
        return sys.executable

    def on_stop_code(self) -> None:
        """코드 실행 강제 중지 (F9 단축키 또는 중지 버튼).

        세 가지 실행 path 모두 stop:
        - 코드 뷰어 탭 ▶ 실행: CodeSandbox 서브프로세스 → stop()
        - 블럭 뷰 탭 (▶ 처음부터 / ⏯ 단독): WorkflowEngine.stop() + Kernel.stop()
        """
        mw = self.mw
        # 1. CodeSandbox 서브프로세스 즉시 kill (코드 뷰어 탭 path)
        if mw._current_sandbox is not None:
            mw._current_sandbox.stop()
        # 2. 워크플로우 엔진 중지 플래그 설정 (블럭 뷰 path - 다음 step 시작 안 함)
        mw.workflow_engine.stop()
        # 3. 현재 세션의 ExecutionKernel 도 stop (블럭 뷰 path - 진행 중 step 즉시 종료)
        if mw.current_session:
            sid = mw.current_session.session_id
            kernel = mw._kernels.get(sid)
            if kernel is not None:
                try:
                    kernel.stop()
                except Exception as e:
                    logger.warning(f"kernel.stop() 실패: {e}")
                # kernel 재시작 가능하도록 dict 에서 제거
                mw._kernels.pop(sid, None)
        # 4. UI 상태 복원
        mw.is_processing = False
        mw.chat_panel.set_input_enabled(True)
        mw.code_viewer.set_running(False)  # run_btn 활성, stop_btn 비활성
        mw.statusBar().showMessage("⛔ 실행 강제 중지 (F9)")
        mw.console_panel.log("⛔ 실행 강제 중지 (F9)", "WARNING")
        self.on_kernel_status_changed()
        # 메인 윈도우 즉시 복원 (멱등 — thread finally 가 또 호출해도 무해)
        self.restore_main_window()
