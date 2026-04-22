# PyInstaller spec for ohdo agent.
#
# 사용:
#     pip install pyinstaller
#     pyinstaller build.spec --clean --noconfirm
#
# 산출물: dist/ohdo-agent/ohdo-agent.exe (+ 동반 DLL)
# Inno Setup 이 이 dist 폴더 전체를 설치 파일로 묶는다.

# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None

AGENT_ROOT = Path(".").resolve()

a = Analysis(
    [str(AGENT_ROOT / "agent_main.py")],
    pathex=[str(AGENT_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        # pystray 가 플랫폼별 백엔드를 런타임에 고르므로 명시
        "pystray._win32",
        "PIL.Image",
        "PIL.ImageDraw",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 데스크톱 앱 전용 대형 의존성은 Agent 번들에서 제외 (용량 절감)
        "PyQt6",
        "selenium",
        "opencv",
        "opencv-python",
        "pandas",
        "openpyxl",
        "pywinauto",
        "uiautomation",
        "pytesseract",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ohdo-agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 트레이 앱 — 콘솔 창 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='installer/ohdo.ico',   # M1 에서 아이콘 파일 추가
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ohdo-agent",
)
