"""
Emergency Button Widget (PySide6)
紧急停止按钮部件

A large, prominent emergency stop button with visual feedback.
一个大的、醒目的紧急停止按钮，带有视觉反馈。
"""

import threading
from gui.qt_imports import (
    QWidget, QFrame, QVBoxLayout, QLabel, QPushButton,
    QPainter, QColor, QBrush, QPen, Qt, QSize, QFont, QRect,
    QMouseEvent, QPaintEvent,
)
from config.i18n import t
from app_core.emergency_controller import get_emergency_controller
from app_core.logger import get_logger

logger = get_logger(__name__)


class EmergencyButton(QWidget):
    """
    Emergency stop button widget with custom painting.
    紧急停止按钮部件，使用自定义绘制。
    """

    def __init__(self, parent=None, size=100, on_emergency=None, on_release=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._size = size
        self.on_emergency = on_emergency
        self.on_release = on_release
        self.emergency_controller = get_emergency_controller()

        self._is_active = False
        self._is_pressed = False

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = self._size // 2
        size = self._size

        if self._is_active:
            outer_color = QColor("#cc9900")
            inner_color = QColor("#ffcc00")
            text = t("control.emergency_stop_release").split('\n')[0]
        else:
            outer_color = QColor("#8b0000")
            inner_color = QColor("#b02a37") if self._is_pressed else QColor("#dc3545")
            text = t("control.emergency_stop").split('\n')[0]

        # Outer ring
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(outer_color))
        painter.drawEllipse(5, 5, size - 10, size - 10)

        # Inner button
        offset = 3 if self._is_pressed else 0
        painter.setBrush(QBrush(inner_color))
        painter.drawEllipse(10 + offset, 10 + offset, size - 20, size - 20)

        # Text
        painter.setPen(QPen(QColor("white")))
        font = QFont("Microsoft YaHei UI", 9, QFont.Weight.Bold)
        painter.setFont(font)

        lines = text.split()
        if len(lines) > 2:
            lines = [lines[0], ' '.join(lines[1:])]

        for i, line in enumerate(lines[:2]):
            y_offset = int((i - 0.5) * 14)
            rect = QRect(offset, center + offset + y_offset - 7, size, 14)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, line)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_pressed = True
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_pressed = False
            pos = event.position().toPoint()
            if 0 <= pos.x() <= self._size and 0 <= pos.y() <= self._size:
                self._trigger_action()
            self.update()

    def _trigger_action(self):
        if self._is_active:
            self._release_emergency()
        else:
            self._trigger_emergency()

    def _trigger_emergency(self):
        logger.warning("Emergency stop triggered by user")
        self._set_active(True)
        threading.Thread(
            target=self._do_emergency_stop,
            daemon=True, name="EmergencyStop"
        ).start()
        if self.on_emergency:
            self.on_emergency()

    def _do_emergency_stop(self):
        try:
            self.emergency_controller.emergency_stop_all()
        except Exception as e:
            logger.error(f"Emergency stop execution error: {e}")

    def _release_emergency(self):
        self.emergency_controller.release_emergency_stop()
        self._set_active(False)
        if self.on_release:
            self.on_release()
        logger.info("Emergency stop released by user")

    def _set_active(self, active: bool):
        self._is_active = active
        self.update()

    def set_active(self, active: bool):
        self._set_active(active)

    @property
    def is_active(self) -> bool:
        return self._is_active

    def update_language(self):
        self.update()  # Repaint with new text


class EmergencyButtonLarge(QWidget):
    """
    Large emergency button with title label.
    带标题的大型紧急按钮。
    """

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.title_label = QLabel(t("control.emergency_stop"))
        self.title_label.setStyleSheet("font-size: 12pt; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        self.button = EmergencyButton(self, size=120, **kwargs)
        layout.addWidget(self.button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 9pt;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        self.emergency_controller = get_emergency_controller()
        self.emergency_controller.add_emergency_callback(self._on_emergency_changed)

    def _on_emergency_changed(self, is_active: bool):
        from gui.signals import get_thread_bridge
        bridge = get_thread_bridge()
        bridge.gui_callback.emit(lambda: self._update_status(is_active))

    def _update_status(self, is_active: bool):
        self.button.set_active(is_active)
        if is_active:
            self.status_label.setText(t("msg.emergency_stop_active"))
            self.status_label.setStyleSheet("font-size: 9pt; color: #dc3545;")
        else:
            self.status_label.setText("")
            self.status_label.setStyleSheet("font-size: 9pt; color: black;")

    def update_language(self):
        self.title_label.setText(t("control.emergency_stop"))
        self.button.update_language()
        if self.button.is_active:
            self.status_label.setText(t("msg.emergency_stop_active"))
