"""
Dexhand Widget Module
灵巧手部件模块

Main PySide6 widget for dexterous hand control.
灵巧手控制的主 PySide6 部件。
"""

import threading
from typing import Dict, List, Optional

from gui.qt_imports import (
    QWidget, QGroupBox, QLabel, QPushButton, QComboBox, QLineEdit,
    QSlider, QTabWidget, QScrollArea, QVBoxLayout, QHBoxLayout,
    QGridLayout, QFont, Qt, QTimer,
)
from gui.signals import get_thread_bridge

from .hand_configs import HAND_CONFIGS, get_hand_config, L6_FINGER_NAMES_EN, L10_FINGER_NAMES_EN
from .dexhand_controller import DexhandController
from .force_grab_controller import ForceGrabController
from .force_grab_widget import ForceGrabWidget
from .touch_matrix_widget import FingerMatrixDisplay


class DexhandWidget(QWidget):
    """
    Main dexterous hand control widget.
    主灵巧手控制部件。

    Provides UI for:
    - Hand connection (CAN interface)
    - Joint position control via sliders
    - Preset actions
    - Force grab control
    - Touch sensor visualization
    """

    def __init__(self, parent=None, controller: Optional[DexhandController] = None,
                 hand_side: str = "right", hand_type: str = "L6",
                 language: str = "en", **kwargs):
        """
        Initialize dexhand widget.
        初始化灵巧手部件。

        Args:
            parent: Parent widget
            controller: DexhandController instance (created if None)
            hand_side: "left" or "right"
            hand_type: "L6" or "L10"
            language: Display language ("en" or "zh")
        """
        super().__init__(parent)

        self._hand_side = hand_side
        self._hand_type = hand_type
        self._language = language

        # Controller
        self._controller = controller or DexhandController(
            name=f"{hand_side}_hand",
            config={
                "hand_type": hand_type,
                "hand_side": hand_side,
            }
        )

        # Force grab controller
        self._force_grab_controller = ForceGrabController(self._controller)

        # UI state
        self._can_value = self._controller._can_interface
        self._modbus_value = self._controller._modbus_port or "None"
        self._hand_type_value = hand_type
        self._hand_side_value = hand_side

        # Sliders
        self.slider_widgets: List[QSlider] = []
        self.slider_labels: List[QLabel] = []

        # Touch sensor polling
        self._touch_timer: Optional[QTimer] = None
        self._touch_poll_interval = 100  # ms

        self._create_widgets()

    def _create_widgets(self):
        """Create child widgets / 创建子部件"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Main notebook with tabs
        self.notebook = QTabWidget()
        main_layout.addWidget(self.notebook)

        # Tab 1: Joint Control
        self.control_tab = QWidget()
        self.notebook.addTab(self.control_tab,
                             "Joint Control" if self._language == "en" else "关节控制")
        self._create_control_tab()

        # Tab 2: Force Grab
        self.force_tab = QWidget()
        self.notebook.addTab(self.force_tab,
                             "Force Grab" if self._language == "en" else "力控抓取")
        self._create_force_tab()

        # Tab 3: Touch Sensors
        self.touch_tab = QWidget()
        self.notebook.addTab(self.touch_tab,
                             "Touch Sensors" if self._language == "en" else "触觉传感器")
        self._create_touch_tab()

    def _create_control_tab(self):
        """Create joint control tab / 创建关节控制选项卡"""
        layout = QVBoxLayout(self.control_tab)

        # Connection frame
        conn_group = QGroupBox("Connection" if self._language == "en" else "连接")
        layout.addWidget(conn_group)
        self._create_connection_frame(conn_group)

        # Hand type selection
        type_widget = QWidget()
        layout.addWidget(type_widget)
        self._create_type_frame(type_widget)

        # Preset buttons
        preset_group = QGroupBox("Presets" if self._language == "en" else "预设")
        layout.addWidget(preset_group)
        self._create_preset_frame(preset_group)

        # Sliders frame
        slider_group = QGroupBox(
            "Finger Positions (0-255)" if self._language == "en" else "手指位置")
        layout.addWidget(slider_group, 1)  # stretch factor 1
        self._create_slider_frame(slider_group)

        # Send button
        btn_layout = QHBoxLayout()
        layout.addLayout(btn_layout)

        send_text = "Send Positions" if self._language == "en" else "发送位置"
        send_btn = QPushButton(send_text)
        send_btn.clicked.connect(self._send_positions)
        btn_layout.addWidget(send_btn)

        self.result_label = QLabel("")
        self.result_label.setStyleSheet("color: gray;")
        btn_layout.addWidget(self.result_label)
        btn_layout.addStretch()

    def _create_connection_frame(self, parent):
        """Create connection controls / 创建连接控件"""
        h_layout = QHBoxLayout(parent)

        h_layout.addWidget(QLabel("CAN:"))
        self.can_entry = QLineEdit(self._can_value)
        self.can_entry.setFixedWidth(60)
        h_layout.addWidget(self.can_entry)

        h_layout.addWidget(QLabel("Serial:"))
        self.modbus_entry = QLineEdit(self._modbus_value)
        self.modbus_entry.setFixedWidth(90)
        h_layout.addWidget(self.modbus_entry)

        connect_text = "Connect" if self._language == "en" else "连接"
        self.connect_btn = QPushButton(connect_text)
        self.connect_btn.clicked.connect(self._connect)
        h_layout.addWidget(self.connect_btn)

        disconnect_text = "Disconnect" if self._language == "en" else "断开"
        self.disconnect_btn = QPushButton(disconnect_text)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.clicked.connect(self._disconnect)
        h_layout.addWidget(self.disconnect_btn)

        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("color: red;")
        h_layout.addWidget(self.status_label)
        h_layout.addStretch()

    def _create_type_frame(self, parent):
        """Create hand type selection / 创建手型选择"""
        h_layout = QHBoxLayout(parent)

        h_layout.addWidget(QLabel("Hand Type:" if self._language == "en" else "手型:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["L6", "L10"])
        self.type_combo.setCurrentText(self._hand_type_value)
        self.type_combo.setFixedWidth(60)
        self.type_combo.currentTextChanged.connect(self._on_type_change)
        h_layout.addWidget(self.type_combo)

        h_layout.addSpacing(15)
        h_layout.addWidget(QLabel("Side:" if self._language == "en" else "侧别:"))
        self.side_combo = QComboBox()
        self.side_combo.addItems(["left", "right"])
        self.side_combo.setCurrentText(self._hand_side_value)
        self.side_combo.setFixedWidth(70)
        h_layout.addWidget(self.side_combo)

        h_layout.addSpacing(10)
        setup_text = "Setup CAN" if self._language == "en" else "设置CAN"
        setup_btn = QPushButton(setup_text)
        setup_btn.clicked.connect(self._setup_can)
        h_layout.addWidget(setup_btn)
        h_layout.addStretch()

    def _create_preset_frame(self, parent):
        """Create preset action buttons / 创建预设动作按钮"""
        h_layout = QHBoxLayout(parent)

        presets = [
            ("Open (255)", self._open_hand),
            ("Close (0)", self._close_hand),
            ("Half (128)", self._half_hand),
            ("Grab (50)", self._grab_hand),
        ]

        for text, cmd in presets:
            btn = QPushButton(text)
            btn.clicked.connect(cmd)
            h_layout.addWidget(btn)
        h_layout.addStretch()

    def _create_slider_frame(self, parent):
        """Create finger position sliders / 创建手指位置滑块"""
        outer_layout = QVBoxLayout(parent)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedHeight(200)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        outer_layout.addWidget(scroll_area)

        self.sliders_inner = QWidget()
        self.sliders_inner_layout = QVBoxLayout(self.sliders_inner)
        self.sliders_inner_layout.setContentsMargins(0, 0, 0, 0)
        scroll_area.setWidget(self.sliders_inner)

        self._create_sliders()

    def _create_sliders(self):
        """Create sliders for current hand type / 为当前手型创建滑块"""
        # Clear existing
        while self.sliders_inner_layout.count():
            item = self.sliders_inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.slider_widgets.clear()
        self.slider_labels.clear()

        # Get finger names
        hand_type = self.type_combo.currentText() if hasattr(self, 'type_combo') else self._hand_type_value
        if hand_type == "L6":
            finger_names = L6_FINGER_NAMES_EN
        else:
            finger_names = L10_FINGER_NAMES_EN

        for i, name in enumerate(finger_names):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)

            name_label = QLabel(f"{name}:")
            name_label.setFixedWidth(110)
            row_layout.addWidget(name_label)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 255)
            slider.setValue(255)
            slider.setFixedWidth(150)
            row_layout.addWidget(slider)
            self.slider_widgets.append(slider)

            val_label = QLabel("255")
            val_label.setFixedWidth(30)
            row_layout.addWidget(val_label)
            self.slider_labels.append(val_label)
            row_layout.addStretch()

            # Update label on change
            idx = i
            slider.valueChanged.connect(
                lambda v, i=idx: self._update_slider_label(i)
            )

            self.sliders_inner_layout.addWidget(row_widget)

        self.sliders_inner_layout.addStretch()

    def _update_slider_label(self, idx: int):
        """Update slider value label / 更新滑块值标签"""
        if idx < len(self.slider_widgets) and idx < len(self.slider_labels):
            val = self.slider_widgets[idx].value()
            self.slider_labels[idx].setText(str(val))

    def _create_force_tab(self):
        """Create force grab tab / 创建力控抓取选项卡"""
        layout = QVBoxLayout(self.force_tab)
        self.force_grab_widget = ForceGrabWidget(
            controller=self._force_grab_controller,
            language=self._language
        )
        layout.addWidget(self.force_grab_widget)

    def _create_touch_tab(self):
        """Create touch sensor tab / 创建触觉传感器选项卡"""
        layout = QVBoxLayout(self.touch_tab)

        # Touch matrix display
        self.touch_display = FingerMatrixDisplay(language=self._language)
        layout.addWidget(self.touch_display)

        # Control buttons
        btn_layout = QHBoxLayout()
        layout.addLayout(btn_layout)

        start_text = "Start Polling" if self._language == "en" else "开始轮询"
        self.poll_btn = QPushButton(start_text)
        self.poll_btn.clicked.connect(self._toggle_touch_poll)
        btn_layout.addWidget(self.poll_btn)

        clear_text = "Clear" if self._language == "en" else "清除"
        clear_btn = QPushButton(clear_text)
        clear_btn.clicked.connect(self.touch_display.clear_all)
        btn_layout.addWidget(clear_btn)
        btn_layout.addStretch()

    # Connection methods
    def _setup_can(self):
        """Setup CAN interface / 设置CAN接口"""
        import subprocess

        can_if = self.can_entry.text()
        self.status_label.setText("Setting up CAN...")
        self.status_label.setStyleSheet("color: orange;")

        def do_setup():
            try:
                result = subprocess.run(
                    ['sudo', 'ip', 'link', 'set', can_if, 'up', 'type', 'can', 'bitrate', '1000000'],
                    capture_output=True, text=True, timeout=10
                )
                success = result.returncode == 0

                def update_ui():
                    if success:
                        self.status_label.setText(f"CAN {can_if} ready")
                        self.status_label.setStyleSheet("color: blue;")
                    else:
                        self.status_label.setText("CAN setup failed")
                        self.status_label.setStyleSheet("color: red;")

                get_thread_bridge().gui_callback.emit(update_ui)
            except Exception as e:
                get_thread_bridge().gui_callback.emit(
                    lambda: (self.status_label.setText(f"Error: {e}"),
                             self.status_label.setStyleSheet("color: red;")))

        threading.Thread(target=do_setup, daemon=True).start()

    def _connect(self):
        """Connect to hand / 连接到手部"""
        self.status_label.setText("Connecting...")
        self.status_label.setStyleSheet("color: orange;")

        # Update controller config
        modbus = self.modbus_entry.text()
        self._controller._can_interface = self.can_entry.text()
        self._controller._modbus_port = None if modbus == "None" else modbus
        self._controller._hand_type = self.type_combo.currentText()
        self._controller._hand_side = self.side_combo.currentText()

        def do_connect():
            success = self._controller.connect()

            def update_ui():
                if success:
                    hand_type = self.type_combo.currentText()
                    hand_side = self.side_combo.currentText()
                    self.status_label.setText(f"Connected ({hand_side} {hand_type})")
                    self.status_label.setStyleSheet("color: green;")
                    self.connect_btn.setEnabled(False)
                    self.disconnect_btn.setEnabled(True)
                else:
                    self.status_label.setText("Connection failed")
                    self.status_label.setStyleSheet("color: red;")

            get_thread_bridge().gui_callback.emit(update_ui)

        threading.Thread(target=do_connect, daemon=True).start()

    def _disconnect(self):
        """Disconnect from hand / 断开与手部的连接"""
        self._stop_touch_poll()
        self._controller.disconnect()
        self.status_label.setText("Disconnected")
        self.status_label.setStyleSheet("color: red;")
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)

    def _on_type_change(self, text=None):
        """Handle hand type change / 处理手型变化"""
        self._hand_type = self.type_combo.currentText()
        self._create_sliders()

    # Position control methods
    def _set_all_positions(self, value: int):
        """Set all sliders to same value / 将所有滑块设置为相同值"""
        for slider in self.slider_widgets:
            slider.setValue(value)

    def _open_hand(self):
        self._set_all_positions(255)
        self._send_positions()

    def _close_hand(self):
        self._set_all_positions(0)
        self._send_positions()

    def _half_hand(self):
        self._set_all_positions(128)
        self._send_positions()

    def _grab_hand(self):
        self._set_all_positions(50)
        self._send_positions()

    def _send_positions(self):
        """Send current slider positions to hand / 发送当前滑块位置到手部"""
        if not self._controller.is_ready():
            self.result_label.setText("Not connected!")
            self.result_label.setStyleSheet("color: red;")
            return

        positions = [slider.value() for slider in self.slider_widgets]
        self.result_label.setText("Sending...")
        self.result_label.setStyleSheet("color: orange;")

        def do_send():
            success = self._controller.set_positions(positions)

            def update_ui():
                if success:
                    self.result_label.setText("Sent OK")
                    self.result_label.setStyleSheet("color: green;")
                else:
                    self.result_label.setText("Send failed")
                    self.result_label.setStyleSheet("color: red;")

            get_thread_bridge().gui_callback.emit(update_ui)

        threading.Thread(target=do_send, daemon=True).start()

    # Touch sensor methods
    def _toggle_touch_poll(self):
        """Toggle touch sensor polling / 切换触觉传感器轮询"""
        if self._touch_timer and self._touch_timer.isActive():
            self._stop_touch_poll()
            self.poll_btn.setText("Start Polling" if self._language == "en" else "开始轮询")
        else:
            self._start_touch_poll()
            self.poll_btn.setText("Stop Polling" if self._language == "en" else "停止轮询")

    def _start_touch_poll(self):
        """Start touch sensor polling / 开始触觉传感器轮询"""
        if self._touch_timer and self._touch_timer.isActive():
            return

        self._touch_timer = QTimer(self)
        self._touch_timer.timeout.connect(self._poll_touch)
        self._touch_timer.start(self._touch_poll_interval)

    def _poll_touch(self):
        """Poll touch sensor data / 轮询触觉传感器数据"""
        if self._controller.is_ready():
            touch_data = self._controller.get_touch_data()
            self.touch_display.update_all(touch_data)

    def _stop_touch_poll(self):
        """Stop touch sensor polling / 停止触觉传感器轮询"""
        if self._touch_timer:
            self._touch_timer.stop()
            self._touch_timer = None

    # Public methods
    def get_positions(self) -> List[int]:
        """Get current slider positions / 获取当前滑块位置"""
        return [slider.value() for slider in self.slider_widgets]

    def set_positions(self, positions: List[int]):
        """Set slider positions / 设置滑块位置"""
        for i, val in enumerate(positions[:len(self.slider_widgets)]):
            self.slider_widgets[i].setValue(val)

    def get_actual_positions(self) -> List[int]:
        """Get actual positions from hardware / 从硬件获取实际位置"""
        return self._controller.get_actual_positions()

    def update_language(self, language: str):
        """Update display language / 更新显示语言"""
        self._language = language
        # Would need to recreate widgets for full language update

    def shutdown(self):
        """Clean shutdown / 清理关闭"""
        self._stop_touch_poll()
        self._controller.disconnect()
