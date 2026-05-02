"""
세션 목록 패널

저장된 세션들을 표시하고 선택/삭제할 수 있는 패널입니다.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QLineEdit, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor


class SessionListPanel(QWidget):
    """세션 목록 패널"""

    session_selected = pyqtSignal(str)              # 세션 선택 시그널
    session_delete_requested = pyqtSignal(str)      # 세션 삭제 요청 시그널

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sessions = []
        self._active_session_id: str | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 헤더
        header = QLabel("📋 세션 목록")
        header.setFont(QFont("Malgun Gothic", 12, QFont.Weight.Bold))
        header.setStyleSheet("padding: 5px; color: #cdd6f4;")
        layout.addWidget(header)

        # 검색창
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 세션 검색...")
        self.search_box.textChanged.connect(self._filter_sessions)
        layout.addWidget(self.search_box)

        # 세션 리스트
        self.list_widget = QListWidget()
        self.list_widget.setFont(QFont("Malgun Gothic", 10))
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget)

        # 하단 버튼
        btn_frame = QFrame()
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        self.delete_btn = QPushButton("🗑 삭제")
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #45475a;
                color: #f38ba8;
                border-radius: 4px;
                padding: 5px;
            }
            QPushButton:hover { background-color: #585b70; }
        """)
        self.delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self.delete_btn)

        layout.addWidget(btn_frame)

    def refresh(self, sessions: list):
        """세션 목록 새로고침. active 세션은 set_active_session 으로 별도 지정."""
        self._sessions = sessions
        self._update_list(self.search_box.text())

    def set_active_session(self, session_id: str | None):
        """현재 작업 중인 세션 ID 지정 — 시각적으로 강조 표시.

        강조: 좌측 ▶ marker + 강조색 배경 (#313244) + 강조색 텍스트 (#89b4fa) + bold.
        """
        if self._active_session_id == session_id:
            return
        self._active_session_id = session_id
        self._update_list(self.search_box.text())

    def _update_list(self, filter_text: str = ""):
        """리스트 위젯 업데이트"""
        self.list_widget.clear()

        for session in self._sessions:
            title = session.title
            if filter_text and filter_text.lower() not in title.lower():
                continue

            # 표시 텍스트
            step_info = f"({session.completed_steps}/{session.total_steps} steps)"
            ptype = "🌐" if session.project_type == "web" else "🖥️"
            is_active = session.session_id == self._active_session_id
            marker = "▶ " if is_active else "   "
            display_text = f"{marker}{ptype} {title}\n     {step_info}"

            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, session.session_id)

            if is_active:
                # 활성 세션 — 배경색 + 강조 텍스트색 + bold
                item.setBackground(QColor("#313244"))
                item.setForeground(QColor("#89b4fa"))
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self.list_widget.addItem(item)

    def _filter_sessions(self, text: str):
        """검색 필터"""
        self._update_list(text)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """세션 더블클릭으로 선택"""
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if session_id:
            self.session_selected.emit(session_id)

    def _on_delete(self):
        """선택된 세션 삭제 요청"""
        current = self.list_widget.currentItem()
        if current:
            session_id = current.data(Qt.ItemDataRole.UserRole)
            if session_id:
                self.session_delete_requested.emit(session_id)
