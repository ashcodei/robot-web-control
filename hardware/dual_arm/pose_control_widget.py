"""
Pose Control Widget Module
位姿控制部件模块

PySide6 widget for pose list management and playback.
用于位姿列表管理和回放的 PySide6 部件。
"""

import json
import os
from datetime import datetime
from gui.qt_imports import (
    QWidget, QGroupBox, QLabel, QPushButton, QLineEdit, QComboBox,
    QCheckBox, QListWidget, QListWidgetItem, QDialog, QDoubleSpinBox,
    QHBoxLayout, QVBoxLayout, QGridLayout, QFormLayout,
    QMessageBox, QFileDialog, QTimer,
)
from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass, asdict, field


@dataclass
class RecordedPose:
    """Represents a recorded robot pose / 记录的机器人位姿"""
    name: str
    timestamp: str
    arm: str  # "left", "right", or "both"
    pose_type: str  # "joint" or "tcp" or "force_grab"
    joints: List[float]  # Left arm joints (or primary arm)
    position: Dict[str, float] = field(default_factory=dict)  # x, y, z
    euler: Dict[str, float] = field(default_factory=dict)  # roll, pitch, yaw
    speed: float = 0.5
    acceleration: float = 0.5
    # Hand positions (optional)
    hand_positions: Optional[List[int]] = None
    hand_type: Optional[str] = None
    hand_side: Optional[str] = None
    # Force grab settings (optional)
    force_grab: Optional[Dict] = None
    # Trajectory recording (optional)
    trajectory_file: Optional[str] = None
    trajectory_duration: Optional[float] = None
    trajectory_points: Optional[int] = None
    # Right arm data (for dual-arm "both" poses)
    right_joints: Optional[List[float]] = None
    right_position: Optional[Dict[str, float]] = None
    right_euler: Optional[Dict[str, float]] = None
    right_speed: Optional[float] = None
    right_acceleration: Optional[float] = None
    right_hand_positions: Optional[List[int]] = None
    right_hand_type: Optional[str] = None
    # Gripper state (optional, right arm LMG-90, 0-100%)
    gripper_position: Optional[int] = None
    gripper_torque: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary / 转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'RecordedPose':
        """Create from dictionary / 从字典创建"""
        # Filter valid keys
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)


@dataclass
class Step:
    """Represents a step containing multiple poses / 包含多个位姿的步骤"""
    name: str
    poses: List[RecordedPose]
    created: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary / 转换为字典"""
        return {
            'name': self.name,
            'poses': [p.to_dict() for p in self.poses],
            'created': self.created
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Step':
        """Create from dictionary / 从字典创建"""
        poses = [RecordedPose.from_dict(p) for p in data.get('poses', [])]
        return cls(name=data['name'], poses=poses, created=data.get('created', ''))


class PoseListWidget(QGroupBox):
    """
    Widget for displaying and managing a list of poses.
    用于显示和管理位姿列表的部件。
    """

    def __init__(self, parent, on_play_callback: Optional[Callable[[RecordedPose], None]] = None,
                 language: str = "en", **kwargs):
        """
        Initialize pose list widget.
        初始化位姿列表部件。

        Args:
            parent: Parent widget
            on_play_callback: Callback when pose is played
            language: Display language
        """
        title = "Pose List" if language == "en" else "位姿列表"
        super().__init__(title, parent)

        self._language = language
        self._on_play = on_play_callback
        self.poses: List[RecordedPose] = []
        self._selected_index: Optional[int] = None

        self._create_widgets()

    def _create_widgets(self):
        """Create child widgets / 创建子部件"""
        main_layout = QVBoxLayout(self)

        # Listbox with scrollbar
        self.listbox = QListWidget()
        self.listbox.setFont(self.listbox.font())  # Keep default; Courier optional
        main_layout.addWidget(self.listbox)

        self.listbox.currentRowChanged.connect(self._on_select)
        self.listbox.doubleClicked.connect(self._on_double_click)

        # Control buttons
        btn_layout = QHBoxLayout()
        main_layout.addLayout(btn_layout)

        play_text = "Play" if self._language == "en" else "执行"
        self.play_btn = QPushButton(play_text)
        self.play_btn.clicked.connect(self._play_selected)
        btn_layout.addWidget(self.play_btn)

        edit_text = "Edit" if self._language == "en" else "编辑"
        edit_btn = QPushButton(edit_text)
        edit_btn.clicked.connect(self._edit_selected)
        btn_layout.addWidget(edit_btn)

        delete_text = "Delete" if self._language == "en" else "删除"
        delete_btn = QPushButton(delete_text)
        delete_btn.clicked.connect(self._delete_selected)
        btn_layout.addWidget(delete_btn)

        up_text = "Up" if self._language == "en" else "上移"
        up_btn = QPushButton(up_text)
        up_btn.clicked.connect(self._move_up)
        btn_layout.addWidget(up_btn)

        down_text = "Down" if self._language == "en" else "下移"
        down_btn = QPushButton(down_text)
        down_btn.clicked.connect(self._move_down)
        btn_layout.addWidget(down_btn)

        btn_layout.addStretch()

        # Info label
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: gray;")
        main_layout.addWidget(self.info_label)

    def _on_select(self, row: int):
        """Handle listbox selection / 处理列表框选择"""
        if row >= 0 and row < len(self.poses):
            self._selected_index = row
            pose = self.poses[self._selected_index]
            info = f"Arm: {pose.arm} | Type: {pose.pose_type} | Speed: {pose.speed}"
            self.info_label.setText(info)
        else:
            self._selected_index = None
            self.info_label.setText("")

    def _on_double_click(self):
        """Handle double-click to play / 处理双击播放"""
        self._play_selected()

    def _play_selected(self):
        """Play selected pose / 执行选中的位姿"""
        if self._selected_index is not None and self._on_play:
            pose = self.poses[self._selected_index]
            self._on_play(pose)

    def _edit_selected(self):
        """Edit selected pose / 编辑选中的位姿"""
        if self._selected_index is None:
            return

        pose = self.poses[self._selected_index]

        # Simple edit dialog for name and speed
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Pose" if self._language == "en" else "编辑位姿")
        dialog.resize(300, 150)

        form_layout = QFormLayout(dialog)

        name_edit = QLineEdit(pose.name)
        form_layout.addRow("Name:" if self._language == "en" else "名称:", name_edit)

        speed_spin = QDoubleSpinBox()
        speed_spin.setRange(0.0, 10.0)
        speed_spin.setSingleStep(0.1)
        speed_spin.setValue(pose.speed)
        form_layout.addRow("Speed:" if self._language == "en" else "速度:", speed_spin)

        save_btn = QPushButton("Save" if self._language == "en" else "保存")
        form_layout.addRow(save_btn)

        def save():
            pose.name = name_edit.text()
            pose.speed = speed_spin.value()
            self._refresh_list()
            dialog.accept()

        save_btn.clicked.connect(save)
        dialog.exec()

    def _delete_selected(self):
        """Delete selected pose / 删除选中的位姿"""
        if self._selected_index is None:
            return

        title = "Confirm" if self._language == "en" else "确认"
        msg = "Delete this pose?" if self._language == "en" else "删除此位姿?"
        reply = QMessageBox.question(self, title, msg,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            del self.poses[self._selected_index]
            self._selected_index = None
            self._refresh_list()

    def _move_up(self):
        """Move selected pose up / 上移选中的位姿"""
        if self._selected_index is None or self._selected_index == 0:
            return

        idx = self._selected_index
        self.poses[idx], self.poses[idx - 1] = self.poses[idx - 1], self.poses[idx]
        self._selected_index -= 1
        self._refresh_list()
        self.listbox.setCurrentRow(self._selected_index)

    def _move_down(self):
        """Move selected pose down / 下移选中的位姿"""
        if self._selected_index is None or self._selected_index >= len(self.poses) - 1:
            return

        idx = self._selected_index
        self.poses[idx], self.poses[idx + 1] = self.poses[idx + 1], self.poses[idx]
        self._selected_index += 1
        self._refresh_list()
        self.listbox.setCurrentRow(self._selected_index)

    def _refresh_list(self):
        """Refresh listbox display / 刷新列表框显示"""
        self.listbox.clear()
        for i, pose in enumerate(self.poses):
            arm_icon = {"left": "L", "right": "R", "both": "B"}.get(pose.arm, "?")
            text = f"{i+1:02d}. [{arm_icon}] {pose.name}"
            self.listbox.addItem(text)

    def add_pose(self, pose: RecordedPose):
        """Add pose to list / 添加位姿到列表"""
        self.poses.append(pose)
        self._refresh_list()

    def clear_poses(self):
        """Clear all poses / 清除所有位姿"""
        self.poses.clear()
        self._selected_index = None
        self._refresh_list()

    def get_poses(self) -> List[RecordedPose]:
        """Get all poses / 获取所有位姿"""
        return self.poses.copy()

    def set_poses(self, poses: List[RecordedPose]):
        """Set poses list / 设置位姿列表"""
        self.poses = poses.copy()
        self._selected_index = None
        self._refresh_list()


class PoseControlWidget(QWidget):
    """
    Main pose control widget with recording, list, and playback.
    包含录制、列表和回放的主位姿控制部件。
    """

    def __init__(self, parent,
                 on_record_callback: Optional[Callable[[], RecordedPose]] = None,
                 on_play_callback: Optional[Callable[[RecordedPose], None]] = None,
                 language: str = "en", **kwargs):
        """
        Initialize pose control widget.
        初始化位姿控制部件。

        Args:
            parent: Parent widget
            on_record_callback: Callback to get current pose for recording
            on_play_callback: Callback when pose is played
            language: Display language
        """
        super().__init__(parent)

        self._language = language
        self._on_record = on_record_callback
        self._on_play = on_play_callback
        self._playback_running = False

        self._create_widgets()

    def _create_widgets(self):
        """Create child widgets / 创建子部件"""
        main_layout = QVBoxLayout(self)

        # Recording controls
        record_frame = QGroupBox("Record" if self._language == "en" else "录制")
        main_layout.addWidget(record_frame)
        record_layout = QVBoxLayout(record_frame)

        record_inner = QHBoxLayout()
        record_layout.addLayout(record_inner)

        record_inner.addWidget(QLabel("Name:" if self._language == "en" else "名称:"))
        self.pose_name_edit = QLineEdit("Pose_001")
        self.pose_name_edit.setMaximumWidth(120)
        record_inner.addWidget(self.pose_name_edit)

        record_inner.addWidget(QLabel("Arm:" if self._language == "en" else "手臂:"))
        self.arm_combo = QComboBox()
        self.arm_combo.addItems(["left", "right", "both"])
        self.arm_combo.setCurrentText("both")
        self.arm_combo.setMaximumWidth(80)
        record_inner.addWidget(self.arm_combo)

        record_text = "Record" if self._language == "en" else "录制"
        record_btn = QPushButton(record_text)
        record_btn.clicked.connect(self._record_pose)
        record_inner.addWidget(record_btn)

        record_inner.addStretch()

        # Pose list
        self.pose_list = PoseListWidget(self, on_play_callback=self._play_pose, language=self._language)
        main_layout.addWidget(self.pose_list)

        # Playback controls
        playback_frame = QGroupBox("Playback" if self._language == "en" else "回放")
        main_layout.addWidget(playback_frame)
        playback_layout = QVBoxLayout(playback_frame)

        playback_inner = QHBoxLayout()
        playback_layout.addLayout(playback_inner)

        play_all_text = "Play All" if self._language == "en" else "全部执行"
        self.play_all_btn = QPushButton(play_all_text)
        self.play_all_btn.clicked.connect(self._play_all)
        playback_inner.addWidget(self.play_all_btn)

        loop_text = "Loop" if self._language == "en" else "循环"
        self.loop_cb = QCheckBox(loop_text)
        playback_inner.addWidget(self.loop_cb)

        stop_text = "Stop" if self._language == "en" else "停止"
        stop_btn = QPushButton(stop_text)
        stop_btn.clicked.connect(self._stop_playback)
        playback_inner.addWidget(stop_btn)

        playback_inner.addWidget(QLabel("Delay (s):" if self._language == "en" else "延时(秒):"))
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.0, 60.0)
        self.delay_spin.setSingleStep(0.1)
        self.delay_spin.setValue(0.5)
        self.delay_spin.setMaximumWidth(70)
        playback_inner.addWidget(self.delay_spin)

        playback_inner.addStretch()

        # File operations
        file_layout = QHBoxLayout()
        main_layout.addLayout(file_layout)

        load_text = "Load" if self._language == "en" else "加载"
        load_btn = QPushButton(load_text)
        load_btn.clicked.connect(self._load_poses)
        file_layout.addWidget(load_btn)

        save_text = "Save" if self._language == "en" else "保存"
        save_btn = QPushButton(save_text)
        save_btn.clicked.connect(self._save_poses)
        file_layout.addWidget(save_btn)

        clear_text = "Clear All" if self._language == "en" else "清除全部"
        clear_btn = QPushButton(clear_text)
        clear_btn.clicked.connect(self._clear_poses)
        file_layout.addWidget(clear_btn)

        file_layout.addStretch()

    def _record_pose(self):
        """Record current pose / 录制当前位姿"""
        if not self._on_record:
            QMessageBox.warning(self, "Warning", "No record callback configured")
            return

        pose = self._on_record()
        if pose:
            pose.name = self.pose_name_edit.text()
            pose.arm = self.arm_combo.currentText()
            pose.timestamp = datetime.now().isoformat()
            self.pose_list.add_pose(pose)

            # Auto-increment name
            self._increment_name()

    def _increment_name(self):
        """Auto-increment pose name / 自动递增位姿名称"""
        name = self.pose_name_edit.text()
        # Find trailing number
        i = len(name) - 1
        while i >= 0 and name[i].isdigit():
            i -= 1

        if i < len(name) - 1:
            prefix = name[:i + 1]
            num = int(name[i + 1:]) + 1
            width = len(name) - i - 1
            self.pose_name_edit.setText(f"{prefix}{num:0{width}d}")
        else:
            self.pose_name_edit.setText(f"{name}_2")

    def _play_pose(self, pose: RecordedPose):
        """Play single pose / 执行单个位姿"""
        if self._on_play:
            self._on_play(pose)

    def _play_all(self):
        """Play all poses sequentially / 顺序执行所有位姿"""
        if self._playback_running:
            return

        poses = self.pose_list.get_poses()
        if not poses:
            return

        self._playback_running = True
        self.play_all_btn.setEnabled(False)

        def play_sequence():
            import time
            from gui.signals import get_thread_bridge
            bridge = get_thread_bridge()
            while self._playback_running:
                for pose in poses:
                    if not self._playback_running:
                        break
                    if self._on_play:
                        bridge.gui_callback.emit(lambda p=pose: self._on_play(p))
                    time.sleep(self.delay_spin.value())

                if not self.loop_cb.isChecked():
                    break

            self._playback_running = False
            bridge.gui_callback.emit(lambda: self.play_all_btn.setEnabled(True))

        import threading
        threading.Thread(target=play_sequence, daemon=True).start()

    def _stop_playback(self):
        """Stop playback / 停止回放"""
        self._playback_running = False

    def _load_poses(self):
        """Load poses from file / 从文件加载位姿"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Poses", "",
            "JSON files (*.json);;All files (*.*)"
        )
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                poses = [RecordedPose.from_dict(p) for p in data]
                self.pose_list.set_poses(poses)
                QMessageBox.information(self, "Success", f"Loaded {len(poses)} poses")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load: {e}")

    def _save_poses(self):
        """Save poses to file / 保存位姿到文件"""
        poses = self.pose_list.get_poses()
        if not poses:
            QMessageBox.information(self, "Info", "No poses to save")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Poses", "poses.json",
            "JSON files (*.json);;All files (*.*)"
        )
        if filename:
            try:
                data = [p.to_dict() for p in poses]
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                QMessageBox.information(self, "Success", f"Saved {len(poses)} poses")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def _clear_poses(self):
        """Clear all poses / 清除所有位姿"""
        reply = QMessageBox.question(self, "Confirm", "Clear all poses?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.pose_list.clear_poses()

    def update_language(self, language: str):
        """Update display language / 更新显示语言"""
        self._language = language
