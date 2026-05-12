# PyInstaller spec for ohdo agent.
#
# 사용:
#     pip install pyinstaller
#     pyinstaller build.spec --clean --noconfirm
#
# 산출물: dist/ohdo-agent/ohdo-agent.exe (+ 동반 DLL)
# Inno Setup 이 이 dist 폴더 전체를 설치 파일로 묶는다.
#
# M2.7: runner.py 가 `core.workflow_engine` 을 import 하므로 pathex 에 프로젝트
# 루트를 추가하고 hiddenimports 에 명시. core.visual_overlay 는 런타임에
# `visual_feedback_enabled=False` 이므로 제외 (용량 절감).

# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None

AGENT_ROOT = Path(".").resolve()
PROJECT_ROOT = AGENT_ROOT.parent  # ohdo/ — core/ 가 여기 있다

# M2.8: 동반 배포할 Windows embeddable Python. 없으면 빌드 직전에
# scripts/fetch-embedded-python.ps1 을 돌려 생성해야 한다.
EMBED_PY_DIR = AGENT_ROOT / "vendor" / "python"
if not (EMBED_PY_DIR / "python.exe").is_file():
    raise SystemExit(
        f"Embedded Python not found at {EMBED_PY_DIR}. "
        "Run scripts/fetch-embedded-python.ps1 first."
    )

a = Analysis(
    [str(AGENT_ROOT / "agent_main.py")],
    pathex=[str(AGENT_ROOT), str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # M2.8: vendor/python/ 를 bundle 의 _internal/python/ 로 복사. runner.py 의
        # _resolve_python_exe() 가 sys._MEIPASS/python/python.exe 를 찾는다.
        (str(EMBED_PY_DIR), "python"),
    ],
    hiddenimports=[
        # pystray 가 플랫폼별 백엔드를 런타임에 고르므로 명시
        "pystray._win32",
        "PIL.Image",
        "PIL.ImageDraw",
        # M2.7: runner 가 사용하는 core 모듈. static analysis 가 못 잡을 수 있어 명시.
        "core",
        "core.workflow_engine",
        # M2.9.1: runner 가 스텝 실패 시 화면 캡처.
        "mss",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 데스크톱 앱 전용 대형 의존성은 Agent 번들에서 제외 (용량 절감)
        "PySide6",
        "PyQt6",  # legacy_pyqt6/ 코드 잔재 방어
        "selenium",
        "opencv",
        "opencv-python",
        "pandas",
        "openpyxl",
        "pywinauto",
        "uiautomation",
        "pytesseract",
        # M2.7: 이하 core 모듈은 runner 가 사용하지 않음. 번들에서 제외해
        # 트랜지티브 의존성 (PySide6/PyQt6 등) 이 딸려오는 것 방지.
        "core.adapters",
        "core.adapters.base_adapter",
        "core.adapters.gemini_cli_adapter",
        "core.ai_engine",
        "core.app_service",
        "core.environment_scanner",
        "core.execution_kernel",
        "core.import_manager",
        "core.kernel_worker",
        "core.prompt_builder",
        "core.session_manager",
        "core.storage",
        "core.visual_overlay",
        "core.win_inspector",
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
