# Claude Code 세션 인계 문서 (Handoff)

> **사용법**: 새 Claude 세션 시작 시 첫 입력으로 "이 파일 읽고 이어서 작업" 하라고 하세요.
> 이 문서는 Claude 의 auto-memory 가 컴퓨터 간 옮겨지지 않아 새 세션에서 컨텍스트 빠르게 복원하기 위한 용도입니다.
> 마지막 업데이트: 2026-05-06 새벽 (5/4~5/6 작업 — 자세한 변경은 §5 변경 이력 + §11 인계 노트 참조). baseline: **core 75/75 + scenarios 70/70 그린**. **wireframe D1~D26 100% 구현 완료**. 5/5 밤~5/6: 8 layer 회귀 fix (idempotent driver / SW_RESTORE / step_code 분리 / pyautogui PRIMARY / title_re / walk-up + picker 가드 / element resolution fallback / 환각 import 교정) + tmp/ 정리 + AI 대화 자동 로그 ([tmp/conversations/](../tmp/conversations/)).

## 1. 프로젝트 한 줄 요약

**ohdo** — AI (Gemini CLI) 와 대화하면서 Windows 데스크톱/웹 자동화 코드를 단계별로 생성/실행하는 PyQt6 기반 RPA 솔루션. SaaS 확장 계획 진행 중 ([docs/ROADMAP.md](ROADMAP.md) §1, AGPL-3.0 데스크톱 + 상업 SaaS 오픈코어 전략 — **2026-05-05 사용자 결정 확정**).

## 2. 작업 환경 (사용자 preference)

- **터미널**: PowerShell (복붙용 명령은 PowerShell 문법 — `Activate.ps1`, `$env:X`, `Copy-Item`)
- **Python**: `py -3.12 -m venv venv` 로 venv 생성, **항상 venv python 의 절대경로** 사용 (`venv\Scripts\python.exe` — 점 없음). 시스템 `python` 은 고장난 3.8 32-bit.
- **em-dash (—) cp949 인코딩 금지**: test/log/print 메시지에 사용 X. hyphen (-) 사용. (docstring/markdown 은 OK)
- **commit**: 사용자 명시 요청 시에만 (CLAUDE.md 규칙)
- **PySide6 포트 동기화**: 코드 수정 시 `pyside6_port/` 도 sed 로 자동 sync (PyQt6→PySide6, pyqtSignal→Signal 등)

## 3. 코드 구조 핵심

```
ohdo/
├── main.py
├── ui/                              — PyQt6 GUI
│   ├── main_window.py               — 1211줄 (2058 → 1823 → 1538 → 1211, 분해 Step 4 완료)
│   ├── ui_inspection_handler.py     — element picker + window inspector 핸들러 (Step 2)
│   ├── block_execution_handler.py   — 코드/블럭 실행 controller 16개 메서드 (Step 3, 478줄)
│   ├── ai_call_handler.py           — AI 호출 controller 6개 메서드 (Step 4, 412줄)
│   ├── element_picker.py            — element 검출 (EFP 토글 + walker)
│   ├── code_viewer.py               — 코드 뷰 / 블럭 뷰 + BlockCard / _WaitSpinBox
│   └── ...
├── core/
│   ├── workflow_engine.py           — block 실행 + step delta 추출
│   ├── execution_kernel.py          — kernel subprocess 관리 (env OHDO_PARENT_PID 전달)
│   ├── kernel_worker.py             — exec subprocess (step 종료 후 AllowSetForegroundWindow)
│   ├── import_manager.py            — extract_code_delta, _smart_dedent, _unwrap_main_function, extract_initial_block
│   ├── session_manager.py           — Step.wait_after_ms, Session.settings.step_delay_ms
│   └── ...
├── tests/
│   └── test_core.py                 — 65 tests, 모두 그린
├── pyside6_port/                    — LGPL 라이선스 PySide6 포트 (수동 sed sync)
│   ├── data/                        — junction → ../data (세션 공유)
│   └── (별도 venv 없음 — GUI 검증은 사용자 직접 환경에서)
└── docs/
    ├── ROADMAP.md                   — SaaS 장기 계획
    ├── triage.md                    — 작업 history (이거 먼저 보면 최근 변경 흐름 파악)
    └── handoff.md                   — 이 파일
```

## 4. 핵심 contract (회귀하면 안 되는 baseline)

### 4.1 Element picker baseline (test_42~48)
- **EFP (IUIAutomation::ElementFromPoint)** 호출 동안만 `WS_EX_TRANSPARENT` 토글 (try/finally), walker 들은 토글 밖. 매 tick 토글 회귀하면 picker 의 mouseover 누수 회귀, 토글 0 으로 가면 Excel 셀 detection 회귀.
- **F3 wait + post_pause_mode**: 항상 TRANSPARENT 켬 (방향 B 통합) + WH_MOUSE_LL hook 으로 click 차단 + 키보드 hook 은 picker 전체 lifecycle 유지.
- settings: `uia_max_depth=15`, `uia_time_budget_ms=500`, `descendants area threshold=5000 px²`, `cdp_enabled=false (default)`.

### 4.2 Jupyter mode (블럭 단독 실행) — test_51~54, 64, 66, 67
AI 생성 코드가 step 별 단독 실행되려면 **6가지 함수/필터 모두** 필요:
1. `extract_code_delta` — prefix + SequenceMatcher fallback
2. `extract_step_delta_code(step, prev_step)` — generated_code diff 재계산
3. `_smart_dedent` — try 블록 안 라인 indent 정리
4. `_unwrap_main_function` — `def main(): ...; main()` 패턴 unwrap (AST)
5. **except 캡처 변수 stale 라인 필터링** — 5/4 추가, NameError 'e' 회귀 방지
6. **prev_set 필터의 컨트롤 헤더 화이트리스트** — 5/4 밤 추가 (test_67). `try:`, `except`, `else:`, `if`, `for`, `while`, `with`, `def`, `class` 등 컨트롤 헤더는 prev 에 동일 패턴 있어도 보존 (제거하면 새 try/if/for 블록의 본문이 module-level 로 평면화되어 try/except 의미 깨짐).

추가로 **prompt 측 예방** (5/4 밤, test_66):
- `prompt_builder.build_step_prompt` [3] 규칙 섹션 + `prompts.json/system_context` 절대 규칙 9~10 에 jupyter 호환 가이드 박힘:
  - `def main(): ...; main()` 금지 (모듈 레벨 작성) — `_unwrap_main_function` 의존도 낮춤
  - except 변수(e, ex 등) 는 except 블록 안에서만 사용 — stale 라인 필터 의존도 낮춤
  - 후속 스텝은 이전 변수(driver, app, dlg) 재정의 X — globals 잃음 방지 (사후 필터 없음, 더 위험)

### 4.3 closeEvent 단일 정의 (test_62)
이전 두 번 정의되어 buggy. 통합 closeEvent: 세션 저장 + 커널 정리.

### 4.4 Step wait 시스템 (test_63)
3단계 우선순위: `step.wait_after_ms > session.settings.step_delay_ms > settings.execution.step_delay_ms`. UI 는 `_WaitSpinBox` (focus 시 selectAll) + `editingFinished` (입력 중 카드 재생성 X) + 개별 변경 시 `_refresh_block_view` 호출 안 함 (포커스 유지).

### 4.5 Win11 ForegroundLock 우회 (test_65)
subprocess (`kernel_worker`) 가 step 코드 안에서 `pyautogui.click/write/press` 같은 SendInput 호출하면 `SetForegroundWindow` 권한이 ohdo → kernel_worker 로 이전됨. 이후 ohdo 의 `mw.activateWindow()` 가 거부되어 작업표시줄 flash 만 발생. **Fix**:
- [core/execution_kernel.py](../core/execution_kernel.py) `start()`: subprocess `env` 에 `OHDO_PARENT_PID = str(os.getpid())` 전달.
- [core/kernel_worker.py](../core/kernel_worker.py): exec() finally 절에서 `ctypes.windll.user32.AllowSetForegroundWindow(parent_pid)` 호출 — 부모 (ohdo) 에 명시적 권한 양도. ohdo 의 다음 1회 `activateWindow` 통과 보장.
- 회귀 시 이 패턴 유지 — `OHDO_PARENT_PID` 키, `AllowSetForegroundWindow` 호출, `sys.platform == "win32"` 가드 모두 필수.

### 4.6 Block 실행 controller 분리 (Step 3, test_50/55/56/57/63)
[ui/main_window.py](../ui/main_window.py) 의 코드/블럭 실행 path 16개 메서드를 [ui/block_execution_handler.py](../ui/block_execution_handler.py) (`BlockExecutionHandler`) 로 분리. main_window 는 위임 stub 만 (`def _on_xxx: self.block_executor.on_xxx()`). 회귀 테스트는 `inspect.getsource(BlockExecutionHandler.method)` 로 검사 (self → mw 변환된 패턴, 예: `mw.lower()`).

### 4.7 AI 호출 controller 분리 (Step 4, test_68)
[ui/main_window.py](../ui/main_window.py) 의 AI 호출 path 6개 메서드를 [ui/ai_call_handler.py](../ui/ai_call_handler.py) (`AICallHandler`) 로 분리. 메서드: `on_cancel_ai`, `on_user_message`, `call_ai_thread` (백그라운드), `on_ai_response`, `on_step_executed`, `apply_manual_edit_patches`. main_window 는 위임 stub 만 (`def _on_xxx: self.ai_handler.on_xxx()`). 회귀 테스트는 `inspect.getsource(AICallHandler.method)` 로 검사 + `mw.xxx` 패턴. main_window unused imports (`asyncio`, `threading`, `Step`) 정리됨.

### 4.8 코드 편집 시 두 필드 동시 업데이트 + manually_edited 우선 + import 보존 (test_69)
사용자 수정 보호를 위한 4중 안전장치:

1. **두 필드 동시 업데이트** ([ui/main_window.py](../ui/main_window.py)):
   - `_on_block_step_code_edited`: `step_code` + 재구성한 `generated_code` (imports 보존 + prev_body + new_step_code).
   - `_on_step_code_edited`: `generated_code = new` + 재계산한 `step_code` + `step_imports` (extract_code_delta + extract_import_delta).
2. **`extract_step_delta_code` 우선순위 (0) manually_edited** ([core/workflow_engine.py](../core/workflow_engine.py)):
   - `manually_edited=True` + `step_code` 있으면 step_code 무조건 우선 반환 (compile 검증 통과 시 즉시).
   - generated_code 의 stale marker (1순위) / diff (2순위) 보다 앞 — 사용자 의도가 AI 원본보다 우선.
3. **화면 갱신 호출**: `_on_block_step_code_edited` 끝에 `self._refresh_code_viewer()`, `_on_step_code_edited` 끝에 `self._refresh_block_view()` — 위젯이 stale 한 채 남아 사용자가 변경을 못 보는 회귀 방지.
4. **import 보존**: 블럭 카드는 import 표시 안 함 → 사용자가 수정 시 import 안 건드림. 재구성 시 원본 step.generated_code 의 import 들을 prev_imports + old_imports + new_step_imports merge 로 모두 살림. 안 그러면 `extract_library_block` 이 imports 잃어 실행 시 NameError (5/4 사용자 2차 보고 'Application/Keys is not defined' 의 원인).

이 4개 모두 사용자가 어느 뷰에서 수정해도 다른 뷰 + 실행 결과가 일관되게 동기화되도록 보장. 한 가지만 빠지면 회귀 (5/4 사용자 보고 1차/2차/3차 모두 이 4중 fix 로 해소).

### 4.13 D3 — Step 카드 사용자 요청 + AI 설명 통합 (test_24~26)
[Step](../core/session_manager.py) dataclass 에 D3 (와이어프레임 §2.1) 의 핵심 데이터 필드 2개 추가:

- `user_request: str = ""` — 사용자가 입력한 자연어 요청
- `ai_description: str = ""` — AI 응답의 본문 (코드 제외 텍스트)

기본값 `""` — backwards compat. 옛 세션 JSON 에 이 필드 없어도 `Session(**{...})` 가 dataclass field 로 필터해 default 적용. v1 의 `conversation` 리스트도 그대로 보존 (양쪽 path 유지).

[AppService.generate_step](../core/app_service.py) 가 D3 path 의 단일 진입점:
1. `PromptBuilder.build_step_prompt` 로 prompt 구성 (이전 step + 시스템 지시 포함)
2. `AIEngineManager.generate(prompt, images)` 호출
3. `response.success` → Step 생성 — `user_request` / `ai_description` (= response.description) / `generated_code` (= response.code) / `required_packages` 채움
4. `add_step` 으로 자동 저장
5. `(Optional[Step], AIResponse)` 반환 — 실패 시 (None, response)

ui_v2 의 `_on_send_message` 가 이 메서드만 호출 — Step 생성 로직 / 코드 추출 / 세션 저장은 AppService 가 캡슐화. 새 UI 가 v1 의 prompt_builder/ai_engine 직접 import 안 해도 됨.

### 4.12 ui_v2 PoC — UI redesign 1차 슬라이스 (test_21~23)
[ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) — wireframes_v2.md 의 D1~D26 결정 반영한 새 UI PoC. **AppService 만 사용** (ADR 0001 강제 — test_21 가 forbidden import 패턴 검사).

**진입점**: `python main.py --ui v2` ([main.py](../main.py) 에 분기 추가).

**구현된 결정 (PoC 범위)**:
- D1 코드+블럭 뷰 통합 — 단일 스크롤 (라이브러리/Initial/Step 카드 세로 나열)
- D3 사용자 요청 + AI 설명 + 코드 step 카드 통합
- D5 콘솔 토글 (Ctrl+\`, default 닫힘)
- D6 인라인 칩 영역 (입력창 위, stub)
- D7 단축키 (Ctrl+R/F5 실행, F9 중지, Ctrl+Enter 전송, Ctrl+, 설정, Ctrl+K palette, Ctrl+\` 콘솔)
- D11 Initial '여기서 실행' 제거 — '⏯ 단독' 만
- D19 AI 설명 1~2줄 preview + ▼ 펼침 (toggle button)
- D24 Initial 자동 추출 비어있지 않을 때만 표시

**미구현 (후속 슬라이스)**: D4 다중 세션 탭, D8 Command palette 실 구현, D9 토스트, D10 시스템 테마 자동, D14 onboarding wizard, D17 토스트 confirm, D20 사이드바 last state, D21 + 탭 메뉴, D22 우클릭, D23 drag reorder, D25 빈 상태 일러스트.

**stub 처리** (실 동작은 후속 AppService 메서드 추가 시 연결):
- 전체 실행 / 단독 (step>0) / 여기서부터 실행 — `_log` 만 출력
- 사용자 메시지 전송 — `_log` 만 (AppService.generate_step 추가 후 연결)
- 캡처 / 요소 선택 — v1 의 ScreenCaptureOverlay/ElementPickerOverlay 후속 연결
- Settings — v1 의 SettingsDialog 재사용 예정

**실 동작하는 부분**:
- 세션 목록 / 더블클릭 로드 / 새 세션 생성 / closeEvent (커널 정리 + 세션 저장)
- Initial 단독 실행 — `AppService.run_initial_block_sync` 호출 (Phase 2.5 contract)
- 카드 자동 갱신 (세션 변경 시)
- 콘솔 토글
- 단축키 5종 + Ctrl+N

**styling**: wireframes_v2.md §8 디자인 토큰 (Catppuccin Mocha) 인라인 QSS. 후속 슬라이스에서 styles_v2.qss 분리.

### 4.11 AppService façade (Phase 1, test_17~20)
[core/app_service.py](../core/app_service.py) 의 `AppService` 클래스 — UI ↔ Core 분리 진입점. ADR 0001 ([docs/saas/decisions/0001-preserve-existing-core.md](saas/decisions/0001-preserve-existing-core.md)) 의 wrap-first 정책: **기존 UI 는 건드리지 않음**, 새 호출자 (FastAPI 라우터 / Agent runner / ui_v2) 만 AppService 사용.

**구조**:
- `SessionRepository` ([core/storage/base.py](../core/storage/base.py)) 추상화 — `LocalJsonRepository` (기본), 향후 `PostgresRepository` / `HttpRemoteRepository`.
- AppService 는 stateless façade — 매 호출마다 session/kernel 객체 인자로 받음. 상태는 호출자 (handler/UI) 보유.
- AIEngineManager 주입은 선택 — 미주입 시 AI 메서드는 안전한 fallback (`get_ai_engine_name() → None`) 또는 `RuntimeError` (mutating 작업).

**메서드 카테고리**:
1. **세션/스텝 CRUD** (위임): `create_session`, `save_session`, `get_session`, `list_sessions`, `delete_session`, `add_step`, `update_step`, `delete_step`, `insert_step`, `move_step`.
2. **코드 추출** (pure 함수 façade): `get_library_block_code`, `get_initial_block_code`, `get_step_delta_code`. UI 가 workflow_engine/import_manager 직접 import 안 하도록.
3. **블럭 실행** (kernel 외부 주입): `run_initial_block_sync(session, initial_code, kernel, on_log=)` — Phase 2.5 contract (§4.9) 의 라이브러리 자동 선행 + Initial 실행. kernel lifecycle / threading 은 호출자 책임.
4. **AI ops** (AIEngineManager 위임): `generate(async)`, `switch_ai_engine`, `cancel_ai`, `get_ai_engine_name`, `list_ai_engines`.

**ui_v2 가 따라야 할 패턴**: `from core.app_service import AppService` 만 import. `from core.session_manager import ...` / `from core.workflow_engine import ...` 등은 금지 (façade 우회 = ADR 위반).

### 4.10 OpenAI 호환 API 어댑터 (D2, test_75)
[core/adapters/openai_compat_adapter.py](../core/adapters/openai_compat_adapter.py) 의 `OpenAICompatAdapter`:

- **단일 어댑터, 다 서비스**: base_url + api_key 만 받아 OpenAI/DeepSeek/Groq/OpenRouter/Mistral/Together/Perplexity 클라우드 + Ollama/LM Studio 로컬 모두 지원. 모두 `POST {base_url}/chat/completions` 호출.
- **9 프리셋** (`PRESETS` 모듈 상수): Settings UI 드롭다운에서 선택 시 base_url + model 자동 채움. `_PRESET_LABELS` 로 표시 라벨 정확화 (DeepSeek, LM Studio (local) 등).
- **api_key 우선순위**: 직접 입력 (`config["api_key"]`) > 환경변수 (`config["api_key_env"]` 기본 `OPENAI_API_KEY`). 비어있어도 OK (로컬 Ollama/LM Studio).
- **base_url 끝 슬래시 자동 제거**: `chat/completions` 합칠 때 `//` 회피.
- **이미지 첨부**: OpenAI multimodal 포맷 (`content` array `[{type:"text"}, {type:"image_url", image_url:{url:"data:image/png;base64,..."}}]`). vision 지원 모델만 의미있음.
- **HTTP 라이브러리**: `requests` (이미 deps), `asyncio.to_thread` 로 async 호환. httpx/openai SDK 의존성 회피.
- **Cancel**: 플래그 기반 (응답 후 검사). 실시간 mid-request 중단은 향후 httpx 전환 시.
- **API key 저장 위치**: settings.json 평문. keyring 통합은 §6 #5 결정 대기.

### 4.9 Initial 블럭 단독 실행 (Phase 2.5, test_74)
사용자가 driver/options 등 setup 변수를 재정의하고 싶을 때 첫 step 안 돌리고 Initial 블럭만 실행. 4가지 contract:

1. **상수**: `INITIAL_BLOCK_STEP_ID = -1` ([core/execution_kernel.py](../core/execution_kernel.py)) — `LIBRARY_BLOCK_STEP_ID = 0` 와 같은 가상 step_id 패밀리.
2. **UI 노출**: `BlockCard` 가 `step_id > 0 or step_id == -1` 조건으로 "⏯ 단독" 버튼 표시. step_id == -1 전용 tooltip ("Initial 블럭 단독 실행 (driver/options 등 변수 재초기화)"). Library (step_id == 0) 은 여전히 제외 — "한 번만 실행되는 setup" 이라 의미 없음 유지.
3. **Signal 라우팅**: `BlockViewWidget.refresh()` 가 `init_card.run_single_requested` 를 step 카드와 같은 `self.run_single_step_requested` 시그널로 forward. main_window → `BlockExecutionHandler.on_run_single_step(-1)` → 분기 → `on_run_initial_block()`.
4. **실행 path**: `_run_initial_block_thread` 가 `LIBRARY_BLOCK_STEP_ID not in kernel.executed_steps` 일 때 `extract_library_block(session)` 으로 라이브러리 선행 (NameError 회귀 방지 — 카드는 imports 표시 안 함). Initial 코드는 카드의 `code_edit.toPlainText()` 로 사용자 편집 반영. `kernel.execute_block(initial_code, step_id=INITIAL_BLOCK_STEP_ID)`. finally 절에서 `blocks_finished.emit()` (test_73 의 run/stop 자동 리셋과 일관).

다른 step 들의 `kernel.executed_steps` 는 안 건드림 — Initial 만 재실행이고 step 1..N 의 silent replay 도 안 함.

## 5. 최근 작업 내역 (5/2 ~ 5/5)

| 일자 | 작업 |
|------|------|
| 5/2 | PySide6 migration (pyside6_port/), Phase 2 (Initial 블럭 추출), main_window 분해 Step 1 (closeEvent) + Step 2 (UIInspectionHandler 235줄) |
| 5/3 | Step wait 시스템 (3단계 우선순위 + UI), 코드 뷰↔블럭 뷰 상호작용 fix (signal-slot blocks_finished) |
| 5/4 | NameError 'e' fix (extract_code_delta 의 except 변수 필터), wait UI 개선 (_WaitSpinBox + editingFinished + 좌측 정렬) |
| 5/4 (저녁) | main_window 분해 Step 3 (BlockExecutionHandler, 1880→1538줄, 16개 위임 stub), Win11 ForegroundLock 우회 (foreground 복원 보류 해제), test 64 → 65 |
| 5/4 (밤) | AI prompt 강화 — jupyter mode 호환 가이드라인 3종 (`prompt_builder` + `prompts.json/system_context`), test_66 추가 (66/66 그린) |
| 5/4 (밤) | extract_code_delta 컨트롤 헤더 보존 fix — prev_set 필터가 try:/except 헤더 제거해 본문이 module-level 평면화되는 버그 수정. test_67 추가 (67/67 그린) |
| 5/4 (밤) | main_window 분해 Step 4 — AICallHandler (412줄) 신규, 6개 메서드 위임 stub. main_window 1538 → 1211 (-327줄). unused imports 정리. test_68 추가 (68/68 그린). |
| 5/4 (밤) | 코드 편집 desync fix — `_on_block_step_code_edited` / `_on_step_code_edited` 가 step_code + generated_code 두 필드 동시 업데이트. 사용자 보고 (네이버 검색 시나리오: 삼성전자 → 하이닉스 수정이 무시되는 회귀) 해결. test_69 추가 (69/69 그린). |
| 5/4 (밤) | 코드 편집 desync 2차 fix — 1차 fix 후에도 ① 코드 뷰어 탭 갱신 안 됨 ② 실행 시 잘못된 코드 추출 (사용자 보고). `extract_step_delta_code` 에 우선순위 (0) manually_edited + step_code 무조건 우선 추가. 두 핸들러에 _refresh_code_viewer/_refresh_block_view 호출 추가. 3중 안전장치 (§4.8). |
| 5/4 (밤) | 코드 편집 desync 3차 fix — 2차 fix 후에도 사용자 보고 'NameError: name Application/Keys is not defined'. 원인: 새 generated_code 가 prev_step + step_code 만 합쳐 step 의 import 들을 잃음. block 카드는 import 표시 안 하므로 사용자가 수정 안 함. Fix: 원본 step.generated_code 의 import 보존 (prev_imports + old_imports + new_step_imports merge). 4중 안전장치 (§4.8). test_69 갱신. |
| 5/4 (밤) | Selenium prompt 가이드 보강 — AI 가 driver.get() 직후 추측성 element ID (예: 'nm_main_tab') 로 WebDriverWait 사용 → 10초 timeout 회귀 (사용자 보고). prompt_builder 에 "추측성 ID 금지, time.sleep 또는 body/html 사용" 가이드 추가. test_70 (70/70 그린). |
| 5/4 (밤) | Gemini CLI 모델 명시 — headless 모드 default 가 preview 모델 (gemini-3-flash-preview) 로 잡혀 Google 인프라 capacity 부족으로 429/180s timeout 회귀 (사용자 보고). adapter `__init__` 에 `self.model` + `_build_args` 헬퍼 추가. settings.json default = `gemini-2.5-flash` 안정 모델. test_71. **note**: `_build_args` 정의만 추가, 실제 두 subprocess.Popen path (stdin/-p) 에서 호출 안 됨 — 다음 작업으로 production path 적용 필요. |
| 5/4 (밤) | 세션 추가/삭제 시 블럭 뷰 초기화 회귀 — 사용자 보고: `_new_session` / `_on_session_delete` 의 `self.code_viewer.clear()` 가 step 카드만 비웠음, 블럭 뷰는 이전 세션 카드 stale. Fix: `CodeViewer.clear()` 가 `block_view.refresh("", [], "", 500)` 도 호출 (try/except fallback 으로 `block_view.clear()`). test_72 (72/72 그린). |
| 5/5 | 실행 종료 시 run/stop 버튼 자동 리셋 안전망 — 사용자 보고: 모든 step 완료 후에도 stop 버튼이 활성/run 버튼이 비활성 채로 남는 회귀. Fix: `AICallHandler.on_step_executed` (코드 뷰 path) 끝에 `mw.code_viewer.set_running(False)` catch-all 추가. `BlockExecutionHandler.on_blocks_finished` (블럭 뷰 path) 에 `mw.code_viewer.update()` 시각 갱신 강제. test_73 (73/73 그린). |
| 5/5 | Gemini adapter `_build_args` production path 적용 — 5/4 밤 작업 미완성 마감. 두 subprocess.Popen 호출 (stdin / -p) 가 여전히 raw `[gemini_exec, ...]` 리터럴 사용 중이라 -m 플래그가 실제 호출에서 누락 가능했던 문제 해결. 둘 다 `self._build_args(...)` 경유. test_71 확장 — production path source 검증 추가 (raw 리터럴 부재 + `_build_args` 호출 패턴 존재). core 73/73 유지. PySide6 sync. |
| 5/5 | ROADMAP §1 라이선스 전략 결정 확정 — 사용자와 AGPL/폐쇄/오픈코어 비교 후 **오픈코어 (AGPL-3.0 데스크톱 + 추후 폐쇄 SaaS)** 확정. v1.0 은 100% AGPL-3.0 무료, SaaS 라인 긋기는 Phase 2 진입 시점에 결정. ROADMAP §1/§10 갱신, handoff §6 #1 결정 완료 표시. LICENSE 파일/코드 헤더 추가는 미실행 (사용자 결정 대기). |
| 5/5 | Phase 2.5: Initial 블럭 단독 실행 — driver/options 등 setup 변수를 재정의하고 싶을 때 첫 step 안 돌리고 Initial 블럭만 실행하는 path 추가. `INITIAL_BLOCK_STEP_ID = -1` 상수 신설, BlockCard 의 "⏯ 단독" 버튼이 step_id == -1 도 활성화 (전용 tooltip), BlockViewWidget.refresh 가 init_card.run_single_requested 라우팅, BlockExecutionHandler 에 `on_run_initial_block` + `_run_initial_block_thread` 추가 (라이브러리 미초기화 시 자동 선행 → NameError 회귀 방지). 카드 텍스트로 사용자 편집 반영. test_74 (74/74 그린). PySide6 sync. |
| 5/5 | UI redesign 준비 Step 0 #1: [docs/feature_catalog.md](feature_catalog.md) 초안 작성 — 현재 PyQt6 UI 의 모든 화면/위젯/단축키/시그널/다이얼로그/데이터 흐름 카탈로그 (14 섹션, ASCII 레이아웃 다이어그램 포함). redesign 와이어프레임 cover 검증의 baseline 로 사용. §13 에 redesign 시 결정 필요 항목 명시. |
| 5/5 | UI redesign 결정 3건 확정 (사용자 합의) — feature_catalog §13: **D1 코드+블럭 뷰 통합** (블럭 뷰 베이스로 단일 뷰), **D2 OpenAI 호환 API 어댑터 추가** (base_url + api_key, DeepSeek/Groq/OpenRouter/Ollama 등 다 지원), **D3 요청-코드 step 매칭 표시** (각 step 카드에 사용자 요청 + AI 설명 + 코드 모두 통합 — ChatPanel ↔ CodeViewer 좌우 분리 → step 카드 통합). 미결정 13건 남음 (API 키 저장 위치, 단축키 체계, 다중 세션 UX 등). |
| 5/5 | **D2 구현**: OpenAI 호환 어댑터 신규 — [core/adapters/openai_compat_adapter.py](../core/adapters/openai_compat_adapter.py) (`requests` + asyncio.to_thread, multimodal 이미지 base64 변환, 9 프리셋 OpenAI/DeepSeek/Groq/OpenRouter/Mistral/Together/Perplexity/Ollama/LM Studio). `ADAPTER_REGISTRY` 등록, settings.json default 갱신, [SettingsDialog](../ui/settings_dialog.py) AI 탭에 OpenAI 호환 GroupBox 추가 (프리셋 드롭다운 → base_url/model 자동 채움, api_key Password 모드, model/timeout/max_tokens/temperature). test_75 (75/75 그린). PySide6 sync. **API key 저장은 settings.json 평문 — keyring 통합은 §6 #5 결정 대기.** |
| 5/5 | UI redesign 결정 13건 일괄 확정 (사용자 합의, [feature_catalog.md §13](feature_catalog.md)) — D4~D16: **다중 세션 탭 / 콘솔 토글 (Ctrl+\`) / 인라인 요소 칩 / 단축키 5종 추가 (Ctrl+Enter 전송, Ctrl+R 실행, Ctrl+, 설정, Ctrl+K palette, F5 재실행) / Command palette 도입 / 토스트 + QMessageBox 병행 / 시스템 테마 자동 감지 / Initial '여기서 실행' 제거 / 캡처 워크플로우 유지 / 웹은 데스크톱뷰 우선 + 모바일 read-only / 3단계 onboarding wizard / settings.json 평문 (v1.0) → SaaS 시 keyring / BYO 우선 + SaaS hidden 프리셋**. 미결정 0건 — 와이어프레임 작업 진입 가능. |
| 5/5 | UI redesign 준비 Step 0 #2: [tests/test_scenarios.py](../tests/test_scenarios.py) 16 시나리오 신규 — behavior-level 테스트 (UI 우회). test_core 의 inspect.getsource 패턴은 코드 위치 변경에 깨지지만 scenarios 는 입출력 동작만 검증 → AppService 추출/UI redesign 회귀 안전망. 6 그룹: 세션 lifecycle (3) / delta·library·initial 추출 (5) / manually_edited 우선순위 (2) / AIEngineManager 라우팅 (2) / OpenAICompat HTTP mock (3 — 응답 파싱/HTTP 에러/이미지 multimodal 포맷) / wait timing (1). test_runner 에 'scenarios' suite 등록. 16/16 그린. PySide6 sync. |
| 5/5 | UI redesign Step 0/D #4 와이어프레임 1차 초안: [docs/wireframes_v2.md](wireframes_v2.md) — 12 섹션 텍스트 와이어프레임 (메인 윈도우 / Step 카드 v2 / Settings / Onboarding 3단계 wizard / Command palette / Toast / 단축키 17개 / 디자인 토큰 / D1~D16 결정 매핑). §10 에 와이어프레임 도중 발견한 새 결정 10건 (D17 후보). 다음: 사용자 검토 → §10 결정 → Excalidraw 정식 와이어프레임 → AppService 추출 (Step 1) → ui_v2/ PoC. |
| 5/5 | UI redesign 결정 10건 + onboarding 일괄 확정 (D17~D26): 사용자 요청 클릭 토스트 confirm / wait 드롭다운 5+사용자정의 / AI 설명 1~2줄 preview / 사이드바 last state 기억 / + 탭 메뉴 / 우클릭 4항목 / drag+버튼 둘 다 / Initial 자동 표시 / 빈 상태 일러스트 / 테마 토글 settings 만. onboarding 메모장/네이버/빈 세션 3개 확정. **미결정 0건 — Excalidraw 정식 와이어프레임 또는 AppService 추출로 진입 가능.** |
| 5/5 | **Step 1: AppService façade 확장** (Phase 1) — 기존 [core/app_service.py](../core/app_service.py) (세션/스텝 CRUD + `LocalJsonRepository` 이미 존재, ADR 0001/0002 wrap-first 정책) 에 메서드 추가: 코드 추출 (`get_library_block_code` / `get_initial_block_code` / `get_step_delta_code`) + 단독 실행 (`run_initial_block_sync` — Phase 2.5 contract façade) + AI ops (`generate` / `switch_ai_engine` / `cancel_ai` / `get_ai_engine_name` / `list_ai_engines`). AIEngineManager 주입 선택 — 미주입 시 안전 fallback. test_scenarios 에 4 시나리오 추가 (test_17~20: CRUD / 코드 추출 / fake kernel 로 run_initial_block_sync / AI façade). scenarios 20/20 그린, core 75/75 유지. PySide6 sync. handoff §4.11 contract 추가. **기존 BlockExecutionHandler 등은 건드리지 않음** (ADR 0001) — 새 ui_v2 만 AppService 사용. |
| 5/5 | **ui_v2 PoC** (UI redesign 1차 슬라이스, [§4.12](.)) — 신규 [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) 단일 파일 PoC (~600줄). **AppService 만 사용** (test_21 가 forbidden import 강제 검사). [main.py](../main.py) 에 `--ui v2` 플래그 분기. 구현: 메인 윈도우 + 사이드바 (세션 목록) + 카드 스크롤 (라이브러리/Initial/Step 통합) + 채팅 입력 + 콘솔 토글 + 단축키 8개 + 디자인 토큰 인라인 QSS. **실 동작**: 세션 CRUD, 카드 자동 갱신, Initial 단독 실행 (`AppService.run_initial_block_sync` 호출). **stub**: 전체 실행, 메시지 전송 AI 호출, 캡처/요소 선택, Settings (후속 슬라이스에서 AppService.generate_step 추가 + v1 dialog/overlay 재사용 연결). test_21~23 신규 (scenarios 23/23 그린). PySide6 sync. |
| 5/5 | **D3 데이터 모델 + ui_v2 AI 호출 연결** — [Step](../core/session_manager.py) dataclass 에 `user_request` + `ai_description` 필드 추가 (default `""`, backwards compat). [AppService.generate_step](../core/app_service.py) 신규 — async, `PromptBuilder` 사용, AI 호출 → 성공 시 Step 생성 (user_request/ai_description/generated_code/required_packages 채움) + `add_step` 으로 세션 저장, 실패 시 `(None, response)` 반환. [ui_v2._on_send_message](../ui_v2/main_window_v2.py) stub 제거 → 실제 AppService.generate_step 호출 + 백그라운드 thread + step_done signal 로 UI 갱신 (입력 비활/재활). test_24 (mock AI → Step 생성 + D3 필드 보존), test_25 (AI 실패 시 step None + 세션에 추가 안 됨), test_26 (Step dataclass 필드 + default 검증). scenarios 26/26 그린. PySide6 sync. |
| 5/5 | **ui_v2 실행 stub 채우기 — 전체/단독/여기서부터** — [AppService.run_blocks](../core/app_service.py) (async) + `stop_blocks` 신규: WorkflowEngine.execute_session_blocks 위임, lazy engine 생성. ui_v2 의 `_on_run_all` (start=1,stop=None) / `_on_run_from` (start=N,stop=None) / `_on_run_single` (start=N,stop=N) / `_on_stop` (engine.stop()) 모두 실 동작 — 공통 `_start_run` 헬퍼로 백그라운드 thread + lower → run_blocks → step_done 으로 UI 복원. per-step status 는 콘솔 로그만 (카드 rebuild 회피, 완료 시 1번 refresh). test_27 (fake kernel — Step 2 단독 시 1 silent + 2 정상 + 3 미호출), test_28 (engine 미생성 stop_blocks no-op). scenarios 28/28 그린. PySide6 sync. |
| 5/5 | **ui_v2 stub 채우기 — 캡처/요소픽/Settings (v1 재사용)** — UI 컴포넌트 재사용은 ADR 우회 OK (데이터 안 다룸). [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py): `_on_capture` → v1 `ScreenCaptureOverlay` (lower → 캡처 → data/captures/v2_capture_*.png 저장 → pending_images 추가 → chip 표시), `_on_elempick` → v1 `ElementPickerOverlay` (settings.element_picker 옵션 적용 → pending_elements 추가 → chip), `_on_open_settings` → v1 `SettingsDialog` (settings.json + prompts.json 로드 → exec → save → AIEngineManager 재초기화 → 액션바 콤보 갱신). `_on_send_message` 확장 — pending images 가 generate_step images 인자로, pending elements 가 user_request 의 "📌 선택된 요소: ..." prefix 로 (D6). 전송 후 pending 비움 + chip_area 자동 갱신. test_29 (stub 제거 + v1 import + pending 로직), test_30 (send_message 의 pending 처리). scenarios 30/30 그린. PySide6 sync. |
| 5/5 | **ui_v2 카드 가로 스크롤 회귀 fix** (사용자 보고: 카드들이 좌우로 너무 길어 불필요한 가로 스크롤 발생). 원인: QPlainTextEdit 의 sizeHint (~80자, ~600px) + QToolButton (긴 AI preview) 의 word-wrap 미지원 → 카드 폭이 viewport 초과. 4 fix: ① `cards_scroll.HorizontalScrollBarPolicy = AlwaysOff` ② StepCardV2 자체 `setSizePolicy(Preferred,Preferred)` + `setMinimumWidth(0)` ③ `_tame_text_widget` 헬퍼 — req_edit / ai_full QPlainTextEdit 에 `LineWrapMode.WidgetWidth` + 가로스크롤 끄기 + `setSizePolicy(Expanding,Preferred)` + `setMinimumWidth(0)` ④ AI preview QToolButton → `QLabel(wordWrap=True) + mousePressEvent` 교체, preview 길이 120 → 80 자. 코드 영역은 NoWrap + 내부 가로스크롤 유지 (가독성). |
| 5/5 | **D9/D17/D20/D25 일괄 구현** — ui_v2 후속 슬라이스 4 결정 한 번에 박음. ① **D9 Toast** — [Toast](../ui_v2/main_window_v2.py) 위젯 (info/success/warning/error 4 타입, action 버튼 옵션, auto-dismiss 4초/8초) + `ToastManager` (우하단 stack, host resize 시 위치 갱신). ② **D17 사용자 요청 클릭 → 재생성** — `StepCardV2.regenerate_requested(int, str)` signal, user_request QPlainTextEdit 클릭 가능 (PointingHandCursor + tooltip), `MainWindowV2._on_regenerate` 가 토스트 confirm ("재생성" 버튼 + 8초 timeout = cancel). `_send_request` 헬퍼로 send_message + regenerate 공유. ③ **D20 사이드바 toggle** — `_toggle_sidebar` (Ctrl+B + 액션바 ☰ 버튼), `settings.ui.sidebar_collapsed` persist, init 에서 last state 적용. ④ **D25 빈 상태** — `_show_empty_state(title, description, examples=[...])`, 세션 없거나 step 0개 시 표시, 예시 시나리오 3개 (메모장/네이버/윈도우 검사) 클릭 시 입력창 자동 채움 + 포커스. 기존 알림 토스트 교체 (캡처 저장, 요소 선택, 설정 저장, step_done). test_31~33 (Toast 클래스 / D17 D20 D25 메서드 존재 / sidebar persist 패턴). scenarios 33/33 그린. PySide6 sync. |
| 5/5 | **D8 + D14 후속 슬라이스 일괄** — ui_v2 의 마지막 두 큰 stub 끝냄. ① **D8 Command palette** — 신규 [ui_v2/command_palette.py](../ui_v2/command_palette.py) `CommandPalette` (frameless QDialog, 검색 입력 + 그룹 분류 리스트 + ↑↓/Enter/Esc 키, 부모 윈도우 상단 1/4 위치, fuzzy substring 매칭 PoC). `MainWindowV2._on_command_palette` 가 items 동적 구성 — 9개 명령 (실행/중지/커널/세션/설정/캡처/요소픽/사이드바/콘솔, 단축키 표시) + 모든 세션 (더블클릭 = 로드) + 모든 AI 엔진 (✓ 현재 표시). Ctrl+K stub 제거 → 실 호출. ② **D14 Onboarding wizard** — 신규 [ui_v2/onboarding.py](../ui_v2/onboarding.py) `OnboardingWizard` (3 페이지 QStackedWidget — 환경 안내 / 엔진 선택 라디오 / 시나리오 선택, 진행 표시 1/3, 건너뛰기 / 이전 / 다음·시작 버튼, `selected_engine`/`selected_scenario` 결과 외부 노출). `should_show(settings)` static helper 가 `settings.ui.onboarding_done` 플래그 검사. MainWindowV2 init 에서 `QTimer.singleShot(0, _maybe_show_onboarding)` — wizard 결과로 AI 엔진 전환 + 새 세션 + 입력창 자동 채움. 한 번 띄우면 `onboarding_done = True` 저장 → 다음 실행 스킵. test_34 (CommandPalette 인터페이스), test_35 (Ctrl+K wiring + items 그룹), test_36 (OnboardingWizard SCENARIOS 3개 + should_show 토글 + 트리거 패턴). scenarios 36/36 그린. PySide6 sync. **ui_v2 의 모든 D 결정 (D1~D26) 구현 완료** — 남은 항목은 D4 다중 세션 탭 (별도 슬라이스). |
| 5/5 | **D4 다중 세션 탭 + D21 + 탭 메뉴 + D22 탭 우클릭** — ui_v2 의 마지막 큰 redesign. ① **D4 세션별 커널 분리**: `MainWindowV2._kernel: Optional` → `_kernels: dict[str, ExecutionKernel]`. `_get_or_create_kernel` / `_on_kernel_reset` / `closeEvent` 모두 활성 세션 키 기반. ② **QTabBar** (액션바 아래) — `setMovable(True)` (D4 drag reorder) + `setTabsClosable(True)` + 그룹별 styling. `_tabs_state: dict` (탭별 pending images / pending elements / message 입력 텍스트), `_tab_session_ids: list` (탭 인덱스 ↔ session_id 매칭). `_open_session_tab(sid)` (이미 열린 탭이면 그 탭 활성화), `_switch_session(sid)` (pending swap + 카드 재구성 + 사이드바 highlight 동기화). ③ **D21 + 탭 버튼 메뉴**: 새 세션 (빈) / 사이드바 검색 / 템플릿 서브메뉴 (메모장 한글 입력 / 네이버 검색). 템플릿 클릭 → 새 세션 + 입력창 자동 채움. ④ **D22 탭 우클릭 메뉴**: 닫기 / 이름 변경 (QInputDialog) / 복제 (모든 step + D3 필드 복사) / 워크플로우 내보내기 (PoC: 세션 폴더 통째로 shutil.copytree). 사이드바 더블클릭 → `_open_session_tab` (새 탭 또는 기존 탭 전환). 첫 실행 시 첫 세션을 첫 탭으로 자동 로드. test_37 (탭 인프라 + state dict + movable/closable), test_38 (D21 + D22 메뉴), test_39 (세션별 커널 분리 패턴). scenarios 39/39 그린. PySide6 sync. **ui_v2 의 D1~D26 모든 결정 구현 완료** (D23 step drag reorder 만 별도 슬라이스). |
| 5/5 | **D23 step reorder 버튼 fallback** — wireframe §10 #7 의 "drag-drop + ⬆⬇ 버튼 둘 다" 중 버튼 부분 우선. `StepCardV2.reorder_requested(step_id, direction)` signal 추가, footer 에 ⬆⬇ QToolButton (step_id > 0 만, transparent border). MainWindowV2._on_step_reorder → AppService.move_step (기존 함수, "up"/"down" direction) → 세션 다시 로드 → 카드 재구성 → 토스트. 더 이상 이동 불가 시 warning 토스트. test_40 신규 (signal + 핸들러 + 버튼 텍스트 + AppService 위임 검증). scenarios 40/40 그린. PySide6 sync. **drag-drop 본체는 후속 슬라이스** — Qt drag-drop 의 cards_container override 복잡도 때문에 분리. |
| 5/5 | **사용자 보고 fix + 전송/중지 토글** — ① 캡처/요소 선택 버튼 가시성 (transparent → 명확한 배경/테두리/40x40 크기/이모지 18px, hover primary 색상). QToolTip 글로벌 스타일 추가 (어두움 회피). ② `_on_elempick` 강제 종료 fix — `ElementPickerOverlay` 가 받는 인자가 `(parent, settings)` 인데 v2 가 `uia_max_depth=` kwargs 잘못 전달해 TypeError. 전체 settings 통째로 전달 + try/except 안전망. ③ 전송 ↔ 중지 토글 — `self.send_btn` 보유, `_set_send_state(generating)` 헬퍼, `_is_generating` 플래그. AI 호출 중 같은 버튼이 빨간 "⏹ 중지" 로 변환 + 클릭 시 `AppService.cancel_ai()`. `_send_request` 시작 시 True, `_on_step_done` 에서 False 자동 복원 (멱등). test_41. |
| 5/5 | **D23 drag-drop 본체** — wireframe §10 #7 의 마지막 미구현 결정. `AppService.reorder_step(session_id, step_id, target_step_id)` 신규 — pop+insert+renumber 단일-shot (move_step 다중 호출은 `_renumber_steps` 가 step_id 재할당해서 깨짐). [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) `CardDropContainer(QWidget)` 신규 — `setAcceptDrops(True)`, `dragEnter/Move/dropEvent`, `step_reorder_drop(int, int)` signal, drop y 위치로 target step 결정. `StepCardV2.mousePressEvent` / `mouseMoveEvent` — 헤더 영역 (~36px) 좌클릭 + drag distance > startDragDistance 시 `QDrag` 시작 (mime `application/x-ohdo-step` + 카드 미니 미리보기). `cards_container = CardDropContainer()`, `step_reorder_drop` → `MainWindowV2._on_step_reorder_to` → `AppService.reorder_step` + 세션 재로드 + 카드 재구성. test_42 (AppService.reorder_step 동작 검증 + signal/handler/connect 패턴). scenarios 42/42 그린. PySide6 sync. **wireframe D1~D26 모든 결정 100% 구현 완료**. |
| 5/5 | **Syntax highlighting + 코드 편집** (사용자 보고: 코드가 흰색만 + 편집 불가). v1 의 `PythonHighlighter` (Catppuccin Mocha 5 카테고리 — 키워드/문자열/숫자/주석/함수) 와 BlockCard 편집 토글 패턴을 v2 에 이식. ① `PythonHighlighter(QSyntaxHighlighter)` 신규 — v1 코드 재사용 + COLORS 토큰 매핑. ② StepCardV2: `code_edit.document()` 에 highlighter 인스턴스 부착 (`self._highlighter` 보유 = GC 방지), `_readonly_style` / `_editing_style` 분리 (편집 모드 = 2px primary 테두리), `_toggle_edit` / `_enter_edit_mode` / `_exit_edit_mode` (높이 180→320 확장, "✏️ 수정" → "✅ 저장" 토글), `code_edited(int, str)` signal. Library (step_id == 0) 제외, Initial/Step 모두 편집 가능. ③ MainWindowV2._on_block_code_edited — AppService.update_step(sid, step_id, {step_code, manually_edited=True}) → 세션 재로드 → 카드 재구성. Initial 직접 편집은 후속 (현재 안내 토스트만). test_43 (PythonHighlighter QSyntaxHighlighter 상속 + 5 룰 + 키워드 + signal + 핸들러 + GC 방지 패턴). scenarios 43/43 그린. PySide6 sync. |
| 5/5 | **세션 영구 삭제** (사용자 요청). `MainWindowV2._on_session_delete(session_id)` — QMessageBox.question 으로 destructive confirm (D9 결정 따름) → 열린 탭 있으면 `_on_tab_close(idx)` 먼저 (커널 정리 + state 제거) → `AppService.delete_session` → 사이드바 갱신 + 토스트 (warning). 사이드바 QListWidget 우클릭 컨텍스트 메뉴 활성화 (`_on_sidebar_context_menu`) — 열기 / 이름 변경 / 복제 / 내보내기 / 🗑 영구 삭제 5 항목 (이름변경/복제/내보내기는 D22 의 _on_tab_* 재사용). 탭 우클릭 메뉴에 separator + "🗑 세션 영구 삭제" 항목 추가 (탭 닫기와 분리). test_44 (핸들러 존재 + 메뉴 wiring + AppService.delete_session 실 동작 검증). scenarios 44/44 그린. PySide6 sync. |
| 5/6 | **tmp/ 폴더 + AI 대화 로그 자동 저장** (사용자 요청). ① 프로젝트 루트의 tmp_*/step[0-2]_* 임시 파일 56 개를 [tmp/debug_artifacts/](../tmp/debug_artifacts/) 로 정리. ② [.gitignore](../.gitignore) 에 `tmp/` 추가. ③ [AppService](../core/app_service.py) 에 `_save_conversation_log()` 헬퍼 신규 — `generate_step()` 마다 prompt + AI 응답 + 추출 코드를 단일 .md 파일로 [tmp/conversations/](../tmp/conversations/) 에 저장. 파일명: `{YYYYMMDD_HHMMSS}_step{N}_{session_short}.md`. 백업 [step0_prompt.txt + step0_generated_code.py] 분리 패턴을 통합 — 메타 헤더 (타임스탬프/세션ID/제목/엔진/이미지/길이) + 사용자 요청 + 전체 프롬프트 + AI 응답 원본 + 추출된 코드 + AI 설명. 로깅 실패는 generate_step 본래 동작을 막지 않음 (try/except + on_progress 알림만). `_safe_get_ai_engine_name()` 으로 mock/오류 시 fallback. test_70 (mock AI + 임시 LocalJsonRepository → tmp/conversations/ 에 .md 생성 + 모든 섹션 헤더 + session_id + 사용자 요청 + 코드 본문 검증). scenarios 70/70 + core 75/75 그린. **새 세션부터 모든 AI 호출이 자동 로깅됨 → 추후 디버깅·재현·프롬프트 품질 분석 가능**. |
| 5/5 (밤) | **AI 환각 import 자동 교정** (사용자 보고: 메모장 세션 OK 후 wooyang 브라우저 세션 선택 → 실행 시 `ImportError: cannot import name 'FindBestMatchException' from 'pywinauto.findbestmatch'` → 모든 step cascade fail). 원인: AI 가 pywinauto 의 존재하지 않는 exception 클래스명 (`FindBestMatchException`) 을 환각해서 `from pywinauto.findbestmatch import FindBestMatchException` 생성. 실제 이름은 `MatchError`. 라이브러리 블럭 ImportError → `from selenium...import Options` 등 후속 import 모두 skip → step 1 의 `Options()` NameError, step 2 의 `Application().connect()` 도 except 절에서 `FindBestMatchException` 참조하다 NameError. **윈도우↔브라우저 간섭 X — 단일 세션 내 환각 import 문제**. 3 layer fix: ① **workflow_engine.fix_hallucinated_imports** 신규 — `_HALLUCINATED_PYWINAUTO_NAMES = {'FindBestMatchException': 'MatchError'}` 매핑, 단어 경계 정규식으로 import + except 양쪽 자동 치환. self-멱등 (이미 교정된 코드 재변환 X). 라이브러리 블럭과 delta_code 양쪽에 적용 → 기존 wooyang 세션도 즉시 효과. ② **prompts.json guideline 19** — pywinauto 실제 exception 카탈로그 명시 (`MatchError`, `ElementNotFoundError`, `ElementAmbiguousError`, `WindowAmbiguousError`, `WindowNotFoundError`, `AppNotConnected`, `AppStartError`) + 환각 금지 강조 + 불확실하면 `Exception` 사용 권장. ③ test_68 (transform 동작 + 멱등 + 무관 코드 보존), test_69 (prompt 카탈로그 가이드). scenarios 69/69 + core 75/75 그린. |
| 5/5 (밤) | **picker descent 가드 + element resolution fallback** (사용자 보고: walk-up 해도 메뉴 클릭 안 됨, "부모 walk up 실패" 후 ElementNotFoundError). 원인 — picker 로그 분석: `EFP → MenuItem '파일' (area=4704)` 정상 검출 후 raw walker 가 더 작은 leaf TextBlock (area=1617) 으로 descend 해서 채택 → control_type='Text' 로 저장. 그러나 pywinauto `child_window(title='파일', control_type='Text')` 로는 그 leaf 못 찾음 (picker 는 uiautomation 직접 호출, pywinauto IUIAutomation 의 lazy resolution 경로 다름) → ElementNotFoundError. walk-up 코드는 `element.element_info` 접근 시점에 이미 실패. 2 layer fix: ① **element_picker 의 descent 가드** — `_CLICKABLE_CONTROL_TYPES` (MenuItem/Button/MenuBarItem/TabItem/ListItem/Hyperlink/Edit/등) frozenset + `_is_clickable_element()` helper. raw/descendants 폴백 + multi_backend 후보 비교에서 "현재 candidate 가 clickable 이고 새 candidate 는 비클릭" 이면 면적이 작아도 채택 거부. EFP 가 잡은 MenuItem '파일' 보존 → AI 가 `control_type="MenuItem"` 코드 생성 → pywinauto 정상 lookup. ② **win_inspector element resolution fallback** — `_resolve_element()` 함수 생성: 원본 selector → control_type 빼고 title-only → title_re 정규식 순으로 시도, 각 candidate 마다 `element_info.control_type` 강제 resolution 검증. 기존 세션 (control_type='Text' 저장된) 도 title-only fallback 으로 복구. test_66 (picker descent 가드 + clickable types + helper), test_67 (win_inspector resolution fallback chain). scenarios 67/67 + core 75/75 그린. PySide6 sync (sed 로 PyQt6→PySide6 import 변환). |
| 5/5 (밤) | **비클릭 leaf element 클릭 가능 부모 promote** (사용자 보고: Win11 메모장 [Text] "파일"/"보기" 메뉴 클릭 안 됨, 같은 메모장 [Button] "설정" 은 작동). 원인: picker 가 호버 시 가장 깊은 leaf (Text/Image/Pane) 를 잡는데 메뉴바의 "TextBlock 파일" 같은 leaf 라벨은 클릭 핸들러가 부모 MenuBarItem/MenuItem 에 있음 → leaf center 좌표 클릭이 hit-testing 죽은 영역에 떨어져 routed event 가 부모로 propagate 안 됨. [Button] "설정" 은 자체에 핸들러 있어 작동. 2 layer fix: ① **win_inspector template** — 클릭 직전 walk-up 패턴 추가. `_clickable_types = {Button, MenuItem, MenuBarItem, TabItem, ListItem, CheckBox, RadioButton, Hyperlink, Edit, ComboBox, SplitButton, TreeItem}`. element 의 control_type 이 set 에 없으면 최대 6 단계까지 parent() 로 walk up 해서 첫 클릭 가능 ancestor 를 `click_target` 으로. promotion 후 `click_target.rectangle()` 로 center 계산, fallback 도 `click_target.click()` 호출. 이미 클릭 가능한 타입은 promote 안 함 → 회귀 X. ② **prompts.json guideline 18** — Text/Image/Pane leaf → 부모 promote 패턴 강제. test_64 (template walk-up + click_target + clickable types + promote skip 회귀 검증), test_65 (prompt 가이드 영구). scenarios 65/65 + core 75/75 그린. **새 세션부터 메뉴바 라벨 / 아이콘 / 그룹 등 leaf 픽도 부모 클릭 핸들러 도달**. |
| 5/5 (밤) | **비브라우저 앱 title hardcoding fix — title_re program 명만 매칭** (사용자 보고: 새 메모장 세션 step 2 가 step 1 이 연 새 빈 메모장에서 보기 메뉴 못 찾음 → ElementNotFoundError). 원인: win_inspector 가 element 픽 시점의 full window title (예: `*hello world - 메모장`) 을 그대로 hardcode. step 1 이 새 메모장 열어 title 이 `제목 없음 - 메모장` 으로 바뀌니 connect 매칭 실패. 2 layer fix: ① **win_inspector 분기** — `is_browser_process` 면 full title 유지 (페이지별 식별), 아니면 `parent_title.split(' - ')[-1]` 로 program 명 추출 → `re.escape` 후 `title_re=r".*<program>"` 로 안전 매칭. 메모장 → `.*메모장`, IDE/계산기 등 동일. ② **prompts.json guideline 17** — full title hardcoding 금지 + program 명만 사용 강제 명시. 실측 검증: 메모장 `title_re='.*메모장'` / Chrome `title="업무전산 시스템 - Chrome"` (브라우저는 그대로). test_62 (template 패턴 검증), test_63 (prompt 가이드). scenarios 63/63 + core 75/75 그린. **새 세션부터 비브라우저 앱이 새/기존 인스턴스 무관 매칭**. |
| 5/5 (밤) | **데스크톱 click 전략 fix — pyautogui PRIMARY** (사용자 보고: Win11 메모장 "보기" 메뉴 클릭 안 됨). 원인: win_inspector 데스크톱 template 이 `element.click()` (WM 메시지 / UIA InvokePattern) 을 PRIMARY 로, pyautogui 는 권한 에러일 때만 fallback. UWP/XAML (Win11 메모장) 에서 element.click() 이 silent 실패 — 예외 안 나는데 클릭 효과 없음 → fallback 트리거 X → "보기" 메뉴 안 열림. 또 `control_type="Text"` 같은 라벨 컨트롤 클릭 시 부모 MenuItem 으로 invoke 전달 안 됨. 2 layer fix: ① **win_inspector.py 데스크톱/브라우저 통합 분기** — 둘 다 pyautogui.click(center_x, center_y) PRIMARY, element.click() fallback. pyautogui 의 OS 레벨 SendInput 이 좌표 hit-test 라 Text 라벨 → 부모 MenuItem 까지 자동 도달. ② **prompts.json system_context guideline 16** — element.click() silent 실패 함정 명시 + pyautogui PRIMARY 강제. test_60 (template 코드 검증 — element.click() 권한 fallback 패턴 부재 + pyautogui PRIMARY 명시), test_61 (prompt 가이드 영구성). scenarios 61/61 + core 75/75 그린. **새 세션부터 데스크톱 element 도 pyautogui.click 우선 → UWP 앱 메뉴/버튼 정상 클릭**. |
| 5/5 (밤) | **step_code/step_imports 누락 회귀 fix — 백업 패턴 복원** (사용자 보고: "웹브라우저 새로고침 현상이 2~3번 반복" + "각 step 에 이전 모든 step 코드들이 추가되는 형태"). 원인: ui_v2 redesign 시 [AppService.generate_step](../core/app_service.py#L370) 가 `generated_code` 만 채우고 `step_code`/`step_imports` 는 빈 채로 저장. 백업 [ohdo_20260505_backup/ohdo/ui/ai_call_handler.py:248~287] 에서는 AI 응답 받자마자 `extract_imports` + `extract_code_delta` 로 분리해서 step 별 delta + 새 import 만 저장. 현재는 비어있어 [extract_step_delta_code](../core/workflow_engine.py) 의 priority 1 (marker) 가 깨질 때 fallback 으로 priority 4 (전체 generated_code) → 누적 코드 전체 실행 → driver.maximize/get 중복 → 페이지 새로고침 반복. 회귀 fix: ① **AppService.generate_step 백업 패턴 이식** — `extract_imports`/`extract_code_delta`/`extract_import_delta` 호출, **last-non-empty step 을 prev 로 사용** (empty step 끼어 있어도 안전), 호출자 stale session 회피 위해 디스크에서 fresh load. ② **workflow_engine.execute_session_blocks** — empty step skip 시 `prev_step_dict` 갱신 X (다음 step 의 diff 가 깨지지 않게). test_58 (delta + 새 imports 분리), test_59 (empty prev step skip + last-non-empty 사용). scenarios 59/59 + core 75/75 그린. **새 세션부터 step_code/step_imports 자동 채워짐 → 라이브러리 카드 + step 카드 분리 아키텍처 복원**. |
| 5/5 (밤) | **SW_RESTORE → IsIconic 분기 fix** (사용자 보고: 'work.wooyang.co.kr' ID 입력 안 됨 + "전체창이 축소됨"). 원인: pywinauto template 의 `user32.ShowWindow(hwnd, 9)` (SW_RESTORE) 가 maximized Chrome 을 normal 사이즈로 축소 → 직전에 계산한 element 좌표 (1440, 901) 가 무효화 → 클릭이 빈 곳에 가서 focus 못 받음 → `pyautogui.write('doosung.oh')` 가 어디에도 안 들어감. step 3 (PW) 는 새로 좌표 재계산해서 정상 동작. 3 layer fix: ① **workflow_engine.make_show_window_safe** 신규 — 모든 `ShowWindow(hwnd_var, 9)` 를 `if user32.IsIconic(hwnd_var): SW_RESTORE; else: SW_SHOW` 로 자동 변환 (변수명/모듈 prefix 보존, 자기 멱등). ② **win_inspector.py 데스크톱/owner-drawn template** — IsIconic 분기 + element.rectangle() 호출을 활성화 후로 이동 (최신 좌표 보장). ③ **prompts.json system_context guideline 15** — SW_RESTORE 함정 명시 + IsIconic 권장 패턴 + 좌표 계산 순서 가이드. test_56 (transformer + 변수명/멱등/SW_HIDE 미변환), test_57 (prompt + template 영구 가이드). scenarios 57/57 + core 75/75 그린. **기존 세션도 다음 실행부터 즉시 효과**. |
| 5/5 (밤) | **다중 브라우저 회귀 fix — idempotent driver guard** (사용자 보고: "전체 실행" 후 웹브라우저가 3 개 띄워짐). 원인: step 1 의 `driver = webdriver.Chrome(...)` 가 매 실행마다 새 인스턴스 생성. "전체 실행" 두세 번 클릭하거나 silent replay 가 일어나면 누적. 누적된 다중 driver 가 step 2 의 `Application().connect(title="...")` ambiguous 도 유발. 3 layer fix: ① **workflow_engine.make_browser_init_idempotent** 신규 — 실행 직전 모든 delta_code/library_block 의 `driver = webdriver.{Chrome|Firefox|Edge|Safari|Remote}(...)` 호출을 paren-aware 로 추출해 `try: _ = driver.window_handles; except Exception: <원본 호출>` 가드로 감쌈. 이미 감싼 코드는 prefix 검사로 중복 적용 방지 (자기 멱등). 멀티라인/nested 호출/comment/string literal 전부 처리. ② **win_inspector.py 브라우저 템플릿** (line 449~) — 향후 AI 생성 코드도 idempotent 패턴으로 시작. ③ **prompts.json system_context guideline 14** — AI 에게 idempotent driver 패턴 명시 ("'전체 실행' 두 번 눌러도 1 개" 사용자 사례 포함). test_54 (transformer 동작 + 멱등성 + 멀티라인 + Firefox), test_55 (prompt + template 영구 가이드 회귀 안전망). scenarios 55/55 그린, core 75/75 유지. **기존 e862c477 세션도 다음 실행부터 즉시 효과** (코드 재생성 불필요). |

상세는 [docs/triage.md](triage.md) 참조.

## 6. 미해결 / 사용자 결정 대기

1. ~~**ROADMAP §1 라이선스 전략 결정**~~ → **2026-05-05 결정 확정**: 오픈코어 (AGPL-3.0 데스크톱 + 추후 폐쇄 SaaS). v1.0 은 100% AGPL-3.0, SaaS 유료/무료 라인은 Phase 2 진입 시점에 결정. (LICENSE 파일/코드 헤더 추가는 미실행 — 사용자 결정 대기)
2. **PySide6 포트 GUI 검증**: 양쪽 동작 비교 — 사용자 직접 GUI 테스트 필요. 별도 venv 없어서 import sanity 도 사용자 환경에서.
3. ~~**foreground 복원 보류**~~ → **5/4 저녁 해결됨** (§4.5 참조). 사용자 GUI 테스트 통과.
4. **5/4-5/5 작업 사용자 GUI 검증 미확인**: 다음 항목들은 자동 회귀 테스트는 그린이지만 실제 GUI 동작은 사용자 테스트 미완료 — 새 세션에서 첫 sanity check 시 같이 확인하면 좋음:
   - 코드 편집 desync 4중 안전장치 (§4.8) — 블럭 뷰/코드 뷰에서 코드 수정 → 양쪽 동기화 + 실행 정확
   - 세션 추가/삭제 시 블럭 뷰 초기화
   - 실행 종료 시 run/stop 버튼 자동 리셋 (코드 뷰 + 블럭 뷰 양쪽)
   - Gemini CLI 모델 명시 — `gemini-2.5-flash` 로 명시 호출되는지 (5/5: `_build_args` 가 두 production path 에 적용됨, source 검증 test_71 통과 — 실 capacity 회귀 재현 여부 사용자 확인)
   - **Phase 2.5: Initial 블럭 단독 실행** (§4.9) — Initial 블럭 카드의 "⏯ 단독" 버튼 클릭 → driver/options 등 재초기화되는지. 라이브러리 미초기화 상태 / 초기화된 상태 양쪽 시나리오 확인. 다른 step status 안 건드리는지.
4. **PySide6 양쪽 동기화 정책**: 코드 수정 시 어디 먼저 적용할지. 현재 PyQt6 원본 먼저 → 수동 sed 로 sync (자동 스크립트 없음).
5. **API key 저장 위치 (D2 후속)**: 현재 `settings.json` 평문. OS keyring (Windows Credential Manager) 으로 옮길지 사용자 결정 대기. v1.0 공개 전 결정 권장 (보안 디폴트).
6. **장기 AI 모델 (D2 후속)**: BYO API 키만 / ohdo 크레딧 SaaS / 둘 다 — 미정. 현 어댑터는 BYO 우선 설계지만 SaaS 모드 ('proxy' base_url) 로 확장 가능.

## 7. 다음 작업 후보 (우선순위 순)

| 우선순위 | 작업 | 비고 |
|---------|------|-----|
| 1 | **ui_v2 사용자 GUI 검증** — `python main.py --ui v2` 실행 → 와이어프레임 의도와 비교. **이제 실 동작**: AI 호출 / 전체+단독+여기서부터 실행 / 캡처 / 요소픽 / Settings 모두. 어색한 부분 / 빠진 인터랙션 / 디자인 토큰 fine-tune 피드백. | 핵심 검증. PoC 의 stub 영역은 D8 Command palette / D9 토스트 / D14 onboarding 등 미구현 항목만. |
| 2 | **AppService 후속** — 미흡한 분리 영역 추가. `export_workflow` (D22 의 stub 채우기 — main.py + requirements.txt + run.bat 패키징, v1 export_project 활용), `import_workflow` (외부 폴더에서 세션 import). | D22 의 export 가 현재 폴더 통째로 복사 stub. 정식 패키징 필요. |
| 4 | **UI redesign 준비 Step 0 #3: baseline UI 스크린샷** — `data/baseline_ui/` 에 v1 메인 화면 + 다이얼로그들 캡처. 시각 비교 baseline. | 사용자 GUI 작업 (Claude 가 캡처 못 함). |
| 5 | **Excalidraw/Figma 정식 와이어프레임** — wireframes_v2.md 텍스트 → 시각. ui_v2 PoC 와 병행. | 사용자 작업 권장. |
| 6 | AI prompt 강화 + delta fix 효과 측정 — `ai_integration` suite 으로 실제 생성 코드 검증 | 5/4 밤 가이드/필터 추가 후 실 데이터로 회귀율 확인. |
| 7 | LICENSE 파일 (AGPL-3.0) + README 라이선스 섹션 + 모든 source 파일 SPDX 헤더 | Phase 0 시작 시 묶어서 처리 권장 (uv/devcontainer/CI 와 함께). |
| 8 | Phase 0 본격 진입 — `pyproject.toml + uv`, devcontainer, pre-commit, GitHub Actions CI | ROADMAP Phase 0. 데스크톱 안정화 ~80% 도달 시. |
| 9 | SaaS M3.2+ 재개 | Phase 0/1 완료 후. |
| 10 | **AI 자동 에러 복구 기능** (5/6 사용자 아이디어) — step 실행 중 에러 발생 시 AI 가 에러 메시지 + 해당 step 코드 + 누적 컨텍스트 보고 자동으로 코드 수정 + 재시도. | `prompts.json` 의 `error_recovery` 템플릿 (line 6) 은 이미 존재하지만 자동 trigger 없음. 설계 필요: (a) 자동/수동 trigger 토글, (b) retry budget (예: 최대 2회), (c) 사용자 confirm 옵션, (d) 어떤 에러를 자동 처리하고 어떤 건 사용자 개입 요청할지 분류. AppService.generate_step 흐름에 통합. |

**5/5 완료**:
- ~~Gemini adapter `_build_args` production path 적용~~ — 두 Popen 호출 모두 `_build_args` 경유, test_71 production path 검증 추가.
- ~~ROADMAP §1 라이선스 전략 결정~~ — 오픈코어 (AGPL-3.0 데스크톱 + 추후 폐쇄 SaaS) 확정.
- ~~Phase 2.5: Initial 블럭 단독 실행~~ — INITIAL_BLOCK_STEP_ID=-1, BlockCard 단독 버튼 확장, on_run_initial_block + library 자동 선행. test_74 (74/74 그린).
- ~~UI redesign Step 0 #1: feature_catalog.md~~ — 현재 UI 전체 카탈로그 (14 섹션). 사용자 검증 후 Step 0 #2/#3 진행.
- ~~D2 OpenAI 호환 어댑터 구현~~ — `OpenAICompatAdapter` + 9 프리셋 + Settings UI. test_75 (75/75 그린).
- ~~UI redesign 13건 일괄 결정 (D4~D16)~~ — feature_catalog.md §13 미결정 0건.
- ~~Step 0 #2: tests/test_scenarios.py~~ — 16 시나리오 behavior-level 테스트. scenarios suite 등록, 16/16 그린.
- ~~D 와이어프레임 1차 초안: wireframes_v2.md~~ — 텍스트 와이어프레임 12 섹션.
- ~~D17~D26 + onboarding 확정~~ — 와이어프레임 도중 발견 10건 + onboarding 추천 3개 모두 권장안.
- ~~Step 1: AppService façade 확장~~ — 코드 추출/실행/AI ops 메서드 추가. test_scenarios 20/20. ADR 0001 준수 (기존 UI 미수정).
- ~~ui_v2 PoC 1차 슬라이스~~ — 메인 윈도우 + 카드 + 입력 + 단축키 + Initial 단독 실행 동작. `--ui v2` 분기. test_21~23. scenarios 23/23.
- ~~D3 데이터 모델 + ui_v2 AI 호출~~ — Step 에 user_request/ai_description 필드, AppService.generate_step, ui_v2 메시지 전송 실 동작. test_24~26. scenarios 26/26.
- ~~ui_v2 실행 stub 채우기~~ — AppService.run_blocks/stop_blocks, ui_v2 _on_run_all/from/single/stop 실 동작. test_27~28. scenarios 28/28.
- ~~ui_v2 캡처/요소픽/Settings stub 채우기~~ — v1 overlay/dialog 재사용. pending images/elements + chip 갱신. test_29~30. scenarios 30/30.
- ~~ui_v2 카드 가로 스크롤 회귀 fix~~ — 사용자 보고. 4 fix 적용 (sizePolicy, _tame_text_widget, scroll AlwaysOff, AI preview QLabel).
- ~~D9/D17/D20/D25 일괄 구현~~ — Toast/ToastManager, 사용자 요청 클릭 재생성, 사이드바 toggle persist, 빈 상태 + 예시 카드. test_31~33. scenarios 33/33.
- ~~D8 Command palette + D14 Onboarding wizard~~ — Ctrl+K 실 호출 + 첫 실행 wizard. test_34~36. scenarios 36/36. ui_v2 의 D 결정 거의 cover (D4 다중 세션 탭만 별도).
- ~~D4 다중 세션 탭 + D21 + D22~~ — QTabBar + 세션별 커널 dict + 탭별 pending state + + 탭 메뉴 + 우클릭 메뉴. test_37~39. scenarios 39/39. **D1~D26 거의 cover** (D23 drag reorder 만 남음).
- ~~D23 step reorder ⬆⬇ 버튼 fallback~~ — drag-drop 의 일부. 버튼만 먼저, drag-drop 본체는 후속. test_40. scenarios 40/40.
- ~~사용자 보고 fix + 전송/중지 토글~~ — 캡처 버튼 가시성, elempick 강제종료 fix, send_btn 토글. test_41. scenarios 41/41.
- ~~D23 drag-drop 본체~~ — CardDropContainer + StepCardV2 drag source + AppService.reorder_step. test_42. scenarios 42/42. **D1~D26 100% cover**.
- ~~Syntax highlighting + 코드 편집~~ — v1 의 PythonHighlighter + BlockCard 편집 토글 패턴 v2 에 이식. test_43. scenarios 43/43.
- ~~세션 영구 삭제~~ — _on_session_delete + 사이드바 우클릭 + 탭 우클릭 메뉴. test_44. scenarios 44/44.

## 8. 첫 작업 권장

새 세션에서 추천 흐름:

1. **이 파일 + docs/triage.md 빠르게 읽기**
2. `venv\Scripts\python.exe -m tests.test_runner --suite core` (75/75) + `--suite scenarios` (70/70) 실행 → **baseline 무손상 검증**. venv 경로는 `venv/` (점 없음).
3. 사용자에게 직전 GUI 테스트 결과 확인 (§11 참조).

## 11. 5/5 밤 ~ 5/6 새벽 작업 인계 (이전 세션 마지막)

**컨텍스트**: 사용자가 ohdo 의 메모장/브라우저 자동화 시나리오를 반복 테스트하면서 발견된 회귀들을 8 layer 로 fix. 매 fix 후 사용자가 새 세션 만들어 검증하는 루프 진행. 마지막 작업은 [tmp/conversations/](../tmp/conversations/) 자동 로깅 추가 — 다음 사용자 테스트부터 prompt + AI 응답이 자동 저장됨.

**적용된 8 layer fix (모두 PyQt6 + PySide6 sync, scenarios 70/70 + core 75/75 그린)**:

| # | fix | 영향 | 검증 |
|---|-----|------|------|
| 1 | idempotent driver guard ([workflow_engine.make_browser_init_idempotent](../core/workflow_engine.py)) | "전체 실행" 두세 번 클릭 또는 silent replay 시 새 브라우저 안 뜸 | test_54/55 |
| 2 | SW_RESTORE → IsIconic 분기 ([workflow_engine.make_show_window_safe](../core/workflow_engine.py) + win_inspector template) | maximized 창이 normal 로 축소되어 좌표 무효화되는 회귀 방지 | test_56/57 |
| 3 | step_code/step_imports 분리 ([AppService.generate_step](../core/app_service.py)) — 백업 패턴 복원 | 라이브러리/step 카드 분리 아키텍처 회복, 새로고침 반복 회귀 fix | test_58/59 |
| 4 | 데스크톱 click pyautogui PRIMARY (win_inspector template) | UWP/XAML 의 element.click() silent 실패 회피 | test_60/61 |
| 5 | 비브라우저 title_re program 명 매칭 (win_inspector) | 메모장처럼 title 에 문서 내용이 들어가는 앱 매칭 안정화 | test_62/63 |
| 6 | leaf element 클릭 가능 부모 walk-up promote (win_inspector + picker descent 가드) | Text 라벨 픽 → 부모 MenuItem 으로 자동 promote | test_64/65/66/67 |
| 7 | AI 환각 import 자동 교정 (workflow_engine.fix_hallucinated_imports) | `FindBestMatchException` → `MatchError` cascade fail 방지 | test_68/69 |
| 8 | tmp/ 정리 + AI 대화 자동 로그 (AppService._save_conversation_log) | generate_step 마다 prompt + 응답 단일 .md 로 저장 | test_70 |

**사용자 검증 상태 (다음 세션에서 첫 확인)**:
- ✅ 메모장 메뉴 (파일/보기) 클릭 — 5/6 새벽 picker descent 가드 fix 후 정상 (사용자 확인됨)
- ⚠️ wooyang 브라우저 세션 (eb17030a) — `FindBestMatchException` cascade 회귀. 다시 실행하면 workflow_engine 의 hallucinated_imports 교정으로 자동 복구돼야 함. **사용자 미검증**.
- ⚠️ tmp/conversations/ 로그 — 신규 기능. 다음 사용자 테스트 시 실제 .md 파일 생성 확인 필요.

**미해결 / 후속 후보**:
- guideline 14~19 가 prompts.json system_context 에 누적돼 있음. AI 가 매번 1.7만~2만자 이상의 거대한 프롬프트를 받고 있어 응답 속도/품질 영향 우려. **다음 작업 후보**: 가이드라인 통합/압축 검토.
- 기존 wooyang 세션은 step_code 가 비어있어 (이전 generate_step 시 백업 패턴 미적용 시점) 일부 fallback 경로만 사용. 새로 생성하는 세션부터 정상 분리.
- ui_v2 GUI 사용자 테스트 미검증 (§6 #4 항목들). 메모장/브라우저 시나리오 외에 다른 워크플로우 (계산기/IDE 등) 검증 필요.

**5/6 새 세션에서 권장 첫 행동**:
1. baseline 테스트 (`core` + `scenarios`) 실행해서 그린 확인
2. 사용자에게 "어제 fix 들 (특히 8 layer 마지막 — wooyang 세션 재실행 + tmp/conversations 로그 확인) 어떻게 됐는지" 물어보기
3. 그에 따라 후속 fix 또는 다음 작업 후보 (§7) 진입

## 12. 5/6 일과 작업 누적 정리 (prompt 압축 + 모델 변경 + element 메타 강화)

**컨텍스트**: 5/6 종일 사용자 GUI 테스트 + 가이드 강화 루프 + prompt size 폭증으로 인한 Gemini corrupt 응답 root fix. 최종적으로 9 step 까지 깨짐 없이 진행 가능 + prompt size 28% 감소 + AI 응답 quality 회복.

### 적용된 fix (시간순)

| # | 작업 | 영향 | 위치 |
|---|---|---|---|
| 1 | **prompts.json system_context 압축** — 가이드 19개 누적 정상화 (1~19 정상순서, 메타 정보 제거, #11+#19 / #15+#16 통합) + archive 보존 (`config/prompts_archive/prompts_2026-05-06_pre-compression.json`) | 5,911 → 4,900 chars 시작 (이후 가이드 강화로 늘어남) | [config/prompts.json](../config/prompts.json), [config/prompts_archive/](../config/prompts_archive/) |
| 2 | **#13 ASCII/CJK 분기** — `pyautogui.write` 한글 silent skip → ASCII 만 write, CJK 는 `pyperclip.copy + Ctrl+V` | 한글 텍스트 입력 정상화 | prompts.json #13, [core/win_inspector.py](../core/win_inspector.py) (입력 템플릿) |
| 3 | **#14 데스크톱 idempotent + UWP wait 안정성** — 가이드 #14(b) Application.connect try/except 강제, #14(c) UWP `wait('visible')` 권장 | "메모장 실행" 매번 새 인스턴스 회귀 fix | prompts.json #14 |
| 4 | **#18 다이얼로그 처리 트리거** — 5가지 트리거 (자연어 조건/명시 키워드/picker context mismatch/직전 step modal flow/`parent_window_control_type='Dialog'`) + `_find_dialog` 패턴 | 모달 다이얼로그 자동 분기 처리 | prompts.json #18 |
| 5 | **#19 hotkey 표준 키 이름** — `'control'` (X) / `'ctrl'` (O) 명시 + ✅/❌ 예시 | Ctrl+Shift+S 같은 단축키가 's' 만 입력되는 회귀 fix | prompts.json #19 |
| 6 | **prompt_builder 환경 정보** — `_build_env_info_lines()` cache 추가. Python/pywinauto/selenium/pyautogui/pyperclip 버전 자동 detect 후 매 prompt prepend | AI 가 정확한 라이브러리 시그니처 사용 | [core/prompt_builder.py:23](../core/prompt_builder.py#L23) |
| 7 | **#11 메서드 시그니처 명시** — `Application.connect`/`window`/`Desktop().window`/`child_window`/`wait`/`find_elements` 가 받는 kwargs 정확히 나열. timeout 받는 곳 ✅/안 받는 곳 ❌ | `Desktop().window(timeout=N)` invalid kwarg 회귀 fix | prompts.json #11 |
| 8 | **F-3 변수 명명 규칙** — `app` = `Application` 객체, `win` = `WindowSpecification`. `Desktop().window(...)` 결과는 `win` 으로 명명 (절대 `app` 으로 X — 후속 step 의 `app.window()` 호출이 자식 검색이 되어 0 windows found 회귀) | prompt_builder 의 Windows 가이드와 system_context 일관성 회복 | prompts.json #14(b), [core/prompt_builder.py:248](../core/prompt_builder.py#L248) |
| 9 | **E-1 새 step 강제** — "사용자의 새 요청은 누적 코드와 동일해 보여도 반드시 새 step 마커 + 본문 추가" 명령. 빈 step / step 생략 금지 | AI 가 같은 요청 반복 시 새 step 안 만들고 누적 코드만 반환하는 회귀 fix | [core/prompt_builder.py:124](../core/prompt_builder.py#L124) |
| 10 | **E-2 extract_step_delta_code fallback 차단** — generated_code 전체 fallback 을 `prev_step is None` (첫 step) 만 valid 로 제한. prev_step 있으면 빈 string 반환 (fail-fast) | AI 가 새 step 안 만들 때 누적 코드 통째 step_code 저장되는 회귀 fix | [core/workflow_engine.py:1141](../core/workflow_engine.py#L1141) |
| 11 | **자동 교정 확장** — `fix_hallucinated_imports` 가 `FindBestMatchException` + `FindBestMatch` + `FindBestMatch.MatchError` 모두 `MatchError` 로 변환 | AI 의 새 환각 패턴 (5/6) 자동 fix | [core/workflow_engine.py:1029](../core/workflow_engine.py#L1029) |
| 12 | **picker parent_window_control_type capture + Dialog 안내** — `top_level_parent().element_info.control_type` 도 capture. element_context 에 모달 다이얼로그 안내 추가 (가이드 #18 자동 트리거) | picker 가 dialog 안 element 잡으면 AI 가 자동으로 `_find_dialog` 패턴 사용 | [ui/element_picker.py:1227](../ui/element_picker.py#L1227), [core/win_inspector.py:633](../core/win_inspector.py#L633) |
| 13 | **format_element_label helper** — chat_panel/ai_call_handler/ui_inspection_handler 의 inline element 표시 로직 통합. Dialog 부모 인 경우 "(Dialog: ...)" suffix, name 없으면 parent_title 빌림 | UI 표시 일관성 + 정보 풍부 | [core/win_inspector.py:38](../core/win_inspector.py#L38) (helper) + ui/ 3 파일 |
| 14 | **win_inspector 텍스트 입력 placeholder 강화** — `text = 'your_text_here'` → `text = '<<USER_TEXT>>'`. ⚠ 명시 + 조건부 사용 명령 + 키 입력 전용 가이드 분리 | AI 가 placeholder template 을 그대로 코드에 박는 회귀 fix | [core/win_inspector.py:898](../core/win_inspector.py#L898) |
| 15 | **prompt 본문 압축** — `_compress_accumulated_code(keep_last_n=1)` 추가. 마지막 1 step body 만 keep, 이전 step body → 한 줄 마커 (`# === Step N: <task> (본문 생략 — 이미 실행됨) ===`) | prompt 35K → 26K (28% 감소). step 수 늘어도 선형 증가 X | [core/prompt_builder.py:688](../core/prompt_builder.py#L688) |
| 16 | **이미지 첨부 OFF** — `AppService.generate_step` 이 AI 호출 시 `images=None` 전달 (session log 에는 path keep, UI 표시 + 미래 image-based matching 시 활용) | vision latency 5-15s 감소 + Gemini context 부담 감소 | [core/app_service.py:418](../core/app_service.py#L418) |
| 17 | **모델 변경: gemini-2.5-flash → gemini-3.1-pro-preview** + 회귀 가드 완화 (`startswith("gemini-2")` → `startswith("gemini-")`. CLI default 자동 매핑은 여전히 차단, 사용자 명시 preview 만 허용) | 응답 quality 향상 (corrupt/broken 회피). latency 증가 trade-off | [config/settings.json:7](../config/settings.json#L7), [tests/test_core.py:2293](../tests/test_core.py#L2293) |
| 18 | **AppService.save_session 추가** — handoff §3 에 명시됐지만 누락된 메서드. ui_v2 의 세션 이름 변경 등에서 AttributeError 발생 fix | 세션 rename + 사이드바 액션 정상 작동 | [core/app_service.py:78](../core/app_service.py#L78) |

### 검증 결과 — 9 step 세션에서 압축 효과 확인

| 비교 | 압축 전 (9f08ab5d, 8 step) | 압축 후 (de751707, 9 step) |
|---|---|---|
| 평균 prompt | 27,926자 | **23,700자** |
| 최대 prompt | 35,995자 (step 7 corrupt) | **26,427자 (step 9 정상)** |
| step 7 응답 | 24자 (`<ctrl46>` corrupt) | 5,301자 (정상) |
| step 8 응답 | 26,203자 (broken IndentationError) | 5,678자 (정상) |
| 9 step 도달? | ❌ corrupt 7 / broken 8 | ✅ 정상 |

**선형 증가 곡선 → flat 곡선** 으로 전환. step 7-8 기준 ~28% 감소.

### 회귀 가드 갱신
- core 75/75 ✅ / scenarios 70/70 ✅
- test_71 (gemini model) — `gemini-` prefix 만 검증 (preview 허용)

### 미해결 / 후속 작업

**후보 (handoff §7 #10)**: AI 자동 에러 복구 기능 — step 실행 실패 시 AI 가 자동 코드 수정 + 재시도. `prompts.json` 의 `error_recovery` 템플릿은 이미 존재, trigger 흐름만 추가 필요.

### 5/6 → 5/7 새 세션 시작 권장 흐름

1. `core` + `scenarios` baseline 그린 확인 (75/75 + 70/70)
2. 사용자에게 "5/6 fix 들 GUI 검증 결과 어떻게 됐는지" 묻기 (특히 prompt 압축 효과 + 모델 변경 후 응답 quality)
3. 그 결과에 따라:
   - 사용자 만족 → 다음 작업 후보 (§7) 진입 (Phase 0 / D2 / AI 자동 에러 복구 §10 등)
   - 추가 fix 필요 → 사용자 보고 분석 + fix

## 9. 자주 하는 실수 / 주의사항

- **메서드 직접 추가 시**: PyQt6 원본만 수정하고 PySide6 포트 sync 잊으면 양쪽 불일치. 항상 양쪽 확인. core/ 변경은 `cp` 로 복사 (라이브러리 의존성 없음), ui/ 변경은 sed 로 `PyQt6` → `PySide6` 치환.
- **test 메시지에 em-dash 사용**: cp949 인코딩 에러로 test runner 가 ERROR 표시. hyphen 사용. (docstring/markdown 은 OK)
- **delta 추출 fallback**: `.strip()` 사용하면 첫 라인 indent 잘려 `_smart_dedent` 가 못 풀어줌. 사용 금지.
- **wait UI signal**: `valueChanged` 사용하면 매 키 입력마다 emit → 카드 재생성 → 포커스 손실. `editingFinished` 만 사용.
- **개별 step wait 변경 핸들러**: `_refresh_block_view` 호출하면 카드 재생성 → 포커스 손실. session 저장만.
- **handler 분해 시 회귀 테스트**: `inspect.getsource(MainWindow._method)` 로 검사하던 테스트는 메서드가 handler 로 옮겨가면 fail. 검사 대상을 `Handler.method` 로 변경 + `self.xxx` → `mw.xxx` 변환된 패턴으로 assertion 갱신 필수.
- **코드 편집 핸들러는 두 필드 동시 업데이트**: `step_code` 와 `generated_code` 가 desync 되면 `extract_step_delta_code` (실행/화면) 가 stale 한 쪽 우선해 사용자 수정 무시 회귀 발생 (§4.8).
- **subprocess 의 SendInput 으로 ForegroundLock 이전**: pyautogui 같은 input 시뮬레이션 사용 시 권한이 subprocess 로 이동 — `OHDO_PARENT_PID` + `AllowSetForegroundWindow` 패턴 깨면 회귀 (§4.5).

## 10. 사용자에게 빠르게 물어볼 후보

세션 시작 직후 사용자에게 물어볼 만한 질문:
- "다음 작업 후보 (§7) 중 어느 거 진행할까?" (Phase 2.5 Initial 블럭 단독 실행 / AI prompt 효과 측정 / main_window 추가 분해)
- "PySide6 포트 GUI 검증 결과는?"
- "LICENSE 파일 (AGPL-3.0) 추가할까? README 라이선스 섹션도 같이 작성?"
