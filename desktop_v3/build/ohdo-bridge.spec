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
    # 주의: PyPI 배포명은 ``pywinpty`` 지만 import 모듈명은 ``winpty`` 다
    # (``pywinpty`` 모듈은 존재하지 않음 → hidden import 로 넣으면 "not found" ERROR).
    "winpty",
    # 데이터/이미지/기타 core 의존
    "pyautogui", "mss", "PIL", "cv2", "pytesseract", "pandas", "openpyxl",
    "keyring", "keyring.backends", "keyring.backends.Windows",
    "pydantic", "pydantic_settings",
    # 코드 실행 커널 (§92) — 소스에서 파일 경로로만 참조돼 정적 분석에 안 잡힌다.
    # frozen 에선 exe 런너 모드(--run-kernel-worker)가 이 모듈을 runpy 로 실행.
    "core.kernel_worker",
]

# comtypes 가 런타임 생성하는 typelib 캐시 + uiautomation 데이터는 collect_all 권장.
from PyInstaller.utils.hooks import collect_submodules, collect_data_files  # noqa: E402

hiddenimports += collect_submodules("comtypes")
datas = []
datas += collect_data_files("uiautomation")

# config 는 개발자 유지 파일만 **명시적으로** 동봉한다 (handoff §81).
# 절대 폴더째 넣지 말 것 — 빌드 머신의 config/settings.json 에는 사용자 API 키가
# 들어 있어(gitignore 대상) 통째 동봉 시 설치본으로 유출된다. settings.json 은
# 번들 밖 --config-dir(userData)에서 first-run 생성/영속된다.
datas += [
    (os.path.join(PROJECT_ROOT, "config", "default_settings.json"), "config"),
    (os.path.join(PROJECT_ROOT, "config", "prompts.json"), "config"),
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
