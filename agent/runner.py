"""ohdo Agent — Execution Runner (M2.3).

서버가 WS 로 ``execution.start`` 를 보내면 그에 대응하는 ``WorkflowEngine``
실행을 워커 스레드에서 돌리고, 진행 상황을 ``execution.accepted`` /
``.progress`` / ``.result`` 로 보고한다.

설계: docs/saas/architecture/10-m2.3-execution-lifecycle.md

결정 요약:
- visual overlay / screenshot 은 M2.3 에선 비활성 (엔진 생성 시 False).
- progress 는 ``on_step_complete`` 에서만 (스텝당 1 프레임).
- stdout/stderr 스트리밍 (``execution.log``) 은 **M2.4** 범위.
- 동일 ``execution_id`` 가 이미 실행 중이면 중복 ``execution.start`` 는 무시.
"""

from __future__ import annotations

import asyncio
import logging
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

    def _send(self, ftype: str, payload: dict, in_reply_to: str | None = None) -> None:
        if self._sender is None:
            logger.warning("no sender set — cannot send %s", ftype)
            return
        ok = self._sender(_make_frame(ftype, payload, in_reply_to=in_reply_to))
        if not ok:
            logger.warning("failed to send %s", ftype)

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

        # 2) 엔진 실행
        engine = WorkflowEngine(
            step_delay_ms=0,
            screenshot_on_error=False,
            visual_feedback_enabled=False,
        )

        counters = {"executed": 0, "successful": 0, "failed": 0}
        t_start = time.time()

        def on_step_complete(step_id: int, result: Any) -> None:
            counters["executed"] += 1
            if getattr(result, "success", False):
                counters["successful"] += 1
            else:
                counters["failed"] += 1
            self._send(
                "execution.progress",
                {
                    "execution_id": execution_id,
                    "step_id": step_id,
                    "success": bool(getattr(result, "success", False)),
                    "duration_ms": int(getattr(result, "duration_ms", 0) or 0),
                    "executed_steps": counters["executed"],
                    "successful_steps": counters["successful"],
                    "failed_steps": counters["failed"],
                },
            )

        try:
            report = asyncio.run(
                engine.execute_session(
                    session_like,
                    start_from=0,
                    on_step_complete=on_step_complete,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("engine raised: execution_id=%s", execution_id)
            elapsed_ms = int((time.time() - t_start) * 1000)
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

        # 3) result
        error_summary: str | None = None
        if report.failed_steps > 0:
            for r in report.step_results:
                if not getattr(r, "success", True):
                    err = getattr(r, "error", None) or "unknown"
                    first = err.splitlines()[0] if isinstance(err, str) and err else str(err)
                    error_summary = f"step {getattr(r, 'step_id', '?')}: {first}"[:500]
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
