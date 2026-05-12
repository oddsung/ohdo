# ohdo.ai 장기 로드맵

> PySide6 데스크톱 RPA 도구 ohdo.ai 를 오픈소스 커뮤니티 기반 SaaS 로 확장하기 위한 단계적 계획입니다.
>
> 이 문서는 **Living Document** 입니다. 계획·아키텍처·우선순위 변경 시 반드시 함께 수정하고, 변경 이유를 §10 변경 로그에 한 줄로 남기세요.

## 0. 문서 메타

- **마지막 업데이트**: 2026-05-12 (**Phase 0 + Phase 1 모두 100% 완료**. Phase 1 sub-task 2 Chunk B (ui/ legacy 정리) 5/9 마무리 → KPI "ui/ 폴더에서 banned core 직접 import 0건" 충족. Phase 2 진입은 [docs/commercial_review.md](commercial_review.md) GO/NO-GO 게이트 통과 후 결정. **5/9~5/10 Phase 1.8 OpenAI 호환 (DeepSeek) 등록 + 코드 생성 품질 루프 11 unit — handoff §16 참조. baseline 85→96**. **5/12 PySide6 (LGPL) 메인 전환 완료 — handoff §19/§20 — 이전 PyQt6 코드는 legacy_pyqt6/ 보관**)
- **Owner**: @toytiger (dohahado22@gmail.com)
- **타깃 시장**: B2C 개인 개발자 (**글로벌 + 한국 dual-locale**, 오픈코어 전략) — *2026-05-09 사용자 결정으로 한국 niche → 글로벌 우선 + 한국 동시 진행으로 확장*
- **관련 문서**:
  - [CLAUDE.md](../CLAUDE.md) — 프로젝트 지침
  - `docs/ARCHITECTURE.md` — 아직 미작성 (Phase 1 시작 시 작성)
  - `docs/AGENT_PROTOCOL.md` — 아직 미작성 (Phase 2 진입 시 작성)

---

## 1. 비전과 포지셔닝

**비전**: "자연어로 대화하며 실제 Windows 앱과 웹을 자동화하는, 개발자 친화 오픈코어 RPA."

**세 축의 차별화**:
1. **AI 네이티브** — 단계별 대화형으로 코드를 쌓아가며 수동 편집과 AI 생성이 공존. UiPath/Automation Anywhere 의 드래그앤드롭 모델과 다름.
2. **개발자 친화** — 생성물이 순수 Python 코드. Git 에 커밋 가능, VSCode 에서 편집 가능, 타 시스템에 쉽게 이식 가능. Zapier/Make 의 블랙박스 워크플로우와 다름.
3. **실제 Windows 앱 제어** — 브라우저만 자동화하는 도구와 달리 사내 ERP, 레거시 데스크톱 앱, UWP 앱 등 모든 Windows 표면을 건드림.

**라이선스 전략 (오픈코어)** — *2026-05-05 사용자 결정 확정*:
- 데스크톱 앱 + 코어 라이브러리: **AGPL-3.0** (커뮤니티 확산 + 기업 fork 방지)
- 클라우드 서비스 + Pro 기능: 상업 라이선스 (SaaS 구독)
- **유료/무료 라인 긋기는 Phase 2 진입 시점에 결정** (현 단계 v1.0 은 100% AGPL-3.0 무료, SaaS 코드 미존재)

**타깃 시장**: B2C 개인 개발자 (**글로벌 + 한국 dual-locale**, *2026-05-09 사용자 결정 확정*). 오픈소스 커뮤니티를 통해 "개발자에게 사랑받는 도구" 로 포지셔닝한 뒤, 자연스럽게 기업 도입으로 확장. 영어 우선 + 한국어 동시 지원 (i18n) — 글로벌 SAM (50-100M USD) 진입 + 한국 niche 보호막은 약하지만 dual-locale 자체가 작은 차별성.

---

## 2. 아키텍처 권장안: 하이브리드 (에이전트 + 클라우드 컨트롤 플레인)

### 2.1 왜 완전 웹 SaaS 는 불가능한가

`pywinauto`, `pyautogui`, `uiautomation`, `ctypes.windll` 은 **실제 Windows 세션의 HWND 접근과 인풋 포커스**를 필요로 합니다. 클라우드의 headless Windows VM 에서는 고객이 자동화하려는 사내 ERP, 설치된 브라우저 프로파일, 로컬 앱을 제어할 수 없습니다.

따라서 **하이브리드 모델**이 유일한 합리적 선택입니다.

### 2.2 구조

```
┌─────────────────────────┐        ┌──────────────────────────┐
│  고객 Windows PC        │ HTTPS  │  Cloud Control Plane     │
│  ┌───────────────────┐  │◀──────▶│  ┌────────────────────┐  │
│  │ ohdo Agent        │  │  WSS   │  │ FastAPI (API)      │  │
│  │ (경량 Python)     │  │        │  │ PostgreSQL         │  │
│  │ - workflow_engine │  │        │  │ Redis + ARQ        │  │
│  │ - sandbox         │  │        │  │ S3/R2 (캡처/로그)  │  │
│  │ - adapters        │  │        │  │ Stripe/Toss        │  │
│  │ - agent bridge    │  │        │  └────────────────────┘  │
│  └───────────────────┘  │        │  ┌────────────────────┐  │
│  (PySide6 UI 는 선택)   │        │  │ Next.js 웹 대시보드│  │
└─────────────────────────┘        │  └────────────────────┘  │
                                   └──────────────────────────┘
```

### 2.3 역할 분리

| 계층 | 위치 | 책임 | 재사용 대상 |
|---|---|---|---|
| Agent | 고객 PC | RPA 실행, 스크린 캡처, pywinauto 호출 | `core/workflow_engine.py`, `core/win_inspector.py` |
| Control Plane | 클라우드 | 세션/스텝 저장, AI 프록시, 스케줄러, 결제 | `core/session_manager.py`, `core/prompt_builder.py` 서버 이식 |
| Web UI | 브라우저 | 편집·모니터링·관리 | 신규 작성 (Next.js) |
| Desktop App | 고객 PC | 풀 UI 오프라인 사용 | 현 `ui/main_window.py` 유지 |

### 2.4 두 가지 배포 형태 병행

1. **OSS 데스크톱 앱** (현재 형태 유지): 풀 UI, 오프라인 사용 가능 → 커뮤니티 확산 채널
2. **경량 Agent 트레이 앱**: 웹에서 편집, 로컬에서 실행만 → SaaS 기본 배포 형태

두 형태가 동일한 `core/` 모듈을 공유하도록 하는 것이 Phase 1 의 핵심입니다.

---

## 3. 단계별 마일스톤

### Phase 0: OSS 안정화 (1~2개월)

현 코드베이스를 GitHub 공개 가능한 수준으로 다듬고, 이후 모든 단계의 기반이 될 개발·테스트 인프라 구축.

- [x] `pyproject.toml` + **`uv`** 도입 (`requirements.txt` 병행 유지) — 2026-05-07
- [x] `.devcontainer/devcontainer.json` (Python 3.12 + uv + Qt deps) — 2026-05-08. `docker-compose.dev.yml` 은 Phase 2 backend 진입 시점에 추가 예정.
- [x] `pre-commit` + `ruff` (lint + format, black 대체) — 2026-05-07. **mypy 는 Phase 1 의 type hint 작업과 묶음** (legacy 30K 라인 UI 코드에 strict mypy 시 수천 에러).
- [x] GitHub Actions CI 매트릭스 — 2026-05-08:
  - `lint` (ubuntu-latest): ruff check + format check
  - `test-ubuntu`: core + scenarios (Qt deps + offscreen)
  - `test-windows`: core + scenarios (pywinauto/pyautogui 의존성 native)
  - **보류**: `ai_integration` (Gemini CLI + API key secret 필요), GUI 자동화 (notepad/calculator/browser)
- [x] `LICENSE` (AGPL-3.0) — 2026-05-07. SPDX 헤더 113 .py 파일 일괄 (5/8). `CONTRIBUTING.md` 은 외부 기여자 진입 시점에 추가.
- [ ] 구조화 로깅: `structlog` 도입, JSON 포맷, `logs/` 로테이션 — Phase 0 후반 별도 작업
- [ ] Sentry SDK opt-in 통합 — Phase 0 후반 별도 작업

**파일 수준 변경**:
- 신규: `pyproject.toml`, `.devcontainer/`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml`
- 수정: `main.py` 상단 `logging.config.dictConfig` 호출
- 수정: `core/*` 모든 모듈 `from __future__ import annotations` + 타입 힌트 완성

**KPI**: CI 그린 빌드 95%+, GitHub Stars 100+, 이슈 응답 SLA 48시간 이내.

---

### Phase 1: 핵심 리팩토링 — 저장소 추상화 & UI-Core 분리 (2~3개월)

동일한 `core/` 가 데스크톱 앱과 향후 백엔드 서버에서 모두 작동하도록 분리. **이 단계가 가장 중요하며, 건너뛰면 Phase 2~5 가 재작성으로 전락합니다.**

#### (1) 저장소 추상화 `core/storage/`
현 `core/session_manager.py` 는 `Path("data/sessions/")` 에 직접 JSON 을 씁니다. 인터페이스 뒤로 숨깁니다.

```
core/storage/
  __init__.py
  base.py          # SessionRepository(ABC), CaptureStore(ABC)
  local_json.py    # 현 동작 유지 (데스크톱 기본값)
  postgres.py      # Phase 2 에서 추가
  s3.py            # 캡처 이미지 전용
```

#### (2) UI-Core 완전 분리
`ui/main_window.py` (1,649줄) 의 직접 소유 → **AppService 계층** 도입.

```python
# core/app_service.py
class AppService:
    def __init__(self, session_repo, ai_manager, workflow_engine, event_bus): ...
    async def run_step(self, session_id, step_id) -> StepResult: ...
    async def generate_step(self, session_id, user_request) -> Step: ...
```

- UI 는 오직 `AppService` + `EventBus` (Qt Signal 또는 asyncio Queue) 만 의존
- `ui/main_window.py` 를 600줄 수준으로 축소
- 동일 `AppService` 가 Phase 2 에서 FastAPI 라우터 핸들러로 바로 호출됨

#### (3) Pydantic 모델 승격
`core/models.py` — 현 dataclass (`Session`, `Step`, `Capture` 등) 를 Pydantic v2 모델로 승격. 서버 API 응답 스키마로 재사용.

#### (4) 설정 레이어 분리
`config/settings.json` → `core/config.py` 의 Pydantic `Settings` 모델 + `.env` 병합.

#### (5) Agent 브리지 스켈레톤
```
agent/
  __init__.py
  bridge.py        # 로컬 HTTP/WS 브리지 (지금은 no-op)
  runner.py        # WorkflowEngine 을 감싸 원격 명령 수신
```

**추가 의존성**: `pydantic-settings`, `httpx`, `structlog`

**테스트 전략**: `SessionRepository` 인메모리 구현으로 `test_core.py` 속도 향상. `AppService` 단위 테스트 `tests/test_app_service.py` 추가.

**KPI**: `ui/` 폴더에서 `session_manager`·`workflow_engine`·`ai_engine` 직접 import 0건. `AppService` 커버리지 80%+.

---

### Phase 2: 백엔드 API + Agent 프로토콜 (3~4개월)

클라우드 컨트롤 플레인 MVP. 사용자는 여전히 로컬 PC 에서 실행하지만, 세션·스텝·이력이 서버에 저장되고 GitHub 처럼 공유 가능.

- [ ] 모노레포 구조로 전환
  ```
  ohdo/
  ├── packages/
  │   ├── core/           # 현 core/ 이동 (순수 Python 라이브러리)
  │   ├── desktop/        # 현 ui/ + main.py
  │   ├── agent/          # 경량 트레이 에이전트
  │   ├── backend/        # FastAPI (신규)
  │   └── web/            # Next.js (Phase 3)
  ├── pyproject.toml      # uv workspace
  ├── pnpm-workspace.yaml
  └── .devcontainer/
  ```
- [ ] `packages/backend/`:
  - FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2
  - API v1: `sessions`, `steps`, `executions`, `agents`, `ai_proxy`
  - WebSocket Agent 게이트웨이 `ws/agent_gateway.py`
- [ ] PostgreSQL 스키마: `users`, `sessions`, `steps`, `executions`, `agents`, `ai_keys_encrypted`
- [ ] S3/Cloudflare R2 캡처 이미지 저장 (pre-signed URL)
- [ ] Agent 프로토콜 `docs/AGENT_PROTOCOL.md` 작성:
  - WebSocket 메시지: `agent.connect`, `agent.heartbeat`, `execution.start`, `execution.log`, `execution.result`
  - Agent pull 방식: 서버가 큐에 작업 넣으면 Agent 가 WS 로 수신
- [ ] `agent/` 패키지 완성: `ohdo-agent` CLI (`pipx install ohdo-agent`)
- [ ] AI 호출 서버 프록시: 고객 API 키는 서버에 암호화 저장 (`fernet` + KMS)
- [ ] 하위 호환: 데스크톱 앱은 `storage.local_json` 계속 사용 (오프라인 모드)
- [ ] 마이그레이션 CLI: `ohdo migrate-to-cloud` — 로컬 JSON → 서버 업로드

**기술 스택**: FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, PostgreSQL 16, Redis 7, ARQ, Fly.io/Railway.

**테스트 전략**: `pytest-asyncio` + `httpx.AsyncClient`, `testcontainers-python` 으로 PostgreSQL/Redis 통합 테스트, Agent ↔ Server 프로토콜 계약 테스트.

**KPI**: 클로즈드 베타 100명, Agent 연결 성공률 95%+, API 응답 p95 < 300ms.

---

### Phase 3: 웹 대시보드 (2~3개월)

브라우저에서 세션 편집·모니터링·실행 트리거. PySide6 UI 를 점진적으로 웹으로 이관.

- [ ] `packages/web/` (Next.js 14 App Router, TypeScript, Tailwind, shadcn/ui)
  - 세션 목록/편집 (좌측 스텝 리스트 + 중앙 Monaco 에디터 + 우측 프롬프트/캡처)
  - 실행 모니터 (Agent 상태, 실시간 로그 스트리밍 SSE)
  - 캡처 이미지 뷰어 (S3 pre-signed URL)
- [ ] Monaco Editor 로 생성 코드 편집 (현 `ui/code_viewer.py` 대체)
- [ ] 실시간 통신: 서버 → 웹 = SSE (로그 스트림), 웹 → 서버 = REST
- [ ] "Open in Desktop" 버튼: 커스텀 URL 스킴 `ohdo://session/{id}` 로 데스크톱 앱 열기
- [ ] 프롬프트 템플릿 라이브러리 (B2C 확산 기능)
- [ ] 공유 링크 원클릭 설치: `https://ohdo.ai/i/abc123` → Agent 자동 설치 + 세션 import

**기술 스택**: Next.js 14, TanStack Query, Zustand, Clerk/Supabase Auth (초기).

**테스트 전략**: Playwright E2E (회원가입→세션 생성→Agent 연결→실행), Storybook 컴포넌트 격리.

**KPI**: 월 활성 사용자 500+, 웹 편집 비율 50%+, Discord/커뮤니티 가입자 200+.

---

### Phase 4: 인증·결제·멀티테넌트 (2개월)

상용 SaaS 기본기 완성. B2C 개인 개발자 중심 요금제.

- [ ] 사용자 / 워크스페이스 (개인 기본). 조직은 Team 플랜 도입 시 추가.
- [ ] Row-Level Security: 모든 PostgreSQL 쿼리에 `user_id` 필터 + SQLAlchemy 이벤트 훅
- [ ] 결제: Stripe (해외) + Toss Payments (국내)

**요금제 (B2C 우선)**:

| 플랜 | 대상 | 가격 | 주요 제한 |
|---|---|---|---|
| **Free** | 개인 입문 | $0 | 세션 10개, AI 호출 월 100회, 실행 월 50회 |
| **Pro** | 개인 파워유저 | $19/월 | 무제한 세션·실행, 우선 AI 호출, 스케줄러, 웹훅 |
| **Team** | 소규모 팀 (후순위) | $49/인·월 | 3~20인, 팀 템플릿 공유 (Phase 5 말 또는 수요 기반 도입) |
| **Enterprise** | 대기업 | 연간 계약 | SSO, 온프레 Agent, 감사 로그 (수요 기반) |

- [ ] 사용량 미터링: AI 토큰, 실행 분 단위 — Redis 카운터 + 일별 PostgreSQL 집계
- [ ] 시크릿 관리 `backend/app/secrets/`: KMS + Fernet
- [ ] 개인정보: 캡처 로컬만 저장 토글, 기본값 블러 처리 옵션

**KPI**: Free → Pro 전환율 3%+, MRR $5,000, 월간 이탈률 5% 이하.

---

### Phase 5: 커뮤니티·마켓플레이스·엔터프라이즈 (이후)

B2C 우선 재배열. 마켓플레이스·템플릿 공유를 SSO/엔터프라이즈보다 먼저.

**우선순위 재배열 (B2C 기반)**:

1. **템플릿 라이브러리** — 공개 템플릿 (예: "네이버 스마트스토어 주문 수집"), private 템플릿
2. **마켓플레이스** — 검증된 개발자가 유료 템플릿 판매, 수수료 20~30%
3. **공유 링크 원클릭 설치** — Phase 3 에서 기초 구현, Phase 5 에서 확산 기능화
4. **스케줄러 / 예약 실행** — APScheduler → Agent 디스패치. CRON + 조건부 트리거
5. **웹훅 / API 트리거** — `POST /v1/trigger/{token}` → 세션 실행. Zapier/Make 커넥터
6. **Git 통합** — 세션을 `.ohdo/` YAML+Python 파일로 직렬화, GitHub 연동
7. **실행 이력 분석 대시보드** — 성공률, 평균 실행 시간, 실패 상위 원인 (AI 요약)
8. **자연어 → 멀티스텝 자동 생성** — Tool-use / plan-and-execute. 차별화 R&D 과제
9. **멀티 AI 엔진 비용 최적화** — 스텝 난이도 자동 분류, Haiku/Gemini Flash ↔ Opus 자동 라우팅
10. **크로스 플랫폼** — `core/inspector/` (win/mac/linux). macOS Accessibility API, Linux AT-SPI
11. **모바일 모니터링 앱** (React Native) — 알림·상태 조회·원격 중지. 편집 불가. (낮은 우선순위)
12. **SSO (SAML/OIDC)** — 엔터프라이즈 수요 발생 시 도입 (후순위)

**KPI**: MRR $50,000, 마켓플레이스 유료 템플릿 100개+, Team 플랜 사용자 20+ (수요 기반).

---

## 4. 추가 제안 기능 우선순위 매트릭스

| 기능 | 개발 난이도 | 고객 가치 | 권장 Phase | 태그 |
|---|---|---|---|---|
| 프롬프트 템플릿 라이브러리 | 낮음 | 중 | **Phase 3** | B2C 핵심 확산 |
| 원클릭 설치 링크 | 낮음 | 높음 | **Phase 3~5** | B2C 핵심 확산 |
| 템플릿 공유 (private) | 낮음 | 중 | **Phase 5 초반** | B2C 핵심 확산 |
| 공개 마켓플레이스 | 높음 (심사/결제) | 중장기 높음 | Phase 5 중반 | B2C 핵심 확산 |
| 스케줄링/예약 실행 | 중 | 높음 | Phase 5 | |
| 시크릿 관리 | 중 | 높음 (보안 필수) | Phase 4 | |
| 실행 이력 대시보드 | 낮음 | 중 | Phase 3~4 | |
| 웹훅/API 트리거 | 낮음 | 높음 (통합 경로) | Phase 4 말 | |
| 멀티 AI + 비용 최적화 | 중 | 높음 | Phase 5 | |
| Git 통합 | 중 | 니치 고가치 | Phase 5 | |
| 자연어 → 멀티스텝 | 높음 | 매우 높음 (차별화) | Phase 5 R&D | |
| 크로스 플랫폼 (mac/linux) | 높음 | 중 | Phase 5 | |
| SSO | 중 | 엔터프라이즈 한정 | Phase 5 후순위 | 엔터프라이즈 수요 기반 |
| 모바일 앱 | 높음 | 낮음 | 보류 | |

**조언**: 1인~초기 3인 팀에게 모바일 앱·SSO·마켓플레이스 심사 체계는 시간 블랙홀입니다. 대신 **프롬프트 템플릿 + 원클릭 설치**는 Phase 3 에 저비용 고효과로 끼워넣으세요.

---

## 5. 리스크와 대응

### 5.1 기술 리스크

- **고객 PC 코드 실행 보안**: 생성 코드가 의도치 않게 파일을 삭제할 수 있음
  - 대응: `CodeSandbox` 강화 — AST 파서로 `shutil.rmtree`, `os.remove`, `subprocess` 등 위험 호출을 실행 전 탐지·승인. 화이트리스트 import 모드 옵션.
- **AI 비결정성**: 같은 프롬프트에 다른 코드 생성
  - 대응: 스텝별 코드 스냅샷, 승인된 코드 잠금 기능, `temperature=0` 옵션.
- **Agent 버전 파편화**: 구버전 Agent 사용자
  - 대응: 자동 업데이트 (Squirrel/Sparkle 유사), 서버에서 버전 호환성 체크, 구 버전 강제 deprecation 정책.
- **Windows 전용 TAM 제한**: 개인 개발자 시장은 macOS 비중이 큼
  - 대응: 초기엔 "Windows 기업 자동화" 포지셔닝, Phase 5 에서 크로스 플랫폼.

### 5.2 비즈니스 리스크

- **경쟁자**: UiPath (엔터프라이즈), Automation Anywhere, Make.com, Zapier (웹 전용), n8n (OSS 워크플로우)
  - 차별화 = "AI 네이티브 + 개발자 친화 + 실제 Windows 앱 제어" 세 축 유지
- **1인 번아웃**: Phase 2 진입 시점 (약 6개월 후) 공동창업자 또는 시니어 계약 개발자 영입 권장
- **OSS vs 상용 충돌**: 오픈코어 전략으로 해결. AGPL OSS + Pro 클라우드 기능 분리.

### 5.3 법적 리스크

- **개인정보**: 스크린 캡처에 고객 정보 포함 → K-ISMS/GDPR 대응, 데이터 보관 정책, 삭제권, 지역 선택(EU/US/KR), 기본 블러 옵션
- **RPA 자동화 회색지대**: 대상 서비스 이용약관 위반 가능성 → 약관에 "고객이 자동화 대상의 사용권을 보유함을 보증" 명시
- **AI 생성 코드 저작권**: 서비스 약관에 생성물 소유권 고객 귀속 명시

---

## 6. 단계별 KPI 요약

| Phase | 주요 KPI | 목표치 |
|---|---|---|
| 0 | GitHub Stars, CI 안정성 | 100+, 그린 빌드 95% |
| 1 | AppService 커버리지, UI 결합도 감소 | 80%, `ui/`→`core/` 직접 import 0 |
| 2 | 클로즈드 베타 가입자, Agent 연결 성공률 | 100명, 95%+ |
| 3 | 웹 MAU, 웹 편집 비율, Discord 가입자 | 500, 50%+, 200+ |
| 4 | Free→Pro 전환율, MRR, 이탈률 | 3%+, $5k, 5% 이하 |
| 5 | MRR, 마켓플레이스 유료 템플릿, 공개 템플릿 | $50k, 100개+, 500개+ |

---

## 7. 일관된 개발 환경 제안

### 7.1 GitHub 만으로 충분한가?

**아닙니다.** GitHub 은 소스 동기화만 해결합니다. ohdo 는 (a) Python 3.x + PySide6 + Windows 네이티브 API + (b) 향후 Node.js + PostgreSQL + Redis 가 섞여 **환경 재현**이 본질 과제입니다. 신입 기여자·여러 머신을 오가는 자신의 개발 흐름 모두 환경 설치에 몇 시간~며칠이 걸릴 수 있습니다.

### 7.2 권장 스택 (Phase 0 에 도입)

**레이어 1 — 의존성·빌드**
- `pyproject.toml` + **`uv`** (lockfile: `uv.lock`) — `poetry` 대비 10배 빠르고 Windows 안정적
- Node.js (Phase 3~): `package.json` + `pnpm` (모노레포 효율)
- `mise` — Python/Node 버전 통합 관리 (`.mise.toml`), Windows 지원, `asdf` 대체

**레이어 2 — 에디터·재현 가능 환경**
- `.devcontainer/devcontainer.json` — VS Code + GitHub Codespaces 동일 환경
- **주의**: Windows 자동화는 DevContainer (Linux) 에서 실행 불가 → **2분할 전략**:
  1. **코어 개발 환경** (cross-platform): Codespaces / WSL2 / Mac 에서 `core/`, `backend/`, `web/` 개발. `test_core` + `test_prompt_quality` 실행.
  2. **Windows 자동화 테스트 환경**: 개인 Windows PC 또는 GitHub Actions `windows-latest` 러너에서 `test_ai_integration` / `test_notepad` / `test_calculator` 실행.
- Nix/devbox 는 PySide6 Qt 바인딩 빌드 까다로움 → 현재는 비추천. Phase 2 이후 backend 전용 고려 가능.

**레이어 3 — 품질 자동화**
- `pre-commit`: `ruff` (lint+format, black 대체), `mypy`, `prettier` (TS), `sqlfluff` (SQL)
- GitHub Actions 매트릭스: `[ubuntu-latest × {core, prompt}, windows-latest × {integration}]`
- Dependabot + Renovate (주간)

**레이어 4 — 관측**
- 로컬: `structlog` + Rich 콘솔
- 클라우드 (Phase 2~): Sentry (에러), Grafana Cloud 무료 티어 (메트릭), BetterStack 로그 (초기 무료)

### 7.3 저장소 구조 전환 (Phase 1 말 → Phase 2 시작)

단일 저장소 → **모노레포**:

```
ohdo/
├── packages/
│   ├── core/           # 현 core/ 이동 (순수 Python 라이브러리)
│   ├── desktop/        # 현 ui/ + main.py (PySide6 앱)
│   ├── agent/          # 경량 트레이 에이전트
│   ├── backend/        # FastAPI (Phase 2)
│   └── web/            # Next.js (Phase 3)
├── docs/
├── pyproject.toml      # uv workspace
├── pnpm-workspace.yaml
└── .devcontainer/
```

`core` 를 별도 패키지로 분리하면 desktop/agent/backend 가 동일 버전을 공유.

---

## 8. 체크리스트

### 지금 당장 (향후 1개월)
- [ ] `pyproject.toml` 도입 + `uv` 전환
- [ ] `.devcontainer/` + `pre-commit` + GitHub Actions 매트릭스 CI
- [ ] `core/storage/base.py` 인터페이스 설계 초안 (Phase 1 준비)
- [ ] `LICENSE` 결정 및 추가 (AGPL-3.0)
- [ ] `CONTRIBUTING.md` 작성

### 다음 3개월 (Phase 1)
- [ ] `core/storage/` + `core/app_service.py` 구현
- [ ] `ui/main_window.py` 축소 (~600줄)
- [ ] Pydantic v2 모델로 `session_manager.py` dataclass 승격
- [ ] `agent/` 패키지 스켈레톤
- [ ] 프롬프트 템플릿 라이브러리 초기 10개 작성

### 6개월 후 (Phase 2 시작 전)
- [ ] 공동 개발자 또는 계약 프리랜서 영입
- [ ] 클로즈드 베타 대기 리스트 랜딩 페이지 (30~50명 확보)
- [ ] 법인 설립 + 개인정보 처리방침 초안
- [ ] Discord 커뮤니티 개설

---

## 9. Critical Files

Phase 0~1 착수 시 가장 먼저 손대야 할 파일 (프로젝트 루트 기준 상대경로):

- [core/session_manager.py](../core/session_manager.py) — 저장소 추상화의 진원지. `Path("data/sessions/")` 하드코딩을 `SessionRepository` 인터페이스로 대체.
- [ui/main_window.py](../ui/main_window.py) — 1,649줄의 UI-Core 강결합. `AppService` 도입으로 축소.
- [core/workflow_engine.py](../core/workflow_engine.py) — `CodeSandbox` 는 그대로 Agent 런타임으로 이식. 원격 로그 스트리밍 훅 추가 지점.
- [core/ai_engine.py](../core/ai_engine.py) — 서버 프록시 모드 (Phase 2) 를 위한 `ServerProxiedAdapter` 추가 위치. `ADAPTER_REGISTRY` 가 이미 확장 가능한 구조.
- [requirements.txt](../requirements.txt) — `pyproject.toml` 로 승격, `uv.lock` 도입 시작점.

---

## 10. 변경 로그

| 날짜 | 변경 | 이유 |
|---|---|---|
| 2026-04-21 | 초안 작성 | SaaS 확장 장기 로드맵 정립, B2C 개인 개발자 우선 타깃 확정 |
| 2026-04-23 | M1.2 구현 완료 (Device Flow 엔드포인트 + /link 브라우저 승인 페이지 + device_codes 마이그레이션 0002). /link 승인은 M1.2 한정 "이메일 stub" 흐름으로 진행하며 이메일 소유 증명은 M2+ 에서 매직링크로 보강 예정. 상세: [docs/saas/architecture/04-m1.2-device-flow.md](saas/architecture/04-m1.2-device-flow.md). |
| 2026-05-05 | §1 라이선스 전략 사용자 결정 확정 — 오픈코어 (AGPL-3.0 데스크톱 + 추후 폐쇄 SaaS) 유지. v1.0 은 100% AGPL-3.0 으로 진행, SaaS 유료/무료 라인은 Phase 2 진입 시점에 결정. 결정 근거: B2C 개인 개발자 우선 + 수익화 의향 양립 → 오픈코어가 두 목표 동시 충족. |
| 2026-05-07 | Phase 0 sub-phase 1+2 — `pyproject.toml` + `uv` 도입 (lockfile `uv.lock` 64 packages), `pre-commit` + `ruff` (lint+format) 설치, ruff `--fix` 로 520 issue 중 468 auto-fix + 47 manual + format 일괄. mypy 는 Phase 1 type hint 작업과 묶음. LICENSE (AGPL-3.0) + README 라이선스 섹션 추가. |
| 2026-05-08 | Phase 0 sub-phase 3+4+5 — SPDX 헤더 113 .py 파일 일괄 (`# SPDX-License-Identifier: AGPL-3.0-or-later`), GitHub Actions CI 매트릭스 (lint+ubuntu+windows, ai_integration 보류), `.devcontainer/devcontainer.json` (Python 3.12 + uv + Qt deps + ruff/pylance/gitlens 확장). Phase 0 의 인프라 표준화 5/7 항목 완료, structlog/Sentry 는 별도 작업으로 이관. |
| 2026-05-08 | Phase 1 sub-task 1·2A·3·4·5 일괄 진행 — (1) 저장소 추상화 + AppService leak 제거 + InMemoryRepository, (2A) ui_v2 5 banned import → AppService 경유 (KPI Chunk A), (3) Pydantic 모델 parallel 도입 (옵션 B 비파괴), (4) Pydantic Settings + .env 병합, (5) `agent/bridge.py` LocalBridge no-op. core 77→82, scenarios 72→73. 남은 Chunk B (ui/ legacy) 만 Phase 1 마무리 대기. |
| 2026-05-09 | Phase 1 sub-task 2 Chunk B 완결 — ui/ legacy (main_window + 4 handler/panel) 의 banned core import 모두 제거, 모든 import 가 `core.app_service` 단일 진입점 경유. AppService 인터페이스 보강 (클래스/상수/pure 함수 re-export + workflow_engine/prompt_builder property+setter). KPI "ui/ 폴더에서 banned core 직접 import 0건" 충족, test_83/84/85 (interface + main_window + ui/ 전체) 3중 가드. core 82→85, scenarios 73 유지. **Phase 1 100% 완료** — Phase 2 진입은 commercial_review.md GO/NO-GO 게이트 통과 후 결정. |
| 2026-05-09 | **시장 타깃 글로벌 확장 결정** — 한국 niche → 글로벌 우선 + 한국 dual-locale 양립으로 사용자 결정. 근거: 글로벌 SAM (50-100M USD/yr) 이 한국 (5-10M) 의 10배 + Computer Use 와 시간 경쟁. 차별성 재평가: "한국어 UI" 단일 항목 → "i18n (영어 + 한국어) + Plain Python + Local-first" 조합 niche 로 재포지셔닝. 영어 README + 사용자 facing UI/메시지 i18n 작업이 Phase 2 진입 직전 필수. commercial_review.md §3/§5/§7 동기화 갱신. |
| 2026-05-09~10 | **Phase 1.8 OpenAI 호환 (DeepSeek) 등록 + 코드 생성 품질 루프** — 사용자 일상 사용 중 발견 갭 11건 fix (settings dialog Test connection / reload_ai / current_engine 속성명 / ui_v2 step_done 메타 / ai.selected persist / 콘솔 가시성 settings / system_context prompt inject (P1a) / system role 분리 (P1b) / 가이드 #3+#5 강화 (P3) / element_context 템플릿 그대로 사용 강제 (G2) / library 블럭 essential imports prepend (G5) / element_context 템플릿 import 라인 제거 (G2.5)). baseline 85→96 (+11 회귀 가드 test_86~96). 자세한 내용: handoff.md §16. 잔존 갭 (DeepSeek 의 가이드 따르기 한계 — step 3/4 의 변수 재정의 + try/except 누락 + 들여쓰기 깨짐) 은 G6/G7 (정적 분석) 후속으로 보류. |
| 2026-05-12 | **PySide6 (LGPL) 메인 전환 완료 — Plan 1** — 2026-05-02 PySide6 port 추가 이후 양쪽 sync 부담 + PyQt6 (GPL/Riverbank commercial) 라이선스 마찰 해소를 위한 결정. `pyside6_port/` → root promotion (`ui/`, `ui_v2/`, `main.py`, `core/visual_overlay.py`, `core/environment_scanner.py` 의 PySide6 카피로 swap), 이전 PyQt6 코드는 `legacy_pyqt6/` 에 보존 (삭제 X — 사용자 명시 요청), PyQt6 의존성은 `[project.optional-dependencies] legacy-pyqt6` 로 격리. baseline 회귀 0 (core 107 + scenarios 73 그린, PySide6 단독 .venv). 자세한 단계: handoff.md §20. |
