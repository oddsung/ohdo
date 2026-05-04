"""세션 저장소 인터페이스 (ABC).

기존 ``core.session_manager.SessionManager`` 의 공개 API 중 도메인 관점에서
의미가 있는 메서드만 추상 메서드로 정의한다. 파일 시스템 경로 반환 메서드는
로컬 어댑터 전용이므로 여기에 포함하지 않는다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.session_manager import Session, SessionSummary, Step


class SessionRepository(ABC):
    """세션 및 스텝 CRUD 를 추상화하는 저장소 인터페이스.

    구현체:
        - ``LocalJsonRepository`` — 기존 ``SessionManager`` 위에 구현 (현재 기본값).
        - 향후: ``HttpRemoteRepository``, ``PostgresRepository`` 등.
    """

    # ── 세션 ───────────────────────────────────────────

    @abstractmethod
    def create_session(
        self,
        title: str,
        project_type: str = "desktop",
        description: str = "",
    ) -> "Session":
        """새 세션을 생성하고 저장된 상태로 반환한다."""

    @abstractmethod
    def save_session(self, session: "Session") -> None:
        """세션을 저장한다 (updated_at 자동 갱신)."""

    @abstractmethod
    def load_session(self, session_id: str) -> "Session":
        """세션을 조회한다. 없으면 ``FileNotFoundError`` / 원격에서는 동등한 예외."""

    @abstractmethod
    def list_sessions(self) -> list["SessionSummary"]:
        """세션 요약 목록을 반환한다 (최신 업데이트 순)."""

    @abstractmethod
    def delete_session(self, session_id: str) -> None:
        """세션을 삭제한다. 없으면 조용히 무시하거나 경고만 로깅한다."""

    # ── 스텝 ───────────────────────────────────────────

    @abstractmethod
    def add_step(self, session: "Session", step: "Step") -> None:
        """세션에 스텝을 추가하고 저장한다."""

    @abstractmethod
    def update_step(self, session: "Session", step_id: int, updates: dict) -> None:
        """스텝 일부 필드를 업데이트하고 저장한다."""

    @abstractmethod
    def delete_step(self, session: "Session", step_id: int) -> bool:
        """스텝을 삭제하고 ID 를 재정렬한다. 성공 여부 반환."""

    @abstractmethod
    def insert_step(
        self,
        session: "Session",
        after_step_id: int,
        code: str = "",
        description: str = "삽입된 스텝",
    ) -> int:
        """특정 스텝 뒤에 새 스텝을 삽입한다. 새 스텝 ID 반환."""

    @abstractmethod
    def move_step(
        self, session: "Session", step_id: int, direction: str
    ) -> bool:
        """스텝을 위/아래로 이동한다. ``direction`` 은 ``"up"`` 또는 ``"down"``."""
