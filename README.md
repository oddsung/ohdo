# ohdo.ai

[![CI](https://github.com/oddsung/ohdo/actions/workflows/ci.yml/badge.svg)](https://github.com/oddsung/ohdo/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/oddsung/ohdo)

AI(Gemini CLI)와 대화하면서 Windows 데스크톱/웹 자동화 코드를 단계별로 생성·실행하는 PyQt6 기반 RPA 솔루션.

## 핵심 기능

- **자연어 → Python 코드**: "메모장 열고 '안녕' 입력해줘" 같은 요청을 pywinauto/pyautogui/Selenium 코드로 자동 생성
- **단계별 워크플로우**: 각 step 을 카드로 관리, 누적 코드 유지, 실패 step 만 재실행 가능
- **Element 픽**: 스크린 위 위젯을 직접 클릭하여 자동 자동화 코드 생성 (데스크톱/브라우저 자동 분기)
- **데스크톱 + 브라우저**: pywinauto (Windows UIA), Selenium (Chrome/Edge), pyautogui (좌표 기반) 모두 지원
- **세션 영구 저장 + 가져오기/내보내기**: 다른 PC 로 워크플로우 이전 가능 (main.py + requirements.txt + run.bat 패키징)

## 빠른 시작

### 설치 (권장: uv)

```powershell
# Python 3.12+ 필요. uv 미설치 시: pip install uv (또는 https://docs.astral.sh/uv/)
uv sync

# Gemini CLI 설치 (별도 — https://github.com/google-gemini/gemini-cli)
```

`uv sync` 가 `pyproject.toml` + `uv.lock` 을 보고 자동으로 `.venv/` 생성 + 의존성 설치.

### 설치 (legacy: pip)

```powershell
py -3.12 -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 설치 (Codespaces / Dev Container)

GitHub Codespaces 또는 VS Code "Dev Containers" 확장으로 [.devcontainer/](.devcontainer/) 클릭 한 번에 환경 자동 셋업 (Python 3.12 + uv + Qt 의존성 + ruff + pre-commit 모두 사전 설치).

**제약**: 컨테이너는 Linux 환경이라 Windows 자동화 (pywinauto, pyautogui, uiautomation) 는 실행 불가. 컨테이너 = `core/` + 미래 `backend/` + `web/` 개발용. Windows GUI 테스트는 로컬 Windows 또는 GitHub Actions `windows-latest` runner 에서.

### 실행

```powershell
.venv\Scripts\python.exe main.py

# UI redesign v2 PoC (실험적):
.venv\Scripts\python.exe main.py --ui v2
```

## 프로젝트 구조

```
ohdo/
├── main.py                    # 진입점 (PyQt6 앱)
├── core/                      # AI / 워크플로우 / 세션 / Windows inspector
├── ui/                        # PyQt6 UI (메인 윈도우 + 카드 + 콘솔)
├── ui_v2/                     # UI redesign v2 PoC (별도 진입)
├── tests/                     # core / scenarios / ai_integration / GUI 테스트
├── config/                    # settings.json / prompts.json
├── docs/                      # ROADMAP, handoff, 와이어프레임
├── data/                      # 세션, 캡처, 로그
└── pyside6_port/              # PySide6 포팅 버전 (라이선스 유연성)
```

자세한 구조는 [CLAUDE.md](CLAUDE.md) 와 [docs/handoff.md](docs/handoff.md) 참조.

## 테스트

```powershell
# 코어 모듈 + 시나리오 (GUI 불필요)
.venv\Scripts\python.exe -m tests.test_runner --suite core
.venv\Scripts\python.exe -m tests.test_runner --suite scenarios

# AI 통합 (Gemini CLI 필요, 비용·시간 발생)
.venv\Scripts\python.exe -m tests.test_runner --suite ai_integration

# UI 자동화 (Windows GUI 환경 필수)
.venv\Scripts\python.exe -m tests.test_runner --suite all
```

자세한 테스트 가이드는 [CLAUDE.md](CLAUDE.md) 의 "테스트 실행" 섹션 참조.

## 로드맵

데스크톱 안정화 → SaaS 확장 단계로 진행 중. Phase 0 (프로젝트 인프라 표준화) → Phase 1 (오픈코어 구조) → Phase 2+ (백엔드/Agent/웹). 자세한 내용은 [docs/ROADMAP.md](docs/ROADMAP.md).

## 라이선스

이 프로젝트의 데스크톱 코드는 **GNU Affero General Public License v3.0 (AGPL-3.0)** 으로 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 참조.

오픈코어 전략 (자세한 내용은 [docs/ROADMAP.md](docs/ROADMAP.md) §1):
- **데스크톱 (이 저장소)**: AGPL-3.0 — 누구나 자유롭게 사용·수정·재배포 가능. 단, 수정본을 네트워크 서비스로 제공하는 경우 (SaaS) 소스 공개 의무 발생.
- **상용 SaaS**: 향후 별도 폐쇄 소스로 운영 예정 (저작권 보유자가 dual-licensing 가능).
- **PyQt6 ↔ PySide6**: 원본 PyQt6 외에 [pyside6_port/](pyside6_port/) 에 LGPL 기반 포팅 버전 별도 유지.

상용 라이선스 / 면책 라이선스 문의는 별도 협의.

## 기여

이슈 / 개선 제안 환영. 코드 컨벤션과 테스트 가이드는 [CLAUDE.md](CLAUDE.md) 참조.
