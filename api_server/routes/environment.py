# SPDX-License-Identifier: AGPL-3.0-or-later
"""환경 점검 (handoff §47 백로그 #18 — v3 env scanner).

Python/필수·선택 패키지/CLI AI 설치 상태를 스캔해 반환. core 의 공개 ``EnvironmentScanner``
(get_scanner 싱글톤) 를 그대로 호출 — core 0줄 (AppService 에는 노출돼있지 않아 직접 사용).

주의: full_scan 은 다수의 subprocess(패키지 import 확인 + CLI ``--version`` timeout) 를 돌려
응답이 수초 걸릴 수 있다. FastAPI sync 엔드포인트라 threadpool 에서 실행돼 이벤트 루프는 막지
않는다. 프런트는 로딩 표시 + on-demand 호출.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api_server.deps import CONFIG_DIR, require_token

router = APIRouter()


@router.get("/environment")
def scan_environment(request: Request, _: None = Depends(require_token)) -> dict:
    """전체 환경 스캔 — ``EnvironmentScanner.full_scan`` 결과를 그대로 반환.

    반환: success / system_info / python_path / python_version / available_pythons /
    packages(required·optional·all_required_installed) / cli_ai / scan_time.

    --config-dir 지정 시(packaged, handoff §81) 스캔 캐시(environment.json)도 그쪽에
    쓴다 — frozen 번들 내부(_internal/config)는 쓰기 금지 취급(perMachine 설치 대비).
    """
    from pathlib import Path

    from core.environment_scanner import EnvironmentScanner, get_scanner

    config_dir = getattr(request.app.state, "config_dir", None)
    if config_dir is not None and Path(config_dir) != CONFIG_DIR:
        return EnvironmentScanner(config_dir=Path(config_dir)).full_scan()
    return get_scanner().full_scan()
