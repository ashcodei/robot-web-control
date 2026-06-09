"""
Event Bus Module
事件总线模块

Provides publish-subscribe pattern for inter-module communication.
提供模块间通信的发布-订阅模式。
"""

from enum import Enum
from typing import Callable, Dict, List, Any, Optional
import threading
import queue
import time
from dataclasses import dataclass, field


class EventType(Enum):
    """Event type enumeration / 事件类型枚举"""

    # Hardware events / 硬件事件
    HARDWARE_CONNECTED = "hardware_connected"
    HARDWARE_DISCONNECTED = "hardware_disconnected"
    HARDWARE_STATE_CHANGED = "hardware_state_changed"
    HARDWARE_ERROR = "hardware_error"
    HARDWARE_STATUS_UPDATE = "hardware_status_update"

    # System events / 系统事件
    EMERGENCY_STOP = "emergency_stop"
    EMERGENCY_STOP_RELEASED = "emergency_stop_released"
    SYSTEM_READY = "system_ready"
    SYSTEM_SHUTDOWN = "system_shutdown"

    # Recipe events / 配方事件
    RECIPE_STARTED = "recipe_started"
    RECIPE_STEP_CHANGED = "recipe_step_changed"
    RECIPE_COMPLETED = "recipe_completed"
    RECIPE_ERROR = "recipe_error"
    RECIPE_PAUSED = "recipe_paused"
    RECIPE_RESUMED = "recipe_resumed"

    # Order events / 订单事件
    ORDER_CREATED = "order_created"
    ORDER_STARTED = "order_started"
    ORDER_COMPLETED = "order_completed"
    ORDER_CANCELLED = "order_cancelled"

    # Teleop events / 遥操作事件
    TELEOP_CONNECTED = "teleop_connected"
    TELEOP_DISCONNECTED = "teleop_disconnected"
    TELEOP_DATA_RECEIVED = "teleop_data_received"

    # UI events / UI事件
    LOG_MESSAGE = "log_message"
    STATUS_UPDATE = "status_update"
    LANGUAGE_CHANGED = "language_changed"

    # Remote control events / 远程控制事件
    REMOTE_CONNECTED = "remote_connected"
    REMOTE_DISCONNECTED = "remote_disconnected"
    REMOTE_COMMAND_RECEIVED = "remote_command_received"

    # Dexhand events / 灵巧手事件
    HAND_CONNECTED = "hand_connected"
    HAND_DISCONNECTED = "hand_disconnected"
    HAND_POSITION_CHANGED = "hand_position_changed"
    HAND_TOUCH_DATA = "hand_touch_data"
    HAND_ERROR = "hand_error"

    # Force grab events / 力反馈抓取事件
    FORCE_GRAB_STARTED = "force_grab_started"
    FORCE_GRAB_STOPPED = "force_grab_stopped"
    FORCE_GRAB_FINGER_STOPPED = "force_grab_finger_stopped"

    # Gloves teleoperation events / 手套遥操作事件
    GLOVES_CONNECTED = "gloves_connected"
    GLOVES_DISCONNECTED = "gloves_disconnected"
    GLOVES_DATA = "gloves_data"

    # Recording events / 录制事件
    RECORDING_STARTED = "recording_started"
    RECORDING_STOPPED = "recording_stopped"
    RECORDING_PAUSED = "recording_paused"
    RECORDING_RESUMED = "recording_resumed"
    TRAJECTORY_POINT_ADDED = "trajectory_point_added"

    # Pose events / 位姿事件
    POSE_SAVED = "pose_saved"
    POSE_DELETED = "pose_deleted"
    POSE_PLAYING = "pose_playing"
    POSE_PLAYED = "pose_played"


@dataclass
class Event:
    """Event data class / 事件数据类"""
    event_type: EventType
    source: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    priority: int = 0  # Higher priority = handled first


class EventBus:
    """
    Event Bus for publish-subscribe communication.
    用于发布-订阅通信的事件总线。

    Thread-safe implementation with priority queue support.
    线程安全实现，支持优先级队列。
    """

    _instance: Optional['EventBus'] = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern / 单例模式"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._subscribers: Dict[EventType, List[Callable[[Event], None]]] = {}
        self._wildcard_subscribers: List[Callable[[Event], None]] = []
        self._event_queue: queue.PriorityQueue = queue.PriorityQueue()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._subscribe_lock = threading.Lock()
        self._history_lock = threading.Lock()  # Lock for event history
        self._event_history: List[Event] = []
        self._max_history = 1000
        self._initialized = True

    def start(self):
        """Start event processing / 启动事件处理"""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._process_events, daemon=True)
        self._worker_thread.start()

    def stop(self):
        """Stop event processing / 停止事件处理"""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=2.0)

    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        """
        Subscribe to an event type.
        订阅事件类型。

        Args:
            event_type: Type of event to subscribe to / 要订阅的事件类型
            callback: Callback function to handle event / 处理事件的回调函数
        """
        with self._subscribe_lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)

    def subscribe_all(self, callback: Callable[[Event], None]):
        """
        Subscribe to all events (wildcard).
        订阅所有事件（通配符）。

        Args:
            callback: Callback function to handle all events
        """
        with self._subscribe_lock:
            if callback not in self._wildcard_subscribers:
                self._wildcard_subscribers.append(callback)

    def unsubscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        """
        Unsubscribe from an event type.
        取消订阅事件类型。

        Args:
            event_type: Type of event to unsubscribe from
            callback: Callback function to remove
        """
        with self._subscribe_lock:
            if event_type in self._subscribers:
                if callback in self._subscribers[event_type]:
                    self._subscribers[event_type].remove(callback)

    def unsubscribe_all(self, callback: Callable[[Event], None]):
        """Remove wildcard subscription / 移除通配符订阅"""
        with self._subscribe_lock:
            if callback in self._wildcard_subscribers:
                self._wildcard_subscribers.remove(callback)

    def publish(self, event_type: EventType, source: str,
                data: Dict[str, Any] = None, priority: int = 0):
        """
        Publish an event.
        发布事件。

        Args:
            event_type: Type of event / 事件类型
            source: Source of event / 事件来源
            data: Event data / 事件数据
            priority: Event priority (higher = handled first) / 事件优先级
        """
        event = Event(
            event_type=event_type,
            source=source,
            data=data or {},
            priority=priority
        )
        # Use negative priority for PriorityQueue (lower number = higher priority)
        self._event_queue.put((-priority, time.time(), event))

    def publish_sync(self, event_type: EventType, source: str,
                     data: Dict[str, Any] = None):
        """
        Publish an event synchronously (immediate handling).
        同步发布事件（立即处理）。

        Use for high-priority events like emergency stop.
        用于紧急停止等高优先级事件。
        """
        event = Event(
            event_type=event_type,
            source=source,
            data=data or {},
            priority=100  # Highest priority
        )
        self._dispatch_event(event)

    def _process_events(self):
        """Event processing loop / 事件处理循环"""
        while self._running:
            try:
                # Get event with timeout to allow checking _running flag
                _, _, event = self._event_queue.get(timeout=0.1)
                self._dispatch_event(event)
            except queue.Empty:
                continue
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Event processing error: {e}")

    def _dispatch_event(self, event: Event):
        """
        Dispatch event to subscribers.
        将事件分发给订阅者。
        """
        # Add to history (thread-safe)
        with self._history_lock:
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]

        # Get subscribers snapshot
        with self._subscribe_lock:
            subscribers = list(self._subscribers.get(event.event_type, []))
            wildcard_subscribers = list(self._wildcard_subscribers)

        # Notify specific subscribers
        for callback in subscribers:
            try:
                callback(event)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Event callback error for {event.event_type}: {e}")

        # Notify wildcard subscribers
        for callback in wildcard_subscribers:
            try:
                callback(event)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Wildcard callback error for {event.event_type}: {e}")

    def get_history(self, event_type: EventType = None,
                    limit: int = 100) -> List[Event]:
        """
        Get event history.
        获取事件历史。

        Args:
            event_type: Filter by event type (None = all)
            limit: Maximum number of events to return

        Returns:
            List of events (newest first)
        """
        with self._history_lock:
            if event_type:
                events = [e for e in self._event_history if e.event_type == event_type]
            else:
                events = list(self._event_history)

        return events[-limit:][::-1]

    def clear_history(self):
        """Clear event history / 清空事件历史"""
        with self._history_lock:
            self._event_history.clear()


# Global event bus instance / 全局事件总线实例
def get_event_bus() -> EventBus:
    """Get the global event bus instance / 获取全局事件总线实例"""
    return EventBus()
