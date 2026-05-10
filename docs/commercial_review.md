# ohdo 상업적 경쟁력 검토 (2026-05-08, 5/9 글로벌 타깃 갱신)

> **이 문서의 목적**: ohdo 가 SaaS 시장에서 경쟁력 있는 제품인지 솔직하게 검토. 결과물은 "지금 즉시 행동" 이 아니라 **Phase 2 (SaaS 백엔드) 진입 직전 GO/NO-GO 게이트** 에서 다시 읽도록 보관.
>
> **2026-05-09 사용자 결정 반영**: 시장 타깃 = **글로벌 + 한국 dual-locale** (한국 niche 단독 아님). §3 차별성 / §5 SAM / §7 게이트 동기화 갱신.
>
> **언제 다시 읽어야 하는가** (트리거):
> - Phase 1 (저장소 추상화 + UI-Core 분리) 완료 시점 — Phase 2 진입 직전
> - Anthropic Computer Use 가 메이저 업데이트 (예: 5x 속도 / 비용 1/10) 시
> - ohdo 사용자 규모가 의미있는 단계 (GitHub Stars 500+, 유료 의향 5명+) 도달 시
> - 또는 6개월 이상 commit 진행 후 한 번 (잊고 paddling 만 하지 않게)

---

## TL;DR

**상업적 경쟁력**: 정직하게 **약-중**. Computer Use 위협 + 1인 개발 한계 + 작은 시장.

**그러나 zero 는 아님**: 코드 산출물 + 한국어 + offline 의 3 차별성 조합은 niche 에서 valid.

**1-2년 내 ARR 현실 추정**: 비관 $0-$10K / 중립 $10K-$50K / 낙관 $100K-$300K.

**권장**: Phase 1 까지는 어느 시나리오든 진행 가치 있음. Phase 2 (SaaS) 직전 시장 검증 게이트 통과해야 진입.

---

## 1. ohdo 가 실제로 뭔가 (정의 정확히)

> "AI 가 사용자 요청을 **읽을 수 있고, 수정할 수 있고, 독립 실행 가능한 Python 코드**로 변환해주는 Windows 자동화 툴. 데스크톱 앱이 step 카드로 워크플로우 빌드. element picker 로 시각 + 코드 다리. 결과물 = pywinauto/pyautogui/Selenium Python 스크립트."

핵심 메카닉: **"AI 가 코드를 만든다. 코드가 산출물이다."** — UiPath 의 XAML 도, Computer Use 의 vision call sequence 도 아닌 **plain Python**.

---

## 2. 경쟁 환경 (정직하게)

### A. Claude Computer Use (Anthropic, 2024-10)
| 강점 | 약점 |
|---|---|
| 셋업 0 (API 키만) | API 비용 (매 step 마다 vision call) |
| Vision 기반 → selector 안 깨짐, 어떤 앱이든 동작 | 산출물 없음 (재실행 시 매번 AI 호출 → $$$ 누적) |
| Anthropic 백, 매주 개선 | 결정론적 X (같은 task 다른 경로) |
| 데스크톱/브라우저/모든 OS | 디버깅 가시성 낮음 |
| | 컴플라이언스 거부 가능 (vendor lock-in + 화면 캡처 외부 송출) |

**Computer Use 가 "그냥 시키면 알아서 한다" 영역에서는 ohdo 가 빠르게 obsolete 될 가능성 높음.**

### B. UiPath / Automation Anywhere / Microsoft Power Automate
| 강점 | 약점 |
|---|---|
| 엔터프라이즈 레퍼런스 풍부 (Fortune 500 다수) | 라이선스 비쌈 (per-bot/per-user $1K-$5K/yr) |
| Orchestrator (queue, retry, audit, schedule) | Lock-in 강함, 떠나기 어려움 |
| OCR / Document Understanding 내장 | 학습 곡선 가파름 |
| 비개발자도 사용 (low-code) | 코드 산출물 없음, 버전 관리 어려움 |

**ohdo 가 같은 시장에서 정면 경쟁은 불가능. 1인 개발팀 vs 1만명 엔지니어링 조직.**

### C. browser-use, OpenInterpreter, Skyvern (비슷한 코드 생성 AI 에이전트)
| | 차이 |
|---|---|
| browser-use | 브라우저 한정, 라이브러리, 코드 자체는 라이브러리 내부 |
| OpenInterpreter | 범용 (서버/스크립팅), 데스크톱 GUI 자동화 약함 |
| Skyvern | 웹 자동화 SaaS, 엔터프라이즈향 |

**가장 가까운 경쟁자는 OpenInterpreter + browser-use 조합.** 둘 다 오픈소스, 활발히 개발 중.

### D. AutoIt / SikuliX (legacy)
- AI 없음. 2010년대 도구. 사용자 줄어드는 중. 비교 의미 적음.

---

## 3. ohdo 의 실제 차별점 (honest)

| 항목 | 차별성 | 시장 가치 |
|---|---|---|
| **Plain Python 산출물** | 사용자가 읽고/수정하고/git 에 커밋하고/공유 가능. UiPath XAML, Computer Use action log 와 다름 | 🟢 개발자 타깃에서 진짜 가치 |
| **Step-by-step iteration** | AI 가 한 번에 다 만드는 게 아니라 step 카드로 사용자가 빌드 + 검증 + 재실행 | 🟡 OpenInterpreter 도 비슷한 방향, 선점 효과 약함 |
| **Element picker** | 화면 클릭으로 selector 코드 자동 생성. visual + code 다리 | 🟡 UiPath Studio 의 핵심 UX 와 동일 발상. 차별성 약 |
| **Local-first / offline** | AI 호출 외 데이터 외부 송출 0. 컴플라이언스 민감 환경 친화 | 🟢 글로벌 dev 환경 + 한국 공공/금융/의료 양쪽 의미 있음 |
| **i18n (영어 + 한국어) dual-locale** | UiPath/browser-use 등 글로벌 도구는 영어 단일 보편 | 🟡 한국 niche 진입 장벽 (작음) + 글로벌 i18n 자산 (작음) — *2026-05-09 한국 niche 단독 → dual-locale 로 재포지셔닝, 차별성 🟢→🟡* |
| **AGPL 오픈소스** | UiPath 못 가는 곳, dev 신뢰 | 🟡 양날의 검 (수익화 어려움) |

---

## 4. ohdo 의 실제 약점

| 약점 | 영향 |
|---|---|
| **Windows 전용** | Mac/Linux 데스크톱 = no go. 글로벌 시장 절반 못 봄 |
| **Selector 취약성** | pywinauto/auto_id 가 UI 업데이트되면 깨짐. Computer Use vision 이 robust |
| **AI 코드 품질 불안정** | 5/6 까지의 prompt 강화 18 fix 가 증거. 매주 회귀 가능 |
| **1인 개발** | Anthropic, UiPath 와 개발 속도 차이 100배 |
| **Python 읽을 수 있는 사용자만** | 비개발자 = 못 씀. 시장 작음 |
| **Computer Use API 가 6-12 개월 안에 ohdo 의 90% 기능 cover 가능성** | 가장 큰 실존 위험 |

---

## 5. 솔직한 commercial 진단

### 정직한 SAM (Serviceable Available Market) — *2026-05-09 글로벌 우선으로 anchor 변경*
- **글로벌 dev-focused RPA**: ~50-100M USD/yr (작음, 그러나 Cursor/Cody 같은 dev tool 가능성) — **primary anchor**
- **한국 dev RPA**: ~5-10M USD/yr (매우 작음, 그러나 경쟁 적음) — secondary, dual-locale 의 부수 효과
- 비개발자 RPA = ohdo 진입 불가 (UiPath 영역)

### 1-2년 내 ARR 현실 추정 — *글로벌 SAM anchor 기준 상향*
- 비관: $0-$15K (개인 사용자 GitHub stars 만, 영어 traction 없을 시)
- 중립: $20K-$80K (글로벌 dev OSS traction + 한국 niche + 일부 SaaS 유료)
- 낙관: $150K-$500K (영어 + 한국 dual 컨텐츠 → Show HN/Reddit 노출 → 컨설팅/엔터프라이즈)
- 비교: UiPath ARR $1.4B, browser-use Series A $17M raised

### 가장 큰 위협 (3개)
1. **Computer Use 의 발전 속도** — 매 분기 capability 두 배. ohdo 의 selector RPA 는 1-2년 내 obsolete 가능
2. **개발자가 ohdo 대신 ChatGPT 에 그냥 "pywinauto 코드 짜줘" 하고 끝** — 사용자가 직접 LLM + IDE 조합으로 해결
3. **비개발자 진입 장벽** — UiPath/Power Automate 의 영역. ohdo 가 못 들어감

---

## 6. 전략 옵션 (3가지)

### 옵션 A: 현재 방향 유지 (개발자 niche)
- "Windows 자동화의 Cursor" — 코드 산출물 강점 극대화
- Phase 1 (저장소 추상화) 까지는 의미 있음
- Phase 2 (SaaS 백엔드) 는 **5-10 명 paying customer 검증 후** 진입
- 한국 dev 커뮤니티 + 글로벌 OSS 두 트랙
- 현실적 ARR: $20K-$100K 1-2년

### 옵션 B: Computer Use 통합 (포지션 재정의)
- "Computer Use 가 한 일을 inspectable Python 으로 캡처/생성"
- value prop: "AI 가 한 번 시연 → 결정론적 코드로 변환 → 천 번 실행"
- 차별성 명확: agent observability + code generation
- 위험: pivot 필요, 현재 코드 일부 재사용에 그침

### 옵션 C: 학습/포트폴리오 프로젝트로 인정
- 상업화 기대 낮춤
- 오픈소스 quality 위주
- Phase 2+ SaaS 작업 stop, 대신 다른 commercial 프로젝트 시작
- 현재까지 작업한 코드/handoff/Phase 0 인프라 = 본인 dev portfolio 자산

---

## 7. 권장 (2026-05-08 시점)

**지금 멈추거나 큰 pivot 할 필요는 없지만, Phase 2 (SaaS 백엔드) 진입 전 시장 검증이 중요.**

### 근거
1. **Phase 0/1 까지는 commercial outcome 무관하게 가치 있음** — 코드 위생 표준 + 저장소 추상화는 어느 방향이든 자산.
2. **Computer Use 위협은 실재** — ohdo 가 살아남으려면 "code artifact" 차별성을 극대화하거나 (옵션 A), Computer Use 와 손잡거나 (옵션 B). 두 길 다 valid.
3. **솔로 개발 한계** — UiPath 정면 경쟁은 무리. 한국 dev niche + global OSS 가 현실적.
4. **상업적 성공 확률은 솔직히 10-25%** — 노력 부족이 아니라 시장 구조 (1인 vs Anthropic).

### Phase 2 진입 GO/NO-GO 게이트 (제안) — *2026-05-09 글로벌 dual-locale 반영*

다음 모두 충족 시 → GO (Phase 2 SaaS 백엔드 진입):
- [ ] GitHub Stars 500+ (영어 README 기준 글로벌 노출)
- [ ] Discord/이메일/X DM "유료여도 쓰겠다" 응답 5명+ (글로벌 + 한국 합산)
- [ ] **콘텐츠 mix** — 영어 콘텐츠 (Show HN / Reddit r/Python / dev.to / X 의 dev 인플루언서 mention) **AND** 한국어 콘텐츠 (블로그 3+ post 또는 유튜브 1+ 영상). 한 쪽만 충족 시는 게이트 약화 — 글로벌 trajectory 보려면 양쪽 traction 필요
- [ ] Computer Use 가 Windows 데스크톱 앱 (UWP/Win32) 자동화에서 ohdo 보다 명백히 우월하지 *않을* 것

조건 미충족 시:
- 옵션 B (Computer Use 어댑터 통합) PoC 진입 — 1~2주 spike 로 검증
- 또는 옵션 C (포트폴리오로 재정의) — Phase 2 stop, 다른 프로젝트 시작

---

## 8. 검토 시 즉시 후보 (참고용)

이 문서를 다시 읽을 때 다음 후보들 우선순위 재평가 필요:

| 후보 | 상업적 가치 (5/8 시점) | Phase 2 진입 직전 재평가 필요 |
|---|---|---|
| Phase 1 진입 (저장소 추상화) | 🟢 높음 (어느 방향이든 자산) | 완료됐는지 |
| §7-10 AI 자동 에러 복구 | 🟡 차별성 중간 | 사용자 데이터 봐야 결정 |
| structlog/Sentry | 🟡 SaaS 가는 길 필수 | Phase 2 진입 직전 |
| Computer Use 어댑터 PoC | 🟢 옵션 B 검증 + 차별성 ↑ | **권장** |
| 한국어 콘텐츠 (블로그/유튜브) | 🟢 시장 검증 시작 | 코드 작업 외, 사용자 직접 |

---

## 9. 변경 로그

| 날짜 | 변경 | 작성자 |
|---|---|---|
| 2026-05-08 | 초안 작성 — Phase 0 (sub-phase 5) 완료 직후 사용자 요청으로 상업적 경쟁력 검토 | Claude (사용자 합의 후 보관) |
| 2026-05-09 | 시장 타깃 글로벌 확장 결정 반영 — §3 "한국어 UI" 차별성 → "i18n dual-locale" 로 재포지셔닝 (🟢→🟡), §5 SAM anchor 글로벌로 변경 + ARR 추정 상향, §7 GO/NO-GO 게이트 "한국어 콘텐츠 5+" → "영어 + 한국어 mix" 재정의 | Claude (사용자 결정 동기화) |
