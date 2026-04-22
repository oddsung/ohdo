"""UI·서버 공용 애플리케이션 진입점 (Facade).

현재 ``ui/main_window.py`` 가 ``SessionManager`` / ``AIEngineManager`` /
``WorkflowEngine`` 을 직접 import 해서 쓴다. SaaS 로 확장하면 FastAPI 라우터,
Agent runner, 새 UI 컴포넌트 등에서도 동일한 로직을 호출해야 하는데, 그때마다
UI 와 같은 import 경로를 반복할 수는 없다.

``AppService`` 는 도메인 연산의 **단일 진입점**이다.

- 기존 UI 는 건드리지 않는다 ([ADR 0001](../docs/saas/decisions/0001-preserve-existing-core.md)).
- 새로 추가되는 모든 호출자(백엔드, Agent, 새 UI)는 이 클래스만 의존한다.
- 1차 버전은 세션/스텝 CRUD 만 다룬다. AI 생성·워크플로우 실행은 다음 단계에서.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from core.session_manager import Session, SessionSummary, Step

from .storage.base import SessionRepository

if TYPE_CHECKING:
    from core.ai_engine import AIEngineManager
    from core.workflow_engine import WorkflowEngine


class AppService:
    """세션·스텝 CRUD 공용 Facade.

    Args:
        session_repo: 저장소 구현체. 로컬 기본은 ``LocalJsonRepository``.
        ai_manager: AI 엔진 매니저 (현재 1차에서는 미사용, 확장 지점만 확보).
        workflow_engine: 워크플로우 엔진 (현재 1차에서는 미사용, 확장 지점만 확보).
    """

    def __init__(
        self,
        session_repo: SessionRepository,
        ai_manager: Optional["AIEngineManager"] = None,
        workflow_engine: Optional["WorkflowEngine"] = None,
    ) -> None:
        self._repo = session_repo
        self._ai = ai_manager
        self._engine = workflow_engine

    @property
    def repo(self) -> SessionRepository:
        return self._repo

    # ── 세션 ───────────────────────────────────────────

    def list_sessions(self) -> list[SessionSummary]:
        return self._repo.list_sessions()

    def get_session(self, session_id: str) -> Session:
        return self._repo.load_session(session_id)

    def create_session(
        self,
        title: str,
        project_type: str = "desktop",
        description: str = "",
    ) -> Session:
        return self._repo.create_session(
            title=title,
            project_type=project_type,
            description=description,
        )

    def delete_session(self, session_id: str) -> None:
        self._repo.delete_session(session_id)

    # ── 스텝 ───────────────────────────────────────────

    def add_step(self, session_id: str, step: Step) -> None:
        session = self._repo.load_session(session_id)
        self._repo.add_step(session, step)

    def update_step(self, session_id: str, step_id: int, updates: dict) -> None:
        session = self._repo.load_session(session_id)
        self._repo.update_step(session, step_id, updates)

    def delete_step(self, session_id: str, step_id: int) -> bool:
        session = self._repo.load_session(session_id)
        return self._repo.delete_step(session, step_id)

    def insert_step(
        self,
        session_id: str,
        after_step_id: int,
        code: str = "",
        description: str = "삽입된 스텝",
    ) -> int:
        session = self._repo.load_session(session_id)
        return self._repo.insert_step(
            session=session,
            after_step_id=after_step_id,
            code=code,
            description=description,
        )

    def move_step(self, session_id: str, step_id: int, direction: str) -> bool:
        session = self._repo.load_session(session_id)
        return self._repo.move_step(session, step_id, direction)
