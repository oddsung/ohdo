# SPDX-License-Identifier: AGPL-3.0-or-later
"""저장소 추상화 레이어 (ROADMAP §3 Phase 1 (1)).

ohdo SaaS 확장을 위해 세션 저장소를 인터페이스 뒤로 숨긴다. 기존
``SessionManager`` 는 그대로 두고, ``LocalJsonRepository`` 가 그것을
감싸 ``SessionRepository`` 인터페이스로 노출한다.

구현체:

- ``LocalJsonRepository`` — 기존 ``SessionManager`` 위에 구현 (데스크톱 기본값)
- ``InMemoryRepository`` — 테스트 가속용 (file IO 없음)
- ``LocalCaptureStore`` — capture 이미지 전용 (``CaptureStore`` 구현체)

자세한 배경: docs/saas/decisions/0002-appservice-facade-approach.md
"""

from .base import CaptureStore, SessionRepository
from .in_memory import InMemoryRepository
from .local_capture import LocalCaptureStore
from .local_json import LocalJsonRepository

__all__ = [
    "SessionRepository",
    "CaptureStore",
    "LocalJsonRepository",
    "InMemoryRepository",
    "LocalCaptureStore",
]
