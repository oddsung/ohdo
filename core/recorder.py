# SPDX-License-Identifier: AGPL-3.0-or-later
"""작업 녹화 (Action Recording) Recorder lifecycle.

[ADR 0004 + architecture/25-recording-phase-r1-r2.md §"PR-12"] InputHookManager
를 사용해 마우스/키보드 이벤트를 캡처하고 RawEvent 버퍼에 시간순 누적한다.

EFP (ElementFromPoint) element 캡처는 별도 — `element_capture_fn` callback 으로
주입한다 (PR-13/PR-15 에서 win_inspector 와 연결). PR-12 자체는 element_meta 를
None 으로 둔다.

R2 PR-16w 활성화:
- foreground 창 전환 → WinEvent callback → `window_focus` RawEvent (auto_window_focus_boundary)
- F8 키다운 → marker RawEvent 자동 변환 (enable_f8_marker; 평문 key event 안 박힘)

R2 PR-17 마이그레이션 모드:
- LL hook callback 은 RawEvent 생성 + 큐 enqueue 만 (sub-ms). Windows ~300ms
  타임아웃에 닿지 않도록 EFP 같은 무거운 호출은 drain thread 에서 비동기 처리.
- `queue.Queue(maxsize=queue_maxsize)` — 백프레셔: full 시 oldest drop + warn.
- `_drain_loop` 스레드가 큐를 빼며 element_capture_fn 호출 → session.events append.
- `stop()` 이 hook 해제 후 sentinel 로 drain 자연 종료 (join 5s timeout) — 정상
  종료 시 남은 큐 전부 처리됨 (event loss 0).

녹화 lifecycle:
    recorder = Recorder(hook_manager, opts)
    recorder.start(target_session_id=...)
    # ... 사용자 작업 ...
    recorder.add_marker()  # F8 수동 step 경계 (R2: 키보드 F8 도 자동 트리거)
    session = recorder.stop()
"""

from __future__ import annotations

import logging
import queue
import time
import uuid
from datetime import datetime
from threading import Event, Lock, Thread
from typing import Callable, Optional

from core.input_hooks import InputHookManager, KeyboardEvent, MouseEvent, WinEventEvent
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

VK_F8 = 0x77
"""VK_F8 = 0x77 — R2 PR-16w: enable_f8_marker 옵션 활성 시 marker 로 변환."""

DEFAULT_QUEUE_MAXSIZE = 10000
"""R2 PR-17 마이그레이션 모드 — drain queue 기본 상한.

10000 events ≈ 30+분 정상 입력. 빠른 자동화 스크립트 따라잡기 시 backpressure
완충. full 시 oldest drop + warn.
"""

_DRAIN_JOIN_TIMEOUT_SEC = 5.0
"""stop() 의 drain thread join timeout. 무한 대기 회피 (안전망)."""

_DRAIN_POLL_TIMEOUT_SEC = 0.1
"""drain thread 의 queue.get 타임아웃. _drain_stop_event 체크 주기."""


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
        queue_maxsize: int = DEFAULT_QUEUE_MAXSIZE,
    ) -> None:
        self._hook_manager = hook_manager
        self._opts = opts or TransformOptions()
        self._element_capture_fn = element_capture_fn

        self._lock = Lock()
        self._session: Optional[RecordingSession] = None
        self._mouse_cb_id: Optional[int] = None
        self._keyboard_cb_id: Optional[int] = None
        self._winevent_cb_id: Optional[int] = None

        # R2 PR-17 — async drain queue. start() 에서 생성·thread 시작, stop() 에서
        # sentinel + join.
        self._queue_maxsize = queue_maxsize
        self._raw_queue: Optional[queue.Queue] = None
        self._drain_thread: Optional[Thread] = None
        self._drain_stop_event = Event()
        self._dropped_event_count = 0

    @property
    def is_recording(self) -> bool:
        return self._session is not None and not self._session.is_stopped

    @property
    def event_count(self) -> int:
        return self._session.event_count if self._session else 0

    @property
    def current_session(self) -> Optional[RecordingSession]:
        return self._session

    @property
    def dropped_event_count(self) -> int:
        """R2 PR-17 — backpressure 로 큐 full 시 drop 된 누적 event 수."""
        return self._dropped_event_count

    @property
    def queue_size(self) -> int:
        """R2 PR-17 — 현재 drain 큐 대기 event 수 (모니터링/테스트용)."""
        return self._raw_queue.qsize() if self._raw_queue is not None else 0

    def wait_for_event_count(self, expected: int, timeout: float = 1.0) -> bool:
        """R2 PR-17 — drain thread 가 expected 이상의 event 를 처리할 때까지 대기.

        테스트와 동기 검증용. expected 도달 시 즉시 True. timeout 시 마지막 비교.
        polling 간격 5ms — 빠른 단위 테스트 친화적.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.event_count >= expected:
                return True
            time.sleep(0.005)
        return self.event_count >= expected

    def start(self, target_session_id: Optional[str] = None) -> RecordingSession:
        """녹화 시작. hook callback 등록 + drain thread 시작 (R2 PR-17).

        이미 녹화 중이면 RecorderAlreadyStartedError. stop() 후 재진입 가능
        (새 RecordingSession + 새 queue + 새 drain thread 생성).
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

            # PR-17: 매 start 마다 새 queue + drain thread (재진입 안전).
            self._raw_queue = queue.Queue(maxsize=self._queue_maxsize)
            self._dropped_event_count = 0
            self._drain_stop_event.clear()
            self._drain_thread = Thread(
                target=self._drain_loop, name="ohdo-recorder-drain", daemon=True
            )
            self._drain_thread.start()

            self._mouse_cb_id = self._hook_manager.install_mouse_callback(self._on_mouse_event)
            self._keyboard_cb_id = self._hook_manager.install_keyboard_callback(
                self._on_keyboard_event
            )
            self._winevent_cb_id = self._hook_manager.install_winevent_callback(
                self._on_winevent_event
            )

            return session

    def stop(self) -> RecordingSession:
        """녹화 종료. hook callback 해제 + drain 자연 종료 + stopped_at 기록.

        Hook 을 먼저 해제하여 새 enqueue 차단, 그 다음 sentinel 로 drain thread
        가 남은 큐를 처리하고 종료하도록 함. _DRAIN_JOIN_TIMEOUT_SEC 안에 join
        실패 시 강제 종료 신호 (안전망 — 정상 동작에선 거의 닿지 않음).

        녹화 안 한 상태에서 호출 시 RecorderNotStartedError.
        """
        with self._lock:
            if self._session is None:
                raise RecorderNotStartedError("Recorder is not started.")
            if self._session.is_stopped:
                return self._session

            # (1) hook 해제 — 새 event enqueue 차단
            if self._mouse_cb_id is not None:
                self._hook_manager.uninstall_mouse_callback(self._mouse_cb_id)
                self._mouse_cb_id = None
            if self._keyboard_cb_id is not None:
                self._hook_manager.uninstall_keyboard_callback(self._keyboard_cb_id)
                self._keyboard_cb_id = None
            if self._winevent_cb_id is not None:
                self._hook_manager.uninstall_winevent_callback(self._winevent_cb_id)
                self._winevent_cb_id = None

            drain_thread = self._drain_thread
            raw_queue = self._raw_queue

        # (2) drain thread 자연 종료 — sentinel + join (lock 밖에서)
        if raw_queue is not None:
            try:
                raw_queue.put(None, timeout=1.0)
            except queue.Full:
                # full 이면 강제 stop event 만 의지
                self._drain_stop_event.set()
        if drain_thread is not None and drain_thread.is_alive():
            drain_thread.join(timeout=_DRAIN_JOIN_TIMEOUT_SEC)
            if drain_thread.is_alive():
                logger.warning(
                    "Recorder: drain thread 가 %.1fs 안에 종료 안 됨 (남은 큐 일부 손실 가능)",
                    _DRAIN_JOIN_TIMEOUT_SEC,
                )
                self._drain_stop_event.set()

        with self._lock:
            self._drain_thread = None
            self._raw_queue = None
            assert self._session is not None
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
        """mouse hook callback. R2 PR-17 — RawEvent 생성 + 큐 enqueue 만 (sub-ms).

        EFP (element_capture_fn) 호출은 drain thread 가 담당. 항상 False 반환
        (이벤트 통과 — 녹화 중 사용자 평상시 작업 보장).
        """
        try:
            raw = self._build_mouse_raw(event)
            if raw is not None:
                self._enqueue_raw_event(raw)
        except Exception:
            logger.exception("Recorder: mouse event 처리 중 예외 (격리됨)")
        return False

    def _on_keyboard_event(self, event: KeyboardEvent) -> bool:
        """keyboard hook callback. R2 PR-17 — RawEvent 생성 + 큐 enqueue 만.

        F8 marker 변환 (PR-16w) 도 hook 스레드에서 즉시 결정 — drain 의존 X
        (variant 결정에 외부 호출 없음, 매우 빠름).
        """
        try:
            raw = self._build_keyboard_raw(event)
            if raw is not None:
                self._enqueue_raw_event(raw)
        except Exception:
            logger.exception("Recorder: keyboard event 처리 중 예외 (격리됨)")
        return False

    def _on_winevent_event(self, event: WinEventEvent) -> None:
        """WinEvent callback (R2 PR-16w). foreground 창 전환 → window_focus RawEvent.

        반환값 없음 (WinEvent 차단 불가). R2 PR-17 — 큐 enqueue 만.
        """
        try:
            raw = self._build_winevent_raw(event)
            if raw is not None:
                self._enqueue_raw_event(raw)
        except Exception:
            logger.exception("Recorder: winevent 처리 중 예외 (격리됨)")

    def _build_mouse_raw(self, event: MouseEvent) -> Optional[RawEvent]:
        if self._session is None or self._session.is_stopped:
            return None
        if event.type == "move":
            return None
        if event.type == "wheel":
            return RawEvent(
                ts=datetime.now(),
                kind="scroll",
                x=event.x,
                y=event.y,
                wheel_delta=event.wheel_delta,
            )
        if event.type in _MOUSE_BUTTON_MAP and event.type.endswith("_down"):
            # element_meta 는 drain thread 에서 채움 (PR-17 비동기 EFP).
            return RawEvent(
                ts=datetime.now(),
                kind="click",
                x=event.x,
                y=event.y,
                button=_MOUSE_BUTTON_MAP[event.type],
                element_meta=None,
            )
        return None

    def _build_keyboard_raw(self, event: KeyboardEvent) -> Optional[RawEvent]:
        if self._session is None or self._session.is_stopped:
            return None
        if event.type not in ("keydown", "syskeydown"):
            return None

        if self._opts.enable_f8_marker and event.vk_code == VK_F8:
            # R2 PR-16w: F8 → marker. transform 이 marker 자체 drop.
            return RawEvent(ts=datetime.now(), kind="marker")
        return RawEvent(
            ts=datetime.now(),
            kind="key",
            vk_code=event.vk_code,
        )

    def _build_winevent_raw(self, event: WinEventEvent) -> Optional[RawEvent]:
        if self._session is None or self._session.is_stopped:
            return None
        if event.type != "foreground":
            return None
        return RawEvent(
            ts=datetime.now(),
            kind="window_focus",
            hwnd=event.hwnd,
            window_title=event.window_title,
        )

    def _enqueue_raw_event(self, raw: RawEvent) -> None:
        """R2 PR-17 — drain queue 에 enqueue. full 시 oldest drop + counter 증가.

        non-blocking. hook 스레드에서 호출되므로 lock 회피 (Queue 가 내부 lock 보유).
        """
        q = self._raw_queue
        if q is None:
            return
        try:
            q.put_nowait(raw)
        except queue.Full:
            # backpressure: oldest drop 후 재시도
            try:
                q.get_nowait()
                self._dropped_event_count += 1
                if self._dropped_event_count == 1 or self._dropped_event_count % 100 == 0:
                    logger.warning(
                        "Recorder: drain queue full — oldest event 폐기 (총 %d drop)",
                        self._dropped_event_count,
                    )
            except queue.Empty:
                pass
            try:
                q.put_nowait(raw)
            except queue.Full:
                # 정상 시 도달 X (방금 비웠음). 그래도 안전망:
                self._dropped_event_count += 1

    def _drain_loop(self) -> None:
        """R2 PR-17 — drain thread 본체. 큐를 pop 하며 EFP 호출 + session 적재.

        sentinel `None` 받으면 종료. `_drain_stop_event` 셋되면 즉시 종료
        (강제 cleanup path). lock 으로 session.events 동시 접근 보호.
        """
        while not self._drain_stop_event.is_set():
            q = self._raw_queue
            if q is None:
                break
            try:
                raw = q.get(timeout=_DRAIN_POLL_TIMEOUT_SEC)
            except queue.Empty:
                continue
            if raw is None:
                # sentinel — 정상 종료
                break

            # click event 에 한해 EFP 비동기 enrichment.
            if raw.kind == "click" and self._element_capture_fn is not None:
                try:
                    raw.element_meta = self._element_capture_fn(raw.x or 0, raw.y or 0)
                except Exception:
                    logger.exception("Recorder: element_capture_fn 예외 (element_meta None 유지)")

            with self._lock:
                if self._session is not None and not self._session.is_stopped:
                    self._session.events.append(raw)
