"""
Dual Dexhand Widget Module
双灵巧手部件模块

Widget for controlling both left and right dexterous hands.
用于控制左右灵巧手的部件。
"""

from gui.qt_imports import (
    QWidget, QGroupBox, QLabel, QPushButton, QTabWidget,
    QVBoxLayout, QHBoxLayout,
)
from typing import Optional

from .dexhand_controller import DexhandController
from .dexhand_widget import DexhandWidget


class DualDexhandWidget(QWidget):
    """
    Widget for controlling both left and right hands.
    用于控制左右手的部件。
    """

    def __init__(self, parent=None,
                 left_controller: Optional[DexhandController] = None,
                 right_controller: Optional[DexhandController] = None,
                 language: str = "en", **kwargs):
        """
        Initialize dual dexhand widget.
        初始化双灵巧手部件。

        Args:
            parent: Parent widget
            left_controller: Left hand DexhandController
            right_controller: Right hand DexhandController
            language: Display language
        """
        super().__init__(parent)

        self._language = language
        self._left_controller = left_controller
        self._right_controller = right_controller

        self._create_widgets()

    def _create_widgets(self):
        """Create child widgets / 创建子部件"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Notebook for left/right hand tabs
        self.notebook = QTabWidget()
        main_layout.addWidget(self.notebook)

        # Left hand tab
        self.left_widget = DexhandWidget(
            controller=self._left_controller,
            hand_side="left",
            language=self._language
        )
        self.notebook.addTab(self.left_widget,
                             "Left Hand" if self._language == "en" else "左手")

        # Right hand tab
        self.right_widget = DexhandWidget(
            controller=self._right_controller,
            hand_side="right",
            language=self._language
        )
        self.notebook.addTab(self.right_widget,
                             "Right Hand" if self._language == "en" else "右手")

        # Both hands control panel at bottom
        both_group = QGroupBox("Both Hands" if self._language == "en" else "双手控制")
        main_layout.addWidget(both_group)

        btn_layout = QHBoxLayout(both_group)

        # Sync buttons
        open_text = "Open Both" if self._language == "en" else "双手张开"
        open_btn = QPushButton(open_text)
        open_btn.clicked.connect(self._open_both)
        btn_layout.addWidget(open_btn)

        close_text = "Close Both" if self._language == "en" else "双手握拳"
        close_btn = QPushButton(close_text)
        close_btn.clicked.connect(self._close_both)
        btn_layout.addWidget(close_btn)

        sync_text = "Sync Positions" if self._language == "en" else "同步位置"
        sync_btn = QPushButton(sync_text)
        sync_btn.clicked.connect(self._sync_positions)
        btn_layout.addWidget(sync_btn)

        btn_layout.addStretch()

    def _open_both(self):
        """Open both hands / 双手张开"""
        if self._left_controller and self._left_controller.is_ready():
            self._left_controller.open_hand()
        if self._right_controller and self._right_controller.is_ready():
            self._right_controller.open_hand()

        # Update UI
        self.left_widget._set_all_positions(255)
        self.right_widget._set_all_positions(255)

    def _close_both(self):
        """Close both hands / 双手握拳"""
        if self._left_controller and self._left_controller.is_ready():
            self._left_controller.close_hand()
        if self._right_controller and self._right_controller.is_ready():
            self._right_controller.close_hand()

        # Update UI
        self.left_widget._set_all_positions(0)
        self.right_widget._set_all_positions(0)

    def _sync_positions(self):
        """Sync right hand to left hand positions / 将右手同步到左手位置"""
        left_positions = self.left_widget.get_positions()
        self.right_widget.set_positions(left_positions)

        if self._right_controller and self._right_controller.is_ready():
            self._right_controller.set_positions(left_positions)

    def update_language(self, language: str = None):
        """Update display language / 更新显示语言"""
        if language is None:
            from config.i18n import get_i18n
            language = get_i18n().language.value
        self._language = language
        self.left_widget.update_language(language)
        self.right_widget.update_language(language)

        # Update tab labels
        self.notebook.setTabText(0, "Left Hand" if language == "en" else "左手")
        self.notebook.setTabText(1, "Right Hand" if language == "en" else "右手")

    def shutdown(self):
        """Clean shutdown / 清理关闭"""
        self.left_widget.shutdown()
        self.right_widget.shutdown()
