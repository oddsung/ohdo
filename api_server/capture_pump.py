# SPDX-License-Identifier: AGPL-3.0-or-later
"""스크린 영역 캡처 — 드래그한 사각형을 mss 로 grab 해 PNG 저장 (handoff §60, 백로그 #13).

v2 의 ``ui/screen_capture.py`` (전체화면 오버레이 + mss grab + PIL 저장) 흐름을 브리지로
이식한다. v3 는 Electron 오버레이(``capture_overlay.html``)가 드래그로 영역을 받고, 그
**물리 픽셀 사각형**을 ``POST /capture/region`` 으로 보내면 이 모듈이 mss 로 grab → 세션
captures 폴더에 저장 → 경로를 돌려준다. 저장된 경로는 generate 시 ``images`` 로 전달되어
core ``generate_step(images=[...])`` 이 step.captures + AI 프롬프트에 첨부한다 (core 0줄).

element picker(``pick_pump``)와 달리 전역 후크/메시지 펌프가 필요 없다 — 좌표는 이미
프런트가 확정해 보내므로 단순 grab 만 한다. mss/PIL import 는 함수 내부에 둬 비-Windows
(예: CI ubuntu)에서도 모듈 import 자체는 안전.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def capture_region(
    captures_dir: Path,
    left: int,
    top: int,
    width: int,
    height: int,
) -> dict:
    """물리 픽셀 사각형을 grab → ``captures_dir`` 에 PNG 저장.

    Args:
        captures_dir: 저장 폴더(세션 captures). 호출자가 미리 만든다.
        left/top/width/height: 캡처할 영역(물리 픽셀, 가상 데스크톱 좌표).

    Returns:
        ``{"success": True, "path": str, "width": int, "height": int}`` 또는
        ``{"success": False, "error": str}``.
    """
    if width <= 0 or height <= 0:
        return {"success": False, "error": "캡처 영역이 비어 있습니다."}

    try:
        import mss
        from PIL import Image as PilImage
    except Exception as exc:  # noqa: BLE001 — 의존성 미설치(비-Windows 등)
        return {"success": False, "error": f"캡처 의존성 로드 실패: {exc}"}

    try:
        with mss.mss() as sct:
            sct_img = sct.grab(
                {"left": int(left), "top": int(top), "width": int(width), "height": int(height)}
            )
            img = PilImage.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        captures_dir.mkdir(parents=True, exist_ok=True)
        filename = f"region_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        path = captures_dir / filename
        img.save(str(path))
        return {
            "success": True,
            "path": str(path),
            "width": img.size[0],
            "height": img.size[1],
        }
    except Exception as exc:  # noqa: BLE001 — grab/save 실패는 사용자에게 전달
        return {"success": False, "error": f"영역 캡처 실패: {exc}"}
