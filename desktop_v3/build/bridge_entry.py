# SPDX-License-Identifier: AGPL-3.0-or-later
"""PyInstaller freeze 진입점 (handoff §46) — frozen 브리지 exe 의 메인.

``python -m api_server`` 와 동일하게 ``api_server.__main__.main()`` 을 호출한다.
PyInstaller 는 모듈(``-m``)이 아니라 스크립트를 entry 로 받으므로 이 얇은 래퍼가 필요하다.

freeze (사용자가 프로젝트 루트에서 실행):
    pyinstaller desktop_v3/build/ohdo-bridge.spec --noconfirm
    → dist/ohdo-bridge/ohdo-bridge.exe  (onedir)
    이 폴더를 desktop_v3/build/pybridge/ 로 복사하면 electron-builder 가 동봉한다.
"""

from api_server.__main__ import main

if __name__ == "__main__":
    main()
