# CDP attach 기능 고려사항

> **상태**: **deferred** (구현 보류) — 2026-04-28
> **다시 검토할 시점**: 사용자가 "기존 띄워둔 브라우저 자동화" 시나리오를 자주 만나거나, picker 정밀도 차이가 작업에 거슬리는 시점

이 문서는 ohdo 의 웹 자동화 전략과 CDP (Chrome DevTools Protocol) attach 기능의 향후 구현 여부 결정을 위한 종합 정리입니다. 직접 구현하기 전 다시 읽어 맥락을 잡으세요.

---

## 1. 웹 자동화의 두 시나리오

| | A. Selenium 자체 브라우저 | B. 기존 브라우저 attach |
|---|---|---|
| **방식** | `webdriver.Chrome(options=Options())` | `options.add_experimental_option('debuggerAddress', 'localhost:9222')` |
| **사용자 셋업** | 없음 | Chrome 을 `--remote-debugging-port=9222` 로 시작해야 함 |
| **제어 가능성** | ⭐ 풍부 (DOM, XPath, JS, find_element 모두 OK) | ⭐ 풍부 (DOM, XPath, JS, find_element 모두 OK) |
| **컨텍스트** | 새 깨끗한 Chrome (사용자 세션/쿠키 없음) | 사용자가 보던 그 Chrome (탭, 로그인, 쿠키 그대로) |
| **picker 와의 매칭** | picker 가 잡은 element 와 별개의 Chrome | picker 가 잡은 그 element 를 그대로 조작 |
| **대표 워크플로우** | "google 가서 X 검색" 식의 새 자동화 | "지금 이 페이지의 이 버튼 클릭" |

**핵심 통찰**:
- 시나리오 A 는 **CDP 셋업 불필요** (Selenium 의 chromedriver 가 자체적으로 debug port 열어 띄움)
- 시나리오 B 만 CDP attach 필수
- picker 의 본질 ("지금 이 element") 은 시나리오 B 에 가까움 — 하지만 시나리오 A 도 picker 없이 chat 만으로 충분히 가능

---

## 2. ohdo 의 현재 동작 (직전 fix 적용 후)

[core/win_inspector.py:should_use_selenium](../core/win_inspector.py) 라우팅 매트릭스:

| browser? | CDP 응답? | tagName? | 라우팅 | 코드 생성 |
|---|---|---|---|---|
| No | - | - | desktop | pywinauto + WM 메시지 클릭 |
| Yes | Yes | 있음 | **Selenium DOM** | CDP attach + 캡처된 절대 XPath/HTML 정보 |
| Yes | Yes | 없음 | desktop (chrome UI) | pywinauto + click_input (탭/메뉴) |
| Yes | No | - | desktop | pywinauto + **pyautogui PRIMARY** (HTML 콘텐츠도 OS 레벨 클릭) |

**원칙 (하드코딩 0)**: picker 가 수집하는 정보 (`browser_type`, `dom_context.cdp_available`, `dom_context.tagName`) 만으로 결정. 브라우저별 클래스명/control_type 검사 없음.

---

## 3. CDP 활성화의 UX 마찰점

이미 떠있는 Chrome 에 CDP 를 나중에 붙일 수 없음 — **시작 옵션**이라 재시작 필수. 사용자 입장에서 부담:
- 작업 중인 탭들 (로그인 세션, 진행 중 폼, 열어둔 자료) 다 닫아야 함
- 매 RPA 세션마다 반복하기 어려움

이게 CDP attach 기능 구현 보류의 주된 이유.

---

## 4. CDP 활성화 옵션 (사용자가 직접 가능, ohdo 코드 변경 불필요)

### 옵션 1: Chrome 단축키 영구 수정 (가장 매끄러움)
바탕화면/시작메뉴 Chrome 단축키 우클릭 → 속성 → 대상 끝에:
```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```
→ 이후 모든 Chrome 실행 시 자동으로 debug port 활성. 평소 브라우징에 거의 영향 없음.

**Trade-off**: localhost 의 다른 프로세스가 Chrome 을 조작 가능 (외부 인터넷은 무관). 보안에 민감하면 옵션 2 권장.

### 옵션 2: RPA 전용 Chrome 인스턴스 분리
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="C:\ChromeRPA"
```
→ 두 Chrome 인스턴스 공존. 자동화는 RPA 인스턴스에, 일반 브라우징은 메인 Chrome.

**Trade-off**: 세션/쿠키 분리. RPA 대상 사이트는 별도 로그인 필요.

### 옵션 3: ohdo 가 재시작 도와주기 (미구현, 후속 검토)
ohdo 다이얼로그에서 "재시작 도와줄까요?" → Chrome 종료 → debug port 옵션으로 재시작 → 세션 복원 (Chrome 의 마지막 세션 복원 기능 활용).

**복잡성**: 작업 중인 폼 데이터 손실 가능, 사용자 동의 흐름 필요. 일회성 셋업 (옵션 1/2) 보다 매번 발동되는 마찰.

---

## 5. 추천 사용자 워크플로우 (현 상태)

### 시나리오별 권장
| 의도 | 도구 | 비고 |
|---|---|---|
| 새 사이트 자동화 (URL 부터 시작) | chat 에 직접 요청, picker 안 씀 | 가장 간단, OLD 프로젝트에서 잘 작동했던 패턴 |
| 데스크톱 앱 자동화 | picker → pywinauto | NEW 도 OLD 도 잘 작동 |
| 기존 Chrome 의 element 조작 | picker → 현재 NEW 의 fallback (pywinauto + pyautogui) | 정확도는 보통, **CDP 활성화 시 정밀도 대폭 향상** |
| 정밀 웹 자동화 (XPath, JS, DOM) | Chrome 을 옵션 1/2 로 띄움 → picker | NEW 가 OLD 보다 우월한 영역 |

### 일상적 RPA 사용자에게는
**옵션 1** (Chrome 단축키 수정) 이 가장 마찰 적음. 한 번만 셋업하면 picker 가 CDP 자동 연결, 정밀 자동화 항상 가능.

---

## 6. CDP attach 기능 구현을 다시 검토할 시점

다음 신호 중 둘 이상이 나타나면 옵션 3 또는 다른 통합 방식을 검토:

- [ ] 사용자가 "기존 Chrome 자동화" 를 일상적으로 자주 시도 (옵션 1/2 셋업도 부담스러워함)
- [ ] picker 의 fallback (pywinauto + pyautogui) 정확도가 작업에 자주 영향 줌
- [ ] CDP 활성 상태 사용자 비율이 낮아 Selenium DOM 경로가 거의 안 발동 (= XPath 자동화 가치 미실현)
- [ ] 1회 CDP 안내 다이얼로그가 자주 나타나 UX 거슬림 (현재는 suppressible)

이 신호들이 모이면 옵션 3 (ohdo 가 Chrome 재시작 자동화) 또는 더 우아한 통합 방안 (예: Chrome 확장 프로그램으로 항상 debug 포트 노출) 을 설계.

---

## 7. 관련 코드 위치 (구현 시 참고)

| 파일 | 역할 |
|---|---|
| [ui/element_picker.py:1440](../ui/element_picker.py) `_capture_dom_context` | CDP 9222/9223/9224 시도 → DOM 정보 수집 (XPath, attributes, outerHTML 등) |
| [core/win_inspector.py:`should_use_selenium`](../core/win_inspector.py) | 라우팅 매트릭스 단일 진실 |
| [core/win_inspector.py:`_get_browser_element_info_text`](../core/win_inspector.py) | Selenium DOM 경로 코드 생성 (CDP 활성 시) |
| [core/win_inspector.py:`_get_desktop_element_info_text`](../core/win_inspector.py) | desktop path 코드 생성. `is_browser_process` 분기로 pyautogui PRIMARY |
| [ui/main_window.py:`_maybe_show_cdp_hint`](../ui/main_window.py) | 1회 CDP 안내 다이얼로그 (suppressible) |

---

## 8. 결론 요약 (한 줄)

> **CDP attach 는 "기존 띄워둔 브라우저의 그 페이지를 정밀 조작" 시나리오에서만 유의미.** 일반적인 새 자동화는 Selenium 자체 브라우저로 충분. CDP 활성화는 사용자가 옵션 1/2 로 직접 가능하므로 ohdo 가 자동화하는 기능 구현은 **deferred**.
