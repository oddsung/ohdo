# ohdo.ai

AI(Gemini CLI)와 대화하면서 Windows 데스크톱/웹 자동화 코드를 단계별로 생성·실행하는 PyQt6 기반 RPA 솔루션.

> **2026-05-02**: PySide6 포팅 버전이 [pyside6_port/](pyside6_port/) 에 추가됨 (라이선스 유연성 — LGPL).
> 원본 PyQt6 는 그대로 유지. 양쪽 같은 `data/` (junction) 공유. 자세한 차이/실행법은 [pyside6_port/README.md](pyside6_port/README.md) 참조.

## 프로젝트 구조

```
ai_rpa_solution/
├── main.py                          # 진입점 (PyQt6 앱)
├── config/
│   ├── settings.json               # 런타임 설정
│   ├── default_settings.json       # 기본값
│   └── prompts.json                # AI 프롬프트 템플릿
├── core/
│   ├── ai_engine.py                # AI 엔진 매니저 (팩토리 패턴)
│   ├── workflow_engine.py          # CodeSandbox + WorkflowEngine
│   ├── prompt_builder.py           # 프롬프트 동적 구축
│   ├── session_manager.py          # 세션 CRUD
│   ├── win_inspector.py            # Windows UI 트리 탐색 + 코드 생성
│   ├── environment_scanner.py      # 환경 점검
│   └── adapters/
│       ├── base_adapter.py         # AI 어댑터 추상 클래스
│       └── gemini_cli_adapter.py   # Gemini CLI 어댑터
├── ui/                              # PyQt6 UI 컴포넌트
│   ├── main_window.py              # 메인 윈도우
│   ├── chat_panel.py               # 채팅 패널
│   ├── code_viewer.py              # 코드/워크플로우 뷰어
│   ├── console_panel.py            # 콘솔/로그
│   ├── element_picker.py           # UI 요소 선택 (브라우저/데스크톱 분기)
│   ├── screen_capture.py           # 영역 캡처
│   └── ...
├── tests/                           # 테스트 하네스
│   ├── test_runner.py              # 테스트 프레임워크
│   ├── test_notepad.py             # 메모장 RPA 테스트
│   ├── test_calculator.py          # 계산기 RPA 테스트
│   ├── test_browser.py             # Chrome/Selenium 테스트
│   ├── test_core.py                # 코어 모듈 단위 테스트 (GUI 불필요)
│   ├── test_prompt_quality.py      # 프롬프트/컨텍스트 품질 테스트 (GUI 불필요)
│   ├── test_ai_integration.py      # AI 통합 테스트 (Gemini CLI 필요)
│   └── results/                    # 테스트 결과 JSON + 스크린샷
└── data/                            # 세션, 로그, 캡처 데이터
```

## 테스트 실행

### 코어 모듈 테스트 (GUI 불필요, 어디서든 실행 가능)
```bash
cd ai_rpa_solution
python -m tests.test_runner --suite core
```

### 프롬프트 품질 테스트 (GUI 불필요)
```bash
python -m tests.test_runner --suite prompt_quality
```
프롬프트 구조, 누적 코드 유지, 수동 편집 보존, 코드 추출기 정확도 등을 검증합니다.

### AI 통합 테스트 (Gemini CLI 필요)
```bash
python -m tests.test_runner --suite ai_integration
```
실제 AI를 호출하여 프롬프트 → 코드 생성 → 실행 → 결과 검증 전체 파이프라인을 테스트합니다.
주의: AI 호출 비용과 시간이 발생합니다 (테스트당 10~30초).

### UI 자동화 테스트 (Windows GUI 환경 필수)
```bash
python -m tests.test_runner --suite notepad
python -m tests.test_runner --suite calculator
python -m tests.test_runner --suite browser
python -m tests.test_runner --suite all
```

### 특정 테스트만 실행
```bash
python -m tests.test_runner --suite core --test test_10
```

### 결과 확인
- `tests/results/latest_result.json` — 최신 테스트 결과 (JSON)
- `tests/results/*.png` — 각 단계 스크린샷

## 테스트-수정 루프 (Claude Code 워크플로우)

1. **테스트 실행**: `python -m tests.test_runner --suite core` (Bash)
2. **결과 확인**: `tests/results/latest_result.json` 읽기 (Read)
3. **실패 분석**: 스크린샷 확인 (Read — 이미지), 에러 메시지 분석
4. **코드 수정**: 원인 파악 후 수정 (Edit)
5. **재테스트**: 1번으로 돌아가기

## 프롬프트 품질 개선 루프

AI가 생성하는 코드의 품질은 프롬프트와 컨텍스트에 달려 있습니다.

1. **프롬프트 구조 테스트**: `python -m tests.test_runner --suite prompt_quality`
   - 필수 지침 포함 여부, 누적 코드 유지, 수동 편집 보존 등 검증
2. **AI 통합 테스트**: `python -m tests.test_runner --suite ai_integration`
   - 실제 AI 호출 → 코드 생성 → 실행 → 출력 검증
   - 실패 시 prompt_builder.py 또는 win_inspector.py의 코드 템플릿 수정
3. **재테스트**로 개선 확인

### 개선 대상 파일
- `core/prompt_builder.py` — 프롬프트 구조, 가이드라인, 규칙
- `core/win_inspector.py` — 코드 템플릿 (데스크톱/브라우저/owner-drawn)
- `config/prompts.json` — 시스템 프롬프트, 에러 복구 템플릿

## 핵심 모듈 요약

### win_inspector.py
- **브라우저 요소**: Selenium 코드 생성 (JS click / direct click 자동 분기)
- **데스크톱 요소**: pywinauto 코드 생성 (DPI Awareness, 관리자 권한 대응)
- **Owner-drawn**: pyautogui 좌표 기반 클릭 코드 생성
- **동적 auto_id**: 숫자만인 경우 경고 표시

### workflow_engine.py
- **CodeSandbox**: 별도 프로세스에서 코드 실행, 자동 패키지 설치
- **WorkflowEngine**: 세션 스텝 순차 실행, 일시정지/재개/중지

### prompt_builder.py
- 사용자 요청 최상단 배치
- 이전 스텝 코드 누적 유지
- 수동 편집 diff 감지 및 보존
- 브라우저/데스크톱 자동 분기

### session_manager.py
- 세션 CRUD, 스텝 관리 (추가/삭제/이동/삽입)
- 프로젝트 내보내기 (main.py + requirements.txt + README.md + run.bat)

## 주의사항

- Windows 전용 기능: pywinauto, pyautogui, uiautomation, ctypes.windll
- DPI Awareness 설정이 pywinauto/pyautogui 좌표 일치에 필수
- 관리자 권한 앱 제어 시 pyautogui.click(x, y) 사용 (UIPI 우회)
- UWP 앱(Windows 11 메모장 등)은 Desktop().window() 방식으로 연결

## 장기 로드맵 문서 동기화 규칙

[docs/ROADMAP.md](docs/ROADMAP.md) 는 ohdo.ai 의 단계적 SaaS 확장 계획, 기능 우선순위, 리스크, KPI, 개발환경 표준을 담은 살아있는 문서입니다. 타깃 시장은 **B2C 개인 개발자, 글로벌 + 한국 dual-locale**(오픈코어 전략, 2026-05-09 사용자 결정으로 한국 niche → 글로벌 우선 + 한국 동시 진행으로 확장)으로 확정되어 있습니다.

다음 상황에서는 반드시 `docs/ROADMAP.md` 를 **함께 수정**하세요:

- Phase 순서·범위·마일스톤이 달라질 때
- 새 기능을 우선순위 매트릭스에 추가하거나 Phase 를 옮길 때
- 아키텍처 결정 (저장소 스키마, Agent 프로토콜, 인증 방식 등) 이 변경될 때
- 리스크 또는 KPI 가 추가·수정될 때
- 개발환경 표준 (의존성 관리자, CI 구성, Dev Container 설정 등) 이 바뀔 때
- 타깃 시장·요금제·라이선스 전략이 달라질 때

**업데이트 시 지켜야 할 것**:
1. 문서 맨 위 §0 "마지막 업데이트" 날짜 갱신
2. §10 변경 로그에 한 줄로 변경 이유 기록
3. 관련 있다면 이 `CLAUDE.md` 의 상위 섹션들도 함께 조정

Claude Code 에게 로드맵 변경을 지시할 때는 "로드맵 업데이트: <변경 내용>" 형태로 명시적으로 요청하면 문서 동기화를 빠뜨리지 않습니다.

## 개발 환경 표준 (요약)

상세 내용은 `docs/ROADMAP.md` §7 참조. 핵심:

- **의존성**: `pyproject.toml` + `uv` (Phase 0 도입 예정)
- **재현 환경**: `.devcontainer/` — 코어/백엔드/웹은 Linux 컨테이너·Codespaces·WSL2, Windows 자동화 테스트는 로컬 Windows 또는 GitHub Actions `windows-latest` 에서 분리 실행
- **품질**: `pre-commit` (`ruff`, `mypy`), GitHub Actions 매트릭스 CI
- **GitHub 만으로는 부족함** — 소스 동기화만 해결하며, 환경 재현은 위 스택이 필요
