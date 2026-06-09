"""
VLA Recording Widget Module - LeRobot Streaming Format
VLA数据录制部件模块 - LeRobot流式格式

GUI Panel for VLA (Vision-Language-Action) Data Recording.
For training Pi0 and other VLA models.
Supports single-arm (left/right) or dual-arm (both) recording.

Integrated with teleoperation and gripper control:
- Automatic teleop start/stop with recording
- Right-click mouse gripper control during recording
- Automatic return-to-zero after recording

VLA（视觉-语言-动作）数据录制的GUI面板。
用于训练Pi0和其他VLA模型。
支持单臂（左/右）或双臂（both）录制。
"""

from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
import time
import os
import subprocess
import sys

from gui.qt_imports import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QPushButton,
    QLineEdit, QComboBox, QListWidget, QListWidgetItem, QMessageBox,
    QFont, QImage, QPixmap, QTimer, QSizePolicy, Qt, QRadioButton,
    QButtonGroup, QDialog, QDialogButtonBox, QFrame,
)
from gui.signals import get_thread_bridge

from config.i18n import t, get_i18n
from app_core.logger import get_logger

from .vla_recording import VLARecordingManager, VLAStep, VLAEpisode, RecordingState

logger = get_logger(__name__)

# Check for cv2
CV2_AVAILABLE = False
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    logger.warning("cv2 not available")

import numpy as np


def _numpy_to_qpixmap(rgb_array, width, height):
    """Convert a numpy RGB array to a QPixmap scaled to (width, height)."""
    if rgb_array is None:
        return None
    try:
        h, w, ch = rgb_array.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb_array.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimg).scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
    except Exception:
        return None


class VLARecordingWidget(QWidget):
    """
    GUI Panel for VLA Data Recording with integrated teleop and gripper control.
    支持集成遥操作和夹爪控制的VLA数据录制GUI面板。
    """

    # Gripper state cycle: CLOSE(0) -> OPEN(100) -> GRAB(60) -> OPEN(100) -> CLOSE(0) -> repeat
    GRIPPER_CYCLE = [0, 100, 60, 100]  # Position values
    GRIPPER_LABELS = ["CLOSE", "OPEN", "GRAB", "OPEN"]
    GRIPPER_TORQUE = 100  # Fixed torque
    GRIPPER_DEBOUNCE_MS = 2000  # 2 second debounce

    def __init__(self, parent, vla_manager: VLARecordingManager,
                 log_callback: Optional[Callable] = None, **kwargs):
        super().__init__(parent)
        self.vla_manager = vla_manager
        self.log_callback = log_callback

        # Hardware references
        self._camera_panel = None
        self._robot_controller = None
        self._teleop_controller = None
        self._teleop_widget = None  # MasterArmTeleopWidget reference
        self._left_hand_panel = None
        self._right_hand_panel = None
        self._gripper_controller = None

        # State tracking
        self.recording_start_time = None
        self.current_step_count = 0

        # Arm selection state
        self._selected_arms: List[str] = ['left', 'right']  # Default: both
        self._is_initialized = False  # Whether arms have been moved to zero
        self._initialization_shown = False  # Track if init dialog was shown this session

        # Gripper state machine
        self._gripper_cycle_index = 0  # Current position in cycle
        self._gripper_last_click_time = 0  # For debounce
        self._recording_active = False  # Track if recording is active for mouse events

        # Teleop integration state
        self._teleop_started = False
        self._teleop_delay_timer = None
        self._return_to_zero_in_progress = False

        # Cache for hand states
        self._left_hand_cache = None
        self._right_hand_cache = None

        # Preview images (prevent GC)
        self._preview_pixmap = None
        self._preview_pixmap2 = None

        # Thread bridge for safe GUI updates from background threads
        self._bridge = get_thread_bridge()

        # Set step callback
        self.vla_manager.add_step_callback(self._on_step_recorded)

        # Set camera source
        self.vla_manager.set_camera_source(self._get_camera_frames)

        self._create_widgets()

        # Install application-wide event filter for right-click
        from PySide6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)

    def _log(self, message):
        if self.log_callback:
            self.log_callback(message)
        logger.info(f"[VLA] {message}")

    # --- Hardware Setup ---

    def set_camera_panel(self, camera_panel):
        """Set camera panel for frame access."""
        self._camera_panel = camera_panel

    def set_robot_controller(self, dual_arm):
        """Set robot controller for state access."""
        self._robot_controller = dual_arm
        if dual_arm:
            self.vla_manager.set_left_robot_state_source(self._get_left_robot_state)
            self.vla_manager.set_right_robot_state_source(self._get_right_robot_state)
            if hasattr(dual_arm, 'start_state_poller'):
                dual_arm.start_state_poller()

    def set_teleop_controller(self, teleop):
        """Set teleop controller for action access."""
        self._teleop_controller = teleop
        if teleop:
            self.vla_manager.set_teleop_action_source(self._get_teleop_actions)

    def set_teleop_widget(self, teleop_widget):
        """Set MasterArmTeleopWidget reference for teleop control."""
        self._teleop_widget = teleop_widget

    def set_hand_controller(self, hand_ctrl):
        """Set hand controller (LinkerHand or Dexhand)."""
        self._left_hand_panel = hand_ctrl
        self._right_hand_panel = hand_ctrl
        if hand_ctrl:
            self.vla_manager.set_left_hand_state_source(self._get_left_hand_state)
            self.vla_manager.set_right_hand_state_source(self._get_right_hand_state)

    def set_left_hand_panel(self, panel):
        """Set left hand panel for hand state access."""
        self._left_hand_panel = panel
        if panel:
            self.vla_manager.set_left_hand_state_source(self._get_left_hand_state)

    def set_right_hand_panel(self, panel):
        """Set right hand panel for hand state access."""
        self._right_hand_panel = panel
        if panel:
            self.vla_manager.set_right_hand_state_source(self._get_right_hand_state)

    def set_gripper_controller(self, gripper):
        """Set gripper controller (LMG-90, right arm) for state access."""
        self._gripper_controller = gripper
        if gripper:
            self.vla_manager.set_gripper_state_source(self._get_gripper_state)

    # --- Data Source Callbacks ---

    def _get_camera_frames(self) -> Dict:
        """Get camera frames from camera panel (ALWAYS both cameras)"""
        frames = {}
        if self._camera_panel:
            try:
                if hasattr(self._camera_panel, 'get_last_frames'):
                    raw_frames = self._camera_panel.get_last_frames()
                    return raw_frames
            except Exception as e:
                logger.debug(f"Camera frame error: {e}")
        return frames

    def _get_left_robot_state(self) -> Optional[Dict]:
        """Get LEFT arm robot state from DualArmController"""
        if not self._robot_controller:
            return None

        try:
            if hasattr(self._robot_controller, 'get_full_state'):
                state = self._robot_controller.get_full_state('left')
                if state:
                    return state

            if hasattr(self._robot_controller, 'get_full_state_cached'):
                state = self._robot_controller.get_full_state_cached('left')
                if state:
                    return state

            result = {
                'tcp_position': [0.0, 0.0, 0.0],
                'tcp_quaternion': [1.0, 0.0, 0.0, 0.0],
                'joint_positions': [0.0] * 7,
                'joint_velocities': [0.0] * 7,
                'joint_efforts': [0.0] * 7,
            }

            if hasattr(self._robot_controller, 'get_tcp_pose'):
                tcp = self._robot_controller.get_tcp_pose('left')
                if tcp:
                    result['tcp_position'] = tcp.get('position', result['tcp_position'])
                    result['tcp_quaternion'] = tcp.get('quaternion', result['tcp_quaternion'])

            if hasattr(self._robot_controller, 'get_left_joints'):
                joints = self._robot_controller.get_left_joints()
                if joints:
                    result['joint_positions'] = joints

            return result

        except Exception as e:
            logger.debug(f"Left robot state error: {e}")

        return None

    def _get_right_robot_state(self) -> Optional[Dict]:
        """Get RIGHT arm robot state from DualArmController"""
        if not self._robot_controller:
            return None

        try:
            if hasattr(self._robot_controller, 'get_full_state'):
                state = self._robot_controller.get_full_state('right')
                if state:
                    return state

            if hasattr(self._robot_controller, 'get_full_state_cached'):
                state = self._robot_controller.get_full_state_cached('right')
                if state:
                    return state

            result = {
                'tcp_position': [0.0, 0.0, 0.0],
                'tcp_quaternion': [1.0, 0.0, 0.0, 0.0],
                'joint_positions': [0.0] * 7,
                'joint_velocities': [0.0] * 7,
                'joint_efforts': [0.0] * 7,
            }

            if hasattr(self._robot_controller, 'get_tcp_pose'):
                tcp = self._robot_controller.get_tcp_pose('right')
                if tcp:
                    result['tcp_position'] = tcp.get('position', result['tcp_position'])
                    result['tcp_quaternion'] = tcp.get('quaternion', result['tcp_quaternion'])

            if hasattr(self._robot_controller, 'get_right_joints'):
                joints = self._robot_controller.get_right_joints()
                if joints:
                    result['joint_positions'] = joints

            return result

        except Exception as e:
            logger.debug(f"Right robot state error: {e}")

        return None

    def _get_teleop_actions(self) -> Optional[Dict]:
        """Get teleop target actions from teleop controller (both arms)"""
        result = {'timestamp': time.time()}

        if self._teleop_controller:
            try:
                if hasattr(self._teleop_controller, 'get_last_data'):
                    data = self._teleop_controller.get_last_data()
                    if data and data.get('positions'):
                        positions = data.get('positions', [])
                        if len(positions) >= 14:
                            result['left_target_joints'] = positions[:7]
                            result['right_target_joints'] = positions[7:14]
                        elif len(positions) >= 7:
                            result['left_target_joints'] = positions[:7]

                if hasattr(self._teleop_controller, 'master_left_joints'):
                    result['left_target_joints'] = self._teleop_controller.master_left_joints
                if hasattr(self._teleop_controller, 'master_right_joints'):
                    result['right_target_joints'] = self._teleop_controller.master_right_joints

            except Exception as e:
                logger.debug(f"Teleop action error: {e}")

        result['left_hand_command'] = self._get_left_hand_state()
        result['right_hand_command'] = self._get_right_hand_state()

        return result

    def _get_left_hand_state(self) -> List[float]:
        """Get LEFT hand 6 DOF state with caching"""
        current_time = time.time()
        if self._left_hand_cache is not None:
            cache_time, cache_value = self._left_hand_cache
            if current_time - cache_time < 0.020:
                return cache_value

        if self._left_hand_panel:
            try:
                if hasattr(self._left_hand_panel, 'get_finger_positions_real'):
                    positions = self._left_hand_panel.get_finger_positions_real('left')
                    if positions and len(positions) >= 6:
                        result = [float(p) / 255.0 for p in positions[:6]]
                        self._left_hand_cache = (current_time, result)
                        return result

                if hasattr(self._left_hand_panel, 'get_status'):
                    status = self._left_hand_panel.get_status()
                    if status and 'left_finger_positions' in status:
                        positions = status['left_finger_positions']
                        if positions and len(positions) >= 6:
                            result = [float(p) / 255.0 for p in positions[:6]]
                            self._left_hand_cache = (current_time, result)
                            return result

            except Exception as e:
                logger.debug(f"Left hand state error: {e}")

        return [0.0] * 6

    def _get_right_hand_state(self) -> List[float]:
        """Get RIGHT hand 6 DOF state with caching"""
        current_time = time.time()
        if self._right_hand_cache is not None:
            cache_time, cache_value = self._right_hand_cache
            if current_time - cache_time < 0.020:
                return cache_value

        if self._right_hand_panel:
            try:
                if hasattr(self._right_hand_panel, 'get_finger_positions_real'):
                    positions = self._right_hand_panel.get_finger_positions_real('right')
                    if positions and len(positions) >= 6:
                        result = [float(p) / 255.0 for p in positions[:6]]
                        self._right_hand_cache = (current_time, result)
                        return result

                if hasattr(self._right_hand_panel, 'get_status'):
                    status = self._right_hand_panel.get_status()
                    if status and 'right_finger_positions' in status:
                        positions = status['right_finger_positions']
                        if positions and len(positions) >= 6:
                            result = [float(p) / 255.0 for p in positions[:6]]
                            self._right_hand_cache = (current_time, result)
                            return result

            except Exception as e:
                logger.debug(f"Right hand state error: {e}")

        return [0.0] * 6

    def _get_gripper_state(self) -> Optional[Dict]:
        """Get gripper state from GripperController (LMG-90, right arm)."""
        if not self._gripper_controller:
            return None

        try:
            status = self._gripper_controller.get_status()
            if status:
                return {
                    'position': status.get('position', 0),
                    'torque': status.get('torque', 0),
                    'target_opening': status.get('target_opening', 0),
                }
        except Exception as e:
            logger.debug(f"Gripper state error: {e}")

        return None

    # --- Widget Creation ---

    def _create_widgets(self):
        """Create the VLA recording panel widgets"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 5, 10, 5)

        # Connection Status Section
        self._conn_frame = QGroupBox(t("vla.connection_status") if hasattr(t, '__call__') else "Connection Status")
        conn_layout = QHBoxLayout(self._conn_frame)

        self._docker_status = QLabel("Docker: --")
        self._docker_status.setStyleSheet("color: gray;")
        conn_layout.addWidget(self._docker_status)

        self._ros_status = QLabel("ROS: --")
        self._ros_status.setStyleSheet("color: gray;")
        conn_layout.addWidget(self._ros_status)

        self._camera_status = QLabel("Cameras: --")
        self._camera_status.setStyleSheet("color: gray;")
        conn_layout.addWidget(self._camera_status)

        conn_layout.addStretch()
        main_layout.addWidget(self._conn_frame)

        # Configuration Section
        self._config_frame = QGroupBox(t("vla.config_title"))
        config_layout = QVBoxLayout(self._config_frame)

        # Task ID and Language Instruction
        task_row = QHBoxLayout()
        self._task_id_label = QLabel(t("vla.task_id") + ":")
        task_row.addWidget(self._task_id_label)
        self.task_id_entry = QLineEdit("pick_object")
        self.task_id_entry.setMaximumWidth(160)
        task_row.addWidget(self.task_id_entry)

        self._lang_inst_label = QLabel(t("vla.language_inst") + ":")
        task_row.addWidget(self._lang_inst_label)
        self.instruction_entry = QLineEdit("pick up the object")
        task_row.addWidget(self.instruction_entry, 1)
        config_layout.addLayout(task_row)

        # Arm selection (radio buttons instead of dropdown)
        arm_row = QHBoxLayout()
        self._arm_selection_label = QLabel(t("vla.arm_side") + ":")
        arm_row.addWidget(self._arm_selection_label)

        self._arm_button_group = QButtonGroup(self)
        self._left_radio = QRadioButton("Left")
        self._right_radio = QRadioButton("Right")
        self._both_radio = QRadioButton("Both")
        self._both_radio.setChecked(True)  # Default: both

        self._arm_button_group.addButton(self._left_radio, 0)
        self._arm_button_group.addButton(self._right_radio, 1)
        self._arm_button_group.addButton(self._both_radio, 2)

        arm_row.addWidget(self._left_radio)
        arm_row.addWidget(self._right_radio)
        arm_row.addWidget(self._both_radio)

        # Connect arm selection change
        self._arm_button_group.buttonClicked.connect(self._on_arm_selection_changed)

        arm_row.addStretch()
        config_layout.addLayout(arm_row)

        main_layout.addWidget(self._config_frame)

        # Gripper Control Section
        self._gripper_frame = QGroupBox("Gripper Control (Right-click during recording)")
        gripper_layout = QVBoxLayout(self._gripper_frame)

        gripper_row = QHBoxLayout()
        gripper_row.addWidget(QLabel("Current State:"))

        # Gripper state indicators
        self._gripper_indicators = []
        for i, (pos, label) in enumerate(zip(self.GRIPPER_CYCLE, self.GRIPPER_LABELS)):
            indicator = QLabel(f"{label} ({pos})")
            indicator.setFixedWidth(80)
            indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
            indicator.setStyleSheet("border: 1px solid gray; padding: 2px;")
            self._gripper_indicators.append(indicator)
            gripper_row.addWidget(indicator)

        gripper_row.addStretch()

        # Next click label
        self._next_click_label = QLabel("Next click: OPEN (100)")
        self._next_click_label.setStyleSheet("color: blue; font-weight: bold;")
        gripper_row.addWidget(self._next_click_label)

        gripper_layout.addLayout(gripper_row)

        # Torque info
        torque_row = QHBoxLayout()
        torque_row.addWidget(QLabel(f"Torque: {self.GRIPPER_TORQUE} (fixed)"))
        torque_row.addStretch()
        gripper_layout.addLayout(torque_row)

        main_layout.addWidget(self._gripper_frame)

        # Update initial gripper display
        self._update_gripper_display()

        # Recording Controls Section
        self._control_frame = QGroupBox(t("vla.control_title"))
        control_layout = QVBoxLayout(self._control_frame)
        btn_row = QHBoxLayout()

        # Start/Stop button
        self.record_btn = QPushButton(t("vla.start_recording"))
        self.record_btn.clicked.connect(self._toggle_recording)
        self.record_btn.setStyleSheet("background-color: #52C41A; color: white; font-size: 14px; font-weight: bold; padding: 10px 15px;")
        self.record_btn.setMinimumHeight(45)
        btn_row.addWidget(self.record_btn)

        # Discard button (no pause button - removed per requirements)
        self.discard_btn = QPushButton(t("vla.discard"))
        self.discard_btn.clicked.connect(self._discard_episode)
        self.discard_btn.setStyleSheet("background-color: #FF4D4F; color: white; font-size: 13px; font-weight: bold; padding: 8px 12px;")
        self.discard_btn.setMinimumHeight(45)
        self.discard_btn.setEnabled(False)
        btn_row.addWidget(self.discard_btn)

        # New Trial button
        self.new_trial_btn = QPushButton(t("vla.new_trial"))
        self.new_trial_btn.clicked.connect(self._start_new_trial)
        self.new_trial_btn.setStyleSheet("background-color: #1890FF; color: white; font-size: 13px; font-weight: bold; padding: 8px 12px;")
        self.new_trial_btn.setMinimumHeight(45)
        btn_row.addWidget(self.new_trial_btn)

        # Status display
        status_frame_layout = QVBoxLayout()
        self.status_label = QLabel(t("vla.status_idle"))
        self.status_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        status_frame_layout.addWidget(self.status_label)

        self.step_count_label = QLabel(t("vla.steps") + ": 0")
        self.step_count_label.setFont(QFont("Arial", 10))
        status_frame_layout.addWidget(self.step_count_label)

        self.duration_label = QLabel(t("vla.duration") + ": 0.0s")
        self.duration_label.setFont(QFont("Arial", 10))
        status_frame_layout.addWidget(self.duration_label)

        btn_row.addLayout(status_frame_layout, 1)
        control_layout.addLayout(btn_row)
        main_layout.addWidget(self._control_frame)

        # Live Data Preview Section
        self._preview_frame = QGroupBox(t("vla.live_data"))
        preview_layout = QHBoxLayout(self._preview_frame)

        # Left side: State info
        state_layout = QVBoxLayout()
        self._robot_state_label = QLabel(t("vla.robot_state") + ":")
        self._robot_state_label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        state_layout.addWidget(self._robot_state_label)

        from gui.qt_imports import QTextEdit
        self.state_text = QTextEdit()
        self.state_text.setReadOnly(True)
        self.state_text.setMaximumHeight(70)
        self.state_text.setFont(QFont("Courier", 8))
        state_layout.addWidget(self.state_text)

        self._action_label = QLabel(t("vla.action") + ":")
        self._action_label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        state_layout.addWidget(self._action_label)

        self.action_text = QTextEdit()
        self.action_text.setReadOnly(True)
        self.action_text.setMaximumHeight(55)
        self.action_text.setFont(QFont("Courier", 8))
        state_layout.addWidget(self.action_text)

        preview_layout.addLayout(state_layout, 1)

        # Right side: Camera thumbnails
        cam_layout = QVBoxLayout()
        self._cam_preview_label = QLabel(t("vla.camera_preview") + ":")
        self._cam_preview_label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        cam_layout.addWidget(self._cam_preview_label)

        cam_row_layout = QHBoxLayout()

        # Desk camera
        desk_cam_layout = QVBoxLayout()
        self._desk_label = QLabel(t("vla.camera_desk"))
        self._desk_label.setFont(QFont("Arial", 7))
        desk_cam_layout.addWidget(self._desk_label, 0, Qt.AlignmentFlag.AlignCenter)
        self.camera_label = QLabel()
        self.camera_label.setFixedSize(120, 90)
        self.camera_label.setStyleSheet("background-color: black;")
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desk_cam_layout.addWidget(self.camera_label)
        cam_row_layout.addLayout(desk_cam_layout)

        # Wrist camera
        wrist_cam_layout = QVBoxLayout()
        self._wrist_label = QLabel(t("vla.camera_wrist"))
        self._wrist_label.setFont(QFont("Arial", 7))
        wrist_cam_layout.addWidget(self._wrist_label, 0, Qt.AlignmentFlag.AlignCenter)
        self.camera_label2 = QLabel()
        self.camera_label2.setFixedSize(120, 90)
        self.camera_label2.setStyleSheet("background-color: black;")
        self.camera_label2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wrist_cam_layout.addWidget(self.camera_label2)
        cam_row_layout.addLayout(wrist_cam_layout)

        cam_layout.addLayout(cam_row_layout)
        preview_layout.addLayout(cam_layout)
        main_layout.addWidget(self._preview_frame)

        # Episode List Section
        self._list_frame = QGroupBox(t("vla.episode_list"))
        list_layout = QVBoxLayout(self._list_frame)

        # Toolbar
        toolbar_layout = QHBoxLayout()
        self._refresh_btn = QPushButton(t("common.refresh"))
        self._refresh_btn.clicked.connect(self._refresh_episode_list)
        toolbar_layout.addWidget(self._refresh_btn)

        self._delete_btn = QPushButton(t("vla.delete"))
        self._delete_btn.clicked.connect(self._delete_selected)
        toolbar_layout.addWidget(self._delete_btn)

        toolbar_layout.addStretch()

        self._finalize_trial_btn = QPushButton("Finalize Trial")
        self._finalize_trial_btn.clicked.connect(self._finalize_trial)
        self._finalize_trial_btn.setToolTip("Close and finalize the current trial before pushing to hub")
        toolbar_layout.addWidget(self._finalize_trial_btn)

        self._open_folder_btn = QPushButton(t("vla.open_folder"))
        self._open_folder_btn.clicked.connect(self._open_output_folder)
        toolbar_layout.addWidget(self._open_folder_btn)

        list_layout.addLayout(toolbar_layout)

        # Push to Hub row
        hub_layout = QHBoxLayout()
        hub_label = QLabel("HF Repo:")
        hub_label.setFixedWidth(60)
        hub_layout.addWidget(hub_label)

        self._hub_repo_id_entry = QLineEdit()
        self._hub_repo_id_entry.setPlaceholderText("username/dataset-name")
        self._hub_repo_id_entry.setToolTip(
            "Hugging Face repo ID to push to, e.g. myorg/dual-arm-recordings\n"
            "Run 'huggingface-cli login' once to authenticate."
        )
        hub_layout.addWidget(self._hub_repo_id_entry, 1)

        self._hub_private_check = QPushButton("Private")
        self._hub_private_check.setCheckable(True)
        self._hub_private_check.setChecked(True)
        self._hub_private_check.setFixedWidth(65)
        self._hub_private_check.setToolTip("Push as a private dataset")
        hub_layout.addWidget(self._hub_private_check)

        self._push_hub_btn = QPushButton("Push to Hub")
        self._push_hub_btn.clicked.connect(self._push_to_hub)
        self._push_hub_btn.setStyleSheet(
            "background-color: #FF6B35; color: white; font-weight: bold; padding: 4px 10px;"
        )
        self._push_hub_btn.setToolTip(
            "Upload the finalized trial to Hugging Face Hub.\n"
            "Call Finalize Trial first."
        )
        self._push_hub_btn.setEnabled(False)  # enabled only after Finalize Trial
        hub_layout.addWidget(self._push_hub_btn)

        list_layout.addLayout(hub_layout)

        # Episode listbox
        self.episode_listbox = QListWidget()
        self.episode_listbox.setFont(QFont("Courier", 9))
        self.episode_listbox.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.episode_listbox.setMinimumHeight(100)
        list_layout.addWidget(self.episode_listbox)

        main_layout.addWidget(self._list_frame, 1)

        # Initial refresh
        self._refresh_episode_list()

        # Start UI update timer
        self._start_ui_update_timer()

    # --- Arm Selection ---

    def _get_selected_arms(self) -> List[str]:
        """Get currently selected arms as list"""
        if self._left_radio.isChecked():
            return ['left']
        elif self._right_radio.isChecked():
            return ['right']
        else:  # both
            return ['left', 'right']

    def _get_arm_side_string(self) -> str:
        """Get arm side as string for VLA manager"""
        if self._left_radio.isChecked():
            return 'left'
        elif self._right_radio.isChecked():
            return 'right'
        else:
            return 'both'

    def _on_arm_selection_changed(self, button):
        """Handle arm selection change"""
        if self.vla_manager.state != RecordingState.IDLE:
            # Don't allow change during recording
            return

        new_arms = self._get_selected_arms()

        # If already initialized and arms changed, ask to move to zero
        if self._is_initialized and new_arms != self._selected_arms:
            reply = QMessageBox.question(
                self, "Arm Selection Changed",
                "You changed the arm selection.\n\n"
                "Do you want to move the newly selected arm(s) to zero position?\n\n"
                "Make sure the path is clear.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                self._move_arms_to_zero(new_arms)

        self._selected_arms = new_arms

    # --- Initialization ---

    def showEvent(self, event):
        """Called when widget becomes visible (tab switch)"""
        super().showEvent(event)

        # Check connection status
        self._update_connection_status()

        # Always check if initialization is needed (B-modified: show dialog every tab switch,
        # but skip if arms already at zero)
        QTimer.singleShot(100, self._check_initialization_needed)

    def _check_initialization_needed(self):
        """Check if initialization dialog should be shown (B-modified behavior)"""
        # Don't show dialog during active recording
        if self._recording_active:
            return

        # Check if ROS is connected
        ros_connected = self._check_ros_connected()

        if not ros_connected:
            # Just show warning, allow user to proceed anyway (per requirements)
            self._conn_frame.setStyleSheet("background-color: #FFF3CD;")
            self._ros_status.setText("ROS: Not Connected")
            self._ros_status.setStyleSheet("color: red;")
            return

        # B-modified: If arms are already at zero, skip dialog entirely
        arms = self._get_selected_arms()
        if self._check_arms_at_zero(arms):
            self._is_initialized = True
            return

        # Arms not at zero - show initialization dialog
        self._show_initialization_dialog()

    def _show_initialization_dialog(self):
        """Show initialization dialog for arm selection and move to zero"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Initialize VLA Recording")
        dialog.setModal(True)
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        # Instructions
        layout.addWidget(QLabel("Select arm(s) for this recording session:"))

        # Arm selection
        arm_group = QButtonGroup(dialog)
        left_rb = QRadioButton("Left Arm")
        right_rb = QRadioButton("Right Arm")
        both_rb = QRadioButton("Both Arms")
        both_rb.setChecked(True)

        arm_group.addButton(left_rb, 0)
        arm_group.addButton(right_rb, 1)
        arm_group.addButton(both_rb, 2)

        arm_layout = QHBoxLayout()
        arm_layout.addWidget(left_rb)
        arm_layout.addWidget(right_rb)
        arm_layout.addWidget(both_rb)
        layout.addLayout(arm_layout)

        # Warning
        warning_label = QLabel(
            "\nArms will move to zero position.\n"
            "Make sure the path is clear."
        )
        warning_label.setStyleSheet("color: orange; font-weight: bold;")
        layout.addWidget(warning_label)

        # Buttons
        btn_layout = QHBoxLayout()
        skip_btn = QPushButton("Skip")
        init_btn = QPushButton("Initialize")
        init_btn.setStyleSheet("background-color: #52C41A; color: white;")

        btn_layout.addWidget(skip_btn)
        btn_layout.addWidget(init_btn)
        layout.addLayout(btn_layout)

        def on_skip():
            self._initialization_shown = True
            dialog.reject()

        def on_init():
            # Update main arm selection
            if left_rb.isChecked():
                self._left_radio.setChecked(True)
            elif right_rb.isChecked():
                self._right_radio.setChecked(True)
            else:
                self._both_radio.setChecked(True)

            self._selected_arms = self._get_selected_arms()
            self._initialization_shown = True

            # Close dialog first
            dialog.accept()

            # Set gripper to CLOSE
            self._set_gripper_position(0)

            # Move arms to zero
            self._move_arms_to_zero(self._selected_arms)

        skip_btn.clicked.connect(on_skip)
        init_btn.clicked.connect(on_init)

        dialog.exec()

    def _move_arms_to_zero(self, arms: List[str]):
        """Move specified arms to zero position"""
        if not self._teleop_widget:
            self._log("Cannot move to zero: Teleop widget not connected")
            self._is_initialized = True  # Allow recording anyway
            return

        self._log(f"Moving arms {arms} to zero position...")
        self.status_label.setText("Moving to zero...")
        self.status_label.setStyleSheet("color: orange;")
        self.record_btn.setEnabled(False)

        def on_complete():
            self._is_initialized = True
            self._log("Arms at zero position")
            self.status_label.setText(t("vla.status_idle"))
            self.status_label.setStyleSheet("color: gray;")
            self.record_btn.setEnabled(True)

        self._teleop_widget.move_to_zero_position(arms, speed=0.5, on_complete=on_complete)

    def _check_arms_at_zero(self, arms: List[str]) -> bool:
        """Check if arms are at zero position"""
        if not self._teleop_widget:
            return False
        return self._teleop_widget.are_arms_at_zero(arms, tolerance=0.1)

    def _check_ros_connected(self) -> bool:
        """Check if ROS is connected via teleop widget"""
        if self._teleop_widget:
            return self._teleop_widget.is_ros_connected()
        return False

    def _check_docker_running(self) -> bool:
        """Check if Docker is running via teleop widget"""
        if self._teleop_widget:
            return self._teleop_widget.is_docker_running()
        return False

    # --- Connection Status ---

    def _update_connection_status(self):
        """Update connection status display"""
        # Docker status
        docker_ok = self._check_docker_running()
        self._docker_status.setText(f"Docker: {'Running' if docker_ok else 'Stopped'}")
        self._docker_status.setStyleSheet(f"color: {'green' if docker_ok else 'red'};")

        # ROS status
        ros_ok = self._check_ros_connected()
        self._ros_status.setText(f"ROS: {'Connected' if ros_ok else 'Disconnected'}")
        self._ros_status.setStyleSheet(f"color: {'green' if ros_ok else 'red'};")

        # Camera status
        cam1_ok = False
        cam2_ok = False
        if self._camera_panel and hasattr(self._camera_panel, 'get_last_frames'):
            frames = self._camera_panel.get_last_frames()
            cam1_ok = frames and 0 in frames and frames[0] is not None
            cam2_ok = frames and 1 in frames and frames[1] is not None

        cam_count = (1 if cam1_ok else 0) + (1 if cam2_ok else 0)
        self._camera_status.setText(f"Cameras: {cam_count}/2 Ready")
        self._camera_status.setStyleSheet(f"color: {'green' if cam_count == 2 else 'orange' if cam_count == 1 else 'red'};")

    # --- Gripper Control ---

    def eventFilter(self, obj, event):
        """Application-wide event filter for right-click gripper control"""
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QMouseEvent

        if event.type() == QEvent.Type.MouseButtonPress:
            if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.RightButton:
                # Only handle during active recording
                if self._recording_active:
                    self._handle_gripper_click()
                    return True  # Consume event

        return super().eventFilter(obj, event)

    def _handle_gripper_click(self):
        """Handle right-click for gripper control"""
        current_time = time.time() * 1000  # ms

        # Check debounce (2 seconds)
        if current_time - self._gripper_last_click_time < self.GRIPPER_DEBOUNCE_MS:
            # Silently ignore (per requirements)
            return

        self._gripper_last_click_time = current_time

        # Advance to next state in cycle
        self._gripper_cycle_index = (self._gripper_cycle_index + 1) % len(self.GRIPPER_CYCLE)
        new_position = self.GRIPPER_CYCLE[self._gripper_cycle_index]

        # Set gripper position
        self._set_gripper_position(new_position)

        # Update display
        self._update_gripper_display()

        self._log(f"Gripper: {self.GRIPPER_LABELS[self._gripper_cycle_index]} ({new_position})")

    def _set_gripper_position(self, position: int):
        """Set gripper to specified position"""
        if self._gripper_controller:
            try:
                self._gripper_controller.set_position(position, self.GRIPPER_TORQUE)
            except Exception as e:
                logger.warning(f"Gripper set position error: {e}")

    def _update_gripper_display(self):
        """Update gripper state display"""
        for i, indicator in enumerate(self._gripper_indicators):
            if i == self._gripper_cycle_index:
                indicator.setStyleSheet("border: 2px solid green; background-color: #90EE90; padding: 2px; font-weight: bold;")
            else:
                indicator.setStyleSheet("border: 1px solid gray; padding: 2px;")

        # Update next click label
        next_index = (self._gripper_cycle_index + 1) % len(self.GRIPPER_CYCLE)
        next_pos = self.GRIPPER_CYCLE[next_index]
        next_label = self.GRIPPER_LABELS[next_index]
        self._next_click_label.setText(f"Next click: {next_label} ({next_pos})")

    def _reset_gripper_state(self):
        """Reset gripper to initial state (CLOSE)"""
        self._gripper_cycle_index = 0
        self._set_gripper_position(0)  # CLOSE
        self._update_gripper_display()

    # --- Recording Controls ---

    def _toggle_recording(self):
        """Start or stop recording"""
        if self.vla_manager.state == RecordingState.IDLE:
            self._start_recording_sequence()
        else:
            self._stop_recording_sequence()

    def _start_recording_sequence(self):
        """Start recording with integrated teleop start"""
        task_id = self.task_id_entry.text().strip()
        instruction = self.instruction_entry.text().strip()
        arm_side = self._get_arm_side_string()

        if not task_id:
            QMessageBox.warning(self, t("common.error"), t("vla.msg_task_required"))
            return

        if not instruction:
            QMessageBox.warning(self, t("common.error"), t("vla.msg_lang_required"))
            return

        # Check camera availability
        cam1_ok = False
        cam2_ok = False
        if self._camera_panel and hasattr(self._camera_panel, 'get_last_frames'):
            frames = self._camera_panel.get_last_frames()
            cam1_ok = frames and 0 in frames and frames[0] is not None
            cam2_ok = frames and 1 in frames and frames[1] is not None

        if not cam1_ok or not cam2_ok:
            missing = []
            if not cam1_ok:
                missing.append("Desk camera")
            if not cam2_ok:
                missing.append("Wrist camera")

            reply = QMessageBox.question(
                self, "Camera Warning",
                f"The following camera(s) are not available:\n{', '.join(missing)}\n\n"
                "Continue with available camera(s)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Reset gripper to CLOSE
        self._reset_gripper_state()

        # Start VLA recording (arms stationary)
        success = self.vla_manager.start_episode(
            task_id=task_id,
            language_instruction=instruction,
            arm_side=arm_side
        )

        if not success:
            QMessageBox.critical(self, t("common.error"), t("vla.start_failed"))
            return

        self.recording_start_time = time.time()
        self.current_step_count = 0
        self._recording_active = True

        # Update UI
        self.record_btn.setText(t("vla.stop_recording"))
        self.record_btn.setStyleSheet("background-color: #FF4D4F; color: white; font-size: 14px; font-weight: bold; padding: 10px 15px;")
        self.discard_btn.setEnabled(True)
        self.task_id_entry.setEnabled(False)
        self.instruction_entry.setEnabled(False)
        self._left_radio.setEnabled(False)
        self._right_radio.setEnabled(False)
        self._both_radio.setEnabled(False)

        self.status_label.setText("Recording... (starting teleop in 1s)")
        self.status_label.setStyleSheet("color: orange;")

        self._log(f"Started VLA recording: {task_id} - '{instruction}'")

        # Start teleop after 1 second delay
        self._teleop_delay_timer = QTimer(self)
        self._teleop_delay_timer.setSingleShot(True)
        self._teleop_delay_timer.timeout.connect(self._start_teleop_after_delay)
        self._teleop_delay_timer.start(1000)

    def _start_teleop_after_delay(self):
        """Start teleoperation after 1 second delay"""
        if self._teleop_widget:
            arms = self._get_selected_arms()
            success = self._teleop_widget.start_teleop_for_arms(arms)
            if success:
                self._teleop_started = True
                self._log(f"Teleoperation started for arms: {arms}")

        self.status_label.setText(t("vla.status_recording"))
        self.status_label.setStyleSheet("color: green;")

    def _stop_recording_sequence(self):
        """Stop recording with move-to-zero then stop"""
        self._recording_active = False

        # Block UI
        self.record_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self.status_label.setText("Moving to zero position...")
        self.status_label.setStyleSheet("color: orange;")

        self._log("Stopping recording - moving arms to zero...")

        # Move arms to zero FIRST (recording continues)
        arms = self._get_selected_arms()

        if self._teleop_widget:
            self._return_to_zero_in_progress = True
            self._teleop_widget.move_to_zero_position(
                arms,
                speed=0.5,
                on_complete=self._on_return_to_zero_complete
            )
        else:
            # No teleop widget, just stop immediately
            self._finalize_stop_recording()

    def _on_return_to_zero_complete(self):
        """Called when arms reach zero position"""
        self._return_to_zero_in_progress = False
        self._log("Arms at zero position")

        # Now stop recording and teleop simultaneously
        self._finalize_stop_recording()

    def _finalize_stop_recording(self):
        """Finalize stop - called after arms are at zero"""
        # Stop teleop
        if self._teleop_widget and self._teleop_started:
            self._teleop_widget.stop_teleop_external()
            self._teleop_started = False

        # Stop VLA recording
        episode = self.vla_manager.stop_episode()

        if episode:
            self._log(f"Saved episode {episode.episode_num}")
            self._refresh_episode_list()
            # An episode was saved — trial needs finalizing before hub push
            self._finalize_trial_btn.setEnabled(True)
            self._push_hub_btn.setEnabled(False)

        self._reset_recording_ui()

    def _discard_episode(self):
        """Discard current recording with confirmation"""
        # Show confirmation dialog with instructions
        dialog = QDialog(self)
        dialog.setWindowTitle("Discard Recording")
        dialog.setModal(True)
        dialog.setMinimumWidth(450)

        layout = QVBoxLayout(dialog)

        # Warning message
        msg_label = QLabel(
            "Discard current recording?\n\n"
            "Please use the leader arm to guide the follower arm\n"
            "to a position close to all-joints-zero before confirming.\n\n"
            "(Teleoperation remains active)"
        )
        msg_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(msg_label)

        # Buttons
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        confirm_btn = QPushButton("Confirm Discard")
        confirm_btn.setStyleSheet("background-color: #FF4D4F; color: white;")

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(confirm_btn)
        layout.addLayout(btn_layout)

        def on_cancel():
            dialog.reject()

        def on_confirm():
            dialog.accept()
            self._execute_discard()

        cancel_btn.clicked.connect(on_cancel)
        confirm_btn.clicked.connect(on_confirm)

        dialog.exec()

    def _execute_discard(self):
        """Execute discard after confirmation"""
        self._recording_active = False

        # Stop teleop
        if self._teleop_widget and self._teleop_started:
            self._teleop_widget.stop_teleop_external()
            self._teleop_started = False

        # Move to exact zero
        arms = self._get_selected_arms()
        self.status_label.setText("Moving to zero...")
        self.status_label.setStyleSheet("color: orange;")

        def on_zero_complete():
            # Discard the recording
            self.vla_manager.discard_episode()
            self._log("Recording discarded")
            self._reset_recording_ui()

        if self._teleop_widget:
            self._teleop_widget.move_to_zero_position(arms, speed=0.5, on_complete=on_zero_complete)
        else:
            self.vla_manager.discard_episode()
            self._log("Recording discarded")
            self._reset_recording_ui()

    def _start_new_trial(self):
        """Start a new trial folder"""
        if self.vla_manager.state != RecordingState.IDLE:
            QMessageBox.warning(self, t("common.warning"), t("vla.cannot_new_trial_while_recording"))
            return

        trial_name = self.vla_manager.start_new_trial()
        date_str = self.vla_manager._get_date_str()
        self._log(f"Started new trial: {date_str}/{trial_name}")
        QMessageBox.information(self, t("vla.new_trial"), f"{t('vla.new_trial_created')}:\n{date_str}/{trial_name}")
        self._refresh_episode_list()

    def _reset_recording_ui(self):
        """Reset UI after recording stops"""
        self.record_btn.setText(t("vla.start_recording"))
        self.record_btn.setStyleSheet("background-color: #52C41A; color: white; font-size: 14px; font-weight: bold; padding: 10px 15px;")
        self.record_btn.setEnabled(True)
        self.discard_btn.setEnabled(False)
        self.task_id_entry.setEnabled(True)
        self.instruction_entry.setEnabled(True)
        self._left_radio.setEnabled(True)
        self._right_radio.setEnabled(True)
        self._both_radio.setEnabled(True)

        self.status_label.setText(t("vla.status_idle"))
        self.status_label.setStyleSheet("color: gray;")
        self.current_step_count = 0
        self.recording_start_time = None
        self._recording_active = False

        # Reset gripper to CLOSE for next recording
        self._reset_gripper_state()

    # --- Step Callback ---

    def _on_step_recorded(self, step: VLAStep, step_num: int):
        """Callback when a step is recorded"""
        self.current_step_count = step_num

        desk_frame_copy = step.desk_frame.copy() if step.desk_frame is not None else None
        wrist_frame_copy = step.wrist_frame.copy() if step.wrist_frame is not None else None

        try:
            self._bridge.gui_callback.emit(lambda: self._update_step_preview(
                step, desk_frame_copy, wrist_frame_copy))
        except:
            pass

    def _update_step_preview(self, step: VLAStep, desk_frame=None, wrist_frame=None):
        """Update the live data preview (selected arms only)"""
        arm_side = step.arm_side

        def fmt_hand(h):
            return f"[{h[0]:.2f},{h[1]:.2f},{h[2]:.2f},{h[3]:.2f},{h[4]:.2f},{h[5]:.2f}]"

        def fmt_gripper(s):
            return f"pos={s.gripper_position:.2f}, trq={s.gripper_torque:.2f}"

        # Show only selected arm(s) data
        if arm_side == "both":
            state_info = (
                f"LEFT  TCP: [{step.left_tcp_position[0]:.3f}, {step.left_tcp_position[1]:.3f}, {step.left_tcp_position[2]:.3f}] m\n"
                f"RIGHT TCP: [{step.right_tcp_position[0]:.3f}, {step.right_tcp_position[1]:.3f}, {step.right_tcp_position[2]:.3f}] m\n"
                f"Gripper: {fmt_gripper(step)}"
            )
        elif arm_side == "left":
            state_info = (
                f"LEFT TCP: [{step.left_tcp_position[0]:.4f}, {step.left_tcp_position[1]:.4f}, {step.left_tcp_position[2]:.4f}] m\n"
                f"Joints: [{', '.join([f'{j:.2f}' for j in step.left_joint_positions[:4]])} ...] rad"
            )
        else:  # right
            state_info = (
                f"RIGHT TCP: [{step.right_tcp_position[0]:.4f}, {step.right_tcp_position[1]:.4f}, {step.right_tcp_position[2]:.4f}] m\n"
                f"Joints: [{', '.join([f'{j:.2f}' for j in step.right_joint_positions[:4]])} ...] rad\n"
                f"Gripper: {fmt_gripper(step)}"
            )
        self.state_text.setPlainText(state_info)

        # Update action text
        if arm_side == "both":
            action_info = (
                f"L Delta: [{step.left_delta_position[0]:.4f}, {step.left_delta_position[1]:.4f}, {step.left_delta_position[2]:.4f}]\n"
                f"R Delta: [{step.right_delta_position[0]:.4f}, {step.right_delta_position[1]:.4f}, {step.right_delta_position[2]:.4f}]"
            )
        elif arm_side == "left":
            action_info = (
                f"Delta Pos: [{step.left_delta_position[0]:.4f}, {step.left_delta_position[1]:.4f}, {step.left_delta_position[2]:.4f}] m\n"
                f"Delta Rot: [{step.left_delta_rotation[0]:.4f}, {step.left_delta_rotation[1]:.4f}, {step.left_delta_rotation[2]:.4f}] rad"
            )
        else:
            action_info = (
                f"Delta Pos: [{step.right_delta_position[0]:.4f}, {step.right_delta_position[1]:.4f}, {step.right_delta_position[2]:.4f}] m\n"
                f"Delta Rot: [{step.right_delta_rotation[0]:.4f}, {step.right_delta_rotation[1]:.4f}, {step.right_delta_rotation[2]:.4f}] rad"
            )
        self.action_text.setPlainText(action_info)

        # Update camera previews
        if desk_frame is not None:
            try:
                pixmap = _numpy_to_qpixmap(desk_frame, 120, 90)
                if pixmap:
                    self._preview_pixmap = pixmap
                    self.camera_label.setPixmap(pixmap)
            except Exception:
                pass

        if wrist_frame is not None:
            try:
                pixmap2 = _numpy_to_qpixmap(wrist_frame, 120, 90)
                if pixmap2:
                    self._preview_pixmap2 = pixmap2
                    self.camera_label2.setPixmap(pixmap2)
            except Exception:
                pass

    # --- UI Update Timer ---

    def _start_ui_update_timer(self):
        """Start timer for periodic UI updates"""
        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._update_ui_stats)
        self._ui_timer.start(100)

    def _update_ui_stats(self):
        """Update step count, duration, and connection status"""
        # Update connection status periodically
        self._update_connection_status()

        if self.vla_manager.state == RecordingState.RECORDING:
            self.step_count_label.setText(f"{t('vla.steps')}: {self.current_step_count}")
            if self.recording_start_time:
                duration = time.time() - self.recording_start_time
                self.duration_label.setText(f"{t('vla.duration')}: {duration:.1f}s")
        else:
            self._update_idle_preview()

    def _update_idle_preview(self):
        """Update preview when not recording"""
        if self._camera_panel and CV2_AVAILABLE:
            try:
                frames = {}
                if hasattr(self._camera_panel, 'get_last_frames'):
                    frames = self._camera_panel.get_last_frames()

                entry0 = frames.get(0)
                if entry0 is not None:
                    if isinstance(entry0, tuple) and len(entry0) >= 2:
                        rgb = entry0[1]
                    else:
                        rgb = cv2.cvtColor(entry0, cv2.COLOR_BGR2RGB)
                    pixmap = _numpy_to_qpixmap(rgb, 120, 90)
                    if pixmap:
                        self._preview_pixmap = pixmap
                        self.camera_label.setPixmap(pixmap)

                entry1 = frames.get(1)
                if entry1 is not None:
                    if isinstance(entry1, tuple) and len(entry1) >= 2:
                        rgb = entry1[1]
                    else:
                        rgb = cv2.cvtColor(entry1, cv2.COLOR_BGR2RGB)
                    pixmap2 = _numpy_to_qpixmap(rgb, 120, 90)
                    if pixmap2:
                        self._preview_pixmap2 = pixmap2
                        self.camera_label2.setPixmap(pixmap2)
            except Exception:
                pass

    # --- Episode List ---

    def _refresh_episode_list(self):
        """Refresh the episode list"""
        self.episode_listbox.clear()

        episodes = self.vla_manager.list_episodes()

        for ep in episodes:
            arm_str = ep.get('arm_side', '?')[:1].upper()
            num_steps = ep.get('num_steps', 0)
            duration = ep.get('duration', 0)
            task_id = ep.get('task_id', '')[:15] or ep.get('language_instruction', '')[:15]
            date_str = ep.get('date_str', '')
            trial_name = ep.get('trial_name', '')

            line = f"[{date_str}/{trial_name}] Ep{ep['episode_num']:02d} ({arm_str}): {num_steps} steps, {duration:.1f}s - {task_id}"
            self.episode_listbox.addItem(line)

    def _delete_selected(self):
        """Delete selected episodes"""
        selection = self.episode_listbox.selectedItems()
        if not selection:
            QMessageBox.information(self, t("common.info"), t("vla.select_to_delete"))
            return

        selected_rows = [self.episode_listbox.row(item) for item in selection]

        reply = QMessageBox.question(
            self, t("common.confirm"), t("vla.confirm_delete_count", count=len(selected_rows)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted = 0
        episodes = self.vla_manager.list_episodes()

        for idx in reversed(selected_rows):
            try:
                if idx < len(episodes):
                    ep = episodes[idx]
                    if self.vla_manager.delete_episode(ep['date_str'], ep['trial_name'], ep['episode_num']):
                        deleted += 1
            except Exception as e:
                logger.warning(f"Delete error: {e}")

        self._log(f"Deleted {deleted} episode(s)")
        self._refresh_episode_list()

    def _open_output_folder(self):
        """Open the VLA output folder"""
        if os.path.exists(self.vla_manager.output_dir):
            subprocess.Popen(['xdg-open', self.vla_manager.output_dir])
        else:
            os.makedirs(self.vla_manager.output_dir, exist_ok=True)
            subprocess.Popen(['xdg-open', self.vla_manager.output_dir])

    def _finalize_trial(self):
        """Finalize the current trial (required before pushing to hub)."""
        if self.vla_manager.state != RecordingState.IDLE:
            QMessageBox.warning(
                self, "Cannot Finalize",
                "Stop the current recording before finalizing the trial."
            )
            return
        if self.vla_manager._lerobot_dataset is None and not self.vla_manager._trial_finalized:
            QMessageBox.information(
                self, "Nothing to Finalize",
                "No active trial to finalize. Record some episodes first."
            )
            return
        self.vla_manager.finalize_trial()
        self._push_hub_btn.setEnabled(True)
        self._finalize_trial_btn.setEnabled(False)
        self._log("Trial finalized. Ready to push to hub.")
        self._refresh_episode_list()

    def _push_to_hub(self):
        """Push the finalized dataset to Hugging Face Hub."""
        repo_id = self._hub_repo_id_entry.text().strip()
        if not repo_id:
            QMessageBox.warning(
                self, "Missing Repo ID",
                "Enter a Hugging Face repo ID, e.g. myusername/my-dataset"
            )
            return

        private = self._hub_private_check.isChecked()

        reply = QMessageBox.question(
            self, "Push to Hub",
            f"Push dataset to:\n  {repo_id}\n\n"
            f"Visibility: {'Private' if private else 'Public'}\n\n"
            "Make sure you have run 'huggingface-cli login' and called Finalize Trial first.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Pre-flight: verify HuggingFace login before spawning thread
        try:
            import importlib
            hf_hub = importlib.import_module("huggingface_hub")
            hf_hub.whoami()
        except ModuleNotFoundError:
            pass  # huggingface_hub not installed — let backend handle it
        except Exception as e:
            QMessageBox.warning(
                self, "Not Logged In",
                "You are not logged in to Hugging Face.\n\n"
                "Run the following command in your terminal, then try again:\n\n"
                "    huggingface-cli login\n\n"
                f"({type(e).__name__}: {e})"
            )
            return

        self._push_hub_btn.setEnabled(False)
        self._push_hub_btn.setText("Pushing…")

        def _do_push():
            success = self.vla_manager.push_to_hub(repo_id, private=private)
            data = {"success": success, "repo_id": repo_id}
            try:
                self._bridge.gui_callback.emit(lambda d=data: self._on_hub_push_done(d))
            except Exception:
                self._on_hub_push_done(data)

        import threading
        threading.Thread(target=_do_push, daemon=True).start()

    def _on_hub_push_done(self, data: dict):
        """Called (on main thread) when push_to_hub completes."""
        self._push_hub_btn.setText("Push to Hub")
        if data.get("success"):
            # Push consumed — disable push, re-enable finalize for the next trial
            self._push_hub_btn.setEnabled(False)
            self._finalize_trial_btn.setEnabled(True)
            QMessageBox.information(
                self, "Push Complete",
                f"Dataset pushed successfully to:\n{data.get('repo_id', '')}"
            )
            self._log(f"Pushed to hub: {data.get('repo_id', '')}")
        else:
            # Keep push enabled so user can retry after fixing auth
            self._push_hub_btn.setEnabled(True)
            QMessageBox.warning(
                self, "Push Failed",
                "Push to hub failed. Check logs for details.\n"
                "Make sure you are logged in:\n\n  huggingface-cli login"
            )
            self._log("Push to hub failed — see logs")

    # --- Language Update ---

    def update_language(self, language: str = None):
        """Update all UI text for language change"""
        self._conn_frame.setTitle(t("vla.connection_status") if hasattr(t, '__call__') else "Connection Status")
        self._config_frame.setTitle(t("vla.config_title"))
        self._control_frame.setTitle(t("vla.control_title"))
        self._preview_frame.setTitle(t("vla.live_data"))
        self._list_frame.setTitle(t("vla.episode_list"))

        self._task_id_label.setText(t("vla.task_id") + ":")
        self._lang_inst_label.setText(t("vla.language_inst") + ":")
        self._arm_selection_label.setText(t("vla.arm_side") + ":")
        self._robot_state_label.setText(t("vla.robot_state") + ":")
        self._action_label.setText(t("vla.action") + ":")
        self._cam_preview_label.setText(t("vla.camera_preview") + ":")
        self._desk_label.setText(t("vla.camera_desk"))
        self._wrist_label.setText(t("vla.camera_wrist"))

        self._open_folder_btn.setText(t("vla.open_folder"))
        self._refresh_btn.setText(t("common.refresh"))
        self._delete_btn.setText(t("vla.delete"))

        if self.vla_manager.state == RecordingState.IDLE:
            self.record_btn.setText(t("vla.start_recording"))
            self.status_label.setText(t("vla.status_idle"))
        else:
            self.record_btn.setText(t("vla.stop_recording"))
            self.status_label.setText(t("vla.status_recording"))

        self.discard_btn.setText(t("vla.discard"))
        self.new_trial_btn.setText(t("vla.new_trial"))

        self.step_count_label.setText(f"{t('vla.steps')}: {self.current_step_count}")
        if self.recording_start_time:
            duration = time.time() - self.recording_start_time
            self.duration_label.setText(f"{t('vla.duration')}: {duration:.1f}s")
        else:
            self.duration_label.setText(f"{t('vla.duration')}: 0.0s")

    # --- Cleanup ---

    def cleanup(self):
        """Cleanup resources"""
        # Remove event filter
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)

        if hasattr(self, '_ui_timer') and self._ui_timer:
            self._ui_timer.stop()
        if hasattr(self, '_teleop_delay_timer') and self._teleop_delay_timer:
            self._teleop_delay_timer.stop()
        if self.vla_manager.state != RecordingState.IDLE:
            self.vla_manager.discard_episode()
        if self._robot_controller and hasattr(self._robot_controller, 'stop_state_poller'):
            self._robot_controller.stop_state_poller()

    def destroy(self):
        self.cleanup()
        self.deleteLater()
