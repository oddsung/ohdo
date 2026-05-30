# SPDX-License-Identifier: AGPL-3.0-or-later
"""AI 엔진 퀵스위치 (handoff §47 백로그 #14 — 헤더 엔진 전환 UI 백엔드).

설정 다이얼로그(전체 설정 편집) 없이 헤더에서 AI 엔진을 빠르게 바꾸기 위한 엔드포인트.
core/AppService 의 기존 메서드(list_ai_engines/switch_ai_engine/get_ai_engine_name)만 호출 —
core 0줄. 전환 시 settings.json 의 ``ai.selected`` 도 함께 갱신해 설정 다이얼로그(GET /settings)와
일관 + 재시작 후에도 유지된다 (v2 와 같은 파일 공유).

- GET  /ai/engines  → 사용 가능한 엔진 목록(name/display_name/available/is_current) + current
- POST /ai/engine    → 런타임 전환(switch_ai_engine) + settings.json ai.selected 영속
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from api_server.deps import (
    CONFIG_DIR,
    SwitchEngineRequest,
    get_app_service,
    load_json,
    require_token,
    save_json,
)

router = APIRouter()

_SETTINGS_PATH = CONFIG_DIR / "settings.json"


@router.get("/ai/engines")
def list_engines(request: Request, _: None = Depends(require_token)) -> dict:
    """등록된 AI 엔진 목록 + 현재 엔진 — ``AppService.list_ai_engines`` 위임.

    AI 미구성(ai_manager None) 이면 빈 목록 + current None.
    """
    service = get_app_service(request.app)
    return {
        "engines": service.list_ai_engines(),
        "current": service.get_ai_engine_name(),
    }


@router.post("/ai/engine")
def switch_engine(
    body: SwitchEngineRequest, request: Request, _: None = Depends(require_token)
) -> dict:
    """AI 엔진 전환 (백로그 #14) — 런타임 switch + settings.json ai.selected 영속.

    AI 미구성 시 503, 알 수 없는 엔진 이름이면 400. 성공 시 갱신된 current 반환.
    """
    service = get_app_service(request.app)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="engine name 이 비어 있습니다.")

    try:
        service.switch_ai_engine(name)
    except RuntimeError:  # AIEngineManager 미주입 (AI 미구성)
        raise HTTPException(
            status_code=503,
            detail="AI 엔진이 구성되지 않았습니다 (config/settings.json 의 ai 섹션 확인).",
        )
    except ValueError as exc:  # 알 수 없는 엔진 이름
        raise HTTPException(status_code=400, detail=str(exc))

    # settings.json 의 ai.selected 갱신 — 설정 다이얼로그/재시작과 일관 (best-effort).
    persist_error = None
    try:
        current = load_json(_SETTINGS_PATH)
        ai_section = dict(current.get("ai") or {})
        ai_section["selected"] = name
        current["ai"] = ai_section
        save_json(_SETTINGS_PATH, current)
    except Exception as exc:  # noqa: BLE001 — 런타임 전환은 됐으니 경고만
        persist_error = str(exc)

    result = {"success": True, "current": service.get_ai_engine_name()}
    if persist_error:
        result["persist_error"] = persist_error
    return result
