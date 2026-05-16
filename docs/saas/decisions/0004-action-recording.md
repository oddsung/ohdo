# ADR 0004: 작업 녹화 (Action Recording) 를 도입하여 사용자가 평상시 작업을 그대로 따라 자동화 코드가 생성되도록 한다

- **상태**: Accepted (2026-05-16 — 사용자 검토 완료, 5개 결정 확정 + 메인화면 통합점 추가, PR-11 부터 구현 시작)
- **최초 작성일**: 2026-05-16
- **결정자**: @toytiger
- **관련 문서**:
  - [설계 — Phase R1+R2 데이터 흐름·삽입점](../architecture/25-recording-phase-r1-r2.md)
  - [ADR 0001 — wrap-first 정책](0001-preserve-existing-core.md)
  - [ADR 0002 — AppService Facade 접근](0002-appservice-facade-approach.md)
  - [ADR 0003 — 시크릿 처리](0003-secrets-handling.md)
  - [handoff.md §23](../../handoff.md) — ADR 0003 Phase 1+2 구현 완료

## 컨텍스트

ohdo 의 현재 UVP 는 *"AI 와 대화로 RPA 코드 만들기"* 다. 사용자는 "메모장에서 '안녕' 입력하고 저장해" 같은 자연어로 매 단계를 설명해야 한다. 이는 다음 장벽을 만든다:

1. **AI 두려운 사용자 진입 차단**: 비개발자/AI 처음 쓰는 사용자는 *"어떻게 설명해야 잘 만들까"* 자체가 부담.
2. **반복 설명 비용**: 평소 손으로 하던 작업 (예: 매일 ERP 5개 화면 거치는 루틴) 을 글로 풀어쓰는 부담.
3. **기존 자동화 마이그레이션 불가**: Power Automate Desktop, AutoHotkey, pywinauto 스크립트로 이미 만들어둔 자동화를 ohdo 로 옮기려면 처음부터 다시 설명해야 함.

한편 ohdo 의 코어에는 **녹화 기능의 핵심 인프라가 이미 절반 이상 구축되어 있다**:

| 자산 | 위치 | 녹화 역할 |
|---|---|---|
| WH_MOUSE_LL 후크 | [ui/element_picker.py:2150-2227](../../../ui/element_picker.py) | 클릭 이벤트 캡처 (이미 차단·통과 토글까지 구현) |
| WH_KEYBOARD_LL 후크 | [ui/element_picker.py:2077-2145](../../../ui/element_picker.py) | 키입력 + 핫키 캡처 |
| EFP (ElementFromPoint) | element_picker 전체 | 좌표 → UIA element 메타데이터 |
| `win_inspector.generate_*_code` | [core/win_inspector.py](../../../core/win_inspector.py) | element 메타 → 데스크톱/브라우저/owner-drawn 코드 |
| Session + Step 모델 | [core/session_manager.py](../../../core/session_manager.py) + [core/models.py](../../../core/models.py) | 녹화 결과 저장소 (필드 그대로 재사용) |
| AppService step CRUD | [core/app_service.py](../../../core/app_service.py) | 녹화 후 step 일괄 삽입 path |

또한 ADR 0003 (시크릿 처리) 이 5/13~5/14 에 Phase 1+2 까지 완료된 상태로, 녹화 중 PW field 입력을 자동 감지 → advisory → `get_secret()` 변환하는 **강 통합 시너지**가 가능하다.

경쟁 도구 (Power Automate Desktop, UiPath StudioX) 는 녹화를 핵심 기능으로 제공하나 결과물이 closed XML/XAML 이며 AI 와 결합되어 있지 않다. ohdo 는 (a) 결과가 순수 Python 코드, (b) 녹화 후 AI 가 다듬을 수 있음, (c) 데스크톱+웹 통합 — 세 차별점을 가진다.

## 결정

**1. 작업 녹화 (Action Recording) 기능을 Phase R1+R2 로 도입한다.** 사용자가 녹화 시작 → 평상시 작업 → 녹화 중지 → ohdo Session 의 step 리스트로 변환된다.

### 2. 핵심 데이터 흐름

```
[1] 사용자: 녹화 시작 (Ctrl+Shift+R 또는 툴바 ⏺ 버튼)
        ↓
   ohdo 창 minimize, recorder floating overlay (click-through status bar) 만 남음
        ↓
[2] 평상시 작업 수행
   ├── 클릭 → WH_MOUSE_LL → 좌표 + EFP → element 메타
   ├── 키입력 → WH_KEYBOARD_LL → 텍스트 그룹핑 (연속 입력 → 1 event)
   ├── 창 전환 → SetWinEventHook (EVENT_SYSTEM_FOREGROUND) → step 경계
   └── 단축키 F8 (선택) → 명시적 step 경계 marker
        ↓
[3] 녹화 중지 (Ctrl+Shift+R 또는 overlay 클릭)
        ↓
[4] 후처리: raw events → step 변환
   ├── 노이즈 필터 (ohdo 자체 창 클릭, 빈 공간 클릭)
   ├── 텍스트 입력 그룹핑
   ├── win_inspector 로 각 event → Python 코드
   ├── ADR 0003 통합: PW field 입력 → secrets_detector → advisory → get_secret()
   └── step description 자동 생성
        ↓
[5] 검토 다이얼로그: step 목록 미리보기 + 편집 (drop/merge/relabel) → 세션에 commit
```

### 3. 기술적 핵심 결정

- **후크 모듈 추출**: 현재 element_picker 에 박힌 LL hook 코드를 `core/input_hooks.py` 로 추출. element_picker 와 recorder 둘 다 의존. element_picker 의 baseline (§4.1) 회귀 0 보장이 절대 조건.
- **Element 식별 fallback chain**: (1) UIA `automation_id` → (2) UIA `name + control_type` → (3) screenshot + bbox (OpenCV 매칭, Phase R3) → (4) 좌표 + DPI awareness (`pyautogui.click(x, y)`).
- **노이즈 처리 4계층**: (a) 자체 창 자동 drop, (b) 연속 키입력 자동 group, (c) 창 포커스 전환 자동 경계, (d) F8 수동 marker (선택). 변환 후 미리보기 다이얼로그에서 사용자가 drop/merge/relabel 가능.
- **마이그레이션 모드**: 빠른 SendInput 따라잡기 — event queue + async EFP. 데스크톱 RPA (Power Automate Desktop, AutoHotkey, pywinauto) → 가능. Selenium/Playwright (CDP 내부 명령) → 데스크톱/창 전환 부분만 캡처 (Phase R3 에서 CDP 후킹 추가).

### 4. ADR 0003 와의 강 통합

녹화 중 키입력 캡처 시 **포커스 element 가 password field (`type=password` HTML 또는 UIA password-hint automation_id)** 면:

1. `secrets_detector.is_password_field_element` (이미 PR-7 구현됨) 호출
2. PW field 면 raw 텍스트를 buffer 하지 않고 `SecretAdvisoryDialog` 발동
3. 사용자가 라벨 입력 → `vault.set(label, value)`
4. 해당 step 의 `generated_code` 가 `pyautogui.write("...")` 대신 `pyautogui.write(get_secret('label'))` 로 생성

이로써 녹화된 자동화 코드에 평문 PW 가 한 번도 들어가지 않는다. 단순 매크로 도구와의 결정적 차이.

### 5. UX 기본값 (사용자 검토 후 조정 가능)

| 항목 | 기본값 | 대안 |
|---|---|---|
| Step 경계 marker | 자동 (창 포커스 전환) + F8 수동 (둘 다 활성) | 자동만 / F8만 |
| 녹화 중 ohdo UI | minimize + floating overlay (click-through status bar, 빨간 ⏺ + 경과 시간 + step 수) | 완전 hide / 항상 보임 |
| 결과 미리보기 | 항상 강제 (drop/merge/relabel) | 옵션 (즉시 commit 모드 — 익숙해진 사용자) |
| 핫키 | Ctrl+Shift+R (시작/중지), F8 (수동 marker) | 사용자 설정 |
| ohdo 자체 창 클릭 | 자동 drop (overlay 제외) | 옵션 |
| 빈 공간 클릭 (element 못 잡힌) | 좌표만 캡처, 경고 표시 | drop / keep |

### 6. 라이선스·보안 정책

- 녹화 데이터 (raw events + 캡처) 는 **로컬 저장만**. 클라우드 전송 X. Phase 2 SaaS 진입 시 사용자 명시 동의 + opt-in 후에만 전송.
- 화면 캡처 (OpenCV fallback 용) 는 **기본 OFF**. 사용자 명시 동의 후 활성.
- 녹화 중 사용자의 다른 앱 내용이 캡처될 수 있음 → README + 첫 녹화 시 명시 안내 모달.

## 결과 / 트레이드오프

### 긍정

- **진입 장벽 대폭 감소**: 비개발자/AI 두려운 사용자도 평상시처럼 사용 가능. 글로벌 시장 SAM 확장.
- **마이그레이션 채널 확보**: 기존 RPA 사용자가 ohdo 로 옮길 길 — 경쟁 도구 대비 큰 차별점.
- **ADR 0003 와 시너지**: 녹화 + 시크릿 자동 처리 = 단순 매크로보다 한 단계 위. 보안 의식 있는 기업/개발자에게도 어필.
- **기존 자산 재사용 비중 큼**: 새 모듈 신규 작성은 ~30%, 70% 는 기존 코드 통합. MVP (Phase R1) 약 2주 추산.
- **결과물 순수 Python**: Git 커밋, VSCode 편집, 다른 시스템 이식 가능. ohdo 의 핵심 가치 유지.

### 부정 / 리스크

- **LL hook 글로벌 리소스**: 시스템 전체 입력에 영향. hook callback 100ms 이내 처리 강제 (이미 element_picker 가 지킴). hook 모듈 추출 시 element_picker baseline 회귀 회피가 절대 조건.
- **EFP latency (100~500ms)**: 빠른 클릭은 element 식별 실패. screenshot fallback (Phase R3) + 사후 편집으로 사용자 보충.
- **노이즈 폭발 위험**: UX 실패 시 unusable. 자동 그룹핑 + 미리보기 강제로 완화.
- **브라우저 자동화 마이그레이션 제약**: Selenium chromedriver 가 띄운 브라우저 안 클릭은 CDP 내부 → LL hook 안 잡힘. Phase R3 에서 CDP 후킹 추가로 일부 보완.
- **Win11 ForegroundLock**: recorder overlay 가 가짜로 포커스 잡지 않도록 `WS_EX_NOACTIVATE` + click-through 필수.
- **사생활 / 데이터 정책**: 녹화 중 사용자의 다른 앱 콘텐츠가 캡처될 수 있음. 화면 캡처 기본 OFF + 명시 동의로 완화.

### 측정 가능한 성공 기준 (Phase R1 완료 시점)

- core 테스트 baseline 무손상 (144/144 + scenarios 73/73 그린 유지)
- 신규 회귀 테스트: notepad/calculator/explorer 시나리오 5종 녹화 → 변환 → 재생 → 동일 결과
- element_picker baseline (§4.1, test_42~48) 회귀 0
- 녹화 → 변환 후 step 수 / raw event 수 ≤ 30% (노이즈 그룹핑 효과 측정)
- ADR 0003 통합: PW field 녹화 → 자동 `get_secret()` 변환 시나리오 통과

## Phase 분할

상세는 [25-recording-phase-r1-r2.md](../architecture/25-recording-phase-r1-r2.md) 참조.

| Phase | 범위 | 예상 기간 | 핵심 PR |
|---|---|---|---|
| **R1** | 데스크톱 클릭+키 녹화, 후크 모듈 추출, win_inspector 변환, 미리보기 다이얼로그, ADR 0003 강 통합 | ~2주 | PR-11 ~ PR-15 |
| **R2** | 창 포커스 자동 경계, F8 수동 marker, 마이그레이션 모드 (event queue + async EFP), DPI/멀티모니터 안정화, i18n catalog | ~1주 | PR-16 ~ PR-18 |
| **R3** (후순위) | AI 후처리 (raw step 의미 단위로 묶기 + 변수화), 브라우저 CDP 후킹, screenshot OpenCV fallback | ~1~2주 | PR-19+ |

R1+R2 를 묶어 진행 (3주). R3 는 R1+R2 실측 후 결정.

## 확정된 결정 사항 (2026-05-16 사용자 승인)

1. **Phase 범위**: R1+R2 묶음 (3주, 권장안 그대로).
2. **결과 미리보기**: 항상 강제 (R1). 즉시 commit 모드는 R3 후보.
3. **녹화 핫키**: Ctrl+Shift+R 하드코딩 (R1). 사용자 설정은 R2 settings UI.
4. **마이그레이션 모드**: R2 (권장 그대로). R1 은 데스크톱 클릭+키 핵심에 집중.
5. **화면 캡처 기본값**: OFF (권장 그대로). R3 OpenCV fallback 도입 시 옵션 ON 가능.

## 사용자 추가 요청 사항 (2026-05-16)

### 6. 메인화면 통합 (D25 빈 상태 화면)

**요구**: "새 세션을 눌렀을 때 보여지는 메인화면의 템플릿/예시화면 영역에 자동녹화 선택을 할 수 있도록".

**현재 상태**: 새 세션 생성 시 [ui_v2/main_window_v2.py:1969-2018](../../../ui_v2/main_window_v2.py#L1969) 의 `_show_empty_state` 가 빈 상태 안내 + 예시 카드 3개 (notepad/browser/window_title) 표시. 사용자가 카드 클릭하면 입력창 자동 채움.

**결정**:
- D25 빈 상태 화면의 예시 카드 위에 **별도의 강조 박스 "🎬 자동 녹화로 만들기"** 카드 추가. 클릭 시 즉시 녹화 시작.
- 추가로 "+ 새 탭" 메뉴 ([ui_v2/main_window_v2.py:1638](../../../ui_v2/main_window_v2.py#L1638)) 에 **"녹화로 새 세션"** 액션 추가. 새 세션 + 즉시 녹화 시작.
- 첫 사용자에게 녹화 기능을 발견시키는 것이 핵심. 예시 카드 (텍스트 기반 시나리오) 와 녹화 카드 (행동 기반) 가 병렬로 진입점.

### 7. Step 적절한 구분 (녹화 → 의미 단위 step 변환 강화)

**요구**: "녹화 시 각 작업들을 적절하게 구분하여 step 으로 만들어".

**결정** (architecture 25 §3 의 transform 강화):
- **자동 경계 신호 4종**: (a) 창 포커스 전환, (b) F8 수동 marker, (c) 동일 element 연속 키입력 group 종료, (d) 의미 단위 휴리스틱 — 이전 클릭 후 N초 (기본 3초) 휴지면 새 step.
- **각 step 의 user_request 자동 생성**: element 의 control_type + name 조합 (예: "Edit '사용자 ID' 클릭 후 텍스트 입력"). 사용자가 review 다이얼로그에서 inline edit.
- **step 분할/병합 휴리스틱 + 미리보기**: 변환 결과를 사용자에게 항상 보여줌, 의미상 한 step 인데 분할되었거나 그 반대인 경우 사용자가 한 번에 수정 가능.

### 8. 녹화 후 수정 수월화 (review dialog 편집 기능 강화)

**요구**: "녹화로 만들어진 이후에 사용자가 수정할 수 있는 부분을 수월하게 수정할 수 있도록".

**결정** (architecture 25 §4 PR-15 의 review dialog 강화):
- **inline 편집 가능 필드**: user_request (제목), generated_code, wait_after_ms.
- **drag&drop 순서 변경**: step 카드 위/아래 이동.
- **multi-select bulk action**: shift-click 여러 step 선택 → bulk drop / bulk merge.
- **자동 분할 / 병합 버튼**: 인접 step 우클릭 → "이전 step 과 합치기" / step 우클릭 → "이 step 분할".
- **변환 옵션 toggle**: 다이얼로그 상단에 "키 그룹핑 ON/OFF", "빈 공간 클릭 keep/drop", "창 포커스 자동 경계 ON/OFF" 토글 → 즉시 재변환.
- **원본 raw events 보기 (디버그)**: 사용자가 의도한 동작이 누락되었을 때 raw event 시퀀스 보고 어디서 빠졌는지 확인 가능.
- **변환 결과 미리 실행 버튼** (선택): 변환된 step 들을 즉시 한 번 재생해보고 commit 여부 결정.

위 강화는 **PR-15 의 범위 확장**으로 흡수. PR 추가 분할 없음.

---

위 8개 결정 모두 architecture 문서 25 에 반영 완료. PR-11 부터 구현 시작.
