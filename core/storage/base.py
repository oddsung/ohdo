# SPDX-License-Identifier: AGPL-3.0-or-later
"""세션 저장소 인터페이스 (ABC).

기존 ``core.session_manager.SessionManager`` 의 공개 API 중 도메인 관점에서
의미가 있는 메서드만 추상 메서드로 정의한다. 파일 시스템 경로 반환 메서드는
로컬 어댑터 전용이므로 여기에 포함하지 않는다.

ROADMAP §3 Phase 1 (1) 의 인터페이스 정의 — 데스크톱 앱과 향후 backend 서버
양쪽에서 공유 가능한 추상화 layer. 현재 구현체:

- ``LocalJsonRepository`` — JSON 파일 기반 (데스크톱 기본값)
- ``InMemoryRepository`` — 테스트 가속용 (file IO 없음)

Phase 2 추가 예정:

- ``PostgresRepository`` — SaaS backend
- ``S3CaptureStore`` — capture 이미지 전용
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.session_manager import Session, SessionSummary, Step


class SessionRepository(ABC):
    """세션 및 스텝 CRUD 를 추상화하는 저장소 인터페이스.

    구현체:
        - ``LocalJsonRepository`` — 기존 ``SessionManager`` 위에 구현 (현재 기본값).
        - ``InMemoryRepository`` — 테스트 가속용 (file IO 없음).
        - 향후: ``PostgresRepository`` 등.
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
    def move_step(self, session: "Session", step_id: int, direction: str) -> bool:
        """스텝을 위/아래로 이동한다. ``direction`` 은 ``"up"`` 또는 ``"down"``."""

    # ── Export / Import (D22) ──────────────────────────
    #
    # 5/8 Phase 1 sub-task 1 — AppService 의 ``getattr(self._repo, "manager", ...)``
    # leak 제거. 데스크톱 backend 는 filesystem 으로 export, future backend
    # (PostgresRepository 등) 은 zip stream 또는 download URL 등으로 구현 가능.
    # 실패 시 ``NotImplementedError`` 발생.

    @abstractmethod
    def export_session_as_project(
        self,
        session: "Session",
        output_dir: "Path",
        *,
        settings: Optional[dict] = None,
        ai_generated_readme: Optional[str] = None,
    ) -> "Path":
        """세션을 독립 실행 가능한 프로젝트 폴더로 내보낸다.

        ``LocalJsonRepository`` 는 main.py + requirements.txt + README.md +
        run.bat + session.json + captures/ + scripts/ 을 ``output_dir`` 에 생성.
        Backend 미지원 시 ``NotImplementedError``.
        """

    @abstractmethod
    def import_session_folder(
        self,
        source_dir: "Path",
        *,
        new_title: Optional[str] = None,
    ) -> "Session":
        """외부 export 폴더로부터 세션을 임포트한다 (새 UUID 발급)."""

    # ── Recording artifact (PR-19i — 2026-05-24) ──────────────────
    #
    # 작업 녹화 (ADR 0004) raw events 를 세션 부속 artifact 로 저장 — 사후
    # 재변환 / 디버깅 / 옵션 비교 분석에 활용. 데스크톱은 ``data/sessions/<id>/
    # raw_events_<rec_id>.jsonl`` (한 줄당 한 RawEvent JSON dump), backend
    # 미지원 시 None 반환 → caller (``AppService.commit_recording``) 는 graceful
    # skip (commit 자체는 성공).

    @abstractmethod
    def save_recording_raw_events(
        self,
        session_id: str,
        recording_session_id: str,
        events: list[dict],
    ) -> Optional[str]:
        """녹화 raw events 를 세션 부속 artifact 로 저장한다.

        Args:
            session_id: 녹화 commit 대상 ohdo Session id (저장 위치 기준).
            recording_session_id: ``RecordingSession.id`` — 파일명 충돌 회피.
            events: 직렬화된 raw events (Pydantic ``model_dump(mode="json")`` 결과).

        Returns:
            ``recording_meta.raw_events_path`` 에 보존될 식별자 (예: relative
            path). ``None`` 이면 저장 미지원 — caller 는 metadata 에 path 미기록.
        """


class CaptureStore(ABC):
    """캡처 이미지 저장소 인터페이스 (ROADMAP §3 Phase 1 (1)).

    현재 capture 들은 ``data/sessions/<id>/captures/<file>.png`` 의 절대경로 문자열로
    ``step.captures`` 에 저장된다. Phase 2 의 S3/R2 백엔드 진입을 위한 접점만 정의.

    실제 capture 쓰기 경로 (``ui/screen_capture.py``, ``core/win_inspector.py``)
    의 마이그레이션은 Phase 2 진입 시 일괄 처리 — 이 인터페이스는 그때를 위한
    contract 정의에 그친다.
    """

    @abstractmethod
    def resolve_capture_path(self, session_id: str, filename: str) -> "Path":
        """세션 ID + 파일명 → 실제 capture 위치 (로컬: 절대경로, S3: pre-signed URL).

        구현체 (``LocalCaptureStore``): ``<sessions_dir>/<id>/captures/<filename>``.
        """

    @abstractmethod
    def list_captures_for_session(self, session_id: str) -> list[str]:
        """세션의 모든 capture 파일명 목록."""

    @abstractmethod
    def delete_capture(self, session_id: str, filename: str) -> bool:
        """capture 파일 삭제. 성공 여부 반환."""
