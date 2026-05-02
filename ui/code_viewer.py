"""
코드 + 캡처 뷰어

스텝별로 생성된 코드와 캡처 이미지를 표시합니다.
각 스텝에 대해 삭제, 삽입, 이동, Diff 보기 기능을 제공합니다.
"""

import difflib
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QPushButton, QFrame, QPlainTextEdit, QSizePolicy,
    QMessageBox, QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QFont, QPixmap, QSyntaxHighlighter, QTextCharFormat, QColor,
    QTextCursor, QTextBlockFormat
)

import re


class PythonHighlighter(QSyntaxHighlighter):
    """간단한 Python 구문 강조"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        # 키워드
        keyword_fmt = QTextCharFormat()
        keyword_fmt.setForeground(QColor("#cba6f7"))
        keyword_fmt.setFontWeight(QFont.Weight.Bold)
        keywords = [
            'and', 'as', 'assert', 'async', 'await', 'break', 'class',
            'continue', 'def', 'del', 'elif', 'else', 'except', 'finally',
            'for', 'from', 'global', 'if', 'import', 'in', 'is', 'lambda',
            'not', 'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield',
            'True', 'False', 'None'
        ]
        for w in keywords:
            self.rules.append((re.compile(rf'\b{w}\b'), keyword_fmt))

        # 문자열
        string_fmt = QTextCharFormat()
        string_fmt.setForeground(QColor("#a6e3a1"))
        self.rules.append((re.compile(r'\".*?\"'), string_fmt))
        self.rules.append((re.compile(r"\'.*?\'"), string_fmt))

        # 숫자
        number_fmt = QTextCharFormat()
        number_fmt.setForeground(QColor("#fab387"))
        self.rules.append((re.compile(r'\b\d+\.?\d*\b'), number_fmt))

        # 주석
        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#6c7086"))
        comment_fmt.setFontItalic(True)
        self.rules.append((re.compile(r'#.*$', re.MULTILINE), comment_fmt))

        # 함수/메서드 호출
        func_fmt = QTextCharFormat()
        func_fmt.setForeground(QColor("#89b4fa"))
        self.rules.append((re.compile(r'\b\w+(?=\()'), func_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ──────────────────────────────────────────────────
# Diff 뷰어 (코드 변경 색상 표시)
# ──────────────────────────────────────────────────

class DiffCodeViewer(QPlainTextEdit):
    """
    코드 Diff 뷰어.

    이전 스텝 대비 추가/삭제된 줄을 색상으로 표시합니다.
    - 추가된 줄: 초록 배경
    - 삭제된 줄: 빨간 배경
    - 변경 없는 줄: 기본 배경
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 10))
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #11111b;
                color: #cdd6f4;
                border: 1px solid #313244;
                border-radius: 4px;
            }
        """)

    def show_diff(self, old_code: str, new_code: str):
        """두 코드를 비교하여 diff를 색상으로 표시합니다."""
        self.clear()

        old_lines = old_code.splitlines(keepends=True)
        new_lines = new_code.splitlines(keepends=True)

        differ = difflib.unified_diff(old_lines, new_lines, n=9999)

        diff_entries = []  # (prefix, line_text)

        for line in differ:
            if line.startswith('---') or line.startswith('+++') or line.startswith('@@'):
                continue
            elif line.startswith('+'):
                diff_entries.append(('+', line[1:].rstrip('\n')))
            elif line.startswith('-'):
                diff_entries.append(('-', line[1:].rstrip('\n')))
            else:
                diff_entries.append((' ', line[1:].rstrip('\n') if len(line) > 1 else line.rstrip('\n')))

        if not diff_entries:
            # diff가 없으면 전체 코드를 그대로 표시
            for line in new_code.splitlines():
                diff_entries.append((' ', line))

        # 텍스트와 배경색 설정
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)

        for i, (prefix, text) in enumerate(diff_entries):
            if i > 0:
                cursor.insertText('\n')

            # 배경색 결정
            block_fmt = QTextBlockFormat()
            char_fmt = QTextCharFormat()
            char_fmt.setFont(QFont("Consolas", 10))

            if prefix == '+':
                # 추가된 줄: 초록 배경
                block_fmt.setBackground(QColor("#1a3a1a"))
                char_fmt.setForeground(QColor("#a6e3a1"))
                display_text = f"+ {text}"
            elif prefix == '-':
                # 삭제된 줄: 빨간 배경
                block_fmt.setBackground(QColor("#3a1a1a"))
                char_fmt.setForeground(QColor("#f38ba8"))
                display_text = f"- {text}"
            else:
                # 변경 없는 줄
                char_fmt.setForeground(QColor("#cdd6f4"))
                display_text = f"  {text}"

            cursor.setBlockFormat(block_fmt)
            cursor.insertText(display_text, char_fmt)

        self.setTextCursor(cursor)
        self.moveCursor(QTextCursor.MoveOperation.Start)


# ──────────────────────────────────────────────────
# 리사이즈 핸들 (드래그로 코드 에디터 높이 조절)
# ──────────────────────────────────────────────────

class ResizeHandle(QWidget):
    """드래그로 StepCard 코드 에디터 높이를 조절하는 핸들 위젯"""

    def __init__(self, targets: list, parent=None):
        """
        Args:
            targets: 높이를 동기화할 위젯 리스트 (code_edit, diff_viewer 등)
        """
        super().__init__(parent)
        self._targets = targets
        self._drag_start_y: float | None = None
        self._drag_start_height: int | None = None

        self.setFixedHeight(8)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self._normal_style = (
            "background: #313244; border-radius: 3px; margin: 2px 30px;"
        )
        self._hover_style = (
            "background: #585b70; border-radius: 3px; margin: 2px 30px;"
        )
        self.setStyleSheet(self._normal_style)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_y = event.globalPosition().y()
            # 현재 보이는 위젯의 높이를 기준으로 드래그 시작
            visible = next(
                (t for t in self._targets if t.isVisible()),
                self._targets[0] if self._targets else None
            )
            self._drag_start_height = visible.height() if visible else 200

    def mouseMoveEvent(self, event):
        if self._drag_start_y is not None and self._drag_start_height is not None:
            delta = event.globalPosition().y() - self._drag_start_y
            new_height = max(60, self._drag_start_height + int(delta))
            for target in self._targets:
                target.setFixedHeight(new_height)

    def mouseReleaseEvent(self, event):
        self._drag_start_y = None
        self._drag_start_height = None

    def enterEvent(self, event):
        self.setStyleSheet(self._hover_style)

    def leaveEvent(self, event):
        self.setStyleSheet(self._normal_style)


# ──────────────────────────────────────────────────
# 스텝 카드 (액션 버튼 + Diff 포함)
# ──────────────────────────────────────────────────

class StepCard(QFrame):
    """스텝 카드 위젯: 코드 + 캡처 이미지 + 액션 버튼"""

    delete_requested = pyqtSignal(int)      # step_id
    insert_requested = pyqtSignal(int)      # after_step_id
    move_up_requested = pyqtSignal(int)     # step_id
    move_down_requested = pyqtSignal(int)   # step_id
    code_edited = pyqtSignal(int, str)      # step_id, new_code

    def __init__(self, step_id: int, code: str,
                 prev_code: str = "", capture_path: str = None,
                 parent=None):
        super().__init__(parent)
        self.step_id = step_id
        self._code = code
        self._prev_code = prev_code
        self._showing_diff = False
        self._editing = False

        self.setStyleSheet("""
            StepCard {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 6px;
                margin: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # ── 스텝 헤더 (타이틀 + 액션 버튼) ──
        # 클릭 이벤트를 받기 위해 QFrame으로 감쌉니다.
        self.header_frame = QFrame()
        self.header_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_frame.setStyleSheet("StepCard QFrame { background: transparent; }")
        self.header_frame.mousePressEvent = self._toggle_expand
        
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        # 표시 형식: "▼ 📝 Step N" (펼침), "▶ 📝 Step N" (접힘)
        self.expanded_icon = "▼"
        self.collapsed_icon = "▶"
        self._expanded = True

        # 스텝 번호
        self.header_label = QLabel(f"{self.expanded_icon} 📝 Step {step_id}")
        self.header_label.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        self.header_label.setStyleSheet("color: #89b4fa; border: none;")
        header_layout.addWidget(self.header_label)
        header_layout.addStretch()

        # 버튼 스타일
        btn_style = """
            QPushButton {
                background-color: transparent;
                border: 1px solid #45475a;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 12px;
                min-width: 24px;
            }
            QPushButton:hover {
                background-color: #313244;
                border-color: #89b4fa;
            }
        """

        # ⬆ 위로 이동
        self.up_btn = QPushButton("⬆")
        self.up_btn.setToolTip("위로 이동")
        self.up_btn.setStyleSheet(btn_style)
        self.up_btn.clicked.connect(lambda: self.move_up_requested.emit(self.step_id))
        header_layout.addWidget(self.up_btn)

        # ⬇ 아래로 이동
        self.down_btn = QPushButton("⬇")
        self.down_btn.setToolTip("아래로 이동")
        self.down_btn.setStyleSheet(btn_style)
        self.down_btn.clicked.connect(lambda: self.move_down_requested.emit(self.step_id))
        header_layout.addWidget(self.down_btn)

        # 🔄 Diff 보기 토글
        self.diff_btn = QPushButton("🔄 Diff")
        self.diff_btn.setToolTip("이전 스텝과 코드 비교")
        self.diff_btn.setStyleSheet(btn_style)
        self.diff_btn.clicked.connect(self._toggle_diff)
        if not prev_code:
            self.diff_btn.setEnabled(False)
            self.diff_btn.setToolTip("첫 번째 스텝 (비교 대상 없음)")
        header_layout.addWidget(self.diff_btn)

        # ➕ 아래 삽입
        self.insert_btn = QPushButton("➕")
        self.insert_btn.setToolTip("이 스텝 아래에 새 스텝 삽입")
        self.insert_btn.setStyleSheet(btn_style)
        self.insert_btn.clicked.connect(lambda: self.insert_requested.emit(self.step_id))
        header_layout.addWidget(self.insert_btn)

        # ✏️ 코드 수정 (마지막 스텝에서만 표시)
        self.edit_btn = QPushButton("✏️ 수정")
        self.edit_btn.setToolTip("코드 직접 수정")
        edit_btn_style = btn_style.replace(
            "border: 1px solid #45475a;",
            "border: 1px solid #89b4fa;"
        ).replace(
            "QPushButton:hover {\n                background-color: #313244;\n                border-color: #89b4fa;\n            }",
            "QPushButton:hover { background-color: #1e3a5f; border-color: #89dceb; }"
        )
        self.edit_btn.setStyleSheet(edit_btn_style)
        self.edit_btn.clicked.connect(self._toggle_edit)
        self.edit_btn.setVisible(False)  # 기본 숨김 — 마지막 스텝에서만 표시
        header_layout.addWidget(self.edit_btn)

        # 🗑️ 삭제
        self.delete_btn = QPushButton("🗑️")
        self.delete_btn.setToolTip("이 스텝 삭제")
        del_style = btn_style.replace("#45475a", "#45475a").replace(
            "#89b4fa", "#f38ba8"
        )
        self.delete_btn.setStyleSheet(del_style)
        self.delete_btn.clicked.connect(self._on_delete)
        header_layout.addWidget(self.delete_btn)

        layout.addWidget(self.header_frame)

        # ── 캡쳐 컨테이너 (토글 용이성을 위해) ──
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)
        
        # ── 캡처 이미지 (있을 경우) ──
        if capture_path and Path(capture_path).exists():
            img_label = QLabel()
            pixmap = QPixmap(capture_path)
            if not pixmap.isNull():
                scaled = pixmap.scaledToWidth(
                    min(400, pixmap.width()),
                    Qt.TransformationMode.SmoothTransformation
                )
                img_label.setPixmap(scaled)
                img_label.setStyleSheet("border: 1px solid #45475a; border-radius: 4px;")
                content_layout.addWidget(img_label)

        # ── 코드 에디터 ──
        self.code_edit = QPlainTextEdit()
        self.code_edit.setPlainText(code)
        self.code_edit.setFont(QFont("Consolas", 10))
        self.code_edit.setReadOnly(True)
        self._readonly_style = """
            QPlainTextEdit {
                background-color: #11111b;
                color: #cdd6f4;
                border: 1px solid #313244;
                border-radius: 4px;
            }
        """
        self._editing_style = """
            QPlainTextEdit {
                background-color: #1a1a2e;
                color: #cdd6f4;
                border: 2px solid #89b4fa;
                border-radius: 4px;
            }
        """
        self.code_edit.setStyleSheet(self._readonly_style)
        self.code_edit.setFixedHeight(200)

        # 구문 강조
        self.highlighter = PythonHighlighter(self.code_edit.document())
        content_layout.addWidget(self.code_edit)

        # ── Diff 뷰어 (초기 숨김) ──
        self.diff_viewer = DiffCodeViewer()
        self.diff_viewer.setFixedHeight(200)
        self.diff_viewer.setVisible(False)
        content_layout.addWidget(self.diff_viewer)

        # 드래그 리사이즈 핸들
        self.resize_handle = ResizeHandle([self.code_edit, self.diff_viewer])
        content_layout.addWidget(self.resize_handle)

        layout.addWidget(self.content_widget)

    def get_code(self) -> str:
        return self.code_edit.toPlainText()

    def update_step_id(self, new_id: int):
        """스텝 ID 업데이트 (재정렬 시 사용)"""
        self.step_id = new_id
        self.header_label.setText(f"📝 Step {new_id}")

    def set_prev_code(self, prev_code: str):
        """이전 코드 업데이트 (diff 비교용)"""
        self._prev_code = prev_code
        self.diff_btn.setEnabled(bool(prev_code))
        if prev_code:
            self.diff_btn.setToolTip("이전 스텝과 코드 비교")
        else:
            self.diff_btn.setToolTip("첫 번째 스텝 (비교 대상 없음)")

        # diff가 보이고 있으면 새로고침
        if self._showing_diff:
            self._show_diff()

    def _toggle_expand(self, event):
        """본문 숨김/표시 토글"""
        self._expanded = not self._expanded
        self.content_widget.setVisible(self._expanded)
        icon = self.expanded_icon if self._expanded else self.collapsed_icon
        self.header_label.setText(f"{icon} 📝 Step {self.step_id}")

    def _toggle_diff(self):
        """Diff 보기 토글"""
        self._showing_diff = not self._showing_diff

        if self._showing_diff:
            self._show_diff()
            self.code_edit.setVisible(False)
            self.diff_viewer.setVisible(True)
            self.diff_btn.setText("📝 코드")
            self.diff_btn.setToolTip("일반 코드 보기")
        else:
            self.code_edit.setVisible(True)
            self.diff_viewer.setVisible(False)
            self.diff_btn.setText("🔄 Diff")
            self.diff_btn.setToolTip("이전 스텝과 코드 비교")

    def _show_diff(self):
        """Diff 뷰어에 코드 차이를 표시합니다."""
        current_code = self.code_edit.toPlainText()
        self.diff_viewer.show_diff(self._prev_code, current_code)

    def set_is_last(self, is_last: bool):
        """마지막 스텝 여부 설정 — 수정 버튼 표시/숨김"""
        self.edit_btn.setVisible(is_last)
        if not is_last and self._editing:
            # 더 이상 마지막 스텝이 아니면 편집 모드 종료
            self._exit_edit_mode()

    def _toggle_edit(self):
        """편집/완료 토글"""
        if self._editing:
            self._exit_edit_mode()
        else:
            self._enter_edit_mode()

    def _enter_edit_mode(self):
        """편집 모드 활성화"""
        self._editing = True
        self.code_edit.setReadOnly(False)
        self.code_edit.setStyleSheet(self._editing_style)
        self.code_edit.setFixedHeight(400)
        self.edit_btn.setText("✅ 완료")
        self.edit_btn.setToolTip("편집 완료 후 읽기 전용으로 전환")
        self.code_edit.setFocus()

    def _exit_edit_mode(self):
        """편집 모드 종료 (변경 내용 유지)"""
        self._editing = False
        new_code = self.code_edit.toPlainText()
        self._code = new_code
        self.code_edit.setReadOnly(True)
        self.code_edit.setStyleSheet(self._readonly_style)
        self.code_edit.setFixedHeight(200)
        self.edit_btn.setText("✏️ 수정")
        self.edit_btn.setToolTip("코드 직접 수정")
        self.code_edited.emit(self.step_id, new_code)

    def _on_delete(self):
        """삭제 확인 후 시그널 발생"""
        reply = QMessageBox.question(
            self, "스텝 삭제",
            f"Step {self.step_id}을(를) 삭제하시겠습니까?\n"
            "이 작업은 되돌릴 수 없습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self.step_id)


# ──────────────────────────────────────────────────
# 코드 뷰어 패널
# ──────────────────────────────────────────────────

# ──────────────────────────────────────────────────
# 블럭 뷰 카드 (라이브러리 블럭 / 스텝 블럭 공통)
# ──────────────────────────────────────────────────

class BlockCard(QFrame):
    """Colab 스타일의 블럭 카드 — 라이브러리 블럭 또는 스텝 블럭"""

    # 이 블럭부터 실행 요청 (step_id, 0 = 라이브러리 블럭) — N 부터 끝까지
    run_from_here_requested = pyqtSignal(int)
    # 이 블럭만 단독 실행 요청 (step_id) — N 만 실행, 다음 step 안 함
    run_single_requested = pyqtSignal(int)
    # 코드 수정 완료 (step_id, new_code)
    block_code_edited = pyqtSignal(int, str)
    # 블럭 삭제 요청 (step_id)
    block_delete_requested = pyqtSignal(int)

    _BTN_STYLE = """
        QPushButton {
            background-color: transparent;
            border: 1px solid #45475a;
            border-radius: 3px;
            padding: 2px 8px;
            font-size: 12px;
            color: #cdd6f4;
        }
        QPushButton:hover {
            background-color: #313244;
            border-color: #89b4fa;
        }
    """
    _RUN_BTN_STYLE = """
        QPushButton {
            background-color: #1e3a1e;
            color: #a6e3a1;
            border: 1px solid #a6e3a1;
            border-radius: 3px;
            padding: 2px 10px;
            font-size: 12px;
            font-weight: bold;
        }
        QPushButton:hover { background-color: #2d5a2d; }
        QPushButton:disabled { color: #45475a; border-color: #45475a; background: transparent; }
    """
    _READONLY_CODE_STYLE = """
        QPlainTextEdit {
            background-color: #11111b;
            color: #cdd6f4;
            border: 1px solid #313244;
            border-radius: 4px;
        }
    """
    _EDITING_CODE_STYLE = """
        QPlainTextEdit {
            background-color: #1a1a2e;
            color: #cdd6f4;
            border: 2px solid #89b4fa;
            border-radius: 4px;
        }
    """

    def __init__(self, step_id: int, title: str, code: str,
                 status: str = "", parent=None):
        """
        Args:
            step_id: 스텝 ID (0 = 라이브러리 블럭)
            title:   헤더에 표시할 제목
            code:    표시할 코드 (델타 코드 또는 import 목록)
            status:  "✅" / "❌" / "🔄" / "" 등 실행 상태 아이콘
        """
        super().__init__(parent)
        self.step_id = step_id
        self._expanded = True
        self._editing = False

        border_color = "#89b4fa" if step_id == 0 else "#313244"
        self.setStyleSheet(f"""
            BlockCard {{
                background-color: #181825;
                border: 1px solid {border_color};
                border-radius: 6px;
                margin: 3px 4px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(3)

        # ── 헤더 ──
        header_frame = QFrame()
        header_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        header_frame.setStyleSheet("QFrame { background: transparent; }")
        header_frame.mousePressEvent = self._on_header_click

        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(4)

        self._expand_icon_label = QLabel("▼")
        self._expand_icon_label.setStyleSheet("color: #6c7086; border: none;")
        h_layout.addWidget(self._expand_icon_label)

        title_color = "#89b4fa" if step_id == 0 else "#cba6f7"
        self.title_label = QLabel(title)
        self.title_label.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        self.title_label.setStyleSheet(f"color: {title_color}; border: none;")
        h_layout.addWidget(self.title_label)

        self.status_label = QLabel(status)
        self.status_label.setStyleSheet("color: #a6e3a1; border: none; font-size: 13px;")
        h_layout.addWidget(self.status_label)
        h_layout.addStretch()

        # ── 수정 버튼 ──
        self.edit_btn = QPushButton("✏️ 수정")
        self.edit_btn.setStyleSheet(self._BTN_STYLE.replace("#89b4fa", "#89dceb"))
        self.edit_btn.setToolTip("코드 직접 수정")
        self.edit_btn.clicked.connect(self._toggle_edit)
        # 헤더 클릭으로 편집 토글 안되도록 클릭 이벤트 차단
        self.edit_btn.mousePressEvent = lambda e: (
            QPushButton.mousePressEvent(self.edit_btn, e)
        )
        h_layout.addWidget(self.edit_btn)

        # ── 삭제 버튼 (라이브러리 블럭=0은 제외) ──
        if step_id > 0:
            self.delete_btn = QPushButton("🗑️")
            del_style = self._BTN_STYLE.replace("#89b4fa", "#f38ba8")
            self.delete_btn.setStyleSheet(del_style)
            self.delete_btn.setToolTip(f"Step {step_id} 블럭 삭제")
            self.delete_btn.clicked.connect(self._on_delete)
            self.delete_btn.mousePressEvent = lambda e: (
                QPushButton.mousePressEvent(self.delete_btn, e)
            )
            h_layout.addWidget(self.delete_btn)

        # ── 단독 실행 버튼 (라이브러리 블럭=0 은 제외, 한 번만 실행되는 setup 이라 의미 없음) ──
        if step_id > 0:
            self.run_single_btn = QPushButton("⏯ 단독")
            single_style = self._RUN_BTN_STYLE.replace(
                "#1e3a1e", "#2a2a4a"
            ).replace("#a6e3a1", "#cba6f7").replace("#2d5a2d", "#3a3a5a")
            self.run_single_btn.setStyleSheet(single_style)
            self.run_single_btn.setToolTip(
                f"Step {step_id} 만 실행 (다음 step 으로 진행 안 함).\n"
                f"이전 step 들이 이미 커널에 실행된 상태로 가정.\n"
                f"커널 미준비 시 자동 silent replay."
            )
            self.run_single_btn.clicked.connect(
                lambda: self.run_single_requested.emit(self.step_id)
            )
            self.run_single_btn.mousePressEvent = lambda e: (
                QPushButton.mousePressEvent(self.run_single_btn, e)
            )
            h_layout.addWidget(self.run_single_btn)

        # ── 실행 버튼 ──
        self.run_btn = QPushButton("▶ 여기서 실행")
        self.run_btn.setStyleSheet(self._RUN_BTN_STYLE)
        self.run_btn.setToolTip(
            "라이브러리 블럭 재초기화" if step_id == 0
            else f"Step {step_id}부터 끝까지 이어서 실행"
        )
        self.run_btn.clicked.connect(lambda: self.run_from_here_requested.emit(self.step_id))
        self.run_btn.mousePressEvent = lambda e: (
            QPushButton.mousePressEvent(self.run_btn, e)
        )
        h_layout.addWidget(self.run_btn)

        layout.addWidget(header_frame)

        # ── 코드 표시 영역 ──
        self.content_frame = QFrame()
        self.content_frame.setStyleSheet("QFrame { background: transparent; }")
        c_layout = QVBoxLayout(self.content_frame)
        c_layout.setContentsMargins(0, 2, 0, 0)
        c_layout.setSpacing(0)

        self.code_edit = QPlainTextEdit()
        self.code_edit.setPlainText(code)
        self.code_edit.setFont(QFont("Consolas", 10))
        self.code_edit.setReadOnly(True)
        self.code_edit.setStyleSheet(self._READONLY_CODE_STYLE)
        self.code_edit.setFixedHeight(160)
        # 참조 보존 필수 (GC 방지)
        self.highlighter = PythonHighlighter(self.code_edit.document())
        c_layout.addWidget(self.code_edit)

        resize_handle = ResizeHandle([self.code_edit])
        c_layout.addWidget(resize_handle)

        layout.addWidget(self.content_frame)

    # ──────────────────────────────────────
    # 퍼블릭 API
    # ──────────────────────────────────────

    def set_status(self, status: str):
        """실행 상태 아이콘 갱신"""
        self.status_label.setText(status)

    def set_run_enabled(self, enabled: bool):
        """여기서 실행 버튼 활성화/비활성화"""
        self.run_btn.setEnabled(enabled)

    def get_code(self) -> str:
        return self.code_edit.toPlainText()

    # ──────────────────────────────────────
    # 내부 이벤트
    # ──────────────────────────────────────

    def _on_header_click(self, _event=None):
        """헤더 클릭: 접기/펼치기"""
        self._toggle_expand()

    def _toggle_expand(self):
        self._expanded = not self._expanded
        self.content_frame.setVisible(self._expanded)
        self._expand_icon_label.setText("▼" if self._expanded else "▶")

    def _toggle_edit(self):
        """편집/저장 토글"""
        if self._editing:
            self._exit_edit_mode()
        else:
            self._enter_edit_mode()

    def _enter_edit_mode(self):
        self._editing = True
        self.code_edit.setReadOnly(False)
        self.code_edit.setStyleSheet(self._EDITING_CODE_STYLE)
        self.code_edit.setFixedHeight(300)
        self.edit_btn.setText("✅ 저장")
        self.edit_btn.setToolTip("수정 완료 후 저장")
        if not self._expanded:
            self._toggle_expand()
        self.code_edit.setFocus()

    def _exit_edit_mode(self):
        self._editing = False
        new_code = self.code_edit.toPlainText()
        self.code_edit.setReadOnly(True)
        self.code_edit.setStyleSheet(self._READONLY_CODE_STYLE)
        self.code_edit.setFixedHeight(160)
        self.edit_btn.setText("✏️ 수정")
        self.edit_btn.setToolTip("코드 직접 수정")
        self.block_code_edited.emit(self.step_id, new_code)

    def _on_delete(self):
        """삭제 확인 후 시그널 발생"""
        reply = QMessageBox.question(
            self, "블럭 삭제",
            f"Step {self.step_id} 블럭을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.block_delete_requested.emit(self.step_id)


# ──────────────────────────────────────────────────
# 블럭 뷰 위젯 (Colab-style 전체 레이아웃)
# ──────────────────────────────────────────────────

class BlockViewWidget(QWidget):
    """
    Colab 스타일 블럭 뷰.

    - 최상단: 라이브러리 블럭 (imports + 헬퍼 함수)
    - 이후: 스텝별 델타 코드 블럭
    - 각 블럭: "▶ 여기서 실행" 버튼으로 해당 스텝부터 실행 가능
    """

    # 커널 재시작 요청
    kernel_reset_requested = pyqtSignal()
    # N번 스텝부터 실행 요청 (0 = 라이브러리 블럭만 재실행)
    run_from_step_requested = pyqtSignal(int)
    # N번 스텝 단독 실행 (Phase 1 — 다음 step 안 함)
    run_single_step_requested = pyqtSignal(int)
    # 중지 요청
    stop_requested = pyqtSignal()
    # 블럭 코드 수정 완료 (step_id, new_code)
    block_code_edited = pyqtSignal(int, str)
    # 블럭 삭제 요청 (step_id)
    block_delete_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._block_cards: list[BlockCard] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 툴바 ──
        toolbar = QFrame()
        toolbar.setStyleSheet("QFrame { background: #1e1e2e; border-bottom: 1px solid #313244; }")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 4, 8, 4)
        tb_layout.setSpacing(6)

        info_label = QLabel("🧱 Colab 블럭 뷰 — 스텝별 델타 코드")
        info_label.setFont(QFont("Malgun Gothic", 10))
        info_label.setStyleSheet("color: #cdd6f4;")
        tb_layout.addWidget(info_label)
        tb_layout.addStretch()

        _btn_style = """
            QPushButton {
                background-color: transparent;
                border: 1px solid #45475a;
                border-radius: 3px;
                padding: 3px 10px;
                font-size: 12px;
                color: #cdd6f4;
            }
            QPushButton:hover { background-color: #313244; border-color: #cba6f7; }
            QPushButton:disabled { color: #45475a; }
        """

        self.run_all_btn = QPushButton("▶ 처음부터 실행")
        self.run_all_btn.setStyleSheet(_btn_style.replace("#cba6f7", "#a6e3a1").replace(
            "color: #cdd6f4;", "color: #a6e3a1; font-weight: bold;"
        ))
        self.run_all_btn.setToolTip("라이브러리 블럭부터 모든 스텝 순서대로 실행")
        self.run_all_btn.clicked.connect(lambda: self.run_from_step_requested.emit(1))
        tb_layout.addWidget(self.run_all_btn)

        self.stop_btn = QPushButton("■ 중지")
        self.stop_btn.setStyleSheet(_btn_style.replace("#cba6f7", "#f38ba8").replace(
            "color: #cdd6f4;", "color: #f38ba8; font-weight: bold;"
        ))
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        tb_layout.addWidget(self.stop_btn)

        reset_btn = QPushButton("🔄 커널 재시작")
        reset_btn.setStyleSheet(_btn_style)
        reset_btn.setToolTip("커널을 재시작하여 모든 변수 초기화")
        reset_btn.clicked.connect(self.kernel_reset_requested.emit)
        tb_layout.addWidget(reset_btn)

        self.kernel_status_label = QLabel("● 커널 없음")
        self.kernel_status_label.setStyleSheet("color: #6c7086; font-size: 11px;")
        tb_layout.addWidget(self.kernel_status_label)

        layout.addWidget(toolbar)

        # ── 스크롤 영역 (블럭 카드들) ──
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; }")

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.cards_layout.setSpacing(2)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.addStretch()

        self.scroll_area.setWidget(self.cards_container)
        layout.addWidget(self.scroll_area)

    def refresh(self, library_code: str, steps_data: list[dict]):
        """
        블럭 뷰를 전체 갱신합니다.

        Args:
            library_code: 라이브러리 블럭 코드 (imports + 헬퍼 함수)
            steps_data:   [{"step_id": N, "title": "...", "delta_code": "...", "status": ""}, ...]
        """
        self.clear()

        # 라이브러리 블럭
        if library_code.strip():
            lib_card = BlockCard(
                step_id=0,
                title="📦 라이브러리 블럭 (imports + 공통 함수)",
                code=library_code,
                status=""
            )
            lib_card.run_from_here_requested.connect(self._on_run_from)
            lib_card.block_code_edited.connect(self.block_code_edited)
            self._block_cards.append(lib_card)
            self._remove_stretch()
            self.cards_layout.addWidget(lib_card)
            self.cards_layout.addStretch()

        # 스텝 블럭
        for data in steps_data:
            self._add_step_block(data)

        self._update_run_buttons()

    def _add_step_block(self, data: dict):
        step_id = data.get("step_id", 0)
        title = data.get("title", f"Step {step_id}")
        delta_code = data.get("delta_code", "")
        status = data.get("status", "")

        if not delta_code.strip():
            return

        card = BlockCard(
            step_id=step_id,
            title=f"📋 Step {step_id}: {title}",
            code=delta_code,
            status=status
        )
        card.run_from_here_requested.connect(self._on_run_from)
        card.run_single_requested.connect(self.run_single_step_requested)
        card.block_code_edited.connect(self.block_code_edited)
        card.block_delete_requested.connect(self.block_delete_requested)
        self._block_cards.append(card)
        self._remove_stretch()
        self.cards_layout.addWidget(card)
        self.cards_layout.addStretch()

    def _on_run_from(self, step_id: int):
        """블럭 카드의 '여기서 실행' 버튼 처리"""
        if step_id == 0:
            # 라이브러리 블럭 재초기화 → 커널 재시작 후 step 1부터
            self.kernel_reset_requested.emit()
        else:
            self.run_from_step_requested.emit(step_id)

    def update_step_status(self, step_id: int, status: str):
        """특정 스텝 카드의 상태 아이콘 갱신"""
        for card in self._block_cards:
            if card.step_id == step_id:
                card.set_status(status)
                break

    def set_running(self, running: bool):
        """실행 중 UI 상태 전환"""
        self.run_all_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self._update_run_buttons(disabled=running)

    def set_kernel_status(self, alive: bool, executed_steps: list[int]):
        """커널 상태 표시 갱신"""
        if alive:
            count = len(executed_steps)
            self.kernel_status_label.setText(f"● 커널 활성 ({count}개 스텝 완료)")
            self.kernel_status_label.setStyleSheet("color: #a6e3a1; font-size: 11px;")
        else:
            self.kernel_status_label.setText("● 커널 없음")
            self.kernel_status_label.setStyleSheet("color: #6c7086; font-size: 11px;")

    def _update_run_buttons(self, disabled: bool = False):
        for card in self._block_cards:
            card.set_run_enabled(not disabled)

    def _remove_stretch(self):
        if self.cards_layout.count() > 0:
            last = self.cards_layout.itemAt(self.cards_layout.count() - 1)
            if last and last.spacerItem():
                self.cards_layout.removeItem(last)

    def clear(self):
        self._block_cards.clear()
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards_layout.addStretch()


# ──────────────────────────────────────────────────
# 코드 뷰어 패널
# ──────────────────────────────────────────────────

class CodeViewer(QWidget):
    """코드 + 캡처 뷰어 패널"""

    run_code_requested = pyqtSignal(str)           # 코드 실행 요청 (기존 모드)
    stop_code_requested = pyqtSignal()             # 코드 중지 요청
    step_delete_requested = pyqtSignal(int)        # 스텝 삭제 요청
    step_insert_requested = pyqtSignal(int)        # 스텝 삽입 요청 (after_step_id)
    step_move_requested = pyqtSignal(int, str)     # 스텝 이동 (step_id, "up"/"down")
    step_code_edited = pyqtSignal(int, str)        # 사용자가 코드 직접 수정 (step_id, new_code)
    # 블럭 뷰 전용 시그널
    run_from_step_requested = pyqtSignal(int)      # N번 스텝부터 블럭 실행 요청
    run_single_step_requested = pyqtSignal(int)    # N번 스텝 단독 실행 (Phase 1)
    kernel_reset_requested = pyqtSignal()          # 커널 재시작 요청
    block_step_code_edited = pyqtSignal(int, str)  # 블럭에서 코드 수정 (step_id, new_code)
    block_step_delete_requested = pyqtSignal(int)  # 블럭 삭제 요청 (step_id)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._step_cards: list[StepCard] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── 탭 위젯 ──
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                background: #181825;
                color: #cdd6f4;
                padding: 6px 14px;
                border: 1px solid #313244;
                border-bottom: none;
                border-radius: 4px 4px 0 0;
                font-family: 'Malgun Gothic';
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background: #1e1e2e;
                color: #89b4fa;
                border-color: #89b4fa;
            }
            QTabBar::tab:hover:!selected { background: #313244; }
        """)

        # ── 탭 1: 기존 누적 코드 뷰 ──
        self._classic_tab = QWidget()
        self._setup_classic_tab(self._classic_tab)
        self.tab_widget.addTab(self._classic_tab, "💻 코드 뷰어")

        # ── 탭 2: Colab 블럭 뷰 ──
        self.block_view = BlockViewWidget()
        self.block_view.run_from_step_requested.connect(self.run_from_step_requested)
        self.block_view.run_single_step_requested.connect(self.run_single_step_requested)
        self.block_view.kernel_reset_requested.connect(self.kernel_reset_requested)
        self.block_view.stop_requested.connect(self.stop_code_requested)
        self.block_view.block_code_edited.connect(self.block_step_code_edited)
        self.block_view.block_delete_requested.connect(self.block_step_delete_requested)
        self.tab_widget.addTab(self.block_view, "🧱 블럭 뷰")

        layout.addWidget(self.tab_widget)

    def _setup_classic_tab(self, parent: QWidget):
        """기존 누적 코드 뷰 탭 UI 구성"""
        tab_layout = QVBoxLayout(parent)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        # 헤더 + 실행 버튼
        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(5, 5, 5, 5)

        header = QLabel("💻 누적 코드 + 📷 캡처")
        header.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        header_layout.addWidget(header)
        header_layout.addStretch()

        self.run_btn = QPushButton("▶ 실행")
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #a6e3a1;
                color: #1e1e2e;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover { background-color: #94e2d5; }
            QPushButton:disabled {
                background-color: #313244;
                color: #6c7086;
                border: 1px dashed #45475a;
            }
        """)
        self.run_btn.clicked.connect(self._on_run)
        header_layout.addWidget(self.run_btn)

        self.stop_btn = QPushButton("■ 중지")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f38ba8;
                color: #1e1e2e;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover { background-color: #eba0ac; }
            QPushButton:disabled {
                background-color: #313244;
                color: #6c7086;
                border: 1px dashed #45475a;
            }
        """)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_code_requested.emit)
        header_layout.addWidget(self.stop_btn)

        tab_layout.addWidget(header_frame)

        # 스크롤 영역 (스텝 카드들)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.cards_layout.setSpacing(4)
        self.cards_layout.addStretch()

        self.scroll_area.setWidget(self.cards_container)
        tab_layout.addWidget(self.scroll_area)

    # ──────────────────────────────────────
    # 실행 상태 제어
    # ──────────────────────────────────────

    def set_running(self, running: bool):
        """실행 중 UI 상태 전환 (두 탭 모두 적용)"""
        self.run_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.block_view.set_running(running)

    # ──────────────────────────────────────
    # 블럭 뷰 갱신
    # ──────────────────────────────────────

    def refresh_block_view(self, library_code: str, steps_data: list[dict]):
        """
        블럭 뷰를 갱신합니다.

        Args:
            library_code: 라이브러리 블럭 코드
            steps_data:   [{"step_id": N, "title": "...", "delta_code": "...", "status": ""}, ...]
        """
        self.block_view.refresh(library_code, steps_data)

    def update_block_step_status(self, step_id: int, status: str):
        """블럭 뷰의 특정 스텝 상태 갱신"""
        self.block_view.update_step_status(step_id, status)

    def update_kernel_status(self, alive: bool, executed_steps: list[int]):
        """커널 상태 표시 갱신"""
        self.block_view.set_kernel_status(alive, executed_steps)

    # ──────────────────────────────────────
    # 스텝 카드
    # ──────────────────────────────────────

    def add_step(self, step_id: int, code: str, capture_path: str = None):
        """새 스텝 카드 추가"""
        # stretch 제거
        self._remove_trailing_stretch()

        # 이전 코드 가져오기 (diff 비교용)
        prev_code = ""
        if self._step_cards:
            prev_code = self._step_cards[-1].get_code()

        card = StepCard(step_id, code, prev_code=prev_code,
                       capture_path=capture_path)

        # 시그널 연결
        card.delete_requested.connect(self._on_step_delete)
        card.insert_requested.connect(self._on_step_insert)
        card.move_up_requested.connect(self._on_step_move_up)
        card.move_down_requested.connect(self._on_step_move_down)
        card.code_edited.connect(self.step_code_edited)

        self._step_cards.append(card)
        self.cards_layout.addWidget(card)
        self.cards_layout.addStretch()

        # 이동 버튼 상태 업데이트
        self._update_move_buttons()

        # 자동 스크롤
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def get_latest_code(self) -> str:
        """마지막 스텝의 코드 반환"""
        if self._step_cards:
            return self._step_cards[-1].get_code()
        return ""

    def _on_run(self):
        """실행 버튼 클릭 (기존 누적 코드 실행)"""
        code = self.get_latest_code()
        if code:
            self.run_code_requested.emit(code)

    # ──────────────────────────────────────────
    # 스텝 액션
    # ──────────────────────────────────────────

    def _on_step_delete(self, step_id: int):
        """스텝 삭제 시그널 전달"""
        self.step_delete_requested.emit(step_id)

    def _on_step_insert(self, after_step_id: int):
        """스텝 삽입 시그널 전달"""
        self.step_insert_requested.emit(after_step_id)

    def _on_step_move_up(self, step_id: int):
        """스텝 위로 이동 시그널 전달"""
        self.step_move_requested.emit(step_id, "up")

    def _on_step_move_down(self, step_id: int):
        """스텝 아래로 이동 시그널 전달"""
        self.step_move_requested.emit(step_id, "down")

    def _update_move_buttons(self):
        """이동 버튼 활성화/비활성화 업데이트"""
        for i, card in enumerate(self._step_cards):
            card.up_btn.setEnabled(i > 0)
            card.down_btn.setEnabled(i < len(self._step_cards) - 1)
        self._update_last_card()

    def _update_last_card(self):
        """마지막 스텝 카드에만 수정 버튼 표시"""
        for i, card in enumerate(self._step_cards):
            card.set_is_last(i == len(self._step_cards) - 1)

    def _remove_trailing_stretch(self):
        """레이아웃 끝의 stretch 제거"""
        if self.cards_layout.count() > 0:
            last = self.cards_layout.itemAt(self.cards_layout.count() - 1)
            if last and last.spacerItem():
                self.cards_layout.removeItem(last)

    def refresh_steps(self, steps_data: list[dict]):
        """
        전체 스텝 목록을 새로고침합니다.

        Args:
            steps_data: [{step_id, code, capture_path}, ...] 형태의 리스트
        """
        self.clear()

        for i, data in enumerate(steps_data):
            step_id = data.get("step_id", i + 1)
            code = data.get("code", "")
            capture = data.get("capture_path")
            self.add_step(step_id, code, capture)

    def clear(self):
        """모든 스텝 카드 제거"""
        self._step_cards.clear()
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards_layout.addStretch()
