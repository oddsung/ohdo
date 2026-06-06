# devloop — desktop_v3 자율 테스트-개발 환경

> 체크포인트: 2026-06-06 · 브랜치 `feat/devloop-harness` · `main` 무접촉

`desktop_v3`(Electron+React) 제품을 **외부에서** 구동·검증하고, 발견한 문제를 AI(`claude --print`)에
자율 수정시킨 뒤 재테스트하는 독립 모듈. 사람이 직접 클릭·확인하던 RPA 검증을 자동화하는 것이 목적.

devloop 는 desktop_v3 와 **완전히 독립**(자체 `package.json`/`node_modules`, 빌드·의존성 비침투)이며,
모든 작업은 전용 git 브랜치에서만 이뤄진다.

## 두 계층

| 계층 | 위치 | 역할 |
|------|------|------|
| **오케스트레이터 루프** | `devloop/src/` | 빌드→E2E→실패분석→claude 수정→커밋→반복(자율). 안전모델·dry-run·circuit breaker. 상세: [devloop/README.md](../devloop/README.md) |
| **제품 시나리오 테스트** | `devloop/scenarios/` | ohdo 제품 워크플로(아래) 자체를 검증. 이번 세션의 핵심. |

## 제품 시나리오 테스트 — 핵심 방법론

ohdo 의 진짜 가치는 "AI 에게 단계별로 요청 → Python 자동화 코드 생성 → 실행 → 실제 앱이 시나리오대로
동작" 이다. 이를 그대로 자동 검증한다:

```
ohdo 구동 → AI 에 단계 요청(NL) → agy 가 Python 생성 → 실행(실제 앱 제어)
   → 실제 결과(파일/디스플레이/DOM) 검증 → 실패·개선점 판단 → claude 가 ohdo codegen 수정
   → 재생성 → 재실행 → 통과 (= 닫힌 루프 test→fix→retest)
```

**요소 선택(picker)도 포함**: Playwright 로 ohdo 의 "요소 선택"을 누르고, 동시에 `pyautogui` 로 대상
앱의 실제 요소를 클릭해 ohdo 의 전역-후크 picker 가 element_context 를 잡게 한다(충실한 picker UX).

### 두 가지 구동 방식

- **NL(요소선택 불필요)**: `core.AppService` 를 직접 호출(`generate_step` + `run_blocks`). Electron/Playwright 불필요 → 빠름. 예: `close_loop2.py`, `browser_nl.py`.
- **picker 포함**: Playwright-Electron 으로 ohdo UI 를 구동(`요소 선택` 클릭) + `pyautogui` 실제 클릭. 예: `notepad_pick.mts`, `calc_pick.mts`.

## 시나리오 스크립트

| 파일 | 시나리오 | 실행 |
|------|---------|------|
| `scenarios/notepad_saveas.mts` | 메모장 실행→입력→다른이름저장(NL+UI) | `npx tsx scenarios/notepad_saveas.mts` |
| `scenarios/notepad_pick.mts` | 메모장 입력창을 **picker로 선택**→입력→저장 | `npx tsx scenarios/notepad_pick.mts` |
| `scenarios/calc_pick.mts` | 계산기 실행→버튼 4개 **picker 선택**(7+3=10)→결과검증 | `npx tsx scenarios/calc_pick.mts` |
| `scenarios/close_loop2.py` | Save As 닫힌루프(새 세션 3스텝 생성→실행→파일검증) | `python devloop/scenarios/close_loop2.py` |
| `scenarios/browser_nl.py` | 로컬 HTML 을 Chrome(Selenium)으로 열기→입력→전송→결과 | `python devloop/scenarios/browser_nl.py` |
| `scenarios/exec_diag.py` | 기존 세션의 step 들을 직접 실행해 단계별 성공/실패 진단(agy 0) | `python devloop/scenarios/exec_diag.py <세션id접두사>` |
| `scenarios/calc_pick_target.py`, `pick_target.py` | picker용 — 대상 요소 좌표 찾아 실제 클릭(DPI-aware) | (드라이버가 호출) |
| `scenarios/saveas_probe*.py` | Save As 원인 추적 진단 probe 모음(투명 기록용) | (참고) |

> ⚠️ `.mts` 드라이버는 `desktop_v3` 빌드본(`out/main/index.js`)을 Playwright `_electron` 으로 띄운다.
> VS Code 통합 터미널에서 돌릴 땐 `cleanElectronEnv`(src/paths.ts)가 상속 환경의
> `ELECTRON_RUN_AS_NODE`/`VSCODE_*` 를 제거해야 launch 가 된다(미제거 시 자식 electron 이 node 모드).

## 검증으로 발견·수정한 ohdo 결함 (2026-06-06)

자동 테스트가 **사람 검증으로는 놓치기 쉬운 실제 결함**들을 잡았다.

| # | 결함 | 상태 | 수정/메모 |
|---|------|------|-----------|
| 1 | 채팅 전송 버튼 접근이름(aria) 없음 (a11y) | ✅ 수정 | `chat.send` title 추가 |
| 2 | 빈 상태(EmptyState)에 1차 행동 없음 | ✅ 수정 | "새 세션 만들기" CTA |
| 3 | **한국어 IME 가 Ctrl+Shift+S(다른이름저장) 흡수** → 단축키 미동작 | ✅ 수정 | 라이브러리 shim `force_english_ime()` + hotkey 래핑(`core/workflow_engine.py`) |
| 4 | Save As 다이얼로그 탐지 실패(`Desktop().windows()` 모달 누락) | ✅ 수정 | `save_as_to_path()` 헬퍼(GetForegroundWindow) + 가이드 #22(`config/prompts.json`). **닫힌 루프 완성** |
| 5 | 평문-시크릿 감지가 따옴표 일반텍스트 오탐(`quoted_literal`) | ⏳ 발견 | 드라이버는 confirm 자동승인으로 우회 |
| 6 | 실행 실패인데 `success=True` 오보고(생성코드가 예외 삼킴) | ⏳ 발견 | 시나리오 성공은 step.status 아닌 **실제 산출물**로 판정 |
| 7 | picker 연속 픽 신뢰성(=버튼/4번째 캡처 실패) | ⏳ 부분개선 | 상태기반 페이싱(요소선택 enabled 대기 + /pick/cancel) — 7/+/3 안정, = 잔존 |
| 8 | 선택요소 없을 때 AI 가 wrong-button 추측 | ⏳ 발견 | 드라이버는 추측 방지 위해 중단 |
| 9 | 브라우저 codegen routing 비결정성(Selenium/pyautogui/Desktop 혼용) | ⏳ 부분개선 | prompt_builder Selenium-세션 강제 지시(부분) |
| 10 | Selenium Chrome 실행이 커널 컨텍스트에서 flaky | ⏳ 발견 | 동일 코드 단독실행은 성공 |

## 방법론 교훈

- **막히면 스크린샷**(`pyautogui.screenshot`): 로그의 "다이얼로그 못 찾음"이 실제론 "IME로 안 열림" / "열렸는데 탐지 실패"였음을 두 번 다 캡처가 바로잡음.
- **실제 결과로 검증**: step.status/`success` 는 실행 status 를 session.json 에 반영 안 하거나 예외를 삼켜 신뢰 불가 → 파일/디스플레이/DOM 등 실산출물 확인.
- **프로세스 정리**: 테스트 간 `notepad`/`Calculator`/automation `chrome`+`chromedriver` 정리 필요(detach 누적이 다음 런 launch 를 깨뜨림). 사용자 일반 Chrome 은 보존(`--enable-automation`/`--test-type` 플래그로 구분).
- **prompts.json 편집**: 거대 `system_context` 단일 문자열 → 직접 이스케이프 편집 금지, `json.load → 문자열 append → json.dump(ensure_ascii=False)` 로 안전하게.
- **agy 생성 지연**: 단계당 ~1.5~2분, 변동 큼 → 타임아웃 넉넉히(300s). cp949 콘솔은 `PYTHONIOENCODING=utf-8` + `sys.stdout.reconfigure`.

## 알려진 한계 / 다음 단계

- **브라우저(웹) 경로는 가장 미성숙**(docs/[element_picker_research.md](element_picker_research.md)/[cdp_consideration.md](cdp_consideration.md)): Chrome 접근성 핸드셰이크 미해결, CDP attach 수동. 브라우저 picker(CDP+`--force-renderer-accessibility`)는 미진행. 신뢰성 확보엔 codegen 결정성 + 커널 Selenium 안정화가 선행 필요.
- picker 연속 픽의 = 버튼 엣지케이스, success 오보고(#6), 평문 오탐(#5)은 후속 수정 대상.
- 오케스트레이터의 완전자율(next-step) 루프는 검증됨(§Phase 3) — 시나리오 E2E 와 결합은 후속.
