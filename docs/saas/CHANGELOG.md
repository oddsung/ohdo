# SaaS 확장 작업 CHANGELOG

각 세션별 작업을 시간 역순으로 1~3줄 요약. 상세 맥락은 해당 세션에서 만든 문서/파일로 연결.

---

## 2026-04-23 (M2.2 구현·로컬 e2e) — REST `POST/GET /v0/executions`

**설계**: [architecture/09-m2.2-executions-rest.md](architecture/09-m2.2-executions-rest.md) — A 패턴 (agent self-enqueue, Bearer agent 인증만), `exec_<uuid4.hex>` id 포맷, GET 권한은 `user_id` 스코프 (같은 사용자의 모든 기기 교차 조회 가능, 다른 사용자는 404), M2.2 에서는 status 전이 없음 (모두 `queued` 로 생성).

**추가/수정된 코드**:

- `packages/backend/app/routers/executions.py` [신규]:
  - `POST /v0/executions` — Bearer 인증, body `{session_snapshot?, from_step?, to_step?}` 수신 → row insert → 201 + `ExecutionRead` (session_snapshot 은 응답에서 제외).
  - `GET /v0/executions/{execution_id}` — 본인 `user_id` 스코프, 타 사용자는 404 `execution_not_found` (존재 여부 누설 방지).
  - `GET /v0/executions` — 같은 `user_id` 리스트 (최신순), `limit`(1~200, default 50)·`offset`·`status` 쿼리 지원. 허용 status 외 400 `invalid_status_filter`.
  - Pydantic: `ExecutionCreate` (`from_step`/`to_step` 은 `ge=1` 검증), `ExecutionRead` (`from_attributes=True` 로 ORM → 스키마 변환), `ExecutionListResponse`.
- `packages/backend/app/main.py` [수정] — `executions` 라우터 include.

**로컬 e2e 검증** (SQLite, uvicorn :8772, 사용자 A 의 agent A1/A2 + 사용자 B 의 agent B1):

| # | 시나리오 | 결과 |
|---|---|---|
| 1 | unauth `POST /v0/executions` | 401 `missing_token` |
| 2 | A1 POST `{}` | 201, `exec_f103…e1cc`, `status=queued`, from/to_step=null |
| 3 | A1 POST with `session_snapshot` + `from_step=2` | 201, from_step 반영 |
| 4 | A2 POST (동일 user) | 201, agent_id 는 A2 지만 user_id 는 A 와 동일 |
| 5 | B1 POST | 201, 독립 user_id |
| 6 | A1 GET 자기 row | 200 |
| 7 | A2 GET A1 생성 row (same user) | 200 ✅ user 스코프 동작 |
| 8 | B1 GET A1 생성 row (other user) | 404 `execution_not_found` ✅ 격리 |
| 9 | A1 GET 존재하지 않는 `exec_` | 404 |
| 10 | A1 LIST | 200, items=3, ids 포함 |
| 11 | A1 LIST `limit=1` | 200, items=1 |
| 12 | A1 LIST `status=queued` | 200, items=3 |
| 13 | A1 LIST `status=running` | 200, items=0 |
| 14 | A1 LIST `status=nope` | 400 `invalid_status_filter` |
| 15 | B1 LIST | 200, items=1 (B1 것만) |
| 16 | unauth GET detail | 401 |
| 17 | POST `from_step=0` | 422 (Pydantic `ge=1`) |
| 18 | POST `from_step=-3` | 422 |

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (20:34).

**M2.2 완료 조건 체크**:

- [x] `POST /v0/executions` (Bearer) + body 검증 + 201 응답
- [x] `GET /v0/executions/{id}` + user_id 스코프 404 격리
- [x] `GET /v0/executions` + limit/offset/status 필터
- [x] 로컬 SQLite 18 시나리오 통과
- [x] 코어 회귀 25/25
- [ ] Railway Postgres e2e — push 후 외부에서 POST/GET 으로 실제 row 생성 + M2.1 잔여 row-level 검증 동반 수행

**M2.2 범위 밖**: WS `execution.start` push (M2.3), 상태 전이 (M2.3), 로그 스트리밍 (M2.4), cancel (M2.5), 스크린샷 업로드 (M2.6).

**Core 수정**: 없음.

---

## 2026-04-23 (M2.1 구현·로컬 e2e) — `executions` 테이블 + 마이그레이션 `0003`

**설계**: [architecture/08-m2.1-executions-schema.md](architecture/08-m2.1-executions-schema.md) — 테이블 컬럼·인덱스·상태 머신, JSON 타입 선택 (SQLite/Postgres 양쪽 호환), M2 전체 단계별 범위 분할.

**추가된 코드** (API/라우터/WS 무변경, 순수 스키마만):

- `packages/backend/app/models/execution.py` [신규] — `Execution` SQLAlchemy 모델. `execution_id` (public id, unique), `agent_id`/`user_id` FK (CASCADE), `status` (기본 `queued`), `session_snapshot` (JSON — Postgres 는 JSONB, SQLite 는 TEXT 로 매핑), `from/to_step`, `total_steps`/`executed_steps`/`successful_steps`/`failed_steps`/`total_time_ms` 집계 컬럼, `error_summary`, `started_at`/`finished_at`, `created_at`/`updated_at` Mixin.
- `packages/backend/app/models/__init__.py` [수정] — `Execution` 등록 (Alembic autogenerate 가 `Base.metadata` 로 보도록).
- `packages/backend/alembic/versions/20260423_0003_executions.py` [신규] — `0002 → 0003` 마이그레이션. `executions` 테이블 + FK 2개 + 인덱스 4개 (`execution_id` unique / `agent_id` / `user_id` / `status`). `downgrade()` 도 대칭 구현.

**상태 머신** (M2 전체 걸쳐 사용):

```
queued → accepted → running → completed | failed | cancelled
```

M2.1 은 컬럼만 허용. 전이 강제 로직은 M2.3 (WS `execution.*` 처리) 에서 추가.

**로컬 e2e 검증** (SQLite):

| 시나리오 | 결과 |
|---|---|
| `alembic upgrade head` (0002 → 0003) | ✅ 테이블/인덱스/FK 생성 |
| `PRAGMA table_info(executions)` | 18 컬럼 모두 설계와 일치 |
| `PRAGMA foreign_key_list(executions)` | users/agents 양쪽 CASCADE 확인 |
| ORM insert `execution_id='exec_m21_smoke_1'` + JSON payload | `status='queued'` 기본값·created_at 자동 채움 |
| select by `execution_id` 라운드트립 | `session_snapshot.steps` 원본 그대로 |
| 같은 `execution_id` 중복 insert | `IntegrityError` (unique 인덱스 동작) |
| `alembic downgrade -1` → `upgrade head` | 테이블 재생성 OK, 0003 head 복원 |

**기존 API 회귀 (smoke)**: uvicorn 기동 후 `/`, `/healthz`, `/v0/agents/me` (no auth) 전부 기존 동작 유지.

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (17:03).

**M2.1 완료 조건 체크**:

- [x] `Execution` 모델 + `models/__init__.py` 등록
- [x] 마이그레이션 `0003` upgrade/downgrade 쌍
- [x] 로컬 SQLite 테이블 생성 + ORM 라운드트립 + unique 제약 동작
- [x] 코어 회귀 25/25
- [x] Railway Postgres 0003 자동 적용 — 커밋 `78a747f` 푸시 후 `/healthz` 200 지속 + `POST /v0/agents/device_code` 정상 (server 가 재기동 완료 → startCommand `alembic upgrade head && uvicorn` 이 실패 없이 통과 = 0003 적용). 개별 row-level 확인은 M2.2 의 `POST /v0/executions` 에서 직접 검증.

**M2.1 범위 밖**: REST `POST /v0/executions` (M2.2), WS `execution.*` (M2.3), 로그 스트림 (M2.4), 스크린샷 업로드 (M2.6).

**Core 수정**: 없음. ADR 0001 4조건 미발동.

---

## 2026-04-23 (M1.5 구현·로컬 e2e) — WebSocket `/v0/agent` + `server.hello`/`agent.hello`

**설계**: [architecture/07-m1.5-websocket-hello.md](architecture/07-m1.5-websocket-hello.md) — 인증 방식 (Authorization 헤더), close code 규약 (4400/4401/4403), accept-then-close 이유, 재연결 백오프 정책.

**추가/수정된 코드**:

- `packages/backend/app/routers/ws.py` [신규] — `WS /v0/agent`. Bearer 파싱 → `Agent` 조회 (REST 경로와 동일 로직) → `accept()` 후 실패 시 close code (4401 missing/malformed/invalid, 4403 revoked). 성공 시 `server.hello` (server_version/agent_id/user_id/heartbeat_seconds) 즉시 송신 → 5초 내 `agent.hello` 수신 기대 → `last_seen_at` 갱신 → 이후 M2 까지 유휴.
- `packages/backend/app/main.py` [수정] — `ws` 라우터 include.
- `agent/ws_client.py` [신규] — `WebSocketClient` 데몬 스레드. 매 tick `AuthState.credentials` + `token_server_url` 매칭 확인 → `websockets.sync.client.connect` 로 `Authorization` 헤더 포함 연결 → `server.hello` 수신 + `agent.hello` 송신. 연결 유지 루프는 `recv(timeout=60)` 으로 keep-alive (WS protocol-level ping/pong 은 라이브러리가 자동 처리). `ConnectionClosed` 의 `rcvd.code` 가 4401/4403 이면 `on_unauthorized` 호출 + `_auth_blocked=True` 로 재연결 중단. 그 외 종료는 지수 백오프 1→60초로 재시도.
- `agent/agent_main.py` [수정] — `WebSocketClient` 생성 + `on_unauthorized=lambda: auth.handle_unauthorized(icon)` 연결, pinger 와 동일한 라이프사이클 (start / stop). Quit 핸들러도 ws_client.stop 추가.
- `agent/requirements.txt` — `websockets>=12.0` 추가 (sync API 용). agent venv 에 `websockets-16.0` 설치.

**로컬 e2e 검증** (SQLite + uvicorn :8765, raw `websockets.sync` 클라이언트):

| 시나리오 | 결과 |
|---|---|
| 헤더 없음 | 4401 `missing_token` close |
| `Bearer NOT_AG_PREFIX` | 4401 `malformed_token` close |
| `Bearer ag_BADBADBAD` | 4401 `invalid_token` close |
| 정상 연결 | `server.hello` 수신, `agent.hello` 송신, `last_seen_at` 0.93s 내 증가 확인 |
| 5초 내 `agent.hello` 미송신 | 4400 `no_agent_hello` close |
| DB revoke 후 재연결 | 4403 `token_revoked` close |

**WebSocketClient 통합 테스트**:

- 정상 토큰으로 `start()` → 3초 뒤 로그에 `ws connected` + `ws server.hello received` + `ws agent.hello sent` + `last_seen_at` 증가 확인.
- DB revoke 후 client 재시작 → 즉시 `rcvd_code=4403 reason='token_revoked'` → `on_unauthorized` 1회 호출 → `_auth_blocked=True` → 재연결 루프 진입 전 종료 → `auth_state.is_signed_in()==False`.

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (15:43).

**M1.5 완료 조건 체크** (실기 검증 포함):

- [x] `WS /v0/agent` Bearer 인증 + close code taxonomy (4400/4401/4403)
- [x] `server.hello` → `agent.hello` 핸드셰이크 + `last_seen_at` 갱신
- [x] `WebSocketClient` 재연결 백오프 + 4401/4403 시 auth_blocked
- [x] `AuthState.handle_unauthorized` 재사용 (HTTP pinger 와 동일 콜백)
- [x] 로컬 e2e 6 시나리오 + WebSocketClient 통합 테스트
- [x] 코어 회귀 25/25
- [x] Railway 자동 e2e: 4401 taxonomy 3 종 + happy (last_seen_at 06:51:24→27)
- [x] **실기 런타임** (HP-Laptop 16:44): `ws connected` / `server.hello received` / `agent.hello sent` 3 줄 + 기존 `ping ok (authenticated)` 병행 확인.

**M1.5 범위 밖**: `execution.*` 메시지 — M2. subprotocol 기반 auth (브라우저 WS) — 웹 UI 도입 시. 로컬 큐 + `last_event_id` 재동기화 — M2+.

## M1 전체 상태

M1.1 (Postgres 스키마) / M1.2 (Device Flow 서버) / M1.3 (Device Flow 에이전트) / M1.4 (Authenticated Ping) / M1.5 (WebSocket 핸드셰이크) — 모두 Railway 배포 + 에이전트 실기 검증 완료.

이로써 **M1 (인증·DB·실시간 통신) 전체 마무리**. 다음 마일스톤 **M2 (실제 RPA 실행 연결)** 로 진입 준비됨.

---

## 2026-04-23 (M1.4 구현·로컬 e2e) — Authenticated Ping (`GET /v0/agents/me`)

**설계**: [architecture/06-m1.4-authenticated-ping.md](architecture/06-m1.4-authenticated-ping.md) — Bearer dependency 설계, 401 taxonomy, 로그인·서버 mismatch 폴백 규칙.

**추가/수정된 코드** (스키마 변경 없음 — `agents.last_seen_at` 은 마이그레이션 0001 에 이미 존재):

- `packages/backend/app/dependencies.py` [신규] — `current_agent` Bearer dependency. `Authorization: Bearer ag_...` 파싱 → `hash_token` 으로 agents 조회 → `revoked_at` 체크. 실패마다 RFC 6750 스타일 401 + `WWW-Authenticate: Bearer error="..."`. 에러 코드 `missing_token` / `malformed_token` / `invalid_token` / `token_revoked`.
- `packages/backend/app/routers/agents.py` [신규] — `GET /v0/agents/me` (Bearer 전용). `last_seen_at = now()` 업데이트 + agent 기본 정보 반환. prefix `/v0/agents` 공유, 익명 경로는 기존 `device_flow.py` 에 그대로 유지.
- `packages/backend/app/main.py` [수정] — `agents` 라우터 include.
- `agent/agent_main.py` [수정] — `HealthPinger` 가 `auth_state` 참조 + `on_unauthorized` 콜백 보유. 매 tick 에 `AuthState.credentials` 확인, 있고 `token_server_url == server_url` 이면 `GET /v0/agents/me` + Bearer 헤더, 아니면 기존 `GET /healthz`. 401 수신 시 `on_unauthorized` 호출 → `AuthState.handle_unauthorized(icon)` → 인증 키 제거 + "Session expired" 풍선 알림 + 이후 tick 은 anonymous 폴백.

**로컬 e2e 검증** (SQLite, uvicorn :8765):

| 시나리오 | 결과 |
|---|---|
| `GET /v0/agents/me` 헤더 없음 | 401 `missing_token` |
| 스킴이 Bearer 가 아님 | 401 `missing_token` |
| `Bearer` 뒤 값 없음 | 401 `missing_token` |
| `Bearer NOT_PREFIXED` | 401 `malformed_token` |
| `Bearer ag_BADBADBAD` | 401 `invalid_token` |
| 정상 토큰 | 200, `name/hostname/platform/agent_version/last_seen_at` 반환 |
| 동일 토큰 1.2s 뒤 재호출 | `last_seen_at` 이 증가 (서버 시각) |
| DB 에서 `revoked_at = now()` 후 재호출 | 401 `token_revoked`, `WWW-Authenticate` 에도 동일 코드 |

**Agent 측 Pinger 통합 테스트**:

- 로그인 상태 + 서버 일치 → `authenticated` 경로 (`GET /v0/agents/me`) 선택, 200 로그.
- 서버가 토큰 revoke → 401 → `on_unauthorized` 콜백 1회 발화 → config.json 인증 키 5개 제거 → 다음 tick 은 `anonymous` (`/healthz`) 로 폴백, 신호 200.
- `creds.token_server_url` 이 현재 `server_url` 과 다르면 (예: 로컬 기동이지만 토큰은 Railway 에서 발급) → anonymous 폴백. 토큰이 엉뚱한 서버로 새 나가지 않도록 방어.

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (15:20).

**M1.4 완료 조건 체크** (실기 검증 포함):

- [x] Bearer dependency + 401 에러 taxonomy
- [x] `GET /v0/agents/me` 200 + `last_seen_at` 업데이트
- [x] Pinger 인증/익명 분기 + 401 자동 클리어
- [x] 서버 mismatch 시 anonymous 폴백
- [x] 로컬 e2e 전 시나리오
- [x] 코어 회귀 25/25
- [x] Railway `/v0/agents/me` 배포 후 자동 e2e (error taxonomy + happy + last_seen_at 증가)
- [x] **실기 런타임 3 갈래** (HP-Laptop, 15:30-31):
  - 재기동 시 `credentials loaded` → 1 tick 뒤 `ping ok (authenticated)` 200 (agent_id `89a3b150...`)
  - Sign Out → 다음 tick `ping ok (anonymous)` 즉시 폴백 (15:30:44)
  - 새 Sign In → 다음 tick 다시 `ping ok (authenticated)` 200 (새 agent_id `ec2052e2...`)

---

## 2026-04-23 (M1.3 구현·검증) — Agent 트레이 "Sign In" + Device Flow 클라이언트

**설계**: [architecture/05-m1.3-agent-device-flow-client.md](architecture/05-m1.3-agent-device-flow-client.md) — 클라이언트 흐름, 에러 매핑, `%APPDATA%\ohdo\config.json` 스키마, 완료 조건.

**추가/수정된 코드** (기존 core 수정 0):

- `agent/auth.py` [신규] — `DeviceCodeInfo`·`Credentials` 데이터클래스, `DeviceFlow*` 에러 계층, `start_device_flow` / `poll_for_token` / `load_credentials` / `save_credentials` / `clear_credentials`. FastAPI 의 `{"detail": {"error": "..."}}` 래핑·RFC 8628 의 `{"error": "..."}` 양쪽 파싱. `save_credentials` 는 원자적 교체(`.tmp`→replace)로 `server_url` 등 기존 키 보존.
- `agent/agent_main.py` [수정] — `AuthState` 클래스, `Sign In` / `Sign Out` 메뉴 (callable label + enabled), Device Flow 실행을 전담하는 `ohdo-device-flow` 데몬 스레드, `icon.notify` 래핑(`_safe_notify`), 기동 시 `auth.load_credentials()` → 없으면 WARN + setup 콜백에서 풍선 알림.

**로컬 e2e 검증** (Railway `https://ohdo-production.up.railway.app`, 실제 Postgres):

```
start_device_flow                        → user_code=45YW-U33W, expires_in=900, interval=5
direct POST device_token (unapproved)    → 400 {"detail":{"error":"authorization_pending"}}
poll with dev_NOT_VALID                  → DeviceFlowInvalid raised
stop_event cancel mid-poll               → DeviceFlowCancelled raised
happy path (/link/approve 시뮬 3s 후)    → Credentials(agent_token=ag_8JA..., agent_id=a6fdc2e2..., user_id=a075570c...)
save_credentials merge                    → config.json 에 server_url 보존 + 신규 키 5개 추가
device_code replay                       → DeviceFlowInvalid (consumed)
```

**단위 검증**:

- `load_credentials` — 빈/부분 누락/정상 세 케이스 모두 기대대로.
- `clear_credentials` — 인증 키 5개만 삭제, `server_url`·기타 키 보존.

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (2026-04-23 13:27).

**M1.3 완료 조건 체크** (실기 검증 포함):

- [x] `agent/auth.py` — 함수·데이터클래스·에러 계층 완비
- [x] 트레이 메뉴에 Sign In / Sign Out + 동적 enable 상태
- [x] Device Flow 진행 중 WebBrowser 열기 + 5초 간격 폴링
- [x] Railway 대상 happy path 토큰 수령 + config.json 저장 확인
- [x] 기존 `server_url` 등 비-인증 키 보존 (save merge)
- [x] Sign Out 시 인증 키 5개만 제거 (다른 키 보존)
- [x] 코어 회귀 25/25
- [x] **실기 Sign In** (user_code `NV24-56QK`, agent_id `ea2be8bf...`, user_id `b245302a...`, 13:35)
- [x] **실기 재기동 자동 로드** (`credentials loaded` INFO, 13:53)
- [x] **실기 Sign Out** (config.json `{agent_token, agent_id, user_id, token_server_url, signed_in_at}` → `{}`)

**실기 UX 이슈 (해결)**:

- 시스템 `python` 이 `C:\Program Files (x86)\Python38-32\python.exe` (오래된 3.8 32-bit, agent venv 아님) 를 가리켜 `python .\agent_main.py` 가 조용히 종료됨. → agent venv 의 python 을 **절대경로** 로 호출해야 함: `C:\Users\NeodaVinci\ohdo\agent\.venv\Scripts\python.exe ...agent_main.py`. 콘솔 없이 트레이만 띄우려면 `pythonw.exe` 바로가기.
- stderr 의 `Could not find platform independent libraries <prefix>` 경고는 venv 생성 경로 관련, 실행엔 무해.

**M1.3 범위 밖 (의도적 deferred)**:

- 이 토큰으로 ping/요청 인증 — M1.4 에서 `Authorization: Bearer`.
- WebSocket `/v0/agent` + `agent.hello` — M1.5.
- 인스톨러 재빌드 — M1.5 마무리 후 한꺼번에.

**다음 서브마일스톤**: **M1.4** — 기존 `HealthPinger` 를 인증 헤더 포함하도록 감싸고, 서버에 `/v0/agents/me` 같은 Bearer 전용 엔드포인트 추가해 토큰 유효성 확인.

---

## 2026-04-23 (M1.2 완료) — Railway 프로덕션에서 Device Flow 전 시나리오 통과

**배포 커밋**: `8fc311e` — `PUBLIC_BASE_URL` 미설정 시 Railway 가 자동 주입하는 `RAILWAY_PUBLIC_DOMAIN` 을 폴백으로 읽도록 수정. 이로써 **Railway Variables 수동 설정 없이** 바로 동작. 해석 우선순위: `PUBLIC_BASE_URL` → `RAILWAY_PUBLIC_DOMAIN` → `request.base_url`.

**Railway e2e 결과** (`https://ohdo-production.up.railway.app` 대상, 실제 Postgres):

| 단계 | 결과 |
|---|---|
| `POST /v0/agents/device_code` | 200, `verification_uri=https://ohdo-production.up.railway.app/link` |
| `POST /v0/agents/device_token` (승인 전) | 400 `authorization_pending` |
| `GET /link?code=...` | 폼 렌더 OK |
| `POST /link/approve` (stub email) | "기기가 연결되었습니다" 성공 페이지 |
| `POST /v0/agents/device_token` (승인 후) | 200, `agent_token` + `agent_id` + `user_id` 반환 |
| `POST /v0/agents/device_token` (재시도) | 400 `invalid_grant` (consumed) |
| 가짜 device_code | 400 `invalid_grant` |

Railway Postgres 에 실제 `users` 1개, `agents` 1개, `device_codes` 1건 생성 확인. 마이그레이션 0002 가 기동 시 자동 적용되는 것도 함께 검증됨.

**M1.2 완료 조건 최종**:
- [x] 마이그레이션 0002 — 로컬 SQLite + Railway Postgres 양쪽 적용
- [x] `POST /v0/agents/device_code` 200 + https 스킴
- [x] `GET /link?code=...` 렌더
- [x] `POST /link/approve` 성공 + DB 상태 변경
- [x] 승인 후 `device_token` 교환 → agent_token 발급
- [x] 재호출 `invalid_grant` (consumed)
- [x] 승인 전 폴링 `authorization_pending`

다음 서브마일스톤 **M1.3 (Agent 트레이 "Sign In" + Device Flow 클라이언트 + `config.json` 에 agent_token 저장)** 착수 가능.

---

## 2026-04-23 (M1.2 구현) — Device Flow 엔드포인트 + /link 브라우저 승인 페이지

**설계**: [architecture/04-m1.2-device-flow.md](architecture/04-m1.2-device-flow.md) — 3 엔드포인트 + device_codes 스키마 + "이메일 stub" 승인 흐름 결정 근거 (M1 범위 최소화, 이메일 소유 증명은 M2+ 매직링크로 이관).

**추가된 코드** (모두 `packages/backend/`, 기존 core 수정 0):

- `app/auth.py` — `generate_device_code` / `generate_agent_token` / `generate_user_code` / `normalize_user_code` / `hash_token`. token_urlsafe(32) 기반 opaque + SHA-256 해시.
- `app/models/device_code.py` + `models/__init__.py` 업데이트.
- `app/routers/device_flow.py` — `POST /v0/agents/device_code`, `POST /v0/agents/device_token`. RFC 8628 §3.5 에러 형식 (`authorization_pending` / `expired_token` / `invalid_grant` / `access_denied`).
- `app/routers/link.py` + `app/templates/{link.html, link_success.html}` — `GET /link?code=...` 자동 입력 폼 + `POST /link/approve` (email get-or-create + device_code approve).
- `app/main.py` — 라우터 2 개 include.
- `app/config.py` — `PUBLIC_BASE_URL`, `DEVICE_CODE_TTL_SECONDS`, `DEVICE_CODE_INTERVAL_SECONDS` 추가.
- `alembic/versions/20260423_0002_device_codes.py` — device_codes 테이블 + 3 인덱스.
- `requirements.txt` — `jinja2`, `python-multipart` 추가.

**로컬 e2e 검증** (SQLite):
```
POST /v0/agents/device_code → 200 {device_code, user_code: "9B3L-TPF6", ...}
POST /v0/agents/device_token → 400 {"error":"authorization_pending"}
GET  /link?code=9B3L-TPF6    → 200 (폼 렌더)
POST /link/approve (user_code, email) → 200 (성공 페이지) + users/device_codes 업데이트
POST /v0/agents/device_token → 200 {agent_token, agent_id, user_id}
POST /v0/agents/device_token → 400 {"error":"invalid_grant"}  # consumed 재사용 차단
```
DB 상태: 1 user + 1 agent row (`token_hash` 64 chars, `revoked_at=NULL`) + device_codes approved/consumed.

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (기존 core 변경 없으므로 예상된 결과).

**보안 메모 (stub 한계)**:
- /link/approve 가 이메일 소유 증명 없이 user 를 생성·매핑. `stub approval: ...` WARN 로그로 식별.
- CSRF 토큰·rate limit 부재 — M2+ 에서 보강.

**Railway 배포 전 확인 사항**:
- `alembic upgrade head` 이 기동 시 자동 실행되므로 Postgres 에 device_codes 가 생긴다.
- Railway Variables 에 `PUBLIC_BASE_URL=https://ohdo-production.up.railway.app` 을 설정해야 `verification_uri` 가 올바르게 발급된다. 미설정 시 `request.base_url` 폴백 사용 (프록시 뒤에서 `http://internal-host` 로 잘못 찍힐 위험).

**M1.2 완료 조건 체크**:
- [x] 마이그레이션 0002 — 로컬 SQLite 적용 확인
- [ ] Railway 재배포 → Postgres 에 device_codes 생성 확인 (다음 세션 또는 사용자 수동 확인)
- [x] `POST /v0/agents/device_code` 200
- [x] `GET /link?code=...` 렌더
- [x] `POST /link/approve` 성공
- [x] 승인 후 `POST /v0/agents/device_token` agent_token 반환
- [x] 재호출 `invalid_grant` (consumed)
- [x] 승인 전 폴링 `authorization_pending`
- [ ] 만료 device_code → `expired_token` (TTL 15 분이라 수동 테스트 대신 단위 테스트 추가 여지)

**다음 서브마일스톤 (M1.3)** 예정: Agent 트레이 메뉴 "Sign In" + `agent/auth.py` 클라이언트 + `%APPDATA%\ohdo\config.json` 에 `agent_token`/`agent_id` 저장.

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
