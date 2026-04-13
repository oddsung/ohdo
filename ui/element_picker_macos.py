"""
macOS UI 요소 피커 (Element Picker)

macOS Accessibility API를 사용하여 마우스 아래의 UI 요소를 감지합니다.
투명 오버레이를 표시하고, 클릭 시 요소 정보를 수집하여 시그널로 전달합니다.

필요 권한: 시스템 설정 > 개인정보 보호 및 보안 > 손쉬운 사용에서 앱 허용
"""

import logging
import subprocess
from typing import Any
from PyQt6.QtWidgets import QWidget, QApplication, QLabel
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QPoint, QRect
)
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QFont, QCursor,
    QScreen, QGuiApplication
)

logger = logging.getLogger(__name__)

# macOS Accessibility API lazy import
_accessibility_available = False
_AX = None  # ApplicationServices 모듈 참조

try:
    import ApplicationServices as _AX
    _accessibility_available = True
except ImportError:
    pass

# 브라우저 앱 이름 매핑
BROWSER_APPS = {
    "Google Chrome", "Google Chrome Canary",
    "Microsoft Edge", "Firefox", "Safari",
    "Opera", "Brave Browser", "Arc",
    "Naver Whale", "Vivaldi",
}


def _get_element_at_position(x: float, y: float):
    """macOS Accessibility API로 화면 좌표의 UI 요소를 가져옵니다."""
    if not _accessibility_available:
        return None

    try:
        system_element = _AX.AXUIElementCreateSystemWide()
        err, element = _AX.AXUIElementCopyElementAtPosition(
            system_element, x, y, None
        )
        if err == 0 and element:
            return element
    except Exception as e:
        logger.debug(f"AX 요소 감지 실패: {e}")
    return None


def _get_ax_attribute(element, attribute: str, default=None):
    """AX 요소의 속성값을 안전하게 가져옵니다."""
    try:
        err, value = _AX.AXUIElementCopyAttributeValue(element, attribute, None)
        if err == 0 and value is not None:
            return value
    except Exception:
        pass
    return default


def _get_ax_position(element) -> tuple[int, int]:
    """AX 요소의 화면 좌표를 가져옵니다."""
    try:
        pos = _get_ax_attribute(element, "AXPosition")
        if pos:
            point = _AX.AXValueGetValue(pos, _AX.kAXValueCGPointType, None)
            if point:
                return int(point[1].x), int(point[1].y)
    except Exception:
        pass
    return 0, 0


def _get_ax_size(element) -> tuple[int, int]:
    """AX 요소의 크기를 가져옵니다."""
    try:
        size = _get_ax_attribute(element, "AXSize")
        if size:
            sz = _AX.AXValueGetValue(size, _AX.kAXValueCGSizeType, None)
            if sz:
                return int(sz[1].width), int(sz[1].height)
    except Exception:
        pass
    return 0, 0


def _get_app_name_for_element(element) -> str:
    """요소가 속한 앱 이름을 가져옵니다."""
    try:
        current = element
        visited = set()
        for _ in range(30):
            role = _get_ax_attribute(current, "AXRole", "")
            if role == "AXApplication":
                return _get_ax_attribute(current, "AXTitle", "") or ""
            eid = id(current)
            if eid in visited:
                break
            visited.add(eid)
            parent = _get_ax_attribute(current, "AXParent")
            if parent is None:
                break
            current = parent
    except Exception:
        pass
    return ""


def _get_pid_for_element(element) -> int:
    """요소의 프로세스 ID를 가져옵니다."""
    try:
        err, pid = _AX.AXUIElementGetPid(element, None)
        if err == 0:
            return pid
    except Exception:
        pass
    return 0


class ElementPickerOverlay(QWidget):
    """
    macOS UI 요소 피커 오버레이.

    전체 화면 투명 오버레이를 표시하고, 마우스 아래의 UI 요소를
    빨간 사각형으로 하이라이트합니다. 클릭 시 요소 정보를 수집합니다.

    Signals:
        element_picked(dict): 선택된 요소 정보
        pick_cancelled(): 선택 취소
    """

    element_picked = pyqtSignal(dict)
    pick_cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._highlight_rect = QRect()
        self._element_info_text = ""
        self._current_element_info: dict = {}

        # 마우스 추적 타이머
        self._track_timer = QTimer(self)
        self._track_timer.timeout.connect(self._update_element_under_cursor)
        self._track_interval = 100

        # 툴팁 라벨
        self._info_label = QLabel(self)
        self._info_label.setStyleSheet("""
            QLabel {
                background-color: rgba(17, 17, 27, 220);
                color: #cdd6f4;
                border: 1px solid #89b4fa;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 11px;
            }
        """)
        self._info_label.setFont(QFont("Menlo", 10))
        self._info_label.hide()

    def start_picking(self):
        """요소 선택 시작"""
        if not _accessibility_available:
            logger.error("macOS Accessibility API를 사용할 수 없습니다")
            self.pick_cancelled.emit()
            return

        # 접근성 권한 확인
        try:
            trusted = _AX.AXIsProcessTrusted()
            if not trusted:
                logger.warning("접근성 권한이 필요합니다. 시스템 설정에서 허용해주세요.")
                subprocess.run([
                    "osascript", "-e",
                    'display dialog "접근성 권한이 필요합니다.\\n시스템 설정 > 개인정보 보호 및 보안 > 손쉬운 사용에서 이 앱을 허용해주세요." buttons {"확인"} default button 1'
                ], timeout=10)
                self.pick_cancelled.emit()
                return
        except Exception:
            pass

        # 전체 화면 크기 설정
        screens = QGuiApplication.screens()
        if not screens:
            self.pick_cancelled.emit()
            return

        virtual_geo = screens[0].virtualGeometry()
        self.setGeometry(virtual_geo)

        self.show()
        self.raise_()
        self.activateWindow()

        self._highlight_rect = QRect()
        self._element_info_text = ""

        self._track_timer.start(self._track_interval)
        logger.info("macOS UI 요소 피커 시작")

    def stop_picking(self):
        """선택 중단"""
        self._track_timer.stop()
        self._info_label.hide()
        self.hide()

    def _update_element_under_cursor(self):
        """커서 아래의 UI 요소를 감지하고 하이라이트"""
        try:
            cursor_pos = QCursor.pos()
            x, y = cursor_pos.x(), cursor_pos.y()

            # macOS Accessibility API로 요소 감지
            # 오버레이를 잠시 숨겨서 자기 자신이 감지되지 않도록 함
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            element = _get_element_at_position(float(x), float(y))
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

            if element:
                try:
                    ex, ey = _get_ax_position(element)
                    ew, eh = _get_ax_size(element)

                    if ew > 0 and eh > 0:
                        # 로컬 좌표로 변환
                        local_pos = self.mapFromGlobal(QPoint(ex, ey))
                        self._highlight_rect = QRect(
                            local_pos.x(), local_pos.y(), ew, eh
                        )

                        # 요소 정보 수집
                        role = _get_ax_attribute(element, "AXRole", "") or ""
                        subrole = _get_ax_attribute(element, "AXSubrole", "") or ""
                        title = _get_ax_attribute(element, "AXTitle", "") or ""
                        description = _get_ax_attribute(element, "AXDescription", "") or ""
                        value = _get_ax_attribute(element, "AXValue", "")
                        role_desc = _get_ax_attribute(element, "AXRoleDescription", "") or ""
                        identifier = _get_ax_attribute(element, "AXIdentifier", "") or ""

                        # 앱 이름과 브라우저 판별
                        app_name = _get_app_name_for_element(element)
                        is_browser = app_name in BROWSER_APPS
                        browser_type = app_name if is_browser else ""

                        pid = _get_pid_for_element(element)

                        # control_type 매핑 (AXRole → 표시 이름)
                        role_map = {
                            "AXButton": "Button",
                            "AXTextField": "TextField",
                            "AXTextArea": "TextArea",
                            "AXStaticText": "Text",
                            "AXImage": "Image",
                            "AXCheckBox": "CheckBox",
                            "AXRadioButton": "RadioButton",
                            "AXPopUpButton": "PopUpButton",
                            "AXComboBox": "ComboBox",
                            "AXSlider": "Slider",
                            "AXTable": "Table",
                            "AXRow": "Row",
                            "AXCell": "Cell",
                            "AXList": "List",
                            "AXMenu": "Menu",
                            "AXMenuItem": "MenuItem",
                            "AXMenuBar": "MenuBar",
                            "AXToolbar": "Toolbar",
                            "AXGroup": "Group",
                            "AXScrollArea": "ScrollArea",
                            "AXWindow": "Window",
                            "AXSheet": "Sheet",
                            "AXDialog": "Dialog",
                            "AXTabGroup": "TabGroup",
                            "AXLink": "Link",
                            "AXWebArea": "WebArea",
                        }
                        ctrl_type = role_map.get(role, role.replace("AX", ""))

                        name = title or description or ""
                        if not name and value and isinstance(value, str):
                            name = value[:100]

                        self._current_element_info = {
                            "control_type": ctrl_type,
                            "name": (name or "")[:200],
                            "automation_id": identifier,
                            "class_name": role,
                            "subrole": subrole,
                            "role_description": role_desc,
                            "rect": {
                                "left": ex,
                                "top": ey,
                                "right": ex + ew,
                                "bottom": ey + eh,
                                "width": ew,
                                "height": eh
                            },
                            "parent_window_title": app_name,
                            "parent_window_class": "",
                            "screen_x": x,
                            "screen_y": y,
                            "detected_backend": "accessibility",
                            "recommended_backend": "applescript",
                            "is_browser": is_browser,
                            "browser_type": browser_type,
                            "_pid": pid,
                        }

                        # 정보 텍스트 생성
                        if is_browser:
                            lines = [f"[{browser_type} 브라우저] [{ctrl_type}]"]
                        else:
                            lines = [f"[macOS] [{ctrl_type}]"]
                        if name:
                            lines[0] += f' "{name[:50]}"'
                        if identifier:
                            lines.append(f"ID: {identifier}")
                        if app_name:
                            lines.append(f"App: {app_name}")
                        lines.append(f"위치: ({ex},{ey}) {ew}x{eh}")
                        if is_browser:
                            lines.append(f"코드: Selenium ({browser_type})")
                        else:
                            lines.append("코드: AppleScript")

                        self._element_info_text = "\n".join(lines)

                        # 툴팁 라벨 위치
                        cursor_local = self.mapFromGlobal(cursor_pos)
                        self._info_label.setText(self._element_info_text)
                        self._info_label.adjustSize()

                        label_x = cursor_local.x() + 15
                        label_y = cursor_local.y() + 15
                        if label_x + self._info_label.width() > self.width():
                            label_x = cursor_local.x() - self._info_label.width() - 5
                        if label_y + self._info_label.height() > self.height():
                            label_y = cursor_local.y() - self._info_label.height() - 5

                        self._info_label.move(label_x, label_y)
                        self._info_label.show()

                    else:
                        self._highlight_rect = QRect()

                except Exception as e:
                    logger.debug(f"요소 정보 수집 실패: {e}")
                    self._highlight_rect = QRect()
            else:
                self._highlight_rect = QRect()
                self._info_label.hide()

            self.update()

        except Exception as e:
            logger.debug(f"요소 감지 실패: {e}")

    def paintEvent(self, event):
        """하이라이트 사각형 그리기"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 반투명 배경
        painter.fillRect(self.rect(), QColor(0, 0, 0, 30))

        # 하이라이트 사각형
        if not self._highlight_rect.isNull():
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(self._highlight_rect, Qt.GlobalColor.transparent)

            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen = QPen(QColor("#f38ba8"), 3)
            painter.setPen(pen)
            painter.drawRect(self._highlight_rect)

            painter.fillRect(
                self._highlight_rect,
                QColor(243, 139, 168, 30)
            )

        # 상단 안내 문구
        painter.setPen(QColor("#cdd6f4"))
        painter.setFont(QFont("Apple SD Gothic Neo", 14, QFont.Weight.Bold))
        guide_text = "🎯 클릭하여 UI 요소 선택  |  ESC: 취소"
        painter.drawText(
            self.rect().adjusted(0, 20, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            guide_text
        )

        painter.end()

    def mousePressEvent(self, event):
        """클릭 시 요소 선택 완료"""
        if event.button() == Qt.MouseButton.LeftButton:
            element_info = self._current_element_info.copy() if self._current_element_info else {}
            self.stop_picking()
            if element_info:
                self._log_element_details(element_info)
                self.element_picked.emit(element_info)
            else:
                self.pick_cancelled.emit()
        elif event.button() == Qt.MouseButton.RightButton:
            self.stop_picking()
            self.pick_cancelled.emit()

    def keyPressEvent(self, event):
        """ESC로 취소"""
        if event.key() == Qt.Key.Key_Escape:
            self.stop_picking()
            self.pick_cancelled.emit()

    def _log_element_details(self, element_info: dict):
        """선택된 요소의 상세 정보를 로그에 출력"""
        sep = "=" * 70
        logger.info(sep)

        is_browser = element_info.get("is_browser", False)
        browser_type = element_info.get("browser_type", "")
        if is_browser:
            logger.info(f"  UI 요소 선택 완료 - [{browser_type} 브라우저] Selenium 코드 생성")
        else:
            logger.info("  UI 요소 선택 완료 - [macOS 앱] AppleScript 코드 생성")

        logger.info(sep)
        logger.info(f"  [선택된 요소 속성]")
        logger.info(f"    control_type : {element_info.get('control_type', '')}")
        logger.info(f"    name         : \"{element_info.get('name', '')}\"")
        logger.info(f"    class_name   : {element_info.get('class_name', '')}")
        logger.info(f"    subrole      : {element_info.get('subrole', '')}")
        logger.info(f"    automation_id: {element_info.get('automation_id', '') or '(없음)'}")

        r = element_info.get("rect", {})
        if r:
            logger.info(
                f"    rect         : ({r.get('left')},{r.get('top')}) "
                f"~ ({r.get('right')},{r.get('bottom')})  "
                f"크기:{r.get('width')}×{r.get('height')}"
            )
        logger.info(f"    앱 이름      : {element_info.get('parent_window_title', '')}")
        logger.info(f"    화면 좌표    : ({element_info.get('screen_x')}, {element_info.get('screen_y')})")
        logger.info(sep)
