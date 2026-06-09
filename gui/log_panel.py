"""
Log Panel Module (PySide6)
日志面板模块

Panel for displaying operation logs with thread-safe signal-based updates.
用于显示操作日志的面板，使用线程安全的信号更新。
"""

from gui.qt_imports import (
    QWidget, QGroupBox, QVBoxLayout, QHBoxLayout,
    QTextEdit, QComboBox, QPushButton,
    QTextCharFormat, QTextCursor, QColor, QFont,
    Qt,
)
from config.i18n import t
from config.settings import get_settings
from app_core.logger import get_app_logger, LogEntry, LogLevel
from app_core.event_bus import get_event_bus, EventType
from gui.theme import LOG_COLORS
from gui.signals import get_thread_bridge


class LogPanel(QGroupBox):
    """
    Log display panel.
    日志显示面板。
    """

    def __init__(self, parent=None):
        super().__init__(t("panel.logs"), parent)
        self.settings = get_settings()
        self.app_logger = get_app_logger()
        self.event_bus = get_event_bus()
        self._bridge = get_thread_bridge()

        self._log_count = 0
        self._max_lines = self.settings.gui.log_max_lines

        self._build_ui()
        self._setup_logging()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Toolbar
        toolbar = QHBoxLayout()

        # Level filter
        self.level_combo = QComboBox()
        self.level_combo.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.level_combo.setFixedWidth(100)
        self.level_combo.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.level_combo)

        toolbar.addStretch()

        # Clear button
        self.clear_btn = QPushButton(t("panel.clear_logs"))
        self.clear_btn.clicked.connect(self._on_clear)
        toolbar.addWidget(self.clear_btn)

        layout.addLayout(toolbar)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setObjectName("logTextEdit")
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)

    def _setup_logging(self):
        self.app_logger.add_callback(self._on_log_entry)
        self.event_bus.subscribe(EventType.LOG_MESSAGE, self._on_log_event)
        # Connect bridge signal for thread-safe log updates
        self._bridge.log_entry.connect(self._append_log)

    def _on_log_entry(self, entry: LogEntry):
        """Called from any thread - emit signal to main thread."""
        selected_level = self.level_combo.currentText()
        if selected_level != "ALL":
            level_order = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            try:
                if level_order.index(entry.level.value) < level_order.index(selected_level):
                    return
            except ValueError:
                pass
        self._bridge.log_entry.emit(entry)

    def _on_log_event(self, event):
        pass  # Already handled by logger callback

    def _append_log(self, entry: LogEntry):
        """Append log entry (runs on main thread via signal)."""
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Timestamp format
        time_str = entry.timestamp.strftime("%H:%M:%S.%f")[:-3]
        fmt_timestamp = QTextCharFormat()
        fmt_timestamp.setForeground(QColor(LOG_COLORS.get('DEBUG', '#6c757d')))
        cursor.insertText(f"[{time_str}] ", fmt_timestamp)

        # Level format
        fmt_level = QTextCharFormat()
        fmt_level.setForeground(QColor(LOG_COLORS.get(entry.level.value, '#212529')))
        if entry.level.value == "CRITICAL":
            fmt_level.setFontWeight(QFont.Weight.Bold)
        cursor.insertText(f"[{entry.level.value}] ", fmt_level)

        # Source format
        fmt_source = QTextCharFormat()
        fmt_source.setForeground(QColor('#0056b3'))
        short_source = entry.source.split('.')[-1] if '.' in entry.source else entry.source
        cursor.insertText(f"[{short_source}] ", fmt_source)

        # Message
        cursor.insertText(f"{entry.message}\n", fmt_level)

        # Auto-scroll
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()

        # Limit lines
        self._log_count += 1
        if self._log_count > self._max_lines:
            self._trim_logs()

    def _trim_logs(self):
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        for _ in range(self._max_lines // 2):
            cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        self._log_count = self._max_lines // 2

    def _on_filter_changed(self, text):
        self._on_clear()
        level_filter = None if text == "ALL" else LogLevel[text]
        entries = self.app_logger.get_entries(level=level_filter, limit=100)
        for entry in reversed(entries):
            self._append_log(entry)

    def _on_clear(self):
        self.log_text.clear()
        self._log_count = 0

    def update_language(self):
        self.setTitle(t("panel.logs"))
        self.clear_btn.setText(t("panel.clear_logs"))

    def _cleanup(self):
        try:
            self.app_logger.remove_callback(self._on_log_entry)
        except Exception:
            pass
        try:
            self.event_bus.unsubscribe(EventType.LOG_MESSAGE, self._on_log_event)
        except Exception:
            pass
