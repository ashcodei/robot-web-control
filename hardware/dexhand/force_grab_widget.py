"""
Force Grab Widget Module
力反馈抓取部件模块

PySide6 widget for force feedback grab control panel.
力反馈抓取控制面板的 PySide6 部件。
"""

from gui.qt_imports import (
    QWidget, QGroupBox, QLabel, QPushButton, QCheckBox, QComboBox,
    QSlider, QLineEdit, QHBoxLayout, QVBoxLayout, QGridLayout,
    QFont, Qt, QTimer,
)
from gui.signals import get_thread_bridge
from typing import Dict, Optional, Callable

from .force_grab_controller import ForceGrabController, ForceGrabState, FingerState


class ForceGrabWidget(QGroupBox):
    """
    Force feedback grab control panel widget.
    力反馈抓取控制面板部件。

    Provides UI for configuring and controlling force-feedback grabbing.
    提供用于配置和控制力反馈抓取的 UI。
    """

    FINGER_NAMES = {
        "thumb": "Thumb",
        "index": "Index",
        "middle": "Middle",
        "ring": "Ring",
        "little": "Little",
    }

    def __init__(self, parent=None, controller: Optional[ForceGrabController] = None,
                 language: str = "en", **kwargs):
        """
        Initialize force grab widget.
        初始化力反馈抓取部件。

        Args:
            parent: Parent widget
            controller: ForceGrabController instance
            language: Display language ("en" or "zh")
        """
        title = "Force Feedback Grab" if language == "en" else "力反馈抓取"
        super().__init__(title, parent)

        self._controller = controller or ForceGrabController()
        self._language = language

        # Variables (stored as plain values; widgets hold state directly)
        self._use_sensor = True
        self._speed_value = 80
        self._torque_value = 150
        self._threshold_value = 50
        self._step_value = 5

        # UI elements
        self.position_sliders: Dict[int, QSlider] = {}
        self.position_labels: Dict[int, QLabel] = {}
        self.finger_status_labels: Dict[str, QLabel] = {}
        self.grab_btn: Optional[QPushButton] = None

        # Stall time options
        self.stall_time_options = {
            "Soft (0.5s)": 0.5,
            "Medium (1.0s)": 1.0,
            "Hard (1.5s)": 1.5
        }

        self._create_widgets()
        self._setup_callbacks()

    def _create_widgets(self):
        """Create child widgets / 创建子部件"""
        main_layout = QVBoxLayout(self)

        # Description
        desc_text = ("Force-controlled grabbing: fingers stop when force threshold is reached"
                     if self._language == "en" else
                     "力控抓取：手指在达到力阈值时停止")
        desc_label = QLabel(desc_text)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: gray;")
        main_layout.addWidget(desc_label)

        # Pre-grab position sliders
        self._create_position_frame(main_layout)

        # Grab parameters
        self._create_param_frame(main_layout)

        # Finger status display
        self._create_status_frame(main_layout)

        # Control buttons
        self._create_button_frame(main_layout)

    def _create_position_frame(self, parent_layout):
        """Create pre-grab position sliders / 创建预抓取位置滑块"""
        title = "Pre-grab Finger Positions (0=closed, 255=open)" if self._language == "en" else "预抓取手指位置"
        pos_group = QGroupBox(title)
        parent_layout.addWidget(pos_group)

        grid = QGridLayout(pos_group)

        finger_labels = ["Thumb Bend", "Thumb Yaw", "Index", "Middle", "Ring", "Little"]
        if self._language == "zh":
            finger_labels = ["拇指弯曲", "拇指横摆", "食指", "中指", "无名指", "小指"]

        for i, name in enumerate(finger_labels):
            row = i // 2
            col = (i % 2) * 3

            label = QLabel(f"{name}:")
            label.setFixedWidth(90)
            grid.addWidget(label, row, col)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 255)
            slider.setValue(250)
            slider.setFixedWidth(100)
            grid.addWidget(slider, row, col + 1)
            self.position_sliders[i] = slider

            val_label = QLabel("250")
            val_label.setFixedWidth(30)
            grid.addWidget(val_label, row, col + 2)
            self.position_labels[i] = val_label

            # Update label on change
            slider.valueChanged.connect(
                lambda v, lbl=val_label: lbl.setText(str(v))
            )

    def _create_param_frame(self, parent_layout):
        """Create grab parameters frame / 创建抓取参数框架"""
        title = "Grab Parameters" if self._language == "en" else "抓取参数"
        param_group = QGroupBox(title)
        parent_layout.addWidget(param_group)

        grid = QGridLayout(param_group)

        # Mode selection
        sensor_text = "Use Force Feedback Sensors" if self._language == "en" else "使用力反馈传感器"
        self.sensor_checkbox = QCheckBox(sensor_text)
        self.sensor_checkbox.setChecked(True)
        self.sensor_checkbox.stateChanged.connect(self._on_mode_changed)
        grid.addWidget(self.sensor_checkbox, 0, 0, 1, 2)

        # Mode description
        self.mode_desc_label = QLabel("(sensors detect contact → stop finger)")
        self.mode_desc_label.setStyleSheet("color: blue;")
        self.mode_desc_label.setFont(QFont("Arial", 8))
        grid.addWidget(self.mode_desc_label, 0, 2, 1, 2)

        # Speed
        speed_label_text = "Speed:" if self._language == "en" else "速度:"
        grid.addWidget(QLabel(speed_label_text), 1, 0)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(10, 255)
        self.speed_slider.setValue(80)
        self.speed_slider.setFixedWidth(100)
        grid.addWidget(self.speed_slider, 1, 1)
        self.speed_label = QLabel("80")
        self.speed_label.setFixedWidth(30)
        grid.addWidget(self.speed_label, 1, 2)
        self.speed_slider.valueChanged.connect(
            lambda v: (setattr(self, '_speed_value', v), self.speed_label.setText(str(v)))
        )

        # Torque
        torque_label_text = "Torque:" if self._language == "en" else "力矩:"
        grid.addWidget(QLabel(torque_label_text), 2, 0)
        self.torque_entry = QLineEdit("150")
        self.torque_entry.setFixedWidth(60)
        grid.addWidget(self.torque_entry, 2, 1)
        grid.addWidget(QLabel("(1-255)"), 2, 2)

        # Threshold (sensor mode only)
        self.threshold_widgets = []
        threshold_label_text = "Threshold:" if self._language == "en" else "阈值:"
        lbl = QLabel(threshold_label_text)
        grid.addWidget(lbl, 3, 0)
        self.threshold_widgets.append(lbl)

        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(5, 250)
        self.threshold_slider.setValue(50)
        self.threshold_slider.setFixedWidth(100)
        grid.addWidget(self.threshold_slider, 3, 1)
        self.threshold_widgets.append(self.threshold_slider)

        self.threshold_label = QLabel("50")
        self.threshold_label.setFixedWidth(30)
        self.threshold_label.setStyleSheet("color: red; font-weight: bold;")
        self.threshold_label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        grid.addWidget(self.threshold_label, 3, 2)
        self.threshold_widgets.append(self.threshold_label)
        self.threshold_slider.valueChanged.connect(
            lambda v: (setattr(self, '_threshold_value', v), self.threshold_label.setText(str(v)))
        )

        # Step (sensor mode only)
        self.step_widgets = []
        step_label_text = "Step:" if self._language == "en" else "步长:"
        lbl = QLabel(step_label_text)
        grid.addWidget(lbl, 4, 0)
        self.step_widgets.append(lbl)

        self.step_slider = QSlider(Qt.Orientation.Horizontal)
        self.step_slider.setRange(1, 20)
        self.step_slider.setValue(5)
        self.step_slider.setFixedWidth(100)
        grid.addWidget(self.step_slider, 4, 1)
        self.step_widgets.append(self.step_slider)

        self.step_label = QLabel("5")
        self.step_label.setFixedWidth(30)
        grid.addWidget(self.step_label, 4, 2)
        self.step_widgets.append(self.step_label)
        self.step_slider.valueChanged.connect(
            lambda v: (setattr(self, '_step_value', v), self.step_label.setText(str(v)))
        )

        # Stall time
        stall_label_text = "Stall Time:" if self._language == "en" else "堵转时间:"
        grid.addWidget(QLabel(stall_label_text), 5, 0)
        self.stall_combo = QComboBox()
        self.stall_combo.addItems(list(self.stall_time_options.keys()))
        self.stall_combo.setCurrentText("Hard (1.5s)")
        self.stall_combo.setFixedWidth(120)
        grid.addWidget(self.stall_combo, 5, 1)

    def _create_status_frame(self, parent_layout):
        """Create finger status display / 创建手指状态显示"""
        title = "Finger Status" if self._language == "en" else "手指状态"
        status_group = QGroupBox(title)
        parent_layout.addWidget(status_group)

        h_layout = QHBoxLayout(status_group)

        for i, (key, name) in enumerate(self.FINGER_NAMES.items()):
            frame_layout = QVBoxLayout()
            h_layout.addLayout(frame_layout)

            display_name = name if self._language == "en" else {
                "Thumb": "拇指", "Index": "食指", "Middle": "中指",
                "Ring": "无名指", "Little": "小指"
            }.get(name, name)

            name_label = QLabel(display_name)
            name_label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            frame_layout.addWidget(name_label)

            status_lbl = QLabel("Ready")
            status_lbl.setStyleSheet("color: gray;")
            frame_layout.addWidget(status_lbl)
            self.finger_status_labels[key] = status_lbl

    def _create_button_frame(self, parent_layout):
        """Create control buttons / 创建控制按钮"""
        btn_layout = QHBoxLayout()
        parent_layout.addLayout(btn_layout)

        reset_text = "Reset Position" if self._language == "en" else "重置位置"
        reset_btn = QPushButton(reset_text)
        reset_btn.clicked.connect(self._reset_to_preset)
        btn_layout.addWidget(reset_btn)

        grab_text = "Start Grab" if self._language == "en" else "开始抓取"
        self.grab_btn = QPushButton(grab_text)
        self.grab_btn.setStyleSheet(
            "background-color: #52C41A; color: white; font-weight: bold; font-size: 10pt; padding: 4px 12px;"
        )
        self.grab_btn.clicked.connect(self._toggle_grab)
        btn_layout.addWidget(self.grab_btn)

        stop_text = "Emergency Stop" if self._language == "en" else "紧急停止"
        self.stop_btn = QPushButton(stop_text)
        self.stop_btn.setStyleSheet(
            "background-color: #FF4D4F; color: white; font-weight: bold; font-size: 9pt; padding: 4px 8px;"
        )
        self.stop_btn.clicked.connect(self._emergency_stop)
        btn_layout.addWidget(self.stop_btn)

        release_text = "Release" if self._language == "en" else "释放"
        release_btn = QPushButton(release_text)
        release_btn.clicked.connect(self._release_grip)
        btn_layout.addWidget(release_btn)

    def _setup_callbacks(self):
        """Setup controller callbacks / 设置控制器回调"""
        self._controller.set_state_callback(self._on_state_changed)
        self._controller.set_finger_callback(self._on_finger_changed)

    def _on_mode_changed(self):
        """Handle mode checkbox change / 处理模式复选框变化"""
        use_sensor = self.sensor_checkbox.isChecked()
        self._use_sensor = use_sensor

        if use_sensor:
            self.mode_desc_label.setText("(sensors detect contact → stop finger)")
            self.mode_desc_label.setStyleSheet("color: blue;")
            for w in self.threshold_widgets + self.step_widgets:
                w.show()
        else:
            self.mode_desc_label.setText("(torque limit stops finger on contact)")
            self.mode_desc_label.setStyleSheet("color: green;")
            for w in self.threshold_widgets + self.step_widgets:
                w.hide()

    def _on_state_changed(self, state: ForceGrabState):
        """Handle controller state change / 处理控制器状态变化"""
        def update():
            if state == ForceGrabState.IDLE:
                self.grab_btn.setText("Start Grab")
                self.grab_btn.setStyleSheet(
                    "background-color: #52C41A; color: white; font-weight: bold; font-size: 10pt; padding: 4px 12px;")
            elif state == ForceGrabState.PREPARING:
                self.grab_btn.setText("Preparing...")
                self.grab_btn.setStyleSheet(
                    "background-color: #FAAD14; color: white; font-weight: bold; font-size: 10pt; padding: 4px 12px;")
            elif state == ForceGrabState.GRABBING:
                self.grab_btn.setText("Stop Grab")
                self.grab_btn.setStyleSheet(
                    "background-color: #FAAD14; color: white; font-weight: bold; font-size: 10pt; padding: 4px 12px;")
            elif state == ForceGrabState.HOLDING:
                self.grab_btn.setText("Holding")
                self.grab_btn.setStyleSheet(
                    "background-color: #1890FF; color: white; font-weight: bold; font-size: 10pt; padding: 4px 12px;")
            elif state == ForceGrabState.STOPPED:
                self.grab_btn.setText("Start Grab")
                self.grab_btn.setStyleSheet(
                    "background-color: #52C41A; color: white; font-weight: bold; font-size: 10pt; padding: 4px 12px;")

        get_thread_bridge().gui_callback.emit(update)

    def _on_finger_changed(self, finger: str, state: FingerState):
        """Handle finger state change / 处理手指状态变化"""
        def update():
            if finger in self.finger_status_labels:
                lbl = self.finger_status_labels[finger]
                if state.stopped:
                    lbl.setText(f"Stopped\n{state.stop_reason}")
                    lbl.setStyleSheet("color: green;")
                else:
                    lbl.setText(f"pos={state.position}\nF={state.force}")
                    lbl.setStyleSheet("color: blue;")

        get_thread_bridge().gui_callback.emit(update)

    def _reset_to_preset(self):
        """Reset fingers to preset positions / 重置手指到预设位置"""
        positions = [self.position_sliders[i].value() for i in range(6)]
        self._apply_config()
        # Would need dexhand controller reference to send positions

    def _toggle_grab(self):
        """Toggle grab state / 切换抓取状态"""
        if self._controller.state in [ForceGrabState.IDLE, ForceGrabState.STOPPED]:
            self._apply_config()
            self._controller.start_grab()
        else:
            self._controller.stop_grab()

    def _emergency_stop(self):
        """Emergency stop / 紧急停止"""
        self._controller.stop_grab()
        for key in self.finger_status_labels:
            self.finger_status_labels[key].setText("STOPPED")
            self.finger_status_labels[key].setStyleSheet("color: red;")

    def _release_grip(self):
        """Release grip / 释放抓取"""
        self._controller.release()
        for key in self.finger_status_labels:
            self.finger_status_labels[key].setText("Released")
            self.finger_status_labels[key].setStyleSheet("color: gray;")

    def _apply_config(self):
        """Apply current UI settings to controller / 将当前 UI 设置应用到控制器"""
        stall_time = self.stall_time_options.get(self.stall_combo.currentText(), 1.5)

        try:
            torque_val = int(self.torque_entry.text())
        except ValueError:
            torque_val = 150

        self._controller.configure(
            pre_grab_positions=[self.position_sliders[i].value() for i in range(6)],
            speed=self.speed_slider.value(),
            torque=torque_val,
            use_sensor=self.sensor_checkbox.isChecked(),
            threshold=self.threshold_slider.value(),
            step=self.step_slider.value(),
            stall_time=stall_time
        )

    def set_controller(self, controller: ForceGrabController):
        """Set controller / 设置控制器"""
        self._controller = controller
        self._setup_callbacks()

    def update_language(self, language: str):
        """Update display language / 更新显示语言"""
        self._language = language
        # Would need to recreate widgets for full language update
