"""
환경 설정 다이얼로그

초기 실행 시 또는 환경 재설정 시 시스템 환경을 스캔하고 설정합니다.
"""

import sys
from pathlib import Path
from typing import Optional, Dict, List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QComboBox, QGroupBox, QFormLayout,
    QWidget, QStackedWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor


class ScanWorker(QThread):
    """백그라운드 환경 스캔 워커"""

    progress = Signal(str, int)  # message, percentage
    finished = Signal(dict)  # scan result
    error = Signal(str)

    def __init__(self, python_path: Optional[str] = None):
        super().__init__()
        self.python_path = python_path

    def run(self):
        try:
            from core.environment_scanner import get_scanner

            scanner = get_scanner()

            self.progress.emit("시스템 정보 수집 중...", 10)
            self.msleep(200)

            self.progress.emit("Python 경로 탐색 중...", 30)
            self.msleep(200)

            self.progress.emit("패키지 상태 확인 중...", 50)
            result = scanner.full_scan(self.python_path)

            self.progress.emit("스캔 완료!", 100)
            self.finished.emit(result)

        except Exception as e:
            self.error.emit(str(e))


class EnvironmentSetupDialog(QDialog):
    """환경 설정 다이얼로그"""

    def __init__(self, parent=None, force_scan: bool = False):
        super().__init__(parent)
        self.force_scan = force_scan
        self.scan_result: Optional[Dict] = None
        self.selected_python: Optional[str] = None

        self.setWindowTitle("🔧 환경 설정")
        self.setMinimumSize(700, 550)
        self.resize(800, 600)
        self.setModal(True)

        self._setup_ui()
        self._check_existing_environment()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # 헤더
        header = QLabel("AI RPA Solution - 환경 설정")
        header.setFont(QFont("Malgun Gothic", 16, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        # 스택 위젯 (여러 페이지)
        self.stack = QStackedWidget()

        # 페이지 1: 로딩/스캔 중
        self.stack.addWidget(self._create_scanning_page())

        # 페이지 2: 스캔 결과
        self.stack.addWidget(self._create_result_page())

        # 페이지 3: 수동 설정
        self.stack.addWidget(self._create_manual_page())

        layout.addWidget(self.stack)

        # 하단 버튼
        self.btn_layout = QHBoxLayout()

        self.skip_btn = QPushButton("건너뛰기")
        self.skip_btn.clicked.connect(self.reject)
        self.skip_btn.setVisible(False)
        self.btn_layout.addWidget(self.skip_btn)

        self.btn_layout.addStretch()

        self.rescan_btn = QPushButton("🔄 재스캔")
        # QPushButton.clicked 는 bool(checked) 를 emit 하므로 lambda 로 인자를 흡수.
        # 직접 _start_scan 에 connect 하면 python_path=False 로 호출되어 subprocess
        # 가 TypeError("expected str ... not bool") 를 던진다.
        self.rescan_btn.clicked.connect(lambda: self._start_scan())
        self.rescan_btn.setVisible(False)
        self.btn_layout.addWidget(self.rescan_btn)

        self.manual_btn = QPushButton("⚙️ 수동 설정")
        self.manual_btn.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        self.manual_btn.setVisible(False)
        self.btn_layout.addWidget(self.manual_btn)

        self.apply_btn = QPushButton("✅ 적용 및 시작")
        self.apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #a6e3a1;
                color: #1e1e2e;
                font-weight: bold;
                padding: 10px 24px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #94e2d5;
            }
        """)
        self.apply_btn.clicked.connect(self._apply_and_close)
        self.apply_btn.setVisible(False)
        self.btn_layout.addWidget(self.apply_btn)

        layout.addLayout(self.btn_layout)

    def _create_scanning_page(self) -> QWidget:
        """스캔 중 페이지"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("🔍")
        icon.setFont(QFont("Segoe UI Emoji", 48))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        self.scan_status = QLabel("환경 스캔 준비 중...")
        self.scan_status.setFont(QFont("Malgun Gothic", 12))
        self.scan_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.scan_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFixedWidth(400)
        layout.addWidget(self.progress_bar, alignment=Qt.AlignmentFlag.AlignCenter)

        return page

    def _create_result_page(self) -> QWidget:
        """스캔 결과 페이지"""
        page = QWidget()
        layout = QVBoxLayout(page)

        # 시스템 정보
        sys_group = QGroupBox("📋 시스템 정보")
        sys_layout = QFormLayout(sys_group)
        self.sys_os_label = QLabel()
        self.sys_hostname_label = QLabel()
        self.sys_python_label = QLabel()
        sys_layout.addRow("운영체제:", self.sys_os_label)
        sys_layout.addRow("컴퓨터 이름:", self.sys_hostname_label)
        sys_layout.addRow("Python 버전:", self.sys_python_label)
        layout.addWidget(sys_group)

        # Python 경로 선택
        python_group = QGroupBox("🐍 Python 경로")
        python_layout = QVBoxLayout(python_group)

        self.python_combo = QComboBox()
        self.python_combo.setMinimumHeight(30)
        python_layout.addWidget(self.python_combo)

        browse_layout = QHBoxLayout()
        browse_layout.addStretch()
        browse_btn = QPushButton("📁 경로 찾기...")
        browse_btn.clicked.connect(self._browse_python)
        browse_layout.addWidget(browse_btn)
        python_layout.addLayout(browse_layout)

        layout.addWidget(python_group)

        # 패키지 상태
        pkg_group = QGroupBox("📦 패키지 상태")
        pkg_layout = QVBoxLayout(pkg_group)

        self.pkg_table = QTableWidget()
        self.pkg_table.setColumnCount(4)
        self.pkg_table.setHorizontalHeaderLabels(["패키지", "상태", "버전", "필수"])
        self.pkg_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pkg_table.setAlternatingRowColors(True)
        pkg_layout.addWidget(self.pkg_table)

        # 설치 버튼
        install_layout = QHBoxLayout()
        install_layout.addStretch()
        self.install_btn = QPushButton("📥 누락 패키지 설치")
        self.install_btn.clicked.connect(self._install_missing)
        self.install_btn.setVisible(False)
        install_layout.addWidget(self.install_btn)
        pkg_layout.addLayout(install_layout)

        layout.addWidget(pkg_group)

        # Gemini CLI 상태 (F.2)
        gemini_group = QGroupBox("🤖 Gemini CLI (AI 채팅에 필수)")
        gemini_layout = QFormLayout(gemini_group)
        self.gemini_status_label = QLabel("검사 중...")
        self.gemini_path_label = QLabel("-")
        self.gemini_version_label = QLabel("-")
        self.gemini_detail_label = QLabel("")
        self.gemini_detail_label.setWordWrap(True)
        self.gemini_detail_label.setStyleSheet("color: #f9e2af;")
        gemini_layout.addRow("상태:", self.gemini_status_label)
        gemini_layout.addRow("경로:", self.gemini_path_label)
        gemini_layout.addRow("버전:", self.gemini_version_label)
        gemini_layout.addRow("", self.gemini_detail_label)
        layout.addWidget(gemini_group)

        return page

    def _create_manual_page(self) -> QWidget:
        """수동 설정 페이지"""
        page = QWidget()
        layout = QVBoxLayout(page)

        info = QLabel(
            "Python 경로를 직접 입력하거나 찾아보기 버튼을 사용하세요.\n"
            "가상 환경(venv)의 python.exe 경로를 권장합니다."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # 경로 입력
        path_group = QGroupBox("Python 경로")
        path_layout = QHBoxLayout(path_group)

        self.manual_path_edit = QComboBox()
        self.manual_path_edit.setEditable(True)
        self.manual_path_edit.setMinimumHeight(30)
        path_layout.addWidget(self.manual_path_edit)

        browse_btn = QPushButton("📁")
        browse_btn.clicked.connect(self._browse_python_manual)
        path_layout.addWidget(browse_btn)

        layout.addWidget(path_group)

        # 검증 버튼
        verify_layout = QHBoxLayout()
        verify_layout.addStretch()

        back_btn = QPushButton("◀ 뒤로")
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        verify_layout.addWidget(back_btn)

        verify_btn = QPushButton("✅ 검증 및 적용")
        verify_btn.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                font-weight: bold;
                padding: 8px 16px;
            }
        """)
        verify_btn.clicked.connect(self._verify_manual_path)
        verify_layout.addWidget(verify_btn)

        layout.addLayout(verify_layout)
        layout.addStretch()

        return page

    def _check_existing_environment(self):
        """기존 환경 설정 확인"""
        if self.force_scan:
            self._start_scan()
            return

        try:
            from core.environment_scanner import get_scanner

            scanner = get_scanner()
            saved_env = scanner.load_saved_environment()

            if saved_env:
                is_valid, message = scanner.is_environment_valid(saved_env)

                if is_valid:
                    # 유효한 환경 - 바로 적용
                    self.scan_result = saved_env
                    self.selected_python = saved_env.get('python_path')

                    # 저장된 환경 사용 확인
                    QTimer.singleShot(100, lambda: self._show_cached_result(saved_env))
                    return

            # 새 스캔 필요
            self._start_scan()

        except Exception as e:
            self._start_scan()

    def _show_cached_result(self, env_data: Dict):
        """캐시된 환경 결과 표시"""
        self.scan_result = env_data
        self._display_result(env_data)

        # F.2: 캐시에 Gemini 정보가 없거나 미설치면 자동 적용을 보류 (재검사 권장).
        gemini_cached = env_data.get('gemini_cli') or {}
        cache_complete = bool(gemini_cached) and bool(gemini_cached.get('installed'))

        if not cache_complete:
            # 캐시가 오래되어 Gemini 정보가 없거나 미설치 → 라이브 재스캔 추천
            self._show_buttons()
            QMessageBox.information(
                self, "환경 재검사 필요",
                "저장된 환경에 Gemini CLI 정보가 누락되었거나 미설치 상태입니다.\n"
                "'재스캔' 버튼으로 최신 상태를 확인하세요.",
            )
            return

        # 자동 적용 옵션
        reply = QMessageBox.question(
            self,
            "환경 확인",
            f"저장된 환경 설정을 발견했습니다.\n\n"
            f"Python: {env_data.get('python_path', 'N/A')}\n"
            f"버전: {env_data.get('python_version', 'N/A')}\n\n"
            f"이 설정을 사용하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.accept()
        else:
            self._show_buttons()

    def _start_scan(self, python_path: Optional[str] = None):
        """환경 스캔 시작"""
        # 방어: 시그널 잘못 연결 등으로 bool/non-str 가 들어와도 None 으로 정규화
        if not isinstance(python_path, str):
            python_path = None

        self.stack.setCurrentIndex(0)
        self.progress_bar.setValue(0)
        self.scan_status.setText("환경 스캔 시작...")

        self._hide_buttons()

        self.scan_worker = ScanWorker(python_path)
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.error.connect(self._on_scan_error)
        self.scan_worker.start()

    def _on_scan_progress(self, message: str, percentage: int):
        """스캔 진행 상태 업데이트"""
        self.scan_status.setText(message)
        self.progress_bar.setValue(percentage)

    def _on_scan_finished(self, result: Dict):
        """스캔 완료"""
        self.scan_result = result

        if result.get('success'):
            self._display_result(result)
        else:
            QMessageBox.warning(
                self,
                "스캔 실패",
                result.get('error', '알 수 없는 오류가 발생했습니다.')
            )
            self.stack.setCurrentIndex(2)  # 수동 설정 페이지

        self._show_buttons()

    def _on_scan_error(self, error: str):
        """스캔 오류"""
        QMessageBox.critical(self, "오류", f"환경 스캔 중 오류 발생:\n{error}")
        self.stack.setCurrentIndex(2)
        self._show_buttons()

    def _display_result(self, result: Dict):
        """스캔 결과 표시"""
        self.stack.setCurrentIndex(1)

        # 시스템 정보
        sys_info = result.get('system_info', {})
        self.sys_os_label.setText(f"{sys_info.get('os', '')} {sys_info.get('os_release', '')}")
        self.sys_hostname_label.setText(sys_info.get('hostname', 'N/A'))
        self.sys_python_label.setText(result.get('python_version', 'N/A'))

        # Python 경로 목록
        self.python_combo.clear()
        available = result.get('available_pythons', [])

        for py in available:
            path = py.get('path', '')
            version = py.get('version', 'unknown')
            is_current = py.get('is_current', False)
            is_venv = py.get('is_venv', False)

            suffix = ""
            if is_current:
                suffix = " (현재)"
            elif is_venv:
                suffix = " (가상환경)"

            self.python_combo.addItem(f"{path} [v{version}]{suffix}", path)

        # 현재 사용 중인 Python 선택
        current_path = result.get('python_path', sys.executable)
        for i in range(self.python_combo.count()):
            if self.python_combo.itemData(i) == current_path:
                self.python_combo.setCurrentIndex(i)
                break

        self.selected_python = current_path

        # 패키지 상태
        packages = result.get('packages', {})
        required = packages.get('required', [])
        optional = packages.get('optional', [])

        self.pkg_table.setRowCount(len(required) + len(optional))

        row = 0
        has_missing = False

        for pkg in required:
            self._add_package_row(row, pkg, is_required=True)
            if not pkg.get('installed'):
                has_missing = True
            row += 1

        for pkg in optional:
            self._add_package_row(row, pkg, is_required=False)
            row += 1

        self.install_btn.setVisible(has_missing)

        # Gemini CLI 상태 표시 (F.2)
        self._display_gemini(result.get('gemini_cli') or {})

        # Apply 버튼 게이트 갱신
        self._update_apply_gate(result)

    def _display_gemini(self, gemini: Dict):
        """Gemini CLI 상태 패널 갱신"""
        installed = bool(gemini.get('installed'))
        path = gemini.get('path')
        version = gemini.get('version')
        error = gemini.get('error')
        detail = gemini.get('detail') or ""

        if installed:
            self.gemini_status_label.setText("✅ 설치됨")
            self.gemini_status_label.setStyleSheet("color: #a6e3a1; font-weight: bold;")
            self.gemini_detail_label.setText("")
        else:
            err_label = {
                'not_found': "❌ 미설치 (PATH 에 없음)",
                'timeout': "⚠️ 응답 시간 초과",
                'execution_error': "⚠️ 실행 오류",
                'non_zero_exit': "⚠️ 비정상 종료",
            }.get(error, "❌ 사용 불가")
            self.gemini_status_label.setText(err_label)
            self.gemini_status_label.setStyleSheet("color: #f38ba8; font-weight: bold;")
            # 미설치는 가장 흔한 경로 — 추가 안내 1줄
            if error == 'not_found':
                detail = (detail + "\n'gemini' 명령이 PATH 에서 동작해야 AI 채팅이 가능합니다. "
                          "설치 후 '재스캔' 을 눌러주세요.").strip()
            self.gemini_detail_label.setText(detail)

        self.gemini_path_label.setText(path or "-")
        self.gemini_version_label.setText(version or "-")

    def _update_apply_gate(self, result: Dict):
        """Apply 버튼 활성/비활성 + tooltip 사유 갱신.

        활성 조건:
            1) 필수 패키지 모두 설치됨
            2) Gemini CLI installed=True
        둘 다 만족하지 못하면 비활성, tooltip 으로 사유 노출.
        """
        packages = result.get('packages') or {}
        all_required = bool(packages.get('all_required_installed'))
        gemini_ok = bool((result.get('gemini_cli') or {}).get('installed'))

        reasons = []
        if not all_required:
            reasons.append("필수 패키지가 일부 누락되었습니다")
        if not gemini_ok:
            reasons.append("Gemini CLI 가 설치되지 않았습니다")

        if reasons:
            self.apply_btn.setEnabled(False)
            self.apply_btn.setToolTip("적용 불가: " + " / ".join(reasons))
        else:
            self.apply_btn.setEnabled(True)
            self.apply_btn.setToolTip("")

    def _add_package_row(self, row: int, pkg: Dict, is_required: bool):
        """패키지 테이블 행 추가"""
        name_item = QTableWidgetItem(pkg.get('package', ''))
        self.pkg_table.setItem(row, 0, name_item)

        installed = pkg.get('installed', False)
        status_item = QTableWidgetItem("✅ 설치됨" if installed else "❌ 미설치")
        status_item.setForeground(QColor("#a6e3a1" if installed else "#f38ba8"))
        self.pkg_table.setItem(row, 1, status_item)

        version_item = QTableWidgetItem(pkg.get('version', '-') or '-')
        self.pkg_table.setItem(row, 2, version_item)

        req_item = QTableWidgetItem("필수" if is_required else "선택")
        req_item.setForeground(QColor("#f9e2af" if is_required else "#6c7086"))
        self.pkg_table.setItem(row, 3, req_item)

    def _browse_python(self):
        """Python 경로 찾기"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Python 실행 파일 선택",
            "",
            "Python (python.exe);;모든 파일 (*.*)"
        )

        if path:
            # 콤보박스에 추가하고 선택
            self.python_combo.addItem(f"{path} [사용자 지정]", path)
            self.python_combo.setCurrentIndex(self.python_combo.count() - 1)
            self.selected_python = path

    def _browse_python_manual(self):
        """수동 설정에서 Python 경로 찾기"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Python 실행 파일 선택",
            "",
            "Python (python.exe);;모든 파일 (*.*)"
        )

        if path:
            self.manual_path_edit.setEditText(path)

    def _verify_manual_path(self):
        """수동 입력 경로 검증"""
        path = self.manual_path_edit.currentText().strip()

        if not path:
            QMessageBox.warning(self, "경고", "Python 경로를 입력해주세요.")
            return

        from pathlib import Path as P
        if not P(path).exists():
            QMessageBox.warning(self, "경고", f"파일을 찾을 수 없습니다:\n{path}")
            return

        # 새로 스캔
        self._start_scan(path)

    def _install_missing(self):
        """누락된 패키지 설치"""
        if not self.scan_result:
            return

        packages = self.scan_result.get('packages', {}).get('required', [])
        missing = [p for p in packages if not p.get('installed')]

        if not missing:
            QMessageBox.information(self, "알림", "모든 필수 패키지가 설치되어 있습니다.")
            return

        reply = QMessageBox.question(
            self,
            "패키지 설치",
            f"다음 패키지를 설치하시겠습니까?\n\n" +
            "\n".join([f"• {p['package']}" for p in missing]),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            from core.environment_scanner import get_scanner

            scanner = get_scanner()
            python_path = self.python_combo.currentData() or sys.executable

            for pkg in missing:
                self.scan_status.setText(f"{pkg['package']} 설치 중...")
                success, msg = scanner.install_package(python_path, pkg['package'])

                if not success:
                    QMessageBox.warning(
                        self,
                        "설치 실패",
                        f"{pkg['package']} 설치 실패:\n{msg}"
                    )

            # 재스캔
            self._start_scan(python_path)

    def _hide_buttons(self):
        """버튼 숨기기"""
        self.skip_btn.setVisible(False)
        self.rescan_btn.setVisible(False)
        self.manual_btn.setVisible(False)
        self.apply_btn.setVisible(False)

    def _show_buttons(self):
        """버튼 표시"""
        self.skip_btn.setVisible(True)
        self.rescan_btn.setVisible(True)
        self.manual_btn.setVisible(True)
        self.apply_btn.setVisible(True)

    def _apply_and_close(self):
        """설정 적용 및 닫기"""
        if not self.scan_result:
            QMessageBox.warning(self, "경고", "환경 스캔이 완료되지 않았습니다.")
            return

        # 선택된 Python 경로 업데이트
        if self.stack.currentIndex() == 1:  # 결과 페이지
            self.selected_python = self.python_combo.currentData()
            if self.selected_python:
                self.scan_result['python_path'] = self.selected_python

        # 최종 게이트 (F.2): 어떻게든 비활성이 풀려도 한 번 더 막는다
        packages = self.scan_result.get('packages') or {}
        gemini = self.scan_result.get('gemini_cli') or {}
        if not packages.get('all_required_installed') or not gemini.get('installed'):
            problems = []
            if not packages.get('all_required_installed'):
                problems.append("• 필수 패키지 일부 미설치")
            if not gemini.get('installed'):
                problems.append("• Gemini CLI 미설치 (AI 채팅 불가)")
            reply = QMessageBox.warning(
                self, "환경 미충족",
                "다음 문제가 있습니다:\n\n" + "\n".join(problems) +
                "\n\n그래도 이 설정으로 진행하시겠습니까?\n"
                "(나중에 '재스캔' 으로 다시 검사할 수 있습니다)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # 환경 저장
        from core.environment_scanner import get_scanner

        scanner = get_scanner()
        scanner.save_environment(self.scan_result)

        self.accept()

    def get_python_path(self) -> str:
        """선택된 Python 경로 반환"""
        return self.selected_python or sys.executable

    def get_environment(self) -> Optional[Dict]:
        """스캔된 환경 정보 반환"""
        return self.scan_result
