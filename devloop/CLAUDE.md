# devloop — 자율 테스트-개발 루프 (claude 작업 컨텍스트)

이 파일은 **devloop 루프가 `claude --print` 로 너(Claude)를 호출했을 때** 참고하는 컨텍스트다.
즉, 너는 지금 "ohdo desktop_v3 의 완성도를 높이는 자율 수정/개발자" 역할이다.

## 무엇을 고치는가

- **대상**: `desktop_v3/`(Electron + React + TypeScript) + `api_server/`(Python FastAPI 브리지) + 필요 시 `core/`.
- **목표**: `devloop/tests/e2e/` 의 Playwright E2E 가 통과하도록, 그리고 앱의 완성도가 올라가도록 제품 코드를 고친다.

## 아키텍처 (요약)

- `desktop_v3` Electron main(`src/main/index.ts`)이 `python -m api_server` 를 spawn → `OHDO_API_READY {port,token}` 핸드셰이크 → BrowserWindow 로드.
- 렌더러(React)는 preload 가 노출한 `window.ohdo.getApiInfo()` 로 `{baseUrl, token}` 을 받아 HTTP/WS 로 백엔드와 통신.
- E2E 는 `electron-vite build` 산출물(`desktop_v3/out/main/index.js`)을 그대로 띄워 검증한다.

## 절대 규칙 (위반 금지)

1. **`devloop/src/` 하네스 로직을 수정하지 마라.** (루프 자체를 망가뜨림)
2. **E2E 스펙(`devloop/tests/e2e/`)을 삭제·skip·약화시켜 통과시키지 마라.** 테스트는 의도된 검증이다.
   - 단, **자율 개선(advance)** 요청일 때만 새 기능을 검증하는 E2E 스펙을 `devloop/tests/e2e/` 에 **추가**하는 것은 허용된다.
3. **`core/`, `ui/`, `ui_v2/` 의 PySide6(v2) 동작을 깨지 마라.** api_server 는 core 의 public API 만 호출한다.
4. `legacy_pyqt6/` 는 건드리지 마라(deprecated).
5. 비밀키·토큰·민감정보를 코드/로그에 남기지 마라.

## 코딩 규약

- Python: `ruff` (line-length 100, `E/F/W/I`). 루트 `pyproject.toml` 기준. 한국어 주석 OK.
- TypeScript: strict. `desktop_v3` 에서 `npm run typecheck` 통과 필수(TS 변경 시).
- 커밋은 devloop 루프가 대신 한다 — 너는 파일만 고치면 된다.
- 변경은 **최소·근본적**으로. 무관한 리팩터링/포매팅 금지.

## 검증 방법 (네가 직접 돌릴 수 있다면)

- TS 타입체크: `desktop_v3` 에서 `npm run typecheck`
- Python lint: 루트에서 `uv run ruff check .`
- (E2E 전체 재실행은 루프가 담당하므로 너는 안 해도 된다)

## 핸드오프

프로젝트의 결정 이력은 `docs/handoff.md`(§N 형식)에 있다. 큰 구조 변경 시 참고.
