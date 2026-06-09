"""
Base Hardware Widget
基础硬件部件

Shared base class for all hardware tab widgets.
所有硬件标签页部件的共享基类。
"""

import threading
from .qt_imports import (
    QWidget, QVBoxLayout, QTimer, QMessageBox,
)
from config.i18n import t


class BaseHardwareWidget(QWidget):
    """
    Base class for hardware widgets.
    硬件部件基类。

    Provides:
    - Standard layout (_build_ui to override)
    - Language update protocol
    - Thread helper
    - Timer helper
    - Cleanup protocol
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timers = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 10, 10, 10)

    # ── Override points ──

    def _build_ui(self):
        """Override to build the widget UI. Called by subclass __init__."""
        raise NotImplementedError

    def update_language(self):
        """Override to refresh all translatable text."""
        pass

    def cleanup(self):
        """Override for resource cleanup before destruction."""
        for timer in self._timers:
            timer.stop()
        self._timers.clear()

    # ── Helpers ──

    def _run_in_thread(self, func, *args, name=None):
        """Run func in a daemon thread. Returns the thread."""
        thread = threading.Thread(
            target=func, args=args, daemon=True,
            name=name or f"{self.__class__.__name__}-bg"
        )
        thread.start()
        return thread

    def _create_timer(self, interval_ms, callback, start=True):
        """Create a QTimer connected to callback. Tracked for cleanup."""
        timer = QTimer(self)
        timer.setInterval(interval_ms)
        timer.timeout.connect(callback)
        self._timers.append(timer)
        if start:
            timer.start()
        return timer

    def _show_error(self, title, message):
        """Show error message box."""
        QMessageBox.critical(self, title, message)

    def _show_warning(self, title, message):
        """Show warning message box."""
        QMessageBox.warning(self, title, message)

    def _show_info(self, title, message):
        """Show info message box."""
        QMessageBox.information(self, title, message)

    def _confirm(self, title, message):
        """Show yes/no confirmation. Returns True if Yes."""
        result = QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        return result == QMessageBox.StandardButton.Yes

    # ── Qt lifecycle ──

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
