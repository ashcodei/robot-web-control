"""
Teleop Widget Module
遥操作部件模块

GUI widget for teleoperation control.
用于遥操作控制的GUI部件。
"""

from gui.qt_imports import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QLineEdit, QRadioButton, QListWidget,
    QMessageBox, QButtonGroup,
)
from gui.base_widget import BaseHardwareWidget

from .teleop_controller import TeleopController, TeleopConnectionMode
from .trajectory_manager import TrajectoryManager
from config.i18n import t
from app_core.logger import get_logger
from gui.widgets import HardwareStatusCard

logger = get_logger(__name__)


class TeleopWidget(BaseHardwareWidget):
    """
    Widget for teleoperation control.
    用于遥操作控制的部件。
    """

    def __init__(self, parent, controller: TeleopController = None):
        super().__init__(parent)

        self.teleop = controller or TeleopController()
        self.trajectory_manager = TrajectoryManager()

        self._build_ui()
        self._create_timer(200, self._update_display)

    def _build_ui(self):
        """Build UI / 构建UI"""
        # Status card - pass translation key
        self.status_card = HardwareStatusCard(
            self,
            "teleop",
            "hardware.teleop",
            self.teleop
        )
        self._layout.addWidget(self.status_card)

        # Connection settings
        self.conn_frame = QGroupBox(t("teleop.mode"))
        conn_layout = QVBoxLayout(self.conn_frame)
        self._layout.addWidget(self.conn_frame)

        # Mode selection
        mode_row = QHBoxLayout()
        conn_layout.addLayout(mode_row)

        self.mode_label = QLabel(t("teleop.mode") + ":")
        mode_row.addWidget(self.mode_label)

        self._mode_button_group = QButtonGroup(self)
        # Store mode radio buttons for language update
        self.mode_radios = {}
        modes = [
            ("local", "teleop.mode.local"),
            ("remote_lan", "teleop.mode.remote_lan"),
            ("remote_wan", "teleop.mode.remote_wan")
        ]

        for value, text_key in modes:
            radio = QRadioButton(t(text_key))
            self._mode_button_group.addButton(radio)
            radio.toggled.connect(lambda checked, v=value: self._on_mode_changed() if checked else None)
            mode_row.addWidget(radio)
            self.mode_radios[value] = (radio, text_key)

        # Default selection
        self.mode_radios["local"][0].setChecked(True)

        # Host and port
        host_row = QHBoxLayout()
        conn_layout.addLayout(host_row)

        self.host_label = QLabel(t("teleop.ros_host") + ":")
        host_row.addWidget(self.host_label)
        self.host_entry = QLineEdit("localhost")
        self.host_entry.setFixedWidth(160)
        host_row.addWidget(self.host_entry)

        self.port_label = QLabel(t("teleop.ros_port") + ":")
        host_row.addWidget(self.port_label)
        self.port_entry = QLineEdit("9090")
        self.port_entry.setFixedWidth(80)
        host_row.addWidget(self.port_entry)

        host_row.addStretch()

        # Connect buttons
        btn_row = QHBoxLayout()
        conn_layout.addLayout(btn_row)

        self.connect_btn = QPushButton(t("common.connect"))
        self.connect_btn.clicked.connect(self._on_connect)
        btn_row.addWidget(self.connect_btn)

        self.start_btn = QPushButton(t("teleop.start_teleop"))
        self.start_btn.clicked.connect(self._on_start_teleop)
        btn_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton(t("teleop.stop_teleop"))
        self.stop_btn.clicked.connect(self._on_stop_teleop)
        btn_row.addWidget(self.stop_btn)

        btn_row.addStretch()

        # Trajectory recording
        self.traj_frame = QGroupBox(t("teleop.record"))
        traj_layout = QVBoxLayout(self.traj_frame)
        self._layout.addWidget(self.traj_frame)

        traj_btn_row = QHBoxLayout()
        traj_layout.addLayout(traj_btn_row)

        self.record_btn = QPushButton(t("teleop.record"))
        self.record_btn.clicked.connect(self._on_toggle_recording)
        traj_btn_row.addWidget(self.record_btn)

        self.playback_btn = QPushButton(t("teleop.playback"))
        self.playback_btn.clicked.connect(self._on_playback)
        traj_btn_row.addWidget(self.playback_btn)

        traj_btn_row.addStretch()

        # Trajectory list
        self.traj_listbox = QListWidget()
        self.traj_listbox.setMaximumHeight(120)
        traj_layout.addWidget(self.traj_listbox)

        self._refresh_trajectory_list()

        # Status display
        self.teleop_status_frame = QGroupBox(t("common.status"))
        status_layout = QVBoxLayout(self.teleop_status_frame)
        self._layout.addWidget(self.teleop_status_frame)

        self.status_label = QLabel("")
        status_layout.addWidget(self.status_label)

    def _update_display(self):
        """Update display / 更新显示"""
        status = self.teleop.get_status()
        status_text = f"Mode: {status['mode']} | "
        status_text += f"Host: {status['ros_host']}:{status['ros_port']} | "
        status_text += f"Active: {status['is_active']}"
        self.status_label.setText(status_text)

    def _on_mode_changed(self):
        """Handle mode change / 处理模式变化"""
        mode = self._get_selected_mode()
        self.teleop.mode = TeleopConnectionMode(mode)

        # Enable/disable host entry based on mode
        if mode == "local":
            self.host_entry.setText("localhost")
            self.host_entry.setEnabled(False)
        else:
            self.host_entry.setEnabled(True)

    def _get_selected_mode(self) -> str:
        """Get currently selected mode value / 获取当前选中的模式值"""
        for value, (radio, _) in self.mode_radios.items():
            if radio.isChecked():
                return value
        return "local"

    def _on_connect(self):
        """Handle connect button / 处理连接按钮"""
        host = self.host_entry.text()
        port = int(self.port_entry.text())

        self.teleop.set_ros_host(host)
        self.teleop.set_ros_port(port)

        if self.teleop.connect():
            self.connect_btn.setText(t("common.disconnect"))
        else:
            QMessageBox.critical(
                self,
                t("common.error"),
                t("msg.connection_failed")
            )

    def _on_start_teleop(self):
        """Handle start teleop / 处理启动遥操作"""
        self.teleop.start()

    def _on_stop_teleop(self):
        """Handle stop teleop / 处理停止遥操作"""
        self.teleop.stop()

    def _on_toggle_recording(self):
        """Handle toggle recording / 处理切换录制"""
        if self.trajectory_manager.is_recording:
            trajectory = self.trajectory_manager.stop_recording()
            if trajectory:
                self.trajectory_manager.save_trajectory(trajectory)
                self._refresh_trajectory_list()
            self.record_btn.setText(t("teleop.record"))
        else:
            self.trajectory_manager.start_recording()
            self.record_btn.setText(f"{t('teleop.record')} ●")

    def _on_playback(self):
        """Handle playback / 处理回放"""
        items = self.traj_listbox.selectedItems()
        if not items:
            return

        name = items[0].text()
        trajectory = self.trajectory_manager.load_trajectory(name)

        if trajectory:
            self.trajectory_manager.play_trajectory(trajectory)

    def _refresh_trajectory_list(self):
        """Refresh trajectory list / 刷新轨迹列表"""
        self.traj_listbox.clear()
        for name in self.trajectory_manager.list_trajectories():
            self.traj_listbox.addItem(name)

    def update_language(self):
        """Update text for language change / 更新语言变化的文本"""
        # Update status card
        self.status_card.update_language()

        # Update connection frame
        self.conn_frame.setTitle(t("teleop.mode"))
        self.mode_label.setText(t("teleop.mode") + ":")

        # Update mode radio buttons
        for value, (radio, text_key) in self.mode_radios.items():
            radio.setText(t(text_key))

        # Update host/port labels
        self.host_label.setText(t("teleop.ros_host") + ":")
        self.port_label.setText(t("teleop.ros_port") + ":")

        # Update buttons
        self.connect_btn.setText(t("common.connect"))
        self.start_btn.setText(t("teleop.start_teleop"))
        self.stop_btn.setText(t("teleop.stop_teleop"))

        # Update trajectory frame
        self.traj_frame.setTitle(t("teleop.record"))

        # Update record button based on recording state
        if self.trajectory_manager.is_recording:
            self.record_btn.setText(f"{t('teleop.record')} ●")
        else:
            self.record_btn.setText(t("teleop.record"))

        self.playback_btn.setText(t("teleop.playback"))

        # Update status frame
        self.teleop_status_frame.setTitle(t("common.status"))
