"""
Emergency Controller Module
紧急停止控制器模块

Manages emergency stop for all hardware devices.
管理所有硬件设备的紧急停止。
"""

from typing import Dict, Optional, List, Callable
import threading
import time
from dataclasses import dataclass

from app_core.event_bus import EventBus, EventType, get_event_bus
from hardware.base_hardware import BaseHardwareController, HardwareState


@dataclass
class EmergencyStopResult:
    """Result of emergency stop operation / 紧急停止操作结果"""
    success: bool
    hardware_name: str
    error_message: Optional[str] = None
    duration_ms: float = 0


class EmergencyController:
    """
    Emergency Stop Controller.
    紧急停止控制器。

    Manages emergency stop for all registered hardware.
    管理所有注册硬件的紧急停止。

    Singleton pattern implementation.
    单例模式实现。
    """

    _instance: Optional['EmergencyController'] = None
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

        self._hardware: Dict[str, BaseHardwareController] = {}
        self._emergency_active = False
        self._emergency_lock = threading.Lock()
        self._event_bus = get_event_bus()
        self._last_emergency_time: Optional[float] = None
        self._emergency_callbacks: List[Callable[[bool], None]] = []
        self._initialized = True

    @property
    def is_emergency_active(self) -> bool:
        """Check if emergency stop is active / 检查紧急停止是否激活"""
        with self._emergency_lock:
            return self._emergency_active

    def register_hardware(self, name: str, controller: BaseHardwareController):
        """
        Register hardware for emergency control.
        注册硬件以进行紧急控制。

        Args:
            name: Hardware name / 硬件名称
            controller: Hardware controller / 硬件控制器
        """
        with self._lock:
            self._hardware[name] = controller

    def unregister_hardware(self, name: str):
        """Unregister hardware / 取消注册硬件"""
        with self._lock:
            if name in self._hardware:
                del self._hardware[name]

    def add_emergency_callback(self, callback: Callable[[bool], None]):
        """
        Add emergency state change callback.
        添加紧急状态变化回调。

        Args:
            callback: Callback function (is_active) -> None
        """
        self._emergency_callbacks.append(callback)

    def remove_emergency_callback(self, callback: Callable[[bool], None]):
        """Remove emergency state change callback / 移除紧急状态变化回调"""
        if callback in self._emergency_callbacks:
            self._emergency_callbacks.remove(callback)

    def emergency_stop_all(self) -> Dict[str, EmergencyStopResult]:
        """
        Emergency stop all registered hardware in parallel.
        并行紧急停止所有注册的硬件。

        This method executes emergency stop on all hardware simultaneously.
        此方法同时对所有硬件执行紧急停止。

        Returns:
            Dictionary of results for each hardware.
            每个硬件的结果字典。
        """
        with self._emergency_lock:
            if self._emergency_active:
                # Already in emergency stop state
                return {}

            self._emergency_active = True
            self._last_emergency_time = time.time()

        results: Dict[str, EmergencyStopResult] = {}
        threads: List[threading.Thread] = []
        results_lock = threading.Lock()

        def stop_hardware(name: str, controller: BaseHardwareController):
            """Stop single hardware / 停止单个硬件"""
            start_time = time.time()
            try:
                success = controller.emergency_stop()
                duration_ms = (time.time() - start_time) * 1000
                result = EmergencyStopResult(
                    success=success,
                    hardware_name=name,
                    duration_ms=duration_ms
                )
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                result = EmergencyStopResult(
                    success=False,
                    hardware_name=name,
                    error_message=str(e),
                    duration_ms=duration_ms
                )

            with results_lock:
                results[name] = result

        # Get hardware snapshot
        with self._lock:
            hardware_copy = dict(self._hardware)

        # Start all emergency stops in parallel
        for name, controller in hardware_copy.items():
            t = threading.Thread(target=stop_hardware, args=(name, controller))
            t.start()
            threads.append(t)

        # Wait for all to complete with timeout
        for t in threads:
            t.join(timeout=5.0)  # 5 second timeout per hardware

        # Publish emergency stop event synchronously
        self._event_bus.publish_sync(
            EventType.EMERGENCY_STOP,
            "emergency_controller",
            {
                "results": {
                    name: {
                        "success": r.success,
                        "error": r.error_message,
                        "duration_ms": r.duration_ms
                    }
                    for name, r in results.items()
                },
                "timestamp": self._last_emergency_time
            }
        )

        # Notify callbacks
        for callback in self._emergency_callbacks:
            try:
                callback(True)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Emergency callback error: {e}")

        return results

    def release_emergency_stop(self) -> bool:
        """
        Release emergency stop state.
        释放紧急停止状态。

        This does not resume hardware operation - just releases the lock.
        这不会恢复硬件操作 - 只是释放锁定。

        Returns:
            True if release successful, False otherwise.
        """
        with self._emergency_lock:
            if not self._emergency_active:
                return True  # Already released

            self._emergency_active = False

        # Publish event
        self._event_bus.publish(
            EventType.EMERGENCY_STOP_RELEASED,
            "emergency_controller",
            {"timestamp": time.time()}
        )

        # Notify callbacks
        for callback in self._emergency_callbacks:
            try:
                callback(False)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Emergency release callback error: {e}")

        return True

    def stop_single_hardware(self, name: str) -> Optional[EmergencyStopResult]:
        """
        Emergency stop a single hardware.
        紧急停止单个硬件。

        Args:
            name: Hardware name / 硬件名称

        Returns:
            EmergencyStopResult or None if hardware not found.
        """
        with self._lock:
            controller = self._hardware.get(name)

        if not controller:
            return None

        start_time = time.time()
        try:
            success = controller.emergency_stop()
            duration_ms = (time.time() - start_time) * 1000
            return EmergencyStopResult(
                success=success,
                hardware_name=name,
                duration_ms=duration_ms
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return EmergencyStopResult(
                success=False,
                hardware_name=name,
                error_message=str(e),
                duration_ms=duration_ms
            )

    def get_status(self) -> Dict:
        """
        Get emergency controller status.
        获取紧急控制器状态。
        """
        with self._emergency_lock:
            return {
                "is_active": self._emergency_active,
                "last_emergency_time": self._last_emergency_time,
                "registered_hardware": list(self._hardware.keys())
            }


# Global emergency controller instance / 全局紧急控制器实例
def get_emergency_controller() -> EmergencyController:
    """Get the global emergency controller instance / 获取全局紧急控制器实例"""
    return EmergencyController()
