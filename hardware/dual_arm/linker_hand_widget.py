"""
Linker Hand Widget Module
灵巧手部件模块

GUI widget for LinkerHand L6 dexterous hand control with finger sliders and sensor display.
用于LinkerHand L6灵巧手控制的GUI部件，包含手指滑块和传感器显示。
"""

from typing import Optional, List, Dict
import threading
import subprocess

from gui.qt_imports import (
    Qt, QTimer, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QPushButton, QSlider, QLineEdit, QTabWidget,
    QScrollArea, QSizePolicy, QSpacerItem,
    QPainter, QColor, QPaintEvent, QPen, QBrush,
)
from .linker_hand_controller import LinkerHandController, HandSide
from config.i18n import t
from app_core.logger import get_logger
from gui.widgets import ScrollableFrame

logger = get_logger(__name__)


# Finger names for L6 hand
FINGER_NAMES = {
    'zh': ['拇指弯曲', '拇指旋转', '食指', '中指', '无名指', '小指'],
    'en': ['Thumb Bend', 'Thumb Yaw', 'Index', 'Middle', 'Ring', 'Little']
}

# Finger names for touch matrix display
TOUCH_FINGER_NAMES = {
    'zh': ['拇指', '食指', '中指', '无名指', '小指'],
    'en': ['Thumb', 'Index', 'Middle', 'Ring', 'Little']
}


class DotMatrixWidget(QWidget):
    """
    Dot matrix display widget for touch sensor visualization.
    用于触摸传感器可视化的点阵显示部件。
    """

    def __init__(self, parent=None, rows=12, cols=6, dot_size=6, spacing=2):
        """
        Initialize dot matrix widget.

        Args:
            parent: Parent widget
            rows: Number of rows
            cols: Number of columns
            dot_size: Size of each dot
            spacing: Spacing between dots
        """
        super().__init__(parent)
        self.rows = rows
        self.cols = cols
        self.dot_size = dot_size
        self.spacing = spacing
        self.data = None

        # Calculate widget size
        width = cols * (dot_size + spacing) + spacing + 4
        height = rows * (dot_size + spacing) + spacing + 4
        self.setFixedSize(width, height)

    def set_data(self, data: List):
        """
        Set dot matrix data.
        设置点阵数据。

        Args:
            data: List of values (0-255), length should be rows * cols
        """
        self.data = data
        self.update()

    def paintEvent(self, event: QPaintEvent):
        """Paint the dot matrix."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # White background
        painter.fillRect(self.rect(), QColor(255, 255, 255))

        # Border
        painter.setPen(QPen(QColor('#cccccc'), 1))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        for row in range(self.rows):
            for col in range(self.cols):
                x = self.spacing + col * (self.dot_size + self.spacing) + 2
                y = self.spacing + row * (self.dot_size + self.spacing) + 2

                # Get color based on data
                color = QColor('#c8c8c8')  # Default gray
                if self.data is not None:
                    index = row * self.cols + col
                    if index < len(self.data):
                        value = self.data[index]
                        if hasattr(value, 'item'):
                            value = value.item()
                        if value > 0:
                            color = self._get_heat_color(value)

                painter.setPen(QPen(QColor('#666666'), 1))
                painter.setBrush(QBrush(color))
                painter.drawRect(x, y, self.dot_size, self.dot_size)

        painter.end()

    def _get_heat_color(self, value: int) -> QColor:
        """
        Get heat map color from white to dark red.
        获取从白色到深红色的热力图颜色。
        """
        intensity = min(255, max(0, int(value)))

        if intensity < 128:
            # White to light red
            red = 255
            green = 255 - (intensity * 55 // 128)
            blue = 255 - (intensity * 55 // 128)
        else:
            # Light red to dark red
            red = 255
            green = 200 - ((intensity - 128) * 200 // 127)
            blue = 200 - ((intensity - 128) * 200 // 127)

        return QColor(red, green, blue)


class FingerMatrixFrame(QGroupBox):
    """
    Frame containing a single finger's touch matrix display.
    包含单个手指触摸矩阵显示的框架。
    """

    def __init__(self, parent, finger_name: str):
        super().__init__(finger_name, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.matrix = DotMatrixWidget(self)
        layout.addWidget(self.matrix)

    def set_data(self, data: List):
        """Update matrix data"""
        self.matrix.set_data(data)


class LinkerHandWidget(QWidget):
    """
    Widget for LinkerHand L6 dexterous hand control.
    用于LinkerHand L6灵巧手控制的部件。

    Features:
    - Individual finger position sliders (0-255)
    - Speed and torque settings
    - Touch sensor matrix visualization
    - Preset gestures
    """

    def __init__(self, parent, hand_controller: LinkerHandController = None):
        super().__init__(parent)

        self.hand = hand_controller or LinkerHandController()
        self._current_lang = 'zh'  # Default language

        # CAN interface value for connection UI
        self._can_interface_text = self.hand._can_interface or "can0"

        # Finger positions (0-255 for each of 6 joints)
        self._left_positions: List[int] = [128] * 6
        self._right_positions: List[int] = [128] * 6
        # Touch sensor data
        self._left_touch_data: Dict[str, List] = {}
        self._right_touch_data: Dict[str, List] = {}

        # Speed and torque settings
        self._speed: int = 255
        self._torque: int = 255

        # Cached touch capability per side (2=matrix, 1=basic, -1=none, None=unknown)
        self._touch_type: Dict[str, Optional[int]] = {"left": None, "right": None}
        self._touch_poll_stop = threading.Event()
        self._touch_poll_thread: Optional[threading.Thread] = None

        self._build_ui()
        self._schedule_update()
        self._start_touch_poll()

    def _start_touch_poll(self):
        """Start the always-on background touch-matrix poller (~3 Hz)."""
        if self._touch_poll_thread and self._touch_poll_thread.is_alive():
            return
        self._touch_poll_stop.clear()
        self._touch_poll_thread = threading.Thread(
            target=self._touch_poll_loop, daemon=True)
        self._touch_poll_thread.start()

    def _stop_touch_poll(self):
        """Stop the background touch poller."""
        self._touch_poll_stop.set()

    def _touch_poll_loop(self):
        """Background loop: read each connected hand's tactile matrices and push
        them to the UI thread. Reads share the CAN bus with motion commands."""
        from gui.signals import get_thread_bridge
        bridge = get_thread_bridge()
        while not self._touch_poll_stop.wait(0.33):  # ~3 Hz
            for side in ("left", "right"):
                try:
                    if not self.hand or not self.hand.is_hand_connected(side):
                        self._touch_type[side] = None
                        bridge.gui_callback.emit(
                            lambda s=side: self._apply_touch_status(s, "disconnected"))
                        continue

                    # Query capability once per connection, then cache it.
                    if self._touch_type[side] is None:
                        self._touch_type[side] = self.hand.get_touch_type(side)

                    cap = self._touch_type[side]
                    if cap == 2:
                        matrices = self.hand.get_touch_matrices(side)
                        if matrices is not None:
                            bridge.gui_callback.emit(
                                lambda s=side, m=matrices: self._apply_touch_data(s, m))
                    else:
                        state = "no_sensor" if cap in (1, -1) else "querying"
                        bridge.gui_callback.emit(
                            lambda s=side, st=state: self._apply_touch_status(s, st))
                except Exception as e:
                    logger.debug("Touch poll (%s) failed: %s", side, e)
                    # Force a re-query of capability next cycle
                    self._touch_type[side] = None

    def _apply_touch_data(self, side: str, matrices: Dict[str, List[int]]):
        """UI thread: push matrix data into the per-finger grids and clear status."""
        grids = self.left_matrices if side == "left" else self.right_matrices
        status = getattr(self, f"{side}_touch_status", None)
        for finger, data in matrices.items():
            frame = grids.get(f"{finger}_matrix")
            if frame is not None:
                frame.set_data(data)
        if side == "left":
            self._left_touch_data = matrices
        else:
            self._right_touch_data = matrices
        if status is not None:
            status.setText("")
            status.setVisible(False)

    def _apply_touch_status(self, side: str, state: str):
        """UI thread: show a capability/connection message instead of empty grids."""
        status = getattr(self, f"{side}_touch_status", None)
        if status is None:
            return
        key = {
            "disconnected": "dual_arm.touch_not_connected",
            "no_sensor": "dual_arm.touch_no_sensor",
            "querying": "dual_arm.touch_querying",
        }.get(state, "dual_arm.touch_not_connected")
        status.setText(t(key))
        status.setVisible(True)

    def _build_ui(self):
        """Build the UI / 构建UI"""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)

        # Create scrollable container
        self.scroll_frame = ScrollableFrame(self)
        outer_layout.addWidget(self.scroll_frame)

        # Create notebook (QTabWidget) for left/right hand
        self.notebook = QTabWidget()
        self.scroll_frame.inner_layout.addWidget(self.notebook)

        # Left hand tab
        left_frame = QWidget()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(5, 5, 5, 5)
        self.notebook.addTab(left_frame, t("hardware.left_hand"))
        self._build_hand_panel(left_layout, "left")

        # Right hand tab
        right_frame = QWidget()
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(5, 5, 5, 5)
        self.notebook.addTab(right_frame, t("hardware.right_hand"))
        self._build_hand_panel(right_layout, "right")

        # Settings tab
        settings_frame = QWidget()
        settings_layout = QVBoxLayout(settings_frame)
        settings_layout.setContentsMargins(5, 5, 5, 5)
        self.notebook.addTab(settings_frame, t("common.settings"))
        self._build_settings_panel(settings_layout)

    def _build_hand_panel(self, parent_layout: QVBoxLayout, side: str):
        """Build hand control panel / 构建手部控制面板"""
        # Per-side connection controls at the top
        self._build_connection_row(parent_layout, side)

        # Main container with two columns
        main_layout = QHBoxLayout()
        parent_layout.addLayout(main_layout)

        # Left column - Finger controls
        left_col_layout = QVBoxLayout()
        main_layout.addLayout(left_col_layout, stretch=1)

        # Finger control group box
        slider_frame = QGroupBox(t("dual_arm.finger_control"))
        slider_frame_layout = QVBoxLayout(slider_frame)
        left_col_layout.addWidget(slider_frame)
        if side == "left":
            self.left_slider_frame = slider_frame
        else:
            self.right_slider_frame = slider_frame

        # Scrollable inner area for finger rows
        slider_scroll = QScrollArea()
        slider_scroll.setWidgetResizable(True)
        slider_scroll.setFixedHeight(200)
        slider_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sliders_inner = QWidget()
        sliders_inner_layout = QVBoxLayout(sliders_inner)
        sliders_inner_layout.setContentsMargins(0, 0, 0, 0)
        slider_scroll.setWidget(sliders_inner)
        slider_frame_layout.addWidget(slider_scroll)

        sliders: List[QSlider] = []
        slider_labels: List[QLabel] = []
        slider_value_labels: List[QLabel] = []

        from config.i18n import get_i18n
        _lang = get_i18n().language.value if get_i18n() else "en"
        finger_names = FINGER_NAMES.get(_lang, FINGER_NAMES["en"])
        for i, name in enumerate(finger_names):
            row_layout = QHBoxLayout()
            sliders_inner_layout.addLayout(row_layout)

            lbl = QLabel(name + ":")
            lbl.setFixedWidth(100)
            row_layout.addWidget(lbl)
            slider_labels.append(lbl)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 255)
            slider.setValue(255)
            slider.setMinimumWidth(150)
            row_layout.addWidget(slider)
            sliders.append(slider)

            val_lbl = QLabel("255")
            val_lbl.setFixedWidth(35)
            row_layout.addWidget(val_lbl)
            slider_value_labels.append(val_lbl)

            idx, s = i, side
            slider.valueChanged.connect(lambda val, i=idx, s=s: self._on_slider_change(s, i, val))

        sliders_inner_layout.addStretch()

        if side == "left":
            self.left_sliders = sliders
            self.left_slider_labels = slider_labels
            self.left_value_labels = slider_value_labels
        else:
            self.right_sliders = sliders
            self.right_slider_labels = slider_labels
            self.right_value_labels = slider_value_labels

        # Gesture presets
        preset_frame = QGroupBox(t("dual_arm.presets"))
        preset_layout = QHBoxLayout(preset_frame)
        left_col_layout.addWidget(preset_frame)
        if side == "left":
            self.left_preset_frame = preset_frame
        else:
            self.right_preset_frame = preset_frame

        # L6: 255 = open, 0 = closed. Presets like dexhand tab.
        self._preset_gesture_keys = [
            "dual_arm.gesture_open", "dual_arm.gesture_close", "dual_arm.gesture_half",
            "dual_arm.gesture_grab", "dual_arm.gesture_pinch", "dual_arm.gesture_point",
        ]
        gestures_data = [
            ([255, 128, 255, 255, 255, 255],),   # Open
            ([0, 128, 0, 0, 0, 0],),             # Close
            ([128, 128, 128, 128, 128, 128],),   # Half (128)
            ([50, 128, 50, 50, 50, 50],),        # Grab (50)
            ([200, 128, 200, 0, 0, 0],),         # Pinch
            ([200, 128, 0, 200, 200, 200],),     # Point
        ]
        preset_buttons = []
        for i, (key, (pos,)) in enumerate(zip(self._preset_gesture_keys, gestures_data)):
            btn = QPushButton(t(key))
            btn.clicked.connect(lambda checked, s=side, p=pos: self._apply_gesture(s, p))
            preset_layout.addWidget(btn)
            preset_buttons.append(btn)
        if side == "left":
            self.left_preset_buttons = preset_buttons
        else:
            self.right_preset_buttons = preset_buttons

        # Control buttons
        ctrl_layout = QHBoxLayout()
        left_col_layout.addLayout(ctrl_layout)

        get_btn = QPushButton(t("dual_arm.get_position"))
        get_btn.clicked.connect(lambda checked, s=side: self._get_hand_position(s))
        ctrl_layout.addWidget(get_btn)

        send_btn = QPushButton(t("dual_arm.send_position"))
        send_btn.clicked.connect(lambda checked, s=side: self._send_hand_position(s))
        ctrl_layout.addWidget(send_btn)

        zero_btn = QPushButton(t("dual_arm.set_all_zero"))
        zero_btn.clicked.connect(lambda checked, s=side: self._set_all_fingers(s, 0))
        ctrl_layout.addWidget(zero_btn)

        ctrl_layout.addStretch()

        if side == "left":
            self.left_get_btn, self.left_send_btn, self.left_zero_btn = get_btn, send_btn, zero_btn
        else:
            self.right_get_btn, self.right_send_btn, self.right_zero_btn = get_btn, send_btn, zero_btn

        # Right column - Touch sensor display
        touch_frame = QGroupBox(t("dual_arm.touch_sensor"))
        touch_layout = QVBoxLayout(touch_frame)
        main_layout.addWidget(touch_frame)
        if side == "left":
            self.left_touch_frame = touch_frame
        else:
            self.right_touch_frame = touch_frame

        # Status line: shows connection / capability messages above the grids
        touch_status = QLabel(t("dual_arm.touch_not_connected"))
        touch_layout.addWidget(touch_status)
        if side == "left":
            self.left_touch_status = touch_status
        else:
            self.right_touch_status = touch_status

        # Create finger matrix displays
        matrices = {}
        finger_touch_names = TOUCH_FINGER_NAMES.get(_lang, TOUCH_FINGER_NAMES["en"])

        # First row: Thumb, Index, Middle
        row1_layout = QHBoxLayout()
        touch_layout.addLayout(row1_layout)

        for name, key in zip(finger_touch_names[:3], ['thumb', 'index', 'middle']):
            frame = FingerMatrixFrame(touch_frame, name)
            row1_layout.addWidget(frame)
            matrices[f'{key}_matrix'] = frame

        # Second row: Ring, Little
        row2_layout = QHBoxLayout()
        touch_layout.addLayout(row2_layout)

        for name, key in zip(finger_touch_names[3:], ['ring', 'little']):
            frame = FingerMatrixFrame(touch_frame, name)
            row2_layout.addWidget(frame)
            matrices[f'{key}_matrix'] = frame
        row2_layout.addStretch()

        touch_layout.addStretch()

        # Store references
        if side == "left":
            self.left_matrices = matrices
        else:
            self.right_matrices = matrices

    def _build_settings_panel(self, parent_layout: QVBoxLayout):
        """Build settings panel (store refs for language update)."""
        # Speed setting
        speed_frame = QGroupBox(t("dual_arm.speed"))
        speed_layout = QHBoxLayout(speed_frame)
        parent_layout.addWidget(speed_frame)
        self.settings_speed_frame = speed_frame

        self.speed_label = QLabel(t("dual_arm.speed") + ":")
        speed_layout.addWidget(self.speed_label)

        self.speed_value_label = QLabel("255")
        self.speed_value_label.setFixedWidth(35)
        speed_layout.addWidget(self.speed_value_label)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(0, 255)
        self.speed_slider.setValue(255)
        self.speed_slider.valueChanged.connect(self._on_speed_change)
        speed_layout.addWidget(self.speed_slider, stretch=1)

        self.speed_apply_btn = QPushButton(t("common.apply"))
        self.speed_apply_btn.clicked.connect(self._apply_speed)
        speed_layout.addWidget(self.speed_apply_btn)

        # Torque setting
        torque_frame = QGroupBox(t("dual_arm.torque"))
        torque_layout = QHBoxLayout(torque_frame)
        parent_layout.addWidget(torque_frame)
        self.settings_torque_frame = torque_frame

        self.torque_label = QLabel(t("dual_arm.torque") + ":")
        torque_layout.addWidget(self.torque_label)

        self.torque_value_label = QLabel("255")
        self.torque_value_label.setFixedWidth(35)
        torque_layout.addWidget(self.torque_value_label)

        self.torque_slider = QSlider(Qt.Orientation.Horizontal)
        self.torque_slider.setRange(0, 255)
        self.torque_slider.setValue(255)
        self.torque_slider.valueChanged.connect(self._on_torque_change)
        torque_layout.addWidget(self.torque_slider, stretch=1)

        self.torque_apply_btn = QPushButton(t("common.apply"))
        self.torque_apply_btn.clicked.connect(self._apply_torque)
        torque_layout.addWidget(self.torque_apply_btn)

        # Connection info
        info_frame = QGroupBox(t("common.info"))
        info_layout = QVBoxLayout(info_frame)
        parent_layout.addWidget(info_frame)
        self.settings_info_frame = info_frame

        status = self.hand.get_status()
        info_text = f"CAN Interface: {status.get('can_interface', 'N/A')}\n"
        info_text += f"State: {status.get('state', 'unknown')}"

        self.info_label = QLabel(info_text)
        info_layout.addWidget(self.info_label)

        parent_layout.addStretch()

    def _build_connection_row(self, parent_layout: QVBoxLayout, side: str):
        """Build per-side connection controls (CAN entry, Setup CAN, Connect, Disconnect, status)."""
        conn_frame = QGroupBox(t("linker_hand.connection"))
        conn_layout = QHBoxLayout(conn_frame)
        parent_layout.addWidget(conn_frame)

        can_label = QLabel(t("linker_hand.can_interface"))
        conn_layout.addWidget(can_label)

        can_entry = QLineEdit(self._can_interface_text)
        can_entry.setFixedWidth(80)
        conn_layout.addWidget(can_entry)

        setup_btn = QPushButton(t("linker_hand.setup_can"))
        setup_btn.clicked.connect(lambda checked, s=side: self._setup_can(s))
        conn_layout.addWidget(setup_btn)

        connect_btn = QPushButton(t("linker_hand.connect"))
        connect_btn.clicked.connect(lambda checked, s=side: self._connect_hand(s))
        conn_layout.addWidget(connect_btn)

        disconnect_btn = QPushButton(t("linker_hand.disconnect"))
        disconnect_btn.clicked.connect(lambda checked, s=side: self._disconnect_hand(s))
        disconnect_btn.setEnabled(False)
        conn_layout.addWidget(disconnect_btn)

        status_label = QLabel(t("linker_hand.status_disconnected"))
        status_label.setStyleSheet("color: red;")
        conn_layout.addWidget(status_label)

        conn_layout.addStretch()

        # Store per-side references
        setattr(self, f"{side}_conn_frame", conn_frame)
        setattr(self, f"{side}_can_label", can_label)
        setattr(self, f"{side}_can_entry", can_entry)
        setattr(self, f"{side}_setup_can_btn", setup_btn)
        setattr(self, f"{side}_connect_btn", connect_btn)
        setattr(self, f"{side}_disconnect_btn", disconnect_btn)
        setattr(self, f"{side}_conn_status_label", status_label)

    def _get_can_interface(self) -> str:
        """Get CAN interface from whichever entry is available."""
        for side in ("left", "right"):
            entry = getattr(self, f"{side}_can_entry", None)
            if entry:
                return entry.text().strip()
        return self._can_interface_text

    def _connect_hand(self, side: str):
        """Connect a single linker hand via CAN."""
        can_if = self._get_can_interface()
        if not can_if:
            return

        self.hand._can_interface = can_if

        connect_btn = getattr(self, f"{side}_connect_btn")
        status_label = getattr(self, f"{side}_conn_status_label")
        disconnect_btn = getattr(self, f"{side}_disconnect_btn")

        connect_btn.setEnabled(False)
        status_label.setText(t("linker_hand.status_connecting"))
        status_label.setStyleSheet("color: orange;")

        def do_connect():
            success = self.hand.connect_hand(side)

            def update_ui():
                if success:
                    status_label.setText(t("linker_hand.status_connected"))
                    status_label.setStyleSheet("color: green;")
                    disconnect_btn.setEnabled(True)
                    connect_btn.setEnabled(False)
                else:
                    status_label.setText("Error: connect failed")
                    status_label.setStyleSheet("color: red;")
                    connect_btn.setEnabled(True)

            QTimer.singleShot(0, update_ui)

        threading.Thread(target=do_connect, daemon=True).start()

    def _disconnect_hand(self, side: str):
        """Disconnect a single linker hand."""
        self.hand.disconnect_hand(side)

        connect_btn = getattr(self, f"{side}_connect_btn")
        disconnect_btn = getattr(self, f"{side}_disconnect_btn")
        status_label = getattr(self, f"{side}_conn_status_label")

        status_label.setText(t("linker_hand.status_disconnected"))
        status_label.setStyleSheet("color: red;")
        connect_btn.setEnabled(True)
        disconnect_btn.setEnabled(False)

    def _setup_can(self, side: str):
        """Setup CAN interface (bring up with correct bitrate)."""
        can_if = self._get_can_interface()
        if not can_if:
            return

        status_label = getattr(self, f"{side}_conn_status_label")
        status_label.setText(t("linker_hand.status_can_setup"))
        status_label.setStyleSheet("color: orange;")

        def do_setup():
            try:
                subprocess.run(
                    ['sudo', 'ip', 'link', 'set', can_if, 'down'],
                    capture_output=True, text=True, timeout=5
                )
                result = subprocess.run(
                    ['sudo', 'ip', 'link', 'set', can_if, 'up',
                     'type', 'can', 'bitrate', '1000000'],
                    capture_output=True, text=True, timeout=10
                )
                success = result.returncode == 0

                def update_ui():
                    if success:
                        status_label.setText(
                            t("linker_hand.status_can_ready").format(iface=can_if)
                        )
                        status_label.setStyleSheet("color: blue;")
                    else:
                        status_label.setText(t("linker_hand.status_can_failed"))
                        status_label.setStyleSheet("color: red;")

                QTimer.singleShot(0, update_ui)
            except Exception as e:
                def show_error():
                    status_label.setText(f"Error: {e}")
                    status_label.setStyleSheet("color: red;")
                QTimer.singleShot(0, show_error)

        threading.Thread(target=do_setup, daemon=True).start()

    def _on_slider_change(self, side: str, index: int, value: int):
        """Sync value label and _positions when slider is moved by user."""
        labels = self.left_value_labels if side == "left" else self.right_value_labels
        pos_list = self._left_positions if side == "left" else self._right_positions
        pos_list[index] = value
        if index < len(labels):
            labels[index].setText(str(value))

    def _set_finger_value(self, side: str, index: int, value: int):
        """Set a specific finger value (updates slider, label, and _positions)."""
        sliders = self.left_sliders if side == "left" else self.right_sliders
        labels = self.left_value_labels if side == "left" else self.right_value_labels
        pos_list = self._left_positions if side == "left" else self._right_positions
        if sliders and index < len(sliders):
            sliders[index].blockSignals(True)
            sliders[index].setValue(value)
            sliders[index].blockSignals(False)
        pos_list[index] = value
        if labels and index < len(labels):
            labels[index].setText(str(value))

    def _apply_gesture(self, side: str, positions: List[int]):
        """Apply a preset gesture"""
        for i, val in enumerate(positions):
            self._set_finger_value(side, i, val)
        self._send_hand_position(side)

    def _set_all_fingers(self, side: str, value: int):
        """Set all fingers to a value"""
        for i in range(6):
            self._set_finger_value(side, i, value)
        self._send_hand_position(side)

    def get_current_left_positions(self) -> List[int]:
        """Return current left hand finger positions (0-255) from sliders. For recording poses."""
        if hasattr(self, "left_sliders") and self.left_sliders:
            return [s.value() for s in self.left_sliders]
        return list(self._left_positions)

    def get_current_right_positions(self) -> List[int]:
        """Return current right hand finger positions (0-255) from sliders. For recording poses."""
        if hasattr(self, "right_sliders") and self.right_sliders:
            return [s.value() for s in self.right_sliders]
        return list(self._right_positions)

    def _is_valid_hand_reading(self, positions) -> bool:
        """Check if hardware reading looks valid (not all zeros = uninitialized)."""
        if positions is None or len(positions) < 6:
            return False
        # All-zero reading typically means hand SDK hasn't received actual feedback yet
        if all(v == 0 for v in positions[:6]):
            return False
        return True

    def get_actual_left_positions(self) -> List[int]:
        """Read actual left hand positions from hardware, sync sliders, return values.
        Falls back to slider values if hardware read fails or returns all zeros."""
        if self.hand and self.hand.is_ready():
            real = self.hand.get_finger_positions_real("left")
            if self._is_valid_hand_reading(real):
                for i in range(6):
                    self._set_finger_value("left", i, int(round(real[i])))
                return [int(round(v)) for v in real[:6]]
        return self.get_current_left_positions()

    def get_actual_right_positions(self) -> List[int]:
        """Read actual right hand positions from hardware, sync sliders, return values.
        Falls back to slider values if hardware read fails or returns all zeros."""
        if self.hand and self.hand.is_ready():
            real = self.hand.get_finger_positions_real("right")
            if self._is_valid_hand_reading(real):
                for i in range(6):
                    self._set_finger_value("right", i, int(round(real[i])))
                return [int(round(v)) for v in real[:6]]
        return self.get_current_right_positions()

    def _get_hand_position(self, side: str):
        """Get current hand position from hardware and update sliders (only on button click).
        Only updates sliders if a valid (non-zero) reading is obtained from hardware."""
        real = self.hand.get_finger_positions_real(side)
        if self._is_valid_hand_reading(real):
            for i in range(6):
                val = int(round(real[i]))
                self._set_finger_value(side, i, val)
        else:
            logger.info(f"No valid hand reading for {side} — sliders unchanged")

    def _send_hand_position(self, side: str):
        """Send current slider positions to hand (read from sliders)."""
        sliders = self.left_sliders if side == "left" else self.right_sliders
        if sliders:
            positions = [float(s.value()) for s in sliders]
            if side == "left":
                self._left_positions[:] = [s.value() for s in sliders]
                self.hand.set_finger_positions(HandSide.LEFT, positions)
            else:
                self._right_positions[:] = [s.value() for s in sliders]
                self.hand.set_finger_positions(HandSide.RIGHT, positions)

    def _on_speed_change(self, value: int):
        """Handle speed slider change"""
        self._speed = value
        if hasattr(self, 'speed_value_label'):
            self.speed_value_label.setText(str(self._speed))

    def _on_torque_change(self, value: int):
        """Handle torque slider change"""
        self._torque = value
        if hasattr(self, 'torque_value_label'):
            self.torque_value_label.setText(str(self._torque))

    def _apply_speed(self):
        """Apply speed setting"""
        # TODO: Implement when hand controller supports speed setting
        logger.info(f"Set hand speed to {self._speed}")

    def _apply_torque(self):
        """Apply torque setting"""
        # TODO: Implement when hand controller supports torque setting
        logger.info(f"Set hand torque to {self._torque}")

    def closeEvent(self, event):
        """Stop background polling on close."""
        self._stop_touch_poll()
        super().closeEvent(event)

    def _schedule_update(self):
        """Schedule periodic update using QTimer."""
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._safe_update_display)
        self._update_timer.start(500)

    def _safe_update_display(self):
        """Wrapper for _update_display that tolerates errors."""
        try:
            self._update_display()
        except Exception as e:
            logger.debug("Linker hand display update failed: %s", e)

    def _update_display(self):
        """Update status; when connected, push live finger positions to sliders so they show current pose."""
        if not self.hand:
            return
        try:
            status = self.hand.get_status()
        except Exception as e:
            logger.debug("Linker hand get_status: %s", e)
            status = {"can_interface": "N/A", "state": "unknown"}
        try:
            info_text = f"CAN Interface: {status.get('can_interface', 'N/A')}\n"
            info_text += f"State: {status.get('state', 'unknown')}"
            if hasattr(self, "info_label"):
                self.info_label.setText(info_text)
        except Exception as e:
            logger.debug("Linker hand info label: %s", e)
        # Sliders are NOT updated by the timer. Current finger position is shown only
        # when the user presses "Get position". This keeps sliders fully user-controllable.

    def update_language(self):
        """Update all visible text when language changes (L6 hands tab fully bilingual)."""
        # Notebook tabs
        self.notebook.setTabText(0, t("hardware.left_hand"))
        self.notebook.setTabText(1, t("hardware.right_hand"))
        self.notebook.setTabText(2, t("common.settings"))

        # Per-side connection frames
        for side in ("left", "right"):
            cf = getattr(self, f"{side}_conn_frame", None)
            if cf:
                cf.setTitle(t("linker_hand.connection"))
            cl = getattr(self, f"{side}_can_label", None)
            if cl:
                cl.setText(t("linker_hand.can_interface"))
            sb = getattr(self, f"{side}_setup_can_btn", None)
            if sb:
                sb.setText(t("linker_hand.setup_can"))
            cb = getattr(self, f"{side}_connect_btn", None)
            if cb:
                cb.setText(t("linker_hand.connect"))
            db = getattr(self, f"{side}_disconnect_btn", None)
            if db:
                db.setText(t("linker_hand.disconnect"))

        from config.i18n import get_i18n
        lang = get_i18n().language.value if get_i18n() else "en"
        finger_names = FINGER_NAMES.get(lang, FINGER_NAMES["en"])

        # Finger labels
        for i, name in enumerate(finger_names):
            if hasattr(self, "left_slider_labels") and i < len(self.left_slider_labels):
                self.left_slider_labels[i].setText(name + ":")
            if hasattr(self, "right_slider_labels") and i < len(self.right_slider_labels):
                self.right_slider_labels[i].setText(name + ":")

        # Left/right panel frames and buttons
        for side in ("left", "right"):
            sf = getattr(self, f"{side}_slider_frame", None)
            if sf:
                sf.setTitle(t("dual_arm.finger_control"))
            pf = getattr(self, f"{side}_preset_frame", None)
            if pf:
                pf.setTitle(t("dual_arm.presets"))
            tf = getattr(self, f"{side}_touch_frame", None)
            if tf:
                tf.setTitle(t("dual_arm.touch_sensor"))
            preset_btns = getattr(self, f"{side}_preset_buttons", [])
            for j, btn in enumerate(preset_btns):
                if j < len(getattr(self, "_preset_gesture_keys", [])):
                    btn.setText(t(self._preset_gesture_keys[j]))
            for attr, key in [
                (f"{side}_get_btn", "dual_arm.get_position"),
                (f"{side}_send_btn", "dual_arm.send_position"),
                (f"{side}_zero_btn", "dual_arm.set_all_zero"),
            ]:
                b = getattr(self, attr, None)
                if b:
                    b.setText(t(key))

        # Settings panel
        if hasattr(self, "settings_speed_frame"):
            self.settings_speed_frame.setTitle(t("dual_arm.speed"))
            self.speed_label.setText(t("dual_arm.speed") + ":")
            self.speed_apply_btn.setText(t("common.apply"))
        if hasattr(self, "settings_torque_frame"):
            self.settings_torque_frame.setTitle(t("dual_arm.torque"))
            self.torque_label.setText(t("dual_arm.torque") + ":")
            self.torque_apply_btn.setText(t("common.apply"))
        if hasattr(self, "settings_info_frame"):
            self.settings_info_frame.setTitle(t("common.info"))

        # Touch matrix finger names
        touch_names = TOUCH_FINGER_NAMES.get(lang, TOUCH_FINGER_NAMES["en"])
        finger_keys = ["thumb", "index", "middle", "ring", "little"]
        for matrices in [getattr(self, "left_matrices", {}), getattr(self, "right_matrices", {})]:
            for i, key in enumerate(finger_keys):
                matrix_key = f"{key}_matrix"
                if matrix_key in matrices:
                    matrices[matrix_key].setTitle(touch_names[i])
