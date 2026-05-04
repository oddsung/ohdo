"""저장소 추상화 레이어.

ohdo SaaS 확장을 위해 세션 저장소를 인터페이스 뒤로 숨긴다. 기존
``SessionManager`` 는 그대로 두고, ``LocalJsonRepository`` 가 그것을
감싸 ``SessionRepository`` 인터페이스로 노출한다.

자세한 배경: docs/saas/decisions/0002-appservice-facade-approach.md
"""

from .base import SessionRepository
from .local_json import LocalJsonRepository

__all__ = ["SessionRepository", "LocalJsonRepository"]
