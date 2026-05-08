# SPDX-License-Identifier: AGPL-3.0-or-later
"""
PyQt6 메인 윈도우

3패널 레이아웃: 세션 목록 | 대화 패널 | 코드+캡처 뷰어
하단: 콘솔/로그 패널
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .chat_panel import ChatPanel
from .code_viewer import CodeViewer
from .console_panel import ConsolePanel
from .screen_capture import ScreenCaptureOverlay
from .session_list import SessionListPanel
from .settings_dialog import SettingsDialog

if sys.platform == "win32":
    from .element_picker import ElementPickerOverlay
    from .window_picker import WindowPickerOverlay
else:
    from .element_picker_macos import ElementPickerOverlay

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent

# 시스템 모듈 import
sys.path.insert(0, str(PROJECT_ROOT))
from core.ai_engine import AIEngineManager
from core.execution_kernel import ExecutionKernel
from core.import_manager import extract_initial_block
from core.prompt_builder import PromptBuilder
from core.session_manager import Session, SessionManager
from core.win_inspector import WindowInspector
from core.workflow_engine import (
    CodeSandbox,
    WorkflowEngine,
    extract_library_block,
    extract_step_delta_code,
)

logger = logging.getLogger(__name__)


class AsyncSignals(QObject):
    """스레드 간 통신 시그널"""

    ai_response_ready = pyqtSignal(dict)  # AI 응답 수신
    step_executed = pyqtSignal(dict)  # 스텝 실행 완료
    log_message = pyqtSignal(str)  # 로그 메시지
    error_occurred = pyqtSignal(str)  # 에러 발생
    # 블럭 실행 전용
    block_step_started = pyqtSignal(int)  # 블럭 스텝 시작 (step_id)
    block_step_done = pyqtSignal(dict)  # 블럭 스텝 완료
    blocks_finished = pyqtSignal()  # 블럭 실행 모두 완료 (UI 복원 트리거)
    kernel_status_changed = pyqtSignal()  # 커널 상태 변경


class MainWindow(QMainWindow):
    """
    AI RPA Solution 메인 윈도우.

    레이아웃:
    ┌──────────┬─────────────┬──────────────┐
    │ 세션목록  │  대화 패널   │ 코드+캡처 뷰어 │
    ├──────────┴─────────────┴──────────────┤
    │           콘솔/로그 패널               │
    └──────────────────────────────────────┘
    """

    def __init__(self):
        super().__init__()

        self.setWindowTitle("AI RPA Solution v2.0")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # ── 설정 로드 ──
        self.settings = self._load_settings()
        self.prompts_config = self._load_prompts()

        # ── 코어 엔진 초기화 ──
        self.session_manager = SessionManager()
        self.ai_engine = AIEngineManager(self.settings)
        self.prompt_builder = PromptBuilder(self.prompts_config)
        self.workflow_engine = WorkflowEngine(
            step_delay_ms=self.settings.get("execution", {}).get("step_delay_ms", 500),
            visual_feedback_enabled=self.settings.get("visual_feedback", {}).get("enabled", True),
        )

        # ── 상태 변수 ──
        self.current_session: Optional[Session] = None
        self.current_code: str = ""
        self.is_processing: bool = False
        self.pending_images: list[str] = []
        self._current_sandbox: Optional[CodeSandbox] = None  # F9 강제 중지용

        # ── 블럭 실행 커널 (세션별 유지) ──
        self._kernels: dict[str, ExecutionKernel] = {}  # session_id → ExecutionKernel

        # ── 영역 캡처 오버레이 ──
        self.capture_overlay = ScreenCaptureOverlay()
        self.capture_overlay.capture_completed.connect(self._on_region_captured)
        self.capture_overlay.capture_cancelled.connect(self._on_capture_cancelled)

        # ── 윈도우 인스펙터 ──
        self.win_inspector = WindowInspector()
        self.pending_window_context: str = ""

        # ── 윈도우 피커 오버레이 (Windows 전용) ──
        self.window_picker = None
        if sys.platform == "win32":
            self.window_picker = WindowPickerOverlay()
            self.window_picker.window_picked.connect(self._on_window_picked)
            self.window_picker.pick_cancelled.connect(self._on_window_pick_cancelled)

        # ── UI 요소 피커 오버레이 ──
        self.element_picker = ElementPickerOverlay(settings=self.settings)

        # ── UI 검사 핸들러 (element picker + window inspector 콜백 분리) ──
        from ui.ui_inspection_handler import UIInspectionHandler

        self.inspection_handler = UIInspectionHandler(self)
        self.element_picker.element_picked.connect(self.inspection_handler.on_picked)
        self.element_picker.pick_cancelled.connect(self.inspection_handler.on_pick_cancelled)

        # ── 블럭/코드 실행 controller (코드 뷰어 ▶ + 블럭 뷰 ▶/⏯ + F9 stop) ──
        from ui.block_execution_handler import BlockExecutionHandler

        self.block_executor = BlockExecutionHandler(self)

        # ── AI 호출 controller (사용자 메시지 → AI 어댑터 → 응답 처리 → step 누적) ──
        from ui.ai_call_handler import AICallHandler

        self.ai_handler = AICallHandler(self)

        # ── 비동기 시그널 ──
        self.signals = AsyncSignals()
        self.signals.ai_response_ready.connect(self._on_ai_response)
        self.signals.step_executed.connect(self._on_step_executed)
        self.signals.log_message.connect(self._on_log_message)
        self.signals.error_occurred.connect(self._on_error)
        self.signals.block_step_started.connect(self._on_block_step_started)
        self.signals.block_step_done.connect(self._on_block_step_done)
        self.signals.blocks_finished.connect(self._on_blocks_finished)
        self.signals.kernel_status_changed.connect(self._on_kernel_status_changed)

        # ── UI 구성 ──
        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_statusbar()
        self._setup_shortcuts()
        self._apply_theme()

        # ── 로깅 설정 ──
        self._setup_logging()

        # 초기 상태
        self.statusBar().showMessage("준비 완료 - 새 세션을 생성하거나 기존 세션을 불러오세요")

    # ──────────────────────────────────────────
    # 설정 로드
    # ──────────────────────────────────────────

    def _load_settings(self) -> dict:
        settings_file = PROJECT_ROOT / "config" / "settings.json"
        if settings_file.exists():
            with open(settings_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _load_prompts(self) -> dict:
        prompts_file = PROJECT_ROOT / "config" / "prompts.json"
        if prompts_file.exists():
            with open(prompts_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_settings(self):
        settings_file = PROJECT_ROOT / "config" / "settings.json"
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=2)

    # ──────────────────────────────────────────
    # UI 구성
    # ──────────────────────────────────────────

    def _setup_ui(self):
        """메인 윈도우 레이아웃 구성"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # ── 상단: 3패널 영역 ──
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 1. 세션 목록 패널 (왼쪽)
        self.session_list = SessionListPanel()
        self.session_list.session_selected.connect(self._on_session_selected)
        self.session_list.session_delete_requested.connect(self._on_session_delete)
        self.main_splitter.addWidget(self.session_list)

        # 2. 대화 패널 (중앙)
        self.chat_panel = ChatPanel()
        self.chat_panel.message_sent.connect(self._on_user_message)
        self.chat_panel.capture_requested.connect(self._on_capture_request)
        self.chat_panel.element_pick_requested.connect(self.inspection_handler.on_pick_request)
        self.chat_panel.cancel_requested.connect(self._on_cancel_ai)
        self.main_splitter.addWidget(self.chat_panel)

        # 3. 코드+캡처 뷰어 (오른쪽)
        self.code_viewer = CodeViewer()
        self.code_viewer.run_code_requested.connect(self._on_run_code)
        self.code_viewer.stop_code_requested.connect(self._on_stop_code)
        self.code_viewer.step_delete_requested.connect(self._on_step_delete)
        self.code_viewer.step_insert_requested.connect(self._on_step_insert)
        self.code_viewer.step_move_requested.connect(self._on_step_move)
        self.code_viewer.step_code_edited.connect(self._on_step_code_edited)
        # 블럭 뷰 전용
        self.code_viewer.run_from_step_requested.connect(self._on_run_from_step)
        self.code_viewer.run_single_step_requested.connect(self._on_run_single_step)
        self.code_viewer.wait_changed.connect(self._on_wait_changed)
        self.code_viewer.kernel_reset_requested.connect(self._on_kernel_reset)
        self.code_viewer.block_step_code_edited.connect(self._on_block_step_code_edited)
        self.code_viewer.block_step_delete_requested.connect(self._on_step_delete)
        self.main_splitter.addWidget(self.code_viewer)

        # 스플리터 비율 설정 (세션:대화:코드 = 1:2:2)
        self.main_splitter.setSizes([200, 450, 450])

        # ── 하단: 콘솔/로그 패널 ──
        self.vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.vertical_splitter.addWidget(self.main_splitter)

        self.console_panel = ConsolePanel()
        self.vertical_splitter.addWidget(self.console_panel)

        # 상단:하단 비율 = 7:3
        self.vertical_splitter.setSizes([600, 250])

        main_layout.addWidget(self.vertical_splitter)

    def _setup_menu(self):
        """메뉴바 구성"""
        menubar = self.menuBar()

        # 파일 메뉴
        file_menu = menubar.addMenu("파일(&F)")

        new_action = QAction("새 세션(&N)", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._new_session)
        file_menu.addAction(new_action)

        open_action = QAction("세션 불러오기(&O)", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._load_session_dialog)
        file_menu.addAction(open_action)

        save_action = QAction("세션 저장(&S)", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_current_session)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        export_action = QAction("워크플로우 내보내기(&E)...", self)
        export_action.triggered.connect(self._export_workflow)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        exit_action = QAction("종료(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 실행 메뉴
        run_menu = menubar.addMenu("실행(&R)")

        stop_action = QAction("⛔ 실행 강제 중지", self)
        stop_action.setShortcut(QKeySequence(Qt.Key.Key_F9))
        stop_action.setStatusTip("실행 중인 코드를 즉시 강제 종료합니다 (F9)")
        stop_action.triggered.connect(self._on_stop_code)
        run_menu.addAction(stop_action)

        # 설정 메뉴
        settings_menu = menubar.addMenu("설정(&S)")

        pref_action = QAction("환경 설정(&P)...", self)
        pref_action.triggered.connect(self._open_settings)
        settings_menu.addAction(pref_action)

        # 도움말 메뉴
        help_menu = menubar.addMenu("도움말(&H)")
        about_action = QAction("AI RPA Solution 소개", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self):
        """툴바 구성"""
        toolbar = QToolBar("메인 툴바")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # 새 세션 버튼
        new_btn = QAction("📄 새 세션", self)
        new_btn.triggered.connect(self._new_session)
        toolbar.addAction(new_btn)

        toolbar.addSeparator()

        # AI 엔진 선택 콤보박스
        ai_label = QAction("AI 엔진:", self)
        ai_label.setEnabled(False)
        toolbar.addAction(ai_label)

        self.ai_combo = QComboBox()
        self.ai_combo.setMinimumWidth(150)
        self._refresh_ai_combo()
        self.ai_combo.currentTextChanged.connect(self._on_ai_engine_changed)
        toolbar.addWidget(self.ai_combo)

        toolbar.addSeparator()

        # 전체 실행 버튼
        run_all_btn = QAction("▶ 전체 실행", self)
        run_all_btn.triggered.connect(self._run_all_steps)
        toolbar.addAction(run_all_btn)

        toolbar.addSeparator()

        # 윈도우 검사 버튼
        inspect_btn = QAction("🔍 윈도우 검사", self)
        inspect_btn.triggered.connect(self._inspect_window)
        toolbar.addAction(inspect_btn)

    def _setup_statusbar(self):
        """상태바 구성"""
        self.statusBar().showMessage("준비됨")

    def _setup_shortcuts(self):
        """전역 키보드 단축키 등록"""
        # F9: 실행 중인 코드 강제 중지 (포커스 위치에 관계없이 동작)
        f9 = QShortcut(QKeySequence(Qt.Key.Key_F9), self)
        f9.setContext(Qt.ShortcutContext.ApplicationShortcut)
        f9.activated.connect(self._on_stop_code)

    def _apply_theme(self):
        """테마 적용"""
        theme = self.settings.get("ui", {}).get("theme", "dark")
        theme_file = PROJECT_ROOT / "ui" / "resources" / "styles" / f"{theme}_theme.qss"

        if theme_file.exists():
            with open(theme_file, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        else:
            # 기본 다크 테마
            self.setStyleSheet(self._get_default_dark_theme())

    def _get_default_dark_theme(self) -> str:
        """기본 다크 테마 스타일시트"""
        return """
        QMainWindow {
            background-color: #1e1e2e;
            color: #cdd6f4;
        }
        QWidget {
            background-color: #1e1e2e;
            color: #cdd6f4;
            font-family: 'Malgun Gothic', 'Segoe UI', sans-serif;
            font-size: 11px;
        }
        QMenuBar {
            background-color: #181825;
            color: #cdd6f4;
            border-bottom: 1px solid #313244;
        }
        QMenuBar::item:selected {
            background-color: #45475a;
        }
        QMenu {
            background-color: #1e1e2e;
            color: #cdd6f4;
            border: 1px solid #313244;
        }
        QMenu::item:selected {
            background-color: #45475a;
        }
        QToolBar {
            background-color: #181825;
            border-bottom: 1px solid #313244;
            spacing: 5px;
            padding: 3px;
        }
        QSplitter::handle {
            background-color: #313244;
            width: 2px;
            height: 2px;
        }
        QPushButton {
            background-color: #45475a;
            color: #cdd6f4;
            border: 1px solid #585b70;
            border-radius: 4px;
            padding: 6px 16px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #585b70;
        }
        QPushButton:pressed {
            background-color: #6c7086;
        }
        QPushButton:disabled {
            background-color: #313244;
            color: #585b70;
        }
        QLineEdit, QTextEdit, QPlainTextEdit {
            background-color: #313244;
            color: #cdd6f4;
            border: 1px solid #45475a;
            border-radius: 4px;
            padding: 4px;
            selection-background-color: #585b70;
        }
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
            border: 1px solid #89b4fa;
        }
        QComboBox {
            background-color: #313244;
            color: #cdd6f4;
            border: 1px solid #45475a;
            border-radius: 4px;
            padding: 4px 8px;
        }
        QComboBox::drop-down {
            border: none;
        }
        QComboBox QAbstractItemView {
            background-color: #1e1e2e;
            color: #cdd6f4;
            border: 1px solid #45475a;
            selection-background-color: #45475a;
        }
        QListWidget {
            background-color: #181825;
            color: #cdd6f4;
            border: 1px solid #313244;
            border-radius: 4px;
        }
        QListWidget::item {
            padding: 8px;
            border-bottom: 1px solid #313244;
        }
        QListWidget::item:selected {
            background-color: #45475a;
            color: #cdd6f4;
        }
        QListWidget::item:hover {
            background-color: #313244;
        }
        QTabWidget::pane {
            border: 1px solid #313244;
            background-color: #1e1e2e;
        }
        QTabBar::tab {
            background-color: #181825;
            color: #a6adc8;
            border: 1px solid #313244;
            padding: 6px 16px;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background-color: #1e1e2e;
            color: #cdd6f4;
            border-bottom: 2px solid #89b4fa;
        }
        QStatusBar {
            background-color: #181825;
            color: #a6adc8;
            border-top: 1px solid #313244;
        }
        QGroupBox {
            border: 1px solid #313244;
            border-radius: 4px;
            margin-top: 10px;
            padding-top: 10px;
            color: #cdd6f4;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }
        QScrollBar:vertical {
            background-color: #181825;
            width: 10px;
            margin: 0;
        }
        QScrollBar::handle:vertical {
            background-color: #45475a;
            border-radius: 5px;
            min-height: 20px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: #585b70;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }
        QLabel {
            color: #cdd6f4;
        }
        """

    def _setup_logging(self):
        """로깅 설정"""
        log_config = self.settings.get("logging", {})
        log_level = getattr(logging, log_config.get("level", "INFO"))

        # 파일 핸들러
        if log_config.get("file_enabled", True):
            log_dir = PROJECT_ROOT / "logs"
            log_dir.mkdir(exist_ok=True)
            log_file = log_dir / f"rpa_{datetime.now().strftime('%Y%m%d')}.log"

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(
                logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
            )
            logging.getLogger().addHandler(file_handler)

        logging.getLogger().setLevel(log_level)

    # ──────────────────────────────────────────
    # AI 엔진 관리
    # ──────────────────────────────────────────

    def _refresh_ai_combo(self):
        """AI 엔진 콤보박스 새로고침"""
        self.ai_combo.blockSignals(True)
        self.ai_combo.clear()
        for engine in self.ai_engine.list_available():
            display = f"{engine['display_name']}"
            if not engine["available"]:
                display += " (미설치)"
            self.ai_combo.addItem(display, engine["name"])
            if engine["is_current"]:
                self.ai_combo.setCurrentText(display)
        self.ai_combo.blockSignals(False)

    def _on_ai_engine_changed(self, text: str):
        """AI 엔진 변경"""
        idx = self.ai_combo.currentIndex()
        engine_name = self.ai_combo.itemData(idx)
        if engine_name:
            try:
                self.ai_engine.switch_engine(engine_name)
                self.console_panel.log(f"AI 엔진 변경: {text}", "INFO")
            except ValueError as e:
                self.console_panel.log(str(e), "ERROR")

    # ──────────────────────────────────────────
    # 세션 관리
    # ──────────────────────────────────────────

    def _new_session(self):
        """새 세션 생성"""
        from PyQt6.QtWidgets import QInputDialog

        title, ok = QInputDialog.getText(
            self,
            "새 세션",
            "세션 제목을 입력하세요:",
            text=f"RPA_{datetime.now().strftime('%Y%m%d_%H%M')}",
        )
        if not ok or not title.strip():
            return

        # 프로젝트 유형 자동 탐지 모드로 설정 ("auto")
        project_type = "auto"

        self.current_session = self.session_manager.create_session(
            title=title.strip(), project_type=project_type
        )
        self.current_code = ""

        # UI 갱신
        self.chat_panel.clear()
        self.code_viewer.clear()
        self.chat_panel.add_system_message(
            f"새 세션 '{title}' 생성 완료!\n"
            f"자동화하고 싶은 작업을 입력해주세요. (예: 메모장 열기, 특정 웹페이지 접속 등)\n"
            f"입력하신 내용을 바탕으로 데스크톱/웹 자동화 방식을 스스로 결정합니다."
        )
        self._refresh_session_list()
        self.statusBar().showMessage(f"세션 생성: {title}")
        self.console_panel.log(f"새 세션 생성: {title} (자동 탐지 모드)", "INFO")

    def _refresh_session_list(self):
        """세션 목록 새로고침. 현재 작업 중인 세션 강조 표시."""
        sessions = self.session_manager.list_sessions()
        self.session_list.refresh(sessions)
        active_id = self.current_session.session_id if self.current_session else None
        self.session_list.set_active_session(active_id)

    def _on_session_selected(self, session_id: str):
        """세션 목록에서 세션 선택"""
        try:
            # 이전 세션의 커널은 유지 (다시 돌아올 수 있으므로 stop하지 않음)
            self.current_session = self.session_manager.load_session(session_id)
            self._restore_session_ui()
            self.session_list.set_active_session(session_id)
            self.statusBar().showMessage(f"세션 로드: {self.current_session.title}")
            self.console_panel.log(f"세션 로드: {self.current_session.title}", "INFO")
        except Exception as e:
            QMessageBox.warning(self, "로드 실패", f"세션을 불러올 수 없습니다:\n{e}")

    def _on_session_delete(self, session_id: str):
        """세션 삭제 요청"""
        reply = QMessageBox.question(
            self,
            "세션 삭제",
            "선택한 세션을 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.session_manager.delete_session(session_id)
            if self.current_session and self.current_session.session_id == session_id:
                self.current_session = None
                self.chat_panel.clear()
                self.code_viewer.clear()
            self._refresh_session_list()
            self.console_panel.log("세션 삭제 완료", "INFO")

    def _restore_session_ui(self):
        """세션 데이터를 UI에 복원"""
        if not self.current_session:
            return

        self.chat_panel.clear()
        self.code_viewer.clear()

        for step_data in self.current_session.steps:
            step = step_data if isinstance(step_data, dict) else {}

            # 대화 복원
            for msg in step.get("conversation", []):
                m = msg if isinstance(msg, dict) else {}
                if m.get("role") == "user":
                    self.chat_panel.add_user_message(m.get("content", ""))
                elif m.get("role") == "assistant":
                    self.chat_panel.add_ai_message(m.get("content", ""))

            # 코드 복원
            code = step.get("generated_code", "")
            if code:
                self.current_code = code
                captures = step.get("captures", [])
                capture_path = None
                if captures:
                    c = captures[0] if isinstance(captures[0], dict) else {}
                    capture_path = c.get("path")
                self.code_viewer.add_step(step.get("step_id", 0), code, capture_path)

        # 블럭 뷰 갱신
        self._refresh_block_view()

    def _save_current_session(self):
        """현재 세션 저장"""
        if not self.current_session:
            QMessageBox.information(self, "안내", "저장할 세션이 없습니다.")
            return
        self.session_manager.save_session(self.current_session)
        self.statusBar().showMessage("세션 저장 완료")
        self.console_panel.log("세션 저장 완료", "INFO")

    def _load_session_dialog(self):
        """세션 불러오기 - 목록 새로고침"""
        self._refresh_session_list()

    def _export_workflow(self):
        """워크플로우를 독립 프로젝트 폴더로 내보내기"""
        if not self.current_session:
            QMessageBox.information(self, "안내", "내보낼 세션이 없습니다.")
            return

        # 출력 디렉터리 선택
        default_dir = self.settings.get("output_project", {}).get("default_output_dir", "")
        if not default_dir:
            default_dir = str(Path.home() / "Desktop")

        output_dir = QFileDialog.getExistingDirectory(
            self, "프로젝트 내보내기 - 폴더 선택", default_dir
        )
        if not output_dir:
            return

        # 프로젝트 폴더명 = 세션 제목
        import re

        safe_name = re.sub(r'[<>:"/\\|?*]', "_", self.current_session.title)
        project_dir = Path(output_dir) / safe_name

        try:
            output_settings = self.settings.get("output_project", {})

            self.session_manager.export_as_project(
                session=self.current_session, output_dir=project_dir, settings=output_settings
            )

            self.console_panel.log(f"프로젝트 내보내기 완료: {project_dir}", "INFO")
            self.console_panel.log("  - main.py (코드)", "INFO")
            self.console_panel.log("  - requirements.txt (패키지 목록)", "INFO")
            self.console_panel.log("  - README.md (설치/실행 가이드)", "INFO")
            self.console_panel.log("  - run.bat (윈도우 실행 스크립트)", "INFO")

            QMessageBox.information(
                self,
                "내보내기 완료",
                f"프로젝트가 생성되었습니다:\n{project_dir}\n\n"
                f"생성된 파일:\n"
                f"  • main.py - 실행 코드\n"
                f"  • requirements.txt - 패키지 목록\n"
                f"  • README.md - 설치/실행 가이드\n"
                f"  • run.bat - 윈도우 실행 스크립트",
            )
        except Exception as e:
            self.console_panel.log(f"내보내기 실패: {e}", "ERROR")
            QMessageBox.warning(self, "내보내기 실패", f"프로젝트 생성 중 오류:\n{e}")

    # ──────────────────────────────────────────
    # 사용자 입력 처리 (AI 연동)
    # ──────────────────────────────────────────

    def _on_cancel_ai(self):
        """AI 생성 중지 요청 처리 (위임 → AICallHandler)"""
        self.ai_handler.on_cancel_ai()

    def _on_user_message(self, message: str):
        """사용자가 대화 패널에서 메시지를 전송 (위임 → AICallHandler)"""
        self.ai_handler.on_user_message(message)

    def _call_ai_thread(self, user_message: str, images: list[str]):
        """백그라운드 스레드: AI 프롬프트 전송 및 응답 수신 (위임 → AICallHandler)"""
        self.ai_handler.call_ai_thread(user_message, images)

    def _on_ai_response(self, data: dict):
        """AI 응답 수신 처리 (메인 스레드, 위임 → AICallHandler)"""
        self.ai_handler.on_ai_response(data)

    def _on_step_executed(self, data: dict):
        """스텝 실행 완료 처리 (위임 → AICallHandler)"""
        self.ai_handler.on_step_executed(data)

    def _on_log_message(self, message: str):
        """로그 메시지 처리"""
        # workflow_engine에서 에러 traceback 줄은 "  " 들여쓰기 또는 "─"로 시작
        if message.startswith("  ") or message.startswith("─"):
            self.console_panel.log(message, "ERROR")
        else:
            self.console_panel.log(message, "INFO")

    def _on_error(self, message: str):
        """에러 처리"""
        self.console_panel.log(message, "ERROR")
        self.is_processing = False
        self.chat_panel.set_input_enabled(True)
        self.statusBar().showMessage("에러 발생")

    # ──────────────────────────────────────────
    # 화면 캡처 (영역 선택)
    # ──────────────────────────────────────────

    def _on_capture_request(self):
        """화면 캡처 요청 - 영역 선택 오버레이 표시"""
        # 먼저 자신을 최소화한 뒤, 그 다음 포그라운드 윈도우를 검사+캡처
        self.showMinimized()
        QTimer.singleShot(400, self._inspect_then_capture)

    def _inspect_then_capture(self):
        """최소화 후: 포그라운드 윈도우 검사 → 캡처 시작"""
        self.inspection_handler.auto_inspect_before_capture()
        QTimer.singleShot(100, self._start_region_capture)

    def _start_region_capture(self):
        """영역 선택 캡처 오버레이를 시작합니다."""
        self.capture_overlay.start_capture()

    def _on_region_captured(self, pil_image):
        """영역 캡처 완료 콜백"""
        try:
            from PIL import Image

            img = pil_image

            # 이미지 품질 조절
            img_config = self.settings.get("image", {})
            max_width = img_config.get("max_width", 1280)

            if img.width > max_width:
                ratio = max_width / img.width
                new_size = (max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            # 세션 캡처 폴더에 저장
            if self.current_session:
                captures_dir = self.session_manager.get_captures_dir(
                    self.current_session.session_id
                )
            else:
                captures_dir = PROJECT_ROOT / "data" / "captures"
                captures_dir.mkdir(parents=True, exist_ok=True)

            filename = f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            filepath = captures_dir / filename
            img.save(str(filepath))

            self.pending_images.append(str(filepath))
            self.chat_panel.set_capture_status(
                f"📷 캡처 완료: {filename} ({img.width}×{img.height})"
            )
            self.console_panel.log(f"영역 캡처 저장: {filepath} ({img.width}×{img.height})", "INFO")

        except Exception as e:
            self.console_panel.log(f"캡처 저장 실패: {e}", "ERROR")

        finally:
            self.showNormal()
            self.activateWindow()

    def _on_capture_cancelled(self):
        """캡처 취소 콜백"""
        self.showNormal()
        self.activateWindow()
        self.console_panel.log("캡처가 취소되었습니다.", "INFO")

    def _inspect_window(self):
        """윈도우 피커를 열어 사용자가 검사할 윈도우를 클릭으로 선택하게 합니다."""
        if not self.win_inspector.is_available:
            QMessageBox.warning(
                self,
                "기능 비활성화",
                "pywinauto가 설치되지 않았습니다.\npip install pywinauto 로 설치해주세요.",
            )
            return

        self.console_panel.log("윈도우 피커 시작 — 검사할 윈도우를 클릭하세요", "INFO")
        self.statusBar().showMessage("검사할 윈도우를 클릭하세요...")

        # 앱을 최소화하고 윈도우 피커 오버레이 표시
        if self.window_picker is None:
            self.console_panel.log("윈도우 피커는 Windows에서만 지원됩니다", "WARNING")
            return
        self.showMinimized()
        QTimer.singleShot(400, self.window_picker.start_pick)

    def _on_window_picked(self, hwnd: int, title: str):
        """윈도우 피커에서 윈도우가 선택됨"""
        self.console_panel.log(f"윈도우 선택됨: '{title}' (핸들: {hwnd})", "INFO")
        self.statusBar().showMessage(f"윈도우 검사 중: {title}")

        try:
            window_info = self.win_inspector.inspect_window(
                handle=hwnd, max_depth=3, max_controls=50
            )
            self.inspection_handler.finish_inspect(window_info)
        except Exception as e:
            self.console_panel.log(f"윈도우 검사 실패: {e}", "ERROR")
            self.inspection_handler.finish_inspect(None)

    def _on_window_pick_cancelled(self):
        """윈도우 피커가 취소됨 (ESC)"""
        self.showNormal()
        self.activateWindow()
        self.console_panel.log("윈도우 검사가 취소되었습니다.", "INFO")
        self.statusBar().showMessage("준비 완료")

    # ──────────────────────────────────────────
    # UI 요소 선택 (Element Picker)
    # ──────────────────────────────────────────

    # ──────────────────────────────────────────
    # 스텝 관리 (삭제/삽입/이동)
    # ──────────────────────────────────────────

    def _on_step_delete(self, step_id: int):
        """스텝 삭제 처리"""
        if not self.current_session:
            return

        success = self.session_manager.delete_step(self.current_session, step_id)
        if success:
            self.console_panel.log(f"Step #{step_id} 삭제 완료", "INFO")
            self._refresh_code_viewer()
        else:
            self.console_panel.log(f"Step #{step_id} 삭제 실패", "ERROR")

    def _on_step_insert(self, after_step_id: int):
        """스텝 삽입 처리"""
        if not self.current_session:
            return

        new_id = self.session_manager.insert_step(
            self.current_session,
            after_step_id,
            code="# 여기에 코드를 작성하거나 AI에게 요청하세요\n",
            description="수동 삽입된 스텝",
        )
        self.console_panel.log(
            f"Step #{after_step_id} 다음에 새 스텝 삽입 (→ Step #{new_id})", "INFO"
        )
        self._refresh_code_viewer()

    def _on_step_move(self, step_id: int, direction: str):
        """스텝 이동 처리"""
        if not self.current_session:
            return

        success = self.session_manager.move_step(self.current_session, step_id, direction)
        if success:
            dir_text = "위로" if direction == "up" else "아래로"
            self.console_panel.log(f"Step #{step_id} {dir_text} 이동", "INFO")
            self.console_panel.log(
                "⚠ 스텝 이동 시 코드 의존성에 주의하세요 "
                "(이전 스텝의 변수/결과에 의존하는 코드가 있을 수 있습니다)",
                "WARNING",
            )
            self._refresh_code_viewer()
        else:
            self.console_panel.log(f"Step #{step_id} 이동 실패 (더 이상 이동 불가)", "WARNING")

    def _apply_manual_edit_patches(self, code: str) -> str:
        """수동 편집 / AI 공백 변조 복원 (위임 → AICallHandler)"""
        return self.ai_handler.apply_manual_edit_patches(code)

    def _on_block_step_code_edited(self, step_id: int, new_code: str):
        """블럭 뷰에서 step_code 수정 시 세션에 반영.

        두 필드 동시 업데이트 + import 보존 — extract_step_delta_code 우선순위 (1) 마커 /
        (2) diff 가 모두 generated_code 기반이라, step_code 만 업데이트하면 stale
        generated_code 가 화면/실행에서 우선되어 수정이 무시되는 회귀 (5/4 사용자 보고).

        block 카드 코드 영역에는 import 가 표시되지 않으므로, 새 generated_code 를
        재구성할 때 원본 step.generated_code 의 import 들을 보존해야 함. 안 그러면
        실행 시 NameError 발생 (5/4 사용자 2차 보고: 'Application'/'Keys' is not defined).
        """
        if not self.current_session:
            return
        if step_id == 0:
            # 라이브러리 블럭 수정 — 세션에 저장할 위치가 없으므로 알림만
            self.console_panel.log(
                "[편집] 라이브러리 블럭은 실행 시에만 적용됩니다 (세션 저장 대상 아님).", "INFO"
            )
            return

        # prev step (step_id - 1) 의 generated_code 가져오기
        prev_generated = ""
        old_generated = ""
        for step in self.current_session.steps:
            s = step if isinstance(step, dict) else {}
            sid = s.get("step_id")
            if sid == step_id - 1:
                prev_generated = s.get("generated_code", "")
            elif sid == step_id:
                old_generated = s.get("generated_code", "")

        # 원본 step.generated_code 의 import 보존 — block 카드는 import 표시 안 함
        # → 사용자가 수정할 때 import 안 건드림. 재구성 시 옛 import 그대로 살림.
        from core.import_manager import extract_imports, merge_imports

        old_imports, _ = extract_imports(old_generated) if old_generated else ([], "")
        prev_imports, prev_body = extract_imports(prev_generated) if prev_generated else ([], "")
        # 새 step_code 도 import 가 들어있을 수 있음 (사용자가 import 라인 추가 가능)
        new_step_imports, new_step_body = extract_imports(new_code)

        merged_imports = merge_imports([prev_imports, old_imports, new_step_imports])
        import_block = "\n".join(merged_imports)

        # 새 generated_code = imports + prev body + 새 step_code body
        parts: list[str] = []
        if import_block.strip():
            parts.append(import_block)
        if prev_body.strip():
            parts.append(prev_body.rstrip())
        if new_step_body.strip():
            parts.append(new_step_body)
        new_generated = "\n\n".join(parts) if parts else new_code

        self.session_manager.update_step(
            self.current_session,
            step_id,
            {
                "step_code": new_step_body,
                "step_imports": new_step_imports if new_step_imports else old_imports,
                "generated_code": new_generated,
                "manually_edited": True,
                "edit_original_code": old_generated,
            },
        )
        # 코드 뷰어 탭 (StepCard) 갱신 — 위젯이 stale 한 채로 남아 사용자가 변경을 못 보는
        # 회귀 방지 (5/4 사용자 보고: 블럭 뷰 수정 후 코드 뷰어 탭은 옛 값 표시).
        self._refresh_code_viewer()
        self.console_panel.log(f"[블럭 편집] Step #{step_id} delta 코드가 수정되었습니다.", "INFO")

    def _on_step_code_edited(self, step_id: int, new_code: str):
        """사용자가 코드 직접 수정 시 세션에 반영.

        두 필드 + step_imports 동시 업데이트 — generated_code 만 업데이트하면 stale
        step_code 가 남아 jupyter mode 단독 실행 시 이전 값이 사용되는 회귀.

        코드 뷰는 generated_code 통째로 표시하므로 사용자가 import 도 수정 가능 →
        새 generated_code 에서 import / body 분리해 step_imports / step_code 둘 다 갱신.
        """
        if not self.current_session:
            return
        # prev step 의 generated_code + 수정 전 코드 한 번에 수집
        prev_generated = ""
        old_code = ""
        for step in self.current_session.steps:
            s = step if isinstance(step, dict) else {}
            sid = s.get("step_id")
            if sid == step_id - 1:
                prev_generated = s.get("generated_code", "")
            elif sid == step_id:
                old_code = s.get("generated_code", "")

        # 새 step_code (delta) + step_imports 재계산
        from core.import_manager import (
            extract_code_delta,
            extract_import_delta,
            extract_imports,
        )

        new_imports_all, new_body_all = extract_imports(new_code)
        if prev_generated.strip():
            prev_imports, prev_body = extract_imports(prev_generated)
            new_step_code = extract_code_delta(new_body_all, prev_body)
            new_step_imports = extract_import_delta(new_imports_all, prev_imports)
        else:
            # 첫 스텝 — step_code = body (import 제외), step_imports = 전체 imports
            new_step_code = new_body_all
            new_step_imports = new_imports_all

        self.session_manager.update_step(
            self.current_session,
            step_id,
            {
                "generated_code": new_code,
                "step_code": new_step_code,
                "step_imports": new_step_imports,
                "manually_edited": True,
                "edit_original_code": old_code,
            },
        )
        # 블럭 뷰 (BlockCard) 도 갱신 — step_code 가 바뀌었으므로 화면 동기화 필수.
        self._refresh_block_view()
        self.console_panel.log(
            f"[편집] Step #{step_id} 코드가 수정되었습니다. 다음 AI 요청에 반영됩니다.", "INFO"
        )

    def _refresh_code_viewer(self):
        """세션의 스텝 데이터를 CodeViewer에 동기화합니다."""
        if not self.current_session:
            return

        steps_data = []
        for step in self.current_session.steps:
            s = step if isinstance(step, dict) else {}
            step_id = s.get("step_id", 0)
            code = s.get("generated_code", "")
            captures = s.get("captures", [])
            capture_path = None
            if captures:
                cap = captures[0] if isinstance(captures[0], dict) else {}
                capture_path = cap.get("path")

            steps_data.append({"step_id": step_id, "code": code, "capture_path": capture_path})

        self.code_viewer.refresh_steps(steps_data)
        self._refresh_block_view()

    # ──────────────────────────────────────────
    # 코드 실행
    # ──────────────────────────────────────────

    def _on_run_code(self, code: str):
        """코드 실행 요청 (코드 뷰어 탭의 ▶ 실행 버튼) — handler 위임."""
        self.block_executor.on_run_code(code)

    def _execute_code_thread(self, code: str):
        """코드를 백그라운드에서 실행 — handler 위임."""
        self.block_executor.execute_code_thread(code)

    # ──────────────────────────────────────────
    # 블럭 기반 실행 (Colab-style)
    # ──────────────────────────────────────────

    def _get_or_create_kernel(self) -> Optional[ExecutionKernel]:
        """현재 세션의 ExecutionKernel을 반환합니다 (없으면 생성) — handler 위임."""
        return self.block_executor.get_or_create_kernel()

    def _on_run_from_step(self, start_step_id: int):
        """블럭 뷰: N번 스텝부터 실행 요청 — handler 위임."""
        self.block_executor.on_run_from_step(start_step_id)

    def _on_run_single_step(self, step_id: int):
        """블럭 뷰: N번 스텝 단독 실행 — handler 위임."""
        self.block_executor.on_run_single_step(step_id)

    def _on_wait_changed(self, step_id: int, new_wait):
        """Wait 변경 (step > session > 글로벌 우선순위) — handler 위임."""
        self.block_executor.on_wait_changed(step_id, new_wait)

    def _on_kernel_reset(self):
        """커널 재시작 요청 — handler 위임."""
        self.block_executor.on_kernel_reset()

    def _run_blocks_thread(
        self,
        kernel: ExecutionKernel,
        start_step_id: int,
        stop_after_step_id: int | None = None,
    ):
        """블럭 기반 실행 백그라운드 스레드 — handler 위임."""
        self.block_executor.run_blocks_thread(kernel, start_step_id, stop_after_step_id)

    def _on_blocks_finished(self):
        """블럭 실행 완료 후 UI 복원 (signals.blocks_finished slot) — handler 위임."""
        self.block_executor.on_blocks_finished()

    def _restore_main_window(self):
        """메인 윈도우 raise_/activateWindow 복원 — handler 위임."""
        self.block_executor.restore_main_window()

    def _on_block_step_started(self, step_id: int):
        """블럭 스텝 시작 UI 표시 — handler 위임."""
        self.block_executor.on_block_step_started(step_id)

    def _on_block_step_done(self, data: dict):
        """블럭 스텝 완료 UI 갱신 — handler 위임."""
        self.block_executor.on_block_step_done(data)

    def _on_kernel_status_changed(self):
        """커널 상태 블럭 뷰 반영 — handler 위임."""
        self.block_executor.on_kernel_status_changed()

    def _refresh_block_view(self):
        """현재 세션의 블럭 뷰를 갱신합니다."""
        if not self.current_session or not self.current_session.steps:
            self.code_viewer.refresh_block_view("", [])
            return

        library_code = extract_library_block(self.current_session)
        initial_code = extract_initial_block(self.current_session)
        steps_data = []
        prev_step_dict: dict | None = None
        for step in self.current_session.steps:
            step_dict = step if isinstance(step, dict) else {}
            step_id = step_dict.get("step_id", 0)
            # 스텝 제목: 대화 내역 첫 번째 user 메시지 요약
            conv = step_dict.get("conversation", [])
            title = ""
            for msg in conv:
                if isinstance(msg, dict) and msg.get("role") == "user":
                    title = str(msg.get("content", ""))[:40]
                    break
            if not title:
                title = f"Step {step_id}"

            # prev_step 전달 — 저장된 step_code 가 누적이라도 generated_code diff 로 재계산
            delta_code = extract_step_delta_code(step_dict, prev_step_dict)
            steps_data.append(
                {
                    "step_id": step_id,
                    "title": title,
                    "delta_code": delta_code,
                    "status": "",
                    "wait_after_ms": step_dict.get("wait_after_ms"),
                }
            )
            prev_step_dict = step_dict

        # Effective default: 세션 default 가 있으면 그 값, 없으면 글로벌 settings.
        # 카드의 "default Nms" 표시 + workflow_engine 의 fallback 모두 사용.
        global_default = self.settings.get("execution", {}).get("step_delay_ms", 500)
        session_default = self.current_session.settings.get("step_delay_ms")
        effective_default = session_default if session_default is not None else global_default
        self.code_viewer.refresh_block_view(
            library_code, steps_data, initial_code, effective_default
        )
        # 세션 wait SpinBox 도 갱신 (signal 무한루프 방지 위해 blockSignals)
        if hasattr(self.code_viewer, "block_view") and hasattr(
            self.code_viewer.block_view, "set_session_wait"
        ):
            self.code_viewer.block_view.set_session_wait(session_default)
        self._on_kernel_status_changed()

    def _stop_session_kernels(self):
        """현재 세션의 커널을 정지합니다 (세션 전환 시 호출) — handler 위임."""
        self.block_executor.stop_session_kernels()

    def _get_valid_python_exe(self) -> str:
        """유효한 Python 실행 경로 반환 — handler 위임."""
        return self.block_executor.get_valid_python_exe()

    def _on_stop_code(self):
        """코드 실행 강제 중지 (F9 단축키 또는 중지 버튼) — handler 위임."""
        self.block_executor.on_stop_code()

    def _run_all_steps(self):
        """전체 스텝 실행"""
        if not self.current_session or not self.current_session.steps:
            QMessageBox.information(self, "안내", "실행할 스텝이 없습니다.")
            return
        self.console_panel.log("전체 워크플로우 실행은 아직 구현 중입니다.", "WARNING")

    # ──────────────────────────────────────────
    # 설정
    # ──────────────────────────────────────────

    def _open_settings(self):
        """설정 다이얼로그 열기"""
        dialog = SettingsDialog(self.settings, self.prompts_config, self)
        if dialog.exec():
            self.settings = dialog.get_settings()
            self._save_settings()
            self._apply_theme()
            self._refresh_ai_combo()
            # 런타임 엔진에 즉시 반영
            self.workflow_engine.visual_feedback_enabled = self.settings.get(
                "visual_feedback", {}
            ).get("enabled", True)
            # 요소 picker 의 UIA walk 파라미터 즉시 반영
            self.element_picker.update_settings(self.settings)
            self.console_panel.log("설정이 변경되었습니다.", "INFO")

    def _show_about(self):
        """소개 다이얼로그"""
        QMessageBox.about(
            self,
            "AI RPA Solution",
            "<h2>AI RPA Solution v2.0</h2>"
            "<p>AI와 대화하면서 Python RPA 자동화 코드를"
            " 단계별로 생성·실행하는 솔루션입니다.</p>"
            "<p><b>기술 스택:</b> PyQt6, Gemini CLI, PyAutoGUI, Selenium</p>"
            "<hr>"
            "<p>© 2025 AI RPA Solution</p>",
        )

    # ──────────────────────────────────────────
    # 윈도우 이벤트
    # ──────────────────────────────────────────

    def closeEvent(self, event):
        """윈도우 닫기 시: 세션 자동 저장 + 모든 커널 정리.

        이전에 두 번 정의되어 첫 번째 (커널 정리) 가 두 번째 (세션 저장) 에
        덮어쓰여 커널이 정리 안 되는 buggy 동작이었음. 통합하여 둘 다 수행.
        """
        # 1. 현재 세션 저장
        if self.current_session:
            try:
                self.session_manager.save_session(self.current_session)
            except Exception as e:
                logger.warning(f"세션 저장 실패: {e}")
        # 2. 모든 ExecutionKernel 정리 (좀비 프로세스 방지)
        for kernel in list(self._kernels.values()):
            try:
                kernel.stop()
            except Exception:
                pass
        self._kernels.clear()
        # 3. event accept (super().closeEvent 도 호출)
        super().closeEvent(event)
        event.accept()

    def showEvent(self, event):
        """윈도우 표시 시 세션 목록 로드"""
        super().showEvent(event)
        self._refresh_session_list()
