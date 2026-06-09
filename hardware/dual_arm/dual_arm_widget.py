"""
Dual Arm Widget Module
双臂部件模块

GUI widget for dual arm robot control with combined left/right arm view.
用于双臂机器人控制的GUI部件，包含组合的左/右臂视图。
"""

import os
import threading
import time

from gui.qt_imports import (
    QWidget, QGroupBox, QLabel, QPushButton, QLineEdit, QComboBox,
    QCheckBox, QSpinBox, QDoubleSpinBox, QSlider, QTabWidget,
    QListWidget, QListWidgetItem, QDialog, QTextEdit,
    QHBoxLayout, QVBoxLayout, QGridLayout, QFrame,
    QMessageBox, QFileDialog, QInputDialog, QTimer,
    Qt, QFont, QSizePolicy,
)
from typing import Optional, List

from .dual_arm_controller import DualArmController, ArmSide
from .linker_hand_controller import LinkerHandController, HandSide
from .linker_hand_widget import LinkerHandWidget
from .poses import DualArmPoseManager, DualArmPose
from .pose_control_widget import RecordedPose
from hardware.gripper.gripper_widget import GripperWidget
from datetime import datetime
from config.i18n import t
from app_core.logger import get_logger
from gui.widgets import HardwareStatusCard, ScrollableFrame

logger = get_logger(__name__)


class ArmControlPanel(QGroupBox):
    """
    Control panel for a single arm with joint display and control buttons.
    单臂控制面板，包含关节显示和控制按钮。
    """

    def __init__(self, parent, side: str, arm_controller: DualArmController):
        """
        Initialize arm control panel.

        Args:
            parent: Parent widget
            side: "left" or "right"
            arm_controller: DualArmController instance
        """
        title = t("hardware.left_arm") if side == "left" else t("hardware.right_arm")
        super().__init__(title, parent)

        self.side = side
        self.arm = arm_controller
        self.joint_labels: List[QLabel] = []
        self.joint_entries: List[QLineEdit] = []

        self._build_ui()

    def _build_ui(self):
        """Build the UI / 构建UI"""
        main_layout = QVBoxLayout(self)

        # Joint display and entry frame
        joints_layout = QVBoxLayout()
        main_layout.addLayout(joints_layout)

        # Create 7 joint rows
        for i in range(7):
            row_layout = QHBoxLayout()
            joints_layout.addLayout(row_layout)

            # Joint label
            jlabel = QLabel(f"J{i+1}:")
            jlabel.setMinimumWidth(30)
            row_layout.addWidget(jlabel)

            # Current value display
            val_label = QLabel("0.00")
            val_label.setMinimumWidth(70)
            self.joint_labels.append(val_label)
            row_layout.addWidget(val_label)

            row_layout.addWidget(QLabel("rad"))

            # Jog buttons (delta in radians: 0.05 rad ~ 2.86 deg)
            minus_btn = QPushButton("-")
            minus_btn.setMaximumWidth(30)
            minus_btn.clicked.connect(lambda checked=False, j=i: self._on_joint_jog(j, -0.05))
            row_layout.addWidget(minus_btn)

            plus_btn = QPushButton("+")
            plus_btn.setMaximumWidth(30)
            plus_btn.clicked.connect(lambda checked=False, j=i: self._on_joint_jog(j, 0.05))
            row_layout.addWidget(plus_btn)

            # Entry for target value
            entry = QLineEdit("0.0")
            entry.setMaximumWidth(70)
            row_layout.addWidget(entry)
            self.joint_entries.append(entry)

            # Move to entry value button
            go_btn = QPushButton("Go")
            go_btn.setMaximumWidth(35)
            go_btn.clicked.connect(lambda checked=False, j=i: self._on_move_single_joint(j))
            row_layout.addWidget(go_btn)

        # Control buttons frame
        btn_layout = QHBoxLayout()
        main_layout.addLayout(btn_layout)

        self.get_pos_btn = QPushButton(t("dual_arm.get_position"))
        self.get_pos_btn.clicked.connect(self._on_get_position)
        btn_layout.addWidget(self.get_pos_btn)

        self.set_zero_btn = QPushButton(t("dual_arm.set_to_zero"))
        self.set_zero_btn.clicked.connect(self._on_set_to_zero)
        btn_layout.addWidget(self.set_zero_btn)

        self.move_joints_btn = QPushButton(t("dual_arm.move_to_joints"))
        self.move_joints_btn.clicked.connect(self._on_move_to_joints)
        btn_layout.addWidget(self.move_joints_btn)

        btn_layout.addStretch()

    def _on_joint_jog(self, joint_index: int, delta: float):
        """Handle joint jog button / 处理关节点动按钮"""
        if self.side == "left":
            joints = list(self.arm.get_left_joints())
        else:
            joints = list(self.arm.get_right_joints())

        joints[joint_index] += delta

        def do_move():
            try:
                if self.side == "left":
                    self.arm.move_left_joints(joints)
                else:
                    self.arm.move_right_joints(joints)
            except Exception as e:
                logger.exception("Arm move (delta) failed: %s", e)

        threading.Thread(target=do_move, daemon=True).start()

    def _on_move_single_joint(self, joint_index: int):
        """Move single joint to entry value / 移动单个关节到输入值"""
        try:
            target = float(self.joint_entries[joint_index].text())
        except ValueError:
            QMessageBox.critical(self, t("common.error"), "Invalid joint value")
            return

        if self.side == "left":
            joints = list(self.arm.get_left_joints())
        else:
            joints = list(self.arm.get_right_joints())

        joints[joint_index] = target

        def do_move():
            try:
                if self.side == "left":
                    self.arm.move_left_joints(joints)
                else:
                    self.arm.move_right_joints(joints)
            except Exception as e:
                logger.exception("Arm move (single joint) failed: %s", e)

        threading.Thread(target=do_move, daemon=True).start()

    def _on_get_position(self):
        """Get current position and update display + entries / 获取当前位置并更新显示和输入框"""
        try:
            if self.side == "left":
                joints = self.arm.get_left_joints()
            else:
                joints = self.arm.get_right_joints()
        except Exception as e:
            logger.exception("Get arm position failed: %s", e)
            QMessageBox.critical(self, t("common.error"), str(e)[:200])
            return
        for i, val in enumerate(joints):
            # Update display labels
            if i < len(self.joint_labels):
                self.joint_labels[i].setText(f"{val:.4f}")
            # Also update editable entry fields
            if i < len(self.joint_entries):
                self.joint_entries[i].setText(f"{val:.4f}")

    def _on_set_to_zero(self):
        """Set all joint entry fields to zero (does NOT move the robot) / 将所有关节输入框设为零（不移动机器人）"""
        for entry in self.joint_entries:
            entry.setText("0.0000")

    def _on_move_to_joints(self):
        """Move to joint values in entries / 移动到输入框中的关节值"""
        try:
            joints = [float(entry.text()) for entry in self.joint_entries]
        except ValueError:
            QMessageBox.critical(self, t("common.error"), "Invalid joint values")
            return

        def do_move():
            try:
                if self.side == "left":
                    self.arm.move_left_joints(joints)
                else:
                    self.arm.move_right_joints(joints)
            except Exception as e:
                logger.exception("Arm move to joints failed: %s", e)

        threading.Thread(target=do_move, daemon=True).start()

    def update_display(self, joints: List[float]):
        """Update joint display values / 更新关节显示值"""
        for i, val in enumerate(joints):
            if i < len(self.joint_labels):
                self.joint_labels[i].setText(f"{val:.4f}")

    def update_language(self):
        """Update text for language change / 更新语言变化的文本"""
        title = t("hardware.left_arm") if self.side == "left" else t("hardware.right_arm")
        self.setTitle(title)

        self.get_pos_btn.setText(t("dual_arm.get_position"))
        self.set_zero_btn.setText(t("dual_arm.set_to_zero"))
        self.move_joints_btn.setText(t("dual_arm.move_to_joints"))


class DualArmWidget(QWidget):
    """
    Widget for dual arm robot control.
    用于双臂机器人控制的部件。

    Contains tabs for:
    - Combined arm control (both arms side by side)
    - LinkerHand control (finger sliders and touch sensors)
    - Pose management
    """

    def __init__(self, parent,
                 arm_controller: DualArmController = None,
                 hand_controller: LinkerHandController = None,
                 gripper_controller=None):
        super().__init__(parent)

        self.arm = arm_controller or DualArmController()
        self.hand = hand_controller or LinkerHandController()
        self.gripper = gripper_controller
        self.pose_manager = DualArmPoseManager()
        self._current_step_index: Optional[int] = None
        self._file_paths: dict = {}  # Maps displayed filename -> full path

        self._build_ui()
        self._schedule_update()

    def _build_ui(self):
        """Build UI / 构建UI"""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)

        # Top row - Status cards
        status_layout = QHBoxLayout()
        outer_layout.addLayout(status_layout)

        self.arm_card = HardwareStatusCard(
            self,
            "dual_arm",
            "hardware.dual_arm",
            self.arm
        )
        status_layout.addWidget(self.arm_card)

        self.hand_card = HardwareStatusCard(
            self,
            "linker_hand",
            "hardware.linker_hand",
            self.hand
        )
        status_layout.addWidget(self.hand_card)

        self.gripper_card = HardwareStatusCard(
            self,
            "gripper",
            "hardware.gripper",
            self.gripper
        )
        status_layout.addWidget(self.gripper_card)

        # Notebook for different control sections
        self.notebook = QTabWidget()
        outer_layout.addWidget(self.notebook)

        # Arm control tab (combined left and right)
        arm_tab = QWidget()
        self.notebook.addTab(arm_tab, t("dual_arm.arm_control"))
        self._build_arm_tab(arm_tab)

        # Hand control tab
        hand_tab = QWidget()
        self.notebook.addTab(hand_tab, t("hardware.linker_hand"))
        self._build_hand_tab(hand_tab)

        # Gripper control tab
        gripper_tab = QWidget()
        self.notebook.addTab(gripper_tab, t("hardware.gripper"))
        self._build_gripper_tab(gripper_tab)

        # Poses tab
        poses_tab = QWidget()
        self.notebook.addTab(poses_tab, t("pose.list"))
        self._build_poses_tab(poses_tab)

    def _build_arm_tab(self, parent):
        """Build combined arm control tab / 构建组合手臂控制标签页"""
        tab_layout = QVBoxLayout(parent)

        # Create scrollable frame for arm controls
        scroll_frame = ScrollableFrame(parent)
        tab_layout.addWidget(scroll_frame)

        content_layout = scroll_frame.inner_layout

        # Arm control section: enable/disable left and right arms (above left/right panels)
        self.arm_ctrl_frame = QGroupBox(t("dual_arm.arm_control"))
        content_layout.addWidget(self.arm_ctrl_frame)
        arm_ctrl_layout = QVBoxLayout(self.arm_ctrl_frame)

        # Row 1: enable/disable buttons + status
        row1_layout = QHBoxLayout()
        arm_ctrl_layout.addLayout(row1_layout)

        self.enable_left_btn = QPushButton(t("dual_arm.enable_left"))
        self.enable_left_btn.clicked.connect(lambda: self._enable_arm("left", True))
        row1_layout.addWidget(self.enable_left_btn)

        self.disable_left_btn = QPushButton(t("dual_arm.disable_left"))
        self.disable_left_btn.clicked.connect(lambda: self._enable_arm("left", False))
        row1_layout.addWidget(self.disable_left_btn)

        self.enable_right_btn = QPushButton(t("dual_arm.enable_right"))
        self.enable_right_btn.clicked.connect(lambda: self._enable_arm("right", True))
        row1_layout.addWidget(self.enable_right_btn)

        self.disable_right_btn = QPushButton(t("dual_arm.disable_right"))
        self.disable_right_btn.clicked.connect(lambda: self._enable_arm("right", False))
        row1_layout.addWidget(self.disable_right_btn)

        self.arm_status_label = QLabel("")
        self.arm_status_label.setStyleSheet("color: gray;")
        row1_layout.addWidget(self.arm_status_label)
        row1_layout.addStretch()

        # Row 2: Start button + auto re-enable and auto disable options
        row2_layout = QHBoxLayout()
        arm_ctrl_layout.addLayout(row2_layout)

        # Auto-cycle running state
        self._auto_cycle_running = False

        self.auto_cycle_btn = QPushButton(t("dual_arm.auto_cycle_start"))
        self.auto_cycle_btn.clicked.connect(self._toggle_auto_cycle)
        row2_layout.addWidget(self.auto_cycle_btn)

        self.auto_cycle_reset_btn = QPushButton(t("dual_arm.auto_cycle_reset"))
        self.auto_cycle_reset_btn.clicked.connect(self._reset_auto_cycle)
        row2_layout.addWidget(self.auto_cycle_reset_btn)

        # -- Auto re-enable after disable --
        self._auto_reenable = False
        self.auto_reenable_chk = QCheckBox(t("dual_arm.auto_reenable"))
        self.auto_reenable_chk.toggled.connect(lambda v: setattr(self, '_auto_reenable', v))
        row2_layout.addWidget(self.auto_reenable_chk)

        self.auto_reenable_spin = QSpinBox()
        self.auto_reenable_spin.setRange(1, 120)
        self.auto_reenable_spin.setValue(10)
        self.auto_reenable_spin.setMaximumWidth(60)
        row2_layout.addWidget(self.auto_reenable_spin)

        self.auto_reenable_sec_label = QLabel(t("dual_arm.auto_reenable_sec"))
        row2_layout.addWidget(self.auto_reenable_sec_label)

        # Separator between the two auto options
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        row2_layout.addWidget(sep)

        # -- Auto disable after enable --
        self._auto_disable = False
        self.auto_disable_chk = QCheckBox(t("dual_arm.auto_disable"))
        self.auto_disable_chk.toggled.connect(lambda v: setattr(self, '_auto_disable', v))
        row2_layout.addWidget(self.auto_disable_chk)

        self.auto_disable_spin = QSpinBox()
        self.auto_disable_spin.setRange(1, 120)
        self.auto_disable_spin.setValue(10)
        self.auto_disable_spin.setMaximumWidth(60)
        row2_layout.addWidget(self.auto_disable_spin)

        self.auto_disable_sec_label = QLabel(t("dual_arm.auto_disable_sec"))
        row2_layout.addWidget(self.auto_disable_sec_label)

        # Countdown label (shows seconds remaining until next auto action)
        self.auto_countdown_label = QLabel("")
        self.auto_countdown_label.setStyleSheet("color: orange; font-weight: bold; font-size: 9pt;")
        row2_layout.addWidget(self.auto_countdown_label)
        row2_layout.addStretch()

        # Pending auto timer IDs (keyed by "reenable:<arm>" / "disable:<arm>")
        self._auto_timer_ids: dict = {}
        # Countdown state
        self._countdown_remaining = 0
        self._countdown_action = ""
        self._countdown_next_enable = True  # True = next action is enable
        self._countdown_timer = None
        # Debounce: only one record-on-enable per cycle step
        self._record_on_enable_timer = None
        # Paused state for resume
        self._paused_remaining = 0
        self._paused_next_enable = True

        # Both arms button row
        top_btn_layout = QHBoxLayout()
        content_layout.addLayout(top_btn_layout)

        self.get_both_btn = QPushButton(t("dual_arm.get_both_positions"))
        self.get_both_btn.clicked.connect(self._on_get_both_positions)
        top_btn_layout.addWidget(self.get_both_btn)

        self.set_both_zero_btn = QPushButton(t("dual_arm.set_both_zero"))
        self.set_both_zero_btn.clicked.connect(self._on_set_both_zero)
        top_btn_layout.addWidget(self.set_both_zero_btn)
        top_btn_layout.addStretch()

        # Container for both arm panels side by side
        arms_layout = QHBoxLayout()
        content_layout.addLayout(arms_layout)

        # Left arm panel
        self.left_arm_panel = ArmControlPanel(None, "left", self.arm)
        arms_layout.addWidget(self.left_arm_panel)

        # Right arm panel
        self.right_arm_panel = ArmControlPanel(None, "right", self.arm)
        arms_layout.addWidget(self.right_arm_panel)

    def _build_hand_tab(self, parent):
        """Build hand control tab with finger control and record-pose button."""
        tab_layout = QVBoxLayout(parent)

        # Top: Record current arms + fingers as pose (store refs for language update)
        record_layout = QHBoxLayout()
        tab_layout.addLayout(record_layout)

        self.hand_record_btn = QPushButton(t("dual_arm.record_from_hand_tab"))
        self.hand_record_btn.clicked.connect(self._record_current_pose_from_hand_tab)
        record_layout.addWidget(self.hand_record_btn)

        self.hand_record_hint = QLabel(" -> " + t("pose.list"))
        self.hand_record_hint.setStyleSheet("color: gray;")
        record_layout.addWidget(self.hand_record_hint)
        record_layout.addStretch()

        # LinkerHand finger sliders and presets
        self.hand_widget = LinkerHandWidget(parent, self.hand)
        tab_layout.addWidget(self.hand_widget)

    def _build_gripper_tab(self, parent):
        """Build gripper control tab with embedded GripperWidget and record button."""
        tab_layout = QVBoxLayout(parent)

        # Top: Record current arms + gripper as pose
        record_layout = QHBoxLayout()
        tab_layout.addLayout(record_layout)

        self.gripper_record_btn = QPushButton(t("dual_arm.record_from_gripper_tab"))
        self.gripper_record_btn.clicked.connect(self._record_current_pose_from_gripper_tab)
        record_layout.addWidget(self.gripper_record_btn)

        self.gripper_record_hint = QLabel(" -> " + t("pose.list"))
        self.gripper_record_hint.setStyleSheet("color: gray;")
        record_layout.addWidget(self.gripper_record_hint)
        record_layout.addStretch()

        # Embed the GripperWidget (reuse gripper controller from DualArmWidget)
        if self.gripper:
            self.gripper_widget = GripperWidget(parent, controller=self.gripper)
        else:
            self.gripper_widget = GripperWidget(parent)
        tab_layout.addWidget(self.gripper_widget)

    def _record_current_pose_from_gripper_tab(self):
        """Record current arms + gripper state as a pose (called from gripper tab)."""
        if self._current_step_index is None:
            self.pose_manager.add_step(self.pose_manager.next_default_step_name())
            self._current_step_index = len(self.pose_manager._steps) - 1
            self._update_steps_list()
        self._include_gripper = True
        self.include_gripper_chk.setChecked(True)
        name = self.pose_manager.next_default_pose_name(self._current_step_index)
        self.pose_name_edit.setText(name)

        left_state = self.arm.get_arm_state("left")
        right_state = self.arm.get_arm_state("right")

        grip_pos, grip_torque = self._get_gripper_state_for_record()

        speed = self.arm._speed_factor
        pose = RecordedPose(
            name=name,
            timestamp=datetime.now().isoformat(),
            arm="both",
            pose_type="joint",
            joints=list(left_state['joints']) if left_state else list(self.arm.get_left_joints()),
            position=dict(left_state.get('position', {})) if left_state else {},
            euler=dict(left_state.get('euler', {})) if left_state else {},
            speed=speed,
            acceleration=0.5,
            right_joints=list(right_state['joints']) if right_state else list(self.arm.get_right_joints()),
            right_position=dict(right_state.get('position', {})) if right_state else {},
            right_euler=dict(right_state.get('euler', {})) if right_state else {},
            right_speed=speed,
            right_acceleration=0.5,
            gripper_position=grip_pos,
            gripper_torque=grip_torque,
        )
        self.pose_manager.add_pose_to_step(self._current_step_index, pose)
        self.pose_name_edit.setText(self.pose_manager.next_default_pose_name(self._current_step_index))
        self._refresh_poses_in_step()
        self._update_steps_list()
        QMessageBox.information(self, t("common.info"), t("dual_arm.msg_recorded_pose").replace("{name}", name))

    def _build_poses_tab(self, parent):
        """Build poses tab with steps and poses-in-step (like robot_control_gui)."""
        tab_layout = QVBoxLayout(parent)

        main_layout = QHBoxLayout()
        tab_layout.addLayout(main_layout)

        # Left: Steps (store refs for language update)
        self.steps_frame = QGroupBox(t("dual_arm.steps"))
        main_layout.addWidget(self.steps_frame)
        steps_layout = QVBoxLayout(self.steps_frame)

        # File selector row
        file_selector_layout = QHBoxLayout()
        steps_layout.addLayout(file_selector_layout)
        self.file_label = QLabel(t("dual_arm.file_label"))
        file_selector_layout.addWidget(self.file_label)
        self.file_combobox = QComboBox()
        self.file_combobox.setMinimumWidth(180)
        self.file_combobox.currentIndexChanged.connect(self._on_file_selected)
        file_selector_layout.addWidget(self.file_combobox)
        refresh_file_btn = QPushButton("\u21BB")
        refresh_file_btn.setMaximumWidth(30)
        refresh_file_btn.clicked.connect(self._refresh_file_list)
        file_selector_layout.addWidget(refresh_file_btn)

        # File action buttons
        file_btn_layout = QHBoxLayout()
        steps_layout.addLayout(file_btn_layout)
        self.load_file_btn = QPushButton(t("dual_arm.load_file"))
        self.load_file_btn.clicked.connect(self._on_load_file)
        file_btn_layout.addWidget(self.load_file_btn)
        self.save_file_btn = QPushButton(t("dual_arm.save_file"))
        self.save_file_btn.clicked.connect(self._on_save_file)
        file_btn_layout.addWidget(self.save_file_btn)
        self.save_as_btn = QPushButton(t("dual_arm.save_as"))
        self.save_as_btn.clicked.connect(self._on_save_as)
        file_btn_layout.addWidget(self.save_as_btn)
        file_btn_layout.addStretch()

        step_ctrl_layout = QHBoxLayout()
        steps_layout.addLayout(step_ctrl_layout)
        self.step_name_label = QLabel(t("pose.name") + ":")
        step_ctrl_layout.addWidget(self.step_name_label)
        self.step_name_edit = QLineEdit("Step_1")
        self.step_name_edit.setMaximumWidth(100)
        step_ctrl_layout.addWidget(self.step_name_edit)
        self.add_step_btn = QPushButton(t("dual_arm.add_step"))
        self.add_step_btn.clicked.connect(self._on_add_step)
        step_ctrl_layout.addWidget(self.add_step_btn)
        step_ctrl_layout.addStretch()

        self.steps_listbox = QListWidget()
        self.steps_listbox.currentRowChanged.connect(lambda row: self._on_step_select())
        steps_layout.addWidget(self.steps_listbox)

        step_btn_layout = QHBoxLayout()
        steps_layout.addLayout(step_btn_layout)
        self.execute_step_btn = QPushButton(t("dual_arm.execute_step"))
        self.execute_step_btn.clicked.connect(self._on_execute_step)
        step_btn_layout.addWidget(self.execute_step_btn)
        self.stop_execution_btn = QPushButton(t("common.stop"))
        self.stop_execution_btn.clicked.connect(self._stop_execution)
        step_btn_layout.addWidget(self.stop_execution_btn)
        self.delete_step_btn = QPushButton(t("dual_arm.delete_step"))
        self.delete_step_btn.clicked.connect(self._on_delete_step)
        step_btn_layout.addWidget(self.delete_step_btn)
        self.rename_step_btn = QPushButton(t("dual_arm.rename_step"))
        self.rename_step_btn.clicked.connect(self._on_rename_step)
        step_btn_layout.addWidget(self.rename_step_btn)
        self.save_step_btn = QPushButton(t("dual_arm.save_step"))
        self.save_step_btn.clicked.connect(self._on_save_step)
        step_btn_layout.addWidget(self.save_step_btn)

        # Right: Poses in step (store refs for language update)
        self.poses_frame = QGroupBox(t("dual_arm.poses_in_step"))
        main_layout.addWidget(self.poses_frame)
        poses_layout = QVBoxLayout(self.poses_frame)

        pose_ctrl_layout = QHBoxLayout()
        poses_layout.addLayout(pose_ctrl_layout)
        self.pose_name_label = QLabel(t("pose.name") + ":")
        pose_ctrl_layout.addWidget(self.pose_name_label)
        self.pose_name_edit = QLineEdit("Pose_1")
        self.pose_name_edit.setMaximumWidth(80)
        pose_ctrl_layout.addWidget(self.pose_name_edit)
        self.record_arm_label = QLabel(t("dual_arm.record_arm") + ":")
        pose_ctrl_layout.addWidget(self.record_arm_label)
        self.record_arm_combo = QComboBox()
        self.record_arm_combo.addItems(["both", "left", "right"])
        self.record_arm_combo.setMaximumWidth(80)
        pose_ctrl_layout.addWidget(self.record_arm_combo)
        self._include_hand = True
        self.include_hand_chk = QCheckBox(t("dual_arm.include_hand"))
        self.include_hand_chk.setChecked(True)
        self.include_hand_chk.toggled.connect(lambda v: setattr(self, '_include_hand', v))
        pose_ctrl_layout.addWidget(self.include_hand_chk)
        self._include_gripper = True
        self.include_gripper_chk = QCheckBox(t("dual_arm.include_gripper"))
        self.include_gripper_chk.setChecked(True)
        self.include_gripper_chk.toggled.connect(lambda v: setattr(self, '_include_gripper', v))
        pose_ctrl_layout.addWidget(self.include_gripper_chk)
        self.record_pose_btn = QPushButton(t("dual_arm.record_pose"))
        self.record_pose_btn.clicked.connect(self._on_record_pose)
        pose_ctrl_layout.addWidget(self.record_pose_btn)
        self._record_on_enable_flag = False
        self.record_on_enable_cb = QCheckBox(t("dual_arm.record_on_enable"))
        self.record_on_enable_cb.toggled.connect(lambda v: setattr(self, '_record_on_enable_flag', v))
        pose_ctrl_layout.addWidget(self.record_on_enable_cb)

        self.pose_listbox = QListWidget()
        self.pose_listbox.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.pose_listbox.doubleClicked.connect(self._on_pose_double_click)
        poses_layout.addWidget(self.pose_listbox)

        pose_btn_layout = QHBoxLayout()
        poses_layout.addLayout(pose_btn_layout)
        self.pose_move_btn = QPushButton(t("dual_arm.execute_pose"))
        self.pose_move_btn.clicked.connect(self._on_execute_pose_one)
        pose_btn_layout.addWidget(self.pose_move_btn)
        self.stop_pose_btn = QPushButton(t("common.stop"))
        self.stop_pose_btn.clicked.connect(self._stop_execution)
        pose_btn_layout.addWidget(self.stop_pose_btn)
        self.pose_delete_btn = QPushButton(t("pose.delete"))
        self.pose_delete_btn.clicked.connect(self._on_delete_pose_from_step)
        pose_btn_layout.addWidget(self.pose_delete_btn)
        self.pose_up_btn = QPushButton(t("dual_arm.pose_move_up"))
        self.pose_up_btn.clicked.connect(self._on_pose_move_up)
        pose_btn_layout.addWidget(self.pose_up_btn)
        self.pose_down_btn = QPushButton(t("dual_arm.pose_move_down"))
        self.pose_down_btn.clicked.connect(self._on_pose_move_down)
        pose_btn_layout.addWidget(self.pose_down_btn)
        self.pose_refresh_btn = QPushButton(t("common.refresh"))
        self.pose_refresh_btn.clicked.connect(self._refresh_poses_in_step)
        pose_btn_layout.addWidget(self.pose_refresh_btn)

        # Bottom bar: delay + speed/accel sliders + execute all
        bottom_layout = QHBoxLayout()
        tab_layout.addLayout(bottom_layout)

        # Delay
        self.delay_label = QLabel(t("dual_arm.delay_sec") + ":")
        bottom_layout.addWidget(self.delay_label)
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.0, 60.0)
        self.delay_spin.setSingleStep(0.1)
        self.delay_spin.setValue(0.0)
        self.delay_spin.setMaximumWidth(60)
        bottom_layout.addWidget(self.delay_spin)

        # Smooth replay toggle: stream poses continuously (no stop between poses)
        self.smooth_cb = QCheckBox(t("dual_arm.smooth_replay"))
        self.smooth_cb.setToolTip(t("dual_arm.smooth_replay_tip"))
        self.smooth_cb.setChecked(True)
        bottom_layout.addWidget(self.smooth_cb)

        # Contact limit (torque) for smooth replay; 0 = off. Live torque shown beside it.
        self.contact_label = QLabel(t("dual_arm.contact_limit") + ":")
        bottom_layout.addWidget(self.contact_label)
        self.effort_limit_spin = QDoubleSpinBox()
        self.effort_limit_spin.setRange(0.0, 500.0)
        self.effort_limit_spin.setSingleStep(1.0)
        self.effort_limit_spin.setValue(0.0)
        self.effort_limit_spin.setMaximumWidth(70)
        self.effort_limit_spin.setToolTip(t("dual_arm.contact_limit_tip"))
        bottom_layout.addWidget(self.effort_limit_spin)
        self.torque_readout = QLabel(t("dual_arm.live_torque") + ": --")
        self.torque_readout.setToolTip(t("dual_arm.live_torque_tip"))
        bottom_layout.addWidget(self.torque_readout)

        # Speed
        self.speed_label = QLabel(t("dual_arm.speed") + ":")
        bottom_layout.addWidget(self.speed_label)
        self.arm._speed_factor = 0.5  # default replay speed
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.05, 2.0)
        self.speed_spin.setSingleStep(0.05)
        self.speed_spin.setValue(self.arm._speed_factor)
        self.speed_spin.setMaximumWidth(60)
        self.speed_spin.valueChanged.connect(self._on_speed_changed)
        bottom_layout.addWidget(self.speed_spin)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(5, 200)  # 0.05 to 2.0, *100
        self.speed_slider.setValue(int(self.arm._speed_factor * 100))
        self.speed_slider.setMaximumWidth(100)
        self.speed_slider.valueChanged.connect(self._on_speed_slider_changed)
        bottom_layout.addWidget(self.speed_slider)

        # Accel
        self.accel_label = QLabel(t("dual_arm.accel") + ":")
        bottom_layout.addWidget(self.accel_label)
        self.accel_spin = QDoubleSpinBox()
        self.accel_spin.setRange(0.05, 2.0)
        self.accel_spin.setSingleStep(0.05)
        self.accel_spin.setValue(self.arm._accel_factor)
        self.accel_spin.setMaximumWidth(60)
        self.accel_spin.valueChanged.connect(self._on_accel_changed)
        bottom_layout.addWidget(self.accel_spin)

        self.accel_slider = QSlider(Qt.Orientation.Horizontal)
        self.accel_slider.setRange(5, 200)
        self.accel_slider.setValue(int(self.arm._accel_factor * 100))
        self.accel_slider.setMaximumWidth(100)
        self.accel_slider.valueChanged.connect(self._on_accel_slider_changed)
        bottom_layout.addWidget(self.accel_slider)

        self.execute_all_steps_btn = QPushButton(t("dual_arm.execute_all_steps"))
        self.execute_all_steps_btn.clicked.connect(self._on_execute_all_steps)
        bottom_layout.addWidget(self.execute_all_steps_btn)
        self.stop_all_btn = QPushButton(t("common.stop"))
        self.stop_all_btn.clicked.connect(self._stop_execution)
        bottom_layout.addWidget(self.stop_all_btn)
        bottom_layout.addStretch()

        self._refresh_file_list()
        self._update_steps_list()
        self._refresh_poses_in_step()
        self._speed_updating = False
        self._accel_updating = False
        self._execution_stop = threading.Event()

        # Live torque readout (updates whenever the arm is connected).
        self._torque_timer = QTimer(self)
        self._torque_timer.timeout.connect(self._update_torque_readout)
        self._torque_timer.start(300)

        # Live connection-status indicators (arm / hands / gripper) — authoritative
        # poll so the dots/text/detail stay accurate even on silent drops.
        self._status_card_timer = QTimer(self)
        self._status_card_timer.timeout.connect(self._refresh_status_cards)
        self._status_card_timer.start(1000)
        self._refresh_status_cards()

    def _on_speed_changed(self, val):
        """Sync speed spin -> slider and controller."""
        if self._speed_updating:
            return
        self._speed_updating = True
        try:
            val = round(max(0.05, min(2.0, val)), 2)
            self.speed_slider.setValue(int(val * 100))
            self.arm._speed_factor = val
        except (ValueError, Exception):
            pass
        finally:
            self._speed_updating = False

    def _on_speed_slider_changed(self, raw_val):
        """Sync speed slider -> spin and controller."""
        if self._speed_updating:
            return
        self._speed_updating = True
        try:
            val = round(raw_val / 100.0, 2)
            self.speed_spin.setValue(val)
            self.arm._speed_factor = val
        except (ValueError, Exception):
            pass
        finally:
            self._speed_updating = False

    def _on_accel_changed(self, val):
        """Sync accel spin -> slider and controller."""
        if self._accel_updating:
            return
        self._accel_updating = True
        try:
            val = round(max(0.05, min(2.0, val)), 2)
            self.accel_slider.setValue(int(val * 100))
            self.arm._accel_factor = val
        except (ValueError, Exception):
            pass
        finally:
            self._accel_updating = False

    def _on_accel_slider_changed(self, raw_val):
        """Sync accel slider -> spin and controller."""
        if self._accel_updating:
            return
        self._accel_updating = True
        try:
            val = round(raw_val / 100.0, 2)
            self.accel_spin.setValue(val)
            self.arm._accel_factor = val
        except (ValueError, Exception):
            pass
        finally:
            self._accel_updating = False

    def _toggle_auto_cycle(self):
        """Start or stop (pause) the auto enable/disable cycle."""
        if self._auto_cycle_running:
            self._stop_auto_cycle()
        else:
            self._auto_cycle_running = True
            self.auto_cycle_btn.setText(t("dual_arm.auto_cycle_stop"))
            # Resume from paused state if available
            if self._paused_remaining > 0:
                enable = self._paused_next_enable
                secs = self._paused_remaining
                self._paused_remaining = 0
                prefix = "reenable" if enable else "disable"
                self._schedule_auto_timer(f"{prefix}:left", secs, "left", enable)
                self._schedule_auto_timer(f"{prefix}:right", secs, "right", enable)
                logger.info(f"Auto cycle resumed -- {'Enable' if enable else 'Disable'} in {secs}s")
            else:
                # Fresh start: schedule the first timer
                if self._auto_reenable:
                    secs = self.auto_reenable_spin.value()
                    self._schedule_auto_timer("reenable:left", secs, "left", True)
                    self._schedule_auto_timer("reenable:right", secs, "right", True)
                elif self._auto_disable:
                    secs = self.auto_disable_spin.value()
                    self._schedule_auto_timer("disable:left", secs, "left", False)
                    self._schedule_auto_timer("disable:right", secs, "right", False)
                logger.info("Auto cycle started")

    def _stop_auto_cycle(self):
        """Pause the auto cycle, saving remaining time for resume."""
        self._auto_cycle_running = False
        self.auto_cycle_btn.setText(t("dual_arm.auto_cycle_start"))
        # Save remaining countdown for resume
        self._paused_remaining = self._countdown_remaining
        self._paused_next_enable = self._countdown_next_enable
        # Cancel every pending auto timer
        for key in list(self._auto_timer_ids):
            self._cancel_auto_timer(key)
        # Stop countdown display (but paused state is preserved)
        self._stop_countdown()
        logger.info(f"Auto cycle paused -- {self._paused_remaining}s remaining")

    def _reset_auto_cycle(self):
        """Stop the cycle and clear all paused state so next Start is a fresh run."""
        self._stop_auto_cycle()
        self._paused_remaining = 0
        self._paused_next_enable = True
        logger.info("Auto cycle reset")

    def _cancel_auto_timer(self, key: str):
        """Cancel a pending auto timer by key."""
        old_timer = self._auto_timer_ids.pop(key, None)
        if old_timer is not None:
            old_timer.stop()

    def _start_countdown(self, secs: int, action: str, next_enable: bool):
        """Start or restart the countdown display."""
        self._stop_countdown()
        self._countdown_remaining = secs
        self._countdown_action = action
        self._countdown_next_enable = next_enable
        self._update_countdown_label()
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._countdown_tick)
        self._countdown_timer.start(1000)

    def _countdown_tick(self):
        """Tick the countdown every second."""
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._stop_countdown()
            return
        self._update_countdown_label()

    def _update_countdown_label(self):
        """Update the countdown label text."""
        self.auto_countdown_label.setText(
            f"{self._countdown_action} {self._countdown_remaining}s"
        )

    def _stop_countdown(self):
        """Stop the countdown and clear the label."""
        if self._countdown_timer is not None:
            self._countdown_timer.stop()
            self._countdown_timer = None
        self._countdown_remaining = 0
        self._countdown_action = ""
        self.auto_countdown_label.setText("")

    def _enable_arm(self, arm: str, enable: bool):
        """Enable or disable arm using controller API / 通过控制器API使能或禁用手臂"""
        if not self.arm.is_ready():
            QMessageBox.warning(self, t("common.warning"), t("teach.err_not_connected"))
            return

        # Cancel any pending auto timers for this arm (both directions)
        self._cancel_auto_timer(f"reenable:{arm}")
        self._cancel_auto_timer(f"disable:{arm}")

        arm_side = ArmSide.LEFT if arm == "left" else ArmSide.RIGHT
        arm_name = t("hardware.left_arm") if arm == "left" else t("hardware.right_arm")
        action = "Enabling" if enable else "Disabling"

        self.arm_status_label.setText(f"{action} {arm_name}...")
        self.arm_status_label.setStyleSheet("color: orange;")

        def do_enable():
            try:
                success = self.arm.enable_arm(arm_side, enable)
                def update_ui():
                    if success:
                        status = "Enabled" if enable else "Disabled"
                        color = "green" if enable else "blue"
                        self.arm_status_label.setText(f"{arm_name} {status}")
                        self.arm_status_label.setStyleSheet(f"color: {color};")
                        # Record pose on enable if feature is on
                        # 2s delay: lets joints settle + debounces left/right into one record
                        if enable and self._record_on_enable_flag:
                            if self._record_on_enable_timer is not None:
                                self._record_on_enable_timer.stop()
                            self._record_on_enable_timer = QTimer(self)
                            self._record_on_enable_timer.setSingleShot(True)
                            self._record_on_enable_timer.timeout.connect(self._do_record_on_enable)
                            self._record_on_enable_timer.start(2000)
                        # Auto timers only run when cycle is started
                        if self._auto_cycle_running:
                            # Schedule auto re-enable if disabling and feature is on
                            if not enable and self._auto_reenable:
                                secs = self.auto_reenable_spin.value()
                                self._schedule_auto_timer(f"reenable:{arm}", secs, arm, True)
                            # Schedule auto disable if enabling and feature is on
                            if enable and self._auto_disable:
                                secs = self.auto_disable_spin.value()
                                self._schedule_auto_timer(f"disable:{arm}", secs, arm, False)
                    else:
                        self.arm_status_label.setText(f"{arm_name} failed")
                        self.arm_status_label.setStyleSheet("color: red;")
                    QTimer.singleShot(3000, lambda: self.arm_status_label.setText(""))
                QTimer.singleShot(0, update_ui)
            except Exception as e:
                def update_ui_err():
                    self.arm_status_label.setText(f"Error: {e}")
                    self.arm_status_label.setStyleSheet("color: red;")
                    QTimer.singleShot(3000, lambda: self.arm_status_label.setText(""))
                QTimer.singleShot(0, update_ui_err)
                logger.exception("Enable arm failed")

        threading.Thread(target=do_enable, daemon=True).start()

    def _schedule_auto_timer(self, key: str, secs: int, arm: str, enable: bool):
        """Schedule an automatic enable/disable of an arm after secs seconds."""
        arm_name = t("hardware.left_arm") if arm == "left" else t("hardware.right_arm")
        action_label = "Enable" if enable else "Disable"
        logger.info(f"Auto {action_label.lower()} {arm_name} in {secs}s")
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._auto_timer_fire(key, arm, enable))
        timer.start(secs * 1000)
        self._auto_timer_ids[key] = timer
        # Start countdown (use the longest pending timer so the label stays visible)
        if secs >= self._countdown_remaining:
            self._start_countdown(secs, action_label, enable)

    def _auto_timer_fire(self, key: str, arm: str, enable: bool):
        """Callback fired by an auto timer."""
        self._auto_timer_ids.pop(key, None)
        self._enable_arm(arm, enable)

    def _do_record_on_enable(self):
        """Auto-record a pose after an arm is enabled (uses current pose configs)."""
        self._record_on_enable_timer = None
        if self._current_step_index is None:
            self.pose_manager.add_step(self.pose_manager.next_default_step_name())
            self._current_step_index = len(self.pose_manager._steps) - 1
            self._update_steps_list()
        self._on_record_pose()
        logger.info("Auto-recorded pose on enable")

    def _on_get_both_positions(self):
        """Get positions of both arms / 获取双臂位置"""
        self.left_arm_panel._on_get_position()
        self.right_arm_panel._on_get_position()

    def _on_set_both_zero(self):
        """Set both arms entry fields to zero (does NOT move the robot) / 将双臂输入框设为零（不移动机器人）"""
        self.left_arm_panel._on_set_to_zero()
        self.right_arm_panel._on_set_to_zero()

    def _schedule_update(self):
        """Schedule periodic update using QTimer."""
        self._display_timer = QTimer(self)
        self._display_timer.timeout.connect(self._safe_update_display)
        self._display_timer.start(50)  # ~20Hz

    def _safe_update_display(self):
        """Update display, tolerating errors so timer keeps running."""
        try:
            self._update_display()
        except Exception as e:
            logger.debug("Dual arm display update failed: %s", e)

    def _update_display(self):
        """Update display / 更新显示"""
        try:
            left_joints = self.arm.get_left_joints()
            right_joints = self.arm.get_right_joints()
        except Exception as e:
            logger.debug("Dual arm get joints: %s", e)
            return
        try:
            self.left_arm_panel.update_display(left_joints)
            self.right_arm_panel.update_display(right_joints)
        except Exception as e:
            logger.debug("Dual arm panel update_display: %s", e)

    def _update_steps_list(self):
        """Refresh steps listbox."""
        self.steps_listbox.clear()
        for step in self.pose_manager._steps:
            n = len(step.poses)
            self.steps_listbox.addItem(f"{step.name} ({n} poses)")

    def _refresh_file_list(self):
        """Scan data directory for JSON files and populate the file combobox."""
        files = DualArmPoseManager.scan_data_dir()
        self._file_paths = {fname: fpath for fname, fpath in files}
        filenames = list(self._file_paths.keys())
        self.file_combobox.blockSignals(True)
        self.file_combobox.clear()
        self.file_combobox.addItems(filenames)
        # Select the currently loaded file
        current_file = os.path.basename(self.pose_manager._poses_file)
        idx = self.file_combobox.findText(current_file)
        if idx >= 0:
            self.file_combobox.setCurrentIndex(idx)
        elif filenames:
            self.file_combobox.setCurrentIndex(0)
        self.file_combobox.blockSignals(False)

    def _on_file_selected(self, index=None):
        """Handle file selection from combobox -- load the file and refresh steps."""
        selected = self.file_combobox.currentText()
        if not selected or selected not in self._file_paths:
            return
        filepath = self._file_paths[selected]
        # Recreate pose manager with the new file
        self.pose_manager = DualArmPoseManager(poses_file=filepath)
        self._current_step_index = None
        self._update_steps_list()
        self._refresh_poses_in_step()
        logger.info(f"Loaded file: {selected} ({len(self.pose_manager._steps)} steps)")

    def _on_load_file(self):
        """Load poses/steps from a file chosen via dialog."""
        from config.settings import DUAL_ARM_STEPS_DIR as DATA_DIR
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load File", str(DATA_DIR),
            "JSON files (*.json);;All files (*.*)"
        )
        if not filepath:
            return
        reply = QMessageBox.question(self, t("common.confirm"), t("dual_arm.replace_or_append"),
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        replace = (reply == QMessageBox.StandardButton.Yes)
        success = self.pose_manager.load_file(filepath, replace=replace)
        if success:
            if replace:
                self.pose_manager.set_poses_file(filepath)
            self._current_step_index = None
            self._update_steps_list()
            self._refresh_poses_in_step()
            self._refresh_file_list()
            fname = os.path.basename(filepath)
            idx = self.file_combobox.findText(fname)
            if idx >= 0:
                self.file_combobox.setCurrentIndex(idx)
            QMessageBox.information(self, t("common.info"), t("dual_arm.file_loaded").replace("{name}", fname))

    def _on_save_file(self):
        """Save current steps/poses to the currently selected file."""
        self.pose_manager._save_poses()
        fname = os.path.basename(self.pose_manager._poses_file)
        QMessageBox.information(self, t("common.info"), t("dual_arm.file_saved").replace("{name}", fname))

    def _on_save_as(self):
        """Save current steps/poses to a new file via dialog."""
        from config.settings import DUAL_ARM_STEPS_DIR as DATA_DIR
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save As", str(DATA_DIR),
            "JSON files (*.json);;All files (*.*)"
        )
        if not filepath:
            return
        self.pose_manager.set_poses_file(filepath)
        self.pose_manager._save_poses()
        self._refresh_file_list()
        fname = os.path.basename(filepath)
        idx = self.file_combobox.findText(fname)
        if idx >= 0:
            self.file_combobox.setCurrentIndex(idx)
        QMessageBox.information(self, t("common.info"), t("dual_arm.file_saved").replace("{name}", fname))

    def _on_step_select(self):
        """When a step is selected, show its poses."""
        row = self.steps_listbox.currentRow()
        if row >= 0:
            self._current_step_index = row
        else:
            self._current_step_index = None
        self._refresh_poses_in_step()

    def _refresh_poses_in_step(self):
        """Refresh poses listbox for current step."""
        self.pose_listbox.clear()
        if self._current_step_index is None:
            return
        step = self.pose_manager.get_step(self._current_step_index)
        if step:
            for p in step.poses:
                # Show arm type: L=left, R=right, B=both
                arm_indicator = {"left": "L", "right": "R", "both": "B"}.get(p.arm, "B")
                # Show hand indicator if hand positions are included
                hand_indicator = "+H" if (p.hand_positions or p.right_hand_positions) else ""
                # Show gripper indicator if gripper data is included
                gripper_indicator = "+G" if (p.gripper_position is not None) else ""
                # Format: "PoseName [B+H+G]" or "PoseName [L]" etc.
                display_text = f"{p.name} [{arm_indicator}{hand_indicator}{gripper_indicator}]"
                self.pose_listbox.addItem(display_text)

    def _on_pose_double_click(self):
        """Show pose details when double-clicked."""
        if self._current_step_index is None:
            return
        sel = self.pose_listbox.currentRow()
        if sel < 0:
            return
        pose = self.pose_manager.get_pose_in_step(self._current_step_index, sel)
        if not pose:
            return

        # Build detail text
        arm_text = {"left": "Left Arm Only", "right": "Right Arm Only", "both": "Both Arms"}.get(pose.arm, "Both Arms")
        has_hand = bool(pose.hand_positions or pose.right_hand_positions)

        details = []
        details.append(f"Pose Name: {pose.name}")
        details.append(f"Arm: {arm_text}")
        details.append(f"Hand Data: {'Yes' if has_hand else 'No'}")
        details.append("")

        # Left arm joints
        if pose.arm in ["left", "both"]:
            details.append("Left Arm Joints (rad):")
            for i, j in enumerate(pose.joints):
                details.append(f"  J{i+1}: {j:.4f}")
            details.append("")

        # Right arm joints
        if pose.arm in ["right", "both"] and pose.right_joints:
            details.append("Right Arm Joints (rad):")
            for i, j in enumerate(pose.right_joints):
                details.append(f"  J{i+1}: {j:.4f}")
            details.append("")

        # Hand positions
        if pose.hand_positions:
            details.append("Left Hand (0-255):")
            finger_names = ["Thumb", "Index", "Middle", "Ring", "Pinky", "Thumb Rot"]
            for i, val in enumerate(pose.hand_positions):
                name = finger_names[i] if i < len(finger_names) else f"F{i+1}"
                details.append(f"  {name}: {val}")
            details.append("")

        if pose.right_hand_positions:
            details.append("Right Hand (0-255):")
            finger_names = ["Thumb", "Index", "Middle", "Ring", "Pinky", "Thumb Rot"]
            for i, val in enumerate(pose.right_hand_positions):
                name = finger_names[i] if i < len(finger_names) else f"F{i+1}"
                details.append(f"  {name}: {val}")
            details.append("")

        # Gripper data
        if pose.gripper_position is not None:
            details.append("Gripper (LMG-90):")
            details.append(f"  Position: {pose.gripper_position}%")
            if pose.gripper_torque is not None:
                details.append(f"  Torque: {pose.gripper_torque}%")

        # Show in a dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Pose Details: {pose.name}")
        dialog.resize(300, 400)

        dlg_layout = QVBoxLayout(dialog)

        text_widget = QTextEdit()
        text_widget.setReadOnly(True)
        text_widget.setFont(QFont("Courier", 10))
        text_widget.setPlainText("\n".join(details))
        dlg_layout.addWidget(text_widget)

        close_btn = QPushButton(t("common.close"))
        close_btn.clicked.connect(dialog.accept)
        dlg_layout.addWidget(close_btn)

        dialog.exec()

    def _increment_pose_name(self):
        """Auto-increment pose name (Pose_1 -> Pose_2, etc.)."""
        name = self.pose_name_edit.text().strip()
        if name and name[-1].isdigit():
            i = len(name) - 1
            while i >= 0 and name[i].isdigit():
                i -= 1
            prefix = name[: i + 1]
            num = int(name[i + 1 :]) + 1
            self.pose_name_edit.setText(f"{prefix}{num}")
        else:
            self.pose_name_edit.setText(f"{name or 'Pose'}_1")

    def _on_add_step(self):
        """Add a new step with current name or default."""
        name = self.step_name_edit.text().strip() or self.pose_manager.next_default_step_name()
        self.pose_manager.add_step(name)
        self._update_steps_list()
        idx = len(self.pose_manager._steps) - 1
        self.steps_listbox.setCurrentRow(idx)
        self._current_step_index = idx
        self._refresh_poses_in_step()
        self.step_name_edit.setText(self.pose_manager.next_default_step_name())

    def _on_delete_step(self):
        """Delete selected step."""
        if self._current_step_index is None:
            QMessageBox.information(self, t("common.info"), t("dual_arm.msg_select_step_first"))
            return
        step = self.pose_manager.get_step(self._current_step_index)
        if step:
            reply = QMessageBox.question(
                self, t("common.confirm"),
                t("dual_arm.msg_delete_step_confirm").replace("{name}", step.name),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.pose_manager.delete_step(self._current_step_index)
                self._current_step_index = None
                self._update_steps_list()
                self._refresh_poses_in_step()

    def _on_rename_step(self):
        """Rename the selected step."""
        if self._current_step_index is None:
            QMessageBox.information(self, t("common.info"), t("dual_arm.msg_select_step_first"))
            return
        step = self.pose_manager.get_step(self._current_step_index)
        if not step:
            return
        new_name, ok = QInputDialog.getText(
            self,
            t("dual_arm.rename_step"),
            t("dual_arm.rename_step_prompt"),
            text=step.name
        )
        if ok and new_name and new_name.strip():
            step.name = new_name.strip()
            self.pose_manager._autosave()
            self._update_steps_list()
            # Re-select the same step
            self.steps_listbox.setCurrentRow(self._current_step_index)

    def _on_save_step(self):
        """Export the selected step to a separate JSON file."""
        if self._current_step_index is None:
            QMessageBox.information(self, t("common.info"), t("dual_arm.msg_select_step_first"))
            return
        step = self.pose_manager.get_step(self._current_step_index)
        if not step:
            return
        from config.settings import DUAL_ARM_STEPS_DIR as DATA_DIR
        import json
        default_name = f"{step.name}.json"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Step", os.path.join(str(DATA_DIR), default_name),
            "JSON files (*.json);;All files (*.*)"
        )
        if not filepath:
            return
        try:
            data = {
                "version": "2.0",
                "created": datetime.now().isoformat(),
                "steps": [step.to_dict()],
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            fname = os.path.basename(filepath)
            self._refresh_file_list()
            QMessageBox.information(self, t("common.info"), t("dual_arm.step_saved").replace("{name}", fname))
        except Exception as e:
            logger.error(f"Failed to export step: {e}")
            QMessageBox.critical(self, t("common.error"), str(e)[:200])

    def _get_hand_positions_for_record(self):
        """Get current finger positions for both hands for recording.

        Uses get_actual_*_positions() which reads from hardware, syncs sliders,
        and falls back to slider values if hardware read fails or returns zeros.
        If hand_widget is not available, reads directly from controller.
        """
        left_hand = right_hand = None
        if not self._include_hand:
            return left_hand, right_hand
        try:
            if hasattr(self, "hand_widget"):
                left_hand = self.hand_widget.get_actual_left_positions()
                right_hand = self.hand_widget.get_actual_right_positions()
            elif self.hand and self.hand.is_ready():
                left_real = self.hand.get_finger_positions_real("left")
                right_real = self.hand.get_finger_positions_real("right")
                if left_real is not None:
                    left_hand = [int(x) for x in left_real]
                if right_real is not None:
                    right_hand = [int(x) for x in right_real]
        except Exception as e:
            logger.debug("Get hand positions for record: %s", e)
        return left_hand, right_hand

    def _get_hand_positions_for_single_arm(self, arm_str: str):
        """Get hand positions for a single arm."""
        try:
            if hasattr(self, "hand_widget"):
                if arm_str == "left":
                    return self.hand_widget.get_actual_left_positions()
                else:
                    return self.hand_widget.get_actual_right_positions()
            elif self.hand and self.hand.is_ready():
                real = self.hand.get_finger_positions_real(arm_str)
                if real is not None:
                    return [int(x) for x in real]
        except Exception as e:
            logger.debug("Get hand positions for single arm: %s", e)
        return None

    def _get_gripper_state_for_record(self):
        """Get current gripper position and torque for recording.

        Returns (position, torque) as integers 0-100, or (None, None) if not available.
        """
        if not self._include_gripper:
            return None, None
        if not self.gripper:
            return None, None
        try:
            status = self.gripper.get_status()
            if status:
                return int(status.get('position', 0)), int(status.get('torque', 0))
        except Exception as e:
            logger.debug("Get gripper state for record: %s", e)
        return None, None

    def _on_record_pose(self):
        """Record current arms (and optionally hands) as a pose in the selected step."""
        if self._current_step_index is None:
            QMessageBox.warning(self, t("common.warning"), t("dual_arm.msg_select_or_add_step"))
            return

        arm_sel = self.record_arm_combo.currentText()
        if arm_sel == "both":
            self._record_dual_arm_pose()
        else:
            self._record_single_arm_pose(arm_sel)

    def _record_single_arm_pose(self, arm_str: str):
        """Record pose for a single arm (matching reference format)."""
        name = self.pose_name_edit.text().strip() or self.pose_manager.next_default_pose_name(self._current_step_index)

        state = self.arm.get_arm_state(arm_str)
        if state is None:
            QMessageBox.warning(self, t("common.warning"), f"No {arm_str} arm state available")
            return

        hand_positions = None
        if self._include_hand:
            hand_positions = self._get_hand_positions_for_single_arm(arm_str)

        # Gripper (right arm only)
        grip_pos, grip_torque = (None, None)
        if arm_str == "right":
            grip_pos, grip_torque = self._get_gripper_state_for_record()

        speed = self.arm._speed_factor
        accel = self.arm._accel_factor

        pose = RecordedPose(
            name=name,
            timestamp=datetime.now().isoformat(),
            arm=arm_str,
            pose_type="joint",
            joints=list(state.get('joints', [0.0] * 7)),
            position=dict(state.get('position', {})),
            euler=dict(state.get('euler', {})),
            speed=speed,
            acceleration=accel,
            hand_positions=hand_positions,
            gripper_position=grip_pos,
            gripper_torque=grip_torque,
        )
        self.pose_manager.add_pose_to_step(self._current_step_index, pose)
        self._increment_pose_name()
        self._refresh_poses_in_step()
        self._update_steps_list()
        logger.info(f"Recorded single-arm pose '{name}' (arm={arm_str})")

    def _record_dual_arm_pose(self):
        """Record a dual-arm pose containing data for both arms (matching reference format)."""
        name = self.pose_name_edit.text().strip() or self.pose_manager.next_default_pose_name(self._current_step_index)

        left_state = self.arm.get_arm_state("left")
        if left_state is None:
            QMessageBox.warning(self, t("common.warning"), "No left arm state available")
            return

        right_state = self.arm.get_arm_state("right")
        if right_state is None:
            QMessageBox.warning(self, t("common.warning"), "No right arm state available")
            return

        left_hand = right_hand = None
        if self._include_hand:
            left_hand, right_hand = self._get_hand_positions_for_record()

        grip_pos, grip_torque = self._get_gripper_state_for_record()

        speed = self.arm._speed_factor
        accel = self.arm._accel_factor

        pose = RecordedPose(
            name=name,
            timestamp=datetime.now().isoformat(),
            arm="both",
            pose_type="joint",
            joints=list(left_state.get('joints', [0.0] * 7)),
            position=dict(left_state.get('position', {})),
            euler=dict(left_state.get('euler', {})),
            speed=speed,
            acceleration=accel,
            hand_positions=left_hand,
            right_joints=list(right_state.get('joints', [0.0] * 7)),
            right_position=dict(right_state.get('position', {})),
            right_euler=dict(right_state.get('euler', {})),
            right_speed=speed,
            right_acceleration=accel,
            right_hand_positions=right_hand,
            gripper_position=grip_pos,
            gripper_torque=grip_torque,
        )
        self.pose_manager.add_pose_to_step(self._current_step_index, pose)
        self._increment_pose_name()
        self._refresh_poses_in_step()
        self._update_steps_list()
        logger.info(f"Recorded dual-arm pose '{name}'")

    def _record_current_pose_from_hand_tab(self):
        """Record current arms + current hand positions as pose (call from hand tab)."""
        if self._current_step_index is None:
            self.pose_manager.add_step(self.pose_manager.next_default_step_name())
            self._current_step_index = len(self.pose_manager._steps) - 1
            self._update_steps_list()
        self._include_hand = True
        self.include_hand_chk.setChecked(True)
        name = self.pose_manager.next_default_pose_name(self._current_step_index)
        self.pose_name_edit.setText(name)

        left_state = self.arm.get_arm_state("left")
        right_state = self.arm.get_arm_state("right")

        left_hand = right_hand = None
        if hasattr(self, "hand_widget"):
            left_hand = self.hand_widget.get_actual_left_positions()
            right_hand = self.hand_widget.get_actual_right_positions()

        grip_pos, grip_torque = self._get_gripper_state_for_record()

        speed = self.arm._speed_factor
        pose = RecordedPose(
            name=name,
            timestamp=datetime.now().isoformat(),
            arm="both",
            pose_type="joint",
            joints=list(left_state['joints']) if left_state else list(self.arm.get_left_joints()),
            position=dict(left_state.get('position', {})) if left_state else {},
            euler=dict(left_state.get('euler', {})) if left_state else {},
            speed=speed,
            acceleration=0.5,
            hand_positions=left_hand,
            right_joints=list(right_state['joints']) if right_state else list(self.arm.get_right_joints()),
            right_position=dict(right_state.get('position', {})) if right_state else {},
            right_euler=dict(right_state.get('euler', {})) if right_state else {},
            right_speed=speed,
            right_acceleration=0.5,
            right_hand_positions=right_hand,
            gripper_position=grip_pos,
            gripper_torque=grip_torque,
        )
        self.pose_manager.add_pose_to_step(self._current_step_index, pose)
        self.pose_name_edit.setText(self.pose_manager.next_default_pose_name(self._current_step_index))
        self._refresh_poses_in_step()
        self._update_steps_list()
        QMessageBox.information(self, t("common.info"), t("dual_arm.msg_recorded_pose").replace("{name}", name))

    def _apply_pose_hands(self, pose: RecordedPose):
        """Apply hand/finger positions from pose to hardware. Tolerates hand errors."""
        if not self.hand or not self.hand.is_ready():
            return
        try:
            if pose.hand_positions:
                self.hand.set_finger_positions(HandSide.LEFT, [float(x) for x in pose.hand_positions])
            if pose.right_hand_positions:
                self.hand.set_finger_positions(HandSide.RIGHT, [float(x) for x in pose.right_hand_positions])
        except Exception as e:
            logger.debug("Apply pose hands: %s", e)

    def _apply_pose_gripper(self, pose: RecordedPose):
        """Apply gripper position from pose to hardware. Tolerates gripper errors."""
        if not self.gripper or not self.gripper.is_ready():
            return
        if pose.gripper_position is None:
            return
        try:
            self.gripper.set_opening(int(pose.gripper_position))
        except Exception as e:
            logger.debug("Apply pose gripper: %s", e)

    def _wait_end_effectors_settled(self, pose, grip_timeout: float = 1.5,
                                    hand_timeout: float = 0.8):
        """Wait for the gripper/hand to finish — ONLY when their commanded value changed
        from the previous pose (so unchanged poses don't stall), and capped by a short
        timeout per actuator. Interruptible by Stop; returns early once at target."""
        stop = self._execution_stop

        # --- Gripper (right / both poses) ---
        if (pose.arm in ("both", "right") and pose.gripper_position is not None
                and self.gripper and self.gripper.is_ready()):
            target = int(pose.gripper_position)
            if target != self._last_grip_cmd:
                self._last_grip_cmd = target
                deadline = time.monotonic() + grip_timeout
                while not stop.is_set() and time.monotonic() < deadline:
                    try:
                        if abs(self.gripper.get_position() - target) <= 4:
                            break
                    except Exception:
                        break
                    stop.wait(0.05)

        # --- Hand fingers (per side, 0-255) ---
        if self.hand and self.hand.is_ready():
            targets = []
            if pose.arm == "both":
                if pose.hand_positions:
                    targets.append(("left", [float(x) for x in pose.hand_positions]))
                if pose.right_hand_positions:
                    targets.append(("right", [float(x) for x in pose.right_hand_positions]))
            elif pose.arm == "left":
                if pose.hand_positions:
                    targets.append(("left", [float(x) for x in pose.hand_positions]))
            else:  # right
                if pose.hand_positions:
                    targets.append(("right", [float(x) for x in pose.hand_positions]))
            for side, tgt in targets:
                if self._last_hand_cmd.get(side) == tgt:
                    continue  # unchanged — no wait
                self._last_hand_cmd[side] = list(tgt)
                deadline = time.monotonic() + hand_timeout
                while not stop.is_set() and time.monotonic() < deadline:
                    try:
                        real = self.hand.get_finger_positions_real(side)
                    except Exception:
                        break
                    if real and all(abs(a - b) <= 15 for a, b in zip(real, tgt)):
                        break
                    stop.wait(0.05)

    def _execute_pose(self, pose: RecordedPose):
        """Execute a single pose, respecting which arm(s) should move.

        For dual-arm ("both") poses: left hand+arm and right hand+arm run in
        parallel threads so both sides move simultaneously (matches reference).
        For single-arm poses: hand then arm on the selected side only.
        Supports hand_only pose_type (skip arm movement).
        """
        speed = self.arm._speed_factor
        accel = self.arm._accel_factor
        hand_ready = self.hand and self.hand.is_ready()
        is_hand_only = (pose.pose_type == "hand_only")

        if pose.arm == "both":
            return self._execute_dual_arm_pose(pose)

        # Single-arm execution
        arm_side = ArmSide.LEFT if pose.arm == "left" else ArmSide.RIGHT

        # Execute hand positions if available
        if hand_ready and pose.hand_positions:
            hand_side = HandSide.LEFT if pose.arm == "left" else HandSide.RIGHT
            try:
                self.hand.set_finger_positions(hand_side, [float(x) for x in pose.hand_positions])
            except Exception as e:
                logger.debug(f"Hand move error: {e}")

        # Apply gripper for right arm poses
        if pose.arm == "right":
            self._apply_pose_gripper(pose)

        # Skip arm movement for hand-only poses
        if is_hand_only:
            return

        # Move arm
        self.arm._move_arm_joints(arm_side, pose.joints, speed, accel)

    def _execute_dual_arm_pose(self, pose: RecordedPose):
        """Execute a dual-arm pose with both arms moving in parallel (matches reference)."""
        speed = self.arm._speed_factor
        accel = self.arm._accel_factor
        right_speed = speed
        right_accel = accel
        hand_ready = self.hand and self.hand.is_ready()
        is_hand_only = (pose.pose_type == "hand_only")

        def _left_side():
            try:
                if hand_ready and pose.hand_positions:
                    self.hand.set_finger_positions(
                        HandSide.LEFT, [float(x) for x in pose.hand_positions])
                if not is_hand_only:
                    self.arm._move_arm_joints(ArmSide.LEFT, pose.joints, speed, accel)
            except Exception as e:
                logger.error(f"Left side execute failed: {e}")

        def _right_side():
            try:
                if hand_ready and pose.right_hand_positions:
                    self.hand.set_finger_positions(
                        HandSide.RIGHT, [float(x) for x in pose.right_hand_positions])
                self._apply_pose_gripper(pose)
                if not is_hand_only and pose.right_joints:
                    self.arm._move_arm_joints(ArmSide.RIGHT, pose.right_joints, right_speed, right_accel)
            except Exception as e:
                logger.error(f"Right side execute failed: {e}")

        lt = threading.Thread(target=_left_side, daemon=True)
        rt = threading.Thread(target=_right_side, daemon=True)
        lt.start()
        rt.start()
        lt.join()
        rt.join()

    def _pose_to_waypoint(self, pose: RecordedPose):
        """Convert a RecordedPose to a {'left','right'} joint waypoint for smooth replay.

        A None side means that arm holds position. Hand-only poses move neither arm.
        """
        if pose.pose_type == "hand_only":
            return {"left": None, "right": None}
        if pose.arm == "both":
            return {
                "left": list(pose.joints) if pose.joints else None,
                "right": list(pose.right_joints) if pose.right_joints else None,
            }
        if pose.arm == "left":
            return {"left": list(pose.joints) if pose.joints else None, "right": None}
        # single right arm: pose.joints holds the right arm joints
        return {"left": None, "right": list(pose.joints) if pose.joints else None}

    def _smooth_execute_poses(self, poses, effort_limit="__spin__") -> bool:
        """Replay a list of poses as one continuous, non-stopping motion.

        Arm joints are streamed via the controller's joint_follow path; hand and
        gripper actions fire as each pose is reached. effort_limit defaults to the
        UI contact-limit spin; pass an explicit value (e.g. for the startup pose).

        Returns True if the full sequence completed, False if it was stopped early
        (user stop, or contact that persisted past hold_timeout).
        """
        if not poses:
            return True
        waypoints = [self._pose_to_waypoint(p) for p in poses]
        # Reset end-effector command tracking so only *changes* to the gripper/hand
        # are waited on during this sequence (unchanged poses don't stall).
        self._last_grip_cmd = None
        self._last_hand_cmd = {}

        def on_waypoint(idx):
            pose = poses[idx]
            try:
                if pose.arm == "both":
                    self._apply_pose_hands(pose)
                    self._apply_pose_gripper(pose)
                elif pose.arm == "left":
                    if self.hand and self.hand.is_ready() and pose.hand_positions:
                        self.hand.set_finger_positions(
                            HandSide.LEFT, [float(x) for x in pose.hand_positions])
                else:  # right
                    if self.hand and self.hand.is_ready() and pose.hand_positions:
                        self.hand.set_finger_positions(
                            HandSide.RIGHT, [float(x) for x in pose.hand_positions])
                    self._apply_pose_gripper(pose)
            except Exception as e:
                logger.debug("Smooth replay hand/gripper apply failed: %s", e)
            # Wait for the gripper/hand to finish — but only when they actually changed
            # at this pose, and with tight time caps, so smooth motion isn't stalled.
            try:
                self._wait_end_effectors_settled(pose)
            except Exception as e:
                logger.debug("End-effector settle wait failed: %s", e)

        if effort_limit == "__spin__":
            effort_limit = self.effort_limit_spin.value() or None
        return bool(self.arm.smooth_replay(
            waypoints,
            speed_factor=self.arm._speed_factor,
            stop_event=self._execution_stop,
            on_waypoint=on_waypoint,
            effort_limit=effort_limit,
            hold_timeout=10.0,  # hold/wait on contact, then stop the replay after 10 s
        ))

    def _load_initial_pose(self):
        """Load the dedicated startup poses from config/initial_pose.json — a protected
        copy independent of the editable pose list. Returns a list of RecordedPose or None."""
        import json
        path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "initial_pose.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            poses = [RecordedPose.from_dict(p) for p in data.get("poses", [])]
            return poses or None
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.warning("Failed to load dedicated initial pose (%s); falling back", e)
            return None

    def _find_step_index(self, name: str):
        """Index of the first step matching this name (case-insensitive), or None."""
        target = name.strip().lower()
        for i, s in enumerate(self.pose_manager._steps):
            if (s.name or "").strip().lower() == target:
                return i
        return None

    def run_startup_sequence(self, step_name: str = "initial_pose"):
        """Startup init: enable both arms, ease to zero, then run the named step smoothly
        at full speed. Runs in a background thread; no-op if the arm isn't connected.
        Interruptible via Stop (the execution-stop event)."""
        def seq():
            if not (self.arm and self.arm.is_ready()):
                logger.warning("Startup sequence skipped: dual arm not connected")
                return
            self._execution_stop.clear()
            try:
                # Startup always uses the default contact limit (3.5), regardless of
                # the UI spin (which now defaults to 0 / off for manual runs).
                effort_limit = 3.5

                logger.info("Startup: enabling both arms")
                self.arm.enable_arm(ArmSide.LEFT, True)
                self.arm.enable_arm(ArmSide.RIGHT, True)
                if self._execution_stop.wait(1.5):   # let enable settle (or Stop)
                    return

                logger.info("Startup: easing to zero")
                self.arm.smooth_replay(
                    [{"left": [0.0] * 7, "right": [0.0] * 7}],
                    speed_factor=0.5, stop_event=self._execution_stop,
                    effort_limit=effort_limit, hold_timeout=10.0)
                if self._execution_stop.is_set():
                    return

                # Load the initialization poses from the dedicated, protected file
                # (config/initial_pose.json) so startup survives deletion of the
                # editable 'initial_pose' step. Fall back to the pose list if missing.
                poses = self._load_initial_pose()
                src = "config/initial_pose.json"
                if not poses:
                    idx = self._find_step_index(step_name)
                    step = self.pose_manager.get_step(idx) if idx is not None else None
                    poses = list(step.poses) if step and step.poses else None
                    src = f"pose-list step '{step_name}'"
                if not poses:
                    logger.warning("Startup: no initial pose available "
                                   "(dedicated file or pose list); done after zero")
                    return

                logger.info("Startup: running initial pose from %s (%d poses) "
                            "smooth at speed 1.5", src, len(poses))
                prev_speed = self.arm._speed_factor
                self.arm._speed_factor = 1.5
                try:
                    ok = self._smooth_execute_poses(poses, effort_limit=effort_limit)
                finally:
                    self.arm._speed_factor = prev_speed
                logger.info("Startup sequence %s", "complete" if ok else "stopped early")
            except Exception as e:
                logger.exception("Startup sequence failed: %s", e)

        threading.Thread(target=seq, daemon=True).start()

    def _set_card_visual(self, card, ready: bool, detail: str, partial: bool = False):
        """Drive a status card's dot + status text + detail line from live readiness."""
        from gui.theme import STATE_COLORS
        if partial:
            color = STATE_COLORS.get("connecting", "#ffc107")
            text = t("state.partial")
        elif ready:
            color = STATE_COLORS.get("connected", "#28a745")
            text = t("state.connected")
        else:
            color = STATE_COLORS.get("disconnected", "#6c757d")
            text = t("state.disconnected")
        try:
            card.indicator.set_color(color)
            card.status_label.setText(text)
            card.connection_label.setText(detail)
        except Exception as e:
            logger.debug("Status card visual update failed: %s", e)

    def _refresh_status_cards(self):
        """Poll live connection state and update the arm/hands/gripper indicators."""
        # Dual arm
        try:
            arm_ready = bool(self.arm and self.arm.is_ready())
            ip = getattr(self.arm, "_ip", "") or ""
            self._set_card_visual(self.arm_card, arm_ready,
                                  f"{t('connection.arm_ip')}: {ip}" if ip else "")
        except Exception as e:
            logger.debug("Arm status refresh failed: %s", e)

        # Hands (per side)
        try:
            l = bool(self.hand and self.hand.is_hand_connected("left"))
            r = bool(self.hand and self.hand.is_hand_connected("right"))
            mark = lambda ok: "✓" if ok else "✗"
            detail = f"{t('hardware.left')}: {mark(l)}   {t('hardware.right')}: {mark(r)}"
            self._set_card_visual(self.hand_card, (l or r), detail, partial=(l != r))
        except Exception as e:
            logger.debug("Hand status refresh failed: %s", e)

        # Gripper
        try:
            g = bool(self.gripper and self.gripper.is_ready())
            port = getattr(self.gripper, "_port", "") or ""
            self._set_card_visual(self.gripper_card, g,
                                  f"{t('gripper.port')}: {port}" if port else "")
        except Exception as e:
            logger.debug("Gripper status refresh failed: %s", e)

    def _update_torque_readout(self):
        """Update the live max-torque readout; colour it relative to the contact limit."""
        try:
            if not (self.arm and getattr(self.arm, "_connected", False)):
                self.torque_readout.setText(t("dual_arm.live_torque") + ": --")
                self.torque_readout.setStyleSheet("")
                return
            mx = float(self.arm.get_effort_status().get("max", 0.0))
            self.torque_readout.setText(t("dual_arm.live_torque") + f": {mx:.2f}")
            lim = self.effort_limit_spin.value()
            if lim and mx >= lim:
                self.torque_readout.setStyleSheet("color: red; font-weight: bold;")
            elif lim and mx >= lim * 0.7:
                self.torque_readout.setStyleSheet("color: orange;")
            else:
                self.torque_readout.setStyleSheet("")
        except Exception as e:
            logger.debug("Torque readout update failed: %s", e)

    def _stop_execution(self):
        """Signal any running step/pose execution to stop after the current pose."""
        self._execution_stop.set()
        logger.info("Execution stop requested")

    def _on_execute_pose_one(self):
        """Execute selected pose (one by one)."""
        if self._current_step_index is None:
            return
        sel = self.pose_listbox.currentRow()
        if sel < 0:
            QMessageBox.information(self, t("common.info"), t("dual_arm.msg_select_pose_execute"))
            return
        pose = self.pose_manager.get_pose_in_step(self._current_step_index, sel)
        if not pose:
            return
        self._execution_stop.clear()
        def run():
            try:
                if self.smooth_cb.isChecked():
                    self._smooth_execute_poses([pose])
                else:
                    self._execute_pose(pose)
            except Exception as e:
                logger.exception("Execute pose failed: %s", e)
        threading.Thread(target=run, daemon=True).start()

    def _on_delete_pose_from_step(self):
        """Delete selected pose(s) from current step."""
        if self._current_step_index is None:
            return
        sel_items = self.pose_listbox.selectedIndexes()
        sel = sorted(set(idx.row() for idx in sel_items))
        if not sel:
            return
        step = self.pose_manager.get_step(self._current_step_index)
        if not step:
            return
        if len(sel) == 1:
            idx = sel[0]
            if 0 <= idx < len(step.poses):
                name = step.poses[idx].name
                reply = QMessageBox.question(
                    self, t("common.confirm"),
                    t("dual_arm.msg_delete_pose_confirm").replace("{name}", name),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.pose_manager.delete_pose_from_step(self._current_step_index, idx)
                    self._refresh_poses_in_step()
                    self._update_steps_list()
        else:
            valid = [i for i in sel if 0 <= i < len(step.poses)]
            if not valid:
                return
            names = [step.poses[i].name for i in valid]
            names_str = "\n".join(f"  * {n}" for n in names)
            msg = (t("dual_arm.msg_delete_poses_confirm")
                   .replace("{count}", str(len(valid)))
                   .replace("{names}", names_str))
            reply = QMessageBox.question(
                self, t("common.confirm"), msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                for i in sorted(valid, reverse=True):
                    self.pose_manager.delete_pose_from_step(self._current_step_index, i)
                self._refresh_poses_in_step()
                self._update_steps_list()

    def _on_pose_move_up(self):
        """Move all selected poses up by one within the current step."""
        if self._current_step_index is None:
            return
        sel = sorted(set(idx.row() for idx in self.pose_listbox.selectedIndexes()))
        if not sel or sel[0] == 0:
            return
        step = self.pose_manager.get_step(self._current_step_index)
        if not step:
            return
        # Process ascending so each swap doesn't disturb the next one
        for idx in sel:
            self.pose_manager.move_pose_in_step(self._current_step_index, idx, -1)
        new_sel = [i - 1 for i in sel]
        self._refresh_poses_in_step()
        for i in new_sel:
            self.pose_listbox.setCurrentRow(i)

    def _on_pose_move_down(self):
        """Move all selected poses down by one within the current step."""
        if self._current_step_index is None:
            return
        sel = sorted(set(idx.row() for idx in self.pose_listbox.selectedIndexes()))
        if not sel:
            return
        step = self.pose_manager.get_step(self._current_step_index)
        if not step or sel[-1] == len(step.poses) - 1:
            return
        # Process descending so each swap doesn't disturb the next one
        for idx in sorted(sel, reverse=True):
            self.pose_manager.move_pose_in_step(self._current_step_index, idx, +1)
        new_sel = [i + 1 for i in sel]
        self._refresh_poses_in_step()
        for i in new_sel:
            self.pose_listbox.setCurrentRow(i)

    def _on_execute_step(self):
        """Execute all poses in the selected step with delay."""
        if self._current_step_index is None:
            QMessageBox.information(self, t("common.info"), t("dual_arm.msg_select_step_first"))
            return
        step = self.pose_manager.get_step(self._current_step_index)
        if not step or not step.poses:
            QMessageBox.information(self, t("common.info"), t("dual_arm.msg_step_has_no_poses"))
            return
        delay = max(0.0, self.delay_spin.value())
        self._execution_stop.clear()

        def run():
            try:
                if self.smooth_cb.isChecked():
                    completed = self._smooth_execute_poses(list(step.poses))
                    if completed:
                        logger.info(f"Smooth-replayed step '{step.name}' ({len(step.poses)} poses)")
                    else:
                        logger.warning(f"Step '{step.name}' stopped early (contact/stop); "
                                       f"remaining poses not executed")
                    return
                for i, pose in enumerate(step.poses):
                    if self._execution_stop.is_set():
                        logger.info("Step execution stopped by user")
                        break
                    self._execute_pose(pose)
                    if i < len(step.poses) - 1 and delay > 0:
                        self._execution_stop.wait(timeout=delay)
                logger.info(f"Executed step '{step.name}' ({len(step.poses)} poses)")
            except Exception as e:
                logger.exception("Execute step failed: %s", e)

        threading.Thread(target=run, daemon=True).start()

    def _on_execute_all_steps(self):
        """Execute all steps in sequence with delay between poses."""
        delay = max(0.0, self.delay_spin.value())
        self._execution_stop.clear()

        def run():
            try:
                if self.smooth_cb.isChecked():
                    all_poses = [p for step in self.pose_manager._steps for p in step.poses]
                    completed = self._smooth_execute_poses(all_poses)
                    if completed:
                        logger.info(f"Smooth-replayed all steps ({len(all_poses)} poses)")
                    else:
                        logger.warning("All-steps smooth replay stopped early "
                                       "(contact/stop); remaining poses not executed")
                    return
                for step in self.pose_manager._steps:
                    for pose in step.poses:
                        if self._execution_stop.is_set():
                            logger.info("All-steps execution stopped by user")
                            return
                        self._execute_pose(pose)
                        if delay > 0:
                            self._execution_stop.wait(timeout=delay)
                logger.info("Executed all steps")
            except Exception as e:
                logger.exception("Execute all steps failed: %s", e)

        threading.Thread(target=run, daemon=True).start()

    def update_language(self):
        """Update text for language change / 更新语言变化的文本"""
        # Update status cards
        self.arm_card.update_language()
        self.hand_card.update_language()
        self.gripper_card.update_language()
        self._refresh_status_cards()

        # Update notebook tabs
        self.notebook.setTabText(0, t("dual_arm.arm_control"))
        self.notebook.setTabText(1, t("hardware.linker_hand"))
        self.notebook.setTabText(2, t("hardware.gripper"))
        self.notebook.setTabText(3, t("pose.list"))

        # Update arm control section
        self.arm_ctrl_frame.setTitle(t("dual_arm.arm_control"))
        self.enable_left_btn.setText(t("dual_arm.enable_left"))
        self.disable_left_btn.setText(t("dual_arm.disable_left"))
        self.enable_right_btn.setText(t("dual_arm.enable_right"))
        self.disable_right_btn.setText(t("dual_arm.disable_right"))
        if self._auto_cycle_running:
            self.auto_cycle_btn.setText(t("dual_arm.auto_cycle_stop"))
        else:
            self.auto_cycle_btn.setText(t("dual_arm.auto_cycle_start"))
        self.auto_cycle_reset_btn.setText(t("dual_arm.auto_cycle_reset"))
        self.auto_reenable_chk.setText(t("dual_arm.auto_reenable"))
        self.auto_reenable_sec_label.setText(t("dual_arm.auto_reenable_sec"))
        self.auto_disable_chk.setText(t("dual_arm.auto_disable"))
        self.auto_disable_sec_label.setText(t("dual_arm.auto_disable_sec"))

        # Update arm panels
        self.left_arm_panel.update_language()
        self.right_arm_panel.update_language()

        # Update top buttons
        self.get_both_btn.setText(t("dual_arm.get_both_positions"))
        self.set_both_zero_btn.setText(t("dual_arm.set_both_zero"))

        # Update hand tab record button and hint
        if hasattr(self, "hand_record_btn"):
            self.hand_record_btn.setText(t("dual_arm.record_from_hand_tab"))
            self.hand_record_hint.setText(" -> " + t("pose.list"))
        # Update hand widget (L6 hands content)
        if hasattr(self, 'hand_widget'):
            self.hand_widget.update_language()

        # Update gripper tab
        if hasattr(self, "gripper_record_btn"):
            self.gripper_record_btn.setText(t("dual_arm.record_from_gripper_tab"))
            self.gripper_record_hint.setText(" -> " + t("pose.list"))
        if hasattr(self, "gripper_widget"):
            self.gripper_widget.update_language()

        # Update poses tab -- file selector
        if hasattr(self, "file_label"):
            self.file_label.setText(t("dual_arm.file_label"))
            self.load_file_btn.setText(t("dual_arm.load_file"))
            self.save_file_btn.setText(t("dual_arm.save_file"))
            self.save_as_btn.setText(t("dual_arm.save_as"))

        # Update poses tab (steps + poses in step + all labels/buttons)
        if hasattr(self, "steps_frame"):
            self.steps_frame.setTitle(t("dual_arm.steps"))
            self.step_name_label.setText(t("pose.name") + ":")
            self.add_step_btn.setText(t("dual_arm.add_step"))
            self.execute_step_btn.setText(t("dual_arm.execute_step"))
            self.delete_step_btn.setText(t("dual_arm.delete_step"))
            self.rename_step_btn.setText(t("dual_arm.rename_step"))
            self.save_step_btn.setText(t("dual_arm.save_step"))
        if hasattr(self, "poses_frame"):
            self.poses_frame.setTitle(t("dual_arm.poses_in_step"))
            self.pose_name_label.setText(t("pose.name") + ":")
            self.record_arm_label.setText(t("dual_arm.record_arm") + ":")
            self.include_hand_chk.setText(t("dual_arm.include_hand"))
            self.include_gripper_chk.setText(t("dual_arm.include_gripper"))
            self.record_pose_btn.setText(t("dual_arm.record_pose"))
            self.record_on_enable_cb.setText(t("dual_arm.record_on_enable"))
            self.pose_move_btn.setText(t("dual_arm.execute_pose"))
            self.pose_delete_btn.setText(t("pose.delete"))
            self.pose_up_btn.setText(t("dual_arm.pose_move_up"))
            self.pose_down_btn.setText(t("dual_arm.pose_move_down"))
            self.pose_refresh_btn.setText(t("common.refresh"))
        if hasattr(self, "delay_label"):
            self.delay_label.setText(t("dual_arm.delay_sec") + ":")
            self.speed_label.setText(t("dual_arm.speed") + ":")
            self.accel_label.setText(t("dual_arm.accel") + ":")
            self.execute_all_steps_btn.setText(t("dual_arm.execute_all_steps"))
            self.smooth_cb.setText(t("dual_arm.smooth_replay"))
            self.smooth_cb.setToolTip(t("dual_arm.smooth_replay_tip"))
            self.contact_label.setText(t("dual_arm.contact_limit") + ":")
            self.effort_limit_spin.setToolTip(t("dual_arm.contact_limit_tip"))
            self.torque_readout.setToolTip(t("dual_arm.live_torque_tip"))
