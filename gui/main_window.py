"""
Main Window Module (PySide6)
主窗口模块

Main application window for the cooking robot control system.
烹饪机器人控制系统的主应用窗口。
"""

from typing import Dict, Optional
from gui.qt_imports import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QSplitter, QPushButton, QFrame,
    QMessageBox, QTimer, Qt, QCloseEvent,
)
from config.settings import get_settings
from config.i18n import get_i18n, t, Language
from app_core.event_bus import get_event_bus, EventType
from app_core.state_manager import get_state_manager, SystemState
from app_core.emergency_controller import get_emergency_controller
from app_core.logger import get_logger
from hardware.base_hardware import HardwareState

from .control_panel import ControlPanel
from .status_bar import StatusBar
from .log_panel import LogPanel
from .camera_panel import CameraPanel
from .signals import EventBusBridge, get_thread_bridge

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    """
    Main application window.
    主应用程序窗口。
    """

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.i18n = get_i18n()
        self.event_bus = get_event_bus()
        self.state_manager = get_state_manager()
        self.emergency_controller = get_emergency_controller()
        self._bridge = get_thread_bridge()
        self._event_bridge = EventBusBridge(self)

        # Connect the generic callback signal for thread-safe UI updates
        self._bridge.gui_callback.connect(self._on_gui_callback)

        self.setWindowTitle(t("app.title"))
        self.resize(self.settings.gui.window_width, self.settings.gui.window_height)
        self.setMinimumSize(1200, 700)

        # Hardware reference
        self._hardware: Optional[Dict] = None
        self._conn_dialog = None

        # Tab storage
        self.tab_frames: Dict[str, QWidget] = {}
        self.tab_widgets: Dict[str, Optional[QWidget]] = {}

        self._build_ui()
        self._setup_event_handlers()

        self.i18n.add_callback(self._on_language_changed)

        # Schedule periodic updates
        self._schedule_updates()

        logger.info("Main window initialized")

    def _on_gui_callback(self, callback):
        """Execute a callback on the main thread."""
        if callable(callback):
            callback()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Top control bar
        self._build_top_bar(main_layout)

        # Content area: tabs (left) + camera/log (right)
        content_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Tab widget
        self.notebook = QTabWidget()
        self._create_tabs()
        content_splitter.addWidget(self.notebook)

        # Right: Camera + Log (vertical splitter)
        right_splitter = QSplitter(Qt.Orientation.Vertical)

        self.camera_panel = CameraPanel()
        right_splitter.addWidget(self.camera_panel)

        self.log_panel = LogPanel()
        right_splitter.addWidget(self.log_panel)

        right_splitter.setSizes([400, 200])
        right_splitter.setMinimumWidth(400)

        content_splitter.addWidget(right_splitter)
        content_splitter.setSizes([700, 400])

        main_layout.addWidget(content_splitter, stretch=1)

        # Bottom status bar
        self.status_bar = StatusBar()
        main_layout.addWidget(self.status_bar)

    def _build_top_bar(self, parent_layout):
        top_bar = QHBoxLayout()

        self.lang_btn = QPushButton("中文/EN")
        self.lang_btn.setFixedWidth(80)
        self.lang_btn.clicked.connect(self._toggle_language)
        top_bar.addWidget(self.lang_btn)

        self.check_conn_btn = QPushButton(t("control.check_connections"))
        self.check_conn_btn.setFixedWidth(120)
        self.check_conn_btn.clicked.connect(self._show_connection_check)
        top_bar.addWidget(self.check_conn_btn)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setFixedWidth(2)
        top_bar.addWidget(sep)

        self.control_panel = ControlPanel()
        top_bar.addWidget(self.control_panel, stretch=1)

        parent_layout.addLayout(top_bar)

    def _create_tabs(self):
        tab_keys = [
            ('gantry_lebai', 'tab.gantry_lebai'),
            ('teach_record', 'tab.teach_record'),
            ('dual_arm', 'tab.dual_arm'),
            ('dexhand', 'tab.dexhand'),
            ('gripper', 'tab.gripper'),
            ('master_teleop', 'tab.master_teleop'),
            ('wok', 'tab.wok'),
            ('recording', 'tab.recording'),
            ('episode', 'tab.episode'),
        ]

        for tab_name, text_key in tab_keys:
            frame = QWidget()
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(10, 10, 10, 10)
            self.tab_frames[tab_name] = frame
            self.notebook.addTab(frame, t(text_key))

    def _setup_event_handlers(self):
        self._event_bridge.subscribe(EventType.EMERGENCY_STOP, self._on_emergency_stop_event)
        self._event_bridge.subscribe(EventType.EMERGENCY_STOP_RELEASED, self._on_emergency_released_event)
        self._event_bridge.subscribe(EventType.HARDWARE_STATE_CHANGED, self._on_hardware_state_changed)

    def _schedule_updates(self):
        update_interval = int(self.settings.gui.status_update_interval * 1000)
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._on_update)
        self._update_timer.start(update_interval)

    def _on_update(self):
        try:
            self.status_bar.update_status()
        except Exception as e:
            logger.error(f"Update error: {e}")

    def _toggle_language(self):
        self.i18n.toggle_language()

    def _on_language_changed(self, language: Language):
        self.setWindowTitle(t("app.title"))
        self.check_conn_btn.setText(t("control.check_connections"))

        # Update tab labels
        tab_keys = ['gantry_lebai', 'teach_record', 'dual_arm', 'dexhand',
                     'gripper', 'master_teleop', 'wok', 'recording', 'episode']
        for i, key in enumerate(tab_keys):
            self.notebook.setTabText(i, t(f"tab.{key}"))

        self.control_panel.update_language()
        self.status_bar.update_language()
        self.log_panel.update_language()
        self.camera_panel.update_language()

        for tab_name, widget in self.tab_widgets.items():
            if widget and hasattr(widget, 'update_language'):
                try:
                    widget.update_language()
                except Exception as e:
                    logger.error(f"Error updating language for {tab_name}: {e}")

        logger.info(f"Language changed to: {language.value}")

    def _on_emergency_stop_event(self, event):
        self.status_bar.set_message(t("msg.emergency_stop_active"), level="warning")

    def _on_emergency_released_event(self, event):
        self.status_bar.set_message(t("msg.emergency_stop_released"), level="info")

    def _on_hardware_state_changed(self, event):
        hw_name = event.data.get('hardware_name')
        new_state_str = event.data.get('new_state')
        if hw_name and new_state_str:
            try:
                new_state = HardwareState(new_state_str)
                self.control_panel.update_hardware_state(hw_name, new_state)
            except ValueError:
                pass

    def closeEvent(self, event: QCloseEvent):
        result = QMessageBox.question(
            self, t("common.confirm"),
            "Exit application? / 退出应用程序？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if result != QMessageBox.StandardButton.Yes:
            event.ignore()
            return

        logger.info("Application shutting down...")

        # Camera cleanup first
        if hasattr(self, 'camera_panel') and self.camera_panel:
            try:
                self.camera_panel._cleanup()
            except Exception as e:
                logger.debug(f"Camera cleanup: {e}")

        # Unsubscribe events
        self._event_bridge.unsubscribe_all()

        try:
            self.i18n.remove_callback(self._on_language_changed)
        except Exception:
            pass

        # Cleanup panels
        for panel in [self.control_panel, self.status_bar, self.log_panel]:
            if panel and hasattr(panel, '_cleanup'):
                try:
                    panel._cleanup()
                except Exception:
                    pass

        # Cleanup tab widgets
        for tab_name, widget in self.tab_widgets.items():
            if widget:
                if hasattr(widget, 'cleanup'):
                    try:
                        widget.cleanup()
                    except Exception as e:
                        logger.debug(f"Tab widget {tab_name} cleanup: {e}")
                elif hasattr(widget, '_cleanup'):
                    try:
                        widget._cleanup()
                    except Exception as e:
                        logger.debug(f"Tab widget {tab_name} cleanup: {e}")

        # Stop update timer
        if hasattr(self, '_update_timer'):
            self._update_timer.stop()

        logger.info("Application closed")
        event.accept()

        # Force exit
        import os
        os._exit(0)

    # ── Public API ──

    def set_hardware(self, hardware: Dict):
        self._hardware = hardware

    def _show_connection_check(self):
        if self._hardware is None:
            logger.warning("Hardware not set")
            return

        if self._conn_dialog is not None and self._conn_dialog.isVisible():
            self._conn_dialog.raise_()
            self._conn_dialog.activateWindow()
            return

        try:
            from .connection_check_dialog import ConnectionCheckDialog
            self._conn_dialog = ConnectionCheckDialog(
                self, self._hardware,
                on_close_callback=lambda: setattr(self, '_conn_dialog', None)
            )
            self._conn_dialog.show()
        except Exception as e:
            logger.error(f"Failed to show connection check dialog: {e}", exc_info=True)

    def show_startup_connection_check(self):
        if self._hardware is None:
            return
        QTimer.singleShot(200, self._show_connection_check)

    def set_tab_widget(self, tab_name: str, widget_class, *args, **kwargs):
        if tab_name not in self.tab_frames:
            logger.warning(f"Unknown tab: {tab_name}")
            return

        frame = self.tab_frames[tab_name]

        # Clear existing widgets
        layout = frame.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Create new widget
        widget = widget_class(frame, *args, **kwargs)
        layout.addWidget(widget)

        self.tab_widgets[tab_name] = widget

    def run(self):
        """For compatibility - not needed with QApplication.exec()"""
        self.event_bus.start()
        logger.info("Starting main application loop")
        self.show()


def create_main_window() -> MainWindow:
    return MainWindow()
