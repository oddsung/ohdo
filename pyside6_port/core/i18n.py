# SPDX-License-Identifier: AGPL-3.0-or-later
"""ohdo i18n module (Phase 1.9 C-1).

dict 기반 단순 translation dispatcher.

- catalogue: ``core/locale/{locale}.json`` (UTF-8)
- fallback locale: ``en`` (5/9 글로벌 우선 결정)
- missing key: 키 자체 반환 (placeholder 안 깨짐)

UI/core 의 사용자 노출 문자열은 ``tr("ns.key")`` 로 감싸고 catalogue 에서 분기.
catalogue 파일이 비어있어도 import + tr() 호출은 정상 동작 (fallback chain).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_LOCALE_DIR = Path(__file__).parent / "locale"
_FALLBACK_LOCALE = "en"

_current_locale: str = _FALLBACK_LOCALE
_catalogue_cache: dict[str, dict[str, str]] = {}


def set_locale(locale: str) -> None:
    """활성 locale 변경. catalogue 는 첫 ``tr`` 호출 시 lazy 로드."""
    global _current_locale
    _current_locale = locale


def get_locale() -> str:
    return _current_locale


def _load_catalogue(locale: str) -> dict[str, str]:
    if locale in _catalogue_cache:
        return _catalogue_cache[locale]
    path = _LOCALE_DIR / f"{locale}.json"
    data: dict[str, str] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = {str(k): str(v) for k, v in loaded.items()}
        except (json.JSONDecodeError, OSError):
            data = {}
    _catalogue_cache[locale] = data
    return data


def tr(key: str, **kwargs: Any) -> str:
    """``key`` 를 활성 locale 로 번역. lookup 순서: current -> fallback -> key.

    ``kwargs`` 는 ``str.format`` 치환에 사용. 치환 실패 시 원문 그대로 반환.
    """
    cat = _load_catalogue(_current_locale)
    text = cat.get(key)
    if text is None and _current_locale != _FALLBACK_LOCALE:
        text = _load_catalogue(_FALLBACK_LOCALE).get(key)
    if text is None:
        # missing key: 키 자체 반환 (format 스킵 — debug 시 placeholder 그대로 보임)
        return key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass
    return text


def reset_cache() -> None:
    """catalogue 캐시 비움. 테스트에서 catalogue 파일 변경 후 재로드용."""
    _catalogue_cache.clear()
