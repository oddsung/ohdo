# 02. M0 — 설치 스켈레톤 + 최소 백엔드 (Railway)

- **상태**: 구현 착수 (2026-04-22)
- **관련 문서**: [installer/00-strategy.md](../installer/00-strategy.md), [protocols/AGENT_PROTOCOL.md](../protocols/AGENT_PROTOCOL.md)

## 목표

**"빈 Agent 가 Windows PC 에 설치되어 트레이에 뜨고, Railway 에 올라간 FastAPI `/healthz` 에 주기적으로 ping 을 보내 200 을 받아 로그에 남긴다."**

이것만 되면 아래 위험이 모두 해소된 것으로 본다:

1. Python 번들링 (PyInstaller) 이 실제 Windows 에서 뜨는가
2. Inno Setup 인스톨러가 정상 설치/제거되는가
3. 설치된 Agent 가 Windows 시작 시 자동 실행되는가
4. Railway 에 FastAPI 가 올라가는가 + 외부에서 HTTPS 로 접근되는가
5. Agent 가 클라우드 URL 과 통신하는가 (방화벽·프록시 이슈 노출)

이 다섯 가지가 확인되기 전까지는 프로토콜 구현·인증·세션 동기화 같은 상위 작업이 모두 가설 위에서 진행된다.

## 왜 Railway 인가

Railway vs Fly.io 를 두고 짧게 비교했다:

| 항목 | Railway | Fly.io |
|---|---|---|
| Python MVP 배포 경로 | Procfile 감지로 자동 | Dockerfile 권장 |
| 무료 티어 | $5/월 크레딧 (소규모 충분) | 무료 앱 3개 |
| Postgres/Redis 프로비저닝 | 클릭 한 번 | 클릭 한 번 |
| 한국 레이턴시 | US/EU 리전 (일본은 Pro 플랜부터) | 도쿄 리전 무료 |
| 설정 복잡도 | 낮음 | 중간 |
| 인디/소규모 SaaS 점유율 | 높음 (2024~2026) | 높음 |

**결정: Railway.** 이유:
- Python FastAPI 단일 서비스에서 `Procfile` 한 줄만 있으면 자동 배포된다. Dockerfile 관리 부담 없음.
- 이 프로젝트는 타깃이 한국+글로벌 개인 개발자라 초기 레이턴시는 critical 하지 않다. Pro 전환 후 수요 보고 리전 재검토.
- 결제 계정 하나로 Postgres/Redis 도 같이 붙일 수 있어 Phase 2 로 넘어갈 때 추가 인프라 결정이 줄어든다.

**언제 Fly.io 재고려?**: 한국 사용자 p95 레이턴시가 실제로 문제되기 시작하는 시점 (Pro 가입자 100명 이상).

## 구조 (신규 파일만)

```
ohdo/
├── packages/
│   └── backend/                    # FastAPI 서비스 (Railway 배포 대상)
│       ├── app/
│       │   ├── __init__.py
│       │   └── main.py             # FastAPI 앱, /healthz
│       ├── requirements.txt        # fastapi, uvicorn
│       ├── Procfile                # Railway 시작 명령
│       ├── railway.json            # Railway 프로젝트 설정 (선택)
│       ├── .env.example
│       └── README.md               # 로컬 실행 + Railway 배포 가이드
├── agent/                           # 로컬 트레이 Agent
│   ├── __init__.py
│   ├── agent_main.py               # 단일 파일 트레이 앱 (M0 범위)
│   ├── requirements.txt            # pystray, pillow, httpx
│   ├── build.spec                  # PyInstaller 스펙
│   ├── installer/
│   │   └── ohdo-agent.iss          # Inno Setup 스크립트
│   └── README.md                   # 빌드·설치 가이드
└── docs/saas/architecture/02-m0-installer-and-backend.md   # 이 문서
```

기존 `core/`, `ui/`, `main.py`, `requirements.txt` 는 **건드리지 않음** — M0 는 core 와 독립적으로 설치/통신 경로만 검증한다.

## 컴포넌트 책임

### 백엔드 (packages/backend)

- FastAPI 앱. 라우트는 `/` 와 `/healthz` 둘.
- `/healthz` → `{"status": "ok", "version": "0.0.1", "ts": "<ISO>"}` 반환.
- 포트: 로컬은 8000, Railway 는 `$PORT` 환경변수 (Procfile 에서 참조).
- 로깅: 기본 uvicorn access 로그. 구조화 로깅은 M1 에서.

### 에이전트 (agent/)

- `pystray` 기반 트레이 아이콘 하나.
- 백그라운드 스레드에서 `OHDO_SERVER_URL`(기본 `http://localhost:8000`) 의 `/healthz` 를 30초마다 GET.
- 성공/실패를 로그 파일(`%APPDATA%\ohdo\agent.log`) 에 1줄씩 기록.
- 트레이 메뉴:
  - `Open Log Folder` — 로그 폴더를 탐색기로 연다
  - `Reload Config` — 환경변수/설정 재로드 (M0 는 스텁)
  - `Quit` — 종료
- 아이콘은 코드로 PIL 이미지 생성 (외부 파일 의존 없음).

### 인스톨러 (agent/installer)

- Inno Setup 6+ 스크립트.
- 설치 위치: `{autopf}\ohdo\agent`
- 시작 메뉴 바로가기 + 시작 프로그램 등록 (레지스트리 `Run` 키).
- 제거 시: 프로세스 종료 → 파일 삭제 → `%APPDATA%\ohdo` 는 보존 (사용자 데이터).

## 로컬 검증 절차 (이 문서 작성 시점 기준)

```pwsh
# 1. 백엔드 로컬 실행
cd packages/backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# → http://localhost:8000/healthz 에서 JSON 확인

# 2. 에이전트 로컬 실행 (PyInstaller 빌드 전)
cd agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
$env:OHDO_SERVER_URL = "http://localhost:8000"
python agent_main.py
# → 트레이에 ohdo 아이콘 생성, 로그에 ping 결과 기록
```

## Railway 배포 절차 (최초 1회)

```
1. https://railway.app/new → GitHub 계정 연결 → ohdo 레포 선택
2. Service > Root Directory = "packages/backend"
3. Variables (지금은 불필요, M1 부터 DATABASE_URL 등 추가)
4. Deploy → 발급된 도메인 https://ohdo-backend-production.up.railway.app 확인
5. 로컬에서: curl https://ohdo-backend-production.up.railway.app/healthz
6. Agent 에 그 URL 을 OHDO_SERVER_URL 로 설정 후 재시작
```

상세 절차와 스크린샷 위치는 [packages/backend/README.md](../../../packages/backend/README.md) 에 둔다.

## 완료 조건 (M0 DONE)

- [ ] `uvicorn` 로컬 실행, `/healthz` 200
- [ ] Railway 배포, 퍼블릭 URL `/healthz` 200
- [ ] `python agent_main.py` 로 트레이 아이콘 확인, 로그에 30초 간격 ping 기록
- [ ] PyInstaller 빌드 → `dist/ohdo-agent.exe` 생성
- [ ] Inno Setup 컴파일 → `ohdo-agent-setup-0.0.1.exe` 생성
- [ ] 빌드된 인스톨러로 깨끗한 Windows 에 설치 → 자동 실행 확인 → 클라우드 ping 성공

위 6개 중 본 세션에서 **코드와 스크립트까지** 준비하고, 실제 Railway 배포·PyInstaller 빌드·Windows 설치 테스트는 **사용자가 수동으로 실행** 한다. Claude 쪽에서 못 하는 부분이라 절차를 명확히 문서화.

## 다음 마일스톤 (M0 이후)

- **M1**: Device Flow 인증 + WebSocket 연결 + `agent.hello` (백엔드에 DB 추가, Agent 에 토큰 저장)
- **M2**: Agent 에 `core/` 번들 → `execution.start` 수신 시 실제 워크플로우 실행

M1 부터는 기존 core 수정이 발생할 가능성 있음 (예: `WorkflowEngine` 에 이벤트 콜백 훅 추가). [ADR 0001](../decisions/0001-preserve-existing-core.md) 의 4조건(사전 고지·회귀 테스트·CHANGELOG·범위 최소) 에 따라 진행.
