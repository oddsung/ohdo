# SPDX-License-Identifier: AGPL-3.0-or-later
"""
UI 요소 피커 (Element Picker)

투명 오버레이를 표시하고, 마우스 아래의 UI 요소를 실시간으로 하이라이트합니다.
사용자가 클릭하면 해당 요소의 정보를 수집하여 시그널로 전달합니다.
"""

import ctypes
import logging
import sys
import time

if sys.platform == "win32":
    import ctypes.wintypes
from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPen, QScreen
from PySide6.QtWidgets import QLabel, QWidget

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
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
HWND_TOPMOST = -1  # SetWindowPos 의 hWndInsertAfter sentinel — 진짜 topmost
VK_F3 = 0x72
VK_ESCAPE = 0x1B

# user32 argtypes 1 회 설정 플래그 (모듈 레벨)
_user32_argtypes_set = False

# pywinauto lazy import
_pywinauto_available = False
try:
    import pywinauto
    from pywinauto import Desktop

    _pywinauto_available = True
except ImportError:
    pass

# 브라우저 프로세스명 → 브라우저 이름 매핑
BROWSER_PROCESSES: dict[str, str] = {
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
    "firefox.exe": "Firefox",
    "iexplore.exe": "IE",
    "opera.exe": "Opera",
    "brave.exe": "Brave",
    "whale.exe": "Whale",  # 네이버 웨일
    "vivaldi.exe": "Vivaldi",
    "arc.exe": "Arc",
}

# 브라우저 최상위 창 클래스명 → 브라우저 이름 (프로세스명 미확인 시 보조 판단)
BROWSER_WINDOW_CLASSES: dict[str, str] = {
    "Chrome_WidgetWin_1": "Chrome/Edge",
    "MozillaWindowClass": "Firefox",
    "IEFrame": "IE",
    "OperaWindowClass": "Opera",
    "ApplicationFrameWindow": "",  # UWP 앱 (브라우저 아님)
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

    element_picked = Signal(dict)
    pick_cancelled = Signal()

    # UIA 트리 walk 의 기본값. update_settings() 으로 재정의 가능.
    DEFAULT_UIA_MAX_DEPTH = 15
    DEFAULT_UIA_TIME_BUDGET_MS = 150

    # post_pause_mode 후 일반 picker mode 로 전환 지연 (ms).
    # 이 시간 동안 click-through 로 OS 가 submenu 에 cursor 위치를 등록하면,
    # 그 후 TRANSPARENT 끄고 일반 mode 로 가도 submenu 유지 (가설).
    POST_PAUSE_TRANSITION_MS = 200

    # walker 결과 area 가 이보다 작으면 descendants 폴백 skip — 이미 충분히 깊음.
    # Excel cell ≈1600, 메뉴 항목 ≈1920, 작은 버튼 ≈3000 — 이런 케이스에서
    # descendants() (800-1000ms) 호출 회피해서 picker 반응성 향상.
    NEEDS_DESCENDANTS_AREA_THRESHOLD = 5000

    # 사용자 보고 (5/5): Win11 메모장 메뉴바 [MenuItem '파일'] 안의 leaf TextBlock 으로
    # picker descent 했더니 control_type='Text' 로 저장 → pywinauto child_window 가 못 찾음.
    # EFP/walker 가 이 set 의 control_type 을 잡았으면 더 깊은 비클릭 leaf 로 descend 안 함.
    _CLICKABLE_CONTROL_TYPES = frozenset(
        {
            "Button",
            "MenuItem",
            "MenuBarItem",
            "TabItem",
            "ListItem",
            "CheckBox",
            "RadioButton",
            "Hyperlink",
            "SplitButton",
            "TreeItem",
            "Edit",
            "ComboBox",
            "Slider",
            "Spinner",
        }
    )

    def _is_clickable_element(self, element) -> bool:
        """element 의 control_type 이 클릭 가능한 타입인지 확인. 예외는 False."""
        try:
            return element.element_info.control_type in self._CLICKABLE_CONTROL_TYPES
        except Exception:
            return False

    def __init__(self, parent=None, settings: dict | None = None):
        super().__init__(parent)

        # UIA tree walk 파라미터 (settings 에서 덮어쓰기 가능)
        self._uia_max_depth = self.DEFAULT_UIA_MAX_DEPTH
        self._uia_time_budget_sec = self.DEFAULT_UIA_TIME_BUDGET_MS / 1000.0
        # post_pause → 일반 picker mode 전환 지연 (ms). 0 이면 transition 비활성
        # (방향 B 직접 — post_pause_mode 가 click/ESC 까지 유지).
        self._post_pause_transition_ms = self.POST_PAUSE_TRANSITION_MS
        # CDP 사용 여부 (default False). 활성화 시 element 선택 후 Chrome
        # remote-debugging-port 시도 → DOM context 수집. 비활성화 시 click 후
        # 메인 화면 전환 즉시 (CDP 포트 timeout 대기 없음).
        self._cdp_enabled = False
        if settings:
            self.update_settings(settings)

        # 윈도우 설정: 전체 화면 투명 레이어
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
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
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
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

    def update_settings(self, settings: dict):
        """settings dict 의 element_picker 섹션에서 UIA walk 파라미터 갱신.

        설정이 다이얼로그로 변경되면 main_window 가 이 메서드를 호출.
        """
        ep = (settings or {}).get("element_picker", {}) or {}

        try:
            md = int(ep.get("uia_max_depth", self.DEFAULT_UIA_MAX_DEPTH))
        except (TypeError, ValueError):
            md = self.DEFAULT_UIA_MAX_DEPTH
        self._uia_max_depth = max(1, min(50, md))  # 1~50 클램프

        try:
            tb_ms = int(ep.get("uia_time_budget_ms", self.DEFAULT_UIA_TIME_BUDGET_MS))
        except (TypeError, ValueError):
            tb_ms = self.DEFAULT_UIA_TIME_BUDGET_MS
        self._uia_time_budget_sec = max(0.03, min(2.0, tb_ms / 1000.0))  # 30ms~2s 클램프

        try:
            pp_ms = int(
                ep.get(
                    "post_pause_transition_ms",
                    self.POST_PAUSE_TRANSITION_MS,
                )
            )
        except (TypeError, ValueError):
            pp_ms = self.POST_PAUSE_TRANSITION_MS
        # 0 이면 transition 비활성 (방향 B 직접). 양수면 그 ms 후 자동 전환.
        self._post_pause_transition_ms = max(0, min(5000, pp_ms))

        # cdp_enabled — Chrome remote-debugging-port 시도 여부.
        # False (default) 면 element 선택 후 즉시 emit. True 면 DOM context 수집.
        self._cdp_enabled = bool(ep.get("cdp_enabled", False))

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
        # PySide6는 기본적으로 DPI-aware이므로 물리 좌표를 직접 사용하면
        # Qt가 내부적으로 변환함
        logger.info(f"Win32 물리 좌표 직접 사용: ({vx},{vy}) 크기:{vw}x{vh}")

        # 가장 큰 영역 선택 (세 방법 중 가장 큰 것)
        candidates = [
            (
                virtual_geo.x(),
                virtual_geo.y(),
                virtual_geo.x() + virtual_geo.width(),
                virtual_geo.y() + virtual_geo.height(),
            ),
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

        # 진짜 TOPMOST 강제 — Qt WindowStaysOnTopHint 만으로는 Win11 작업표시줄
        # (Shell_TrayWnd) 나 Chrome 메인 윈도우가 우리 overlay 위로 올라오는 케이스가
        # 있어 SetWindowPos 로 z-order 강제 재배치. 이게 빠지면 picker 의 click 이
        # underlying app 에 가려져 element 선택이 안 되는 회귀 발생함.
        self._force_topmost()

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
                f"  모니터 {i}: 논리({geo.x()},{geo.y()})~({geo.x() + geo.width()},{geo.y() + geo.height()}) | "
                f"논리크기:{geo.width()}x{geo.height()} | 물리크기:{phys_w}x{phys_h} | 배율:{dpr}"
            )

        self._highlight_rect = QRect()
        self._element_info_text = ""
        self._paused = False
        self._pause_countdown = 0
        self._cursor_local_pos = QPoint()
        self._current_screen_info = ""
        self._paint_logged = False  # 디버그 로깅 초기화
        self._diag_tick_count = 0  # 진단 print 카운터 리셋 (picker 시작 시 첫 3 tick 만 출력)

        # 마우스 추적 시작
        self._track_timer.start(self._track_interval)

        # 키보드 hook 설치 — picker 전체 lifecycle 동안 유지 (focus 무관 ESC/F3 응답)
        self._install_keyboard_hook()

        logger.info("UI 요소 피커 시작")
        print("[ElementPicker] 진단 출력 활성화 (첫 3 tick)", flush=True)

    def stop_picking(self):
        """선택 중단"""
        self._track_timer.stop()
        self._info_label.hide()
        self._pause_label.hide()
        self._paused = False
        if self._post_pause_mode:
            self._exit_post_pause_mode()
        # 키보드 hook 해제 (lifecycle 종료)
        self._uninstall_keyboard_hook()
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
            if (
                geo.x() <= logical_x < geo.x() + geo.width()
                and geo.y() <= logical_y < geo.y() + geo.height()
            ):
                return screen, dpr

        # 찾지 못한 경우: 커서 위치 기반으로 스크린 찾기 (fallback)
        cursor_pos = QCursor.pos()
        screen_at_cursor = QGuiApplication.screenAt(cursor_pos)
        if screen_at_cursor:
            return screen_at_cursor, screen_at_cursor.devicePixelRatio()

        # 최후의 fallback: 주 모니터
        primary = QGuiApplication.primaryScreen()
        return primary, primary.devicePixelRatio() if primary else 1.0

    @staticmethod
    def _ensure_user32_argtypes():
        """user32 의 HWND 관련 함수들 argtypes 를 명시적으로 설정.

        64-bit Windows 에서 HWND 는 8-byte (c_void_p) 인데 ctypes 기본은 c_int (4-byte) 라
        argtypes 미설정 시 HWND 값이 잘려 IsWindowVisible/GetWindowRect 등이 잘못된
        결과를 반환할 수 있다. 한 번만 설정하면 모듈 lifetime 동안 유지.
        """
        global _user32_argtypes_set
        if _user32_argtypes_set:
            return
        if not user32:
            return
        user32.GetTopWindow.argtypes = [ctypes.wintypes.HWND]
        user32.GetTopWindow.restype = ctypes.wintypes.HWND
        user32.GetWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_uint]
        user32.GetWindow.restype = ctypes.wintypes.HWND
        user32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]
        user32.IsWindowVisible.restype = ctypes.wintypes.BOOL
        user32.IsIconic.argtypes = [ctypes.wintypes.HWND]
        user32.IsIconic.restype = ctypes.wintypes.BOOL
        user32.GetWindowRect.argtypes = [
            ctypes.wintypes.HWND,
            ctypes.POINTER(ctypes.wintypes.RECT),
        ]
        user32.GetWindowRect.restype = ctypes.wintypes.BOOL
        # SetWindowPos 시그니처. 두 번째 HWND 자리에 HWND_TOPMOST(-1) 같은 음수
        # sentinel 이 들어가므로 c_ssize_t 로 받아 부호 보존.
        user32.SetWindowPos.argtypes = [
            ctypes.wintypes.HWND,
            ctypes.c_ssize_t,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.SetWindowPos.restype = ctypes.wintypes.BOOL
        _user32_argtypes_set = True

    def _force_topmost(self):
        """Win32 SetWindowPos(HWND_TOPMOST) 로 진짜 z-order 최상단에 박는다.

        Qt 의 WindowStaysOnTopHint + raise_() 만으로는 Win11 작업표시줄
        (Shell_TrayWnd) 같은 시스템 우선 z-order 윈도우들을 못 이겨, Chrome 메인
        윈도우가 우리 overlay 위로 올라오는 등의 회귀가 발생함. SetWindowPos 가 실제
        WS_EX_TOPMOST 플래그 설정 + z-order 강제 재배치.
        """
        if not user32:
            return
        self._ensure_user32_argtypes()
        try:
            hwnd = int(self.winId())
            ok = user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
            logger.info(f"SetWindowPos(HWND_TOPMOST) → {bool(ok)}")
        except Exception as e:
            logger.debug(f"SetWindowPos(HWND_TOPMOST) 실패: {e}")

    def _find_topmost_window_at_point(self, x: int, y: int, exclude_hwnd: int):
        """GetTopWindow + GetWindow(GW_HWNDNEXT) 루프로 z-order top-down 순회하며
        (x,y) 를 포함하는 가시 윈도우 중 exclude_hwnd 가 아닌 첫 HWND 를 반환.

        설계 의도 (mouse-over 누수 방지):
            WS_EX_TRANSPARENT 토글을 **전혀 사용하지 않는다**. z-order 상단부터
            우리 overlay 를 명시적으로 skip 하면 "그 다음 윈도우" 를 자연스럽게 얻을
            수 있다. OS click-through 플래그가 한순간도 켜지지 않으므로 mouse-move
            이벤트 누수 가능성이 0.

            EnumWindows 의 콜백 + ctypes 변환에서 가끔 동작 이상이 보고되어 더 단순한
            GetTopWindow/GetWindow 루프로 대체. argtypes 도 명시 설정.
        """
        if not user32:
            return None

        self._ensure_user32_argtypes()

        diag = getattr(self, "_diag_tick_count", 99) <= 10

        GW_HWNDNEXT = 2
        # GetTopWindow(0) = 데스크톱의 z-order top-most child = 최상위 top-level 윈도우
        hwnd = user32.GetTopWindow(None)
        scanned = 0
        skipped_self = 0
        skipped_invisible = 0
        skipped_iconic = 0
        skipped_norect = 0
        skipped_outside = 0
        sample_lines = []
        max_scan = 500

        while hwnd and scanned < max_scan:
            scanned += 1
            try:
                if hwnd == exclude_hwnd:
                    skipped_self += 1
                else:
                    visible = bool(user32.IsWindowVisible(hwnd))
                    iconic = bool(user32.IsIconic(hwnd))
                    if not visible:
                        skipped_invisible += 1
                    elif iconic:
                        skipped_iconic += 1
                    else:
                        rect = ctypes.wintypes.RECT()
                        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                            skipped_norect += 1
                        else:
                            inside = rect.left <= x < rect.right and rect.top <= y < rect.bottom
                            if diag and len(sample_lines) < 8:
                                sample_lines.append(
                                    f"  HWND=0x{hwnd:x} rect=({rect.left},{rect.top})"
                                    f"~({rect.right},{rect.bottom}) "
                                    f"inside={inside}"
                                )
                            if inside:
                                if diag:
                                    print(
                                        f"[ElementPicker DIAG] z-order 매칭: HWND=0x{hwnd:x} "
                                        f"scanned={scanned}",
                                        flush=True,
                                    )
                                return hwnd
                            else:
                                skipped_outside += 1
            except Exception as e:
                if diag:
                    print(f"[ElementPicker DIAG] z-order 순회 중 예외: {e}", flush=True)

            hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)

        if diag:
            print(
                f"[ElementPicker DIAG] _find_topmost_window: 매칭 없음 "
                f"(scanned={scanned}, self={skipped_self}, invisible={skipped_invisible}, "
                f"iconic={skipped_iconic}, norect={skipped_norect}, outside={skipped_outside})",
                flush=True,
            )
            for line in sample_lines:
                print(f"[ElementPicker DIAG]{line}", flush=True)
        return None

    def _find_deepest_descendant(self, root_wrapper, x: int, y: int, time_budget_sec: float = 0.1):
        """root_wrapper 의 모든 descendants 를 훑어 (x,y) 를 포함하는 가장 작은 것 반환.

        ⚠ pywinauto.descendants() 는 모든 element 를 eager 하게 wrap 해서 Chrome 같이
        거대한 UIA 트리에서 호출만 300-500ms 소요. _raw_walk_at_point 가 더 빠르고
        포괄적이므로 raw 폴백으로 대체. 이 메서드는 fallback-of-fallback 으로만 유지.
        """
        deadline = time.time() + time_budget_sec
        try:
            descendants = root_wrapper.descendants()
        except Exception:
            return None

        best = None
        best_area = None
        for desc in descendants:
            if time.time() > deadline:
                break
            try:
                r = desc.rectangle()
            except Exception:
                continue
            if r.left <= x < r.right and r.top <= y < r.bottom:
                w = max(1, r.right - r.left)
                h = max(1, r.bottom - r.top)
                area = w * h
                if best_area is None or area < best_area:
                    best_area = area
                    best = desc

        return best

    def _raw_walk_at_point(
        self,
        target_hwnd: int,
        x: int,
        y: int,
        time_budget_sec: float | None = None,
        max_depth: int | None = None,
    ):
        """IUIA RawViewWalker 로 (x,y) 를 포함하는 가장 깊은 element 를 lazily 탐색.

        ControlView (pywinauto 의 .children()/.descendants() 기본값) 는 Chrome/Win11
        XAML 등에서 sparse 하게 돌아옴. RawView 는 모든 UIA element (구조 element
        포함) 를 보여주므로 Chrome 탭 같은 깊은 element 도 닿는다.

        Eager wrapping 없이 raw IUIAutomationElement 로만 traversal 후 결과 1개만
        UIAWrapper 로 wrap → 거대 트리에서도 빠름.

        Returns:
            UIAWrapper 또는 None (실패/타임아웃)
        """
        if max_depth is None:
            max_depth = self._uia_max_depth
        if time_budget_sec is None:
            time_budget_sec = self._uia_time_budget_sec

        try:
            from pywinauto.controls.uiawrapper import UIAWrapper
            from pywinauto.uia_defines import IUIA
            from pywinauto.uia_element_info import UIAElementInfo
        except Exception as e:
            logger.debug(f"raw walker import 실패: {e}")
            return None

        deadline = time.time() + time_budget_sec

        try:
            iuia = IUIA().iuia
            walker = iuia.RawViewWalker

            root_info = UIAElementInfo(target_hwnd)
            root_elem = root_info._element  # IUIAutomationElement
        except Exception as e:
            logger.debug(f"raw walker 초기화 실패: {e}")
            return None

        def _rect_contains(rect, px, py):
            return rect.left <= px < rect.right and rect.top <= py < rect.bottom

        def _area(rect):
            return max(1, (rect.right - rect.left)) * max(1, (rect.bottom - rect.top))

        def walk(elem, depth):
            if depth <= 0 or time.time() > deadline:
                return elem
            try:
                rect = elem.CurrentBoundingRectangle
            except Exception:
                return elem
            if not _rect_contains(rect, x, y):
                return None

            best = elem
            best_area = _area(rect)

            try:
                child = walker.GetFirstChildElement(elem)
            except Exception:
                return best

            while child:
                if time.time() > deadline:
                    break
                try:
                    cr = child.CurrentBoundingRectangle
                except Exception:
                    cr = None
                if cr is not None and _rect_contains(cr, x, y):
                    deeper = walk(child, depth - 1)
                    if deeper is not None and deeper is not elem:
                        try:
                            dr = deeper.CurrentBoundingRectangle
                            d_area = _area(dr)
                            if d_area < best_area:
                                best = deeper
                                best_area = d_area
                        except Exception:
                            pass
                try:
                    child = walker.GetNextSiblingElement(child)
                except Exception:
                    break

            return best

        try:
            deepest = walk(root_elem, max_depth)
        except Exception as e:
            logger.debug(f"raw walker 실행 실패: {e}")
            return None

        if deepest is None:
            return None

        try:
            return UIAWrapper(UIAElementInfo(deepest))
        except Exception as e:
            logger.debug(f"raw walker 결과 wrap 실패: {e}")
            return None

    def _walk_uia_to_deepest(
        self,
        root_wrapper,
        x: int,
        y: int,
        max_depth: int | None = None,
        time_budget_sec: float | None = None,
    ):
        """root_wrapper 의 UIA 트리를 walk 하여 (x,y) 를 포함하는 가장 깊은 자식을 찾는다.

        - 각 레벨에서 (x,y) 를 포함하는 children 중 **가장 작은** 것을 선택해 깊이 들어감
        - max_depth 또는 time_budget 초과 시 거기서 멈춤 (Chrome 같은 거대 UIA 트리 보호)
        - 깊은 자식이 없으면 root_wrapper 자체 반환

        max_depth/time_budget_sec 를 명시적으로 안 주면 instance 의 설정값 사용.
        """
        if max_depth is None:
            max_depth = self._uia_max_depth
        if time_budget_sec is None:
            time_budget_sec = self._uia_time_budget_sec

        current = root_wrapper
        deadline = time.time() + time_budget_sec

        for _ in range(max_depth):
            if time.time() > deadline:
                break

            try:
                children = current.children()
            except Exception:
                break

            if not children:
                break

            best_child = None
            best_area = None
            for child in children:
                if time.time() > deadline:
                    break
                try:
                    r = child.rectangle()
                except Exception:
                    continue
                if r.left <= x < r.right and r.top <= y < r.bottom:
                    area = max(1, (r.right - r.left)) * max(1, (r.bottom - r.top))
                    if best_area is None or area < best_area:
                        best_area = area
                        best_child = child

            if best_child is None:
                break

            current = best_child

        return current

    def _detect_via_efp(self, x_phys: int, y_phys: int):
        """IUIAutomation::ElementFromPoint 직호출 — TreeWalker 와 다른 OS-level path.

        walker (ControlView/RawView) 가 leaf 에서 멈추는 lazy a11y 트리 케이스
        (MFC+WebView, Chrome lazy renderer 등) 도 OS 가 직접 깊이 들어감.
        HWND 무관 — cursor 좌표만으로 element 반환.

        Returns:
            (wrapper, rect, area) 또는 (None, None, None)
        """
        diag = getattr(self, "_diag_tick_count", 99) <= 10
        try:
            from pywinauto.controls.uiawrapper import UIAWrapper
            from pywinauto.uia_defines import IUIA
            from pywinauto.uia_element_info import UIAElementInfo

            iuia = IUIA().iuia
            pt = ctypes.wintypes.POINT(x_phys, y_phys)
            elem_com = iuia.ElementFromPoint(pt)
            if not elem_com:
                if diag:
                    print("[ElementPicker DIAG] EFP → None", flush=True)
                return None, None, None

            info = UIAElementInfo(elem_com)
            wrapper = UIAWrapper(info)
            rect = wrapper.rectangle()
            if rect.width() <= 0 or rect.height() <= 0:
                if diag:
                    print("[ElementPicker DIAG] EFP → 빈 rect", flush=True)
                return None, None, None
            area = max(1, rect.width() * rect.height())
            if diag:
                print(
                    f"[ElementPicker DIAG] EFP → {wrapper!r} "
                    f"area={area} rect=({rect.left},{rect.top})~"
                    f"({rect.right},{rect.bottom})",
                    flush=True,
                )
            return wrapper, rect, area
        except Exception as e:
            if diag:
                print(f"[ElementPicker DIAG] EFP 실패: {e}", flush=True)
            return None, None, None

    def _detect_in_hwnd(self, hwnd: int, x_phys: int, y_phys: int, label: str = ""):
        """주어진 HWND 의 UIA tree 에서 (x,y) 위치의 가장 깊은 element 를 찾는다.

        Single-HWND detection — main HWND 와 child HWND 각각 호출 가능.
        Chrome 같은 multi-process 앱에서:
          - main HWND (Chrome_WidgetWin_1) → 탭 strip / URL bar / 툴바 등 chrome UI
          - child HWND (Chrome Legacy Window/renderer) → HTML 페이지 콘텐츠
        둘 다 시도해야 모든 케이스 커버.

        Returns:
            tuple: (element, rect, area) 또는 (None, None, None)
        """
        if not user32:
            return None, None, None

        diag = getattr(self, "_diag_tick_count", 99) <= 10
        label_prefix = f"[{label}] " if label else ""

        # WM_GETOBJECT 송신 — UIA tree 활성화 신호 (특히 Chrome 같은 lazy 앱)
        try:
            WM_GETOBJECT = 0x003D
            OBJID_CLIENT = ctypes.c_long(-4).value & 0xFFFFFFFF
            user32.SendMessageW(hwnd, WM_GETOBJECT, 0, OBJID_CLIENT)
        except Exception:
            pass

        try:
            from pywinauto.controls.uiawrapper import UIAWrapper
            from pywinauto.uia_element_info import UIAElementInfo

            elem_info = UIAElementInfo(hwnd)
            window_wrapper = UIAWrapper(elem_info)
            if diag:
                print(
                    f"[ElementPicker DIAG] {label_prefix}UIA wrap(0x{hwnd:x}) → {window_wrapper!r}",
                    flush=True,
                )
        except Exception as e:
            if diag:
                print(f"[ElementPicker DIAG] {label_prefix}UIA wrap 실패: {e}", flush=True)
            return None, None, None

        try:
            # 1) children walk (fast preview)
            t0 = time.time()
            element = self._walk_uia_to_deepest(window_wrapper, x_phys, y_phys)
            walk_ms = int((time.time() - t0) * 1000)
            rect = element.rectangle()
            current_area = max(1, rect.width() * rect.height())
            if diag:
                print(
                    f"[ElementPicker DIAG] {label_prefix}walk {walk_ms}ms → "
                    f"area={current_area} rect=({rect.left},{rect.top})~"
                    f"({rect.right},{rect.bottom})",
                    flush=True,
                )

            # 2) raw walker — RawView, lazy
            budget_remaining = self._uia_time_budget_sec - (time.time() - t0)
            if budget_remaining > 0.03:
                t1 = time.time()
                deeper = self._raw_walk_at_point(hwnd, x_phys, y_phys, budget_remaining)
                raw_ms = int((time.time() - t1) * 1000)
                if deeper is not None:
                    try:
                        d_rect = deeper.rectangle()
                        d_area = max(1, d_rect.width() * d_rect.height())
                        if diag:
                            print(
                                f"[ElementPicker DIAG] {label_prefix}raw {raw_ms}ms → "
                                f"area={d_area}",
                                flush=True,
                            )
                        # 현재 element 가 clickable 이고 raw 결과가 비클릭이면 descent 거부
                        # (메뉴 MenuItem → 내부 TextBlock 처럼 hit-test 가 안 되는 leaf 회피)
                        if (
                            d_area < current_area
                            and d_rect.width() > 0
                            and d_rect.height() > 0
                            and not (
                                self._is_clickable_element(element)
                                and not self._is_clickable_element(deeper)
                            )
                        ):
                            element = deeper
                            rect = d_rect
                            current_area = d_area
                        elif (
                            diag
                            and self._is_clickable_element(element)
                            and not self._is_clickable_element(deeper)
                        ):
                            print(
                                f"[ElementPicker DIAG] {label_prefix}raw descent 거부 "
                                f"— current clickable, deeper non-clickable",
                                flush=True,
                            )
                    except Exception:
                        pass
                elif diag:
                    print(
                        f"[ElementPicker DIAG] {label_prefix}raw {raw_ms}ms → 매칭 없음", flush=True
                    )

            # 3) descendants() 폴백 — Chrome 같은 sparse children 케이스.
            #    walker 가 이미 작은 element (Excel cell, 메뉴 항목 등) 잡았으면
            #    skip 해서 매 tick 800-1000ms 절약 (반응성 향상).
            budget_remaining = self._uia_time_budget_sec - (time.time() - t0)
            if budget_remaining > 0.03 and current_area > self.NEEDS_DESCENDANTS_AREA_THRESHOLD:
                t2 = time.time()
                desc_result = self._find_deepest_descendant(
                    window_wrapper,
                    x_phys,
                    y_phys,
                    budget_remaining,
                )
                desc_ms = int((time.time() - t2) * 1000)
                if desc_result is not None:
                    try:
                        ds_rect = desc_result.rectangle()
                        ds_area = max(1, ds_rect.width() * ds_rect.height())
                        if diag:
                            print(
                                f"[ElementPicker DIAG] {label_prefix}descendants {desc_ms}ms "
                                f"→ area={ds_area}",
                                flush=True,
                            )
                        # raw 와 동일 가드: clickable element 를 비클릭 leaf 로 안 바꿈
                        if (
                            ds_area < current_area
                            and ds_rect.width() > 0
                            and ds_rect.height() > 0
                            and not (
                                self._is_clickable_element(element)
                                and not self._is_clickable_element(desc_result)
                            )
                        ):
                            element = desc_result
                            rect = ds_rect
                            current_area = ds_area
                    except Exception:
                        pass
                elif diag:
                    print(
                        f"[ElementPicker DIAG] {label_prefix}descendants {desc_ms}ms → 매칭 없음",
                        flush=True,
                    )

            if rect.width() > 0 and rect.height() > 0:
                return element, rect, current_area
        except Exception as e:
            if diag:
                print(f"[ElementPicker DIAG] {label_prefix}detection 실패: {e}", flush=True)

        return None, None, None

    def _detect_element_multi_backend(self, x_phys: int, y_phys: int):
        """
        다중 백엔드를 사용하여 커서 위치의 UI 요소를 감지합니다.

        설계 (회귀 방지):
          1. EFP (IUIAutomation::ElementFromPoint) — Excel 셀 같은 deeply-nested
             가상 element reach. overlay 가 hit-test 에서 자기 자신을 잡지 않도록
             WS_EX_TRANSPARENT 를 EFP 호출 동안만 짧게 토글 (수 ms).
             누수 가능성 있지만 호출 시간이 매우 짧아 시각적 효과 거의 없음.
          2. main HWND (e.g., Chrome_WidgetWin_1) 의 UIA tree 에서 검색 → 탭/URL bar
          3. child HWND (e.g., Chrome Legacy Window) 의 UIA tree → HTML 콘텐츠
          4. 셋 중 더 깊은 (= 더 작은 면적) 결과 채택

        과거 회귀: 토글 안에서 walker / descendants (50-200ms) 까지 실행해서
        underlying mouseover 누수 발견됨. 지금은 EFP 만 토글 안에서 (수 ms) +
        walker 들은 토글 밖에서 (자체 트리 검색이라 overlay 영향 안 받음).

        Returns:
            tuple: (element, backend_name) 또는 (None, None)
        """
        if not user32:
            return None, None

        overlay_hwnd = int(self.winId())
        diag = getattr(self, "_diag_tick_count", 99) <= 10

        # 0) IUIAutomation::ElementFromPoint — overlay 짧게 hit-test 제외 후 호출.
        #    Excel 셀, MFC+WebView 같은 lazy/virtual element 까지 OS 가 reach.
        ex_style = user32.GetWindowLongW(overlay_hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            overlay_hwnd,
            GWL_EXSTYLE,
            ex_style | WS_EX_TRANSPARENT,
        )
        try:
            best_element, best_rect, best_area = self._detect_via_efp(
                x_phys,
                y_phys,
            )
        finally:
            user32.SetWindowLongW(overlay_hwnd, GWL_EXSTYLE, ex_style)

        # 1) z-order 순회로 main HWND 찾기 (e.g., Chrome_WidgetWin_1)
        main_hwnd = self._find_topmost_window_at_point(x_phys, y_phys, overlay_hwnd)
        if diag:
            print(
                f"[ElementPicker DIAG] _find_topmost_window_at_point → "
                f"{'0x%x' % main_hwnd if main_hwnd else 'None'}",
                flush=True,
            )
        if not main_hwnd:
            # main HWND 못 찾았어도 EFP 가 잡았으면 그걸 반환
            if best_element is not None and best_rect is not None:
                if best_rect.width() > 0 and best_rect.height() > 0:
                    if diag:
                        print("[ElementPicker DIAG] main HWND 없음 → EFP 결과 반환", flush=True)
                    return best_element, "uia"
            return None, None

        # 2) child HWND 도 추출 (e.g., Chrome Legacy Window/renderer)
        child_hwnd = None
        try:
            client_pt = ctypes.wintypes.POINT(x_phys, y_phys)
            user32.ScreenToClient(main_hwnd, ctypes.byref(client_pt))
            ch = user32.ChildWindowFromPointEx(main_hwnd, client_pt, 3)
            if diag:
                print(
                    f"[ElementPicker DIAG] ChildWindowFromPointEx → "
                    f"child={'0x%x' % ch if ch else 'None'}",
                    flush=True,
                )
            if ch and ch != main_hwnd:
                child_hwnd = ch
        except Exception as e:
            if diag:
                print(f"[ElementPicker DIAG] ChildWindowFromPointEx 예외: {e}", flush=True)

        # 3) 양쪽 HWND 의 UIA tree 에서 검색 — main 은 chrome UI (탭 strip 등),
        #    child 는 콘텐츠 (HTML 페이지 등). 둘 중 더 깊은 결과 채택.
        #    best_* 는 §0 의 EFP 결과로 이미 초기화 — walker 가 더 작은 area 면 갱신.
        candidates = [(main_hwnd, "main")]
        if child_hwnd:
            candidates.append((child_hwnd, "child"))

        for hwnd, label in candidates:
            elem, rect, area = self._detect_in_hwnd(hwnd, x_phys, y_phys, label)
            if elem is not None and area is not None:
                if best_area is None or area < best_area:
                    # 사용자 보고 (5/5): Win11 메모장 메뉴 [Text] 라벨 클릭 안 됨 — picker 가
                    # EFP MenuItem '파일' (clickable) 을 받았는데 더 작은 leaf 로 descend 해서
                    # control_type='Text' 로 저장 → pywinauto child_window(control_type='Text')
                    # 가 그 leaf 못 찾음 (picker uiautomation vs pywinauto IUIAutomation 차이).
                    # 현재 best_element 가 클릭 가능한 타입이고 새 candidate 는 비클릭이면
                    # 면적이 작아도 채택 안 함 (clickable 부모 보존).
                    if (
                        best_element is not None
                        and self._is_clickable_element(best_element)
                        and not self._is_clickable_element(elem)
                    ):
                        if diag:
                            print(
                                f"[ElementPicker DIAG] [{label}] descent 거부 — "
                                f"기존 candidate 가 clickable, 새 candidate 는 비클릭 "
                                f"(area={area} < {best_area} 무시)",
                                flush=True,
                            )
                        continue
                    best_element = elem
                    best_rect = rect
                    best_area = area
                    if diag:
                        print(
                            f"[ElementPicker DIAG] [{label}] 채택 "
                            f"(area={area} {'<' if best_area == area else '<='} prev)",
                            flush=True,
                        )

        if best_element is not None and best_rect is not None:
            if best_rect.width() > 0 and best_rect.height() > 0:
                return best_element, "uia"

        # 4) Win32 폴백 (UIA 모두 실패 시 main HWND 만)
        try:
            from pywinauto.controls.hwndwrapper import HwndWrapper

            element = HwndWrapper(main_hwnd)
            if diag:
                print(f"[ElementPicker DIAG] Win32 wrap(0x{main_hwnd:x}) → {element!r}", flush=True)
            try:
                rect = element.rectangle()
                if rect.width() > 0 and rect.height() > 0:
                    return element, "win32"
            except Exception as e:
                if diag:
                    print(f"[ElementPicker DIAG] Win32 rectangle() 실패: {e}", flush=True)
        except Exception as e:
            if diag:
                print(f"[ElementPicker DIAG] Win32 wrap 실패: {e}", flush=True)

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
        child_hwnd = user32.ChildWindowFromPointEx(target_hwnd, client_pt, 3)
        if child_hwnd and child_hwnd != target_hwnd:
            target_hwnd = child_hwnd

        # pywinauto로 래핑 시도
        try:
            from pywinauto import Desktop

            # UIA로 먼저 시도
            try:
                desktop = Desktop(backend="uia")
                element = desktop.from_handle(target_hwnd)
                if element:
                    return element, "win32api+uia"
            except Exception:
                pass

            # Win32로 시도
            try:
                desktop = Desktop(backend="win32")
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

        # 진단: picker 시작 후 첫 10 tick (~1초) 의 진행 상황을 사용자 콘솔에 직접 출력.
        # 사용자가 picker 시작 후 cursor 를 원하는 위치 (탭 등) 로 옮길 시간 확보.
        if not hasattr(self, "_diag_tick_count"):
            self._diag_tick_count = 0
        self._diag_tick_count += 1
        diag = self._diag_tick_count <= 10

        try:
            # Win32 물리 좌표 (pywinauto 요소 감지용)
            pt_phys = ctypes.wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt_phys))
            x_phys, y_phys = pt_phys.x, pt_phys.y

            # Qt 논리 좌표 (오버레이 로컬 좌표 계산용)
            cursor_logical = QCursor.pos()

            if diag:
                print(
                    f"[ElementPicker DIAG #{self._diag_tick_count}] "
                    f"cursor phys=({x_phys},{y_phys}) overlay_hwnd=0x{int(self.winId()):x}",
                    flush=True,
                )

            # 다중 백엔드로 요소 감지
            element, backend_used = self._detect_element_multi_backend(x_phys, y_phys)

            if diag:
                if element is None:
                    print(
                        f"[ElementPicker DIAG #{self._diag_tick_count}] "
                        f"_detect_element_multi_backend → None (감지 실패)",
                        flush=True,
                    )
                else:
                    try:
                        r = element.rectangle()
                        print(
                            f"[ElementPicker DIAG #{self._diag_tick_count}] "
                            f"감지 OK backend={backend_used} "
                            f"rect=({r.left},{r.top})~({r.right},{r.bottom}) "
                            f"size={r.width()}x{r.height()}",
                            flush=True,
                        )
                    except Exception as _re:
                        print(
                            f"[ElementPicker DIAG #{self._diag_tick_count}] "
                            f"감지 OK backend={backend_used} 그러나 rectangle() 실패: {_re}",
                            flush=True,
                        )

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

                    # 부모 윈도우 정보 (top-level)
                    # 다이얼로그/팝업/메인 윈도우 구분을 위해 control_type 도 capture.
                    # AI 가 element_context 에서 모달 다이얼로그 / 메인 윈도우를 분간 가능
                    # → 가이드 #18 의 dialog 처리 패턴 자동 트리거.
                    parent_title = ""
                    parent_class = ""
                    parent_control_type = ""
                    try:
                        top = element.top_level_parent()
                        if top:
                            parent_title = top.window_text() or ""
                            parent_class = top.class_name() or ""
                            try:
                                parent_control_type = top.element_info.control_type or ""
                            except Exception:
                                pass
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
                            # title + text를 하나의 XPath OR 조건으로 합쳐서 불필요한 10초 타임아웃 방지.
                            # 예: <span class="ax-menu-item-label">실패사례</span> 처럼 @title 속성이
                            # 없는 SPA 메뉴 아이템도 text 조건으로 즉시 찾을 수 있음.
                            _safe = name[:200].replace('"', "'")
                            locator_candidates.append(
                                (
                                    "xpath",
                                    f'//*[normalize-space(@title)="{_safe}"'
                                    f" or (not(self::script) and not(self::style)"
                                    f' and normalize-space(.)="{_safe}")]',
                                )
                            )

                    self._current_element_ref = element  # 계층 수집용 레퍼런스 보관
                    self._current_element_info = {
                        "control_type": ctrl_type,
                        "name": name[:200],
                        "automation_id": auto_id,
                        "class_name": element.class_name()
                        if hasattr(element, "class_name")
                        else "",
                        "rect": {
                            "left": rect.left,
                            "top": rect.top,
                            "right": rect.right,
                            "bottom": rect.bottom,
                            "width": rect.width(),
                            "height": rect.height(),
                        },
                        "parent_window_title": parent_title,
                        "parent_window_class": parent_class,
                        "parent_window_control_type": parent_control_type,
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
                        lines.append(
                            f"백엔드: {backend_used or 'uia'} → 권장: {recommended_backend}"
                        )

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
        if not hasattr(self, "_paint_logged"):
            self._paint_logged = True
            geo = self.geometry()
            logger.info(
                f"[paintEvent] 실제 위젯 geometry: ({geo.x()},{geo.y()}) "
                f"크기:{geo.width()}x{geo.height()} | "
                f"rect(): {self.rect().width()}x{self.rect().height()}"
            )

        # 반투명 배경 (alpha>0 으로 Windows hit-test 차단 — click-through 방지)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 30))

        # 하이라이트 사각형
        if not self._highlight_rect.isNull():
            # 핵심: 하이라이트 영역도 alpha=0 으로 만들지 않는다.
            # Windows 의 layered window 는 alpha=0 픽셀을 자동 click-through 하므로
            # CompositionMode_Clear 로 구멍을 뚫으면 mouse-move 이벤트가 그 아래
            # 앱으로 새어 나가 mouse-over 효과가 발동된다 (이전 버그).
            # 대신 highlight 영역의 dim 을 약간 줄이는 방식으로 시각적 강조만 유지.

            # 1) 배경 dim 을 부분 상쇄 — alpha=30 - 20 ≈ 10 효과 (alpha>0 유지로 hit-test 차단)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
            painter.fillRect(self._highlight_rect, QColor(0, 0, 0, 20))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # 2) 빨간 테두리
            pen = QPen(QColor("#f38ba8"), 3)
            painter.setPen(pen)
            painter.drawRect(self._highlight_rect)

            # 3) 내부 반투명 채우기 (강조)
            painter.fillRect(self._highlight_rect, QColor(243, 139, 168, 30))

        # 상단 안내 문구
        painter.setPen(QColor("#cdd6f4"))
        painter.setFont(QFont("Malgun Gothic", 14, QFont.Weight.Bold))
        guide_text = "🎯 클릭하여 UI 요소 선택  |  F3: 일시정지  |  ESC: 취소"
        painter.drawText(
            self.rect().adjusted(0, 20, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            guide_text,
        )

        # 디버그: 모니터 정보 표시 (두 번째 줄)
        if self._current_screen_info:
            painter.setFont(QFont("Consolas", 11))
            painter.setPen(QColor("#fab387"))  # 주황색
            painter.drawText(
                self.rect().adjusted(0, 50, 0, 0),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                self._current_screen_info,
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
                    return (
                        True,
                        "OpenProcess 접근 거부 (ACCESS_DENIED) → 관리자 권한 프로세스로 추정",
                    )
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
                        ctypes.byref(ret_len),
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
                handle = getattr(current, "handle", None)
                if handle and handle in visited:
                    break
                if handle:
                    visited.add(handle)

                info: dict[str, Any] = {}
                info["name"] = (current.window_text() or "")[:120]
                info["class_name"] = current.class_name() or ""

                try:
                    info["control_type"] = current.element_info.control_type or ""
                except Exception:
                    info["control_type"] = ""

                try:
                    info["automation_id"] = current.element_info.automation_id or ""
                except Exception:
                    info["automation_id"] = ""

                try:
                    r = current.rectangle()
                    info["rect"] = (r.left, r.top, r.right, r.bottom, r.width(), r.height())
                except Exception:
                    info["rect"] = None

                try:
                    info["handle"] = hex(current.handle) if current.handle else ""
                except Exception:
                    info["handle"] = ""

                try:
                    info["process_id"] = current.process_id()
                except Exception:
                    info["process_id"] = 0

                try:
                    info["is_visible"] = current.is_visible()
                except Exception:
                    info["is_visible"] = None

                try:
                    info["is_enabled"] = current.is_enabled()
                except Exception:
                    info["is_enabled"] = None

                hierarchy.append(info)

                # 부모로 이동
                try:
                    parent = current.parent()
                    if parent is None:
                        break
                    # 부모가 자기 자신이면 종료
                    parent_handle = getattr(parent, "handle", None)
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
                logger.info(
                    "  *** WM 메시지(click/click_input) 불가 - pyautogui.click(x,y) 사용 필요 ***"
                )

        logger.info(
            f"  감지 백엔드: {element_info.get('detected_backend', '?')}"
            f"  →  권장 백엔드: {element_info.get('recommended_backend', '?')}"
        )
        logger.info("")

        # 선택된 요소 속성
        logger.info("  [선택된 요소 속성]")
        logger.info(f"    control_type : {element_info.get('control_type', '')}")
        logger.info(f'    name         : "{element_info.get("name", "")}"')
        logger.info(f"    class_name   : {element_info.get('class_name', '')}")
        logger.info(f"    automation_id: {element_info.get('automation_id', '') or '(없음)'}")
        r = element_info.get("rect", {})
        if r:
            logger.info(
                f"    rect         : ({r.get('left')},{r.get('top')}) "
                f"~ ({r.get('right')},{r.get('bottom')})  "
                f"크기:{r.get('width')}×{r.get('height')}"
            )
        logger.info(
            f"    화면 좌표    : ({element_info.get('screen_x')}, {element_info.get('screen_y')})"
        )
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
                        label = (
                            "(선택)"
                            if i == 0
                            else f"(부모 {i})"
                            if i < len(hierarchy) - 1
                            else "(루트)"
                        )

                        ctrl = lvl.get("control_type") or lvl.get("class_name") or "?"
                        name_str = f' "{lvl["name"]}"' if lvl.get("name") else ""
                        cls_str = f"  class={lvl['class_name']}" if lvl.get("class_name") else ""
                        aid_str = f"  id={lvl['automation_id']}" if lvl.get("automation_id") else ""
                        hwnd_str = f"  hwnd={lvl['handle']}" if lvl.get("handle") else ""

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

    def _capture_dom_context(self, name: str, auto_id: str) -> dict:
        """
        Chrome CDP(포트 9222)를 통해 현재 페이지의 DOM 컨텍스트를 수집합니다.
        CDP 포트가 없거나 Selenium 연결 실패 시 빈 dict 반환 (비파괴적).

        설정의 cdp_enabled=False (default) 면 즉시 빈 dict 반환 — 매 click
        마다 CDP 포트 탐색 timeout (수백 ms) 회피해서 picker 응답성 유지.

        반환 키:
            cdp_available (bool)
            page_url, page_title (str)
            xpath, outerHTML, tagName, textContent (str)
            attributes (dict)  — 실제 HTML 속성 목록 (title 존재 여부 확인용)
            hasTitle (bool)
            parentOuterHTML (str)
        """
        if not self._cdp_enabled:
            return {"cdp_available": False}

        import urllib.request

        # CDP 포트 탐색 (9222 → 9223 → 9224). timeout 짧게 — 미연결 환경에서
        # 사용자 click → 메인 화면 띄워지는 시간 단축 (3초 → ~1초).
        cdp_port: int | None = None
        for port in (9222, 9223, 9224):
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{port}/json/version", timeout=0.3
                ) as resp:
                    if resp.status == 200:
                        cdp_port = port
                        break
            except Exception:
                continue

        if not cdp_port:
            logger.debug(
                "DOM 컨텍스트 수집 스킵: CDP 포트 없음 (Chrome --remote-debugging-port=9222 필요)"
            )
            return {"cdp_available": False}

        ctx: dict = {"cdp_available": True, "cdp_port": cdp_port}
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options as _ChromeOptions

            opts = _ChromeOptions()
            opts.add_experimental_option("debuggerAddress", f"localhost:{cdp_port}")
            driver = webdriver.Chrome(options=opts)

            try:
                ctx["page_url"] = driver.current_url
                ctx["page_title"] = driver.title

                result = driver.execute_script(
                    """
(function(elId, elText) {
    function getXPath(el) {
        if (!el) return '';
        if (el.id) return '//*[@id="' + el.id.replace(/"/g,'&quot;') + '"]';
        var parts = [];
        while (el && el.nodeType === 1) {
            var tag = el.tagName.toLowerCase();
            if (el.parentElement) {
                var sibs = Array.from(el.parentElement.children)
                    .filter(function(s){ return s.tagName === el.tagName; });
                if (sibs.length > 1) tag += '[' + (sibs.indexOf(el) + 1) + ']';
            }
            parts.unshift(tag);
            el = el.parentElement;
        }
        return '/' + parts.join('/');
    }
    function getAttrs(el) {
        var obj = {};
        if (!el || !el.attributes) return obj;
        Array.from(el.attributes).forEach(function(a){ obj[a.name] = a.value; });
        return obj;
    }
    function elInfo(el) {
        return {
            xpath: getXPath(el),
            outerHTML: el.outerHTML.substring(0, 1000),
            tagName: el.tagName.toLowerCase(),
            textContent: (el.textContent || '').trim().substring(0, 300),
            attributes: getAttrs(el),
            hasTitle: el.hasAttribute('title'),
            titleValue: el.getAttribute('title') || '',
            parentOuterHTML: el.parentElement ? el.parentElement.outerHTML.substring(0, 1500) : ''
        };
    }
    // 1순위: HTML id로 찾기
    if (elId) {
        var byId = document.getElementById(elId);
        if (byId) return elInfo(byId);
    }
    // 2순위: 텍스트가 정확히 일치하는 leaf 요소 (script/style 제외)
    if (elText) {
        var walker = document.createTreeWalker(
            document.body, NodeFilter.SHOW_ELEMENT, null, false);
        var found = null;
        while (walker.nextNode()) {
            var node = walker.currentNode;
            if (node.tagName === 'SCRIPT' || node.tagName === 'STYLE') continue;
            if ((node.textContent || '').trim() === elText) {
                found = node;
                break;
            }
        }
        if (found) return elInfo(found);
    }
    return null;
})(arguments[0], arguments[1]);
""",
                    auto_id or "",
                    name or "",
                )
                if result:
                    ctx.update(result)
                else:
                    ctx["dom_note"] = (
                        "해당 요소를 DOM에서 찾지 못함 (동적 렌더링 또는 텍스트 불일치)"
                    )

            finally:
                # debuggerAddress 모드: quit()은 chromedriver만 종료, 브라우저는 유지
                try:
                    driver.quit()
                except Exception:
                    pass

        except Exception as e:
            ctx["cdp_error"] = str(e)[:300]
            logger.debug(f"DOM 컨텍스트 수집 실패: {e}")

        return ctx

    def mousePressEvent(self, event):
        """클릭 시 요소 선택 완료"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 로깅에 필요한 레퍼런스를 stop_picking() 호출 전에 보관
            element_info = self._current_element_info.copy() if self._current_element_info else {}
            element_ref = self._current_element_ref
            self.stop_picking()
            if element_info:
                # 브라우저 요소인 경우 DOM 컨텍스트 수집 (CDP 연결 가능 시)
                if element_info.get("is_browser"):
                    dom_ctx = self._capture_dom_context(
                        element_info.get("name", ""),
                        element_info.get("automation_id", ""),
                    )
                    element_info["dom_context"] = dom_ctx
                self._log_element_details(element_info, element_ref)
                self.element_picked.emit(element_info)
            else:
                self.pick_cancelled.emit()
        elif event.button() == Qt.MouseButton.RightButton:
            self.stop_picking()
            self.pick_cancelled.emit()

    def keyPressEvent(self, event):
        """ESC로 취소, F3으로 일시정지 (3초 wait 후 picker 복귀)"""
        if event.key() == Qt.Key.Key_Escape:
            self._pause_label.hide()
            self.stop_picking()
            self.pick_cancelled.emit()
        elif event.key() == Qt.Key.Key_F3:
            if not self._paused:
                self._start_pause()

    def _start_pause(self):
        """F3 일시정지 시작 - 3초간 오버레이 숨기고 자유롭게 조작 가능.

        3초 후 _resume_after_pause 가 post_pause_mode 진입 — overlay 다시 띄우되
        WS_EX_TRANSPARENT 켜서 underlying app 으로 mouse 이벤트 통과 (펼친
        hover-only submenu 유지 + 다른 창 활성화 가능). click 은 WH_MOUSE_LL
        hook 으로 감지해서 element_picked emit 한 후 underlying 에 통과.

        Trade-off: post_pause_mode 동안만 underlying mouseover 누수 발생.
        일반 picker mode (F3 누르기 전) 의 누수 0 보장은 그대로 유지.
        """
        self._paused = True
        self._pause_countdown = 3
        self._track_timer.stop()
        # transition timer 가 active 면 정지 (post_pause 중 F3 재진입)
        if hasattr(self, "_post_pause_transition_timer"):
            self._post_pause_transition_timer.stop()

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
        F3 일시정지 후 picker 복귀 (post_pause_mode 진입).

        설계 (방향 B 통합):
        - WS_EX_NOACTIVATE: show() 시 focus 빼앗기 방지
        - WS_EX_TRANSPARENT: click-through 로 underlying 에 mouse 이벤트 통과
          → 펼친 hover-only submenu 유지 + wait 후 다른 창 활성화 자연스러움
        - WH_KEYBOARD_LL hook: F3/ESC 글로벌 가로챔 (overlay 가 키 못 받음)
        - WH_MOUSE_LL hook: 좌클릭 감지 + 통과. click 시 element_picked emit
          후 underlying 동작도 정상 진행.
        - _poll_mouse_click 폴링: hook 실패 시 fallback.

        Trade-off: post_pause_mode 동안만 underlying mouseover 누수 발생.
        일반 picker mode (F3 누르기 전) 의 누수 0 보장은 그대로.
        """
        self._post_pause_mode = True

        if sys.platform == "win32":
            hwnd = int(self.winId())
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                ex_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT,
            )
            self.show()
            self.raise_()
        else:
            self.show()
            self.raise_()

        # 커서 추적 재개 (하이라이트용)
        self._track_timer.start(self._track_interval)

        # 키보드 hook 은 start_picking 에서 이미 설치 — lifecycle 전체 유지
        # (재설치는 _install_keyboard_hook 의 idempotent guard 가 막음)

        # WS_EX_TRANSPARENT 켜진 overlay 는 mouse 이벤트 못 받음 → click 감지 hook
        self._install_mouse_hook()

        # 마우스 클릭 폴링 (hook 실패 시 fallback)
        if not hasattr(self, "_click_poll_timer"):
            self._click_poll_timer = QTimer(self)
            self._click_poll_timer.timeout.connect(self._poll_mouse_click)
        self._click_poll_timer.start(50)

        # 짧은 transition 후 일반 picker mode 로 자동 전환 — 누수 최소화 시도.
        # 가설: post_pause click-through 동안 OS 가 cursor 위치를 submenu 에
        # 등록한 후 TRANSPARENT 를 꺼도 cursor 좌표 변경 없으면 mouse-leave 미발생.
        # 실험 결과 (2026-04-29): SetWindowLongW 호출 시 OS 가 hit-test 다시 함 →
        # mouse-leave 트리거되어 menu 닫힘. 가설 실패. settings 로 0 (비활성)
        # 가능. 0 이면 post_pause_mode 가 click/ESC 까지 유지 (방향 B 직접).
        if self._post_pause_transition_ms > 0:
            if not hasattr(self, "_post_pause_transition_timer"):
                self._post_pause_transition_timer = QTimer(self)
                self._post_pause_transition_timer.setSingleShot(True)
                self._post_pause_transition_timer.timeout.connect(self._exit_post_pause_mode)
            self._post_pause_transition_timer.start(self._post_pause_transition_ms)

    # ── 저수준 키보드 훅 (WH_KEYBOARD_LL) ──

    def _install_keyboard_hook(self):
        """
        WH_KEYBOARD_LL 훅으로 F3/ESC 를 시스템 레벨에서 가로챔.

        picker 전체 lifecycle 동안 유지 (start_picking 부터 stop_picking 까지).
        focus 와 무관하게 키 입력 즉시 감지 → ESC/F3 응답성 보장.
        대상 앱에 키 이벤트가 전달되기 전에 차단해 메모장 "다음 찾기" 같은
        동작도 방지.
        """
        if sys.platform != "win32":
            return
        if hasattr(self, "_keyboard_hook") and self._keyboard_hook:
            return  # 이미 설치 — 재설치 방지 (leak)

        # 콜백 함수 타입 정의
        HOOKPROC = ctypes.CFUNCTYPE(
            ctypes.c_long,  # return: LRESULT
            ctypes.c_int,  # nCode
            ctypes.c_ulonglong,  # wParam (WPARAM, 64bit)
            ctypes.c_ulonglong,  # lParam (LPARAM, 64bit)
        )

        def _keyboard_hook_proc(nCode, wParam, lParam):
            """저수준 키보드 훅 콜백 — picker active (paused 또는 visible) 시 동작"""
            picker_active = self._paused or not self.isHidden()
            if nCode >= 0 and picker_active:
                # lParam은 KBDLLHOOKSTRUCT 포인터
                # 구조체의 첫 번째 DWORD가 vkCode
                vk_code = ctypes.cast(lParam, ctypes.POINTER(ctypes.c_ulong))[0]

                WM_KEYDOWN = 0x0100
                WM_KEYUP = 0x0101

                if vk_code == VK_F3:
                    if wParam == WM_KEYUP:
                        # F3 릴리즈 시 → 일시정지 진입 (이미 paused 면 _on_hook_f3 가 무시)
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
            0,  # dwThreadId: 0 for all threads
        )
        if not self._keyboard_hook:
            logger.warning("키보드 훅 설치 실패")

    def _uninstall_keyboard_hook(self):
        """저수준 키보드 훅 해제"""
        if hasattr(self, "_keyboard_hook") and self._keyboard_hook:
            user32.UnhookWindowsHookEx(self._keyboard_hook)
            self._keyboard_hook = None
        self._hook_proc_ref = None

    # ── 저수준 마우스 훅 (WH_MOUSE_LL) ──

    def _install_mouse_hook(self):
        """
        WH_MOUSE_LL 훅으로 좌/우 클릭을 시스템 레벨에서 감지 + 차단.

        post_pause_mode 의 overlay 는 WS_EX_TRANSPARENT 가 켜져 있어 mouse
        이벤트를 받지 못함 (방향 B 통합). hook 으로 click 감지하고 underlying
        에 전달은 차단 — 일반 picker mode 와 동일하게 picker 만 element 선택,
        underlying 메뉴/버튼은 클릭 효과 발동 안 함 (사용자 의도).

        - LBUTTONDOWN: element_picked emit + click 차단 (return 1)
        - LBUTTONUP: down/up consistency 위해 차단
        - RBUTTONDOWN: cancel + 차단 (일반 picker mode 의 우클릭 = cancel 과 일관)
        - RBUTTONUP: 차단
        """
        if sys.platform != "win32":
            return

        HOOKPROC = ctypes.CFUNCTYPE(
            ctypes.c_long,
            ctypes.c_int,
            ctypes.c_ulonglong,
            ctypes.c_ulonglong,
        )

        WM_LBUTTONDOWN = 0x0201
        WM_LBUTTONUP = 0x0202
        WM_RBUTTONDOWN = 0x0204
        WM_RBUTTONUP = 0x0205

        def _mouse_hook_proc(nCode, wParam, lParam):
            if nCode >= 0 and self._post_pause_mode:
                if wParam == WM_LBUTTONDOWN:
                    QTimer.singleShot(0, self._on_hook_click)
                    return 1  # underlying 에 click 전달 차단
                if wParam == WM_LBUTTONUP:
                    return 1  # down/up consistency
                if wParam == WM_RBUTTONDOWN:
                    QTimer.singleShot(0, self._on_hook_rclick)
                    return 1
                if wParam == WM_RBUTTONUP:
                    return 1
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        # GC 방지용 레퍼런스 유지
        self._mouse_hook_proc_ref = HOOKPROC(_mouse_hook_proc)

        WH_MOUSE_LL = 14
        self._mouse_hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL,
            self._mouse_hook_proc_ref,
            None,
            0,
        )
        if not self._mouse_hook:
            logger.warning("마우스 훅 설치 실패 (Shift+F3 모드 클릭 감지가 폴링에만 의존)")

    def _uninstall_mouse_hook(self):
        """저수준 마우스 훅 해제"""
        if hasattr(self, "_mouse_hook") and self._mouse_hook:
            user32.UnhookWindowsHookEx(self._mouse_hook)
            self._mouse_hook = None
        self._mouse_hook_proc_ref = None

    def _on_hook_click(self):
        """훅에서 좌클릭 감지 → 요소 선택 + picker 종료.

        _poll_mouse_click 과 동일 흐름. 둘 중 먼저 발동되는 쪽이
        _post_pause_mode 를 False 로 바꿔 다른 쪽은 no-op.
        """
        if not self._post_pause_mode:
            return
        self._exit_post_pause_mode()
        element_info = self._current_element_info.copy() if self._current_element_info else {}
        element_ref = self._current_element_ref
        self.stop_picking()
        if element_info:
            self._log_element_details(element_info, element_ref)
            self.element_picked.emit(element_info)
        else:
            self.pick_cancelled.emit()

    def _on_hook_rclick(self):
        """훅에서 우클릭 감지 → picker 취소 (일반 picker mode 와 일관)."""
        if not self._post_pause_mode:
            return
        self._exit_post_pause_mode()
        self.stop_picking()
        self.pick_cancelled.emit()

    def _on_hook_f3(self):
        """훅에서 F3 감지 → 일시정지 진입.

        일반 picker mode + post_pause_mode 둘 다 처리 (lifecycle 통합).
        wait 중이면 무시 (이미 paused).
        """
        if self._paused:
            return
        if self._post_pause_mode:
            self._exit_post_pause_mode()
        self._start_pause()

    def _on_hook_esc(self):
        """훅에서 ESC 감지 → picker 취소.

        일반 picker mode + post_pause + wait 중 어디서든 즉시 종료.
        focus 와 무관하게 hook 으로 가로채니 응답성 보장.
        """
        if self._post_pause_mode:
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
        """post_pause 모드 종료: 훅 해제, 타이머 정지, ex-style 정리.

        _resume_after_pause 가 켠 WS_EX_NOACTIVATE 와 WS_EX_TRANSPARENT 둘 다 제거.

        호출 경로 (3가지):
        - 사용자 click/ESC → _on_hook_click / _on_hook_esc
        - F3 재진입 → _on_hook_f3 (다음에 _start_pause)
        - **자동 transition** → POST_PAUSE_TRANSITION_MS 후 자동 호출 (가설:
          submenu 등록 후 mode 전환해도 menu 유지)
        """
        if not self._post_pause_mode:
            return  # idempotent — transition timer 와 user 액션 동시 fire 방어
        self._post_pause_mode = False
        if hasattr(self, "_post_pause_transition_timer"):
            self._post_pause_transition_timer.stop()
        # keyboard hook 은 picker 전체 lifecycle 유지 — 여기선 해제 안 함
        self._uninstall_mouse_hook()
        if hasattr(self, "_click_poll_timer"):
            self._click_poll_timer.stop()
        if sys.platform == "win32":
            hwnd = int(self.winId())
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                ex_style & ~WS_EX_NOACTIVATE & ~WS_EX_TRANSPARENT,
            )

    def _update_pause_label(self):
        """일시정지 카운트다운 라벨 업데이트"""
        self._pause_label.setText(
            f"  ⏸️ 일시정지 중... {self._pause_countdown}초 후 재개  |  "
            f"마우스/키보드 자유롭게 조작하세요  "
        )
        self._pause_label.adjustSize()

        # 화면 중앙 상단에 배치
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self._pause_label.width()) // 2
            y = geo.y() + 50
            self._pause_label.move(x, y)
