# SaaS 확장 작업 CHANGELOG

각 세션별 작업을 시간 역순으로 1~3줄 요약. 상세 맥락은 해당 세션에서 만든 문서/파일로 연결.

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
