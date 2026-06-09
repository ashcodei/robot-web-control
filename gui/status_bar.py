"""
Status Bar Module (PySide6)
状态栏模块

Bottom status bar showing hardware connection status.
底部状态栏，显示硬件连接状态。
"""

import time
from gui.qt_imports import (
    QWidget, QHBoxLayout, QLabel, QFrame, QTimer, Qt,
)
from config.i18n import t
from app_core.state_manager import get_state_manager
from app_core.emergency_controller import get_emergency_controller
from hardware.base_hardware import HardwareState
from gui.theme import STATE_COLORS


class StatusBar(QFrame):
    """
    Bottom status bar.
    底部状态栏。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("background-color: #e8e8e8; border-top: 1px solid #cccccc;")
        self.setFixedHeight(30)

        self.state_manager = get_state_manager()
        self.emergency_controller = get_emergency_controller()

        self.status_labels = {}
        self._message_clear_timer = None

        self._build_ui()
        self._start_time_update()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)

        # Hardware status labels
        hardware_list = ['gantry_lebai', 'dual_arm', 'wok', 'teleop']

        for i, hw_name in enumerate(hardware_list):
            label = QLabel(self._format_status(hw_name, HardwareState.DISCONNECTED))
            label.setStyleSheet("font-size: 9pt;")
            layout.addWidget(label)
            self.status_labels[hw_name] = label

            if i < len(hardware_list) - 1:
                sep = QLabel("|")
                sep.setStyleSheet("font-size: 9pt; color: #999999;")
                layout.addWidget(sep)

        # Message label
        self.message_label = QLabel("")
        self.message_label.setStyleSheet("font-size: 9pt;")
        layout.addWidget(self.message_label)

        layout.addStretch()

        # Time label
        self.time_label = QLabel("")
        self.time_label.setStyleSheet("font-size: 9pt;")
        layout.addWidget(self.time_label)

    def _format_status(self, hw_name: str, state: HardwareState) -> str:
        display_name = t(f"hardware.{hw_name}")
        state_text = t(f"state.{state.value}")
        return f"{display_name}: {state_text}"

    def _get_state_color(self, state: HardwareState) -> str:
        return STATE_COLORS.get(state.value, '#6c757d')

    def _start_time_update(self):
        self._time_timer = QTimer(self)
        self._time_timer.timeout.connect(self._update_time)
        self._time_timer.start(1000)
        self._update_time()

    def _update_time(self):
        current_time = time.strftime("%H:%M:%S")
        self.time_label.setText(current_time)

    def update_status(self):
        for hw_name, label in self.status_labels.items():
            info = self.state_manager.get_hardware_info(hw_name)
            if info:
                state = info.controller.state
            else:
                state = HardwareState.DISCONNECTED

            label.setText(self._format_status(hw_name, state))
            color = self._get_state_color(state)
            label.setStyleSheet(f"font-size: 9pt; color: {color};")

    def set_message(self, text: str, level: str = "info", duration_ms: int = 5000):
        color_map = {
            'info': '#212529',
            'warning': '#dc3545',
            'error': '#dc3545',
        }
        color = color_map.get(level, '#212529')
        self.message_label.setText(text)
        self.message_label.setStyleSheet(f"font-size: 9pt; color: {color};")

        if self._message_clear_timer:
            self._message_clear_timer.stop()

        if duration_ms > 0:
            self._message_clear_timer = QTimer(self)
            self._message_clear_timer.setSingleShot(True)
            self._message_clear_timer.timeout.connect(
                lambda: self.message_label.setText("")
            )
            self._message_clear_timer.start(duration_ms)

    def update_language(self):
        self.update_status()

    def _cleanup(self):
        if hasattr(self, '_time_timer'):
            self._time_timer.stop()
