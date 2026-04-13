"""
콘솔/로그 패널

프롬프트 로그, 실행 로그, AI 통신 로그를 탭으로 분리하여 표시합니다.
"""

from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QPlainTextEdit, QLabel
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor, QTextCursor, QTextCharFormat


class LogTextEdit(QPlainTextEdit):
    """로그 레벨별 색상이 적용되는 텍스트 에디터"""

    LEVEL_COLORS = {
        "DEBUG": "#6c7086",
        "INFO": "#a6e3a1",
        "WARNING": "#f9e2af",
        "ERROR": "#f38ba8",
        "PROMPT": "#89b4fa",
        "AI": "#cba6f7",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 10))
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #11111b;
                color: #a6adc8;
                border: none;
            }
        """)
        self.setMaximumBlockCount(5000)  # 최대 5000줄

    def contextMenuEvent(self, event):
        """컨텍스트 메뉴 - Copy를 Win32 API 폴백으로 처리"""
        menu = self.createStandardContextMenu()
        # Copy 액션을 Win32 API 폴백으로 교체
        for action in menu.actions():
            if action.text().startswith("&Copy") or action.text().startswith("복사"):
                action.triggered.disconnect()
                action.triggered.connect(self._copy_with_fallback)
                break
        menu.exec(event.globalPos())

    def _copy_with_fallback(self):
        """클립보드 복사 (크로스 플랫폼)"""
        text = self.textCursor().selectedText()
        if text:
            text = text.replace('\u2029', '\n')
            try:
                from PyQt6.QtWidgets import QApplication
                clipboard = QApplication.clipboard()
                clipboard.setText(text)
            except Exception:
                pass

    def append_log(self, text: str, level: str = "INFO"):
        """로그 메시지를 색상과 함께 추가"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = self.LEVEL_COLORS.get(level, "#a6adc8")

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # 타임스탬프
        ts_fmt = QTextCharFormat()
        ts_fmt.setForeground(QColor("#585b70"))
        cursor.insertText(f"[{timestamp}] ", ts_fmt)

        # 레벨
        level_fmt = QTextCharFormat()
        level_fmt.setForeground(QColor(color))
        level_fmt.setFontWeight(QFont.Weight.Bold)
        cursor.insertText(f"[{level}] ", level_fmt)

        # 내용
        content_fmt = QTextCharFormat()
        content_fmt.setForeground(QColor(color if level in ("ERROR", "WARNING") else "#cdd6f4"))
        cursor.insertText(f"{text}\n", content_fmt)

        self.setTextCursor(cursor)
        self.ensureCursorVisible()


class ConsolePanel(QWidget):
    """콘솔/로그 패널 (3탭)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 탭 위젯
        self.tabs = QTabWidget()

        # 1. 통합 로그
        self.all_log = LogTextEdit()
        self.tabs.addTab(self.all_log, "📟 전체 로그")

        # 2. 프롬프트 로그
        self.prompt_log = LogTextEdit()
        self.tabs.addTab(self.prompt_log, "💬 프롬프트")

        # 3. 실행 로그
        self.exec_log = LogTextEdit()
        self.tabs.addTab(self.exec_log, "▶ 실행")

        # 4. AI 통신 로그
        self.ai_log = LogTextEdit()
        self.tabs.addTab(self.ai_log, "🤖 AI 통신")

        layout.addWidget(self.tabs)

    def log(self, message: str, level: str = "INFO"):
        """로그 메시지 추가 (전체 로그에는 항상, 분류 탭에는 자동 분류)"""
        self.all_log.append_log(message, level)

        # 자동 분류
        if message.startswith("[PROMPT]") or "프롬프트" in message:
            self.prompt_log.append_log(message, "PROMPT")
        elif message.startswith("[AI]") or "AI" in message:
            self.ai_log.append_log(message, "AI")
        elif "실행" in message or "출력" in message:
            self.exec_log.append_log(message, level)

    def clear(self):
        """모든 로그 탭 초기화"""
        self.all_log.clear()
        self.prompt_log.clear()
        self.exec_log.clear()
        self.ai_log.clear()

    def log_prompt_detail(
        self,
        user_message: str,
        full_prompt: str,
        ai_response: str,
        code: str,
        tokens_used: int = 0,
        response_time_ms: int = 0,
        ai_engine: str = "",
        has_images: bool = False,
        element_info: str = ""
    ):
        """AI 대화 상세 로그를 프롬프트 탭에 구조화하여 표시"""
        cursor = self.prompt_log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 구분선
        separator_fmt = QTextCharFormat()
        separator_fmt.setForeground(QColor("#585b70"))
        cursor.insertText("\n" + "═" * 80 + "\n", separator_fmt)

        # 헤더
        header_fmt = QTextCharFormat()
        header_fmt.setForeground(QColor("#89dceb"))
        header_fmt.setFontWeight(QFont.Weight.Bold)
        cursor.insertText(f"📨 AI 대화 기록 [{timestamp}]\n", header_fmt)

        # 메타 정보
        meta_fmt = QTextCharFormat()
        meta_fmt.setForeground(QColor("#6c7086"))
        meta_info = f"   엔진: {ai_engine} | 응답시간: {response_time_ms}ms | 토큰: {tokens_used}"
        if has_images:
            meta_info += " | 📷 이미지 첨부"
        cursor.insertText(meta_info + "\n", meta_fmt)

        # 구분선
        cursor.insertText("─" * 80 + "\n", separator_fmt)

        # 선택된 요소 정보 (있으면)
        if element_info:
            element_label_fmt = QTextCharFormat()
            element_label_fmt.setForeground(QColor("#f9e2af"))
            element_label_fmt.setFontWeight(QFont.Weight.Bold)
            cursor.insertText("📌 선택된 요소:\n", element_label_fmt)

            element_content_fmt = QTextCharFormat()
            element_content_fmt.setForeground(QColor("#f9e2af"))
            cursor.insertText(f"{element_info}\n\n", element_content_fmt)

        # 사용자 메시지
        user_label_fmt = QTextCharFormat()
        user_label_fmt.setForeground(QColor("#a6e3a1"))
        user_label_fmt.setFontWeight(QFont.Weight.Bold)
        cursor.insertText("👤 사용자 요청:\n", user_label_fmt)

        user_content_fmt = QTextCharFormat()
        user_content_fmt.setForeground(QColor("#cdd6f4"))
        cursor.insertText(f"   {user_message}\n\n", user_content_fmt)

        # 전체 프롬프트 (접힌 형태로 표시 - 처음 500자만)
        prompt_label_fmt = QTextCharFormat()
        prompt_label_fmt.setForeground(QColor("#89b4fa"))
        prompt_label_fmt.setFontWeight(QFont.Weight.Bold)
        cursor.insertText(f"📋 AI에게 전송된 프롬프트 ({len(full_prompt)}자):\n", prompt_label_fmt)

        prompt_content_fmt = QTextCharFormat()
        prompt_content_fmt.setForeground(QColor("#7f849c"))
        # 프롬프트가 길면 처음 1000자 + 끝 500자 표시
        if len(full_prompt) > 2000:
            preview = full_prompt[:1000] + "\n\n   ... (중략) ...\n\n" + full_prompt[-500:]
        else:
            preview = full_prompt
        for line in preview.split('\n'):
            cursor.insertText(f"   {line}\n", prompt_content_fmt)
        cursor.insertText("\n", prompt_content_fmt)

        # AI 응답
        ai_label_fmt = QTextCharFormat()
        ai_label_fmt.setForeground(QColor("#cba6f7"))
        ai_label_fmt.setFontWeight(QFont.Weight.Bold)
        cursor.insertText("🤖 AI 응답:\n", ai_label_fmt)

        ai_content_fmt = QTextCharFormat()
        ai_content_fmt.setForeground(QColor("#cdd6f4"))
        for line in ai_response.split('\n'):
            cursor.insertText(f"   {line}\n", ai_content_fmt)
        cursor.insertText("\n", ai_content_fmt)

        # 생성된 코드 (있으면)
        if code:
            code_label_fmt = QTextCharFormat()
            code_label_fmt.setForeground(QColor("#f38ba8"))
            code_label_fmt.setFontWeight(QFont.Weight.Bold)
            cursor.insertText(f"💻 추출된 코드 ({len(code)}자):\n", code_label_fmt)

            code_content_fmt = QTextCharFormat()
            code_content_fmt.setForeground(QColor("#fab387"))
            cursor.insertText("   ```python\n", code_content_fmt)
            for line in code.split('\n'):
                cursor.insertText(f"   {line}\n", code_content_fmt)
            cursor.insertText("   ```\n", code_content_fmt)

        # 마무리 구분선
        cursor.insertText("═" * 80 + "\n\n", separator_fmt)

        self.prompt_log.setTextCursor(cursor)
        self.prompt_log.ensureCursorVisible()

        # 전체 로그에도 요약 추가
        self.all_log.append_log(
            f"[AI 대화] 요청: {user_message[:50]}... → 응답: {len(ai_response)}자, 코드: {len(code)}자",
            "AI"
        )
