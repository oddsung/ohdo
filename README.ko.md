# ohdo

[![CI](https://github.com/oddsung/ohdo/actions/workflows/ci.yml/badge.svg)](https://github.com/oddsung/ohdo/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/oddsung/ohdo)

> **Windows 를 위한 AI 네이티브 RPA** — LLM 과 대화로 **순수 Python** 자동화 코드를 만들고, 로컬에서 실행. 클라우드 락인 없음.

🌐 **English README**: [README.md](README.md)

---

## ohdo 는 무엇인가

ohdo 는 *"메모장 열고 '안녕' 입력해줘"* 같은 자연어 요청을
[`pywinauto`](https://github.com/pywinauto/pywinauto) / [`pyautogui`](https://pyautogui.readthedocs.io/) /
[Selenium](https://www.selenium.dev/) Python 스크립트로 **단계별로** 변환하는 데스크톱 채팅 앱입니다.
각 step 은 카드로 관리되어 편집·재실행·삭제 가능. 결과물은 자체 실행 가능한 Python 프로젝트 — 벤더 종속 바이너리가 아닙니다.

## 왜 ohdo 인가

| | ohdo | UiPath / Power Automate | Claude Computer Use |
|---|---|---|---|
| **결과물** | 🟢 순수 Python (`pywinauto`/Selenium) — git 커밋 / IDE 편집 / 이식 가능 | 🔴 XAML (벤더 락인) | 🟡 매 실행마다 vision action (재사용 산출물 없음) |
| **비용 모델** | 🟢 Step 빌드할 때 1회 LLM 호출, 이후 영구 오프라인 실행 | 🔴 봇/사용자당 라이선스 ($1K-$5K/yr) | 🔴 매 실행마다 Vision API 비용 |
| **결정성** | 🟢 Selector 기반 코드 = 재현 가능 | 🟢 Selector 기반 | 🔴 매번 다른 경로 |
| **오프라인 실행** | 🟢 빌드 후 네트워크 불필요 | 🟡 Orchestrator 의존 | 🔴 항상 클라우드 |
| **컴플라이언스** | 🟢 Local-first (화면 프레임 외부 송출 X) | 🟡 벤더 처리 | 🔴 화면 내용 API 송출 |
| **타깃 사용자** | Python 읽을 수 있는 개발자 | 비개발자 (시민 개발자) | 누구나 (그러나 비싸고 불투명) |

ohdo 는 **자기 niche 에 정직**합니다: *개발자 친화적, 코드 우선* RPA 대안.
비개발자용 no-code RPA 가 필요하면 UiPath / Power Automate 가 더 적합.
한 번에 자연어로 자동화하는 게 우선이면 Computer Use 가 더 유연.
**Inspectable + 이식 가능 + 반복 가능한 Python** 을 step-by-step 빌드 루프로 만들고 싶다면 ohdo 입니다.

경쟁 분석 (ohdo 의 약점 포함) 자세히 보기: [`docs/commercial_review.md`](docs/commercial_review.md).

## 핵심 기능

- **자연어 → Python 코드** — 요청 → 실제 `pywinauto`/`pyautogui`/Selenium 코드 생성 → 편집 → 실행
- **Step 카드 워크플로우** — 매 step 카드, 누적 코드 유지, 개별 재실행 가능
- **Element 픽** — 화면 위젯 클릭으로 selector 코드 자동 생성 (데스크톱 UIA / Selenium 자동 분기)
- **데스크톱 + 브라우저** — pywinauto (Windows UIA), Selenium (Chrome/Edge), pyautogui (좌표 fallback)
- **세션 영구 저장 + 가져오기/내보내기** — 세션을 실행 가능한 폴더 (`main.py` + `requirements.txt` + `run.bat`) 로 패키징해 다른 PC 로 이전
- **로컬 실행** — 화면/프롬프트/결과는 모두 로컬 (LLM 프롬프트 자체만 선택한 제공자에게 전송)

> **참고**: ohdo 는 현재 **Windows 전용** (Win32 / UWP / Windows 의 브라우저).
> macOS / Linux 데스크톱 지원은 단기 로드맵에 없음.

## 빠른 시작

### 설치 (권장: [`uv`](https://docs.astral.sh/uv/))

```powershell
# Python 3.12+ 필요. uv 미설치 시: pip install uv (또는 uv 공식 문서)
uv sync

# Gemini CLI 설치 (별도) — https://github.com/google-gemini/gemini-cli
```

`uv sync` 가 `pyproject.toml` + `uv.lock` 을 보고 자동으로 `.venv/` 생성 + 의존성 잠금 설치.

### 설치 (legacy: `pip`)

```powershell
py -3.12 -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 설치 (Codespaces / Dev Container)

상단 Codespaces 배지 클릭, 또는 VS Code "Dev Containers" 확장으로 [.devcontainer/](.devcontainer/) 열면 Python 3.12 + uv + Qt 의존성 + ruff + pre-commit 자동 셋업.

> **제약**: Dev container 는 Linux 환경이라 Windows 자동화 라이브러리 (`pywinauto`, `pyautogui`, `uiautomation`) 는 실행 불가.
> 컨테이너는 `core/` + 미래 `backend/` + `web/` 작업용.
> 실제 Windows 자동화 테스트는 로컬 Windows (또는 GitHub Actions `windows-latest`).

### 실행

```powershell
.venv\Scripts\python.exe main.py

# 실험적 v2 UI:
.venv\Scripts\python.exe main.py --ui v2
```

## 프로젝트 구조

```
ohdo/
├── main.py                # 진입점 (PyQt6 앱)
├── core/                  # AI 엔진 / 워크플로우 / 세션 / Windows inspector
├── ui/                    # PyQt6 메인 윈도우 + step 카드 + 콘솔
├── ui_v2/                 # UI redesign v2 PoC (별도 진입)
├── tests/                 # core / scenarios / ai_integration / GUI 테스트
├── config/                # settings.json / prompts.json
├── docs/                  # ROADMAP, handoff, 상업 검토, 와이어프레임
├── data/                  # 세션, 캡처, 로그 (git-ignored)
└── pyside6_port/          # PySide6 포팅 (LGPL 유연성 — 자체 README 참조)
```

자세한 구조: [`CLAUDE.md`](CLAUDE.md) 와 [`docs/handoff.md`](docs/handoff.md).

## 테스트

```powershell
# 코어 + 시나리오 (GUI 불필요)
.venv\Scripts\python.exe -m tests.test_runner --suite core
.venv\Scripts\python.exe -m tests.test_runner --suite scenarios

# AI 통합 (Gemini CLI 호출 — API 토큰 비용 + ~10-30 s/테스트)
.venv\Scripts\python.exe -m tests.test_runner --suite ai_integration

# GUI 자동화 (실제 Windows 데스크톱 필요)
.venv\Scripts\python.exe -m tests.test_runner --suite all
```

테스트 가이드: [`CLAUDE.md`](CLAUDE.md) "테스트 실행" 섹션.

## 로드맵

ohdo 는 오픈코어 전략 하 SaaS 확장 단계로 진행 중: Phase 0 (인프라 표준화) → Phase 1 (저장소 추상화 + UI-Core 분리) → Phase 2+ (백엔드 / Agent / 웹 대시보드).
**Phase 0 + Phase 1 모두 100% 완료 (2026-05-09).** Phase 2 진입은 [`docs/commercial_review.md`](docs/commercial_review.md) 의 게이트 통과 후 결정.

전체 계획: [`docs/ROADMAP.md`](docs/ROADMAP.md).

## 라이선스

데스크톱 클라이언트 + 코어 라이브러리는 **GNU Affero General Public License v3.0 (AGPL-3.0)** 으로 배포. 자세한 내용은 [`LICENSE`](LICENSE).

**오픈코어 전략** ([`docs/ROADMAP.md`](docs/ROADMAP.md) §1):
- **데스크톱 (이 저장소)**: AGPL-3.0. 자유 사용·수정·재배포 가능. 단, 수정본을 네트워크 서비스 (SaaS) 로 제공하는 경우 소스 공개 의무.
- **Hosted SaaS / Pro 기능**: 향후 별도 라이선스 (폐쇄 소스) 운영 예정. 저작권 보유자가 dual-licensing 가능.
- **PyQt6 ↔ PySide6**: 원본 PyQt6 는 저장소 루트, LGPL 친화 PySide6 포트는 [`pyside6_port/`](pyside6_port/) 별도 유지.

상업 / 비-AGPL 라이선스 문의: 이슈 또는 `pyproject.toml` 의 contact 으로.

## 기여

이슈 / 개선 제안 환영. 코드 컨벤션, 테스트 워크플로우, step 별 prompt 품질 루프는 [`CLAUDE.md`](CLAUDE.md). 큰 기여는 방향 정렬 위해 먼저 discussion 열어주세요 (특히 오픈코어 경계 관련).
