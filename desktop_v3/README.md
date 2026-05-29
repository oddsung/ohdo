# ohdo desktop_v3 (Electron + React + TS)

TS UI v3 트랙 (handoff §37). Discord-like 데스크톱 UX 를 목표로 하는 새 UI 레이어.
기존 Python `core/` 와 PySide6 (`ui/`, `ui_v2/`) 는 **건드리지 않는다** — 이 앱은
localhost FastAPI 브리지(`api_server/`) 를 통해 core 로직을 호출만 한다.

## 아키텍처

```
Electron Renderer (React+TS)  ──HTTP/WS──>  Python FastAPI (127.0.0.1:<port>)
                                                    └──> AppService ──> core/*
Electron Main (Node)  ──spawn──>  python -m api_server   (자식 lifecycle 소유)
```

- **포트**: main 이 빈 포트를 골라 `--port` 로 전달. Python 이 실제 바인딩한 포트를
  stdout `OHDO_API_READY {json}` 한 줄로 보고 → main 이 확정.
- **인증**: main 이 random 토큰 생성 → `OHDO_API_TOKEN` env 로 Python 에 주입 →
  preload(`window.ohdo.getApiInfo()`) 를 통해 renderer 가 받아 `Authorization: Bearer` 헤더로 사용.
- **종료**: app `before-quit` → SIGTERM → 5s 후 SIGKILL.

## 개발 실행

전제: 프로젝트 루트에서 `uv sync` 로 `.venv` + `fastapi`/`uvicorn` 설치 완료.

```powershell
cd desktop_v3
npm install        # 최초 1회 (node_modules 는 .gitignore)
npm run dev        # electron-vite dev — Python 브리지 자동 spawn
```

- Python 실행 파일은 기본적으로 `..\.venv\Scripts\python.exe` 를 사용.
  다른 인터프리터를 쓰려면 `OHDO_PYTHON` env 로 override.
- 패키징 환경에서는 `OHDO_PROJECT_ROOT` 로 프로젝트 루트를 지정.

### 문제 해결

**`Error: Electron uninstall`** (dev 실행 시) — `npm install` 의 Electron postinstall
(`install.js`)이 zip 다운로드는 받았지만 **압축 해제(extract-zip) 단계가 조용히 실패**해서
`node_modules/electron/dist/` 에 `locales/` 만 남고 `electron.exe` 가 없는 상태
(`require('electron')` 가 실재하지 않는 경로를 반환 → electron-vite 가 "uninstall" 판정).

`npm rebuild electron` 은 깨진 캐시를 그대로 재사용하므로 무효일 수 있다. 캐시에 받아둔
zip 을 직접 풀어 복구:

```powershell
$zip = "$env:LOCALAPPDATA\electron\Cache\*\electron-v*-win32-x64.zip"
$dist = ".\node_modules\electron\dist"
Remove-Item $dist -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $dist | Out-Null
Expand-Archive -Path (Resolve-Path $zip) -DestinationPath $dist -Force
Set-Content ".\node_modules\electron\path.txt" "electron.exe" -NoNewline
```

확인 (※ `ELECTRON_RUN_AS_NODE` env 가 1 이면 Node 버전이 찍히니 해제 후):
`.\node_modules\electron\dist\electron.exe --version` → `v38.8.6`.

## 빌드 / 타입체크

```powershell
npm run typecheck  # tsc --noEmit
npm run build      # electron-vite build → out/
```

## 구조

```
desktop_v3/
├── electron.vite.config.ts    # main/preload/renderer 3-타깃 빌드
├── tailwind.config.js         # Discord 팔레트 (다크)
├── src/
│   ├── main/index.ts          # Python spawn + 포트/토큰/lifecycle + BrowserWindow
│   ├── preload/index.ts       # contextBridge: window.ohdo.getApiInfo()
│   └── renderer/
│       ├── index.html
│       └── src/
│           ├── App.tsx        # Discord-like 3-column 셸 + 세션 목록
│           ├── api/client.ts  # fetch + Bearer 토큰
│           └── store/uiStore.ts  # Zustand
```

## API 엔드포인트 (api_server)

| 메서드 | 경로 | 설명 | 인증 |
|---|---|---|---|
| GET | `/health` | 브리지 readiness | 불필요 |
| GET | `/sessions` | 세션 목록 | Bearer |
| GET | `/sessions/{id}` | 세션 상세 (steps 포함) | Bearer |
| POST | `/sessions` | 새 세션 생성 | Bearer |
| POST | `/sessions/{id}/generate` | 자연어 → AI 코드 생성 (element_context 첨부 가능) | Bearer |
| PUT | `/sessions/{id}/steps/{step}` | step 코드 편집 저장 | Bearer |
| POST | `/pick` | 커서 위치 UI element 캡처 (Windows) | Bearer |
| WS | `/ws/execute` | step 실행 + live 로그 스트리밍 | 쿼리 토큰 |
| WS | `/ws/generate` | AI 코드 생성 진행상황 스트리밍 | 쿼리 토큰 |
| POST | `/sessions/{id}/recording/start` | 작업 녹화 시작 (Windows) | Bearer |
| GET | `/recording/status` | 녹화 상태 (is_recording, event_count) | Bearer |
| POST | `/recording/marker` | step 경계 구분점 추가 | Bearer |
| POST | `/sessions/{id}/recording/stop_commit` | 녹화 종료 + step 추가 | Bearer |
| POST | `/recording/cancel` | 녹화 취소 (저장 안 함) | Bearer |

WS 메시지: `{type:"log"|"step_done"|"done"|"error", ...}`. 클라이언트 → `"stop"` 로 중단.
쿼리: `session_id`, `mode`(all/from/single), `step_id`, `token`.

## 단축키

- **Ctrl/Cmd+R**: 전체 실행 / 실행 중이면 중단
- **Ctrl/Cmd+N**: 새 세션
- **Esc**: 요소 선택 카운트다운 취소
- **Enter** (입력창): 전송, **Shift+Enter**: 줄바꿈

## Phase 진행 (handoff §37~§40)

- **A. 셋업** ✅ — 보일러플레이트 + 브리지 + 세션 목록 (§38).
- **B. 핵심 화면 MVP** (진행 중):
  - ✅ AI 생성 루프 + shadcn/ui + Monaco (§39).
  - ✅ #1 실행 + live 로그 (WS) / #2 코드 편집·저장 / #3 element picker (카운트다운) /
    #4 polish (토스트·단축키·테마 토글) (§40).
  - ✅ 작업 녹화 lifecycle (start/marker/stop_commit/cancel + status polling) (§41).
  - 잔여: 녹화 review/편집 (현재는 stop 시 바로 commit).
- **C. 통합 기능** — picker/실행/녹화 완료, review·고급 옵션 후속.
- **D. Polish** — i18n + 애니메이션 (단축키·테마는 §40 선반영).
- **E. 배포** — electron-builder.
