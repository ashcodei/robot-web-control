"""
Joint Control Widget Module
关节控制部件模块

PySide6 widget for controlling individual joint positions.
用于控制单个关节位置的 PySide6 部件。
"""

import threading
from gui.qt_imports import (
    QWidget, QGroupBox, QLabel, QPushButton, QSlider, QRadioButton,
    QHBoxLayout, QVBoxLayout, QScrollArea, Qt,
)
from typing import List, Optional, Callable, Dict
from dataclasses import dataclass


@dataclass
class JointLimits:
    """Joint limits configuration / 关节限位配置"""
    min_deg: float = -180.0
    max_deg: float = 180.0
    name: str = ""
    name_zh: str = ""


# Default joint limits for 7-DOF arm
DEFAULT_JOINT_LIMITS = [
    JointLimits(-170, 170, "Joint 1 (Base)", "关节1 (底座)"),
    JointLimits(-120, 120, "Joint 2 (Shoulder)", "关节2 (肩)"),
    JointLimits(-170, 170, "Joint 3 (Elbow)", "关节3 (肘)"),
    JointLimits(-120, 120, "Joint 4 (Wrist1)", "关节4 (腕1)"),
    JointLimits(-170, 170, "Joint 5 (Wrist2)", "关节5 (腕2)"),
    JointLimits(-120, 120, "Joint 6 (Wrist3)", "关节6 (腕3)"),
    JointLimits(-360, 360, "Joint 7 (Tool)", "关节7 (工具)"),
]


class JointControlWidget(QGroupBox):
    """
    Widget for controlling arm joint positions.
    控制手臂关节位置的部件。

    Provides sliders for each joint with real-time feedback.
    为每个关节提供滑块和实时反馈。
    """

    def __init__(self, parent, arm_side: str = "left", num_joints: int = 7,
                 joint_limits: Optional[List[JointLimits]] = None,
                 on_change_callback: Optional[Callable[[str, List[float]], None]] = None,
                 language: str = "en", **kwargs):
        """
        Initialize joint control widget.
        初始化关节控制部件。

        Args:
            parent: Parent widget
            arm_side: "left" or "right"
            num_joints: Number of joints
            joint_limits: List of JointLimits for each joint
            on_change_callback: Callback when joints change (arm_side, joints) -> None
            language: Display language ("en" or "zh")
        """
        title = f"{arm_side.capitalize()} Arm Joints" if language == "en" else f"{'左' if arm_side == 'left' else '右'}臂关节"
        super().__init__(title, parent)

        self._arm_side = arm_side
        self._num_joints = num_joints
        self._joint_limits = joint_limits or DEFAULT_JOINT_LIMITS[:num_joints]
        self._on_change = on_change_callback
        self._language = language

        # UI elements
        self.joint_sliders: List[QSlider] = []
        self.joint_labels: List[QLabel] = []
        self.actual_labels: List[QLabel] = []

        # Tracking
        self._send_on_change = True
        self._lock = threading.Lock()

        self._create_widgets()

    def _create_widgets(self):
        """Create child widgets / 创建子部件"""
        main_layout = QVBoxLayout(self)

        # Create scrollable frame for sliders
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(250)
        main_layout.addWidget(scroll_area)

        self.sliders_frame = QWidget()
        sliders_layout = QVBoxLayout(self.sliders_frame)
        sliders_layout.setContentsMargins(5, 5, 5, 5)
        scroll_area.setWidget(self.sliders_frame)

        # Create slider for each joint
        for i in range(self._num_joints):
            self._create_joint_slider(sliders_layout, i)

        # Control buttons
        btn_layout = QHBoxLayout()
        main_layout.addLayout(btn_layout)

        zero_text = "Zero All" if self._language == "en" else "全部归零"
        zero_btn = QPushButton(zero_text)
        zero_btn.clicked.connect(self._zero_all)
        btn_layout.addWidget(zero_btn)

        home_text = "Home" if self._language == "en" else "复位"
        home_btn = QPushButton(home_text)
        home_btn.clicked.connect(self._go_home)
        btn_layout.addWidget(home_btn)

        send_text = "Send" if self._language == "en" else "发送"
        send_btn = QPushButton(send_text)
        send_btn.clicked.connect(self._send_positions)
        btn_layout.addWidget(send_btn)

        btn_layout.addStretch()

    def _create_joint_slider(self, parent_layout: QVBoxLayout, index: int):
        """Create slider for a single joint / 为单个关节创建滑块"""
        limits = self._joint_limits[index] if index < len(self._joint_limits) else JointLimits()

        row_layout = QHBoxLayout()
        parent_layout.addLayout(row_layout)

        # Joint name
        name = limits.name_zh if self._language == "zh" else limits.name
        if not name:
            name = f"Joint {index + 1}" if self._language == "en" else f"关节 {index + 1}"
        name_label = QLabel(name)
        name_label.setMinimumWidth(130)
        row_layout.addWidget(name_label)

        # Slider (QSlider uses integer values, so we multiply by 10 for 0.1 precision)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(int(limits.min_deg * 10), int(limits.max_deg * 10))
        slider.setValue(0)
        slider.setMinimumWidth(150)
        row_layout.addWidget(slider)
        self.joint_sliders.append(slider)

        # Command value label
        cmd_label = QLabel("0.0°")
        cmd_label.setMinimumWidth(60)
        row_layout.addWidget(cmd_label)
        self.joint_labels.append(cmd_label)

        # Actual value label
        actual_label = QLabel("(--)")
        actual_label.setMinimumWidth(60)
        actual_label.setStyleSheet("color: gray;")
        row_layout.addWidget(actual_label)
        self.actual_labels.append(actual_label)

        # Update label on change
        slider.valueChanged.connect(lambda val, idx=index: self._on_slider_change(idx, val))

    def _on_slider_change(self, index: int, raw_value: int):
        """Handle slider value change / 处理滑块值变化"""
        val = raw_value / 10.0
        if index < len(self.joint_labels):
            self.joint_labels[index].setText(f"{val:.1f}°")

        if self._send_on_change and self._on_change:
            joints = self.get_positions()
            self._on_change(self._arm_side, joints)

    def _zero_all(self):
        """Set all joints to zero / 将所有关节设为零"""
        self._send_on_change = False
        for slider in self.joint_sliders:
            slider.setValue(0)
        self._send_on_change = True
        self._send_positions()

    def _go_home(self):
        """Move to home position / 移动到初始位置"""
        # Default home position (can be customized)
        home = [0.0] * self._num_joints
        self.set_positions(home)

    def _send_positions(self):
        """Send current positions via callback / 通过回调发送当前位置"""
        if self._on_change:
            joints = self.get_positions()
            self._on_change(self._arm_side, joints)

    def get_positions(self) -> List[float]:
        """Get current slider positions / 获取当前滑块位置"""
        return [slider.value() / 10.0 for slider in self.joint_sliders]

    def set_positions(self, positions: List[float], send: bool = True):
        """
        Set slider positions.
        设置滑块位置。

        Args:
            positions: List of joint positions in degrees
            send: Whether to trigger callback
        """
        self._send_on_change = False
        for i, val in enumerate(positions[:self._num_joints]):
            if i < len(self.joint_sliders):
                self.joint_sliders[i].setValue(int(val * 10))
        self._send_on_change = True

        if send and self._on_change:
            self._on_change(self._arm_side, positions[:self._num_joints])

    def update_actual_positions(self, positions: List[float]):
        """
        Update actual position labels (from hardware feedback).
        更新实际位置标签（来自硬件反馈）。

        Args:
            positions: List of actual joint positions
        """
        for i, val in enumerate(positions[:len(self.actual_labels)]):
            self.actual_labels[i].setText(f"({val:.1f}°)")

    def update_language(self, language: str):
        """Update display language / 更新显示语言"""
        self._language = language
        title = f"{self._arm_side.capitalize()} Arm Joints" if language == "en" else f"{'左' if self._arm_side == 'left' else '右'}臂关节"
        self.setTitle(title)


class DualJointControlWidget(QWidget):
    """
    Widget for controlling both arms' joints.
    控制双臂关节的部件。
    """

    def __init__(self, parent, on_change_callback: Optional[Callable[[str, List[float]], None]] = None,
                 language: str = "en", **kwargs):
        """
        Initialize dual joint control widget.
        初始化双关节控制部件。

        Args:
            parent: Parent widget
            on_change_callback: Callback when joints change
            language: Display language
        """
        super().__init__(parent)

        self._language = language
        self._on_change = on_change_callback

        main_layout = QVBoxLayout(self)

        # Arm selector
        selector_layout = QHBoxLayout()
        main_layout.addLayout(selector_layout)

        selector_layout.addWidget(QLabel("Control:" if language == "en" else "控制:"))

        self._arm_selection = "both"

        self.radio_left = QRadioButton("Left" if language == "en" else "左臂")
        self.radio_left.clicked.connect(lambda: self._set_arm_selection("left"))
        selector_layout.addWidget(self.radio_left)

        self.radio_right = QRadioButton("Right" if language == "en" else "右臂")
        self.radio_right.clicked.connect(lambda: self._set_arm_selection("right"))
        selector_layout.addWidget(self.radio_right)

        self.radio_both = QRadioButton("Both" if language == "en" else "双臂")
        self.radio_both.setChecked(True)
        self.radio_both.clicked.connect(lambda: self._set_arm_selection("both"))
        selector_layout.addWidget(self.radio_both)

        selector_layout.addStretch()

        # Create joint controls for both arms
        arms_layout = QHBoxLayout()
        main_layout.addLayout(arms_layout)

        self.left_control = JointControlWidget(
            self, arm_side="left",
            on_change_callback=self._on_left_change,
            language=language
        )
        arms_layout.addWidget(self.left_control)

        self.right_control = JointControlWidget(
            self, arm_side="right",
            on_change_callback=self._on_right_change,
            language=language
        )
        arms_layout.addWidget(self.right_control)

    def _set_arm_selection(self, value: str):
        """Set arm selection / 设置手臂选择"""
        self._arm_selection = value

    def _on_left_change(self, arm_side: str, joints: List[float]):
        """Handle left arm change / 处理左臂变化"""
        if self._arm_selection in ["left", "both"]:
            if self._on_change:
                self._on_change("left", joints)

    def _on_right_change(self, arm_side: str, joints: List[float]):
        """Handle right arm change / 处理右臂变化"""
        if self._arm_selection in ["right", "both"]:
            if self._on_change:
                self._on_change("right", joints)

    def get_positions(self, arm: str = "both") -> Dict[str, List[float]]:
        """Get joint positions / 获取关节位置"""
        result = {}
        if arm in ["left", "both"]:
            result["left"] = self.left_control.get_positions()
        if arm in ["right", "both"]:
            result["right"] = self.right_control.get_positions()
        return result

    def set_positions(self, arm: str, positions: List[float]):
        """Set joint positions / 设置关节位置"""
        if arm == "left":
            self.left_control.set_positions(positions)
        elif arm == "right":
            self.right_control.set_positions(positions)

    def update_actual_positions(self, arm: str, positions: List[float]):
        """Update actual positions / 更新实际位置"""
        if arm == "left":
            self.left_control.update_actual_positions(positions)
        elif arm == "right":
            self.right_control.update_actual_positions(positions)

    def update_language(self, language: str):
        """Update display language / 更新显示语言"""
        self._language = language
        self.left_control.update_language(language)
        self.right_control.update_language(language)
