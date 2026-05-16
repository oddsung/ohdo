# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recorder overlay — 작업 녹화 중에 화면 우상단에 떠 있는 작은 상태 막대.

[ADR 0004 + architecture/25 §"PR-15"] 녹화 중 사용자가 ohdo 외부에서
평상시처럼 작업할 수 있도록 main window 를 minimize 하고, 대신 이 floating
overlay 만 표시한다.

핵심:
- 막대 전체는 ``WA_TransparentForMouseEvents`` 로 click-through (사용자
  클릭이 overlay 를 통과해서 밑 창에 전달). 단 [중지] 버튼 영역만 mouse
  통과를 끄고 받음.
- ``WindowStaysOnTopHint | FramelessWindowHint | Tool`` + ``WA_ShowWithoutActivating``.
- 0.5초마다 경과시간 / event_count 갱신 (AppService 가 emit 하는 이벤트 + 자체
  QTimer).
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from core.i18n import tr

__all__ = ["RecorderOverlay"]


# 디자인 토큰 (main_window_v2.COLORS 와 일관 — circular import 회피 위해 직접 정의)
_BG = "#1e1e2e"
_BORDER = "#f38ba8"
_REC_DOT = "#f38ba8"
_TEXT = "#cdd6f4"
_TEXT_MUTED = "#6c7086"


class RecorderOverlay(QWidget):
    """녹화 중 floating click-through 상태 막대.

    Args:
        get_event_count: 현재 캡처된 raw event 개수를 반환하는 callable.
            AppService.recording_event_count 를 그대로 넘기면 됨.
        on_stop: 사용자가 [중지] 버튼 클릭 시 호출되는 callback (인자 없음).
    """

    def __init__(
        self,
        get_event_count: Callable[[], int],
        on_stop: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._get_event_count = get_event_count
        self._on_stop = on_stop
        self._started_at: Optional[datetime] = None

        # 창 속성 — frameless + top + tool + show-without-activating
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        # 전체 위젯은 click-through. 자식 [중지] 버튼만 명시적으로 false 로 재설정.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._refresh_labels)

        self.resize(280, 36)

    # ── UI ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setStyleSheet(
            f"""
            QWidget#recorderOverlayRoot {{
                background-color: {_BG};
                border: 2px solid {_BORDER};
                border-radius: 6px;
            }}
            QLabel {{
                color: {_TEXT};
                background: transparent;
                border: none;
                font-family: 'Malgun Gothic', 'Inter', sans-serif;
                font-size: 12px;
            }}
            QLabel#recDot {{
                color: {_REC_DOT};
                font-weight: bold;
            }}
            QLabel#eventCount {{
                color: {_TEXT_MUTED};
            }}
            QPushButton#stopBtn {{
                background-color: {_REC_DOT};
                color: {_BG};
                border: none;
                border-radius: 4px;
                padding: 2px 10px;
                font-weight: bold;
            }}
            QPushButton#stopBtn:hover {{
                background-color: #e0788f;
            }}
            """
        )
        self.setObjectName("recorderOverlayRoot")

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 6, 4)
        row.setSpacing(8)

        self._rec_dot = QLabel(tr("ui_v2.recording.overlay.label_recording"))
        self._rec_dot.setObjectName("recDot")
        row.addWidget(self._rec_dot)

        self._elapsed_label = QLabel("00:00")
        row.addWidget(self._elapsed_label)

        self._event_count_label = QLabel(tr("ui_v2.recording.overlay.label_events", count=0))
        self._event_count_label.setObjectName("eventCount")
        row.addWidget(self._event_count_label)

        row.addStretch()

        self._stop_btn = QPushButton(tr("ui_v2.recording.overlay.btn_stop"))
        self._stop_btn.setObjectName("stopBtn")
        self._stop_btn.setToolTip(tr("ui_v2.recording.overlay.btn_stop_tooltip"))
        # 부모는 click-through 지만 자식은 명시적으로 mouse 받기.
        self._stop_btn.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        row.addWidget(self._stop_btn)

    # ── Lifecycle ───────────────────────────────────────────

    def start(self) -> None:
        """녹화 시작 시 호출 — 표시 + timer 활성."""
        self._started_at = datetime.now()
        self._refresh_labels()
        self._position_top_right()
        self.show()
        self._timer.start()

    def stop_and_hide(self) -> None:
        """녹화 중지 시 호출 — timer 정지 + 숨김."""
        self._timer.stop()
        self.hide()

    def _on_stop_clicked(self) -> None:
        try:
            self._on_stop()
        except Exception:  # noqa: BLE001
            # callback 예외가 overlay 자체를 마비시키지 않도록 격리.
            import logging

            logging.getLogger(__name__).exception("RecorderOverlay stop callback 예외")

    # ── 갱신 ─────────────────────────────────────────────────

    def _refresh_labels(self) -> None:
        if self._started_at is not None:
            elapsed = (datetime.now() - self._started_at).total_seconds()
            mm, ss = divmod(int(elapsed), 60)
            self._elapsed_label.setText(f"{mm:02d}:{ss:02d}")
        try:
            count = int(self._get_event_count())
        except Exception:  # noqa: BLE001
            count = 0
        self._event_count_label.setText(tr("ui_v2.recording.overlay.label_events", count=count))

    def _position_top_right(self) -> None:
        """주 화면 우상단으로 위치 — 작업 표시줄과 안 겹치게 약간 여백."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        margin = 20
        top_left = QPoint(geo.right() - self.width() - margin, geo.top() + margin)
        self.move(top_left)
