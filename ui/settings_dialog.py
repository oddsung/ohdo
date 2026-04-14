"""
설정 다이얼로그

AI 엔진 선택, 이미지 품질, 프롬프트 편집, 환경 설정 등을 관리합니다.
"""

import json
import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QLabel, QComboBox, QSlider, QSpinBox,
    QTextEdit, QCheckBox, QPushButton, QGroupBox,
    QFormLayout, QLineEdit, QFileDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor


class SettingsDialog(QDialog):
    """환경 설정 다이얼로그"""

    def __init__(self, settings: dict, prompts: dict, parent=None):
        super().__init__(parent)
        self.settings = json.loads(json.dumps(settings))  # 딥 카피
        self.prompts = json.loads(json.dumps(prompts))

        self.setWindowTitle("⚙️ 환경 설정")
        self.setMinimumSize(600, 500)
        self.resize(700, 550)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 탭 위젯
        tabs = QTabWidget()

        # 1. AI 설정 탭
        tabs.addTab(self._create_ai_tab(), "🤖 AI 엔진")

        # 2. 이미지 설정 탭
        tabs.addTab(self._create_image_tab(), "📷 이미지")

        # 3. 실행 설정 탭
        tabs.addTab(self._create_execution_tab(), "▶ 실행")

        # 4. 프롬프트 편집 탭
        tabs.addTab(self._create_prompt_tab(), "💬 프롬프트")

        # 5. UI 설정 탭
        tabs.addTab(self._create_ui_tab(), "🎨 UI")

        # 6. 환경 설정 탭
        tabs.addTab(self._create_environment_tab(), "🔧 환경")

        layout.addWidget(tabs)

        # 하단 버튼
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("적용")
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                font-weight: bold;
                padding: 8px 24px;
                border-radius: 4px;
            }
        """)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

    def _create_ai_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)

        # AI 엔진 선택
        self.ai_combo = QComboBox()
        engines = self.settings.get("ai", {}).get("available_engines", {})
        current = self.settings.get("ai", {}).get("selected", "gemini_cli")
        for name in engines:
            self.ai_combo.addItem(name)
        self.ai_combo.setCurrentText(current)
        form.addRow("AI 엔진:", self.ai_combo)

        # 타임아웃 (AI 응답 대기 시간)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(30, 600)  # 30초 ~ 10분
        self.timeout_spin.setSuffix(" 초")
        self.timeout_spin.setToolTip("AI 응답 대기 최대 시간 (권장: 180초)")
        gemini_config = engines.get("gemini_cli", {})
        self.timeout_spin.setValue(gemini_config.get("timeout_seconds", 180))
        form.addRow("응답 타임아웃:", self.timeout_spin)

        # 재시도 횟수
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(gemini_config.get("max_retries", 3))
        form.addRow("최대 재시도:", self.retry_spin)

        return widget

    def _create_image_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)

        img_config = self.settings.get("image", {})

        # 이미지 품질
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(10, 100)
        self.quality_slider.setValue(img_config.get("capture_quality", 60))

        self.quality_label = QLabel(f"{self.quality_slider.value()}%")
        self.quality_slider.valueChanged.connect(
            lambda v: self.quality_label.setText(f"{v}%")
        )

        quality_layout = QHBoxLayout()
        quality_layout.addWidget(self.quality_slider)
        quality_layout.addWidget(self.quality_label)
        form.addRow("캡처 품질:", quality_layout)

        # 최대 해상도
        self.max_width_spin = QSpinBox()
        self.max_width_spin.setRange(640, 3840)
        self.max_width_spin.setSuffix(" px")
        self.max_width_spin.setValue(img_config.get("max_width", 1280))
        form.addRow("최대 가로 해상도:", self.max_width_spin)

        # 흑백 변환
        self.grayscale_cb = QCheckBox("AI 전송 시 흑백 변환 (토큰 절약)")
        self.grayscale_cb.setChecked(img_config.get("grayscale_for_ai", False))
        form.addRow(self.grayscale_cb)

        return widget

    def _create_execution_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)

        exec_config = self.settings.get("execution", {})
        vf_config   = self.settings.get("visual_feedback", {})

        # 스텝 딜레이
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 5000)
        self.delay_spin.setSuffix(" ms")
        self.delay_spin.setValue(exec_config.get("step_delay_ms", 500))
        form.addRow("스텝 간 대기:", self.delay_spin)

        # 에러 시 스크린샷
        self.error_screenshot_cb = QCheckBox("에러 발생 시 자동 스크린샷")
        self.error_screenshot_cb.setChecked(exec_config.get("screenshot_on_error", True))
        form.addRow(self.error_screenshot_cb)

        # 샌드박스 모드
        self.sandbox_cb = QCheckBox("샌드박스 모드 (별도 프로세스 실행)")
        self.sandbox_cb.setChecked(exec_config.get("sandbox_mode", True))
        form.addRow(self.sandbox_cb)

        # 비주얼 피드백 오버레이
        self.visual_feedback_cb = QCheckBox(
            "실행 중 시각 피드백 표시 (마우스 클릭 리플 · 좌표 · 키 입력)"
        )
        self.visual_feedback_cb.setChecked(vf_config.get("enabled", True))
        self.visual_feedback_cb.setToolTip(
            "자동화 코드 실행 중 화면 위에 투명 오버레이를 띄워\n"
            "마우스가 어디를 클릭하는지, 어떤 키를 입력하는지 확인할 수 있습니다.\n"
            "DBeaver 등 클릭이 제대로 되지 않는 경우 디버깅에 유용합니다."
        )
        form.addRow(self.visual_feedback_cb)

        return widget

    def _create_prompt_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        label = QLabel("시스템 프롬프트 (AI에게 전달되는 기본 지시문)")
        label.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        layout.addWidget(label)

        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setFont(QFont("Consolas", 10))
        self.system_prompt_edit.setText(self.prompts.get("system_context", ""))
        self.system_prompt_edit.setStyleSheet("""
            QTextEdit {
                background-color: #11111b;
                color: #cdd6f4;
                border: 1px solid #313244;
            }
        """)
        layout.addWidget(self.system_prompt_edit)

        return widget

    def _create_ui_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)

        ui_config = self.settings.get("ui", {})

        # 테마
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        self.theme_combo.setCurrentText(ui_config.get("theme", "dark"))
        form.addRow("테마:", self.theme_combo)

        # 폰트 크기
        self.fontsize_spin = QSpinBox()
        self.fontsize_spin.setRange(8, 20)
        self.fontsize_spin.setSuffix(" px")
        self.fontsize_spin.setValue(ui_config.get("font_size", 11))
        form.addRow("폰트 크기:", self.fontsize_spin)

        # 콘솔 표시
        self.console_cb = QCheckBox("콘솔 패널 표시")
        self.console_cb.setChecked(ui_config.get("console_visible", True))
        form.addRow(self.console_cb)

        return widget

    def _create_environment_tab(self) -> QWidget:
        """환경 설정 탭"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 현재 환경 정보
        env_group = QGroupBox("📋 현재 환경")
        env_layout = QFormLayout(env_group)

        # 환경 정보 로드
        env_info = self._load_environment_info()

        self.env_python_label = QLabel(env_info.get('python_path', sys.executable))
        self.env_python_label.setWordWrap(True)
        self.env_python_label.setStyleSheet("color: #89b4fa;")
        env_layout.addRow("Python 경로:", self.env_python_label)

        self.env_version_label = QLabel(env_info.get('python_version', 'N/A'))
        env_layout.addRow("Python 버전:", self.env_version_label)

        self.env_hostname_label = QLabel(env_info.get('hostname', 'N/A'))
        env_layout.addRow("컴퓨터 이름:", self.env_hostname_label)

        self.env_scan_label = QLabel(env_info.get('last_scan', 'N/A'))
        env_layout.addRow("마지막 스캔:", self.env_scan_label)

        layout.addWidget(env_group)

        # 패키지 상태
        pkg_group = QGroupBox("📦 패키지 상태")
        pkg_layout = QVBoxLayout(pkg_group)

        self.env_pkg_table = QTableWidget()
        self.env_pkg_table.setColumnCount(3)
        self.env_pkg_table.setHorizontalHeaderLabels(["패키지", "상태", "버전"])
        self.env_pkg_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.env_pkg_table.setMaximumHeight(150)

        # 패키지 정보 표시
        packages = env_info.get('packages', {}).get('required', [])
        self.env_pkg_table.setRowCount(len(packages))

        for row, pkg in enumerate(packages):
            name_item = QTableWidgetItem(pkg.get('package', ''))
            self.env_pkg_table.setItem(row, 0, name_item)

            installed = pkg.get('installed', False)
            status_item = QTableWidgetItem("✅" if installed else "❌")
            status_item.setForeground(QColor("#a6e3a1" if installed else "#f38ba8"))
            self.env_pkg_table.setItem(row, 1, status_item)

            version_item = QTableWidgetItem(pkg.get('version', '-') or '-')
            self.env_pkg_table.setItem(row, 2, version_item)

        pkg_layout.addWidget(self.env_pkg_table)
        layout.addWidget(pkg_group)

        # 작업 버튼
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        rescan_btn = QPushButton("🔄 환경 재스캔")
        rescan_btn.setToolTip("시스템 환경을 다시 스캔합니다")
        rescan_btn.clicked.connect(self._rescan_environment)
        btn_layout.addWidget(rescan_btn)

        change_python_btn = QPushButton("🐍 Python 경로 변경")
        change_python_btn.setToolTip("다른 Python 경로를 선택합니다")
        change_python_btn.clicked.connect(self._change_python_path)
        btn_layout.addWidget(change_python_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

        return widget

    def _load_environment_info(self) -> dict:
        """저장된 환경 정보 로드"""
        try:
            from core.environment_scanner import get_scanner
            scanner = get_scanner()
            env = scanner.load_saved_environment()
            return env if env else {}
        except Exception:
            return {}

    def _rescan_environment(self):
        """환경 재스캔"""
        try:
            from ui.environment_setup_dialog import EnvironmentSetupDialog

            dialog = EnvironmentSetupDialog(self, force_scan=True)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                # 탭 새로고침
                env_info = self._load_environment_info()
                self.env_python_label.setText(env_info.get('python_path', 'N/A'))
                self.env_version_label.setText(env_info.get('python_version', 'N/A'))
                self.env_hostname_label.setText(env_info.get('hostname', 'N/A'))
                self.env_scan_label.setText(env_info.get('last_scan', 'N/A'))

                QMessageBox.information(self, "완료", "환경 스캔이 완료되었습니다.")

        except Exception as e:
            QMessageBox.warning(self, "오류", f"환경 스캔 중 오류 발생:\n{e}")

    def _change_python_path(self):
        """Python 경로 변경"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Python 실행 파일 선택",
            "",
            "Python (python.exe);;모든 파일 (*.*)"
        )

        if path:
            if not os.path.exists(path):
                QMessageBox.warning(self, "경고", "파일을 찾을 수 없습니다.")
                return

            try:
                from core.environment_scanner import get_scanner

                scanner = get_scanner()
                result = scanner.full_scan(path)

                if result.get('success'):
                    scanner.save_environment(result)
                    self.env_python_label.setText(path)
                    self.env_version_label.setText(result.get('python_version', 'N/A'))

                    QMessageBox.information(
                        self,
                        "완료",
                        f"Python 경로가 변경되었습니다.\n{path}"
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "오류",
                        result.get('error', '알 수 없는 오류')
                    )

            except Exception as e:
                QMessageBox.warning(self, "오류", f"Python 경로 변경 중 오류:\n{e}")

    def get_settings(self) -> dict:
        """현재 설정값을 딕셔너리로 반환"""
        # AI
        self.settings["ai"]["selected"] = self.ai_combo.currentText()
        gemini = self.settings["ai"]["available_engines"].get("gemini_cli", {})
        gemini["timeout_seconds"] = self.timeout_spin.value()
        gemini["max_retries"] = self.retry_spin.value()

        # 이미지
        self.settings["image"]["capture_quality"] = self.quality_slider.value()
        self.settings["image"]["max_width"] = self.max_width_spin.value()
        self.settings["image"]["grayscale_for_ai"] = self.grayscale_cb.isChecked()

        # 실행
        self.settings["execution"]["step_delay_ms"] = self.delay_spin.value()
        self.settings["execution"]["screenshot_on_error"] = self.error_screenshot_cb.isChecked()
        self.settings["execution"]["sandbox_mode"] = self.sandbox_cb.isChecked()

        # 비주얼 피드백
        if "visual_feedback" not in self.settings:
            self.settings["visual_feedback"] = {}
        self.settings["visual_feedback"]["enabled"] = self.visual_feedback_cb.isChecked()

        # UI
        self.settings["ui"]["theme"] = self.theme_combo.currentText()
        self.settings["ui"]["font_size"] = self.fontsize_spin.value()
        self.settings["ui"]["console_visible"] = self.console_cb.isChecked()

        return self.settings

    def get_prompts(self) -> dict:
        """프롬프트 설정 반환"""
        self.prompts["system_context"] = self.system_prompt_edit.toPlainText()
        return self.prompts
