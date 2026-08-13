# SPDX-License-Identifier: AGPL-3.0-or-later
"""
워크플로우 실행 엔진

세션의 스텝 코드를 순차적으로 실행하는 엔진입니다.
코드 샌드박스를 통해 안전하게 실행하며, 에러 처리와 재시도를 지원합니다.
"""

import ctypes
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# 비주얼 오버레이 스크립트 경로
_OVERLAY_SCRIPT = Path(__file__).parent / "visual_overlay.py"

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """단일 스텝 실행 결과"""

    step_id: int = 0
    success: bool = False
    output: str = ""
    error: Optional[str] = None
    duration_ms: int = 0
    error_screenshot: Optional[str] = None


@dataclass
class ExecutionReport:
    """전체 워크플로우 실행 리포트"""

    session_id: str = ""
    total_steps: int = 0
    executed_steps: int = 0
    successful_steps: int = 0
    failed_steps: int = 0
    total_time_ms: int = 0
    step_results: list = field(default_factory=list)


class CodeSandbox:
    """
    생성된 코드를 안전하게 실행하는 샌드박스.

    별도 프로세스(subprocess)에서 코드를 실행하여:
    - 메인 프로세스와 격리
    - stdout/stderr 캡처
    - 타임아웃 설정 가능
    """

    def __init__(self, python_exe: Optional[str] = None, timeout: int = 60):
        """
        Args:
            python_exe: Python 인터프리터 경로. None이면 현재 실행 중인 Python 사용
            timeout: 실행 타임아웃 (초)
        """
        self.python_exe = python_exe or sys.executable
        self.timeout = timeout
        self._current_proc: Optional[subprocess.Popen] = None  # 강제 중지용 프로세스 핸들

        # Python 표준 라이브러리 목록 (설치 불필요)
        self._stdlib = {
            "os",
            "sys",
            "time",
            "json",
            "pathlib",
            "subprocess",
            "re",
            "datetime",
            "collections",
            "functools",
            "itertools",
            "typing",
            "dataclasses",
            "abc",
            "io",
            "logging",
            "shutil",
            "tempfile",
            "threading",
            "queue",
            "uuid",
            "hashlib",
            "base64",
            "glob",
            "math",
            "random",
            "string",
            "traceback",
            "copy",
            "enum",
            "csv",
            "sqlite3",
            "http",
            "urllib",
            "email",
            "html",
            "xml",
            "ctypes",
            "struct",
            "socket",
            "ssl",
            "asyncio",
            "multiprocessing",
            "concurrent",
            "contextlib",
            "inspect",
            "unittest",
            "pprint",
            "textwrap",
            "warnings",
            "signal",
            "platform",
            "getpass",
            "configparser",
            "argparse",
            "pickle",
            "shelve",
            "zipfile",
            "tarfile",
            "gzip",
            "bz2",
            "lzma",
            "webbrowser",
            "tkinter",
            "codecs",
        }

        # 내부 모듈명 -> pip 설치 패키지명 매핑
        self._pip_name_map = {
            "cv2": "opencv-python",
            "PIL": "Pillow",
            "pil": "Pillow",
            "bs4": "beautifulsoup4",
            "yaml": "PyYAML",
            "sklearn": "scikit-learn",
            "dotenv": "python-dotenv",
            "win32com": "pywin32",
            "win32api": "pywin32",
            "win32gui": "pywin32",
            "pythoncom": "pywin32",
            "uiautomation": "uiautomation",
            "webdriver_manager": "webdriver-manager",
            "playwright": "playwright",
        }

    def _install_missing_packages(self, code: str) -> Optional[str]:
        """
        코드에서 사용된 패키지를 추출하여 설치되지 않은 패키지를 찾아 자동으로 설치합니다.

        Returns:
            설치 로그 메시지 (설치된 경우), 패키지가 모두 있거나 실패하면 None 또는 에러 메시지
        """
        # 1. 코드에서 import 모듈 추출
        imports = set()
        for match in re.finditer(r"^(?:import|from)\s+([a-zA-Z0-9_]+)", code, re.MULTILINE):
            pkg_name = match.group(1).lower()
            if pkg_name not in self._stdlib:
                imports.add(pkg_name)

        if not imports:
            return None

        # 2. 필요한 패키지의 pip 설치 이름 매핑
        required_packages = {self._pip_name_map.get(pkg, pkg) for pkg in imports}
        missing_packages = []

        # 3. 설치 여부 확인
        # pkg_resources를 이용해 확인 (경량화된 방법)
        try:
            import pkg_resources

            installed_packages = {pkg.key for pkg in pkg_resources.working_set}

            for pkg in required_packages:
                # 패키지 이름은 소문자로 비교 (-와 _ 혼용 주의)
                canonical_pkg = pkg.lower().replace("_", "-")
                if not any(inst.replace("_", "-") == canonical_pkg for inst in installed_packages):
                    missing_packages.append(pkg)
        except ImportError:
            # pkg_resources를 사용할 수 없는 경우 모두 설치 시도
            missing_packages = list(required_packages)

        # 4. 누락된 패키지 설치
        if missing_packages:
            log_msgs = [f"누락된 패키지를 발견했습니다: {', '.join(missing_packages)}"]
            log_msgs.append("자동 설치를 시작합니다...")
            print("\n".join(log_msgs))  # 터미널 즉시 출력
            logger.info("누락된 패키지 설치 시도: %s", missing_packages)

            try:
                # pip install 실행
                result = subprocess.run(
                    [self.python_exe, "-m", "pip", "install", *missing_packages],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

                if result.returncode == 0:
                    success_msg = f"패키지 설치 성공: {', '.join(missing_packages)}"
                    print(success_msg)
                    logger.info(success_msg)

                    # Playwright의 경우 브라우저 바이너리 설치가 추가로 필요할 수 있음
                    if "playwright" in missing_packages:
                        print("Playwright 브라우저 의존성 설치 중...")
                        subprocess.run(
                            [self.python_exe, "-m", "playwright", "install", "chromium"],
                            capture_output=True,
                        )

                    return "\n".join(log_msgs) + "\n" + success_msg
                else:
                    error_msg = f"패키지 설치 실패:\n{result.stderr}"
                    print(error_msg)
                    logger.error(error_msg)
                    return error_msg
            except Exception as e:
                error_msg = f"패키지 설치 중 오류 발생: {e}"
                print(error_msg)
                logger.error(error_msg)
                return error_msg

        return None

    @staticmethod
    def _is_self_elevated() -> bool:
        """현재 프로세스가 관리자 권한으로 실행 중인지 확인"""
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        except Exception:
            return False

    def execute(
        self,
        code: str,
        cwd: Optional[str] = None,
        pre_exec_callback: Optional[Callable] = None,
        post_exec_callback: Optional[Callable] = None,
    ) -> StepResult:
        """
        코드를 별도 프로세스에서 실행합니다.

        Args:
            code: 실행할 Python 코드 문자열
            cwd: 작업 디렉터리
            pre_exec_callback: 실행 직전 호출 (UI 창 최소화 등)
            post_exec_callback: 실행 완료 후 호출 (UI 창 복원 등)

        Returns:
            StepResult
        """
        start_time = time.time()

        # 스크립트 실행 전 패키지 자동 설치
        install_log = self._install_missing_packages(code)
        if install_log:
            # 설치 로그를 확인할 수 있도록 약간 대기
            time.sleep(1)

        # 실행 전 콜백 (예: RPA 창 최소화)
        if pre_exec_callback:
            try:
                pre_exec_callback()
                time.sleep(0.8)  # 창 최소화 애니메이션 완료 대기
            except Exception:
                pass

        # 코드를 임시 파일로 저장
        script_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8", dir=cwd
            ) as f:
                f.write(code)
                script_file = f.name

            # 별도 프로세스에서 실행 (한글 깨짐 방지를 위해 PYTHONIOENCODING 지정)
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

            # Popen으로 실행 — F9 강제 중지 시 proc.kill() 호출 가능
            self._current_proc = subprocess.Popen(
                [self.python_exe, "-u", script_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                env=env,
            )
            timed_out = False
            try:
                stdout, stderr = self._current_proc.communicate(timeout=self.timeout)
                returncode = self._current_proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                self._current_proc.kill()
                stdout, stderr = self._current_proc.communicate()
                returncode = -1
            finally:
                self._current_proc = None

            elapsed_ms = int((time.time() - start_time) * 1000)

            # 타임아웃 (communicate 시간 초과)
            if timed_out:
                return StepResult(
                    success=False,
                    error=f"실행 시간 초과 ({self.timeout}초)",
                    duration_ms=elapsed_ms,
                )

            # 사용자가 F9로 강제 중지한 경우 (returncode < 0)
            if returncode < 0:
                return StepResult(
                    success=False,
                    error="⛔ 사용자에 의해 실행이 강제 중지되었습니다 (F9)",
                    duration_ms=elapsed_ms,
                )

            # 최종 출력물 구성 (설치 로그가 있다면 앞에 붙임)
            final_output = stdout.strip()
            if install_log and returncode == 0:
                final_output = f"[{install_log}]\n\n{final_output}"

            if returncode == 0:
                return StepResult(success=True, output=final_output.strip(), duration_ms=elapsed_ms)
            else:
                error_msg = stderr.strip() or stdout.strip()
                return StepResult(
                    success=False, output=stdout.strip(), error=error_msg, duration_ms=elapsed_ms
                )

        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return StepResult(
                success=False, error=f"실행 시간 초과 ({self.timeout}초)", duration_ms=elapsed_ms
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return StepResult(success=False, error=f"실행 오류: {str(e)}", duration_ms=elapsed_ms)

        finally:
            if script_file:
                try:
                    Path(script_file).unlink(missing_ok=True)
                except OSError:
                    pass
            # 실행 후 콜백 (예: RPA 창 복원)
            if post_exec_callback:
                try:
                    post_exec_callback()
                except Exception:
                    pass

        # 정적 분석기용 fallback (실제로는 도달하지 않음)
        return StepResult(success=False, error="알 수 없는 실행 오류")

    def stop(self):
        """현재 실행 중인 서브프로세스를 강제 종료합니다 (F9 단축키)."""
        proc = self._current_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
                logger.info("CodeSandbox: 서브프로세스 강제 종료 (kill)")
            except Exception as e:
                logger.warning(f"CodeSandbox: 프로세스 종료 실패: {e}")


class WorkflowEngine:
    """
    워크플로우 실행 엔진.

    세션의 스텝 리스트를 순차적으로 실행합니다.
    실행 중 일시정지, 재개, 중지가 가능합니다.
    """

    def __init__(
        self,
        sandbox: Optional[CodeSandbox] = None,
        step_delay_ms: int = 500,
        max_retries: int = 3,
        screenshot_on_error: bool = True,
        visual_feedback_enabled: bool = True,
    ):
        """
        Args:
            sandbox: 코드 실행 샌드박스. None이면 기본 생성
            step_delay_ms: 스텝 간 대기 시간 (밀리초)
            max_retries: 실패 시 최대 재시도 횟수
            screenshot_on_error: 에러 발생 시 스크린샷 자동 저장 여부
            visual_feedback_enabled: 실행 중 마우스/키보드 시각 효과 오버레이 표시 여부
        """
        self.sandbox = sandbox or CodeSandbox()
        self.step_delay_ms = step_delay_ms
        self.max_retries = max_retries
        self.screenshot_on_error = screenshot_on_error
        self.visual_feedback_enabled = visual_feedback_enabled

        self.is_running = False
        self.is_paused = False
        self.should_stop = False
        self.current_step_index = 0
        self._overlay_proc: Optional[subprocess.Popen] = None

    async def execute_session(
        self,
        session,
        start_from: int = 0,
        on_step_start: Optional[Callable] = None,
        on_step_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_log: Optional[Callable] = None,
    ) -> ExecutionReport:
        """
        세션의 모든 스텝을 순차 실행합니다.

        Args:
            session: Session 객체
            start_from: 시작 스텝 인덱스 (0-based)
            on_step_start: 스텝 시작 콜백 (step_id)
            on_step_complete: 스텝 완료 콜백 (step_id, StepResult)
            on_error: 에러 발생 콜백 (step_id, error_msg)
            on_log: 로그 콜백 (message)

        Returns:
            ExecutionReport
        """
        self.is_running = True
        self.is_paused = False
        self.should_stop = False

        # 비주얼 피드백 오버레이 시작
        if self.visual_feedback_enabled:
            self._start_overlay()

        report = ExecutionReport(session_id=session.session_id, total_steps=len(session.steps))

        start_time = time.time()

        steps = session.steps[start_from:]
        self.current_step_index = start_from

        for i, step_data in enumerate(steps):
            if self.should_stop:
                if on_log:
                    on_log("워크플로우 실행이 중지되었습니다.")
                break

            # 일시정지 대기
            while self.is_paused:
                await self._async_sleep(0.1)
                if self.should_stop:
                    break

            step = step_data if isinstance(step_data, dict) else {}
            step_id = step.get("step_id", i + 1)
            code = step.get("generated_code", "")

            if not code.strip():
                if on_log:
                    on_log(f"스텝 #{step_id}: 실행할 코드 없음, 건너뜀")
                continue

            # 스텝 시작 알림
            if on_step_start:
                on_step_start(step_id)
            if on_log:
                on_log(f"스텝 #{step_id} 실행 시작...")

            # 실행
            result = self.sandbox.execute(code)
            result.step_id = step_id
            report.executed_steps += 1

            if result.success:
                report.successful_steps += 1
                if on_log:
                    on_log(f"스텝 #{step_id} 완료 ({result.duration_ms}ms)")
                    if result.output:
                        on_log(f"  출력: {result.output[:200]}")
            else:
                report.failed_steps += 1
                if on_error:
                    on_error(step_id, result.error)
                if on_log:
                    on_log(f"스텝 #{step_id} 실행 완료: 실패")
                    # 에러 전체 내용을 줄별로 분리해서 출력 (traceback 전체 표시)
                    if result.error:
                        on_log("─" * 50)
                        for line in result.error.splitlines():
                            if line.strip():
                                on_log(f"  {line}")
                        on_log("─" * 50)

                # 에러 시 스크린샷 캡처
                if self.screenshot_on_error:
                    screenshot_path = self._capture_error_screen(session.session_id, step_id)
                    result.error_screenshot = screenshot_path

            # 스텝 완료 알림
            if on_step_complete:
                on_step_complete(step_id, result)

            report.step_results.append(result)
            self.current_step_index = start_from + i + 1

            # 스텝 간 딜레이
            if self.step_delay_ms > 0 and i < len(steps) - 1:
                await self._async_sleep(self.step_delay_ms / 1000.0)

        report.total_time_ms = int((time.time() - start_time) * 1000)
        self.is_running = False

        # 비주얼 피드백 오버레이 종료
        self._stop_overlay()

        if on_log:
            on_log(
                f"워크플로우 완료: {report.successful_steps}/{report.executed_steps} "
                f"성공 ({report.total_time_ms}ms)"
            )

        return report

    async def execute_single_step(self, code: str, cwd: Optional[str] = None) -> StepResult:
        """단일 코드를 실행합니다."""
        if self.visual_feedback_enabled:
            self._start_overlay()
        try:
            return self.sandbox.execute(code, cwd)
        finally:
            self._stop_overlay()

    # ── 비주얼 피드백 오버레이 ───────────────────────────────────────────────────

    def _start_overlay(self) -> None:
        """비주얼 피드백 오버레이 프로세스를 시작합니다."""
        if not _OVERLAY_SCRIPT.exists():
            logger.warning("visual_overlay.py 를 찾을 수 없습니다. 오버레이를 건너뜁니다.")
            return
        if self._overlay_proc and self._overlay_proc.poll() is None:
            return  # 이미 실행 중

        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self._overlay_proc = subprocess.Popen(
                [sys.executable, str(_OVERLAY_SCRIPT)],
                creationflags=flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # 오버레이 창이 뜰 시간을 확보
            time.sleep(0.4)
            logger.info("비주얼 피드백 오버레이 시작 (PID=%s)", self._overlay_proc.pid)
        except Exception as exc:
            logger.warning("비주얼 피드백 오버레이 시작 실패: %s", exc)
            self._overlay_proc = None

    def _stop_overlay(self) -> None:
        """비주얼 피드백 오버레이 프로세스를 종료합니다."""
        proc = self._overlay_proc
        if proc is None:
            return
        self._overlay_proc = None
        if proc.poll() is not None:
            return  # 이미 종료됨
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        logger.info("비주얼 피드백 오버레이 종료")

    # ────────────────────────────────────────────────────────────────────────────

    def pause(self):
        """실행을 일시정지합니다."""
        self.is_paused = True
        logger.info("워크플로우 일시정지")

    def resume(self):
        """일시정지된 실행을 재개합니다."""
        self.is_paused = False
        logger.info("워크플로우 재개")

    def stop(self):
        """실행을 중지합니다."""
        self.should_stop = True
        self.is_paused = False
        logger.info("워크플로우 중지 요청")

    def _capture_error_screen(self, session_id: str, step_id: int) -> Optional[str]:
        """에러 발생 시 스크린샷을 캡처합니다."""
        try:
            import mss
            from PIL import Image

            captures_dir = (
                Path(__file__).parent.parent / "data" / "sessions" / session_id / "captures"
            )
            captures_dir.mkdir(parents=True, exist_ok=True)

            with mss.mss() as sct:
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                filename = f"error_step{step_id}_{int(time.time())}.png"
                filepath = captures_dir / filename
                img.save(str(filepath))
                logger.info(f"에러 스크린샷 저장: {filepath}")
                return str(filepath)

        except Exception as e:
            logger.warning(f"에러 스크린샷 캡처 실패: {e}")
            return None

    @staticmethod
    async def _async_sleep(seconds: float):
        """비동기 sleep (asyncio 호환)"""
        import asyncio

        await asyncio.sleep(seconds)

    # ── 블럭 기반 실행 (Colab-style) ─────────────────────────────────────────

    async def execute_session_blocks(
        self,
        session,
        kernel,
        start_from_step_id: int = 1,
        stop_after_step_id: Optional[int] = None,
        silent_replay: bool = True,
        on_step_start: Optional[Callable] = None,
        on_step_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_log: Optional[Callable] = None,
    ) -> "ExecutionReport":
        """
        블럭 기반 실행 모드 (Colab-style).

        ExecutionKernel을 사용하여 각 스텝의 델타 코드만 순차 실행합니다.
        커널이 살아있는 한 변수 상태(driver, app 등)가 유지됩니다.

        Args:
            session: Session 객체
            kernel: ExecutionKernel 인스턴스 (이미 start() 호출된 상태)
            start_from_step_id: 이 스텝 ID부터 실행 (이전 스텝은 silent replay)
            stop_after_step_id: 지정 시 이 스텝까지만 실행하고 종료 (단독 실행 모드).
                start_from == stop_after 면 정확히 그 step 한 개만 실행.
                None 이면 끝까지 실행 (기본 동작).
            silent_replay: True이면 start_from 이전 스텝을 조용히 재실행
            on_step_start: 스텝 시작 콜백 (step_id)
            on_step_complete: 스텝 완료 콜백 (step_id, StepResult)
            on_error: 에러 콜백 (step_id, error_msg)
            on_log: 로그 콜백 (message)
        """
        from .execution_kernel import LIBRARY_BLOCK_STEP_ID

        self.is_running = True
        self.is_paused = False
        self.should_stop = False

        report = ExecutionReport(session_id=session.session_id, total_steps=len(session.steps))
        start_time = time.time()

        # ── 라이브러리 블럭 실행 (커널 미초기화 OR 라이브러리 코드 변경 시) ──
        # 사용자 보고 (5/5): step 1 시점 cached library 가 step 2 의 helper 함수
        # (find_and_click) 누락 → NameError. library_hash 로 변경 감지 → 재실행.
        import hashlib as _hashlib

        lib_block = extract_library_block(session)
        new_lib_hash = (
            _hashlib.md5(lib_block.encode("utf-8")).hexdigest() if lib_block.strip() else None
        )
        prev_lib_hash = getattr(kernel, "library_hash", None)
        lib_needs_run = (
            LIBRARY_BLOCK_STEP_ID not in kernel.executed_steps or prev_lib_hash != new_lib_hash
        )
        if lib_needs_run and lib_block.strip():
            if on_log:
                changed = (
                    "변경 감지"
                    if (prev_lib_hash is not None and prev_lib_hash != new_lib_hash)
                    else "초기화"
                )
                on_log(f"📦 라이브러리 블럭 {changed} 중...")
            # AI 환각 import (예: FindBestMatchException) 자동 교정 후 idempotent 가드.
            # 환각 import 가 라이브러리 블럭에서 ImportError 로 죽으면 후속 import 도 skip
            # → 모든 step cascade fail (사용자 보고 5/5 wooyang 세션).
            lib_result = kernel.execute_block(
                make_browser_init_idempotent(fix_hallucinated_imports(lib_block)),
                step_id=LIBRARY_BLOCK_STEP_ID,
                timeout=30,
            )
            if not lib_result.success:
                if on_log:
                    on_log(f"⚠️ 라이브러리 블럭 실행 오류: {lib_result.error}")
            else:
                # hash 갱신 (다음 호출에서 같으면 skip)
                try:
                    kernel.library_hash = new_lib_hash
                except Exception:
                    pass

        # ── 스텝 실행 루프 ──
        prev_step_dict: dict | None = None
        for step_data in session.steps:
            if self.should_stop:
                if on_log:
                    on_log("워크플로우 실행이 중지되었습니다.")
                break

            while self.is_paused:
                await self._async_sleep(0.1)
                if self.should_stop:
                    break

            step = step_data if isinstance(step_data, dict) else {}
            step_id = step.get("step_id", 0)
            # prev_step 전달 — 저장된 step_code 가 누적이라도 generated_code diff 로 재계산
            delta_code = extract_step_delta_code(step, prev_step_dict)
            # AI 환각 심볼 (예: FindBestMatchException) 자동 교정 — except 절에서 NameError
            # cascade 회귀 방지. 라이브러리 블럭과 동일한 매핑 적용.
            delta_code = fix_hallucinated_imports(delta_code)
            # 같은 step 또는 silent replay 가 여러 번 일어나도 새 브라우저가 추가로 뜨지
            # 않도록 driver 초기화 코드를 idempotent 가드로 감쌈 (5/5 회귀 fix).
            delta_code = make_browser_init_idempotent(delta_code)
            # SW_RESTORE 가 maximized 창을 normal 로 축소시켜 직전 element 좌표가
            # 무효화되는 회귀 (5/5 사용자 보고: ID 입력 안 됨, "전체창이 축소됨") 방지.
            delta_code = make_show_window_safe(delta_code)

            if not delta_code.strip():
                # empty step 은 prev_step_dict 갱신 없이 skip — 다음 step 의 diff 가 깨지지 않게
                # (5/5 회귀: AI 가 응답 실패로 generated_code="" 인 step 이 끼어 있으면
                # 다음 step 의 marker 누락 시 prev_body="" 로 delta 계산 → 전체 cumulative
                # 실행 → driver.get/maximize 중복 → 새로고침 반복).
                if on_log:
                    on_log(f"스텝 #{step_id}: 실행할 코드 없음, 건너뜀")
                continue
            prev_step_dict = step

            is_silent = (step_id < start_from_step_id) and silent_replay
            already_done = step_id in kernel.executed_steps

            # start_from 이전이면서 커널에 이미 있으면 건너뜀
            if step_id < start_from_step_id and already_done:
                continue

            # start_from 이전이면서 커널에 없으면 silent replay
            if is_silent:
                if on_log:
                    on_log(f"⏩ 스텝 #{step_id} silent replay...")
                kernel.execute_block(delta_code, step_id=step_id, silent=True)
                continue

            # 정상 실행
            if on_step_start:
                on_step_start(step_id)
            if on_log:
                on_log(f"스텝 #{step_id} 실행 시작...")

            result = kernel.execute_block(delta_code, step_id=step_id)
            result.step_id = step_id
            report.executed_steps += 1

            # 실행 결과를 step.status 에 반영 (devloop #6). 이후 app_service.run_blocks
            # 가 session.json 에 영속화 → UI 배지/외부 폴링이 실제 실행 결과를 본다.
            # 이전엔 status 가 'pending' 으로 고착(엔진이 status 미기록 + onDone refetch).
            if isinstance(step_data, dict):
                step_data["status"] = "completed" if result.success else "failed"

            if result.success:
                report.successful_steps += 1
                if on_log:
                    on_log(f"스텝 #{step_id} 완료 ({result.duration_ms}ms)")
                    if result.output:
                        on_log(f"  출력: {result.output[:300]}")
            else:
                report.failed_steps += 1
                if on_error:
                    on_error(step_id, result.error)
                if on_log:
                    on_log(f"스텝 #{step_id} 실패")
                    if result.error:
                        on_log("─" * 50)
                        for line in result.error.splitlines():
                            if line.strip():
                                on_log(f"  {line}")
                        on_log("─" * 50)

            if on_step_complete:
                on_step_complete(step_id, result)
            report.step_results.append(result)

            # 단독 실행 모드 — stop_after 도달 시 종료 (다음 step 안 함)
            if stop_after_step_id is not None and step_id >= stop_after_step_id:
                if on_log:
                    on_log(f"⏹ stop_after_step_id={stop_after_step_id} 도달, 종료")
                break

            # Step 사이 대기 — 우선순위: step.wait_after_ms > session.settings.step_delay_ms
            # > self.step_delay_ms (engine 의 글로벌 default).
            # 사용자가 "1초 대기" 같은 요청을 안 해도 기본 wait 가 자동 적용됨.
            step_wait = step.get("wait_after_ms")
            if step_wait is None:
                # 세션 default (Session.settings.step_delay_ms) — None 이면 engine default
                session_default = (
                    session.settings.get("step_delay_ms") if hasattr(session, "settings") else None
                )
                step_wait = session_default if session_default is not None else self.step_delay_ms
            if step_wait > 0:
                if on_log and step.get("wait_after_ms") is not None:
                    on_log(f"⏱ Step {step_id} 후 {step_wait}ms 대기 (개별 설정)")
                await self._async_sleep(step_wait / 1000.0)

        report.total_time_ms = int((time.time() - start_time) * 1000)
        self.is_running = False

        if on_log:
            on_log(
                f"블럭 실행 완료: {report.successful_steps}/{report.executed_steps} "
                f"성공 ({report.total_time_ms}ms)"
            )
        return report


# ── 블럭 추출 헬퍼 함수 ────────────────────────────────────────────────────────


def extract_library_block(session) -> str:
    """
    세션의 마지막 스텝 generated_code에서 라이브러리 블럭을 추출합니다.

    라이브러리 블럭 = '# === Step 1:' 마커 이전의 모든 코드
    (imports + DPI 설정 + 헬퍼 함수 등)

    G5 (5/9): AI 가 step_imports 에 핵심 패키지 (pyautogui / pyperclip / ctypes /
    time / subprocess) 누락 시 step 본문 안에서 NameError. extract 후 누락된
    핵심 import 를 자동 prepend — 모든 step 이 step_imports 비어있어도 사용 가능.
    """
    if not session.steps:
        return ""
    last_step = session.steps[-1]
    code = last_step.get("generated_code", "") if isinstance(last_step, dict) else ""
    if not code:
        block = ""
    else:
        match = re.search(r"^# === Step 1:", code, re.MULTILINE)
        if match:
            block = code[: match.start()].strip()
        else:
            # Step 1 마커가 없으면 imports 라인만 추출
            import_lines = [
                ln for ln in code.splitlines() if ln.startswith("import ") or ln.startswith("from ")
            ]
            block = "\n".join(import_lines)

    # 멀티스텝/혼용 세션 import 집계 (devloop): 각 step 이 자기 import 를 따로 선언하면
    # delta 추출 시 import 가 제거되고(extract_step_delta_code), 위 block 은 마지막 step
    # 만 보므로 중간 step 고유 import (예: 엑셀 pywinauto, 브라우저 selenium Options/webdriver)
    # 가 유실 → 후속 step NameError. 모든 step 의 import 라인을 union 해 보강한다.
    # (markers 누적코드 세션은 last_step 에 전 import 가 모여 있어 dedupe 로 무해.)
    existing = {ln.strip() for ln in block.splitlines() if ln.strip()}
    extra_imports: list[str] = []
    for st in session.steps:
        gen = st.get("generated_code", "") if isinstance(st, dict) else ""
        for ln in gen.splitlines():
            s = ln.strip()
            if (s.startswith("import ") or s.startswith("from ")) and s not in existing:
                existing.add(s)
                extra_imports.append(s)
    if extra_imports:
        joined = "\n".join(extra_imports)
        block = (joined + "\n" + block).strip() if block else joined

    # 핵심 import prepend 후, IME 호환 shim 을 그 뒤에 주입(헬퍼/래핑은 import 이후 정의돼야 함).
    result = _ensure_essential_imports(block)
    return result + "\n" + _IME_COMPAT_SHIM.strip() if result else _IME_COMPAT_SHIM.strip()


# G5: 모든 step 이 사용할 수 있어야 하는 핵심 패키지. AI 가 누락해도 library
# 블럭에서 미리 import 되어 step 본문 안에서 NameError 회피. 5/9 회귀:
# DeepSeek 가 step_code 안에 pyautogui.click 호출 + step_imports [] → NameError.
# G2.5 (5/9): ctypes.wintypes + pywinauto.Application 추가 — element_context
# 코드 템플릿에서 import 라인 제거 후 누락 회피.
_ESSENTIAL_LIBRARY_IMPORTS = (
    "import time",
    "import os",
    "import subprocess",
    "import ctypes",
    "import ctypes.wintypes",
    "import pyautogui",
    "import pyperclip",
    "from pywinauto import Application",
)


# IME 호환 shim (devloop 실측, 2026-06-05 / 사용자 실측 §80, 2026-08-13): 한국어 등 IME
# 환경에서 Ctrl+Shift 는 IME 언어전환 단축키라 `pyautogui.hotkey('ctrl','shift','s')`
# (다른 이름으로 저장) 등 modifier 조합이 IME 에 흡수되어 앱에 닿지 않는다(스크린샷으로
# 확인 — 영문 강제 시 정상 동작). 라이브러리 블럭에 자동 주입:
# - force_english_ime(): 대상 창을 영문 입력으로 강제하되 **원래 레이아웃/IME 모드를 저장**
# - restore_user_ime(): 저장된 상태 복원(+우리가 새로 로드한 US 레이아웃은 언로드)
# - hotkey/write 래핑: 자동화 입력 직전 영문 강제 + **디바운스 자동 복원**(마지막 강제 후
#   ~2.5s) — 이전 버전은 복원이 없어 실행 후 사용자의 한/영 키가 죽었다(레이아웃이 US 로
#   남아 한/영 키 무반응, Win+Space 로만 복귀 가능 — §80 사용자 실측). 비-IME 환경 무해.
_IME_COMPAT_SHIM = '''
_ohdo_ime_state = {"saved": {}, "loaded_hkl": None, "timer": None}

def _ohdo_english_hkl():
    """활성화할 영문 HKL 결정 — 이미 시스템에 있는 영문 레이아웃을 재사용하고,
    없을 때만 US 레이아웃을 새로 로드(이 경우 복원 시 언로드 대상으로 기록)."""
    import ctypes
    u = ctypes.windll.user32
    n = u.GetKeyboardLayoutList(0, None)
    if n > 0:
        buf = (ctypes.c_void_p * n)()
        u.GetKeyboardLayoutList(n, buf)
        for h in buf:
            if h and (int(h) & 0xFFFF) == 0x0409:  # LOWORD = 언어 (en-US)
                return int(h), False
    hkl = u.LoadKeyboardLayoutW("00000409", 0x00000001)  # US, KLF_ACTIVATE
    return int(hkl), True

def force_english_ime(hwnd=None):
    """foreground(또는 지정 hwnd) 창을 영문 입력으로 강제 — 원래 상태는 저장해 두고
    restore_user_ime()(자동화 입력 종료 후 자동 호출)가 복원한다.
    IME 환경에서 Ctrl+Shift 등 가속기가 언어전환에 흡수되는 문제 회피."""
    try:
        import ctypes
        import time as _t
        u = ctypes.windll.user32
        if not hwnd:
            hwnd = u.GetForegroundWindow()
        hwnd = int(hwnd or 0)
        if not hwnd:
            return
        # 원래 IME 변환 모드 저장 + 영숫자 모드 강제 (한/영 키와 동일 차원의 토글).
        conv = None
        try:
            imm = ctypes.windll.imm32
            himc = imm.ImmGetContext(hwnd)
            if himc:
                c = ctypes.c_uint(0); s = ctypes.c_uint(0)
                if imm.ImmGetConversionStatus(himc, ctypes.byref(c), ctypes.byref(s)):
                    conv = (c.value, s.value)
                imm.ImmSetConversionStatus(himc, 0, 0)  # IME_CMODE_ALPHANUMERIC
                imm.ImmReleaseContext(hwnd, himc)
        except Exception:
            pass
        tid = u.GetWindowThreadProcessId(hwnd, None)
        cur = int(u.GetKeyboardLayout(tid))
        if (cur & 0xFFFF) != 0x0409:  # 이미 영문이면 레이아웃 전환 불필요
            en, loaded = _ohdo_english_hkl()
            if loaded and _ohdo_ime_state["loaded_hkl"] is None:
                _ohdo_ime_state["loaded_hkl"] = en
            # 창별 **최초** 상태만 저장 (반복 강제가 원래 상태를 덮어쓰지 않게).
            if hwnd not in _ohdo_ime_state["saved"]:
                _ohdo_ime_state["saved"][hwnd] = (cur, conv)
            u.PostMessageW(hwnd, 0x0050, 0, en)  # WM_INPUTLANGCHANGEREQUEST
            _t.sleep(0.3)  # 언어전환 적용 대기(미적용 시 단축키가 IME 에 흡수되는 race)
        _ohdo_schedule_ime_restore()
    except Exception:
        pass

def restore_user_ime():
    """force_english_ime 가 저장해 둔 창들의 레이아웃/IME 모드를 복원하고, 우리가 새로
    로드한 US 레이아웃은 언로드 — 사용자의 한/영 키 전환 환경을 원상 복구(§80)."""
    try:
        import ctypes
        u = ctypes.windll.user32
        t = _ohdo_ime_state["timer"]
        if t is not None:
            _ohdo_ime_state["timer"] = None
            try: t.cancel()
            except Exception: pass
        saved = _ohdo_ime_state["saved"]
        _ohdo_ime_state["saved"] = {}
        for hwnd, (hkl, conv) in saved.items():
            if not u.IsWindow(hwnd):
                continue
            u.PostMessageW(hwnd, 0x0050, 0, hkl)  # 원래 레이아웃으로
            if conv is not None:
                try:
                    imm = ctypes.windll.imm32
                    himc = imm.ImmGetContext(hwnd)
                    if himc:
                        imm.ImmSetConversionStatus(himc, conv[0], conv[1])
                        imm.ImmReleaseContext(hwnd, himc)
                except Exception:
                    pass
        loaded = _ohdo_ime_state["loaded_hkl"]
        if loaded:
            _ohdo_ime_state["loaded_hkl"] = None
            try:
                u.UnloadKeyboardLayout(ctypes.c_void_p(loaded))  # 입력 언어 목록 원복
            except Exception:
                pass
    except Exception:
        pass

def _ohdo_schedule_ime_restore(delay=2.5):
    """마지막 영문 강제 후 delay 초 뒤 자동 복원 (자동화 입력 burst 동안은 디바운스)."""
    try:
        import threading
        t = _ohdo_ime_state["timer"]
        if t is not None:
            try: t.cancel()
            except Exception: pass
        nt = threading.Timer(delay, restore_user_ime)
        nt.daemon = True
        _ohdo_ime_state["timer"] = nt
        nt.start()
    except Exception:
        pass

def save_as_to_path(path):
    """'다른 이름으로 저장'(Save As)을 안정적으로 수행 — Win11 메모장 등 표준 파일 다이얼로그.

    devloop 실측(2026-06-06)으로 확정한 레시피:
    1) IME 영문 강제(한글 IME 가 Ctrl+Shift/Ctrl+S 가속기를 흡수하는 문제 회피),
    2) Ctrl+Shift+S(미저장 문서면 Ctrl+S 폴백)로 다이얼로그 오픈,
    3) 다이얼로그는 GetForegroundWindow 로 잡음(Desktop().windows() 열거는 모달을 놓침),
    4) 파일명 필드는 다이얼로그 오픈 시 **자동 포커스** → 다른 Edit 클릭 금지(잘못된 필드 입력 방지).
       Ctrl+A(기본명 선택) → 전체 경로 붙여넣기 → Enter → 덮어쓰기 확인 Enter.
    """
    import time as _t
    import ctypes as _c

    import pyautogui as _p
    import pyperclip as _pc

    _u = _c.windll.user32
    force_english_ime()  # 대상 앱(foreground)에 영문 강제
    _t.sleep(0.1)
    _before = _u.GetForegroundWindow()
    _p.hotkey("ctrl", "shift", "s")  # wrapped hotkey(=영문강제 포함) → Save As
    _t.sleep(1.5)
    _dlg = _u.GetForegroundWindow()
    if _dlg == _before:  # 안 열렸으면 미저장 문서용 Ctrl+S 폴백
        _p.hotkey("ctrl", "s")
        _t.sleep(1.5)
        _dlg = _u.GetForegroundWindow()
    # 파일명 필드 자동 포커스 — 클릭하지 않는다.
    _p.hotkey("ctrl", "a")  # 기본 파일명 전체선택
    _t.sleep(0.15)
    _pc.copy(path)
    _p.hotkey("ctrl", "v")  # 전체 경로 붙여넣기
    _t.sleep(0.3)
    _p.press("enter")  # 저장
    _t.sleep(1.2)
    _p.press("enter")  # 덮어쓰기 확인(있으면)
    _t.sleep(0.5)


try:
    import pyautogui as _ohdo_pg
    if not getattr(_ohdo_pg, "_ohdo_ime_wrapped", False):
        _ohdo_orig_hotkey = _ohdo_pg.hotkey
        def _ohdo_hotkey(*a, **k):
            _mods = {"ctrl", "alt", "shift", "win", "command", "option"}
            if any(isinstance(x, str) and x.lower() in _mods for x in a):
                force_english_ime()
            return _ohdo_orig_hotkey(*a, **k)
        _ohdo_pg.hotkey = _ohdo_hotkey
        # write/typewrite 도 래핑 — 한글 IME 상태로 ASCII 를 치면 한글이 되는 문제.
        # (이전엔 직전 hotkey 의 영문 강제에 우연히 의존 — §80 복원 도입으로 명시 보장.)
        _ohdo_orig_write = _ohdo_pg.write
        def _ohdo_write(message, *a, **k):
            try:
                if message and any(ord(ch) < 128 for ch in str(message)):
                    force_english_ime()
            except Exception:
                pass
            return _ohdo_orig_write(message, *a, **k)
        _ohdo_pg.write = _ohdo_write
        _ohdo_pg.typewrite = _ohdo_write
        _ohdo_pg._ohdo_ime_wrapped = True
except Exception:
    pass
'''


def _ensure_essential_imports(library_block: str) -> str:
    """library_block 에 핵심 패키지가 없으면 prepend."""
    missing = []
    for imp in _ESSENTIAL_LIBRARY_IMPORTS:
        # 모듈명 추출 (예: 'import pyautogui' → 'pyautogui')
        mod = imp.split()[-1]
        # 이미 'import pyautogui' 또는 'from pyautogui ...' 가 있으면 skip
        if re.search(
            rf"^\s*(?:import\s+{re.escape(mod)}\b|from\s+{re.escape(mod)}\b)",
            library_block,
            re.MULTILINE,
        ):
            continue
        missing.append(imp)
    if not missing:
        return library_block
    prefix = "\n".join(missing)
    if not library_block.strip():
        return prefix
    return prefix + "\n" + library_block


def _is_compilable(code: str) -> bool:
    """코드가 단독 module-level 로 compile 가능한지 검사."""
    if not code or not code.strip():
        return False
    try:
        compile(code, "<delta_check>", "exec")
        return True
    except SyntaxError:
        return False


def _extract_by_step_marker(code: str, step_id: int) -> str:
    """generated_code 에서 ``# === Step {step_id}: ... (시작) === ~ (끝) ===`` 사이를 추출.

    AI 가 누적 코드를 재출력할 때 이전 스텝 본문을 미세하게 변형(공백·따옴표·
    주석 위치 등) 하더라도, 새 스텝의 본문은 마커 안에 깨끗히 격리돼 있어 diff
    보다 신뢰도가 높음.

    여러 시작 마커가 있으면 마지막 시작 ~ 그 뒤 첫 끝 마커. 추출 후
    ``_smart_dedent`` + ``_unwrap_main_function`` 을 적용해 module-level 실행
    가능 형태로 정리.
    """
    if not code or not step_id:
        return ""
    start_pattern = rf"# === Step {step_id}:.*?\(시작\) ==="
    end_pattern = rf"# === Step {step_id}:.*?\(끝\) ==="
    starts = [m.end() for m in re.finditer(start_pattern, code)]
    ends = [m.start() for m in re.finditer(end_pattern, code)]
    if not starts or not ends:
        return ""
    content_start = starts[-1]
    valid_ends = [e for e in ends if e > content_start]
    if not valid_ends:
        return ""
    body = code[content_start : valid_ends[0]].strip()
    if not body:
        return ""
    from .import_manager import _smart_dedent, _unwrap_main_function

    return _smart_dedent(_unwrap_main_function(body))


def _find_paren_end(code: str, open_pos: int) -> int:
    """Given position of '(', return position AFTER matching ')'.

    Handles nested parens, single/double/triple-quoted strings, and #-comments.
    Returns ``open_pos`` (or `len(code)`) if balancing fails.
    """
    if open_pos >= len(code) or code[open_pos] != "(":
        return open_pos
    depth = 1
    i = open_pos + 1
    n = len(code)
    while i < n and depth > 0:
        ch = code[i]
        if ch == "#":
            nl = code.find("\n", i)
            i = nl if nl >= 0 else n
            continue
        if ch in ('"', "'"):
            triple = code[i : i + 3]
            if triple == ch * 3:
                end = code.find(ch * 3, i + 3)
                i = end + 3 if end >= 0 else n
            else:
                j = i + 1
                while j < n and code[j] != ch:
                    j += 2 if code[j] == "\\" else 1
                i = j + 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


_BROWSER_INIT_RE = re.compile(
    r"^(?P<indent>[ \t]*)driver\s*=\s*webdriver\."
    r"(?:Chrome|Firefox|Edge|Safari|ChromiumEdge|Remote)\b",
    re.MULTILINE,
)


def make_browser_init_idempotent(code: str) -> str:
    """``driver = webdriver.Chrome(...)`` 를 idempotent 가드로 감쌉니다.

    "전체 실행" 을 두 번 누르거나 step 1 을 silent replay 할 때마다 새 브라우저가
    추가로 뜨는 회귀 (5/5 사용자 보고: "웹브라우저가 3개가 띄워지고") 방지. 살아있는
    driver 가 있으면 재사용하고, 없거나 죽었을 때만 새로 생성.

    이미 try/except 안에 있거나 이전에 본 메서드가 한 번 감싼 코드는 다시 건드리지
    않도록 직전 구간에서 우리 마커 또는 ``driver.window_handles`` 시그니처를 검사.
    """
    if "webdriver" not in code:
        return code
    matches = list(_BROWSER_INIT_RE.finditer(code))
    if not matches:
        return code

    out: list[str] = []
    pos = 0
    for m in matches:
        indent = m.group("indent")
        start = m.start()
        open_paren = code.find("(", m.end())
        # webdriver.X 와 '(' 사이에는 공백만 허용 — 멀리 떨어졌으면 패턴 아님
        if open_paren < 0 or open_paren - m.end() > 4:
            continue
        end = _find_paren_end(code, open_paren)
        if end <= open_paren:
            continue

        # 이미 idempotent 가드 안에 있으면 건너뜀
        prefix_window = code[max(0, start - 250) : start]
        if "_idem_browser_init" in prefix_window or "driver.window_handles" in prefix_window:
            continue
        prev_lines = prefix_window.rstrip().splitlines()[-3:] if prefix_window else []
        if any(
            "try:" in pl or "'driver' not in" in pl or "'driver' in globals" in pl
            for pl in prev_lines
        ):
            continue

        original_call = code[start:end]
        wrapped = (
            f"{indent}# _idem_browser_init: 살아있는 driver 재사용 (다중 실행 방지)\n"
            f"{indent}try:\n"
            f"{indent}    _ = driver.window_handles\n"
            f"{indent}except Exception:\n"
            f"{indent}    {original_call}"
        )
        out.append(code[pos:start])
        out.append(wrapped)
        pos = end
    out.append(code[pos:])
    return "".join(out)


_SHOW_WINDOW_RESTORE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<call>(?:\w+\.)*ShowWindow)\s*\(\s*"
    r"(?P<hwnd>[\w_.]+)\s*,\s*9\s*\)\s*(?:#[^\n]*)?$",
    re.MULTILINE,
)


def make_show_window_safe(code: str) -> str:
    """``ShowWindow(hwnd, 9)`` (SW_RESTORE) 를 IsIconic 분기로 감쌉니다.

    SW_RESTORE 는 maximized 창을 normal 사이즈로 축소시킴 → 직전에 계산한 element
    좌표 무효화 → 클릭이 빈 곳으로 가는 회귀 (5/5 사용자 보고: ID 입력 안 됨,
    "전체창이 축소됨"). minimized 일 때만 SW_RESTORE, 그 외는 SW_SHOW (5) 로
    현재 사이즈 (maximized 포함) 보존.

    이미 IsIconic 분기 안에 있는 호출은 재변환하지 않음 (자기 멱등).
    """
    if "ShowWindow" not in code:
        return code
    matches = list(_SHOW_WINDOW_RESTORE_RE.finditer(code))
    if not matches:
        return code

    out: list[str] = []
    pos = 0
    for m in matches:
        indent = m.group("indent")
        call = m.group("call")
        hwnd_var = m.group("hwnd")
        start = m.start()
        end = m.end()

        # 이미 IsIconic guard 안이면 skip
        prefix = code[max(0, start - 250) : start]
        if "IsIconic" in prefix:
            iso_pos = prefix.rfind("IsIconic")
            if (len(prefix) - iso_pos) < 200:
                continue

        # ShowWindow 호출의 module prefix (예: user32.) 를 그대로 IsIconic 에 적용
        if "." in call:
            module_prefix = call.rsplit(".", 1)[0]
            isiconic = f"{module_prefix}.IsIconic"
            show_call = call
        else:
            isiconic = "user32.IsIconic"
            show_call = "user32.ShowWindow"

        wrapped = (
            f"{indent}# _safe_show: SW_RESTORE 는 maximized 창을 축소시키므로 minimized 만 복원\n"
            f"{indent}if {isiconic}({hwnd_var}):\n"
            f"{indent}    {show_call}({hwnd_var}, 9)   # SW_RESTORE\n"
            f"{indent}else:\n"
            f"{indent}    {show_call}({hwnd_var}, 5)   # SW_SHOW (maximized 보존)"
        )
        out.append(code[pos:start])
        out.append(wrapped)
        pos = end
    out.append(code[pos:])
    return "".join(out)


# 사용자 보고 (5/5, 5/6): AI 가 pywinauto 의 존재하지 않는 exception 클래스명/모듈명을 환각.
# - 5/5: 'FindBestMatchException' (실제는 'MatchError') → import 가 ImportError 로 죽음
# - 5/6: 'FindBestMatch' (단독) / 'FindBestMatch.MatchError' (점 표기) → 같은 ImportError
# import 실패 시 라이브러리 블럭 전체가 partial 실행되어 Options/Application 등 후속 import 도 skip
# → 모든 step 이 NameError cascade. 알려진 환각 → 실제 이름 매핑.
_HALLUCINATED_PYWINAUTO_NAMES = {
    "FindBestMatchException": "MatchError",
    "FindBestMatch": "MatchError",  # 5/6 환각 — 단독 / 점 표기 모두 처리 (점 표기는 아래에서 먼저)
    # 추후 다른 환각 발견 시 여기 추가
}


def fix_hallucinated_imports(code: str) -> str:
    """AI 가 만들어낸 존재하지 않는 pywinauto/selenium 심볼명을 실제 이름으로 치환.

    교정 사례:
    - `from pywinauto.findbestmatch import FindBestMatchException` → `MatchError`
    - `except FindBestMatchException as e:` → `except MatchError as e:`
    - `from pywinauto.findbestmatch import FindBestMatch` → `MatchError` (5/6)
    - `except FindBestMatch.MatchError as e:` → `except MatchError as e:` (5/6)

    self-멱등 (이미 교정된 코드는 재교정 X — 원래 이름이 사라졌으므로 매칭 안 됨).
    """
    if not code:
        return code
    out = code
    # 1단계: 점 표기 환각 우선 처리 — `FindBestMatch.MatchError` → `MatchError`
    # (`FindBestMatch` 단독 치환 전에 먼저. 안 그러면 `MatchError.MatchError` 같은 잘못된 형태 됨.)
    out = re.sub(r"\bFindBestMatch\.MatchError\b", "MatchError", out)
    # 2단계: 단독 환각 이름 → 실제 이름 (단어 경계 매칭으로 부분 일치 회피)
    for fake, real in _HALLUCINATED_PYWINAUTO_NAMES.items():
        if fake in out:
            out = re.sub(rf"\b{re.escape(fake)}\b", real, out)
    return out


def extract_step_delta_code(step: dict, prev_step: dict | None = None) -> str:
    """
    스텝의 델타 코드를 반환합니다.

    추출 우선순위 (앞 단계가 compile 검증 통과 시 즉시 반환):
    1. **마커 추출** — ``generated_code`` 의 ``# === Step N: ... (시작/끝) ===``
       사이. AI 가 이전 스텝을 미세 변형해도 안전하므로 최우선.
    2. **diff 재계산** — prev_step.generated_code vs current.generated_code 의
       line diff. 마커가 없을 때 사용.
    3. **저장된 step_code** — unwrap + dedent.
    4. **generated_code 전체** — 마지막 fallback.

    각 후보는 ``_is_compilable`` 로 syntax 검증. 검증 통과한 첫 후보를 반환.
    모두 실패하면 가장 짧은 후보를 반환 (런타임에 명확한 오류 표시).

    Args:
        step: 현재 스텝 dict
        prev_step: 직전 스텝 dict (None 이면 첫 스텝). 있으면 generated_code 들의
            diff 로 delta 재계산해 누적 step_code 도 자동 fix.
    """
    from .import_manager import (
        _smart_dedent as _sd,
    )
    from .import_manager import (
        _unwrap_main_function as _uwm,
    )
    from .import_manager import (
        extract_code_delta as _ecd,
    )
    from .import_manager import (
        extract_imports,
    )

    step_code = step.get("step_code", "").strip()
    generated_code = step.get("generated_code", "")
    step_id = step.get("step_id", 0)

    candidates: list[str] = []

    # ── 0) 사용자 수동 편집 우선 (manually_edited + step_code 있음) ──
    # 사용자가 블럭 뷰에서 직접 수정한 경우 step_code 가 진실. generated_code 의 marker
    # (1) 나 diff (2) 를 우선하면 stale 한 AI 원본이 사용되어 사용자 수정이 무시됨
    # (5/4 사용자 보고: 네이버 검색 '삼성전자' → '하이닉스' 수정 후 실행 시 '삼성전자' 그대로).
    if step.get("manually_edited") and step_code:
        normalized = _sd(_uwm(step_code))
        if normalized and _is_compilable(normalized):
            return normalized
        # compile 실패해도 사용자 의도 우선 — 런타임 오류는 사용자가 보고 수정
        if normalized:
            candidates.append(normalized)

    # ── 1) 마커 기반 추출 (최우선) ──
    if step_id and generated_code:
        marker = _extract_by_step_marker(generated_code, step_id)
        if marker:
            if _is_compilable(marker):
                return marker
            candidates.append(marker)

    # ── 2) prev_step 기반 diff 재계산 ──
    if prev_step is not None and generated_code:
        prev_generated = prev_step.get("generated_code", "") if isinstance(prev_step, dict) else ""
        if prev_generated:
            _, prev_body = extract_imports(prev_generated)
            _, curr_body = extract_imports(generated_code)
            recomputed = _ecd(curr_body, prev_body)
            if recomputed:
                if _is_compilable(recomputed):
                    return recomputed
                candidates.append(recomputed)

    # ── 3) 저장된 step_code ──
    if step_code:
        normalized = _sd(_uwm(step_code))
        if normalized:
            if _is_compilable(normalized):
                return normalized
            candidates.append(normalized)

    # ── 4) generated_code 전체 — prev_step is None (첫 step) 만 valid ──
    # 사용자 보고 (5/6): AI 가 새 step 본문 안 만들고 응답에 누적 코드만 반환 시
    # 마커 추출 / diff / step_code 모두 fail → 4번 fallback 으로 누적 코드 통째가 step_code
    # 로 저장됨 → 단독 실행 시 import + 메모장 실행까지 전부 실행되는 silent 회귀.
    # prev_step 이 있으면 (이미 step 1 이상 진행됨) 이 fallback 차단해서 빈 string 반환 →
    # 호출자 (AppService.generate_step) 에서 fail-fast 처리 가능.
    if generated_code and prev_step is None:
        if _is_compilable(generated_code):
            return generated_code
        candidates.append(generated_code)

    if not candidates:
        return ""
    # 모두 syntax 깨졌으면 가장 짧은 후보 (오류가 한눈에 보이도록)
    return min(candidates, key=len)
