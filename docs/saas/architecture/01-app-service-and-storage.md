# 01. AppService + Storage 레이어 설계

- **상태**: 구현 착수 (2026-04-22)
- **관련 ADR**: [0001](../decisions/0001-preserve-existing-core.md), [0002](../decisions/0002-appservice-facade-approach.md)

## 목표

기존 [core/session_manager.py](../../../core/session_manager.py) 를 수정하지 않고, **같은 도메인 로직을 두 경로에서 호출할 수 있는 seam(이음매)** 을 만든다.

- 경로 1 (현재): PyQt6 UI → `SessionManager` 직접 호출 (그대로 둔다)
- 경로 2 (신규): FastAPI 서버 / Agent runner / 새 UI → `AppService` → `SessionRepository` → `LocalJsonRepository` → `SessionManager`

## 파일 레이아웃

```
core/
├── session_manager.py   # 기존 — 수정 없음
├── workflow_engine.py   # 기존 — 수정 없음
├── ai_engine.py         # 기존 — 수정 없음
├── app_service.py       # [신규] UI·서버 공용 진입점
└── storage/             # [신규]
    ├── __init__.py
    ├── base.py          # SessionRepository (ABC)
    └── local_json.py    # 기존 SessionManager 를 감싸는 어댑터
```

## `SessionRepository` 인터페이스 (요약)

기존 `SessionManager` 의 공개 메서드 중 **데이터 조작 핵심** 만 추상화한다. 파일 시스템 경로 반환 메서드(`get_session_dir`, `get_captures_dir`, `get_scripts_dir`) 는 로컬 어댑터 전용으로 남기고 ABC 에는 넣지 않는다 — 원격 저장소에서는 의미가 없기 때문.

| 추상 메서드 | 위임 대상 (`LocalJsonRepository`) |
|---|---|
| `create_session(title, project_type, description)` | `SessionManager.create_session` |
| `save_session(session)` | `SessionManager.save_session` |
| `load_session(session_id)` | `SessionManager.load_session` |
| `list_sessions()` | `SessionManager.list_sessions` |
| `delete_session(session_id)` | `SessionManager.delete_session` |
| `add_step(session, step)` | `SessionManager.add_step` |
| `update_step(session, step_id, updates)` | `SessionManager.update_step` |
| `delete_step(session, step_id)` | `SessionManager.delete_step` |
| `insert_step(session, after_step_id, code, description)` | `SessionManager.insert_step` |
| `move_step(session, step_id, direction)` | `SessionManager.move_step` |

반환 타입은 기존 `Session`·`SessionSummary`·`Step` (dataclass) 을 그대로 재사용 — Pydantic 으로의 승격은 Phase 2 로 미룬다.

## `AppService` 인터페이스 (1차)

```python
class AppService:
    def __init__(
        self,
        session_repo: SessionRepository,
        ai_manager: Optional[AIEngineManager] = None,
        workflow_engine: Optional[WorkflowEngine] = None,
    ) -> None: ...

    # 세션
    def list_sessions(self) -> list[SessionSummary]: ...
    def get_session(self, session_id: str) -> Session: ...
    def create_session(self, title: str, project_type: str = "desktop",
                       description: str = "") -> Session: ...
    def delete_session(self, session_id: str) -> None: ...

    # 스텝
    def add_step(self, session_id: str, step: Step) -> None: ...
    def update_step(self, session_id: str, step_id: int, updates: dict) -> None: ...
    def delete_step(self, session_id: str, step_id: int) -> bool: ...
    def insert_step(self, session_id: str, after_step_id: int,
                    code: str = "", description: str = "") -> int: ...
    def move_step(self, session_id: str, step_id: int, direction: str) -> bool: ...
```

### 의도적으로 뺀 것들

- `run_step()` / `generate_step()` — AI 호출·워크플로우 실행 흐름은 현재 `ui/main_window.py` 가 직접 소유한다. 이걸 AppService 로 옮기려면 UI 수정이 필요 → [ADR 0001](../decisions/0001-preserve-existing-core.md) 에 따라 **다음 단계**로 미룸. 다만 `ai_manager`·`workflow_engine` 인자를 이미 받을 수 있게 열어둬서 확장 지점은 확보.
- 파일 시스템 경로 접근자 — `LocalJsonRepository` 에서만 노출 (하위 호환).
- Pydantic 승격 — 별도 ADR 대상.

## 호출 예시

### 데스크톱 (현재 UI 와 공존)

```python
from core.session_manager import SessionManager
from core.storage.local_json import LocalJsonRepository
from core.app_service import AppService

mgr = SessionManager()                  # 기존 방식 그대로
repo = LocalJsonRepository(mgr)         # 새 레이어가 감쌈
service = AppService(session_repo=repo)

for summary in service.list_sessions():
    print(summary.title)
```

### 향후 FastAPI (Phase 2)

```python
# packages/backend/app/deps.py
def get_app_service() -> AppService:
    repo = HttpOrPostgresRepository(...)
    return AppService(session_repo=repo)

# packages/backend/app/routers/sessions.py
@router.get("/sessions")
def list_sessions(svc: AppService = Depends(get_app_service)):
    return svc.list_sessions()
```

같은 `AppService` 클래스를 데스크톱·서버 모두가 쓴다. Repository 구현체만 바꿔 끼우면 로컬 ↔ 원격 전환.

## 테스트 전략

- `tests/test_app_service.py` (신규): `InMemorySessionRepository` 테스트 더블을 만들어 AppService 단위 테스트. 기존 `tests/test_runner.py` 와는 독립.
- `LocalJsonRepository` 자체는 기존 `SessionManager` 실제 구현을 감쌀 뿐이므로 `tests/test_core.py` 가 기존 세션 매니저에 대해 돌고 있다면 **회귀는 자동 커버**.

## 남은 질문

- [ ] `AppService.run_step` / `generate_step` 를 도입할 때, UI 의 기존 흐름(시그널 기반 비동기)을 어떻게 해치지 않고 확장할지 → `EventBus` 추상화 설계가 별도 ADR 로 필요.
- [ ] 서버 쪽 Repository 를 만들 때 `Session` dataclass 를 그대로 쓸지, Pydantic 모델로 바꿀지 → Phase 2 착수 직전 결정.
