# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# PyInstaller spec — ohdo Python 브리지(api_server + core) freeze (handoff §46).
#
# 실행 (프로젝트 루트에서):
#     pyinstaller desktop_v3/build/ohdo-bridge.spec --noconfirm
# 결과:
#     dist/ohdo-bridge/ohdo-bridge.exe  (onedir)
#     → desktop_v3/build/pybridge/ 로 복사 후 `npm run dist` (electron-builder 가 동봉)
#
# 주의: 이 spec 은 프로젝트 루트를 CWD 로 가정한다 (api_server/, core/ 가 보이도록).
# 동봉 검증은 사용자 Windows 머신에서 (이 개발 환경에선 GUI/설치 테스트 불가).

import os

PROJECT_ROOT = os.path.abspath(os.getcwd())  # pyinstaller 실행 CWD = 프로젝트 루트
ENTRY = os.path.join(PROJECT_ROOT, "desktop_v3", "build", "bridge_entry.py")

# Windows 자동화 + CLI AI 의존성은 동적 import 가 많아 PyInstaller 정적 분석이 놓치기 쉽다.
# 누락 시 frozen exe 가 ImportError 로 죽으므로 명시 수집.
hiddenimports = [
    # FastAPI / uvicorn 런타임
    "uvicorn", "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on", "websockets", "wsproto",
    # Windows UI 자동화 (recorder / element picker / win_inspector)
    "pywinauto", "pywinauto.controls.uiawrapper", "pywinauto.uia_defines",
    "pywinauto.uia_element_info", "uiautomation", "comtypes", "comtypes.stream",
    "win32api", "win32con", "win32gui", "win32process", "win32clipboard",
    "pywinpty", "winpty",
    # 데이터/이미지/기타 core 의존
    "pyautogui", "mss", "PIL", "cv2", "pytesseract", "pandas", "openpyxl",
    "keyring", "keyring.backends", "keyring.backends.Windows",
    "pydantic", "pydantic_settings",
]

# comtypes 가 런타임 생성하는 typelib 캐시 + uiautomation 데이터는 collect_all 권장.
from PyInstaller.utils.hooks import collect_submodules, collect_data_files  # noqa: E402

hiddenimports += collect_submodules("comtypes")
datas = []
datas += collect_data_files("uiautomation")

# config/ (settings/prompts) + core/locale 는 런타임에 파일로 읽으므로 동봉.
datas += [
    (os.path.join(PROJECT_ROOT, "config"), "config"),
    (os.path.join(PROJECT_ROOT, "core", "locale"), "core/locale"),
]

a = Analysis(
    [ENTRY],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["PySide6", "PyQt6", "tkinter"],  # GUI 프레임워크는 브리지에 불필요
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ohdo-bridge",  # main/index.ts 의 packaged spawn 이 기대하는 이름
    console=True,        # stdout READY 마커를 Electron 이 파싱 → 콘솔 필요
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ohdo-bridge",
)
