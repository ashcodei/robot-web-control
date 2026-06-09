"""
Gripper Widget Module (PySide6)
夹爪部件模块

GUI widget for LMG-90 gripper control.
用于LMG-90夹爪控制的GUI部件。
"""

import threading
from gui.qt_imports import (
    QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QSlider, QProgressBar,
    Qt, QTimer,
)
from .gripper_controller import GripperController
from config.i18n import t
from app_core.logger import get_logger
from gui.widgets import HardwareStatusCard

logger = get_logger(__name__)

# Button style helpers
_GREEN_STYLE = "background-color: #27ae60; color: white; font-weight: bold; padding: 4px 8px;"
_RED_STYLE = "background-color: #c0392b; color: white; font-weight: bold; padding: 4px 8px;"
_DARK_STYLE = "background-color: #2c2c2c; color: white; font-weight: bold; padding: 4px 6px;"
_PURPLE_STYLE = "background-color: #8e44ad; color: white; font-weight: bold; padding: 4px 6px;"


class GripperWidget(QWidget):
    """
    Widget for gripper control.
    用于夹爪控制的部件。
    """

    def __init__(self, parent, controller: GripperController = None):
        super().__init__(parent)

        self.gripper = controller or GripperController()
        self._build_ui()
        self._schedule_update()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Status card
        self.status_card = HardwareStatusCard(
            self, "gripper", "hardware.gripper", self.gripper
        )
        layout.addWidget(self.status_card)

        # Main control area - two columns
        columns = QHBoxLayout()

        # Left panel
        left_panel = QVBoxLayout()
        self._build_opening_section(left_panel)
        self._build_force_section(left_panel)
        left_panel.addStretch()
        columns.addLayout(left_panel, stretch=1)

        # Right panel
        right_panel = QVBoxLayout()
        self._build_status_section(right_panel)
        self._build_speed_section(right_panel)
        right_panel.addStretch()
        columns.addLayout(right_panel, stretch=1)

        layout.addLayout(columns)

    def _build_opening_section(self, parent_layout):
        self.opening_frame = QGroupBox(t("gripper.opening"))
        layout = QVBoxLayout(self.opening_frame)

        # Slider
        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("0%"))
        self.opening_slider = QSlider(Qt.Orientation.Horizontal)
        self.opening_slider.setRange(0, 100)
        self.opening_slider.setValue(50)
        self.opening_slider.valueChanged.connect(self._on_opening_change)
        slider_row.addWidget(self.opening_slider, stretch=1)
        slider_row.addWidget(QLabel("100%"))
        layout.addLayout(slider_row)

        # Value display
        value_row = QHBoxLayout()
        self.opening_value_label = QLabel(t("gripper.target") + ":")
        value_row.addWidget(self.opening_value_label)
        self.opening_display = QLabel("50%")
        self.opening_display.setStyleSheet("font-size: 11pt; font-weight: bold; color: #1a6ec2;")
        value_row.addWidget(self.opening_display)
        value_row.addStretch()
        layout.addLayout(value_row)

        # Quick buttons
        btn_row = QHBoxLayout()
        self.close_btn = QPushButton(t("gripper.close") + " (0%)")
        self.close_btn.setStyleSheet(_RED_STYLE)
        self.close_btn.clicked.connect(lambda: self._set_opening(0))
        btn_row.addWidget(self.close_btn)

        for pct in [25, 50, 75]:
            btn = QPushButton(f"{pct}%")
            btn.setStyleSheet(_DARK_STYLE)
            btn.clicked.connect(lambda checked, v=pct: self._set_opening(v))
            btn_row.addWidget(btn)

        self.open_btn = QPushButton(t("gripper.open") + " (100%)")
        self.open_btn.setStyleSheet(_GREEN_STYLE)
        self.open_btn.clicked.connect(lambda: self._set_opening(100))
        btn_row.addWidget(self.open_btn)
        layout.addLayout(btn_row)

        parent_layout.addWidget(self.opening_frame)

    def _build_force_section(self, parent_layout):
        self.force_frame = QGroupBox(t("gripper.force"))
        layout = QVBoxLayout(self.force_frame)

        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("0%"))
        self.force_slider = QSlider(Qt.Orientation.Horizontal)
        self.force_slider.setRange(0, 100)
        self.force_slider.setValue(50)
        self.force_slider.valueChanged.connect(self._on_force_change)
        slider_row.addWidget(self.force_slider, stretch=1)
        slider_row.addWidget(QLabel("100%"))
        layout.addLayout(slider_row)

        value_row = QHBoxLayout()
        self.force_value_label = QLabel(t("gripper.target_force") + ":")
        value_row.addWidget(self.force_value_label)
        self.force_display = QLabel("50%")
        self.force_display.setStyleSheet("font-size: 11pt; font-weight: bold; color: #8e44ad;")
        value_row.addWidget(self.force_display)
        value_row.addStretch()
        layout.addLayout(value_row)

        btn_row = QHBoxLayout()
        force_presets = [
            ("gripper.light", 20), ("gripper.medium", 50),
            ("gripper.strong", 80), ("gripper.max", 100),
        ]
        self._force_btns = []
        for key, val in force_presets:
            btn = QPushButton(f"{t(key)} ({val}%)")
            btn.setStyleSheet(_PURPLE_STYLE)
            btn.clicked.connect(lambda checked, v=val: self._set_force(v))
            btn_row.addWidget(btn)
            self._force_btns.append((btn, key, val))
        layout.addLayout(btn_row)

        parent_layout.addWidget(self.force_frame)

    def _build_status_section(self, parent_layout):
        self.status_frame = QGroupBox(t("gripper.current_status"))
        layout = QVBoxLayout(self.status_frame)

        # Position
        pos_row = QHBoxLayout()
        self.pos_label = QLabel(t("gripper.position") + " (40005):")
        pos_row.addWidget(self.pos_label)
        pos_row.addStretch()
        self.pos_value = QLabel("--")
        self.pos_value.setStyleSheet("font-size: 14pt; font-weight: bold; color: #27ae60;")
        pos_row.addWidget(self.pos_value)
        layout.addLayout(pos_row)

        self.pos_progress = QProgressBar()
        self.pos_progress.setRange(0, 100)
        layout.addWidget(self.pos_progress)

        # Torque
        torque_row = QHBoxLayout()
        self.torque_label = QLabel(t("gripper.torque") + " (40006):")
        torque_row.addWidget(self.torque_label)
        torque_row.addStretch()
        self.torque_value = QLabel("--")
        self.torque_value.setStyleSheet("font-size: 14pt; font-weight: bold; color: #c0392b;")
        torque_row.addWidget(self.torque_value)
        layout.addLayout(torque_row)

        self.torque_progress = QProgressBar()
        self.torque_progress.setRange(0, 100)
        layout.addWidget(self.torque_progress)

        parent_layout.addWidget(self.status_frame)

    def _build_speed_section(self, parent_layout):
        self.speed_frame = QGroupBox(t("gripper.speed"))
        layout = QVBoxLayout(self.speed_frame)

        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("0%"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(0, 100)
        self.speed_slider.setValue(50)
        self.speed_slider.valueChanged.connect(self._on_speed_change)
        slider_row.addWidget(self.speed_slider, stretch=1)
        slider_row.addWidget(QLabel("100%"))
        layout.addLayout(slider_row)

        value_row = QHBoxLayout()
        self.speed_value_label = QLabel(t("gripper.speed") + ":")
        value_row.addWidget(self.speed_value_label)
        self.speed_display = QLabel("50%")
        self.speed_display.setStyleSheet("font-size: 11pt; font-weight: bold; color: #3498db;")
        value_row.addWidget(self.speed_display)
        value_row.addStretch()
        layout.addLayout(value_row)

        parent_layout.addWidget(self.speed_frame)

    # ── Update loop ──

    def _schedule_update(self):
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_display)
        self._update_timer.start(500)

    def _update_display(self):
        try:
            status = self.gripper.get_status()
            pos = status.get('position', 0)
            self.pos_value.setText(f"{pos}%")
            self.pos_progress.setValue(pos)

            torque = status.get('torque', 0)
            self.torque_value.setText(f"{torque}%")
            self.torque_progress.setValue(torque)
        except Exception:
            pass

    # ── Callbacks ──

    def _bg(self, func, *args):
        threading.Thread(target=func, args=args, daemon=True).start()

    def _on_opening_change(self, value):
        self.opening_display.setText(f"{value}%")
        self._bg(self.gripper.set_opening, value)

    def _set_opening(self, value):
        self.opening_slider.setValue(value)
        self.opening_display.setText(f"{value}%")
        self._bg(self.gripper.set_opening, value)

    def _on_force_change(self, value):
        self.force_display.setText(f"{value}%")
        self._bg(self.gripper.set_force, value)

    def _set_force(self, value):
        self.force_slider.setValue(value)
        self.force_display.setText(f"{value}%")
        self._bg(self.gripper.set_force, value)

    def _on_speed_change(self, value):
        self.speed_display.setText(f"{value}%")
        self._bg(self.gripper.set_speed, value)

    # ── Language ──

    def update_language(self):
        try:
            self.status_card.update_language()
            self.opening_frame.setTitle(t("gripper.opening"))
            self.opening_value_label.setText(t("gripper.target") + ":")
            self.close_btn.setText(t("gripper.close") + " (0%)")
            self.open_btn.setText(t("gripper.open") + " (100%)")

            self.force_frame.setTitle(t("gripper.force"))
            self.force_value_label.setText(t("gripper.target_force") + ":")
            for btn, key, val in self._force_btns:
                btn.setText(f"{t(key)} ({val}%)")

            self.status_frame.setTitle(t("gripper.current_status"))
            self.pos_label.setText(t("gripper.position") + " (40005):")
            self.torque_label.setText(t("gripper.torque") + " (40006):")

            self.speed_frame.setTitle(t("gripper.speed"))
            self.speed_value_label.setText(t("gripper.speed") + ":")
        except Exception:
            pass
