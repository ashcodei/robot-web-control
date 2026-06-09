"""
Hardware Status Card Widget (PySide6)
硬件状态卡片部件

A card widget for displaying hardware status and quick controls.
用于显示硬件状态和快速控制的卡片部件。
"""

import threading
from gui.qt_imports import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QPainter, QColor, QBrush, QPen, Qt, QSize,
)
from config.i18n import t
from app_core.logger import get_logger
from hardware.base_hardware import HardwareState, BaseHardwareController
from gui.theme import STATE_COLORS

logger = get_logger(__name__)


class StatusIndicator(QWidget):
    """Colored circle indicator widget."""

    def __init__(self, parent=None, size=14):
        super().__init__(parent)
        self._color = QColor(STATE_COLORS.get('disconnected', '#6c757d'))
        self._size = size
        self.setFixedSize(size + 2, size + 2)

    def set_color(self, hex_color: str):
        self._color = QColor(hex_color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(1, 1, self._size, self._size)
        painter.end()


class HardwareStatusCard(QFrame):
    """
    Hardware status card widget.
    硬件状态卡片部件。
    """

    def __init__(self, parent, hardware_name: str,
                 display_name_key: str,
                 controller: BaseHardwareController = None,
                 show_controls: bool = True):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setLineWidth(1)

        self.hardware_name = hardware_name
        self.display_name_key = display_name_key
        self.controller = controller
        self.show_controls = show_controls
        self._state = HardwareState.DISCONNECTED

        self._build_ui()

        if controller:
            controller.add_state_callback(self._on_state_changed)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header row: indicator + name + status
        header = QHBoxLayout()
        self.indicator = StatusIndicator(self)
        header.addWidget(self.indicator)

        self.name_label = QLabel(t(self.display_name_key))
        self.name_label.setStyleSheet("font-size: 11pt; font-weight: bold;")
        header.addWidget(self.name_label)
        header.addStretch()

        self.status_label = QLabel(t(f"state.{self._state.value}"))
        self.status_label.setStyleSheet("font-size: 10pt;")
        header.addWidget(self.status_label)
        layout.addLayout(header)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Connection info
        self.connection_label = QLabel("")
        self.connection_label.setStyleSheet("font-size: 9pt;")
        layout.addWidget(self.connection_label)

        # Control buttons
        if self.show_controls:
            btn_layout = QHBoxLayout()

            self.connect_btn = QPushButton(t("common.connect"))
            self.connect_btn.setFixedWidth(80)
            self.connect_btn.clicked.connect(self._on_connect)
            btn_layout.addWidget(self.connect_btn)

            self.start_btn = QPushButton(t("common.start"))
            self.start_btn.setFixedWidth(80)
            self.start_btn.clicked.connect(self._on_start)
            btn_layout.addWidget(self.start_btn)

            self.stop_btn = QPushButton(t("common.stop"))
            self.stop_btn.setFixedWidth(80)
            self.stop_btn.clicked.connect(self._on_stop)
            btn_layout.addWidget(self.stop_btn)

            btn_layout.addStretch()
            layout.addLayout(btn_layout)
            self._update_button_states()

    def _get_state_color(self, state: HardwareState) -> str:
        return STATE_COLORS.get(state.value, '#6c757d')

    def _update_button_states(self):
        if not self.show_controls:
            return

        s = self._state
        if s == HardwareState.DISCONNECTED:
            self.connect_btn.setText(t("common.connect"))
            self.connect_btn.setEnabled(True)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
        elif s == HardwareState.CONNECTING:
            self.connect_btn.setEnabled(False)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
        elif s == HardwareState.CONNECTED:
            self.connect_btn.setText(t("common.disconnect"))
            self.connect_btn.setEnabled(True)
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
        elif s == HardwareState.RUNNING:
            self.connect_btn.setEnabled(False)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
        elif s == HardwareState.PAUSED:
            self.connect_btn.setEnabled(False)
            self.start_btn.setText(t("common.resume"))
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)
        elif s == HardwareState.ERROR:
            self.connect_btn.setText(t("common.connect"))
            self.connect_btn.setEnabled(True)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
        elif s == HardwareState.EMERGENCY_STOP:
            self.connect_btn.setEnabled(False)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)

    def _on_state_changed(self, old_state, new_state):
        from gui.signals import get_thread_bridge
        bridge = get_thread_bridge()
        bridge.gui_callback.emit(lambda: self.update_state(new_state))

    def _on_connect(self):
        if not self.controller:
            return
        if self._state in [HardwareState.DISCONNECTED, HardwareState.ERROR]:
            def do_connect():
                if hasattr(self.controller, 'reconnect'):
                    self.controller.reconnect()
                else:
                    self.controller.connect()
            threading.Thread(target=do_connect, daemon=True,
                           name=f"Connect-{self.hardware_name}").start()
        else:
            threading.Thread(target=self.controller.disconnect, daemon=True,
                           name=f"Disconnect-{self.hardware_name}").start()

    def _on_start(self):
        if not self.controller:
            return
        if self._state == HardwareState.PAUSED:
            threading.Thread(target=self.controller.resume, daemon=True,
                           name=f"Resume-{self.hardware_name}").start()
        else:
            threading.Thread(target=self.controller.start, daemon=True,
                           name=f"Start-{self.hardware_name}").start()

    def _on_stop(self):
        if not self.controller:
            return
        threading.Thread(target=self.controller.stop, daemon=True,
                       name=f"Stop-{self.hardware_name}").start()

    def update_state(self, state: HardwareState):
        self._state = state
        self.indicator.set_color(self._get_state_color(state))
        self.status_label.setText(t(f"state.{state.value}"))
        self._update_button_states()

    def update_info(self, info: dict):
        info_text = "\n".join(f"{k}: {v}" for k, v in info.items())
        self.connection_label.setText(info_text)

    def set_controller(self, controller: BaseHardwareController):
        self.controller = controller
        controller.add_state_callback(self._on_state_changed)
        self.update_state(controller.state)

    def update_language(self):
        self.name_label.setText(t(self.display_name_key))
        self.status_label.setText(t(f"state.{self._state.value}"))
        if self.show_controls:
            if self._state in [HardwareState.DISCONNECTED, HardwareState.ERROR]:
                self.connect_btn.setText(t("common.connect"))
            else:
                self.connect_btn.setText(t("common.disconnect"))
            if self._state == HardwareState.PAUSED:
                self.start_btn.setText(t("common.resume"))
            else:
                self.start_btn.setText(t("common.start"))
            self.stop_btn.setText(t("common.stop"))
