"""
Dexhand Controller Module
灵巧手控制器模块

BaseHardwareController implementation for LinkerHand SDK.
LinkerHand SDK 的 BaseHardwareController 实现。
"""

import os
import sys
import threading
import time
import logging
from typing import Dict, Any, List, Optional

from ..base_hardware import BaseHardwareController, HardwareState
from .hand_configs import HAND_CONFIGS, get_hand_config
from .touch_sensor import TouchSensor, TouchData

logger = logging.getLogger(__name__)

# LinkerHand SDK import
LINKERHAND_AVAILABLE = False
LinkerHandApi = None

try:
    # Try to find and import LinkerHand SDK
    sdk_paths = [
        # libs/ inside project root
        os.path.join(os.path.dirname(__file__), '..', '..', 'libs', 'linkerhand-python-sdk-main'),
        # Sibling project (legacy)
        os.path.join(os.path.dirname(__file__), '..', '..', '..', 'New_GUI_with_Master_Arm_Teleop', 'linkerhand-python-sdk-main'),
    ]

    for sdk_path in sdk_paths:
        resolved = os.path.abspath(sdk_path)
        if os.path.exists(resolved) and resolved not in sys.path:
            sys.path.insert(0, resolved)
            break

    from LinkerHand.linker_hand_api import LinkerHandApi
    LINKERHAND_AVAILABLE = True
except ImportError as e:
    logger.warning(f"LinkerHand SDK not available: {e}")


class DexhandController(BaseHardwareController):
    """
    Dexterous hand controller using LinkerHand SDK.
    使用 LinkerHand SDK 的灵巧手控制器。

    Supports L6 and L10 hand types via CAN bus.
    通过 CAN 总线支持 L6 和 L10 手型。
    """

    def __init__(self, name: str = "dexhand", config: Dict[str, Any] = None):
        """
        Initialize dexhand controller.
        初始化灵巧手控制器。

        Args:
            name: Controller name
            config: Configuration dict with keys:
                - can_interface: CAN interface name (default: "can0")
                - modbus_port: Modbus serial port (default: None)
                - hand_type: "L6" or "L10" (default: "L6")
                - hand_side: "left" or "right" (default: "right")
                - default_speed: Default movement speed (default: 100)
                - default_torque: Default torque limit (default: 150)
        """
        super().__init__(name, config)

        # Configuration
        self._can_interface = config.get("can_interface", "can0") if config else "can0"
        self._modbus_port = config.get("modbus_port", None) if config else None
        self._hand_type = config.get("hand_type", "L6") if config else "L6"
        self._hand_side = config.get("hand_side", "right") if config else "right"
        self._default_speed = config.get("default_speed", 100) if config else 100
        self._default_torque = config.get("default_torque", 150) if config else 150

        # Hand API instance
        self._hand_api = None
        self._hand_config = get_hand_config(self._hand_type)

        # Touch sensor
        self._touch_sensor = TouchSensor()

        # State tracking
        self._current_positions: List[int] = []
        self._target_positions: List[int] = []
        self._lock = threading.Lock()

        # Initialize positions
        if self._hand_config:
            self._current_positions = list(self._hand_config.init_pos)
            self._target_positions = list(self._hand_config.init_pos)

    @property
    def hand_api(self):
        """Get LinkerHand API instance / 获取 LinkerHand API 实例"""
        return self._hand_api

    @property
    def hand_type(self) -> str:
        """Get hand type / 获取手型"""
        return self._hand_type

    @property
    def hand_side(self) -> str:
        """Get hand side / 获取手部侧别"""
        return self._hand_side

    @property
    def num_joints(self) -> int:
        """Get number of joints / 获取关节数量"""
        return self._hand_config.num_joints if self._hand_config else 6

    @property
    def touch_sensor(self) -> TouchSensor:
        """Get touch sensor handler / 获取触觉传感器处理器"""
        return self._touch_sensor

    def connect(self) -> bool:
        """
        Connect to hand via LinkerHand SDK.
        通过 LinkerHand SDK 连接手部。
        """
        if not LINKERHAND_AVAILABLE:
            self._set_error("LinkerHand SDK not available")
            return False

        self.state = HardwareState.CONNECTING

        try:
            logger.info(f"Connecting to {self._hand_side} {self._hand_type} hand via {self._can_interface}")

            # Create LinkerHand API instance
            # Note: SDK may call sys.exit(1) if CAN interface is not up,
            # so we catch BaseException (SystemExit inherits from BaseException, not Exception)
            self._hand_api = LinkerHandApi(
                hand_type=self._hand_side,
                hand_joint=self._hand_type,
                can=self._can_interface,
                modbus=self._modbus_port or "None"
            )

            # Set initial speed and torque
            self._set_speed_torque(self._default_speed, self._default_torque)

            # Read initial state
            self._read_state()

            self.state = HardwareState.CONNECTED
            logger.info(f"Connected to {self._hand_side} {self._hand_type} hand")
            return True

        except SystemExit as e:
            self._set_error(f"LinkerHand SDK exited (CAN interface not ready?): {e}")
        except Exception as e:
            self._set_error(f"Connection failed: {e}")
            logger.error(f"Failed to connect to hand: {e}")
            return False

    def disconnect(self) -> bool:
        """
        Disconnect from hand.
        断开与手部的连接。
        """
        try:
            self._hand_api = None
            self.state = HardwareState.DISCONNECTED
            logger.info(f"Disconnected from {self._hand_side} hand")
            return True
        except Exception as e:
            logger.error(f"Disconnect error: {e}")
            return False

    def start(self) -> bool:
        """Start hand operation / 启动手部操作"""
        if self.state == HardwareState.CONNECTED:
            self.state = HardwareState.RUNNING
            return True
        return False

    def stop(self) -> bool:
        """Stop hand operation / 停止手部操作"""
        if self.state == HardwareState.RUNNING:
            self.state = HardwareState.CONNECTED
            return True
        return False

    def pause(self) -> bool:
        """Pause hand operation / 暂停手部操作"""
        if self.state == HardwareState.RUNNING:
            self.state = HardwareState.PAUSED
            return True
        return False

    def resume(self) -> bool:
        """Resume hand operation / 恢复手部操作"""
        if self.state == HardwareState.PAUSED:
            self.state = HardwareState.RUNNING
            return True
        return False

    def emergency_stop(self) -> bool:
        """
        Emergency stop - open hand immediately.
        紧急停止 - 立即张开手。
        """
        self.state = HardwareState.EMERGENCY_STOP

        if self._hand_api:
            try:
                # Open hand (safe position)
                open_pos = [255] * self.num_joints
                self._hand_api.finger_move(open_pos)
                logger.warning(f"Emergency stop: {self._hand_side} hand opened")
            except Exception as e:
                logger.error(f"Emergency stop error: {e}")

        return True

    def get_status(self) -> Dict[str, Any]:
        """Get hand status / 获取手部状态"""
        return {
            "name": self._name,
            "state": self._state.value,
            "hand_type": self._hand_type,
            "hand_side": self._hand_side,
            "connected": self._hand_api is not None,
            "num_joints": self.num_joints,
            "current_positions": list(self._current_positions),
            "target_positions": list(self._target_positions),
            "can_interface": self._can_interface,
            "error_message": self._error_message,
        }

    def is_ready(self) -> bool:
        """Check if hand is ready / 检查手部是否就绪"""
        return (self._hand_api is not None and
                self.state in [HardwareState.CONNECTED, HardwareState.RUNNING])

    def _set_speed_torque(self, speed: int, torque: int):
        """Set speed and torque for all joints / 为所有关节设置速度和力矩"""
        if not self._hand_api:
            return

        try:
            speed_values = [speed] * self.num_joints
            torque_values = [torque] * self.num_joints
            self._hand_api.set_speed(speed_values)
            self._hand_api.set_torque(torque_values)
        except Exception as e:
            logger.warning(f"Set speed/torque error: {e}")

    def _read_state(self):
        """Read current joint positions from hand / 从手部读取当前关节位置"""
        if not self._hand_api:
            return

        try:
            state = self._hand_api.get_state()
            if state and len(state) >= self.num_joints:
                with self._lock:
                    self._current_positions = [int(v) for v in state[:self.num_joints]]
        except Exception as e:
            logger.debug(f"Read state error: {e}")

    def set_positions(self, positions: List[int]) -> bool:
        """
        Set finger positions.
        设置手指位置。

        Args:
            positions: List of joint positions (0-255)

        Returns:
            True if command sent successfully
        """
        if not self._hand_api:
            return False

        try:
            # Validate and clamp positions
            valid_positions = [
                max(0, min(255, int(p)))
                for p in positions[:self.num_joints]
            ]

            # Pad if needed
            while len(valid_positions) < self.num_joints:
                valid_positions.append(self._current_positions[len(valid_positions)])

            with self._lock:
                self._target_positions = valid_positions

            self._hand_api.finger_move(valid_positions)
            return True

        except Exception as e:
            logger.error(f"Set positions error: {e}")
            return False

    def get_positions(self) -> List[int]:
        """
        Get current joint positions (from last read).
        获取当前关节位置（从最后一次读取）。

        Returns:
            List of joint positions
        """
        with self._lock:
            return list(self._current_positions)

    def get_actual_positions(self) -> List[int]:
        """
        Read and return actual joint positions from hardware.
        从硬件读取并返回实际关节位置。

        Returns:
            List of actual joint positions
        """
        self._read_state()
        return self.get_positions()

    def set_speed(self, speed: int) -> bool:
        """Set movement speed for all joints / 为所有关节设置运动速度"""
        if not self._hand_api:
            return False

        try:
            speed_values = [max(1, min(255, speed))] * self.num_joints
            self._hand_api.set_speed(speed_values)
            return True
        except Exception as e:
            logger.error(f"Set speed error: {e}")
            return False

    def set_torque(self, torque: int) -> bool:
        """Set torque limit for all joints / 为所有关节设置力矩限制"""
        if not self._hand_api:
            return False

        try:
            torque_values = [max(1, min(255, torque))] * self.num_joints
            self._hand_api.set_torque(torque_values)
            return True
        except Exception as e:
            logger.error(f"Set torque error: {e}")
            return False

    def get_touch_data(self) -> Optional[TouchData]:
        """
        Get touch sensor data.
        获取触觉传感器数据。

        Returns:
            TouchData if available
        """
        if not self._hand_api:
            return None
        return self._touch_sensor.update_from_api(self._hand_api)

    def execute_preset(self, action_name: str) -> bool:
        """
        Execute a preset action.
        执行预设动作。

        Args:
            action_name: Name of preset action (e.g., "张开", "握拳")

        Returns:
            True if action executed successfully
        """
        if not self._hand_config or not self._hand_config.preset_actions:
            return False

        positions = self._hand_config.preset_actions.get(action_name)
        if positions:
            return self.set_positions(list(positions))
        return False

    def open_hand(self) -> bool:
        """Open hand fully / 完全张开手"""
        return self.set_positions([255] * self.num_joints)

    def close_hand(self) -> bool:
        """Close hand fully / 完全握拳"""
        return self.set_positions([0] * self.num_joints)
