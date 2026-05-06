"""
설정 다이얼로그

AI 엔진 선택, 이미지 품질, 프롬프트 편집, 환경 설정 등을 관리합니다.
"""

import json
import sys
import os
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QLabel, QComboBox, QSlider, QSpinBox,
    QTextEdit, QCheckBox, QPushButton, QGroupBox,
    QFormLayout, QLineEdit, QFileDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor


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

        # 3-1. 요소 선택 탭
        tabs.addTab(self._create_element_picker_tab(), "🎯 요소 선택")

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

        engines = self.settings.get("ai", {}).get("available_engines", {})
        current = self.settings.get("ai", {}).get("selected", "gemini_cli")

        # AI 엔진 선택
        self.ai_combo = QComboBox()
        for name in engines:
            self.ai_combo.addItem(name)
        self.ai_combo.setCurrentText(current)
        form.addRow("AI 엔진:", self.ai_combo)

        # 타임아웃 (Gemini CLI 전용)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(30, 600)
        self.timeout_spin.setSuffix(" 초")
        self.timeout_spin.setToolTip("AI 응답 대기 최대 시간 (권장: 180초)")
        gemini_config = engines.get("gemini_cli", {})
        self.timeout_spin.setValue(gemini_config.get("timeout_seconds", 180))
        form.addRow("Gemini 응답 타임아웃:", self.timeout_spin)

        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(gemini_config.get("max_retries", 3))
        form.addRow("Gemini 최대 재시도:", self.retry_spin)

        # ── OpenAI 호환 API 설정 ────────────────────────────────────
        # base_url + api_key 만 등록하면 OpenAI / DeepSeek / Groq /
        # OpenRouter / Ollama / LM Studio 등 모두 지원.
        from core.adapters.openai_compat_adapter import PRESETS as _OPENAI_PRESETS
        oc_config = engines.get("openai_compat", {})

        oc_group = QGroupBox("OpenAI 호환 API")
        oc_group.setToolTip(
            "OpenAI Chat Completions API 형식을 지원하는 모든 LLM 서비스용. "
            "base_url + api_key 만 등록하면 됨."
        )
        oc_form = QFormLayout(oc_group)

        # 프리셋 드롭다운 (선택 시 base_url + model 자동 채움)
        self.openai_preset_combo = QComboBox()
        self.openai_preset_combo.addItem("(프리셋 선택...)", "")
        for preset_name in _OPENAI_PRESETS.keys():
            self.openai_preset_combo.addItem(preset_name, preset_name)
        current_preset = oc_config.get("preset", "")
        if current_preset:
            idx = self.openai_preset_combo.findData(current_preset)
            if idx >= 0:
                self.openai_preset_combo.setCurrentIndex(idx)
        self.openai_preset_combo.setToolTip(
            "프리셋 선택 시 base_url 과 model 이 자동으로 채워집니다. "
            "그 후 api_key 만 입력하면 사용 가능."
        )
        self.openai_preset_combo.currentIndexChanged.connect(
            lambda _: self._on_openai_preset_changed(_OPENAI_PRESETS)
        )
        oc_form.addRow("프리셋:", self.openai_preset_combo)

        self.openai_base_url_edit = QLineEdit()
        self.openai_base_url_edit.setPlaceholderText("https://api.openai.com/v1")
        self.openai_base_url_edit.setText(oc_config.get("base_url", ""))
        self.openai_base_url_edit.setToolTip(
            "API 엔드포인트 — '/chat/completions' 앞까지의 경로. "
            "끝의 슬래시는 자동 제거됨."
        )
        oc_form.addRow("base_url:", self.openai_base_url_edit)

        self.openai_api_key_edit = QLineEdit()
        self.openai_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_api_key_edit.setText(oc_config.get("api_key", ""))
        self.openai_api_key_edit.setToolTip(
            "API 키. 비워두면 환경변수 OPENAI_API_KEY 사용. "
            "로컬 Ollama/LM Studio 는 비워둬도 됨.\n"
            "⚠ 현재 settings.json 평문 저장 — keyring 통합은 추후."
        )
        oc_form.addRow("api_key:", self.openai_api_key_edit)

        self.openai_model_edit = QLineEdit()
        self.openai_model_edit.setPlaceholderText("gpt-4o-mini")
        self.openai_model_edit.setText(oc_config.get("model", ""))
        self.openai_model_edit.setToolTip(
            "모델 이름 (서비스마다 다름). 예: gpt-4o-mini, deepseek-chat, "
            "llama-3.3-70b-versatile, llama3.2 (Ollama)."
        )
        oc_form.addRow("model:", self.openai_model_edit)

        self.openai_timeout_spin = QSpinBox()
        self.openai_timeout_spin.setRange(30, 600)
        self.openai_timeout_spin.setSuffix(" 초")
        self.openai_timeout_spin.setValue(oc_config.get("timeout_seconds", 180))
        oc_form.addRow("timeout:", self.openai_timeout_spin)

        self.openai_max_tokens_spin = QSpinBox()
        self.openai_max_tokens_spin.setRange(256, 32768)
        self.openai_max_tokens_spin.setValue(oc_config.get("max_tokens", 4096))
        oc_form.addRow("max_tokens:", self.openai_max_tokens_spin)

        # temperature 는 0.0~2.0 float — QSpinBox 대신 LineEdit 으로 단순화
        self.openai_temperature_edit = QLineEdit()
        self.openai_temperature_edit.setText(str(oc_config.get("temperature", 0.3)))
        self.openai_temperature_edit.setToolTip(
            "0.0 (결정적) ~ 2.0 (매우 random). 코드 생성은 0.3 권장."
        )
        oc_form.addRow("temperature:", self.openai_temperature_edit)

        form.addRow(oc_group)

        return widget

    def _on_openai_preset_changed(self, presets: dict) -> None:
        """프리셋 선택 시 base_url + model 자동 채움."""
        preset_name = self.openai_preset_combo.currentData()
        if not preset_name:
            return
        preset = presets.get(preset_name, {})
        if preset.get("base_url"):
            self.openai_base_url_edit.setText(preset["base_url"])
        if preset.get("model"):
            self.openai_model_edit.setText(preset["model"])

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

    def _create_element_picker_tab(self) -> QWidget:
        """🎯 요소 선택 탭 — UIA 트리 walk 파라미터"""
        widget = QWidget()
        form = QFormLayout(widget)

        ep_config = self.settings.get("element_picker", {})

        # 안내 라벨
        intro = QLabel(
            "요소 선택(picker) 도구가 마우스 아래의 UI 요소를 찾을 때 사용하는 파라미터입니다.\n"
            "값이 클수록 더 깊은 요소(예: 페이지 안의 버튼)까지 잡지만, picker 가 살짝 lag 될 수 있습니다."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #6c7086; padding: 4px 0 12px 0;")
        form.addRow(intro)

        # max_depth
        self.uia_max_depth_spin = QSpinBox()
        self.uia_max_depth_spin.setRange(1, 50)
        self.uia_max_depth_spin.setValue(int(ep_config.get("uia_max_depth", 10)))
        self.uia_max_depth_spin.setSuffix(" 단계")
        self.uia_max_depth_spin.setToolTip(
            "UIA 트리 walk 의 최대 깊이입니다.\n"
            "\n"
            "Picker 는 마우스 아래 요소를 찾기 위해 UI 계층을 따라 들어갑니다.\n"
            "예: 윈도우 → 페이지 → 헤더 → 메뉴 → 버튼 (5단계)\n"
            "\n"
            "  - 작게 (3-5): 큰 영역만 (윈도우/페이지) 잡힘. 빠름.\n"
            "  - 보통 (10): 일반 데스크톱 앱 + 일부 웹페이지 요소까지.\n"
            "  - 크게 (15-25): Chrome 안 깊은 HTML 요소까지. cycle 위험 살짝 있음.\n"
            "\n"
            "권장: 10. 깊은 element 가 안 잡히면 15-20 으로 올려보세요.\n"
            "범위: 1 ~ 50"
        )
        form.addRow("UIA 최대 깊이:", self.uia_max_depth_spin)

        # time_budget_ms
        self.uia_time_budget_spin = QSpinBox()
        self.uia_time_budget_spin.setRange(30, 2000)
        self.uia_time_budget_spin.setValue(int(ep_config.get("uia_time_budget_ms", 150)))
        self.uia_time_budget_spin.setSuffix(" ms")
        self.uia_time_budget_spin.setSingleStep(10)
        self.uia_time_budget_spin.setToolTip(
            "UIA 트리 walk 한 번에 사용할 수 있는 최대 시간 (밀리초).\n"
            "\n"
            "Picker 는 100ms 마다 마우스 아래 요소를 다시 감지합니다.\n"
            "이 시간 내에 walk 가 끝나야 부드럽게 추적되며,\n"
            "넘으면 그 시점까지의 best match 를 반환하고 다음 tick 에 재시도합니다.\n"
            "\n"
            "  - 작게 (50-100ms): 부드러운 추적, 깊은 element 못 찾을 수 있음.\n"
            "  - 보통 (150ms): 일반 앱은 끝까지 가고 Chrome 같은 거대 트리는 부분 매칭.\n"
            "  - 크게 (300-500ms): Chrome 안 깊은 element 까지 정확히, 추적이 약간 lag.\n"
            "\n"
            "권장: 150ms. lag 가 거슬리면 줄이고, 깊이가 부족하면 늘리세요.\n"
            "범위: 30 ~ 2000ms"
        )
        form.addRow("UIA 시간 예산:", self.uia_time_budget_spin)

        # CDP 사용 여부 — Chrome remote-debugging-port 로 DOM context 수집
        self.cdp_enabled_cb = QCheckBox("Chrome CDP 로 DOM 정보 수집 (느릴 수 있음)")
        self.cdp_enabled_cb.setChecked(bool(ep_config.get("cdp_enabled", False)))
        self.cdp_enabled_cb.setToolTip(
            "활성화 시 element 선택 후 Chrome remote-debugging-port (9222) 에\n"
            "접속해 DOM context (XPath, outerHTML, attributes 등) 수집.\n"
            "AI 가 더 정확한 selector 를 만들 수 있지만 click → 메인 화면 전환에\n"
            "수백 ms ~ 1초 추가 지연 (CDP 미연결 시 매번 timeout 대기).\n"
            "\n"
            "Chrome 을 다음 명령으로 띄운 경우만 활성화 권장:\n"
            "  chrome.exe --remote-debugging-port=9222\n"
            "\n"
            "기본: 비활성 (반응성 우선)"
        )
        form.addRow("Chrome CDP:", self.cdp_enabled_cb)

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

        # OpenAI 호환 API
        engines_dict = self.settings["ai"].setdefault("available_engines", {})
        oc = engines_dict.setdefault("openai_compat", {})
        preset_data = self.openai_preset_combo.currentData() or ""
        oc["preset"] = preset_data
        oc["base_url"] = self.openai_base_url_edit.text().strip()
        oc["api_key"] = self.openai_api_key_edit.text()
        oc["model"] = self.openai_model_edit.text().strip()
        oc["timeout_seconds"] = self.openai_timeout_spin.value()
        oc["max_tokens"] = self.openai_max_tokens_spin.value()
        try:
            oc["temperature"] = float(self.openai_temperature_edit.text() or "0.3")
        except ValueError:
            oc["temperature"] = 0.3
        # 환경변수 fallback 유지 (기존 default)
        oc.setdefault("api_key_env", "OPENAI_API_KEY")
        oc.setdefault("max_retries", 3)

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

        # 요소 선택 (UIA 트리 walk)
        if "element_picker" not in self.settings:
            self.settings["element_picker"] = {}
        self.settings["element_picker"]["uia_max_depth"] = self.uia_max_depth_spin.value()
        self.settings["element_picker"]["uia_time_budget_ms"] = self.uia_time_budget_spin.value()
        self.settings["element_picker"]["cdp_enabled"] = self.cdp_enabled_cb.isChecked()

        # UI
        self.settings["ui"]["theme"] = self.theme_combo.currentText()
        self.settings["ui"]["font_size"] = self.fontsize_spin.value()
        self.settings["ui"]["console_visible"] = self.console_cb.isChecked()

        return self.settings

    def get_prompts(self) -> dict:
        """프롬프트 설정 반환"""
        self.prompts["system_context"] = self.system_prompt_edit.toPlainText()
        return self.prompts
