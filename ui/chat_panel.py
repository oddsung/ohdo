"""
대화 패널

사용자와 AI 간의 대화를 표시하고 입력을 받는 패널입니다.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QTextEdit, QPushButton, QLabel, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont


class ElementChip(QFrame):
    """선택된 UI 요소를 나타내는 칩 위젯 — Del/Backspace 또는 ✕ 버튼으로 삭제"""

    remove_requested = pyqtSignal()

    def __init__(self, element_info: dict, parent=None):
        super().__init__(parent)
        ctrl_type = element_info.get("control_type", "?")
        name = element_info.get("name", "")
        display = f"🎯 [{ctrl_type}]"
        if name:
            display += f" {name[:28]}"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(7, 2, 4, 2)
        layout.setSpacing(4)

        label = QLabel(display)
        label.setFont(QFont("Malgun Gothic", 9))
        label.setStyleSheet("color: #cdd6f4;")
        layout.addWidget(label)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(16, 16)
        del_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #6c7086;
                          border: none; font-size: 10px; font-weight: bold; }
            QPushButton:hover { color: #f38ba8; }
        """)
        del_btn.clicked.connect(self.remove_requested.emit)
        layout.addWidget(del_btn)

        self.setFixedHeight(26)
        self.setStyleSheet("""
            ElementChip {
                background-color: #2a2a3d;
                border: 1px solid #89b4fa;
                border-radius: 4px;
            }
        """)


class ChatBubble(QFrame):
    """채팅 말풍선 위젯"""

    def __init__(self, role: str, content: str, parent=None):
        super().__init__(parent)
        self.role = role
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # 역할 라벨
        role_label = QLabel()
        role_label.setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold))

        # 내용 라벨 — QLabel + WordWrap으로 전체 내용이 항상 표시됨
        content_label = QLabel()
        content_label.setText(content)
        content_label.setWordWrap(True)
        content_label.setFont(QFont("Malgun Gothic", 10))
        content_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        content_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        content_label.setMinimumHeight(20)

        if role == "user":
            role_label.setText("👤 You")
            role_label.setStyleSheet("color: #89b4fa;")
            content_label.setStyleSheet("color: #cdd6f4; padding: 2px;")
            self.setStyleSheet("""
                ChatBubble {
                    background-color: #313244;
                    border-radius: 8px;
                    border-left: 3px solid #89b4fa;
                    margin-left: 40px;
                    margin-right: 5px;
                }
            """)
        elif role == "assistant":
            role_label.setText("🤖 AI")
            role_label.setStyleSheet("color: #a6e3a1;")
            content_label.setStyleSheet("color: #cdd6f4; padding: 2px;")
            self.setStyleSheet("""
                ChatBubble {
                    background-color: #1e1e2e;
                    border-radius: 8px;
                    border-left: 3px solid #a6e3a1;
                    margin-left: 5px;
                    margin-right: 40px;
                }
            """)
        else:  # system
            role_label.setText("⚙️ System")
            role_label.setStyleSheet("color: #f9e2af;")
            content_label.setStyleSheet("color: #cdd6f4; padding: 2px;")
            self.setStyleSheet("""
                ChatBubble {
                    background-color: #1e1e2e;
                    border-radius: 8px;
                    border-left: 3px solid #f9e2af;
                    margin: 5px;
                }
            """)

        layout.addWidget(role_label)
        layout.addWidget(content_label)


class ChatPanel(QWidget):
    """대화 패널 위젯"""

    message_sent = pyqtSignal(str)          # 사용자 메시지 전송 시그널
    capture_requested = pyqtSignal()        # 화면 캡처 요청 시그널
    element_pick_requested = pyqtSignal()   # UI 요소 선택 요청 시그널
    cancel_requested = pyqtSignal()         # AI 생성 중지 요청 시그널

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending_elements: list[dict] = []   # element_info 목록
        self._chip_widgets: list[ElementChip] = []
        self._is_generating: bool = False          # AI 생성 중 여부
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # 헤더
        header = QLabel("💬 대화 및 작업 요청")
        header.setFont(QFont("Malgun Gothic", 12, QFont.Weight.Bold))
        header.setStyleSheet("padding: 5px; color: #cdd6f4;")
        layout.addWidget(header)

        # 스크롤 영역 (대화 내용) — 최대 영역 확보
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setMinimumHeight(200)
        self.scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setSpacing(8)
        self.chat_layout.setContentsMargins(4, 4, 4, 4)
        # 상단에 stretch 하나만 유지 → 메시지가 항상 하단에 쌓임
        self.chat_layout.addStretch(1)

        self.scroll_area.setWidget(self.chat_container)
        layout.addWidget(self.scroll_area, stretch=1)  # stretch=1: 남은 공간 모두 차지

        # ── 하단 고정 영역 (캡처 + 입력) ──
        bottom_frame = QWidget()
        bottom_layout = QVBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(2)

        # 캡처 상태 바
        self.capture_frame = QFrame()
        capture_bar = QHBoxLayout(self.capture_frame)
        capture_bar.setContentsMargins(5, 2, 5, 2)

        self.capture_btn = QPushButton("📷 화면 캡처")
        self.capture_btn.setFixedHeight(30)
        self.capture_btn.clicked.connect(self.capture_requested.emit)
        capture_bar.addWidget(self.capture_btn)

        self.element_pick_btn = QPushButton("🎯 요소 선택")
        self.element_pick_btn.setFixedHeight(30)
        self.element_pick_btn.setToolTip("UI 요소를 클릭하여 요소 정보를 AI 컨텍스트로 추가합니다")
        self.element_pick_btn.clicked.connect(self.element_pick_requested.emit)
        capture_bar.addWidget(self.element_pick_btn)

        self.capture_status = QLabel("첨부된 캡처 없음")
        self.capture_status.setStyleSheet("color: #6c7086; font-size: 10px;")
        capture_bar.addWidget(self.capture_status)
        capture_bar.addStretch()

        bottom_layout.addWidget(self.capture_frame)

        # 요소 칩 영역 (선택된 UI 요소 표시, 기본 숨김)
        self.chips_frame = QWidget()
        chips_outer = QHBoxLayout(self.chips_frame)
        chips_outer.setContentsMargins(4, 2, 4, 2)
        chips_outer.setSpacing(4)
        self._chips_layout = chips_outer  # 칩 삽입용
        chips_outer.addStretch()
        self.chips_frame.hide()
        bottom_layout.addWidget(self.chips_frame)

        # 입력 영역
        input_frame = QFrame()
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(0, 0, 0, 0)

        self.input_box = QTextEdit()
        self.input_box.setPlaceholderText("자동화할 작업을 입력하세요... (Enter: 전송, Shift+Enter: 줄바꿈)")
        self.input_box.setMaximumHeight(80)
        self.input_box.setFont(QFont("Malgun Gothic", 10))
        self.input_box.installEventFilter(self)
        input_layout.addWidget(self.input_box)

        self.send_btn = QPushButton("전송 ▶")
        self.send_btn.setFixedSize(80, 70)
        self._send_btn_normal_style = """
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                font-weight: bold;
                font-size: 13px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #74c7ec; }
            QPushButton:disabled { background-color: #45475a; color: #6c7086; }
        """
        self._send_btn_stop_style = """
            QPushButton {
                background-color: #f38ba8;
                color: #1e1e2e;
                font-weight: bold;
                font-size: 13px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #eba0ac; }
        """
        self.send_btn.setStyleSheet(self._send_btn_normal_style)
        self.send_btn.clicked.connect(self._on_send_btn_clicked)
        input_layout.addWidget(self.send_btn)

        bottom_layout.addWidget(input_frame)

        layout.addWidget(bottom_frame, stretch=0)  # stretch=0: 하단 고정


    def eventFilter(self, obj, event):
        """Enter 키로 전송, Shift+Enter는 줄바꿈"""
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent

        if obj == self.input_box and event.type() == QEvent.Type.KeyPress:
            key_event = event
            if (key_event.key() == Qt.Key.Key_Return and
                not key_event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                if not self._is_generating:
                    self._send_message()
                return True
            # 백스페이스로 칩 삭제 기능 제거 - 칩의 X 버튼으로만 삭제 가능
        return super().eventFilter(obj, event)

    def _on_send_btn_clicked(self):
        """전송/중지 버튼 클릭 — 생성 중이면 취소, 아니면 전송"""
        if self._is_generating:
            self.cancel_requested.emit()
        else:
            self._send_message()

    def _send_message(self):
        """메시지 전송"""
        text = self.input_box.toPlainText().strip()
        if not text:
            return

        # 선택된 요소 정보가 있으면 메시지 앞에 추가해서 표시
        display_text = text
        if self._pending_elements:
            summaries = []
            for e in self._pending_elements:
                ctrl_type = e.get("control_type", "")
                name = e.get("name", "")
                auto_id = e.get("automation_id", "")
                if name:
                    summaries.append(f"[{ctrl_type}] \"{name}\"")
                elif auto_id:
                    summaries.append(f"[{ctrl_type}] (ID: {auto_id})")
                else:
                    summaries.append(f"[{ctrl_type}]")
            element_summary = "📌 선택된 요소: " + ", ".join(summaries) + "\n"
            display_text = element_summary + text

        self.add_user_message(display_text)
        self.input_box.clear()
        self.message_sent.emit(text)

    def add_user_message(self, text: str):
        """사용자 메시지 추가"""
        self._add_bubble("user", text)

    def add_ai_message(self, text: str):
        """AI 메시지 추가"""
        self._add_bubble("assistant", text)

    def add_system_message(self, text: str):
        """시스템 메시지 추가"""
        self._add_bubble("system", text)

    def _add_bubble(self, role: str, content: str):
        """말풍선 추가 — 상단 stretch 유지, 메시지는 항상 아래로 쌓임"""
        bubble = ChatBubble(role, content)
        self.chat_layout.addWidget(bubble)

        # 레이아웃 갱신 후 최하단으로 스크롤
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def set_capture_status(self, text: str):
        """캡처 상태 라벨 업데이트"""
        self.capture_status.setText(text)
        self.capture_status.setStyleSheet("color: #89b4fa; font-size: 10px;")

    def clear_capture_status(self):
        """캡처 상태 초기화"""
        self.capture_status.setText("첨부된 캡처 없음")
        self.capture_status.setStyleSheet("color: #6c7086; font-size: 10px;")

    def set_generating(self, generating: bool):
        """
        AI 생성 중 상태 전환.
        - generating=True : 전송 버튼 → ⏹ 중지 (빨간색), 나머지 입력 비활성화
        - generating=False: 전송 버튼 → 전송 ▶ (파란색), 나머지 입력 활성화
        """
        self._is_generating = generating
        if generating:
            self.send_btn.setText("⏹ 중지")
            self.send_btn.setStyleSheet(self._send_btn_stop_style)
            self.send_btn.setEnabled(True)   # 중지 버튼은 항상 클릭 가능
            self.input_box.setEnabled(False)
            self.capture_btn.setEnabled(False)
            self.element_pick_btn.setEnabled(False)
        else:
            self.send_btn.setText("전송 ▶")
            self.send_btn.setStyleSheet(self._send_btn_normal_style)
            self.send_btn.setEnabled(True)
            self.input_box.setEnabled(True)
            self.capture_btn.setEnabled(True)
            self.element_pick_btn.setEnabled(True)

    def set_input_enabled(self, enabled: bool):
        """입력 활성화/비활성화 (생성 중 상태와 무관한 일반 제어용)"""
        self.input_box.setEnabled(enabled)
        self.capture_btn.setEnabled(enabled)
        self.element_pick_btn.setEnabled(enabled)
        # send_btn은 생성 중이 아닐 때만 enabled 상태 동기화
        if not self._is_generating:
            self.send_btn.setEnabled(enabled)

    # ── 요소 칩 관리 ──────────────────────────────────────

    def add_element_chip(self, element_info: dict):
        """선택된 UI 요소를 칩으로 입력 영역에 추가"""
        item = dict(element_info)
        self._pending_elements.append(item)
        chip = ElementChip(element_info)
        self._chip_widgets.append(chip)
        chip.remove_requested.connect(lambda c=chip, d=item: self._remove_chip(c, d))
        # stretch 바로 앞에 삽입
        self._chips_layout.insertWidget(self._chips_layout.count() - 1, chip)
        self.chips_frame.show()

    def _remove_chip(self, chip: ElementChip, item: dict):
        """칩 위젯과 대응 데이터 제거"""
        if item in self._pending_elements:
            self._pending_elements.remove(item)
        if chip in self._chip_widgets:
            self._chip_widgets.remove(chip)
        chip.setParent(None)  # type: ignore
        chip.deleteLater()
        if not self._chip_widgets:
            self.chips_frame.hide()

    def get_pending_elements(self) -> list[dict]:
        """전송 대기 중인 요소 정보 목록 반환"""
        return list(self._pending_elements)

    def clear_pending_elements(self):
        """모든 요소 칩 제거"""
        for chip in list(self._chip_widgets):
            chip.setParent(None)  # type: ignore
            chip.deleteLater()
        self._chip_widgets.clear()
        self._pending_elements.clear()
        self.chips_frame.hide()

    def clear(self):
        """대화 내용 모두 삭제"""
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # 상단 stretch 복원
        self.chat_layout.addStretch(1)
