"""
Episode Orchestrator Widget
编排器部件

GUI for creating, editing, and playing multi-component episodes.
"""

import json
import os
import threading
import uuid
from typing import List, Optional, Dict, Union

from gui.qt_imports import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter,
    QGroupBox, QLabel, QPushButton, QLineEdit, QComboBox, QListWidget,
    QListWidgetItem, QTreeWidget, QTreeWidgetItem, QDoubleSpinBox, QSpinBox,
    QSlider, QMessageBox, QFileDialog, QInputDialog, QDialog,
    QHeaderView, QFont, QColor, Qt, QTimer,
)
from gui.signals import get_thread_bridge, EventBusBridge

from config.i18n import t
from config.settings import DATA_DIR, EPISODES_DIR, DUAL_ARM_STEPS_DIR
from app_core.logger import get_logger
from app_core.event_bus import EventType, get_event_bus
from .episode_model import ActionGroup, ComponentAction, Episode, EpisodeSet
from .playback_engine import PlaybackEngine

logger = get_logger(__name__)

# Available components and their action types
COMPONENTS = ["dual_arm", "lebai", "wok", "wait"]
ACTION_TYPES = {
    "dual_arm": ["play_step"],
    "lebai": ["replay_trajectory"],
    "wok": ["wok_command"],
    "wait": ["wait"],
}
WOK_COMMANDS = [
    "run_recipe",
    "working_pos", "pour_pos", "wash_pos", "loading_pos", "max_up",
    "start_heating", "stop_heating", "start_stirring", "stop_stirring",
    "dispense_sauce",
]
DEPENDENCY_TYPES = ["none", "starts_with", "starts_after"]

# Lebai log directory
_LEBAI_LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "gantry_lebai", "log")

_BTN_FONT = QFont("Arial", 9, QFont.Weight.Bold)
_HEADING_FONT = QFont("Arial", 11, QFont.Weight.Bold)
_AUTOSAVE_FILE = os.path.join(str(EPISODES_DIR), ".episode_autosave.json")


class EpisodeOrchestratorWidget(QWidget):
    """Widget for multi-component episode orchestration."""

    def __init__(self, parent, dual_arm=None, linker_hand=None, lebai=None, wok=None, gripper=None):
        super().__init__(parent)

        self._engine = PlaybackEngine(dual_arm, linker_hand, lebai, wok, gripper=gripper)
        self._episode_set = EpisodeSet(episodes=[Episode(name="Episode 1")])
        self._selected_episode_idx: Optional[int] = None
        self._selected_action_idx: Optional[int] = None
        self._current_file: Optional[str] = None
        self._playback_thread: Optional[threading.Thread] = None
        # Cache of parsed steps per file path
        self._step_cache: Dict[str, list] = {}

        # Playback state for current-action display
        self._playing_episodes: List[Episode] = []
        self._playing_episode_idx: int = 0
        self._running_action_indices: set = set()  # all concurrently running action indices
        self._countdown_remaining: int = 0
        self._countdown_active: bool = False
        self._seen_m0_on: bool = False
        self._countdown_action_idx: Optional[int] = None  # which action owns the timer
        self._countdown_type: str = ""  # "wok_recipe" or "wait"

        # Guard flag: suppress selection events during refresh
        self._refreshing: bool = False

        # Thread bridge for cross-thread GUI updates
        self._bridge = get_thread_bridge()

        # Subscribe to emergency stop via bridge
        self._event_bridge = EventBusBridge(self)
        self._event_bridge.subscribe(EventType.EMERGENCY_STOP, self._on_emergency_stop)

        # Index mappings rebuilt in _refresh_action_list()
        self._flat_idx_to_item: Dict[int, QTreeWidgetItem] = {}
        self._item_to_flat_idx: Dict[int, int] = {}  # id(item) -> flat_idx
        self._group_item_to_gid: Dict[int, str] = {}  # id(item) -> gid

        # Drag-and-drop state
        self._drag_data: Dict[str, object] = {'item': None, 'start_y': 0}

        self._build_ui()
        self._load_autosave()
        self._refresh_episode_list()

    # ==================================================================
    # UI Construction
    # ==================================================================

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Main horizontal splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # --- LEFT PANEL: Episodes + Controls ---
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(5, 5, 5, 5)
        splitter.addWidget(left)
        self._build_episode_panel(left_layout)

        # --- RIGHT PANEL: Actions + Editor ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(5, 5, 5, 5)
        splitter.addWidget(right)
        self._build_action_panel(right_layout)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    def _build_episode_panel(self, parent_layout):
        """Build the left panel: episode list + playback controls."""
        # Heading
        self.episodes_label = QLabel(t("episode.episodes"))
        self.episodes_label.setFont(_HEADING_FONT)
        parent_layout.addWidget(self.episodes_label)

        # Episode listbox
        self.episode_listbox = QListWidget()
        self.episode_listbox.currentRowChanged.connect(self._on_episode_select)
        parent_layout.addWidget(self.episode_listbox, 1)

        # Episode management buttons -- two rows
        btn_row1 = QHBoxLayout()
        parent_layout.addLayout(btn_row1)
        self.ep_add_btn = QPushButton(t("episode.add"))
        self.ep_add_btn.clicked.connect(self._add_episode)
        btn_row1.addWidget(self.ep_add_btn)
        self.ep_remove_btn = QPushButton(t("episode.remove"))
        self.ep_remove_btn.clicked.connect(self._remove_episode)
        btn_row1.addWidget(self.ep_remove_btn)
        self.rename_btn = QPushButton(t("episode.rename"))
        self.rename_btn.clicked.connect(self._rename_episode)
        btn_row1.addWidget(self.rename_btn)

        btn_row2 = QHBoxLayout()
        parent_layout.addLayout(btn_row2)
        self.ep_up_btn = QPushButton(t("episode.move_up"))
        self.ep_up_btn.clicked.connect(self._move_episode_up)
        btn_row2.addWidget(self.ep_up_btn)
        self.ep_down_btn = QPushButton(t("episode.move_down"))
        self.ep_down_btn.clicked.connect(self._move_episode_down)
        btn_row2.addWidget(self.ep_down_btn)

        # --- Current Action display ---
        self.current_action_frame = QGroupBox(t("episode.current_action"))
        ca_layout = QVBoxLayout(self.current_action_frame)
        parent_layout.addWidget(self.current_action_frame)

        # Container for dynamic action labels
        self.current_action_list = QVBoxLayout()
        ca_layout.addLayout(self.current_action_list)
        self._action_labels: Dict[int, QLabel] = {}  # action_idx -> label widget

        # Idle label shown when nothing is running
        self.current_action_idle = QLabel(t("episode.idle"))
        self.current_action_idle.setFont(QFont("Arial", 9))
        self.current_action_idle.setStyleSheet("background-color: #f0f0f0; color: #6c757d;")
        self.current_action_list.addWidget(self.current_action_idle)

        # Timer label (shared, shown below action list for wok recipes)
        self.current_action_timer = QLabel("")
        self.current_action_timer.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.current_action_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_action_timer.setStyleSheet("background-color: #f0f0f0; color: #c0392b;")
        self.current_action_timer.setVisible(False)
        ca_layout.addWidget(self.current_action_timer)

        # Playback controls
        self.play_frame = QGroupBox(t("episode.playback"))
        play_layout = QVBoxLayout(self.play_frame)
        parent_layout.addWidget(self.play_frame)

        self.play_ep_btn = QPushButton(t("episode.play_episode"))
        self.play_ep_btn.setStyleSheet(
            "QPushButton { background-color: #27ae60; color: white; font-weight: bold; font-size: 9pt; }"
        )
        self.play_ep_btn.clicked.connect(self._on_play_episode)
        play_layout.addWidget(self.play_ep_btn)

        self.play_all_btn = QPushButton(t("episode.play_all"))
        self.play_all_btn.setStyleSheet(
            "QPushButton { background-color: #1a6ec2; color: white; font-weight: bold; font-size: 9pt; }"
        )
        self.play_all_btn.clicked.connect(self._on_play_all)
        play_layout.addWidget(self.play_all_btn)

        self.stop_btn = QPushButton(t("episode.stop"))
        self.stop_btn.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; font-weight: bold; font-size: 9pt; }"
        )
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        play_layout.addWidget(self.stop_btn)

        self.emergency_stop_btn = QPushButton(t("episode.emergency_stop"))
        self.emergency_stop_btn.setStyleSheet(
            "QPushButton { background-color: #8b0000; color: white; font-weight: bold; font-size: 10pt; }"
        )
        self.emergency_stop_btn.setEnabled(False)
        self.emergency_stop_btn.clicked.connect(self._on_emergency_stop_btn)
        play_layout.addWidget(self.emergency_stop_btn)

        # Wait between episodes
        ep_wait_layout = QHBoxLayout()
        play_layout.addLayout(ep_wait_layout)
        self.ep_wait_label = QLabel(t("episode.wait_between_episodes"))
        ep_wait_layout.addWidget(self.ep_wait_label)
        self.ep_wait_spin = QDoubleSpinBox()
        self.ep_wait_spin.setRange(0, 60)
        self.ep_wait_spin.setSingleStep(0.5)
        self.ep_wait_spin.setValue(1.0)
        self.ep_wait_spin.setFixedWidth(60)
        ep_wait_layout.addWidget(self.ep_wait_spin)

        # Wait between actions
        act_wait_layout = QHBoxLayout()
        play_layout.addLayout(act_wait_layout)
        self.act_wait_label = QLabel(t("episode.wait_between_actions"))
        act_wait_layout.addWidget(self.act_wait_label)
        self.act_wait_spin = QDoubleSpinBox()
        self.act_wait_spin.setRange(0, 60)
        self.act_wait_spin.setSingleStep(0.5)
        self.act_wait_spin.setValue(0.5)
        self.act_wait_spin.setFixedWidth(60)
        act_wait_layout.addWidget(self.act_wait_spin)

        # File controls
        file_layout = QHBoxLayout()
        parent_layout.addLayout(file_layout)
        self.save_btn = QPushButton(t("episode.save"))
        self.save_btn.clicked.connect(self._on_save)
        file_layout.addWidget(self.save_btn)
        self.load_btn = QPushButton(t("episode.load"))
        self.load_btn.clicked.connect(self._on_load)
        file_layout.addWidget(self.load_btn)

    def _build_action_panel(self, parent_layout):
        """Build the right panel: action list + editor."""
        # Actions heading
        self.actions_label = QLabel(t("episode.actions"))
        self.actions_label.setFont(_HEADING_FONT)
        parent_layout.addWidget(self.actions_label)

        # Action treeview
        self.action_tree = QTreeWidget()
        self.action_tree.setHeaderHidden(True)
        self.action_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.action_tree.itemSelectionChanged.connect(self._on_action_select)
        self.action_tree.itemDoubleClicked.connect(self._on_tree_double_click)
        self.action_tree.itemExpanded.connect(self._on_group_expand)
        self.action_tree.itemCollapsed.connect(self._on_group_collapse)
        parent_layout.addWidget(self.action_tree, 1)

        # Action list management buttons -- row 1
        act_btn_layout = QHBoxLayout()
        parent_layout.addLayout(act_btn_layout)

        self.new_action_btn = QPushButton(t("episode.new_action"))
        self.new_action_btn.setStyleSheet(
            "QPushButton { background-color: #8e44ad; color: white; }"
        )
        self.new_action_btn.clicked.connect(self._new_action)
        act_btn_layout.addWidget(self.new_action_btn)

        self.play_action_btn = QPushButton(t("episode.play_action"))
        self.play_action_btn.setStyleSheet(
            "QPushButton { background-color: #16a085; color: white; }"
        )
        self.play_action_btn.clicked.connect(self._on_play_action)
        act_btn_layout.addWidget(self.play_action_btn)

        self.act_remove_btn = QPushButton(t("episode.remove_action"))
        self.act_remove_btn.clicked.connect(self._remove_action)
        act_btn_layout.addWidget(self.act_remove_btn)

        self.act_up_btn = QPushButton(t("episode.move_up"))
        self.act_up_btn.clicked.connect(self._move_action_up)
        act_btn_layout.addWidget(self.act_up_btn)

        self.act_down_btn = QPushButton(t("episode.move_down"))
        self.act_down_btn.clicked.connect(self._move_action_down)
        act_btn_layout.addWidget(self.act_down_btn)

        # Row 2: group operations
        act_btn_layout2 = QHBoxLayout()
        parent_layout.addLayout(act_btn_layout2)
        self.group_btn = QPushButton(t("episode.group"))
        self.group_btn.clicked.connect(self._group_selected_actions)
        act_btn_layout2.addWidget(self.group_btn)
        self.ungroup_btn = QPushButton(t("episode.ungroup"))
        self.ungroup_btn.clicked.connect(self._ungroup_selected)
        act_btn_layout2.addWidget(self.ungroup_btn)
        self.rename_group_btn = QPushButton(t("episode.rename_group"))
        self.rename_group_btn.clicked.connect(self._rename_selected_group)
        act_btn_layout2.addWidget(self.rename_group_btn)

        # --- Action Editor (grid layout) ---
        self.editor_frame = QGroupBox(t("episode.editor"))
        self._editor_grid = QGridLayout(self.editor_frame)
        self._editor_grid.setColumnStretch(1, 1)
        parent_layout.addWidget(self.editor_frame)

        grid = self._editor_grid

        # Row 0: Component (always visible)
        self.comp_label = QLabel(t("episode.component") + ":")
        self.comp_label.setFixedWidth(110)
        self.comp_combo = QComboBox()
        self.comp_combo.addItems(COMPONENTS)
        self.comp_combo.setCurrentText("dual_arm")
        self.comp_combo.currentTextChanged.connect(self._on_comp_changed)

        # Row 1: File (dual_arm, lebai)
        self.file_label = QLabel(t("episode.file") + ":")
        self.file_label.setFixedWidth(110)
        self.file_combo = QComboBox()
        self.file_combo.currentTextChanged.connect(self._on_file_changed)
        self.browse_btn = QPushButton("...")
        self.browse_btn.setFixedWidth(30)
        self.browse_btn.clicked.connect(self._browse_file)
        self.file_row = QWidget()
        file_row_layout = QHBoxLayout(self.file_row)
        file_row_layout.setContentsMargins(0, 0, 0, 0)
        file_row_layout.addWidget(self.file_combo, 1)
        file_row_layout.addWidget(self.browse_btn)

        # Row 2: Step (dual_arm only)
        self.step_label = QLabel(t("episode.step") + ":")
        self.step_label.setFixedWidth(110)
        self.step_combo = QComboBox()

        # Speed override
        self.ep_speed_label = QLabel(t("episode.speed") + ":")
        self.ep_speed_label.setFixedWidth(110)
        self.ep_speed_row = QWidget()
        speed_row_layout = QHBoxLayout(self.ep_speed_row)
        speed_row_layout.setContentsMargins(0, 0, 0, 0)
        self.ep_speed_entry = QLineEdit("0.0")
        self.ep_speed_entry.setFixedWidth(50)
        speed_row_layout.addWidget(self.ep_speed_entry)
        self.ep_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.ep_speed_slider.setRange(0, 200)  # 0.0 to 2.0 * 100
        self.ep_speed_slider.setValue(0)
        self.ep_speed_slider.valueChanged.connect(
            lambda v: self.ep_speed_entry.setText(f"{v / 100.0:.2f}")
        )
        self.ep_speed_entry.textChanged.connect(self._on_speed_entry_changed)
        speed_row_layout.addWidget(self.ep_speed_slider, 1)

        # Accel override
        self.ep_accel_label = QLabel(t("episode.accel") + ":")
        self.ep_accel_label.setFixedWidth(110)
        self.ep_accel_row = QWidget()
        accel_row_layout = QHBoxLayout(self.ep_accel_row)
        accel_row_layout.setContentsMargins(0, 0, 0, 0)
        self.ep_accel_entry = QLineEdit("0.0")
        self.ep_accel_entry.setFixedWidth(50)
        accel_row_layout.addWidget(self.ep_accel_entry)
        self.ep_accel_slider = QSlider(Qt.Orientation.Horizontal)
        self.ep_accel_slider.setRange(0, 200)
        self.ep_accel_slider.setValue(0)
        self.ep_accel_slider.valueChanged.connect(
            lambda v: self.ep_accel_entry.setText(f"{v / 100.0:.2f}")
        )
        self.ep_accel_entry.textChanged.connect(self._on_accel_entry_changed)
        accel_row_layout.addWidget(self.ep_accel_slider, 1)

        # Pose delay
        self.ep_pose_delay_label = QLabel(t("episode.pose_delay") + ":")
        self.ep_pose_delay_label.setFixedWidth(110)
        self.ep_pose_delay_spin = QDoubleSpinBox()
        self.ep_pose_delay_spin.setRange(0.0, 10.0)
        self.ep_pose_delay_spin.setSingleStep(0.1)
        self.ep_pose_delay_spin.setValue(0.3)
        self.ep_pose_delay_spin.setDecimals(2)

        # Wok command
        self.wok_label = QLabel(t("episode.wok_cmd") + ":")
        self.wok_label.setFixedWidth(110)
        self.wok_combo = QComboBox()
        self.wok_combo.addItems(WOK_COMMANDS)
        self.wok_combo.currentTextChanged.connect(self._on_wok_cmd_changed)

        # Wok parameter widgets
        self.sauce_id_label = QLabel(t("wok.sauce_id") + ":")
        self.sauce_id_label.setFixedWidth(110)
        self.sauce_id_spin = QSpinBox()
        self.sauce_id_spin.setRange(1, 5)
        self.sauce_id_spin.setValue(1)

        self.pulse_label = QLabel(t("wok.pulse_value") + ":")
        self.pulse_label.setFixedWidth(110)
        self.pulse_spin = QSpinBox()
        self.pulse_spin.setRange(1, 9999)
        self.pulse_spin.setSingleStep(10)
        self.pulse_spin.setValue(100)

        self.recipe_id_label_ed = QLabel(t("wok.recipe_id") + ":")
        self.recipe_id_label_ed.setFixedWidth(110)
        self.recipe_id_spin_ed = QSpinBox()
        self.recipe_id_spin_ed.setRange(1, 99)
        self.recipe_id_spin_ed.setValue(1)

        self.timer_label_ed = QLabel(t("wok.timer") + ":")
        self.timer_label_ed.setFixedWidth(110)
        self.timer_spin_ed = QSpinBox()
        self.timer_spin_ed.setRange(0, 3600)
        self.timer_spin_ed.setSingleStep(10)
        self.timer_spin_ed.setValue(10)

        # Wait duration
        self.duration_label = QLabel(t("episode.duration") + ":")
        self.duration_label.setFixedWidth(110)
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 3600)
        self.duration_spin.setValue(30)

        # Dependency
        self.dep_label = QLabel(t("episode.dependency") + ":")
        self.dep_label.setFixedWidth(110)
        self.dep_combo = QComboBox()
        self.dep_combo.addItems(DEPENDENCY_TYPES)

        # Target
        self.target_label = QLabel(t("episode.target") + ":")
        self.target_label.setFixedWidth(110)
        self._target_dep_value: str = ""
        self._target_options_map: Dict[str, str] = {}
        self.target_combo = QComboBox()
        self.target_combo.currentTextChanged.connect(self._on_target_selected)

        # Group assignment
        self.group_assign_label = QLabel(t("episode.group") + ":")
        self.group_assign_label.setFixedWidth(110)
        self._group_combo_map: Dict[str, str] = {}
        self.group_assign_combo = QComboBox()
        self.group_assign_combo.currentTextChanged.connect(self._on_group_combo_changed)

        # Add Action button
        self.act_add_btn = QPushButton(t("episode.add_action"))
        self.act_add_btn.setStyleSheet(
            "QPushButton { background-color: #2980b9; color: white; font-weight: bold; font-size: 9pt; }"
        )
        self.act_add_btn.clicked.connect(self._add_action)

        # Apply button
        self.apply_btn = QPushButton(t("episode.apply"))
        self.apply_btn.setStyleSheet(
            "QPushButton { background-color: #2c2c2c; color: white; font-weight: bold; font-size: 9pt; }"
        )
        self.apply_btn.clicked.connect(self._apply_action_edit)

        # Hidden var for action type
        self._atype_value = "play_step"

        # Initial layout
        self._layout_editor_rows()
        self._refresh_file_options()

    def _on_speed_entry_changed(self, text):
        try:
            v = float(text)
            v = max(0.0, min(2.0, v))
            self.ep_speed_slider.blockSignals(True)
            self.ep_speed_slider.setValue(int(v * 100))
            self.ep_speed_slider.blockSignals(False)
        except ValueError:
            pass

    def _on_accel_entry_changed(self, text):
        try:
            v = float(text)
            v = max(0.0, min(2.0, v))
            self.ep_accel_slider.blockSignals(True)
            self.ep_accel_slider.setValue(int(v * 100))
            self.ep_accel_slider.blockSignals(False)
        except ValueError:
            pass

    def _clear_grid(self):
        """Remove all widgets from the editor grid."""
        while self._editor_grid.count():
            item = self._editor_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

    def _layout_editor_rows(self):
        """Arrange editor rows based on the selected component."""
        comp = self.comp_combo.currentText()

        self._clear_grid()
        grid = self._editor_grid

        # Row 0: Component (always visible)
        grid.addWidget(self.comp_label, 0, 0, Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(self.comp_combo, 0, 1, Qt.AlignmentFlag.AlignLeft)

        row = 1

        if comp in ("dual_arm", "lebai"):
            grid.addWidget(self.file_label, row, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(self.file_row, row, 1)
            row += 1

        if comp == "dual_arm":
            grid.addWidget(self.step_label, row, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(self.step_combo, row, 1, Qt.AlignmentFlag.AlignLeft)
            row += 1
            grid.addWidget(self.ep_speed_label, row, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(self.ep_speed_row, row, 1)
            row += 1
            grid.addWidget(self.ep_accel_label, row, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(self.ep_accel_row, row, 1)
            row += 1
            grid.addWidget(self.ep_pose_delay_label, row, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(self.ep_pose_delay_spin, row, 1, Qt.AlignmentFlag.AlignLeft)
            row += 1

        if comp == "wok":
            grid.addWidget(self.wok_label, row, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(self.wok_combo, row, 1, Qt.AlignmentFlag.AlignLeft)
            row += 1

            wok_cmd = self.wok_combo.currentText()
            if wok_cmd == "dispense_sauce":
                grid.addWidget(self.sauce_id_label, row, 0, Qt.AlignmentFlag.AlignLeft)
                grid.addWidget(self.sauce_id_spin, row, 1, Qt.AlignmentFlag.AlignLeft)
                row += 1
                grid.addWidget(self.pulse_label, row, 0, Qt.AlignmentFlag.AlignLeft)
                grid.addWidget(self.pulse_spin, row, 1, Qt.AlignmentFlag.AlignLeft)
                row += 1
            elif wok_cmd == "run_recipe":
                grid.addWidget(self.recipe_id_label_ed, row, 0, Qt.AlignmentFlag.AlignLeft)
                grid.addWidget(self.recipe_id_spin_ed, row, 1, Qt.AlignmentFlag.AlignLeft)
                row += 1
                grid.addWidget(self.timer_label_ed, row, 0, Qt.AlignmentFlag.AlignLeft)
                grid.addWidget(self.timer_spin_ed, row, 1, Qt.AlignmentFlag.AlignLeft)
                row += 1

        if comp == "wait":
            grid.addWidget(self.duration_label, row, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(self.duration_spin, row, 1, Qt.AlignmentFlag.AlignLeft)
            row += 1

        # Dependency (always)
        grid.addWidget(self.dep_label, row, 0, Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(self.dep_combo, row, 1, Qt.AlignmentFlag.AlignLeft)
        row += 1

        # Target (always)
        grid.addWidget(self.target_label, row, 0, Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(self.target_combo, row, 1, Qt.AlignmentFlag.AlignLeft)
        row += 1

        # Group assignment (always)
        grid.addWidget(self.group_assign_label, row, 0, Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(self.group_assign_combo, row, 1, Qt.AlignmentFlag.AlignLeft)
        self._refresh_group_options()
        row += 1

        # Add Action + Apply buttons
        grid.addWidget(self.act_add_btn, row, 0, Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(self.apply_btn, row, 1, Qt.AlignmentFlag.AlignRight)

        # Auto-set action type
        atypes = ACTION_TYPES.get(comp, [])
        if atypes:
            self._atype_value = atypes[0]

        # Refresh target dropdown
        self._refresh_target_options()

    # ==================================================================
    # Episode list management
    # ==================================================================

    def _refresh_episode_list(self):
        self._refreshing = True
        try:
            self.episode_listbox.clear()
            for i, ep in enumerate(self._episode_set.episodes):
                count = len(ep.actions)
                self.episode_listbox.addItem(f"  {i + 1}. {ep.name}  ({count})")
            if self._selected_episode_idx is not None:
                if self._selected_episode_idx < len(self._episode_set.episodes):
                    self.episode_listbox.setCurrentRow(self._selected_episode_idx)
            self._refresh_action_list_inner()
        finally:
            self._refreshing = False

    def _on_episode_select(self, row=None):
        if self._refreshing:
            return
        if row is not None and row >= 0:
            self._selected_episode_idx = row
            self._selected_action_idx = None
            self._refresh_action_list()

    def _get_current_episode(self) -> Optional[Episode]:
        if self._selected_episode_idx is not None and \
           self._selected_episode_idx < len(self._episode_set.episodes):
            return self._episode_set.episodes[self._selected_episode_idx]
        return None

    def _add_episode(self):
        idx = len(self._episode_set.episodes) + 1
        ep = Episode(name=f"Episode {idx}")
        self._episode_set.episodes.append(ep)
        self._selected_episode_idx = len(self._episode_set.episodes) - 1
        self._refresh_episode_list()
        self._autosave()

    def _remove_episode(self):
        ep = self._get_current_episode()
        if not ep:
            return
        reply = QMessageBox.question(
            self, t("common.confirm"), f"Delete '{ep.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._episode_set.episodes.pop(self._selected_episode_idx)
            self._selected_episode_idx = None
            self._selected_action_idx = None
            self._refresh_episode_list()
            self._autosave()

    def _move_episode_up(self):
        idx = self._selected_episode_idx
        eps = self._episode_set.episodes
        if idx is None or idx == 0:
            return
        eps[idx], eps[idx - 1] = eps[idx - 1], eps[idx]
        self._selected_episode_idx = idx - 1
        self._refresh_episode_list()
        self._autosave()

    def _move_episode_down(self):
        idx = self._selected_episode_idx
        eps = self._episode_set.episodes
        if idx is None or idx >= len(eps) - 1:
            return
        eps[idx], eps[idx + 1] = eps[idx + 1], eps[idx]
        self._selected_episode_idx = idx + 1
        self._refresh_episode_list()
        self._autosave()

    def _rename_episode(self):
        ep = self._get_current_episode()
        if not ep:
            return
        name, ok = QInputDialog.getText(
            self, t("episode.rename"), t("episode.name") + ":", text=ep.name
        )
        if ok and name:
            ep.name = name.strip() or ep.name
            self._refresh_episode_list()
            self._autosave()

    # ==================================================================
    # Action list management
    # ==================================================================

    def _refresh_action_list(self):
        self._refreshing = True
        try:
            self._refresh_action_list_inner()
        finally:
            self._refreshing = False

    def _refresh_action_list_inner(self):
        self.action_tree.clear()
        self._flat_idx_to_item.clear()
        self._item_to_flat_idx.clear()
        self._group_item_to_gid.clear()
        ep = self._get_current_episode()
        if not ep:
            return

        _group_items: Dict[str, QTreeWidgetItem] = {}
        _visiting: set = set()

        def ensure_group(gid: str) -> QTreeWidgetItem:
            if gid in _group_items:
                return _group_items[gid]
            if gid in _visiting:
                return None
            _visiting.add(gid)
            gmeta = ep.groups.get(gid, ActionGroup(name="Group"))
            parent_gid = getattr(gmeta, 'parent_group_id', '') or ''
            if parent_gid and parent_gid in ep.groups:
                tv_parent = ensure_group(parent_gid)
            else:
                tv_parent = None

            group_item = QTreeWidgetItem()
            group_item.setText(0, gmeta.name)
            group_item.setFont(0, QFont("Arial", 10, QFont.Weight.Bold))

            if tv_parent:
                tv_parent.addChild(group_item)
            else:
                self.action_tree.addTopLevelItem(group_item)

            group_item.setExpanded(not gmeta.collapsed)
            _group_items[gid] = group_item
            self._group_item_to_gid[id(group_item)] = gid
            return group_item

        for i, act in enumerate(ep.actions):
            gid = getattr(act, 'group_id', '') or ''
            action_item = QTreeWidgetItem()
            action_item.setText(0, f"  {i + 1}. {act.display_name()}")
            action_item.setFont(0, QFont("Arial", 9))

            if gid:
                parent_item = ensure_group(gid)
                if parent_item:
                    parent_item.addChild(action_item)
                else:
                    self.action_tree.addTopLevelItem(action_item)
            else:
                self.action_tree.addTopLevelItem(action_item)

            self._flat_idx_to_item[i] = action_item
            self._item_to_flat_idx[id(action_item)] = i

        if self._selected_action_idx is not None:
            item = self._flat_idx_to_item.get(self._selected_action_idx)
            if item:
                self.action_tree.setCurrentItem(item)
                self.action_tree.scrollToItem(item)
                self._load_action_to_editor(ep.actions[self._selected_action_idx])

    def _on_action_select(self):
        if self._refreshing:
            return
        selection = self.action_tree.selectedItems()
        ep = self._get_current_episode()
        if not ep:
            return
        if not selection:
            self._selected_action_idx = None
            self._reset_editor_to_new()
            return
        item = selection[-1]
        item_id = id(item)
        if item_id in self._item_to_flat_idx:
            self._selected_action_idx = self._item_to_flat_idx[item_id]
            if self._selected_action_idx < len(ep.actions):
                self._load_action_to_editor(ep.actions[self._selected_action_idx])
        else:
            self._selected_action_idx = None
            self._reset_editor_to_new()

    def _on_tree_double_click(self, item, column):
        item_id = id(item)
        if item_id in self._group_item_to_gid:
            self._rename_group_by_gid(self._group_item_to_gid[item_id])

    def _on_group_expand(self, item):
        ep = self._get_current_episode()
        item_id = id(item)
        if ep and item_id in self._group_item_to_gid:
            gid = self._group_item_to_gid[item_id]
            if gid in ep.groups:
                ep.groups[gid].collapsed = False
                self._autosave()

    def _on_group_collapse(self, item):
        ep = self._get_current_episode()
        item_id = id(item)
        if ep and item_id in self._group_item_to_gid:
            gid = self._group_item_to_gid[item_id]
            if gid in ep.groups:
                ep.groups[gid].collapsed = True
                self._autosave()

    def _new_action(self):
        self.action_tree.clearSelection()
        self._selected_action_idx = None
        self._reset_editor_to_new()

    def _reset_editor_to_new(self):
        self.comp_combo.setCurrentText("")
        self._atype_value = ""
        self.file_combo.setCurrentText("")
        self.step_combo.setCurrentText("")
        self.wok_combo.setCurrentText("")
        self.dep_combo.setCurrentText("none")
        self.target_combo.setCurrentText("")
        self._target_dep_value = ""
        self.group_assign_combo.setCurrentText(t("episode.ungrouped"))
        self.sauce_id_spin.setValue(1)
        self.pulse_spin.setValue(100)
        self.recipe_id_spin_ed.setValue(1)
        self.duration_spin.setValue(30)
        self._layout_editor_rows()
        self._refresh_target_options()

    def _refresh_group_options(self):
        ep = self._get_current_episode()
        ungrouped = t("episode.ungrouped")
        new_group = t("episode.new_group")
        self._group_combo_map = {ungrouped: ""}
        values = [ungrouped]
        if ep:
            _seen: set = set()

            def _add_children(parent_gid: str, indent: int):
                for gid, gmeta in ep.groups.items():
                    if gid in _seen:
                        continue
                    gpid = getattr(gmeta, 'parent_group_id', '') or ''
                    if gpid == parent_gid:
                        _seen.add(gid)
                        prefix = "  " * indent
                        display = f"{prefix}{gmeta.name}"
                        self._group_combo_map[display] = gid
                        values.append(display)
                        _add_children(gid, indent + 1)
            _add_children("", 0)
        values.append(new_group)
        self._group_combo_map[new_group] = "__new__"

        current = self.group_assign_combo.currentText()
        self.group_assign_combo.blockSignals(True)
        self.group_assign_combo.clear()
        self.group_assign_combo.addItems(values)
        if current in values:
            self.group_assign_combo.setCurrentText(current)
        else:
            self.group_assign_combo.setCurrentText(ungrouped)
        self.group_assign_combo.blockSignals(False)

    def _on_group_combo_changed(self, text):
        gid = self._group_combo_map.get(text, "")
        if gid == "__new__":
            ep = self._get_current_episode()
            default_name = f"Group {len(ep.groups) + 1}" if ep else "Group 1"
            name, ok = QInputDialog.getText(
                self, t("episode.rename_group"), t("episode.group_name") + ":",
                text=default_name
            )
            if not ok or not name:
                self.group_assign_combo.setCurrentText(t("episode.ungrouped"))
                return
            if ep:
                new_gid = uuid.uuid4().hex[:8]
                ep.groups[new_gid] = ActionGroup(name=name.strip(), collapsed=False)
                self._refresh_group_options()
                self.group_assign_combo.setCurrentText(name.strip())
            else:
                self.group_assign_combo.setCurrentText(t("episode.ungrouped"))

    def _get_group_id_from_editor(self) -> str:
        sel = self.group_assign_combo.currentText()
        gid = self._group_combo_map.get(sel, "")
        return "" if gid == "__new__" else gid

    def _add_action(self):
        ep = self._get_current_episode()
        if not ep:
            QMessageBox.information(self, t("common.info"), t("episode.select_episode_first"))
            return
        if not self._confirm_timer_zero():
            return
        action = self._build_action_from_editor()
        action.group_id = self._get_group_id_from_editor()
        ep.actions.append(action)
        self._selected_action_idx = None
        self._refresh_action_list()
        self._refresh_episode_list()
        self._refresh_target_options()
        self._autosave()

    def _collect_group_action_indices(self, ep: Episode, gid: str,
                                      _visited: set = None) -> List[int]:
        if _visited is None:
            _visited = set()
        if gid in _visited:
            return []
        _visited.add(gid)
        indices: List[int] = []
        for i, a in enumerate(ep.actions):
            if a.group_id == gid:
                indices.append(i)
        for child_gid, child_meta in ep.groups.items():
            if getattr(child_meta, 'parent_group_id', '') == gid:
                indices.extend(self._collect_group_action_indices(ep, child_gid, _visited))
        return sorted(set(indices))

    def _collect_descendant_group_ids(self, ep: Episode, gid: str,
                                      _visited: set = None) -> List[str]:
        if _visited is None:
            _visited = set()
        if gid in _visited:
            return []
        _visited.add(gid)
        result: List[str] = []
        for child_gid, child_meta in ep.groups.items():
            if getattr(child_meta, 'parent_group_id', '') == gid:
                result.append(child_gid)
                result.extend(self._collect_descendant_group_ids(ep, child_gid, _visited))
        return result

    def _collect_selected_action_indices(self, ep: Episode) -> List[int]:
        selection = self.action_tree.selectedItems()
        if not selection:
            return []
        indices: List[int] = []
        for item in selection:
            item_id = id(item)
            if item_id in self._item_to_flat_idx:
                indices.append(self._item_to_flat_idx[item_id])
            elif item_id in self._group_item_to_gid:
                gid = self._group_item_to_gid[item_id]
                indices.extend(self._collect_group_action_indices(ep, gid))
        return sorted(set(indices))

    def _remove_action(self):
        ep = self._get_current_episode()
        if not ep:
            return
        selection = self.action_tree.selectedItems()
        if not selection:
            return
        selected_gids: List[str] = []
        for item in selection:
            item_id = id(item)
            if item_id in self._group_item_to_gid:
                gid = self._group_item_to_gid[item_id]
                selected_gids.append(gid)
                selected_gids.extend(self._collect_descendant_group_ids(ep, gid))
        indices_to_remove = self._collect_selected_action_indices(ep)
        if not indices_to_remove and not selected_gids:
            return
        n_actions = len(indices_to_remove)
        n_groups = len(set(selected_gids))
        if n_groups > 0 and n_actions > 0:
            msg = f"Delete {n_actions} action(s) and {n_groups} group(s)?"
        elif n_groups > 0:
            msg = f"Delete {n_groups} group(s)?"
        else:
            msg = f"Delete {n_actions} action(s)?"
        reply = QMessageBox.question(
            self, t("common.confirm"), msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for idx in sorted(indices_to_remove, reverse=True):
            if idx < len(ep.actions):
                ep.actions.pop(idx)
        for gid in set(selected_gids):
            ep.groups.pop(gid, None)
        changed = True
        while changed:
            changed = False
            for gid in list(ep.groups.keys()):
                remaining = sum(1 for a in ep.actions if a.group_id == gid)
                has_children = any(
                    getattr(m, 'parent_group_id', '') == gid
                    for m in ep.groups.values()
                )
                if remaining == 0 and not has_children:
                    parent_gid = getattr(ep.groups.get(gid, ActionGroup()), 'parent_group_id', '') or ''
                    for child_gid, child_meta in list(ep.groups.items()):
                        if getattr(child_meta, 'parent_group_id', '') == gid:
                            child_meta.parent_group_id = parent_gid
                    ep.groups.pop(gid, None)
                    changed = True
        self._selected_action_idx = None
        self._reset_editor_to_new()
        self._refresh_action_list()
        self._refresh_episode_list()
        self._refresh_target_options()
        self._autosave()

    def _move_action_up(self):
        ep = self._get_current_episode()
        idx = self._selected_action_idx
        if not ep or idx is None or idx == 0:
            return
        ep.actions[idx], ep.actions[idx - 1] = ep.actions[idx - 1], ep.actions[idx]
        self._remap_dependency_targets(ep, idx, idx - 1)
        self._selected_action_idx = idx - 1
        self._refresh_action_list()
        self._refresh_target_options()
        self._autosave()

    def _move_action_down(self):
        ep = self._get_current_episode()
        idx = self._selected_action_idx
        if not ep or idx is None or idx >= len(ep.actions) - 1:
            return
        ep.actions[idx], ep.actions[idx + 1] = ep.actions[idx + 1], ep.actions[idx]
        self._remap_dependency_targets(ep, idx, idx + 1)
        self._selected_action_idx = idx + 1
        self._refresh_action_list()
        self._refresh_target_options()
        self._autosave()

    def _remap_dependency_targets(self, ep: Episode, old_idx: int, new_idx: int):
        for act in ep.actions:
            if act.dependency != "none" and act.dependency_target.isdigit():
                target = int(act.dependency_target)
                if target == old_idx:
                    act.dependency_target = str(new_idx)
                elif target == new_idx:
                    act.dependency_target = str(old_idx)

    # ==================================================================
    # Group operations
    # ==================================================================

    def _group_selected_actions(self):
        ep = self._get_current_episode()
        if not ep:
            return
        selection = self.action_tree.selectedItems()
        flat_indices = sorted(
            self._item_to_flat_idx[id(item)]
            for item in selection
            if id(item) in self._item_to_flat_idx
        )
        if len(flat_indices) < 2:
            QMessageBox.information(self, t("common.info"), t("episode.select_two_or_more"))
            return
        existing_groups = set()
        for idx in flat_indices:
            gid = ep.actions[idx].group_id
            if gid:
                existing_groups.add(gid)
        if len(existing_groups) > 1:
            QMessageBox.warning(self, t("common.warning"), t("episode.cannot_merge_groups"))
            return
        if len(existing_groups) == 1:
            parent_gid = existing_groups.pop()
        else:
            parent_gid = ""
        name, ok = QInputDialog.getText(
            self, t("episode.rename_group"), t("episode.group_name") + ":",
            text=f"Group {len(ep.groups) + 1}"
        )
        if not ok or not name:
            return
        gid = uuid.uuid4().hex[:8]
        for idx in flat_indices:
            ep.actions[idx].group_id = gid
        ep.groups[gid] = ActionGroup(name=name.strip(), collapsed=False, parent_group_id=parent_gid)
        self._refresh_action_list()
        self._refresh_episode_list()
        self._autosave()

    def _ungroup_selected(self):
        ep = self._get_current_episode()
        if not ep:
            return
        selection = self.action_tree.selectedItems()
        gids_to_dissolve: set = set()
        for item in selection:
            item_id = id(item)
            if item_id in self._group_item_to_gid:
                gids_to_dissolve.add(self._group_item_to_gid[item_id])
            elif item_id in self._item_to_flat_idx:
                gid = ep.actions[self._item_to_flat_idx[item_id]].group_id
                if gid:
                    gids_to_dissolve.add(gid)
        if not gids_to_dissolve:
            return
        for gid in gids_to_dissolve:
            parent_gid = getattr(ep.groups.get(gid, ActionGroup()), 'parent_group_id', '') or ''
            for act in ep.actions:
                if act.group_id == gid:
                    act.group_id = parent_gid
            for child_gid, child_meta in list(ep.groups.items()):
                if getattr(child_meta, 'parent_group_id', '') == gid:
                    child_meta.parent_group_id = parent_gid
            ep.groups.pop(gid, None)
        self._refresh_action_list()
        self._refresh_episode_list()
        self._autosave()

    def _rename_selected_group(self):
        ep = self._get_current_episode()
        if not ep:
            return
        selection = self.action_tree.selectedItems()
        gid = None
        for item in selection:
            item_id = id(item)
            if item_id in self._group_item_to_gid:
                gid = self._group_item_to_gid[item_id]
                break
            elif item_id in self._item_to_flat_idx:
                gid = ep.actions[self._item_to_flat_idx[item_id]].group_id
                if gid:
                    break
        if gid:
            self._rename_group_by_gid(gid)

    def _rename_group_by_gid(self, gid: str):
        ep = self._get_current_episode()
        if not ep or gid not in ep.groups:
            return
        new_name, ok = QInputDialog.getText(
            self, t("episode.rename_group"), t("episode.group_name") + ":",
            text=ep.groups[gid].name
        )
        if ok and new_name:
            ep.groups[gid].name = new_name.strip()
            self._refresh_action_list()
            self._autosave()

    def _prompt_group_name(self, default: str = "Group") -> Optional[str]:
        name, ok = QInputDialog.getText(
            self, t("episode.rename_group"), t("episode.group_name") + ":",
            text=default
        )
        if ok and name:
            return name.strip() or default
        return None

    # ==================================================================
    # Action editor
    # ==================================================================

    def _load_action_to_editor(self, action: ComponentAction):
        self.comp_combo.setCurrentText(action.component)
        self._on_comp_changed()
        self._atype_value = action.action_type
        self.dep_combo.setCurrentText(action.dependency)
        self.wok_combo.setCurrentText(action.wok_command or "working_pos")
        self._layout_editor_rows()

        params = getattr(action, 'parameters', {}) or {}
        if action.component == "wait":
            self.duration_spin.setValue(params.get("duration", 30))
        elif action.wok_command == "dispense_sauce":
            self.sauce_id_spin.setValue(params.get("sauce_id", 1))
            self.pulse_spin.setValue(params.get("pulse_value", 100))
        elif action.wok_command == "run_recipe":
            self.recipe_id_spin_ed.setValue(params.get("recipe_id", 1))
            self.timer_spin_ed.setValue(params.get("timer", 0))
        if action.component == "dual_arm":
            speed = params.get("speed", 0.0)
            accel = params.get("accel", 0.0)
            self.ep_speed_entry.setText(f"{speed:.3f}")
            self.ep_accel_entry.setText(f"{accel:.3f}")
            self.ep_pose_delay_spin.setValue(params.get("pose_delay", 0.3))

        self._target_dep_value = action.dependency_target or ""
        self._refresh_target_options()

        if action.recording_file:
            fname = os.path.basename(action.recording_file)
            idx = self.file_combo.findText(fname)
            if idx >= 0:
                self.file_combo.setCurrentIndex(idx)
            else:
                self.file_combo.setCurrentText(action.recording_file)
            if action.component == "dual_arm":
                full_path = self._resolve_file_path("dual_arm", fname)
                self._refresh_step_options(full_path)

        self._select_step_by_index(action.step_index)

        gid = getattr(action, 'group_id', '') or ''
        matched = False
        if gid:
            for display, mapped_gid in self._group_combo_map.items():
                if mapped_gid == gid:
                    self.group_assign_combo.setCurrentText(display)
                    matched = True
                    break
        if not matched:
            self.group_assign_combo.setCurrentText(t("episode.ungrouped"))

    def _select_step_by_index(self, step_index: int):
        for i in range(self.step_combo.count()):
            text = self.step_combo.itemText(i)
            if text.startswith(f"{step_index}:"):
                self.step_combo.setCurrentIndex(i)
                return
        self.step_combo.setCurrentText(str(step_index))

    def _confirm_timer_zero(self) -> bool:
        if self.comp_combo.currentText() == "wok" and self.wok_combo.currentText() == "run_recipe":
            if self.timer_spin_ed.value() == 0:
                reply = QMessageBox.question(
                    self, t("common.warning"), t("wok.timer_zero_warning"),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self.timer_spin_ed.setValue(10)
                    return False
        return True

    def _build_action_from_editor(self) -> ComponentAction:
        comp = self.comp_combo.currentText()
        fname = self.file_combo.currentText()
        dep_target = self._target_dep_value

        step_str = self.step_combo.currentText()
        try:
            step_idx = int(step_str.split(":")[0].strip())
        except (ValueError, IndexError):
            step_idx = 0

        parameters = {}
        if comp == "wait":
            parameters = {"duration": self.duration_spin.value()}
        elif comp == "dual_arm":
            try:
                speed_val = round(float(self.ep_speed_entry.text()), 3)
            except ValueError:
                speed_val = 0.0
            try:
                accel_val = round(float(self.ep_accel_entry.text()), 3)
            except ValueError:
                accel_val = 0.0
            parameters = {
                "speed": speed_val,
                "accel": accel_val,
                "pose_delay": round(self.ep_pose_delay_spin.value(), 3),
            }
        elif comp == "wok":
            wok_cmd = self.wok_combo.currentText()
            if wok_cmd == "dispense_sauce":
                parameters = {
                    "sauce_id": self.sauce_id_spin.value(),
                    "pulse_value": self.pulse_spin.value(),
                }
            elif wok_cmd == "run_recipe":
                parameters = {
                    "recipe_id": self.recipe_id_spin_ed.value(),
                    "timer": self.timer_spin_ed.value(),
                }

        return ComponentAction(
            component=comp,
            action_type=self._atype_value,
            recording_file=self._resolve_file_path(comp, fname),
            step_index=step_idx,
            wok_command=self.wok_combo.currentText(),
            dependency=self.dep_combo.currentText(),
            dependency_target=dep_target,
            parameters=parameters,
        )

    def _apply_action_edit(self):
        ep = self._get_current_episode()
        if not ep or self._selected_action_idx is None:
            return
        if self._selected_action_idx >= len(ep.actions):
            return
        if not self._confirm_timer_zero():
            return

        new = self._build_action_from_editor()
        act = ep.actions[self._selected_action_idx]
        old_gid = act.group_id
        act.component = new.component
        act.action_type = new.action_type
        act.recording_file = new.recording_file
        act.step_index = new.step_index
        act.wok_command = new.wok_command
        act.parameters = new.parameters
        act.dependency = new.dependency
        act.dependency_target = new.dependency_target
        new_gid = self._get_group_id_from_editor()
        act.group_id = new_gid
        if old_gid and old_gid != new_gid:
            remaining = sum(1 for a in ep.actions if a.group_id == old_gid)
            if remaining == 0:
                parent_gid = getattr(ep.groups.get(old_gid, ActionGroup()), 'parent_group_id', '') or ''
                for child_gid, child_meta in list(ep.groups.items()):
                    if getattr(child_meta, 'parent_group_id', '') == old_gid:
                        child_meta.parent_group_id = parent_gid
                ep.groups.pop(old_gid, None)

        self._refresh_action_list()
        self._refresh_episode_list()
        self._refresh_target_options()
        self._autosave()

    def _on_comp_changed(self, text=None):
        self._layout_editor_rows()
        self._refresh_file_options()

    def _on_wok_cmd_changed(self, text=None):
        self._layout_editor_rows()

    def _on_target_selected(self, text):
        self._target_dep_value = self._target_options_map.get(text, "")

    def _refresh_target_options(self):
        ep = self._get_current_episode()
        cur_idx = self._selected_action_idx
        options = []
        self._target_options_map = {}
        if ep:
            for i, act in enumerate(ep.actions):
                if i == cur_idx:
                    continue
                display = f"{i + 1}: {act.display_name()}"
                options.append(display)
                self._target_options_map[display] = str(i)
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        self.target_combo.addItems(options)
        val = self._target_dep_value
        if val and val.isdigit():
            idx = int(val)
            if ep and 0 <= idx < len(ep.actions):
                display = f"{idx + 1}: {ep.actions[idx].display_name()}"
                if display in self._target_options_map:
                    self.target_combo.setCurrentText(display)
                    self.target_combo.blockSignals(False)
                    return
        self.target_combo.setCurrentText("")
        self._target_dep_value = ""
        self.target_combo.blockSignals(False)

    def _on_file_changed(self, text=None):
        comp = self.comp_combo.currentText()
        if comp == "dual_arm":
            fname = self.file_combo.currentText()
            full_path = self._resolve_file_path("dual_arm", fname)
            self._refresh_step_options(full_path)

    def _refresh_file_options(self):
        comp = self.comp_combo.currentText()
        files = []
        if comp == "dual_arm":
            data_dir = str(DUAL_ARM_STEPS_DIR)
            if os.path.isdir(data_dir):
                files = sorted(f for f in os.listdir(data_dir)
                               if f.lower().endswith('.json') and not f.endswith('.episode.json'))
        elif comp == "lebai":
            log_dir = os.path.normpath(_LEBAI_LOG_DIR)
            if os.path.isdir(log_dir):
                files = sorted(f for f in os.listdir(log_dir)
                               if f.lower().endswith('.json') and '_events' not in f)
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        self.file_combo.addItems(files)
        if files and not self.file_combo.currentText():
            self.file_combo.setCurrentIndex(0)
            if comp == "dual_arm" and files:
                full_path = self._resolve_file_path("dual_arm", files[0])
                self._refresh_step_options(full_path)
        self.file_combo.blockSignals(False)

    def _refresh_step_options(self, filepath: str):
        if filepath in self._step_cache:
            steps = self._step_cache[filepath]
        else:
            steps = []
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for i, s in enumerate(data.get('steps', [])):
                    name = s.get('name', f'Step {i}')
                    pose_count = len(s.get('poses', []))
                    steps.append(f"{i}: {name} ({pose_count} poses)")
            except Exception:
                pass
            self._step_cache[filepath] = steps
        self.step_combo.blockSignals(True)
        self.step_combo.clear()
        self.step_combo.addItems(steps or ["0"])
        if steps:
            self.step_combo.setCurrentIndex(0)
        self.step_combo.blockSignals(False)

    def _resolve_file_path(self, component: str, fname: str) -> str:
        if not fname:
            return ""
        if os.path.isabs(fname):
            return fname
        if component == "dual_arm":
            return os.path.join(str(DUAL_ARM_STEPS_DIR), fname)
        elif component == "lebai":
            return os.path.join(os.path.normpath(_LEBAI_LOG_DIR), fname)
        return fname

    def _browse_file(self):
        comp = self.comp_combo.currentText()
        if comp == "dual_arm":
            initdir = str(DUAL_ARM_STEPS_DIR)
        elif comp == "lebai":
            initdir = os.path.normpath(_LEBAI_LOG_DIR)
        else:
            initdir = str(DUAL_ARM_STEPS_DIR)
        path, _ = QFileDialog.getOpenFileName(
            self, t("episode.file"),
            initdir,
            "JSON files (*.json);;All files (*.*)"
        )
        if path:
            self.file_combo.setCurrentText(os.path.basename(path))
            if comp == "dual_arm":
                self._refresh_step_options(path)

    # ==================================================================
    # Playback
    # ==================================================================

    def _on_play_action(self):
        ep = self._get_current_episode()
        if not ep:
            return
        indices = self._collect_selected_action_indices(ep)
        if not indices:
            return
        actions = [ep.actions[i] for i in indices if i < len(ep.actions)]
        if not actions:
            return
        play_ep = Episode(name="selection", actions=actions)
        self._start_playback([play_ep])

    def _on_play_episode(self):
        ep = self._get_current_episode()
        if not ep or not ep.actions:
            QMessageBox.information(self, t("common.info"), t("episode.no_actions"))
            return
        self._start_playback([ep])

    def _on_play_all(self):
        if not self._episode_set.episodes:
            return
        self._start_playback(self._episode_set.episodes)

    def _start_playback(self, episodes: List[Episode]):
        if self._engine.is_running:
            return
        self._playing_episodes = episodes
        self._playing_episode_idx = 0
        self._set_playing_state(True)
        ep_delay = self.ep_wait_spin.value()
        act_delay = self.act_wait_spin.value()

        def run():
            try:
                self._engine.play_all(
                    episodes,
                    on_episode_progress=self._on_episode_progress,
                    on_action_progress=self._on_action_progress,
                    episode_delay=ep_delay,
                    action_delay=act_delay,
                )
            except Exception as e:
                logger.error(f"Playback error: {e}")
            finally:
                self._bridge.gui_callback.emit(lambda: self._set_playing_state(False))

        self._playback_thread = threading.Thread(target=run, daemon=True, name="EpisodePlayback")
        self._playback_thread.start()

    def _on_stop(self):
        threading.Thread(target=self._engine.stop, daemon=True).start()

    def _on_emergency_stop_btn(self):
        logger.warning("Episode emergency stop triggered by user")
        threading.Thread(target=self._engine.emergency_stop, daemon=True).start()

    def _on_emergency_stop(self, event):
        logger.warning("Global emergency stop received -- stopping episode playback")
        self._engine.emergency_stop()
        self._bridge.gui_callback.emit(lambda: self._set_playing_state(False))

    def _on_episode_progress(self, episode_idx: int, total: int, status: str):
        if status == "running":
            self._playing_episode_idx = episode_idx

    def _on_action_progress(self, action_idx: int, status: str):
        def _update():
            item = self._flat_idx_to_item.get(action_idx)
            if status == "running":
                if item:
                    parent = item.parent()
                    if parent:
                        parent.setExpanded(True)
                    item.setBackground(0, QColor("#d4edda"))
                    self.action_tree.setCurrentItem(item)
                    self.action_tree.scrollToItem(item)
                self._running_action_indices.add(action_idx)
                self._rebuild_current_action_display()
                action = self._get_playing_action(action_idx)
                if action is not None:
                    if (action.component == "wok"
                            and action.wok_command == "run_recipe"
                            and action.parameters.get("timer", 0) > 0):
                        timer_secs = int(action.parameters["timer"])
                        self._start_countdown(timer_secs, action_idx, "wok_recipe")
                    elif (action.component == "wait"
                            and action.parameters.get("duration", 0) > 0):
                        duration = int(action.parameters["duration"])
                        self._start_countdown(duration, action_idx, "wait")
            elif status == "done":
                if item:
                    item.setBackground(0, QColor("#f8f9fa"))
                self._running_action_indices.discard(action_idx)
                if self._countdown_action_idx == action_idx:
                    self._stop_countdown()
                self._rebuild_current_action_display()
        self._bridge.gui_callback.emit(_update)

    def _get_playing_action(self, action_idx: int) -> Optional[ComponentAction]:
        try:
            ep_idx = self._playing_episode_idx
            if ep_idx < len(self._playing_episodes):
                ep = self._playing_episodes[ep_idx]
                if action_idx < len(ep.actions):
                    return ep.actions[action_idx]
        except (IndexError, AttributeError):
            pass
        return None

    def _rebuild_current_action_display(self):
        for idx in list(self._action_labels):
            if idx not in self._running_action_indices:
                self._action_labels[idx].setParent(None)
                self._action_labels[idx].deleteLater()
                del self._action_labels[idx]

        if not self._running_action_indices:
            self.current_action_idle.setVisible(True)
            return

        self.current_action_idle.setVisible(False)

        for idx in sorted(self._running_action_indices):
            action = self._get_playing_action(idx)
            text = f"\u25b6  {action.display_name()}" if action else f"\u25b6  Action {idx + 1}"
            if idx in self._action_labels:
                self._action_labels[idx].setText(text)
            else:
                lbl = QLabel(text)
                lbl.setFont(QFont("Arial", 9))
                lbl.setStyleSheet("background-color: #f0f0f0; color: #1a6ec2;")
                lbl.setWordWrap(True)
                self.current_action_list.addWidget(lbl)
                self._action_labels[idx] = lbl

    def _start_countdown(self, seconds: int, action_idx: int, countdown_type: str = "wok_recipe"):
        self._countdown_remaining = seconds
        self._countdown_active = True
        self._seen_m0_on = False
        self._countdown_action_idx = action_idx
        self._countdown_type = countdown_type
        mins, secs = divmod(seconds, 60)
        label = t('episode.waiting') if countdown_type == "wait" else t('episode.remaining')
        self.current_action_timer.setText(f"{label}: {mins:02d}:{secs:02d}")
        self.current_action_timer.setVisible(True)
        QTimer.singleShot(1000, self._tick_countdown)

    def _tick_countdown(self):
        if not self._countdown_active:
            return
        if self._countdown_type == "wait":
            self._tick_wait_countdown()
        else:
            self._tick_wok_countdown()

    def _tick_wait_countdown(self):
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self.current_action_timer.setText(f"{t('episode.waiting')}: 00:00")
            self._countdown_active = False
            return
        mins, secs = divmod(self._countdown_remaining, 60)
        self.current_action_timer.setText(f"{t('episode.waiting')}: {mins:02d}:{secs:02d}")
        QTimer.singleShot(1000, self._tick_countdown)

    def _tick_wok_countdown(self):
        wok = self._engine._wok
        is_cooking = False
        if wok is not None:
            try:
                status = wok.get_status()
                is_cooking = status.get('is_auto_cooking', False)
            except Exception:
                pass
        if not self._seen_m0_on:
            if is_cooking:
                self._seen_m0_on = True
            QTimer.singleShot(1000, self._tick_countdown)
            return
        if not is_cooking:
            self._stop_countdown()
            return
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self.current_action_timer.setText(f"{t('episode.remaining')}: 00:00")
            self._countdown_active = False
            return
        mins, secs = divmod(self._countdown_remaining, 60)
        self.current_action_timer.setText(f"{t('episode.remaining')}: {mins:02d}:{secs:02d}")
        QTimer.singleShot(1000, self._tick_countdown)

    def _stop_countdown(self):
        self._countdown_active = False
        self._countdown_remaining = 0
        self._seen_m0_on = False
        self._countdown_action_idx = None
        self._countdown_type = ""
        self.current_action_timer.setVisible(False)

    def _reset_current_action_display(self):
        self._stop_countdown()
        self._running_action_indices.clear()
        for lbl in self._action_labels.values():
            lbl.setParent(None)
            lbl.deleteLater()
        self._action_labels.clear()
        self.current_action_idle.setVisible(True)
        self._playing_episodes = []

    def _set_playing_state(self, playing: bool):
        self.play_action_btn.setEnabled(not playing)
        self.play_ep_btn.setEnabled(not playing)
        self.play_all_btn.setEnabled(not playing)
        self.stop_btn.setEnabled(playing)
        self.emergency_stop_btn.setEnabled(playing)
        self.apply_btn.setEnabled(not playing)
        if not playing:
            self._reset_current_action_display()

    # ==================================================================
    # Save / Load
    # ==================================================================

    def _autosave(self):
        try:
            self._episode_set.save(_AUTOSAVE_FILE)
        except Exception as e:
            logger.debug(f"Autosave failed: {e}")

    def _load_autosave(self):
        if os.path.isfile(_AUTOSAVE_FILE):
            try:
                self._episode_set = EpisodeSet.load(_AUTOSAVE_FILE)
                self._selected_episode_idx = 0 if self._episode_set.episodes else None
                logger.info("Restored episodes from autosave")
            except Exception as e:
                logger.debug(f"Autosave load failed: {e}")

    def _on_save(self):
        ep = self._get_current_episode()
        if ep and ep.name:
            safe_name = ep.name.lower().replace(" ", "_")
            auto_name = f"{safe_name}.episode.json"
        else:
            from datetime import datetime
            auto_name = datetime.now().strftime("episode_%Y%m%d_%H%M%S.episode.json")
        path, _ = QFileDialog.getSaveFileName(
            self, t("episode.save"),
            os.path.join(str(EPISODES_DIR), auto_name),
            "Episode files (*.episode.json);;All files (*.*)"
        )
        if path:
            self._episode_set.save(path)
            self._current_file = path
            self._autosave()
            QMessageBox.information(self, t("common.info"), t("episode.saved"))

    def _on_load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("episode.load"),
            str(EPISODES_DIR),
            "Episode files (*.episode.json);;JSON files (*.json);;All files (*.*)"
        )
        if path:
            try:
                self._episode_set = EpisodeSet.load(path)
                self._current_file = path
                self._selected_episode_idx = 0 if self._episode_set.episodes else None
                self._selected_action_idx = None
                self._refresh_episode_list()
                self._autosave()
            except Exception as e:
                QMessageBox.critical(self, t("common.error"), str(e))

    # ==================================================================
    # Language update
    # ==================================================================

    def update_language(self):
        # Left panel
        self.episodes_label.setText(t("episode.episodes"))
        self.ep_add_btn.setText(t("episode.add"))
        self.ep_remove_btn.setText(t("episode.remove"))
        self.rename_btn.setText(t("episode.rename"))
        self.ep_up_btn.setText(t("episode.move_up"))
        self.ep_down_btn.setText(t("episode.move_down"))
        self.current_action_frame.setTitle(t("episode.current_action"))
        if not self._engine.is_running:
            self.current_action_idle.setText(t("episode.idle"))
        self.play_frame.setTitle(t("episode.playback"))
        self.play_action_btn.setText(t("episode.play_action"))
        self.play_ep_btn.setText(t("episode.play_episode"))
        self.play_all_btn.setText(t("episode.play_all"))
        self.stop_btn.setText(t("episode.stop"))
        self.emergency_stop_btn.setText(t("episode.emergency_stop"))
        self.save_btn.setText(t("episode.save"))
        self.load_btn.setText(t("episode.load"))
        self.ep_wait_label.setText(t("episode.wait_between_episodes"))
        self.act_wait_label.setText(t("episode.wait_between_actions"))
        # Right panel
        self.actions_label.setText(t("episode.actions"))
        self.new_action_btn.setText(t("episode.new_action"))
        self.act_add_btn.setText(t("episode.add_action"))
        self.act_remove_btn.setText(t("episode.remove_action"))
        self.act_up_btn.setText(t("episode.move_up"))
        self.act_down_btn.setText(t("episode.move_down"))
        self.editor_frame.setTitle(t("episode.editor"))
        self.comp_label.setText(t("episode.component") + ":")
        self.file_label.setText(t("episode.file") + ":")
        self.step_label.setText(t("episode.step") + ":")
        self.wok_label.setText(t("episode.wok_cmd") + ":")
        self.sauce_id_label.setText(t("wok.sauce_id") + ":")
        self.pulse_label.setText(t("wok.pulse_value") + ":")
        self.recipe_id_label_ed.setText(t("wok.recipe_id") + ":")
        self.timer_label_ed.setText(t("wok.timer") + ":")
        self.duration_label.setText(t("episode.duration") + ":")
        self.dep_label.setText(t("episode.dependency") + ":")
        self.target_label.setText(t("episode.target") + ":")
        self.apply_btn.setText(t("episode.apply"))
        self.group_assign_label.setText(t("episode.group") + ":")
        self.group_btn.setText(t("episode.group"))
        self.ungroup_btn.setText(t("episode.ungroup"))
        self.rename_group_btn.setText(t("episode.rename_group"))

    def cleanup(self):
        """Cleanup resources."""
        self._event_bridge.unsubscribe_all()
