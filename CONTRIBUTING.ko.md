# ohdo 기여 가이드

관심 가져 주셔서 감사합니다. ohdo 는 작은 프로젝트라 시작 전 몇 가지 안내가 모두의 시간을 절약합니다.

🌐 **English**: [CONTRIBUTING.md](CONTRIBUTING.md)

---

## PR 열기 전에

1. **작은 fix / typo 외에는 먼저 discussion 또는 issue 열어주세요.** ohdo 는 오픈코어 전략 ([`COMMERCIAL.md`](COMMERCIAL.md) + [`docs/ROADMAP.md`](docs/ROADMAP.md) §1) 을 따르며, 코딩 *전에* 방향 정렬이 시간을 아낍니다.
2. **관련 문서 읽기** — 영역별:
   - 프로젝트 구조 + 테스트 워크플로우: [`CLAUDE.md`](CLAUDE.md)
   - 장기 로드맵: [`docs/ROADMAP.md`](docs/ROADMAP.md)
   - 최근 변경 이력 + 진행 작업: [`docs/handoff.md`](docs/handoff.md)
   - 정직한 경쟁 분석: [`docs/commercial_review.md`](docs/commercial_review.md)
3. **기존 테스트 확인** — `tests/test_runner.py` 가 `core` / `scenarios` / `ai_integration` / GUI 스위트 실행. 대부분의 기여는 `core` 또는 `scenarios` 회귀 테스트 필요.

## 개발 환경 셋업

```powershell
# 권장: uv (https://docs.astral.sh/uv/)
uv sync --extra dev
.venv\Scripts\python.exe -m pre_commit install

# Lint + format 검증
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .

# GUI 불필요 테스트 로컬 실행
venv\Scripts\python.exe -m tests.test_runner --suite core
venv\Scripts\python.exe -m tests.test_runner --suite scenarios
```

CI 가 매 push / PR 마다 lint + ubuntu/windows 테스트 실행 ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## 코딩 컨벤션

- **Python 3.12+**. Type hint 권장하지만 repo 전체 강제 X (mypy 는 Phase 1 type-hint 작업과 묶음).
- **`ruff` 가 lint + format 의 진실의 원천**. commit 전 `ruff format` — pre-commit 이 어차피 강제.
- **test/log/print 메시지에 em-dash X** — Windows `cp949` 콘솔 인코딩이 처리 못 함. hyphen 사용. (Markdown / docstring 은 OK.)
- **`ui/` 의 모든 파일은 `from core.app_service import …` 단일 진입점만** — `core.session_manager`, `core.ai_engine`, `core.execution_kernel`, `core.workflow_engine`, `core.import_manager`, `core.prompt_builder`, `core.win_inspector`, `core.storage.*` 직접 import 는 test_80 / test_84 / test_85 에서 차단.
- **PySide6 port sync** — `core/` 또는 `ui/` 변경 시 `pyside6_port/` 에 mirror (`cp` for `core/`, `sed` PyQt6→PySide6 for `ui/`). 정확한 절차는 `CLAUDE.md`.

## 커밋 sign-off (DCO)

ohdo 는 무거운 CLA 대신 [Developer Certificate of Origin](https://developercertificate.org/) ("DCO") 사용. 모든 commit 에 `Signed-off-by:` 라인 필수 — 본인이 patch 작성했거나 (또는 제출 권한이 있고), AGPL-3.0 으로 라이선스에 동의한다는 단일 선언.

`git commit -s` 가 가장 간편:

```bash
git commit -s -m "Fix the thing"
# 자동으로 "Signed-off-by: Your Name <your.email@example.com>" 추가
```

서명은 `git config user.name "Your Name"` + `git config user.email "your.email@example.com"` 한 번 설정.

큰 / 구조적 기여는 **CLA** 별도 서명 요청 가능 (프로젝트가 [`COMMERCIAL.md`](COMMERCIAL.md) 으로 깔끔히 dual-license 하기 위해). 가능한 드물게 — 단일 파일 patch 는 대부분 불필요.

## PR 체크리스트

- [ ] 연결된 issue / discussion 존재 (자명한 변경 외).
- [ ] `ruff check .` + `ruff format --check .` 로컬 통과.
- [ ] `tests/test_runner.py --suite core` + `--suite scenarios` 로컬 통과.
- [ ] 새 동작에 회귀 테스트 (`tests/test_core.py` 또는 `tests/test_scenarios.py`).
- [ ] `ui/`, `core/`, `tests/` 변경 시 `pyside6_port/` 에 mirror.
- [ ] 모든 commit 에 `Signed-off-by:` 라인.
- [ ] PR description 이 *what* 이 아니라 *why* 설명.

## 특히 환영하는 기여 영역

- **i18n** — 사용자 facing 문자열이 일부 한국어. 깔끔한 i18n 레이어로 정리는 고가치 + 코드 깊이 이해 불필요.
- **Element picker 견고성** — UWP 앱, hidden control type, 브라우저 frame 의 edge case.
- **테스트 픽스처** — 현재 inspection 의존 동작을 pin 하는 `core` / `scenarios` 케이스 더.
- **문서** — 특히 internal 한국어 문서의 영어 버전.

## 범위 외 (현재)

- macOS / Linux 데스크톱 지원 (Windows 전용은 의도적 niche — `docs/commercial_review.md` 참조).
- 벤더 락인 포맷 (XAML, 자체 스크립팅). ohdo 의 핵심은 순수 Python.
- Phase 2 SaaS 코드 — 오픈코어 경계 너머, 아직 비공개.

## 감사

여기까지 읽은 것만으로도 도움이 됩니다. 불명확한 부분 issue 열어주시면 문서 개선합니다.
