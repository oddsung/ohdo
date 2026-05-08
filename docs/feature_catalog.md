# ohdo 데스크톱 UI 기능 카탈로그

> **목적**: 현재 PyQt6 데스크톱 UI 의 모든 기능/위젯/인터랙션을 redesign 의 baseline 로 기록한다.
> 새 UI 가 이 카탈로그의 모든 항목을 동등하게 cover 하면 회귀 없음으로 판정.
>
> **마지막 업데이트**: 2026-05-05 (Phase 2.5 Initial 블럭 단독 실행까지 반영)
>
> **사용법**: redesign 와이어프레임 작성 시 항목별 cover 여부 체크. 새 UI 에서 의도적으로 제거하는 기능은 §11 결정 로그에 사유 기록.

---

## 1. 메인 윈도우 전체 레이아웃

```
┌─────────────────────────────────────────────────────────────┐
│ 메뉴바 (파일/실행/설정/도움말)    툴바 (새세션/AI엔진/실행/검사)│
├──────────┬───────────────────┬──────────────────────────────┤
│  세션    │    대화 패널      │    코드 + 블럭 뷰어         │  상단
│  목록    │   (ChatPanel)     │    (CodeViewer)             │  splitter
│ (좌 1/6) │   (중 2.5/6)      │    (우 2.5/6)               │  ratio 7
│          │                   │    [Tab1: 코드뷰]            │
│          │                   │    [Tab2: 블럭뷰]            │
├──────────┴───────────────────┴──────────────────────────────┤
│   콘솔/로그 패널 (4개 탭: 전체 / 프롬프트 / 실행 / AI)     │  하단 ratio 3
└─────────────────────────────────────────────────────────────┘
                          상태바
```

**계층 구조**:
```
MainWindow
├── MenuBar + ToolBar + StatusBar
└── CentralWidget (VBoxLayout)
    └── vertical_splitter (Vertical)
        ├── main_splitter (Horizontal, stretch=7)
        │   ├── SessionListPanel  (1/6, 200px 고정)
        │   ├── ChatPanel         (2.5/6, 450px)
        │   └── CodeViewer        (2.5/6, 450px)
        └── ConsolePanel          (stretch=3, 250px)
```

**테마**: 다크 (Catppuccin Mocha — 배경 `#1e1e2e`, 텍스트 `#cdd6f4`). settings 에서 light/dark 토글, 폰트 크기 8~20px.

---

## 2. 메뉴바 / 툴바 / 단축키

### 메뉴 항목
| 메뉴 | 항목 | 단축키 | 비고 |
|------|------|--------|------|
| 파일 | 새 세션 | Ctrl+N | RPA_YYYYMMDD... 자동 명명 |
| 파일 | 세션 불러오기 | Ctrl+O | 목록 새로고침 |
| 파일 | 세션 저장 | Ctrl+S | 현재 세션 즉시 저장 |
| 파일 | 워크플로우 내보내기 | — | main.py + requirements.txt + README.md + run.bat |
| 파일 | 종료 | Ctrl+Q | closeEvent → 세션 저장 + 커널 정리 |
| 실행 | ⛔ 실행 강제 중지 | F9 | 전역 (ApplicationShortcut, 포커스 무관) |
| 설정 | 환경 설정 | — | EnvironmentSetupDialog |
| 도움말 | 정보 | — | 앱 소개 |

### 툴바 버튼
- 📄 **새 세션**
- **AI 엔진 드롭다운** (현재 엔진 선택 + "미설치" 상태 표시)
- ▶ **전체 실행** (코드 뷰 활성 시 Ctrl+R 매핑은 미정)
- 🔍 **윈도우 검사** (Windows 전용, pywinauto 필요)

### 컨텍스트 단축키
- ChatPanel: **Enter** = 전송, **Shift+Enter** = 줄바꿈
- 요소 칩: **Del / Backspace** = 칩 삭제
- ElementPicker overlay: **F3** = 3초 일시정지/복귀, **ESC** = 취소
- ScreenCapture overlay: **드래그** = 영역 선택, **ESC** = 취소

---

## 3. 세션 목록 패널 (`SessionListPanel`)

```
┌─ 📋 세션 목록 ──────────────┐
│ 🔍 세션 검색...            │
│ ┌──────────────────────────┐│
│ │ ▶ 🌐 RPA_20260505...     ││  ← 활성: 좌측 ▶ + 파란 배경
│ │      (3/5 steps)         ││
│ │   🖥️ 메모장 자동화        ││
│ │      (2/2 steps)         ││
│ └──────────────────────────┘│
│ [🗑 삭제]                  │
└────────────────────────────┘
```

**시그널**: `session_selected(id)` (더블클릭) / `session_delete_requested(id)`.

**프로젝트 타입 표시**: 🌐 웹 / 🖥️ 데스크톱 (세션 메타 기반).

**검색**: 제목 부분 일치, 대소문자 무관, 실시간 필터.

**삭제**: "세션을 삭제하시겠습니까?" 확인 → `session_manager.delete_session()`.

---

## 4. 대화 패널 (`ChatPanel`)

```
┌─ 💬 대화 및 작업 요청 ──────┐
│  [스크롤 영역 - 80%]        │
│  👤 You: ...                │  파란 #313244 좌측
│         🤖 AI: ...          │  초록 #1e1e2e 우측
│  ⚙️ System: 캡처 완료       │  노란
│  ...                        │
├────────────────────────────┤
│ 📷 캡처  🎯 요소 선택      │
│ [🎯 [Button] 제출 ✕] [🎯..] │ ← 요소 칩 (선택 시에만 표시)
│ ┌────────────────┬────────┐│
│ │ 자동화할 작업.. │  전송 ▶││  Shift+Enter=줄바꿈
│ │                │  (80×70)││  AI 생성 중: ⏹ 중지 (빨강)
│ └────────────────┴────────┘│
└────────────────────────────┘
```

**메시지 역할별 스타일**:
- 👤 You: 파란색, 좌측 정렬, `#313244` 배경
- 🤖 AI: 초록색, 우측 정렬, `#1e1e2e` 배경
- ⚙️ System: 노란색 (캡처/오류 안내)

**요소 칩** (`ElementChip`):
- 형식: `🎯 [control_type] name[:28]` + ✕ 삭제 버튼
- 다중 선택 가능. 메시지 전송 시 `📌 선택된 요소: [Type] Name, ...` 자동 prefix.

**전송 버튼 토글** (`set_generating`):
- False (기본): 전송 ▶, 파란 #89b4fa, 입력 활성
- True (AI 처리 중): ⏹ 중지, 빨강 #f38ba8, 입력/캡처/요소 선택 비활성

**시그널**: `message_sent(str)`, `capture_requested()`, `element_pick_requested()`, `cancel_requested()`.

---

## 5. 코드 + 블럭 뷰어 (`CodeViewer` — 2개 탭)

### 5.1 코드 뷰 탭 (`StepCard`)

```
┌─ ▼ 📝 Step 3: 검색창 클릭 ────────────────┐
│  ⬆ ⬇ 🔄 Diff ➕ 삽입 ✏️ 수정 🗑️ 삭제   │  헤더 액션
├──────────────────────────────────────────┤
│ [캡처 이미지 — 선택 시 표시]               │
│ ┌────────────────────────────────────┐  │
│ │ 1  from selenium import webdriver  │  │  코드 에디터
│ │ 2  driver = webdriver.Chrome()     │  │  (읽기 전용 또는
│ │ 3  driver.get("https://...")       │  │   마지막 step 만 편집)
│ │ ...                                │  │
│ └────────────────────────────────────┘  │
│ ════ ResizeHandle (높이 드래그) ════    │
└──────────────────────────────────────────┘
```

**액션 버튼**:
- ⬆ / ⬇: 스텝 위/아래 이동
- 🔄 Diff: 이전 스텝과 비교 뷰 토글 (+ 초록 추가, - 빨강 삭제)
- ➕ 삽입: 이 스텝 다음에 새 스텝 삽입
- ✏️ 수정: 편집 모드 (마지막 스텝만)
- 🗑️ 삭제: 이 스텝 삭제

**편집 모드**:
- 진입: 높이 400px, 테두리 2px 파란 #89b4fa, 자동 포커스
- 종료 (focusOut/Esc): 높이 200px, 읽기전용, `step_code_edited(step_id, new_code)` emit

### 5.2 블럭 뷰 탭 (`BlockCard` × 3 종류 + `BlockViewWidget` 컨테이너)

```
┌─ 🧱 Colab 블럭 뷰 — 스텝별 델타 코드 ──┐
│         ● 커널 활성 (3개 완료)        │  툴바
│                  [🔄 커널 재시작]      │
├───────────────────────────────────────┤
│ ┌─ ▼ 📦 라이브러리 블럭 ────────┐     │  step_id=0, 파란
│ │ ✏️ 수정  ▶ 여기서 실행        │     │  imports + 헬퍼
│ │ from selenium import...       │     │
│ └──────────────────────────────┘     │
│ ┌─ ▼ 🎬 Initial 블럭 ──────────┐     │  step_id=-1, 노랑
│ │ ✏️ 수정  ⏯ 단독  ▶ 여기서   │     │  변수/초기값 (Phase 2.5
│ │ driver = Chrome()             │     │   ⏯ 단독 = driver 재초기화)
│ └──────────────────────────────┘     │
│ ┌─ ▼ 📋 Step 1: 페이지 열기 ✅─┐     │  step_id>0
│ │ ✏️ 수정 🗑️ ⏯ 단독 ▶ 여기서  │     │
│ │ driver.get("https://...")     │     │
│ │ ⏱ 대기시간 [500] ms ☑ 기본값│     │  Wait 행 (step>0만)
│ └──────────────────────────────┘     │
│ ┌─ ▼ 📋 Step 2: 검색 🔄 ──────┐     │
│ │ ...                           │     │
│ └──────────────────────────────┘     │
└───────────────────────────────────────┘
```

**3 종류 BlockCard**:

| 종류 | step_id | 테두리 | 아이콘 | 단독 버튼 | 코드 내용 |
|------|---------|--------|--------|-----------|-----------|
| 라이브러리 | 0 | 파란 #89b4fa | 📦 | ❌ (한 번만 실행되는 setup) | imports + 공통 함수 |
| Initial | -1 | 노랑 #f9e2af | 🎬 | ✅ (Phase 2.5 — driver 재초기화) | 모듈 레벨 변수/setup |
| Step | >0 | 어둠 #313244 | 📋 | ✅ | 스텝별 델타 코드 |

**헤더 상태 아이콘**: ✅ 성공 / ❌ 실패 / 🔄 실행 중 / "" 미실행.

**액션 버튼별 동작**:
- ✏️ 수정 → `block_code_edited(step_id, new_code)` (모든 카드)
- 🗑️ 삭제 → `block_delete_requested(step_id)` (step>0 만)
- ⏯ 단독 → `run_single_requested(step_id)` (step>0 + step==-1)
- ▶ 여기서 실행 → `run_from_here_requested(step_id)`
  - step_id=0: 커널 재시작 (`kernel_reset_requested`)
  - step_id>0: N부터 끝까지 (`run_from_step_requested`)
  - step_id=-1: 현재 미정의 동작 (잠재 회귀 영역 — redesign 시 정리)

**Wait 행** (step>0 카드 하단, 점선 구분선 위):
- "⏱ 대기시간 [N] ms" SpinBox
- "기본값 사용" 체크박스
- override 시 주황 #f9e2af 테두리, 기본값 시 회색 #6c7086
- 상위 BlockViewWidget 툴바에 세션 default SpinBox + "글로벌 사용" 체크박스 (sentinel step_id=0)
- **3 단계 우선순위**: `step.wait_after_ms` > `session.settings.step_delay_ms` > `settings.execution.step_delay_ms`

**Python 구문 강조** (`PythonHighlighter`):
- 키워드: 보라 #cba6f7 굵음
- 문자열: 초록 #a6e3a1
- 숫자: 주황 #fab387
- 주석: 회색 #6c7086 기울임
- 함수 호출: 파란 #89b4fa

### 5.3 코드 편집 desync 4중 안전장치 ([handoff §4.8](handoff.md))

사용자가 어느 뷰에서 수정해도 일관 동기화 — 한 가지 빠지면 회귀.
1. `_on_block_step_code_edited`: step_code + generated_code 동시 갱신 (import 보존)
2. `_on_step_code_edited`: generated_code + 재계산 step_code/step_imports
3. `extract_step_delta_code` 우선순위 (0): `manually_edited=True` + step_code 무조건 우선
4. 수정 후 반대 뷰 즉시 재렌더링 (`_refresh_code_viewer` / `_refresh_block_view`)

---

## 6. 콘솔/로그 패널 (`ConsolePanel`, 4 탭)

| 탭 | 내용 |
|----|------|
| 📟 전체 로그 | 모든 메시지 |
| 💬 프롬프트 | AI 대화 + 프롬프트 상세 (마크다운 스타일 구분선) |
| ▶ 실행 | 코드 실행 로그 |
| 🤖 AI 통신 | AI 엔진 통신 로그 |

**로그 레벨 색상**:
- DEBUG: 회색 #6c7086
- INFO: 초록 #a6e3a1 (기본)
- WARNING: 노랑 #f9e2af
- ERROR: 빨강 #f38ba8
- PROMPT: 파랑 #89b4fa
- AI: 보라 #cba6f7

**타임스탬프**: `[HH:MM:SS] [LEVEL] msg`

**프롬프트 상세 로그** (`log_prompt_detail`): `═══...` 구분선 + 엔진/응답시간/토큰/이미지 첨부 메타 + 사용자 요청 + 전송 프롬프트 (앞 1000자/뒤 500자) + AI 응답 + 추출 코드.

**컨텍스트 메뉴**: 복사 (Win32 API 폴백 포함 — RDP/VM 환경 호환).

**Cap**: 최대 5000줄, 초과 시 1회 경고.

---

## 7. 화면 캡처 오버레이 (`ScreenCaptureOverlay`)

**용도**: AI 에 첨부할 영역 캡처.

**UI**:
- 전체 화면 반투명 오버레이 (검은색 120 알파, 선택 영역 외)
- 선택 테두리: 밝은 파란색 (0, 170, 255)
- 크기 라벨: "W × H"
- 안내 텍스트: "드래그하여 캡처 영역을 선택하세요  |  ESC: 취소"
- 커서: CrossCursor

**워크플로우**:
1. ChatPanel `📷 캡처` → MainWindow `_on_capture_request`
2. 메인 윈도우 최소화 (400ms 지연)
3. 윈도우 검사 자동 (포그라운드 창 분석)
4. ScreenCaptureOverlay → 사용자 드래그
5. `capture_completed(PIL.Image)` → 이미지 저장 + pending_images 추가
6. ChatPanel.set_capture_status: "📷 캡처 완료: filename (W×H)"

---

## 8. UI 요소 피커 (`ElementPickerOverlay`, Windows 전용)

**용도**: AI 에 보낼 자동화 대상 요소 선택.

**UI**:
- 전체 화면 투명 오버레이
- 마우스 아래 요소 빨간 사각형 하이라이트 (100ms 주기)
- 툴팁 라벨: control_type, name, automation_id, rect

**시그널**:
- `element_picked(dict)`: control_type, name, automation_id, rect, class_name, hwnd, browser
- `pick_cancelled()` (ESC)

**F3 일시정지**:
- 3초 카운트다운 (메뉴 열려있을 때 캡처용)
- 카운트다운 라벨 화면 중앙

**파라미터** (settings 의 🎯 요소 선택 탭):
- `uia_max_depth`: 1~50 (기본 15)
- `uia_time_budget_ms`: 30~2000 (기본 150)
- `cdp_enabled`: bool (기본 False, Chrome DOM context — 500ms~1초 추가)

**EFP 토글 baseline** ([handoff §4.1](handoff.md)): IUIAutomation::ElementFromPoint 호출 동안만 `WS_EX_TRANSPARENT` 토글 (try/finally), walker 들은 토글 밖. F3 wait 시 항상 TRANSPARENT 켬 + WH_MOUSE_LL hook 으로 click 차단.

---

## 9. 윈도우 피커 (`WindowPickerOverlay`, Windows 전용)

**용도**: 대상 윈도우 선택 → WindowInspector 로 컨트롤 트리 분석 → AI 컨텍스트 추가.

**UI**: 마우스 위치의 최상위 윈도우에 빨간 테두리 (3px). 클릭/Enter 선택, ESC 취소.

**워크플로우**:
1. 툴바 "🔍 윈도우 검사" → pywinauto 확인 (미설치 시 경고)
2. 메인 윈도우 최소화 (400ms 지연)
3. 사용자 윈도우 클릭
4. `WindowInspector.inspect_window()` (max_depth=3, max_controls=50)
5. UIInspectionHandler.finish_inspect → AI 컨텍스트 추가

---

## 10. 다이얼로그

### 10.1 환경 설정 (`EnvironmentSetupDialog`, 3페이지 스택)

**Page 0: 스캔 중**
- 🔍 아이콘 (48pt) + 진행률 바
- 상태 텍스트: "환경 스캔 준비 중..." → "Python 경로 탐색 중..." → "스캔 완료!"

**Page 1: 스캔 결과**
- 📋 시스템 정보 (OS, 컴퓨터 이름, Python 버전)
- 🐍 Python 경로 드롭다운 + 📁 경로 찾기
- 📦 패키지 상태 테이블 (패키지 / 상태 ✅❌ / 버전 / 필수)
  - 📥 누락 패키지 설치 (누락 시만 표시)
- 🤖 Gemini CLI 상태 (✅ 설치됨 / ❌ PATH 에 없음)

**Page 2: 수동 설정** (자동 스캔 실패 시)
- Python 경로 입력 + 📁 찾아보기 + ◀ 뒤로 / ✅ 검증 및 적용

**하단 버튼**: 건너뛰기 / 🔄 재스캔 / ⚙️ 수동 설정 / ✅ 적용 및 시작 (필수 패키지 + Gemini CLI 충족 시 활성)

### 10.2 일반 설정 (`SettingsDialog`, 7 탭)

| 탭 | 항목 |
|----|------|
| 🤖 AI 엔진 | 엔진 선택 / 응답 타임아웃 30~600s (180) / 최대 재시도 0~10 (3) |
| 📷 이미지 | 캡처 품질 10~100% (60) / 최대 가로 640~3840 (1280) / 흑백 변환 |
| ▶ 실행 | 스텝 간 대기 0~5000ms (500) / 에러 자동 스크린샷 / 샌드박스 모드 / 비주얼 피드백 |
| 🎯 요소 선택 | UIA 최대 깊이 1~50 (10) / UIA 시간 예산 30~2000ms (150) / Chrome CDP |
| 💬 프롬프트 | 시스템 프롬프트 QTextEdit (Consolas 10pt) |
| 🎨 UI | 테마 dark/light / 폰트 크기 8~20 (11) / 콘솔 패널 표시 |
| 🔧 환경 | Python 경로/버전/호스트/마지막 스캔 + 패키지 상태 + 🔄 재스캔 / 🐍 경로 변경 |

**버튼**: 취소 / 적용 (파란 굵음).

---

## 11. 데이터 흐름 요약

### AI 호출 path
```
ChatPanel.message_sent
  → MainWindow._on_user_message
  → AICallHandler.on_user_message
  → call_ai_thread (백그라운드)
  → signals.ai_response_ready
  → MainWindow._on_ai_response
  → ChatPanel.add_ai_message + session.add_step + CodeViewer.add_step + _refresh_block_view
```

### 블럭 실행 path
```
사용자 ▶ 클릭
  → BlockViewWidget.run_from_step_requested(N)
  → MainWindow._on_run_from_step
  → BlockExecutionHandler.on_run_from_step
  → _run_blocks_thread (백그라운드)
  → ExecutionKernel.execute_block → signals.block_step_done
  → MainWindow._on_block_step_done (UI 갱신)
  → 모두 완료 → signals.blocks_finished → on_blocks_finished (run/stop 자동 리셋)
```

### Initial 블럭 단독 path (Phase 2.5, [handoff §4.9](handoff.md))
```
Initial 카드 ⏯ 단독
  → run_single_requested(-1)
  → run_single_step_requested(-1)
  → BlockExecutionHandler.on_run_single_step
  → INITIAL_BLOCK_STEP_ID 분기 → on_run_initial_block
  → _run_initial_block_thread (라이브러리 미초기화 시 자동 선행)
  → kernel.execute_block(initial_code, step_id=-1)
  → blocks_finished
```

---

## 12. 비기능 요구사항 (현재 cover 중)

- **다중 세션 동시 보유**: `_kernels` 딕셔너리 — 세션 전환 시 커널 유지
- **세션 영속화**: `data/sessions/{session_id}/session.json`
- **캡처 영속화**: `data/sessions/{session_id}/captures/*.png`
- **로그 영속화**: 콘솔 패널 + (선택) 파일 로그
- **F9 강제 중지**: CodeSandbox / ExecutionKernel / 워크플로우 3 path 모두 처리
- **Win11 ForegroundLock 우회** ([handoff §4.5](handoff.md)): subprocess SendInput 후 `AllowSetForegroundWindow(parent_pid)` 호출 보장
- **DPI Awareness**: pywinauto/pyautogui 좌표 일치
- **관리자 권한 앱 제어**: pyautogui 좌표 클릭 (UIPI 우회)
- **UWP 앱 호환** (Windows 11 메모장 등): `Desktop().window()` 방식
- **PySide6 포트 동기화**: `pyside6_port/` 별도 동작, 같은 `data/` junction 공유

---

## 13. Redesign 결정 사항

> 사용자와 합의된 redesign 방향. 새 UI 가 이 결정들을 반영해야 함.

### ✅ 결정됨 (2026-05-05)

#### D1. 코드 뷰 ↔ 블럭 뷰 통합
- **결정**: 두 탭을 하나의 통합 뷰로 합침. 블럭 뷰 (Colab 스타일) 가 시각적 모델로 우월하므로 그쪽을 베이스로 함.
- **현재**: `CodeViewer` 가 QTabWidget 으로 [코드 뷰] / [블럭 뷰] 두 탭 분리.
- **새 UI**: 단일 스크롤 뷰. 라이브러리/Initial/Step 카드 세로 나열. 각 카드에서 코드 편집/실행/Diff/캡처 모두 처리.
- **영향**:
  - StepCard 와 BlockCard 의 기능 union 필요 (StepCard 의 Diff 뷰, 캡처 이미지 표시 → BlockCard 에 흡수).
  - 코드 편집 desync 4중 안전장치 (§5.3) 가 단순화 가능 — 한 뷰만 유지하면 두 필드 동시 업데이트 부담 ↓.
  - tab 전환 학습 비용 제거.

#### D2. AI 어댑터 확장 — OpenAI 호환 API 등록
- **결정**: Gemini CLI 외에 **OpenAI 호환 API** 어댑터 추가. base_url + api_key 입력 받음.
- **호환 서비스 (단일 어댑터로 모두 지원)**:
  - 클라우드: OpenAI, DeepSeek, Groq, Together AI, OpenRouter, Mistral, Perplexity, Fireworks 등
  - 로컬: Ollama (`localhost:11434/v1`), LM Studio (`localhost:1234/v1`), vLLM, llama.cpp server
- **장기 계획**: 사용자가 자기 API 키 BYO (Bring Your Own) vs. ohdo 가 크레딧 SaaS — **미정**. 어떤 방향이든 OpenAI 호환 어댑터는 둘 다에 활용 가능 (BYO 면 직접 입력, SaaS 면 ohdo 가 대리 호출).
- **영향**:
  - `core/adapters/openai_compat_adapter.py` 신규 — `httpx` 또는 `openai` Python SDK 사용.
  - `ADAPTER_REGISTRY` 에 `"openai_compat"` 등록.
  - 설정 다이얼로그 🤖 AI 엔진 탭에 추가 입력란: base_url, api_key, model (자유 입력 — 서비스마다 다름).
  - 프리셋 드롭다운: "OpenAI / DeepSeek / Groq / OpenRouter / Ollama (local) / 직접 입력" — base_url 자동 채움.
  - api_key 저장 위치: settings.json 평문 vs. OS keyring (Windows Credential Manager / macOS Keychain). **결정 필요**.

#### D3. 요청-코드 step 단위 매칭 표시
- **결정**: 사용자 요청 (자연어) 과 그 요청으로 생성된 코드를 같은 step 안에서 함께 보임. ChatPanel ↔ CodeViewer 의 좌우 분리를 step 카드 하나에 통합.
- **현재**: ChatPanel (좌) 에 사용자 메시지 + AI 응답 텍스트, CodeViewer (우) 에 생성 코드. 둘이 분리돼 어떤 메시지가 어떤 코드를 만들었는지 시각 매칭 어려움.
- **새 UI**: 각 BlockCard (Step 카드) 가 다음을 모두 표시:
  ```
  ┌─ ▼ 📋 Step N ──────────────────────────────────┐
  │ 👤 사용자 요청: "검색창에 '삼성전자' 입력하고 검색"     │  ← 신규 영역
  │ 🤖 AI 설명: "Selenium 으로 검색창 찾아 입력 후 ..."  │  ← 신규 영역 (옵션, 접힘)
  │ ─────────────────────────────────────────────  │
  │ ✏️ 수정 🗑️ ⏯ 단독 ▶ 여기서 실행                │
  │ ┌───────────────────────────────────────────┐  │
  │ │ search_box = driver.find_element(...)     │  │  ← 기존 코드 영역
  │ │ search_box.send_keys("삼성전자")           │  │
  │ └───────────────────────────────────────────┘  │
  │ ⏱ 대기시간 [500] ms ☑ 기본값                  │
  │ 📷 캡처 [썸네일]                                │  ← 옵션
  └─────────────────────────────────────────────────┘
  ```
- **영향**:
  - Session/Step 데이터 모델: `step.user_request: str` 필드 추가 (이미 있을 수 있음 — 확인). `step.ai_description: str` (AI 응답 본문 텍스트, 코드와 분리 저장).
  - 스토리지 마이그레이션: 기존 세션 JSON 호환성 — `user_request` 없으면 빈 문자열 fallback.
  - ChatPanel 의 역할 축소: "현재 대화 입력" 만 담당. 과거 대화 history 는 step 카드 안에 분산.
  - 또는 ChatPanel 을 timeline view 로 유지하면서 step 카드와 양방향 link (클릭 시 해당 step 으로 스크롤).

### ✅ 추가 결정됨 (2026-05-05, 13건 일괄)

| # | 항목 | 결정 |
|---|------|------|
| D4 | 다중 세션 UX | **탭** (브라우저 스타일). 좌측 세션 목록은 사이드 토글로. D3 통합 step 카드가 화면 많이 차지하므로 탭 모델이 future-proof. SaaS 클라우드 동기화와도 자연스러움. |
| D5 | 콘솔 패널 위치 | **VS Code 스타일 토글** (Ctrl+\`). 기본 닫힘, 열릴 때만 하단 25%. 4개 탭 (전체/프롬프트/실행/AI) 유지. |
| D6 | 요소 칩 위치 | **인라인** — 입력 시점엔 입력창 위, 전송 후엔 step 카드 안에 metadata 로 보존. "이 step 의 컨텍스트가 뭐였나" 추적 가능. |
| D7 | 단축키 체계 | 표준 셋 추가: **Ctrl+Enter 전송 / Ctrl+R 실행 / Ctrl+, 설정 / Ctrl+K 명령 팔레트 / F5 재실행**. 추가는 사용자 피드백 기반. |
| D8 | Command palette | **도입** (Ctrl+K). 모든 액션을 검색으로 호출. 메뉴/툴바 의존도 ↓. |
| D9 | 상태 알림 | **토스트 + QMessageBox 병행**. 정보성은 토스트 (floating, 자동 사라짐), confirm/destructive 만 QMessageBox. statusBar 는 영구 상태만. |
| D10 | 다크/라이트 테마 | **시스템 자동 감지 + 수동 override**. settings.json `theme: "auto" | "dark" | "light"`. |
| D11 | Initial 블럭 "여기서 실행" 의미 | **제거**. Initial 카드는 "⏯ 단독" 버튼만 노출 (Phase 2.5 와 일치). |
| D12 | 캡처/요소 선택 워크플로우 | **유지**. 메인 윈도우 lower → 오버레이 → 복귀 — Win11 ForegroundLock 우회 (§4.5) 와 검증된 path. |
| D13 | 모바일/태블릿 (Phase 3 웹) | **데스크톱뷰 우선 + 모바일은 read-only viewer**. 디자인 토큰만 공유. |
| D14 | 온보딩 / 첫 실행 | **3단계 wizard**: (1) 환경 점검 (재활용) → (2) AI 엔진 선택 (Gemini CLI 자동 감지 + OpenAI 호환 옵션) → (3) "첫 자동화 만들기" 튜토리얼 (메모장 한글 입력). Skip 가능. |
| D15 | API key 저장 위치 (D2 후속) | **v1.0 OSS 공개까지는 settings.json 평문 + .gitignore**. SaaS 진입 시점에 keyring 도입. 결정 정책: BYO 모델 데스크톱은 평문 OK (사용자 PC 격리), SaaS 모드면 ohdo 가 키 관리. |
| D16 | 장기 AI 모델 (D2 후속) | **BYO 우선 + SaaS 진입 시 hidden 프리셋 추가**. 결정 시점 미루기. 현 BYO 어댑터에 'proxy' base_url 추가만으로 SaaS 모드 가능. |

→ 미결정 항목 0건. 와이어프레임 작업 진입 가능.

### ✅ 와이어프레임 도중 발견 — 추가 결정 (2026-05-05, 10건 + onboarding)

| # | 항목 | 결정 |
|---|------|------|
| D17 | Step 카드의 사용자 요청 영역 클릭 → 재생성 트리거 | **토스트 confirm** ("이 요청으로 다시 생성?") + 5초 안에 응답 없으면 cancel. AI 호출 비용 보호. |
| D18 | wait 드롭다운 옵션 | **0 / 200 / 500 / 1000 / 2000 ms + 사용자정의** (5개 프리셋 + 사용자 입력). 현재 SpinBox 보다 빠른 UX. |
| D19 | AI 설명 영역 default 상태 | **첫 1~2 줄만 preview**, ▼ 클릭으로 전체. 카드 길이 통제 + 코드 집중. |
| D20 | 사이드바 default 상태 | **사용자 마지막 상태 기억** (`settings.ui.sidebar_collapsed`). |
| D21 | 새 탭 (+) 클릭 동작 | **메뉴** (새로 만들기 / 불러오기 / 템플릿). 첫 사용자 안내 효과. |
| D22 | 세션 탭 우클릭 메뉴 | **4 항목**: 닫기 / 이름 변경 / 복제 / 내보내기. |
| D23 | Step 카드 reorder | **drag-and-drop + ⬆⬇ 버튼 fallback** 둘 다. 접근성용 fallback 유지. |
| D24 | Initial 블럭 표시 조건 | **자동 추출 결과 비어있지 않을 때만** (현재 동작 유지). 빈 카드 노출 회피. |
| D25 | 메인 뷰 빈 상태 (세션 있지만 step 0개) | **일러스트 + "첫 요청을 입력해 자동화를 시작하세요" 안내 + 예시 카드 3개**. |
| D26 | 다크/라이트 토글 위치 | **settings 탭 만** (탭바 아이콘 X). 자동 감지 default 라 자주 변경 X. |
| onboarding | 추천 시나리오 (D14 wizard Step 3) | **메모장 한글 입력 / 네이버 검색 / 빈 세션 시작** 3개. |

---

---

## 14. 변경 로그

| 날짜 | 변경 |
|------|------|
| 2026-05-05 | 초안 작성 — Phase 2.5 Initial 블럭 단독 실행까지 반영 |
| 2026-05-05 | §13 결정 3건 추가: D1 코드+블럭 뷰 통합, D2 OpenAI 호환 어댑터, D3 요청-코드 step 매칭 표시. 사용자 결정 대기 항목 12 → 13 (api_key 저장 위치 추가) |
| 2026-05-05 | §13 미결정 13건 일괄 결정 (D4~D16): 다중 세션 탭 / 콘솔 토글 / 인라인 요소 칩 / 단축키 5종 / Command palette / 토스트 + QMessageBox / 시스템 테마 자동 / Initial 여기서 실행 제거 / 캡처 워크플로우 유지 / 웹은 데스크톱 우선 / 3단계 wizard / settings.json 평문 → SaaS 시 keyring / BYO 우선 + SaaS hidden 프리셋. 미결정 0건. |
| 2026-05-05 | §13 와이어프레임 도중 발견 10건 + onboarding 일괄 결정 (D17~D26): 사용자 요청 클릭 토스트 confirm / wait 드롭다운 5+사용자정의 / AI 설명 1~2줄 preview / 사이드바 last state 기억 / + 탭 메뉴 / 우클릭 4항목 / drag+버튼 둘 다 / Initial 자동 표시 / 빈 상태 일러스트 / 테마 토글 settings 만. onboarding 추천 메모장/네이버/빈 세션 3개 확정. |
