# SPDX-License-Identifier: AGPL-3.0-or-later
"""ohdo Agent — Execution Runner (M2.3 ~ M2.8).

서버가 WS 로 ``execution.start`` 를 보내면 그에 대응하는 ``WorkflowEngine``
실행을 워커 스레드에서 돌리고, 진행 상황을 ``execution.accepted`` /
``.progress`` / ``.result`` 로 보고한다.

M2.4 추가:
- 엔진 on_log + 스텝별 stdout/stderr 를 `execution.log` 프레임으로 배치 전송.
- stderr 의 Windows Python 런치 노이즈 필터링.
- error_summary 는 필터된 stderr 의 첫 실제 라인을 사용.

M2.5 추가:
- ``execution.cancel`` 프레임 수신 시 현재 실행 중인 engine.stop() +
  engine.sandbox.stop() 호출 → 서브프로세스 즉시 terminate.
- cancel 된 execution 은 ``execution.result`` 를 status='cancelled' 로 송신.

M2.6 추가:
- ``screenshot_on_error=True`` 로 복귀. 스텝 실패 시 ``result.error_screenshot``
  경로를 읽어 ``POST /v0/executions/{id}/captures`` 로 multipart 업로드.

M2.8 추가:
- 동반 배포되는 embedded Python (``_internal/python/python.exe``) 을 ``CodeSandbox``
  에 명시적으로 주입. ``sys.executable`` 이 번들 exe 가 되어 user code subprocess
  를 재귀 spawn 하던 M2.7 문제 해소.

M2.9 추가:
- embedded python 이 이미 pywinauto/pyautogui/selenium/mss 를 가지고 있으므로
  CodeSandbox 의 런타임 auto-install 을 subclass 로 skip. agent 프로세스의
  pkg_resources 와 bundle python 의 site-packages 가 서로 달라 매번 pip 를 돌려
  stdout 에 노이즈가 섞이던 문제 제거. 누락 패키지는 ImportError 로 명확히 노출.

M2.9.1 수정 (캡처 업로드 복구):
- core `_capture_error_screen` 는 agent 프로세스에서 `import mss` 하는데 agent 런타임
  에는 mss 가 없어 항상 None 반환 → 업로드 skip 되던 문제. 해결:
  runner 가 자체적으로 `_capture_desktop_png` 로 screenshot 을 temp 파일에 저장해
  업로드 후 정리. `WorkflowEngine(screenshot_on_error=False)` 로 core 경로는 비활성.

M2.10 추가:
- session_snapshot 의 `requirements: list[str]` 를 해석해
  `%APPDATA%/ohdo/packages/<sha256>` 에 `pip install --target` 으로 설치.
  sha256 기반 content-addressed 캐시로 재실행 시 skip.
- `_BundleCodeSandbox.execute` 가 user code 앞에 `sys.path.insert(0, cache_dir)` 를
  prepend 해 설치된 패키지 import 가능.
- 설치 로그는 `execution.log(stream="engine")` 로 스트리밍.
- 설치 실패 시 engine 실행 전에 execution.result(failed) 로 즉시 종료.

설계:
- docs/saas/architecture/10-m2.3-execution-lifecycle.md
- docs/saas/architecture/11-m2.4-execution-log.md
- docs/saas/architecture/12-m2.5-execution-cancel.md
- docs/saas/architecture/13-m2.6-captures-upload.md
- docs/saas/architecture/15-m2.8-embedded-python.md
- docs/saas/architecture/16-m2.9-python-packages.md
- docs/saas/architecture/17-m2.10-requirements.md
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

try:
    import httpx  # used for multipart capture upload (M2.6)
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

# core/workflow_engine.py 를 에이전트에서 import — sys.path 에 프로젝트 루트가
# 없으면 추가. PyInstaller 번들 시엔 이 경로가 번들 내부에 맞춰질 것 (M2.7).
try:
    from core.workflow_engine import CodeSandbox, WorkflowEngine  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    _project_root = Path(__file__).resolve().parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))
    from core.workflow_engine import CodeSandbox, WorkflowEngine  # type: ignore[import-not-found]

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


class _BundleCodeSandbox(CodeSandbox):
    """M2.9: agent 번들 환경용 CodeSandbox.

    부모 클래스의 ``_install_missing_packages`` 는 ``pkg_resources.working_set``
    로 현재 인터프리터 (= agent 프로세스) 의 패키지 목록을 본다. 하지만 코드는
    ``python_exe`` (= 번들에 동반된 embedded python) 에서 돌아가므로, 두 목록이
    달라 이미 설치된 pywinauto/pyautogui/selenium/mss 도 매번 "누락됨 → pip
    install" 로 인식되어 stdout 에 노이즈 + 불필요한 ~500ms 오버헤드. 여기선
    auto-install 을 전부 skip 하고, 누락 패키지는 사용자가 ImportError 로 직접
    확인하도록 둔다.

    M2.10: per-session requirements 를 설치한 캐시 디렉터리를 ``extra_syspath`` 로
    받아 execute 시점에 user code 앞에 ``sys.path.insert`` 라인을 prepend.
    ``PYTHONPATH`` env 경쟁을 회피하기 위해 코드 주입 방식을 사용한다.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_syspath: list[str] = []

    def _install_missing_packages(self, code: str):  # type: ignore[override]
        return None

    def execute(  # type: ignore[override]
        self,
        code: str,
        cwd: str | None = None,
        pre_exec_callback: Callable[[], None] | None = None,
        post_exec_callback: Callable[[], None] | None = None,
    ):
        if self.extra_syspath:
            prelude_lines = ["import sys"]
            for p in self.extra_syspath:
                prelude_lines.append(f"sys.path.insert(0, {p!r})")
            code = "\n".join(prelude_lines) + "\n" + code
        return super().execute(
            code,
            cwd=cwd,
            pre_exec_callback=pre_exec_callback,
            post_exec_callback=post_exec_callback,
        )


def _resolve_agent_appdata() -> Path:
    """agent_main 의 _resolve_appdata_dir 와 동일한 폴백 정책.

    agent_main import 는 순환을 피하기 위해 여기서 독립 구현.
    """
    override = os.getenv("OHDO_APPDATA")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.getenv("APPDATA")
        if base:
            return Path(base) / "ohdo"
    return Path.home() / ".ohdo"


def _capture_desktop_png() -> str | None:
    """M2.9.1: agent 프로세스에서 주화면 스크린샷을 PNG 로 temp 파일에 저장.

    성공 시 파일 경로, 실패 시 None. 호출자는 업로드 후 파일 삭제할 것.
    """
    try:
        import tempfile

        import mss  # agent bundle 에 포함 (M2.9.1 부터).
        import mss.tools as mss_tools
    except Exception as exc:  # noqa: BLE001
        logger.warning("capture import failed: %s", exc)
        return None

    try:
        fd, path = tempfile.mkstemp(prefix="ohdo_capture_", suffix=".png")
        os.close(fd)
        with mss.mss() as sct:
            monitors = sct.monitors
            # monitors[0] = virtual screen 전체, monitors[1] = primary monitor
            target = monitors[1] if len(monitors) > 1 else monitors[0]
            img = sct.grab(target)
            mss_tools.to_png(img.rgb, img.size, output=path)
        return path
    except Exception as exc:  # noqa: BLE001
        logger.warning("capture save failed: %s", exc)
        return None


def _resolve_python_exe() -> str:
    """Code 실행용 python.exe 경로 결정 (M2.8).

    우선순위:
    1. PyInstaller 번들이면 ``sys._MEIPASS/python/python.exe`` — 동반 배포된
       embedded Python. 이게 없으면 CodeSandbox 가 ohdo-agent.exe 를 재귀
       spawn 하는 M2.7 버그가 재발한다.
    2. dev run (bundle 아님) 이면 ``sys.executable`` — 현재 agent venv python.
    """
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        candidate = Path(mei) / "python" / "python.exe"
        if candidate.is_file():
            return str(candidate)
        logger.warning(
            "embedded python not found at %s — falling back to sys.executable "
            "(%s). user code subprocess may misbehave in bundled mode.",
            candidate,
            sys.executable,
        )
    return sys.executable


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


def _slice_steps(all_steps: list, from_step: int | None, to_step: int | None) -> list:
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
    """WS 프레임 핸들러. ``execution.start`` / ``execution.cancel`` 처리."""

    def __init__(self) -> None:
        self._sender: Sender | None = None
        self._lock = threading.Lock()
        self._running: set[str] = set()
        # M2.5: execution_id → 활성 WorkflowEngine 참조 (cancel 시 stop 용).
        self._active_engines: dict[str, Any] = {}
        self._active_lock = threading.Lock()
        # M2.5: cancel 요청 받은 execution_id 들. engine 종료 후 result 분기에 사용.
        self._cancelled: set[str] = set()
        # M2.6: capture 업로드에 쓰는 서버 URL + auth_state.
        self._server_url: str | None = None
        self._auth_state: Any = None

    def set_sender(self, sender: Sender) -> None:
        self._sender = sender

    def set_http_context(self, server_url: str, auth_state: Any) -> None:
        """M2.6: capture upload 등 HTTP 호출을 위한 서버 URL + 토큰 공급자 등록."""
        self._server_url = server_url.rstrip("/")
        self._auth_state = auth_state

    def handle_frame(self, frame: dict) -> None:
        if not isinstance(frame, dict):
            return
        ftype = frame.get("type")
        if ftype == "execution.start":
            self._handle_start(frame)
        elif ftype == "execution.cancel":
            self._handle_cancel_frame(frame)
        else:
            logger.debug("runner ignoring frame type=%s", ftype)

    # ── execution.start ────────────────────────────────────────────────────

    def _handle_start(self, frame: dict) -> None:
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

    # ── execution.cancel ───────────────────────────────────────────────────

    def _handle_cancel_frame(self, frame: dict) -> None:
        payload = frame.get("payload") if isinstance(frame.get("payload"), dict) else None
        if not payload:
            return
        execution_id = payload.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id:
            return
        logger.info("execution.cancel received: %s", execution_id)

        with self._active_lock:
            self._cancelled.add(execution_id)
            engine = self._active_engines.get(execution_id)

        if engine is None:
            # 이미 끝났거나 시작 전. 서버가 terminal 게이트로 이걸 걸렀어야 하지만
            # 경쟁 조건에 대비.
            logger.info("cancel for unknown/finished execution: %s", execution_id)
            return

        try:
            engine.stop()
        except Exception:  # pragma: no cover
            logger.exception("engine.stop raised")
        sandbox = getattr(engine, "sandbox", None)
        if sandbox is not None:
            try:
                sandbox.stop()
            except Exception:  # pragma: no cover
                logger.exception("sandbox.stop raised")

    # ── 내부 ────────────────────────────────────────────────────────────────

    def _send(self, ftype: str, payload: dict, in_reply_to: str | None = None) -> bool:
        if self._sender is None:
            logger.warning("no sender set - cannot send %s", ftype)
            return False
        ok = self._sender(_make_frame(ftype, payload, in_reply_to=in_reply_to))
        if not ok:
            logger.warning("failed to send %s", ftype)
        return ok

    def _pop_cancelled(self, execution_id: str) -> bool:
        """cancel 요청이 있었는지 확인하면서 플래그 제거. thread-safe."""
        with self._active_lock:
            was = execution_id in self._cancelled
            self._cancelled.discard(execution_id)
            return was

    def _unregister_engine(self, execution_id: str) -> None:
        with self._active_lock:
            self._active_engines.pop(execution_id, None)

    def _ensure_requirements_installed(
        self,
        execution_id: str,
        requirements: list[str],
        log_buf: "_LogBuffer",
    ) -> Path | None:
        """M2.10: content-addressed `pip install --target` 캐시.

        같은 requirements 조합 → 같은 hash → 같은 디렉터리 → 재사용.
        설치 로그는 log_buf 에 engine stream 으로 누적 (호출자가 flush).
        성공 시 캐시 디렉터리 Path, 빈 목록이면 None. 실패 시 예외.
        """
        normalized = sorted(r.strip() for r in requirements if isinstance(r, str) and r.strip())
        if not normalized:
            return None

        digest = hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()[:16]
        cache_dir = _resolve_agent_appdata() / "packages" / digest
        marker = cache_dir / ".ok"

        if marker.is_file():
            log_buf.append(
                stream="engine",
                step_id=None,
                line=f"requirements cache hit: {digest}",
            )
            return cache_dir

        log_buf.append(
            stream="engine",
            step_id=None,
            line=f"installing requirements (sha256={digest}): {', '.join(normalized)}",
        )
        cache_dir.mkdir(parents=True, exist_ok=True)
        python_exe = _resolve_python_exe()
        cmd = [
            python_exe,
            "-m",
            "pip",
            "install",
            "--target",
            str(cache_dir),
            "--no-warn-script-location",
            *normalized,
        ]
        logger.info("pip install starting: %s", cmd)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.rstrip()
                if line:
                    log_buf.append(
                        stream="engine",
                        step_id=None,
                        line=f"pip: {line}"[:LOG_LINE_MAX],
                    )
            rc = proc.wait(timeout=120)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
            raise

        if rc != 0:
            raise RuntimeError(f"pip install rc={rc}")

        marker.write_text("ok", encoding="ascii")
        log_buf.append(
            stream="engine",
            step_id=None,
            line=f"requirements installed: {cache_dir}",
        )
        return cache_dir

    def _upload_capture(self, execution_id: str, step_id: int, path: str) -> None:
        """M2.6: 스크린샷 파일을 `POST /v0/executions/{id}/captures` 로 업로드.

        실패는 조용히 swallow — 실행 결과 자체에는 영향 없음.
        """
        if httpx is None:
            logger.debug("capture upload skipped: httpx not available")
            return
        if not self._server_url or self._auth_state is None:
            logger.debug("capture upload skipped: http context not set")
            return
        creds = getattr(self._auth_state, "credentials", None)
        token = getattr(creds, "agent_token", None) if creds else None
        if not token:
            logger.debug("capture upload skipped: no agent_token")
            return

        filename = os.path.basename(path) or "capture.png"
        content_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
        try:
            with open(path, "rb") as f:
                blob = f.read()
        except OSError as exc:
            logger.warning("capture file read failed: %s (%s)", path, exc)
            return

        url = f"{self._server_url}/v0/executions/{execution_id}/captures"
        try:
            resp = httpx.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (filename, blob, content_type)},
                data={"step_id": str(step_id), "kind": "error_screenshot"},
                timeout=20.0,
            )
        except httpx.HTTPError as exc:
            logger.warning("capture upload http error: %s", exc)
            return

        if resp.status_code == 201:
            try:
                cid = resp.json().get("capture_id")
            except Exception:
                cid = "<unparsed>"
            logger.info(
                "capture uploaded: execution_id=%s step_id=%s capture_id=%s size=%dB",
                execution_id,
                step_id,
                cid,
                len(blob),
            )
        else:
            logger.warning(
                "capture upload non-201: status=%s body=%r",
                resp.status_code,
                resp.text[:200],
            )

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

    def _run_execution(self, execution_id: str, payload: dict, in_reply_to: str | None) -> None:
        try:
            self._run_execution_inner(execution_id, payload, in_reply_to)
        except Exception as exc:  # noqa: BLE001
            logger.exception("runner unexpected error: execution_id=%s", execution_id)
            # 외부에서 cancel 이 들어온 상태였다면 그걸 우선.
            was_cancelled = self._pop_cancelled(execution_id)
            self._unregister_engine(execution_id)
            self._send(
                "execution.result",
                {
                    "execution_id": execution_id,
                    "status": "cancelled" if was_cancelled else "failed",
                    "error_summary": None
                    if was_cancelled
                    else f"runner exception: {exc.__class__.__name__}: {exc}"[:500],
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
        requirements = snapshot.get("requirements") if isinstance(snapshot, dict) else None

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
        t_start = time.time()

        # M2.10: per-session requirements 설치. 실패 시 engine 실행 없이 즉시 result.
        cache_dir: Path | None = None
        if isinstance(requirements, list) and requirements:
            try:
                cache_dir = self._ensure_requirements_installed(execution_id, requirements, log_buf)
            except Exception as exc:  # noqa: BLE001
                logger.exception("requirements install failed: execution_id=%s", execution_id)
                self._flush_logs(execution_id, log_buf)
                elapsed_ms = int((time.time() - t_start) * 1000)
                was_cancelled = self._pop_cancelled(execution_id)
                self._send(
                    "execution.result",
                    {
                        "execution_id": execution_id,
                        "status": "cancelled" if was_cancelled else "failed",
                        "total_steps": len(steps),
                        "executed_steps": 0,
                        "successful_steps": 0,
                        "failed_steps": 0,
                        "total_time_ms": elapsed_ms,
                        "error_summary": None
                        if was_cancelled
                        else (
                            f"requirements install failed: {exc.__class__.__name__}: {exc}"[:500]
                        ),
                    },
                )
                return

        # 2) 엔진 실행
        # M2.8: CodeSandbox 에 embedded python.exe 를 명시적으로 주입. 기본
        # sys.executable 은 번들 시 ohdo-agent.exe 가 되어 재귀 spawn 을 일으킨다.
        # M2.9: _BundleCodeSandbox 로 auto-install 노이즈 제거.
        # M2.9.1: screenshot_on_error=False. core 의 캡처 경로는 agent 런타임에 mss
        # 가 없어 항상 실패했고 경로도 Program Files 쪽을 가리킴. 캡처는 runner 의
        # _capture_desktop_png 가 on_step_complete 에서 자체 수행한다.
        # M2.10: extra_syspath 에 requirements 캐시 dir 주입 → user code 앞에
        # sys.path.insert 라인 자동 prepend.
        sandbox = _BundleCodeSandbox(python_exe=_resolve_python_exe())
        if cache_dir is not None:
            sandbox.extra_syspath.append(str(cache_dir))
        engine = WorkflowEngine(
            sandbox=sandbox,
            step_delay_ms=0,
            screenshot_on_error=False,
            visual_feedback_enabled=False,
        )
        # M2.5: cancel 요청이 이 engine 을 찾을 수 있도록 등록.
        with self._active_lock:
            self._active_engines[execution_id] = engine

        counters = {"executed": 0, "successful": 0, "failed": 0}
        last_step_error_lines: dict[int, list[str]] = {}
        # t_start 는 requirements install 전에 이미 set (elapsed 를 install 포함 시점부터 집계)

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

            # M2.6: 스텝 실패 시 화면 캡처 업로드.
            # M2.9.1: core 대신 runner 가 직접 캡처 (agent 프로세스의 mss 사용).
            if not success:
                shot_path = _capture_desktop_png()
                if shot_path:
                    try:
                        self._upload_capture(execution_id, step_id, shot_path)
                    finally:
                        try:
                            os.unlink(shot_path)
                        except OSError:
                            pass

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
            # cancel 중 예외면 cancelled 로 보고. 아니면 failed.
            was_cancelled = self._pop_cancelled(execution_id)
            self._unregister_engine(execution_id)
            self._send(
                "execution.result",
                {
                    "execution_id": execution_id,
                    "status": "cancelled" if was_cancelled else "failed",
                    "total_steps": len(steps),
                    "executed_steps": counters["executed"],
                    "successful_steps": counters["successful"],
                    "failed_steps": counters["failed"],
                    "total_time_ms": elapsed_ms,
                    "error_summary": None
                    if was_cancelled
                    else f"engine exception: {exc.__class__.__name__}: {exc}"[:500],
                },
            )
            return

        # 종료 전 잔여 로그 flush (on_step_complete 이후 엔진이 "완료" 메시지 등 송신).
        self._flush_logs(execution_id, log_buf)

        # M2.5: cancel 요청이 있었으면 최종 상태는 'cancelled'.
        was_cancelled = self._pop_cancelled(execution_id)
        self._unregister_engine(execution_id)

        # 3) result — error_summary 는 필터된 stderr 의 첫 의미있는 라인 (cancelled 면 None).
        error_summary: str | None = None
        if not was_cancelled and report.failed_steps > 0:
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

        if was_cancelled:
            final_status = "cancelled"
        else:
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
