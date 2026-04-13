"""
화면 영역 캡처 오버레이

전체 화면을 반투명으로 덮고, 마우스 드래그로 캡처 영역을 지정합니다.
선택 영역의 스크린샷을 저장합니다.
"""

import mss
from PIL import Image
from PyQt6.QtWidgets import QWidget, QApplication, QLabel
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QFont, QPixmap, QScreen,
    QMouseEvent, QPaintEvent, QKeyEvent
)


class ScreenCaptureOverlay(QWidget):
    """
    전체 화면 반투명 오버레이.

    사용법:
    1. show()로 표시
    2. 사용자가 마우스 드래그로 영역 선택
    3. 선택 완료 시 capture_completed 시그널 발생 (PIL Image 객체)
    4. ESC로 취소 시 capture_cancelled 시그널 발생
    """

    capture_completed = pyqtSignal(object)    # PIL Image 전달
    capture_cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # 전체 화면 프레임리스 윈도우
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # 상태 변수
        self._start_pos = QPoint()
        self._end_pos = QPoint()
        self._is_selecting = False
        self._background_pixmap: QPixmap = None

        # 안내 텍스트
        self._guide_text = "드래그하여 캡처 영역을 선택하세요  |  ESC: 취소  |  전체화면: Space"

    def start_capture(self):
        """캡처 모드를 시작합니다."""
        # 먼저 전체 화면 스크린샷을 배경으로 찍기
        QTimer.singleShot(150, self._take_background_and_show)

    def _take_background_and_show(self):
        """배경 스크린샷을 찍고 오버레이를 표시합니다."""
        try:
            # 전체 화면 스크린샷 (mss로 캡처)
            with mss.mss() as sct:
                monitor = sct.monitors[0]  # 전체 가상 스크린
                sct_img = sct.grab(monitor)

                # QPixmap으로 변환
                from PyQt6.QtGui import QImage
                img_data = bytes(sct_img.rgb)
                qimg = QImage(
                    img_data,
                    sct_img.width, sct_img.height,
                    sct_img.width * 3,
                    QImage.Format.Format_RGB888
                )
                # mss는 BGR 순서이므로 RGB로 교환
                qimg = qimg.rgbSwapped()
                self._background_pixmap = QPixmap.fromImage(qimg)

            # 전체 화면 크기로 설정
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.geometry()
                self.setGeometry(geo)

            self._start_pos = QPoint()
            self._end_pos = QPoint()
            self._is_selecting = False

            self.showFullScreen()
            self.activateWindow()
            self.raise_()

        except Exception as e:
            print(f"배경 캡처 실패: {e}")
            self.capture_cancelled.emit()

    def paintEvent(self, event: QPaintEvent):
        """오버레이 그리기"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # 1. 배경 (스크린샷)
        if self._background_pixmap:
            painter.drawPixmap(0, 0, self._background_pixmap.scaled(
                w, h, Qt.AspectRatioMode.IgnoreAspectRatio
            ))

        # 2. 반투명 어둡게 (선택 영역 제외)
        overlay_color = QColor(0, 0, 0, 120)

        if self._is_selecting and not self._start_pos.isNull() and not self._end_pos.isNull():
            selection = QRect(self._start_pos, self._end_pos).normalized()

            # 선택 영역 외의 4개 사각형을 어둡게
            # 상단
            painter.fillRect(0, 0, w, selection.top(), overlay_color)
            # 하단
            painter.fillRect(0, selection.bottom() + 1, w, h - selection.bottom() - 1, overlay_color)
            # 좌측
            painter.fillRect(0, selection.top(), selection.left(), selection.height(), overlay_color)
            # 우측
            painter.fillRect(selection.right() + 1, selection.top(),
                           w - selection.right() - 1, selection.height(), overlay_color)

            # 선택 영역 테두리
            pen = QPen(QColor(0, 170, 255), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(selection)

            # 선택 크기 표시
            size_text = f"{selection.width()} × {selection.height()}"
            painter.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
            painter.setPen(QColor(255, 255, 255))

            # 텍스트 배경
            text_rect = painter.fontMetrics().boundingRect(size_text)
            text_x = selection.center().x() - text_rect.width() // 2
            text_y = selection.bottom() + 22

            if text_y + text_rect.height() > h:
                text_y = selection.top() - 8

            bg_rect = QRect(text_x - 6, text_y - text_rect.height() - 2,
                          text_rect.width() + 12, text_rect.height() + 6)
            painter.fillRect(bg_rect, QColor(0, 0, 0, 180))
            painter.drawText(text_x, text_y, size_text)

        else:
            # 선택 전: 전체 반투명
            painter.fillRect(0, 0, w, h, overlay_color)

        # 3. 상단 안내 텍스트
        painter.setFont(QFont("Malgun Gothic", 13, QFont.Weight.Bold))
        painter.setPen(QColor(255, 255, 255))

        text_rect = painter.fontMetrics().boundingRect(self._guide_text)
        text_x = (w - text_rect.width()) // 2
        text_y = 40

        # 텍스트 배경
        bg = QRect(text_x - 16, text_y - text_rect.height() - 4,
                  text_rect.width() + 32, text_rect.height() + 12)
        painter.fillRect(bg, QColor(0, 0, 0, 200))
        painter.drawText(text_x, text_y, self._guide_text)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        """마우스 클릭: 선택 시작"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.pos()
            self._end_pos = event.pos()
            self._is_selecting = True
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        """마우스 이동: 선택 영역 업데이트"""
        if self._is_selecting:
            self._end_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """마우스 릴리스: 선택 완료"""
        if event.button() == Qt.MouseButton.LeftButton and self._is_selecting:
            self._end_pos = event.pos()
            self._is_selecting = False

            selection = QRect(self._start_pos, self._end_pos).normalized()

            # 최소 크기 체크 (10x10 이상)
            if selection.width() >= 10 and selection.height() >= 10:
                self._capture_region(selection)
            else:
                self.update()

    def keyPressEvent(self, event: QKeyEvent):
        """키 입력 처리"""
        if event.key() == Qt.Key.Key_Escape:
            # ESC: 취소
            self.hide()
            self.capture_cancelled.emit()
        elif event.key() == Qt.Key.Key_Space:
            # Space: 전체 화면 캡처
            screen_rect = QRect(0, 0, self.width(), self.height())
            self._capture_region(screen_rect)

    def _capture_region(self, selection: QRect):
        """선택 영역을 캡처합니다."""
        self.hide()

        try:
            with mss.mss() as sct:
                # 선택 영역을 모니터 좌표로 변환
                monitor = {
                    "left": selection.x(),
                    "top": selection.y(),
                    "width": selection.width(),
                    "height": selection.height()
                }

                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                self.capture_completed.emit(img)

        except Exception as e:
            print(f"영역 캡처 실패: {e}")
            self.capture_cancelled.emit()
