"""
State Manager Module
全局状态管理器模块

Manages global application state and hardware states.
管理全局应用状态和硬件状态。
"""

from typing import Dict, Any, Optional, Callable, List, Set
import threading
import time
from enum import Enum
from dataclasses import dataclass, field

from app_core.event_bus import EventBus, EventType, get_event_bus
from hardware.base_hardware import HardwareState, BaseHardwareController


class SystemState(Enum):
    """System state enumeration / 系统状态枚举"""
    INITIALIZING = "initializing"    # 初始化中
    READY = "ready"                  # 就绪
    RUNNING = "running"              # 运行中
    PAUSED = "paused"                # 已暂停
    ERROR = "error"                  # 错误
    EMERGENCY_STOP = "emergency_stop"  # 紧急停止
    SHUTDOWN = "shutdown"            # 关闭中


# Valid state transitions (python-gui-architecture state machine pattern)
# 有效的状态转换（python-gui-architecture状态机模式）
# Note: SHUTDOWN can be reached from any state (like EMERGENCY_STOP for safety)
# 注意: SHUTDOWN可从任何状态到达（类似EMERGENCY_STOP的安全覆盖）
VALID_STATE_TRANSITIONS: Dict[SystemState, Set[SystemState]] = {
    SystemState.INITIALIZING: {SystemState.READY, SystemState.ERROR, SystemState.SHUTDOWN},
    SystemState.READY: {SystemState.RUNNING, SystemState.SHUTDOWN, SystemState.ERROR, SystemState.EMERGENCY_STOP},
    SystemState.RUNNING: {SystemState.PAUSED, SystemState.READY, SystemState.SHUTDOWN, SystemState.ERROR, SystemState.EMERGENCY_STOP},
    SystemState.PAUSED: {SystemState.RUNNING, SystemState.READY, SystemState.SHUTDOWN, SystemState.ERROR, SystemState.EMERGENCY_STOP},
    SystemState.ERROR: {SystemState.READY, SystemState.SHUTDOWN},
    SystemState.EMERGENCY_STOP: {SystemState.READY, SystemState.SHUTDOWN},
    SystemState.SHUTDOWN: set(),  # Terminal state
}


@dataclass
class HardwareInfo:
    """Hardware information container / 硬件信息容器"""
    name: str
    controller: BaseHardwareController
    category: str  # e.g., "gantry_lebai", "dual_arm", "wok"
    enabled: bool = True
    last_update: float = field(default_factory=time.time)


class StateManager:
    """
    Global State Manager.
    全局状态管理器。

    Singleton pattern implementation.
    单例模式实现。
    """

    _instance: Optional['StateManager'] = None
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

        self._system_state = SystemState.INITIALIZING
        self._hardware: Dict[str, HardwareInfo] = {}
        self._state_lock = threading.Lock()
        self._event_bus = get_event_bus()
        self._state_callbacks: List[Callable[[SystemState, SystemState], None]] = []
        self._custom_state: Dict[str, Any] = {}
        self._initialized = True

    @property
    def system_state(self) -> SystemState:
        """Get current system state / 获取当前系统状态"""
        with self._state_lock:
            return self._system_state

    def can_transition_to(self, target: SystemState) -> bool:
        """
        Check if transition to target state is valid.
        检查是否可以转换到目标状态。

        Args:
            target: Target state

        Returns:
            True if transition is valid
        """
        valid_targets = VALID_STATE_TRANSITIONS.get(self._system_state, set())
        return target in valid_targets

    def get_valid_transitions(self) -> Set[SystemState]:
        """
        Get all valid transitions from current state.
        获取当前状态的所有有效转换。
        """
        return VALID_STATE_TRANSITIONS.get(self._system_state, set())

    @system_state.setter
    def system_state(self, new_state: SystemState):
        """
        Set system state with transition validation.
        设置系统状态（带转换验证）。

        Note: EMERGENCY_STOP and SHUTDOWN can be reached from any state (safety/cleanup override).
        注意: EMERGENCY_STOP和SHUTDOWN可从任何状态到达（安全/清理覆盖）。
        """
        with self._state_lock:
            old_state = self._system_state

            # Special states that can be reached from any state
            always_allowed = {SystemState.EMERGENCY_STOP, SystemState.SHUTDOWN}

            # Validate transition (except for always-allowed states)
            if new_state not in always_allowed:
                valid_targets = VALID_STATE_TRANSITIONS.get(old_state, set())
                if new_state not in valid_targets:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Invalid state transition: {old_state.value} -> {new_state.value}. "
                        f"Valid targets: {[s.value for s in valid_targets]}"
                    )
                    return  # Reject invalid transition

            self._system_state = new_state

        # Notify callbacks
        for callback in self._state_callbacks:
            try:
                callback(old_state, new_state)
            except Exception as e:
                # Import logger here to avoid circular import at module level
                import logging
                logging.getLogger(__name__).warning(f"State callback error: {e}")

        # Publish event
        self._event_bus.publish(
            EventType.STATUS_UPDATE,
            "state_manager",
            {"old_state": old_state.value, "new_state": new_state.value}
        )

    def add_state_callback(self, callback: Callable[[SystemState, SystemState], None]):
        """Add system state change callback / 添加系统状态变化回调"""
        self._state_callbacks.append(callback)

    def remove_state_callback(self, callback: Callable[[SystemState, SystemState], None]):
        """Remove system state change callback / 移除系统状态变化回调"""
        if callback in self._state_callbacks:
            self._state_callbacks.remove(callback)

    def register_hardware(self, name: str, controller: BaseHardwareController,
                          category: str, enabled: bool = True):
        """
        Register a hardware controller.
        注册硬件控制器。

        Args:
            name: Hardware name / 硬件名称
            controller: Hardware controller instance / 硬件控制器实例
            category: Hardware category / 硬件类别
            enabled: Whether hardware is enabled / 硬件是否启用
        """
        with self._state_lock:
            self._hardware[name] = HardwareInfo(
                name=name,
                controller=controller,
                category=category,
                enabled=enabled
            )

        # Subscribe to controller state changes
        controller.add_state_callback(
            lambda old, new: self._on_hardware_state_change(name, old, new)
        )

    def unregister_hardware(self, name: str):
        """Unregister a hardware controller / 取消注册硬件控制器"""
        with self._state_lock:
            if name in self._hardware:
                del self._hardware[name]

    def get_hardware(self, name: str) -> Optional[BaseHardwareController]:
        """Get hardware controller by name / 通过名称获取硬件控制器"""
        with self._state_lock:
            info = self._hardware.get(name)
            return info.controller if info else None

    def get_hardware_info(self, name: str) -> Optional[HardwareInfo]:
        """Get hardware info by name / 通过名称获取硬件信息"""
        with self._state_lock:
            return self._hardware.get(name)

    def get_all_hardware(self) -> Dict[str, HardwareInfo]:
        """Get all registered hardware / 获取所有注册的硬件"""
        with self._state_lock:
            return dict(self._hardware)

    def get_hardware_by_category(self, category: str) -> List[HardwareInfo]:
        """Get hardware by category / 通过类别获取硬件"""
        with self._state_lock:
            return [
                info for info in self._hardware.values()
                if info.category == category
            ]

    def get_enabled_hardware(self) -> List[HardwareInfo]:
        """Get all enabled hardware / 获取所有已启用的硬件"""
        with self._state_lock:
            return [
                info for info in self._hardware.values()
                if info.enabled
            ]

    def set_hardware_enabled(self, name: str, enabled: bool):
        """Enable or disable hardware / 启用或禁用硬件"""
        with self._state_lock:
            if name in self._hardware:
                self._hardware[name].enabled = enabled

    def _on_hardware_state_change(self, name: str,
                                   old_state: HardwareState,
                                   new_state: HardwareState):
        """Handle hardware state change / 处理硬件状态变化"""
        with self._state_lock:
            if name in self._hardware:
                self._hardware[name].last_update = time.time()

        # Publish event
        self._event_bus.publish(
            EventType.HARDWARE_STATE_CHANGED,
            name,
            {
                "hardware_name": name,
                "old_state": old_state.value,
                "new_state": new_state.value
            }
        )

        # Check if any hardware in error state
        self._check_system_state()

    def _check_system_state(self):
        """Check and update system state based on hardware states / 检查并更新系统状态"""
        with self._state_lock:
            enabled_hardware = [
                info for info in self._hardware.values()
                if info.enabled
            ]
            current = self._system_state

        # Determine target state based on hardware states
        target = None

        # Check for emergency stop
        if any(h.controller.state == HardwareState.EMERGENCY_STOP
               for h in enabled_hardware):
            target = SystemState.EMERGENCY_STOP
        # Check for errors
        elif any(h.controller.state == HardwareState.ERROR
                 for h in enabled_hardware):
            target = SystemState.ERROR
        # Check if any running
        elif any(h.controller.state == HardwareState.RUNNING
                 for h in enabled_hardware):
            target = SystemState.RUNNING
        # Check if all connected
        elif all(h.controller.state in [HardwareState.CONNECTED, HardwareState.PAUSED]
                 for h in enabled_hardware if h.enabled):
            target = SystemState.READY

        # Only transition if target differs from current state
        if target is not None and target != current:
            self.system_state = target

    def get_all_status(self) -> Dict[str, Any]:
        """
        Get complete system status.
        获取完整系统状态。

        Returns:
            Dictionary with system and hardware status.
        """
        with self._state_lock:
            hardware_status = {}
            for name, info in self._hardware.items():
                hardware_status[name] = {
                    "category": info.category,
                    "enabled": info.enabled,
                    "state": info.controller.state.value,
                    "is_ready": info.controller.is_ready(),
                    "last_update": info.last_update,
                    "status": info.controller.get_status()
                }

            return {
                "system_state": self._system_state.value,
                "hardware": hardware_status,
                "custom": dict(self._custom_state)
            }

    def set_custom_state(self, key: str, value: Any):
        """Set custom state value / 设置自定义状态值"""
        with self._state_lock:
            self._custom_state[key] = value

    def get_custom_state(self, key: str, default: Any = None) -> Any:
        """Get custom state value / 获取自定义状态值"""
        with self._state_lock:
            return self._custom_state.get(key, default)

    def is_all_connected(self) -> bool:
        """Check if all enabled hardware is connected / 检查所有已启用硬件是否已连接"""
        with self._state_lock:
            for info in self._hardware.values():
                if info.enabled:
                    if info.controller.state == HardwareState.DISCONNECTED:
                        return False
            return True

    def is_any_running(self) -> bool:
        """Check if any hardware is running / 检查是否有硬件正在运行"""
        with self._state_lock:
            return any(
                info.controller.state == HardwareState.RUNNING
                for info in self._hardware.values()
                if info.enabled
            )


# Global state manager instance / 全局状态管理器实例
def get_state_manager() -> StateManager:
    """Get the global state manager instance / 获取全局状态管理器实例"""
    return StateManager()
