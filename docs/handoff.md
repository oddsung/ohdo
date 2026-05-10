# Claude Code 세션 인계 문서 (Handoff)

> **사용법**: 새 Claude 세션 시작 시 첫 입력으로 "이 파일 읽고 이어서 작업" 하라고 하세요.
> 이 문서는 Claude 의 auto-memory 가 컴퓨터 간 옮겨지지 않아 새 세션에서 컨텍스트 빠르게 복원하기 위한 용도입니다.
> 마지막 업데이트: 2026-05-10 (5/4~5/10 작업 — 자세한 변경은 §5 변경 이력 + §11/§12/§13/§14/§15/§16 인계 노트 참조). baseline: **core 96/96 + scenarios 73/73 그린**. **wireframe D1~D26 100% 구현 완료**. 5/7~5/8: Phase 0 인프라 표준화 5/7 sub-phase 완료 — pyproject.toml + uv + pre-commit + ruff (lint+format) + LICENSE (AGPL-3.0) + SPDX 헤더 113 파일 + GitHub Actions CI + .devcontainer. **5/8~5/9: Phase 1 5/5 sub-task 모두 완료** — 저장소 추상화 + UI-Core 분리 (Chunk A 5/8 + Chunk B 5/9) + Pydantic 모델 + 설정 레이어 + Agent 브리지. **5/9 시장 타깃 결정**: 한국 niche → **글로벌 + 한국 dual-locale**. 영어 README + UI/메시지 i18n 작업이 Phase 2 진입 직전 필수. **Phase 2 진입은 [docs/commercial_review.md](commercial_review.md) GO/NO-GO 게이트 통과 후 결정** (5/9 글로벌 dual-locale 반영 갱신). **5/9~5/10: Phase 1.8 OpenAI 호환 (DeepSeek) 등록 + 코드 생성 품질 루프 — Step A/B (settings dialog Test connection + reload_ai), B1+B2+B4 (current_engine 속성명 fix + ui_v2 step_done 메타 + ai.selected persist), P4 (콘솔 가시성 settings 따름), P1a/P1b/P3 (system_context 가 prompt 에 inject + system role 분리 + 가이드 #3/#5 강화), G1/G2/G2.5 (element_context 템플릿 + element 변수 자동 정의 명시 + import 라인 제거), G5 (library 블럭 essential imports prepend) — 11 unit, test_86~96 회귀 가드. baseline 85→96 (+11 guards). 자세한 §16.

## 1. 프로젝트 한 줄 요약

**ohdo** — AI (Gemini CLI) 와 대화하면서 Windows 데스크톱/웹 자동화 코드를 단계별로 생성/실행하는 PyQt6 기반 RPA 솔루션. SaaS 확장 계획 진행 중 ([docs/ROADMAP.md](ROADMAP.md) §1, AGPL-3.0 데스크톱 + 상업 SaaS 오픈코어 전략 — **2026-05-05 사용자 결정 확정**).

## 2. 작업 환경 (사용자 preference)

- **터미널**: PowerShell (복붙용 명령은 PowerShell 문법 — `Activate.ps1`, `$env:X`, `Copy-Item`)
- **Python 의존성 (5/7 Phase 0 sub-phase 1 도입)**: `pyproject.toml` + `uv` (lockfile: `uv.lock`). 새 머신 셋업: `uv sync` → `.venv/` 자동 생성. 실행: `.venv\Scripts\python.exe ...`.
  - **레거시 `venv/`** (점 없음) 도 그대로 유지 — 5/6 까지 사용한 기존 환경. 둘 다 baseline 그린. 새 setup 은 `.venv/` 권장.
  - 시스템 `python` 은 고장난 3.8 32-bit — 절대 사용 X.
- **em-dash (—) cp949 인코딩 금지**: test/log/print 메시지에 사용 X. hyphen (-) 사용. (docstring/markdown 은 OK)
  - 5/7 부터 `tests/test_runner.py` 가 `sys.stdout.reconfigure(errors='replace')` 로 fallback 처리 — em-dash 가 ERROR 안 내고 `?` 로 표시됨. 그래도 가능한 hyphen 권장.
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

## 13. 5/7 D22 export/import 워크플로우 정식 구현

**컨텍스트**: 5/6 GUI 검증 결과 큰 문제 없음 → §7 후속 작업 진입. §7-10 (AI 자동 에러 복구) 는 사용자 보류 → §7-2 진행.

### 적용된 변경

| # | 작업 | 영향 | 위치 |
|---|---|---|---|
| 1 | `SessionManager.export_as_project` 확장 — session.json + captures/ + scripts/ 도 같이 복사 | export 결과가 실행 가능 + import 가능 단일 번들 | [core/session_manager.py:527](../core/session_manager.py#L527) |
| 2 | `SessionManager.import_session_folder` 신규 — 외부 export 폴더 → 새 UUID 로 data/sessions/ 복사 + 옛 UUID 일괄 치환 (captures 절대 경로 cover) | 다른 PC 워크플로우 가져오기 가능. 같은 export 두 번 import 도 충돌 X | [core/session_manager.py](../core/session_manager.py) |
| 3 | `AppService.export_workflow(session_id, output_dir, settings=None)` + `import_workflow(source_dir, new_title=None)` 신규 façade | UI 가 단일 진입점만 의존 (ADR 0001 준수) | [core/app_service.py](../core/app_service.py) |
| 4 | ui_v2 `_on_tab_export` 교체 — stub `shutil.copytree` → `app_service.export_workflow` | D22 stub 정식판으로 승격 | [ui_v2/main_window_v2.py:1453](../ui_v2/main_window_v2.py#L1453) |
| 5 | ui_v2 `_on_import_workflow` 신규 + + 탭 메뉴 "📥 워크플로우 가져오기..." 액션 | 가져오기 짝 추가 | [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) |
| 6 | core test_76 (export 결과 main.py + session.json + captures 모두 검증), test_77 (import 새 UUID + 절대경로 재작성 + new_title) | 회귀 가드 | [tests/test_core.py](../tests/test_core.py) |
| 7 | scenarios test_71 (`_on_tab_export` 가 AppService 사용 + stub copytree 제거 검증), test_72 (가져오기 액션 + AppService 호출 검증) | 회귀 가드 | [tests/test_scenarios.py](../tests/test_scenarios.py) |

### export 결과 폴더 구조

```
{title}_{session_id_short}/
├── main.py                # 실행 가능 코드 (기존)
├── requirements.txt       # 패키지 목록 (기존)
├── README.md              # 가이드 (기존)
├── run.bat                # 윈도우 실행 스크립트 (기존)
├── session.json           # 🆕 가져오기 메타
├── captures/              # 🆕 스크린샷 (있을 때)
└── scripts/               # 🆕 원본 스크립트 (있을 때)
```

### 회귀 가드 갱신
- core 77/77 ✅ / scenarios 72/72 ✅
- PySide6 port sync 완료 (`cp` for core/, `sed` for ui_v2/)

### §7-6 ai_integration suite 실측 (5/7)

**결과**: 9/9 PASS — 5/6 fix 회귀 X. 단, 두 가지 테스트 인프라 fix 발견.

| # | 발견 | 원인 | fix |
|---|---|---|---|
| 1 | test_01/test_08 가 `'cp949' codec can't encode '—'` 로 ERROR | Windows 콘솔 cp949 가 AI 응답의 em-dash 처리 불가 | [tests/test_runner.py](../tests/test_runner.py) 모듈 로드 시 `sys.stdout/stderr.reconfigure(errors='replace')` |
| 2 | test_08 의 `_validate_generated_code` 가 `import` 무조건 강제 → trivial 코드 (예: `print(sum(range(1,11)))`) 에서 false negative | AI 가 합리적으로 unnecessary import 생략한 경우도 fail | [tests/test_ai_integration.py](../tests/test_ai_integration.py) `import` 검증을 hard assert → soft `[INFO]` log (try/except/print 패턴과 일관) |

각 step 의 AI 응답 자체는 모두 합격 — prompt 압축 + 모델 변경 + 가이드 강화의 실 효과 확인.

### §7-7 부분 (5/7) — LICENSE + README

| 작업 | 위치 |
|---|---|
| AGPL-3.0 공식 텍스트 (gnu.org 661 line) | [LICENSE](../LICENSE) + [pyside6_port/LICENSE](../pyside6_port/LICENSE) |
| 루트 README.md — 프로젝트 소개 + 설치/실행 + 테스트 + 로드맵 + 라이선스 섹션 | [README.md](../README.md) |
| **SPDX 헤더** | Phase 0 sub-phase 3 으로 이관 (ruff/pre-commit 도구 셋업 후 일괄) |

### §7-8 Phase 0 sub-phase 1 (5/7) — pyproject.toml + uv

**컨텍스트**: ROADMAP §7.2 의 권장 스택 도입 시작. 이후 Sub-phase 2 (pre-commit + ruff) → 3 (SPDX 헤더) → 4 (GitHub Actions CI) → 5 (devcontainer) 순서.

| 변경 | 위치 | 효과 |
|---|---|---|
| `pyproject.toml` 신규 — `[project]` 메타 + `dependencies` (requirements.txt 이주) + `[tool.uv] package = false` (Phase 1 의 `core/` 분리 전까지 packaging 비활성) | [pyproject.toml](../pyproject.toml) | uv / Dependabot / 보안 스캐너가 인식하는 표준 메타 |
| `uv.lock` 생성 (1050 line, 64 packages 해석) | [uv.lock](../uv.lock) | 재현 가능한 정확한 버전 고정 |
| pyside6_port 도 같은 패턴 — `pyside6_port/pyproject.toml` + `pyside6_port/uv.lock` (PyQt6 → PySide6 만 차이) | [pyside6_port/pyproject.toml](../pyside6_port/pyproject.toml) | 라이선스 비교 baseline 유지 |
| README + handoff §2 install 흐름 갱신 — `uv sync` 권장, 레거시 `venv/` 도 그대로 유지 | [README.md](../README.md), 본 §2 | 사용자 muscle memory 보호 + 신규 setup 은 권장 path |

**검증**:
- core 77/77 ✅ + scenarios 72/72 ✅ (양쪽 venv 모두 — 레거시 `venv/` + uv-managed `.venv/`)
- pyside6_port 의 `uv.lock` 은 lockfile 만 생성 (`.venv/` 미설치 — 사용자가 `uv sync` 시점에 활성화)

### §7-8 Phase 0 sub-phase 2 (5/7) — pre-commit + ruff

**컨텍스트**: lint + format 자동화. mypy 는 Phase 1 의 type hint 도입과 묶음.

| 변경 | 위치 | 효과 |
|---|---|---|
| `pyproject.toml` 의 `[tool.ruff]` 섹션 — 보수적 ruleset (E/F/W/I) + per-file-ignores (E402 in tests/ + ui/main_window.py, F401 in element_picker.py + ws_client.py) + `[tool.ruff.format]` (double quote) | [pyproject.toml](../pyproject.toml) | 30K 라인 legacy 에 너무 엄격하게 켜는 것 회피, Phase 1 type hint 시 점진 강화 |
| `[project.optional-dependencies].dev` — `ruff>=0.6.0` + `pre-commit>=3.7.0` | [pyproject.toml](../pyproject.toml) | `uv sync --extra dev` 로 dev 도구 일괄 설치 |
| `.pre-commit-config.yaml` 신규 — ruff lint+format + 표준 위생 hooks (trailing-whitespace, end-of-file-fixer, large file guard 1MB) | [.pre-commit-config.yaml](../.pre-commit-config.yaml) + [pyside6_port/.pre-commit-config.yaml](../pyside6_port/.pre-commit-config.yaml) | 매 commit 자동 검증 |
| `ruff check --fix` 1회 일괄 적용 — 520 issue 중 468 auto-fix | 코드베이스 전체 | I001 (import 정렬) 270, F541 54, W293 38, F401 105 등 자동 수정 |
| 남은 47 manual issue 처리 — `l` → `ln` (E741), 디버그 docstring 공백 (W293), `ovr_geo`/`x_log,y_log` 미사용 변수 제거 (F841), unused `Qt` import 제거 (F401), per-file-ignore 추가 | core/import_manager.py + core/workflow_engine.py + ui/element_picker.py + main.py + tests/test_ai_integration.py | 0 lint issue 도달 |
| `ruff format` 1회 일괄 적용 — 106 파일 reformat (double quote, indent, line break 표준화) | 코드베이스 전체 | 향후 incremental 변경만 format 검사 |
| 3 scenarios 테스트 fix — format 으로 깨진 string-pattern matching (test_43/44/66) 을 quote/whitespace-agnostic 으로 갱신 | [tests/test_scenarios.py](../tests/test_scenarios.py) | format 무관 검증 |
| pyside6_port sync — pyproject.toml/.pre-commit + 모든 코드 reformat (uv.lock 75 packages 재해석) | [pyside6_port/](../pyside6_port/) | 양쪽 일관성 |
| `pre-commit install` 실행 — `.git/hooks/pre-commit` 등록 | (git config) | 매 commit 시 자동 검증 발동 |

**검증**:
- ruff check . → All checks passed! (0 issue)
- ruff format --check . → 114 files already formatted (0 diff)
- core 77/77 ✅ + scenarios 72/72 ✅
- mypy 보류 (Phase 1 type hint 도입 시점에 추가)

### §7-8 Phase 0 sub-phase 3 (5/8) — SPDX 헤더 일괄

**컨텍스트**: 모든 `.py` 파일에 `# SPDX-License-Identifier: AGPL-3.0-or-later` 추가. 향후 dual-licensing / 법무 검토 / 외부 코드 유입 차단의 법적 근거.

| 작업 | 결과 |
|---|---|
| 일회용 스크립트 (`.tmp_spdx_apply.py`) — shebang 다음 줄 OR 첫 줄 삽입. 제외: `venv/`, `.venv/`, `ohdo_20260505_backup/`, `packages/`, `tmp/`, `data/`, 루트 debug 스크립트 (test_click_diagnosis.py 등) | 113개 .py 파일 일괄 추가, 0 skip (이미 있는 파일 X) |
| Python `write_text()` 가 Windows 에서 CRLF 로 쓰는 문제 → ruff format 으로 LF 통일 | 113 files reformatted |
| 스크립트 실행 후 즉시 삭제 (`.tmp_spdx_apply.py` 정리) | 일회성 작업 정리 |

**검증**:
- 113 .py 파일 모두 SPDX 라인 포함 (grep 검증)
- ruff check . → All checks passed!
- ruff format --check . → 114 files already formatted
- core 77/77 ✅ + scenarios 72/72 ✅

**적용 위치 예시** (shebang 유무 분기):
```python
# main.py (shebang 있음):
#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""AI RPA Solution - Main Entry Point ..."""

# core/app_service.py (shebang 없음):
# SPDX-License-Identifier: AGPL-3.0-or-later
"""UI·서버 공용 애플리케이션 진입점 (Facade) ..."""
```

### §7-8 Phase 0 sub-phase 4 (5/8) — GitHub Actions CI

**컨텍스트**: 매 push / PR 마다 자동 회귀 가드. main 머지 전 lint + test 통과 강제.

| 변경 | 위치 | 효과 |
|---|---|---|
| `.github/workflows/ci.yml` 신규 — 3 job 매트릭스: `lint`(ubuntu) + `test-ubuntu` + `test-windows` | [.github/workflows/ci.yml](../.github/workflows/ci.yml) | push/PR 자동 검증 |
| `lint` job — `ruff check .` + `ruff format --check .` (빠른 피드백, ~30s) | (위 파일) | lint 실패 시 test job 차단 (`needs: lint`) |
| `test-ubuntu` job — Qt system deps (libgl1/libegl1/libxkbcommon0/libdbus-1-3/libfontconfig1/libxcb-cursor0) + `QT_QPA_PLATFORM=offscreen` 환경 + uv sync + core/scenarios 실행 | (위 파일) | cross-platform 회귀 검증 (Phase 1+ backend Linux 호환성 사전 확보) |
| `test-windows` job — uv sync + core/scenarios (pywinauto/pyautogui 의존성 native 검증) | (위 파일) | Windows-specific 동작 검증 |
| 테스트 결과 artifact 업로드 — `tests/results/*.json` 14일 보관 | (위 파일) | CI 실패 시 결과 디버그 가능 |
| README CI 배지 추가 — CI status / AGPL v3 / Python 3.12+ | [README.md](../README.md) | 프로젝트 상태 visibility |

**보류**:
- `ai_integration` suite — Gemini CLI 셋업 + API key secret 필요 (로컬 수동 유지)
- GUI 자동화 suite (notepad/calculator/browser) — Windows GUI 환경 필수
- `pyside6_port` — venv 미설치 (사용자 수동 셋업). CI 미포함

**검증** (로컬):
- ruff check . → All checks passed!
- ruff format --check . → 114 files already formatted
- `uv run python -m tests.test_runner --suite core` → 77/77 ✅
- `uv run python -m tests.test_runner --suite scenarios` → 72/72 ✅
- ci.yml YAML 유효성 검증

**최초 commit / push 시**:
- GitHub Actions 가 자동 트리거됨. 첫 ubuntu test 가 PyQt6 system deps 누락 등 환경 문제로 fail 할 수 있음 → 그땐 `apt-get install` 라인 보강.

### §7-8 Phase 0 sub-phase 5 (5/8) — Dev Container

**컨텍스트**: cross-platform 개발 환경 표준화 마무리. 클릭 한 번에 동일 환경 (Codespaces / VS Code Dev Containers).

| 변경 | 위치 | 효과 |
|---|---|---|
| `.devcontainer/devcontainer.json` 신규 — Python 3.12 (mcr.microsoft.com/devcontainers/python:1-3.12-bookworm) + uv (astral-sh/uv:0 feature) + Qt system deps | [.devcontainer/devcontainer.json](../.devcontainer/devcontainer.json) | Codespaces / VS Code Dev Containers 표준 환경 |
| postCreateCommand — apt-get install Qt deps + `uv sync --extra dev` + `pre-commit install` | (위 파일) | 컨테이너 첫 부팅 시 의존성 + dev 도구 + git hook 자동 셋업 |
| VS Code 확장 5종 — Python / Pylance / Ruff / GitLens / even-better-toml | (위 파일) | 일관된 에디터 경험 |
| editor 설정 — ruff 가 default formatter, formatOnSave, codeActionsOnSave (organize imports + auto fix) | (위 파일) | 매 저장 시 자동 lint/format |
| `QT_QPA_PLATFORM=offscreen` 환경변수 — headless Qt 모듈 import 호환 | (위 파일) | 컨테이너에서 ui_v2 모듈 import 정상 |
| README Codespaces 배지 + 설치 (Codespaces / Dev Container) 섹션 + 2분할 전략 명시 | [README.md](../README.md) | 신규 기여자 진입점 |

**2분할 전략 (ROADMAP §7.2)**:
- 컨테이너 (Linux) = `core/` + 미래 `backend/` + `web/` 개발 + `core` / `scenarios` 테스트
- 로컬 Windows = `pywinauto` / `pyautogui` 의존하는 GUI 자동화 테스트 + 데스크톱 앱 실행

**검증**:
- devcontainer.json JSON 유효성 (jsonc 주석 strip 후 파싱) ✅
- ruff check . → All checks passed!
- ruff format --check . → 114 files already formatted
- core 77/77 ✅ + scenarios 72/72 ✅

### Phase 0 (§7-8) 완료 체크리스트

- [x] **Sub-phase 1**: `pyproject.toml` + `uv` (5/7)
- [x] **Sub-phase 2**: `pre-commit` + `ruff` (lint+format) (5/7)
- [x] **Sub-phase 3**: SPDX 헤더 일괄 (5/8)
- [x] **Sub-phase 4**: GitHub Actions CI (5/8)
- [x] **Sub-phase 5**: `.devcontainer/` (5/8)
- [ ] **structlog + Sentry** — ROADMAP Phase 0 의 observability layer. Phase 0 후반 또는 Phase 1 초반에 별도 작업.
- [ ] **mypy 도입** — Phase 1 의 "core/* 타입 힌트 완성" 마일스톤과 묶음.

### Phase 1 sub-task 1 (5/8) — 저장소 추상화 강화 + AppService leak 제거

**컨텍스트**: ROADMAP §3 Phase 1 (1) 시작. 데스크톱 앱과 향후 backend (PostgresRepository) 가 **동일한 `core/`** 를 공유하도록 저장소 인터페이스 정리.

| 변경 | 위치 | 효과 |
|---|---|---|
| `SessionRepository(ABC)` 에 `export_session_as_project()` + `import_session_folder()` abstract 메서드 추가 | [core/storage/base.py](../core/storage/base.py) | 모든 backend 가 export/import contract 준수 (NotImplementedError 가능) |
| `CaptureStore(ABC)` 신규 — `resolve_capture_path` / `list_captures_for_session` / `delete_capture` | (위 파일) | Phase 2 의 S3CaptureStore 진입로. 실제 capture 쓰기 경로 마이그레이션은 Phase 2 일괄 |
| `LocalCaptureStore` 신규 — filesystem 기반 구현 | [core/storage/local_capture.py](../core/storage/local_capture.py) | CaptureStore contract 준수 |
| `InMemoryRepository` 신규 — 테스트 가속용 (file IO 없음) | [core/storage/in_memory.py](../core/storage/in_memory.py) | tempdir 기반 테스트 대비 빠름. ROADMAP "테스트 전략" 항목 충족 |
| `LocalJsonRepository` 에 `export_session_as_project` / `import_session_folder` 메서드 추가 (manager 위임) | [core/storage/local_json.py](../core/storage/local_json.py) | 새 abstract 메서드 구현 |
| `AppService` 의 `getattr(self._repo, "manager", None)` **leak 2 곳 제거** — `export_workflow` / `import_workflow` / `reorder_step` 모두 abstraction 만 사용 | [core/app_service.py](../core/app_service.py) | Phase 2 PostgresRepository 가 manager 속성 없이도 작동 |
| `reorder_step` 의 `_renumber_steps` 호출 → 인라인 (3 줄) | (위 파일) | private 메서드 의존 제거 |
| test_78 (InMemoryRepository contract) + test_79 (AppService leak 차단) 추가 | [tests/test_core.py](../tests/test_core.py) | 회귀 가드 |

**검증**:
- core 79/79 ✅ (test_78 + test_79 신규)
- scenarios 72/72 ✅
- ruff check 0 issue + format 0 diff
- PySide6 port sync 완료 (5 파일)

### Phase 1 sub-task 2 Chunk A (5/8) — UI-Core 분리: ui_v2 정리

**컨텍스트**: ROADMAP §3 Phase 1 (2) KPI: "ui/ 폴더에서 session_manager · workflow_engine · ai_engine 직접 import 0건". 큰 작업이라 2 chunk 분할:
- **Chunk A** (5/8 완료): ui_v2 의 5 import 정리 + AppService 인터페이스 확장
- **Chunk B** (예정): ui/ legacy 의 12+ import 정리 + main_window.py 1649 → 600줄 축소

| 변경 | 위치 | 효과 |
|---|---|---|
| `AppService` 가 `Session/Step/SessionSummary` + `ExecutionKernel/StepResult` re-export | [core/app_service.py](../core/app_service.py) | UI 가 `core.session_manager` / `core.execution_kernel` 직접 import 안 해도 됨 |
| `AppService.create_default(data_dir, settings)` classmethod 추가 | (위 파일) | LocalJsonRepository + AIEngineManager 일괄 생성. UI 가 storage/ai_engine 직접 import 안 함 |
| `AppService.reload_ai(settings)` + `create_kernel()` factory 메서드 | (위 파일) | settings 변경 시 AI 재초기화, 세션별 kernel 생성 모두 facade 경유 |
| ui_v2/main_window_v2.py 의 5 banned import 모두 제거 — 모든 import 가 `core.app_service` 경유 | [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) | KPI 충족 |
| 함수 내부 `from core.session_manager import Step` → 모듈 상단 `from core.app_service import Step` | (위 파일) | local import 도 정리 |
| test_80 (ui_v2 banned import 0건 + AppService re-export + factory 메서드 검증) 추가 | [tests/test_core.py](../tests/test_core.py) | KPI 자동 가드 |

**검증**:
- core 80/80 ✅ (test_80 신규)
- scenarios 72/72 ✅
- ruff check 0 issue + format 0 diff
- PySide6 port sync 완료

### Phase 1 sub-task 5 (5/8) — Agent 브리지 스켈레톤

**컨텍스트**: ROADMAP §3 Phase 1 (5) 의 마지막 결산. agent/ 의 두 항목 평가:

| 항목 | ROADMAP 의도 | 실제 상태 |
|---|---|---|
| `agent/runner.py` — WorkflowEngine 감싸 원격 명령 수신 | no-op 스켈레톤 | ✅ **이미 초과 달성** — 827 line, M2.10 까지 완성. ExecutionRunner 가 `execution.start`/`execution.cancel` WS 프레임 처리, capture 업로드, mid-run cancel 등 모두 동작 |
| `agent/bridge.py` — 로컬 HTTP/WS 브리지 (no-op) | no-op 스켈레톤 | ❌ 미작성 → 5/8 추가 |

**(외 부수적 컴포넌트)**: `agent/agent_main.py` (623), `agent/auth.py` (386 — device flow), `agent/ws_client.py` (319 — cloud → agent WS) 도 이미 운영급 구현 완료.

| 변경 | 위치 |
|---|---|
| `agent/bridge.py` 신규 — `LocalBridge` 클래스 (no-op contract). `register_handler` / `start(port)` / `stop()` / `is_running` / `port` / `list_actions` / `get_handler` | [agent/bridge.py](../agent/bridge.py) |
| 미래 사용 시나리오 명시 — Phase 3 의 `ohdo://session/<id>` URL scheme 처리, desktop UI ↔ agent IPC, 외부 도구 (VS Code 확장 등) | (위 파일 docstring) |
| scenarios test_73 (LocalBridge contract 가드) 추가 — 인스턴스화 + handler 등록/조회 + 잘못된 입력 ValueError + start/stop 토글 | [tests/test_scenarios.py](../tests/test_scenarios.py) |
| pyside6_port sync — agent/ 폴더 전체 복사 (Qt 의존성 없음, cp 가능) | [pyside6_port/agent/](../pyside6_port/agent/) |

**검증**:
- core 80/80 ✅
- scenarios 73/73 ✅ (test_73 신규)
- ruff 0 issue + format 0 diff
- PySide6 port sync 완료

### Phase 1 sub-task 4 (5/8) — 설정 레이어 (Pydantic Settings)

**컨텍스트**: ROADMAP §3 Phase 1 (4) — `config/settings.json` 의 dict 기반 → Pydantic v2 `Settings` 모델 + `.env` / 환경변수 병합. 비파괴 도입 (기존 `_load_settings() -> dict` callers 유지).

| 변경 | 위치 | 효과 |
|---|---|---|
| `pydantic-settings>=2.0.0` 의존성 추가 | [pyproject.toml](../pyproject.toml) | typed Settings + .env 병합 도구 |
| `core/config.py` 신규 — 10 섹션 모델 (AI/Image/Recognition/Execution/VisualFeedback/UI/OutputProject/Logging/Hints/ElementPicker) + `Settings(BaseSettings)` 최상위 | [core/config.py](../core/config.py) | 타입 안전 접근, IDE 자동완성, validation |
| `load_settings(path) -> Settings` + `load_settings_dict(path) -> dict` (legacy 호환) + `save_settings(s, path)` | (위 파일) | 신/구 callers 양쪽 cover |
| `settings_customise_sources` override — env > dotenv > init(JSON) > secrets > defaults 우선순위 | (위 파일) | 사용자가 `.env` / shell 로 settings.json 값 override 가능 (CI/Docker 친화) |
| 모든 섹션 모델에 `extra="allow"` — 미정의 키 보존 (forward compat, settings.json 새 필드 추가 시 모델 갱신 전이라도 무손실) | (위 파일) | breaking change 회피 |
| test_81 (Settings 모델 + JSON load + env override + save 라운드트립 + extra=allow forward compat) 추가 | [tests/test_core.py](../tests/test_core.py) | 회귀 가드 |

**비파괴 정책**:
- 기존 `_load_settings()` patterns (ui/, ui_v2/) 그대로 작동 — `load_settings_dict()` 가 동일한 dict 반환
- 신규 코드는 `from core.config import load_settings; s = load_settings(); s.execution.step_delay_ms` typed access 권장
- Phase 2 backend 가 같은 `Settings` 모델을 FastAPI 의존성 주입에 활용 가능

**환경변수 override 예**:
- `OHDO_AI__SELECTED=openai_compat` → `s.ai.selected`
- `OHDO_EXECUTION__STEP_DELAY_MS=2000` → `s.execution.step_delay_ms`
- `OHDO_UI__THEME=dark` → `s.ui.theme`

**검증**:
- core 81/81 ✅ (test_81 신규)
- scenarios 73/73 ✅
- ruff 0 issue + format 0 diff
- pydantic-settings 양 venv (legacy + uv-managed) 설치 완료
- PySide6 port sync 완료 (uv.lock 76 packages 재해석)

### Phase 1 sub-task 3 (5/8) — Pydantic 모델 승격 (옵션 B parallel)

**컨텍스트**: ROADMAP §3 Phase 1 (3) — dataclass (Session/Step/Capture 등) → Pydantic v2. 비파괴 도입 정책 채택 (옵션 B):
- 기존 dataclass 유지 — 사용자 JSON 데이터 + 모든 callers 무손상
- 신규 Pydantic 모델은 **API 경계용** (Phase 2 FastAPI `response_model` 즉시 활용 가능)
- `from_dataclass()` / `to_dataclass()` 변환 helper

| 변경 | 위치 | 효과 |
|---|---|---|
| `core/models.py` 신규 — 7 Pydantic 모델 (CaptureModel/PromptLogModel/ExecutionResultModel/ConversationMessageModel/StepModel/SessionModel/SessionSummaryModel) | [core/models.py](../core/models.py) | dataclass 와 동일 필드 + 기본값 + `extra="allow"` (forward compat) |
| `from_dataclass(instance)` / `to_dataclass(model)` 변환 helper | (위 파일) | dataclass ↔ 모델 양방향. `_DATACLASS_TO_MODEL` 매핑 dict |
| 매핑 안 된 타입은 `TypeError` (잘못 호출 시 명시적 fail) | (위 파일) | 안전성 |
| `model_dump()` 결과 = `asdict(dataclass)` 결과 (JSON wire format 동일) | (검증 by test) | Phase 2 backend 의 `response_model` 호환 보장 |
| test_82 (round-trip + JSON 직렬화 + extra=allow + TypeError) 추가 | [tests/test_core.py](../tests/test_core.py) | 회귀 가드 |

**API 경계 활용 예** (Phase 2 진입 시):
```python
# FastAPI 백엔드
from core.models import SessionModel, StepModel, from_dataclass

@app.get("/sessions/{sid}", response_model=SessionModel)
async def get_session(sid: str):
    session = repo.load_session(sid)  # dataclass
    return from_dataclass(session)    # SessionModel
```

**비파괴 검증**:
- 기존 dataclass 호출 사이트 (수십 개) 전혀 변경 X
- 사용자 data/sessions/ JSON 파일 호환성 유지
- `model_dump()` ↔ `asdict()` 라운드트립 손실 0

**검증**:
- core 82/82 ✅ (test_82 신규)
- scenarios 73/73 ✅
- ruff 0 issue + format 0 diff
- PySide6 port sync 완료

### Phase 1 진행 체크리스트 (ROADMAP §3 Phase 1)

- [x] (1) 저장소 추상화 `core/storage/` — 5/8 완료
- [x] (2) UI-Core 완전 분리 — **Chunk A (5/8 ui_v2) + Chunk B (5/9 ui/ legacy) 모두 완료**
- [x] (3) Pydantic 모델 승격 — 5/8 완료 (parallel 모델 + 변환 helper)
- [x] (4) 설정 레이어 분리 — 5/8 완료
- [x] (5) Agent 브리지 스켈레톤 — 5/8 완료

**Phase 1 진행률: 5/5 (100% 완료)** — Phase 2 진입 직전 [docs/commercial_review.md](commercial_review.md) 재독 필수. 자세한 Chunk B 변경 내역은 §14 참조.

### 다음 작업 후보
- **main_window.py 줄수 축소 (stretch)** — 1304 → 600줄대. handler 추가 분해 (Step 5+). KPI 무관, 별도 결정.
- **structlog + Sentry SDK** (ROADMAP Phase 0 후반) — observability layer
- **§7-10**: AI 자동 에러 복구 — 사용자 보류 중
- **Phase 2 진입** — commercial_review.md 재독 + GO/NO-GO 게이트 통과 후 결정

### ⚠️ Phase 2 (SaaS 백엔드) 진입 직전 필독 문서

[docs/commercial_review.md](commercial_review.md) — 5/8 작성. ohdo 의 상업적 경쟁력 정직 진단 + Computer Use / UiPath / 기타 RPA 와의 비교 + GO/NO-GO 게이트 제안. **Phase 1 완료 직후 / Phase 2 진입 결정 전 반드시 재독.** Phase 1 까지는 어느 시나리오든 가치 있어 진행 OK.

## 14. 5/9 Phase 1 sub-task 2 Chunk B — UI-Core 완전 분리 (ui/ legacy)

**컨텍스트**: ROADMAP §3 Phase 1 (2) KPI: "ui/ 폴더에서 session_manager · workflow_engine · ai_engine 직접 import 0건" 의 Chunk B (ui/ legacy 정리). 5/8 의 Chunk A (ui_v2) 와 합쳐 KPI 100% 충족. 3 sub-step 으로 분할 진행 — AppService 보강 → main_window 정리 → handler/panel 정리.

### Sub-step 1 (5/9) — AppService 인터페이스 보강

| 변경 | 위치 | 효과 |
|---|---|---|
| 클래스 re-export 추가: `AIEngineManager / WorkflowEngine / PromptBuilder / WindowInspector / CodeSandbox` | [core/app_service.py](../core/app_service.py) `__all__` + 모듈 상단 eager import | UI 가 type hint / 인스턴스 보유 / 생성 시 모두 `from core.app_service import` 만 |
| 상수 re-export 추가: `INITIAL_BLOCK_STEP_ID / LIBRARY_BLOCK_STEP_ID` | (위 파일) | block_execution_handler 에서 사용 |
| pure 함수 re-export 추가: `extract_imports / merge_imports / extract_code_delta / extract_import_delta / extract_initial_block / extract_library_block / extract_step_delta_code / format_element_label` | (위 파일) | UI 가 pure 함수 직접 호출하는 사이트 모두 cover |
| `workflow_engine` property + `set_workflow_engine(engine)` setter | (위 파일) | 외부에서 settings (`step_delay_ms` / `visual_feedback_enabled`) 반영 인스턴스 주입 가능 |
| `prompt_builder` property + `set_prompt_builder(builder)` setter + `__init__(prompt_builder=)` 인자 | (위 파일) | 외부 prompts.json 주입 + lazy 생성 fallback |
| test_83 (Chunk B 인터페이스 가드 — 클래스/상수/함수 re-export + property/setter contract) 추가 | [tests/test_core.py](../tests/test_core.py) | 회귀 가드 |

**검증**: core 83/83 ✅ + scenarios 73/73 ✅ + ruff 0 issue + format 0 diff + PySide6 sync.

### Sub-step 2 (5/9) — ui/main_window.py banned import 정리

**Option A (보수)** 채택: import 만 정리하고 `self.session_manager / self.ai_engine / self.prompt_builder / self.workflow_engine` alias attributes 보존 (handler / code_viewer 등 산재된 호출 사이트 보호). KPI 는 import 만 측정하므로 충족.

| 변경 | 위치 |
|---|---|
| 모듈 상단 7 banned `from core.* import` (ai_engine / execution_kernel / import_manager / prompt_builder / session_manager / win_inspector / workflow_engine) → `from core.app_service import (...)` 단일 진입점 | [ui/main_window.py:47-66](../ui/main_window.py#L47-L66) |
| 함수 내부 `from core.import_manager import` 2 곳 (line 993 / 1052) 제거 — 모듈 상단에서 이미 import | (위 파일) |
| `__init__` 의 `self.session_manager = SessionManager()` / `self.ai_engine = AIEngineManager(...)` / `self.prompt_builder = PromptBuilder(...)` / `self.workflow_engine = WorkflowEngine(...)` 4개 인스턴스화 → `self.app_service = AppService.create_default(data_dir=..., settings=...)` + `set_workflow_engine(...)` + `set_prompt_builder(...)` 후 alias 4개 (`self.session_manager = self.app_service.repo.manager` 등) | (위 파일 line 100-123) |
| test_84 (main_window 의 banned core import 0건 + `from core.app_service import` 단일 진입점 가드) 추가 | [tests/test_core.py](../tests/test_core.py) |

**검증**: core 84/84 ✅.

### Sub-step 3 (5/9) — handler / chat_panel / ui_inspection_handler 정리

| 변경 | 위치 |
|---|---|
| `ui/ai_call_handler.py` — 모듈 상단 2 banned (`session_manager.Step` + `win_inspector.format_element_label`) + 함수 내부 1 (`import_manager.*` 3 함수) → `from core.app_service import (Step, extract_code_delta, extract_import_delta, extract_imports, format_element_label)` 단일 진입점 | [ui/ai_call_handler.py](../ui/ai_call_handler.py) |
| `ui/block_execution_handler.py` — 모듈 상단 2 banned (`execution_kernel.{INITIAL_BLOCK_STEP_ID, LIBRARY_BLOCK_STEP_ID, ExecutionKernel}` + `workflow_engine.{CodeSandbox, extract_library_block}`) → 단일 진입점 | [ui/block_execution_handler.py](../ui/block_execution_handler.py) |
| `ui/chat_panel.py` + `ui/ui_inspection_handler.py` — `win_inspector.format_element_label` → app_service 경유 | [ui/chat_panel.py](../ui/chat_panel.py), [ui/ui_inspection_handler.py](../ui/ui_inspection_handler.py) |
| test_85 (ui/ 폴더 전체 banned core import 0건 가드) 추가 — test_80 (ui_v2) + test_84 (main_window) 의 영역을 ui/*.py 전체로 확장 | [tests/test_core.py](../tests/test_core.py) |

**검증**: core 85/85 ✅ + scenarios 73/73 ✅ + ruff 0 issue + format 0 diff (`tests/test_core.py` 두 개 reformat 적용 후) + PySide6 port 7 파일 sync (cp + sed `PyQt6→PySide6, pyqtSignal→Signal`).

### Sub-step 4a (5/9, stretch — partial) — 기본 다크 테마 stylesheet 분리

**컨텍스트**: KPI 와 무관한 main_window.py 줄수 축소 stretch goal 의 첫 sub-step. 가장 risk 낮고 효과 큰 단일 변경.

| 변경 | 위치 |
|---|---|
| `_get_default_dark_theme()` 메서드 (156줄 stylesheet 문자열) → `ui/themes.py` 의 `get_default_dark_theme()` 함수로 추출 | [ui/themes.py](../ui/themes.py) (신규) |
| main_window 의 `_apply_theme` 이 `from .themes import get_default_dark_theme` 후 호출. 메서드 자체 통째 제거 (CLAUDE.md "delete completely" 룰) | [ui/main_window.py:392-403](../ui/main_window.py#L392-L403) |

**검증**: core 85/85 ✅ + scenarios 73/73 ✅ + ruff 0 issue + format 0 diff (130 files) + PySide6 sync (sed `PyQt6→PySide6, pyqtSignal→Signal`).

**효과**: main_window.py **1321 → 1166 줄 (-155줄)**.

### 보류된 stretch sub-step

- **4b**: 세션 CRUD (8 메서드, ~169줄) → `ui/session_management_handler.py` (예상 1166 → ~997)
- **4c**: Step 편집 (7 메서드, ~170줄) → `ui/step_edit_handler.py` (예상 ~997 → ~827)
- **4d**: UI setup `_setup_*` (5 메서드, ~175줄) → `ui/ui_setup.py` (예상 ~827 → ~652)

KPI 무관 + (c) commercial_review.md 게이트 우선순위로 보류 결정 (5/9 사용자). 4b~d 진행 시 main_window.py 600줄대 stretch goal 도달.

### Phase 1 최종 상태

- ROADMAP §3 Phase 1 의 5/5 sub-task 모두 완료. KPI ("ui/ 폴더에서 banned core 직접 import 0건") 충족. test_80 + test_84 + test_85 가드 3중.
- 예외: `core.environment_scanner` (environment_setup_dialog / settings_dialog 에서 함수 내 import) + `core.adapters.openai_compat_adapter` (settings_dialog) 는 KPI banned 목록 외 → 추후 정리.
- main_window.py 줄수: 1304 → 1166 (Sub-step 4a 적용). 600줄대 stretch goal 은 4b/4c/4d 보류.

## 15. 5/9 시장 결정 글로벌 확장 + 공개 직전 방어 정비

**컨텍스트**: Phase 1 100% 완료 직후 사용자와 commercial_review.md 재독 → 시장 타깃 변경 + 공개 직전 외부 정비 패키지를 한 세션에 묶어 처리.

### Stage 1 — 시장 타깃 글로벌 확장 결정 (사용자 결정 5/9)

- 한국 niche 단독 → **글로벌 + 한국 dual-locale** 양립으로 변경.
- 근거: 글로벌 dev-focused RPA SAM (~50-100M USD/yr) 이 한국 (~5-10M) 의 10배 + Computer Use 와 시간 경쟁.
- 차별성 재포지셔닝: "한국어 UI" 단일 강점 (🟢) → "i18n (영어 + 한국어) dual-locale" 의 하나 (🟡). 진입 장벽 효과 약화 인정 + 글로벌 SAM 진입.

| 갱신 문서 | 항목 |
|---|---|
| [docs/ROADMAP.md](../ROADMAP.md) | §0 타깃 시장 라인, §1 비전 본문 + 라이선스 절 본문, §10 변경 로그 5/9 행 |
| [docs/commercial_review.md](commercial_review.md) | 헤더 5/9 갱신 표시, §3 차별성 표 (한국어 UI → i18n dual-locale, 🟢→🟡), §5 SAM anchor 글로벌 + ARR 추정 상향 (비관 0-15K / 중립 20-80K / 낙관 150-500K), §7 GO/NO-GO 게이트 ("한국어 콘텐츠 5+" → "영어 + 한국어 mix"), §9 변경 로그 |
| [CLAUDE.md](../../CLAUDE.md) | 장기 로드맵 동기화 규칙 절의 타깃 시장 본문 |
| 본 §0 | 마지막 업데이트 라인 + 시장 결정 표시 |

### Stage 2 — 영어 README + 한국어 분리

- [README.md](../../README.md) → 영어로 전면 재작성. 차별성 표 (ohdo vs UiPath/Power Automate vs Computer Use), Windows 전용 명시, commercial_review link 추가.
- [README.ko.md](../../README.ko.md) 신규 — 한국어 버전. 양쪽 상단에서 cross-link.
- pyside6_port/README.md 는 internal (라이선스 비교 baseline) 수준이라 영어 변환 보류.

### Stage 3 — 공개 직전 방어 정비

| 변경 | 위치 | 효과 |
|---|---|---|
| `.gitignore` 강화 — secrets / credentials 패턴 추가 (`.env`, `.env.local`, `.env.*.local`, `*.key`, `*.pem`, `*.p12`, `*.pfx`, `*credentials*`, `*secret*`) | [.gitignore](../../.gitignore) | broad guard |
| `COMMERCIAL.md` 신규 — 오픈코어 의도 + AGPL 적용 경계 (when AGPL OK / when commercial license 필요) + 문의 가이드 | [COMMERCIAL.md](../../COMMERCIAL.md) | dual-licensing 의도 명시. 외부 commercial 문의 진입점 |
| `CONTRIBUTING.md` (영어) + `CONTRIBUTING.ko.md` (한국어) — DCO sign-off 가이드 (`git commit -s`), PR 체크리스트, scope 명시 (Windows-only, no XAML, Phase 2 SaaS 미공개), 환영 영역 (i18n, element picker, 테스트, 문서) | [CONTRIBUTING.md](../../CONTRIBUTING.md), [CONTRIBUTING.ko.md](../../CONTRIBUTING.ko.md) | 외부 기여자 진입점. CLA 보류 (DCO 만으로 작은 OSS 충분, 큰 기여 시 별 협의) |

### 보안 검증 결과

- `git ls-files | grep -iE "tmp/|data/sessions/|\.env|secret|\.key$|\.pem$|conversations"` → tracked sensitive 0건 (`.env.example` template 만).
- `git log --diff-filter=A -- 'tmp/*' 'data/sessions/*' ...` → history commit 0건. **`git filter-repo` 불필요**.

### 최종 상태 (5/9 세션 종료 시점)

- baseline: core 85/85 ✅ + scenarios 73/73 ✅ + ruff 0 issue + format 0 diff (130 files).
- **공개 가능 상태** (private → public 전환 결정만 사용자에게 남음).
- 시장 검증 GO/NO-GO 게이트 0/4 (private 유지로 측정 불가).

### 사용자 결정: 다음 단계 보류 + Phase 1.8 진입

5/9 세션 종료 결정 — Phase 2 / 공개 / 시장 검증 등 외부 다음 단계는 잠시 보류.
사용자 본인이 ohdo 를 일상 사용하면서 **AI 대화 → Python 자동화 코드 생성 기능의 완성도 향상 루프** 진행 (= 비공식 Phase 1.8).

작업 흐름:
1. 사용자가 자동화 시나리오에서 ohdo 사용
2. 회귀 / 엣지케이스 / 품질 이슈 발견 → Claude 와 함께 root cause 분석 + fix
3. 회귀 가드 추가 (test_core / test_scenarios)
4. baseline 그린 유지

영향 영역 (개선 후보):
- [core/prompt_builder.py](../core/prompt_builder.py) — 프롬프트 동적 구축 (누적 코드, 컨텍스트, 분기)
- [config/prompts.json](../config/prompts.json) — 시스템 프롬프트, 에러 복구 템플릿, jupyter 호환 가이드
- [core/win_inspector.py](../core/win_inspector.py) — element → 코드 변환 (UWP, owner-drawn, 브라우저, 동적 auto_id)
- [core/workflow_engine.py](../core/workflow_engine.py) + [core/import_manager.py](../core/import_manager.py) — step delta + import 추출 + jupyter 호환
- [core/adapters/gemini_cli_adapter.py](../core/adapters/gemini_cli_adapter.py) — AI 어댑터 (응답 corrupt, timeout, 인코딩)
- [ui/element_picker.py](../ui/element_picker.py) — element 검출 + EFP 토글 + F3 wait
- [ui/ai_call_handler.py](../ui/ai_call_handler.py) — AI 호출 path + step_code/generated_code 분리

회귀 위험 baseline: §4 의 contract 들 모두 (특히 §4.2 jupyter 6 함수, §4.5 ForegroundLock, §4.8 코드 편집 4중 안전장치) 회귀 시 즉시 발견.

## 16. 5/9~5/10 Phase 1.8 OpenAI 호환 (DeepSeek) 등록 + 코드 생성 품질 루프

**컨텍스트**: 5/9 §15 종료 시점 사용자 결정 — Phase 2/공개/시장 검증 보류, 본인이 ohdo 일상 사용하면서 AI 대화→Python 자동화 코드 생성 완성도 향상 루프 진행. 검증 시나리오: OpenAI API (DeepSeek 키) 등록 → 메모장 자동화 step 1 (실행) → step 2 (새 탭 추가 클릭) → step 3 (텍스트 입력) → 발견 이슈 fix.

11 unit 누적, baseline 85 → 96 (+11 회귀 가드). PySide6 port 양쪽 sync (core/ 는 cp, ui/ 는 sed PyQt6→PySide6).

### Step A (5/9) — settings dialog 의 Test connection 버튼 (test_86)
| 발견 갭 | DeepSeek 등 OpenAI 호환 LLM 을 등록해도 키 정확성 즉시 검증 불가 — 채팅에서 코드 생성 끝까지 돌려야 401 알 수 있음 (UX 나쁨, 비용 낭비) |
| Fix | [ui/settings_dialog.py:209-302](../ui/settings_dialog.py#L209-L302) 에 `Test connection` 버튼 + `_test_openai_connection` 메서드. dialog 입력값으로 임시 어댑터 → ping 호출 (timeout 15s + max_tokens 32 + temperature 0 + "Reply with OK only.") → ✅/❌ inline label. Save 안 한 입력값으로 즉시 검증 |
| 가드 | test_86 — 메서드 존재 + 위젯 + 콜백 dialog 입력값 사용 + 15s/32 강제 + OpenAICompatAdapter._generate_sync 직접 호출 5중 |

### Step B (5/9) — _open_settings 가 AIEngineManager 재로드 (test_87)
| 발견 갭 | settings dialog 에서 OpenAI 엔진 선택 + Apply → settings.json 저장 + theme/picker 즉시 반영. **AIEngineManager 재로드 누락** → 다음 AI 호출이 init 시점 settings 그대로 (gemini_cli 만 가지고 있어서 OpenAI 호환은 빈 api_key 401) |
| Fix | [ui/main_window.py:1107-1124](../ui/main_window.py#L1107-L1124) `_open_settings` 가 `_save_settings()` 후 `app_service.reload_ai(self.settings)` + `self.ai_engine = self.app_service.ai_manager` 추가. ai_call_handler 가 매번 `mw.ai_engine` lookup 하므로 alias 만 갱신하면 자동 전파 |
| 가드 | test_87 — `_open_settings` 소스에 `reload_ai(self.settings)` + `ai_manager` alias 패턴 |

### B1+B2+B4 (5/9) — 어느 엔진이 호출됐는지 확인 가능 + settings 영구 저장 (test_88)
| 발견 갭 | (B1) `mw.ai_engine.current_engine` 은 없는 속성 (`get_current_name()` 이 정답) — legacy ui 콘솔 패널의 `엔진:` 메타가 항상 빈 칸. (B2) ui_v2 의 `_send_request` worker 에서 step_done 메시지에 어느 엔진이 답했는지 명시 누락. (B4) `switch_ai_engine` (헤더 콤보 / 명령 팔레트 / onboarding 4 호출 사이트) 가 메모리 `_current_name` 만 변경하고 settings.json 영구 저장 X — 사용자가 ui_v2 헤더로 openai_compat 변경했는데 settings.json 의 ai.selected 는 gemini_cli 그대로 → 재시작 시 회귀 |
| Fix | (B1) [ui/ai_call_handler.py:193-195](../ui/ai_call_handler.py#L193-L195) `current_engine` → `get_current_name()`. (B2) [ui_v2/main_window_v2.py:2165-2188](../ui_v2/main_window_v2.py#L2165-L2188) step_done 메시지에 `엔진: {name}` prefix. (B4) ui_v2 에 `_persist_engine_choice(name)` 헬퍼 (settings.ai.selected = name + _save_settings) + 헤더/팔레트/onboarding 모두 호출. legacy main_window `_on_ai_engine_changed` 도 settings persist |
| 가드 | test_88 — 5중 (B1 속성명 + B2 메시지 prefix + B4 4 호출 사이트의 persist 패턴) |

### P4 (5/9) — 콘솔 패널이 settings.ui.console_visible 따름 (test_89)
| 발견 갭 | ui_v2 의 `_console_visible = False` 하드코딩 + `_build_console_panel` 의 `hide()` 하드코딩. 사용자가 Ctrl+\` 모르면 AI 응답 메타 (엔진/토큰/시간) 화면에서 볼 수 없음 + 토글해도 settings.json 영구 저장 X |
| Fix | [ui_v2/main_window_v2.py](../ui_v2/main_window_v2.py) `__init__` 가 `_load_settings()` 로 ui.console_visible 읽고 `_console_visible` 초기화. `_build_console_panel` 이 `setVisible(self._console_visible)`. `_toggle_console` 가 settings.json 영구 저장 |
| 가드 | test_89 — `__init__` settings 로드 + `_build_console_panel` setVisible (hardcoded hide() 0건) + `_toggle_console` 의 _save_settings 3중 |

### P1a (5/9) — 가장 큰 본질 fix: system_context 가 prompt 에 inject (test_90)
| 발견 갭 | **prompt_builder 가 self.system_context 를 보유만 하고 build_step_prompt 의 출력 (parts.join) 에 어디에도 append 하지 않음**. prompts.json 의 12K+ chars 핵심 가이드 (idempotent driver, jupyter mode, UWP wait, pyautogui PRIMARY, title_re, Text→부모 promote 등) 가 어떤 모델에도 도달조차 안 함. 이전엔 inline 가이드만 적용됨. 이게 5/9 step 2/3 가이드 무시 회귀의 진짜 원인 |
| Fix | [core/prompt_builder.py:90](../core/prompt_builder.py#L90) `_build_step_prompt_parts` (private 공통 빌더) 에서 `system_text = self.system_context or ""` 분리. `build_step_prompt` 는 backward compat (system + user 합쳐 단일 string 반환) — 호출자 깨지지 않음 |
| 가드 | test_90 — sentinel 본문 prepend 검증 + 사용자 요청보다 앞 위치 + 빈 system_context fail-safe |

### P1b (5/9) — system role 분리 (test_91)
| 발견 갭 | OpenAI compat 어댑터의 messages = [{role:user}] — system role 미활용. P1a 단일 string prepend 보다 best practice = system role 분리 (모델 attention 강화) |
| Fix | (a) [core/adapters/base_adapter.py](../core/adapters/base_adapter.py) `generate(prompt, images, system=None)` 시그니처 확장. (b) [core/adapters/openai_compat_adapter.py](../core/adapters/openai_compat_adapter.py) `_generate_sync` 가 system 받으면 `messages = [{role:system}, {role:user}]`. (c) [core/adapters/gemini_cli_adapter.py](../core/adapters/gemini_cli_adapter.py) system 받으면 stdin prompt 앞에 prepend (CLI 는 role 분리 path 없음). (d) [core/ai_engine.py](../core/ai_engine.py) 통과. (e) [core/prompt_builder.py](../core/prompt_builder.py) `build_step_prompt_split` 신규 메서드 — `(system_text, user_text)` 튜플 반환. (f) [core/app_service.py:622-634](../core/app_service.py#L622-L634) `generate_step` 가 split 호출 + 어댑터에 system 별도 전달 |
| 가드 | test_91 — split 메서드 + 어댑터 시그니처 + OpenAICompat messages 분리 + AIEngineManager 통과 + AppService split 호출 7중. scenarios mocks (`_FakeAI` / `MockAI` / `FakeAIManager` / `MockPromptBuilder`) 모두 `system=None` 인자 + `build_step_prompt_split` 추가 |

### P3 (5/9) — system_context 가이드 #3 + #5 강화 (test_92)
| Fix | [config/prompts.json](../config/prompts.json) system_context #3 → "**try/except 강제 (예외 없음)**: 외부 자원 다루는 모든 코드 블록 (앱 실행/연결 / 윈도우 wait / UI 조작 / 파일 I/O / 네트워크 / subprocess / 클립보드 / 단축키) 반드시 try/except". #5 → "**import 위치 강제 (Jupyter 호환)**: 모든 import 는 코드의 가장 최상단 (라인 1~N) 에만. try/except/함수/step 본문 안 import 금지" |
| 가드 | test_92 — sentinel 어휘 (`try/except 강제` / `예외 없음` / `import 위치 강제` / `가장 최상단` / `step 본문 안 import 금지`) |

### G1 (5/9) — system_context #17 의 element 자동 주입 X 명시 (test_93)
| 발견 갭 | DeepSeek 가 #17 예제 (`click_target = element` 패턴) 만 복사 → `name 'click_target' is not defined` 즉시 NameError. 기존 #17 예제는 `element` 가 자동 주입된다는 잘못된 가정 — ohdo 의 흐름은 element_context 에 텍스트 메타로만 들어가고 코드는 `win.child_window(...)` 로 직접 찾아야 함 |
| Fix | [config/prompts.json](../config/prompts.json) #17 본문에 "⚠ **변수 자동 주입 X — element 를 코드 안에서 직접 찾으세요**" 명시 + Step 1) `element = win.child_window(auto_id=..., control_type=..., found_index=0)` Step 2) walk-up promote Step 3) pyautogui.click 의 3단계 예제 추가. NameError 회귀 사례 인용 |
| 가드 | test_93 — sentinel 4중 |

### G2 + G5 (5/9) — element_context 템플릿 강제 사용 + library 블럭 essential imports (test_94/95)
| 발견 갭 | (G2) prompt_builder 의 element_context 가이드 "참고하되 ... 수정" 어휘 너무 약함 → DeepSeek 가 [core/win_inspector.py:680-940](../core/win_inspector.py) 의 ready-to-use 코드 템플릿 (`_resolve_element` + `element` + `click_target` + walk-up + pyautogui.click 모두 포함) 을 무시하고 짧은 자체 코드 작성 → element 변수 누락. (G5) `pyautogui` import 누락 — try block 에서 NameError → except 의 fallback `click_input()` 으로 살아남음 (silent fail). 모든 step 에서 pyautogui 호출 silent fail |
| Fix | (G2) [core/prompt_builder.py:297-340](../core/prompt_builder.py#L297-L340) "🚨 **위 ## 선택된 UI 요소 섹션의 ```python 코드 템플릿을 그대로 시작 코드로 사용하세요**" + "**자체적으로 element 변수를 다시 만들지 마세요**" + 회귀 사례 (`name 'click_target' is not defined`) 인용 + "사용자 요청 동작 코드만 템플릿 끝에 추가" 명시. (G5) [core/workflow_engine.py:846+](../core/workflow_engine.py#L846) `extract_library_block` 후 `_ensure_essential_imports` 적용 — 핵심 5개 (`time`, `subprocess`, `ctypes`, `pyautogui`, `pyperclip`) 누락 시 자동 prepend. regex 매칭으로 `import X` / `from X` 양쪽 인식 — 중복 prepend 방지 |
| 가드 | test_94 (G5 — 5개 패키지 prepend / 누락만 / 중복 방지 / from-style 인식) + test_95 (G2 — '그대로 시작 코드로 사용' / 'element 자체 정의 금지' / 회귀 사례 인용). [tests/test_scenarios.py:2506-2515](../tests/test_scenarios.py#L2506-L2515) test_42 의 `gc.startswith` → `in gc` 변경 (G5 의 prepend 로 generated_code 시작이 library 로 변경 — 의도된 동작) |

### G2.5 (5/10) — element_context 템플릿에서 import 라인 제거 (test_96)
| 발견 갭 | G2 효과로 DeepSeek 가 element_context 템플릿을 그대로 사용 → 마커 안에 `import ctypes` / `import pyautogui` 등이 들어감. `extract_imports` (header 영역만 인식) 가 step 1 의 상단 import 만 추출 → step 2/3 의 step_imports = []. P3 #5 (import 위치 강제) 위반 + G5 와 중복 import |
| Fix | [core/win_inspector.py:853-862](../core/win_inspector.py#L853-L862) desktop element 템플릿에서 import 5줄 (`ctypes` / `ctypes.wintypes` / `time` / `pyautogui` / `from pywinauto import Application`) 제거 + 안내 주석. owner-drawn 템플릿도 동일. [core/workflow_engine.py](../core/workflow_engine.py) `_ESSENTIAL_LIBRARY_IMPORTS` 에 `ctypes.wintypes` + `pywinauto.Application` 추가 (5 → 7개). [core/prompt_builder.py](../core/prompt_builder.py) element_context 가이드에 "import 는 코드 안에 작성하지 마세요 — 라이브러리 블럭에 자동 prepend 됨" 안내 한 줄 추가 |
| 가드 | test_96 — desktop / owner-drawn 템플릿 import 라인 0건 + `_ESSENTIAL_LIBRARY_IMPORTS` 보강 (ctypes.wintypes + Application) |

### 검증 결과 (5/10 사용자 'v2-새세션-150708' 메모장테스트 세션)

**🎉 G2.5 효과 확인** — Step 2 의 import 가 정확히 step_imports 영역으로 분리됨:
```
step 2.step_imports: ['import ctypes', 'import ctypes.wintypes', 'import pyautogui']
step 2.step_code: import 라인 0건. element_context 템플릿 거의 그대로 사용 (_resolve_element + element + click_target + walk-up + pyautogui.click + try/except 전체 wrapping)
```

### 잔존 갭 (다음 세션 출발점)

DeepSeek-V3 의 가이드 따르기 한계로 step 3/4 에서 모델이 가이드 일관성 떨어짐:

1. **Step 3 의 `app`/`win` 변수 재정의** — system_context #14(b) jupyter mode 호환 위반 (이전 step 변수 재정의 금지)
2. **Step 3+4 의 try/except 누락** — P3 #3 위반
3. **Step 3 의 들여쓰기 깨짐** — `def _resolve_element():` 라인 누락 + 본문만 indent → SyntaxError 가능
4. **Step 3 의 `import pyperclip` 이 else 블록 안** — P3 #5 위반 (G5 가 자동 prepend 했음에도 AI 가 또 작성)
5. **Step 1 의 `Application().connect(timeout=3)` 짧음** — 매 실행마다 새 메모장 인스턴스 띄움 가능. system_context #14(b) timeout 보강 필요
6. **자동 실행 옵션 부재 (F1 후보)** — 사용자가 코드 생성 후 별도로 ▶ Ctrl+R 눌러야 실행. settings.execution.auto_run_on_step_create 같은 옵션

### 후속 fix 옵션 (보류 — 다음 세션)

| 옵션 | 설명 | 분량 | 기대 효과 |
|---|---|---|---|
| **G6** | system_context #14(b) (변수 재정의 금지) + #3 (try/except) 어휘 더 강화 + 이전 step 변수 활용 안내 명시 | 작음 | 갭 #1 + #2 부분 개선 (모델 한계 — 100% 보장 X) |
| **G7** | step 코드 생성 후 ast 정적 분석 — 미정의 변수 / 변수 재정의 / try/except 누락 / compile fail (들여쓰기 깨짐) 검출 → 사용자 경고 + 자동 재생성 옵션 | 중간 | 모든 갭 사전 방지. 본질 해결 |
| **G4** | system_context #14(b) timeout=3s → 5s 권장 또는 polling 추가 | 매우 작음 | 갭 #5 (메모장 재사용 안정화) |
| **F1** | settings.execution 에 `auto_run_on_step_create` 옵션 + worker 끝부분에 옵션 체크 후 _on_run_single 호출 | 작음 | 갭 #6 (사용자 편의) |
| **F2** | step 카드 첫 생성 시 토스트에 "▶ Ctrl+R 로 실행" 힌트 | 매우 작음 | 발견성 |

**권장 우선순위**: G7 (정적 분석) > G6 (가이드 강화) > G4 + F1/F2.

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
