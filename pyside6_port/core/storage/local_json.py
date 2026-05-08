# SPDX-License-Identifier: AGPL-3.0-or-later
"""기존 ``SessionManager`` 를 감싸는 로컬 JSON 저장소 어댑터.

현재 동작을 100% 유지하기 위해 ``SessionRepository`` 의 각 메서드를
``SessionManager`` 의 대응 메서드로 **위임만** 한다. 추가 로직 없음.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.session_manager import (
    Session,
    SessionManager,
    SessionSummary,
    Step,
)

from .base import SessionRepository


class LocalJsonRepository(SessionRepository):
    """``data/sessions/`` JSON 기반 로컬 저장소.

    인스턴스를 직접 생성하거나, 이미 존재하는 ``SessionManager`` 를 주입할 수 있다.
    주입 방식은 데스크톱 앱의 기존 ``SessionManager`` 싱글 인스턴스를 공유할 때 사용한다.
    """

    def __init__(
        self,
        manager: Optional[SessionManager] = None,
        data_dir: Optional[Path] = None,
    ) -> None:
        self._manager = manager if manager is not None else SessionManager(data_dir)

    # 기존 SessionManager 인스턴스를 그대로 필요로 하는 UI 코드를 위해 노출.
    # 신규 코드는 이 속성 사용을 지양하고 인터페이스 메서드만 호출할 것.
    @property
    def manager(self) -> SessionManager:
        return self._manager

    # ── 세션 ───────────────────────────────────────────

    def create_session(
        self,
        title: str,
        project_type: str = "desktop",
        description: str = "",
    ) -> Session:
        return self._manager.create_session(
            title=title,
            project_type=project_type,
            description=description,
        )

    def save_session(self, session: Session) -> None:
        self._manager.save_session(session)

    def load_session(self, session_id: str) -> Session:
        return self._manager.load_session(session_id)

    def list_sessions(self) -> list[SessionSummary]:
        return self._manager.list_sessions()

    def delete_session(self, session_id: str) -> None:
        self._manager.delete_session(session_id)

    # ── 스텝 ───────────────────────────────────────────

    def add_step(self, session: Session, step: Step) -> None:
        self._manager.add_step(session, step)

    def update_step(self, session: Session, step_id: int, updates: dict) -> None:
        self._manager.update_step(session, step_id, updates)

    def delete_step(self, session: Session, step_id: int) -> bool:
        return self._manager.delete_step(session, step_id)

    def insert_step(
        self,
        session: Session,
        after_step_id: int,
        code: str = "",
        description: str = "삽입된 스텝",
    ) -> int:
        return self._manager.insert_step(
            session=session,
            after_step_id=after_step_id,
            code=code,
            description=description,
        )

    def move_step(self, session: Session, step_id: int, direction: str) -> bool:
        return self._manager.move_step(session, step_id, direction)

    # ── Export / Import (D22) ──────────────────────────

    def export_session_as_project(
        self,
        session: Session,
        output_dir: Path,
        *,
        settings: Optional[dict] = None,
        ai_generated_readme: Optional[str] = None,
    ) -> Path:
        return self._manager.export_as_project(
            session=session,
            output_dir=output_dir,
            settings=settings,
            ai_generated_readme=ai_generated_readme,
        )

    def import_session_folder(
        self,
        source_dir: Path,
        *,
        new_title: Optional[str] = None,
    ) -> Session:
        return self._manager.import_session_folder(
            source_dir=source_dir,
            new_title=new_title,
        )
