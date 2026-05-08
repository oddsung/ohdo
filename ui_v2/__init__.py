# SPDX-License-Identifier: AGPL-3.0-or-later
"""ohdo UI v2 — redesign PoC.

[docs/wireframes_v2.md](../docs/wireframes_v2.md) 의 D1~D26 결정을 반영한 새 UI.

**규칙**:
- ``core.app_service.AppService`` 만 import. ``core.session_manager``,
  ``core.workflow_engine`` 등 직접 import 금지 (ADR 0001).
- 기존 ``ui/`` 는 건드리지 않음. ``main.py`` 에서 ``--ui v2`` 플래그로 분기.
- v1 과 같은 ``data/`` 사용 — 세션 호환.

**현재 PoC 범위**:
- 단일 윈도우 / 단일 세션 (탭 D4 는 후속).
- 라이브러리 / Initial / Step 카드 통합 단일 스크롤 (D1).
- Step 카드에 사용자 요청 + AI 설명 + 코드 + wait 통합 (D3).
- 좌측 사이드바: 세션 목록 (collapsible).
- 하단 채팅 입력 + 캡처/요소 선택 (D6).
- AI 호출은 stub (실 호출은 후속에 연결).
"""

from .main_window_v2 import MainWindowV2  # noqa: F401

__all__ = ["MainWindowV2"]
