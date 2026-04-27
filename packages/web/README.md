# ohdo-web

ohdo.ai 의 사용자 대시보드 (Next.js 16 + React 19 + Tailwind 3).

## 로컬 개발

두 터미널 필요. 백엔드는 별도로 띄워야 함.

```powershell
# 터미널 A — backend (FastAPI)
cd ..\backend
$env:PUBLIC_BASE_URL = "http://localhost:3000"   # 매직링크 URL 이 web 도메인으로 출력되도록
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --log-level info

# 터미널 B — web (Next.js)
cd packages\web
npm install                # 첫 1회만
npm run dev                # http://localhost:3000
```

기본 `API_BASE_URL=http://localhost:8000` 사용. 다른 backend 를 보려면
`.env.local` 에 `API_BASE_URL=...` 추가.

### 매직링크 로그인

1. 브라우저: http://localhost:3000 → /sign-in 으로 자동 redirect
2. 이메일 입력 → "로그인 링크 받기"
3. **터미널 A** 의 backend 로그에서 다음 라인 찾기:
   ```
   [MAGIC LINK] dev stub — deliver this to user a@b.com:
   http://localhost:3000/auth/verify?token=...
   ```
4. URL 을 브라우저에 붙여넣기 → /dashboard 진입

## 빌드 & 검증

```powershell
npm run typecheck     # tsc --noEmit
npm run build         # Next.js production build
```

## 프로덕션 배포 (Vercel)

상세 가이드: [docs/saas/architecture/23-m3.1.6-vercel-deploy.md](../../docs/saas/architecture/23-m3.1.6-vercel-deploy.md)

요약:

1. https://vercel.com → New Project → GitHub `oddsung/ohdo` import
2. **Root Directory**: `packages/web`
3. **Environment Variables**: `API_BASE_URL=https://ohdo-production.up.railway.app`
4. Deploy → URL 메모
5. Railway 대시보드 → Variables → `PUBLIC_BASE_URL=https://<vercel-url>` 추가
6. (권장) Railway → `OHDO_ENV=production` 추가 (secure cookie 활성)

배포 후 Vercel URL 에서 매직링크 sign-in → dashboard → 실 데이터 표시까지 동일 흐름.

## 구조

```
app/
├── globals.css                  # Pretendard + Tailwind directives
├── layout.tsx                   # 루트 레이아웃
├── page.tsx                     # / — 쿠키 → /dashboard or /sign-in redirect
├── sign-in/page.tsx             # client, 매직링크 요청 폼
├── dashboard/page.tsx           # server, executions 리스트 + 신규 실행 링크
└── executions/
    ├── new/page.tsx             # server, NewExecutionForm 호스트
    └── [id]/page.tsx            # server, 메타 + 로그 + 캡처 그리드 + Cancel

components/
├── ui/{button,input}.tsx
├── execution-status-badge.tsx
├── executions-list.tsx          # client, 필터 + 더보기 + 새로고침
├── execution-logs-tail.tsx      # client, 3s polling
├── captures-grid.tsx            # client, 인라인 PNG + 410 fallback
├── cancel-button.tsx            # client, confirm + POST cancel
├── new-execution-form.tsx       # client, session_id + reqs + steps
└── sign-out-button.tsx          # client

lib/
├── api.ts                       # client fetch wrapper (credentials: include)
├── auth.ts                      # server-only getCurrentUser (next/headers cookies)
├── executions.ts                # server fetch helpers + 타입
└── format.ts                    # 상태 색·duration·시각 포맷
```

## 동작 원리 (요약)

- 모든 API 호출은 `/v0/*` 경로로 → [next.config.ts](next.config.ts) 의 `rewrites` 가 backend 로 server-side proxy
- 브라우저는 항상 web origin 만 봄 → CORS 불필요, 쿠키 자동 첨부
- 매직링크 verify 도 `/auth/verify` 로 proxy → 쿠키가 web origin 에 묶임
- Server Components 는 `next/headers` 의 `cookies()` 로 직접 backend 호출 (rewrites 우회)
