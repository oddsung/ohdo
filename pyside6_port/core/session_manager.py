"""
세션 매니저

세션 JSON 파일의 생성, 읽기, 수정, 삭제, 목록 조회를 담당합니다.
각 세션은 data/sessions/{session_id}/ 폴더에 저장됩니다.
"""

import json
import uuid
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 데이터 모델
# ──────────────────────────────────────────────

@dataclass
class CaptureInfo:
    """캡처 이미지 정보"""
    type: str = "screen"                      # "screen" | "object"
    path: str = ""                            # 상대 경로
    timestamp: str = ""
    resolution: str = ""
    selector_info: Optional[dict] = None      # 객체 선택 정보


@dataclass
class PromptLog:
    """AI 프롬프트/응답 로그"""
    system_prompt: str = ""
    full_prompt: str = ""
    raw_response: str = ""
    tokens_used: int = 0
    response_time_ms: int = 0


@dataclass
class ExecutionResult:
    """코드 실행 결과"""
    success: bool = False
    output: str = ""
    error: Optional[str] = None
    duration_ms: int = 0
    error_screenshot: Optional[str] = None


@dataclass
class ConversationMessage:
    """대화 메시지"""
    role: str = ""       # "user" | "assistant" | "system"
    content: str = ""
    timestamp: str = ""


@dataclass
class Step:
    """워크플로우의 하나의 스텝"""
    step_id: int = 0
    status: str = "pending"                    # "pending" | "completed" | "failed"
    created_at: str = ""
    conversation: list = field(default_factory=list)
    generated_code: str = ""
    required_packages: list = field(default_factory=list)
    captures: list = field(default_factory=list)
    prompt_log: Optional[dict] = None
    execution_result: Optional[dict] = None
    # import 분리 필드 (Phase 1)
    step_code: str = ""                        # 이 스텝만의 로직 (import 제외)
    step_imports: list = field(default_factory=list)  # 이 스텝이 추가한 import 문
    # Step 후 대기시간 (ms). None 이면 settings.execution.step_delay_ms 사용 (default).
    # 양수면 이 step 만 override.
    wait_after_ms: Optional[int] = None


@dataclass
class Session:
    """하나의 RPA 세션 (워크플로우)"""
    session_id: str = ""
    version: str = "2.0"
    created_at: str = ""
    updated_at: str = ""
    title: str = ""
    description: str = ""
    project_type: str = "desktop"              # "desktop" | "web"

    settings: dict = field(default_factory=lambda: {
        "ai_engine": "gemini_cli",
        "image_quality": 60,
        # step_delay_ms: None = 글로벌 settings.execution.step_delay_ms 사용 (default)
        # int = 이 세션만의 default (개별 step 의 wait_after_ms 보다 낮은 우선순위)
        "step_delay_ms": None,
    })

    steps: list = field(default_factory=list)

    workflow_metadata: dict = field(default_factory=lambda: {
        "total_steps": 0,
        "completed_steps": 0,
        "total_execution_time_ms": 0,
        "ai_total_tokens": 0,
        "run_count": 0
    })


@dataclass
class SessionSummary:
    """세션 목록 표시용 요약 정보"""
    session_id: str
    title: str
    description: str
    project_type: str
    created_at: str
    updated_at: str
    total_steps: int
    completed_steps: int


# ──────────────────────────────────────────────
# 세션 매니저
# ──────────────────────────────────────────────

class SessionManager:
    """
    세션 JSON 파일 CRUD 관리자.

    세션은 다음 경로에 저장됩니다:
        data/sessions/{session_id}/
            ├── session.json
            ├── captures/
            └── scripts/
    """

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Args:
            data_dir: data 디렉터리 경로. None이면 프로젝트 기본 경로 사용
        """
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data"
        self.sessions_dir = data_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def create_session(
        self,
        title: str,
        project_type: str = "desktop",
        description: str = ""
    ) -> Session:
        """
        새로운 세션을 생성합니다.

        Args:
            title: 세션 제목
            project_type: "desktop" 또는 "web"
            description: 세션 설명
        """
        now = datetime.now().isoformat()
        session = Session(
            session_id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            title=title,
            description=description,
            project_type=project_type
        )

        # 세션 폴더 구조 생성
        session_dir = self.sessions_dir / session.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "captures").mkdir(exist_ok=True)
        (session_dir / "scripts").mkdir(exist_ok=True)

        # 즉시 저장
        self.save_session(session)
        logger.info(f"새 세션 생성: {title} ({session.session_id})")

        return session

    def save_session(self, session: Session):
        """세션을 JSON 파일로 저장합니다."""
        session.updated_at = datetime.now().isoformat()

        session_dir = self.sessions_dir / session.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        session_file = session_dir / "session.json"
        data = asdict(session)

        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.debug(f"세션 저장: {session.session_id}")

    def load_session(self, session_id: str) -> Session:
        """세션 JSON 파일을 읽어 Session 객체로 반환합니다."""
        session_file = self.sessions_dir / session_id / "session.json"

        if not session_file.exists():
            raise FileNotFoundError(f"세션을 찾을 수 없습니다: {session_id}")

        with open(session_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        session = Session(**{
            k: v for k, v in data.items()
            if k in Session.__dataclass_fields__
        })

        logger.info(f"세션 로드: {session.title} ({session_id})")
        return session

    def list_sessions(self) -> list[SessionSummary]:
        """저장된 모든 세션의 요약 목록을 반환합니다."""
        summaries = []

        for session_dir in self.sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue
            session_file = session_dir / "session.json"
            if not session_file.exists():
                continue

            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                metadata = data.get("workflow_metadata", {})
                summaries.append(SessionSummary(
                    session_id=data.get("session_id", session_dir.name),
                    title=data.get("title", "제목 없음"),
                    description=data.get("description", ""),
                    project_type=data.get("project_type", "desktop"),
                    created_at=data.get("created_at", ""),
                    updated_at=data.get("updated_at", ""),
                    total_steps=metadata.get("total_steps", len(data.get("steps", []))),
                    completed_steps=metadata.get("completed_steps", 0)
                ))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"세션 파일 읽기 실패: {session_file} - {e}")

        # 최신순 정렬
        summaries.sort(key=lambda s: s.updated_at, reverse=True)
        return summaries

    def delete_session(self, session_id: str):
        """세션 폴더 전체를 삭제합니다."""
        import gc
        import time

        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            logger.warning(f"삭제할 세션을 찾을 수 없습니다: {session_id}")
            return

        # subprocess가 CWD로 scripts/ 폴더를 잡고 있을 수 있으므로 GC 후 재시도
        gc.collect()

        last_error = None
        for attempt in range(3):
            try:
                shutil.rmtree(session_dir)
                logger.info(f"세션 삭제: {session_id}")
                return
            except PermissionError as e:
                last_error = e
                logger.warning(f"세션 삭제 재시도 {attempt + 1}/3 (파일 사용 중): {e}")
                gc.collect()
                time.sleep(0.5)

        # 최종 실패: 삭제 가능한 파일만이라도 정리
        logger.error(f"세션 폴더 삭제 실패 (일부 파일 사용 중): {last_error}")
        try:
            shutil.rmtree(session_dir, ignore_errors=True)
        except Exception:
            pass

    def add_step(self, session: Session, step: Step):
        """세션에 새로운 스텝을 추가하고 저장합니다."""
        step.step_id = len(session.steps) + 1
        if not step.created_at:
            step.created_at = datetime.now().isoformat()

        session.steps.append(asdict(step))
        session.workflow_metadata["total_steps"] = len(session.steps)

        # 완료 스텝 수 업데이트
        completed = sum(
            1 for s in session.steps
            if (s.get("status") if isinstance(s, dict) else s.status) == "completed"
        )
        session.workflow_metadata["completed_steps"] = completed

        self.save_session(session)
        logger.info(f"스텝 추가: #{step.step_id} ({session.session_id})")

    def update_step(self, session: Session, step_id: int, updates: dict):
        """특정 스텝의 정보를 업데이트합니다."""
        for i, step in enumerate(session.steps):
            if isinstance(step, dict):
                if step.get("step_id") == step_id:
                    step.update(updates)
                    break
            else:
                # dataclass → dict으로 교체하여 업데이트 내용 반영
                step_dict = asdict(step)
                if step_dict.get("step_id") == step_id:
                    step_dict.update(updates)
                    session.steps[i] = step_dict
                    break

        self.save_session(session)

    def delete_step(self, session: Session, step_id: int) -> bool:
        """
        특정 스텝을 삭제하고 step_id를 재정렬합니다.

        Returns:
            삭제 성공 여부
        """
        original_len = len(session.steps)

        session.steps = [
            s for s in session.steps
            if (s.get("step_id") if isinstance(s, dict) else s.step_id) != step_id
        ]

        if len(session.steps) == original_len:
            logger.warning(f"삭제할 스텝을 찾을 수 없습니다: #{step_id}")
            return False

        # step_id 재정렬 (1부터 시작)
        self._renumber_steps(session)
        self._update_step_metadata(session)
        self.save_session(session)

        logger.info(f"스텝 삭제: #{step_id} ({session.session_id})")
        return True

    def insert_step(self, session: Session, after_step_id: int,
                   code: str = "", description: str = "삽입된 스텝") -> int:
        """
        특정 스텝 뒤에 새 스텝을 삽입합니다.

        Args:
            session: 대상 세션
            after_step_id: 이 스텝 다음에 삽입
            code: 삽입할 코드 (빈 문자열이면 빈 스텝)
            description: 스텝 설명

        Returns:
            삽입된 스텝의 새 step_id
        """
        # 삽입 위치 찾기
        insert_idx = 0
        for i, s in enumerate(session.steps):
            sid = s.get("step_id") if isinstance(s, dict) else s.step_id
            if sid == after_step_id:
                insert_idx = i + 1
                break

        new_step = asdict(Step(
            step_id=0,  # 재정렬에서 설정됨
            status="pending",
            created_at=datetime.now().isoformat(),
            generated_code=code,
            conversation=[{
                "role": "system",
                "content": description,
                "timestamp": datetime.now().isoformat()
            }]
        ))

        session.steps.insert(insert_idx, new_step)

        # step_id 재정렬
        self._renumber_steps(session)
        self._update_step_metadata(session)
        self.save_session(session)

        new_id = insert_idx + 1
        logger.info(f"스텝 삽입: after #{after_step_id} → new #{new_id} ({session.session_id})")
        return new_id

    def move_step(self, session: Session, step_id: int, direction: str) -> bool:
        """
        스텝을 위/아래로 이동합니다.

        Args:
            session: 대상 세션
            step_id: 이동할 스텝 ID
            direction: "up" 또는 "down"

        Returns:
            이동 성공 여부
        """
        # 스텝 인덱스 찾기
        target_idx = None
        for i, s in enumerate(session.steps):
            sid = s.get("step_id") if isinstance(s, dict) else s.step_id
            if sid == step_id:
                target_idx = i
                break

        if target_idx is None:
            logger.warning(f"이동할 스텝을 찾을 수 없습니다: #{step_id}")
            return False

        if direction == "up" and target_idx > 0:
            swap_idx = target_idx - 1
        elif direction == "down" and target_idx < len(session.steps) - 1:
            swap_idx = target_idx + 1
        else:
            logger.warning(f"스텝을 더 이상 이동할 수 없습니다: #{step_id} {direction}")
            return False

        # 위치 교환
        session.steps[target_idx], session.steps[swap_idx] = \
            session.steps[swap_idx], session.steps[target_idx]

        # step_id 재정렬
        self._renumber_steps(session)
        self.save_session(session)

        logger.info(f"스텝 이동: #{step_id} {direction} ({session.session_id})")
        return True

    def _renumber_steps(self, session: Session):
        """스텝 ID를 1부터 순차적으로 재정렬합니다."""
        for i, step in enumerate(session.steps):
            if isinstance(step, dict):
                step["step_id"] = i + 1
            else:
                step.step_id = i + 1

    def _update_step_metadata(self, session: Session):
        """스텝 메타데이터를 업데이트합니다."""
        session.workflow_metadata["total_steps"] = len(session.steps)
        completed = sum(
            1 for s in session.steps
            if (s.get("status") if isinstance(s, dict) else s.status) == "completed"
        )
        session.workflow_metadata["completed_steps"] = completed

    def get_session_dir(self, session_id: str) -> Path:
        """세션 디렉터리 경로를 반환합니다."""
        return self.sessions_dir / session_id

    def get_captures_dir(self, session_id: str) -> Path:
        """세션의 캡처 이미지 디렉터리 경로를 반환합니다."""
        captures_dir = self.sessions_dir / session_id / "captures"
        captures_dir.mkdir(parents=True, exist_ok=True)
        return captures_dir

    def get_scripts_dir(self, session_id: str) -> Path:
        """세션의 스크립트 디렉터리 경로를 반환합니다."""
        scripts_dir = self.sessions_dir / session_id / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        return scripts_dir

    def export_workflow(self, session: Session) -> str:
        """
        세션의 모든 스텝 코드를 하나의 독립 실행 가능한 Python 파일로 결합합니다.

        Returns:
            결합된 Python 코드 문자열
        """
        from core.import_manager import extract_imports, merge_imports, assemble_script

        header = (
            "#!/usr/bin/env python3\n"
            f'"""\n'
            f'AI RPA 워크플로우: {session.title}\n'
            f'생성일: {session.created_at}\n'
            f'스텝 수: {len(session.steps)}\n'
            f'"""\n'
        )

        all_imports = []
        step_entries = []  # (step_id, task_name, code) 튜플 리스트

        for step_data in session.steps:
            step = step_data if isinstance(step_data, dict) else asdict(step_data)

            # step_code/step_imports가 있으면 사용, 없으면 generated_code에서 추출
            step_imports = step.get("step_imports", [])
            step_code = step.get("step_code", "")

            if step_code:
                all_imports.append(step_imports)
                body = step_code
            else:
                code = step.get("generated_code", "")
                if code:
                    imports, body = extract_imports(code)
                    all_imports.append(imports)
                else:
                    continue

            # conversation에서 사용자 요청(task_name) 추출
            task_name = ""
            for msg in step.get("conversation", []):
                if isinstance(msg, dict) and msg.get("role") == "user":
                    task_name = msg.get("content", "")
                    break
            if not task_name:
                task_name = f"작업 {step.get('step_id', '?')}"

            step_entries.append((step.get("step_id", 0), task_name, body))

        merged_imports = merge_imports(all_imports)
        script_body = assemble_script(merged_imports, step_entries)

        return header + "\n" + script_body

    def export_as_project(
        self,
        session: Session,
        output_dir: Path,
        settings: dict = None,
        ai_generated_readme: str = None
    ) -> Path:
        """
        세션 워크플로우를 독립 실행 가능한 프로젝트 폴더로 내보냅니다.

        생성 구조:
            {output_dir}/
            ├── main.py              # 실행 가능한 메인 코드
            ├── requirements.txt     # 필요 패키지 목록
            ├── README.md            # 프로젝트 설명 및 실행 가이드
            └── run.bat              # 윈도우 실행 스크립트

        Args:
            session: 내보낼 세션
            output_dir: 출력 프로젝트 폴더 경로
            settings: output_project 설정 (settings.json)
            ai_generated_readme: AI가 생성한 README 내용 (선택)

        Returns:
            생성된 프로젝트 폴더 경로
        """
        if settings is None:
            settings = {}

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # ── 1. main.py 생성 ──
        main_code = self.export_workflow(session)
        (output_dir / "main.py").write_text(main_code, encoding="utf-8")
        logger.info(f"main.py 생성 완료: {output_dir / 'main.py'}")

        # ── 2. requirements.txt 생성 ──
        if settings.get("auto_requirements", True):
            packages = self._collect_all_packages(session)
            req_content = self._generate_requirements(packages)
            (output_dir / "requirements.txt").write_text(req_content, encoding="utf-8")
            logger.info(f"requirements.txt 생성 완료 ({len(packages)}개 패키지)")

        # ── 3. README.md 생성 ──
        if settings.get("auto_readme", True):
            if ai_generated_readme:
                readme_content = ai_generated_readme
            else:
                readme_content = self._generate_default_readme(
                    session, packages if settings.get("auto_requirements", True) else []
                )
            (output_dir / "README.md").write_text(readme_content, encoding="utf-8")
            logger.info("README.md 생성 완료")

        # ── 4. run.bat 실행 스크립트 생성 ──
        if settings.get("include_run_script", True):
            bat_content = self._generate_run_script(session.title)
            (output_dir / "run.bat").write_text(bat_content, encoding="cp949")
            logger.info("run.bat 생성 완료")

        logger.info(f"프로젝트 내보내기 완료: {output_dir}")
        return output_dir

    def _collect_all_packages(self, session: Session) -> list[str]:
        """세션의 모든 스텝에서 사용된 외부 패키지를 수집합니다."""
        from core.import_manager import extract_imports, extract_package_names

        all_imports = []

        for step_data in session.steps:
            step = step_data if isinstance(step_data, dict) else asdict(step_data)

            # step_imports가 있으면 사용
            step_imports = step.get("step_imports", [])
            if step_imports:
                all_imports.extend(step_imports)
            else:
                # generated_code에서 추출
                code = step.get("generated_code", "")
                if code:
                    imports, _ = extract_imports(code)
                    all_imports.extend(imports)

            # required_packages 필드도 수집
            for pkg in step.get("required_packages", []):
                if pkg:
                    all_imports.append(f"import {pkg}")

        return extract_package_names(all_imports)

    def _generate_requirements(self, packages: list[str]) -> str:
        """requirements.txt 내용을 생성합니다."""
        # 패키지 이름 → pip 설치 이름 매핑
        pip_name_map = {
            'cv2': 'opencv-python',
            'PIL': 'Pillow',
            'pil': 'Pillow',
            'bs4': 'beautifulsoup4',
            'yaml': 'PyYAML',
            'sklearn': 'scikit-learn',
            'dotenv': 'python-dotenv',
            'win32com': 'pywin32',
            'win32api': 'pywin32',
            'win32gui': 'pywin32',
            'pythoncom': 'pywin32',
            'uiautomation': 'uiautomation',
        }

        lines = [
            "# ===========================================",
            "# Auto-generated by AI RPA Solution",
            f"# 생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "# ===========================================",
            "",
        ]

        seen = set()
        for pkg in packages:
            pip_name = pip_name_map.get(pkg, pkg)
            if pip_name not in seen:
                lines.append(pip_name)
                seen.add(pip_name)

        return "\n".join(lines) + "\n"

    def _generate_default_readme(self, session: Session, packages: list[str]) -> str:
        """기본 README.md를 생성합니다."""
        title = session.title or "RPA 워크플로우"
        desc = session.description or "AI RPA Solution으로 생성된 자동화 프로젝트"
        ptype = "데스크톱" if session.project_type == "desktop" else "웹 브라우저"
        step_count = len(session.steps)
        created = session.created_at[:10] if session.created_at else ""

        # 스텝 요약
        steps_summary = ""
        for step_data in session.steps:
            step = step_data if isinstance(step_data, dict) else {}
            sid = step.get("step_id", "?")
            conv = step.get("conversation", [])
            user_msg = ""
            for msg in conv:
                m = msg if isinstance(msg, dict) else {}
                if m.get("role") == "user":
                    user_msg = m.get("content", "")[:80]
                    break
            if user_msg:
                steps_summary += f"  {sid}. {user_msg}\n"

        readme = f"""# {title}

> {desc}

## 📋 개요

| 항목 | 내용 |
|------|------|
| **유형** | {ptype} 자동화 |
| **스텝 수** | {step_count} |
| **생성일** | {created} |
| **생성 도구** | AI RPA Solution v2.0 |

## 🔧 설치 방법

### 1. Python 설치
- [Python 공식 사이트](https://www.python.org/downloads/)에서 Python 3.10 이상을 설치하세요.
- 설치 시 **"Add Python to PATH"** 체크를 반드시 해주세요.

### 2. 가상환경 생성 (권장)
```bash
# 프로젝트 폴더로 이동
cd {title}

# 가상환경 생성
python -m venv venv

# 가상환경 활성화 (Windows)
.\\venv\\Scripts\\activate

# 가상환경 활성화 (macOS/Linux)
source venv/bin/activate
```

### 3. 패키지 설치
```bash
pip install -r requirements.txt
```

## ▶️ 실행 방법

### 방법 1: 직접 실행
```bash
python main.py
```

### 방법 2: run.bat 사용 (Windows)
`run.bat` 파일을 더블클릭하면 자동으로 가상환경 활성화 + 실행됩니다.

## 📝 워크플로우 스텝
{steps_summary}
## ⚠️ 주의사항

- 실행 전 대상 프로그램이 열려있는지 확인하세요.
- 자동화 실행 중에는 마우스/키보드를 사용하지 마세요.
- 화면 해상도가 코드 생성 시와 동일해야 정상 동작합니다.

---

*이 프로젝트는 [AI RPA Solution](https://github.com/ai-rpa-solution)으로 자동 생성되었습니다.*
"""
        return readme

    def _generate_run_script(self, title: str) -> str:
        """Windows용 run.bat 실행 스크립트를 생성합니다."""
        return f"""@echo off
chcp 65001 >nul
title {title}

echo ============================================
echo   {title}
echo   AI RPA Solution으로 생성된 자동화 프로그램
echo ============================================
echo.

REM 가상환경 확인
if exist "venv\\Scripts\\activate.bat" (
    echo [INFO] 가상환경을 활성화합니다...
    call venv\\Scripts\\activate.bat
) else (
    echo [INFO] 가상환경이 없습니다. 생성합니다...
    python -m venv venv
    call venv\\Scripts\\activate.bat
    echo [INFO] 패키지를 설치합니다...
    pip install -r requirements.txt
)

echo.
echo [INFO] 프로그램을 실행합니다...
echo.
python main.py

echo.
echo [완료] 프로그램이 종료되었습니다.
pause
"""
