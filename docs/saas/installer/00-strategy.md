# 설치 프로그램 전략 (1차 스켈레톤)

- **상태**: Draft — 사용자 리뷰 대기
- **날짜**: 2026-04-22

## 1. 무엇을 설치하는가

SaaS 확장 후 Windows PC 에는 **두 가지 형태 중 하나 혹은 둘 다** 가 깔릴 수 있다.

| 배포 형태 | 구성 | 타깃 |
|---|---|---|
| **A. 풀 데스크톱 앱** (현재) | PyQt6 UI + core + 로컬 데이터 | 오프라인 파워유저, OSS 사용자 |
| **B. 경량 Agent 트레이** | core + agent runner + 트레이 아이콘, UI 없음 | SaaS 기본 배포 (웹에서 편집, 로컬에서 실행만) |

초기에는 A 와 B 를 **같은 인스톨러**에서 선택할 수 있게 하고, 나중에 사용자 피드백에 따라 분리 여부 결정.

## 2. 기술 스택 선정

### 2.1 Python 번들링 — PyInstaller

- 현재 `requirements.txt` 스택(PyQt6, pywinauto, pyautogui, uiautomation, Pillow 등)을 단일 EXE + 사이드 DLL 로 번들.
- `--onedir` 선호 (`--onefile` 은 첫 실행 속도 저하 + 안티바이러스 오탐 이슈).
- 대안 후보: Nuitka (더 빠른 런타임, 빌드 시간 김) / PyOxidizer (부트스트랩 복잡). **초기는 PyInstaller 로 시작**.

### 2.2 인스톨러 — Inno Setup

- Windows 11/10 호환, 라이선스 무료, 한국어 UI 리소스 내장, 코드 사이닝 지원.
- 스크립트 1개로 설치/제거/바로가기/자동 실행 등록이 모두 가능.
- 대안: WiX (MSI) — Windows Store / 그룹 정책 배포가 필요할 때. 현재는 과함.

### 2.3 자동 업데이트

- MVP: 기동 시 `GET /v0/agents/latest` 로 버전 확인 → 새 버전 있으면 다운로드 → 임시 디렉터리에 풀고 별도 updater.exe 가 교체 후 재기동.
- 검증: SHA-256 해시 + 배포용 인증서로 서명된 PE 만 허용.
- 라이브러리 재활용: [PyUpdater](https://www.pyupdater.org/) 는 유지보수 애매 → 자체 구현 권장 (코드 100줄 수준).

### 2.4 코드 사이닝

- 개인 개발자용: [SignPath](https://signpath.io/) 오픈소스 프로그램 (무료) 혹은 일반 EV 인증서 (연 $300 내외).
- 사이닝 없으면 Windows SmartScreen 경고가 떠서 설치율이 급감 — **베타 단계부터** 도입 권장.

## 3. 최소 스켈레톤 (Milestone 0)

> "빈 Agent 가 PC 에 깔리고 트레이에 떠서 서버에 ping 을 보낸다" — 이것만 되면 SaaS 설치/실행 경로가 검증된 것으로 본다.

1. `packages/agent/` (신규, 본 프로젝트 `agent/` 디렉터리) 에 최소 트레이 앱:
   - `pystray` + `Pillow` 로 트레이 아이콘 하나.
   - `httpx` 로 `GET https://api.ohdo.ai/v0/healthz` 를 30초마다 호출해 로그만 남김 (아직 WS 없음).
2. `packages/agent/build.spec` — PyInstaller 스펙 파일.
3. `installer/ohdo-agent.iss` — Inno Setup 스크립트.
4. GitHub Actions 워크플로우 `.github/workflows/build-agent.yml`:
   - `windows-latest` 러너에서 PyInstaller → Inno Setup 실행 → `ohdo-agent-setup-<ver>.exe` 업로드.
5. 릴리스 페이지에서 다운로드 → 설치 → 트레이 아이콘 확인 → 서버 로그에서 ping 확인.

**이 Milestone 0 에는 AppService/Storage 연결이 필요 없다.** 설치·분배·자동실행 경로만 검증. 그 다음 Milestone 에서 `core` 패키지와 실제 실행 연결.

## 4. 단계별 로드맵

| Milestone | 내용 | 선행 조건 |
|---|---|---|
| M0 | 빈 트레이 Agent + 설치/업데이트/헬스체크 | 서버에 `/healthz` 만 있으면 됨 |
| M1 | Device Flow 인증 + WS 연결 + `agent.hello` | 백엔드 FastAPI 스켈레톤 |
| M2 | `core` 번들링 → `execution.start` 수신 후 실제 워크플로우 실행 | `AppService.run_step` 경로 정리 완료 |
| M3 | 자동 업데이트 + 코드 사이닝 + 크래시 리포트(Sentry) | 베타 오픈 |
| M4 | 풀 데스크톱 앱 모드와 Agent 모드 통합 인스톨러 | 사용자 피드백 기반 |

## 5. 주의사항

- **Windows Defender 오탐**: PyInstaller + pyautogui 조합은 종종 "행위 기반" 오탐을 유발 → VirusTotal 등록 + 코드 사이닝 필수. MVP 중에는 "설치 시 경고가 뜰 수 있음" 안내 문구 추가.
- **관리자 권한**: 현재 workflow_engine 이 UIPI 우회용으로 관리자 권한을 요구할 수 있음 → 인스톨러는 비관리자 기본, Agent 실행 시 필요하면 UAC 프롬프트로 승격 요청.
- **DPI Awareness**: 기존 코드가 ctypes 로 DPI Awareness 를 설정하는데, 이 설정이 서비스(Windows Service) 모드에서는 다르게 동작 → 1차는 트레이 앱(일반 사용자 세션)만 지원, 서비스 모드는 차후.
- **경로 하드코딩**: `data/sessions/` 같은 경로를 현재 프로젝트 루트 기준으로 잡음. 설치 환경에서는 `%APPDATA%\ohdo\sessions\` 로 매핑되어야 함 → `core/storage/local_json.py` 가 `data_dir` 을 받도록 이미 설계되어 있어 OK (기존 SessionManager 도 동일 인자 지원).

## 6. 다음 결정

- [ ] M0 을 먼저 붙일지, 백엔드 FastAPI(M1) 와 동시에 진행할지.
- [ ] 코드 사이닝 방법 (SignPath OSS 신청 vs EV 인증서 구매) 결정.
- [ ] 데이터 저장 위치 표준 (`%APPDATA%\ohdo\` vs 프로젝트 상대 경로) — OSS 개발 환경에서 혼동 없도록 환경 변수로 분기.
