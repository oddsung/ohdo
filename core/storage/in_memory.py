# SPDX-License-Identifier: AGPL-3.0-or-later
"""인메모리 저장소 — 테스트 가속용 (file IO 없음).

ROADMAP §3 Phase 1 (1) 의 "테스트 전략: ``SessionRepository`` 인메모리 구현으로
``test_core.py`` 속도 향상" 항목 구현.

특징:

- 파일 시스템 IO 없음 → tempfile.TemporaryDirectory 보다 빠름 (특히 다수의 작은
  ``create_session`` / ``save_session`` 사이클)
- 본격 구현은 단순 dict — 동시성/락 X (단일 테스트 스레드 가정)
- export/import 는 filesystem 기반이라 ``NotImplementedError`` 발생 (이 backend
  의 의도가 아님 — file IO 가 정말 필요하면 ``LocalJsonRepository`` 사용)

비고:

- 실제 데스크톱 앱은 항상 ``LocalJsonRepository`` 를 사용. 이 클래스는 프로덕션
  경로에 절대 사용되지 않음.
- 향후 SaaS backend 의 ``HttpRemoteRepository`` 의 in-memory mock 으로도 활용 가능.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.session_manager import Session, SessionSummary, Step

from .base import SessionRepository


class InMemoryRepository(SessionRepository):
    """``dict[session_id, Session]`` 위에 동작하는 in-memory 저장소.

    LocalJsonRepository 와 동일한 contract 를 준수해야 함 (test 로 검증).
    """

    def __init__(self) -> None:
        # session_id → Session (deep-copy 로 격리)
        self._sessions: dict[str, Session] = {}

    # ── 세션 ───────────────────────────────────────────

    def create_session(
        self,
        title: str,
        project_type: str = "desktop",
        description: str = "",
    ) -> Session:
        now = datetime.now().isoformat()
        session = Session(
            session_id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            title=title,
            description=description,
            project_type=project_type,
        )
        self._sessions[session.session_id] = copy.deepcopy(session)
        return session

    def save_session(self, session: Session) -> None:
        session.updated_at = datetime.now().isoformat()
        self._sessions[session.session_id] = copy.deepcopy(session)

    def load_session(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            raise FileNotFoundError(f"세션을 찾을 수 없습니다: {session_id}")
        return copy.deepcopy(self._sessions[session_id])

    def list_sessions(self) -> list[SessionSummary]:
        summaries = []
        for s in self._sessions.values():
            metadata = s.workflow_metadata
            summaries.append(
                SessionSummary(
                    session_id=s.session_id,
                    title=s.title,
                    description=s.description,
                    project_type=s.project_type,
                    created_at=s.created_at,
                    updated_at=s.updated_at,
                    total_steps=metadata.get("total_steps", len(s.steps)),
                    completed_steps=metadata.get("completed_steps", 0),
                )
            )
        # 최신순
        summaries.sort(key=lambda x: x.updated_at, reverse=True)
        return summaries

    def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    # ── 스텝 ───────────────────────────────────────────

    def add_step(self, session: Session, step: Step) -> None:
        target = self._sessions.get(session.session_id)
        if target is None:
            raise FileNotFoundError(f"세션을 찾을 수 없습니다: {session.session_id}")
        # step_id 자동 부여 (1-based)
        step.step_id = len(target.steps) + 1
        if not step.created_at:
            step.created_at = datetime.now().isoformat()
        # asdict 상응 — Session.steps 는 dict 리스트로 저장
        from dataclasses import asdict

        step_dict = asdict(step) if not isinstance(step, dict) else dict(step)
        target.steps.append(step_dict)
        target.updated_at = datetime.now().isoformat()
        # 호출자가 in-memory 인스턴스를 보고 있을 수 있어 동기화
        session.steps.append(copy.deepcopy(step_dict))

    def update_step(self, session: Session, step_id: int, updates: dict) -> None:
        target = self._sessions.get(session.session_id)
        if target is None:
            raise FileNotFoundError(f"세션을 찾을 수 없습니다: {session.session_id}")
        for st in target.steps:
            if isinstance(st, dict) and st.get("step_id") == step_id:
                st.update(updates)
                break
        target.updated_at = datetime.now().isoformat()
        # 호출자 인스턴스도 갱신
        for st in session.steps:
            if isinstance(st, dict) and st.get("step_id") == step_id:
                st.update(updates)
                break

    def delete_step(self, session: Session, step_id: int) -> bool:
        target = self._sessions.get(session.session_id)
        if target is None:
            return False
        before = len(target.steps)
        target.steps = [
            st for st in target.steps if not (isinstance(st, dict) and st.get("step_id") == step_id)
        ]
        if len(target.steps) == before:
            return False
        # ID 재정렬
        for i, st in enumerate(target.steps, start=1):
            if isinstance(st, dict):
                st["step_id"] = i
        target.updated_at = datetime.now().isoformat()
        # 호출자 인스턴스 동기화
        session.steps = copy.deepcopy(target.steps)
        return True

    def insert_step(
        self,
        session: Session,
        after_step_id: int,
        code: str = "",
        description: str = "삽입된 스텝",
    ) -> int:
        target = self._sessions.get(session.session_id)
        if target is None:
            raise FileNotFoundError(f"세션을 찾을 수 없습니다: {session.session_id}")
        new_step = {
            "step_id": after_step_id + 1,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "generated_code": code,
            "step_code": code,
            "step_imports": [],
            "conversation": [],
            "captures": [],
            "required_packages": [],
            "user_request": description,
            "ai_description": "",
        }
        # after_step_id 다음에 삽입 + 이후 step_id +1
        new_steps = []
        inserted = False
        for st in target.steps:
            if isinstance(st, dict):
                if st.get("step_id", 0) > after_step_id and not inserted:
                    new_steps.append(new_step)
                    inserted = True
                if inserted:
                    st = dict(st)
                    st["step_id"] = st.get("step_id", 0) + 1
            new_steps.append(st)
        if not inserted:
            new_steps.append(new_step)
        target.steps = new_steps
        target.updated_at = datetime.now().isoformat()
        session.steps = copy.deepcopy(target.steps)
        return new_step["step_id"]

    def move_step(self, session: Session, step_id: int, direction: str) -> bool:
        target = self._sessions.get(session.session_id)
        if target is None:
            return False
        idx = None
        for i, st in enumerate(target.steps):
            if isinstance(st, dict) and st.get("step_id") == step_id:
                idx = i
                break
        if idx is None:
            return False
        if direction == "up" and idx > 0:
            target.steps[idx - 1], target.steps[idx] = target.steps[idx], target.steps[idx - 1]
        elif direction == "down" and idx < len(target.steps) - 1:
            target.steps[idx + 1], target.steps[idx] = target.steps[idx], target.steps[idx + 1]
        else:
            return False
        # ID 재부여
        for i, st in enumerate(target.steps, start=1):
            if isinstance(st, dict):
                st["step_id"] = i
        target.updated_at = datetime.now().isoformat()
        session.steps = copy.deepcopy(target.steps)
        return True

    # ── Export / Import — In-memory 는 미지원 ──────────

    def export_session_as_project(
        self,
        session: Session,
        output_dir: Path,
        *,
        settings: Optional[dict] = None,
        ai_generated_readme: Optional[str] = None,
    ) -> Path:
        raise NotImplementedError(
            "InMemoryRepository 는 file IO 가 본 의도가 아님 — "
            "export 는 LocalJsonRepository 또는 향후 backend 구현체 사용"
        )

    def import_session_folder(
        self,
        source_dir: Path,
        *,
        new_title: Optional[str] = None,
    ) -> Session:
        raise NotImplementedError(
            "InMemoryRepository 는 file IO 가 본 의도가 아님 — "
            "import 는 LocalJsonRepository 또는 향후 backend 구현체 사용"
        )
