"""
Gloves Widget Module
手套部件模块

PySide6 widget for gloves teleoperation control.
手套遥操作控制的 PySide6 部件。
"""

import threading
from typing import Optional, Dict

from gui.qt_imports import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QPushButton, QLineEdit, QSlider, QFont,
    QPainter, QPen, QBrush, QColor, QPointF, Qt,
    QSizePolicy, QTimer,
)

from .gloves_controller import GlovesController, GlovesState, HandData
from .ros_connection import ROSConnection
from gui.signals import get_thread_bridge


class HandVisualizationWidget(QWidget):
    """
    Simple hand visualization canvas.
    简单的手部可视化画布。
    """

    def __init__(self, parent=None, hand_side: str = "left", width: int = 150, height: int = 200):
        """
        Initialize hand visualization.
        初始化手部可视化。

        Args:
            parent: Parent widget
            hand_side: "left" or "right"
            width: Canvas width
            height: Canvas height
        """
        super().__init__(parent)

        self._hand_side = hand_side
        self._finger_positions = [0.0] * 5  # thumb, index, middle, ring, pinky

        self.setFixedSize(width, height)
        self.setStyleSheet("background-color: white; border: 1px solid #cccccc;")

    def paintEvent(self, event):
        """Paint the hand visualization / 绘制手部可视化"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Palm
        palm_x = w / 2
        palm_y = h * 0.6
        palm_w = w * 0.5
        palm_h = h * 0.3

        painter.setPen(QPen(QColor('#999999'), 2))
        painter.setBrush(QColor('#e0e0e0'))
        painter.drawEllipse(
            QPointF(palm_x, palm_y),
            palm_w / 2, palm_h / 2
        )

        # Finger positions (relative to palm)
        finger_bases = [
            (palm_x - palm_w * 0.4, palm_y - palm_h * 0.4),  # Thumb
            (palm_x - palm_w * 0.2, palm_y - palm_h * 0.5),  # Index
            (palm_x, palm_y - palm_h * 0.55),                 # Middle
            (palm_x + palm_w * 0.2, palm_y - palm_h * 0.5),   # Ring
            (palm_x + palm_w * 0.35, palm_y - palm_h * 0.4),  # Pinky
        ]

        finger_lengths = [h * 0.2, h * 0.25, h * 0.28, h * 0.25, h * 0.2]
        finger_widths = [w * 0.08, w * 0.06, w * 0.06, w * 0.06, w * 0.05]

        # Draw fingers
        for i, ((bx, by), length, fw) in enumerate(zip(finger_bases, finger_lengths, finger_widths)):
            # Calculate bend (0 = straight up, 1 = fully bent)
            bend = self._finger_positions[i]

            # Calculate finger tip position
            # When bent, finger curls toward palm
            tip_y = by - length * (1 - bend * 0.7)
            tip_x = bx

            # Color based on bend
            intensity = int(255 * (1 - bend))
            color = QColor(intensity, 200, intensity)

            # Draw finger
            pen = QPen(color, fw)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(bx, by), QPointF(tip_x, tip_y))

            # Draw fingertip
            painter.setPen(QPen(QColor('#666666'), 1))
            painter.setBrush(color)
            painter.drawEllipse(QPointF(tip_x, tip_y), fw / 2, fw / 2)

        # Label
        label = "L" if self._hand_side == "left" else "R"
        painter.setPen(QColor('#000000'))
        font = QFont("Arial", 12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(10, 20, label)

        painter.end()

    def update_fingers(self, positions: list):
        """
        Update finger positions and redraw.
        更新手指位置并重绘。

        Args:
            positions: List of 5 finger positions (0-1)
        """
        self._finger_positions = positions[:5] + [0.0] * (5 - len(positions))
        self.update()  # trigger repaint


class GlovesWidget(QGroupBox):
    """
    Widget for gloves teleoperation control.
    手套遥操作控制部件。
    """

    def __init__(self, parent, controller: Optional[GlovesController] = None,
                 ros_connection: Optional[ROSConnection] = None,
                 language: str = "en", **kwargs):
        """
        Initialize gloves widget.
        初始化手套部件。

        Args:
            parent: Parent widget
            controller: GlovesController instance
            ros_connection: ROSConnection instance
            language: Display language
        """
        title = "Gloves Teleoperation" if language == "en" else "手套遥操作"
        super().__init__(title, parent)

        self._language = language
        self._ros = ros_connection or ROSConnection()
        self._controller = controller or GlovesController(self._ros)

        # Poll timer
        self._poll_timer = None

        self._create_widgets()
        self._setup_callbacks()

    def _create_widgets(self):
        """Create child widgets / 创建子部件"""
        main_layout = QVBoxLayout(self)

        # Connection frame
        conn_frame = QGroupBox("ROS Connection" if self._language == "en" else "ROS连接")
        conn_layout = QGridLayout(conn_frame)
        main_layout.addWidget(conn_frame)

        conn_layout.addWidget(QLabel("Host:"), 0, 0)
        self.host_entry = QLineEdit("localhost")
        self.host_entry.setFixedWidth(120)
        conn_layout.addWidget(self.host_entry, 0, 1)

        conn_layout.addWidget(QLabel("Port:"), 0, 2)
        self.port_entry = QLineEdit("9090")
        self.port_entry.setFixedWidth(60)
        conn_layout.addWidget(self.port_entry, 0, 3)

        connect_text = "Connect" if self._language == "en" else "连接"
        self.connect_btn = QPushButton(connect_text)
        self.connect_btn.clicked.connect(self._connect)
        conn_layout.addWidget(self.connect_btn, 0, 4)

        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("color: red;")
        conn_layout.addWidget(self.status_label, 0, 5)

        # Topic configuration
        topic_frame = QGroupBox("Topics" if self._language == "en" else "话题")
        topic_layout = QGridLayout(topic_frame)
        main_layout.addWidget(topic_frame)

        topic_layout.addWidget(QLabel("Left:"), 0, 0)
        self.left_topic_entry = QLineEdit("/gloves/left_hand")
        self.left_topic_entry.setMinimumWidth(200)
        topic_layout.addWidget(self.left_topic_entry, 0, 1)

        topic_layout.addWidget(QLabel("Right:"), 1, 0)
        self.right_topic_entry = QLineEdit("/gloves/right_hand")
        self.right_topic_entry.setMinimumWidth(200)
        topic_layout.addWidget(self.right_topic_entry, 1, 1)

        # Smoothing
        smoothing_label_text = "Smoothing:" if self._language == "en" else "平滑:"
        topic_layout.addWidget(QLabel(smoothing_label_text), 2, 0)
        self.smoothing_slider = QSlider(Qt.Orientation.Horizontal)
        self.smoothing_slider.setRange(0, 100)
        self.smoothing_slider.setValue(80)  # 0.8 * 100
        self.smoothing_slider.setFixedWidth(150)
        topic_layout.addWidget(self.smoothing_slider, 2, 1)

        # Hand visualization
        viz_frame = QGroupBox("Hand Tracking" if self._language == "en" else "手部跟踪")
        viz_layout = QHBoxLayout(viz_frame)
        main_layout.addWidget(viz_frame, 1)  # stretch

        self.left_viz = HandVisualizationWidget(viz_frame, hand_side="left")
        viz_layout.addWidget(self.left_viz)

        self.right_viz = HandVisualizationWidget(viz_frame, hand_side="right")
        viz_layout.addWidget(self.right_viz)

        # Finger values display
        values_layout = QVBoxLayout()
        viz_layout.addLayout(values_layout)

        courier_font = QFont("Courier", 9)

        self.left_values_label = QLabel("Left:\n---")
        self.left_values_label.setFont(courier_font)
        values_layout.addWidget(self.left_values_label)

        self.right_values_label = QLabel("Right:\n---")
        self.right_values_label.setFont(courier_font)
        values_layout.addWidget(self.right_values_label)

        values_layout.addStretch()

        # Control buttons
        btn_layout = QHBoxLayout()
        main_layout.addLayout(btn_layout)

        start_text = "Start Gloves" if self._language == "en" else "启动手套"
        self.start_btn = QPushButton(start_text)
        self.start_btn.clicked.connect(self._start_gloves)
        self.start_btn.setEnabled(False)
        btn_layout.addWidget(self.start_btn)

        stop_text = "Stop Gloves" if self._language == "en" else "停止手套"
        self.stop_btn = QPushButton(stop_text)
        self.stop_btn.clicked.connect(self._stop_gloves)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)

        calibrate_text = "Calibrate" if self._language == "en" else "校准"
        self.calibrate_btn = QPushButton(calibrate_text)
        self.calibrate_btn.clicked.connect(self._calibrate)
        self.calibrate_btn.setEnabled(False)
        btn_layout.addWidget(self.calibrate_btn)

        btn_layout.addStretch()

    def _setup_callbacks(self):
        """Setup controller callbacks / 设置控制器回调"""
        self._controller.add_state_callback(self._on_state_changed)
        self._controller.add_data_callback(self._on_hand_data)

    def _connect(self):
        """Connect to ROS / 连接到 ROS"""
        host = self.host_entry.text()
        port = int(self.port_entry.text())

        self.status_label.setText("Connecting...")
        self.status_label.setStyleSheet("color: orange;")

        bridge = get_thread_bridge()

        def do_connect():
            success = self._ros.connect(host, port)

            def update_ui():
                if success:
                    self.status_label.setText("ROS Connected")
                    self.status_label.setStyleSheet("color: green;")
                    self.connect_btn.setText("Disconnect" if self._language == "en" else "断开")
                    self.start_btn.setEnabled(True)
                else:
                    self.status_label.setText("Connection failed")
                    self.status_label.setStyleSheet("color: red;")

            bridge.gui_callback.emit(update_ui)

        threading.Thread(target=do_connect, daemon=True).start()

    def _start_gloves(self):
        """Start gloves tracking / 开始手套跟踪"""
        # Configure controller
        self._controller.configure(
            left_topic=self.left_topic_entry.text(),
            right_topic=self.right_topic_entry.text(),
            smoothing_factor=self.smoothing_slider.value() / 100.0
        )

        if self._controller.connect():
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.calibrate_btn.setEnabled(True)
            self._start_polling()

    def _stop_gloves(self):
        """Stop gloves tracking / 停止手套跟踪"""
        self._stop_polling()
        self._controller.disconnect()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.calibrate_btn.setEnabled(False)

    def _calibrate(self):
        """Calibrate gloves / 校准手套"""
        self._controller.start_calibration()

    def _start_polling(self):
        """Start UI polling / 开始 UI 轮询"""
        if self._poll_timer:
            return

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)  # 20 Hz
        self._poll_timer.timeout.connect(self._update_display)
        self._poll_timer.start()

    def _stop_polling(self):
        """Stop UI polling / 停止 UI 轮询"""
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer = None

    def _update_display(self):
        """Update visualization / 更新可视化"""
        left = self._controller.left_hand
        right = self._controller.right_hand

        self.left_viz.update_fingers(left.to_finger_list())
        self.right_viz.update_fingers(right.to_finger_list())

        left_text = f"Left:\nT:{left.thumb:.2f} I:{left.index:.2f}\nM:{left.middle:.2f} R:{left.ring:.2f}\nP:{left.pinky:.2f}"
        self.left_values_label.setText(left_text)

        right_text = f"Right:\nT:{right.thumb:.2f} I:{right.index:.2f}\nM:{right.middle:.2f} R:{right.ring:.2f}\nP:{right.pinky:.2f}"
        self.right_values_label.setText(right_text)

    def _on_state_changed(self, state: GlovesState):
        """Handle state change / 处理状态变化"""
        pass

    def _on_hand_data(self, side: str, data: HandData):
        """Handle hand data update / 处理手部数据更新"""
        pass

    def update_language(self, language: str):
        """Update display language / 更新显示语言"""
        self._language = language

    def shutdown(self):
        """Clean shutdown / 清理关闭"""
        self._stop_polling()
        self._controller.disconnect()
        self._ros.disconnect()
