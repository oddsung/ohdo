"""
ExecutionKernel - 영속적 Python 커널 관리자

Jupyter/Colab 방식과 동일하게 한 번 시작된 Python 프로세스를
세션 동안 유지하여 변수 상태(driver, app 등)를 보존합니다.

주요 기능:
  - kernel_worker.py를 서브프로세스로 실행/관리
  - IPC(stdin/stdout)를 통한 코드 블럭 전송 및 결과 수신
  - 실행된 스텝 추적 (어느 스텝까지 실행됐는지)
  - 타임아웃 지원 (reader 스레드 + queue 방식, Windows 호환)
  - 스레드 안전 실행 (threading.Lock)
"""

import sys
import os
import time
import queue
import threading
import subprocess
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# 라이브러리 블럭의 가상 step_id
LIBRARY_BLOCK_STEP_ID = 0


@dataclass
class StepResult:
    """단일 블럭 실행 결과 (workflow_engine.StepResult와 호환 구조)"""
    step_id: int = 0
    success: bool = False
    output: str = ""
    error: Optional[str] = None
    duration_ms: int = 0


class ExecutionKernel:
    """
    영속적 Python 커널.

    start() 후 execute_block() 호출로 코드를 순차 실행합니다.
    동일 커널 안에서 실행된 모든 블럭은 같은 네임스페이스를 공유하므로
    이전 블럭에서 생성된 변수/객체를 이후 블럭에서 그대로 사용할 수 있습니다.
    """

    # IPC 프로토콜 센티넬 (kernel_worker.py와 동일해야 함)
    _SENTINEL_END = "<<<EXECUTE_END>>>"
    _RESULT_SUCCESS = "<<<SUCCESS>>>"
    _RESULT_ERROR = "<<<ERROR>>>"
    _RESULT_DONE = "<<<DONE>>>"
    _PING = "<<<PING>>>"
    _PONG = "<<<PONG>>>"

    def __init__(self, python_exe: Optional[str] = None, default_timeout: int = 60):
        """
        Args:
            python_exe: Python 인터프리터 경로. None이면 현재 실행 중인 Python 사용
            default_timeout: execute_block() 기본 타임아웃(초)
        """
        self.python_exe = python_exe or sys.executable
        self.default_timeout = default_timeout

        self._proc: Optional[subprocess.Popen] = None
        self._output_queue: queue.Queue = queue.Queue()
        self._reader_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._executed_steps: list[int] = []

    # ──────────────────────────────────────
    # 생명주기
    # ──────────────────────────────────────

    def start(self) -> None:
        """커널 프로세스를 시작합니다."""
        if self.is_alive:
            return

        worker_path = Path(__file__).parent / "kernel_worker.py"
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"

        self._proc = subprocess.Popen(
            [self.python_exe, "-u", str(worker_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # stderr를 stdout으로 병합
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            bufsize=1,                  # 라인 버퍼 (실시간 출력)
        )
        self._executed_steps = []
        self._output_queue = queue.Queue()

        # 비동기 reader 스레드 시작 (Windows에서 readline 블로킹 우회)
        self._reader_thread = threading.Thread(
            target=self._read_loop,
            daemon=True,
            name=f"KernelReader-{id(self)}"
        )
        self._reader_thread.start()
        logger.info("ExecutionKernel 시작 (PID=%s)", self._proc.pid)

    def stop(self) -> None:
        """커널 프로세스를 종료합니다."""
        proc = self._proc
        self._proc = None
        self._executed_steps = []

        if proc is not None:
            try:
                proc.stdin.close()
            except Exception:
                pass
            try:
                proc.kill()
                proc.wait(timeout=3)
            except Exception:
                pass
            logger.info("ExecutionKernel 종료")

        # 큐에 종료 센티넬 삽입 (대기 중인 execute_block 해제)
        self._output_queue.put(None)

    def reset(self) -> None:
        """커널을 재시작합니다 (변수 상태 초기화)."""
        self.stop()
        self.start()

    @property
    def is_alive(self) -> bool:
        """커널 프로세스가 실행 중인지 여부"""
        return self._proc is not None and self._proc.poll() is None

    @property
    def executed_steps(self) -> list[int]:
        """현재 커널 세션에서 실행 완료된 step_id 목록"""
        return list(self._executed_steps)

    # ──────────────────────────────────────
    # 코드 블럭 실행
    # ──────────────────────────────────────

    def execute_block(
        self,
        code: str,
        step_id: int = -1,
        timeout: Optional[int] = None,
        silent: bool = False,
    ) -> StepResult:
        """
        코드 블럭을 커널에서 실행합니다.

        Args:
            code: 실행할 Python 코드
            step_id: 스텝 ID (-1이면 추적 안 함, 0이면 라이브러리 블럭)
            timeout: 타임아웃(초). None이면 default_timeout 사용
            silent: True이면 출력을 StepResult에 포함하지 않음 (silent replay용)

        Returns:
            StepResult
        """
        if not self.is_alive:
            return StepResult(
                step_id=step_id,
                success=False,
                error="커널이 실행 중이 아닙니다. start()를 먼저 호출하세요."
            )

        with self._lock:
            return self._execute_locked(code, step_id, timeout, silent)

    def ping(self, timeout: float = 3.0) -> bool:
        """커널 프로세스가 응답하는지 확인합니다."""
        if not self.is_alive:
            return False
        result = self.execute_block(self._PING, step_id=-1, timeout=int(timeout))
        return result.success

    # ──────────────────────────────────────
    # 내부 구현
    # ──────────────────────────────────────

    def _read_loop(self) -> None:
        """stdout을 비동기로 읽어 큐에 삽입하는 reader 스레드"""
        proc = self._proc
        try:
            while proc and proc.poll() is None:
                line = proc.stdout.readline()
                if not line:
                    break
                self._output_queue.put(line.rstrip('\r\n'))
        except Exception as e:
            logger.debug("KernelReader 종료: %s", e)
        finally:
            # 프로세스 종료 신호
            self._output_queue.put(None)

    def _execute_locked(
        self,
        code: str,
        step_id: int,
        timeout: Optional[int],
        silent: bool,
    ) -> StepResult:
        """Lock 내부에서 실행되는 실제 실행 로직"""
        start_time = time.time()
        t = timeout if timeout is not None else self.default_timeout

        # PING 명령이면 코드 대신 PING 센티넬 전송
        actual_code = self._PING if code.strip() == self._PING else code

        try:
            # stdin으로 코드 전송
            self._proc.stdin.write(actual_code + "\n")
            self._proc.stdin.write(self._SENTINEL_END + "\n")
            self._proc.stdin.flush()
        except Exception as e:
            return StepResult(
                step_id=step_id,
                success=False,
                error=f"커널 stdin 쓰기 오류: {e}",
                duration_ms=int((time.time() - start_time) * 1000)
            )

        # 결과 수신 (RESULT_DONE까지 읽기)
        output_lines = []
        success = True
        deadline = time.time() + t

        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                self.stop()  # 응답 없는 커널 강제 종료
                return StepResult(
                    step_id=step_id,
                    success=False,
                    error=f"실행 시간 초과 ({t}초). 커널이 재시작되었습니다.",
                    duration_ms=int((time.time() - start_time) * 1000)
                )

            try:
                line = self._output_queue.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                # 타임아웃 재확인
                if time.time() >= deadline:
                    self.stop()
                    return StepResult(
                        step_id=step_id,
                        success=False,
                        error=f"실행 시간 초과 ({t}초). 커널이 재시작되었습니다.",
                        duration_ms=int((time.time() - start_time) * 1000)
                    )
                continue

            if line is None:
                # 프로세스 종료 신호
                return StepResult(
                    step_id=step_id,
                    success=False,
                    error="커널 프로세스가 예기치 않게 종료되었습니다.",
                    duration_ms=int((time.time() - start_time) * 1000)
                )

            if line == self._RESULT_DONE:
                break
            elif line == self._RESULT_SUCCESS or line == self._PONG:
                success = True
            elif line == self._RESULT_ERROR:
                success = False
            else:
                output_lines.append(line)

        elapsed_ms = int((time.time() - start_time) * 1000)
        output_text = "\n".join(output_lines).strip()

        # 성공 시 실행 스텝 기록
        if success and step_id >= 0:
            if step_id not in self._executed_steps:
                self._executed_steps.append(step_id)

        if success:
            return StepResult(
                step_id=step_id,
                success=True,
                output="" if silent else output_text,
                duration_ms=elapsed_ms
            )
        else:
            return StepResult(
                step_id=step_id,
                success=False,
                output="" if silent else output_text.split('\n')[0] if output_text else "",
                error=output_text,
                duration_ms=elapsed_ms
            )