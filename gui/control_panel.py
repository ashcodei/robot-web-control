"""
Control Panel Module (PySide6)
控制面板模块

Main control panel with hardware start/stop and emergency stop buttons.
主控制面板，包含硬件启动/停止和紧急停止按钮。
"""

import threading
from gui.qt_imports import (
    QWidget, QFrame, QGroupBox, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, Qt,
    QPainter, QColor, QBrush, QPen,
)
from config.i18n import t
from app_core.event_bus import get_event_bus, EventType
from app_core.state_manager import get_state_manager, SystemState
from app_core.emergency_controller import get_emergency_controller
from app_core.logger import get_logger
from hardware.base_hardware import HardwareState
from gui.theme import STATE_COLORS
from gui.signals import EventBusBridge, get_thread_bridge
from gui.widgets.hardware_status_card import StatusIndicator

logger = get_logger(__name__)

HARDWARE_NAME_TO_CATEGORY = {
    'gantry': 'gantry_lebai',
    'lebai': 'gantry_lebai',
    'dual_arm': 'dual_arm',
    'linker_hand': 'dual_arm',
    'wok': 'wok',
    'teleop': 'teleop',
    'dexhand_left': 'dexhand',
    'dexhand_right': 'dexhand',
}

BUTTON_STATE_RULES = {
    'connect_all': {SystemState.READY, SystemState.ERROR, SystemState.INITIALIZING},
    'start_all': {SystemState.READY},
    'pause_all': {SystemState.RUNNING},
    'resume_all': {SystemState.PAUSED},
    'stop_all': {SystemState.RUNNING, SystemState.PAUSED},
    'emergency': {SystemState.READY, SystemState.RUNNING, SystemState.PAUSED},
}


class HardwareStatusIndicator(QWidget):
    """Hardware status indicator with colored dot + labels."""

    def __init__(self, parent, hardware_name: str, display_name_key: str):
        super().__init__(parent)
        self.hardware_name = hardware_name
        self.display_name_key = display_name_key
        self.state = HardwareState.DISCONNECTED

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        self.indicator = StatusIndicator(self, size=12)
        layout.addWidget(self.indicator)

        self.label = QLabel(t(self.display_name_key))
        layout.addWidget(self.label)

        self.state_label = QLabel(t(f"state.{self.state.value}"))
        self.state_label.setFixedWidth(90)
        layout.addWidget(self.state_label)

    def update_state(self, state: HardwareState):
        self.state = state
        color = STATE_COLORS.get(state.value, '#6c757d')
        self.indicator.set_color(color)
        self.state_label.setText(t(f"state.{state.value}"))

    def update_language(self):
        self.label.setText(t(self.display_name_key))
        self.state_label.setText(t(f"state.{self.state.value}"))


class EmergencyStopButton(QPushButton):
    """Emergency stop button."""

    def __init__(self, parent=None, command=None):
        super().__init__(t("control.emergency_stop"), parent)
        self.setObjectName("emergencyButton")
        self.emergency_controller = get_emergency_controller()
        self._is_active = False

        self.clicked.connect(command or self._on_click)

    def _on_click(self):
        if self._is_active:
            self._release_emergency()
        else:
            self._trigger_emergency()

    def _trigger_emergency(self):
        logger.warning("Emergency stop triggered by user")
        self._set_active(True)
        threading.Thread(
            target=self._do_emergency_stop,
            daemon=True, name="EmergencyStop"
        ).start()

    def _do_emergency_stop(self):
        try:
            self.emergency_controller.emergency_stop_all()
        except Exception as e:
            logger.error(f"Emergency stop execution error: {e}")

    def _release_emergency(self):
        self.emergency_controller.release_emergency_stop()
        self._set_active(False)

    def _set_active(self, active: bool):
        self._is_active = active
        if active:
            self.setText(t("control.emergency_stop_release"))
            self.setProperty("active", True)
        else:
            self.setText(t("control.emergency_stop"))
            self.setProperty("active", False)
        # Force style refresh
        self.style().unpolish(self)
        self.style().polish(self)

    def update_language(self):
        if self._is_active:
            self.setText(t("control.emergency_stop_release"))
        else:
            self.setText(t("control.emergency_stop"))


class ControlPanel(QWidget):
    """
    Main control panel.
    主控制面板。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state_manager = get_state_manager()
        self.emergency_controller = get_emergency_controller()
        self.event_bus = get_event_bus()
        self._bridge = get_thread_bridge()
        self._event_bridge = EventBusBridge(self)

        self.status_indicators = {}
        self.hardware_buttons = {}

        self._build_ui()
        self._setup_event_handlers()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Left: System status
        self.status_frame = QGroupBox(t("control.system_status"))
        status_layout = QVBoxLayout(self.status_frame)

        hardware_list = [
            ('gantry_lebai', 'hardware.gantry_lebai'),
            ('dual_arm', 'hardware.dual_arm'),
            ('wok', 'hardware.wok'),
            ('teleop', 'hardware.teleop'),
        ]

        for hw_name, display_key in hardware_list:
            indicator = HardwareStatusIndicator(self.status_frame, hw_name, display_key)
            status_layout.addWidget(indicator)
            self.status_indicators[hw_name] = indicator

        main_layout.addWidget(self.status_frame)

        # Middle: Quick actions
        self.actions_frame = QGroupBox(t("control.quick_actions"))
        actions_layout = QVBoxLayout(self.actions_frame)

        # Top row - global
        top_row = QHBoxLayout()

        self.connect_all_btn = QPushButton(t("control.connect_all"))
        self.connect_all_btn.clicked.connect(self._on_connect_all)
        top_row.addWidget(self.connect_all_btn)

        self.start_all_btn = QPushButton(t("control.start_all"))
        self.start_all_btn.clicked.connect(self._on_start_all)
        top_row.addWidget(self.start_all_btn)

        self.pause_all_btn = QPushButton(t("control.pause_all"))
        self.pause_all_btn.clicked.connect(self._on_pause_all)
        top_row.addWidget(self.pause_all_btn)

        self.resume_all_btn = QPushButton(t("control.resume_all"))
        self.resume_all_btn.clicked.connect(self._on_resume_all)
        top_row.addWidget(self.resume_all_btn)

        self.stop_all_btn = QPushButton(t("control.stop_all"))
        self.stop_all_btn.clicked.connect(self._on_stop_all)
        top_row.addWidget(self.stop_all_btn)

        actions_layout.addLayout(top_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        actions_layout.addWidget(sep)

        # Bottom row - individual
        bottom_row = QHBoxLayout()

        hardware_controls = [
            ('gantry_lebai', 'hardware.gantry_lebai'),
            ('dual_arm', 'hardware.dual_arm'),
            ('wok', 'hardware.wok'),
        ]

        self.hardware_control_labels = {}
        self.hardware_start_btns = {}
        self.hardware_stop_btns = {}
        self._hardware_display_keys = {}

        for hw_name, display_key in hardware_controls:
            self._hardware_display_keys[hw_name] = display_key
            hw_layout = QHBoxLayout()

            label = QLabel(f"{t(display_key)}:")
            hw_layout.addWidget(label)
            self.hardware_control_labels[hw_name] = label

            start_btn = QPushButton(t("common.start"))
            start_btn.setFixedWidth(60)
            start_btn.clicked.connect(lambda checked, n=hw_name: self._on_hardware_start(n))
            hw_layout.addWidget(start_btn)
            self.hardware_start_btns[hw_name] = start_btn

            stop_btn = QPushButton(t("common.stop"))
            stop_btn.setFixedWidth(60)
            stop_btn.clicked.connect(lambda checked, n=hw_name: self._on_hardware_stop(n))
            hw_layout.addWidget(stop_btn)
            self.hardware_stop_btns[hw_name] = stop_btn

            bottom_row.addLayout(hw_layout)

        actions_layout.addLayout(bottom_row)
        main_layout.addWidget(self.actions_frame, stretch=1)

        # Right: Emergency stop
        emergency_frame = QWidget()
        emergency_layout = QVBoxLayout(emergency_frame)
        self.emergency_btn = EmergencyStopButton()
        emergency_layout.addWidget(self.emergency_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(emergency_frame)

    def _setup_event_handlers(self):
        self._event_bridge.subscribe(EventType.HARDWARE_STATE_CHANGED, self._on_hardware_state_changed)
        self._event_bridge.subscribe(EventType.EMERGENCY_STOP, self._on_emergency_event)
        self._event_bridge.subscribe(EventType.EMERGENCY_STOP_RELEASED, self._on_emergency_released)
        self._event_bridge.subscribe(EventType.STATUS_UPDATE, self._on_system_state_changed)

        self.state_manager.add_state_callback(self._on_state_manager_callback)
        self._update_button_states()

    def _on_system_state_changed(self, event):
        self._update_button_states()

    def _on_state_manager_callback(self, old_state, new_state):
        self._bridge.gui_callback.emit(self._update_button_states)

    def _update_button_states(self):
        current_state = self.state_manager.system_state

        buttons = {
            'connect_all': self.connect_all_btn,
            'start_all': self.start_all_btn,
            'pause_all': self.pause_all_btn,
            'resume_all': self.resume_all_btn,
            'stop_all': self.stop_all_btn,
        }

        for btn_name, btn_widget in buttons.items():
            enabled_states = BUTTON_STATE_RULES.get(btn_name, set())
            btn_widget.setEnabled(current_state in enabled_states)

        for hw_name in self.hardware_start_btns:
            controller = self.state_manager.get_hardware(hw_name)
            if controller:
                hw_state = controller.state
                self.hardware_start_btns[hw_name].setEnabled(
                    hw_state in [HardwareState.DISCONNECTED, HardwareState.CONNECTED])
                self.hardware_stop_btns[hw_name].setEnabled(
                    hw_state in [HardwareState.RUNNING, HardwareState.PAUSED])

        if current_state == SystemState.SHUTDOWN:
            self.emergency_btn.setEnabled(False)
        else:
            self.emergency_btn.setEnabled(True)

    def _on_hardware_state_changed(self, event):
        hw_name = event.data.get('hardware_name')
        new_state_str = event.data.get('new_state')
        category = HARDWARE_NAME_TO_CATEGORY.get(hw_name, hw_name)
        if category in self.status_indicators:
            try:
                new_state = HardwareState(new_state_str)
                self.status_indicators[category].update_state(new_state)
            except ValueError:
                pass
        self._update_button_states()

    def _on_emergency_event(self, event):
        self.emergency_btn._set_active(True)

    def _on_emergency_released(self, event):
        self.emergency_btn._set_active(False)

    def _on_connect_all(self):
        logger.info("Connect all hardware requested")
        def do_connect():
            for info in self.state_manager.get_enabled_hardware():
                try:
                    info.controller.connect()
                except Exception as e:
                    logger.error(f"Failed to connect {info.name}: {e}")
        threading.Thread(target=do_connect, daemon=True, name="ConnectAll").start()

    def _on_start_all(self):
        logger.info("Start all hardware requested")
        def do_start():
            for info in self.state_manager.get_enabled_hardware():
                try:
                    if info.controller.is_ready():
                        info.controller.start()
                except Exception as e:
                    logger.error(f"Failed to start {info.name}: {e}")
        threading.Thread(target=do_start, daemon=True, name="StartAll").start()

    def _on_pause_all(self):
        logger.info("Pause all hardware requested")
        def do_pause():
            for info in self.state_manager.get_enabled_hardware():
                try:
                    info.controller.pause()
                except Exception as e:
                    logger.error(f"Failed to pause {info.name}: {e}")
        threading.Thread(target=do_pause, daemon=True, name="PauseAll").start()

    def _on_resume_all(self):
        logger.info("Resume all hardware requested")
        def do_resume():
            for info in self.state_manager.get_enabled_hardware():
                try:
                    info.controller.resume()
                except Exception as e:
                    logger.error(f"Failed to resume {info.name}: {e}")
        threading.Thread(target=do_resume, daemon=True, name="ResumeAll").start()

    def _on_stop_all(self):
        logger.info("Stop all hardware requested")
        def do_stop():
            for info in self.state_manager.get_enabled_hardware():
                try:
                    info.controller.stop()
                except Exception as e:
                    logger.error(f"Failed to stop {info.name}: {e}")
        threading.Thread(target=do_stop, daemon=True, name="StopAll").start()

    def _on_hardware_start(self, hw_name):
        logger.info(f"Start {hw_name} requested")
        controller = self.state_manager.get_hardware(hw_name)
        if controller:
            def do_start():
                try:
                    if controller.state == HardwareState.DISCONNECTED:
                        controller.connect()
                    elif controller.is_ready():
                        controller.start()
                except Exception as e:
                    logger.error(f"Failed to start {hw_name}: {e}")
            threading.Thread(target=do_start, daemon=True, name=f"Start-{hw_name}").start()

    def _on_hardware_stop(self, hw_name):
        logger.info(f"Stop {hw_name} requested")
        controller = self.state_manager.get_hardware(hw_name)
        if controller:
            threading.Thread(target=controller.stop, daemon=True, name=f"Stop-{hw_name}").start()

    def update_language(self):
        self.status_frame.setTitle(t("control.system_status"))
        self.actions_frame.setTitle(t("control.quick_actions"))

        self.connect_all_btn.setText(t("control.connect_all"))
        self.start_all_btn.setText(t("control.start_all"))
        self.pause_all_btn.setText(t("control.pause_all"))
        self.resume_all_btn.setText(t("control.resume_all"))
        self.stop_all_btn.setText(t("control.stop_all"))

        for indicator in self.status_indicators.values():
            indicator.update_language()

        for hw_name, label in self.hardware_control_labels.items():
            display_key = self._hardware_display_keys.get(hw_name, f"hardware.{hw_name}")
            label.setText(f"{t(display_key)}:")

        for btn in self.hardware_start_btns.values():
            btn.setText(t("common.start"))
        for btn in self.hardware_stop_btns.values():
            btn.setText(t("common.stop"))

        self.emergency_btn.update_language()

    def update_hardware_state(self, hw_name: str, state: HardwareState):
        category = HARDWARE_NAME_TO_CATEGORY.get(hw_name, hw_name)
        if category in self.status_indicators:
            self.status_indicators[category].update_state(state)

    def _cleanup(self):
        self._event_bridge.unsubscribe_all()

    def destroy(self):
        self._cleanup()
