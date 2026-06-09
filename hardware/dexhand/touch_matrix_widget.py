"""
Touch Matrix Widget Module
触觉矩阵显示部件模块

PySide6 widgets for displaying touch sensor matrix heatmaps.
用于显示触觉传感器矩阵热力图的 PySide6 部件。
"""

from gui.qt_imports import (
    QWidget, QGroupBox, QLabel, QHBoxLayout, QVBoxLayout,
    QPainter, QPen, QBrush, QColor, QFont, QSize, QPaintEvent,
)
from typing import Dict, List, Optional, Any


class TouchMatrixCanvas(QWidget):
    """
    Canvas widget for displaying finger touch sensor matrix heatmap.
    用于显示手指触觉传感器矩阵热力图的画布部件。
    """

    def __init__(self, parent=None, rows: int = 12, cols: int = 6,
                 dot_size: int = 6, spacing: int = 3, **kwargs):
        """
        Initialize touch matrix canvas.
        初始化触觉矩阵画布。

        Args:
            parent: Parent widget
            rows: Number of rows in matrix
            cols: Number of columns in matrix
            dot_size: Size of each dot in pixels
            spacing: Spacing between dots in pixels
        """
        super().__init__(parent)
        self.rows = rows
        self.cols = cols
        self.dot_size = dot_size
        self.spacing = spacing

        # Calculate canvas size
        width = cols * (dot_size + spacing) + spacing + 4
        height = rows * (dot_size + spacing) + spacing + 4

        self.setFixedSize(width, height)
        self.setStyleSheet("background-color: white; border: 1px solid #cccccc;")

        self.data: Optional[List[int]] = None

    def paintEvent(self, event: QPaintEvent):
        """Paint the matrix dots / 绘制矩阵点"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outline_color = QColor('#666666')

        for row in range(self.rows):
            for col in range(self.cols):
                x = self.spacing + col * (self.dot_size + self.spacing) + 2
                y = self.spacing + row * (self.dot_size + self.spacing) + 2

                color_str = '#c8c8c8'  # Default gray

                if self.data is not None:
                    try:
                        index = row * self.cols + col
                        if index < len(self.data):
                            value = self.data[index]
                            # Handle numpy types
                            if hasattr(value, 'item'):
                                value = value.item()
                            if value > 0:
                                color_str = self._value_to_color(value)
                    except Exception:
                        pass

                painter.setPen(QPen(outline_color))
                painter.setBrush(QBrush(QColor(color_str)))
                painter.drawEllipse(x, y, self.dot_size, self.dot_size)

        painter.end()

    def set_data(self, data: Optional[Any]):
        """
        Set matrix data and redraw.
        设置矩阵数据并重绘。

        Args:
            data: List/array of sensor values (0-255)
        """
        if data is not None:
            try:
                # Handle numpy arrays
                if hasattr(data, 'tolist'):
                    self.data = data.tolist()
                elif hasattr(data, 'flatten'):
                    self.data = list(data.flatten())
                else:
                    self.data = list(data) if data else None
            except Exception:
                self.data = None
        else:
            self.data = None
        self.update()

    def _value_to_color(self, value: int) -> str:
        """
        Convert sensor value to color.
        将传感器值转换为颜色。

        Uses gradient from white (0) -> yellow -> red (255)
        使用从白色（0）到黄色到红色（255）的渐变

        Args:
            value: Sensor value (0-255)

        Returns:
            Hex color string
        """
        intensity = min(255, max(0, int(value)))

        if intensity < 128:
            # White to yellow gradient
            red = 255
            green = 255 - (intensity * 55 // 128)
            blue = 255 - (intensity * 55 // 128)
        else:
            # Yellow to red gradient
            red = 255
            green = 200 - ((intensity - 128) * 200 // 127)
            blue = 200 - ((intensity - 128) * 200 // 127)

        return f'#{red:02x}{green:02x}{blue:02x}'

    def get_max_value(self) -> int:
        """Get maximum value in current data / 获取当前数据中的最大值"""
        if not self.data:
            return 0

        valid_values = [v for v in self.data if isinstance(v, (int, float)) and v >= 0]
        return int(max(valid_values)) if valid_values else 0

    def clear(self):
        """Clear matrix data / 清除矩阵数据"""
        self.data = None
        self.update()


class FingerMatrixDisplay(QGroupBox):
    """
    Widget displaying touch matrices for all 5 fingers.
    显示所有 5 个手指触觉矩阵的部件。
    """

    # Finger names for display
    FINGER_ORDER = [
        ("thumb", "Thumb", "拇指"),
        ("index", "Index", "食指"),
        ("middle", "Middle", "中指"),
        ("ring", "Ring", "无名指"),
        ("little", "Little", "小指"),
    ]

    def __init__(self, parent=None, language: str = "en", **kwargs):
        """
        Initialize finger matrix display.
        初始化手指矩阵显示。

        Args:
            parent: Parent widget
            language: Display language ("en" or "zh")
        """
        title = "Touch Sensor Heatmap" if language == "en" else "触觉传感器热力图"
        super().__init__(title, parent)

        self._language = language
        self.matrices: Dict[str, TouchMatrixCanvas] = {}
        self.value_labels: Dict[str, QLabel] = {}
        self._create_widgets()

    def _create_widgets(self):
        """Create child widgets / 创建子部件"""
        main_layout = QVBoxLayout(self)

        # Row 1: Thumb, Index, Middle
        row1_layout = QHBoxLayout()
        main_layout.addLayout(row1_layout)

        for key, name_en, name_zh in self.FINGER_ORDER[:3]:
            frame_layout = QVBoxLayout()
            row1_layout.addLayout(frame_layout)
            row1_layout.addSpacing(10)

            name = name_zh if self._language == "zh" else name_en
            name_label = QLabel(name)
            name_label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            frame_layout.addWidget(name_label)

            matrix = TouchMatrixCanvas()
            frame_layout.addWidget(matrix)
            self.matrices[key] = matrix

            # Value label
            val_label = QLabel("Max: 0")
            val_label.setFont(QFont("Arial", 8))
            frame_layout.addWidget(val_label)
            self.value_labels[key] = val_label

        row1_layout.addStretch()

        # Row 2: Ring, Little
        row2_layout = QHBoxLayout()
        main_layout.addLayout(row2_layout)

        for key, name_en, name_zh in self.FINGER_ORDER[3:]:
            frame_layout = QVBoxLayout()
            row2_layout.addLayout(frame_layout)
            row2_layout.addSpacing(10)

            name = name_zh if self._language == "zh" else name_en
            name_label = QLabel(name)
            name_label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            frame_layout.addWidget(name_label)

            matrix = TouchMatrixCanvas()
            frame_layout.addWidget(matrix)
            self.matrices[key] = matrix

            # Value label
            val_label = QLabel("Max: 0")
            val_label.setFont(QFont("Arial", 8))
            frame_layout.addWidget(val_label)
            self.value_labels[key] = val_label

        row2_layout.addStretch()
        main_layout.addStretch()

    def update_finger(self, finger: str, data: Any):
        """
        Update data for a specific finger.
        更新特定手指的数据。

        Args:
            finger: Finger key ("thumb", "index", "middle", "ring", "little")
            data: Matrix data
        """
        if finger in self.matrices:
            self.matrices[finger].set_data(data)
            max_val = self.matrices[finger].get_max_value()
            if finger in self.value_labels:
                self.value_labels[finger].setText(f"Max: {max_val}")

    def update_all(self, touch_data: Optional[Any]):
        """
        Update all fingers from TouchData.
        从 TouchData 更新所有手指。

        Args:
            touch_data: TouchData instance or dict with finger data
        """
        if touch_data is None:
            self.clear_all()
            return

        for key, _, _ in self.FINGER_ORDER:
            data = None
            if hasattr(touch_data, key):
                data = getattr(touch_data, key)
            elif isinstance(touch_data, dict):
                data = touch_data.get(key)

            if key in self.matrices:
                self.matrices[key].set_data(data)
                max_val = self.matrices[key].get_max_value()
                if key in self.value_labels:
                    self.value_labels[key].setText(f"Max: {max_val}")

    def get_max_values(self) -> Dict[str, int]:
        """
        Get maximum force values for all fingers.
        获取所有手指的最大力值。

        Returns:
            Dictionary mapping finger keys to max values
        """
        return {
            key: self.matrices[key].get_max_value()
            for key in self.matrices
        }

    def clear_all(self):
        """Clear all matrices / 清除所有矩阵"""
        for matrix in self.matrices.values():
            matrix.clear()
        for label in self.value_labels.values():
            label.setText("Max: 0")

    def update_language(self, language: str):
        """
        Update display language.
        更新显示语言。

        Args:
            language: "en" or "zh"
        """
        self._language = language
        title = "Touch Sensor Heatmap" if language == "en" else "触觉传感器热力图"
        self.setTitle(title)
