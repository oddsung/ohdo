# Element Picker 리서치 정리

> 작성일: 2026-04-28
> 목적: Windows/macOS/Linux 데스크톱 + 브라우저 요소 선택 (RPA picker) 의 기존 도구·라이브러리·방법론을 한 곳에 모아두고, 내일 이어서 작업할 때 참고할 가이드.
> 맥락: ohdo 의 [ui/element_picker.py](../ui/element_picker.py) 가 Chrome 웹페이지 내부 요소를 일관되게 잡지 못하는 문제 (탭 갯수에 따라 잡히고 안 잡히는 비결정적 동작) 의 원인과 해결책을 찾기 위한 리서치.

---

## 0. 가장 중요한 발견 (TL;DR — 내일 이걸로 시작)

### Chrome 의 **2단계 accessibility handshake**

Chrome 은 화면읽기 성능 비용을 줄이기 위해 **요청이 있을 때만** 접근성 트리를 활성화한다. 활성화 트리거는 **세 가지**:

1. `--force-renderer-accessibility` CLI 플래그로 강제 켜기
2. NVDA/JAWS 같은 알려진 화면읽기 프로세스가 띄워져 있으면 자동 감지
3. **두 단계 핸드셰이크**:
   1. Chrome 이 자기 윈도우에 대해 `NotifyWinEvent(EVENT_SYSTEM_ALERT, hwnd, kIdCustom, 0)` 를 쏨 (kIdCustom = 1, 윈도우즈 표준이 아닌 Chrome 자체 magic number)
   2. AT (assistive technology) 측에서 그 alert 를 받고 `WM_GETOBJECT` 를 lParam 으로 **해당 custom id (1)** 를 실어 응답해야 함
   3. 응답이 오면 Chrome 이 "AT 가 듣고 있구나" 를 인식하고 renderer 의 accessibility 를 켬

### 우리 코드의 현재 상태

[ui/element_picker.py](../ui/element_picker.py) 는 `WM_GETOBJECT` 를 `OBJID_CLIENT(-4)` 로 보내고 있는데, 이 magic number 는 일반 윈도우용 표준이고 **Chrome 의 custom check (1)** 와 매치되지 않는다. 그래서 Chrome 이 "AT 신호" 로 인식하지 않고 renderer accessibility 를 켜지 않는 것으로 보임.

### 내일 시도할 수정

```python
# 현재: ui/element_picker.py 내 _trigger_chrome_accessibility 같은 위치
SendMessageW(hwnd, WM_GETOBJECT, 0, OBJID_CLIENT)  # -4

# 시도해볼 것:
KID_CUSTOM = 1
SendMessageW(hwnd, WM_GETOBJECT, 0, KID_CUSTOM)
# 또는 Chrome 의 NotifyWinEvent 패턴을 우리가 흉내내서 더 적극적으로:
# 1) WM_GETOBJECT (KID_CUSTOM) 를 모든 Chrome 자식 HWND 에 broadcast
# 2) 200~500ms 대기 (renderer 가 트리 빌드할 시간)
# 3) UIA tree walk 재시도
```

대안으로 `--force-renderer-accessibility` 를 ohdo 사용자에게 권장하는 옵션 (기존 CDP hint 처럼 토스트로 안내) 도 fallback 으로 같이 두는 것이 안전.

### 출처

- chromium.googlesource.com — `BrowserAccessibilityManagerWin::FireWinAccessibilityEvent` 에 EVENT_SYSTEM_ALERT + kIdCustom 패턴
- Chrome Accessibility Architecture 문서: "WebContents only enables accessibility when an assistive tech client requests it"
- AssistiveTechnologySupportObserver 클래스가 WM_GETOBJECT 응답을 감지

---

## 1. 기존 데스크톱 element picker 도구 비교

### 1.1 Microsoft Inspect.exe (UIA SDK 표준 도구)

- **설치**: Windows SDK 와 함께 제공 (`C:\Program Files (x86)\Windows Kits\10\bin\<ver>\x64\inspect.exe`)
- **방식**: IUIAutomation::ElementFromPoint 를 cursor 위치에 호출
- **장점**: Microsoft 공식, 가장 정확한 ground-truth
- **단점**: hover-only 모드는 키보드 단축키 (Ctrl) 로 잠깐 멈춰야 함, GUI 가 별도 창
- **참고**: Chrome/Edge accessibility 는 inspect.exe 가 띄워져 있으면 자동으로 활성화됨 — 이게 inspect.exe 가 잘 보는 핵심 이유 (내가 띄우는 순간 #2 트리거 발동)

### 1.2 Accessibility Insights for Windows (Microsoft, 후속 도구)

- **레포**: github.com/microsoft/accessibility-insights-windows
- **차이점**: inspect.exe 의 modern 버전, WPF 로 작성, 자동 결함 검출 기능
- **방식**: 동일하게 IUIAutomation 기반
- **참고할 점**: 오버레이 highlighting 패턴 — `SnapshotApp` 라는 별도 visualization layer 를 사용하여 cursor 추적 시 깜빡임 최소화

### 1.3 FlaUInspect (FlaUI 생태계, .NET)

- **레포**: github.com/FlaUI/FlaUInspect
- **방식**: HoverMode + Focus tracking + Tree drill-down 세 가지 모드
- **HoverMode 구현**: `DispatcherTimer` 가 cursor 위치를 폴링 (16ms tick) → `Automation.FromPoint()` 호출 → 결과를 cache 에 비교 → 변경되면 highlight 갱신
- **trigger**: Ctrl 키 누르고 있을 때만 hover 동작 활성화 (우리 F3 와 비슷한 사용 흐름)
- **활용 가능한 패턴**:
  1. Cursor 폴링 주기 (60Hz) + 변경 감지 후 트리 walk
  2. **previously highlighted element** 와 동일하면 walk 스킵 → CPU 절약
  3. Ctrl 키 modifier 로 hover/freeze 토글

### 1.4 UIPath / BluePrism / AA picker (상용 RPA)

- **공통 패턴**:
  - 다중 backend 시도 (UIA → MSAA → Win32 → Image OCR)
  - **selector 의 우선순위 트리** 에 가중치 부여 (자식이 너무 작으면 부모로 fallback, 100×100 보다 작으면 부모 사용)
  - **Anchor element** 개념: 타깃 요소가 동적이면 근처의 안정적인 요소를 anchor 로 잡고 상대 좌표로 클릭
- **공식 문서 키워드**: "Computer Vision activities", "UI Object Repository", "Strict selectors vs Fuzzy selectors"

### 1.5 pywinauto (우리가 사용 중)

- **장점**: Python 네이티브, UIA + Win32 둘 다 지원, ControlViewWalker / RawViewWalker 노출
- **약점**:
  - `descendants()` 는 IUIAutomation::FindAll 을 root 에 호출 → Chrome 처럼 트리가 거대하면 매우 느림 (우리 케이스: 437ms)
  - `from_point` 가 IUIAutomation::ElementFromPoint 를 wrap 하지만 Chrome 의 lazy renderer 트리는 first call 에 비어있을 수 있음
- **권장 사용 패턴**:
  - root 에서 descendants 로 검색하지 말고, **TreeWalker.GetFirstChild + GetNextSibling** 으로 좌표 안에 들어오는 가지만 따라 내려가기 (우리 `_walk_uia_to_deepest` 와 동일 전략)

### 1.6 Python-UIAutomation-for-Windows (yinkaisheng)

- **레포**: github.com/yinkaisheng/Python-UIAutomation-for-Windows
- **차별점**: pywinauto 보다 IUIAutomation COM 을 더 얇게 wrap, ctypes 직호출, 일부 케이스에서 빠름
- **검토 가치**: pywinauto 가 막히는 Chrome 케이스에서 이 라이브러리는 다르게 동작하는지 비교

### 1.7 pyUIAuto / atomacos (macOS 호환)

- **pyUIAuto**: cross-platform 시도, Windows/Mac/Linux 표면 통합
- **atomacos**: macOS Accessibility 전용, AXUIElement API wrap
- **참고**: ohdo 가 향후 Mac 지원할 때 atomacos + pyobjc 조합이 표준

---

## 2. 브라우저 (특히 Chrome) 접근성 활성화 메커니즘

### 2.1 Chrome 의 accessibility lazy loading

기본 동작:
- Chrome 은 시작 시 renderer 의 a11y 트리를 **빌드하지 않음** (성능 비용 ~5-15% CPU)
- AT 가 요청한 시점에만 켜고, 켠 뒤로는 유지

활성화 트리거 (다시 정리):
1. **CLI 플래그**: `chrome.exe --force-renderer-accessibility`
   - 모든 탭에서 즉시 a11y 켜짐
   - 사용자에게 권장 가능한 옵션 (단, Chrome 재시작 필요)
2. **알려진 AT 프로세스 감지**: NVDA, JAWS, Dragon, Inspect.exe 등이 있으면 자동
3. **kIdCustom WM_GETOBJECT 핸드셰이크** (위 §0 참조)

### 2.2 chrome://accessibility 페이지

- 내부 페이지에서 탭별 a11y 상태 확인 가능
- 디버깅 시: 우리 picker 가 hover 한 후 `chrome://accessibility` 에서 해당 탭의 "accessibility mode" 가 "complete" 로 바뀌는지 확인하면 핸드셰이크 성공 여부 검증 가능

### 2.3 Chrome 자식 윈도우 구조

Chrome 의 HWND 트리는 다음과 같음:
```
Chrome_WidgetWin_1            ← 최상위 (탭바 + 주소창)
├── Chrome_RenderWidgetHostHWND ← 실제 렌더링 표면
└── Intermediate D3D Window     ← GPU compositor (HWND 으로 보이지만 a11y 트리 없음)
└── Chrome Legacy Window         ← UIA fallback HWND (이 위치에 WM_GETOBJECT 보내야 a11y 트리 옴!)
```

**핵심**: WM_GETOBJECT 는 **Chrome Legacy Window** HWND 또는 RenderWidgetHostHWND 에 보내야 한다. 우리 picker 가 main HWND (Chrome_WidgetWin_1) 에만 보내면 효과 없음.

내일 시도할 코드:
```python
# Chrome 자식 HWND 를 EnumChildWindows 로 전부 수집
# 클래스 이름이 "Chrome_RenderWidgetHostHWND" 또는 "Chrome Legacy Window" 인 것들 모두에 WM_GETOBJECT(kIdCustom=1) 발송
```

### 2.4 CDP (Chrome DevTools Protocol) 우회

- 이미 [docs/cdp_consideration.md](cdp_consideration.md) 에 작성된 결정대로, CDP attach 는 사용자에게 부담이 큼 (Chrome 종료 후 `--remote-debugging-port=9222` 로 재시작 필요)
- M3 이후 Phase 로 미룸
- 단, 사용자가 명시적으로 "내가 띄운 자동화용 Chrome" 이라면 Selenium 으로 처음부터 띄우는 것이 가장 안정적 — 이건 RPA 표준 패턴

---

## 3. Cursor → Element 매핑의 정확도 문제

### 3.1 IUIAutomation::ElementFromPoint 의 함정

- **공식 문서**: "may return a high-level element instead of the deepest"
- 실제로 Chrome 같은 거대 트리에서는 root 또는 mid-level 만 반환하는 경우 빈번
- 해결: 반환된 요소에서 다시 TreeWalker 로 cursor 위치를 따라 가장 깊은 자식까지 drill down

### 3.2 우리 `_walk_uia_to_deepest` 와 `_raw_walk_at_point` 의 차이

- `_walk_uia_to_deepest`: ControlViewWalker 사용 (PaneControl 등 컨테이너 스킵)
- `_raw_walk_at_point`: RawViewWalker 사용 (모든 노드, 더 깊지만 느림)
- **권장 사용**: ControlView 먼저, 결과가 너무 큰 영역이면 RawView 로 fallback

### 3.3 ChildWindowFromPointEx + UIA 조합

- Win32 ChildWindowFromPointEx 로 **HWND 단위** 의 깊은 자식을 먼저 찾음 (CWP_SKIPINVISIBLE | CWP_SKIPDISABLED)
- 그 HWND 에서 UIA tree 로 다시 들어감
- **주의**: Chrome Legacy Window 에 빠질 수 있음 (UIA 트리는 비어있는 stub HWND) → main HWND 와 child HWND 둘 다 시도하고 area 가 더 작은 결과 채택 (현재 구현 방식)

---

## 4. Cross-platform 라이브러리 매트릭스

| 라이브러리 | OS | API 종류 | Chrome 지원 | 비고 |
|-----------|-----|---------|------------|-----|
| pywinauto | Windows | UIA + Win32 | 부분적 (lazy 트리 문제) | 우리 사용 중 |
| Python-UIAutomation-for-Windows | Windows | UIA only | 부분적 | pywinauto 대체 후보 |
| comtypes + IUIAutomation 직접 | Windows | UIA raw | 모든 시나리오 | 가장 강력하지만 boilerplate 많음 |
| atomacos + pyobjc | macOS | AXUIElement | 잘 지원 (Safari/Chrome 동일) | macOS 미래 지원 시 |
| pyatspi (AT-SPI2) | Linux | AT-SPI | 일부 | GTK/Qt 둘 다 노출 |
| AutoIt + ctypes wrapper | Windows | Win32 only | 약함 (UIA 없음) | legacy app 용 |
| OpenCV + pyautogui | 전 OS | 픽셀 매칭 | 100% (시각만) | UIA fail 시 fallback |
| Selenium WebDriver | 전 OS (브라우저만) | DOM | 완벽 (DOM 직접) | 브라우저 한정 |

---

## 5. 효과적인 picker 설계 방법론 (업계 표준)

### 5.1 Multi-backend 캐스케이드

```
1순위: UIA (ControlView) → 깊이 walk → 가장 작은 영역
2순위: Win32 ChildWindowFromPointEx → 그 HWND 에서 UIA 재시도
3순위: UIA (RawView) → 더 깊게
4순위: Selenium (브라우저 + CDP 가능 시)
5순위: OCR + 픽셀 매칭 (마지막 수단)
```

각 단계의 결과를 area 로 비교, 가장 작은 (=가장 구체적인) 요소 채택.

### 5.2 Selector 안정성 우선순위

좋은 selector 의 특징:
1. **AutomationId** (있으면 거의 항상 stable)
2. **Name + ControlType** 조합
3. **ClassName + index**
4. **Path-based** (부모 → 자식 인덱스)
5. **Image / Coordinate** (가장 불안정)

ohdo 의 `win_inspector.py` 가 이미 이 우선순위를 따르고 있음 (확인됨).

### 5.3 Anchor + Offset 패턴

동적 UI (예: 검색 결과 카드, 채팅 메시지) 에서 매번 좌표가 다른 경우:
- 안정적인 부모를 anchor 로 잡음 (예: "검색결과" 컨테이너)
- 그 안에서 상대적 path 또는 텍스트 매칭으로 타깃 찾기

UIPath 의 "Find Children + filter by attribute" 가 이 패턴.

### 5.4 Highlighting 깜빡임 줄이기

FlaUInspect/Inspect.exe 패턴:
- 별도 transparent overlay 윈도우 (우리 ElementPickerOverlay 와 동일)
- previous_element 와 같은 요소면 redraw 스킵
- TopMost flag 를 매 tick 갱신 (다른 윈도우 위로 올라오는 것 방지)

우리 `_force_topmost()` 는 시작 시 1회만 호출. **개선 가능**: 매 tick 마다 (혹은 1초마다) 다시 호출하여 topmost 보장.

### 5.5 Hover modifier (Ctrl/F3) 패턴

- 사용자가 hover 중에 키 누르면 **freeze** (현재 요소 고정, picker 종료)
- Ctrl 누르고 있을 동안만 hover 활성화 → 실수로 잘못된 요소 잡는 것 방지
- 우리 F3 = pause/resume 은 표준에서 약간 벗어남 — 향후 "Ctrl-hold = active hover" 패턴 검토 가능

---

## 6. 내일 작업 계획 (TODO)

우선순위 순:

### 6.1 Chrome accessibility handshake 수정 (가장 가능성 높음)

1. [ui/element_picker.py](../ui/element_picker.py) 에서 WM_GETOBJECT 보내는 위치 찾기
2. `lParam=OBJID_CLIENT(-4)` → `lParam=1 (kIdCustom)` 로 시도
3. 또는 두 번 보내기: `OBJID_CLIENT` 한 번 + `kIdCustom` 한 번
4. `EnumChildWindows` 로 Chrome 의 모든 자식 HWND 수집 → 클래스 이름이 `"Chrome_RenderWidgetHostHWND"`, `"Chrome Legacy Window"`, `"Chrome_WidgetWin_*"` 인 것들 전부에 WM_GETOBJECT 발송
5. 발송 후 200~500ms 대기 → UIA tree walk 재시도

### 6.2 Fallback: --force-renderer-accessibility 안내

- main_window.py 의 `_maybe_show_cdp_hint` 처럼 일회성 안내 토스트
- "Chrome 웹페이지 요소를 더 정확히 잡으려면 Chrome 을 `--force-renderer-accessibility` 플래그로 띄우세요" + 복사 버튼

### 6.3 Chrome Legacy Window 경로 검증

- diag 출력에서 ChildWindowFromPointEx 가 어느 HWND 를 반환하는지 다시 확인
- "Chrome Legacy Window" 면 그 HWND 에서 UIA 트리가 비어있는지, 부모로 올라가야 하는지 확인

### 6.4 Python-UIAutomation-for-Windows 비교 테스트

- 별도 스크립트 (scripts/compare_uia_libs.py) 작성
- 같은 좌표에서 pywinauto vs yinkaisheng 라이브러리가 다른 element 를 반환하는지 비교
- Chrome 케이스에서 후자가 더 잘 잡으면 picker 의 fallback 으로 추가 검토

### 6.5 회귀 테스트 보강

- test_core.py 에 "Chrome handshake 함수 존재" 정적 테스트 추가
- 가능하면 Chrome 을 띄우지 않아도 통과하는 mock 테스트

### 6.6 시간 남으면

- Hover modifier (Ctrl-hold) 옵션 추가 (사용자 설정)
- `_force_topmost()` 를 매 tick 호출하도록 변경 (작업표시줄 위로 올라오기)

---

## 7. 참고 링크 (검색해서 모은 출처)

### Chrome 접근성
- chromium.googlesource.com/chromium/src/+/refs/heads/main/docs/accessibility/
- chromium.googlesource.com — `BrowserAccessibilityManagerWin`
- chrome://accessibility (브라우저 내부 페이지)
- "How Chrome Accessibility Works" - Google Developers 블로그

### Microsoft UIA
- learn.microsoft.com/en-us/windows/win32/winauto/entry-uiauto-win32
- learn.microsoft.com — IUIAutomation::ElementFromPoint
- github.com/microsoft/accessibility-insights-windows

### Python 라이브러리
- pywinauto.readthedocs.io
- github.com/yinkaisheng/Python-UIAutomation-for-Windows
- github.com/FlaUI/FlaUInspect (참고용 .NET 구현)

### RPA 업계
- UIPath docs: "UI Automation activities — Selectors"
- Robocorp docs: "Hybrid Image / OCR / UIA approach"

---

## 8. 메모

- **하드코딩 금지 원칙** (사용자 강조): 위 §6.1 의 Chrome handshake 도 클래스 이름으로 분기하면 일종의 하드코딩이지만, 이건 "Chrome 의 documented behavior 에 맞춤" 이지 "특정 사이트/특정 앱 좌표" 가 아니므로 허용 범위. 다른 브라우저 (Edge 도 Chromium 이라 동일, Firefox 는 다른 방식) 도 같이 케이스로 다루는 형태로.
- **F3 정책**: 현재 "leak 없음" 우선. submenu 추적은 향후 Ctrl-hold 모드로 별도 제공하는 방향.
- **테스트 가능성**: Chrome 핸드셰이크는 GUI 가 필요해서 단위 테스트 어려움 → 정적 검사 (함수 존재 + WM_GETOBJECT 인자 값) 까지만 자동화하고 수동 검증 의존.

---

내일 시작점: **§0 의 kIdCustom=1 시도부터**.
