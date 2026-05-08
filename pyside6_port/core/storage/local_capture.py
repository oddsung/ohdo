# SPDX-License-Identifier: AGPL-3.0-or-later
"""로컬 파일시스템 기반 capture 이미지 저장소 (CaptureStore 구현).

ROADMAP §3 Phase 1 (1) 의 ``CaptureStore(ABC)`` interface 구현. 현재 capture
이미지는 ``data/sessions/<session_id>/captures/<filename>.png`` 으로 저장된다.

**현 단계의 한계** (의도적):

- 실제 capture 쓰기 경로 (``ui/screen_capture.py``, ``core/win_inspector.py``)
  는 여전히 filesystem 직접 접근. 이 파일은 contract 정의에 그치며, capture 쓰기
  마이그레이션은 Phase 2 의 S3CaptureStore 도입 시점에 일괄 처리.
- 따라서 현재는 단순 path resolution + listing + delete 만 지원.
"""

from __future__ import annotations

from pathlib import Path

from .base import CaptureStore


class LocalCaptureStore(CaptureStore):
    """``data/sessions/<id>/captures/`` 위에 동작하는 capture 저장소."""

    def __init__(self, sessions_dir: Path) -> None:
        """
        Args:
            sessions_dir: ``data/sessions/`` 의 절대 경로 (``SessionManager.sessions_dir``).
        """
        self._sessions_dir = Path(sessions_dir)

    def resolve_capture_path(self, session_id: str, filename: str) -> Path:
        """``<sessions_dir>/<session_id>/captures/<filename>``."""
        return self._sessions_dir / session_id / "captures" / filename

    def list_captures_for_session(self, session_id: str) -> list[str]:
        captures_dir = self._sessions_dir / session_id / "captures"
        if not captures_dir.exists() or not captures_dir.is_dir():
            return []
        return sorted(p.name for p in captures_dir.iterdir() if p.is_file())

    def delete_capture(self, session_id: str, filename: str) -> bool:
        path = self.resolve_capture_path(session_id, filename)
        if not path.exists():
            return False
        try:
            path.unlink()
            return True
        except OSError:
            return False
