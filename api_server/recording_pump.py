# SPDX-License-Identifier: AGPL-3.0-or-later
"""작업 녹화용 Windows 메시지 펌프 스레드 (handoff §42).

**왜 필요한가**: ``core/input_hooks.py`` 의 LL 훅(WH_MOUSE_LL/WH_KEYBOARD_LL)은
``SetWindowsHookExW`` 를 호출한 **그 스레드에서 메시지 펌프(GetMessage/PeekMessage)가
돌아야** 콜백이 호출된다. PySide 앱은 Qt 이벤트 루프가 펌프 역할을 하지만, FastAPI
브리지에는 uvicorn 의 asyncio 루프만 있고 Windows 메시지 펌프가 없다 → 훅은 설치되지만
콜백이 안 불려서 입력이 하나도 기록되지 않는다 (사용자 실측 §42).

**해결**: 녹화 전용 데몬 스레드를 띄워 그 스레드에서
1. ``AppService.start_recording`` 호출 (= 그 스레드에 훅 설치)
2. PeekMessage 펌프 루프 (5ms 간격) — LL 훅 콜백이 비로소 발화
3. stop 신호 시 ``stop_recording`` 호출 (= 같은 스레드에서 UnhookWindowsHookEx)
한다. Windows 는 SetWindowsHookEx / 펌프 / UnhookWindowsHookEx 가 모두 같은 스레드일
것을 요구하므로 start~stop 전체를 이 스레드가 소유한다.

``core/`` 는 수정하지 않는다 — ``AppService`` 공개 메서드만 호출.
"""

from __future__ import annotations

import ctypes
import threading
import time
from typing import Callable, Optional

PM_REMOVE = 0x0001
_PUMP_INTERVAL_SEC = 0.005  # LL hook 타임아웃(~300ms) 대비 충분히 짧게


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MSG(ctypes.Structure):
    # 포인터/핸들 필드는 64-bit 안전 타입으로 (OverflowError 회피).
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint),
        ("pt", _POINT),
    ]


class RecordingActiveError(RuntimeError):
    """이미 녹화(펌프 스레드)가 활성인데 start 재호출."""


class RecordingController:
    """녹화 lifecycle 을 단일 펌프 스레드로 오케스트레이션.

    Args:
        service_getter: 호출 시 AppService 를 반환하는 콜러블 (lazy).
    """

    def __init__(self, service_getter: Callable[[], object]) -> None:
        self._get_service = service_getter
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

        self._stop_event = threading.Event()
        self._started_event = threading.Event()
        self._stopped_event = threading.Event()

        self._session_id: Optional[str] = None
        self._mode: str = "commit"  # "commit" | "preview" | "cancel"
        self._steps = None  # stop_recording 결과 (list[Step]) — commit/preview 모드
        self._start_error: Optional[BaseException] = None
        self._stop_error: Optional[BaseException] = None

    def is_active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, session_id: str, timeout: float = 5.0) -> None:
        """녹화 펌프 스레드 시작 → 그 스레드에서 start_recording (훅 설치)."""
        with self._lock:
            if self.is_active():
                raise RecordingActiveError("이미 녹화 중입니다.")
            self._stop_event.clear()
            self._started_event.clear()
            self._stopped_event.clear()
            self._session_id = session_id
            self._mode = "commit"
            self._steps = None
            self._start_error = None
            self._stop_error = None
            self._thread = threading.Thread(
                target=self._run, name="ohdo-recording-pump", daemon=True
            )
            self._thread.start()

        if not self._started_event.wait(timeout):
            raise RuntimeError("녹화 스레드 시작 타임아웃")
        if self._start_error is not None:
            raise self._start_error

    def stop(self, mode: str = "commit", timeout: float = 20.0):
        """녹화 종료 신호 → 펌프 스레드가 같은 스레드에서 stop_recording.

        Returns:
            ``mode in ("commit", "preview")`` 이면 변환된 step 리스트, ``cancel`` 이면 None.
            "preview"(handoff §63)는 커밋하지 않고 step 만 돌려준다 — review 후 commit_steps.
        """
        if not self.is_active():
            return None
        self._mode = mode
        self._stop_event.set()
        if not self._stopped_event.wait(timeout):
            raise RuntimeError("녹화 종료 타임아웃")
        if self._stop_error is not None:
            raise self._stop_error
        return self._steps

    def commit_steps(self, session_id: str, steps: list):
        """녹화 review 후 확정 step 을 세션에 커밋 (handoff §63, 백로그 #22).

        ``commit_recording`` 은 순수 데이터(세션 append + save)라 LL 후크/펌프 스레드와
        무관 — 호출(요청) 스레드에서 직접 실행해도 안전(stop("preview") 로 펌프 종료 후).
        """
        return self._get_service().commit_recording(  # type: ignore[attr-defined]
            edited_steps=steps, target_session_id=session_id
        )

    # ── 펌프 스레드 본체 ──────────────────────────────

    def _run(self) -> None:
        service = self._get_service()

        # UIA element 캡처는 COM(STA)을 요구. 펌프 스레드(및 recorder drain 스레드)에서
        # COM 미초기화면 capture_element_at 이 None 반환(좌표 fallback) — 그래도 녹화는
        # 동작한다. 여기서 best-effort 로 STA 초기화해 element 캡처 성공률을 높인다.
        try:
            ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
        except Exception:
            pass

        try:
            from core.element_inspect import capture_element_at

            service.start_recording(  # type: ignore[attr-defined]
                target_session_id=self._session_id,
                element_capture_fn=capture_element_at,
            )
        except BaseException as exc:  # noqa: BLE001 — 호출자에게 전달
            self._start_error = exc
            self._started_event.set()
            return

        self._started_event.set()

        # ── 메시지 펌프 루프 — 이게 있어야 LL 훅 콜백이 발화한다 ──
        user32 = ctypes.windll.user32
        msg = _MSG()
        try:
            while not self._stop_event.is_set():
                # PeekMessage 가 LL 훅 콜백을 dispatch 한다 (스레드 메시지 큐 처리 시점).
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                time.sleep(_PUMP_INTERVAL_SEC)
        finally:
            # stop_recording / 훅 해제는 반드시 같은 스레드에서 (UnhookWindowsHookEx 제약).
            try:
                if self._mode in ("commit", "preview"):
                    # commit/preview 둘 다 변환된 step 을 _steps 에 보존. preview(handoff §63)
                    # 는 커밋하지 않고 review 후 commit_steps 로 별도 커밋.
                    self._steps = service.stop_recording(  # type: ignore[attr-defined]
                        self_window_titles=["ohdo"]
                    )
                else:
                    service.stop_recording(self_window_titles=["ohdo"])  # type: ignore[attr-defined]
                    # cancel — recorder 인스턴스 폐기 (commit 안 함).
                    try:
                        service._recorder = None  # type: ignore[attr-defined]
                    except Exception:
                        pass
            except BaseException as exc:  # noqa: BLE001
                self._stop_error = exc
            finally:
                try:
                    ctypes.windll.ole32.CoUninitialize()
                except Exception:
                    pass
                self._stopped_event.set()
