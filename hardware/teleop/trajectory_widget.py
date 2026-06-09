"""
Trajectory Widget Module
轨迹部件模块

PySide6 widget for trajectory visualization and preview.
轨迹可视化和预览的 PySide6 部件。
"""

import math
from typing import List, Dict, Optional, Tuple, Any

from gui.qt_imports import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QRadioButton, QButtonGroup,
    QPainter, QPen, QBrush, QColor, QPointF, Qt,
    QSizePolicy,
)


class TrajectoryCanvas(QWidget):
    """
    Canvas for 2D trajectory visualization.
    2D 轨迹可视化画布。
    """

    def __init__(self, parent=None, width: int = 300, height: int = 300):
        """
        Initialize trajectory canvas.
        初始化轨迹画布。
        """
        super().__init__(parent)

        self._width = width
        self._height = height
        self._points: List[Tuple[float, float, float]] = []  # (x, y, z)
        self._view = "xy"  # "xy", "xz", "yz"
        self._scale = 1.0
        self._offset_x = width // 2
        self._offset_y = height // 2

        self.setMinimumSize(width, height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background-color: white; border: 1px solid #cccccc;")

    def resizeEvent(self, event):
        """Handle resize / 处理调整大小"""
        super().resizeEvent(event)
        self._width = event.size().width()
        self._height = event.size().height()
        self._offset_x = self._width // 2
        self._offset_y = self._height // 2
        self.update()  # trigger repaint

    def paintEvent(self, event):
        """Paint the canvas / 绘制画布"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._draw_grid(painter)
        self._draw_trajectory(painter)

        painter.end()

    def _draw_grid(self, painter: QPainter):
        """Draw grid / 绘制网格"""
        # Draw grid lines
        grid_pen = QPen(QColor('#f0f0f0'))
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)

        spacing = 50
        for x in range(0, self._width, spacing):
            painter.drawLine(x, 0, x, self._height)
        for y in range(0, self._height, spacing):
            painter.drawLine(0, y, self._width, y)

        # Draw center axes
        axis_pen = QPen(QColor('#e0e0e0'))
        axis_pen.setWidth(1)
        painter.setPen(axis_pen)
        painter.drawLine(0, self._height // 2, self._width, self._height // 2)
        painter.drawLine(self._width // 2, 0, self._width // 2, self._height)

        # Axis labels
        labels = {"xy": ("X", "Y"), "xz": ("X", "Z"), "yz": ("Y", "Z")}
        h_label, v_label = labels.get(self._view, ("X", "Y"))
        painter.setPen(QColor('#000000'))
        painter.drawText(self._width - 15, self._height // 2 - 10, h_label)
        painter.drawText(self._width // 2 + 10, 15, v_label)

    def _draw_trajectory(self, painter: QPainter):
        """Draw trajectory points and lines / 绘制轨迹点和线"""
        if not self._points:
            return

        if len(self._points) < 2:
            # Draw single point
            sx, sy = self._world_to_screen(*self._points[0])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor('#1890ff'))
            painter.drawEllipse(QPointF(sx, sy), 5, 5)
            return

        # Draw trajectory line
        line_pen = QPen(QColor('#1890ff'))
        line_pen.setWidth(2)
        painter.setPen(line_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        for i in range(len(self._points) - 1):
            sx1, sy1 = self._world_to_screen(*self._points[i])
            sx2, sy2 = self._world_to_screen(*self._points[i + 1])
            painter.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))

        # Draw start point (green)
        sx, sy = self._world_to_screen(*self._points[0])
        painter.setPen(QPen(QColor('#389e0d'), 2))
        painter.setBrush(QColor('#52c41a'))
        painter.drawEllipse(QPointF(sx, sy), 6, 6)

        # Draw end point (red)
        sx, sy = self._world_to_screen(*self._points[-1])
        painter.setPen(QPen(QColor('#cf1322'), 2))
        painter.setBrush(QColor('#ff4d4f'))
        painter.drawEllipse(QPointF(sx, sy), 6, 6)

        # Draw waypoints
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#1890ff'))
        for i, p in enumerate(self._points[1:-1], 1):
            sx, sy = self._world_to_screen(*p)
            painter.drawEllipse(QPointF(sx, sy), 3, 3)

    def set_view(self, view: str):
        """Set view plane / 设置视图平面"""
        self._view = view
        self._redraw()

    def set_trajectory(self, points: List[Tuple[float, float, float]]):
        """
        Set trajectory points.
        设置轨迹点。

        Args:
            points: List of (x, y, z) tuples in mm
        """
        self._points = points
        self._auto_scale()
        self._redraw()

    def add_point(self, x: float, y: float, z: float):
        """Add single point / 添加单个点"""
        self._points.append((x, y, z))
        self._auto_scale()
        self._redraw()

    def clear(self):
        """Clear trajectory / 清除轨迹"""
        self._points = []
        self._redraw()

    def _auto_scale(self):
        """Auto-calculate scale to fit points / 自动计算缩放以适应点"""
        if not self._points:
            self._scale = 1.0
            return

        # Get range
        xs = [p[0] for p in self._points]
        ys = [p[1] for p in self._points]
        zs = [p[2] for p in self._points]

        if self._view == "xy":
            h_range = max(xs) - min(xs) if xs else 1
            v_range = max(ys) - min(ys) if ys else 1
        elif self._view == "xz":
            h_range = max(xs) - min(xs) if xs else 1
            v_range = max(zs) - min(zs) if zs else 1
        else:  # yz
            h_range = max(ys) - min(ys) if ys else 1
            v_range = max(zs) - min(zs) if zs else 1

        max_range = max(h_range, v_range, 100)
        self._scale = min(self._width, self._height) * 0.8 / max_range

    def _world_to_screen(self, x: float, y: float, z: float) -> Tuple[int, int]:
        """Convert world coordinates to screen / 将世界坐标转换为屏幕坐标"""
        if self._view == "xy":
            sx = self._offset_x + x * self._scale
            sy = self._offset_y - y * self._scale  # Y is inverted
        elif self._view == "xz":
            sx = self._offset_x + x * self._scale
            sy = self._offset_y - z * self._scale
        else:  # yz
            sx = self._offset_x + y * self._scale
            sy = self._offset_y - z * self._scale

        return int(sx), int(sy)

    def _redraw(self):
        """Redraw trajectory / 重绘轨迹"""
        self.update()  # triggers paintEvent


class TrajectoryWidget(QGroupBox):
    """
    Widget for trajectory visualization and control.
    轨迹可视化和控制部件。
    """

    def __init__(self, parent, language: str = "en", **kwargs):
        """
        Initialize trajectory widget.
        初始化轨迹部件。

        Args:
            parent: Parent widget
            language: Display language
        """
        title = "Trajectory Preview" if language == "en" else "轨迹预览"
        super().__init__(title, parent)

        self._language = language
        self._trajectory_data: List[Dict[str, Any]] = []

        self._create_widgets()

    def _create_widgets(self):
        """Create child widgets / 创建子部件"""
        main_layout = QVBoxLayout(self)

        # View selection
        view_layout = QHBoxLayout()
        main_layout.addLayout(view_layout)

        self._view_label = QLabel("View:" if self._language == "en" else "视图:")
        view_layout.addWidget(self._view_label)

        self._view_button_group = QButtonGroup(self)
        self._view_radios = {}
        self._selected_view = "xy"

        for view, label in [("xy", "X-Y"), ("xz", "X-Z"), ("yz", "Y-Z")]:
            radio = QRadioButton(label)
            self._view_button_group.addButton(radio)
            radio.toggled.connect(lambda checked, v=view: self._on_view_change(v) if checked else None)
            view_layout.addWidget(radio)
            self._view_radios[view] = radio

        self._view_radios["xy"].setChecked(True)
        view_layout.addStretch()

        # Trajectory canvas
        self.canvas = TrajectoryCanvas(self)
        main_layout.addWidget(self.canvas, 1)  # stretch factor 1

        # Info display
        info_layout = QHBoxLayout()
        main_layout.addLayout(info_layout)

        self.info_label = QLabel("Points: 0 | Duration: -- | Length: --")
        info_layout.addWidget(self.info_label)
        info_layout.addStretch()

        # Control buttons
        btn_layout = QHBoxLayout()
        main_layout.addLayout(btn_layout)

        clear_text = "Clear" if self._language == "en" else "清除"
        clear_btn = QPushButton(clear_text)
        clear_btn.clicked.connect(self._clear)
        btn_layout.addWidget(clear_btn)

        zoom_in_text = "Zoom In" if self._language == "en" else "放大"
        zoom_in_btn = QPushButton(zoom_in_text)
        zoom_in_btn.clicked.connect(self._zoom_in)
        btn_layout.addWidget(zoom_in_btn)

        zoom_out_text = "Zoom Out" if self._language == "en" else "缩小"
        zoom_out_btn = QPushButton(zoom_out_text)
        zoom_out_btn.clicked.connect(self._zoom_out)
        btn_layout.addWidget(zoom_out_btn)

        btn_layout.addStretch()

    def _on_view_change(self, view: str):
        """Handle view change / 处理视图变化"""
        self._selected_view = view
        self.canvas.set_view(view)

    def set_trajectory(self, points: List[Dict[str, Any]]):
        """
        Set trajectory data.
        设置轨迹数据。

        Args:
            points: List of trajectory points with 'position' key
        """
        self._trajectory_data = points

        # Extract positions
        xyz_points = []
        for p in points:
            pos = p.get('position', p.get('tcp', {}))
            if pos:
                xyz_points.append((
                    pos.get('x', 0),
                    pos.get('y', 0),
                    pos.get('z', 0)
                ))

        self.canvas.set_trajectory(xyz_points)
        self._update_info()

    def add_point(self, point: Dict[str, Any]):
        """Add single trajectory point / 添加单个轨迹点"""
        self._trajectory_data.append(point)

        pos = point.get('position', point.get('tcp', {}))
        if pos:
            self.canvas.add_point(pos.get('x', 0), pos.get('y', 0), pos.get('z', 0))

        self._update_info()

    def _update_info(self):
        """Update info display / 更新信息显示"""
        num_points = len(self._trajectory_data)

        # Calculate total length
        total_length = 0
        points = []
        for p in self._trajectory_data:
            pos = p.get('position', p.get('tcp', {}))
            if pos:
                points.append((pos.get('x', 0), pos.get('y', 0), pos.get('z', 0)))

        if len(points) >= 2:
            for i in range(1, len(points)):
                dx = points[i][0] - points[i - 1][0]
                dy = points[i][1] - points[i - 1][1]
                dz = points[i][2] - points[i - 1][2]
                total_length += math.sqrt(dx * dx + dy * dy + dz * dz)

        # Duration (if timestamps available)
        duration = "--"
        if self._trajectory_data:
            first = self._trajectory_data[0].get('timestamp', 0)
            last = self._trajectory_data[-1].get('timestamp', 0)
            if first and last:
                duration = f"{last - first:.1f}s"

        info = f"Points: {num_points} | Duration: {duration} | Length: {total_length:.1f}mm"
        self.info_label.setText(info)

    def _clear(self):
        """Clear trajectory / 清除轨迹"""
        self._trajectory_data = []
        self.canvas.clear()
        self._update_info()

    def _zoom_in(self):
        """Zoom in / 放大"""
        self.canvas._scale *= 1.2
        self.canvas._redraw()

    def _zoom_out(self):
        """Zoom out / 缩小"""
        self.canvas._scale /= 1.2
        self.canvas._redraw()

    def get_trajectory(self) -> List[Dict[str, Any]]:
        """Get trajectory data / 获取轨迹数据"""
        return self._trajectory_data.copy()

    def update_language(self, language: str):
        """Update display language / 更新显示语言"""
        self._language = language
