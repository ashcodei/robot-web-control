"""
Scrollable Area Widget
可滚动区域部件

Configured QScrollArea replacing the 125-line Canvas hack.
配置好的 QScrollArea，替代 125 行的 Canvas 方案。
"""

from gui.qt_imports import QScrollArea, QWidget, QVBoxLayout, Qt


class ScrollableArea(QScrollArea):
    """
    A scrollable area wrapping an inner widget.

    Usage:
        area = ScrollableArea(parent)
        area.inner_layout.addWidget(some_widget)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._inner = QWidget()
        self.inner_layout = QVBoxLayout(self._inner)
        self.inner_layout.setContentsMargins(0, 0, 0, 0)
        self.setWidget(self._inner)
