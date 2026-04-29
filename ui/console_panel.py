"""
콘솔/로그 패널

프롬프트 로그, 실행 로그, AI 통신 로그를 탭으로 분리하여 표시합니다.
"""

import sys
import ctypes
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QPlainTextEdit, QLabel,
    QToolTip, QApplication,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor, QTextCursor, QTextCharFormat, QCursor


def _win32_clipboard_copy(text: str) -> bool:
    """Win32 API 로 클립보드에 직접 복사 (Qt clipboard 폴백).

    Qt 의 OleSetClipboard 가 일부 환경 (RDP, VM, 보안 솔루션 등) 에서 조용히
    실패할 때 사용한다. main.py 의 _win32_copy 와 동일한 패턴이지만 console
    내부 폴백이라 인라인.

    Returns:
        True: SetClipboardData 가 NULL 이 아닌 핸들 반환 (성공)
        False: Windows 가 아니거나 어딘가에서 실패
    """
    if sys.platform != "win32":
        return False

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # 64bit Windows 에서 OverflowError/AV 방지를 위해 시그니처 명시
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = ctypes.c_bool
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = ctypes.c_bool

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        encoded = text.encode('utf-16-le') + b'\x00\x00'
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not h_mem:
            return False
        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            kernel32.GlobalFree(h_mem)
            return False
        ctypes.memmove(p_mem, encoded, len(encoded))
        kernel32.GlobalUnlock(h_mem)
        handle = user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        return bool(handle)
    finally:
        user32.CloseClipboard()


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

    MAX_LINES = 5000  # G.1.1: cap 도달 시 1회 경고용으로 명시 상수화

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
        self.setMaximumBlockCount(self.MAX_LINES)
        # G.1.1: cap 트렁케이션 가시화
        self._append_count = 0  # append_log 누적 호출 수
        self._truncation_warned = False  # cap 도달 시 1회만 경고

    def clear(self):
        """텍스트 초기화 + 트렁케이션 카운터 리셋"""
        super().clear()
        self._append_count = 0
        self._truncation_warned = False

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
        """선택 텍스트 클립보드 복사. 진짜 폴백 체인.

        1) Qt clipboard.setText → clipboard.text() 검증
        2) Win32 API 직접 호출 (Windows, 시도 1 실패 시)
        3) 모두 실패: ToolTip + WARNING 로그
        """
        text = self.textCursor().selectedText()
        if not text:
            return
        text = text.replace('\u2029', '\n')

        # \uc2dc\ub3c4 1: Qt clipboard
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            if clipboard.text() == text:
                return  # \uac80\uc99d\uae4c\uc9c0 \uc131\uacf5
        except Exception as e:
            print(f"[DEBUG] Qt clipboard.setText \uc2e4\ud328: {e}")

        # \uc2dc\ub3c4 2: Win32 \uc9c1\uc811 (Windows \uc804\uc6a9)
        if _win32_clipboard_copy(text):
            return

        # \ubaa8\ub450 \uc2e4\ud328 \u2014 \uc0ac\uc6a9\uc790\uc5d0\uac8c \uc54c\ub9bc
        QToolTip.showText(QCursor.pos(), "\u274c \ud074\ub9bd\ubcf4\ub4dc \ubcf5\uc0ac \uc2e4\ud328", self)
        self.append_log("\ud074\ub9bd\ubcf4\ub4dc \ubcf5\uc0ac \uc2e4\ud328 (Qt + Win32 \ubaa8\ub450 \uc2e4\ud328)", "WARNING")

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

        # G.1.1: cap 트렁케이션 1회 경고
        # _append_count 가 MAX_LINES 를 막 넘은 순간 = Qt 가 처음 1줄 트림한 시점
        self._append_count += 1
        if self._append_count > self.MAX_LINES and not self._truncation_warned:
            self._truncation_warned = True
            warn_cursor = self.textCursor()
            warn_cursor.movePosition(QTextCursor.MoveOperation.End)
            warn_fmt = QTextCharFormat()
            warn_fmt.setForeground(QColor(self.LEVEL_COLORS["WARNING"]))
            warn_fmt.setFontWeight(QFont.Weight.Bold)
            warn_cursor.insertText(
                f"[{datetime.now().strftime('%H:%M:%S')}] [WARNING] "
                f"⚠ {self.MAX_LINES}줄 cap 초과 — 오래된 로그가 잘리기 시작합니다 "
                f"(이후 silent)\n",
                warn_fmt,
            )
            self.setTextCursor(warn_cursor)
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
