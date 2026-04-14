"""
Visual Feedback Overlay for RPA Execution
==========================================
자동화 코드 실행 중 마우스 클릭, 위치, 키 입력을 화면에 표시하는
투명 클릭스루 오버레이.

독립 프로세스로 실행됩니다:
    python -m core.visual_overlay   (또는 직접 실행)

WorkflowEngine이 실행 시작 전에 subprocess로 띄우고,
실행 완료 후 terminate() 합니다.
"""

import sys
import ctypes
import ctypes.wintypes
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QGuiApplication

# ── Win32 상수 ─────────────────────────────────────────────────────────────────

user32 = ctypes.windll.user32

WH_MOUSE_LL    = 14
WH_KEYBOARD_LL = 13
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
WM_MOUSEMOVE   = 0x0200
WM_KEYDOWN     = 0x0100
WM_SYSKEYDOWN  = 0x0104

GWL_EXSTYLE       = -20
WS_EX_LAYERED     = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE  = 0x08000000

# 가상 데스크톱 메트릭
SM_XVIRTUALSCREEN  = 76
SM_YVIRTUALSCREEN  = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int,
    ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM
)


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt",          ctypes.wintypes.POINT),
        ("mouseData",   ctypes.wintypes.DWORD),
        ("flags",       ctypes.wintypes.DWORD),
        ("time",        ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode",      ctypes.wintypes.DWORD),
        ("scanCode",    ctypes.wintypes.DWORD),
        ("flags",       ctypes.wintypes.DWORD),
        ("time",        ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


# VK 코드 → 표시 이름
VK_NAMES: dict[int, str] = {
    0x08: "Bksp", 0x09: "Tab",    0x0D: "Enter",  0x10: "Shift",
    0x11: "Ctrl", 0x12: "Alt",    0x1B: "Esc",     0x20: "Space",
    0x21: "PgUp", 0x22: "PgDn",   0x23: "End",     0x24: "Home",
    0x25: "←",    0x26: "↑",      0x27: "→",       0x28: "↓",
    0x2E: "Del",  0x2D: "Ins",    0x2C: "PrtSc",
    **{0x30 + i: str(i) for i in range(10)},
    **{0x41 + i: chr(0x41 + i) for i in range(26)},
    **{0x70 + i: f"F{i + 1}" for i in range(24)},
    0xBB: "+", 0xBD: "-", 0xBE: ".", 0xBC: ",",
    0xBA: ";", 0xC0: "`", 0xDB: "[", 0xDD: "]",
}


# ── 리플 ────────────────────────────────────────────────────────────────────────

class Ripple:
    DURATION_MS = 650
    MAX_RADIUS  = 75

    def __init__(self, x: int, y: int, color: QColor):
        self.x       = x
        self.y       = y
        self.color   = color
        self.elapsed = 0

    def advance(self, dt: int) -> None:
        self.elapsed += dt

    @property
    def done(self) -> bool:
        return self.elapsed >= self.DURATION_MS

    @property
    def progress(self) -> float:
        return min(self.elapsed / self.DURATION_MS, 1.0)

    @property
    def radius(self) -> int:
        return int(self.progress * self.MAX_RADIUS)

    @property
    def alpha(self) -> int:
        return max(0, int(255 * (1.0 - self.progress)))


# ── 오버레이 위젯 ───────────────────────────────────────────────────────────────

class OverlayWidget(QWidget):
    """
    전체 가상 데스크톱을 덮는 투명 클릭스루 오버레이.
    마우스 리플, 좌표 표시, 키 입력 표시를 렌더링합니다.
    """

    KEY_CLEAR_MS = 2500   # 마지막 키 입력 후 2.5초 지나면 키 버퍼 초기화
    MAX_RIPPLES  = 12

    def __init__(self):
        super().__init__()

        self.ripples: list[Ripple] = []
        self.mouse_x: int = 0
        self.mouse_y: int = 0
        self.key_buffer: list[str] = []
        self._key_idle_ms: int = 0

        # 가상 데스크톱 원점 (다중 모니터에서 음수일 수 있음)
        self._vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        self._vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw       = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh       = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

        # 창 스타일
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint     |
            Qt.WindowType.WindowStaysOnTopHint    |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        # 전체 가상 데스크톱을 커버하는 지오메트리
        self.setGeometry(self._vx, self._vy, vw, vh)
        self.show()

        # 클릭스루 처리 (WS_EX_LAYERED | WS_EX_TRANSPARENT)
        self._apply_click_through()

        # 60fps 애니메이션 타이머
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _apply_click_through(self) -> None:
        hwnd  = int(self.winId())
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

    # ── 이벤트 수신 (Win32 훅 콜백에서 호출) ───────────────────────────────────

    def on_mouse_move(self, win32_x: int, win32_y: int) -> None:
        self.mouse_x = win32_x
        self.mouse_y = win32_y

    def on_click(self, win32_x: int, win32_y: int, color: QColor) -> None:
        # Win32 가상 좌표 → 위젯 로컬 좌표
        lx = win32_x - self._vx
        ly = win32_y - self._vy
        self.ripples.append(Ripple(lx, ly, color))
        if len(self.ripples) > self.MAX_RIPPLES:
            self.ripples.pop(0)

    def on_key(self, key_name: str) -> None:
        self.key_buffer.append(key_name)
        self._key_idle_ms = 0
        # 최대 12개 유지
        if len(self.key_buffer) > 12:
            self.key_buffer.pop(0)

    # ── 애니메이션 루프 ─────────────────────────────────────────────────────────

    def _tick(self) -> None:
        dt = self._timer.interval()

        # 리플 업데이트
        for r in self.ripples:
            r.advance(dt)
        self.ripples = [r for r in self.ripples if not r.done]

        # 키 버퍼 자동 초기화
        if self.key_buffer:
            self._key_idle_ms += dt
            if self._key_idle_ms >= self.KEY_CLEAR_MS:
                self.key_buffer.clear()
                self._key_idle_ms = 0

        self.update()

    # ── 렌더링 ──────────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._draw_ripples(painter)
        self._draw_hud(painter)

        painter.end()

    def _draw_ripples(self, painter: QPainter) -> None:
        for ripple in self.ripples:
            r   = ripple.radius
            alp = ripple.alpha

            # 외곽 링
            ring_color = QColor(ripple.color)
            ring_color.setAlpha(alp)
            pen = QPen(ring_color, 3)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if r > 0:
                painter.drawEllipse(ripple.x - r, ripple.y - r, r * 2, r * 2)

            # 두 번째 (내부) 링 — 살짝 느리게
            r2 = max(0, r - 20)
            if r2 > 0:
                ring2 = QColor(ripple.color)
                ring2.setAlpha(min(alp + 60, 255))
                painter.setPen(QPen(ring2, 2))
                painter.drawEllipse(ripple.x - r2, ripple.y - r2, r2 * 2, r2 * 2)

            # 초기 150ms: 중심 점
            if ripple.elapsed < 150:
                dot_alpha = int(alp * (1 - ripple.elapsed / 150))
                dot_c = QColor(ripple.color)
                dot_c.setAlpha(dot_alpha)
                painter.setBrush(dot_c)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(ripple.x - 7, ripple.y - 7, 14, 14)

    def _draw_hud(self, painter: QPainter) -> None:
        font = QFont("Consolas", 11)
        font.setBold(True)
        painter.setFont(font)
        fm   = painter.fontMetrics()
        th   = fm.height()
        pad  = 6
        rx   = 5  # 라운드 반경

        # ── 마우스 좌표 ─────────────────────────────────────────────────────────
        pos_text = f"  \U0001f5b1  ({self.mouse_x}, {self.mouse_y})  "
        tw = fm.horizontalAdvance(pos_text)
        px, py = 10, 10

        painter.setBrush(QColor(0, 0, 0, 170))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(px, py, tw + pad, th + pad, rx, rx)

        painter.setPen(QColor(100, 230, 130))
        painter.drawText(px + pad // 2, py + th + 1, pos_text)

        # ── 키 입력 ─────────────────────────────────────────────────────────────
        if self.key_buffer:
            key_text = "  \u2328  " + "  ".join(self.key_buffer[-10:]) + "  "
            kw = fm.horizontalAdvance(key_text)
            kx = 10
            ky = py + th + pad + 6

            painter.setBrush(QColor(0, 0, 0, 170))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(kx, ky, kw + pad, th + pad, rx, rx)

            painter.setPen(QColor(255, 210, 70))
            painter.drawText(kx + pad // 2, ky + th + 1, key_text)


# ── 전역 참조 (GC 방지 & 훅 콜백 접근) ──────────────────────────────────────────

_overlay: OverlayWidget | None = None
_mouse_hook    = None
_keyboard_hook = None
_mouse_cb:    HOOKPROC | None = None  # type: ignore[type-arg]
_keyboard_cb: HOOKPROC | None = None  # type: ignore[type-arg]

# 클릭 색상
COLOR_LEFT   = QColor(80,  160, 255)   # 파란색 — 좌클릭
COLOR_RIGHT  = QColor(255, 90,  90)    # 빨간색 — 우클릭
COLOR_MIDDLE = QColor(255, 200, 50)    # 노란색 — 중간 클릭


def _mouse_proc(nCode: int, wParam: int, lParam: int) -> int:
    if nCode >= 0 and _overlay is not None:
        ms = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        x, y = ms.pt.x, ms.pt.y
        _overlay.on_mouse_move(x, y)
        if   wParam == WM_LBUTTONDOWN:
            _overlay.on_click(x, y, COLOR_LEFT)
        elif wParam == WM_RBUTTONDOWN:
            _overlay.on_click(x, y, COLOR_RIGHT)
        elif wParam == WM_MBUTTONDOWN:
            _overlay.on_click(x, y, COLOR_MIDDLE)
    return user32.CallNextHookEx(None, nCode, wParam, lParam)


def _keyboard_proc(nCode: int, wParam: int, lParam: int) -> int:
    if nCode >= 0 and _overlay is not None and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
        kb   = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        name = VK_NAMES.get(kb.vkCode, f"[{kb.vkCode:02X}]")
        _overlay.on_key(name)
    return user32.CallNextHookEx(None, nCode, wParam, lParam)


def _install_hooks() -> None:
    global _mouse_hook, _keyboard_hook, _mouse_cb, _keyboard_cb
    _mouse_cb    = HOOKPROC(_mouse_proc)
    _keyboard_cb = HOOKPROC(_keyboard_proc)
    _mouse_hook    = user32.SetWindowsHookExW(WH_MOUSE_LL,    _mouse_cb,    None, 0)
    _keyboard_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _keyboard_cb, None, 0)


def _remove_hooks() -> None:
    if _mouse_hook:
        user32.UnhookWindowsHookEx(_mouse_hook)
    if _keyboard_hook:
        user32.UnhookWindowsHookEx(_keyboard_hook)


def main() -> None:
    global _overlay
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    _overlay = OverlayWidget()
    _install_hooks()

    code = app.exec()
    _remove_hooks()
    sys.exit(code)


if __name__ == "__main__":
    main()
