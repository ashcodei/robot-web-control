"""
Teleoperation Controller Module
遥操作控制器模块

Controls teleoperation via ROS/roslibpy WebSocket.
通过ROS/roslibpy WebSocket控制遥操作。
"""

import threading
import time
from typing import Dict, Any, Optional, List, Callable
from enum import Enum

from hardware.base_hardware import BaseHardwareController, HardwareState
from config.settings import get_settings
from app_core.logger import get_logger
from app_core.remote_control import remote_callable

logger = get_logger(__name__)


class TeleopConnectionMode(Enum):
    """Teleop connection mode / 遥操作连接模式"""
    LOCAL = "local"           # localhost:9090
    REMOTE_LAN = "remote_lan"  # Same LAN other IP:9090
    REMOTE_WAN = "remote_wan"  # Cross-network (reserved)


class TeleopController(BaseHardwareController):
    """
    Teleoperation controller using ROS/roslibpy.
    使用ROS/roslibpy的遥操作控制器。

    Supports local Docker, LAN remote, and WAN remote modes.
    支持本地Docker、局域网远程和跨网络远程模式。
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize teleop controller.

        Args:
            config: Configuration dictionary (optional)
        """
        super().__init__("teleop", config)

        settings = get_settings()
        mode_str = config.get('mode') if config else settings.teleop.mode
        self._mode = TeleopConnectionMode(mode_str)
        self._ros_host = config.get('ros_host') if config else settings.teleop.ros_host
        self._ros_port = config.get('ros_port') if config else settings.teleop.ros_port
        self._relay_server = config.get('relay_server') if config else settings.teleop.relay_server
        self._update_rate = config.get('update_rate') if config else settings.teleop.update_rate

        self._ros_client = None
        self._is_active = False
        self._data_callbacks: List[Callable[[Dict], None]] = []
        self._receive_thread: Optional[threading.Thread] = None
        self._last_data: Dict[str, Any] = {}
        self._lock = threading.Lock()

        # Try to import roslibpy
        self._ros_available = False
        try:
            import roslibpy
            self._ros_available = True
        except ImportError:
            logger.warning("roslibpy not installed, running in simulation mode")

    @property
    def mode(self) -> TeleopConnectionMode:
        """Get current connection mode / 获取当前连接模式"""
        return self._mode

    @mode.setter
    def mode(self, value: TeleopConnectionMode):
        """Set connection mode / 设置连接模式"""
        self._mode = value

    def set_ros_host(self, host: str):
        """Set ROS host address / 设置ROS主机地址"""
        self._ros_host = host

    def set_ros_port(self, port: int):
        """Set ROS port / 设置ROS端口"""
        self._ros_port = port

    def connect(self) -> bool:
        """Connect to ROS via WebSocket / 通过WebSocket连接ROS"""
        self.state = HardwareState.CONNECTING

        if not self._ros_available:
            logger.warning("Teleop: roslibpy not installed, cannot connect (simulation mode)")
            self.state = HardwareState.DISCONNECTED
            return False

        try:
            if self._mode == TeleopConnectionMode.LOCAL:
                return self._connect_local()
            elif self._mode == TeleopConnectionMode.REMOTE_LAN:
                return self._connect_remote_lan()
            elif self._mode == TeleopConnectionMode.REMOTE_WAN:
                return self._connect_remote_wan()
        except Exception as e:
            logger.error(f"Failed to connect teleop: {e}")
            self._set_error(str(e))
            return False

    def _connect_local(self) -> bool:
        """Connect to local Docker ROS / 连接本地Docker ROS"""
        import roslibpy

        self._ros_client = roslibpy.Ros(host='localhost', port=9090)
        self._ros_client.run()

        if self._ros_client.is_connected:
            logger.info("Teleop connected to localhost:9090")
            self.state = HardwareState.CONNECTED
            return True

        raise Exception("Failed to connect to local ROS")

    def _connect_remote_lan(self) -> bool:
        """Connect to remote LAN ROS / 连接远程局域网ROS"""
        import roslibpy

        self._ros_client = roslibpy.Ros(
            host=self._ros_host,
            port=self._ros_port
        )
        self._ros_client.run()

        if self._ros_client.is_connected:
            logger.info(f"Teleop connected to {self._ros_host}:{self._ros_port}")
            self.state = HardwareState.CONNECTED
            return True

        raise Exception(f"Failed to connect to {self._ros_host}:{self._ros_port}")

    def _connect_remote_wan(self) -> bool:
        """Connect to remote WAN (not implemented) / 连接远程WAN（未实现）"""
        raise NotImplementedError("Remote WAN connection not yet implemented")

    def disconnect(self) -> bool:
        """Disconnect from ROS / 断开ROS连接"""
        self._is_active = False

        if self._ros_client:
            try:
                self._ros_client.terminate()
            except Exception:
                pass
            self._ros_client = None

        self.state = HardwareState.DISCONNECTED
        logger.info("Teleop disconnected")
        return True

    def start(self) -> bool:
        """Start teleoperation / 启动遥操作"""
        if self.state != HardwareState.CONNECTED:
            return False

        self._is_active = True
        self._start_receive_thread()
        self.state = HardwareState.RUNNING
        logger.info("Teleoperation started")
        return True

    def stop(self) -> bool:
        """Stop teleoperation / 停止遥操作"""
        self._is_active = False
        self.state = HardwareState.CONNECTED
        logger.info("Teleoperation stopped")
        return True

    def pause(self) -> bool:
        """Pause teleoperation / 暂停遥操作"""
        self._is_active = False
        self.state = HardwareState.PAUSED
        return True

    def resume(self) -> bool:
        """Resume teleoperation / 恢复遥操作"""
        self._is_active = True
        self.state = HardwareState.RUNNING
        return True

    @remote_callable(
        name="急停",
        category="teleop",
        description="Emergency stop teleoperation",
        description_zh="遥操作紧急停止",
        is_emergency=True
    )
    def emergency_stop(self) -> bool:
        """Emergency stop teleoperation / 遥操作紧急停止"""
        self._is_active = False
        self.state = HardwareState.EMERGENCY_STOP
        logger.warning("Teleop emergency stop executed")
        return True

    def get_status(self) -> Dict[str, Any]:
        """Get teleop status / 获取遥操作状态"""
        return {
            "name": self._name,
            "state": self._state.value,
            "mode": self._mode.value,
            "ros_host": self._ros_host,
            "ros_port": self._ros_port,
            "is_active": self._is_active,
            "connected": self._ros_client.is_connected if self._ros_client else False,
            "last_data": self._last_data
        }

    def is_ready(self) -> bool:
        """Check if teleop is ready / 检查遥操作是否就绪"""
        return self.state in [HardwareState.CONNECTED, HardwareState.RUNNING]

    def add_data_callback(self, callback: Callable[[Dict], None]):
        """Add data receive callback / 添加数据接收回调"""
        self._data_callbacks.append(callback)

    def remove_data_callback(self, callback: Callable[[Dict], None]):
        """Remove data receive callback / 移除数据接收回调"""
        if callback in self._data_callbacks:
            self._data_callbacks.remove(callback)

    def _start_receive_thread(self):
        """Start data receive thread / 启动数据接收线程"""
        if self._receive_thread and self._receive_thread.is_alive():
            return

        self._receive_thread = threading.Thread(
            target=self._receive_loop,
            daemon=True
        )
        self._receive_thread.start()

    def _receive_loop(self):
        """Data receive loop / 数据接收循环"""
        if not self._ros_client:
            return

        import roslibpy

        # Subscribe to master arm topic
        topic = roslibpy.Topic(
            self._ros_client,
            '/master_arm/joint_states',
            'sensor_msgs/JointState'
        )

        def callback(message):
            with self._lock:
                self._last_data = {
                    'positions': message.get('position', []),
                    'velocities': message.get('velocity', []),
                    'efforts': message.get('effort', []),
                    'timestamp': time.time()
                }

            for cb in self._data_callbacks:
                try:
                    cb(self._last_data)
                except Exception as e:
                    logger.error(f"Data callback error: {e}")

        topic.subscribe(callback)

        while self._is_active:
            time.sleep(0.01)

        topic.unsubscribe()

    def get_last_data(self) -> Dict[str, Any]:
        """Get last received data / 获取最后接收的数据"""
        with self._lock:
            return dict(self._last_data)
