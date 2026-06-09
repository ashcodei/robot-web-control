"""
Wok Widget Module (PySide6)
炒锅部件模块

GUI widget for wok control.
用于炒锅控制的GUI部件。
"""

import threading
from gui.qt_imports import (
    QWidget, QGroupBox, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QCheckBox, QSlider, QSpinBox,
    QMessageBox, Qt, QTimer,
)
from .wok_controller import WokController, WokPosition
from config.i18n import t
from app_core.logger import get_logger
from gui.widgets import HardwareStatusCard

logger = get_logger(__name__)

# Button styles
_POS_STYLE = "background-color: #2c2c2c; color: white; font-weight: bold; padding: 4px 10px;"
_UP_STYLE = "background-color: #1a6ec2; color: white; font-weight: bold; padding: 4px 10px;"
_DOWN_STYLE = "background-color: #c0392b; color: white; font-weight: bold; padding: 4px 10px;"
_MAX_UP_STYLE = "background-color: #27ae60; color: white; font-weight: bold; padding: 4px 10px;"
_SAUCE_STYLE = "background-color: #8e44ad; color: white; font-weight: bold; padding: 3px 6px;"
_RECIPE_STYLE = "background-color: #d35400; color: white; font-weight: bold; padding: 4px 8px;"


class WokWidget(QWidget):
    """
    Widget for wok control.
    用于炒锅控制的部件。
    """

    def __init__(self, parent, controller: WokController = None):
        super().__init__(parent)

        self.wok = controller or WokController()
        self._build_ui()
        self._schedule_update()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Status card
        self.status_card = HardwareStatusCard(self, "wok", "hardware.wok", self.wok)
        layout.addWidget(self.status_card)

        # Two columns
        columns = QHBoxLayout()

        left = QVBoxLayout()
        self._build_position_section(left)
        self._build_temperature_section(left)
        self._build_stirring_section(left)
        left.addStretch()
        columns.addLayout(left, stretch=1)

        right = QVBoxLayout()
        self._build_recipe_section(right)
        self._build_sauce_section(right)
        right.addStretch()
        columns.addLayout(right, stretch=1)

        layout.addLayout(columns)

    def _build_position_section(self, parent_layout):
        self.pos_frame = QGroupBox(t("gantry.position"))
        layout = QVBoxLayout(self.pos_frame)

        # Status row
        status_row = QHBoxLayout()
        self.pos_status_label = QLabel(t("common.status") + ":")
        status_row.addWidget(self.pos_status_label)
        self.pos_display = QLabel(t("wok.working_position"))
        self.pos_display.setStyleSheet("font-size: 10pt; font-weight: bold; color: #1a6ec2;")
        status_row.addWidget(self.pos_display)
        status_row.addStretch()
        layout.addLayout(status_row)

        # Position buttons
        pos_row = QHBoxLayout()
        self.working_pos_btn = QPushButton(t("wok.working_position"))
        self.working_pos_btn.setStyleSheet(_POS_STYLE)
        self.working_pos_btn.clicked.connect(lambda: self._bg(self.wok.move_to_working_position))
        pos_row.addWidget(self.working_pos_btn)

        self.pour_pos_btn = QPushButton(t("wok.pour_position"))
        self.pour_pos_btn.setStyleSheet(_POS_STYLE)
        self.pour_pos_btn.clicked.connect(lambda: self._bg(self.wok.move_to_pour_position))
        pos_row.addWidget(self.pour_pos_btn)

        self.wash_pos_btn = QPushButton(t("wok.wash_position"))
        self.wash_pos_btn.setStyleSheet(_POS_STYLE)
        self.wash_pos_btn.clicked.connect(lambda: self._bg(self.wok.move_to_wash_position))
        pos_row.addWidget(self.wash_pos_btn)

        self.loading_pos_btn = QPushButton(t("wok.loading_position"))
        self.loading_pos_btn.setStyleSheet(_POS_STYLE)
        self.loading_pos_btn.clicked.connect(lambda: self._bg(self.wok.move_to_loading_position))
        pos_row.addWidget(self.loading_pos_btn)
        layout.addLayout(pos_row)

        # Feedback
        fb_row = QHBoxLayout()
        self.feedback_label = QLabel(t("wok.position_feedback") + ":")
        fb_row.addWidget(self.feedback_label)
        self.feedback_display = QLabel("---")
        self.feedback_display.setStyleSheet("font-size: 9pt; color: #666666;")
        fb_row.addWidget(self.feedback_display)
        fb_row.addStretch()
        layout.addLayout(fb_row)

        # Manual movement
        move_row = QHBoxLayout()
        self.wok_up_btn = QPushButton(t("wok.wok_up"))
        self.wok_up_btn.setStyleSheet(_UP_STYLE)
        self.wok_up_btn.pressed.connect(lambda: self.wok.wok_up())
        self.wok_up_btn.released.connect(lambda: self.wok.wok_up_release())
        move_row.addWidget(self.wok_up_btn)

        self.wok_down_btn = QPushButton(t("wok.wok_down"))
        self.wok_down_btn.setStyleSheet(_DOWN_STYLE)
        self.wok_down_btn.pressed.connect(lambda: self.wok.wok_down())
        self.wok_down_btn.released.connect(lambda: self.wok.wok_down_release())
        move_row.addWidget(self.wok_down_btn)

        self.max_up_btn = QPushButton(t("wok.move_up"))
        self.max_up_btn.setStyleSheet(_MAX_UP_STYLE)
        self.max_up_btn.clicked.connect(lambda: self._bg(self.wok.move_to_max_up))
        move_row.addWidget(self.max_up_btn)
        move_row.addStretch()
        layout.addLayout(move_row)

        parent_layout.addWidget(self.pos_frame)

    def _build_temperature_section(self, parent_layout):
        self.temp_frame = QGroupBox(t("wok.temperature"))
        layout = QHBoxLayout(self.temp_frame)

        self.temp_label = QLabel(t("wok.temperature") + ":")
        layout.addWidget(self.temp_label)
        self.temp_display = QLabel("0.0")
        self.temp_display.setStyleSheet("font-size: 11pt; font-weight: bold; color: #c0392b;")
        layout.addWidget(self.temp_display)
        layout.addWidget(QLabel("\u00b0C"))
        layout.addStretch()

        self.heating_check = QCheckBox(t("wok.heating"))
        self.heating_check.toggled.connect(self._on_heating_toggle)
        layout.addWidget(self.heating_check)

        parent_layout.addWidget(self.temp_frame)

    def _build_stirring_section(self, parent_layout):
        self.stir_frame = QGroupBox(t("wok.stirring"))
        layout = QHBoxLayout(self.stir_frame)

        self.stir_speed_label = QLabel(t("wok.stir_speed") + ":")
        layout.addWidget(self.stir_speed_label)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(0, 100)
        self.speed_slider.setValue(50)
        self.speed_slider.setFixedWidth(200)
        self.speed_slider.valueChanged.connect(self._on_speed_change)
        layout.addWidget(self.speed_slider)

        self.speed_value_label = QLabel("50")
        self.speed_value_label.setStyleSheet("font-size: 10pt; font-weight: bold;")
        self.speed_value_label.setFixedWidth(40)
        layout.addWidget(self.speed_value_label)

        layout.addStretch()

        self.stirring_check = QCheckBox(t("wok.stirring"))
        self.stirring_check.toggled.connect(self._on_stirring_toggle)
        layout.addWidget(self.stirring_check)

        parent_layout.addWidget(self.stir_frame)

    def _build_recipe_section(self, parent_layout):
        self.recipe_frame = QGroupBox(t("wok.recipe"))
        layout = QVBoxLayout(self.recipe_frame)

        # Recipe ID + buttons
        top_row = QHBoxLayout()
        self.recipe_id_label = QLabel(t("wok.recipe_id") + ":")
        top_row.addWidget(self.recipe_id_label)

        self.recipe_id_spin = QSpinBox()
        self.recipe_id_spin.setRange(1, 99)
        self.recipe_id_spin.setValue(1)
        self.recipe_id_spin.setFixedWidth(60)
        top_row.addWidget(self.recipe_id_spin)

        self.run_recipe_btn = QPushButton(t("wok.run_recipe"))
        self.run_recipe_btn.setStyleSheet(_RECIPE_STYLE)
        self.run_recipe_btn.clicked.connect(self._on_run_recipe)
        top_row.addWidget(self.run_recipe_btn)

        self.stop_recipe_btn = QPushButton(t("wok.stop_recipe"))
        self.stop_recipe_btn.setStyleSheet(_DOWN_STYLE)
        self.stop_recipe_btn.clicked.connect(self._on_stop_recipe)
        top_row.addWidget(self.stop_recipe_btn)
        top_row.addStretch()
        layout.addLayout(top_row)

        # Timer row
        timer_row = QHBoxLayout()
        self.timer_label = QLabel(t("wok.timer") + ":")
        timer_row.addWidget(self.timer_label)

        self.timer_spin = QSpinBox()
        self.timer_spin.setRange(0, 3600)
        self.timer_spin.setSingleStep(10)
        self.timer_spin.setValue(10)
        self.timer_spin.setFixedWidth(70)
        timer_row.addWidget(self.timer_spin)

        self.countdown_display = QLabel("")
        self.countdown_display.setStyleSheet("font-size: 10pt; font-weight: bold; color: #c0392b;")
        timer_row.addWidget(self.countdown_display)

        timer_row.addStretch()

        self.auto_cook_display = QLabel("M0: OFF")
        self.auto_cook_display.setStyleSheet("font-size: 9pt; font-weight: bold; color: #666666;")
        timer_row.addWidget(self.auto_cook_display)
        layout.addLayout(timer_row)

        # Timer state
        self._countdown_remaining = 0
        self._countdown_active = False
        self._seen_m0_on = False
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._tick_countdown)

        parent_layout.addWidget(self.recipe_frame)

    def _build_sauce_section(self, parent_layout):
        self.sauce_frame = QGroupBox(t("wok.sauce"))
        layout = QVBoxLayout(self.sauce_frame)

        self._sauce_spins = []
        self._sauce_btns = []
        self._sauce_labels = []
        self._sauce_pulse_labels = []

        for i in range(5):
            row = QHBoxLayout()
            label = QLabel(f"{t('wok.sauce')} {i+1}:")
            label.setFixedWidth(80)
            row.addWidget(label)
            self._sauce_labels.append(label)

            pulse_label = QLabel(t("wok.pulse_value") + ":")
            row.addWidget(pulse_label)
            self._sauce_pulse_labels.append(pulse_label)

            spin = QSpinBox()
            spin.setRange(1, 9999)
            spin.setSingleStep(10)
            spin.setValue(100)
            spin.setFixedWidth(70)
            row.addWidget(spin)
            self._sauce_spins.append(spin)

            sauce_id = i + 1
            btn = QPushButton(t("wok.dispense"))
            btn.setStyleSheet(_SAUCE_STYLE)
            btn.clicked.connect(lambda checked, sid=sauce_id: self._on_dispense_sauce(sid))
            row.addWidget(btn)
            self._sauce_btns.append(btn)

            row.addStretch()
            layout.addLayout(row)

        parent_layout.addWidget(self.sauce_frame)

    # ── Update ──

    def _schedule_update(self):
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_display)
        self._update_timer.start(1000)

    def _update_display(self):
        status = self.wok.get_status()

        self.temp_display.setText(f"{status['temperature']:.1f}")
        self.heating_check.blockSignals(True)
        self.heating_check.setChecked(status['is_heating'])
        self.heating_check.blockSignals(False)
        self.stirring_check.blockSignals(True)
        self.stirring_check.setChecked(status['is_stirring'])
        self.stirring_check.blockSignals(False)

        pos_names = {
            "WORKING": t("wok.working_position"),
            "POUR": t("wok.pour_position"),
            "WASH": t("wok.wash_position")
        }
        self.pos_display.setText(pos_names.get(status['position'], status['position']))

        feedback = status.get('position_feedback', {})
        parts = []
        if feedback.get('at_stirfry'):
            parts.append(t("wok.at_stirfry"))
        if feedback.get('at_pour'):
            parts.append(t("wok.at_pour"))
        if feedback.get('at_loading'):
            parts.append(t("wok.at_loading"))
        self.feedback_display.setText(", ".join(parts) if parts else "---")

        is_cooking = status.get('is_auto_cooking', False)
        if is_cooking:
            self.auto_cook_display.setText("M0: ON")
            self.auto_cook_display.setStyleSheet("font-size: 9pt; font-weight: bold; color: #27ae60;")
        else:
            self.auto_cook_display.setText("M0: OFF")
            self.auto_cook_display.setStyleSheet("font-size: 9pt; font-weight: bold; color: #666666;")

    # ── Callbacks ──

    def _bg(self, func, *args):
        threading.Thread(target=func, args=args, daemon=True).start()

    def _on_run_recipe(self):
        recipe_id = self.recipe_id_spin.value()
        timer_sec = self.timer_spin.value()
        if timer_sec == 0:
            result = QMessageBox.question(
                self, t("common.warning"), t("wok.timer_zero_warning"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if result != QMessageBox.StandardButton.Yes:
                self.timer_spin.setValue(10)
                return
        self._bg(self.wok.run_recipe, recipe_id)
        if timer_sec > 0:
            self._countdown_remaining = timer_sec
            self._countdown_active = True
            self._seen_m0_on = False
            mins, secs = divmod(timer_sec, 60)
            self.countdown_display.setText(f"{mins:02d}:{secs:02d}")
            self._countdown_timer.start()

    def _on_stop_recipe(self):
        self._countdown_active = False
        self._countdown_remaining = 0
        self._seen_m0_on = False
        self._countdown_timer.stop()
        self.countdown_display.setText("")
        self._bg(self.wok.stop_auto_cooking)

    def _tick_countdown(self):
        if not self._countdown_active:
            self.countdown_display.setText("")
            self._countdown_timer.stop()
            return

        status = self.wok.get_status()
        is_cooking = status.get('is_auto_cooking', False)

        if not self._seen_m0_on:
            if is_cooking:
                self._seen_m0_on = True
            else:
                return

        if not is_cooking:
            self._countdown_active = False
            self._countdown_remaining = 0
            self.countdown_display.setText("")
            self._countdown_timer.stop()
            return

        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._countdown_active = False
            self.countdown_display.setText("00:00")
            self._countdown_timer.stop()
            self._bg(self.wok.stop_auto_cooking)
            return

        mins, secs = divmod(self._countdown_remaining, 60)
        self.countdown_display.setText(f"{mins:02d}:{secs:02d}")

    def _on_dispense_sauce(self, sauce_id):
        pulse_value = self._sauce_spins[sauce_id - 1].value()
        self._bg(self.wok.dispense_sauce, sauce_id, pulse_value)

    def _on_heating_toggle(self, checked):
        if checked:
            self._bg(self.wok.start_heating)
        else:
            self._bg(self.wok.stop_heating)

    def _on_stirring_toggle(self, checked):
        if checked:
            self._bg(self.wok.start_stirring, self.speed_slider.value())
        else:
            self._bg(self.wok.stop_stirring)

    def _on_speed_change(self, value):
        self.speed_value_label.setText(str(value))
        if self.stirring_check.isChecked():
            self._bg(self.wok.set_stir_speed, value)

    # ── Language ──

    def update_language(self):
        self.status_card.update_language()

        self.pos_frame.setTitle(t("gantry.position"))
        self.pos_status_label.setText(t("common.status") + ":")
        self.working_pos_btn.setText(t("wok.working_position"))
        self.pour_pos_btn.setText(t("wok.pour_position"))
        self.wash_pos_btn.setText(t("wok.wash_position"))
        self.loading_pos_btn.setText(t("wok.loading_position"))
        self.feedback_label.setText(t("wok.position_feedback") + ":")
        self.wok_up_btn.setText(t("wok.wok_up"))
        self.wok_down_btn.setText(t("wok.wok_down"))
        self.max_up_btn.setText(t("wok.move_up"))

        self.temp_frame.setTitle(t("wok.temperature"))
        self.temp_label.setText(t("wok.temperature") + ":")
        self.heating_check.setText(t("wok.heating"))

        self.stir_frame.setTitle(t("wok.stirring"))
        self.stir_speed_label.setText(t("wok.stir_speed") + ":")
        self.stirring_check.setText(t("wok.stirring"))

        self.recipe_frame.setTitle(t("wok.recipe"))
        self.recipe_id_label.setText(t("wok.recipe_id") + ":")
        self.run_recipe_btn.setText(t("wok.run_recipe"))
        self.stop_recipe_btn.setText(t("wok.stop_recipe"))
        self.timer_label.setText(t("wok.timer") + ":")

        self.sauce_frame.setTitle(t("wok.sauce"))
        for i, btn in enumerate(self._sauce_btns):
            btn.setText(t("wok.dispense"))
        for i, label in enumerate(self._sauce_labels):
            label.setText(f"{t('wok.sauce')} {i+1}:")
        for label in self._sauce_pulse_labels:
            label.setText(t("wok.pulse_value") + ":")

        self._update_display()
