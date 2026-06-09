"""
Scrollable Frame Widget (PySide6)
可滚动框架部件

QScrollArea replacement for the Canvas+mousewheel hack.
"""

from gui.qt_imports import QScrollArea, QWidget, QVBoxLayout, Qt


class ScrollableFrame(QScrollArea):
    """
    A scrollable frame widget providing vertical scrolling.
    可滚动框架部件，提供垂直滚动功能。

    Usage:
        scrollable = ScrollableFrame(parent)
        layout.addWidget(scrollable)
        scrollable.inner_layout.addWidget(content)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFrameShape(QScrollArea.Shape.NoFrame)

        # Inner widget (replaces scrollable_frame attribute)
        self.scrollable_frame = QWidget()
        self.inner_layout = QVBoxLayout(self.scrollable_frame)
        self.inner_layout.setContentsMargins(0, 0, 0, 0)
        self.setWidget(self.scrollable_frame)

    def scroll_to_top(self):
        """Scroll to top of content."""
        self.verticalScrollBar().setValue(0)

    def scroll_to_bottom(self):
        """Scroll to bottom of content."""
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
