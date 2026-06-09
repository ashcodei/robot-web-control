"""
Thread Bridge Signals Module
线程桥接信号模块

Provides thread-safe signal/slot bridges replacing all Tkinter .after() calls.
提供线程安全的信号/槽桥接，替代所有 Tkinter .after() 调用。
"""

from .qt_imports import QObject, Signal, Slot, QTimer
from app_core.event_bus import get_event_bus, EventType, Event


class ThreadBridge(QObject):
    """
    Singleton thread-safe signal bridge.
    单例线程安全信号桥接。

    Emit from any thread; connected slots run on the Qt main thread.
    从任意线程发射信号；连接的槽在 Qt 主线程运行。
    """

    # Generic callback: pass any Python object
    gui_callback = Signal(object)

    # Camera frame ready: (slot_index, qimage)
    frame_ready = Signal(int, object)

    # Log entry arrived
    log_entry = Signal(object)

    # Hardware state changed: (hardware_name, new_state_str)
    hardware_state_changed = Signal(str, str)

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        super().__init__()
        self._initialized = True


class EventBusBridge(QObject):
    """
    Bridges event bus callbacks to Qt main thread via signals.
    通过信号将事件总线回调桥接到 Qt 主线程。

    Usage:
        bridge = EventBusBridge()
        bridge.subscribe(EventType.HARDWARE_STATE_CHANGED, self._on_hw_state)
        # _on_hw_state will be called on the main thread
    """

    _event_signal = Signal(object, object)  # (callback, event)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._event_bus = get_event_bus()
        self._subscriptions = []
        self._event_signal.connect(self._dispatch)

    @Slot(object, object)
    def _dispatch(self, callback, event):
        """Dispatch on main thread."""
        callback(event)

    def subscribe(self, event_type: EventType, callback):
        """Subscribe to event bus, auto-marshal callback to main thread."""
        def _bridge(event, cb=callback):
            self._event_signal.emit(cb, event)

        self._event_bus.subscribe(event_type, _bridge)
        self._subscriptions.append((event_type, _bridge))

    def unsubscribe_all(self):
        """Unsubscribe all registered callbacks."""
        for event_type, bridge_cb in self._subscriptions:
            try:
                self._event_bus.unsubscribe(event_type, bridge_cb)
            except Exception:
                pass
        self._subscriptions.clear()


def get_thread_bridge() -> ThreadBridge:
    """Get the global ThreadBridge singleton."""
    return ThreadBridge()
