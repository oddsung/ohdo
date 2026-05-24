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

R2 PR-18 — DPI / 멀티모니터 안정화:
- click event 적재 시 drain thread 가 `get_dpi_for_point(x, y)` 로 좌표 모니터의
  effective DPI 캡처 (RawEvent.monitor_dpi). transform 의 fallback 좌표 코드에
  코멘트로 첨부되어 재생 환경 DPI 와 불일치 진단 가능.

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

from core.input_hooks import (
    InputHookManager,
    KeyboardEvent,
    MouseEvent,
    WinEventEvent,
    get_dpi_for_point,
)
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

VK_R = 0x52
"""VK_R = 0x52 — Ctrl+Shift+R 글로벌 stop hotkey 감지용 (2026-05-20 실측 fix)."""

VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12  # Alt
VK_LWIN = 0x5B
VK_RWIN = 0x5C

# PR-19f (2026-05-24) — modifier 키 인식. _build_keyboard_raw 가 매 keydown 시
# 현재 OS modifier 상태를 GetAsyncKeyState 로 캡처해 RawEvent.modifiers 에 채움.
# recorder_transform._emit_key_group 가 modifier 있는 char/special 키를
# pyautogui.hotkey(...) 로 변환 (예: Ctrl+A → pyautogui.hotkey('ctrl', 'a')).
_MODIFIER_CHECKS = (
    ("ctrl", VK_CONTROL),
    ("shift", VK_SHIFT),
    ("alt", VK_MENU),
    ("win", VK_LWIN),
    ("win", VK_RWIN),
)


def _capture_modifier_state() -> list[str]:
    """현재 눌려 있는 modifier 키 리스트 (``["ctrl", "shift"]`` 등).

    ``GetAsyncKeyState`` 로 OS real-time 상태 조회. modifier 자체 keydown 의
    경우도 자기 자신이 modifier 로 포함됨 (예: Ctrl 눌림 RawEvent.modifiers =
    ``["ctrl"]``) — transform 단계에서 modifier 자체 키는 skip 하므로 무해.
    """
    out: list[str] = []
    for label, vk in _MODIFIER_CHECKS:
        if _is_modifier_pressed(vk) and label not in out:
            out.append(label)
    return out


def _is_modifier_pressed(vk_code: int) -> bool:
    """Win32 GetAsyncKeyState 로 modifier 키 현재 상태 확인 (Ctrl/Shift 등).

    LL hook callback 에서 호출 — 별도 keystate 추적 없이 OS 가 보유한 정확한
    real-time 상태 사용. high-order bit (0x8000) 가 set 이면 현재 눌림 상태.
    non-Windows 환경에서는 False 반환 (Ctrl+Shift+R hotkey 미작동, 정상).
    """
    import sys

    if sys.platform != "win32":
        return False
    try:
        import ctypes

        state = ctypes.windll.user32.GetAsyncKeyState(vk_code)  # type: ignore[attr-defined]
        return bool(state & 0x8000)
    except Exception:
        return False


def _capture_ime_open() -> bool:
    """PR-19k (2026-05-24) — 활성 창의 IME open 상태 캡처.

    Windows: ``ImmGetContext(GetForegroundWindow()) → ImmGetOpenStatus``.
    True 면 한글/CJK IME mode 가 켜진 상태에서 사용자가 keydown 함을 의미.
    transform 단계에서 이 키들을 모아 ``pyperclip.copy(...) + Ctrl+V`` placeholder
    로 변환 → 사용자가 review dialog 에서 실제 텍스트로 교체.

    실패 (non-Windows / IMM 미설치 / hwnd=0 / ImmGetContext NULL / 예외) 시
    False 반환 — 현재 동작 그대로 유지 (False 가 안전 default).
    """
    import sys

    if sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        imm32 = ctypes.windll.imm32  # type: ignore[attr-defined]
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        himc = imm32.ImmGetContext(hwnd)
        if not himc:
            return False
        try:
            return bool(imm32.ImmGetOpenStatus(himc))
        finally:
            imm32.ImmReleaseContext(hwnd, himc)
    except Exception:
        return False


DEFAULT_QUEUE_MAXSIZE = 10000
"""R2 PR-17 마이그레이션 모드 — drain queue 기본 상한.

10000 events ≈ 30+분 정상 입력. 빠른 자동화 스크립트 따라잡기 시 backpressure
완충. full 시 oldest drop + warn.
"""

_DRAIN_JOIN_TIMEOUT_SEC = 5.0
"""stop() 의 drain thread join timeout. 무한 대기 회피 (안전망)."""

_DRAIN_POLL_TIMEOUT_SEC = 0.1
"""drain thread 의 queue.get 타임아웃. _drain_stop_event 체크 주기."""


# 2026-05-23 input 씹힘 원인 진단 history:
# - 옵션 A (WinEvent disable): 무효 → WinEvent 가 원인 X
# - 옵션 B (EFP disable): 무효 → EFP 가 원인 X
# - **실제 root cause**: core/input_hooks.py 의 CallNextHookEx argtypes 미설정 →
#   x64 LL hook lParam (64-bit 포인터) 가 default c_int 마샬링에서 OverflowError →
#   매 mouse/keyboard event 마다 stderr 예외 + propagation 실패. fix: argtypes/restype
#   명시 설정 (InputHookManager._configure_user32_signatures).


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
        stop_hotkey_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        self._hook_manager = hook_manager
        self._opts = opts or TransformOptions()
        self._element_capture_fn = element_capture_fn
        # 2026-05-20 fix: Ctrl+Shift+R 글로벌 stop hotkey. main window 가 minimize
        # 된 상태에서 Qt QShortcut 이 focus 못 받아 작동 X. recorder 의 LL keyboard
        # hook 이 항상 활성이므로 여기서 modifier+R 패턴 직접 감지. callback 은
        # hook thread 에서 호출되므로 UI 측에서 thread-safe (QTimer.singleShot) 처리 필수.
        self._stop_hotkey_callback = stop_hotkey_callback

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

        # 2026-05-20 fix: Ctrl+Shift+R 글로벌 stop hotkey 감지 — keydown 만, R 키만.
        # 트리거 시 callback 호출 + raw event 생성 안 함 (R 키 자체가 녹화에 박히지 않음).
        if (
            event.vk_code == VK_R
            and self._stop_hotkey_callback is not None
            and _is_modifier_pressed(VK_CONTROL)
            and _is_modifier_pressed(VK_SHIFT)
        ):
            try:
                self._stop_hotkey_callback()
            except Exception:
                logger.exception("Recorder: stop_hotkey_callback 예외 (격리됨)")
            return None

        if self._opts.enable_f8_marker and event.vk_code == VK_F8:
            # R2 PR-16w: F8 → marker. transform 이 marker 자체 drop.
            return RawEvent(ts=datetime.now(), kind="marker")
        # PR-19f (2026-05-24): modifier 상태 캡처 → transform 이 hotkey 변환에 사용.
        # PR-19k (2026-05-24): IME open 상태 캡처 → transform 이 한글 IME 입력 시
        # pyperclip + Ctrl+V placeholder 로 변환.
        modifiers = _capture_modifier_state()
        ime_open = _capture_ime_open()
        return RawEvent(
            ts=datetime.now(),
            kind="key",
            vk_code=event.vk_code,
            modifiers=modifiers,
            ime_open=ime_open,
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

            # click event 에 한해 EFP + monitor DPI 비동기 enrichment.
            if raw.kind == "click":
                cx, cy = raw.x or 0, raw.y or 0
                if self._element_capture_fn is not None:
                    try:
                        raw.element_meta = self._element_capture_fn(cx, cy)
                    except Exception:
                        logger.exception(
                            "Recorder: element_capture_fn 예외 (element_meta None 유지)"
                        )
                # R2 PR-18 — 좌표 모니터의 effective DPI 캡처 (재생 시 좌표 진단용)
                try:
                    raw.monitor_dpi = get_dpi_for_point(cx, cy)
                except Exception:
                    logger.exception("Recorder: get_dpi_for_point 예외 (monitor_dpi None 유지)")

            with self._lock:
                if self._session is not None and not self._session.is_stopped:
                    self._session.events.append(raw)
