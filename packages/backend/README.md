# ohdo backend (Control Plane)

FastAPI 기반 ohdo.ai Control Plane. 현재는 **M0 — 헬스체크만** 제공.

- 관련 설계: [docs/saas/architecture/02-m0-installer-and-backend.md](../../docs/saas/architecture/02-m0-installer-and-backend.md)
- 전체 프로토콜 계획: [docs/saas/protocols/AGENT_PROTOCOL.md](../../docs/saas/protocols/AGENT_PROTOCOL.md)

## 로컬 실행

PowerShell 에서 activation 스크립트가 실행정책에 막히거나 이름이 달라 혼란을 주는 경우가 많다. **venv 활성화 없이 `.venv\Scripts\python.exe` 를 직접 호출**하는 아래 방식이 가장 안정적이다.

```pwsh
cd packages\backend
python -m venv .venv

.venv\Scripts\python.exe -m pip install -r requirements.txt

# (선택) 환경변수 파일 복사
Copy-Item .env.example .env

.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

### venv 를 활성화해서 쓰고 싶을 때

```pwsh
# 현재 PowerShell 세션 한정 실행정책 완화 (한 번만)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

> PowerShell 에서 `.venv\Scripts\activate` (확장자 없이) 는 cmd/bash 용이라 "module could not be loaded" 에러가 난다. `Activate.ps1` 을 명시적으로 호출.

확인:

```pwsh
curl http://localhost:8000/healthz
# → {"status":"ok","version":"0.0.1","ts":"...","env":"development"}

# 브라우저에서 자동 생성된 OpenAPI 문서
start http://localhost:8000/docs
```

## Railway 배포 (최초 1회)

### 사전 준비

- Railway 계정 (https://railway.app)
- GitHub 레포 ohdo 가 Railway 에서 접근 가능해야 함 (Railway 설치 시 권한 부여)

### 절차

1. Railway 대시보드 → **New Project** → **Deploy from GitHub repo** → `ohdo` 선택.
2. 프로젝트 생성 후 **Settings → Service**:
   - **Root Directory**: `packages/backend`
   - **Build Command**: (비움 — nixpacks 가 `requirements.txt` 자동 감지)
   - **Start Command**: (비움 — `Procfile` 또는 `railway.json` 자동 감지)
3. **Settings → Networking → Generate Domain** 클릭 → 공개 URL 발급 (`https://ohdo-backend-production-xxxx.up.railway.app` 형식).
4. **Variables** 에 다음 추가 (선택):
   - `OHDO_ENV=production`
5. 자동 배포가 끝나면 헬스체크:

```pwsh
curl https://<발급된 도메인>/healthz
# → {"status":"ok","env":"production",...}
```

### 이후 배포

- `main` 브랜치 푸시 → Railway 자동 재배포.
- 배포 로그는 대시보드 → **Deployments**.

## 파일 구조

```
packages/backend/
├── app/
│   ├── __init__.py      # 버전만
│   └── main.py          # FastAPI 앱
├── requirements.txt     # fastapi, uvicorn
├── Procfile             # Railway 시작 명령 (nixpacks 가 감지)
├── railway.json         # Railway 프로젝트 설정 + 헬스체크
├── .env.example         # 환경변수 템플릿
├── .gitignore
└── README.md            # 이 파일
```

## 다음 마일스톤

- **M1**: Device Flow (`POST /v0/agents/device_code`, `POST /v0/agents/device_token`), SQLAlchemy + Alembic 도입, PostgreSQL (Railway 플러그인), Agent 테이블.
- **M2**: WebSocket Gateway (`/v0/agent`), Redis + ARQ, 실행 지시 큐잉.

## 트러블슈팅

**Railway 배포 실패 (`uvicorn` 미발견)**: `requirements.txt` 가 Root Directory 바로 아래 있는지 확인. nixpacks 는 Root Directory 기준으로 Python 감지.

**PORT 에러**: Railway 는 `$PORT` 를 자동 주입. Procfile 의 `${PORT:-8000}` 이 없으면 시작 실패할 수 있음. railway.json 의 `startCommand` 가 우선.

**CORS 오류 (추후)**: 웹 대시보드를 붙일 때 `fastapi.middleware.cors.CORSMiddleware` 추가. M0 에서는 불필요.
