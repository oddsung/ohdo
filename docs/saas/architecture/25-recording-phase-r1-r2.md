# Architecture: 작업 녹화 (Action Recording) Phase R1+R2 — 데이터 흐름·삽입점

> **상태**: Accepted (2026-05-16 — 사용자 검토 완료 + 메인화면 통합점 / step 구분 강화 / review dialog 편집 강화 추가, PR-11 부터 구현 시작)
> **관련**: [ADR 0004 — 작업 녹화 도입](../decisions/0004-action-recording.md), [ADR 0003 — 시크릿 처리](../decisions/0003-secrets-handling.md)

## 0. 목적

ADR 0004 의 *"녹화 시작 → 평상시 작업 → step 리스트로 변환"* 결정을 구현 단위로 풀어, **삽입점 (어느 파일에 어떻게 박는가)** 과 **PR 분할 (PR-11 ~ PR-18)** 을 명확히 한다.

## 1. 모듈 구조 (신규 + 수정)

```
core/
├── input_hooks.py          ★ 신규 — WH_MOUSE_LL / WH_KEYBOARD_LL / WinEvent 후크
│                             element_picker 가 이 모듈을 import (현재 inline 코드 추출)
├── recorder.py             ★ 신규 — 녹화 lifecycle (start/stop/pause) + raw event buffer
├── recorder_transform.py   ★ 신규 — raw events → Step 변환 (노이즈 필터 + 그룹핑 + win_inspector 위임)
├── recorder_models.py      ★ 신규 — RawEvent, RecordingSession, TransformOptions Pydantic
├── element_picker.py       (수정) — input_hooks 사용으로 전환 (baseline 회귀 0 보장)
├── win_inspector.py        (수정) — generate_*_code 가 recorder 에서도 호출 가능하도록 signature 정리
├── secrets_detector.py     (수정) — recorder 에서 호출하는 entrypoint 추가 (이미 PR-7 의 is_password_field_element 재사용)
└── app_service.py          (수정) — start_recording / stop_recording / commit_recording 메서드 + EventBus 이벤트

ui_v2/
├── recorder_overlay.py     ★ 신규 — 녹화 중 floating click-through status bar (WS_EX_NOACTIVATE)
├── recording_review_dialog.py ★ 신규 — 변환 후 step 리스트 미리보기 + drop/merge/relabel
├── main_window_v2.py       (수정) — 툴바 ⏺ 버튼 + Ctrl+Shift+R 핫키 + recording lifecycle UI

ui/
└── (R1 범위 외 — v1 UI 는 Phase 2.5 후 또는 deprecated)

locale/
├── en.json                 (수정) — recording.* catalog 키 ~40개
└── ko.json                 (수정) — 위 동일

tests/
├── test_core.py            (추가) — test_145 ~ test_165 정도 (21 신규)
└── test_scenarios.py       (추가) — test_74 ~ test_76 정도 (3 신규: notepad/calc/explorer 녹화 시나리오)
```

## 2. 데이터 모델 (recorder_models.py)

```python
from typing import Literal
from datetime import datetime
from pydantic import BaseModel, Field

class RawEvent(BaseModel):
    """LL hook 으로 캡처된 raw 입력 이벤트 (변환 전)."""
    ts: datetime                    # 시간순 정렬
    kind: Literal["click", "key", "scroll", "window_focus", "marker"]
    # 클릭
    x: int | None = None
    y: int | None = None
    button: Literal["left", "right", "middle"] | None = None
    click_count: int = 1            # double click 시 2
    # 키
    key: str | None = None          # vk code → name (예: "a", "Enter", "Tab")
    text: str | None = None         # 그룹핑된 텍스트 ("hello world")
    modifiers: list[str] = Field(default_factory=list)  # ["ctrl", "shift"]
    # 창 포커스
    hwnd: int | None = None
    window_title: str | None = None
    exe_name: str | None = None
    # element (클릭 시점에 EFP 로 잡힌 메타)
    element_meta: dict | None = None  # win_inspector 의 ElementInfo dict
    # 보조
    screenshot_path: str | None = None  # 옵션 (R3)
    is_password_field: bool = False     # ADR 0003 통합 — secrets_detector 가 채움


class RecordingSession(BaseModel):
    """녹화 한 세션 (start ~ stop)."""
    id: str                         # uuid4
    started_at: datetime
    stopped_at: datetime | None = None
    events: list[RawEvent] = Field(default_factory=list)
    target_session_id: str | None = None  # 변환 후 어느 ohdo Session 에 commit 할지


class TransformOptions(BaseModel):
    """raw events → Step 변환 옵션."""
    auto_window_focus_boundary: bool = True
    enable_f8_marker: bool = True
    drop_self_window_clicks: bool = True
    drop_empty_space_clicks: bool = False   # 기본 keep + 경고
    group_consecutive_keys: bool = True
    group_key_idle_ms: int = 500             # 이 시간 이상 비면 새 group
    integrate_secrets: bool = True            # ADR 0003 강 통합
```

## 3. 데이터 흐름 (Phase R1+R2)

```
[1] UI: ⏺ 또는 Ctrl+Shift+R
        ↓
[2] app_service.start_recording(target_session_id)
        ↓
   recorder.start() → input_hooks.install() (LL hooks + WinEvent)
        ↓
   ui_v2.main_window_v2.showMinimized() + recorder_overlay.show()
        ↓
[3] 사용자 작업 — input_hooks 가 callback 으로 raw event emit
        ↓
   recorder.events.append(RawEvent(...))
   ├── click 시: ThreadPool 에서 async EFP → element_meta + is_password_field
   ├── key 시: 포커스 element 가 password field 면 R1 에서 secrets_detector.detect → SecretAdvisoryDialog
   │           (text 는 placeholder `{{secret:label}}` 로 buffer)
   └── window_focus 시: 이전 이벤트 batch 끝 → 새 batch 시작 표시
        ↓
[4] UI: ⏺ 다시 또는 overlay 클릭
        ↓
[5] app_service.stop_recording() → recorder.stop()
        ↓
[6] recorder_transform.transform(recording_session, opts) → list[Step]
   ├── 노이즈 필터 (drop_self_window_clicks, drop_empty_space_clicks)
   ├── 키 그룹핑 (group_consecutive_keys)
   ├── 각 batch → win_inspector.generate_*_code 호출
   │   ├── desktop element → generate_desktop_code
   │   ├── browser element (CDP, R3) → generate_browser_code
   │   └── owner-drawn / fallback → generate_owner_drawn_code (좌표)
   ├── ADR 0003 통합: PW step → get_secret('label') 패턴 삽입
   └── Step.user_request 자동 생성 ("Edit 컨트롤 'Username' 클릭")
        ↓
[7] ui_v2.recording_review_dialog.show(steps)
   사용자: drop / merge / relabel / 순서 변경
        ↓
[8] 확정 → app_service.commit_recording(target_session_id, edited_steps)
   각 step → session_manager.add_step (마지막에 batch 로 추가)
        ↓
[9] 기존 ohdo flow 그대로 — 검토 / 실행 / 편집 가능
```

## 4. 핵심 삽입점 (PR 단위로 매핑)

### PR-11 — LL hook 모듈 신규 작성 (`core/input_hooks.py`) — element_picker 는 그대로 둠

**설계 결정**: element_picker 의 기존 inline hook 코드 ([ui/element_picker.py:2079-2209](../../../ui/element_picker.py)) 는 회귀 테스트 sentinel (test_44~48) 이 까다로워 PR-11 에서는 건드리지 않는다. recorder 만 input_hooks 를 사용. element_picker 의 input_hooks 통합은 Phase R2/R3 의 점진 마이그레이션으로 미룸.

**근거**:
- test_44 sentinel 이 element_picker 의 `_install_mouse_hook` source 안에서 `WH_MOUSE_LL`, `WM_LBUTTONDOWN`, `return 1`, `CallNextHookEx` 등 키워드를 직접 검사 → wrapper 로 바꾸면 자동 fail
- Win32 LL hook 은 같은 thread 에 여러 hook 동시 설치 가능 (call chain) → element_picker hook + input_hooks hook 동시 활성 OK
- element_picker 와 recorder 는 lifecycle 이 동시 활성 X (recorder 시작 시 picker 비활성, ADR 0004 명시)

**대상 파일**:
- 신규: `core/input_hooks.py`

**API**:
```python
# core/input_hooks.py
@dataclass
class MouseEvent:
    type: Literal["move", "lbutton_down", ..., "wheel"]
    x: int; y: int; wheel_delta: int; timestamp_ms: int

@dataclass
class KeyboardEvent:
    type: Literal["keydown", "keyup", "syskeydown", "syskeyup"]
    vk_code: int; scan_code: int; timestamp_ms: int

class InputHookManager:
    """multi-callback dispatch — 여러 callback 등록 가능, 하나라도 True 반환 시 차단."""
    def install_mouse_callback(self, cb: Callable[[MouseEvent], bool]) -> int: ...
    def install_keyboard_callback(self, cb: Callable[[KeyboardEvent], bool]) -> int: ...
    def uninstall_mouse_callback(self, cb_id: int) -> None: ...
    def uninstall_keyboard_callback(self, cb_id: int) -> None: ...
    def uninstall_all(self) -> None: ...
    @property
    def is_mouse_hook_installed(self) -> bool: ...
    @property
    def is_keyboard_hook_installed(self) -> bool: ...

def get_hook_manager() -> InputHookManager:
    """싱글톤."""
```

**회귀 가드 (test_145 ~ test_148)**:
- input_hooks 모듈 존재 + 핵심 dataclass / API 메서드 sentinel (test_145)
- callback 등록/해제 멱등성 + 등록 ID 고유성 + uninstall_all 동작 (test_146)
- callback 예외 발생해도 다른 callback dispatch 영향 X (test_147)
- non-Windows 환경에서 install/uninstall 이 silent noop (test_148)
- element_picker baseline (test_42~48) 그린 유지 — 자동 보장 (안 건드림)

### PR-12 — Recorder lifecycle + raw event buffer (`core/recorder.py`, `recorder_models.py`)

**대상 파일**:
- 신규: `core/recorder.py`, `core/recorder_models.py`

**API**:
```python
class Recorder:
    def __init__(self, hook_manager: InputHookManager, opts: TransformOptions): ...
    def start(self, target_session_id: str | None = None) -> RecordingSession: ...
    def stop(self) -> RecordingSession: ...
    def add_marker(self) -> None: ...  # F8 핫키
    @property
    def is_recording(self) -> bool: ...
    @property
    def event_count(self) -> int: ...
```

**회귀 가드 (test_149 ~ test_152)**:
- start/stop/marker 호출 시퀀스
- buffer 가 시간순 정렬 보장
- stop 후 start 재진입 가능
- 동시 두 번 start 거부

### PR-13 — Raw events → Step 변환 (`core/recorder_transform.py`) + Step 적절한 구분 강화

**대상 파일**:
- 신규: `core/recorder_transform.py`
- 수정: `core/win_inspector.py` (recorder 에서도 호출 가능하도록 signature 정리 — element_meta dict 입력 받기)

**핵심 함수**:
```python
def transform(session: RecordingSession, opts: TransformOptions) -> list[Step]:
    """raw events → Step 변환.

    1. 노이즈 필터 (drop_self_window_clicks, drop_empty_space_clicks)
    2. 키 그룹핑 (group_consecutive_keys + group_key_idle_ms)
    3. 자동 경계 신호 4종 (사용자 추가 요청 §7 반영):
       (a) 창 포커스 전환 (auto_window_focus_boundary, R2 의 PR-16 에서 활성)
       (b) F8 수동 marker (enable_f8_marker, R2 의 PR-16)
       (c) 동일 element 연속 키입력 group 종료
       (d) 의미 단위 휴지 — 이전 클릭 후 N초 (idle_boundary_ms, 기본 3000ms) 휴지면 새 step
    4. 각 batch → win_inspector.generate_*_code (desktop / browser / owner-drawn)
    5. user_request 자동 생성 — element control_type + name 조합 (예: "Edit '사용자 ID' 클릭 후 텍스트 입력")
    6. ADR 0003 통합 (integrate_secrets)
    """
```

**TransformOptions 확장 (사용자 추가 요청 §7)**:
- `idle_boundary_ms: int = 3000` — 의미 단위 휴지 시간 (R1 부터)
- `auto_user_request: bool = True` — element 메타에서 user_request 자동 생성

**회귀 가드 (test_153 ~ test_158)**:
- notepad 시나리오 mock raw events → 예상 step 출력
- 노이즈 필터 동작 (ohdo 자체 창 클릭 drop)
- 키 그룹핑 (연속 입력 → 1 step)
- **idle_boundary_ms 경계** (3초 휴지 후 새 step)
- **user_request 자동 생성** sentinel (control_type + name 포함)
- ADR 0003 통합 (PW field → get_secret)

### PR-14 — AppService 메서드 + EventBus 이벤트

**대상 파일**:
- 수정: `core/app_service.py`

**API**:
```python
class AppService:
    def start_recording(self, target_session_id: str | None = None) -> str:
        """recording_session_id 반환."""

    def stop_recording(self, recording_session_id: str) -> list[Step]:
        """변환된 step 리스트 반환 (아직 commit 안 됨)."""

    def commit_recording(self, target_session_id: str, edited_steps: list[Step]) -> None:
        """편집된 step 리스트를 세션에 일괄 추가."""
```

**EventBus 신규 이벤트**: `recording.started`, `recording.event_count_changed`, `recording.stopped`, `recording.committed`.

**회귀 가드 (test_159 ~ test_161)**:
- start → stop → commit 전체 path
- 미commit 상태에서 두 번째 start 거부
- target_session_id None 일 때 새 세션 자동 생성

### PR-15 — UI: 툴바 + overlay + 미리보기 다이얼로그 + 메인화면 통합 + ADR 0003 통합

**대상 파일**:
- 신규: `ui_v2/recorder_overlay.py`, `ui_v2/recording_review_dialog.py`
- 수정: `ui_v2/main_window_v2.py`:
  - 툴바 ⏺ 버튼 + Ctrl+Shift+R 핫키
  - **D25 빈 상태 화면 (`_show_empty_state`) 에 "🎬 자동 녹화로 만들기" 강조 카드** 추가 (예시 카드 위)
  - **"+ 새 탭" 메뉴 (line 1638) 에 "녹화로 새 세션" 액션** 추가 (새 세션 + 즉시 녹화)
  - recording lifecycle 연결
- 수정: `locale/en.json`, `locale/ko.json` (recording.* catalog ~50개 키 — empty state / menu / overlay / review dialog)

**recorder_overlay 핵심**:
- `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`
- `WindowAttribute.WA_TransparentForMouseEvents` (click-through)
- `setAttribute(Qt.WA_ShowWithoutActivating)` + Win32 `WS_EX_NOACTIVATE`
- 표시: 빨간 ⏺ + 경과 시간 + event count + (R2) batch count
- 클릭 가능 영역: overlay 우측 끝 [중지] 버튼만 (mouse_through 예외)

**recording_review_dialog 핵심 (사용자 추가 요청 §8 반영 — 편집 기능 강화)**:
- step 리스트 (cards) + 각 step 의 user_request / generated_code 미리보기
- **inline 편집 가능 필드**: user_request (제목, double-click), generated_code (Edit 버튼 → 코드 다이얼로그), wait_after_ms (spinbox)
- **drag&drop 순서 변경**: step 카드 위/아래 이동 (기존 main_window_v2 의 step drag 패턴 재사용)
- **multi-select bulk action**: shift-click 여러 step 선택 → 우클릭 → bulk drop / bulk merge
- **자동 분할 / 병합 버튼**: 인접 step 우클릭 → "이전 step 과 합치기" / step 우클릭 → "이 step 분할" (텍스트 그룹 분리)
- **변환 옵션 toggle**: 다이얼로그 상단에 토글 3개 (키 그룹핑 / 빈 공간 클릭 keep / 창 포커스 경계) → 즉시 재변환 (raw events 보존된 상태에서 transform 다시 호출)
- **원본 raw events 보기 (디버그)**: 우하단 [Raw events] 버튼 → 별도 다이얼로그
- **변환 결과 미리 실행 버튼** (선택, R2 후보): 변환된 step 들을 즉시 한 번 재생해보고 commit 여부 결정
- 하단 [확정 (commit)] / [취소] / [Raw events 보기]

**회귀 가드 (test_162 ~ test_167, R1 추가 요청 반영으로 +2 신규)**:
- 툴바 ⏺ 버튼 존재 + Ctrl+Shift+R 핫키 등록 (test_162)
- recorder_overlay 의 WA_TransparentForMouseEvents 속성 (test_163)
- recording_review_dialog 의 i18n catalog 키 누락 0 (test_164)
- ADR 0003 시너지: PW field 녹화 시 advisory 발동 sentinel (test_165)
- **D25 빈 상태에 "🎬 자동 녹화" 카드 sentinel** (test_166)
- **review dialog 의 inline 편집 / 변환 옵션 toggle / bulk action 메서드 존재 sentinel** (test_167)

---

### PR-16 (Phase R2) — 창 포커스 자동 경계 + F8 marker

**대상 파일**:
- 수정: `core/input_hooks.py` (SetWinEventHook(EVENT_SYSTEM_FOREGROUND) 추가)
- 수정: `core/recorder.py` (window_focus event 처리 + F8 marker 등록)
- 수정: `core/recorder_transform.py` (auto_window_focus_boundary 적용)

### PR-17 (Phase R2) — 마이그레이션 모드 (event queue + async EFP)

**대상 파일**:
- 수정: `core/recorder.py` (event queue 비동기 drain)
- 수정: `core/input_hooks.py` (callback 100ms 이내 처리 강제 + queue enqueue 만)
- 신규 테스트 시나리오: pywinauto 스크립트 따라잡기 (test_scenarios.py)

### PR-18 (Phase R2) — DPI / 멀티모니터 안정화 + i18n 완성

**대상 파일**:
- 수정: `core/input_hooks.py` (PROCESS_PER_MONITOR_DPI_AWARE 보장)
- 수정: `core/recorder_transform.py` (모니터별 좌표 보정)
- 수정: `locale/en.json`, `ko.json` (R2 신규 키)

## 5. ADR 0003 통합 데이터 흐름 (재상세)

```
[키입력 캡처 시점 — input_hooks.keyboard_callback]
        ↓
[recorder.handle_key_event]
        ↓
포커스 element 조회 (UIAutomation.GetFocusedElement)
        ↓
secrets_detector.is_password_field_element(focused_element)
        ↓
   ├── False → 정상 buffer (text 누적)
   └── True →
       ├── 누적 중인 평문 text 즉시 abort (메모리에서 제거)
       ├── ui_v2.show_advisory_modal_async() (UI 스레드로 dispatch)
       │     사용자가 라벨 입력 → vault.set(label, captured_text)
       └── RawEvent.text = f"{{{{secret:{label}}}}}"  + is_password_field=True
                ↓
[recorder_transform 시점]
        ↓
is_password_field=True 인 키 그룹 →
    Step.generated_code 가 pyautogui.write(get_secret('label'))
    (ADR 0003 PR-3 의 get_secret helper 그대로 사용)
        ↓
세션 JSON 에 평문 없이 placeholder 만 저장
        ↓
실행 시 ADR 0003 PR-6 의 push_secrets IPC 가 env 주입
```

핵심: **녹화된 자동화 코드에 평문 PW 가 단 한 번도 들어가지 않는다.** 단순 매크로 도구와의 결정적 차이이자 보안 의식 있는 사용자/기업에 어필 가능한 포인트.

## 6. element_picker baseline 회귀 회피 전략

PR-11 이 element_picker 의 LL hook 코드를 input_hooks 로 추출하므로 회귀 우려가 가장 큰 PR. 다음으로 보호:

1. **input_hooks 의 API 는 element_picker 의 기존 패턴을 그대로 wrap** — install/uninstall, callback 시그니처 동일
2. **element_picker baseline 테스트 (test_42~48) 전부 그린 유지** — PR-11 merge 조건
3. **WS_EX_TRANSPARENT 토글 패턴은 element_picker 가 자체 관리** — input_hooks 는 hook 만 제공, picker 의 토글에 관여 X
4. **WH_MOUSE_LL 의 차단·통과 모드** — input_hooks API 에 `block: bool` 인자 추가, picker 는 True, recorder 는 False
5. **테스트 추가**: element_picker 시나리오 + input_hooks 모듈 단위 테스트 (총 4 신규)

## 7. 핫키 처리 — 충돌 회피

- **Ctrl+Shift+R**: 녹화 시작/중지. ohdo 외부 (다른 앱 활성) 에서도 작동 → 글로벌 핫키. `keyboard` 라이브러리 또는 `RegisterHotKey` Win32 API.
- **F8**: 녹화 중에만 marker. 평소엔 일반 키. recorder 가 녹화 활성 중일 때만 가로채고, 비활성 시 통과.
- **F9** (기존 강제 중지) 와 충돌 X.
- **F3** (element picker) 와 충돌 X — picker 와 recorder 동시 활성 X (recorder 시작 시 picker 비활성).

핫키 사용자 설정은 **R2** 의 settings UI 로 미룸 (R1 은 하드코딩).

## 8. PR-11 ~ PR-18 의존성 그래프

```
PR-11 (input_hooks 추출) ─┬─ PR-12 (recorder lifecycle) ─┬─ PR-13 (transform) ─┬─ PR-14 (app_service) ─ PR-15 (UI)
                          │                              │                    │
                          └─ PR-11 회귀 가드 통과 필수    └─ secrets_detector  │
                                                            (이미 있음)         │
                                                                              │
                                                              ── R1 완료 ──────┘
                                                                              │
                                                              PR-16 (window focus) ─┐
                                                              PR-17 (async EFP) ────┼─ R2 완료
                                                              PR-18 (DPI + i18n) ───┘
```

PR-11 만 단독 merge 가능 (element_picker 회귀만 안 나면). PR-12~14 는 PR-11 의존. PR-15 는 PR-12~14 전부 의존. R2 PR 들은 R1 완료 후 시작.

## 9. 측정 가능한 완료 기준

### R1 완료 (PR-11 ~ PR-15)

- [ ] core 144/144 + scenarios 73/73 baseline 무손상
- [ ] 신규 23 unit test (test_145 ~ test_167) + 3 scenario test (test_74 ~ test_76) 그린
- [ ] element_picker baseline (test_42 ~ test_48) 그린 유지
- [ ] notepad 녹화 → 변환 → review → commit → 재생 → 동일 결과 (end-to-end 사용자 검증)
- [ ] ADR 0003 시너지: PW field 녹화 → advisory → `get_secret()` 변환 시나리오 통과
- [ ] D25 빈 상태 화면에 "🎬 자동 녹화" 카드 노출 (사용자 추가 요청 §6)
- [ ] review dialog 의 inline 편집 / 변환 옵션 toggle / bulk action 작동 (사용자 추가 요청 §8)
- [ ] i18n catalog `recording.*` (en + ko) 누락 0

### R2 완료 (PR-16 ~ PR-18)

- [ ] R1 의 모든 baseline 무손상
- [ ] 신규 ~10 unit test + 2 scenario test (pywinauto / Power Automate Desktop 마이그레이션)
- [ ] DPI 100/125/150/175/200% 멀티모니터 환경 좌표 정확도 ±2px 이내
- [ ] 마이그레이션 모드: 1초당 10 events 의 빠른 입력 따라잡기 (drop 율 ≤ 5%)

## 10. R3 (후순위) 미리보기

R3 는 R1+R2 실측 후 우선순위 결정. 후보:

- **AI 후처리**: 변환된 raw step 을 AI 에게 *"의미 단위로 묶고 변수화해줘"* → cleaner 코드
- **브라우저 CDP 후킹**: Chrome 자동 attach, 브라우저 안 클릭/입력 캡처
- **screenshot OpenCV fallback**: element 못 잡힌 케이스, 재생 시 이미지 매칭
- **Power Automate Desktop import** (반대 방향 마이그레이션): .pad 파일 → Step 리스트

---

## 사용자 검토 후 확정 사항

ADR 0004 §"미결정 사항" 5개 결정 후 본 문서의 PR 분할 / 핫키 / 기본값을 최종 갱신한다.
