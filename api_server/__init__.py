# SPDX-License-Identifier: AGPL-3.0-or-later
"""ohdo desktop_v3 용 FastAPI bridge.

handoff §37 (TS UI v3 트랙) Phase A 신규. Electron + React 데스크톱 셸이
``core/`` 의 도메인 로직을 직접 import 할 수 없으므로 (Node ↔ Python 분리),
localhost HTTP/WS 로 접근하는 얇은 브리지 레이어를 둔다.

핵심 원칙 (handoff §37 "핵심 원칙"):
- ``core/`` 는 절대 수정하지 않는다. 여기서는 ``AppService`` 를 통해 **호출만** 한다.
- PySide6 v1/v2 (``ui/``, ``ui_v2/``) 도 건드리지 않는다.
- 같은 ``data/`` 디렉터리를 공유한다 (세션 저장소 재사용).

진입점은 ``python -m api_server`` ([api_server/__main__.py](__main__.py)).
"""

from .server import create_app

__all__ = ["create_app"]
