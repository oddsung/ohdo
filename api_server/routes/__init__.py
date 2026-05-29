# SPDX-License-Identifier: AGPL-3.0-or-later
"""api_server 라우터 모듈 (handoff §43 routes 분리).

각 도메인별 ``APIRouter`` 를 ``server.create_app`` 이 ``include_router`` 한다.
상태(AppService/kernel/recording controller)는 ``request.app.state`` 경유 접근.
"""
