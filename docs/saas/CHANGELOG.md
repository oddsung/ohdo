# SaaS 확장 작업 CHANGELOG

각 세션별 작업을 시간 역순으로 1~3줄 요약. 상세 맥락은 해당 세션에서 만든 문서/파일로 연결.

---

## 2026-04-27 (M3.1.4 구현·로컬 e2e) — 웹 Cancel 버튼 + 신규 실행 폼

**설계**: [architecture/21-m3.1.4-cancel-and-new-execution.md](architecture/21-m3.1.4-cancel-and-new-execution.md) — 웹에서 직접 실행을 만들고 취소할 수 있게. 백엔드 POST /v0/executions 가 cookie 인증도 받고 agent 자동 선택. cancel 은 M3.1.3 의 current_subject 덕에 백엔드 변경 0.

**변경된 파일** (core 수정 0):

### 백엔드

- `packages/backend/app/routers/executions.py` [수정] — `create_execution` 의 dep 가 `current_agent` → `current_subject`. 인증 주체가 agent 면 `agent.id` 그대로 사용 (회귀 0). user 면 `Agent` 테이블에서 `user_id == subject.user_id AND revoked_at IS NULL` 중 `last_seen_at desc nulls last` 첫 row 선택. 없으면 400 `no_agent_available`. 이후 row insert / WS push 로직 동일.

### 웹

- `packages/web/components/cancel-button.tsx` [신규, client] — non-terminal 일 때만 표시. `window.confirm` → POST `/v0/executions/{id}/cancel` → 202 시 낙관적 hide + 1.5s 뒤 `router.refresh()` 로 헤더 status 갱신. 409/503/404/401 별 inline alert 메시지.
- `packages/web/components/new-execution-form.tsx` [신규, client] — session_id (text, optional, 비우면 `web-{Date.now()}`), requirements (multiline → split lines), steps 동적 리스트 (추가/제거, 최소 1 비어있지 않은 스텝 필수). 제출 → `apiFetch("/v0/executions", POST)` → 201 시 `router.push("/executions/[id]")`. 400 `no_agent_available` 안내 메시지 명시.
- `packages/web/app/executions/new/page.tsx` [신규] — 인증 가드 + `<NewExecutionForm>` 호스팅.
- `packages/web/app/dashboard/page.tsx` [수정] — 헤더 우측 `+ 새 실행` 링크 (Tailwind 직접, Button 컴포넌트 import 안 함).
- `packages/web/app/executions/[id]/page.tsx` [수정] — 헤더 layout 을 `flex items-start justify-between` 으로 바꿔 `<CancelButton>` 추가. CancelButton 은 status 가 terminal 이면 자동 null 반환.

**검증**:

- 백엔드 e2e (SQLite, uvicorn :8780) **5 시나리오** PASS:
  - C1 cookie + 1 agent → 201, 그 agent_id 사용
  - C2 cookie + 0 agent → 400 `no_agent_available`
  - C3 cookie + 2 agent (다른 last_seen_at) → 가장 최근 선택
  - C4 revoked agent 만 → 400
  - C5 Bearer agent → 자기 자신 사용 (회귀 0)
- 웹: `npm run typecheck` PASS / `npm run build` PASS (5 routes — `/executions/new` 추가됨).
- 코어 회귀 25/25 (19:42).

**M3.1.4 완료 조건 체크**:

- [x] POST /v0/executions current_subject + agent 자동 선택
- [x] 백엔드 e2e 5 시나리오
- [x] CancelButton + NewExecutionForm + /executions/new
- [x] 대시보드 + 새 실행 링크 + 상세 페이지 CancelButton 통합
- [x] typecheck + build PASS
- [x] 코어 회귀 25/25
- [ ] **브라우저 실기 검증** (M3.1.3 와 동일하게 dev 격리 이슈 — 사용자가 옵션 A 로컬 dev agent 띄우거나 M3.1.6 배포 후 자연 검증)

**M3.1.4 범위 밖**: 다중 agent 직접 선택 dropdown (M3.1.5+), 코드 에디터 syntax highlight (Monaco), 캡처 인라인 이미지 (M3.1.5), session JSON 임포트.

**Core 수정**: 없음.

---

## 2026-04-27 (M3.1.3 구현·로컬 e2e) — Executions 리스트·상세 페이지 + 합성 인증 dep

**설계**: [architecture/20-m3.1.3-executions-ui.md](architecture/20-m3.1.3-executions-ui.md) — 백엔드에 `current_subject` (쿠키 OR Bearer) 합성 dep 도입해 read-only 엔드포인트가 web/agent 양쪽에서 호출 가능. 웹은 dashboard 가 executions 리스트로 교체되고 `/executions/[id]` 상세 페이지가 추가됨. 진행 중인 실행은 3초 polling, terminal 도달 시 자동 정지.

**변경된 파일** (core 수정 0):

### 백엔드

- `packages/backend/app/dependencies.py` [수정] — `AuthSubject` dataclass (`user_id`, `agent_id`, `kind`) + `_try_cookie_user` / `_try_bearer_agent` silent helper + `current_subject` dep. 기존 `current_user`/`current_agent` 는 유지 (다른 라우터들과 write 라우터에서 사용 중).
- `packages/backend/app/routers/executions.py` [수정] — read-only 4 엔드포인트 (`GET /v0/executions/{id}`, `GET /v0/executions`, `GET /v0/executions/{id}/logs`, `POST /v0/executions/{id}/cancel`) 가 `current_subject` 사용. POST `/v0/executions` 는 `current_agent` 유지 (agent_id 가 row 에 박힘).
- `packages/backend/app/routers/captures.py` [수정] — `_fetch_owned_execution` 시그니처 `agent: Agent` → `user_id: uuid.UUID` 로 일반화. GET `/v0/executions/{id}/captures` + GET `/v0/captures/{id}` 가 `current_subject` 사용. POST `/v0/executions/{id}/captures` 는 `current_agent` 유지.

### 웹

- `packages/web/lib/format.ts` [신규] — `STATUS_STYLES`/`STATUS_LABELS`/`TERMINAL_STATUSES` + `formatDateTime`/`formatDuration`/`shortenExecId`.
- `packages/web/lib/executions.ts` [신규] — `serverFetch` 헬퍼 (cookies 자동 첨부) + `listExecutionsServer`/`getExecutionServer`/`listLogsServer`/`listCapturesServer` + Execution/LogEntry/Capture 타입.
- `packages/web/components/execution-status-badge.tsx` [신규] — Tailwind 색 배지.
- `packages/web/components/executions-list.tsx` [신규, client] — 상태 dropdown 필터 + "더 보기" 페이지네이션 (limit 20) + "새로고침" 버튼. apiFetch 로 `/v0/executions` 호출.
- `packages/web/components/execution-logs-tail.tsx` [신규, client] — 스트림 dropdown (전체/engine/stdout/stderr) + 3초 polling (status 가 non-terminal 일 때만) + 스트림별 색 (engine 회색 / stdout 검은색 / stderr 빨강) + 더 보기. 폴링 race 방지를 위해 tick 카운터로 stale response 무시.
- `packages/web/app/dashboard/page.tsx` [교체] — 헤더 + `<ExecutionsList>` 초기 데이터를 server-side fetch 로 prefetch.
- `packages/web/app/executions/[id]/page.tsx` [신규] — 상태 배지 + `error_summary` 강조 + 메타 카드 6개 (총 스텝 / 실행됨·성공·실패 / 총 소요 / 시작 / 종료 / from-to step) + LogsTail + Captures 메타 (count + step_id + size, 인라인 이미지는 M3.1.5).

**검증**:

- 백엔드 e2e (SQLite, uvicorn :8779) 8 시나리오 모두 PASS:
  - B1 쿠키 GET /executions → 200 + 자기 user_id 의 row 만
  - B2 쿠키로 다른 user 의 detail → 404
  - B3 Bearer GET /executions → 기존과 동일
  - B4 인증 없이 → 401 not_authenticated
  - B5 쿠키 사용자 POST cancel (자기 exec, agent offline) → 503 agent_offline
  - B6 쿠키 사용자 POST /v0/executions → 401 missing_token (current_agent 만 받음)
  - B7 쿠키 GET /logs → 200
  - B8 쿠키 GET /captures → 200 (path traversal regex 도 함께 검증됨)
- 웹: `npm run typecheck` PASS / `npm run build` PASS (4 routes: 정적 /sign-in, 동적 / /dashboard /executions/[id]).
- 코어 회귀 25/25 (18:59).

**M3.1.3 완료 조건 체크**:

- [x] AuthSubject + current_subject (cookie OR bearer)
- [x] 6 read-only 라우트 current_subject 적용 (write 2개는 current_agent 유지)
- [x] 백엔드 e2e 8 시나리오
- [x] 웹 lib/components/pages
- [x] typecheck + build PASS
- [x] 코어 회귀 25/25
- [x] Railway smoke (커밋 `6680249`) — 새 배포 활성화 후 unauth/bad-bearer 둘 다 `not_authenticated` (current_subject 적용 증거), 유효한 agent Bearer 로 GET /v0/executions 200 + M2.10 의 `exec_db547c8...` 정상 반환 (기존 agent 호환성 0 regression).
- [ ] **브라우저 실기 검증** — 사용자가 dashboard 에서 리스트 보기 → 상태 필터 → 상세 페이지 → 로그 polling → "더 보기"

**M3.1.3 범위 밖**: cancel 버튼 UI (M3.1.4), 신규 실행 폼 (M3.1.4), 캡처 인라인 이미지 (M3.1.5), Vercel 배포.

**Core 수정**: 없음.

---

## 2026-04-24 (M3.1.2 구현·로컬 스모크) — Next.js 대시보드 shell + 매직링크 sign-in

**설계**: [architecture/19-m3.1.2-web-scaffold.md](architecture/19-m3.1.2-web-scaffold.md) — `packages/web/` 신규. Next.js 16 + React 19 + Tailwind 3. 백엔드와 다른 포트지만 Next.js `rewrites` 로 `/v0/*` 와 `/auth/verify` 를 proxy 해 **브라우저 관점 same-origin** → CORS/쿠키 이슈 0. PUBLIC_BASE_URL 을 `http://localhost:3000` 으로 세팅하면 백엔드가 매직링크 URL 을 웹 도메인으로 출력.

**추가된 파일** (백엔드·core 수정 0):

- `packages/web/package.json` — next 16.2.4, react 19.2.5, typescript 5.6, tailwind 3.4.
- `packages/web/tsconfig.json` / `next.config.ts` / `postcss.config.mjs` / `tailwind.config.ts` — 설정 파일.
- `packages/web/app/globals.css` — Pretendard (jsdelivr CDN) + tailwind directive.
- `packages/web/app/layout.tsx` — `<html lang="ko">` + `font-sans` 루트 레이아웃.
- `packages/web/app/page.tsx` [server component] — `getCurrentUser()` 로 쿠키 확인 후 `/dashboard` 또는 `/sign-in` 으로 redirect.
- `packages/web/app/sign-in/page.tsx` [client component] — 이메일 입력 폼, POST `/v0/auth/magic-link`, 202/422/기타 상태별 메시지.
- `packages/web/app/dashboard/page.tsx` [server component] — getCurrentUser 재확인, 미인증이면 /sign-in redirect, 아니면 email/user_id/가입일 카드 + Logout 버튼.
- `packages/web/lib/api.ts` — `apiFetch<T>()` fetch 래퍼 (credentials:include, 204 처리).
- `packages/web/lib/auth.ts` — server-only `getCurrentUser()`. `cookies()` 로 `ohdo_session` 읽어 `/v0/users/me` 직접 호출 (same-process 에서 rewrite 말고 env `API_BASE_URL` 로 직통).
- `packages/web/components/ui/button.tsx` / `input.tsx` — 기본 스타일 래퍼 (shadcn 는 M3.1.3+).
- `packages/web/components/sign-out-button.tsx` [client] — POST `/v0/auth/logout` + window.location 으로 /sign-in 강제 네비게이션.
- `.gitignore` — `packages/web/node_modules`, `.next`, `out`, `next-env.d.ts`, `.env.local` 제외.

**검증**:

- `npm install` → 109 packages, **0 vulnerabilities**.
- `npm run typecheck` 통과.
- `npm run build` 통과 (static: /sign-in, /_not-found / dynamic: /, /dashboard).
- Dev server smoke:
  - `GET /` → `307 Location: /sign-in` (쿠키 없음 → getCurrentUser null → redirect)
  - `GET /sign-in` → `200 OK`
  - `POST /v0/auth/magic-link` (Next.js :3000 → rewrite → backend :8000) → `202 {email, expires_in: 900}`
  - 백엔드 로그에 **`[MAGIC LINK] http://localhost:3000/auth/verify?token=...`** (웹 도메인으로 링크 생성 확인)
- 코어 회귀 `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (16:54).

**M3.1.2 완료 조건 체크**:

- [x] Next.js scaffold + 빌드 성공 + typecheck 통과
- [x] 3 페이지 (`/`, `/sign-in`, `/dashboard`) + layout
- [x] rewrites proxy (v0 + auth/verify)
- [x] `lib/auth.ts` 서버 컴포넌트에서 `getCurrentUser()` 동작
- [x] 매직링크 URL 이 웹 도메인 (localhost:3000) 으로 출력되는 것 확인
- [x] 코어 회귀 25/25
- [ ] **브라우저 실기 검증** — 사용자가 실제 브라우저에서 sign-in → verify URL 클릭 → dashboard 진입 → Logout 전 사이클 확인 필요

**M3.1.2 범위 밖**: executions 리스트 (M3.1.3), cancel 버튼 (M3.1.4), 캡처 뷰어 (M3.1.5), Vercel 배포 (M3.1.6+), 프로필 편집, 회원가입 별도 flow.

---

## 2026-04-24 (M3.1.1 구현·로컬 e2e) — 웹 사용자 인증 (매직링크 + 세션 쿠키)

**설계**: [architecture/18-m3.1.1-web-auth.md](architecture/18-m3.1.1-web-auth.md) — 브라우저 사용자가 이메일로 로그인하고 httpOnly 쿠키로 세션을 유지. dev 에선 SMTP 대신 서버 로그에 verify URL stub. `current_agent` (Bearer ag_...) 와 완전 별개의 `current_user` (cookie sess_...) 의존성.

**변경된 파일** (core 수정 0):

- `packages/backend/app/models/user_session.py` [신규] — 세션 쿠키 메타. `token_hash` unique, `expires_at` (30일 fixed), `last_seen_at`, `revoked_at`.
- `packages/backend/app/models/magic_link.py` [신규] — 일회성 로그인 토큰. `email`, `token_hash` unique, `expires_at` (15분), `consumed_at`.
- `packages/backend/alembic/versions/20260424_0006_web_auth.py` [신규] — 두 테이블 + 인덱스 생성 (user_sessions 3개: user_id/token_hash unique; magic_links 2개: token_hash unique/email).
- `packages/backend/app/models/__init__.py` [수정] — 두 모델 export.
- `packages/backend/app/auth.py` [수정] — `SESSION_TOKEN_PREFIX = "sess_"`, `generate_session_token()`, `generate_magic_token()` 추가.
- `packages/backend/app/dependencies.py` [수정] — `SESSION_COOKIE_NAME = "ohdo_session"` 상수 + `current_user(request, session)` async dep. 쿠키 파싱 → token_hash 조회 → expires/revoked 체크 → `last_seen_at` 갱신. 실패 시 401 `not_authenticated` / `session_revoked` / `session_expired`.
- `packages/backend/app/routers/auth.py` [신규]:
  - `POST /v0/auth/magic-link {email}` → 202 + 서버 WARNING 로그에 `[MAGIC LINK] http://.../auth/verify?token=<raw>` 출력 (dev stub).
  - `GET /auth/verify?token=...` → token_hash 조회 → `users` get-or-create → `user_sessions` insert → `consumed_at` 세팅 → `Set-Cookie: ohdo_session=sess_...; HttpOnly; SameSite=Lax; Path=/; Max-Age=30d` → 302 `/`. 실패 시 400 `invalid_or_expired_token` / `missing_token`.
  - `POST /v0/auth/logout` → 세션 revoke + Set-Cookie Max-Age=0 → 204 (idempotent).
- `packages/backend/app/routers/users.py` [신규] — `GET /v0/users/me` (쿠키 인증, id/email/created_at 반환).
- `packages/backend/app/main.py` [수정] — 세 라우터 include.
- 이메일 validation: `re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")` 로 간단히 — `pydantic[email]` extra 없이 dep 최소.

**보안 결정**:
- `Secure` 플래그는 `OHDO_ENV=production` 일 때만. dev 는 HTTP 허용.
- `SameSite=Lax` + `HttpOnly` 로 CSRF/XSS 기본 방어. 별도 CSRF 토큰 없음 (MVP).
- 매직링크 TTL 15분 + 일회성 (`consumed_at`) 으로 replay 차단.
- 세션 TTL 30일 fixed. rolling 은 M3.1.3+ 에서.

**로컬 e2e 검증** (SQLite, uvicorn :8778, 쿠키 jar 보관 opener):

| # | 시나리오 | 결과 |
|---|---|---|
| S1 | `POST /v0/auth/magic-link {email}` | 202, `{email, expires_in: 900}` |
| S2 | DB 에 직접 magic_link row 생성 + raw 반환 (테스트 헬퍼) | OK |
| S3 | `GET /auth/verify?token=raw` (opener follows 302) | 200 at `/`, 쿠키 jar 에 `ohdo_session` 저장됨 |
| S4 | `GET /v0/users/me` (쿠키) | 200, `email` 일치 |
| S5 | DB row 검사 | user=1 / magic_links=2 (S1 + S2) / user_sessions=1 |
| S6 | 쿠키 없이 `/v0/users/me` | 401 `not_authenticated` |
| S7 | 잘못된 token 으로 verify | 400 `invalid_or_expired_token` |
| S8 | token 누락 verify | 400 `missing_token` |
| S9 | 이미 consumed 된 토큰 재사용 | 400 `invalid_or_expired_token` |
| S10 | `POST /v0/auth/logout` | 204 |
| S11 | 로그아웃 후 `/v0/users/me` | 401 |
| S12 | 잘못된 이메일 (`"not-an-email"`) 으로 magic-link | 422 pydantic validation |

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (16:34).

**M3.1.1 완료 조건 체크**:

- [x] 두 테이블 + 마이그 0006 (인덱스 5개)
- [x] 3 엔드포인트 (`/v0/auth/magic-link` / `/auth/verify` / `/v0/auth/logout`)
- [x] `current_user` dep (쿠키 기반, agent_id 스코프와 완전 분리)
- [x] `GET /v0/users/me` 기본 정보
- [x] 로컬 12 시나리오 통과
- [x] 코어 회귀 25/25
- [x] Railway e2e (커밋 `e8cf4f9`) — API 레벨 6 시나리오 (202 magic-link / 422 invalid email / 400 bad token / 400 missing token / 401 /me / 204 logout idempotent) 전부 통과. 0006 마이그가 Railway Postgres 에 정상 적용됨 확인. 실 verify + 쿠키 플로우는 로컬 12 시나리오에서 검증 완료 (raw 토큰은 서버 로그 내부에 있어 외부 e2e 불가, M3.1.2 브라우저 테스트로 완결 예정).

**M3.1.1 범위 밖**: 실 SMTP 이메일 (M3.2), rate limiting, CSRF 토큰, rolling 세션, 2FA/OAuth, 관리자 세션 revoke UI.

**Core 수정**: 없음.

---

## 2026-04-24 (M2.10 구현·로컬 e2e) — per-session `requirements` 자동설치 (v0.4.0)

**설계**: [architecture/17-m2.10-requirements.md](architecture/17-m2.10-requirements.md) — session_snapshot 의 `requirements: list[str]` 해석 → `%APPDATA%/ohdo/packages/<sha256>/` 에 `pip install --target` → `sys.path.insert` 코드 주입으로 격리 실행.

**변경된 파일** (core 수정 0):

- `agent/runner.py` [수정]:
  - `_BundleCodeSandbox.__init__` 에 `extra_syspath: list[str]` 추가. `execute()` override 로 user code 앞에 `import sys; sys.path.insert(0, <cache_dir>)` 자동 prepend. **PYTHONPATH env 를 쓰지 않아** 멀티 실행 race-free.
  - `_resolve_agent_appdata()` 신규 — agent_main 의 APPDATA 해석 동일 정책 (OHDO_APPDATA → APPDATA → ~/.ohdo).
  - `ExecutionRunner._ensure_requirements_installed()` 신규 — sha256 hash 로 디렉터리 이름 결정, `.ok` 마커로 캐시 히트 확인, pip stdout 을 execution.log stream=engine 으로 라인단위 스트리밍, 실패 시 RuntimeError.
  - `_run_execution_inner` 에 requirements 단계 삽입 (execution.accepted 직후). 설치 실패 시 engine 안 만들고 즉시 `execution.result(failed, error_summary="requirements install failed: ...")`.
- 버전 `0.3.1 → 0.4.0` (minor bump — 신규 기능).

**로컬 e2e 검증** (SQLite, uvicorn :8777, OHDO_APPDATA 를 `%TEMP%/ohdo_m210_<pid>` 로 격리):

| # | 시나리오 | 결과 |
|---|---|---|
| S1 | `requirements=["six"]` 첫 실행 | **4초** settled, status=completed, engine log 에 `installing...`/`pip:...`/`installed` 3 계열 전부, stdout `six.version= 1.17.0` |
| S2 | 같은 `["six"]` 로 2번째 실행 | **1초** settled, `cache hit: <digest>` 라인 + 설치 로그 없음 → 캐시 정상 |
| S3 | `requirements=["nonexistent-xyz-qqqq-pkg"]` | **3초** 만에 status=failed, `error_summary="requirements install failed: RuntimeError: pip install rc=1"`, stdout 비어있음 (step 미실행) |
| S4 | requirements 없음 | M2.9 회귀 0, install 로그 없음 |

**빌드** (v0.4.0):
- bundle `dist/ohdo-agent/` 150 MB (변동 없음 — 코드만 추가)
- `ohdo-agent-setup-0.4.0.exe` **45 MB**
- smoke: `version=0.4.0` 기동, ImportError 없음

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (16:00).

**M2.10 완료 조건 체크**:

- [x] session_snapshot `requirements` 필드 해석
- [x] sha256 content-addressed 캐시 + `.ok` 마커
- [x] pip stdout 을 execution.log stream=engine 으로 스트리밍
- [x] 설치 실패 시 status=failed + error_summary
- [x] `sys.path.insert` 주입으로 user code 가 설치 패키지 import 가능
- [x] requirements 없으면 기존 동작 (회귀 0)
- [x] 코어 회귀 25/25
- [x] **설치본 실기 e2e 완료 (2026-04-24 16:14~)** — HP-Laptop 에 0.4.0 설치 후 `{"requirements":["requests"]}` POST → 25초 내 `status=completed`, `total_time_ms=940`, engine 로그에 pip 설치 5 패키지 (urllib3/idna/certifi/charset_normalizer/requests) + `requirements installed: ...\packages\ec72420df5dfbdce`, stdout `requests 2.33.1`. 예: `exec_db547c8178b94cdf81b7ac6e33f88820`.

**Core 수정**: 없음.

**알려진 제약 (M3+ 이관)**:

1. 설치 중 cancel 지원 안 함. 설치 타임아웃 120초로 클램프.
2. 캐시 GC 없음 — 수동 정리 (`%APPDATA%\ohdo\packages\` 폴더 삭제).
3. requirements 에 로컬 경로·git URL 허용 여부는 보안 검토 후 결정.

---

## 2026-04-24 (M2.9.1 patch) — capture 업로드 복구 (v0.3.1)

**트리거**: 사용자 실기에서 0.3.0 설치본으로 `raise RuntimeError(...)` 스텝 실행 시 `/captures` 목록이 비어있음 확인. `pyautogui.size()` 등 user code 실행은 정상 (`real screen 1920x1080`) — M2.9 메인 기능은 작동. 캡처 파이프라인만 실패.

**원인**:
- `core._capture_error_screen` 은 **agent 프로세스** 에서 `import mss` 한다. 하지만 agent 런타임 번들 (ohdo-agent.exe 내부 파이썬) 에는 mss 가 없었음 (embedded python 쪽 mss 와 별개).
- 또 저장 경로도 `Path(__file__).parent.parent/data/sessions/...` 를 쓰는데 설치본은 Program Files 에 있어 쓰기 권한 이슈.
- 결과: `error_screenshot = None` → runner 의 업로드 분기 조용히 skip → 로그에 흔적 없음.

**수정** (core 수정 0):

- `agent/requirements.txt` — `mss>=10.0` 추가. agent venv 에도 설치 (`pip install mss`).
- `agent/build.spec` [수정] — hiddenimports 에 `"mss"` 추가. PyInstaller 가 PYZ 에 번들.
- `agent/runner.py` [수정]:
  - `_capture_desktop_png()` 신규 — agent 프로세스에서 mss 로 주모니터 PNG 캡처 → temp 파일 경로 반환. 실패 시 warn + None.
  - `on_step_complete` 의 캡처 업로드 경로 변경: `result.error_screenshot` 참조 제거, 대신 `_capture_desktop_png()` 직접 호출 → `_upload_capture` → `os.unlink` 정리.
  - `WorkflowEngine(screenshot_on_error=False)` — core 의 캡처 경로 비활성 (경로 이슈 + mss 미존재 이중문제 회피). `_capture_error_screen` 재정의·monkey-patch 없이 책임 분리.
- 버전 `0.3.0 → 0.3.1` 세 파일 동기화.

**빌드**:

- PYZ 에 `mss.*` 모듈 포함 확인 (TOC 에서 검증).
- bundle 150 MB 유지 (mss 자체는 67 KB).
- `ohdo-agent-setup-0.3.1.exe` **45 MB** (0.3.0 = 44 MB, +1 MB).
- bundle smoke: `version=0.3.1` 기동, ping/ws 정상, ImportError 없음.

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (15:41).

**사용자 재검증 완료 (2026-04-24)**:

```
execution_id: exec_ab4abf33066c44a58c3bbfddaaee38b2
step_id:      1
size_bytes:   276051   ← 270 KB 실제 HP-Laptop 스크린샷
content_type: image/png
```

HP-Laptop 에서 0.3.1 설치본 → `raise RuntimeError` 스텝 실행 → `POST /v0/executions/{id}/captures` 정상 → `GET /captures` 에 row 1개. M2.6 의 "monkey-patch 로만 검증" 제약 **실기에서 최종 해소**. M2 전체 + M2.9 체인 완전 종료.

**Core 수정**: 없음.

---

## 2026-04-24 (M2.9 빌드·번들) — embedded python + pip + 핵심 RPA 패키지 4종 (v0.3.0)

**설계**: [architecture/16-m2.9-python-packages.md](architecture/16-m2.9-python-packages.md) — A2 (핵심 4개 `pywinauto`/`pyautogui`/`selenium`/`mss`) + 빌드시점 설치 + `._pth` 자동편집. per-session requirements 자동화는 M2.10+ 로 이관.

**변경된 파일** (core 수정 0):

- `agent/scripts/fetch-embedded-python.ps1` [개편] — 기존 download+extract 뒤에 5단계 추가: `._pth` 에 `import site` 활성화, `get-pip.py` 로 pip 부트스트랩, `pip install pywinauto pyautogui selenium mss`, smoke test. idempotent.
- `agent/runner.py` [수정] — `_BundleCodeSandbox` 서브클래스 추가. `_install_missing_packages` 를 no-op 으로 재정의. 이유: 부모 CodeSandbox 는 `pkg_resources.working_set` 로 agent 프로세스 자신의 패키지를 보지만, 코드는 `python_exe` (embedded python) 에서 돌아가 두 목록이 다름. 매번 "누락됨→pip install" 노이즈 + ~500ms overhead 가 섞이던 것을 차단. 누락 패키지는 사용자가 ImportError 로 확인.
- `agent/__init__.py` / `agent/agent_main.py` / `installer/ohdo-agent.iss` [수정] — `0.2.0 → 0.3.0`.

**빌드 결과 (크기)**:

| 단계 | 용량 |
|---|---|
| `vendor/python/` (stdlib+pip+4 패키지) | 22 MB → **108 MB** |
| `dist/ohdo-agent/` 번들 | 57 MB → **150 MB** |
| `dist-installer/ohdo-agent-setup-0.3.0.exe` | 23 MB → **44 MB** (lzma 압축) |

설치할 수 있는 pro-grade RPA 툴 기준 허용범위.

**CodeSandbox 단위 검증** (`_BundleCodeSandbox` + bundle 내 python):

| # | 시나리오 | 결과 |
|---|---|---|
| S1 | `import pywinauto` | success, `pywinauto 0.6.9` |
| S2 | `pyautogui.size()` | success, `screen 1920x1080` (실제 해상도) |
| S3 | `from selenium import webdriver` | success, `selenium 4.43.0` |
| S4 | `mss().monitors` | success, `monitors=2` |
| S5 | **mss 로 실제 스크린샷 저장** | success, **`png_bytes 186013`** (M2.6 의 실 캡처 기능 활성화됨!) |
| S6 | stdlib | `{"py":[3,12,7]}` |
| S7 | 누락 패키지 `import nonexistent_pkg_xyz` | `ModuleNotFoundError` 로 clean 실패 |
| 노이즈 | stdout 에 "자동 설치" / "패키지를 발견" 문자열 | 0 (모든 케이스) |

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (10:59).

**M2.9 완료 조건 체크**:

- [x] fetch 스크립트가 pip + 4 패키지 설치
- [x] `._pth` 자동편집 (`import site`)
- [x] bundle 내 python 에서 4 패키지 전부 import 성공
- [x] `_BundleCodeSandbox` 로 auto-install 노이즈 0
- [x] **실제 스크린샷 mss 로 저장 확인** (M2.6 의 monkey-patch 제약 해소)
- [x] 버전 0.2.0 → 0.3.0 동기화
- [x] PyInstaller 150 MB, installer 44 MB 빌드
- [x] 누락 패키지는 ImportError 로 노출
- [x] 코어 회귀 25/25
- [ ] **설치본 실기 e2e** — 사용자가 `ohdo-agent-setup-0.3.0.exe` 설치 후 `import pyautogui; print(pyautogui.size())` 실행 시 `status=completed` 기대.

**알려진 제약 (M2.10+ 이관)**:

1. 번들 패키지 목록이 빌드 시점 고정. 사용자 추가 패키지는 session_snapshot `requirements` 필드 + runtime install 필요 (M2.10).
2. Chrome/Edge WebDriver 바이너리 미포함 — selenium 실 실행엔 OS 측 드라이버 필요. `webdriver-manager` 도입 검토.
3. pywinauto `SyntaxWarning: invalid escape sequence` 는 upstream 이슈.

**Core 수정**: 없음.

---

## 2026-04-24 (M2.8 빌드·번들) — Agent 에 Python 3.12 Embedded 동반 (v0.2.0)

**트리거**: M2.7 실기에서 확인된 3중 문제 — `sys.executable == ohdo-agent.exe` 때문에 `CodeSandbox.subprocess.Popen(...)` 이 (a) user code 가 아닌 트레이 앱을 spawn, (b) 60초 timeout 으로 모든 실행이 `failed`, (c) child agent 가 server registry 를 하이재킹해 cancel/기타 WS push 가 부모에 닿지 못함.

**설계**: [architecture/15-m2.8-embedded-python.md](architecture/15-m2.8-embedded-python.md) — Windows embeddable Python 3.12.7 (~22 MB) 을 PyInstaller datas 로 번들에 동반. runner 가 `sys._MEIPASS/python/python.exe` 를 resolve 해 `CodeSandbox(python_exe=...)` 에 주입. dev run 폴백은 `sys.executable`.

**변경된 파일** (core 수정 0):

- `agent/scripts/fetch-embedded-python.ps1` [신규] — python.org 공식 embeddable zip (3.12.7) 다운로드 + `agent/vendor/python/` 에 추출. 재실행 시 idempotent.
- `.gitignore` [수정] — `agent/vendor/` 추가 (22 MB 바이너리 제외).
- `agent/build.spec` [수정] — `EMBED_PY_DIR` 존재 검증 + `datas=[(str(EMBED_PY_DIR), "python")]` 로 번들에 동반. PyInstaller 는 `_internal/python/` 에 복사.
- `agent/runner.py` [수정]:
  - `from core.workflow_engine import CodeSandbox, WorkflowEngine` (CodeSandbox 추가).
  - `_resolve_python_exe()` 신규 — `sys._MEIPASS/python/python.exe` 우선, fallback `sys.executable`.
  - `_run_execution_inner` 에서 `WorkflowEngine(sandbox=CodeSandbox(python_exe=_resolve_python_exe()), ...)` 로 명시 주입.
- `agent/__init__.py` / `agent/agent_main.py` / `installer/ohdo-agent.iss` [수정] — `0.1.0 → 0.2.0`.

**빌드 검증**:

- `scripts/fetch-embedded-python.ps1` — Python 3.12.7 22 MB 추출 확인.
- `pyinstaller build.spec --clean --noconfirm` 성공. `dist/ohdo-agent/` 34 MB → **57 MB** (+23 MB, embedded python).
- Bundle 내부 python.exe 직접 실행: `py: 3.12.7 exe: ...\_internal\python\python.exe` 정상.
- `dist-installer/ohdo-agent-setup-0.2.0.exe` **23 MB** (이전 0.1.0=14 MB, +9 MB).

**CodeSandbox 실기 증명** (bundle 내 embedded python 을 `python_exe` 로 직접 주입):

| # | 시나리오 | 결과 |
|---|---|---|
| S1 | `print('hello from embedded python')` | `success=True`, 46 ms, output 일치 |
| S2 | `raise RuntimeError('boom-m28')` | `success=False`, error 에 `RuntimeError: boom-m28` |
| S3 | stdlib import (`import json, sys`) | success + `{"ok":true,"py":[3,12,7]}` |
| S4 | `time.sleep(10)` 중 `sandbox.stop()` | **1.5 초 내 kill 반영** → M2.5 cancel 이 설치본에서도 작동할 근거 |

**Smoke (bundle exe 기동, 격리 appdata)**:

```
ohdo agent starting: version=0.2.0 ...
ws client starting: url=wss://ohdo-production.up.railway.app/v0/agent
ping ok (anonymous): .../healthz status=200 elapsed=766ms
```

ImportError 없음. 재귀 spawn 흔적 없음.

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (10:00).

**M2.8 완료 조건 체크**:

- [x] embeddable zip fetch 스크립트 + .gitignore
- [x] build.spec datas 에 vendor/python 포함
- [x] runner 가 `_resolve_python_exe` 경로 주입
- [x] 버전 0.1.0 → 0.2.0 세 파일 동기화
- [x] PyInstaller 빌드 성공 + _internal/python/python.exe 존재
- [x] Inno Setup → ohdo-agent-setup-0.2.0.exe (23 MB)
- [x] CodeSandbox via embedded python 단위 검증 (성공·실패·kill 전부)
- [x] 코어 회귀 25/25
- [x] **설치본 실기 e2e 완료 (2026-04-24)** — HP-Laptop 에 `ohdo-agent-setup-0.2.0.exe` 설치 후:
  - mid-run cancel 시나리오 (`exec_f05fd719e66344c9bb0b36ceabd891f8`): **`status=cancelled`**, `total_time_ms=2663` (M2.7 의 `60030` timeout 아님), `error_summary` null, `executed_steps=1` (subprocess 실제 시작 증거), `started_at → finished_at` 2.7초.
  - → M2.7 의 3중 버그 (재귀 spawn / 60초 timeout / registry 하이재킹) **전부 해소** 확인.

**알려진 제약 (M2.9+ 이관)**:

1. **stdlib 한정** — pip 미포함. `import pywinauto` 등 3rd-party 는 ImportError. 실제 RPA 시나리오에는 ensurepip + per-session venv 필요 (M2.9).
2. `mss` 미포함 — 실제 화면 스크린샷은 None 반환. M2.6 캡처 파이프라인은 여전히 monkey-patch 로만 검증됨.

**Core 수정**: 없음.

---

## 2026-04-24 (M2.7 빌드·번들) — Agent PyInstaller 에 `core.workflow_engine` 포함 + Inno Setup 재빌드 (v0.1.0)

**설계**: [architecture/14-m2.7-agent-bundle-core.md](architecture/14-m2.7-agent-bundle-core.md) — `pathex` 에 프로젝트 루트 추가, `core.workflow_engine` 을 hiddenimports 로 명시, runner 가 쓰지 않는 core 모듈 전부 excludes (트랜지티브로 PyQt6 등 딸려오는 것 차단). 설치본 실기 검증 (device_flow → execution lifecycle → capture 전체) 은 **사용자가 별도 시점에 수행**.

**변경된 파일** (core 수정 0):

- `agent/build.spec` [수정] — `PROJECT_ROOT = AGENT_ROOT.parent`, `pathex=[AGENT_ROOT, PROJECT_ROOT]`, hiddenimports 에 `"core"` / `"core.workflow_engine"` 추가, excludes 에 `core.adapters`·`core.ai_engine`·`core.app_service`·`core.environment_scanner`·`core.execution_kernel`·`core.import_manager`·`core.kernel_worker`·`core.prompt_builder`·`core.session_manager`·`core.storage`·`core.visual_overlay`·`core.win_inspector` 명시 제외.
- `agent/__init__.py` / `agent/agent_main.py` [수정] — `__version__ = "0.1.0"` (M2 전체 묶음 의미).
- `agent/installer/ohdo-agent.iss` [수정] — `MyAppVersion = "0.1.0"`.

**빌드 검증**:

- `pyinstaller build.spec --clean --noconfirm` 성공. `PYZ-00.toc` 에 `('core.workflow_engine', ...agent/../core/workflow_engine.py, ...)` 확인.
- `dist/ohdo-agent/` 총 용량 34 MB (변동 없음 — workflow_engine 자체는 28 KB stdlib only).
- `dist-installer/ohdo-agent-setup-0.1.0.exe` 14.2 MB (이전 0.0.1 = 13.8 MB, +430 KB).

**Smoke test (번들 exe 기동)**: `OHDO_APPDATA=/tmp/...` 로 격리 기동. 로그에 다음 전부 출력 + ImportError 없음:

```
ohdo agent starting: version=0.1.0 server=https://ohdo-production.up.railway.app
no credentials found - Sign In required
pinger started: url=https://... interval=30s
ws client starting: url=wss://ohdo-production.up.railway.app/v0/agent
ping ok (anonymous): .../healthz status=200 elapsed=1000ms
```

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (06:59).

**알려진 제약 (M2.7 에서 문서화만, 수정은 후속)**:

1. `CodeSandbox` 가 `sys.executable` 을 subprocess 로 호출. 번들 실행 시 `sys.executable == ohdo-agent.exe` 가 되어 **Agent 가 재귀 실행** → M2.8+ 에서 embedded python 동반 혹은 시스템 Python 탐지 필요.
2. `mss` 는 agent/requirements.txt 에 없음 → `screenshot_on_error=True` 지만 실제 스크린샷은 None 반환 + warn (core 로직). 업로드 파이프라인은 monkey-patch 테스트로 이미 검증. 실 캡처 활성화는 후속.

**M2.7 완료 조건 체크**:

- [x] build.spec 에 core.workflow_engine 번들 포함 + 미사용 core 모듈 excludes
- [x] 버전 0.0.1 → 0.1.0 세 파일 동기화
- [x] PyInstaller 빌드 성공 + PYZ 에 core.workflow_engine 수록 확인
- [x] 번들 exe smoke (version=0.1.0 기동, ws client starting, ping ok (anonymous), ImportError 없음)
- [x] Inno Setup 으로 `ohdo-agent-setup-0.1.0.exe` 재빌드
- [x] 코어 회귀 25/25
- [ ] **설치본 실기 e2e** — 사용자가 별도 시점에 수행 예정 (device_flow → Sign In → 간단 실행 · cancel · 캡처 업로드 확인). 위의 "알려진 제약 1" 때문에 실 RPA 코드는 실패 가능하지만 device flow / WS 핸드셰이크 / 로그·캡처 파이프라인 자체 검증까지는 가능.

**Core 수정**: 없음.

## M2 전체 ✅ 완료 (2026-04-24 빌드 측면)

M2.1 executions 스키마 / M2.2 REST / M2.3 WS lifecycle / M2.4 로그 스트리밍 / M2.5 cancel / M2.6 캡처 업로드 / M2.7 번들 확장 — 모두 로컬 + Railway e2e 통과 (M2.7 은 설치본 실기는 사용자 검증 대기). 백엔드 Railway 배포 유지. Agent `v0.1.0` 번들 + 인스톨러 준비.

다음 마일스톤: **M2.8** 또는 **M3 (결제/요금제 or 웹 UI)** — ROADMAP 재점검 필요.

---

## 2026-04-23 (M2.6 구현·로컬 e2e) — 캡처 업로드 + `execution_captures` + FS 저장

**설계**: [architecture/13-m2.6-captures-upload.md](architecture/13-m2.6-captures-upload.md) — 로컬 파일시스템 기반 (`packages/backend/data/captures/{execution_id}/{capture_id}.{ext}`), multipart REST 업로드 (pre-signed URL 은 S3/R2 전환 시 도입 예정), agent 가 step 실패 시 자동 업로드, WS `execution.capture` 프레임은 범위 밖. 사용자 결정 9항목 반영.

**추가/수정된 코드** (core 수정 0):

- `packages/backend/app/models/execution_capture.py` [신규] — `ExecutionCapture` 모델. `id` (capture_id), `execution_id` FK CASCADE, `step_id`, `kind` (`error_screenshot` default), `storage_key`, `content_type`, `size_bytes`, `created_at`.
- `packages/backend/alembic/versions/20260423_0005_execution_captures.py` [신규] — 테이블 + FK + 인덱스. upgrade/downgrade.
- `packages/backend/app/models/__init__.py` [수정] — `ExecutionCapture` 등록.
- `packages/backend/app/routers/captures.py` [신규] — 두 라우터:
  - `exec_captures` (prefix `/v0/executions`): `POST /{execution_id}/captures` (multipart, 201, 415/413/400/404 taxonomy) + `GET /{execution_id}/captures` (list).
  - `cap_router` (prefix `/v0/captures`): `GET /{capture_id}` (바이너리 다운로드, user_id 스코프 join, 410 Gone if FS miss).
  - 상수: `CAPTURE_ROOT = packages/backend/data/captures`, `MAX_CAPTURE_BYTES=10MB`, allowed content_types = `image/png|jpeg`, `_EXECUTION_ID_RE = ^exec_[a-f0-9]{32}$` path traversal 방어.
- `packages/backend/app/main.py` [수정] — captures 라우터 2개 include.
- `agent/runner.py` [수정]:
  - `WorkflowEngine(screenshot_on_error=True)` 로 복귀 (M2.3 에서 False 였음).
  - `set_http_context(server_url, auth_state)` 메서드 추가.
  - `on_step_complete` 내에서 `result.error_screenshot` 이 존재하면 `_upload_capture` 호출.
  - `_upload_capture`: httpx.post multipart → 201 로그, 실패 조용히 swallow.
- `agent/agent_main.py` [수정] — runner 생성 뒤 `runner.set_http_context(server_url, auth)` 추가.

**로컬 e2e 검증** (SQLite, uvicorn :8776, `WorkflowEngine._capture_error_screen` 을 monkey-patch stub 으로 대체):

| # | 시나리오 | 결과 |
|---|---|---|
| S1 | 실패 스텝 1개 → 자동 업로드 | 1 capture, step_id=1, image/png, **size_bytes=105 정확히 매치** |
| S2 | `GET /v0/captures/{id}` 다운로드 | 200, bytes 동일, `content-type: image/png` |
| S3 | 다른 user 가 download/list 시도 | 404 `capture_not_found` / `execution_not_found` |
| S4 | unauth download | 401 `missing_token` |
| S5 | 성공 스텝만 | 캡처 0 row |
| S6 | `text/plain` 업로드 시도 | 415 `unsupported_content_type` |
| S7 | 10MB 초과 PNG 업로드 | 413 `file_too_large` |
| S8 | `execution_id=not_an_exec_id` | 404 (regex validation) |

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (22:11).

**M2.6 완료 조건 체크**:

- [x] `execution_captures` 테이블 + 마이그 0005 (FK CASCADE + index)
- [x] `POST /v0/executions/{id}/captures` multipart + 타입/크기 검증
- [x] `GET /v0/executions/{id}/captures` list (limit/offset/step_id 필터)
- [x] `GET /v0/captures/{id}` 바이너리 다운로드 (user_id join 권한 + 410 Gone fallback)
- [x] agent 자동 업로드 (on step failure, screenshot_on_error=True 복귀)
- [x] user 스코프 격리 + taxonomy (401/404/413/415)
- [x] 코어 회귀 25/25
- [x] Railway e2e (커밋 `940ce54`) — wss + REST 파이프라인 통과. `RuntimeError('rail-boom')` 실패 스텝에서 monkey-patched PNG (101 bytes) 업로드 → `GET /captures/{id}` 로 다운로드 바이트 일치 확인. 415/401 taxonomy 동일 동작. 예: `capture_id=6ecc59e2-2223-4683-a39d-f0fbadb336c4`, execution=`exec_5aec92b1...`.

**M2.6 범위 밖**: 실제 S3/R2 전환, `execution.capture` WS 프레임, 사용자 수동 캡처, 썸네일.

**Railway 제약 (명시)**: 컨테이너 파일시스템 ephemeral — 재배포 시 캡처 바이너리 소실 (메타 row 는 남지만 `GET /v0/captures/{id}` 는 410 `capture_bytes_missing`). **운영 전 S3/R2 교체 필수**.

**Core 수정**: 없음. `screenshot_on_error` + `StepResult.error_screenshot` 은 이미 public 인터페이스.

---

## 2026-04-23 (M2.5 구현·로컬 e2e) — `execution.cancel` + mid-step subprocess 종료

**설계**: [architecture/12-m2.5-execution-cancel.md](architecture/12-m2.5-execution-cancel.md) — REST `POST /v0/executions/{id}/cancel` → WS `execution.cancel` push → agent 가 `engine.stop()` + `sandbox.stop()` 으로 subprocess 즉시 kill → `execution.result(status='cancelled')` 송신으로 확정. 에러 taxonomy (404/409/503/401). 사용자 결정 7항목 반영.

**추가/수정된 코드** (core 수정 0):

- `packages/backend/app/routers/executions.py` [수정] — `POST /{execution_id}/cancel` 엔드포인트 추가. user_id 스코프 조회 → terminal 게이트 (409 `already_terminal`) → `registry.get(agent_id)` 체크 (503 `agent_offline`) → WS 프레임 push → 202. row status 는 여기서 바꾸지 않음 (agent 가 execution.result 로 확정).
- `agent/runner.py` [수정] — `handle_frame` 이 `execution.cancel` 도 dispatch. `_active_engines: dict[exec_id, WorkflowEngine]` + `_cancelled: set[exec_id]` + `_active_lock` 추가. `_handle_cancel_frame` 이 cancel flag 세팅 + `engine.stop()` + `engine.sandbox.stop()` 호출. `_run_execution_inner` 에서 engine 등록·해제, 실행 종료 후 `_pop_cancelled` 결과에 따라 final_status 를 `cancelled` 로 덮어쓰고 error_summary 는 None 으로 세팅. engine 예외 경로에서도 동일 처리.

**로컬 e2e 검증** (SQLite, uvicorn :8775):

| # | 시나리오 | 결과 |
|---|---|---|
| S1 | 20 tick / 0.5s 스텝 2초 실행 후 cancel | `202 accepted` → **1초 내** `status=cancelled`, `executed_steps=1`, `error_summary=None`, `finished_at` 세팅 |
| S2 | 이미 cancelled 된 execution 을 다시 cancel | 409 `already_terminal`, `status=cancelled` |
| S3 | 다른 user 의 execution 을 cancel 시도 | 404 `execution_not_found` (존재 여부 누설 방지) |
| S4 | 에이전트 오프라인 (ws.stop) 상태에서 cancel | 503 `agent_offline` |
| S5 | unauth cancel | 401 `missing_token` |
| S6 | 존재하지 않는 execution_id cancel | 404 `execution_not_found` |

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (21:42).

**M2.5 완료 조건 체크**:

- [x] `POST /v0/executions/{id}/cancel` (Bearer) + taxonomy (404/409/503)
- [x] WS `execution.cancel` 프레임 push
- [x] agent 가 `engine.stop()` + `sandbox.stop()` 조합으로 subprocess 즉시 terminate
- [x] `execution.result(status='cancelled')` 송신 + 서버 반영
- [x] 코어 회귀 25/25
- [x] Railway e2e (커밋 `c3314af`) — S1 (`range(30)` 반복 tick 실행 중 cancel → 1초 내 `status=cancelled`, `error_summary=None`) / S2 (이미 terminal → 409 `already_terminal`) / S3 (ws.stop 후 → 503 `agent_offline`) 전부 wss 에서 통과.

**M2.5 범위 밖**: 타임아웃 기반 강제 cancelled 확정 (agent 응답 없을 시) → M2.6+. 웹 UI 취소 버튼 → Phase 3.

**Core 수정**: 없음. `WorkflowEngine.stop()` + `CodeSandbox.stop()` 모두 기존 public 메서드 사용. **ADR 0001 4조건 미발동**.

---

## 2026-04-23 (M2.4 구현·로컬 e2e) — `execution.log` 스트리밍 + `execution_logs` 테이블 + 노이즈 필터

**설계**: [architecture/11-m2.4-execution-log.md](architecture/11-m2.4-execution-log.md) — 테이블 스키마 (`execution_logs` = id/execution_id/seq/step_id/stream/line/created_at, FK CASCADE), 프레임 스펙 (`entries[]` 배치), agent 쪽 버퍼링 (`_LogBuffer` + seq monotonic), 3-stream 분류 (`stdout/stderr/engine`), noise filter 정규식, error_summary 재구성 로직. 사용자 결정 8항목 반영.

**추가/수정된 코드** (core 수정 0):

- `packages/backend/app/models/execution_log.py` [신규] — `ExecutionLog` 모델. `execution_id` Text FK (executions.execution_id unique → ondelete CASCADE). 3 인덱스 (`execution_id` / `(execution_id, seq)` / `stream`).
- `packages/backend/alembic/versions/20260423_0004_execution_logs.py` [신규] — 테이블 + FK + 3 인덱스. downgrade 대칭.
- `packages/backend/app/models/__init__.py` [수정] — `ExecutionLog` 등록.
- `packages/backend/app/routers/ws.py` [수정] — `execution.log` 프레임 핸들러 추가 (`_handle_log`). entries 배열 bulk insert, agent_id 소유 검증, stream 허용 목록 검증, 라인 길이 4000자 서버 clamp. 터미널 상태 이후 수신도 거부 안 함 (지연 flush 수용).
- `packages/backend/app/routers/executions.py` [수정] — `ExecutionLogEntry` / `ExecutionLogsResponse` 스키마, `GET /v0/executions/{execution_id}/logs` (user_id 스코프, limit 500/max 2000, offset, stream/step_id 필터, `seq ASC + created_at ASC` 정렬, 잘못된 stream 은 400 `invalid_stream_filter`, 다른 user 의 id 는 404 `execution_not_found`).
- `agent/runner.py` [수정] — `_LogBuffer` (monotonic seq, thread-safe append/drain), stderr 노이즈 정규식 필터 (`Could not find platform independent libraries`, `Consider setting $PYTHONHOME`), 엔진 `on_log` 훅 추가, `on_step_start` 로 현재 step_id 추적, `on_step_complete` 에서 stdout/stderr 분해 후 progress 송신 + 로그 flush, 실행 종료 직전 최종 flush. error_summary 재구성: 실패 step 의 필터된 stderr 중 `^[A-Za-z_]\w*(Error|Exception|Warning): ` 매치되는 라인을 우선 (traceback 마지막 줄), 없으면 첫 라인.

**로컬 e2e 검증** (SQLite, uvicorn :8774, 실제 `ws_client` + `runner`):

| # | 시나리오 | 결과 |
|---|---|---|
| S1 | 1 step multi-line stdout (`print('line1')\nprint('line2')`) | `status=completed`, logs 6 개 (stdout 2 + engine 4). stdout 라인 그대로 보존. |
| S2 | 2 steps mixed (2번째 `raise RuntimeError('boom-m24')`) | `status=failed`, **`error_summary='step 2: RuntimeError: boom-m24'`** (M2.3 의 Python 런치 노이즈 사라짐). stderr 4 개 = Traceback 전체 필터 통과 라인. |
| S3 | `GET .../logs?step_id=1` | step_id 1 만 반환 (stdout 'ok-before' 포함). |
| S4 | `GET .../logs?stream=stdout` | stdout stream 만. |
| S5 | `GET .../logs?stream=nope` | 400 `invalid_stream_filter`. |
| S6 | 다른 user 의 agent 로 `GET .../logs` | 404 `execution_not_found`. |
| S7 | unauth `GET .../logs` | 401 `missing_token`. |
| 노이즈 필터 | exec2 stderr 로그에 `Could not find platform independent libraries` 라인 0 개 | ✅ 필터 동작. |
| DB count | exec2 의 logs 18 rows (engine + stderr) | agent 배치 전송 정상. |

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (21:27).

**M2.4 완료 조건 체크**:

- [x] `execution_logs` 테이블 + 마이그레이션 0004 (upgrade/downgrade, 인덱스 3개, FK CASCADE)
- [x] WS `execution.log` 핸들러 (agent_id 소유 검증 + bulk insert)
- [x] `GET /v0/executions/{id}/logs` (user_id 스코프 + limit/offset/stream/step_id 필터)
- [x] agent 로그 버퍼링 + per-step flush + 종료 직전 final flush
- [x] stderr 노이즈 필터 (Windows Python 런치 잡음 2 패턴)
- [x] error_summary 재구성 — M2.3 의 "step 2: Could not find..." → "step 2: RuntimeError: boom-m24"
- [x] 코어 회귀 25/25
- [x] Railway e2e (커밋 `eab1c01`) — warm-up 1회 재시도 후 안정. S1 (stdout 2줄 + engine 4줄 persist), S2 (`error_summary='step 2: RuntimeError: rail-boom'` 깔끔하게 정제 + stderr 에 노이즈 라인 0개), S3 (step_id=1 필터) 전부 통과. wss Postgres e2e 확인.

**M2.4 범위 밖**: `execution.cancel` → `WorkflowEngine.stop()` (M2.5), S3/R2 업로드 (M2.6), 실시간 tail / SSE (웹 UI 단계), 페이지네이션 커서.

**Core 수정**: 없음. `WorkflowEngine.execute_session()` 의 기존 `on_log`/`on_step_start`/`on_step_complete` 콜백만 이용.

---

## 2026-04-23 (M2.3 구현·로컬 e2e) — WS `execution.start/.accepted/.progress/.result` + 첫 실제 실행

**설계**: [architecture/10-m2.3-execution-lifecycle.md](architecture/10-m2.3-execution-lifecycle.md) — 프레임 스펙, 서버 상태 머신 (`queued → accepted → running → completed|failed`), agent_id 소유 검증, offline 시 queued 유지 정책. 사용자 결정 7항목 반영.

**추가/수정된 코드** (core 수정 0):

- `packages/backend/app/registry.py` [신규] — `{agent_id: WebSocket}` 단순 레지스트리. 동일 agent 이중 연결 시 "나중 연결 win", unregister 는 현재 ws 와 일치할 때만.
- `packages/backend/app/routers/ws.py` [수정] — handshake 성공 후 `registry.register` 호출, 수신 루프를 `receive_text + json.loads` 로 변경해 `_route_agent_frame` 로 dispatch. 핸들러 3개 (`execution.accepted`/`.progress`/`.result`) 각각 상태 전이 규칙 + `agent_id` 소유 검증. finally 에서 unregister.
- `packages/backend/app/routers/executions.py` [수정] — `create_execution` 이 row insert 후 `registry.get(agent.id)` 로 WS 확인 → `execution.start` 프레임 push. 오프라인이면 로그만 남기고 queued 유지.
- `agent/ws_client.py` [수정] — `frame_handler` 콜백 파라미터 추가. `_connect_once` 에서 활성 소켓 기록 (`self._ws` + `_send_lock`). `send_frame(frame)` 메서드로 외부에서 스레드 안전 송신. `stop()` 이 flag 만 세팅 → 활성 소켓 즉시 close (테스트 분리 + 실무 정상 종료). receive 루프가 JSON 파싱 후 `frame_handler` 로 위임.
- `agent/runner.py` [신규] — `ExecutionRunner` 클래스. `execution.start` 를 받으면 워커 스레드 spawn → `accepted` 송신 → `SimpleNamespace` 로 session 감싸 → `WorkflowEngine(visual_feedback_enabled=False, screenshot_on_error=False)` 생성 → `asyncio.run(engine.execute_session(on_step_complete=...))`. `on_step_complete` 에서 `.progress` 송신, 종료 후 `.result`. 예외/엔진 실패 모두 `failed` result 로 커버. 같은 `execution_id` 중복 실행 방지 lock.
- `agent/agent_main.py` [수정] — `ExecutionRunner` 인스턴스 생성 + `WebSocketClient(frame_handler=runner.handle_frame)` + `runner.set_sender(ws_client.send_frame)`.

**로컬 e2e 검증** (SQLite, uvicorn :8773, 실제 `ws_client.WebSocketClient` + `runner.ExecutionRunner` 를 별도 프로세스 아닌 테스트 드라이버 프로세스에서 기동):

| 시나리오 | 결과 |
|---|---|
| S1 (스텝 1개 `print('hello')`) | `status=completed`, executed=1, successful=1, total_time_ms 기록, started_at/finished_at 둘 다 세팅 |
| S2 (스텝 2개, 2번째 `raise RuntimeError`) | `status=failed`, executed=2, successful=1, failed=1, `error_summary` 채워짐 (step 2 에 해당) |
| S3 (agent offline, WS 연결 없음) | POST 201 후 DB 는 `queued` 유지, executed/started_at 모두 None |
| S4 (`from_step=2, to_step=2` 슬라이스) | 가운데 성공 스텝만 실행되어 `completed`, executed=1 |
| Ownership guard (B 에이전트가 A 의 execution_id 에 `execution.accepted` 보내기 시도) | 서버가 `agent_id` 불일치로 거부 → A 의 row 는 `queued` 유지 |

**회귀 테스트**: `python -m tests.test_runner --suite core` → **25 passed / 0 failed** (21:04).

**M2.3 완료 조건 체크**:

- [x] Registry register/unregister + 같은 agent 재연결 handling
- [x] WS 수신 루프 JSON 파싱 + 3 프레임 타입 dispatch
- [x] `agent_id` 소유 검증 (거부 시 조용히 무시 + WARN)
- [x] 상태 전이 (`queued → accepted → running → completed|failed`) + 터미널 재수신 무시
- [x] Offline agent POST → `queued` 유지
- [x] `from_step`/`to_step` 슬라이싱
- [x] 엔진 예외 시 `execution.result` status=failed + error_summary 커버
- [x] 코어 회귀 25/25
- [x] Railway e2e (커밋 `88e460b` 반영 후) — 단일 wss 연결로 S1 (성공) / S2 (mixed 실패) / S3 (from_step/to_step 슬라이스) / S4 (offline → queued 유지) 모두 1~6초 안에 settled. 예: `exec_b0ec86e6...` status=failed + executed=2 + failed_steps=1. 새 배포 감지용 probe 는 2번째 시도에서 completed 로 전환 (첫 번째는 wss 핸드셰이크 + 배포 타이밍).

**M2.3 범위 밖**: `.log` 스트리밍 (M2.4), `execution.cancel` (M2.5), 스크린샷 업로드 (M2.6), offline catchup (M2.4+), stderr 노이즈 필터 (Windows Python launch noise `Could not find platform independent libraries` 가 error_summary 첫 줄을 점유 — M2.4 에서 `.log` 도입과 함께 개선).

**Core 수정**: 없음. `WorkflowEngine.execute_session()` 의 기존 `on_step_complete` 콜백만 이용. ADR 0001 4조건 미발동.

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
- [x] Railway e2e (커밋 `9636382`) — device_code → /link/approve → device_token → POST execution → GET detail + LIST + status filter, 전부 200/201. 응답의 `created_at='2026-04-23T11:38:02.150258Z'` (TZ-aware, Postgres `timestamptz`) 확인 = **M2.1 0003 row-level 검증 동반 완료**. 생성된 execution_id=`exec_9162adfa11e241e4ae6b8bfda8821faa`.

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
