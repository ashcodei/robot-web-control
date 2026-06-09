"""
Master Arm Teleoperation Widget Module
主臂遥操作部件模块

GUI widget for master-follower arm control via ROS2 rosbridge.
用于通过ROS2 rosbridge进行主从臂控制的GUI部件。
"""

import os
import re
import time
import json
import math
import signal
import threading
import subprocess
from datetime import datetime
from typing import Optional, Callable, List, Dict

from gui.qt_imports import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QScrollArea, QFrame, QFont,
    QMessageBox, QTimer, QSizePolicy, Qt,
)

from config.i18n import t
from app_core.logger import get_logger
from gui.signals import get_thread_bridge

logger = get_logger(__name__)

# Try to import roslibpy for ROS2 communication
try:
    import roslibpy
    ROSLIBPY_AVAILABLE = True
except ImportError:
    logger.warning("roslibpy not available. Install with: pip install roslibpy")
    ROSLIBPY_AVAILABLE = False



class MasterArmTeleopWidget(QWidget):
    """
    Master arm teleoperation widget for master-follower arm control.

    Connects to ROS2 via rosbridge to receive master arm joint positions,
    then sends them to the follower arm using joint_follow().
    """

    def __init__(self, parent, dual_arm_controller=None, **kwargs):
        super().__init__(parent)

        self.dual_arm = dual_arm_controller

        # ROS connection state
        self.ros_client = None
        self.ros_connected = False
        self.left_arm_subscriber = None
        self.right_arm_subscriber = None

        # Teleoperation state
        self.teleop_active = False
        self.teleop_left_enabled = False
        self.teleop_right_enabled = False

        # Latest master arm data
        self.master_left_joints = None
        self.master_right_joints = None
        self.last_send_time = {'left': 0, 'right': 0}
        self.send_interval = 0.02  # 50Hz
        self._first_data_received = {'left': False, 'right': False}
        self._message_count = {'left': 0, 'right': 0}

        # Joint direction mapping for mirroring
        self.joint_negation = {
            'left': [1, 1, 1, 1, 1, 1, 1],
            'right': [1, -1, 1, -1, 1, 1, 1]  # Negate J1, J3 for right arm
        }

        # Joint offset calibration
        self.joint_offsets = {
            'left': [0.0] * 7,
            'right': [0.0] * 7
        }
        self.offsets_calibrated = False

        # Smoothed joint positions for velocity limiting
        self.smoothed_joints = {'left': None, 'right': None}
        self.last_sent_joints = {'left': None, 'right': None}

        # Trajectory storage directory
        self.trajectory_directory = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'trajectories'
        )
        os.makedirs(self.trajectory_directory, exist_ok=True)

        # Docker state
        self._docker_process = None
        self._docker_running = False
        self._docker_starting = False  # Prevent multiple starts
        self._docker_dir = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "../../libs/linkerta_v2_1.0.3"
        ))

        # Recording state
        self.is_recording = False
        self.recording_data = {'left': [], 'right': []}
        self.recording_start_time = None

        # Track which joints should be highlighted red (diff > 10 degrees)
        self._joints_highlight_red = {
            'left': [False] * 7,
            'right': [False] * 7
        }

        # Timers
        self._follower_timer = None
        self._recording_timer = None
        self._check_ros_timer = None
        self._check_data_timer = None

        # Thread-safe bridge for cross-thread GUI updates
        self._thread_bridge = get_thread_bridge()

        self._build_ui()

        # Check and stop any existing Docker containers on startup
        QTimer.singleShot(100, self._check_existing_docker)

        # Start follower position updates (shows robot state continuously)
        QTimer.singleShot(500, self._start_follower_updates)

    def _log(self, message):
        """Log message"""
        logger.info(f"[MasterTeleop] {message}")

    def _build_ui(self):
        """Build the UI"""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # ===== Scrollable Container =====
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        outer_layout.addWidget(scroll_area)

        scrollable_widget = QWidget()
        scroll_layout = QVBoxLayout(scrollable_widget)
        scroll_layout.setContentsMargins(10, 10, 10, 10)
        scroll_area.setWidget(scrollable_widget)

        mono_font = QFont("Consolas", 9)
        mono_font_small = QFont("Consolas", 8)
        topic_font = QFont("Arial", 8)

        # ===== Master Arm Docker Section =====
        self.docker_frame = QGroupBox(t("master_teleop.docker_control"))
        docker_layout = QVBoxLayout(self.docker_frame)
        scroll_layout.addWidget(self.docker_frame)

        docker_row = QHBoxLayout()
        docker_layout.addLayout(docker_row)

        self.docker_btn = QPushButton(t("master_teleop.start_docker"))
        self.docker_btn.setFixedWidth(180)
        self.docker_btn.setStyleSheet("background-color: #1890FF; color: white;")
        self.docker_btn.clicked.connect(self._toggle_docker)
        docker_row.addWidget(self.docker_btn)

        self.docker_status_label = QLabel(t("master_teleop.docker_stopped"))
        self.docker_status_label.setStyleSheet("color: gray;")
        docker_row.addWidget(self.docker_status_label)
        docker_row.addStretch()

        # ===== ROS Connection Section =====
        self.ros_frame = QGroupBox(t("master_teleop.ros_connection"))
        ros_layout = QVBoxLayout(self.ros_frame)
        scroll_layout.addWidget(self.ros_frame)

        conn_row = QHBoxLayout()
        ros_layout.addLayout(conn_row)

        conn_row.addWidget(QLabel(t("master_teleop.host") + ":"))
        self.ros_host_entry = QLineEdit("localhost")
        self.ros_host_entry.setFixedWidth(120)
        conn_row.addWidget(self.ros_host_entry)

        conn_row.addWidget(QLabel(t("master_teleop.port") + ":"))
        self.ros_port_entry = QLineEdit("9090")
        self.ros_port_entry.setFixedWidth(60)
        conn_row.addWidget(self.ros_port_entry)

        self.ros_connect_btn = QPushButton(t("common.connect"))
        self.ros_connect_btn.setFixedWidth(100)
        self.ros_connect_btn.setStyleSheet("background-color: #1890FF; color: white;")
        self.ros_connect_btn.clicked.connect(self._toggle_ros_connection)
        conn_row.addWidget(self.ros_connect_btn)

        self.ros_status_label = QLabel(t("common.disconnected"))
        self.ros_status_label.setStyleSheet("color: gray;")
        conn_row.addWidget(self.ros_status_label)
        conn_row.addStretch()

        # ROS Topics info
        topics_label = QLabel("Topics: /left_arm_joint_control, /right_arm_joint_control")
        topics_label.setFont(topic_font)
        topics_label.setStyleSheet("color: gray;")
        ros_layout.addWidget(topics_label)

        # ===== Teleoperation Control Section =====
        self.teleop_frame = QGroupBox(t("master_teleop.control"))
        teleop_layout = QVBoxLayout(self.teleop_frame)
        scroll_layout.addWidget(self.teleop_frame)

        ctrl_row = QHBoxLayout()
        teleop_layout.addLayout(ctrl_row)

        # Left arm teleop checkbox
        self.teleop_left_cb = QCheckBox(t("master_teleop.left_arm"))
        self.teleop_left_cb.stateChanged.connect(self._on_teleop_left_changed)
        ctrl_row.addWidget(self.teleop_left_cb)

        # Right arm teleop checkbox
        self.teleop_right_cb = QCheckBox(t("master_teleop.right_arm"))
        self.teleop_right_cb.stateChanged.connect(self._on_teleop_right_changed)
        ctrl_row.addWidget(self.teleop_right_cb)

        # Start/Stop teleop button
        self.teleop_btn = QPushButton(t("master_teleop.start"))
        self.teleop_btn.setFixedWidth(120)
        self.teleop_btn.setStyleSheet("background-color: #52C41A; color: white;")
        self.teleop_btn.clicked.connect(self._toggle_teleop)
        ctrl_row.addWidget(self.teleop_btn)

        self.teleop_status_label = QLabel(t("common.stopped"))
        self.teleop_status_label.setStyleSheet("color: gray;")
        ctrl_row.addWidget(self.teleop_status_label)
        ctrl_row.addStretch()

        # ===== Motion Settings Section =====
        self.motion_frame = QGroupBox(t("master_teleop.motion_settings"))
        motion_layout = QVBoxLayout(self.motion_frame)
        scroll_layout.addWidget(self.motion_frame)

        speed_row = QHBoxLayout()
        motion_layout.addLayout(speed_row)

        speed_row.addWidget(QLabel(t("master_teleop.max_speed") + ":"))
        self.teleop_speed_entry = QLineEdit("2.0")
        self.teleop_speed_entry.setFixedWidth(60)
        speed_row.addWidget(self.teleop_speed_entry)
        speed_row.addWidget(QLabel("rad/s"))

        speed_row.addWidget(QLabel(t("master_teleop.max_accel") + ":"))
        self.teleop_accel_entry = QLineEdit("2.0")
        self.teleop_accel_entry.setFixedWidth(60)
        speed_row.addWidget(self.teleop_accel_entry)
        speed_row.addWidget(QLabel("rad/s\u00b2"))

        speed_row.addWidget(QLabel(t("master_teleop.smoothing") + ":"))
        self.teleop_smoothing_entry = QLineEdit("0.3")
        self.teleop_smoothing_entry.setFixedWidth(50)
        speed_row.addWidget(self.teleop_smoothing_entry)
        speed_row.addWidget(QLabel("(0.1-1.0)"))
        speed_row.addStretch()

        # Options row
        options_row = QHBoxLayout()
        motion_layout.addLayout(options_row)

        self.convert_deg_to_rad_cb = QCheckBox(t("master_teleop.deg_to_rad"))
        self.convert_deg_to_rad_cb.setChecked(True)
        options_row.addWidget(self.convert_deg_to_rad_cb)

        self.apply_negation_cb = QCheckBox(t("master_teleop.apply_negation"))
        self.apply_negation_cb.setChecked(True)
        options_row.addWidget(self.apply_negation_cb)

        self.debug_teleop_cb = QCheckBox(t("master_teleop.debug"))
        self.debug_teleop_cb.setChecked(False)
        options_row.addWidget(self.debug_teleop_cb)

        # Calibration button
        self.calibrate_btn = QPushButton(t("master_teleop.calibrate"))
        self.calibrate_btn.setFixedWidth(130)
        self.calibrate_btn.setStyleSheet("background-color: #722ED1; color: white;")
        self.calibrate_btn.clicked.connect(self._calibrate_offsets)
        options_row.addWidget(self.calibrate_btn)

        self.calibration_status = QLabel(t("master_teleop.not_calibrated"))
        self.calibration_status.setStyleSheet("color: gray;")
        options_row.addWidget(self.calibration_status)
        options_row.addStretch()

        # ===== Trajectory Recording Section =====
        self.record_frame = QGroupBox(t("master_teleop.trajectory_recording"))
        record_layout = QVBoxLayout(self.record_frame)
        scroll_layout.addWidget(self.record_frame)

        record_row = QHBoxLayout()
        record_layout.addLayout(record_row)

        record_row.addWidget(QLabel(t("master_teleop.name") + ":"))
        self.traj_name_entry = QLineEdit("teleop_traj_1")
        self.traj_name_entry.setFixedWidth(160)
        record_row.addWidget(self.traj_name_entry)

        self.record_btn = QPushButton(t("master_teleop.start_recording"))
        self.record_btn.setFixedWidth(130)
        self.record_btn.setStyleSheet("background-color: #FF4D4F; color: white;")
        self.record_btn.clicked.connect(self._toggle_recording)
        record_row.addWidget(self.record_btn)

        self.record_status_label = QLabel(t("common.ready"))
        self.record_status_label.setStyleSheet("color: gray;")
        record_row.addWidget(self.record_status_label)
        record_row.addStretch()

        # Recording options
        options_row2 = QHBoxLayout()
        record_layout.addLayout(options_row2)

        self.record_left_cb = QCheckBox(t("master_teleop.record_left"))
        self.record_left_cb.setChecked(True)
        options_row2.addWidget(self.record_left_cb)

        self.record_right_cb = QCheckBox(t("master_teleop.record_right"))
        self.record_right_cb.setChecked(True)
        options_row2.addWidget(self.record_right_cb)

        options_row2.addWidget(QLabel(t("master_teleop.sample_rate") + ":"))
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItems(["10", "20", "30", "50", "100"])
        self.sample_rate_combo.setCurrentText("50")
        self.sample_rate_combo.setFixedWidth(70)
        options_row2.addWidget(self.sample_rate_combo)
        options_row2.addWidget(QLabel("Hz"))
        options_row2.addStretch()

        # ===== Master Arm & Follower Status Display =====
        self.status_frame = QGroupBox(t("master_teleop.status"))
        status_layout = QVBoxLayout(self.status_frame)
        scroll_layout.addWidget(self.status_frame)

        # Joint labels header (J1-J7)
        header_row = QHBoxLayout()
        status_layout.addLayout(header_row)
        spacer_lbl = QLabel("")
        spacer_lbl.setFixedWidth(60)
        header_row.addWidget(spacer_lbl)
        for i in range(7):
            lbl = QLabel(f"J{i+1}")
            lbl.setFont(mono_font_small)
            lbl.setFixedWidth(55)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header_row.addWidget(lbl)
        header_row.addStretch()

        # Left arm section
        self.left_section_frame = QGroupBox(t("master_teleop.left_arm"))
        left_section_layout = QVBoxLayout(self.left_section_frame)
        status_layout.addWidget(self.left_section_frame)

        # Left Master - individual labels for each joint
        left_master_row = QHBoxLayout()
        left_section_layout.addLayout(left_master_row)
        self.left_master_lbl = QLabel("Master:")
        self.left_master_lbl.setFixedWidth(60)
        left_master_row.addWidget(self.left_master_lbl)
        self.left_master_joint_labels = []
        for i in range(7):
            lbl = QLabel("--")
            lbl.setFont(mono_font)
            lbl.setFixedWidth(55)
            lbl.setStyleSheet("color: gray;")
            left_master_row.addWidget(lbl)
            self.left_master_joint_labels.append(lbl)
        left_master_row.addStretch()

        # Left Follower - individual labels for each joint
        left_follower_row = QHBoxLayout()
        left_section_layout.addLayout(left_follower_row)
        self.left_follower_lbl = QLabel("Follower:")
        self.left_follower_lbl.setFixedWidth(60)
        left_follower_row.addWidget(self.left_follower_lbl)
        self.left_follower_joint_labels = []
        for i in range(7):
            lbl = QLabel("--")
            lbl.setFont(mono_font)
            lbl.setFixedWidth(55)
            lbl.setStyleSheet("color: gray;")
            left_follower_row.addWidget(lbl)
            self.left_follower_joint_labels.append(lbl)
        left_follower_row.addStretch()

        # Left Diff indicator
        left_diff_row = QHBoxLayout()
        left_section_layout.addLayout(left_diff_row)
        self.left_diff_lbl = QLabel("Diff:")
        self.left_diff_lbl.setFixedWidth(60)
        left_diff_row.addWidget(self.left_diff_lbl)
        self.left_diff_label = QLabel("--")
        self.left_diff_label.setFont(mono_font)
        self.left_diff_label.setStyleSheet("color: gray;")
        left_diff_row.addWidget(self.left_diff_label)
        left_diff_row.addStretch()

        # Right arm section
        self.right_section_frame = QGroupBox(t("master_teleop.right_arm"))
        right_section_layout = QVBoxLayout(self.right_section_frame)
        status_layout.addWidget(self.right_section_frame)

        # Right Master - individual labels for each joint
        right_master_row = QHBoxLayout()
        right_section_layout.addLayout(right_master_row)
        self.right_master_lbl = QLabel("Master:")
        self.right_master_lbl.setFixedWidth(60)
        right_master_row.addWidget(self.right_master_lbl)
        self.right_master_joint_labels = []
        for i in range(7):
            lbl = QLabel("--")
            lbl.setFont(mono_font)
            lbl.setFixedWidth(55)
            lbl.setStyleSheet("color: gray;")
            right_master_row.addWidget(lbl)
            self.right_master_joint_labels.append(lbl)
        right_master_row.addStretch()

        # Right Follower - individual labels for each joint
        right_follower_row = QHBoxLayout()
        right_section_layout.addLayout(right_follower_row)
        self.right_follower_lbl = QLabel("Follower:")
        self.right_follower_lbl.setFixedWidth(60)
        right_follower_row.addWidget(self.right_follower_lbl)
        self.right_follower_joint_labels = []
        for i in range(7):
            lbl = QLabel("--")
            lbl.setFont(mono_font)
            lbl.setFixedWidth(55)
            lbl.setStyleSheet("color: gray;")
            right_follower_row.addWidget(lbl)
            self.right_follower_joint_labels.append(lbl)
        right_follower_row.addStretch()

        # Right Diff indicator
        right_diff_row = QHBoxLayout()
        right_section_layout.addLayout(right_diff_row)
        self.right_diff_lbl = QLabel("Diff:")
        self.right_diff_lbl.setFixedWidth(60)
        right_diff_row.addWidget(self.right_diff_lbl)
        self.right_diff_label = QLabel("--")
        self.right_diff_label.setFont(mono_font)
        self.right_diff_label.setStyleSheet("color: gray;")
        right_diff_row.addWidget(self.right_diff_label)
        right_diff_row.addStretch()

        # Add stretch at the bottom so content stays top-aligned
        scroll_layout.addStretch()

        # Check roslibpy availability
        if not ROSLIBPY_AVAILABLE:
            self.ros_connect_btn.setEnabled(False)
            self.ros_status_label.setText(t("master_teleop.roslibpy_not_installed"))
            self.ros_status_label.setStyleSheet("color: red;")

    # ==================== Helper for thread-safe UI updates ====================

    def _run_on_gui(self, func):
        """Schedule a callable to run on the GUI thread via the ThreadBridge signal."""
        self._thread_bridge.gui_callback.emit(func)

    # ==================== Docker Control ====================

    def _log_safe(self, message: str):
        """Thread-safe logging to GUI"""
        self._run_on_gui(lambda: self._log(message))

    def _check_existing_docker(self):
        """Check and stop any existing Docker containers on startup"""
        def check():
            try:
                result = subprocess.run(
                    ["docker", "ps", "--filter", "name=linkerta", "--format", "{{.Names}}"],
                    capture_output=True, text=True, timeout=5
                )
                containers = result.stdout.strip()
                if containers:
                    self._log_safe(f"Found existing Docker containers: {containers}")
                    self._log_safe("Stopping existing containers to prevent conflicts...")
                    subprocess.run(
                        ["docker", "compose", "down"],
                        cwd=self._docker_dir,
                        capture_output=True, timeout=15
                    )
                    self._log_safe("Existing containers stopped")
            except Exception as e:
                self._log_safe(f"Docker check: {e}")

        threading.Thread(target=check, daemon=True).start()

    def _toggle_docker(self):
        """Start or stop Docker containers"""
        if self._docker_running:
            self._stop_docker()
        else:
            self._start_docker()

    def _start_docker(self):
        """Start master arm Docker containers using docker compose"""
        if self._docker_running or self._docker_starting:
            return

        self._docker_starting = True
        self.docker_btn.setEnabled(False)
        self.docker_status_label.setText(t("master_teleop.docker_starting"))
        self.docker_status_label.setStyleSheet("color: orange;")
        self._log("Starting master arm Docker...")

        def run_docker():
            try:
                # Step 1: Check CAN interface
                self._log_safe("Checking CAN interface...")
                result = subprocess.run(
                    ["ip", "link", "show", "can0"],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    self._log_safe("[ERROR] CAN device (can0) not found")
                    self._run_on_gui(lambda: self._docker_start_failed("CAN not found"))
                    return

                # Check CAN state and bring up if needed
                can_state = subprocess.run(
                    ["cat", "/sys/class/net/can0/operstate"],
                    capture_output=True, text=True
                )
                if can_state.stdout.strip() != "up":
                    self._log_safe("Setting up CAN interface...")
                    subprocess.run(
                        ["sudo", "ip", "link", "set", "can0", "up", "type", "can", "bitrate", "1000000"],
                        capture_output=True, timeout=5
                    )
                self._log_safe("CAN interface ready")

                # Step 2: Build Docker image (quiet)
                self._log_safe("Building Docker image (this may take a few minutes on first run)...")
                result = subprocess.run(
                    ["docker", "compose", "build", "--quiet"],
                    cwd=self._docker_dir,
                    capture_output=True, text=True, timeout=300  # 5 minutes for first build
                )
                if result.returncode != 0:
                    # Filter out warning lines to show actual errors
                    error_lines = [l for l in result.stderr.split('\n')
                                   if l.strip() and 'level=warning' not in l]
                    error_msg = '\n'.join(error_lines[:5]) if error_lines else result.stderr[:500]
                    self._log_safe(f"[ERROR] Docker build failed (code {result.returncode}):")
                    self._log_safe(f"  {error_msg}")
                    self._run_on_gui(lambda: self._docker_start_failed("Build failed"))
                    return
                self._log_safe("Docker image ready")

                # Step 3: Stop any existing containers
                self._log_safe("Stopping existing containers...")
                subprocess.run(
                    ["docker", "compose", "down"],
                    cwd=self._docker_dir,
                    capture_output=True, timeout=15
                )

                # Step 4: Start rosbridge
                self._log_safe("Starting rosbridge server...")
                result = subprocess.run(
                    ["docker", "compose", "up", "-d", "rosbridge"],
                    cwd=self._docker_dir,
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode != 0:
                    self._log_safe(f"[ERROR] Rosbridge start failed: {result.stderr[:200]}")
                    self._run_on_gui(lambda: self._docker_start_failed("Rosbridge failed"))
                    return
                self._log_safe("Rosbridge started on port 9090")

                # Wait for rosbridge to be ready
                time.sleep(2)

                # Step 5: Start linkerta driver (detached)
                self._log_safe("Starting LinkerTA driver...")
                result = subprocess.run(
                    ["docker", "compose", "run", "-d", "--rm", "linkerta",
                     "bash", "-c",
                     "source /opt/ros/humble/setup.bash && "
                     "source /linkerta_ws/install/local_setup.bash && "
                     "ros2 launch linkerta run.launch.py"],
                    cwd=self._docker_dir,
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode != 0:
                    self._log_safe(f"[ERROR] LinkerTA start failed: {result.stderr[:200]}")
                    self._run_on_gui(lambda: self._docker_start_failed("LinkerTA failed"))
                    return

                # Wait for container to start
                self._log_safe("Waiting for LinkerTA to initialize...")
                time.sleep(5)

                # Check if container started
                result = subprocess.run(
                    ["docker", "ps", "--filter", "name=linkerta", "--format", "{{.Names}}"],
                    capture_output=True, text=True
                )
                if result.stdout.strip():
                    self._log_safe(f"LinkerTA containers: {result.stdout.strip()}")
                    self._docker_running = True
                    self._run_on_gui(lambda: self._update_docker_ui(True))
                    self._log_safe("Docker startup complete - ready to connect ROS")
                else:
                    self._log_safe("[ERROR] LinkerTA container not running")
                    self._run_on_gui(lambda: self._docker_start_failed("Container not started"))

            except subprocess.TimeoutExpired:
                self._log_safe("[ERROR] Docker command timed out")
                self._run_on_gui(lambda: self._docker_start_failed("Timeout"))
            except Exception as e:
                self._log_safe(f"[ERROR] Docker startup failed: {e}")
                self._run_on_gui(lambda: self._docker_start_failed(str(e)))
            finally:
                self._docker_starting = False

        threading.Thread(target=run_docker, daemon=True).start()

    def _docker_start_failed(self, reason: str):
        """Handle Docker start failure"""
        self._docker_starting = False
        self._docker_running = False
        self._update_docker_ui(False)
        self.docker_status_label.setText(t("master_teleop.docker_failed", reason=reason))
        self.docker_status_label.setStyleSheet("color: red;")

    def _stop_docker(self):
        """Stop Docker containers"""
        if not self._docker_running:
            return

        self.docker_btn.setEnabled(False)
        self.docker_status_label.setText(t("master_teleop.docker_stopping"))
        self.docker_status_label.setStyleSheet("color: orange;")
        self._log("Stopping master arm Docker...")

        def stop():
            try:
                # Use docker compose down
                result = subprocess.run(
                    ["docker", "compose", "down"],
                    cwd=self._docker_dir,
                    capture_output=True, text=True, timeout=15
                )
                if result.returncode == 0:
                    self._log_safe("Docker containers stopped")
                else:
                    self._log_safe(f"Docker stop warning: {result.stderr[:100]}")

                # Also kill process if running
                if self._docker_process:
                    try:
                        self._docker_process.terminate()
                    except Exception:
                        pass
                    self._docker_process = None

            except subprocess.TimeoutExpired:
                self._log_safe("Docker stop timed out, forcing...")
                try:
                    subprocess.run(
                        ["docker", "compose", "kill"],
                        cwd=self._docker_dir,
                        timeout=5
                    )
                except Exception:
                    pass
            except Exception as e:
                self._log_safe(f"Docker stop error: {e}")
            finally:
                self._docker_running = False
                self._run_on_gui(lambda: self._update_docker_ui(False))

        threading.Thread(target=stop, daemon=True).start()

    def _update_docker_ui(self, running: bool):
        """Update Docker button and status label"""
        self.docker_btn.setEnabled(True)
        if running:
            self.docker_btn.setText(t("master_teleop.stop_docker"))
            self.docker_btn.setStyleSheet("background-color: #FF4D4F; color: white;")
            self.docker_status_label.setText(t("master_teleop.docker_running"))
            self.docker_status_label.setStyleSheet("color: green;")
        else:
            self.docker_btn.setText(t("master_teleop.start_docker"))
            self.docker_btn.setStyleSheet("background-color: #1890FF; color: white;")
            self.docker_status_label.setText(t("master_teleop.docker_stopped"))
            self.docker_status_label.setStyleSheet("color: gray;")

    # ==================== ROS Connection ====================

    def _toggle_ros_connection(self):
        """Connect or disconnect from rosbridge"""
        if self.ros_connected:
            self._disconnect_ros()
        else:
            self._connect_ros()

    def _connect_ros(self):
        """Connect to rosbridge WebSocket server (non-blocking)"""
        if not ROSLIBPY_AVAILABLE:
            QMessageBox.critical(self, t("common.error"), t("master_teleop.roslibpy_install_hint"))
            return

        host = self.ros_host_entry.text()
        try:
            port = int(self.ros_port_entry.text())
        except ValueError:
            QMessageBox.critical(self, t("common.error"), t("master_teleop.invalid_port"))
            return

        self._log(f"Connecting to rosbridge at {host}:{port}...")
        self.ros_status_label.setText(t("common.connecting"))
        self.ros_status_label.setStyleSheet("color: orange;")
        self.ros_connect_btn.setEnabled(False)

        def do_connect():
            """Run connection in background thread"""
            try:
                self.ros_client = roslibpy.Ros(host=host, port=port)
                self.ros_client.on_ready(self._on_ros_connected)
                # This will block this thread, but not the main GUI thread
                self.ros_client.run()
            except Exception as e:
                self._log_safe(f"ROS connection error: {e}")

        # Start connection in background thread
        self._ros_connect_thread = threading.Thread(target=do_connect, daemon=True)
        self._ros_connect_thread.start()
        self._log("ROS connection started in background thread")

        # Check connection status after a delay
        QTimer.singleShot(2000, lambda: self._check_ros_connection(0))

    def _check_ros_connection(self, retry_count=0):
        """Check if ROS connection was successful"""
        try:
            if self.ros_client and self.ros_client.is_connected:
                self.ros_connected = True
                self.ros_connect_btn.setEnabled(True)
                self.ros_connect_btn.setText(t("common.disconnect"))
                self.ros_connect_btn.setStyleSheet("background-color: #FF4D4F; color: white;")
                self.ros_status_label.setText(t("common.connected"))
                self.ros_status_label.setStyleSheet("color: green;")
                self._log("Connected to rosbridge")
                self._subscribe_to_topics()
            elif retry_count < 8:
                # Keep retrying - rosbridge may take time to fully start
                QTimer.singleShot(1000, lambda: self._check_ros_connection(retry_count + 1))
            else:
                self.ros_connect_btn.setEnabled(True)
                self.ros_status_label.setText(t("master_teleop.connection_failed"))
                self.ros_status_label.setStyleSheet("color: red;")
                self._log("Connection failed - make sure Docker and rosbridge are running")
                self._cleanup_ros_client()
        except Exception as e:
            self._log(f"Connection check error: {e}")
            self.ros_connect_btn.setEnabled(True)
            self._cleanup_ros_client()

    def _cleanup_ros_client(self):
        """Clean up ROS client on failure"""
        if self.ros_client:
            try:
                self.ros_client.close()
            except:
                pass
            self.ros_client = None
        self.ros_connected = False

    def _on_ros_connected(self):
        """Callback when ROS connection is ready"""
        self._log("ROS connection ready")

    def _disconnect_ros(self):
        """Disconnect from rosbridge (non-blocking)"""
        self._stop_teleop()

        # Update UI immediately (non-blocking)
        self.ros_connected = False
        self._first_data_received = {'left': False, 'right': False}
        self.ros_connect_btn.setText(t("common.connect"))
        self.ros_connect_btn.setStyleSheet("background-color: #1890FF; color: white;")
        self.ros_status_label.setText(t("common.disconnected"))
        self.ros_status_label.setStyleSheet("color: gray;")
        self._log("Disconnecting from rosbridge...")

        # Capture references for background thread
        left_sub = self.left_arm_subscriber
        right_sub = self.right_arm_subscriber
        client = self.ros_client

        # Clear references immediately
        self.left_arm_subscriber = None
        self.right_arm_subscriber = None
        self.ros_client = None

        # Run disconnect in background thread to avoid GUI freeze
        def do_disconnect():
            if left_sub:
                try:
                    left_sub.unsubscribe()
                except:
                    pass
            if right_sub:
                try:
                    right_sub.unsubscribe()
                except:
                    pass
            if client:
                try:
                    if client.is_connected:
                        client.close()
                except Exception as e:
                    logger.debug(f"Warning during disconnect: {e}")

        threading.Thread(target=do_disconnect, daemon=True).start()

    def _subscribe_to_topics(self):
        """Subscribe to master arm joint topics"""
        if not self.ros_client or not self.ros_connected:
            return

        msg_type = 'sensor_msgs/msg/JointState'
        self._log(f"Using message type: {msg_type}")

        self.left_arm_subscriber = roslibpy.Topic(
            self.ros_client,
            '/left_arm_joint_control',
            msg_type,
            queue_size=1,
            throttle_rate=20
        )
        self.left_arm_subscriber.subscribe(self._on_left_arm_data)
        self._log("Subscribed to /left_arm_joint_control")

        self.right_arm_subscriber = roslibpy.Topic(
            self.ros_client,
            '/right_arm_joint_control',
            msg_type,
            queue_size=1,
            throttle_rate=20
        )
        self.right_arm_subscriber.subscribe(self._on_right_arm_data)
        self._log("Subscribed to /right_arm_joint_control")

        QTimer.singleShot(5000, self._check_data_received)

    def _check_data_received(self):
        """Check if any data has been received after subscription"""
        if not self.ros_connected:
            return
        if not self._first_data_received['left'] and not self._first_data_received['right']:
            self._log("WARNING: No data received from master arm after 5 seconds!")
            self._log("Please verify:")
            self._log("  1. Master arm is connected and powered on")
            self._log("  2. LinkerTA driver is running in Docker")
            self._log("  3. Move the master arm to generate data")

    # ==================== Data Callbacks ====================

    def _on_left_arm_data(self, message):
        """Callback for left arm joint data from master"""
        try:
            self._message_count['left'] += 1

            data = message.get('position', [])
            if len(data) >= 7:
                if not self._first_data_received['left']:
                    self._first_data_received['left'] = True
                    self._log(f"First left arm data received: {len(data)} joints")

                joints = list(data[:7])

                if self.convert_deg_to_rad_cb.isChecked():
                    joints = [j * math.pi / 180.0 for j in joints]

                if self.apply_negation_cb.isChecked():
                    joints = [joints[i] * self.joint_negation['left'][i] for i in range(7)]

                self.master_left_joints = joints

                # Update UI - individual joint labels
                display_vals = list(data[:7]) if self.convert_deg_to_rad_cb.isChecked() else [j * 180.0 / math.pi for j in joints]
                # Capture current red highlight state for closure
                red_flags = list(self._joints_highlight_red['left'])

                def update_labels():
                    try:
                        for i, val in enumerate(display_vals):
                            color = "red" if red_flags[i] else "blue"
                            self.left_master_joint_labels[i].setText(f"{val:.1f}")
                            self.left_master_joint_labels[i].setStyleSheet(f"color: {color};")
                    except:
                        pass
                self._run_on_gui(update_labels)

                # Send to follower if active
                if self.teleop_active and self.teleop_left_enabled:
                    self._send_to_follower('left', joints)

        except Exception as e:
            self._log(f"Error processing left arm data: {e}")

    def _on_right_arm_data(self, message):
        """Callback for right arm joint data from master"""
        try:
            self._message_count['right'] += 1

            data = message.get('position', [])
            if len(data) >= 7:
                if not self._first_data_received['right']:
                    self._first_data_received['right'] = True
                    self._log(f"First right arm data received: {len(data)} joints")

                joints = list(data[:7])

                if self.convert_deg_to_rad_cb.isChecked():
                    joints = [j * math.pi / 180.0 for j in joints]

                # Always apply negation for right arm J1, J3
                joints[1] = -joints[1]
                joints[3] = -joints[3]

                self.master_right_joints = joints

                # Update UI - individual joint labels
                display_vals = list(data[:7]) if self.convert_deg_to_rad_cb.isChecked() else [j * 180.0 / math.pi for j in joints]
                # Capture current red highlight state for closure
                red_flags = list(self._joints_highlight_red['right'])

                def update_labels():
                    try:
                        for i, val in enumerate(display_vals):
                            color = "red" if red_flags[i] else "blue"
                            self.right_master_joint_labels[i].setText(f"{val:.1f}")
                            self.right_master_joint_labels[i].setStyleSheet(f"color: {color};")
                    except:
                        pass
                self._run_on_gui(update_labels)

                # Send to follower if active
                if self.teleop_active and self.teleop_right_enabled:
                    self._send_to_follower('right', joints)

        except Exception as e:
            self._log(f"Error processing right arm data: {e}")

    def _send_to_follower(self, arm: str, joints: List[float]):
        """Send joint positions to follower arm with speed limiting"""
        current_time = time.time()

        if current_time - self.last_send_time[arm] < self.send_interval:
            return

        dt = current_time - self.last_send_time[arm] if self.last_send_time[arm] > 0 else self.send_interval
        self.last_send_time[arm] = current_time

        try:
            if self.dual_arm and self.dual_arm.is_ready():
                # Apply joint offsets
                target_joints = [joints[i] + self.joint_offsets[arm][i] for i in range(7)]

                max_speed = float(self.teleop_speed_entry.text() or "0.5")
                smoothing = max(0.1, min(1.0, float(self.teleop_smoothing_entry.text() or "0.3")))

                # Initialize smoothed joints if needed
                if self.smoothed_joints[arm] is None:
                    if arm == 'left':
                        current_joints = self.dual_arm.get_left_joints()
                    else:
                        current_joints = self.dual_arm.get_right_joints()

                    if current_joints:
                        self.smoothed_joints[arm] = list(current_joints)
                    else:
                        self.smoothed_joints[arm] = target_joints.copy()

                # Apply exponential smoothing
                smoothed = self.smoothed_joints[arm]
                for i in range(7):
                    delta = target_joints[i] - smoothed[i]
                    max_delta = max_speed * dt
                    if abs(delta) > max_delta:
                        delta = max_delta if delta > 0 else -max_delta
                    smoothed[i] += delta * smoothing

                self.smoothed_joints[arm] = smoothed

                # Send to robot using joint_follow
                self.dual_arm.joint_follow(arm, smoothed)

                self.last_sent_joints[arm] = smoothed.copy()

                # Debug output
                if self.debug_teleop_cb.isChecked():
                    smoothed_deg = [s * 180.0 / math.pi for s in smoothed]
                    self._log(f"[{arm}] Sent(deg): {[f'{d:.1f}' for d in smoothed_deg]}")

                # Record if active
                if self.is_recording:
                    if (arm == 'left' and self.record_left_cb.isChecked()) or \
                       (arm == 'right' and self.record_right_cb.isChecked()):
                        self.recording_data[arm].append({
                            'timestamp': current_time - self.recording_start_time,
                            'joints': smoothed.copy()
                        })

        except Exception as e:
            self._log(f"Error sending to follower {arm}: {e}")

    # ==================== Follower Position Display ====================

    def _start_follower_updates(self):
        """Start automatic follower position updates"""
        if self._follower_timer is None:
            self._follower_timer = QTimer(self)
            self._follower_timer.timeout.connect(self._update_follower_positions)
            self._follower_timer.start(200)
            self._log("Started follower position updates")

    def _stop_follower_updates(self):
        """Stop automatic follower position updates"""
        if self._follower_timer is not None:
            self._follower_timer.stop()
            self._follower_timer = None

    def _update_follower_positions(self):
        """Update follower arm position display"""
        try:
            if self.dual_arm and self.dual_arm.is_ready():
                # Get follower positions
                left_joints = self.dual_arm.get_left_joints()
                right_joints = self.dual_arm.get_right_joints()

                # Format and display left follower - individual joint labels
                if left_joints and len(left_joints) >= 7:
                    joints_deg = [j * 180.0 / math.pi for j in left_joints]
                    for i, val in enumerate(joints_deg):
                        self.left_follower_joint_labels[i].setText(f"{val:.1f}")
                        self.left_follower_joint_labels[i].setStyleSheet("color: green;")

                    # Calculate difference if master data exists
                    if self.master_left_joints:
                        self._update_diff_indicator('left', self.master_left_joints, left_joints)
                    else:
                        self.left_diff_label.setText("No master data")
                        self.left_diff_label.setStyleSheet("color: gray;")
                        # Reset joint colors to default when no master data
                        for lbl in self.left_master_joint_labels:
                            lbl.setStyleSheet("color: gray;")
                        for lbl in self.left_follower_joint_labels:
                            lbl.setStyleSheet("color: green;")

                # Format and display right follower - individual joint labels
                if right_joints and len(right_joints) >= 7:
                    joints_deg = [j * 180.0 / math.pi for j in right_joints]
                    for i, val in enumerate(joints_deg):
                        self.right_follower_joint_labels[i].setText(f"{val:.1f}")
                        self.right_follower_joint_labels[i].setStyleSheet("color: green;")

                    # Calculate difference if master data exists
                    if self.master_right_joints:
                        self._update_diff_indicator('right', self.master_right_joints, right_joints)
                    else:
                        self.right_diff_label.setText("No master data")
                        self.right_diff_label.setStyleSheet("color: gray;")
                        # Reset joint colors to default when no master data
                        for lbl in self.right_master_joint_labels:
                            lbl.setStyleSheet("color: gray;")
                        for lbl in self.right_follower_joint_labels:
                            lbl.setStyleSheet("color: green;")
            else:
                # Robot not ready - show message in first label, clear others
                self.left_follower_joint_labels[0].setText("Robot")
                self.left_follower_joint_labels[0].setStyleSheet("color: gray;")
                self.left_follower_joint_labels[1].setText("not")
                self.left_follower_joint_labels[1].setStyleSheet("color: gray;")
                self.left_follower_joint_labels[2].setText("ready")
                self.left_follower_joint_labels[2].setStyleSheet("color: gray;")
                for i in range(3, 7):
                    self.left_follower_joint_labels[i].setText("--")
                    self.left_follower_joint_labels[i].setStyleSheet("color: gray;")

                self.right_follower_joint_labels[0].setText("Robot")
                self.right_follower_joint_labels[0].setStyleSheet("color: gray;")
                self.right_follower_joint_labels[1].setText("not")
                self.right_follower_joint_labels[1].setStyleSheet("color: gray;")
                self.right_follower_joint_labels[2].setText("ready")
                self.right_follower_joint_labels[2].setStyleSheet("color: gray;")
                for i in range(3, 7):
                    self.right_follower_joint_labels[i].setText("--")
                    self.right_follower_joint_labels[i].setStyleSheet("color: gray;")

                self.left_diff_label.setText("--")
                self.left_diff_label.setStyleSheet("color: gray;")
                self.right_diff_label.setText("--")
                self.right_diff_label.setStyleSheet("color: gray;")

        except Exception as e:
            self._log(f"Error updating follower positions: {e}")

    def _update_diff_indicator(self, arm: str, master: List[float], follower: List[float]):
        """Update position difference indicator with color coding and per-joint highlighting"""
        try:
            # Get the appropriate labels
            if arm == 'left':
                master_labels = self.left_master_joint_labels
                follower_labels = self.left_follower_joint_labels
                diff_label = self.left_diff_label
            else:
                master_labels = self.right_master_joint_labels
                follower_labels = self.right_follower_joint_labels
                diff_label = self.right_diff_label

            # Calculate difference for each joint (in degrees)
            num_joints = min(7, len(master), len(follower))
            diffs_deg = []
            for i in range(num_joints):
                diff_rad = abs(master[i] - follower[i])
                diff_deg = diff_rad * 180.0 / math.pi
                diffs_deg.append(diff_deg)

            # Find max difference and which joint
            max_diff_deg = max(diffs_deg) if diffs_deg else 0
            max_joint_idx = diffs_deg.index(max_diff_deg) if diffs_deg else 0

            # Color individual joints: red if diff > 10 degrees, else normal color
            # Also store the red state so master arm callbacks can use it
            for i in range(num_joints):
                if diffs_deg[i] > 10:
                    # Mark this joint as needing red highlight
                    self._joints_highlight_red[arm][i] = True
                    # Highlight both master and follower joint in red
                    master_labels[i].setStyleSheet("color: red;")
                    follower_labels[i].setStyleSheet("color: red;")
                else:
                    # Mark this joint as normal
                    self._joints_highlight_red[arm][i] = False
                    # Normal colors: blue for master, green for follower
                    master_labels[i].setStyleSheet("color: blue;")
                    follower_labels[i].setStyleSheet("color: green;")

            # Overall status color coding
            if max_diff_deg < 5:
                color = "green"
                status = f"OK ({max_diff_deg:.1f}\u00b0)"
            elif max_diff_deg < 15:
                color = "orange"
                status = f"Max: J{max_joint_idx + 1} ({max_diff_deg:.1f}\u00b0)"
            else:
                color = "red"
                status = f"Max: J{max_joint_idx + 1} ({max_diff_deg:.1f}\u00b0)"

            diff_label.setText(status)
            diff_label.setStyleSheet(f"color: {color};")

        except Exception as e:
            self._log(f"Error updating diff indicator: {e}")

    # ==================== Calibration ====================

    def _calibrate_offsets(self):
        """Calibrate joint offsets"""
        if not self.dual_arm or not self.dual_arm.is_ready():
            QMessageBox.warning(self, "Warning", t("master_teleop.robot_not_connected"))
            return

        if not self.ros_connected:
            QMessageBox.warning(self, "Warning", t("master_teleop.ros_not_connected"))
            return

        if self.master_left_joints is None and self.master_right_joints is None:
            QMessageBox.warning(self, "Warning", t("master_teleop.no_master_data"))
            return

        calibrated = []

        if self.master_left_joints is not None:
            robot_joints = self.dual_arm.get_left_joints()
            if robot_joints:
                self.joint_offsets['left'] = [robot_joints[i] - self.master_left_joints[i] for i in range(7)]
                calibrated.append("Left")
                self._log(f"Left arm offsets: {[f'{o:.3f}' for o in self.joint_offsets['left']]}")

        if self.master_right_joints is not None:
            robot_joints = self.dual_arm.get_right_joints()
            if robot_joints:
                self.joint_offsets['right'] = [robot_joints[i] - self.master_right_joints[i] for i in range(7)]
                calibrated.append("Right")
                self._log(f"Right arm offsets: {[f'{o:.3f}' for o in self.joint_offsets['right']]}")

        if calibrated:
            self.offsets_calibrated = True
            self.calibration_status.setText(
                f"{t('master_teleop.calibrated')}: {', '.join(calibrated)}"
            )
            self.calibration_status.setStyleSheet("color: green;")
            self.smoothed_joints = {'left': None, 'right': None}
            QMessageBox.information(
                self,
                t("master_teleop.calibration"),
                f"{t('master_teleop.calibrated')}: {', '.join(calibrated)}"
            )
        else:
            QMessageBox.critical(self, "Error", t("master_teleop.calibration_failed"))

    # ==================== Teleop Control ====================

    def _on_teleop_left_changed(self):
        self.teleop_left_enabled = self.teleop_left_cb.isChecked()

    def _on_teleop_right_changed(self):
        self.teleop_right_enabled = self.teleop_right_cb.isChecked()

    def _toggle_teleop(self):
        if self.teleop_active:
            self._stop_teleop()
        else:
            self._start_teleop()

    def _start_teleop(self):
        if not self.ros_connected:
            QMessageBox.warning(self, "Warning", t("master_teleop.ros_not_connected"))
            return

        if not self.dual_arm or not self.dual_arm.is_ready():
            QMessageBox.warning(self, "Warning", t("master_teleop.robot_not_connected"))
            return

        if not self.teleop_left_cb.isChecked() and not self.teleop_right_cb.isChecked():
            QMessageBox.warning(self, "Warning", t("master_teleop.select_arm"))
            return

        self.teleop_active = True
        self.teleop_left_enabled = self.teleop_left_cb.isChecked()
        self.teleop_right_enabled = self.teleop_right_cb.isChecked()

        self.teleop_btn.setText(t("master_teleop.stop"))
        self.teleop_btn.setStyleSheet("background-color: #FF4D4F; color: white;")
        self.teleop_status_label.setText(t("common.active"))
        self.teleop_status_label.setStyleSheet("color: green;")

        arms = []
        if self.teleop_left_enabled:
            arms.append("Left")
        if self.teleop_right_enabled:
            arms.append("Right")
        self._log(f"Teleoperation started: {', '.join(arms)}")

    def _stop_teleop(self):
        self.teleop_active = False
        self.teleop_btn.setText(t("master_teleop.start"))
        self.teleop_btn.setStyleSheet("background-color: #52C41A; color: white;")
        self.teleop_status_label.setText(t("common.stopped"))
        self.teleop_status_label.setStyleSheet("color: gray;")
        self.smoothed_joints = {'left': None, 'right': None}
        self._log("Teleoperation stopped")

    # ==================== Recording ====================

    def _toggle_recording(self):
        if self.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        if not self.teleop_active:
            QMessageBox.warning(self, "Warning", t("master_teleop.start_teleop_first"))
            return

        self.is_recording = True
        self.recording_data = {'left': [], 'right': []}
        self.recording_start_time = time.time()

        self.record_btn.setText(t("master_teleop.stop_recording"))
        self.record_btn.setStyleSheet("background-color: #52C41A; color: white;")
        self.record_status_label.setText(t("master_teleop.recording"))
        self.record_status_label.setStyleSheet("color: red;")

        self._log("Trajectory recording started")

        # Start recording status timer
        self._recording_timer = QTimer(self)
        self._recording_timer.timeout.connect(self._update_recording_status)
        self._recording_timer.start(200)

    def _update_recording_status(self):
        if self.is_recording:
            elapsed = time.time() - self.recording_start_time
            left_pts = len(self.recording_data['left'])
            right_pts = len(self.recording_data['right'])
            self.record_status_label.setText(
                f"{t('master_teleop.recording')}: {elapsed:.1f}s (L:{left_pts} R:{right_pts})"
            )
            self.record_status_label.setStyleSheet("color: red;")

    def _stop_recording(self):
        if not self.is_recording:
            return

        self.is_recording = False

        # Stop recording timer
        if self._recording_timer is not None:
            self._recording_timer.stop()
            self._recording_timer = None

        self.record_btn.setText(t("master_teleop.start_recording"))
        self.record_btn.setStyleSheet("background-color: #FF4D4F; color: white;")

        duration = time.time() - self.recording_start_time
        left_pts = len(self.recording_data['left'])
        right_pts = len(self.recording_data['right'])

        self._log(f"Recording stopped: {duration:.1f}s, Left:{left_pts}pts, Right:{right_pts}pts")

        if left_pts < 10 and right_pts < 10:
            self.record_status_label.setText(t("master_teleop.too_short"))
            self.record_status_label.setStyleSheet("color: orange;")
            QMessageBox.warning(self, "Warning", t("master_teleop.recording_too_short"))
            return

        traj_name = self.traj_name_entry.text().strip() or "teleop_traj"
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

        saved_files = []

        if left_pts >= 10 and self.record_left_cb.isChecked():
            filename = f"{traj_name}_left_{timestamp_str}.json"
            filepath = os.path.join(self.trajectory_directory, filename)
            self._save_trajectory_file(filepath, 'left', self.recording_data['left'], duration)
            saved_files.append(filename)

        if right_pts >= 10 and self.record_right_cb.isChecked():
            filename = f"{traj_name}_right_{timestamp_str}.json"
            filepath = os.path.join(self.trajectory_directory, filename)
            self._save_trajectory_file(filepath, 'right', self.recording_data['right'], duration)
            saved_files.append(filename)

        if saved_files:
            self.record_status_label.setText(
                f"{t('master_teleop.saved')}: {len(saved_files)}"
            )
            self.record_status_label.setStyleSheet("color: green;")
            self._increment_traj_name()
        else:
            self.record_status_label.setText(t("master_teleop.nothing_saved"))
            self.record_status_label.setStyleSheet("color: orange;")

    def _save_trajectory_file(self, filepath: str, arm: str, data: List[dict], duration: float):
        sample_rate = int(self.sample_rate_combo.currentText())
        traj_data = {
            'version': '1.0',
            'source': 'master_arm_teleoperation',
            'arm': arm,
            'duration': round(duration, 2),
            'points': len(data),
            'sample_rate': sample_rate,
            'created': datetime.now().isoformat(),
            'data': data
        }

        try:
            with open(filepath, 'w') as f:
                json.dump(traj_data, f, indent=2)
            self._log(f"Saved trajectory: {filepath}")
        except Exception as e:
            self._log(f"Error saving trajectory: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save trajectory: {e}")

    def _increment_traj_name(self):
        name = self.traj_name_entry.text()
        match = re.match(r'^(.+?)(\d+)$', name)
        if match:
            prefix = match.group(1)
            num = int(match.group(2)) + 1
            self.traj_name_entry.setText(f"{prefix}{num}")
        else:
            self.traj_name_entry.setText(f"{name}_2")

    # ==================== Cleanup ====================

    def cleanup(self):
        """Cleanup resources including Docker"""
        # Stop follower position updates
        self._stop_follower_updates()

        # Stop recording timer
        if self._recording_timer is not None:
            self._recording_timer.stop()
            self._recording_timer = None

        # Stop teleop if running
        if self.teleop_active:
            self._stop_teleop()

        # Disconnect ROS
        if self.ros_connected:
            self._disconnect_ros()

        # Stop Docker synchronously on cleanup
        if self._docker_running:
            self._log("Stopping Docker on cleanup...")
            try:
                subprocess.run(
                    ["docker", "compose", "down"],
                    cwd=self._docker_dir,
                    capture_output=True,
                    timeout=10
                )
                self._log("Docker stopped on cleanup")
            except Exception as e:
                self._log(f"Docker cleanup error: {e}")

            if self._docker_process:
                try:
                    self._docker_process.terminate()
                except Exception:
                    pass
                self._docker_process = None

            self._docker_running = False
            self._log("Docker stopped on cleanup")

    def update_language(self):
        """Update text for language change"""
        # Update GroupBox titles
        self.docker_frame.setTitle(t("master_teleop.docker_control"))
        self.ros_frame.setTitle(t("master_teleop.ros_connection"))
        self.teleop_frame.setTitle(t("master_teleop.control"))
        self.motion_frame.setTitle(t("master_teleop.motion_settings"))
        self.record_frame.setTitle(t("master_teleop.trajectory_recording"))
        self.status_frame.setTitle(t("master_teleop.status"))
        self.left_section_frame.setTitle(t("master_teleop.left_arm"))
        self.right_section_frame.setTitle(t("master_teleop.right_arm"))

        # Update Docker section
        if self._docker_running:
            self.docker_btn.setText(t("master_teleop.stop_docker"))
            self.docker_status_label.setText(t("master_teleop.docker_running"))
        elif self._docker_starting:
            self.docker_status_label.setText(t("master_teleop.docker_starting"))
        else:
            self.docker_btn.setText(t("master_teleop.start_docker"))
            self.docker_status_label.setText(t("master_teleop.docker_stopped"))

        # Update ROS section
        if self.ros_connected:
            self.ros_connect_btn.setText(t("common.disconnect"))
            self.ros_status_label.setText(t("common.connected"))
        elif not ROSLIBPY_AVAILABLE:
            self.ros_status_label.setText(t("master_teleop.roslibpy_not_installed"))
        else:
            self.ros_connect_btn.setText(t("common.connect"))
            self.ros_status_label.setText(t("common.disconnected"))

        # Update teleop checkboxes
        self.teleop_left_cb.setText(t("master_teleop.left_arm"))
        self.teleop_right_cb.setText(t("master_teleop.right_arm"))

        # Update teleop section
        if self.teleop_active:
            self.teleop_btn.setText(t("master_teleop.stop"))
            self.teleop_status_label.setText(t("common.active"))
        else:
            self.teleop_btn.setText(t("master_teleop.start"))
            self.teleop_status_label.setText(t("common.stopped"))

        # Update calibration button and status
        self.calibrate_btn.setText(t("master_teleop.calibrate"))
        if self.offsets_calibrated:
            self.calibration_status.setText(t("master_teleop.calibrated"))
        else:
            self.calibration_status.setText(t("master_teleop.not_calibrated"))

        # Update recording section
        if self.is_recording:
            self.record_btn.setText(t("master_teleop.stop_recording"))
        else:
            self.record_btn.setText(t("master_teleop.start_recording"))
            if not self.is_recording:
                self.record_status_label.setText(t("common.ready"))

    # ==================== Public API for VLA Recording ====================

    def is_ros_connected(self) -> bool:
        """Check if ROS is connected (public API for VLA recording)"""
        return self.ros_connected

    def is_docker_running(self) -> bool:
        """Check if Docker is running (public API for VLA recording)"""
        return self._docker_running

    def start_teleop_for_arms(self, arms: List[str]):
        """
        Start teleoperation for specified arms (called by VLA Recording widget).

        Args:
            arms: List of arm names, e.g., ['left'], ['right'], or ['left', 'right']
        """
        if not self.ros_connected:
            self._log("Cannot start teleop: ROS not connected")
            return False

        if not self.dual_arm or not self.dual_arm.is_ready():
            self._log("Cannot start teleop: Robot not ready")
            return False

        # Set which arms to enable
        self.teleop_left_enabled = 'left' in arms
        self.teleop_right_enabled = 'right' in arms

        # Update checkboxes to reflect state
        self.teleop_left_cb.setChecked(self.teleop_left_enabled)
        self.teleop_right_cb.setChecked(self.teleop_right_enabled)

        # Start teleop
        self.teleop_active = True
        self.teleop_btn.setText(t("master_teleop.stop"))
        self.teleop_btn.setStyleSheet("background-color: #FF4D4F; color: white;")
        self.teleop_status_label.setText(t("common.active"))
        self.teleop_status_label.setStyleSheet("color: green;")

        self._log(f"Teleoperation started for arms: {arms}")
        return True

    def stop_teleop_external(self):
        """Stop teleoperation (called by VLA Recording widget)"""
        self._stop_teleop()

    def get_arm_joint_positions(self, arm: str) -> Optional[List[float]]:
        """
        Get current joint positions for an arm.

        Args:
            arm: 'left' or 'right'

        Returns:
            List of 7 joint positions in radians, or None if not available
        """
        if not self.dual_arm or not self.dual_arm.is_ready():
            return None

        try:
            if arm == 'left':
                return self.dual_arm.get_left_joints()
            elif arm == 'right':
                return self.dual_arm.get_right_joints()
            else:
                return None
        except Exception as e:
            self._log(f"Error getting {arm} arm positions: {e}")
            return None

    def are_arms_at_zero(self, arms: List[str], tolerance: float = 0.05) -> bool:
        """
        Check if specified arms are at all-joints-zero position.

        Args:
            arms: List of arm names, e.g., ['left'], ['right'], or ['left', 'right']
            tolerance: Maximum allowed deviation from zero in radians (default 0.05 rad ~ 3 degrees)

        Returns:
            True if all specified arms are at zero position within tolerance
        """
        for arm in arms:
            joints = self.get_arm_joint_positions(arm)
            if joints is None:
                return False

            for joint_val in joints:
                if abs(joint_val) > tolerance:
                    return False

        return True

    def move_to_zero_position(self, arms: List[str], speed: float = 0.5,
                               on_complete: Optional[Callable[[], None]] = None):
        """
        Move specified arms to all-joints-zero position.

        Args:
            arms: List of arm names, e.g., ['left'], ['right'], or ['left', 'right']
            speed: Movement speed in rad/s (default 0.5 for safety)
            on_complete: Optional callback when movement complete
        """
        if not self.dual_arm or not self.dual_arm.is_ready():
            self._log("Cannot move to zero: Robot not ready")
            if on_complete:
                on_complete()
            return

        self._log(f"Moving arms {arms} to zero position at {speed} rad/s...")

        # Target: all joints at zero
        zero_joints = [0.0] * 7

        # Track completion
        self._move_to_zero_arms = list(arms)
        self._move_to_zero_callback = on_complete
        self._move_to_zero_speed = speed

        # Start movement for each arm
        for arm in arms:
            try:
                if arm == 'left':
                    self.dual_arm.move_left_joints(zero_joints, speed=speed)
                elif arm == 'right':
                    self.dual_arm.move_right_joints(zero_joints, speed=speed)
            except Exception as e:
                self._log(f"Error starting move to zero for {arm}: {e}")

        # Start timer to check completion
        self._move_to_zero_timer = QTimer(self)
        self._move_to_zero_timer.timeout.connect(self._check_move_to_zero_complete)
        self._move_to_zero_timer.start(100)  # Check every 100ms

    def _check_move_to_zero_complete(self):
        """Check if move-to-zero is complete"""
        try:
            # Check if all arms are at zero position
            if self.are_arms_at_zero(self._move_to_zero_arms, tolerance=0.05):
                self._log("Arms reached zero position")

                # Stop timer
                if self._move_to_zero_timer:
                    self._move_to_zero_timer.stop()
                    self._move_to_zero_timer = None

                # Call completion callback
                if self._move_to_zero_callback:
                    self._move_to_zero_callback()
                    self._move_to_zero_callback = None

        except Exception as e:
            self._log(f"Error checking move-to-zero completion: {e}")
