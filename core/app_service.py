# SPDX-License-Identifier: AGPL-3.0-or-later
"""UI·서버 공용 애플리케이션 진입점 (Facade).

현재 ``ui/main_window.py`` 가 ``SessionManager`` / ``AIEngineManager`` /
``WorkflowEngine`` 을 직접 import 해서 쓴다. SaaS 로 확장하면 FastAPI 라우터,
Agent runner, 새 UI 컴포넌트 등에서도 동일한 로직을 호출해야 하는데, 그때마다
UI 와 같은 import 경로를 반복할 수는 없다.

``AppService`` 는 도메인 연산의 **단일 진입점**이다.

- 기존 UI 는 건드리지 않는다 ([ADR 0001](../docs/saas/decisions/0001-preserve-existing-core.md)).
- 새로 추가되는 모든 호출자(백엔드, Agent, 새 UI v2)는 이 클래스만 의존한다.
- 세션/스텝 CRUD + 코드 추출 + 단독 실행 + AI ops 까지 cover.
- 상태 (current_session, kernel) 는 호출자가 보유. AppService 는 stateless façade —
  매 호출마다 필요한 객체를 인자로 받음.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from core.ai_engine import AIEngineManager
from core.execution_kernel import (
    INITIAL_BLOCK_STEP_ID,
    LIBRARY_BLOCK_STEP_ID,
    ExecutionKernel,
    StepResult,
)
from core.import_manager import (
    extract_code_delta,
    extract_import_delta,
    extract_imports,
    extract_initial_block,
    merge_imports,
)
from core.prompt_builder import PromptBuilder
from core.session_manager import Session, SessionSummary, Step
from core.win_inspector import WindowInspector, format_element_label
from core.workflow_engine import (
    CodeSandbox,
    WorkflowEngine,
    extract_library_block,
    extract_step_delta_code,
)

from .storage.base import SessionRepository

if TYPE_CHECKING:
    from core.adapters.base_adapter import AIResponse
    from core.recorder import Recorder
    from core.secrets import SecretsVault

# UI 가 직접 ``core.session_manager`` / ``core.execution_kernel`` 등을 import 하지
# 않도록 도메인 타입 + 코드 추출 pure 함수 + 핵심 클래스를 AppService 모듈에서
# re-export. ROADMAP §3 Phase 1 (2) KPI: "ui/ 폴더에서 session_manager·
# workflow_engine·ai_engine 직접 import 0건". ui/ legacy (Chunk B) 는
# `from core.app_service import ...` 단일 진입점만 사용.
__all__ = [
    "AppService",
    "Session",
    "SessionSummary",
    "Step",
    "ExecutionKernel",
    "StepResult",
    "INITIAL_BLOCK_STEP_ID",
    "LIBRARY_BLOCK_STEP_ID",
    # 핵심 클래스 re-export — UI 가 인스턴스 보유 / type hint 에 사용
    "AIEngineManager",
    "WorkflowEngine",
    "PromptBuilder",
    "WindowInspector",
    "CodeSandbox",
    # pure 함수 re-export — UI 가 함수 직접 호출 (manager-less)
    "extract_imports",
    "merge_imports",
    "extract_code_delta",
    "extract_import_delta",
    "extract_initial_block",
    "extract_library_block",
    "extract_step_delta_code",
    "format_element_label",
]


class AppService:
    """세션·스텝 CRUD 공용 Facade.

    Args:
        session_repo: 저장소 구현체. 로컬 기본은 ``LocalJsonRepository``.
        ai_manager: AI 엔진 매니저 (현재 1차에서는 미사용, 확장 지점만 확보).
        workflow_engine: 워크플로우 엔진 (현재 1차에서는 미사용, 확장 지점만 확보).
        secrets_vault: 비밀 정보 vault — [ADR 0003](../docs/saas/decisions/0003-secrets-handling.md)
            Phase 2-b. 미주입 시 vault 의존 path (runtime env 주입) 만 skip.
            ``placeholder`` 가 들어있는 prompt / generated_code 는 그대로 통과 —
            AI 가이드 (system_context #21) 가 ``get_secret()`` 패턴 생성 유도.
    """

    def __init__(
        self,
        session_repo: SessionRepository,
        ai_manager: Optional["AIEngineManager"] = None,
        workflow_engine: Optional["WorkflowEngine"] = None,
        prompt_builder: Optional["PromptBuilder"] = None,
        secrets_vault: Optional["SecretsVault"] = None,
    ) -> None:
        self._repo = session_repo
        self._ai = ai_manager
        self._engine = workflow_engine
        self._prompt_builder = prompt_builder
        self._secrets_vault = secrets_vault

        # [ADR 0004 PR-14] 작업 녹화 lifecycle 상태 — 단일 instance per AppService.
        # UI 가 동시에 두 녹화 진입하지 못하도록 Recorder 자체가 거부 (lock).
        self._recorder: Optional["Recorder"] = None
        self._recording_listeners: list[Callable[[str, dict], None]] = []  # (event_name, payload)

    @classmethod
    def create_default(
        cls,
        data_dir: "Path | str",
        settings: Optional[dict] = None,
    ) -> "AppService":
        """데스크톱 앱 기본 셋업 — LocalJsonRepository + AIEngineManager 를 자동 생성.

        UI 가 ``core.ai_engine`` / ``core.storage.local_json`` 를 직접 import
        하지 않아도 되게 한다 (ROADMAP §3 Phase 1 (2) KPI).

        Args:
            data_dir: 세션 저장소 디렉토리 (보통 ``Path("data")``).
            settings: ``settings.json`` 내용. ``None`` 이면 AI 미주입 상태로 생성.

        Returns:
            바로 사용 가능한 ``AppService`` 인스턴스.
        """
        from core.ai_engine import AIEngineManager

        from .storage.local_json import LocalJsonRepository

        repo = LocalJsonRepository(data_dir=Path(data_dir))
        ai_mgr = AIEngineManager(settings) if settings is not None else None

        # ADR 0003 Phase 2-b — KeyringVault 자동 시도, 실패 시 None (vault 의존 path skip).
        # 헤드리스/CI 환경 (keyring backend 없음) 에서도 데스크톱 앱 자체는 정상 부팅.
        vault = None
        try:
            from core.secrets import KeyringVault

            vault = KeyringVault(index_path=Path(data_dir) / "vault_index.json")
        except Exception as exc:  # noqa: BLE001 — best-effort
            import logging

            logging.getLogger(__name__).info(
                "KeyringVault 초기화 실패 — vault 의존 path 비활성 (%s)", exc
            )

        return cls(session_repo=repo, ai_manager=ai_mgr, secrets_vault=vault)

    def reload_ai(self, settings: dict) -> None:
        """Settings 변경 후 AI 엔진 재초기화 (UI 가 ``AIEngineManager`` 를 직접 import 안 하도록)."""
        from core.ai_engine import AIEngineManager

        self._ai = AIEngineManager(settings)

    def create_kernel(self) -> ExecutionKernel:
        """새 ``ExecutionKernel`` 인스턴스 — 세션별 분리 사용.

        UI 가 ``core.execution_kernel`` 을 직접 import 안 하도록 factory 제공.
        ADR 0003 Phase 2-b — vault 가 있으면 kernel 에 주입 (env 자동 주입).
        """
        return ExecutionKernel(secrets_vault=self._secrets_vault)

    @property
    def secrets_vault(self) -> Optional["SecretsVault"]:
        """vault 인스턴스 — UI Settings 시크릿 관리 탭이 직접 호출용 (PR-4)."""
        return self._secrets_vault

    @property
    def repo(self) -> SessionRepository:
        return self._repo

    @property
    def ai_manager(self) -> Optional["AIEngineManager"]:
        """AI 엔진 매니저 — UI 가 가끔 직접 호출 필요한 경우 (예: chat panel)."""
        return self._ai

    @property
    def workflow_engine(self) -> "WorkflowEngine":
        """``WorkflowEngine`` 인스턴스 — 미주입 시 lazy 생성.

        UI 가 직접 ``core.workflow_engine.WorkflowEngine`` 을 import / 보유 안 해도
        되도록 façade. 외부에서 settings 기반 인스턴스를 ``set_workflow_engine`` 으로
        주입하면 그것을 그대로 사용.
        """
        return self._get_or_create_engine()

    def set_workflow_engine(self, engine: "WorkflowEngine") -> None:
        """외부에서 settings 반영해 만든 ``WorkflowEngine`` 인스턴스를 주입.

        예: UI 가 ``execution.step_delay_ms`` / ``visual_feedback.enabled`` 를
        반영한 ``WorkflowEngine(...)`` 를 만들어 set 호출. 이후 ``run_blocks`` /
        ``stop_blocks`` 모두 그 인스턴스 경유.
        """
        self._engine = engine

    @property
    def prompt_builder(self) -> "PromptBuilder":
        """``PromptBuilder`` 인스턴스 — 미주입 시 lazy 생성 (default config).

        UI 가 ``prompts.json`` 로딩 + 인스턴스 생성 + 주입 패턴이면
        ``set_prompt_builder`` 로 미리 주입. 그렇지 않으면 빈 config 로 lazy 생성.
        """
        if self._prompt_builder is None:
            self._prompt_builder = PromptBuilder()
        return self._prompt_builder

    def set_prompt_builder(self, builder: "PromptBuilder") -> None:
        """외부에서 ``prompts.json`` 등 config 와 함께 만든 ``PromptBuilder`` 주입."""
        self._prompt_builder = builder

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

    def save_session(self, session: "Session") -> None:
        """세션 변경사항을 저장 (제목/메타/스텝 등). repo 에 위임.

        ui_v2 의 세션 이름 변경, 사이드바 액션 등 in-memory 변경 후 호출.
        handoff §3 의 AppService 메서드 목록에 명시됐지만 실제 정의 누락이라
        ui_v2 가 AttributeError 발생 (5/6 사용자 보고).
        """
        self._repo.save_session(session)

    # ── Export / Import (D22) ──────────────────────────

    def export_workflow(
        self,
        session_id: str,
        output_dir: "Path | str",
        *,
        settings: Optional[dict] = None,
        ai_generated_readme: Optional[str] = None,
    ) -> "Path":
        """세션을 독립 프로젝트 폴더로 내보낸다.

        결과 폴더 구성: ``main.py`` / ``requirements.txt`` / ``README.md`` /
        ``run.bat`` (실행 가능) + ``session.json`` / ``captures/`` / ``scripts/``
        (``import_workflow`` 로 재가져오기 가능).

        Args:
            session_id: 내보낼 세션 ID.
            output_dir: 출력 폴더 경로. 없으면 자동 생성.
            settings: ``output_project`` 설정 (settings.json). ``None`` 이면 기본값.
            ai_generated_readme: AI 가 생성한 README 내용 (선택).

        Returns:
            생성된 프로젝트 폴더 경로 (``Path``).

        Raises:
            NotImplementedError: 저장소 백엔드가 export 미지원
                (``InMemoryRepository`` 등). file IO 가 의도되지 않는 backend
                는 raise — Phase 2 의 ``PostgresRepository`` 는 zip stream 같은
                대안 메커니즘으로 구현 가능.
        """
        session = self._repo.load_session(session_id)
        return self._repo.export_session_as_project(
            session=session,
            output_dir=Path(output_dir),
            settings=settings,
            ai_generated_readme=ai_generated_readme,
        )

    def import_workflow(
        self,
        source_dir: "Path | str",
        *,
        new_title: Optional[str] = None,
    ) -> "Session":
        """외부 export 폴더로부터 세션을 임포트한다.

        ``export_workflow`` 결과 폴더 (또는 같은 구조의 폴더 — ``session.json`` 필수)
        를 받아 새 UUID 로 ``data/sessions/`` 에 복사. 기존 세션과 충돌하지 않음.

        Args:
            source_dir: ``session.json`` 이 들어있는 폴더 경로.
            new_title: 임포트 후 세션 제목 변경. ``None`` 이면 원본 제목 유지.

        Returns:
            새로 만든 세션 (``Session``).

        Raises:
            NotImplementedError: 저장소 백엔드가 import 미지원
                (``InMemoryRepository`` 등).
        """
        return self._repo.import_session_folder(
            source_dir=Path(source_dir),
            new_title=new_title,
        )

    # ── 작업 녹화 (ADR 0004 PR-14) ─────────────────────

    def add_recording_listener(self, callback: Callable[[str, dict], None]) -> None:
        """녹화 lifecycle 이벤트 listener 등록.

        callback 시그니처: ``(event_name: str, payload: dict) -> None``.

        이벤트 종류:
        - ``"recording.started"`` — payload: ``{recording_session_id, target_session_id}``
        - ``"recording.stopped"`` — payload: ``{recording_session_id, raw_event_count,
          transformed_step_count}``
        - ``"recording.committed"`` — payload: ``{recording_session_id, target_session_id,
          step_count}``
        """
        if callback not in self._recording_listeners:
            self._recording_listeners.append(callback)

    def remove_recording_listener(self, callback: Callable[[str, dict], None]) -> None:
        try:
            self._recording_listeners.remove(callback)
        except ValueError:
            pass

    def _emit_recording_event(self, event_name: str, payload: dict) -> None:
        for cb in list(self._recording_listeners):
            try:
                cb(event_name, payload)
            except Exception:
                import logging

                logging.getLogger(__name__).exception(
                    "recording listener 예외 (격리됨): event=%s", event_name
                )

    @property
    def is_recording(self) -> bool:
        return self._recorder is not None and self._recorder.is_recording

    @property
    def recording_event_count(self) -> int:
        return self._recorder.event_count if self._recorder else 0

    def start_recording(
        self,
        target_session_id: Optional[str] = None,
        element_capture_fn: Optional[Callable[[int, int], Optional[dict]]] = None,
        stop_hotkey_callback: Optional[Callable[[], None]] = None,
    ) -> str:
        """녹화 시작. 신규 RecordingSession id 반환.

        이미 녹화 중이면 ``RecorderAlreadyStartedError``.

        Args:
            target_session_id: commit 시 step 들을 추가할 ohdo Session id.
                ``None`` 이면 commit_recording 에서 새 세션 자동 생성.
            element_capture_fn: 클릭 시점 element 메타 capture callback.
                일반적으로 ``WindowInspector`` 의 EFP 함수 (PR-15 UI 가 주입).
            stop_hotkey_callback: Ctrl+Shift+R 글로벌 stop hotkey trigger 시 호출
                (2026-05-20 실측 fix). hook thread 에서 호출되므로 UI 측은
                반드시 thread-safe (QTimer.singleShot 등) 으로 stop 처리해야 함.
        """
        from core.input_hooks import get_hook_manager
        from core.recorder import Recorder, RecorderAlreadyStartedError

        if self._recorder is not None and self._recorder.is_recording:
            raise RecorderAlreadyStartedError("AppService: 이미 녹화 중. stop_recording 먼저 호출.")

        self._recorder = Recorder(
            hook_manager=get_hook_manager(),
            element_capture_fn=element_capture_fn,
            stop_hotkey_callback=stop_hotkey_callback,
        )
        rec_session = self._recorder.start(target_session_id=target_session_id)
        self._emit_recording_event(
            "recording.started",
            {
                "recording_session_id": rec_session.id,
                "target_session_id": target_session_id,
            },
        )
        return rec_session.id

    def stop_recording(self, self_window_titles: Optional[list[str]] = None) -> list[Step]:
        """녹화 종료 + raw events → Step 변환. commit 은 별도 단계.

        Args:
            self_window_titles: ohdo 자체 창 title 리스트 (drop_self_window_clicks
                필터용). 예: ``["ohdo"]``.

        Returns:
            변환된 Step 리스트. ``commit_recording`` 으로 ohdo Session 에 추가.
        """
        from core.recorder import RecorderNotStartedError
        from core.recorder_transform import transform

        if self._recorder is None:
            raise RecorderNotStartedError("AppService: 녹화 안 한 상태에서 stop_recording.")

        rec_session = self._recorder.stop()
        steps = transform(rec_session, self_window_titles=self_window_titles)

        self._emit_recording_event(
            "recording.stopped",
            {
                "recording_session_id": rec_session.id,
                "raw_event_count": rec_session.event_count,
                "transformed_step_count": len(steps),
            },
        )
        return steps

    def commit_recording(
        self,
        edited_steps: list[Step],
        target_session_id: Optional[str] = None,
        new_session_title: Optional[str] = None,
    ) -> "Session":
        """편집된 step 리스트를 ohdo Session 에 batch 추가.

        Args:
            edited_steps: review dialog (PR-15) 에서 사용자가 편집한 Step 리스트.
            target_session_id: 추가할 세션 id. ``None`` 이면 새 세션 자동 생성.
            new_session_title: target_session_id None 시 새 세션 제목. None 이면
                "Recording YYYYMMDD-HHMMSS" 자동.

        Returns:
            commit 된 Session.
        """
        from datetime import datetime

        # PR-19f (2026-05-24): commit 시점에 녹화 metadata 추출 (cleanup 전).
        # 사용자 사후 분석 / 디버깅 / 미래 raw event 재변환 시 유용.
        rec_meta: Optional[dict] = None
        if self._recorder is not None and self._recorder.current_session is not None:
            rs = self._recorder.current_session
            duration_sec: Optional[float] = None
            try:
                if rs.stopped_at is not None:
                    duration_sec = (rs.stopped_at - rs.started_at).total_seconds()
            except Exception:
                duration_sec = None
            rec_meta = {
                "recording_session_id": rs.id,
                "started_at": rs.started_at.isoformat(),
                "stopped_at": rs.stopped_at.isoformat() if rs.stopped_at else None,
                "duration_sec": duration_sec,
                "raw_event_count": rs.event_count,
                "transformed_step_count": len(edited_steps),
                "dropped_event_count": self._recorder.dropped_event_count,
                "committed_at": datetime.now().isoformat(),
            }

        if target_session_id is None:
            title = new_session_title or f"Recording {datetime.now().strftime('%Y%m%d-%H%M%S')}"
            session = self.create_session(title=title, description="작업 녹화로 자동 생성")
            target_session_id = session.session_id
        else:
            session = self._repo.load_session(target_session_id)

        for step in edited_steps:
            self._repo.add_step(session, step)

        # PR-19f: 녹화 metadata 를 Session 에 보존 + 저장
        if rec_meta is not None:
            committed_step_ids = [
                getattr(s, "step_id", None) if not isinstance(s, dict) else s.get("step_id")
                for s in session.steps[-len(edited_steps) :]
            ]
            rec_meta["committed_step_ids"] = [sid for sid in committed_step_ids if sid]

            # PR-19i (2026-05-24): raw events JSONL 저장 — 사후 재변환 / 디버깅 /
            # 옵션 비교 분석용. 저장 실패해도 commit 자체는 성공 (graceful).
            # InMemoryRepository / 백엔드 미지원 시 None 반환 → metadata 미기록.
            if self._recorder is not None and self._recorder.current_session is not None:
                rs = self._recorder.current_session
                try:
                    events_json = [
                        ev.model_dump(mode="json", exclude_none=True) for ev in rs.events
                    ]
                    raw_path = self._repo.save_recording_raw_events(
                        session_id=target_session_id,
                        recording_session_id=rs.id,
                        events=events_json,
                    )
                    if raw_path:
                        rec_meta["raw_events_path"] = raw_path
                except Exception:
                    import logging as _logging

                    _logging.getLogger(__name__).exception(
                        "PR-19i: raw events JSONL 저장 실패 (commit 자체는 성공): rec=%s",
                        rs.id,
                    )

            if not hasattr(session, "recording_meta") or session.recording_meta is None:
                session.recording_meta = []
            session.recording_meta.append(rec_meta)
            self._repo.save_session(session)

        self._emit_recording_event(
            "recording.committed",
            {
                "recording_session_id": (
                    self._recorder.current_session.id
                    if self._recorder and self._recorder.current_session
                    else None
                ),
                "target_session_id": target_session_id,
                "step_count": len(edited_steps),
            },
        )

        # 녹화 lifecycle 종료 후 Recorder 인스턴스 정리 (다음 start 가 새 instance)
        self._recorder = None
        return session

    # ── 스텝 ───────────────────────────────────────────

    def add_step(self, session_id: str, step: Step) -> None:
        session = self._repo.load_session(session_id)
        self._repo.add_step(session, step)

    def update_step(self, session_id: str, step_id: int, updates: dict) -> None:
        session = self._repo.load_session(session_id)
        self._repo.update_step(session, step_id, updates)

    def delete_step(self, session_id: str, step_id: int) -> bool:
        """step 삭제 + cumulative generated_code chain 재구성.

        2026-05-12 사용자 보고 버그: 단순 `_repo.delete_step` 은 session.steps
        에서 대상만 빼고 step_id 만 renumber. 각 step 의 generated_code 는
        **cumulative** (library + 이전 step 들의 코드 누적) 이므로 삭제 후에도
        후속 step 의 generated_code 에 삭제된 step 의 코드가 잔존 → 전체 실행
        시 삭제된 코드가 그대로 실행됨.

        Fix: `reorder_step` 의 step_code 사전 추출 + chain 재구성 패턴 동일 적용.
        1. 삭제 전 모든 step 의 step_code 추출 (chain 정상 시점).
        2. step_code + manually_edited=True 마킹 (downstream 우선순위 0).
        3. 대상 step 제거.
        4. 새 순서대로 generated_code 재구성 (library + step_code 누적).
        5. renumber + save.
        """
        session = self._repo.load_session(session_id)
        steps = session.steps

        target_idx = None
        for i, s in enumerate(steps):
            sid = s.get("step_id") if isinstance(s, dict) else getattr(s, "step_id", 0)
            if sid == step_id:
                target_idx = i
                break
        if target_idx is None:
            return False

        # 1. 모든 step 의 step_code 사전 추출 (재정렬 전 — chain 정상 시점).
        from core.workflow_engine import (
            extract_library_block,
            extract_step_delta_code,
        )

        library_code = extract_library_block(session)
        prev = None
        for s in steps:
            if not isinstance(s, dict):
                prev = s
                continue
            if s.get("manually_edited") and s.get("step_code", "").strip():
                pass
            else:
                sc = extract_step_delta_code(s, prev)
                s["step_code"] = sc
                s["manually_edited"] = True
            prev = s

        # 2. 대상 step 제거
        steps.pop(target_idx)

        # 3. 새 순서대로 generated_code 재구성 (library + step_code 누적)
        accumulated = library_code
        for s in steps:
            if not isinstance(s, dict):
                continue
            sc = s.get("step_code", "")
            if accumulated.strip() and sc.strip():
                accumulated = accumulated + "\n\n" + sc
            elif sc.strip():
                accumulated = sc
            s["generated_code"] = accumulated

        # 4. renumber + save
        for i, s in enumerate(steps):
            if isinstance(s, dict):
                s["step_id"] = i + 1
            else:
                s.step_id = i + 1
        self._repo.save_session(session)
        return True

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
        """⬆⬇ step 이동 — 안전한 reorder_step 으로 위임.

        주의 (사용자 보고 5/5): 기존 SessionManager.move_step 은 단순 swap +
        renumber 만 해서 cumulative ``generated_code`` chain 이 깨짐 → 실행 시
        잘못된 delta. reorder_step 의 step_code 사전 추출 + generated_code 재구성
        path 로 위임해 안전하게 처리.
        """
        session = self._repo.load_session(session_id)
        steps = session.steps
        cur = None
        for i, s in enumerate(steps):
            ssid = s.get("step_id") if isinstance(s, dict) else getattr(s, "step_id", 0)
            if ssid == step_id:
                cur = i
                break
        if cur is None:
            return False
        if direction == "up" and cur > 0:
            target_idx = cur - 1
        elif direction == "down" and cur < len(steps) - 1:
            target_idx = cur + 1
        else:
            return False
        target_step = steps[target_idx]
        target_sid = (
            target_step.get("step_id")
            if isinstance(target_step, dict)
            else getattr(target_step, "step_id", 0)
        )
        return self.reorder_step(session_id, step_id, target_sid)

    def reorder_step(self, session_id: str, step_id: int, target_step_id: int) -> bool:
        """drag-drop reorder — step_id 를 target_step_id 의 자리로 이동.

        **누적 chain 보존** (사용자 보고 5/5): 단순 pop+insert 는 cumulative
        ``generated_code`` 가 깨져 실행 시 잘못된 delta 가 추출됨. 따라서:

        1. 재정렬 **전** 모든 step 의 step_code 를 ``extract_step_delta_code`` 로
           추출 (현 generated_code 의 마커/diff 활용 — 이 시점은 chain 정상).
        2. 추출한 step_code 를 step 에 보존 + ``manually_edited=True`` 마킹
           (downstream 의 extract_step_delta_code 우선순위 0 으로 step_code 사용).
        3. pop(cur) + insert(tgt) — 새 순서.
        4. **새 순서대로 generated_code 재구성** (library + step_code 누적). 다음
           AI 호출 / kernel 실행 모두 새 순서에 맞는 누적 코드 봄.
        5. renumber + save.

        Args:
            session_id: 세션
            step_id: 이동할 step (현재 step_id)
            target_step_id: 이동 목표 위치의 step (그 자리에 step_id 가 들어감)

        Returns:
            실제 이동 발생 여부 (no-op 시 False)
        """
        if step_id == target_step_id:
            return False
        session = self._repo.load_session(session_id)
        steps = session.steps

        def _idx(sid):
            for i, s in enumerate(steps):
                ssid = s.get("step_id") if isinstance(s, dict) else getattr(s, "step_id", 0)
                if ssid == sid:
                    return i
            return None

        cur = _idx(step_id)
        tgt = _idx(target_step_id)
        if cur is None or tgt is None or cur == tgt:
            return False

        # 1. 모든 step 의 step_code 사전 추출 (재정렬 전 — chain 정상 시점).
        #    이미 step_code + manually_edited=True 면 그대로 보존.
        from core.workflow_engine import (
            extract_library_block,
            extract_step_delta_code,
        )

        library_code = extract_library_block(session)
        prev = None
        for s in steps:
            if not isinstance(s, dict):
                prev = s
                continue
            # 이미 manually_edited 사용자 수정이 있으면 step_code 그대로 유지
            if s.get("manually_edited") and s.get("step_code", "").strip():
                pass
            else:
                sc = extract_step_delta_code(s, prev)
                s["step_code"] = sc
                s["manually_edited"] = True  # downstream 우선순위 0 으로 step_code 사용
            prev = s

        # 2. pop + insert
        moved = steps.pop(cur)
        steps.insert(tgt, moved)

        # 3. 새 순서대로 generated_code 재구성 (library + step_code 누적)
        accumulated = library_code
        for s in steps:
            if not isinstance(s, dict):
                continue
            sc = s.get("step_code", "")
            if accumulated.strip() and sc.strip():
                accumulated = accumulated + "\n\n" + sc
            elif sc.strip():
                accumulated = sc
            # accumulated 가 빈 채로 sc 도 빈 경우는 그대로 유지
            s["generated_code"] = accumulated

        # 4. renumber (step_id 1..N 재부여) + save — abstraction 만 사용.
        for i, s in enumerate(steps):
            if isinstance(s, dict):
                s["step_id"] = i + 1
            else:
                s.step_id = i + 1
        self._repo.save_session(session)
        return True

    # ── 코드 추출 (pure functions 위임) ──────────────────────────────
    # UI 가 workflow_engine / import_manager 를 직접 import 하지 않도록 façade 제공.

    def get_library_block_code(self, session: "Session") -> str:
        """라이브러리 블럭 (imports + 헬퍼) 코드 추출."""
        from core.workflow_engine import extract_library_block

        return extract_library_block(session)

    def get_initial_block_code(self, session: "Session") -> str:
        """Initial 블럭 (모듈 레벨 변수/setup) 코드 추출."""
        from core.import_manager import extract_initial_block

        return extract_initial_block(session)

    def get_step_delta_code(self, step: dict, prev_step: Optional[dict] = None) -> str:
        """Step delta 코드 (이전 step 과의 차이) 추출.

        manually_edited=True + step_code 우선, marker 추출, diff 재계산 순.
        """
        from core.workflow_engine import extract_step_delta_code

        return extract_step_delta_code(step, prev_step)

    # ── Block 실행 ops (kernel 외부 주입) ──────────────────────────────
    # kernel 의 lifecycle / threading / UI 갱신은 호출자 (handler 또는 ui_v2) 책임.
    # AppService 는 "어떤 코드를 어떤 step_id 로 보낼지" 만 결정.

    async def run_blocks(
        self,
        session: "Session",
        kernel: "ExecutionKernel",
        start_from_step_id: int = 1,
        stop_after_step_id: Optional[int] = None,
        silent_replay: bool = True,
        on_step_start: Optional[Callable[[int], None]] = None,
        on_step_complete: Optional[Callable] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ):
        """블럭 기반 실행 — 전체 / 여기서부터 / 단독 모두 cover.

        호출 패턴:
          - 전체 실행:    ``run_blocks(session, kernel)`` (start=1, stop=None)
          - 여기서부터:   ``run_blocks(session, kernel, start_from_step_id=N)``
          - Step 단독:    ``run_blocks(session, kernel, start_from_step_id=N, stop_after_step_id=N)``

        WorkflowEngine 인스턴스가 미주입이면 default 로 lazy 생성.
        ``stop_blocks()`` 로 진행 중 중지 신호 전달 가능.

        Returns:
            ``ExecutionReport`` — engine.execute_session_blocks 반환값
        """
        engine = self._get_or_create_engine()

        def on_error_wrapped(sid, msg):
            if on_log:
                on_log(f"Step {sid} 실패: {msg}")

        report = await engine.execute_session_blocks(
            session=session,
            kernel=kernel,
            start_from_step_id=start_from_step_id,
            stop_after_step_id=stop_after_step_id,
            silent_replay=silent_replay,
            on_step_start=on_step_start,
            on_step_complete=on_step_complete,
            on_error=on_error_wrapped,
            on_log=on_log,
        )
        # 실행으로 갱신된 step.status(completed/failed)를 session.json 에 영속화 (devloop #6).
        # UI 는 onDone 후 세션을 invalidate→refetch 하므로 영속화돼야 배지가 실제 실행
        # 결과를 보여준다. 이전엔 미영속화로 status 가 'pending' 에 고착했다.
        try:
            self.save_session(session)
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "run_blocks: 실행 후 session 영속화 실패", exc_info=True
            )
        return report

    def stop_blocks(self) -> None:
        """진행 중인 ``run_blocks`` 실행을 중지 (should_stop 플래그)."""
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                pass

    def _get_or_create_engine(self) -> "WorkflowEngine":
        """WorkflowEngine lazy 생성. 외부 주입돼있으면 그대로 사용."""
        if self._engine is None:
            from core.workflow_engine import WorkflowEngine

            self._engine = WorkflowEngine()
        return self._engine

    def run_initial_block_sync(
        self,
        session: "Session",
        initial_code: str,
        kernel: "ExecutionKernel",
        on_log: Optional[Callable[[str], None]] = None,
    ) -> "StepResult":
        """Initial 블럭 단독 실행 (Phase 2.5 contract, [handoff §4.9](../docs/handoff.md)).

        라이브러리 블럭이 커널에 미초기화면 자동 선행 (NameError 회귀 방지).
        그 후 initial_code 를 step_id=INITIAL_BLOCK_STEP_ID 로 실행.
        다른 step 들의 ``kernel.executed_steps`` 는 건드리지 않음.

        Args:
            session: 라이브러리 코드 추출용
            initial_code: 사용자 편집 반영된 Initial 카드 텍스트
            kernel: ``ExecutionKernel`` 인스턴스 (호출자가 lifecycle 관리)
            on_log: 진행 메시지 콜백 (선택)

        Returns:
            ``StepResult`` — kernel.execute_block 결과
        """
        from core.execution_kernel import INITIAL_BLOCK_STEP_ID, LIBRARY_BLOCK_STEP_ID

        if LIBRARY_BLOCK_STEP_ID not in kernel.executed_steps:
            lib_block = self.get_library_block_code(session)
            if lib_block.strip():
                if on_log:
                    on_log("📦 라이브러리 블럭 초기화 중...")
                lib_result = kernel.execute_block(
                    lib_block, step_id=LIBRARY_BLOCK_STEP_ID, timeout=30
                )
                if not lib_result.success and on_log:
                    on_log(f"⚠️ 라이브러리 블럭 실행 오류: {lib_result.error}")

        if on_log:
            on_log("🎬 Initial 블럭 실행 시작...")
        return kernel.execute_block(initial_code, step_id=INITIAL_BLOCK_STEP_ID)

    # ── AI ops (AIEngineManager 위임 — None 주입 시 NotImplementedError) ──

    async def generate(self, prompt: str, images: Optional[list[str]] = None) -> "AIResponse":
        if self._ai is None:
            raise RuntimeError(
                "AppService 에 AIEngineManager 가 주입되지 않았습니다. "
                "생성자에서 ai_manager= 인자 전달 필요."
            )
        return await self._ai.generate(prompt, images)

    async def generate_step(
        self,
        session: "Session",
        user_request: str,
        images: Optional[list[str]] = None,
        *,
        prompt_builder=None,
        on_progress: Optional[Callable[[str], None]] = None,
        element_context: Optional[str] = None,
        window_context: Optional[str] = None,
        is_browser_element: bool = False,
        previous_warnings: Optional[list[dict]] = None,
        replaces_step_id: Optional[int] = None,
    ) -> tuple[Optional[Step], "AIResponse"]:
        """사용자 요청 → 프롬프트 구성 → AI 호출 → Step 생성 + 세션에 추가.

        D3 (UI redesign) 의 핵심 path. ui_v2 의 메시지 전송 핸들러가 호출.

        흐름:
          1. PromptBuilder 로 prompt 구성 (이전 step 컨텍스트 + 시스템 지시 포함).
          2. AIEngineManager.generate 호출.
          3. AIResponse 가 success 면 Step 생성:
             - user_request: 입력 그대로
             - ai_description: response.description (코드 제외 텍스트)
             - generated_code: response.code
             - required_packages: response.packages
             - status: "pending" (아직 미실행)
          4. ``add_step`` 으로 session 에 추가 + 자동 저장.

        실패 시 (response.success=False) Step 안 생성. 호출자가 response.error 처리.

        Args:
            session: 현재 세션 (project_type 사용)
            user_request: 사용자 입력 자연어
            images: 첨부 이미지 경로
            prompt_builder: 외부 주입 가능 (test 용 mock). 미주입 시 default 생성.
            on_progress: 진행 메시지 콜백

        Returns:
            (Optional[Step], AIResponse) — 성공 시 (Step, response), 실패 시 (None, response).
        """
        if self._ai is None:
            raise RuntimeError("AIEngineManager 미주입 — generate_step 사용 불가")

        if prompt_builder is None:
            from core.prompt_builder import PromptBuilder

            prompt_builder = PromptBuilder()

        if on_progress:
            on_progress("프롬프트 구성 중...")
        # 이미지는 AI 에 전달하지 않음 (5/6 사용자 결정):
        # - element_context (control_type/name/auto_id/parent_title 등) 가 이미 풍부 → 이미지 가치 marginal
        # - vision 처리 latency 5-15s + Gemini context 부담 → corrupt 응답 risk
        # - session 에는 image path keep (UI 표시 + 미래 image-based matching 기능 시 활용)
        # P1b: system_context 와 user 영역을 split — OpenAI 호환 어댑터가 system role
        # 로 분리해서 messages 에 넣을 수 있도록. Gemini CLI 는 자체 prepend.
        system_text, user_text = prompt_builder.build_step_prompt_split(
            session=session,
            user_request=user_request,
            image_paths=None,
            project_type=getattr(session, "project_type", "desktop"),
            element_context=element_context,
            window_context=window_context,
            is_browser_element=is_browser_element,
            previous_warnings=previous_warnings,
        )
        # 로깅용 합본 (대화 로그 저장 + on_progress 메시지) — 어댑터엔 split 전달
        prompt = (system_text + "\n\n" + user_text) if system_text else user_text

        if on_progress:
            on_progress(f"AI 호출 중 (프롬프트 {len(prompt)}자)...")
        response = await self._ai.generate(user_text, None, system=system_text or None)

        # AI 대화 로그 저장 (성공/실패 모두) — 추후 디버깅·재현용.
        # 백업 [ohdo_20260505_backup/.../step0_prompt.txt + step0_generated_code.py] 처럼
        # 두 파일로 나누는 대신 하나의 파일에 prompt + 응답 합쳐 저장.
        try:
            self._save_conversation_log(
                session=session,
                user_request=user_request,
                prompt=prompt,
                response=response,
                image_paths=list(images) if images else [],
            )
        except Exception as _log_err:
            # 로깅 실패는 generate_step 의 본래 동작을 막지 않음
            if on_progress:
                on_progress(f"대화 로그 저장 실패 (무시): {_log_err}")

        if not response.success:
            return None, response

        # ── step_code / step_imports 분리 (5/5 회귀 fix) ──
        # 5/5 사용자 보고: AI 가 누적 코드를 생성하면서 marker 가 깨지면 fallback 으로
        # 전체 cumulative 가 실행되어 driver.get/maximize 가 여러 번 → 페이지 새로고침
        # 반복. 백업 [ui/ai_call_handler.py:248~287] 패턴 — generated_code 는 전체 누적
        # (다음 prompt 의 컨텍스트용) 로 저장하지만 step_code 에 이번 step delta 만,
        # step_imports 에 새 import 만 분리 저장. workflow_engine 의 extract_step_delta_code
        # 가 manually_edited 조건이면 우선순위 0 으로 step_code 사용.
        from .import_manager import (
            extract_code_delta as _ecd,
        )
        from .import_manager import (
            extract_import_delta as _eid,
        )
        from .import_manager import (
            extract_imports as _ei,
        )

        full_code = response.code or ""
        separated_imports, separated_body = _ei(full_code)
        prev_body = ""
        prev_imports: list[str] = []
        # 호출자가 stale session 참조를 갖고 있을 수 있어 디스크에서 fresh load.
        # add_step 이 repo 에서 새로 load 후 mutate 하므로 in-memory session 참조의
        # steps 가 갱신 안 됨 — fresh 로드해야 직전 step 들이 보임.
        try:
            steps_for_prev = self._repo.load_session(session.session_id).steps
        except Exception:
            steps_for_prev = session.steps
        # 직전 step 이 empty (AI 실패) 면 더 거슬러 올라가 last-non-empty step 사용.
        # 그렇지 않으면 prev_body="" 가 되어 delta = 전체 body → 중복 driver init 등 회귀.
        # replaces_step_id 가 주어지면 그 step 은 skip — 재생성 path 에서 자기 자신
        # 의 stale 코드를 prev 로 인식하면 delta=0 또는 잘못된 delta 회귀.
        for ls_data in reversed(steps_for_prev):
            ls = ls_data if isinstance(ls_data, dict) else {}
            if replaces_step_id is not None and ls.get("step_id") == replaces_step_id:
                continue
            prev_full = (ls.get("generated_code") or "").strip()
            if prev_full:
                prev_imports = list(ls.get("step_imports", []) or [])
                _, prev_body = _ei(prev_full)
                break
        delta_body = _ecd(separated_body, prev_body) if prev_body else separated_body
        delta_imports = _eid(separated_imports, prev_imports)

        # G7-B (Phase 1.8): AI 가 생성한 delta_body 정적 분석. DeepSeek 같은
        # 모델이 system_context 가이드를 100% 안 따르는 케이스 (변수 재정의 /
        # try-except 누락 / import 위치 위반 / SyntaxError) 를 사용자에게 경고.
        # 차단 X — 실행은 그대로 가능. UI 표시 + 자동 재생성은 G7-C/D.
        # 정적 분석 자체 실패는 try/except 로 막아 step 생성 흐름 보호.
        validation_warnings: list[dict] = []
        try:
            from .code_validator import validate_step_code

            prev_step_codes_for_check: list[str] = []
            for ls_data in steps_for_prev:
                ls = ls_data if isinstance(ls_data, dict) else {}
                sc = ls.get("step_code") or ""
                if sc:
                    prev_step_codes_for_check.append(sc)
            val_result = validate_step_code(delta_body, prev_step_codes=prev_step_codes_for_check)
            validation_warnings = [
                {"kind": iss.kind, "message": iss.message, "line": iss.line}
                for iss in val_result.issues
            ]
        except Exception:
            # 정적 분석 실패는 step 생성을 막지 않음
            pass

        # Step 생성 — D6: 첨부 이미지가 있으면 captures 에 보존
        # (카드 thumbnail 표시 + 디버깅 추적용)
        step = Step(
            status="pending",
            user_request=user_request,
            ai_description=response.description or "",
            generated_code=full_code,
            required_packages=list(response.packages or []),
            captures=list(images) if images else [],
            step_code=delta_body,
            step_imports=delta_imports,
            validation_warnings=validation_warnings,
        )

        # replaces_step_id 가 주어지면 in-place update — 새 step 추가 X.
        # 사용자 직관: ⚠ 재생성 = "이 step 의 문제 해결" → 기존 step 갱신.
        # 사용자 보고 (2026-05-12 메모장테스트): 재생성 path 가 add_step 으로
        # 새 step 추가 → 같은 user_request 두 개 존재 → 전체 실행 시 작업 2번
        # 또는 잘못된 step1 실패로 step2 도달 불가 회귀.
        if replaces_step_id is not None:
            updates = {
                "user_request": user_request,
                "ai_description": response.description or "",
                "generated_code": full_code,
                "required_packages": list(response.packages or []),
                "captures": list(images) if images else [],
                "step_code": delta_body,
                "step_imports": delta_imports,
                "validation_warnings": validation_warnings,
                "status": "pending",
                "execution_result": None,  # 이전 실행 결과 무효화
            }
            self.update_step(session.session_id, replaces_step_id, updates)
            step.step_id = replaces_step_id
        else:
            self.add_step(session.session_id, step)
        return step, response

    def _safe_get_ai_engine_name(self) -> str:
        """AI 엔진 이름을 안전하게 가져옴 (mock/실패 시 'unknown')."""
        try:
            return self.get_ai_engine_name() if self._ai else "unknown"
        except Exception:
            return type(self._ai).__name__ if self._ai else "unknown"

    def _save_conversation_log(
        self,
        session: "Session",
        user_request: str,
        prompt: str,
        response: "AIResponse",
        image_paths: list[str],
    ) -> Optional[str]:
        """AI 호출 1 회분 (prompt + 응답) 을 ``tmp/conversations/`` 에 단일 파일로 저장.

        백업 [ohdo_20260505_backup/.../step0_prompt.txt + step0_generated_code.py] 가
        두 파일로 분리됐던 패턴을 하나의 .md 파일로 통합. 추후 디버깅·재현·프롬프트 품질
        분석에 사용.

        파일명: ``{YYYYMMDD_HHMMSS}_step{N}_{session_short}.md``
        - YYYYMMDD_HHMMSS: 호출 시각 (정렬 + 충돌 방지)
        - N: 이번 호출로 추가될 step_id (호출 시점의 session.steps 길이 + 1)
        - session_short: session_id 의 첫 8 자

        Returns:
            저장된 파일의 절대 경로. 실패 시 None.
        """
        from datetime import datetime
        from pathlib import Path

        # 프로젝트 루트 = core/app_service.py 의 부모의 부모
        project_root = Path(__file__).resolve().parent.parent
        log_dir = project_root / "tmp" / "conversations"
        log_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        next_step_id = len(session.steps) + 1 if hasattr(session, "steps") else 0
        sid_short = session.session_id[:8] if hasattr(session, "session_id") else "noid"
        filename = f"{ts}_step{next_step_id}_{sid_short}.md"
        out_path = log_dir / filename

        # 본문 구성 — 백업 포맷 정신 유지 + 메타데이터 헤더 + 단일 파일에 prompt/응답 통합
        sep = "=" * 70
        meta_lines = [
            sep,
            "# AI 대화 로그",
            sep,
            f"- **타임스탬프**: {datetime.now().isoformat()}",
            f"- **세션 ID**: {getattr(session, 'session_id', 'unknown')}",
            f"- **세션 제목**: {getattr(session, 'title', 'unknown')}",
            f"- **프로젝트 유형**: {getattr(session, 'project_type', 'unknown')}",
            f"- **다음 step_id**: {next_step_id}",
            f"- **AI 엔진**: {self._safe_get_ai_engine_name()}",
            f"- **첨부 이미지**: {len(image_paths)} 개",
        ]
        if image_paths:
            for i, p in enumerate(image_paths, 1):
                meta_lines.append(f"  - {i}. {p}")
        meta_lines.extend(
            [
                f"- **프롬프트 길이**: {len(prompt)} 자",
                f"- **응답 길이**: {len(response.text or '')} 자",
                f"- **추출된 코드 길이**: {len(response.code or '')} 자",
                f"- **응답 success**: {response.success}",
                f"- **응답 partial**: {getattr(response, 'partial', False)}",
                f"- **소요 시간**: {getattr(response, 'response_time_ms', 0)} ms",
                f"- **토큰 사용량**: {getattr(response, 'tokens_used', 0)}",
            ]
        )
        if not response.success:
            meta_lines.append(f"- **에러**: {response.error}")

        body_parts = [
            "\n".join(meta_lines),
            "",
            sep,
            "# 사용자 요청 (원본)",
            sep,
            "",
            user_request or "(빈 요청)",
            "",
            sep,
            "# AI 에 전달된 전체 프롬프트",
            sep,
            "",
            prompt or "(빈 프롬프트)",
            "",
            sep,
            "# AI 응답 (원본 텍스트)",
            sep,
            "",
            response.text or "(빈 응답)",
            "",
            sep,
            "# 추출된 코드 (실행에 사용됨)",
            sep,
            "",
            "```python",
            response.code or "(코드 없음)",
            "```",
            "",
            sep,
            "# AI 설명 (코드 외 텍스트)",
            sep,
            "",
            response.description or "(설명 없음)",
            "",
        ]
        try:
            out_path.write_text("\n".join(body_parts), encoding="utf-8")
            return str(out_path)
        except Exception:
            return None

    def switch_ai_engine(self, engine_name: str) -> None:
        if self._ai is None:
            raise RuntimeError("AIEngineManager 미주입")
        self._ai.switch_engine(engine_name)

    def cancel_ai(self) -> None:
        if self._ai is None:
            return
        self._ai.cancel()

    def get_ai_engine_name(self) -> Optional[str]:
        if self._ai is None:
            return None
        return self._ai.get_current_name()

    def list_ai_engines(self) -> list[dict]:
        if self._ai is None:
            return []
        return self._ai.list_available()
