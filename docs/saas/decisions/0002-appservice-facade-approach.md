# ADR 0002: AppService + Storage Facade 로 SaaS 레이어를 연다

- **상태**: Accepted
- **날짜**: 2026-04-22
- **결정자**: @oddsung

## 컨텍스트

[ADR 0001](0001-preserve-existing-core.md) 로 기존 코드는 건드리지 않기로 했다. 그런데 SaaS 확장을 위해서는:

- **클라우드 저장소** 로 세션을 올릴 수 있어야 함 — 하지만 현재 `SessionManager` 는 `Path("data/sessions/")` 에 JSON 을 직접 쓴다.
- **FastAPI 라우터** 에서도 동일한 세션 로직을 호출해야 함 — 현재는 PyQt6 UI 가 `SessionManager`·`WorkflowEngine` 을 직접 들고 있다.
- **Agent 프로세스** 에서 `WorkflowEngine` 을 원격 명령으로 돌려야 함.

기존 코드를 그대로 두면서 이 세 가지가 다 가능해야 한다.

## 결정

두 가지 얇은 레이어를 **신규 파일로만** 추가한다.

### 1. `core/storage/` — 저장소 추상화

```
core/storage/
├── __init__.py
├── base.py         # SessionRepository (ABC) — 인터페이스만
└── local_json.py   # 기존 SessionManager 를 감싸는 어댑터
```

- `SessionRepository` 는 `create_session`, `load_session`, `list_sessions`, `delete_session`, `add_step`, `update_step`, `delete_step`, `insert_step`, `move_step` 등 현 `SessionManager` 의 핵심 API 와 1:1 로 맞춘 추상 메서드를 정의한다.
- `LocalJsonRepository` 는 내부에 `SessionManager` 인스턴스를 가지고 **모든 호출을 그대로 위임** 한다. 기존 동작과 100% 동일.
- 향후 `PostgresRepository`, `HttpRemoteRepository` 를 같은 인터페이스로 추가할 수 있다.

### 2. `core/app_service.py` — UI·서버 공용 진입점

```python
class AppService:
    def __init__(self, session_repo: SessionRepository,
                 ai_manager: AIEngineManager | None = None,
                 workflow_engine: WorkflowEngine | None = None): ...
```

- `AppService` 는 `SessionRepository`(필수) + `AIEngineManager`(선택) + `WorkflowEngine`(선택) 을 composition 으로 받는다.
- **초기 버전은 얇다**: 세션 CRUD 와 스텝 CRUD 를 repo 로 위임하는 메서드만. AI 생성·워크플로우 실행은 **다음 단계**에서 추가.
- `ui/` 는 **직접 import 하지 않는다**. 기존 UI 는 그대로 두되, 이후 새 UI 컴포넌트가 만들어질 때 `AppService` 만 의존하도록 유도.
- FastAPI 라우터에서도 같은 `AppService` 를 DI 로 주입받아 호출한다.

### 3. 의존 방향

```
(기존) ui/main_window.py → core/session_manager.py 등 직접
(신규) FastAPI 라우터  ─┐
        새 Agent runner ├→ core/app_service.py → core/storage/base.py ← core/storage/local_json.py → core/session_manager.py (기존)
        새 UI 컴포넌트  ─┘
```

기존 경로와 신규 경로가 **공존**한다. 기존 UI 는 아무것도 모르는 채로 그대로 동작.

## 결과

### 장점

- 회귀 0 — 기존 흐름이 전혀 건드려지지 않음.
- 서버·Agent 작업이 `AppService` 하나만 import 하면 되므로 의존성이 단순.
- `LocalJsonRepository` vs `HttpRemoteRepository` 전환이 설정 한 줄로 가능 (Phase 2 의 `ohdo migrate-to-cloud` 마이그레이션 경로).

### 단점 및 대응

- 당분간 AppService 와 기존 UI 호출 경로가 **중복**된다 → Facade 는 로직 없이 위임만. 중복이라기보다 "같은 것을 두 방향에서 노출" 로 본다.
- AppService 테스트가 기존 `SessionManager` 실제 구현을 통과한다 → 인메모리 `SessionRepository` 테스트 더블을 추후 추가해서 단위 테스트 속도를 유지.

## 다음 단계

1. `core/storage/base.py` + `local_json.py` 구현.
2. `core/app_service.py` 최소 버전 구현 (세션 목록/조회/생성/삭제만).
3. 단위 테스트 추가 (`tests/test_app_service.py` 같은 신규 파일).
4. `AppService.run_step()`, `AppService.generate_step()` 확장 — UI 의 직접 호출을 하나씩 AppService 로 옮겨갈 수 있도록.
