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

from typing import TYPE_CHECKING, Optional, Callable

from core.session_manager import Session, SessionSummary, Step

from .storage.base import SessionRepository

if TYPE_CHECKING:
    from core.ai_engine import AIEngineManager
    from core.workflow_engine import WorkflowEngine
    from core.execution_kernel import ExecutionKernel, StepResult
    from core.adapters.base_adapter import AIResponse


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

    def save_session(self, session: "Session") -> None:
        """세션 변경사항을 저장 (제목/메타/스텝 등). repo 에 위임.

        ui_v2 의 세션 이름 변경, 사이드바 액션 등 in-memory 변경 후 호출.
        handoff §3 의 AppService 메서드 목록에 명시됐지만 실제 정의 누락이라
        ui_v2 가 AttributeError 발생 (5/6 사용자 보고).
        """
        self._repo.save_session(session)

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
            ssid = (
                s.get("step_id") if isinstance(s, dict)
                else getattr(s, "step_id", 0)
            )
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
            target_step.get("step_id") if isinstance(target_step, dict)
            else getattr(target_step, "step_id", 0)
        )
        return self.reorder_step(session_id, step_id, target_sid)

    def reorder_step(
        self, session_id: str, step_id: int, target_step_id: int
    ) -> bool:
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
                ssid = (
                    s.get("step_id") if isinstance(s, dict)
                    else getattr(s, "step_id", 0)
                )
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
            extract_step_delta_code,
            extract_library_block,
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

        # 4. renumber + save — LocalJsonRepository 의 manager 통해서 호출.
        manager = getattr(self._repo, "manager", None)
        if manager is not None and hasattr(manager, "_renumber_steps"):
            manager._renumber_steps(session)
            manager.save_session(session)
        else:
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

    def get_step_delta_code(
        self, step: dict, prev_step: Optional[dict] = None
    ) -> str:
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

        return await engine.execute_session_blocks(
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
        from core.execution_kernel import LIBRARY_BLOCK_STEP_ID, INITIAL_BLOCK_STEP_ID

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
        return kernel.execute_block(
            initial_code, step_id=INITIAL_BLOCK_STEP_ID
        )

    # ── AI ops (AIEngineManager 위임 — None 주입 시 NotImplementedError) ──

    async def generate(
        self, prompt: str, images: Optional[list[str]] = None
    ) -> "AIResponse":
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
        prompt = prompt_builder.build_step_prompt(
            session=session,
            user_request=user_request,
            image_paths=None,
            project_type=getattr(session, "project_type", "desktop"),
            element_context=element_context,
            window_context=window_context,
            is_browser_element=is_browser_element,
        )

        if on_progress:
            on_progress(f"AI 호출 중 (프롬프트 {len(prompt)}자)...")
        response = await self._ai.generate(prompt, None)

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
            extract_imports as _ei,
            extract_code_delta as _ecd,
            extract_import_delta as _eid,
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
        for ls_data in reversed(steps_for_prev):
            ls = ls_data if isinstance(ls_data, dict) else {}
            prev_full = (ls.get("generated_code") or "").strip()
            if prev_full:
                prev_imports = list(ls.get("step_imports", []) or [])
                _, prev_body = _ei(prev_full)
                break
        delta_body = _ecd(separated_body, prev_body) if prev_body else separated_body
        delta_imports = _eid(separated_imports, prev_imports)

        # Step 생성 + 세션 추가 — D6: 첨부 이미지가 있으면 captures 에 보존
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
        )
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
        from pathlib import Path
        from datetime import datetime

        # 프로젝트 루트 = core/app_service.py 의 부모의 부모
        project_root = Path(__file__).resolve().parent.parent
        log_dir = project_root / "tmp" / "conversations"
        log_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        next_step_id = len(session.steps) + 1 if hasattr(session, "steps") else 0
        sid_short = (session.session_id[:8] if hasattr(session, "session_id") else "noid")
        filename = f"{ts}_step{next_step_id}_{sid_short}.md"
        out_path = log_dir / filename

        # 본문 구성 — 백업 포맷 정신 유지 + 메타데이터 헤더 + 단일 파일에 prompt/응답 통합
        sep = "=" * 70
        meta_lines = [
            sep,
            f"# AI 대화 로그",
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
        meta_lines.extend([
            f"- **프롬프트 길이**: {len(prompt)} 자",
            f"- **응답 길이**: {len(response.text or '')} 자",
            f"- **추출된 코드 길이**: {len(response.code or '')} 자",
            f"- **응답 success**: {response.success}",
            f"- **응답 partial**: {getattr(response, 'partial', False)}",
            f"- **소요 시간**: {getattr(response, 'response_time_ms', 0)} ms",
            f"- **토큰 사용량**: {getattr(response, 'tokens_used', 0)}",
        ])
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
