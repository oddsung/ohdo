# Triage 노트

손 테스트하면서 발견한 것을 적어두는 곳. 다음 세션 시작 시 같이 읽고 분류한다.

## 분류 (다음 세션에서 함께 결정)

- **fix-now**: 즉시 수정
- **test**: 회귀 테스트로 박을 것 (`prompt_quality` / `ai_integration` / `core`)
- **backlog**: 우선순위 낮음, 나중에

## 항목 작성 형식

```
### YYYY-MM-DD HH:MM - 짧은 제목
- **상황**: 어떤 시나리오에서 발견했나 (예: 메모장에 한글 입력, 4K 모니터, Chrome iframe ...)
- **요청**: AI 에 무엇을 시켰나 (한 문장)
- **기대**: 무엇이 일어나야 했나
- **실제**: 무엇이 일어났나 (에러/잘못된 코드/UI 깨짐 등)
- **증거**: 스크린샷 경로 / 콘솔 로그 / 생성된 코드 스니펫
- **태그**: ai-quality | element-picker | kernel | ui | env | adapter | other
```

> 가볍게 메모해도 됨. 빠진 칸이 있어도 괜찮음 — 다음 세션에서 같이 채운다.

---

## 항목

<!-- 새 항목을 위에서부터 추가 -->

### 2026-05-05 - 실행 종료 시 run/stop 버튼 자동 리셋 안전망
- **상황**: 사용자 보고 — 모든 step 완료 후에도 코드 뷰/블럭 뷰의 stop 버튼이 활성화된 채 / run 버튼이 비활성화된 채로 남음.
- **분석**: 모든 종료 path (`execute_code_thread` finally, `run_blocks_thread` finally → `blocks_finished` signal) 가 이미 `set_running(False)` 호출 중이었지만 timing/race 또는 시각 갱신 누락 의심.
- **Fix**:
  1. [ui/ai_call_handler.py](../ui/ai_call_handler.py) `AICallHandler.on_step_executed` 끝에 `mw.code_viewer.set_running(False)` catch-all 추가 — 코드 뷰 path 의 `step_executed` signal slot. `set_running` 은 멱등 → 중복 호출 무해.
  2. [ui/block_execution_handler.py](../ui/block_execution_handler.py) `BlockExecutionHandler.on_blocks_finished` 에 `mw.code_viewer.update()` 호출 추가 — Qt 가 즉시 repaint 안 하는 케이스 방지.
- **CodeViewer.set_running** 은 양쪽 탭 동시 처리 (run_btn/stop_btn + block_view.set_running → run_all_btn/stop_btn + 카드 별 run_btn).
- **회귀 보호**: test_73 신규 — 4개 메서드 (`AICallHandler.on_step_executed`, `BlockExecutionHandler.on_blocks_finished`, `CodeViewer.set_running`, `BlockViewWidget.set_running`) 의 source 검증.
- **자동 검증**: core 73/73 그린. PySide6 sync.

### 2026-05-04 (밤) - 세션 추가/삭제 시 블럭 뷰 초기화 (CodeViewer.clear 통합)
- **상황**: 사용자 보고 — 새 세션 생성 / 현재 세션 삭제 시 블럭 뷰가 이전 세션 카드를 그대로 표시 (stale).
- **분석**: `_new_session` (line 574), `_on_session_delete` (line 627) 모두 `self.code_viewer.clear()` 호출하지만 그 메서드는 step 카드만 비움 (line 1547+). BlockViewWidget 은 별도 컴포넌트라 clear 안 됨 → library/initial/block 카드들이 이전 세션 그대로 남음.
- **Fix**: [ui/code_viewer.py](../ui/code_viewer.py) `CodeViewer.clear()` 에 `self.block_view.refresh("", [], "", 500)` 호출 추가. try/except 로 감싸서 refresh 시그니처 변경 시 `block_view.clear()` fallback. 호출자 (_new_session, _on_session_delete, _restore_session_ui) 모두 자동으로 양쪽 비움.
- **회귀 보호**: test_72 신규 — `inspect.getsource(CodeViewer.clear)` 가 `block_view` 호출 키워드 포함하는지 + 두 핸들러가 `code_viewer.clear()` 호출하는지 검증.
- **자동 검증**: core 72/72 그린. PySide6 sync.

### 2026-05-04 (밤) - Gemini CLI 어댑터: 모델 명시 (-m) 전달 + 안정 모델 default

### 2026-05-04 (밤) - Selenium prompt: 추측성 element ID 대기 금지 가이드 추가
- **상황**: 사용자 RPA_20260504_2206 세션 — step 1 (네이버 접속) 실행이 12초 걸리고 chromedriver stacktrace 출력. 우리 fix 와 무관 — AI 코드 품질 이슈.
- **분석**: AI 가 step 1 코드에 `WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'nm_main_tab')))` 삽입. 'nm_main_tab' 은 네이버 메인페이지에 없는 가짜 ID → 10초 timeout → TimeoutException → except 절로 잡혀 stacktrace 가 print 됨 (driver 객체는 이미 만들어져 있어 다음 step 정상 동작).
- **Fix**: [core/prompt_builder.py](../core/prompt_builder.py) `_append_selenium_guide` 에 "페이지 로드 대기 — 추측성 ID 금지" 가이드 추가:
  - 잘못된 예: `WebDriverWait(...).until(EC.presence_of_element_located((By.ID, 'nm_main_tab')))` ← 추측성 ID
  - 올바른 예: `time.sleep(2)` / `By.TAG_NAME, 'body'` / 사용자 명시한 다음 동작 element 만 대기
  - 원칙: generic 페이지 로드 대기는 sleep 또는 body/html, 특정 element 대기는 ID/CSS 가 사용자/요소피커에서 확인된 경우만
- **회귀 보호**: test_70 신규 — selenium 가이드에 '추측성', 'time.sleep + body', 'WebDriverWait + timeout' 키워드 검증.
- **자동 검증**: core 70/70 그린. PySide6 sync.

### 2026-05-04 (밤) - 코드 편집 desync 3차 fix: import 보존 (사용자 'NameError' 보고)
- **상황**: 2차 fix 후 사용자가 동일 시나리오 재테스트 → 실행 시 `NameError: name 'Application' is not defined` (블럭 뷰 실행) / `NameError: name 'Keys' is not defined` (이전 첫 세션 코드 뷰 실행) 발생.
- **분석**: 원본 step 2 의 generated_code 에는 `from pywinauto.application import Application`, `from selenium.webdriver.common.keys import Keys` 등이 포함. 사용자가 블럭 뷰에서 step 2 카드의 코드를 수정 — block 카드는 step_code (delta body) 만 표시하므로 사용자는 import 라인 안 건드림. 우리 2차 fix 가 새 generated_code 만들 때 `prev_step.generated_code (step 1) + new_step_code (사용자 수정값, import 없음)` → step 2 의 import 들이 사라짐. `extract_library_block` (마지막 step 의 generated_code 에서 imports 추출) 도 누락된 imports 만 가져옴 → 실행 시 NameError.
- **Fix**: [ui/main_window.py](../ui/main_window.py) `_on_block_step_code_edited`:
  - 원본 `step.generated_code` (`old_generated`) 에서 imports 추출 (`old_imports`)
  - prev_step.generated_code 에서 imports + body 분리 (`prev_imports`, `prev_body`)
  - 새 step_code 에서도 imports + body 분리 (`new_step_imports`, `new_step_body`) — 사용자가 import 추가 가능성 대응
  - `merge_imports([prev_imports, old_imports, new_step_imports])` 로 통합 (중복제거 + 정렬)
  - 새 generated_code = imports + prev_body + new_step_body 결합
  - `step_imports` 도 같이 update (workflow_engine path 호환)
- **`_on_step_code_edited` 도 갱신**: 코드 뷰는 사용자가 import 까지 수정 가능 → `extract_import_delta(new_imports, prev_imports)` 로 재계산해 `step_imports` 동기화.
- **회귀 보호**: test_69 (c) 신규 추가 — 사용자 시나리오 (selenium + Keys + pywinauto.Application) 정확 시뮬레이션, 재구성된 generated_code 가 모든 imports 보존 + 사용자 수정값 포함 검증.
- **자동 검증**: core 69/69 그린. PySide6 sync.

### 2026-05-04 (밤) - 코드 편집 desync 2차 fix: manually_edited 우선 + 화면 갱신
- **상황**: 1차 fix (두 필드 동시 업데이트) 후에도 사용자가 동일 시나리오 재테스트 시:
  - **추가 증상 1**: 블럭 뷰에서 '하이닉스' 수정 → 코드 뷰어 탭은 여전히 '삼성전자' 표시.
  - **추가 증상 2**: 실행하면 검색어 입력칸에 아무 입력 안 되고 종료 (의심: 우리 fix 가 만든 generated_code 의 marker 위치가 어긋나 stale 부분이 추출됨).
- **분석**:
  - 증상 1: `_on_block_step_code_edited` 가 update_step (디스크 저장) 만 하고 화면 위젯 갱신 trigger 안 함 → 코드 뷰어 탭 (StepCard) 위젯이 stale.
  - 증상 2: `extract_step_delta_code` 의 (1) 마커 추출 / (2) diff 재계산이 generated_code 기반 — 우리가 새로 만든 generated_code 에 marker 가 있어도 그 marker 사이의 코드가 사용자 의도와 어긋날 수 있음 (특히 try/except 블록이 step_code 안에 통째로 들어있는 경우).
- **Fix (3중 안전장치)**:
  1. [core/workflow_engine.py](../core/workflow_engine.py) `extract_step_delta_code` — 우선순위 (0) `manually_edited + step_code` 추가. 사용자 수정값 무조건 우선 (compile 통과 시 즉시 반환).
  2. [ui/main_window.py](../ui/main_window.py) `_on_block_step_code_edited` 끝에 `self._refresh_code_viewer()` 호출 — 코드 뷰어 탭 동기화.
  3. [ui/main_window.py](../ui/main_window.py) `_on_step_code_edited` 끝에 `self._refresh_block_view()` 호출 — 블럭 뷰 동기화.
- **회귀 보호**: test_69 갱신 — (a) manually_edited + step_code 가 stale generated_code marker 보다 우선되는지 in-memory 검증. (b) 두 핸들러 source 에 refresh 호출 키워드 검증.
- **자동 검증**: core 69/69 그린. PySide6 sync.

### 2026-05-04 (밤) - 코드 편집 desync fix: step_code ↔ generated_code 동시 업데이트
- **상황**: 사용자가 새 세션에서 네이버 검색 시나리오로 테스트 — Chrome 으로 naver.com 접속 → "삼성전자 주가" 검색어 입력 코드 생성 → 블럭 뷰에서 직접 "하이닉스 주가" 로 수정.
  - **증상 1**: 실행 버튼 누르면 여전히 "삼성전자 주가" 로 검색됨.
  - **증상 2**: 다른 세션 갔다가 돌아오면 화면이 "하이닉스" → "삼성전자" 로 되돌아감.
- **분석**: `_on_block_step_code_edited` 가 `step_code` 만 업데이트, `generated_code` 는 stale 채로 남음. `extract_step_delta_code` ([core/workflow_engine.py](../core/workflow_engine.py)) 의 우선순위 (1) 마커 추출 / (2) prev/curr generated_code diff 재계산이 모두 generated_code 기반이라 stale 값이 화면/실행에서 우선됨 — 사용자 수정 무시.
- **Fix**: [ui/main_window.py](../ui/main_window.py)
  - `_on_block_step_code_edited`: `step_code` + 새 `generated_code` (= prev_step.generated_code + "\n\n" + new_step_code) 동시 업데이트.
  - `_on_step_code_edited`: `generated_code` + 새 `step_code` (= extract_code_delta(new_body, prev_body)) 동시 업데이트. 코드 뷰 수정도 동일 desync 가능성 사전 차단.
  - 둘 다 `manually_edited=True`, `edit_original_code` 보존 (수동복원/AI 변조 자동복원 path 호환 유지).
- **회귀 보호**: test_69 신규 — 사용자 보고 시나리오 (네이버 검색 step 1+2, 수정 후 extract_step_delta_code 결과 + 디스크 reload 후 결과) 검증.
- **자동 검증**: core 69/69 그린. PySide6 sync.
- **handoff §4.8 신규** — 코드 편집 핸들러 baseline 으로 등록.

### 2026-05-04 (밤) - main_window 분해 Step 4: AICallHandler (327줄 분리)
- **목표**: main_window.py 1538줄 → 더 슬림화. AI 호출 path (6개 메서드) 를 별도 controller 로 분리. Step 3 (BlockExecutionHandler) 와 동일 패턴.
- **결과**:
  - 신규 [ui/ai_call_handler.py](../ui/ai_call_handler.py) (412줄, 6개 메서드: `on_cancel_ai`, `on_user_message`, `call_ai_thread` (백그라운드 스레드), `on_ai_response`, `on_step_executed`, `apply_manual_edit_patches`).
  - [ui/main_window.py](../ui/main_window.py) 1538 → 1211 (-327줄). 6개 메서드 1줄 위임 stub 으로 교체. `__init__` 에 `self.ai_handler = AICallHandler(self)` 추가. unused imports (`asyncio`, `threading`, `Step`) 제거.
  - 회귀 테스트 1건 신규 (test_68) — `inspect.getsource(MainWindow._stub)` 위임 검증 + `inspect.getsource(AICallHandler.method)` 의 `mw.xxx` 패턴 검사 (prompt_builder.build_step_prompt, ai_engine.generate, extract_code_delta, session_manager.add_step, send_keys 복원 등).
  - [pyside6_port/](../pyside6_port/) sed 치환 (`PyQt6` → `PySide6`) 로 sync. AST syntax 검증 OK.
- **자동 검증**: core 68/68 그린.
- **파일 구성** (분해 누적 결과):
  - main_window.py: 2058 → 1823 → 1538 → **1211** (분해 4 step 누적)
  - ui_inspection_handler.py (Step 2): 275줄
  - block_execution_handler.py (Step 3): 478줄
  - ai_call_handler.py (Step 4): 412줄

### 2026-05-04 (밤) - extract_code_delta: 컨트롤 헤더 보존 fix
- **상황**: 새 세션 RPA_20260504_2035 (메모장 자동화) step 4 의 step_code (단독 실행용 delta) 검증 중 발견. prev/new 모두 `try:`/`except Exception:` 패턴이 있을 때, SequenceMatcher 가 새 try/except 블록을 'insert' 로 추출하지만 직후 prev_set 필터가 `try:`/`except Exception:` 헤더를 "prev 에 동일 패턴 있음" 이라고 제거 → 본문만 module-level 로 평면화 → 성공 print 와 에러 print 가 둘 다 항상 출력되는 buggy 코드.
- **재현 (실제 데이터)**:
  ```python
  # step 4 의 step_code (fix 전):
  zoom_menu = app_window.child_window(...)
  zoom_menu.click_input()
  print("'확대/축소' 클릭")              # try 블록 본문
  print("'확대/축소' 클릭 중 오류 발생")   # except 본문 — 같이 출력됨!
  ```
- **Fix**: [core/import_manager.py](../core/import_manager.py) `extract_code_delta` 의 prev_set 필터에 컨트롤 헤더 화이트리스트 추가. `try`, `except`, `else`, `elif`, `finally`, `if`, `for`, `while`, `with`, `def`, `class` 로 시작하는 라인은 prev 에 동일 라인 있어도 보존 (새 블록의 일부일 수 있음).
- **회귀 보호**: test_67 신규 — 헤더 보존 + 본문 try/except 안에 위치 + module-level print 0 검증.
- **검증**: core 67/67 그린 + 실제 세션 step 4 의 generated_code 로 delta 재계산 → try/except 보존된 정상 형태로 복원 확인.
- **handoff §4.2 갱신**: jupyter mode baseline 5 → 6 (prev_set 필터 컨트롤 헤더 화이트리스트 추가).

### 2026-05-04 (밤) - AI prompt 강화: jupyter mode 호환 가이드라인 3종
- **목표**: §4.2 의 사후 필터 (extract_code_delta 의 except 변수 stale 라인 제거, _unwrap_main_function 등) 가 처리하는 회귀 패턴을 AI 가 애초에 안 만들도록 prompt 에서 명시적 금지. 사후 필터 의존도 낮추고 근본 예방.
- **추가된 가이드라인**:
  1. `def main(): ...; main()` 패턴 금지 — 모듈 레벨에 직접 작성. 함수 내 변수(driver, app)가 다음 스텝에서 NameError 됨.
  2. except 캡처 변수(e, ex 등)는 except 블록 안에서만 사용. 밖에서 참조 시 단독 실행에서 NameError.
  3. (current_code 있을 때만) 이전 스텝 변수 재정의 금지. globals 잃어 사후 필터로도 못 살림.
- **수정 파일**:
  - [core/prompt_builder.py](../core/prompt_builder.py) `build_step_prompt` [3] 규칙 섹션
  - [config/prompts.json](../config/prompts.json) `system_context` 절대 규칙 9~10 추가
  - [pyside6_port/](../pyside6_port/) 양쪽 sync (cp, 라이브러리 의존 없음)
- **회귀 보호**: test_66 신규 — `build_step_prompt` 출력 + `prompts.json/system_context` 양쪽에서 가이드 키워드 검증.
- **검증**: core 66/66 그린.
- **다음 후보**: ai_integration suite 으로 실제 생성 코드의 회귀율 측정 (handoff §7 #3).

### 2026-05-04 - Win11 ForegroundLock 우회 (foreground 복원 보류 해제)
- **상황**: 단독 실행 (⏯) 시 step1 (Selenium-only) 끝나면 메인 윈도우 정상 복원, step2 이후 (pyautogui.click/write/press 사용) 끝나면 메인 윈도우 안 떠오르고 작업표시줄에서 알림 깜빡임만.
- **분석**: subprocess (kernel_worker) 가 `pyautogui.click` 등으로 SendInput 호출 → Windows 의 `SetForegroundWindow` 권한이 ohdo → kernel_worker 로 이전됨 → ohdo 의 `mw.activateWindow()` 가 ForegroundLock 으로 거부 → flash 만. step1 은 Selenium 만 써서 SendInput 미발동 → 권한 ohdo 에 잔존 → 정상 복원.
- **Fix**: kernel_worker 가 매 step 종료 시 부모 (ohdo) PID 로 `AllowSetForegroundWindow` 호출하여 명시적 권한 양도. ohdo 의 다음 1회 `activateWindow` 통과 보장.
  1. [core/execution_kernel.py](../core/execution_kernel.py) — `start()` 의 subprocess `env` 에 `OHDO_PARENT_PID = str(os.getpid())` 전달
  2. [core/kernel_worker.py](../core/kernel_worker.py) — exec() finally 에서 `OHDO_PARENT_PID` 읽고 `ctypes.windll.user32.AllowSetForegroundWindow(parent_pid)` 호출 (sys.platform == 'win32' 가드)
- **회귀 보호**: test_65 신규 — `ExecutionKernel.start` 의 OHDO_PARENT_PID 전달 + kernel_worker 의 AllowSetForegroundWindow + win32 가드 패턴 검증.
- **검증**: 사용자 GUI 테스트 — step2~7 단독 실행 후 메인 윈도우 모두 정상 복원 확인됨.
- **handoff §6 #3 (foreground 복원 보류) 해제**.

### 2026-05-04 - main_window 분해 Step 3: BlockExecutionHandler (~340줄 분리)
- **목표**: main_window.py 1880줄 비대 — 코드/블럭 실행 path (16개 메서드) 를 별도 controller 로 분리.
- **결과**:
  - 신규 [ui/block_execution_handler.py](../ui/block_execution_handler.py) (478줄, 16개 메서드: on_run_code/execute_code_thread/get_or_create_kernel/on_run_from_step/on_run_single_step/on_wait_changed/on_kernel_reset/run_blocks_thread/on_blocks_finished/restore_main_window/on_block_step_started/on_block_step_done/on_kernel_status_changed/stop_session_kernels/get_valid_python_exe/on_stop_code).
  - [ui/main_window.py](../ui/main_window.py) 1880 → 1538 (-342줄). 16개 메서드 1줄 위임 stub 으로 교체. `__init__` 에 `self.block_executor = BlockExecutionHandler(self)` 추가. unused imports (`os`, `subprocess`) 제거.
  - 회귀 테스트 5건 갱신 (test_50, 55, 56, 57, 63) — `inspect.getsource(MainWindow._method)` → `inspect.getsource(BlockExecutionHandler.method)` 로 검사 대상 변경. self.xxx → mw.xxx 변환된 패턴 (`mw.lower()` 등) 으로 assertion 업데이트.
  - [pyside6_port/](../pyside6_port/) sed 치환 (`PyQt6` → `PySide6`) 로 sync. AST syntax 검증 OK.
- **자동 검증**: core 64/64 그린.

### 2026-05-04 - Wait UI 추가 fix (3건)
- **체크박스 좌측 정렬**: BlockCard 카드 하단 + BlockViewWidget toolbar 양쪽. 이전 `[stretch]` 후 체크박스 → 우측 끝. 변경 후 SpinBox 옆에 바로.
- **SpinBox 입력 중 포커스 손실**: `valueChanged` 가 매 키 입력마다 emit → 카드 재생성 → 포커스 잃음. **Fix**:
  1. `valueChanged` → `editingFinished` (사용자 enter/focusOut 시점만)
  2. 개별 step wait 변경 시 `_refresh_block_view` 호출 안 함 (session 저장만)
  3. 세션 default 변경 시 `set_session_wait` 만 호출 (카드 재생성 없이)
- **SpinBox 클릭 시 "ms" suffix 영역 선택 회귀**: `_WaitSpinBox` subclass — focusInEvent/mousePressEvent 시 `lineEdit().selectAll()` (QTimer.singleShot(0)). 클릭 시 항상 숫자 부분 선택되어 사용자가 바로 덮어쓰기 가능.
- 자동 검증: core 64/64 그린.

### 2026-05-04 - NameError 'e' is not defined fix (delta 추출 회귀)
- **상황**: 사용자 RPA_20260502_1753 세션에서 step 2 단독 실행 시 `NameError: name 'e' is not defined`. step 2 의 generated_code 가 `try/except Exception as e:` 구조인데 SequenceMatcher 가 except 헤더는 'equal' 로 매칭하고 안의 print 만 새 라인으로 추출 → `print(f"동작 중 오류 발생: {e}")` 가 except 없이 module-level 에 등장.
- **분류**: **fix-now (적용 완료)** — [core/import_manager.py:extract_code_delta](../core/import_manager.py):
  1. prev 의 `except ... as e:` 패턴에서 캡처 변수명 추출
  2. delta 에 `except` 가 없는데 그 변수명 참조 라인 있으면 제거
  3. `.strip()` 사용 안 함 — 첫 라인 indent 보존하여 `_smart_dedent` 가 정확히 처리
- **회귀 보호**: test_64 신규 — except 캡처 변수 stale 라인 제거 + 컴파일 가능 검증.

### 2026-05-04 - Step wait 시스템 (3단계 우선순위)
- **요구**: 사용자가 매번 "1초 대기" 요청 안 해도 자동 wait + 세션별 default + 개별 step 변경 가능.
- **구현**:
  - `Step.wait_after_ms: Optional[int]` (None=fallback, int=개별 override)
  - `Session.settings.step_delay_ms` 활용 (None=글로벌 사용)
  - 우선순위: step > session > settings.execution
  - workflow_engine 가 자동 적용
- **UI**:
  - 블록 뷰 toolbar: "⏱ 세션 기본: [____ ms] ☑ 글로벌 사용"
  - step 카드 하단: "⏱ 대기시간 [____ ms] ☑ 기본값 사용"
  - SpinBox 화살표 제거 (ms 라 1씩 증감 불필요)
  - `_WaitSpinBox` subclass — focus 시 자동 selectAll
  - `editingFinished` 사용 — 입력 중 포커스 유지
- **회귀 보호**: test_63.

### 2026-05-03 - Phase 2 (Initial 블럭 추출) + main_window 분해 Step 1+2
- **Initial 블럭**: 첫 step 의 generated_code 에서 모듈 레벨 ast.Assign + 모듈 레벨 try 블록 안 ast.Assign 만 추출 (driver, options 등 setup 변수). [core/import_manager.py:extract_initial_block](../core/import_manager.py).
- **BlockCard step_id=-1**: "🎬 Initial 블럭 (변수/초기값)" 노란색 카드.
- **main_window 분해**:
  - Step 1: closeEvent 중복 정의 (1910 + 2038) 통합 — 이전엔 두 번째가 첫 번째 덮어 커널 정리 안 되던 buggy 동작.
  - Step 2: [ui/ui_inspection_handler.py](../ui/ui_inspection_handler.py) 신규 — 6개 메서드 (235줄) UIInspectionHandler 클래스로 추출. main_window: 2058 → 1823 줄.
- **회귀 보호**: test_60, test_61, test_62.

### 2026-05-02 - PySide6 migration (라이선스 유연성) — pyside6_port/ 별도 디렉토리
- **상황**: PyQt6 라이선스 (GPL/상용) 가 SaaS 또는 폐쇄 소스 운영 시 부담. PySide6 (LGPL) 가 더 유연.
- **요청**: 사용자 결정 — "기존 보존 + PySide6 포트 추가". 동기화 정책은 추후 결정.
- **분류**: **fix-now (적용 완료)**:
  1. `pyside6_port/` 별도 디렉토리 (sub-directory pattern)
  2. data/ junction 으로 공유, 별도 venv (`pyside6_port/.venv/`)
  3. 자동 sed 변환 (6개 패턴: PyQt6→PySide6, pyqtSignal→Signal, pyqtSlot→Slot, pyqtProperty→Property, QtWidgets.QAction→QtGui.QAction, exec_()→exec())
  4. enum 모두 long-form (Qt.WindowType.X) — PySide6 호환 자동
  5. environment_scanner / test_runner 의 패키지 검증 PySide6 로 명시
  6. requirements.txt 갱신 + PySide6 6.11 설치
- **자동 검증**: 양쪽 core suite 59/59 그린.
- **남은 결정**: ROADMAP §1 라이선스 전략 (AGPL 유지 / 폐쇄 소스 / 양쪽 유지) — 사용자 대기.
- **회귀 위험**: 향후 fix 적용 시 양쪽 동기화 누락 위험. 메모리에 동기화 정책 미결로 표시.

### 2026-05-02 - 코드 뷰 ↔ 블록 뷰 상호작용 + signal-slot fix
- **상황**: step 1 단독 실행 후 코드 뷰 탭 ▶ 실행 버튼 비활성화 유지. 블록 뷰 ■ 중지 누르면 그제서야 활성화. F9 stop 가 블록 모드에선 안 멈춤.
- **근본 원인**:
  1. `_on_run_code` 가 set_running(True) 호출 안 함 → 양쪽 탭 UI 상태 불일치
  2. `_execute_code_thread` 의 finally 에서 set_running(False) 호출 없음
  3. `_on_stop_code` 가 sandbox 만 stop, ExecutionKernel 안 stop → 블록 모드 진행 중 step 안 멈춤
  4. `_run_blocks_thread` 의 finally 가 `QTimer.singleShot(0, _on_blocks_finished)` 사용했는데 어떤 케이스에서 호출 안 됨
- **분류**: **fix-now (적용 완료)**:
  - AsyncSignals 에 `blocks_finished` signal 추가 → main thread queued connection 으로 안전 호출
  - `_on_run_code` 시작에 set_running(True), `_execute_code_thread` finally 에 set_running(False)
  - `_on_stop_code` 가 ExecutionKernel.stop() 도 호출 + set_running(False) + _restore_main_window
  - 코드 뷰 탭 run/stop 버튼 disabled stylesheet 추가 (어두운 회색 + 점선 테두리 — 시각 구분 명확)
  - 세션 목록 활성 세션 색상 구분 (▶ marker + #313244 배경 + #89b4fa 텍스트 + bold)
- **자동 검증**: test_55 (lower/raise), test_56 (run/stop 상호작용), test_57 (blocks_finished signal). core 59/59 그린.

### 2026-05-02 - 실행 중 메인 윈도우 가림 방지 (foreground 복원 미해결)
- **상황**: 자동화 실행 시 ohdo 메인 윈도우가 underlying app element 를 가려 클릭 못 받는 경우.
- **시도 4회** (모두 foreground 자동 복원 실패):
  1. `showMinimized() + showNormal()` — Win11 정책 막힘
  2. `showMinimized() + AttachThreadInput trick + SetForegroundWindow` — 막힘
  3. `hide() + show()` (picker 패턴) — 작업표시줄 사라짐 + 막힘
  4. `lower() + raise_()` — 가림 해결 OK, 단 foreground 복원은 여전히 실패
- **현재 상태**: lower 패턴 채택 — 실행 중 가림 방지 OK, foreground 복원은 사용자 보류 결정 (수동 alt+tab 필요).
- **분류**: **fix-now (부분 적용)** + foreground 복원은 보류.

### 2026-05-02 - Step 단독 실행 (jupyter 블록 모드) 회귀 fix 4건
1. **Excel 셀 detection 회귀** — EFP 만 토글 안으로 분리 (walker 들은 토글 밖). [project_element_picker_baseline.md](../memory/...) 의 EFP 토글 패턴 참조.
2. **Delta 추출 누적 step_code** — `extract_code_delta` SequenceMatcher fallback + `extract_step_delta_code(prev_step)` 으로 generated_code diff 재계산. 7-step 세션 검증: step 2~7 의 step_code 가 4827c→666c 등으로 감소.
3. **IndentationError** — `_smart_dedent` helper. try 블록 안 라인이 indent 4 로 추출되는 경우 코드 라인 (주석/빈 줄 제외) 의 최소 indent 만큼 left-shift.
4. **NameError 'driver' is not defined** — `_unwrap_main_function` AST. AI 가 `def main(): driver = ...; main()` 패턴으로 작성한 경우 main 본문을 module-level 로 unwrap + `if __name__:` 블록 제거.
- **회귀 보호**: test_51, test_52, test_53, test_54 (delta + dedent + unwrap).
- **사용자 검증**: 7-step 세션에서 브라우저 1개만 띄우고 step 2~7 단독 실행 가능 확인.

### 2026-05-02 - Phase 1: Step 단독 실행 기능 (블록 카드 ⏯ 단독)
- **상황**: 사용자 요구 — step 5 만 단독 실행하고 싶은데 "▶ 여기서 실행" 누르면 5,6,7,...10 까지 실행됨. jupyter 처럼 N 만 실행 가능해야.
- **분류**: **fix-now (적용 완료)**:
  - `BlockCard` 에 "⏯ 단독" 버튼 (step_id>0 한정) + `run_single_requested` signal
  - `BlockViewWidget`, `CodeViewer` signal 통과
  - `workflow_engine.execute_session_blocks` 에 `stop_after_step_id` 인자 — 도달 시 break
  - `MainWindow._on_run_single_step` 핸들러 — `_run_blocks_thread(start=stop=N)`
  - 라이브러리 블럭 (step_id=0) 은 단독 버튼 없음 (한 번만 실행되는 setup)
- **자동 검증**: test_49 (workflow_engine stop_after_step_id), test_50 (BlockCard 단독 버튼 + signal chain).

### 2026-05-02 - Element picker 반응성 fix (descendants threshold + CDP 가드)
- **상황**: cursor 이동 시 highlight 박스가 1초+ 지연. click 후 메인 화면 전환도 1-3초.
- **근본 원인**:
  1. `_detect_in_hwnd` 의 descendants 호출이 매 tick 마다 800-1000ms 사용. walker 가 이미 작은 element 잡아도 호출.
  2. `_capture_dom_context` 의 CDP 포트 시도 (9222/9223/9224) 가 미연결 시 매번 timeout 대기 (3초).
- **분류**: **fix-now (적용 완료)**:
  - `NEEDS_DESCENDANTS_AREA_THRESHOLD = 5000` 가드 — walker 결과 area 작으면 descendants skip
  - CDP timeout 1초 → 0.3초
  - `cdp_enabled` settings (default false) — 매 click 마다 CDP 시도 회피. settings_dialog 에 체크박스.
- **자동 검증**: test_47 (descendants threshold), test_48 (cdp_enabled 가드).

### 2026-04-28 늦은밤 - 웹페이지 요소 picker 리서치 정리 → [docs/element_picker_research.md](element_picker_research.md)
- **배경**: Chrome 웹페이지 내부 요소를 picker 가 일관되게 못 잡음 (탭 갯수/타이밍에 따라 비결정적). 사용자 요청으로 기존 도구·라이브러리·방법론 검색 후 정리.
- **핵심 발견**: Chrome accessibility 활성화의 **2단계 핸드셰이크** — `NotifyWinEvent(EVENT_SYSTEM_ALERT, kIdCustom=1)` + `WM_GETOBJECT(lParam=kIdCustom)` 응답. 우리는 현재 `OBJID_CLIENT(-4)` 로 보내고 있어 Chrome 의 custom check 와 매치 안 됨. 이게 가장 가능성 높은 원인.
- **추가 정리**: Inspect.exe / FlaUInspect / pywinauto / yinkaisheng UIAuto 비교 매트릭스, Chrome HWND 구조 (Chrome Legacy Window 포함), multi-backend 캐스케이드 패턴, anchor+offset 패턴, hover modifier (Ctrl-hold) 등.
- **내일 시작점**: `WM_GETOBJECT(lParam=1)` 시도 + EnumChildWindows 로 Chrome_RenderWidgetHostHWND / Chrome Legacy Window 모두에 발송 + 200~500ms 대기 후 UIA 재시도. fallback 으로 `--force-renderer-accessibility` 안내 토스트.
- **분류**: 리서치 (다음 fix-now 후보)

### 2026-04-28 23:40 - **회귀 발견** — `_force_topmost` 가 사라져 Chrome 탭 picker 안 됨
- **증상**: 사용자가 picker 로 Chrome 탭 위에 호버해도 highlight 안 뜨고 click 시 선택 안 됨
- **사용자 우려**: "이전에 해결한 문제가 다시 발생, 검증 어렵다"
- **근본 원인**: 이전에 작업표시줄 z-order 문제 해결로 추가했던 `_force_topmost` 메서드 + `SetWindowPos` argtypes + `SWP_NOMOVE/SWP_NOSIZE` 상수 + `start_picking` 호출 — **모두 어딘가에서 변경 사이에 사라짐** (git 히스토리 없어 정확한 시점 확인 불가).
  - Qt 의 `WindowStaysOnTopHint` + `raise_()` 만으로는 Win11 에서 Chrome 메인 윈도우 / 작업표시줄이 overlay 위로 올라옴
  - overlay 가 가려진 채 picker 가 cursor 추적은 하지만 click 은 underlying 이 받음 → element 선택 불능
- **분류**: **fix-now (적용 완료)** — 모두 복원:
  1. `SWP_NOMOVE`, `SWP_NOSIZE` 상수 복원 ([ui/element_picker.py:41-42](../ui/element_picker.py#L41))
  2. `_ensure_user32_argtypes` 에 `SetWindowPos` argtypes 복원
  3. `_force_topmost` 메서드 복원
  4. `start_picking` 의 `show()/raise_()/activateWindow()` 다음에 `_force_topmost()` 호출 복원
- **회귀 방지 테스트** 강화 — 정적 검증으로 메서드/상수/호출 사라짐 즉시 감지:
  - `test_37_element_picker_force_topmost_exists`: `_force_topmost` 존재 + start_picking 에서 호출 + HWND_TOPMOST/SWP_* 상수 존재
  - `test_38_element_picker_detection_helpers_exist`: detection 헬퍼 7개 존재 검증 (`_find_topmost_window_at_point`, `_walk_uia_to_deepest`, `_find_deepest_descendant`, `_raw_walk_at_point`, `_detect_element_multi_backend`, `_update_element_under_cursor`, `mousePressEvent`)
- **자동 검증**: core 38/38 + prompt_quality 33/33 그린
- **교훈**: 다음에 element_picker 코드를 수정할 때 위 정적 검증 테스트가 안전망. 만약 깨지면 즉시 회귀.

### 2026-04-28 23:33 - 회귀 방지 테스트 추가 (Chrome 탭 / HTML 콘텐츠 코드 생성)
- **상황**: 사용자가 routing 변경 사이에서 동일 시나리오 (Chrome 탭 클릭) 가 여러 번 깨졌다 고쳐졌다 반복하는 것에 우려 표명. "검증 없이 진행" 의 위험.
- **대응**: 사용자 실제 세션 (ce6aa624 step 1, step 2) 의 element_info 를 fixture 로 한 회귀 테스트 2개 추가:
  - `test_32_regression_chrome_tab_session_ce6aa624` — Chrome 탭 (CDP 미연결) 의 라우팅 + 코드 생성 5항목 검증
  - `test_33_regression_html_text_session_ce6aa624` — HTML 페이지 Text 도 동일 path 검증
- **검증 항목**: should_use_selenium=False, webdriver.Chrome 부재, pywinauto Application connect, parent_title 사용, child_window selector 정확, pyautogui PRIMARY 클릭
- **자동 검증**: prompt_quality 33/33 그린. 현재 코드는 두 시나리오 모두 정확한 출력 생성 — 즉 사용자가 "지금 안 된다" 고 본 건 코드 생성 측면 회귀가 아님.
- **남은 분석 (사용자 확인 필요)**: picker 의 시각적 detection 자체가 이슈라면 콘솔 진단 print (첫 10 tick) 출력 공유 부탁.

### 2026-04-28 23:00 - F3 일시정지 후 복귀 시 펼쳐진 submenu 가 접힘 [재논의 후 옵션 A 채택]
- **1차 fix (23:00)**: `WS_EX_TRANSPARENT` 도 켜서 submenu 유지 시도 → submenu 는 유지됐지만 underlying app 에 **mouseover 효과 누수** 발생 (사용자가 picker 의 본질에 어긋난다고 지적).
- **OS 차원의 trade-off**: overlay click-through 켜면 submenu 유지 + mouseover 누수, 끄면 누수 0 + submenu 닫힘. 동시 만족 불가 (마우스가 동시에 두 곳에 있을 수 없음).
- **2차 fix (옵션 A 채택, 23:11)**: `_resume_after_pause` 에서 `WS_EX_TRANSPARENT` 제거. **초기 picker 와 동일한 mouse 동작** 유지가 우선. 결과:
  - ✅ post_pause 모드에서도 mouseover 누수 0 (사용자 일관성 기대 매칭)
  - ⚠ F3 동안 펼친 hover-only submenu 는 resume 시 닫힘 (수용된 trade-off)
- **남은 워크플로우**: submenu 안 항목 picker 로 잡으려면 부모 메뉴 잡고 AI 한테 "X 메뉴 안의 Y 클릭" 식으로 요청 (별도 워크플로우).
- **관련 코드**: [ui/element_picker.py:_resume_after_pause](../ui/element_picker.py), `_exit_post_pause_mode`
- **자동 검증**: core 36/36 그린.

### 2026-04-28 22:11 - 새 세션에서 탭 클릭 요청 → 새 Chrome 띄움 (CDP 미연결 시)
- **상황**: 사용자가 새 세션 만들고 띄워둔 Chrome 의 탭을 picker 로 골라 "클릭하고 1초 대기" 요청
- **기대**: 기존 Chrome 의 그 탭 클릭
- **실제**: AI 가 Selenium `webdriver.Chrome(...)` 로 새 Chrome 띄워 fresh 페이지에서 `view_20` 검색 → 실패
- **증거**: 세션 `60d61699-bb39-43e7-b8fd-d8a321035393` 분석. picker 가 CDP 미연결이라 직전 fix 의 라우팅이 Selenium 경로로 보냄. 코드 템플릿이 "방법 1: 새 브라우저" 활성, "방법 2: attach" 주석. AI 가 방법 1 따름.

- **근본 원인**: 직전 fix 가 "이전 프로젝트 패턴 복원" 이라 browser+no-CDP → Selenium 으로 보냈는데, **CDP 가 없으면 Selenium 으로 사용자 기존 Chrome 에 attach 불가능** → 새 Chrome 띄워서 사용자 의도와 어긋남. 이전 프로젝트의 "유연성" 은 사실 "open URL and automate" 패턴에 대한 것이었지 "click on existing Chrome" 시나리오는 OLD 도 처리 못 했음.

- **분류**: **fix-now (적용 완료)** — routing 수정:

  | browser? | CDP? | tagName? | 결정 |
  |---|---|---|---|
  | No | - | - | pywinauto |
  | Yes | Yes | 있음 | Selenium DOM (attach 가능) |
  | Yes | Yes | 없음 | pywinauto (chrome UI) |
  | Yes | **No** | - | **pywinauto** ← 변경: Selenium 으로 보내면 새 Chrome |

  desktop path 코드 템플릿도 보강:
  - `is_browser=True` 일 때 **pyautogui PRIMARY** 분기 추가 (HTML 콘텐츠 GPU compositor 영역도 OS 레벨 SendInput 으로 정확 전달)
  - 비-브라우저는 기존대로 `element.click()` PRIMARY (속도/정확성)

- **유지**: main_window 의 1회 CDP 안내 다이얼로그 — 사용자가 CDP 셋업하면 케이스 A/B 진입해서 더 풍부한 자동화 가능

- **테스트**: `test_29` 갱신 (browser+no-CDP → desktop path + pyautogui PRIMARY 검증), `test_31` 신규 (비-브라우저 데스크톱은 element.click() PRIMARY). core 36/36 + prompt_quality 31/31 그린.

- **원칙 정리** (다언어/다플랫폼 유연성):
  - picker 가 본 그 윈도우에 connect → element 정확히 찾기 → 실행 시점 좌표로 클릭
  - 데스크톱 앱: pywinauto + WM 메시지 (빠르고 정확)
  - 브라우저: pywinauto + pyautogui SendInput (탭/HTML 콘텐츠 모두 OK)
  - CDP 가 응답하면: 페이지 DOM 까지 정확히 보고 Selenium DOM info 풍부 사용
  - 어떤 경우에도 새 브라우저를 띄워 사용자 의도를 어그러뜨리지 않음

### 2026-04-28 22:00 - 이전 프로젝트 (python_stuff/ai_rpa_solution) 패턴 복원: HTML 콘텐츠 자동화 유연성 회복
- **상황**: 직전 fix (browser+no-CDP → desktop path with pyautogui guidance) 가 탭 클릭은 잡았지만 HTML 페이지 콘텐츠 클릭이 여전히 부정확. 사용자가 이전 프로젝트는 windows app + browser page elements 자동화가 유연했다고 지적.
- **이전 프로젝트 분석** (`C:/Users/NeodaVinci/python_stuff/ai_rpa_solution/core/win_inspector.py:200-336`):
  - `is_browser=True` 면 무조건 Selenium 경로 (CDP 없음)
  - 코드 템플릿에 두 connection 옵션 모두 표시 (방법 1 새 브라우저 / 방법 2 attach)
  - `find_and_click(driver, locators)` — picker 의 UIA-derived locator_candidates (id/title/text)
  - AI 가 컨텍스트에 맞게 connection 방법 선택

- **개선된 라우팅 매트릭스** (이전 + CDP 통합):
  | browser? | CDP? | tagName? | 결정     | 의미                               |
  |----------|------|----------|----------|------------------------------------|
  | No       | -    | -        | pywinauto | 데스크톱 앱                        |
  | Yes      | Yes  | 있음     | Selenium | 페이지 DOM + 정확한 DOM info       |
  | Yes      | Yes  | 없음     | pywinauto | browser chrome (탭/메뉴) 확정      |
  | Yes      | No   | -        | Selenium | unknown, AI 가 connection 선택    |

- **분류**: **fix-now (적용 완료)**:
  1. `should_use_selenium` 로직 변경: browser+no-CDP 도 Selenium default (이전 패턴)
  2. `_get_browser_element_info_text` 코드 템플릿: CDP 가용성에 따라 권장 connection 방법을 명확히 표시 (CDP 있으면 방법 2 활성, 없으면 방법 1 활성 + 방법 2 가이드)
  3. desktop path 의 dead browser warning 섹션 정리 (이제 도달 안 함)

- **유지되는 것**:
  - 직전 fix 의 main_window 1회 CDP 안내 다이얼로그 (옵션 2) — 사용자가 CDP 셋업하도록 자연스럽게 유도
  - 탭/메뉴 (CDP 있음 + tagName 없음) 는 그대로 pywinauto → 직전 fix 검증된 동작

- **테스트**: `test_26_selenium_routing_matrix` (4×2 매트릭스), `test_27_browser_chrome_with_cdp_routes_to_pywinauto`, `test_29_browser_no_cdp_routes_to_selenium`. core 36/36 + prompt_quality 30/30 그린.

- **원칙 (no hardcoding)**: 브라우저 클래스명/control_type 검사 0. picker 가 수집하는 process detection (`browser_type`) + CDP 응답 (`dom_context`) 만으로 결정. 어떤 브라우저든, 어떤 element 든 동일 로직.

### 2026-04-28 21:32 - HTML 페이지 콘텐츠 (Chrome 안 Text "TYPING SETTING") 클릭 실패
- **상황**: 직전 fix 로 Chrome 탭 클릭 (step 1) 은 성공. step 2 에서 그 페이지 안 Text element 를 picker 로 선택 → 클릭 코드 생성 → 실행 시 클릭 안 됨
- **증거**: 세션 `ce6aa624-fb44-49f1-a381-a853c5020080` 분석. AI 가 `element.click_input()` 을 PRIMARY 로 사용한 코드 생성. pywinauto 가 element 를 찾기는 하지만 click 이 silent 실패.
- **근본 원인**: 브라우저 HTML 페이지 콘텐츠는 Chrome 의 GPU compositor (Skia) 가 렌더 — Win32 윈도우가 아님. pywinauto 의 WM 메시지/click_input 이 렌더 영역에 닿지 못함. 직전 fix 의 `should_use_selenium` 은 CDP 미연결 시 모두 desktop path 로 라우팅했는데, **탭 (browser chrome HWND)** 에는 OK 지만 **HTML 콘텐츠** 에는 부정확.

- **분류**: **fix-now (적용 완료)** — 옵션 1 + 옵션 2 조합:

  **옵션 1** ([core/win_inspector.py](core/win_inspector.py) `_get_desktop_element_info_text`):
  - `is_browser=True` AND `cdp_available=False` 시 prompt 에 새 섹션 추가
  - "GPU compositor 라 click_input 불안정" 명시
  - **`pyautogui.click(cx, cy)` 를 PRIMARY 로** 권장 (OS 레벨 SendInput → 어떤 영역도 일관 동작)
  - CDP 셋업 명령어 안내 (Chrome 재시작 with `--remote-debugging-port=9222`)
  - 하드코딩 0: 브라우저 클래스명/control_type 검사 없이 `is_browser` (process 감지) + `cdp_available` 만으로 판단

  **옵션 2** ([ui/main_window.py](ui/main_window.py) `_on_element_picked` + 신설 `_maybe_show_cdp_hint`):
  - browser process + CDP 미연결 element 선택 시 1회 안내 다이얼로그
  - "다시 보지 않기" 클릭 시 `settings.hints.cdp_browser_hint_dismissed=True` 저장 → 영구 suppress
  - default_settings.json 에 `hints` 섹션 추가
  - 사용자가 다음에 picker 쓰기 전에 Chrome 을 debug port 로 재시작하면 자동으로 Selenium DOM 경로 활성

- **테스트**: prompt_quality `test_29` (browser+no-CDP → pyautogui 가이드 포함), `test_30` (비-브라우저 desktop → CDP 안내 안 뜸). core 36/36 + prompt_quality 30/30 그린.

- **원칙 (다언어/다플랫폼 유연성)**: 데스크톱 Win32 앱 / 브라우저 chrome / 브라우저 HTML 콘텐츠 — 세 영역이 서로 다른 자동화 방식 필요. picker 가 element 정보 + CDP 가용성만으로 자동 라우팅. 어떤 언어로 만든 앱이든, 어떤 브라우저든 동일 코드 경로로 처리.

- **남은 후속**: Chrome 재시작을 사용자가 한 번도 안 했을 때 picker 가 직접 "Chrome 종료하고 debug port 로 재시작해드릴게요" 자동화 (옵션 3) — 별도 작업.

### 2026-04-28 21:09 - Chrome 탭을 picker 로 골랐는데 AI 가 새 Chrome 을 띄우는 코드 생성
- **상황**: 이미 띄워진 Chrome 의 탭 (`typing.works - 메모리 사용량 - 94.1MB`) 을 picker 로 선택, "클릭하고 1초 대기" 요청
- **기대**: 그 탭이 클릭됨
- **실제**: 새 Chrome 창이 빈 페이지로 띄워지고, 그 새 창에서 `id="view_20"` 검색 → 실패. 기존 탭은 클릭 안 됨.
- **증거**: 세션 `cfd1c165-070e-4776-9ce8-7f3327856f4d` 의 generated_code 와 prompt_log 분석.

- **근본 원인 (3중)**:
  1. picker 의 UIA `automation_id="view_20"` 를 `core/win_inspector.py:233` 에서 **"HTML ID"** 로 라벨링. UIA AutomationID 는 HTML id 와 별개인데 동일시.
  2. browser process (Chrome) 인 모든 요소를 무조건 Selenium DOM 경로로 보냄. 탭/주소창 같은 browser chrome UI 는 DOM 이 아닌데 Selenium DOM 으로 처리하라고 잘못 안내.
  3. AI 가 새 driver 를 띄우는 코드를 생성 (기존 Chrome 에 attach 안 함) → 새 창엔 그 element 없으니 전부 실패.

- **태그**: ai-quality, element-picker, prompt
- **분류**: **fix-now (적용 완료)** — 단일 generalize 가능한 기준 추가 (하드코딩 0):
  - `WindowInspector.should_use_selenium(element_info)` = `dom_context.cdp_available AND dom_context.tagName`
  - `get_element_info_text` 가 이 헬퍼로 라우팅 — Selenium DOM 가능 시에만 Selenium path, 그 외 (browser chrome / CDP 미연결 / 데스크톱) 모두 pywinauto path
  - `main_window:791` 의 `is_browser_elem` 도 같은 헬퍼로 결정 (양쪽 일관성)
  - `_get_browser_element_info_text` 의 "HTML ID" → "AutomationID" 라벨 정정
  - 신규 prompt_quality 테스트 3개 + core 테스트 1개 갱신

- **원칙**: picker 가 이미 수집하는 `dom_context` 만으로 결정. Chrome/Edge/Firefox 별 클래스명, 'Tab'/'Toolbar' 같은 control_type 검사 없이 동일 로직 동작. CDP 가 DOM 정보를 가져왔는지 여부 = 그 element 가 진짜 DOM 인지 여부와 동치.
- **남은 후속**: AI 가 기존 Chrome 에 attach 하는 옵션 (`--remote-debugging-port=9222` + `debuggerAddress`) 을 더 잘 안내하도록 prompt 개선은 별도 작업으로.

### 2026-04-28 19:30 - 요소 선택 오버레이가 mouse-over 이벤트를 아래 앱에 새 줌 [2차 fix]
- **상황**: 요소 선택 모드 진입 후 마우스를 움직이는 중
- **요청**: 오버레이가 모든 마우스 이벤트를 차단하고 picker 만 반응해야 함
- **기대**: 아래 앱은 마우스 움직임/hover 효과가 전혀 발동되지 않음
- **실제**: 마우스가 움직일 때마다 underlying 앱 요소가 hover/mouseover 로 미세하게 반응

- **1차 가설 (틀림)**: paint 의 `CompositionMode_Clear` (alpha=0 hole-punch) 가 click-through 의 원인이라 추측. 19:30 에 수정했지만 사용자 재테스트 결과 동일 증상 지속. paint 의 alpha 는 보탬 정도였고 핵심 아니었음.

- **2차 진짜 원인** (`ui/element_picker.py:343-355`): `_detect_element_multi_backend` 가 매 100ms 마다 `WS_EX_TRANSPARENT` 를 토글하고 그 안에서 `pywinauto.from_point()` (50-200ms 소요) 를 호출. 토글 윈도우가 50-200ms 동안 유지되어 그 사이 mouse-move 이벤트가 OS 레벨에서 underlying app 으로 직행. `WS_EX_TRANSPARENT` 자체가 OS click-through 플래그라 `WA_TransparentForMouseEvents=False` 의 Qt 레벨 의도를 override.

- **태그**: ui, element-picker
- **2차 fix (실패)**: `WS_EX_TRANSPARENT` 토글을 µs 단위로 축소했지만 사용자 재테스트 결과 누수 + highlight 미표시 둘 다 발생. SetWindowLongW 의 hit-test 캐시 + 1000Hz 입력 큐 조합에서 µs 토글도 충분히 새는 것으로 추정. 또한 µs 토글 안에서 `WindowFromPoint` 가 우리 overlay 를 반환했을 가능성 (캐시) → highlight 가 우리 overlay 의 거대한 rect 를 그려 시각적으로 보이지 않게 됨.

- **3차 fix (실패)** — EnumWindows + WS_EX_TRANSPARENT 제거 시도. 사용자 재테스트 결과 누수는 사라졌지만 highlight + info 가 **완전히 안 보임**. 진단 print 추가 후 재테스트로 핀포인트.

- **3차 진단 결과** — `cursor phys=(...)` diag 줄은 찍히는데 `감지 OK/실패` diag 줄이 한 번도 안 찍힘. 외곽 `try/except Exception` 이 silently 삼키는 예외가 있다는 뜻.

- **3차 진짜 원인** — 제가 추가한 `_ensure_user32_argtypes` 안에서 클래스명을 **`ElementPicker` 로 하드코딩** 했는데 실제는 **`ElementPickerOverlay`** 였음. 매 tick `NameError` 발생. 외곽 `except Exception` 이 logger.debug 로 삼켜서 콘솔에 한 번도 안 보였음.
  - 역설: 이 NameError 가 함수를 즉시 raise 시켜 `WS_EX_TRANSPARENT` 토글 코드가 한 번도 실행 안 됨 → 누수가 "사라진" 것처럼 보였지만 실제로는 EnumWindows/GetTopWindow 코드도 실행 안 됨 → highlight 도 안 나옴.

- **4차 fix (적용 완료, 재테스트 필요)**:
  1) 클래스명 의존 제거 — 모듈 레벨 `_user32_argtypes_set` 플래그로 변경
  2) `_find_topmost_window_at_point` 가 `GetTopWindow + GetWindow(GW_HWNDNEXT)` 루프로 z-order 순회 (콜백 ctypes 변환 이슈 회피)
  3) user32 argtypes 명시 (HWND 가 c_int 로 잘리는 일 없게)
  4) 진단 print 는 picker 시작 후 첫 3 tick 만 출력하도록 유지 — 다음 재테스트의 결과를 사용자가 콘솔에서 직접 확인 가능

- **태그**: ui, element-picker
- **분류**: **fix-now (적용 완료, 재테스트 필요)**
- **교훈**: 외곽 `except Exception` 이 모든 진단을 삼키고 있어 디버깅이 어려웠음. 이 자리는 logger.debug 보다 logger.warning + 한 번만 출력하도록 정리하는 게 좋음 (별도 polish 후보).


### 2026-04-28 18:50 - 환경 다이얼로그 "재스캔" 클릭 시 TypeError
- **상황**: F.2 GUI 검증 중, 결과 페이지에서 🔄 재스캔 버튼 클릭
- **요청**: 환경 재검사
- **기대**: 새로 스캔하고 결과 표시
- **실제**: "환경 스캔 중 오류 발생: expected str, bytes or os.PathLike object, not bool" 오류 다이얼로그
- **증거**: `ui/environment_setup_dialog.py:106` `clicked.connect(self._start_scan)` — `clicked` 시그널의 bool checked 인자가 `_start_scan(python_path=False)` 로 들어가 `subprocess.run([False, '--version'])` → TypeError. **사전 존재 버그**. F.1 의 silent except 좁힘으로 마스킹이 풀려 노출됨.
- **태그**: ui, env
- **분류**: **fix-now (적용 완료)** — `clicked.connect(lambda: self._start_scan())` + `_start_scan` 에 `isinstance(python_path, str)` 가드. 비슷한 다른 5개 슬롯은 인자 없는 시그니처라 안전.

