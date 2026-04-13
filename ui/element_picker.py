"""
UI 요소 피커 (Element Picker)

투명 오버레이를 표시하고, 마우스 아래의 UI 요소를 실시간으로 하이라이트합니다.
사용자가 클릭하면 해당 요소의 정보를 수집하여 시그널로 전달합니다.
"""

import logging
import sys
import ctypes
if sys.platform == "win32":
    import ctypes.wintypes
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

if sys.platform == "win32":
    user32 = ctypes.windll.user32  # type: ignore
    kernel32 = ctypes.windll.kernel32  # type: ignore
else:
    user32 = None
    kernel32 = None

# Win32 상수
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
HWND_TOPMOST = -1
VK_F3 = 0x72
VK_ESCAPE = 0x1B

# pywinauto lazy import
_pywinauto_available = False
try:
    from pywinauto import Desktop
    import pywinauto
    _pywinauto_available = True
except ImportError:
    pass

# 브라우저 프로세스명 → 브라우저 이름 매핑
BROWSER_PROCESSES: dict[str, str] = {
    "chrome.exe":          "Chrome",
    "msedge.exe":          "Edge",
    "firefox.exe":         "Firefox",
    "iexplore.exe":        "IE",
    "opera.exe":           "Opera",
    "brave.exe":           "Brave",
    "whale.exe":           "Whale",    # 네이버 웨일
    "vivaldi.exe":         "Vivaldi",
    "arc.exe":             "Arc",
}

# 브라우저 최상위 창 클래스명 → 브라우저 이름 (프로세스명 미확인 시 보조 판단)
BROWSER_WINDOW_CLASSES: dict[str, str] = {
    "Chrome_WidgetWin_1":           "Chrome/Edge",
    "MozillaWindowClass":           "Firefox",
    "IEFrame":                      "IE",
    "OperaWindowClass":             "Opera",
    "ApplicationFrameWindow":       "",  # UWP 앱 (브라우저 아님)
}


class ElementPickerOverlay(QWidget):
    """
    UI 요소 피커 오버레이.

    전체 화면 투명 오버레이를 표시하고, 마우스 아래의 UI 요소를
    빨간 사각형으로 하이라이트합니다. 클릭 시 요소 정보를 수집합니다.

    Signals:
        element_picked(dict): 선택된 요소 정보 (control_type, name, automation_id, rect 등)
        pick_cancelled(): 선택 취소
    """

    element_picked = pyqtSignal(dict)
    pick_cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # 윈도우 설정: 전체 화면 투명 레이어
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # 현재 하이라이트 영역
        self._highlight_rect = QRect()
        self._element_info_text = ""
        self._current_element_info: dict = {}
        self._current_element_ref = None  # 선택된 요소 레퍼런스 (계층 수집용)

        # 마우스 추적 타이머
        self._track_timer = QTimer(self)
        self._track_timer.timeout.connect(self._update_element_under_cursor)
        self._track_interval = 100  # 100ms마다 업데이트

        # 일시정지 상태
        self._paused = False
        self._pause_countdown = 0
        self._post_pause_mode = False  # F3 복귀 후 요소 감지 전용 모드

            # 디버그용: 현재 모니터 정보
        self._current_screen_info = ""
        self._cursor_local_pos = QPoint()  # 커서의 오버레이 로컬 좌표 (디버그용)

        # 툴팁 라벨 (요소 정보 표시)
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
        self._info_label.setFont(QFont("Consolas", 10))
        self._info_label.hide()

        # 일시정지 카운트다운 라벨 (화면 중앙)
        self._pause_label = QLabel()
        self._pause_label.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self._pause_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._pause_label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 210);
                color: white;
                font-family: 'Malgun Gothic';
                font-size: 14px;
                font-weight: bold;
                padding: 10px 24px;
                border-radius: 8px;
            }
        """)
        self._pause_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pause_label.hide()

    def start_picking(self):
        """요소 선택 시작 - 전체 화면 오버레이 표시"""
        if not _pywinauto_available:
            logger.error("pywinauto가 없어 요소 선택을 시작할 수 없습니다")
            self.pick_cancelled.emit()
            return

        # Qt 논리 좌표 기반으로 모든 모니터를 포괄하는 가상 화면 계산
        screens = QGuiApplication.screens()
        if not screens:
            self.pick_cancelled.emit()
            return

        # 디버그: Win32 가상 화면 정보 (물리 좌표)
        vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

        logger.info("=" * 60)
        logger.info(f"Win32 가상화면 (물리): ({vx},{vy}) 크기:{vw}x{vh}")

        # 디버그: 각 모니터 정보 출력 (geometry와 virtualGeometry 비교)
        logger.info("Qt 모니터 설정 정보:")
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            vgeo = screen.virtualGeometry()
            dpr = screen.devicePixelRatio()
            logger.info(
                f"  모니터 {i}: {screen.name()} | "
                f"geometry:({geo.x()},{geo.y()}) {geo.width()}x{geo.height()} | "
                f"virtualGeo:({vgeo.x()},{vgeo.y()}) {vgeo.width()}x{vgeo.height()} | "
                f"배율:{dpr}"
            )

        # 방법 1: Qt virtualGeometry 사용 (가상 데스크톱 전체)
        virtual_geo = screens[0].virtualGeometry()
        logger.info(
            f"Qt virtualGeometry: ({virtual_geo.x()},{virtual_geo.y()}) "
            f"크기:{virtual_geo.width()}x{virtual_geo.height()}"
        )

        # 방법 2: 명시적으로 모든 스크린의 바운딩 박스 계산
        min_x = min(s.geometry().x() for s in screens)
        min_y = min(s.geometry().y() for s in screens)
        max_x = max(s.geometry().x() + s.geometry().width() for s in screens)
        max_y = max(s.geometry().y() + s.geometry().height() for s in screens)

        logger.info(
            f"명시적 계산: ({min_x},{min_y}) ~ ({max_x},{max_y}) "
            f"크기:{max_x - min_x}x{max_y - min_y}"
        )

        # 방법 3: Win32 물리 좌표를 그대로 사용 (Qt가 DPI 처리)
        # PyQt6는 기본적으로 DPI-aware이므로 물리 좌표를 직접 사용하면
        # Qt가 내부적으로 변환함
        logger.info(
            f"Win32 물리 좌표 직접 사용: ({vx},{vy}) 크기:{vw}x{vh}"
        )

        # 가장 큰 영역 선택 (세 방법 중 가장 큰 것)
        candidates = [
            (virtual_geo.x(), virtual_geo.y(),
             virtual_geo.x() + virtual_geo.width(), virtual_geo.y() + virtual_geo.height()),
            (min_x, min_y, max_x, max_y),
            (vx, vy, vx + vw, vy + vh),  # Win32 물리 좌표
        ]

        final_x = min(c[0] for c in candidates)
        final_y = min(c[1] for c in candidates)
        final_right = max(c[2] for c in candidates)
        final_bottom = max(c[3] for c in candidates)

        virtual_rect = QRect(final_x, final_y, final_right - final_x, final_bottom - final_y)

        logger.info(
            f"최종 오버레이 영역: ({virtual_rect.x()},{virtual_rect.y()}) "
            f"크기:{virtual_rect.width()}x{virtual_rect.height()}"
        )
        logger.info("=" * 60)

        # 크기 제한 해제 후 geometry 설정
        self.setMinimumSize(1, 1)
        self.setMaximumSize(16777215, 16777215)  # QWIDGETSIZE_MAX
        self.setGeometry(virtual_rect)

        # geometry 설정 후 실제 크기 확인
        actual_geo = self.geometry()
        if actual_geo != virtual_rect:
            logger.warning(
                f"Geometry 불일치! 요청:{virtual_rect.width()}x{virtual_rect.height()} → "
                f"실제:{actual_geo.width()}x{actual_geo.height()}"
            )
            # 강제 크기 재설정 시도
            self.resize(virtual_rect.width(), virtual_rect.height())
            self.move(virtual_rect.x(), virtual_rect.y())

        self.show()
        self.raise_()
        self.activateWindow()

        # show() 후 다시 크기 확인
        shown_geo = self.geometry()
        logger.info(
            f"show() 후 실제 geometry: ({shown_geo.x()},{shown_geo.y()}) "
            f"크기:{shown_geo.width()}x{shown_geo.height()}"
        )

        # 각 모니터의 논리 좌표 상세 로그
        logger.info("각 모니터 논리 좌표 상세:")
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            dpr = screen.devicePixelRatio()
            phys_w = int(geo.width() * dpr)
            phys_h = int(geo.height() * dpr)
            logger.info(
                f"  모니터 {i}: 논리({geo.x()},{geo.y()})~({geo.x()+geo.width()},{geo.y()+geo.height()}) | "
                f"논리크기:{geo.width()}x{geo.height()} | 물리크기:{phys_w}x{phys_h} | 배율:{dpr}"
            )

        self._highlight_rect = QRect()
        self._element_info_text = ""
        self._paused = False
        self._pause_countdown = 0
        self._cursor_local_pos = QPoint()
        self._current_screen_info = ""
        self._paint_logged = False  # 디버그 로깅 초기화

        # 마우스 추적 시작
        self._track_timer.start(self._track_interval)
        logger.info("UI 요소 피커 시작")

    def stop_picking(self):
        """선택 중단"""
        self._track_timer.stop()
        self._info_label.hide()
        self._pause_label.hide()
        self._paused = False
        if self._post_pause_mode:
            self._exit_post_pause_mode()
        self._current_element_ref = None
        self.hide()

    def _get_screen_for_physical_point(self, phys_x: int, phys_y: int) -> tuple[QScreen, float]:
        """
        물리 좌표가 위치한 모니터와 DPI 배율을 찾아 반환합니다.

        멀티모니터 환경에서 각 모니터별 DPI 배율이 다를 수 있으므로,
        물리 좌표를 각 모니터의 논리 좌표 범위로 변환하여 비교합니다.

        Returns:
            tuple: (QScreen, scale) - 해당 모니터와 DPI 배율
        """
        screens = QGuiApplication.screens()

        # 각 스크린별로 물리 좌표가 해당 스크린 영역 내에 있는지 확인
        for screen in screens:
            geo = screen.geometry()  # 논리 좌표
            dpr = screen.devicePixelRatio()

            # 이 스크린의 논리 좌표 범위 확인
            # 물리 좌표를 이 스크린의 DPI로 논리 좌표로 변환
            logical_x = phys_x / dpr
            logical_y = phys_y / dpr

            # 논리 좌표가 이 스크린의 geometry 내에 있는지 확인
            if (geo.x() <= logical_x < geo.x() + geo.width() and
                geo.y() <= logical_y < geo.y() + geo.height()):
                return screen, dpr

        # 찾지 못한 경우: 커서 위치 기반으로 스크린 찾기 (fallback)
        cursor_pos = QCursor.pos()
        screen_at_cursor = QGuiApplication.screenAt(cursor_pos)
        if screen_at_cursor:
            return screen_at_cursor, screen_at_cursor.devicePixelRatio()

        # 최후의 fallback: 주 모니터
        primary = QGuiApplication.primaryScreen()
        return primary, primary.devicePixelRatio() if primary else 1.0

    def _detect_element_multi_backend(self, x_phys: int, y_phys: int):
        """
        다중 백엔드를 사용하여 커서 위치의 UI 요소를 감지합니다.

        순서: UIA → Win32 → Win32 API (WindowFromPoint)

        Returns:
            tuple: (element, backend_name) 또는 (None, None)
        """
        # 오버레이를 hit-test에서 일시 제외
        hwnd = int(self.winId())
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_TRANSPARENT)

        element = None
        backend_used = None

        try:
            # 1순위: UIA 백엔드 (WPF, Qt, 브라우저 등 모던 앱)
            try:
                desktop_uia = Desktop(backend='uia')
                element = desktop_uia.from_point(x_phys, y_phys)
                if element:
                    # 유효한 요소인지 확인 (rectangle이 있어야 함)
                    try:
                        rect = element.rectangle()
                        if rect.width() > 0 and rect.height() > 0:
                            backend_used = "uia"
                            return element, backend_used
                    except Exception:
                        element = None
            except Exception as e:
                logger.debug(f"UIA 백엔드 실패: {e}")

            # 2순위: Win32 백엔드 (MFC, VB6, 레거시 앱)
            try:
                desktop_win32 = Desktop(backend='win32')
                element = desktop_win32.from_point(x_phys, y_phys)
                if element:
                    try:
                        rect = element.rectangle()
                        if rect.width() > 0 and rect.height() > 0:
                            backend_used = "win32"
                            return element, backend_used
                    except Exception:
                        element = None
            except Exception as e:
                logger.debug(f"Win32 백엔드 실패: {e}")

            # 3순위: Win32 API 직접 사용 (WindowFromPoint → 가장 깊은 창)
            try:
                element, backend_used = self._detect_element_win32_api(x_phys, y_phys)
                if element:
                    return element, backend_used
            except Exception as e:
                logger.debug(f"Win32 API 직접 감지 실패: {e}")

        finally:
            # 오버레이 스타일 복원
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

        return None, None

    def _detect_element_win32_api(self, x_phys: int, y_phys: int):
        """
        Win32 API를 직접 사용하여 요소를 감지합니다.
        WindowFromPoint로 창을 찾고, pywinauto로 래핑합니다.
        """
        # WindowFromPoint: 가장 깊은 창 반환
        pt = ctypes.wintypes.POINT(x_phys, y_phys)
        target_hwnd = user32.WindowFromPoint(pt)

        if not target_hwnd:
            return None, None

        # ChildWindowFromPointEx로 더 정밀한 자식 창 탐색
        # 클라이언트 좌표로 변환 필요 (ChildWindowFromPointEx는 클라이언트 좌표 사용)
        client_pt = ctypes.wintypes.POINT(x_phys, y_phys)
        user32.ScreenToClient(target_hwnd, ctypes.byref(client_pt))
        # CWP_SKIPINVISIBLE(1) | CWP_SKIPDISABLED(2) = 3
        child_hwnd = user32.ChildWindowFromPointEx(
            target_hwnd, client_pt, 3
        )
        if child_hwnd and child_hwnd != target_hwnd:
            target_hwnd = child_hwnd

        # pywinauto로 래핑 시도
        try:
            from pywinauto import Desktop
            # UIA로 먼저 시도
            try:
                desktop = Desktop(backend='uia')
                element = desktop.from_handle(target_hwnd)
                if element:
                    return element, "win32api+uia"
            except Exception:
                pass

            # Win32로 시도
            try:
                desktop = Desktop(backend='win32')
                element = desktop.from_handle(target_hwnd)
                if element:
                    return element, "win32api+win32"
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Win32 API 요소 래핑 실패: {e}")

        return None, None

    def _update_element_under_cursor(self):
        """커서 아래의 UI 요소를 감지하고 하이라이트"""
        if not _pywinauto_available:
            return

        try:
            # Win32 물리 좌표 (pywinauto 요소 감지용)
            pt_phys = ctypes.wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt_phys))
            x_phys, y_phys = pt_phys.x, pt_phys.y

            # Qt 논리 좌표 (오버레이 로컬 좌표 계산용)
            cursor_logical = QCursor.pos()
            x_log, y_log = cursor_logical.x(), cursor_logical.y()

            # 다중 백엔드로 요소 감지
            element, backend_used = self._detect_element_multi_backend(x_phys, y_phys)

            if element:
                try:
                    rect = element.rectangle()

                    # 커서가 위치한 모니터 정보 가져오기
                    cursor_screen = QGuiApplication.screenAt(cursor_logical)
                    if not cursor_screen:
                        cursor_screen = QGuiApplication.primaryScreen()

                    scale = cursor_screen.devicePixelRatio()

                    # ===== 새로운 접근법: mapFromGlobal 사용 =====
                    # Qt의 mapFromGlobal은 DPI 스케일링을 자동 처리함
                    cursor_local = self.mapFromGlobal(cursor_logical)

                    # 커서의 물리-논리 좌표 비율로 요소 좌표 변환
                    # 커서: 물리(x_phys, y_phys) -> 로컬(cursor_local.x(), cursor_local.y())
                    # 이 비율을 사용하여 요소 좌표도 변환
                    if cursor_local.x() != 0 and x_phys != 0:
                        ratio_x = cursor_local.x() / x_phys
                    else:
                        ratio_x = 1.0 / scale

                    if cursor_local.y() != 0 and y_phys != 0:
                        ratio_y = cursor_local.y() / y_phys
                    else:
                        ratio_y = 1.0 / scale

                    # 요소의 물리 좌표를 위젯 로컬 좌표로 변환
                    local_x = int(rect.left * ratio_x)
                    local_y = int(rect.top * ratio_y)
                    local_w = max(1, int(rect.width() * ratio_x))
                    local_h = max(1, int(rect.height() * ratio_y))

                    # 커서 위치 저장 (디버그용)
                    self._cursor_local_pos = cursor_local

                    # 디버그: 상세 계산 정보 저장 (사용된 백엔드 포함)
                    ovr_geo = self.geometry()
                    self._current_screen_info = (
                        f"백엔드:{backend_used or 'N/A'} | "
                        f"배율:{scale:.2f} | "
                        f"커서:({cursor_local.x()},{cursor_local.y()})"
                    )
                    self._highlight_rect = QRect(local_x, local_y, local_w, local_h)

                    # 요소 정보 수집
                    ctrl_type = ""
                    auto_id = ""
                    name = element.window_text() or ""

                    try:
                        ctrl_type = element.element_info.control_type or ""
                    except Exception:
                        ctrl_type = element.class_name() or ""

                    try:
                        auto_id = element.element_info.automation_id or ""
                    except Exception:
                        pass

                    # 부모 윈도우 정보
                    parent_title = ""
                    parent_class = ""
                    try:
                        top = element.top_level_parent()
                        if top:
                            parent_title = top.window_text() or ""
                            parent_class = top.class_name() or ""
                    except Exception:
                        pass

                    # 감지에 사용된 백엔드 기반으로 권장 백엔드 결정
                    # win32 계열로 감지된 경우 win32 백엔드 권장
                    if backend_used and "win32" in backend_used:
                        recommended_backend = "win32"
                    else:
                        recommended_backend = "uia"

                    # 프로세스 ID + 브라우저 판별
                    pid = 0
                    try:
                        pid = element.process_id()
                    except Exception:
                        pass

                    browser_type = self._detect_browser(pid, element)
                    is_browser = bool(browser_type)

                    # 브라우저 요소: 로케이터 후보 목록 (안정성 우선순위)
                    locator_candidates: list[tuple[str, str]] = []
                    if is_browser:
                        if auto_id:
                            locator_candidates.append(("id", auto_id))
                        if name:
                            # UIA accessible name = title 속성 또는 텍스트 (브라우저에서)
                            locator_candidates.append(("title", name[:200]))
                            locator_candidates.append(("text", name[:200]))

                    self._current_element_ref = element  # 계층 수집용 레퍼런스 보관
                    self._current_element_info = {
                        "control_type": ctrl_type,
                        "name": name[:200],
                        "automation_id": auto_id,
                        "class_name": element.class_name() if hasattr(element, 'class_name') else "",
                        "rect": {
                            "left": rect.left,
                            "top": rect.top,
                            "right": rect.right,
                            "bottom": rect.bottom,
                            "width": rect.width(),
                            "height": rect.height()
                        },
                        "parent_window_title": parent_title,
                        "parent_window_class": parent_class,
                        "screen_x": x_phys,
                        "screen_y": y_phys,
                        # 백엔드 정보 (AI 코드 생성 시 활용)
                        "detected_backend": backend_used or "uia",
                        "recommended_backend": recommended_backend,
                        # 브라우저 여부 (Selenium vs pywinauto 분기용)
                        "is_browser": is_browser,
                        "browser_type": browser_type,
                        # 브라우저 요소 로케이터 후보 (find_and_click용, 안정성 우선순위)
                        "locator_candidates": locator_candidates,
                        # 프로세스 정보 (로깅용)
                        "_pid": pid,
                    }

                    # 정보 텍스트 생성
                    if is_browser:
                        lines = [f"[{browser_type} 브라우저] [{ctrl_type}]"]
                    else:
                        lines = [f"[데스크톱] [{ctrl_type}]"]
                    if name:
                        lines[0] += f' "{name[:50]}"'
                    if auto_id:
                        lines.append(f"ID: {auto_id}")
                    if parent_title:
                        lines.append(f"Window: {parent_title[:40]}")
                    lines.append(f"위치: ({rect.left},{rect.top}) {rect.width()}x{rect.height()}")
                    if is_browser:
                        lines.append(f"코드: Selenium ({browser_type})")
                    else:
                        lines.append(f"백엔드: {backend_used or 'uia'} → 권장: {recommended_backend}")

                    self._element_info_text = "\n".join(lines)

                    # 툴팁 라벨: 논리 커서 좌표를 오버레이 로컬 좌표로 변환
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

                except Exception as e:
                    logger.debug(f"요소 정보 수집 실패: {e}")
                    self._highlight_rect = QRect()

            self.update()  # 다시 그리기

        except Exception as e:
            logger.debug(f"요소 감지 실패: {e}")

    def paintEvent(self, event):
        """하이라이트 사각형 그리기"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 디버그: 실제 위젯 크기 로그 (첫 번째 페인트 이벤트에서만)
        if not hasattr(self, '_paint_logged'):
            self._paint_logged = True
            geo = self.geometry()
            logger.info(
                f"[paintEvent] 실제 위젯 geometry: ({geo.x()},{geo.y()}) "
                f"크기:{geo.width()}x{geo.height()} | "
                f"rect(): {self.rect().width()}x{self.rect().height()}"
            )

        # 반투명 배경
        painter.fillRect(self.rect(), QColor(0, 0, 0, 30))

        # 하이라이트 사각형
        if not self._highlight_rect.isNull():
            # 하이라이트 영역은 투명하게 (구멍 뚫기)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(self._highlight_rect, Qt.GlobalColor.transparent)

            # 빨간 테두리
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen = QPen(QColor("#f38ba8"), 3)
            painter.setPen(pen)
            painter.drawRect(self._highlight_rect)

            # 내부 반투명 채우기
            painter.fillRect(
                self._highlight_rect,
                QColor(243, 139, 168, 30)
            )

        # 상단 안내 문구
        painter.setPen(QColor("#cdd6f4"))
        painter.setFont(QFont("Malgun Gothic", 14, QFont.Weight.Bold))
        guide_text = "🎯 클릭하여 UI 요소 선택  |  F3: 일시정지  |  ESC: 취소"
        painter.drawText(
            self.rect().adjusted(0, 20, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            guide_text
        )

        # 디버그: 모니터 정보 표시 (두 번째 줄)
        if self._current_screen_info:
            painter.setFont(QFont("Consolas", 11))
            painter.setPen(QColor("#fab387"))  # 주황색
            painter.drawText(
                self.rect().adjusted(0, 50, 0, 0),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                self._current_screen_info
            )

        painter.end()

    def _get_process_name(self, pid: int) -> str:
        """Win32 API로 프로세스명 조회"""
        if not pid:
            return ""
        try:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not hproc:
                return ""
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = ctypes.wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(size)):
                    path = buf.value
                    return path.split("\\")[-1] if path else ""
            finally:
                kernel32.CloseHandle(hproc)
        except Exception:
            pass
        return ""

    def _detect_browser(self, pid: int, element=None) -> str:
        """
        요소가 브라우저 내부 요소인지 판별하고 브라우저 이름을 반환합니다.

        Args:
            pid: 프로세스 ID
            element: pywinauto 요소 (보조 판단용)

        Returns:
            브라우저 이름 (예: "Chrome", "Edge") 또는 "" (데스크톱 앱)
        """
        # 1순위: 프로세스명으로 판단 (가장 확실)
        proc_name = self._get_process_name(pid).lower()
        for exe, browser in BROWSER_PROCESSES.items():
            if proc_name == exe:
                return browser

        # 2순위: 최상위 창 클래스명으로 보조 판단
        if element is not None:
            try:
                top = element.top_level_parent()
                if top:
                    top_class = top.class_name() or ""
                    matched = BROWSER_WINDOW_CLASSES.get(top_class, "")
                    if matched:
                        # Chrome_WidgetWin_1은 Chrome/Edge 공용 → 프로세스명으로 구분
                        if matched == "Chrome/Edge":
                            return "Edge" if "edge" in proc_name else "Chrome"
                        return matched
            except Exception:
                pass

        return ""

    def _is_process_elevated(self, pid: int) -> tuple[bool, str]:
        """
        대상 프로세스가 관리자 권한으로 실행 중인지 확인합니다.

        Returns:
            (is_elevated, reason)
            - is_elevated: True이면 관리자 권한
            - reason: 확인 결과 설명 문자열
        """
        if not pid:
            return False, "PID 없음 (확인 불가)"
        try:
            advapi32 = ctypes.windll.advapi32  # type: ignore
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            TOKEN_QUERY = 0x0008
            TokenElevation = 20

            hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not hproc:
                # OpenProcess 실패 → 대상이 더 높은 권한일 가능성
                err = kernel32.GetLastError()
                if err == 5:  # ERROR_ACCESS_DENIED
                    return True, "OpenProcess 접근 거부 (ACCESS_DENIED) → 관리자 권한 프로세스로 추정"
                return False, f"OpenProcess 실패 (오류 코드: {err})"

            try:
                htoken = ctypes.wintypes.HANDLE()
                if not advapi32.OpenProcessToken(hproc, TOKEN_QUERY, ctypes.byref(htoken)):
                    err = kernel32.GetLastError()
                    return False, f"OpenProcessToken 실패 (오류 코드: {err})"
                try:
                    elevation = ctypes.c_ulong(0)
                    ret_len = ctypes.wintypes.DWORD(0)
                    ok = advapi32.GetTokenInformation(
                        htoken,
                        TokenElevation,
                        ctypes.byref(elevation),
                        ctypes.sizeof(elevation),
                        ctypes.byref(ret_len)
                    )
                    if ok:
                        elevated = bool(elevation.value)
                        reason = "관리자 권한으로 실행 중" if elevated else "일반 권한으로 실행 중"
                        return elevated, reason
                    else:
                        err = kernel32.GetLastError()
                        return False, f"GetTokenInformation 실패 (오류 코드: {err})"
                finally:
                    kernel32.CloseHandle(htoken)
            finally:
                kernel32.CloseHandle(hproc)

        except Exception as e:
            return False, f"확인 중 예외 발생: {e}"

        return False, "확인 실패 (알 수 없는 경로)"

    def _collect_element_hierarchy(self, element) -> list[dict]:
        """
        요소의 부모 체인을 따라 올라가며 계층 구조 정보를 수집합니다.
        index 0 = 선택된 요소, index N = 루트에 가까운 요소
        """
        hierarchy: list[dict] = []
        current: Any = element
        visited: set = set()

        while current is not None:
            try:
                handle = getattr(current, 'handle', None)
                if handle and handle in visited:
                    break
                if handle:
                    visited.add(handle)

                info: dict[str, Any] = {}
                info['name'] = (current.window_text() or "")[:120]
                info['class_name'] = current.class_name() or ""

                try:
                    info['control_type'] = current.element_info.control_type or ""
                except Exception:
                    info['control_type'] = ""

                try:
                    info['automation_id'] = current.element_info.automation_id or ""
                except Exception:
                    info['automation_id'] = ""

                try:
                    r = current.rectangle()
                    info['rect'] = (r.left, r.top, r.right, r.bottom,
                                    r.width(), r.height())
                except Exception:
                    info['rect'] = None

                try:
                    info['handle'] = hex(current.handle) if current.handle else ""
                except Exception:
                    info['handle'] = ""

                try:
                    info['process_id'] = current.process_id()
                except Exception:
                    info['process_id'] = 0

                try:
                    info['is_visible'] = current.is_visible()
                except Exception:
                    info['is_visible'] = None

                try:
                    info['is_enabled'] = current.is_enabled()
                except Exception:
                    info['is_enabled'] = None

                hierarchy.append(info)

                # 부모로 이동
                try:
                    parent = current.parent()
                    if parent is None:
                        break
                    # 부모가 자기 자신이면 종료
                    parent_handle = getattr(parent, 'handle', None)
                    if parent_handle and parent_handle == handle:
                        break
                    current = parent
                except Exception:
                    break

            except Exception:
                break

        return hierarchy

    def _log_element_details(self, element_info: dict, element=None):
        """
        선택된 요소의 상세 정보와 계층 구조를 로그에 출력합니다.
        """
        try:
            self._log_element_details_impl(element_info, element)
        except Exception as e:
            logger.error(f"요소 상세 로그 출력 실패: {e}")

    def _log_element_details_impl(self, element_info: dict, element=None):
        """_log_element_details 실제 구현"""
        sep = "=" * 70
        logger.info(sep)

        is_browser = element_info.get("is_browser", False)
        browser_type = element_info.get("browser_type", "")
        if is_browser:
            logger.info(f"  UI 요소 선택 완료 - [{browser_type} 브라우저] Selenium 코드 생성")
        else:
            logger.info("  UI 요소 선택 완료 - [데스크톱 앱] pywinauto 코드 생성")

        logger.info(sep)

        # 프로세스 정보 + 관리자 권한 확인
        pid = element_info.get("_pid", 0)
        proc_name = self._get_process_name(pid) if pid else ""
        if proc_name or pid:
            logger.info(f"  프로세스: {proc_name}  (PID: {pid})")

        if pid:
            is_elevated, elev_reason = self._is_process_elevated(pid)
            elev_icon = "[관리자 권한 !!]" if is_elevated else "[일반 권한]"
            logger.info(f"  권한 상태 : {elev_icon}  {elev_reason}")
            if is_elevated:
                logger.info("  *** WM 메시지(click/click_input) 불가 - pyautogui.click(x,y) 사용 필요 ***")

        logger.info(f"  감지 백엔드: {element_info.get('detected_backend', '?')}"
                    f"  →  권장 백엔드: {element_info.get('recommended_backend', '?')}")
        logger.info("")

        # 선택된 요소 속성
        logger.info("  [선택된 요소 속성]")
        logger.info(f"    control_type : {element_info.get('control_type', '')}")
        logger.info(f"    name         : \"{element_info.get('name', '')}\"")
        logger.info(f"    class_name   : {element_info.get('class_name', '')}")
        logger.info(f"    automation_id: {element_info.get('automation_id', '') or '(없음)'}")
        r = element_info.get("rect", {})
        if r:
            logger.info(
                f"    rect         : ({r.get('left')},{r.get('top')}) "
                f"~ ({r.get('right')},{r.get('bottom')})  "
                f"크기:{r.get('width')}×{r.get('height')}"
            )
        logger.info(f"    화면 좌표    : ({element_info.get('screen_x')}, {element_info.get('screen_y')})")
        logger.info("")

        # 계층 구조
        if element is not None:
            try:
                hierarchy = self._collect_element_hierarchy(element)
                if hierarchy:
                    logger.info("  [요소 계층 구조]  (선택 요소 → 루트 방향)")
                    logger.info("  " + "-" * 66)
                    for i, lvl in enumerate(hierarchy):
                        prefix = "  ▶ " if i == 0 else f"  {'  ' * min(i, 8)}└ "
                        label = "(선택)" if i == 0 else f"(부모 {i})" if i < len(hierarchy) - 1 else "(루트)"

                        ctrl = lvl.get('control_type') or lvl.get('class_name') or "?"
                        name_str = f' "{lvl["name"]}"' if lvl.get("name") else ""
                        cls_str = f'  class={lvl["class_name"]}' if lvl.get("class_name") else ""
                        aid_str = f'  id={lvl["automation_id"]}' if lvl.get("automation_id") else ""
                        hwnd_str = f'  hwnd={lvl["handle"]}' if lvl.get("handle") else ""

                        rect_str = ""
                        if lvl.get("rect"):
                            rx = lvl["rect"]
                            rect_str = f"  ({rx[0]},{rx[1]}) {rx[4]}×{rx[5]}"

                        vis_str = ""
                        if lvl.get("is_visible") is False:
                            vis_str = "  [hidden]"
                        if lvl.get("is_enabled") is False:
                            vis_str += "  [disabled]"

                        logger.info(
                            f"{prefix}[{ctrl}]{name_str}{cls_str}{aid_str}"
                            f"{hwnd_str}{rect_str}{vis_str}  {label}"
                        )
                    logger.info("  " + "-" * 66)
            except Exception as e:
                logger.debug(f"계층 수집 실패: {e}")

        logger.info(sep)

    def mousePressEvent(self, event):
        """클릭 시 요소 선택 완료"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 로깅에 필요한 레퍼런스를 stop_picking() 호출 전에 보관
            element_info = self._current_element_info.copy() if self._current_element_info else {}
            element_ref = self._current_element_ref
            self.stop_picking()
            if element_info:
                self._log_element_details(element_info, element_ref)
                self.element_picked.emit(element_info)
            else:
                self.pick_cancelled.emit()
        elif event.button() == Qt.MouseButton.RightButton:
            self.stop_picking()
            self.pick_cancelled.emit()

    def keyPressEvent(self, event):
        """ESC로 취소, F3으로 일시정지"""
        if event.key() == Qt.Key.Key_Escape:
            self._pause_label.hide()
            self.stop_picking()
            self.pick_cancelled.emit()
        elif event.key() == Qt.Key.Key_F3:
            if not self._paused:
                self._start_pause()

    def _start_pause(self):
        """F3 일시정지 시작 - 3초간 오버레이 숨기고 자유롭게 조작 가능"""
        self._paused = True
        self._pause_countdown = 3
        self._track_timer.stop()

        # 오버레이 숨기기
        self.hide()
        self._info_label.hide()

        # 카운트다운 라벨 표시
        self._update_pause_label()
        self._pause_label.show()
        self._pause_label.raise_()

        # 1초마다 카운트다운
        QTimer.singleShot(1000, self._pause_tick)

    def _pause_tick(self):
        """일시정지 카운트다운"""
        if not self._paused:
            return

        self._pause_countdown -= 1

        if self._pause_countdown <= 0:
            # 일시정지 종료 — 오버레이를 포커스 없이 복원
            self._paused = False
            self._pause_label.hide()
            self._resume_after_pause()
        else:
            # 카운트다운 업데이트
            self._update_pause_label()
            QTimer.singleShot(1000, self._pause_tick)

    def _resume_after_pause(self):
        """
        F3 일시정지 후 복귀.

        핵심: 오버레이를 다시 표시하되 대상 앱의 포커스/메뉴 상태를 건드리지 않는다.
        - WS_EX_NOACTIVATE로 show() 시 포커스 빼앗기 방지
        - 저수준 키보드 훅(WH_KEYBOARD_LL)으로 F3/ESC를 가로채어
          대상 앱에 전달되지 않게 차단
        - 마우스 좌클릭은 GetAsyncKeyState로 감지
        """
        self._post_pause_mode = True

        if sys.platform == "win32":
            hwnd = int(self.winId())

            # WS_EX_NOACTIVATE로 포커스 빼앗지 않고 표시
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE)
            self.show()
            self.raise_()
        else:
            self.show()
            self.raise_()

        # 커서 추적 재개 (하이라이트용)
        self._track_timer.start(self._track_interval)

        # 저수준 키보드 훅 설치 (F3/ESC 가로채기)
        self._install_keyboard_hook()

        # 마우스 클릭 감지용 폴링 타이머
        if not hasattr(self, '_click_poll_timer'):
            self._click_poll_timer = QTimer(self)
            self._click_poll_timer.timeout.connect(self._poll_mouse_click)
        self._click_poll_timer.start(50)

    # ── 저수준 키보드 훅 (WH_KEYBOARD_LL) ──

    def _install_keyboard_hook(self):
        """
        WH_KEYBOARD_LL 훅을 설치하여 F3/ESC를 시스템 레벨에서 가로챔.
        대상 앱에 키 이벤트가 전달되기 전에 차단하므로
        메모장의 "다음 찾기" 같은 동작이 발생하지 않음.
        """
        if sys.platform != "win32":
            return

        # 콜백 함수 타입 정의
        HOOKPROC = ctypes.CFUNCTYPE(
            ctypes.c_long,       # return: LRESULT
            ctypes.c_int,        # nCode
            ctypes.c_ulonglong,  # wParam (WPARAM, 64bit)
            ctypes.c_ulonglong,  # lParam (LPARAM, 64bit)
        )

        def _keyboard_hook_proc(nCode, wParam, lParam):
            """저수준 키보드 훅 콜백"""
            if nCode >= 0 and self._post_pause_mode:
                # lParam은 KBDLLHOOKSTRUCT 포인터
                # 구조체의 첫 번째 DWORD가 vkCode
                vk_code = ctypes.cast(lParam, ctypes.POINTER(ctypes.c_ulong))[0]

                WM_KEYDOWN = 0x0100
                WM_KEYUP = 0x0101

                if vk_code == VK_F3:
                    if wParam == WM_KEYUP:
                        # F3 릴리즈 시 → 다시 일시정지
                        QTimer.singleShot(0, self._on_hook_f3)
                    return 1  # 키 이벤트 소비 (대상 앱에 전달 안 함)

                if vk_code == VK_ESCAPE:
                    if wParam == WM_KEYDOWN:
                        QTimer.singleShot(0, self._on_hook_esc)
                    return 1  # 키 이벤트 소비

            # 다른 키는 정상 전달
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        # 콜백 레퍼런스 유지 (GC 방지)
        self._hook_proc_ref = HOOKPROC(_keyboard_hook_proc)

        WH_KEYBOARD_LL = 13
        self._keyboard_hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._hook_proc_ref,
            None,  # hMod: None for global hook
            0      # dwThreadId: 0 for all threads
        )
        if not self._keyboard_hook:
            logger.warning("키보드 훅 설치 실패")

    def _uninstall_keyboard_hook(self):
        """저수준 키보드 훅 해제"""
        if hasattr(self, '_keyboard_hook') and self._keyboard_hook:
            user32.UnhookWindowsHookEx(self._keyboard_hook)
            self._keyboard_hook = None
        self._hook_proc_ref = None

    def _on_hook_f3(self):
        """훅에서 F3 감지 → 다시 일시정지"""
        if not self._post_pause_mode:
            return
        self._exit_post_pause_mode()
        self._start_pause()

    def _on_hook_esc(self):
        """훅에서 ESC 감지 → 취소"""
        if not self._post_pause_mode:
            return
        self._exit_post_pause_mode()
        self.stop_picking()
        self.pick_cancelled.emit()

    def _poll_mouse_click(self):
        """마우스 좌클릭을 폴링하여 요소 선택"""
        if not self._post_pause_mode:
            return
        if sys.platform != "win32":
            return

        if user32.GetAsyncKeyState(0x01) & 0x8000:  # VK_LBUTTON
            self._exit_post_pause_mode()
            element_info = self._current_element_info.copy() if self._current_element_info else {}
            element_ref = self._current_element_ref
            self.stop_picking()
            if element_info:
                self._log_element_details(element_info, element_ref)
                self.element_picked.emit(element_info)
            else:
                self.pick_cancelled.emit()

    def _exit_post_pause_mode(self):
        """투과 모드 종료: 훅 해제, 타이머 정지, WS_EX_NOACTIVATE 제거"""
        self._post_pause_mode = False
        self._uninstall_keyboard_hook()
        if hasattr(self, '_click_poll_timer'):
            self._click_poll_timer.stop()
        if sys.platform == "win32":
            hwnd = int(self.winId())
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style & ~WS_EX_NOACTIVATE)

    def _update_pause_label(self):
        """일시정지 카운트다운 라벨 업데이트"""
        self._pause_label.setText(f"  ⏸️ 일시정지 중... {self._pause_countdown}초 후 재개  |  마우스/키보드 자유롭게 조작하세요  ")
        self._pause_label.adjustSize()

        # 화면 중앙 상단에 배치
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self._pause_label.width()) // 2
            y = geo.y() + 50
            self._pause_label.move(x, y)
