# SPDX-License-Identifier: AGPL-3.0-or-later
"""작업 녹화 (Action Recording) Recorder lifecycle.

[ADR 0004 + architecture/25-recording-phase-r1-r2.md §"PR-12"] InputHookManager
를 사용해 마우스/키보드 이벤트를 캡처하고 RawEvent 버퍼에 시간순 누적한다.

EFP (ElementFromPoint) element 캡처는 별도 — `element_capture_fn` callback 으로
주입한다 (PR-13/PR-15 에서 win_inspector 와 연결). PR-12 자체는 element_meta 를
None 으로 둔다.

녹화 lifecycle:
    recorder = Recorder(hook_manager, opts)
    recorder.start(target_session_id=...)
    # ... 사용자 작업 ...
    recorder.add_marker()  # F8 수동 step 경계
    session = recorder.stop()
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from threading import Lock
from typing import Callable, Optional

from core.input_hooks import InputHookManager, KeyboardEvent, MouseEvent
from core.recorder_models import RawEvent, RecordingSession, TransformOptions

logger = logging.getLogger(__name__)


ElementCaptureFn = Callable[[int, int], Optional[dict]]
"""클릭 좌표 (x, y) → element_meta dict 또는 None.

PR-13/PR-15 에서 win_inspector 의 EFP 호출 함수를 주입. PR-12 자체는 None 으로
호출 가능 (element_meta 채우지 않음).
"""


_MOUSE_BUTTON_MAP: dict[str, str] = {
    "lbutton_down": "left",
    "lbutton_up": "left",
    "rbutton_down": "right",
    "rbutton_up": "right",
    "mbutton_down": "middle",
    "mbutton_up": "middle",
}


class RecorderAlreadyStartedError(RuntimeError):
    """이미 녹화 중인데 start() 재호출."""


class RecorderNotStartedError(RuntimeError):
    """녹화 안 한 상태에서 stop() / add_marker() 호출."""


class Recorder:
    """LL hook → RawEvent buffer.

    [architecture/25 §"PR-12"] start ~ stop 동안만 hook callback 활성.
    callback 자체는 hot path 라 try/except 로 격리 (예외가 hook dispatch 영향 X).

    스레드 안전: hook callback 은 OS hook thread 에서 호출되므로 buffer 접근
    시 lock 필수. start/stop 도 lock 으로 idempotent 보장.
    """

    def __init__(
        self,
        hook_manager: InputHookManager,
        opts: Optional[TransformOptions] = None,
        element_capture_fn: Optional[ElementCaptureFn] = None,
    ) -> None:
        self._hook_manager = hook_manager
        self._opts = opts or TransformOptions()
        self._element_capture_fn = element_capture_fn

        self._lock = Lock()
        self._session: Optional[RecordingSession] = None
        self._mouse_cb_id: Optional[int] = None
        self._keyboard_cb_id: Optional[int] = None

    @property
    def is_recording(self) -> bool:
        return self._session is not None and not self._session.is_stopped

    @property
    def event_count(self) -> int:
        return self._session.event_count if self._session else 0

    @property
    def current_session(self) -> Optional[RecordingSession]:
        return self._session

    def start(self, target_session_id: Optional[str] = None) -> RecordingSession:
        """녹화 시작. hook callback 등록.

        이미 녹화 중이면 RecorderAlreadyStartedError. stop() 후 재진입 가능
        (새 RecordingSession 생성).
        """
        with self._lock:
            if self.is_recording:
                raise RecorderAlreadyStartedError(
                    "Recorder is already recording. Call stop() first."
                )

            session = RecordingSession(
                id=str(uuid.uuid4()),
                started_at=datetime.now(),
                target_session_id=target_session_id,
            )
            self._session = session

            self._mouse_cb_id = self._hook_manager.install_mouse_callback(self._on_mouse_event)
            self._keyboard_cb_id = self._hook_manager.install_keyboard_callback(
                self._on_keyboard_event
            )

            return session

    def stop(self) -> RecordingSession:
        """녹화 종료. hook callback 해제 + stopped_at 기록.

        녹화 안 한 상태에서 호출 시 RecorderNotStartedError.
        """
        with self._lock:
            if self._session is None:
                raise RecorderNotStartedError("Recorder is not started.")
            if self._session.is_stopped:
                return self._session

            if self._mouse_cb_id is not None:
                self._hook_manager.uninstall_mouse_callback(self._mouse_cb_id)
                self._mouse_cb_id = None
            if self._keyboard_cb_id is not None:
                self._hook_manager.uninstall_keyboard_callback(self._keyboard_cb_id)
                self._keyboard_cb_id = None

            self._session.stopped_at = datetime.now()
            return self._session

    def add_marker(self) -> None:
        """F8 수동 step 경계 marker 추가.

        녹화 중일 때만 동작. 아니면 RecorderNotStartedError.
        """
        with self._lock:
            if not self.is_recording or self._session is None:
                raise RecorderNotStartedError("Recorder is not recording — cannot add marker.")
            self._session.events.append(RawEvent(ts=datetime.now(), kind="marker"))

    def _on_mouse_event(self, event: MouseEvent) -> bool:
        """mouse hook callback. 항상 False 반환 (이벤트 통과 — 녹화 중 사용자
        평상시 작업 보장)."""
        try:
            self._append_mouse_event(event)
        except Exception:
            logger.exception("Recorder: mouse event 처리 중 예외 (격리됨)")
        return False

    def _on_keyboard_event(self, event: KeyboardEvent) -> bool:
        """keyboard hook callback. 항상 False (이벤트 통과)."""
        try:
            self._append_keyboard_event(event)
        except Exception:
            logger.exception("Recorder: keyboard event 처리 중 예외 (격리됨)")
        return False

    def _append_mouse_event(self, event: MouseEvent) -> None:
        if self._session is None or self._session.is_stopped:
            return

        if event.type == "move":
            return  # PR-12 에서는 move 무시 (drag 캡처는 R3 후보)

        if event.type == "wheel":
            raw = RawEvent(
                ts=datetime.now(),
                kind="scroll",
                x=event.x,
                y=event.y,
                wheel_delta=event.wheel_delta,
            )
        elif event.type in _MOUSE_BUTTON_MAP and event.type.endswith("_down"):
            element_meta = None
            if self._element_capture_fn is not None:
                try:
                    element_meta = self._element_capture_fn(event.x, event.y)
                except Exception:
                    logger.exception(
                        "Recorder: element_capture_fn 예외 (element_meta None 으로 진행)"
                    )
            raw = RawEvent(
                ts=datetime.now(),
                kind="click",
                x=event.x,
                y=event.y,
                button=_MOUSE_BUTTON_MAP[event.type],
                element_meta=element_meta,
            )
        else:
            return

        with self._lock:
            if self._session is not None and not self._session.is_stopped:
                self._session.events.append(raw)

    def _append_keyboard_event(self, event: KeyboardEvent) -> None:
        if self._session is None or self._session.is_stopped:
            return
        if event.type not in ("keydown", "syskeydown"):
            return

        raw = RawEvent(
            ts=datetime.now(),
            kind="key",
            vk_code=event.vk_code,
        )

        with self._lock:
            if self._session is not None and not self._session.is_stopped:
                self._session.events.append(raw)
