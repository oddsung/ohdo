# SPDX-License-Identifier: AGPL-3.0-or-later
"""설정 read/write (handoff §47 백로그 #20 — v3 설정 화면 백엔드).

config/settings.json 을 읽고/쓰는 엔드포인트. PySide6 v2 와 동일한 파일을 공유하므로
v3 설정 화면에서 바꾼 AI 엔진/모델/타임아웃 등이 v2 에도 그대로 반영된다.

- GET /settings  → 현재 설정 (default_settings.json 위에 settings.json 병합) + defaults
- PUT /settings  → settings.json 저장 + AI 매니저 재초기화 (재시작 불필요)

주의: api_key 가 응답에 포함된다 — 브리지는 127.0.0.1 + 토큰 인증 전용(단일 사용자
로컬)이므로 허용. 외부 노출 금지 (server.py CORS 도 localhost 바인딩 전제).
core/ 무수정 — 순수 파일 I/O + 기존 ``AppService.reload_ai`` 위임.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from api_server.deps import (
    CONFIG_DIR,
    SaveSettingsRequest,
    get_app_service,
    load_json,
    require_token,
    save_json,
    settings_path,
)

router = APIRouter()

# defaults 는 개발자 유지 콘텐츠 — 항상 번들(CONFIG_DIR)에서 읽는다 (handoff §81).
# settings.json 은 --config-dir 지정 시 사용자 디렉터리 → settings_path(app) 경유.
_DEFAULTS_PATH = CONFIG_DIR / "default_settings.json"


def _deep_merge(base: dict, override: dict) -> dict:
    """override 를 base 위에 재귀 병합(새 dict 반환). dict 끼리만 깊게, 그 외는 override 우선."""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@router.get("/settings")
def get_settings(request: Request, _: None = Depends(require_token)) -> dict:
    """현재 설정 + 기본값 반환 (handoff §47).

    effective = default_settings.json 위에 settings.json 을 병합한 값.
    UI 는 effective 를 편집하고 PUT 으로 전체를 되돌려 저장한다.
    """
    defaults = load_json(_DEFAULTS_PATH)
    current = load_json(settings_path(request.app))
    effective = _deep_merge(defaults, current)
    return {"settings": effective, "defaults": defaults}


@router.put("/settings")
def save_settings(
    body: SaveSettingsRequest, request: Request, _: None = Depends(require_token)
) -> dict:
    """설정 저장 (handoff §47) — settings.json 기록 후 AI 매니저 재초기화.

    ai 섹션이 있으면 ``AppService.reload_ai`` 로 즉시 반영(앱 재시작 불필요).
    """
    settings = body.settings
    if not isinstance(settings, dict):
        raise HTTPException(status_code=400, detail="settings 는 객체여야 합니다.")

    save_json(settings_path(request.app), settings)

    # AI 재초기화 — 캐시된 AppService 의 ai_manager 를 새 설정으로 교체.
    if settings.get("ai"):
        try:
            get_app_service(request.app).reload_ai(settings)
        except Exception as exc:  # noqa: BLE001 — 저장은 됐으니 경고만 전달
            return {"success": True, "settings": settings, "ai_reload_error": str(exc)}

    return {"success": True, "settings": settings}
