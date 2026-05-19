# SPDX-License-Identifier: AGPL-3.0-or-later
"""작업 녹화 (Action Recording) Pydantic 모델.

[ADR 0004 + architecture/25-recording-phase-r1-r2.md §2] Recorder 가 캡처한
raw event 를 표현. 변환 (recorder_transform, PR-13) 이전 단계의 데이터 구조.

모델:
- RawEvent — LL hook 으로 캡처된 단일 입력 이벤트
- RecordingSession — start ~ stop 한 녹화 세션 (events 시간순)
- TransformOptions — raw events → Step 변환 옵션 (PR-13 에서 사용)
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

RawEventKind = Literal["click", "key", "scroll", "window_focus", "marker"]
"""캡처 이벤트 종류.

- click: 마우스 좌/우/중 클릭 (single/double)
- key: 키입력 (group_consecutive_keys 활성 시 PR-13 에서 텍스트 그룹핑)
- scroll: 마우스 휠
- window_focus: 활성 창 변경 (R2 PR-16w 에서 SetWinEventHook 활성)
- marker: F8 수동 step 경계 marker (R2 PR-16w 키보드 hook 자동 트리거)
"""


class RawEvent(BaseModel):
    """LL hook 으로 캡처된 raw 입력 이벤트 (변환 전).

    [architecture/25 §2] 시간순 정렬 보장. 모든 종류의 캡처를 단일 모델로 표현
    (kind 필드로 분기). 변환 (recorder_transform) 시 노이즈 필터 + 그룹핑 거쳐
    Step 으로 압축됨.
    """

    ts: datetime
    kind: RawEventKind

    x: Optional[int] = None
    y: Optional[int] = None
    button: Optional[Literal["left", "right", "middle"]] = None
    click_count: int = 1

    key: Optional[str] = None
    text: Optional[str] = None
    modifiers: list[str] = Field(default_factory=list)
    vk_code: Optional[int] = None

    hwnd: Optional[int] = None
    window_title: Optional[str] = None
    exe_name: Optional[str] = None

    element_meta: Optional[dict] = None

    screenshot_path: Optional[str] = None
    is_password_field: bool = False

    wheel_delta: int = 0

    monitor_dpi: Optional[int] = None
    """R2 PR-18 — click 좌표가 속한 모니터의 effective DPI (100%=96).

    drain thread 에서 `core.input_hooks.get_dpi_for_point(x, y)` 로 채움.
    transform 이 fallback `pyautogui.click(x, y)` 코드 생성 시 코멘트로 첨부
    (다른 DPI 환경 재생 시 좌표 차이 진단). non-Windows / 캡처 실패 시 None.
    """

    model_config = {"extra": "allow"}


class RecordingSession(BaseModel):
    """녹화 한 세션 (start ~ stop).

    [architecture/25 §2] events 는 ts 시간순 정렬. PR-13 transform 이 이를
    소비하여 Step 리스트로 변환. target_session_id 는 commit 시 어느 ohdo
    Session 에 step 들을 추가할지 (None 이면 새 세션 생성).
    """

    id: str
    started_at: datetime
    stopped_at: Optional[datetime] = None
    events: list[RawEvent] = Field(default_factory=list)
    target_session_id: Optional[str] = None

    model_config = {"extra": "allow"}

    @property
    def is_stopped(self) -> bool:
        return self.stopped_at is not None

    @property
    def event_count(self) -> int:
        return len(self.events)


class TransformOptions(BaseModel):
    """raw events → Step 변환 옵션 (PR-13 에서 사용).

    [architecture/25 §"PR-13" + 사용자 추가 요청 §7] step 자동 구분 4 신호 옵션:
    (a) auto_window_focus_boundary (R2 활성), (b) enable_f8_marker (R2 활성),
    (c) group_consecutive_keys 종료 시 새 step, (d) idle_boundary_ms 휴지 시 새 step.
    """

    auto_window_focus_boundary: bool = True
    enable_f8_marker: bool = True
    drop_self_window_clicks: bool = True
    drop_empty_space_clicks: bool = False
    group_consecutive_keys: bool = True
    group_key_idle_ms: int = 500
    idle_boundary_ms: int = 3000
    integrate_secrets: bool = True
    auto_user_request: bool = True

    model_config = {"extra": "allow"}
