# devloop — desktop_v3 자율 테스트-개발 루프

`desktop_v3`(Electron 앱)를 **외부에서** 빌드·기동하여 Playwright E2E 로 검증하고, 실패를
분석해 `claude --print` 로 자율 수정한 뒤 재테스트하는 루프. desktop_v3 와 **완전히 독립**된
별도 모듈이다(자체 `package.json`/`node_modules`, desktop_v3 빌드·의존성에 끼어들지 않음).

## 루프 흐름

```
[빌드] → [E2E] ─ 통과? ─ 예 → (자율모드면) 다음 개선 구현+E2E추가 → 반복
                        └ 아니오 → 실패 분석 → claude 수정 → 커밋 → 반복
```

각 iteration 은 전용 브랜치 `devloop/auto-<runId>` 에 커밋되어 언제든 롤백 가능하다.

## 안전 모델

- **전용 브랜치에서만 작동** — `main`/`master` 직접 수정·푸시 절대 안 함(코드 레벨 가드).
- 시작 시 baseline 커밋 → iteration 마다 커밋 → `git reset --hard <sha>` 로 임의 지점 복구.
- **circuit breaker**: 동일 실패 시그니처가 N회(기본 3) 연속되면 중단.
- 최대 반복(기본 20), 비용 상한(`--max-cost`), `--dry-run`.
- `--push` 일 때만 전용 브랜치를 origin 에 백업(main 은 제외).

## 사전 조건

- Windows + Node.js + Python(루트 `.venv`) + `claude` CLI 로그인 완료.
- `desktop_v3` 의존성 설치됨(`cd desktop_v3 && npm install`) — electron 바이너리 재사용.

## 설치 / 실행

```bash
cd devloop
npm install
npx playwright install            # (Electron 테스트엔 브라우저 불필요하나, 최초 1회 권장)

# 흐름만 확인 (아무것도 안 고침)
npm run loop:dry

# 실제 루프 (수정만, 자율개발 OFF)
npm run loop

# 완전 자율 (테스트 통과 후 다음 개선까지 스스로) + 전용 브랜치 푸시
npm run loop -- --autonomous --push --max-features 3
```

### 주요 옵션

| 옵션 | 설명 | 기본 |
|------|------|------|
| `--dry-run` | 앱·claude·git 미접촉 시뮬레이션 | off |
| `--max-iterations N` | 최대 반복 | 20 |
| `--max-repeated-failures N` | 동일 실패 N회 시 중단 | 3 |
| `--autonomous` | 통과 후 자율 개선 | off |
| `--max-features N` | 자율 개선 상한 | 3 |
| `--max-cost USD` | 누적 비용 상한(0=무제한) | 0 |
| `--push` | 전용 브랜치 origin 푸시 | off |
| `--no-build` | E2E 전 빌드 생략 | (빌드함) |
| `--permission-mode MODE` | claude 권한 모드 | acceptEdits |
| `--model NAME` | claude 모델 | (CLI 기본) |

> **권한 모드**: 기본 `acceptEdits` 는 파일 편집만 무인 허용한다. claude 가 타입체크/빌드 등
> 명령까지 무인으로 돌리게 하려면 `--permission-mode bypassPermissions` 를 쓴다(전용 브랜치라
> 영향은 격리되지만, claude 가 임의 명령을 실행할 수 있으니 주의).

## 산출물

- `runs/<runId>/run.json` — 단일 실행 기록
- `runs/loop-history.json` — 전체 실행 누적
- `runs/<runId>/loop.log` — 실행 로그
- `runs/last-playwright.json` — 최근 Playwright 리포트

(모두 `.gitignore` 대상 — 소스만 추적)

## 구조

```
devloop/
├── src/
│   ├── orchestrator.ts     # 메인 루프 제어 + circuit breaker
│   ├── config.ts           # 옵션 파싱
│   ├── app-controller.ts   # desktop_v3 빌드/사전점검
│   ├── test-runner.ts      # Playwright 실행 + 리포트 정규화
│   ├── result-analyzer.ts  # 실패 → 시그니처 + 후보파일
│   ├── context-builder.ts  # 수정 프롬프트 조립
│   ├── claude-bridge.ts    # claude --print 호출 + 변경 감지
│   ├── next-step-advisor.ts# 자율 개선 프롬프트/호출
│   ├── git-safety.ts       # 브랜치/커밋/푸시 가드
│   ├── history.ts          # 실행 이력
│   ├── logger.ts / paths.ts / types.ts
├── tests/e2e/              # Playwright-Electron 스펙
└── CLAUDE.md               # 루프가 claude 호출 시 주는 작업 컨텍스트
```
