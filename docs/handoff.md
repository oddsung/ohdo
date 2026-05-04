# Claude Code 세션 인계 문서 (Handoff)

> **사용법**: 새 Claude 세션 시작 시 첫 입력으로 "이 파일 읽고 이어서 작업" 하라고 하세요.
> 이 문서는 Claude 의 auto-memory 가 컴퓨터 간 옮겨지지 않아 새 세션에서 컨텍스트 빠르게 복원하기 위한 용도입니다.
> 마지막 업데이트: 2026-05-05 (5/4~5/5 작업 — 자세한 변경은 §5 변경 이력 참조. 5/5 추가: Gemini adapter `_build_args` production path 적용 + 라이선스 전략 결정 확정 + Phase 2.5 Initial 블럭 단독 실행). baseline: **core 74/74 그린**.

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

## 7. 다음 작업 후보 (우선순위 순)

| 우선순위 | 작업 | 비고 |
|---------|------|-----|
| 1 | AI prompt 강화 + delta fix 효과 측정 — `ai_integration` suite 으로 실제 생성 코드 검증 | 5/4 밤 가이드/필터 추가 후 실 데이터로 회귀율 확인. |
| 2 | main_window 추가 분해 (필요 시) — 남은 1211줄 중 분리 가능 영역 (캡처, 윈도우 검사, 스텝 CRUD 등) | main_window 분해 Step 5 후보. 우선순위 낮음. |
| 3 | LICENSE 파일 (AGPL-3.0) + README 라이선스 섹션 + 모든 source 파일 SPDX 헤더 | Phase 0 시작 시 묶어서 처리 권장 (uv/devcontainer/CI 와 함께). |
| 4 | Phase 0 본격 진입 — `pyproject.toml + uv`, devcontainer, pre-commit, GitHub Actions CI | ROADMAP Phase 0. 데스크톱 안정화 ~80% 도달 시. |
| 5 | SaaS M3.2+ 재개 | Phase 0/1 완료 후. |

**5/5 완료**:
- ~~Gemini adapter `_build_args` production path 적용~~ — 두 Popen 호출 모두 `_build_args` 경유, test_71 production path 검증 추가.
- ~~ROADMAP §1 라이선스 전략 결정~~ — 오픈코어 (AGPL-3.0 데스크톱 + 추후 폐쇄 SaaS) 확정.
- ~~Phase 2.5: Initial 블럭 단독 실행~~ — INITIAL_BLOCK_STEP_ID=-1, BlockCard 단독 버튼 확장, on_run_initial_block + library 자동 선행. test_74 (74/74 그린).

## 8. 첫 작업 권장

새 세션에서 추천 흐름:

1. **이 파일 + docs/triage.md 빠르게 읽기**
2. `venv\Scripts\python.exe -m tests.test_runner --suite core` 실행 → **73/73 그린** 확인 (baseline 무손상 검증). venv 경로는 `venv/` (점 없음).
3. 사용자에게 다음 작업 후보 (§7) 제시 + 결정 받기

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
