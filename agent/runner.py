"""ohdo Agent — Execution Runner (M2.3 + M2.4).

서버가 WS 로 ``execution.start`` 를 보내면 그에 대응하는 ``WorkflowEngine``
실행을 워커 스레드에서 돌리고, 진행 상황을 ``execution.accepted`` /
``.progress`` / ``.result`` 로 보고한다.

M2.4 추가:
- 엔진 on_log + 스텝별 stdout/stderr 를 `execution.log` 프레임으로 배치 전송.
- stderr 의 Windows Python 런치 노이즈 필터링.
- error_summary 는 필터된 stderr 의 첫 실제 라인을 사용.

설계:
- docs/saas/architecture/10-m2.3-execution-lifecycle.md
- docs/saas/architecture/11-m2.4-execution-log.md
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

# core/workflow_engine.py 를 에이전트에서 import — sys.path 에 프로젝트 루트가
# 없으면 추가. PyInstaller 번들 시엔 이 경로가 번들 내부에 맞춰질 것 (M2.7).
try:
    from core.workflow_engine import WorkflowEngine  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    _project_root = Path(__file__).resolve().parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))
    from core.workflow_engine import WorkflowEngine  # type: ignore[import-not-found]

logger = logging.getLogger("ohdo.agent.runner")

PROTOCOL_VERSION = 0

# M2.4: 로그 라인 길이 제한 (agent 쪽 1차 방어).
LOG_LINE_MAX = 2000
# 단일 execution.log 프레임에 담을 entries 상한. 넘치면 여러 프레임으로 나눔.
LOG_ENTRIES_MAX_PER_FRAME = 500

# M2.4: stderr 노이즈 — Windows Python 런치 시 embedded / split install 에서
# 자주 나오는 잡음. 매치되면 drop.
_STDERR_NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^Could not find platform independent libraries"),
    re.compile(r"^Consider setting \$?PYTHONHOME"),
]


def _is_stderr_noise(line: str) -> bool:
    return any(p.search(line) for p in _STDERR_NOISE_PATTERNS)


Sender = Callable[[dict], bool]  # returns True on send success


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _make_frame(ftype: str, payload: dict, in_reply_to: str | None = None) -> dict:
    frame: dict = {
        "v": PROTOCOL_VERSION,
        "type": ftype,
        "id": str(uuid.uuid4()),
        "ts": _now_iso(),
        "payload": payload,
    }
    if in_reply_to:
        frame["in_reply_to"] = in_reply_to
    return frame


def _slice_steps(
    all_steps: list, from_step: int | None, to_step: int | None
) -> list:
    """1-based inclusive 범위로 스텝을 슬라이스. None 은 양끝."""
    if not all_steps:
        return []
    lo = (from_step - 1) if isinstance(from_step, int) and from_step >= 1 else 0
    hi = to_step if isinstance(to_step, int) and to_step >= 1 else len(all_steps)
    lo = max(lo, 0)
    hi = min(hi, len(all_steps))
    return all_steps[lo:hi]


def _filtered_stderr_lines(raw: str | None) -> list[str]:
    """stderr blob 을 줄 단위로 나누고 노이즈 라인과 빈 줄 제거."""
    if not isinstance(raw, str) or not raw:
        return []
    out: list[str] = []
    for line in raw.splitlines():
        stripped = line.rstrip()
        if not stripped:
            continue
        if _is_stderr_noise(stripped):
            continue
        out.append(stripped)
    return out


def _split_stdout_lines(raw: str | None) -> list[str]:
    """stdout 은 stripping 수준만 가볍게. 빈 줄은 제거."""
    if not isinstance(raw, str) or not raw:
        return []
    return [line.rstrip() for line in raw.splitlines() if line.strip()]


class _LogBuffer:
    """한 execution 안에서 쌓이는 로그 entries. monotonic seq 자동 관리."""

    def __init__(self) -> None:
        self._seq = 0
        self._entries: list[dict] = []
        self._lock = threading.Lock()

    def append(self, *, stream: str, step_id: int | None, line: str) -> None:
        if not isinstance(line, str) or not line:
            return
        clipped = line[:LOG_LINE_MAX]
        with self._lock:
            self._seq += 1
            self._entries.append(
                {
                    "seq": self._seq,
                    "stream": stream,
                    "step_id": step_id,
                    "line": clipped,
                }
            )

    def drain(self) -> list[dict]:
        with self._lock:
            out = self._entries
            self._entries = []
            return out


class ExecutionRunner:
    """WS 프레임 핸들러. ``execution.start`` 만 처리한다."""

    def __init__(self) -> None:
        self._sender: Sender | None = None
        self._lock = threading.Lock()
        self._running: set[str] = set()

    def set_sender(self, sender: Sender) -> None:
        self._sender = sender

    def handle_frame(self, frame: dict) -> None:
        if not isinstance(frame, dict):
            return
        if frame.get("type") != "execution.start":
            return
        payload = frame.get("payload") if isinstance(frame.get("payload"), dict) else None
        if not payload:
            logger.warning("execution.start missing payload")
            return
        execution_id = payload.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id:
            logger.warning("execution.start missing execution_id")
            return

        with self._lock:
            if execution_id in self._running:
                logger.info("execution.start duplicate ignored: %s", execution_id)
                return
            self._running.add(execution_id)

        in_reply_to = frame.get("id") if isinstance(frame.get("id"), str) else None
        t = threading.Thread(
            target=self._run_execution,
            args=(execution_id, payload, in_reply_to),
            name=f"ohdo-exec-{execution_id[:12]}",
            daemon=True,
        )
        t.start()

    # ── 내부 ────────────────────────────────────────────────────────────────

    def _send(self, ftype: str, payload: dict, in_reply_to: str | None = None) -> bool:
        if self._sender is None:
            logger.warning("no sender set - cannot send %s", ftype)
            return False
        ok = self._sender(_make_frame(ftype, payload, in_reply_to=in_reply_to))
        if not ok:
            logger.warning("failed to send %s", ftype)
        return ok

    def _flush_logs(self, execution_id: str, buffer: _LogBuffer) -> None:
        """버퍼를 비우고 1~N 개의 execution.log 프레임으로 전송."""
        entries = buffer.drain()
        if not entries:
            return
        for i in range(0, len(entries), LOG_ENTRIES_MAX_PER_FRAME):
            chunk = entries[i : i + LOG_ENTRIES_MAX_PER_FRAME]
            self._send(
                "execution.log",
                {"execution_id": execution_id, "entries": chunk},
            )

    def _run_execution(
        self, execution_id: str, payload: dict, in_reply_to: str | None
    ) -> None:
        try:
            self._run_execution_inner(execution_id, payload, in_reply_to)
        except Exception as exc:  # noqa: BLE001
            logger.exception("runner unexpected error: execution_id=%s", execution_id)
            self._send(
                "execution.result",
                {
                    "execution_id": execution_id,
                    "status": "failed",
                    "error_summary": f"runner exception: {exc.__class__.__name__}: {exc}"[:500],
                },
            )
        finally:
            with self._lock:
                self._running.discard(execution_id)

    def _run_execution_inner(
        self, execution_id: str, payload: dict, in_reply_to: str | None
    ) -> None:
        snapshot = payload.get("session_snapshot") or {}
        from_step = payload.get("from_step")
        to_step = payload.get("to_step")

        all_steps = snapshot.get("steps") if isinstance(snapshot, dict) else None
        if not isinstance(all_steps, list):
            all_steps = []

        steps = _slice_steps(all_steps, from_step, to_step)

        session_like = SimpleNamespace(
            session_id=(snapshot.get("session_id") if isinstance(snapshot, dict) else "")
            or f"sess_{execution_id}",
            steps=steps,
        )

        # 1) accepted
        self._send(
            "execution.accepted",
            {"execution_id": execution_id},
            in_reply_to=in_reply_to,
        )

        # M2.4: 로그 버퍼 + 현재 스텝 추적 (engine on_log 가 어느 스텝에 속한지 tag).
        log_buf = _LogBuffer()
        current_step_id_ref: dict[str, int | None] = {"sid": None}

        # 2) 엔진 실행
        engine = WorkflowEngine(
            step_delay_ms=0,
            screenshot_on_error=False,
            visual_feedback_enabled=False,
        )

        counters = {"executed": 0, "successful": 0, "failed": 0}
        last_step_error_lines: dict[int, list[str]] = {}
        t_start = time.time()

        def on_log(message: str) -> None:
            # engine 자체 상태 메시지 (step 시작/완료, 출력 요약 등).
            log_buf.append(
                stream="engine",
                step_id=current_step_id_ref["sid"],
                line=message,
            )

        def on_step_start(step_id: int) -> None:
            current_step_id_ref["sid"] = step_id

        def on_step_complete(step_id: int, result: Any) -> None:
            current_step_id_ref["sid"] = step_id
            counters["executed"] += 1
            success = bool(getattr(result, "success", False))
            if success:
                counters["successful"] += 1
            else:
                counters["failed"] += 1

            # step 의 stdout / stderr 를 라인 단위로 버퍼에 누적.
            for line in _split_stdout_lines(getattr(result, "output", None)):
                log_buf.append(stream="stdout", step_id=step_id, line=line)
            err_lines = _filtered_stderr_lines(getattr(result, "error", None))
            for line in err_lines:
                log_buf.append(stream="stderr", step_id=step_id, line=line)
            # error_summary 산출을 위해 step 별로 필터된 에러 라인 저장.
            if not success and err_lines:
                last_step_error_lines[step_id] = err_lines

            # progress 송신 (M2.3 동일).
            self._send(
                "execution.progress",
                {
                    "execution_id": execution_id,
                    "step_id": step_id,
                    "success": success,
                    "duration_ms": int(getattr(result, "duration_ms", 0) or 0),
                    "executed_steps": counters["executed"],
                    "successful_steps": counters["successful"],
                    "failed_steps": counters["failed"],
                },
            )

            # M2.4: step 완료마다 로그 flush.
            self._flush_logs(execution_id, log_buf)

        try:
            report = asyncio.run(
                engine.execute_session(
                    session_like,
                    start_from=0,
                    on_log=on_log,
                    on_step_start=on_step_start,
                    on_step_complete=on_step_complete,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("engine raised: execution_id=%s", execution_id)
            elapsed_ms = int((time.time() - t_start) * 1000)
            # 종료 전 잔여 로그 flush.
            self._flush_logs(execution_id, log_buf)
            self._send(
                "execution.result",
                {
                    "execution_id": execution_id,
                    "status": "failed",
                    "total_steps": len(steps),
                    "executed_steps": counters["executed"],
                    "successful_steps": counters["successful"],
                    "failed_steps": counters["failed"],
                    "total_time_ms": elapsed_ms,
                    "error_summary": f"engine exception: {exc.__class__.__name__}: {exc}"[:500],
                },
            )
            return

        # 종료 전 잔여 로그 flush (on_step_complete 이후 엔진이 "완료" 메시지 등 송신).
        self._flush_logs(execution_id, log_buf)

        # 3) result — error_summary 는 필터된 stderr 의 첫 의미있는 라인.
        error_summary: str | None = None
        if report.failed_steps > 0:
            for r in report.step_results:
                if getattr(r, "success", True):
                    continue
                step_id_val = getattr(r, "step_id", "?")
                lines = last_step_error_lines.get(
                    step_id_val if isinstance(step_id_val, int) else -1, []
                )
                if not lines:
                    # on_step_complete 이 미호출된 엣지 케이스 폴백.
                    lines = _filtered_stderr_lines(getattr(r, "error", None))
                # 실제 예외 메시지가 traceback 마지막 줄에 오는 경우가 많음.
                # "RuntimeError: ...", "ValueError: ..." 같은 패턴이 있으면 그걸 선호.
                picked: str | None = None
                for candidate in reversed(lines):
                    if re.match(r"^[A-Za-z_][A-Za-z0-9_\.]*(Error|Exception|Warning): ", candidate):
                        picked = candidate
                        break
                if picked is None and lines:
                    picked = lines[0]
                if picked:
                    error_summary = f"step {step_id_val}: {picked}"[:500]
                break

        final_status = "completed" if report.failed_steps == 0 else "failed"

        self._send(
            "execution.result",
            {
                "execution_id": execution_id,
                "status": final_status,
                "total_steps": report.total_steps,
                "executed_steps": report.executed_steps,
                "successful_steps": report.successful_steps,
                "failed_steps": report.failed_steps,
                "total_time_ms": report.total_time_ms,
                "error_summary": error_summary,
            },
        )
