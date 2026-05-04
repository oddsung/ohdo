# Claude Code 세션 인계 문서 (Handoff)

> **사용법**: 새 Claude 세션 시작 시 첫 입력으로 "이 파일 읽고 이어서 작업" 하라고 하세요.
> 이 문서는 Claude 의 auto-memory 가 컴퓨터 간 옮겨지지 않아 새 세션에서 컨텍스트 빠르게 복원하기 위한 용도입니다.
> 마지막 업데이트: 2026-05-04 (저녁)

## 1. 프로젝트 한 줄 요약

**ohdo** — AI (Gemini CLI) 와 대화하면서 Windows 데스크톱/웹 자동화 코드를 단계별로 생성/실행하는 PyQt6 기반 RPA 솔루션. SaaS 확장 계획 진행 중 ([docs/ROADMAP.md](ROADMAP.md) §1, AGPL-3.0 데스크톱 + 상업 SaaS 오픈코어 전략 — **라이선스 전략 재검토 사용자 결정 대기**).

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
│   ├── main_window.py               — 1538줄 (2058 → 1823 → 1538, 분해 Step 3 완료)
│   ├── ui_inspection_handler.py     — element picker + window inspector 핸들러 (Step 2)
│   ├── block_execution_handler.py   — 코드/블럭 실행 controller 16개 메서드 (Step 3, 478줄)
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

### 4.2 Jupyter mode (블럭 단독 실행) — test_51~54, 64
AI 생성 코드가 step 별 단독 실행되려면 **5가지 함수 모두** 필요:
1. `extract_code_delta` — prefix + SequenceMatcher fallback
2. `extract_step_delta_code(step, prev_step)` — generated_code diff 재계산
3. `_smart_dedent` — try 블록 안 라인 indent 정리
4. `_unwrap_main_function` — `def main(): ...; main()` 패턴 unwrap (AST)
5. **except 캡처 변수 stale 라인 필터링** — 5/4 추가, NameError 'e' 회귀 방지

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

## 5. 최근 작업 내역 (5/2 ~ 5/4)

| 일자 | 작업 |
|------|------|
| 5/2 | PySide6 migration (pyside6_port/), Phase 2 (Initial 블럭 추출), main_window 분해 Step 1 (closeEvent) + Step 2 (UIInspectionHandler 235줄) |
| 5/3 | Step wait 시스템 (3단계 우선순위 + UI), 코드 뷰↔블럭 뷰 상호작용 fix (signal-slot blocks_finished) |
| 5/4 | NameError 'e' fix (extract_code_delta 의 except 변수 필터), wait UI 개선 (_WaitSpinBox + editingFinished + 좌측 정렬) |
| 5/4 (저녁) | main_window 분해 Step 3 (BlockExecutionHandler, 1880→1538줄, 16개 위임 stub), Win11 ForegroundLock 우회 (foreground 복원 보류 해제), test 64 → 65 |

상세는 [docs/triage.md](triage.md) 참조.

## 6. 미해결 / 사용자 결정 대기

1. **ROADMAP §1 라이선스 전략 결정**: AGPL 유지 / 폐쇄 소스 / 양쪽 유지 — 사용자 결정 대기.
2. **PySide6 포트 GUI 검증**: 양쪽 동작 비교 — 사용자 직접 GUI 테스트 필요. 별도 venv 없어서 import sanity 도 사용자 환경에서.
3. ~~**foreground 복원 보류**~~ → **5/4 저녁 해결됨** (§4.5 참조). 사용자 GUI 테스트 통과.
4. **PySide6 양쪽 동기화 정책**: 코드 수정 시 어디 먼저 적용할지. 현재 PyQt6 원본 먼저 → 수동 sed 로 sync (자동 스크립트 없음).

## 7. 다음 작업 후보 (우선순위 순)

| 우선순위 | 작업 | 비고 |
|---------|------|-----|
| 1 | AI prompt 강화 — jupyter mode 호환 ("def main 안 쓰기", except 변수 stale 라인 회피 등) | 위험도 낮음. NameError 'e' 같은 회귀의 근본 예방 — §4.2 의 사후 필터 의존도 낮춤. [core/prompt_builder.py](../core/prompt_builder.py), [config/prompts.json](../config/prompts.json) 가 대상. |
| 2 | main_window 분해 Step 4: AI 호출 controller (~280줄) | Step 3 와 동일 패턴 (BlockExecutionHandler) 재사용 가능. AI 어댑터 호출 + 응답 파싱 + 코드 누적. |
| 3 | Phase 2.5: Initial 블럭 단독 실행 (변수 재정의용) | 옵션 |
| 4 | SaaS M3.2+ 재개 | 데스크톱 안정화 + ROADMAP §1 라이선스 결정 후 |

## 8. 첫 작업 권장

새 세션에서 추천 흐름:

1. **이 파일 + docs/triage.md 빠르게 읽기**
2. `venv\Scripts\python.exe -m tests.test_runner --suite core` 실행 → **65/65 그린** 확인 (baseline 무손상 검증). venv 경로는 `venv/` (점 없음).
3. 사용자에게 다음 작업 후보 (§7) 제시 + 결정 받기

## 9. 자주 하는 실수 / 주의사항

- **메서드 직접 추가 시**: PyQt6 원본만 수정하고 PySide6 포트 sync 잊으면 양쪽 불일치. 항상 양쪽 확인. core/ 변경은 `cp` 로 복사 (라이브러리 의존성 없음), ui/ 변경은 sed 로 `PyQt6` → `PySide6` 치환.
- **test 메시지에 em-dash 사용**: cp949 인코딩 에러로 test runner 가 ERROR 표시. hyphen 사용. (docstring/markdown 은 OK)
- **delta 추출 fallback**: `.strip()` 사용하면 첫 라인 indent 잘려 `_smart_dedent` 가 못 풀어줌. 사용 금지.
- **wait UI signal**: `valueChanged` 사용하면 매 키 입력마다 emit → 카드 재생성 → 포커스 손실. `editingFinished` 만 사용.
- **개별 step wait 변경 핸들러**: `_refresh_block_view` 호출하면 카드 재생성 → 포커스 손실. session 저장만.
- **handler 분해 시 회귀 테스트**: `inspect.getsource(MainWindow._method)` 로 검사하던 테스트는 메서드가 handler 로 옮겨가면 fail. 검사 대상을 `Handler.method` 로 변경 + `self.xxx` → `mw.xxx` 변환된 패턴으로 assertion 갱신 필수.
- **subprocess 의 SendInput 으로 ForegroundLock 이전**: pyautogui 같은 input 시뮬레이션 사용 시 권한이 subprocess 로 이동 — `OHDO_PARENT_PID` + `AllowSetForegroundWindow` 패턴 깨면 회귀 (§4.5).

## 10. 사용자에게 빠르게 물어볼 후보

세션 시작 직후 사용자에게 물어볼 만한 질문:
- "AI prompt 강화 (jupyter mode 호환) 부터 갈까, 아니면 main_window 분해 Step 4 (AI 호출 controller) 부터?"
- "ROADMAP §1 라이선스 전략 결정했어?"
- "PySide6 포트 GUI 검증 결과는?"
