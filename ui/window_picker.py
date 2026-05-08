# SPDX-License-Identifier: AGPL-3.0-or-later
"""
윈도우 피커 — 요소 레벨 하이라이트

전체 화면 오버레이를 사용하지 않고,
타이머로 커서 아래의 UI 요소(윈도우, 버튼, 텍스트박스 등)를 직접 폴링합니다.
하이라이트는 별도의 빨간색 테두리 프레임 윈도우로 표시합니다.

이 방식은 WS_EX_TRANSPARENT 의존 문제를 완전히 제거합니다.
"""

import ctypes
import ctypes.wintypes

from PyQt6.QtCore import QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPaintEvent, QRegion
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

# Win32 상수
VK_LBUTTON = 0x01
VK_ESCAPE = 0x1B
VK_F3 = 0x72
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x20
WS_EX_LAYERED = 0x80000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
LWA_ALPHA = 0x02
GA_ROOT = 2
CWP_SKIPINVISIBLE = 0x0001
CWP_SKIPDISABLED = 0x0002
CWP_SKIPTRANSPARENT = 0x0004
GW_OWNER = 4

# MonitorInfo 상수
MONITOR_DEFAULTTONEAREST = 2

user32 = ctypes.windll.user32  # type: ignore


def _get_class_name(hwnd: int) -> str:
    """윈도우 클래스 이름을 반환합니다."""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _get_window_text(hwnd: int) -> str:
    """윈도우 텍스트(타이틀)를 반환합니다."""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def _get_window_rect_qrect(hwnd: int) -> QRect:
    """윈도우의 스크린 좌표 영역을 QRect로 반환합니다(물리적 픽셀)."""
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return QRect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


# ── 멀티 모니터 DPI 좌표 변환 ──


class _MONITORINFOEXW(ctypes.Structure):
    """Win32 MONITORINFOEXW — 디바이스 이름 포함"""

    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("rcMonitor", ctypes.wintypes.RECT),
        ("rcWork", ctypes.wintypes.RECT),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("szDevice", ctypes.c_wchar * 32),
    ]


def _physical_to_logical_rect(phys_rect: QRect) -> QRect:
    """
    Win32 물리적 픽셀 좌표를 Qt 논리적 좌표로 변환합니다.

    멀티 모니터 환경에서 각 모니터의 DPI가 다를 때,
    MONITORINFOEXW.szDevice ↔ QScreen.name() 을 매칭하여
    정확한 좌표 변환을 수행합니다.
    """
    cx, cy = phys_rect.center().x(), phys_rect.center().y()

    # 1) 물리적 좌표가 속한 모니터 정보 (디바이스 이름 포함)
    pt = ctypes.wintypes.POINT(cx, cy)
    hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
    mi = _MONITORINFOEXW()
    mi.cbSize = ctypes.sizeof(_MONITORINFOEXW)
    user32.GetMonitorInfoW(hmon, ctypes.byref(mi))

    phys_mon_x = mi.rcMonitor.left
    phys_mon_y = mi.rcMonitor.top
    phys_mon_w = mi.rcMonitor.right - mi.rcMonitor.left
    phys_mon_h = mi.rcMonitor.bottom - mi.rcMonitor.top
    device_name = mi.szDevice.rstrip("\x00")

    # 2) 매칭되는 Qt 스크린 찾기
    target_screen = None
    for screen in QApplication.screens():
        qt_name = screen.name().rstrip("\x00")
        # 디바이스 이름 직접 비교 (\\.\ 접두사 유무 모두 처리)
        if qt_name == device_name:
            target_screen = screen
            break
        # 접두사 제거 후 비교
        clean_qt = qt_name.replace("\\\\.\\", "")
        clean_win = device_name.replace("\\\\.\\", "")
        if clean_qt == clean_win:
            target_screen = screen
            break

    if not target_screen:
        # fallback: 물리적 크기 + DPR로 매칭
        for screen in QApplication.screens():
            geo = screen.geometry()
            dpr = screen.devicePixelRatio()
            if (
                abs(int(geo.width() * dpr) - phys_mon_w) < 10
                and abs(int(geo.height() * dpr) - phys_mon_h) < 10
            ):
                target_screen = screen
                break

    if not target_screen:
        target_screen = QApplication.primaryScreen()

    # 3) 좌표 변환: physical → logical
    dpr = target_screen.devicePixelRatio()
    logical_geo = target_screen.geometry()

    logical_x = logical_geo.x() + (phys_rect.x() - phys_mon_x) / dpr
    logical_y = logical_geo.y() + (phys_rect.y() - phys_mon_y) / dpr
    logical_w = phys_rect.width() / dpr
    logical_h = phys_rect.height() / dpr

    return QRect(int(logical_x), int(logical_y), int(logical_w), int(logical_h))


def _physical_to_logical_point(phys_x: int, phys_y: int):
    """물리적 좌표 → Qt 논리적 좌표 (x, y) 튜플"""
    r = _physical_to_logical_rect(QRect(phys_x, phys_y, 1, 1))
    return r.x(), r.y()


def _get_monitor_work_area(x: int, y: int) -> ctypes.wintypes.RECT:
    """주어진 물리 좌표가 속한 모니터의 작업 영역(물리 좌표)을 반환"""
    pt = ctypes.wintypes.POINT(x, y)
    hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
    mi = _MONITORINFOEXW()
    mi.cbSize = ctypes.sizeof(_MONITORINFOEXW)
    user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
    return mi.rcWork


def _deepest_child_at(hwnd: int, screen_x: int, screen_y: int) -> int:
    """
    주어진 스크린 좌표에 있는 가장 깊은 자식 윈도우를 반환합니다.
    RealChildWindowFromPoint를 재귀적으로 호출하여 최하위 요소를 찾습니다.
    """
    current = hwnd
    while True:
        # 스크린 좌표 → 부모 클라이언트 좌표로 변환
        pt = ctypes.wintypes.POINT(screen_x, screen_y)
        user32.ScreenToClient(current, ctypes.byref(pt))

        # 해당 좌표에 있는 자식 윈도우 찾기
        child = user32.RealChildWindowFromPoint(current, ctypes.wintypes.POINT(pt.x, pt.y))

        if not child or child == current:
            break
        current = child

    return current


# ──────────────────────────────────────────────
# 헬퍼: 하이라이트 테두리 프레임 (빨간색)
# ──────────────────────────────────────────────
class _HighlightFrame(QWidget):
    """
    타겟 요소 주변에 표시되는 빨간색 테두리 전용 프레임.
    WA_TranslucentBackground 대신 QRegion 마스크를 사용하여
    레이어드 윈도우 충돌(UpdateLayeredWindowIndirect 에러)을 방지합니다.
    """

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        # WA_TranslucentBackground 사용하지 않음 → 레이어드 윈도우 불필요
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._border_width = 3

    def showEvent(self, event):
        super().showEvent(event)
        self._update_mask()
        QTimer.singleShot(0, self._make_click_through)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_mask()

    def _update_mask(self):
        """테두리 모양의 QRegion 마스크를 설정 — 내부는 완전히 비어있음"""
        w, h = self.width(), self.height()
        if w < 1 or h < 1:
            return
        bw = self._border_width
        outer = QRegion(0, 0, w, h)
        inner = QRegion(bw, bw, max(1, w - 2 * bw), max(1, h - 2 * bw))
        self.setMask(outer.subtracted(inner))

    def _make_click_through(self):
        try:
            hwnd = int(self.winId())
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            # WS_EX_TRANSPARENT: 마우스 클릭 통과
            # WS_EX_LAYERED + SetLayeredWindowAttributes 사용하지 않음
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, ex | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            )
        except Exception:
            pass

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        # 빨간색으로 전체 영역 채우기 (마스크가 테두리 모양만 남김)
        p.fillRect(self.rect(), QColor(255, 50, 50))
        p.end()

    def move_to_rect(self, rect: QRect):
        """
        주어진 물리적 픽셀 좌표 QRect 를
        Qt 논리적 좌표로 변환하여 프레임 이동/리사이즈.
        """
        margin = self._border_width + 1
        phys = QRect(
            rect.x() - margin,
            rect.y() - margin,
            rect.width() + margin * 2,
            rect.height() + margin * 2,
        )
        logical = _physical_to_logical_rect(phys)
        self.setGeometry(logical)


# ──────────────────────────────────────────────
# 헬퍼: 가이드 라벨 (화면 상단)
# ──────────────────────────────────────────────
class _GuideLabel(QLabel):
    """화면 상단에 뜨는 안내 라벨"""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.setStyleSheet("""
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
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._make_click_through)

    def _make_click_through(self):
        try:
            hwnd = int(self.winId())
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            # WS_EX_TRANSPARENT만 추가 — SetLayeredWindowAttributes 호출하지 않음
            # (Qt가 WA_TranslucentBackground로 이미 per-pixel alpha 관리 중)
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, ex | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            )
        except Exception:
            pass

    def place_top_center(self):
        """커서가 위치한 모니터의 상단 중앙에 배치 (논리 좌표)"""
        self.adjustSize()
        try:
            # 커서의 물리 좌표 → 소속 모니터 작업 영역 → 논리 좌표로 변환
            pt = ctypes.wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            work_area = _get_monitor_work_area(pt.x, pt.y)
            phys_center_x = (work_area.left + work_area.right) // 2
            phys_top_y = work_area.top + 18

            lx, ly = _physical_to_logical_point(phys_center_x, phys_top_y)
            x = lx - self.width() // 2
            y = ly
            self.move(x, y)
        except Exception:
            # fallback
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                x = geo.x() + (geo.width() - self.width()) // 2
                y = geo.y() + 18
                self.move(x, y)


# ──────────────────────────────────────────────
# 헬퍼: 타이틀 라벨 (하이라이트 근처)
# ──────────────────────────────────────────────
class _TitleLabel(QLabel):
    """호버 중인 요소 정보를 보여주는 라벨"""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.setStyleSheet("""
            QLabel {
                background-color: rgba(180, 30, 30, 230);
                color: white;
                font-family: 'Malgun Gothic';
                font-size: 11px;
                font-weight: bold;
                padding: 5px 12px;
                border-radius: 4px;
            }
        """)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._make_click_through)

    def _make_click_through(self):
        try:
            hwnd = int(self.winId())
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            # WS_EX_TRANSPARENT만 추가 — SetLayeredWindowAttributes 호출하지 않음
            # (Qt가 WA_TranslucentBackground로 이미 per-pixel alpha 관리 중)
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, ex | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            )
        except Exception:
            pass

    def place_near_rect(self, rect: QRect):
        """
        하이라이트 영역(물리 좌표) 바로 아래에 배치 (공간 없으면 위).
        물리 좌표를 논리 좌표로 변환하여 move 합니다.
        """
        self.adjustSize()

        # self.height()은 논리 픽셀 — 물리 높이로 변환하여 경계 비교
        try:
            screen = QApplication.primaryScreen()
            dpr = screen.devicePixelRatio() if screen else 1.0
        except Exception:
            dpr = 1.0
        phys_label_h = int(self.height() * dpr)

        phys_x = rect.left()
        phys_y = rect.bottom() + 4

        # 대상 좌표가 속한 모니터의 작업 영역으로 경계 확인 (물리 좌표끼리 비교)
        try:
            work_area = _get_monitor_work_area(rect.center().x(), rect.center().y())
            if phys_y + phys_label_h > work_area.bottom:
                phys_y = rect.top() - phys_label_h - 4
        except Exception:
            pass

        # 물리 좌표 → 논리 좌표로 변환하여 이동
        lx, ly = _physical_to_logical_point(max(0, phys_x), max(0, phys_y))
        self.move(lx, ly)


# ══════════════════════════════════════════════
# WindowPickerOverlay  (메인 컨트롤러)
# ══════════════════════════════════════════════
class WindowPickerOverlay(QWidget):
    """
    윈도우 피커 컨트롤러.

    전체 화면 오버레이를 **사용하지 않습니다**.
    대신 타이머+Win32 폴링으로 커서 아래의 UI 요소(윈도우/버튼/텍스트 등)를 추적하고,
    빨간색 테두리 프레임으로 시각 피드백을 줍니다.

    사용법:
        picker.start_pick()   →  마우스 이동 시 빨간색 테두리 하이라이트
                               →  좌클릭 시 window_picked 시그널(root_hwnd, title)
                               →  ESC 시 pick_cancelled 시그널
    """

    window_picked = pyqtSignal(int, str)  # (root_hwnd, window_title)
    pick_cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hide()  # 이 위젯 자체는 표시하지 않음

        # 헬퍼 위젯들
        self._frame = _HighlightFrame()
        self._guide = _GuideLabel()
        self._title_label = _TitleLabel()

        # 상태
        self._hovered_hwnd = 0  # 현재 호버 중인 요소 핸들
        self._hovered_root_hwnd = 0  # 호버 요소의 최상위 부모 핸들
        self._hovered_rect = QRect()
        self._hovered_title = ""
        self._hovered_class = ""
        self._click_ready = False
        self._active = False
        self._paused = False  # F3 일시정지 상태
        self._pause_countdown = 0  # 남은 카운트다운 초
        self._f3_debounce = False  # F3 키 디바운스

        # 자체 위젯 핸들 — 무시 대상
        self._own_hwnds: set[int] = set()

        # 타이머: 30ms 폴링 (더 빠른 반응)
        self._track_timer = QTimer(self)
        self._track_timer.timeout.connect(self._tick)
        self._track_timer.setInterval(30)

    # ──────── public ────────

    def start_pick(self):
        """윈도우 피커를 시작합니다."""
        self._hovered_hwnd = 0
        self._hovered_root_hwnd = 0
        self._hovered_rect = QRect()
        self._hovered_title = ""
        self._hovered_class = ""
        self._click_ready = False
        self._active = True
        self._paused = False
        self._pause_countdown = 0
        self._f3_debounce = False

        # 무시할 자체 hwnd 수집
        self._collect_own_hwnds()

        # 가이드 라벨 표시
        self._guide.setText(
            "  🖱 검사할 윈도우 / 요소를 클릭하세요  |  F3: 일시정지  |  ESC: 취소  "
        )
        self._guide.place_top_center()
        self._guide.show()

        # 500ms 디바운스 후 클릭 수신 시작
        QTimer.singleShot(500, self._enable_click)

        # 타이머 시작
        self._track_timer.start()

    # ──────── 내부 ────────

    def _collect_own_hwnds(self):
        """헬퍼 위젯들의 hwnd + 부모 앱 윈도우 hwnd를 수집"""
        self._own_hwnds.clear()
        for w in (self, self._frame, self._guide, self._title_label):
            try:
                h = int(w.winId())
                if h:
                    self._own_hwnds.add(h)
                    # 최상위 부모도 추가
                    root = user32.GetAncestor(h, GA_ROOT)
                    if root:
                        self._own_hwnds.add(root)
            except Exception:
                pass

    def _enable_click(self):
        self._click_ready = True

    def _tick(self):
        """30ms마다: 커서 추적 + 입력 감지"""
        if not self._active:
            return

        # 일시정지 상태에서는 ESC만 체크
        if self._paused:
            if user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
                self._finish()
                self.pick_cancelled.emit()
            return

        try:
            # ── ESC ──
            if user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
                self._finish()
                self.pick_cancelled.emit()
                return

            # ── F3: 3초 일시정지 ──
            if user32.GetAsyncKeyState(VK_F3) & 0x8000:
                if not self._f3_debounce:
                    self._f3_debounce = True
                    self._start_pause()
                    return
            else:
                self._f3_debounce = False

            # ── 좌클릭 ──
            if self._click_ready and (user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000):
                self._finish()
                if self._hovered_root_hwnd:
                    # 최상위 윈도우 핸들과 타이틀을 전달
                    root_title = _get_window_text(self._hovered_root_hwnd) or self._hovered_title
                    self.window_picked.emit(self._hovered_root_hwnd, root_title)
                else:
                    self.pick_cancelled.emit()
                return

            # ── 커서 아래 요소 추적 ──
            self._track_element_under_cursor()

        except Exception:
            pass

    def _start_pause(self):
        """F3 일시정지 시작 - 3초간 UI 숨기고 자유롭게 조작 가능"""
        self._paused = True
        self._pause_countdown = 3

        # UI 숨기기
        self._frame.hide()
        self._title_label.hide()

        # 가이드 라벨에 카운트다운 표시
        self._update_pause_guide()

        # 1초마다 카운트다운
        QTimer.singleShot(1000, self._pause_tick)

    def _pause_tick(self):
        """일시정지 카운트다운"""
        if not self._active or not self._paused:
            return

        self._pause_countdown -= 1

        if self._pause_countdown <= 0:
            # 일시정지 종료 - 선택 모드로 복귀
            self._paused = False
            self._guide.setText(
                "  🖱 검사할 윈도우 / 요소를 클릭하세요  |  F3: 일시정지  |  ESC: 취소  "
            )
            self._guide.place_top_center()
        else:
            # 카운트다운 업데이트
            self._update_pause_guide()
            QTimer.singleShot(1000, self._pause_tick)

    def _update_pause_guide(self):
        """일시정지 중 가이드 라벨 업데이트"""
        self._guide.setText(
            f"  ⏸️ 일시정지 중... {self._pause_countdown}초 후 재개  |  마우스/키보드 자유롭게 조작하세요  "
        )
        self._guide.place_top_center()

    def _is_own_hwnd(self, hwnd: int) -> bool:
        """자체 위젯인지 확인 (직접 / root 비교)"""
        if hwnd in self._own_hwnds:
            return True
        root = user32.GetAncestor(hwnd, GA_ROOT)
        if root and root in self._own_hwnds:
            return True
        return False

    def _track_element_under_cursor(self):
        """커서 아래의 UI 요소를 추적합니다 (윈도우, 버튼, 텍스트 등)."""
        pt = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))

        # 1단계: 커서 위치의 최상위 윈도우 찾기
        top_hwnd = user32.WindowFromPoint(ctypes.wintypes.POINT(pt.x, pt.y))
        if not top_hwnd:
            return

        # 자체 위젯이면 무시
        if self._is_own_hwnd(top_hwnd):
            return

        # 2단계: 가장 깊은 자식 요소까지 탐색
        deepest = _deepest_child_at(top_hwnd, pt.x, pt.y)
        if not deepest:
            deepest = top_hwnd

        # 자체 위젯의 자식이면 무시
        if self._is_own_hwnd(deepest):
            return

        # 같은 요소 → 업데이트 불필요
        if deepest == self._hovered_hwnd:
            return

        self._hovered_hwnd = deepest

        # 최상위 부모 핸들 (검사에 사용)
        root = user32.GetAncestor(deepest, GA_ROOT)
        self._hovered_root_hwnd = root if root else deepest

        # 요소 정보 수집
        elem_text = _get_window_text(deepest)
        elem_class = _get_class_name(deepest)
        root_title = _get_window_text(self._hovered_root_hwnd)

        self._hovered_title = root_title or "(제목 없음)"
        self._hovered_class = elem_class

        # 요소 영역 가져오기
        elem_rect = _get_window_rect_qrect(deepest)
        # 너무 작은 영역 (1x1 등) 은 부모로 대체
        if elem_rect.width() < 4 or elem_rect.height() < 4:
            elem_rect = _get_window_rect_qrect(top_hwnd)

        self._hovered_rect = elem_rect

        # 하이라이트 프레임 업데이트
        self._frame.move_to_rect(self._hovered_rect)
        if not self._frame.isVisible():
            self._frame.show()
        self._frame.raise_()
        self._frame.update()  # 즉시 다시 그리기

        # 타이틀 라벨 구성: [클래스] "텍스트"  │  부모: 윈도우이름
        parts = []
        if elem_class:
            parts.append(f"[{elem_class}]")
        if elem_text:
            display_text = elem_text[:40] + "…" if len(elem_text) > 40 else elem_text
            parts.append(f'"{display_text}"')

        info_line = " ".join(parts) if parts else "(요소)"

        # 최상위 윈도우와 다른 요소라면 부모 정보도 표시
        if deepest != self._hovered_root_hwnd and root_title:
            info_line += f"  │  🪟 {root_title[:30]}"

        self._title_label.setText(f"  {info_line}  ")
        self._title_label.place_near_rect(self._hovered_rect)
        if not self._title_label.isVisible():
            self._title_label.show()
        self._title_label.raise_()

    def _finish(self):
        """피커 종료: 타이머 정지 + 헬퍼 위젯 숨기기"""
        self._active = False
        self._track_timer.stop()
        self._frame.hide()
        self._guide.hide()
        self._title_label.hide()
