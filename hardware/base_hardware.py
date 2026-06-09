"""
Base Hardware Controller Module
基础硬件控制器模块

Provides abstract base class for all hardware controllers.
提供所有硬件控制器的抽象基类。
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, Callable
import threading
import time


class HardwareState(Enum):
    """Hardware state enumeration / 硬件状态枚举"""
    DISCONNECTED = "disconnected"      # 未连接
    CONNECTING = "connecting"          # 连接中
    CONNECTED = "connected"            # 已连接
    RUNNING = "running"                # 运行中
    PAUSED = "paused"                  # 已暂停
    ERROR = "error"                    # 错误
    EMERGENCY_STOP = "emergency_stop"  # 紧急停止


class BaseHardwareController(ABC):
    """
    Abstract base class for all hardware controllers.
    所有硬件控制器的抽象基类。

    All hardware controllers must implement this interface.
    所有硬件控制器必须实现此接口。
    """

    def __init__(self, name: str, config: Dict[str, Any] = None):
        """
        Initialize hardware controller.
        初始化硬件控制器。

        Args:
            name: Hardware name / 硬件名称
            config: Configuration dictionary / 配置字典
        """
        self._name = name
        self._config = config or {}
        self._state = HardwareState.DISCONNECTED
        self._error_message: Optional[str] = None
        self._state_lock = threading.Lock()
        self._state_callbacks: list[Callable[[HardwareState, HardwareState], None]] = []
        self._last_update_time: float = 0

    @property
    def name(self) -> str:
        """Get hardware name / 获取硬件名称"""
        return self._name

    @property
    def state(self) -> HardwareState:
        """Get current state / 获取当前状态"""
        with self._state_lock:
            return self._state

    @state.setter
    def state(self, new_state: HardwareState):
        """Set state and notify callbacks / 设置状态并通知回调"""
        with self._state_lock:
            old_state = self._state
            self._state = new_state
            self._last_update_time = time.time()

        # Notify callbacks outside lock
        for callback in self._state_callbacks:
            try:
                callback(old_state, new_state)
            except Exception as e:
                # Log but don't let callback errors affect state change
                import logging
                logging.getLogger(__name__).warning(
                    f"Hardware state callback error for {self._name}: {e}"
                )

    @property
    def error_message(self) -> Optional[str]:
        """Get error message / 获取错误信息"""
        return self._error_message

    def add_state_callback(self, callback: Callable[[HardwareState, HardwareState], None]):
        """
        Add state change callback.
        添加状态变化回调。

        Args:
            callback: Callback function (old_state, new_state) -> None
        """
        self._state_callbacks.append(callback)

    def remove_state_callback(self, callback: Callable[[HardwareState, HardwareState], None]):
        """Remove state change callback / 移除状态变化回调"""
        if callback in self._state_callbacks:
            self._state_callbacks.remove(callback)

    @abstractmethod
    def connect(self) -> bool:
        """
        Connect to hardware.
        连接硬件。

        Returns:
            True if connection successful, False otherwise.
            连接成功返回True，否则返回False。
        """
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """
        Disconnect from hardware.
        断开硬件连接。

        Returns:
            True if disconnection successful, False otherwise.
        """
        pass

    @abstractmethod
    def start(self) -> bool:
        """
        Start hardware operation.
        启动硬件运行。

        Returns:
            True if start successful, False otherwise.
        """
        pass

    @abstractmethod
    def stop(self) -> bool:
        """
        Stop hardware operation.
        停止硬件运行。

        Returns:
            True if stop successful, False otherwise.
        """
        pass

    @abstractmethod
    def pause(self) -> bool:
        """
        Pause hardware operation.
        暂停硬件运行。

        Returns:
            True if pause successful, False otherwise.
        """
        pass

    @abstractmethod
    def resume(self) -> bool:
        """
        Resume hardware operation.
        恢复硬件运行。

        Returns:
            True if resume successful, False otherwise.
        """
        pass

    @abstractmethod
    def emergency_stop(self) -> bool:
        """
        Emergency stop - must execute immediately!
        紧急停止 - 必须立即执行！

        This method should stop all motion immediately and safely.
        此方法应立即安全地停止所有运动。

        Returns:
            True if emergency stop successful, False otherwise.
        """
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """
        Get hardware status.
        获取硬件状态。

        Returns:
            Dictionary containing hardware status information.
            包含硬件状态信息的字典。
        """
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """
        Check if hardware is ready for operation.
        检查硬件是否准备好运行。

        Returns:
            True if hardware is ready, False otherwise.
        """
        pass

    def reset_error(self) -> bool:
        """
        Reset error state.
        重置错误状态。

        Returns:
            True if reset successful, False otherwise.
        """
        if self._state == HardwareState.ERROR:
            self._error_message = None
            self.state = HardwareState.DISCONNECTED
            return True
        return False

    def _set_error(self, message: str):
        """
        Set error state with message.
        设置错误状态和消息。

        Args:
            message: Error message / 错误消息
        """
        self._error_message = message
        self.state = HardwareState.ERROR

    def get_state_info(self) -> Dict[str, Any]:
        """
        Get basic state information.
        获取基本状态信息。

        Returns:
            Dictionary with state information.
        """
        return {
            "name": self._name,
            "state": self._state.value,
            "error_message": self._error_message,
            "last_update": self._last_update_time,
            "is_ready": self.is_ready()
        }


class CompositeHardwareController(BaseHardwareController):
    """
    Base class for composite hardware controllers (e.g., Gantry + Lebai).
    组合硬件控制器的基类（例如龙门架+乐白）。

    Manages multiple sub-controllers as a single unit.
    将多个子控制器作为一个单元管理。
    """

    def __init__(self, name: str, config: Dict[str, Any] = None):
        super().__init__(name, config)
        self._sub_controllers: Dict[str, BaseHardwareController] = {}

    def add_sub_controller(self, name: str, controller: BaseHardwareController):
        """Add a sub-controller / 添加子控制器"""
        self._sub_controllers[name] = controller

    def get_sub_controller(self, name: str) -> Optional[BaseHardwareController]:
        """Get a sub-controller by name / 通过名称获取子控制器"""
        return self._sub_controllers.get(name)

    def connect(self) -> bool:
        """Connect all sub-controllers / 连接所有子控制器"""
        self.state = HardwareState.CONNECTING
        success = True
        for name, controller in self._sub_controllers.items():
            if not controller.connect():
                self._set_error(f"Failed to connect {name}")
                success = False
                break
        if success:
            self.state = HardwareState.CONNECTED
        return success

    def disconnect(self) -> bool:
        """Disconnect all sub-controllers / 断开所有子控制器"""
        success = True
        for controller in self._sub_controllers.values():
            if not controller.disconnect():
                success = False
        if success:
            self.state = HardwareState.DISCONNECTED
        return success

    def emergency_stop(self) -> bool:
        """
        Emergency stop all sub-controllers in parallel.
        并行紧急停止所有子控制器。
        """
        threads = []
        results = {}

        def stop_controller(name, controller):
            results[name] = controller.emergency_stop()

        # Start all emergency stops in parallel
        for name, controller in self._sub_controllers.items():
            t = threading.Thread(target=stop_controller, args=(name, controller))
            t.start()
            threads.append(t)

        # Wait for all to complete
        for t in threads:
            t.join(timeout=5.0)  # 5 second timeout

        self.state = HardwareState.EMERGENCY_STOP
        return all(results.values())

    def get_status(self) -> Dict[str, Any]:
        """Get status of all sub-controllers / 获取所有子控制器状态"""
        return {
            "name": self._name,
            "state": self._state.value,
            "sub_controllers": {
                name: controller.get_status()
                for name, controller in self._sub_controllers.items()
            }
        }

    def is_ready(self) -> bool:
        """Check if all sub-controllers are ready / 检查所有子控制器是否就绪"""
        return all(c.is_ready() for c in self._sub_controllers.values())
