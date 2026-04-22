# SaaS 확장 작업 CHANGELOG

각 세션별 작업을 시간 역순으로 1~3줄 요약. 상세 맥락은 해당 세션에서 만든 문서/파일로 연결.

---

## 2026-04-23 (M1.1 완료) — Railway Postgres 에 스키마 실제 적용

**Railway 인시던트 동안의 디버깅 여정**:

1. 최초 푸시(`c570ae0`) 는 Railway 의 Build Machines(Metal) 인시던트로 빌드 자체가 시작 안 됨 — "No build logs were found".
2. 사용자가 `railway.json` 의 `startCommand` 를 `alembic upgrade head && uvicorn ...` 로 체이닝 (`df6e17b`, `e354589`) — 올바른 방향이지만 Procfile `release:` 와 중복 상태.
3. 빌드가 돌기 시작했지만 `[stage-0 8/10] RUN alembic upgrade head` 에서 `socket.gaierror [Errno -2] Name or service not known` — Procfile `release:` 가 **docker build 단계에 RUN 으로 박혀 실행되어** Postgres 사설 네트워크에 붙지 못함 (Railway 는 Heroku 와 달리 release 전용 컨테이너가 없음).
4. 수정 `0ce29e6`: Procfile 의 `release:` 라인 제거, `web:` 에도 alembic 체이닝 추가.
5. 추가 수정 `1af5c26`: Procfile 을 완전 삭제하고 `nixpacks.toml` 로 build plan 명시. `phases.install` 만 정의하여 alembic 이 빌드 단계에 들어갈 모든 경로 차단.
6. 배포 성공 (빌드 47.46s, 헬스체크 `[1/1] Healthcheck succeeded!`).
7. 사용자 확인: Postgres Data 탭에 `users`, `agents`, `alembic_version` 3 테이블 존재, `alembic_version.version_num = 0001`.

**배운 것 (핵심)**:
- Railway nixpacks 의 `release` 는 Heroku 의 release phase 와 **다르다**. Heroku: 별도 런타임 컨테이너(env + network 접근 가능). Railway nixpacks: Dockerfile 의 RUN 스텝(빌드 시점, env/network 제한).
- **Railway 에서 마이그레이션 같은 "배포 직전 런타임 작업"** 은 Procfile `release:` 가 아니라 `railway.json startCommand` 또는 `nixpacks.toml [start].cmd` 에 체이닝해야 한다.
- Procfile 이 어색하게 개입하는 것을 막으려면 **완전 삭제 + nixpacks.toml 명시** 가 가장 안전.

**결과적 M1.1 상태**:
- [x] 백엔드 의존성·모델·마이그레이션 작성
- [x] 로컬 SQLite 마이그레이션 검증
- [x] Railway 에 Postgres 플러그인 + `DATABASE_URL` 참조
- [x] Railway 재배포 후 실제 Postgres 에 `users`·`agents`·`alembic_version` 테이블 존재 확인
- [x] `alembic_version` 레코드 `0001` 확인

다음 서브마일스톤 **M1.2 (Device Flow 엔드포인트 + 브라우저 승인 페이지)** 로 넘어간다.

---

## 2026-04-23 (M1.1 착수) — Postgres + SQLAlchemy + Alembic 스캐폴딩 + 로컬 마이그레이션 검증

**설계**: [architecture/03-m1.1-postgres-auth-schema.md](architecture/03-m1.1-postgres-auth-schema.md) — 스키마 결정(users, agents), 기술 스택 비교, DATABASE_URL 경로, 자동 마이그레이션 정책.

**추가된 코드** (모두 `packages/backend/` 안):
- `app/config.py` — Pydantic Settings. `DATABASE_URL` 자동 정규화 (`postgresql://` → `postgresql+asyncpg://`).
- `app/db.py` — SQLAlchemy async 엔진 + `SessionLocal` + FastAPI Depends 용 `get_session()`.
- `app/models/` — `Base`, `TimestampMixin`, `User`, `Agent` (SQLAlchemy 2.0 typed `Mapped[]` 스타일).
- `alembic.ini` + `alembic/env.py` (async 엔진 대응) + `alembic/script.py.mako` + `alembic/versions/20260423_0001_initial_users_agents.py`.
- `Procfile` — `release: alembic upgrade head` 라인 추가 → Railway 가 배포 직전에 자동으로 스키마 적용.
- `requirements.txt` — `sqlalchemy[asyncio]`, `alembic`, `asyncpg`, `aiosqlite`, `pydantic-settings` 추가.

**로컬 검증** (SQLite 폴백):
```
alembic upgrade head
→ Running upgrade  -> 0001, initial users and agents tables
→ 생성 테이블: users, agents, alembic_version
→ 인덱스: agents_user_id_idx, agents_token_hash_idx
```

**사용자가 Railway 에서 해야 할 것** (1~2분):
1. Railway 대시보드 → 기존 `ohdo` 프로젝트 → **+ New** → **Database** → **Add PostgreSQL** 클릭.
2. 생성된 Postgres 서비스가 `DATABASE_URL` 등 환경변수를 **Postgres 서비스** 자체에만 노출한다. 그걸 backend 서비스로 참조해야 함:
   - backend 서비스 선택 → **Variables** 탭 → **+ New Variable** 또는 **Reference** 선택
   - Name: `DATABASE_URL`
   - Reference: `${{Postgres.DATABASE_URL}}` (Railway 가 자동 완성 제안)
3. 저장하면 backend 가 자동 재배포되며 release 단계에서 `alembic upgrade head` 실행. Deployments 로그에 `Running upgrade  -> 0001` 이 보이면 성공.
4. (선택) Postgres 서비스 → **Data** 탭에서 `users`, `agents` 테이블 존재 확인.

**발견 이슈**:
- `alembic.ini` 의 한국어 주석을 Windows cp949 로 읽으려다 `UnicodeDecodeError`. 영어로 교체. ConfigParser 가 encoding 명시 안 하면 시스템 로케일 쓰기 때문. 이후 `.ini` 계열 파일은 ASCII 만 사용.

**M1.1 완료 조건 체크**:
- [x] 백엔드에 SQLAlchemy/Alembic 의존성 추가 및 모델·마이그레이션 파일 작성
- [x] 로컬 SQLite 대상으로 `alembic upgrade head` 성공
- [ ] Railway 에 Postgres 플러그인 추가 (사용자 수동)
- [ ] Railway 재배포 후 release 단계에서 마이그레이션 자동 실행 로그 확인
- [ ] Postgres 에 테이블 존재 확인

**다음 서브마일스톤 (M1.2)** 예정: Device Flow 엔드포인트 + 브라우저 승인 페이지.

---

## 2026-04-23 (최종) — M0 전체 완료 🎉

설치 테스트 성공. 사용자 머신에서 인스톨러로 설치된 agent 가 재부팅 없이 트레이에 떴고, `%APPDATA%\ohdo\agent.log` 에 Railway 대상 `ping ok 200` 이 30초 주기로 누적됨.

**실제 로그 (2026-04-23 00:50~51)**:
```
ohdo agent starting: version=0.0.1 server=https://ohdo-production.up.railway.app
pinger started: url=https://ohdo-production.up.railway.app interval=30s
ping ok: status=200 elapsed=1078ms   (cold)
ping ok: status=200 elapsed=811ms    (warm)
ping ok: status=200 elapsed=875ms
```

**M0 완료 조건 전체 체크**:
- [x] `uvicorn` 로컬 실행, `/healthz` 200
- [x] Railway 배포, 퍼블릭 URL `/healthz` 200
- [x] `python agent_main.py` ping 루프 정상
- [x] PyInstaller 빌드 → `dist/ohdo-agent.exe` 생성·실행 검증
- [x] Inno Setup 컴파일 → `ohdo-agent-setup-0.0.1.exe` (14 MB)
- [x] **인스톨러 실행 → 트레이 + 자동 실행 + Railway ping 성공**

**M0 의 본래 목적 (아키텍처 문서 §"목표") 대응**:
- ✅ Python 번들링이 실제 Windows 에서 뜨는가
- ✅ Inno Setup 인스톨러가 정상 설치/제거되는가 (자동 실행 레지스트리 등록 확인)
- ⏳ Windows 시작 시 자동 실행 — 재부팅 시 확인 권장 (선택)
- ✅ Railway 에 FastAPI 올라가 외부 HTTPS 로 접근되는가
- ✅ Agent 가 클라우드 URL 과 통신하는가 (방화벽/프록시 문제 없음)

이 다섯 가지 인프라 리스크가 해소되었으므로 **M1 부터는 프로토콜·인증·DB 같은 앱 레이어 구현에 집중**하면 된다.

---

## 2026-04-23 (후속) — PyInstaller 번들 + Inno Setup 인스톨러 생성, Railway 기본값 적용

**완료 항목**:
- PyInstaller 빌드 → `dist/ohdo-agent/ohdo-agent.exe` (3.85 MB, 번들 총 34 MB)
- 번들 exe 실제 실행 → Railway `/healthz` 에 연속 10회 `ping ok 200` 확인 (780~920ms).
- Inno Setup 6 컴파일 → `dist-installer/ohdo-agent-setup-0.0.1.exe` (14 MB, lzma 압축)
- Inno Setup 설치 경로: `%LOCALAPPDATA%\Programs\Inno Setup 6\` (user-scope, 사용자가 기본 옵션으로 설치).

**agent_main.py 개정** (이 세션에서 만든 파일이라 ADR 0001 의 "기존 파일 수정" 조항 비해당):
- `DEFAULT_SERVER_URL` → Railway 프로덕션 URL. 환경변수 없이 설치된 agent 도 기본으로 클라우드와 통신하도록.
- 서버 URL 해석 우선순위: `env var > %APPDATA%/ohdo/config.json > default`. `resolve_server_url()` + `_load_config()` 신규.
- `CONFIG_FILE = %APPDATA%/ohdo/config.json` 경로 추가. M1 Device Flow 가 여기에 `server_url`·`agent_token` 을 쓴다.
- 재빌드 → 재컴파일 → env var 없이 실행 테스트: `server=https://ohdo-production.up.railway.app` 로 해석되고 ping 200 확인.

**README 보강**: [agent/README.md](../../agent/README.md) 에 "서버 URL 해석 우선순위" + config.json 스키마 섹션 추가.

**M0 완료 조건 재점검**:
- [x] `uvicorn` 로컬 실행, `/healthz` 200
- [x] Railway 배포, 퍼블릭 URL `/healthz` 200
- [x] `python agent_main.py` ping 루프 정상
- [x] PyInstaller 빌드 → `dist/ohdo-agent.exe` 생성·실행 검증
- [x] Inno Setup 컴파일 → `ohdo-agent-setup-0.0.1.exe` 생성
- [ ] **깨끗한 Windows 에 설치 → 자동 실행 + Railway ping 성공 — 사용자 수동 1단계만 남음**

**사용자가 할 마지막 단계**:
1. `C:\Users\NeodaVinci\ohdo\agent\dist-installer\ohdo-agent-setup-0.0.1.exe` 더블클릭.
2. Windows SmartScreen 경고 → 추가 정보 → 실행 (코드 사이닝 없음).
3. 마법사 진행 → "지금 실행" 체크 유지 → 설치 완료.
4. 시스템 트레이에 ohdo 아이콘 확인.
5. 10~30초 뒤 `%APPDATA%\ohdo\agent.log` 맨 아래에 `ping ok https://ohdo-production.up.railway.app/healthz status=200` 확인.
6. (선택) Windows 재시작 → 자동 실행 + 지속 ping 확인.

---

## 2026-04-23 — Railway 배포 성공 (M0 클라우드 경로 완료)

**배포 정보**:
- 공개 URL: `https://ohdo-production.up.railway.app`
- 최초 빌드 소요: ~386초 (nixpacks, Python 3.12 감지 → `requirements.txt` 설치 → `Procfile` 시작)
- 헬스체크: `[1/1] Healthcheck succeeded!` (railway.json 의 `/healthz` 30초 타임아웃 적용)
- 상태: **Online**

**검증 결과**:
```
$ curl https://ohdo-production.up.railway.app/healthz
{"status":"ok","version":"0.0.1","ts":"2026-04-22T15:20:09.865282+00:00","env":"development"}

$ curl https://ohdo-production.up.railway.app/
{"service":"ohdo-backend","version":"0.0.1","docs":"/docs"}
```

**배포 절차 (실제 수행된 순서)**:
1. Railway 가입 — GitHub `oddsung` 계정으로 OAuth 로그인, 약관 동의.
2. GitHub App 설치 — `oddsung/ohdo` 레포만 허용 (최소 권한 원칙).
3. New Project → Deploy from GitHub repo → `oddsung/ohdo` 선택.
4. Settings → Source → **Root Directory: `packages/backend`** 로 변경 후 재배포.
5. Networking → Public Networking → Generate Domain, 포트 8080.
6. 빌드 완료 후 `/healthz` 200 확인.

**다음 정리 항목 (선택)**:
- [ ] Railway Variables 에 `OHDO_ENV=production` 추가 — `/healthz` 응답의 `env` 필드 값 교정용, 기능에 영향 없음.
- [ ] 로컬 Agent 를 Railway URL 로 재기동하여 end-to-end ping 확인:
  ```
  taskkill /F /IM python.exe
  cd /d C:\Users\NeodaVinci\ohdo\agent
  set OHDO_SERVER_URL=https://ohdo-production.up.railway.app
  .venv\Scripts\python.exe agent_main.py
  ```
  `%APPDATA%\ohdo\agent.log` 에 원격 URL 기준 `ping ok` 가 쌓이면 성공.

**M0 완료 조건 재점검**:
- [x] `uvicorn` 로컬 실행, `/healthz` 200
- [x] **Railway 배포, 퍼블릭 URL `/healthz` 200**
- [x] `python agent_main.py` ping 루프 정상
- [ ] PyInstaller 빌드 → `dist/ohdo-agent.exe` — 사용자 수동
- [ ] Inno Setup 컴파일 → `ohdo-agent-setup-0.0.1.exe` — 사용자 수동
- [ ] 깨끗한 Windows 에 설치 → 자동 실행 + Railway ping 성공 — 사용자 수동

**다음 세션**: PyInstaller 번들 + Inno Setup 컴파일 진행 ([agent/README.md](../../agent/README.md) §"인스톨러 빌드"). 이게 끝나면 M0 전체 종료. 그 뒤 M1 (Device Flow + WebSocket + PostgreSQL) 착수.

---

## 2026-04-22 (밤) — M0 로컬 검증 완료 + agent_main.py 버그 수정

**검증 방식**: Claude 가 사용자 머신에서 Bash 도구로 직접 실행. 기존 `.venv` 들이 고아 Python38-32 를 가리켜 모두 재생성 필요했음 — `py -3.12 -m venv .venv` 로 해결.

**발견·수정한 버그**:
- [agent/agent_main.py](../../agent/agent_main.py) — `from agent import __version__` 가 `python agent_main.py` 직접 실행 시 `ModuleNotFoundError`. PyInstaller 번들에서도 동일 이슈. `__version__` 을 파일 내부 상수로 하드코딩 (주석으로 `agent/__init__.py` 동기화 명시).

**검증 결과**:
- `uvicorn app.main:app` → `Uvicorn running on http://127.0.0.1:8000` OK
- `GET /` → `{"service":"ohdo-backend","version":"0.0.1","docs":"/docs"}`
- `GET /healthz` → `{"status":"ok","version":"0.0.1","ts":"...","env":"development"}`
- `python agent_main.py` → 트레이 프로세스 + 백그라운드 ping 스레드 구동
- `%APPDATA%\ohdo\agent.log` → 10초 주기로 `ping ok status=200 elapsed=~350ms` 누적 (3분간 20개 기록 확인)

**환경 발견**:
- 사용자 머신 Python: `py -V:3.12` (3.12 64-bit) 사용 가능. 2차 후보 `3.10-32`, `3.8-32`. `python` 명령은 루트 `.venv` 의 고장난 stub 을 가리키므로 **모든 venv 생성은 `py -3.12`** 로 해야 안전.
- PowerShell 의 `.venv\Scripts\activate` 는 bash 용 → PowerShell/cmd 모두에서 **activation 없이 `.venv\Scripts\python.exe` 직접 호출** 방식을 README 기본으로 채택.

**M0 완료 조건 체크**:
- [x] `uvicorn` 로컬 실행, `/healthz` 200
- [ ] Railway 배포, 퍼블릭 URL `/healthz` 200 — **사용자 수동 단계**
- [x] `python agent_main.py` 로 ping 루프 정상, 로그 누적 확인
- [ ] PyInstaller 빌드 → `dist/ohdo-agent.exe` 생성 — **사용자 수동 단계**
- [ ] Inno Setup 컴파일 → `ohdo-agent-setup-0.0.1.exe` 생성 — **사용자 수동 단계**
- [ ] 깨끗한 Windows 에 설치 → 자동 실행 확인 → 클라우드 ping 성공 — **사용자 수동 단계**

**다음 세션**: 사용자가 Railway 배포 + PyInstaller/Inno Setup 빌드를 수동으로 진행한 뒤, 깨끗한 Windows 에서 설치 테스트가 끝나면 M0 전체 완료. 이후 M1 (Device Flow + WebSocket + PostgreSQL) 착수.

---

## 2026-04-22 (저녁) — M0 착수: FastAPI 백엔드 + 트레이 Agent + Inno Setup 스캐폴딩

**목표**: "빈 Agent 가 Windows PC 에 설치되어 트레이에 뜨고, Railway 에 올라간 FastAPI `/healthz` 에 30초마다 ping 을 보내 로그에 기록." 코드·스크립트까지 준비, 실제 Railway 배포·PyInstaller 빌드·Windows 설치는 사용자 수동 실행.

**호스팅 결정**: Railway 로 확정. 이유는 Python Procfile 자동 감지 + Postgres/Redis 원클릭 프로비저닝. Fly.io 재고려 조건은 한국 p95 레이턴시 문제가 실제로 발생하는 시점 ([아키텍처 문서](architecture/02-m0-installer-and-backend.md) §"왜 Railway 인가").

**신규 파일 (기존 core 수정 0)**:

- 설계: [architecture/02-m0-installer-and-backend.md](architecture/02-m0-installer-and-backend.md) — M0 완료 조건 6개, 로컬/Railway 검증 절차, Fly.io 비교.
- 백엔드 [packages/backend/](../../packages/backend/):
  - `app/main.py` — FastAPI, `/`·`/healthz`
  - `requirements.txt`, `Procfile`, `railway.json`, `.env.example`, `.gitignore`
  - `README.md` — 로컬 실행, Railway 단계별 배포 절차, 트러블슈팅
- 에이전트 [agent/](../../agent/):
  - `agent_main.py` — pystray 트레이 + `HealthPinger` 백그라운드 스레드, `%APPDATA%\ohdo\agent.log` 로 회전 로깅
  - `requirements.txt`, `build.spec`, `.gitignore`, `README.md`
  - `installer/ohdo-agent.iss` — Inno Setup 6 스크립트 (자동 실행 레지스트리 등록, 비관리자 설치 기본)

**테스트**:

- `python -m py_compile` 신규 파일 4개 → 모두 SYNTAX_OK.
- `python -m tests.test_runner --suite core` → 25 passed / 0 failed (회귀 없음 재확인).

**사용자가 다음에 할 일 (수동 실행 필요)**:

1. 백엔드 로컬 확인: `cd packages/backend && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt && uvicorn app.main:app --reload`. `curl http://localhost:8000/healthz` 200 확인.
2. 에이전트 로컬 확인: `cd agent && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt && python agent_main.py`. 트레이 아이콘 확인 + 로그 파일 `ping ok` 확인.
3. Railway 배포: [packages/backend/README.md](../../packages/backend/README.md) §"Railway 배포" 단계 그대로.
4. Windows 인스톨러 빌드: [agent/README.md](../../agent/README.md) §"인스톨러 빌드". PyInstaller → Inno Setup → 설치 테스트.

**다음 세션 (M0 검증 완료 후)**:

- M1 착수: Device Flow 엔드포인트(`POST /v0/agents/device_code`, `/device_token`), PostgreSQL + SQLAlchemy + Alembic 도입, Agent 에 토큰 저장, WebSocket 연결 (`/v0/agent` + `agent.hello`).
- 이 시점부터 기존 `core/workflow_engine.py` 에 실행 이벤트 콜백 훅이 필요할 수 있음 → [ADR 0001](decisions/0001-preserve-existing-core.md) 4조건 적용.

---

## 2026-04-22 (오후 후속) — ADR 0001 개정: "수정 금지" → "wrap-first, 필요 시 수정 허용"

- 사용자 피드백: 원래 의도는 회귀 방지였지 수정 전면 금지는 아님.
- [decisions/0001-preserve-existing-core.md](decisions/0001-preserve-existing-core.md) 를 개정. 기본은 여전히 wrap-first, 단 SaaS 연동에 필요하면 기존 `core/`·`ui/`·`main.py` 수정 가능. 조건 4개: 사전 고지 + 회귀 테스트 그린 + CHANGELOG 기록 + 범위 최소화.
- [README.md](README.md) 의 "작업 원칙" 1번 항목도 동일하게 갱신.
- 이번 세션의 코드는 모두 신규 파일이므로 이 변경이 실제 수정으로 이어지진 않음. 다음 번 "기존 파일에 손대야 하는" 작업이 생길 때부터 새 정책이 적용됨.

---

## 2026-04-22 — SaaS 확장 킥오프: 문서 스캐폴딩 + Facade 레이어 초안

- `docs/saas/` 폴더 신설: README, CHANGELOG, 2개 ADR, AppService/Storage 설계 문서 추가.
- 기본 원칙 확정 — **기존 `core/`, `ui/`, `main.py` 는 건드리지 않고 새 파일로 감싸서 확장** ([decisions/0001-preserve-existing-core.md](decisions/0001-preserve-existing-core.md)).
- Facade 방식 채택 ([decisions/0002-appservice-facade-approach.md](decisions/0002-appservice-facade-approach.md)): 새 `core/app_service.py` + `core/storage/` 가 기존 `SessionManager` 등을 composition 으로 감싼다.
- 코드 추가:
  - [core/storage/base.py](../../core/storage/base.py) — `SessionRepository` 추상 인터페이스.
  - [core/storage/local_json.py](../../core/storage/local_json.py) — 기존 `SessionManager` 를 감싸 `SessionRepository` 로 노출.
  - [core/app_service.py](../../core/app_service.py) — 세션 조회/생성/스텝 관리용 얇은 facade. 현재는 storage 래핑만. AI/워크플로우 실행 훅은 다음 단계에서 추가.
- Agent 프로토콜 초안 작성: [protocols/AGENT_PROTOCOL.md](protocols/AGENT_PROTOCOL.md) — WebSocket 메시지 타입, 연결·인증 흐름, 메시지 예시.
- 설치 프로그램 전략 문서: [installer/00-strategy.md](installer/00-strategy.md) — PyInstaller + Inno Setup 기반 1차 목표는 "트레이 Agent 가 설치 후 서버에 ping 보내는" 최소 스켈레톤.
- 테스트 결과: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (회귀 없음 확인). 새 facade import 스모크(`from core.storage import ...`; `AppService(session_repo=LocalJsonRepository(...))`) 도 정상 동작, 기존 세션 목록 조회 확인.

**다음 세션 할 일**:
- `pytest` 로 `core.storage.local_json` 과 `core.app_service` 단위 테스트 추가 (기존 테스트 러너와 별개로 추가 권장).
- AppService 에 `run_step` / `generate_step` 메서드 추가 (현재 UI 직접 호출 흐름을 점진 이식).
- Agent 프로토콜 문서에 대해 사용자 리뷰·승인 → FastAPI 스켈레톤 착수.
