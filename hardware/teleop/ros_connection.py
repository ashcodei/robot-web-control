"""
ROS Connection Module
ROS连接模块

ROS2 rosbridge WebSocket client for teleoperation.
用于遥操作的 ROS2 rosbridge WebSocket 客户端。
"""

import threading
import time
import logging
from typing import Dict, Any, Optional, Callable, List
from enum import Enum

logger = logging.getLogger(__name__)

# Try to import roslibpy
ROSLIBPY_AVAILABLE = False
roslibpy = None

try:
    import roslibpy
    ROSLIBPY_AVAILABLE = True
except ImportError:
    logger.warning("roslibpy not available. ROS features disabled.")


class ROSConnectionState(Enum):
    """ROS connection state / ROS连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class ROSConnection:
    """
    ROS WebSocket connection manager.
    ROS WebSocket 连接管理器。

    Handles connection to rosbridge WebSocket server.
    处理与 rosbridge WebSocket 服务器的连接。
    """

    def __init__(self, host: str = "localhost", port: int = 9090):
        """
        Initialize ROS connection.
        初始化 ROS 连接。

        Args:
            host: rosbridge host
            port: rosbridge port
        """
        self._host = host
        self._port = port
        self._client = None
        self._state = ROSConnectionState.DISCONNECTED
        self._lock = threading.Lock()

        # Callbacks
        self._state_callbacks: List[Callable[[ROSConnectionState], None]] = []

        # Subscriptions
        self._subscribers: Dict[str, Any] = {}

        # Publishers
        self._publishers: Dict[str, Any] = {}

    @property
    def state(self) -> ROSConnectionState:
        """Get connection state / 获取连接状态"""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if connected / 检查是否已连接"""
        return self._state == ROSConnectionState.CONNECTED

    @staticmethod
    def is_available() -> bool:
        """Check if roslibpy is available / 检查 roslibpy 是否可用"""
        return ROSLIBPY_AVAILABLE

    def add_state_callback(self, callback: Callable[[ROSConnectionState], None]):
        """Add state change callback / 添加状态变化回调"""
        self._state_callbacks.append(callback)

    def _set_state(self, new_state: ROSConnectionState):
        """Set state and notify callbacks / 设置状态并通知回调"""
        self._state = new_state
        for callback in self._state_callbacks:
            try:
                callback(new_state)
            except Exception as e:
                logger.warning(f"State callback error: {e}")

    def connect(self, host: Optional[str] = None, port: Optional[int] = None) -> bool:
        """
        Connect to rosbridge server.
        连接到 rosbridge 服务器。

        Args:
            host: Override host (optional)
            port: Override port (optional)

        Returns:
            True if connection successful
        """
        if not ROSLIBPY_AVAILABLE:
            logger.error("roslibpy not available")
            return False

        if host:
            self._host = host
        if port:
            self._port = port

        self._set_state(ROSConnectionState.CONNECTING)

        try:
            url = f"ws://{self._host}:{self._port}"
            logger.info(f"Connecting to rosbridge at {url}")

            self._client = roslibpy.Ros(host=self._host, port=self._port)
            self._client.run()

            # Wait for connection
            timeout = 5.0
            start = time.time()
            while not self._client.is_connected and time.time() - start < timeout:
                time.sleep(0.1)

            if self._client.is_connected:
                self._set_state(ROSConnectionState.CONNECTED)
                logger.info("Connected to rosbridge")
                return True
            else:
                raise Exception("Connection timeout")

        except Exception as e:
            logger.error(f"ROS connection failed: {e}")
            self._set_state(ROSConnectionState.ERROR)
            return False

    def disconnect(self):
        """Disconnect from rosbridge / 断开与 rosbridge 的连接"""
        # Unsubscribe all
        for sub in self._subscribers.values():
            try:
                sub.unsubscribe()
            except Exception:
                pass
        self._subscribers.clear()

        # Unadvertise all
        for pub in self._publishers.values():
            try:
                pub.unadvertise()
            except Exception:
                pass
        self._publishers.clear()

        # Close connection
        if self._client:
            try:
                self._client.terminate()
            except Exception:
                pass
            self._client = None

        self._set_state(ROSConnectionState.DISCONNECTED)
        logger.info("Disconnected from rosbridge")

    def subscribe(self, topic: str, msg_type: str,
                  callback: Callable[[Dict[str, Any]], None],
                  throttle_rate: int = 0,
                  queue_length: int = 0) -> bool:
        """
        Subscribe to a ROS topic.
        订阅 ROS 话题。

        Args:
            topic: Topic name (e.g., "/joint_states")
            msg_type: Message type (e.g., "sensor_msgs/JointState")
            callback: Callback function for messages
            throttle_rate: Maximum rate in Hz (0 = no limit)
            queue_length: Queue length (0 = no limit)

        Returns:
            True if subscription successful
        """
        if not self.is_connected:
            logger.error("Not connected to ROS")
            return False

        try:
            listener = roslibpy.Topic(self._client, topic, msg_type,
                                      throttle_rate=throttle_rate,
                                      queue_length=queue_length)
            listener.subscribe(callback)
            self._subscribers[topic] = listener
            logger.info(f"Subscribed to {topic}")
            return True

        except Exception as e:
            logger.error(f"Subscription failed: {e}")
            return False

    def unsubscribe(self, topic: str):
        """Unsubscribe from topic / 取消订阅话题"""
        if topic in self._subscribers:
            try:
                self._subscribers[topic].unsubscribe()
            except Exception:
                pass
            del self._subscribers[topic]
            logger.info(f"Unsubscribed from {topic}")

    def advertise(self, topic: str, msg_type: str) -> bool:
        """
        Advertise a ROS topic for publishing.
        宣告 ROS 话题用于发布。

        Args:
            topic: Topic name
            msg_type: Message type

        Returns:
            True if advertisement successful
        """
        if not self.is_connected:
            logger.error("Not connected to ROS")
            return False

        try:
            publisher = roslibpy.Topic(self._client, topic, msg_type)
            publisher.advertise()
            self._publishers[topic] = publisher
            logger.info(f"Advertised {topic}")
            return True

        except Exception as e:
            logger.error(f"Advertisement failed: {e}")
            return False

    def publish(self, topic: str, message: Dict[str, Any]) -> bool:
        """
        Publish message to topic.
        发布消息到话题。

        Args:
            topic: Topic name
            message: Message dictionary

        Returns:
            True if publish successful
        """
        if topic not in self._publishers:
            logger.error(f"Topic {topic} not advertised")
            return False

        try:
            self._publishers[topic].publish(roslibpy.Message(message))
            return True

        except Exception as e:
            logger.error(f"Publish failed: {e}")
            return False

    def call_service(self, service: str, service_type: str,
                     request: Dict[str, Any] = None,
                     timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """
        Call a ROS service.
        调用 ROS 服务。

        Args:
            service: Service name
            service_type: Service type
            request: Request dictionary
            timeout: Timeout in seconds

        Returns:
            Response dictionary or None if failed
        """
        if not self.is_connected:
            logger.error("Not connected to ROS")
            return None

        try:
            srv = roslibpy.Service(self._client, service, service_type)
            req = roslibpy.ServiceRequest(request or {})

            result = []
            event = threading.Event()

            def callback(response):
                result.append(response)
                event.set()

            srv.call(req, callback=callback)

            if event.wait(timeout):
                return result[0] if result else None
            else:
                logger.error(f"Service call timeout: {service}")
                return None

        except Exception as e:
            logger.error(f"Service call failed: {e}")
            return None


class ROSTopicMonitor:
    """
    Monitor multiple ROS topics.
    监控多个 ROS 话题。
    """

    def __init__(self, ros_connection: ROSConnection):
        """
        Initialize topic monitor.
        初始化话题监控器。

        Args:
            ros_connection: ROSConnection instance
        """
        self._ros = ros_connection
        self._latest_messages: Dict[str, Dict[str, Any]] = {}
        self._callbacks: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()

    def add_topic(self, topic: str, msg_type: str,
                  callback: Optional[Callable] = None,
                  throttle_rate: int = 30) -> bool:
        """
        Add topic to monitor.
        添加要监控的话题。

        Args:
            topic: Topic name
            msg_type: Message type
            callback: Optional callback for new messages
            throttle_rate: Update rate in Hz

        Returns:
            True if successful
        """
        def internal_callback(msg):
            with self._lock:
                self._latest_messages[topic] = msg

            if topic in self._callbacks:
                for cb in self._callbacks[topic]:
                    try:
                        cb(msg)
                    except Exception as e:
                        logger.warning(f"Topic callback error: {e}")

        if callback:
            if topic not in self._callbacks:
                self._callbacks[topic] = []
            self._callbacks[topic].append(callback)

        return self._ros.subscribe(topic, msg_type, internal_callback,
                                   throttle_rate=throttle_rate)

    def get_latest(self, topic: str) -> Optional[Dict[str, Any]]:
        """Get latest message for topic / 获取话题的最新消息"""
        with self._lock:
            return self._latest_messages.get(topic)

    def remove_topic(self, topic: str):
        """Remove topic from monitor / 从监控器移除话题"""
        self._ros.unsubscribe(topic)
        with self._lock:
            self._latest_messages.pop(topic, None)
            self._callbacks.pop(topic, None)
