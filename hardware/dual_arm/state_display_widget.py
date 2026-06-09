"""
State Display Widget Module
状态显示部件模块

PySide6 widget for displaying robot state (TCP position, joints, status).
用于显示机器人状态（TCP位置、关节、状态）的 PySide6 部件。
"""

from gui.qt_imports import (
    QWidget, QGroupBox, QLabel, QHBoxLayout, QVBoxLayout, QGridLayout, QFont,
)
from typing import Dict, List, Optional, Any


class ArmStateWidget(QGroupBox):
    """
    Widget for displaying single arm state.
    显示单臂状态的部件。
    """

    def __init__(self, parent, arm_side: str = "left", language: str = "en", **kwargs):
        """
        Initialize arm state widget.
        初始化手臂状态部件。

        Args:
            parent: Parent widget
            arm_side: "left" or "right"
            language: Display language
        """
        title = f"{arm_side.capitalize()} Arm State" if language == "en" else f"{'左' if arm_side == 'left' else '右'}臂状态"
        super().__init__(title, parent)

        self._arm_side = arm_side
        self._language = language

        self._create_widgets()

    def _create_widgets(self):
        """Create child widgets / 创建子部件"""
        main_layout = QVBoxLayout(self)

        # TCP Position
        tcp_frame = QGroupBox("TCP Position" if self._language == "en" else "TCP位置")
        main_layout.addWidget(tcp_frame)
        tcp_layout = QVBoxLayout(tcp_frame)

        tcp_inner = QWidget()
        tcp_layout.addWidget(tcp_inner)
        tcp_grid = QGridLayout(tcp_inner)
        tcp_grid.setContentsMargins(5, 3, 5, 3)

        self.tcp_labels = {}
        for i, axis in enumerate(['X', 'Y', 'Z']):
            tcp_grid.addWidget(QLabel(f"{axis}:"), 0, i * 2)
            lbl = QLabel("---.-- mm")
            lbl.setMinimumWidth(90)
            tcp_grid.addWidget(lbl, 0, i * 2 + 1)
            self.tcp_labels[axis.lower()] = lbl

        # Euler angles
        euler_frame = QGroupBox("Euler Angles" if self._language == "en" else "欧拉角")
        main_layout.addWidget(euler_frame)
        euler_layout = QVBoxLayout(euler_frame)

        euler_inner = QWidget()
        euler_layout.addWidget(euler_inner)
        euler_grid = QGridLayout(euler_inner)
        euler_grid.setContentsMargins(5, 3, 5, 3)

        self.euler_labels = {}
        for i, axis in enumerate(['Roll', 'Pitch', 'Yaw']):
            key = axis.lower()
            short_name = {'roll': 'R', 'pitch': 'P', 'yaw': 'Y'}[key]
            euler_grid.addWidget(QLabel(f"{short_name}:"), 0, i * 2)
            lbl = QLabel("---.--°")
            lbl.setMinimumWidth(75)
            euler_grid.addWidget(lbl, 0, i * 2 + 1)
            self.euler_labels[key] = lbl

        # Joint angles
        joints_frame = QGroupBox("Joint Angles" if self._language == "en" else "关节角度")
        main_layout.addWidget(joints_frame)
        joints_layout = QVBoxLayout(joints_frame)

        self.joints_text = QLabel("[---, ---, ---, ---, ---, ---, ---]")
        self.joints_text.setFont(QFont("Courier", 9))
        joints_layout.addWidget(self.joints_text)

        # Status indicator
        status_layout = QHBoxLayout()
        main_layout.addLayout(status_layout)

        status_layout.addWidget(QLabel("Status:" if self._language == "en" else "状态:"))
        self.status_label = QLabel("Unknown")
        self.status_label.setStyleSheet("color: gray;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

    def update_state(self, state: Dict[str, Any]):
        """
        Update displayed state.
        更新显示的状态。

        Args:
            state: Dictionary with 'joints', 'position', 'euler' keys
        """
        # Update TCP position
        position = state.get('position', {})
        for axis in ['x', 'y', 'z']:
            val = position.get(axis, 0)
            if axis in self.tcp_labels:
                self.tcp_labels[axis].setText(f"{val:.2f} mm")

        # Update Euler angles
        euler = state.get('euler', {})
        for axis in ['roll', 'pitch', 'yaw']:
            # Handle both 'roll' and 'x' style keys
            val = euler.get(axis, euler.get({'roll': 'x', 'pitch': 'y', 'yaw': 'z'}[axis], 0))
            if axis in self.euler_labels:
                self.euler_labels[axis].setText(f"{val:.2f}°")

        # Update joints
        joints = state.get('joints', [])
        if joints:
            joints_str = "[" + ", ".join(f"{j:.1f}" for j in joints) + "]"
            self.joints_text.setText(joints_str)

        # Update status
        status = state.get('status', 'connected')
        color = {'connected': 'green', 'moving': 'blue', 'error': 'red',
                 'disconnected': 'gray'}.get(status, 'gray')
        self.status_label.setText(status.capitalize())
        self.status_label.setStyleSheet(f"color: {color};")

    def clear_state(self):
        """Clear displayed state / 清除显示的状态"""
        for lbl in self.tcp_labels.values():
            lbl.setText("---.-- mm")
        for lbl in self.euler_labels.values():
            lbl.setText("---.--°")
        self.joints_text.setText("[---, ---, ---, ---, ---, ---, ---]")
        self.status_label.setText("Disconnected")
        self.status_label.setStyleSheet("color: gray;")

    def update_language(self, language: str):
        """Update display language / 更新显示语言"""
        self._language = language
        title = f"{self._arm_side.capitalize()} Arm State" if language == "en" else f"{'左' if self._arm_side == 'left' else '右'}臂状态"
        self.setTitle(title)


class DualArmStateWidget(QWidget):
    """
    Widget for displaying both arms' states.
    显示双臂状态的部件。
    """

    def __init__(self, parent, language: str = "en", **kwargs):
        """
        Initialize dual arm state widget.
        初始化双臂状态部件。

        Args:
            parent: Parent widget
            language: Display language
        """
        super().__init__(parent)

        self._language = language
        self._create_widgets()

    def _create_widgets(self):
        """Create child widgets / 创建子部件"""
        main_layout = QVBoxLayout(self)

        # Connection status
        status_layout = QHBoxLayout()
        main_layout.addLayout(status_layout)

        status_layout.addWidget(QLabel("Connection:" if self._language == "en" else "连接:"))
        self.connection_label = QLabel("Disconnected")
        self.connection_label.setStyleSheet("color: red;")
        status_layout.addWidget(self.connection_label)

        self.ip_label = QLabel("")
        self.ip_label.setStyleSheet("color: gray;")
        status_layout.addWidget(self.ip_label)
        status_layout.addStretch()

        # Left arm
        self.left_state = ArmStateWidget(self, arm_side="left", language=self._language)
        main_layout.addWidget(self.left_state)

        # Right arm
        self.right_state = ArmStateWidget(self, arm_side="right", language=self._language)
        main_layout.addWidget(self.right_state)

        # Error display
        error_frame = QGroupBox("Errors" if self._language == "en" else "错误")
        main_layout.addWidget(error_frame)
        error_layout = QVBoxLayout(error_frame)

        self.error_label = QLabel("No errors")
        self.error_label.setStyleSheet("color: gray;")
        error_layout.addWidget(self.error_label)

    def update_connection_status(self, connected: bool, ip: str = ""):
        """Update connection status / 更新连接状态"""
        if connected:
            self.connection_label.setText("Connected")
            self.connection_label.setStyleSheet("color: green;")
            self.ip_label.setText(f"({ip})")
        else:
            self.connection_label.setText("Disconnected")
            self.connection_label.setStyleSheet("color: red;")
            self.ip_label.setText("")
            self.left_state.clear_state()
            self.right_state.clear_state()

    def update_arm_state(self, arm: str, state: Dict[str, Any]):
        """
        Update arm state display.
        更新手臂状态显示。

        Args:
            arm: "left" or "right"
            state: State dictionary
        """
        if arm == "left":
            self.left_state.update_state(state)
        elif arm == "right":
            self.right_state.update_state(state)

    def update_error(self, error_message: Optional[str]):
        """Update error display / 更新错误显示"""
        if error_message:
            self.error_label.setText(error_message)
            self.error_label.setStyleSheet("color: red;")
        else:
            self.error_label.setText("No errors")
            self.error_label.setStyleSheet("color: gray;")

    def update_language(self, language: str):
        """Update display language / 更新显示语言"""
        self._language = language
        self.left_state.update_language(language)
        self.right_state.update_language(language)


class RobotInfoWidget(QGroupBox):
    """
    Widget for displaying robot information.
    显示机器人信息的部件。
    """

    def __init__(self, parent, language: str = "en", **kwargs):
        """
        Initialize robot info widget.
        初始化机器人信息部件。
        """
        title = "Robot Information" if language == "en" else "机器人信息"
        super().__init__(title, parent)

        self._language = language
        self._create_widgets()

    def _create_widgets(self):
        """Create child widgets / 创建子部件"""
        grid = QGridLayout(self)
        self.info_labels = {}

        fields = [
            ("model", "Model", "型号"),
            ("version", "Version", "版本"),
            ("ip", "IP Address", "IP地址"),
            ("speed_factor", "Speed Factor", "速度因子"),
        ]

        for i, (key, name_en, name_zh) in enumerate(fields):
            name = name_zh if self._language == "zh" else name_en
            grid.addWidget(QLabel(f"{name}:"), i, 0)
            lbl = QLabel("--")
            lbl.setMinimumWidth(150)
            grid.addWidget(lbl, i, 1)
            self.info_labels[key] = lbl

    def update_info(self, info: Dict[str, Any]):
        """Update robot info display / 更新机器人信息显示"""
        for key, label in self.info_labels.items():
            value = info.get(key, "--")
            label.setText(str(value))

    def update_language(self, language: str):
        """Update display language / 更新显示语言"""
        self._language = language
