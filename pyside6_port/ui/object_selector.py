"""
화면 객체 선택 오버레이 (Phase 7에서 본격 구현)

현재는 스텁으로, Phase 7에서 전체 구현됩니다.
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal


class ObjectSelector(QWidget):
    """
    전체 화면 반투명 오버레이.

    [Phase 7에서 구현 예정]
    - 활성화 시 전체 화면을 반투명 캔버스로 덮음
    - 마우스 이동 시 UI 요소 하이라이트
    - 클릭 시 요소 정보 수집 + 캡처
    """
    object_selected = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

    def activate(self):
        """오버레이 활성화"""
        pass

    def deactivate(self):
        """오버레이 비활성화"""
        pass
