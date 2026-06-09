"""
RL Recording Widget Module
强化学习录制部件模块

PySide6 widget for RL data recording controls.
RL 数据录制控制的 PySide6 部件。
"""

from typing import Optional, List, Callable
from datetime import datetime

from gui.qt_imports import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QPushButton, QLineEdit, QCheckBox, QComboBox, QListWidget,
    QMessageBox, QFont, QTimer,
    QPainter, QColor, QPointF, Qt,
)
from gui.signals import get_thread_bridge

from .rl_recording import RLRecordingManager, RecordingState, Episode, TrajectoryPoint


class RecordingStatusWidget(QGroupBox):
    """
    Widget for displaying recording status.
    显示录制状态的部件。
    """

    def __init__(self, parent, language: str = "en"):
        """
        Initialize recording status widget.
        初始化录制状态部件。
        """
        title = "Recording Status" if language == "en" else "录制状态"
        super().__init__(title, parent)

        self._language = language
        self._indicator_on = False
        self._create_widgets()

    def _create_widgets(self):
        """Create child widgets / 创建子部件"""
        layout = QGridLayout(self)

        # State indicator
        state_label_text = "State:" if self._language == "en" else "状态:"
        layout.addWidget(QLabel(state_label_text), 0, 0)
        self.state_label = QLabel("IDLE")
        font = QFont("Arial", 10)
        font.setBold(True)
        self.state_label.setFont(font)
        layout.addWidget(self.state_label, 0, 1)

        # Episode info
        episode_label_text = "Episode:" if self._language == "en" else "回合:"
        layout.addWidget(QLabel(episode_label_text), 1, 0)
        self.episode_label = QLabel("--")
        layout.addWidget(self.episode_label, 1, 1)

        # Points count
        points_label_text = "Points:" if self._language == "en" else "点数:"
        layout.addWidget(QLabel(points_label_text), 2, 0)
        self.points_label = QLabel("0")
        layout.addWidget(self.points_label, 2, 1)

        # Duration
        duration_label_text = "Duration:" if self._language == "en" else "时长:"
        layout.addWidget(QLabel(duration_label_text), 3, 0)
        self.duration_label = QLabel("00:00")
        layout.addWidget(self.duration_label, 3, 1)

        # Recording indicator (custom painted widget)
        self.record_indicator = _IndicatorWidget(self)
        layout.addWidget(self.record_indicator, 0, 2, 2, 1)

    def update_state(self, state: RecordingState):
        """Update state display / 更新状态显示"""
        colors = {
            RecordingState.IDLE: ("IDLE", "gray"),
            RecordingState.RECORDING: ("RECORDING", "red"),
            RecordingState.PAUSED: ("PAUSED", "orange"),
            RecordingState.SAVING: ("SAVING", "blue"),
            RecordingState.ERROR: ("ERROR", "red"),
        }
        text, color = colors.get(state, ("UNKNOWN", "gray"))
        self.state_label.setText(text)
        self.state_label.setStyleSheet(f"color: {color};")

        # Update indicator
        if state == RecordingState.RECORDING:
            self._blink_indicator()
        elif state == RecordingState.PAUSED:
            self.record_indicator.set_color("orange", "darkorange")
        else:
            self.record_indicator.set_color("gray", "darkgray")

    def _blink_indicator(self):
        """Blink recording indicator / 闪烁录制指示器"""
        color = 'red' if self._indicator_on else '#ffcccc'
        self.record_indicator.set_color(color, 'darkred')
        self._indicator_on = not self._indicator_on

    def update_episode(self, episode_id: int, points: int, duration: float):
        """Update episode info / 更新回合信息"""
        self.episode_label.setText(f"#{episode_id}")
        self.points_label.setText(str(points))

        mins = int(duration) // 60
        secs = int(duration) % 60
        self.duration_label.setText(f"{mins:02d}:{secs:02d}")


class _IndicatorWidget(QWidget):
    """Small circle indicator widget for recording state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self._fill_color = QColor("gray")
        self._outline_color = QColor("darkgray")

    def set_color(self, fill: str, outline: str):
        """Set indicator colors and repaint."""
        self._fill_color = QColor(fill)
        self._outline_color = QColor(outline)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self._outline_color)
        painter.setBrush(self._fill_color)
        painter.drawEllipse(2, 2, 16, 16)
        painter.end()


class RLRecordingWidget(QWidget):
    """
    Main RL recording widget.
    主 RL 录制部件。
    """

    def __init__(self, parent, recording_manager: Optional[RLRecordingManager] = None,
                 language: str = "en", **kwargs):
        """
        Initialize RL recording widget.
        初始化 RL 录制部件。

        Args:
            parent: Parent widget
            recording_manager: RLRecordingManager instance
            language: Display language
        """
        super().__init__(parent)

        self._language = language
        self._manager = recording_manager or RLRecordingManager()

        # Poll timer
        self._poll_timer = None

        self._create_widgets()
        self._setup_callbacks()

    def _create_widgets(self):
        """Create child widgets / 创建子部件"""
        main_layout = QVBoxLayout(self)

        # Status display
        self.status_widget = RecordingStatusWidget(self, language=self._language)
        main_layout.addWidget(self.status_widget)

        # Configuration
        config_frame = QGroupBox("Settings" if self._language == "en" else "设置")
        config_layout = QGridLayout(config_frame)
        main_layout.addWidget(config_frame)

        rate_label_text = "Rate (Hz):" if self._language == "en" else "频率:"
        config_layout.addWidget(QLabel(rate_label_text), 0, 0)
        self.rate_entry = QLineEdit("30.0")
        self.rate_entry.setFixedWidth(60)
        config_layout.addWidget(self.rate_entry, 0, 1)

        max_label_text = "Max (s):" if self._language == "en" else "最大时长:"
        config_layout.addWidget(QLabel(max_label_text), 0, 2)
        self.max_length_entry = QLineEdit("300.0")
        self.max_length_entry.setFixedWidth(60)
        config_layout.addWidget(self.max_length_entry, 0, 3)

        images_text = "Images" if self._language == "en" else "图像"
        self.images_checkbox = QCheckBox(images_text)
        self.images_checkbox.setChecked(True)
        config_layout.addWidget(self.images_checkbox, 0, 4)

        apply_text = "Apply" if self._language == "en" else "应用"
        apply_btn = QPushButton(apply_text)
        apply_btn.clicked.connect(self._apply_config)
        config_layout.addWidget(apply_btn, 0, 5)

        # Control buttons
        control_frame = QGroupBox("Control" if self._language == "en" else "控制")
        control_layout = QHBoxLayout(control_frame)
        main_layout.addWidget(control_frame)

        # Start/Stop button (styled green)
        start_text = "Start Recording" if self._language == "en" else "开始录制"
        self.start_btn = QPushButton(start_text)
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #52c41a; color: white; font-weight: bold; font-size: 11pt; padding: 6px 12px; }"
        )
        self.start_btn.clicked.connect(self._toggle_recording)
        control_layout.addWidget(self.start_btn)

        # Pause button
        pause_text = "Pause" if self._language == "en" else "暂停"
        self.pause_btn = QPushButton(pause_text)
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.pause_btn.setEnabled(False)
        control_layout.addWidget(self.pause_btn)

        # Mark button (add marker during recording)
        mark_text = "Add Marker" if self._language == "en" else "添加标记"
        self.mark_btn = QPushButton(mark_text)
        self.mark_btn.clicked.connect(self._add_marker)
        self.mark_btn.setEnabled(False)
        control_layout.addWidget(self.mark_btn)

        control_layout.addStretch()

        # Episode list
        list_frame = QGroupBox("Episodes" if self._language == "en" else "回合列表")
        list_layout = QHBoxLayout(list_frame)
        main_layout.addWidget(list_frame, 1)  # stretch

        self.episode_listbox = QListWidget()
        courier_font = QFont("Courier", 10)
        self.episode_listbox.setFont(courier_font)
        self.episode_listbox.setMaximumHeight(140)
        list_layout.addWidget(self.episode_listbox)

        # Export controls
        export_layout = QHBoxLayout()
        main_layout.addLayout(export_layout)

        format_label_text = "Format:" if self._language == "en" else "格式:"
        export_layout.addWidget(QLabel(format_label_text))

        self.format_combo = QComboBox()
        self.format_combo.addItems(["json", "hdf5", "pickle"])
        self.format_combo.setFixedWidth(80)
        export_layout.addWidget(self.format_combo)

        export_text = "Export Selected" if self._language == "en" else "导出选中"
        export_btn = QPushButton(export_text)
        export_btn.clicked.connect(self._export_selected)
        export_layout.addWidget(export_btn)

        export_all_text = "Export All" if self._language == "en" else "导出全部"
        export_all_btn = QPushButton(export_all_text)
        export_all_btn.clicked.connect(self._export_all)
        export_layout.addWidget(export_all_btn)

        clear_text = "Clear All" if self._language == "en" else "清除全部"
        clear_btn = QPushButton(clear_text)
        clear_btn.clicked.connect(self._clear_all)
        export_layout.addWidget(clear_btn)

        export_layout.addStretch()

    def _setup_callbacks(self):
        """Setup manager callbacks / 设置管理器回调"""
        self._manager.add_state_change_callback(self._on_state_changed)
        self._manager.add_point_callback(self._on_point_added)

    def _apply_config(self):
        """Apply configuration / 应用配置"""
        self._manager.configure(
            record_rate=float(self.rate_entry.text()),
            include_images=self.images_checkbox.isChecked(),
            max_episode_length=float(self.max_length_entry.text())
        )

    def _toggle_recording(self):
        """Toggle recording state / 切换录制状态"""
        if self._manager.state == RecordingState.IDLE:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        """Start recording / 开始录制"""
        self._apply_config()

        metadata = {
            'timestamp': datetime.now().isoformat(),
            'rate': float(self.rate_entry.text()),
        }

        if self._manager.start_episode(metadata):
            stop_text = "Stop Recording" if self._language == "en" else "停止录制"
            self.start_btn.setText(stop_text)
            self.start_btn.setStyleSheet(
                "QPushButton { background-color: #ff4d4f; color: white; font-weight: bold; font-size: 11pt; padding: 6px 12px; }"
            )
            self.pause_btn.setEnabled(True)
            self.mark_btn.setEnabled(True)
            self._start_polling()

    def _stop_recording(self):
        """Stop recording / 停止录制"""
        episode = self._manager.stop_episode()

        start_text = "Start Recording" if self._language == "en" else "开始录制"
        self.start_btn.setText(start_text)
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #52c41a; color: white; font-weight: bold; font-size: 11pt; padding: 6px 12px; }"
        )
        self.pause_btn.setEnabled(False)
        self.mark_btn.setEnabled(False)
        self._stop_polling()

        if episode:
            self._update_episode_list()

    def _toggle_pause(self):
        """Toggle pause state / 切换暂停状态"""
        if self._manager.state == RecordingState.RECORDING:
            self._manager.pause()
            self.pause_btn.setText("Resume" if self._language == "en" else "恢复")
        elif self._manager.state == RecordingState.PAUSED:
            self._manager.resume()
            self.pause_btn.setText("Pause" if self._language == "en" else "暂停")

    def _add_marker(self):
        """Add marker to current recording / 在当前录制中添加标记"""
        if self._manager.current_episode:
            self._manager.current_episode.metadata.setdefault('markers', [])
            self._manager.current_episode.metadata['markers'].append({
                'timestamp': datetime.now().isoformat(),
                'point_index': len(self._manager.current_episode.points)
            })

    def _start_polling(self):
        """Start status polling / 开始状态轮询"""
        if self._poll_timer:
            return

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._update_status)
        self._poll_timer.start()

    def _stop_polling(self):
        """Stop status polling / 停止状态轮询"""
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer = None

    def _update_status(self):
        """Update status display / 更新状态显示"""
        self.status_widget.update_state(self._manager.state)

        episode = self._manager.current_episode
        if episode:
            import time
            duration = time.time() - episode.start_time
            self.status_widget.update_episode(episode.episode_id, len(episode.points), duration)

    def _on_state_changed(self, state: RecordingState):
        """Handle state change / 处理状态变化"""
        bridge = get_thread_bridge()
        bridge.gui_callback.emit(lambda: self.status_widget.update_state(state))

    def _on_point_added(self, point: TrajectoryPoint):
        """Handle point added / 处理点添加"""
        pass  # Handled by polling

    def _update_episode_list(self):
        """Update episode listbox / 更新回合列表"""
        self.episode_listbox.clear()
        for episode in self._manager.get_episodes():
            text = f"#{episode.episode_id:04d} | {len(episode.points):5d} pts | {episode.duration():.1f}s"
            self.episode_listbox.addItem(text)

    def _export_selected(self):
        """Export selected episode / 导出选中的回合"""
        items = self.episode_listbox.selectedItems()
        if not items:
            QMessageBox.warning(self, "Warning", "No episode selected")
            return

        selection_idx = self.episode_listbox.row(items[0])
        episodes = self._manager.get_episodes()
        if selection_idx < len(episodes):
            episode = episodes[selection_idx]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"episode_{episode.episode_id:04d}_{timestamp}"

            if self._manager.export_episode(episode, filename, self.format_combo.currentText()):
                QMessageBox.information(self, "Success", f"Exported to {filename}")
            else:
                QMessageBox.critical(self, "Error", "Export failed")

    def _export_all(self):
        """Export all episodes / 导出所有回合"""
        count = self._manager.export_all(self.format_combo.currentText())
        if count > 0:
            QMessageBox.information(self, "Success", f"Exported {count} episodes")
        else:
            QMessageBox.information(self, "Info", "No episodes to export")

    def _clear_all(self):
        """Clear all episodes / 清除所有回合"""
        result = QMessageBox.question(
            self, "Confirm", "Clear all recorded episodes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if result == QMessageBox.StandardButton.Yes:
            self._manager.clear_episodes()
            self._update_episode_list()

    def set_state_callback(self, callback: Callable[[], dict]):
        """Set robot state callback / 设置机器人状态回调"""
        self._manager.set_state_callback(callback)

    def set_action_callback(self, callback: Callable[[], dict]):
        """Set action callback / 设置动作回调"""
        self._manager.set_action_callback(callback)

    def update_language(self, language: str):
        """Update display language / 更新显示语言"""
        self._language = language

    def shutdown(self):
        """Clean shutdown / 清理关闭"""
        self._stop_polling()
        if self._manager.state == RecordingState.RECORDING:
            self._manager.stop_episode()
