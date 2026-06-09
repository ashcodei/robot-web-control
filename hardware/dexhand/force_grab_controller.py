"""
Force Grab Controller Module
力反馈抓取控制器模块

Logic controller for force-feedback grabbing with dual detection modes.
支持双重检测模式的力反馈抓取逻辑控制器。
"""

import threading
import time
import logging
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class ForceGrabState(Enum):
    """Force grab state enumeration / 力反馈抓取状态枚举"""
    IDLE = "idle"
    PREPARING = "preparing"
    GRABBING = "grabbing"
    HOLDING = "holding"
    RELEASING = "releasing"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ForceGrabConfig:
    """Force grab configuration / 力反馈抓取配置"""
    # Pre-grab positions (0=closed, 255=open)
    pre_grab_positions: List[int] = field(default_factory=lambda: [250] * 6)
    # Movement parameters
    speed: int = 80
    torque: int = 150
    # Sensor mode parameters
    use_sensor: bool = True
    threshold: int = 50
    step: int = 5
    consecutive_readings_required: int = 3
    # Stall detection
    stall_time: float = 1.5
    stall_tolerance: int = 2
    # Position threshold to ignore sensor noise
    ignore_position_threshold: int = 200


@dataclass
class FingerState:
    """Per-finger state tracking / 每个手指的状态跟踪"""
    stopped: bool = False
    position: int = 250
    actual_position: int = 250
    force: int = 0
    consecutive_readings: int = 0
    stall_start_time: Optional[float] = None
    stop_reason: str = ""


class ForceGrabController:
    """
    Force feedback grab controller.
    力反馈抓取控制器。

    Implements two grab modes:
    1. Sensor mode: Uses touch sensors to detect contact
    2. Torque limit mode: Uses motor torque limit for contact detection

    实现两种抓取模式：
    1. 传感器模式：使用触觉传感器检测接触
    2. 力矩限制模式：使用电机力矩限制进行接触检测
    """

    # L6 finger joint mapping: each finger's bend joint index
    FINGER_JOINT_MAP = {
        "thumb": 0,   # Thumb bend
        "index": 2,   # Index bend
        "middle": 3,  # Middle bend
        "ring": 4,    # Ring bend
        "little": 5,  # Little bend
    }

    FINGER_NAMES = ["thumb", "index", "middle", "ring", "little"]

    def __init__(self, dexhand_controller=None):
        """
        Initialize force grab controller.
        初始化力反馈抓取控制器。

        Args:
            dexhand_controller: DexhandController instance
        """
        self._controller = dexhand_controller
        self._config = ForceGrabConfig()
        self._state = ForceGrabState.IDLE
        self._finger_states: Dict[str, FingerState] = {}
        self._current_positions: List[int] = [250] * 6

        # Threading
        self._lock = threading.Lock()
        self._grab_thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()

        # Callbacks
        self._state_callback: Optional[Callable[[ForceGrabState], None]] = None
        self._finger_callback: Optional[Callable[[str, FingerState], None]] = None

        self._init_finger_states()

    def _init_finger_states(self):
        """Initialize finger states / 初始化手指状态"""
        for finger in self.FINGER_NAMES:
            self._finger_states[finger] = FingerState()

    @property
    def state(self) -> ForceGrabState:
        """Get current state / 获取当前状态"""
        return self._state

    @property
    def config(self) -> ForceGrabConfig:
        """Get configuration / 获取配置"""
        return self._config

    @property
    def finger_states(self) -> Dict[str, FingerState]:
        """Get finger states / 获取手指状态"""
        return self._finger_states

    def set_controller(self, controller):
        """Set dexhand controller / 设置灵巧手控制器"""
        self._controller = controller

    def set_state_callback(self, callback: Callable[[ForceGrabState], None]):
        """Set state change callback / 设置状态变化回调"""
        self._state_callback = callback

    def set_finger_callback(self, callback: Callable[[str, FingerState], None]):
        """Set finger state callback / 设置手指状态回调"""
        self._finger_callback = callback

    def _set_state(self, new_state: ForceGrabState):
        """Set state and notify callback / 设置状态并通知回调"""
        self._state = new_state
        if self._state_callback:
            try:
                self._state_callback(new_state)
            except Exception as e:
                logger.warning(f"State callback error: {e}")

    def _update_finger(self, finger: str, **kwargs):
        """Update finger state and notify callback / 更新手指状态并通知回调"""
        if finger in self._finger_states:
            for key, value in kwargs.items():
                if hasattr(self._finger_states[finger], key):
                    setattr(self._finger_states[finger], key, value)

            if self._finger_callback:
                try:
                    self._finger_callback(finger, self._finger_states[finger])
                except Exception as e:
                    logger.warning(f"Finger callback error: {e}")

    def configure(self, **kwargs):
        """
        Update configuration.
        更新配置。

        Args:
            **kwargs: Configuration parameters
        """
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)

    def start_grab(self) -> bool:
        """
        Start force grab sequence.
        开始力反馈抓取序列。

        Returns:
            True if grab started successfully
        """
        if not self._controller or not self._controller.is_ready():
            logger.error("Controller not ready")
            return False

        if self._state not in [ForceGrabState.IDLE, ForceGrabState.STOPPED]:
            logger.warning("Cannot start grab in current state")
            return False

        # Reset state
        self._stop_flag.clear()
        self._init_finger_states()
        self._current_positions = list(self._config.pre_grab_positions)

        # Set speed and torque
        self._controller.set_speed(self._config.speed)
        self._controller.set_torque(self._config.torque)

        # Start grab thread
        self._grab_thread = threading.Thread(target=self._grab_sequence, daemon=True)
        self._grab_thread.start()

        return True

    def stop_grab(self):
        """Stop grab sequence / 停止抓取序列"""
        self._stop_flag.set()
        self._set_state(ForceGrabState.STOPPED)

    def release(self) -> bool:
        """
        Release grip - open all fingers.
        释放抓取 - 张开所有手指。

        Returns:
            True if release successful
        """
        self.stop_grab()

        if self._controller:
            self._set_state(ForceGrabState.RELEASING)
            self._controller.open_hand()
            self._init_finger_states()
            self._set_state(ForceGrabState.IDLE)
            return True
        return False

    def _grab_sequence(self):
        """Main grab sequence thread / 主抓取序列线程"""
        try:
            # Phase 1: Move to pre-grab position
            self._set_state(ForceGrabState.PREPARING)
            self._controller.set_positions(self._current_positions)
            time.sleep(0.5)  # Wait for position

            if self._stop_flag.is_set():
                return

            # Phase 2: Start grabbing
            self._set_state(ForceGrabState.GRABBING)

            if self._config.use_sensor:
                self._sensor_mode_grab()
            else:
                self._torque_limit_grab()

        except Exception as e:
            logger.error(f"Grab sequence error: {e}")
            self._set_state(ForceGrabState.ERROR)

    def _sensor_mode_grab(self):
        """Sensor-based grab with force feedback / 基于传感器的力反馈抓取"""
        step_interval = 0.05  # 50ms per step

        while not self._stop_flag.is_set():
            # Get force values
            touch_data = self._controller.get_touch_data()
            force_values = {}
            if touch_data:
                force_values = touch_data.get_max_values()

            # Get actual positions
            actual_positions = self._controller.get_actual_positions()

            current_time = time.time()
            all_stopped = True

            # Process each finger
            for finger, joint_idx in self.FINGER_JOINT_MAP.items():
                if self._finger_states[finger].stopped:
                    continue

                all_stopped = False
                current_force = force_values.get(finger, 0)
                current_pos = self._current_positions[joint_idx]
                actual_pos = actual_positions[joint_idx] if joint_idx < len(actual_positions) else current_pos

                # Update finger state
                self._update_finger(finger, force=current_force, actual_position=actual_pos)

                # Little finger follows ring finger (sensor workaround)
                if finger == "little" and self._finger_states["ring"].stopped:
                    self._update_finger(finger, stopped=True, stop_reason="follow_ring")
                    continue

                # Ignore sensor readings until position < threshold (noise reduction)
                if current_pos > self._config.ignore_position_threshold:
                    new_pos = max(0, current_pos - self._config.step)
                    self._current_positions[joint_idx] = new_pos
                    self._update_finger(finger, position=new_pos, consecutive_readings=0)
                    self._finger_states[finger].stall_start_time = None
                    continue

                # Stall detection (time-based)
                last_actual = self._finger_states[finger].actual_position
                is_stalled = False
                stall_duration = 0.0

                if abs(actual_pos - last_actual) <= self._config.stall_tolerance:
                    if self._finger_states[finger].stall_start_time is None:
                        self._finger_states[finger].stall_start_time = current_time
                    else:
                        stall_duration = current_time - self._finger_states[finger].stall_start_time
                        if stall_duration >= self._config.stall_time:
                            is_stalled = True
                else:
                    self._finger_states[finger].stall_start_time = None

                # Force detection
                force_exceeded = current_force >= self._config.threshold
                if force_exceeded:
                    self._finger_states[finger].consecutive_readings += 1
                else:
                    self._finger_states[finger].consecutive_readings = 0

                force_confirmed = (self._finger_states[finger].consecutive_readings >=
                                   self._config.consecutive_readings_required)

                # Stop if either detection confirms contact
                if force_confirmed or is_stalled:
                    if force_confirmed and is_stalled:
                        reason = f"F={current_force},Stall"
                    elif force_confirmed:
                        reason = f"F={current_force}"
                    else:
                        reason = f"Stall@{actual_pos}"

                    self._update_finger(finger, stopped=True, stop_reason=reason)
                    logger.info(f"Finger {finger} stopped: {reason}")

                    # Stop little finger if ring stops
                    if finger == "ring" and not self._finger_states["little"].stopped:
                        self._update_finger("little", stopped=True, stop_reason="follow_ring")
                else:
                    # Continue closing
                    new_pos = max(0, current_pos - self._config.step)
                    self._current_positions[joint_idx] = new_pos
                    self._update_finger(finger, position=new_pos)

                    # Fully closed
                    if new_pos == 0:
                        self._update_finger(finger, stopped=True, stop_reason="fully_closed")
                        if finger == "ring":
                            self._update_finger("little", stopped=True, stop_reason="follow_ring")

            # Send positions
            self._controller.set_positions(self._current_positions)

            # Check if all stopped
            if all_stopped or all(fs.stopped for fs in self._finger_states.values()):
                self._set_state(ForceGrabState.HOLDING)
                logger.info("Force grab complete - all fingers stable")
                return

            time.sleep(step_interval)

    def _torque_limit_grab(self):
        """Torque-limited grab (motor stall detection) / 力矩限制抓取（电机堵转检测）"""
        # Close all fingers to position 0
        close_positions = [0] * 6
        # Keep thumb yaw at preset
        close_positions[1] = self._config.pre_grab_positions[1]

        logger.info(f"Torque limit grab: closing to {close_positions}")
        self._controller.set_positions(close_positions)

        # Update finger states
        for finger in self.FINGER_NAMES:
            self._update_finger(finger, position=0, stop_reason=f"T={self._config.torque}")

        # Wait for motors to stall
        time.sleep(2.0)

        self._set_state(ForceGrabState.HOLDING)
        logger.info("Torque limit grab complete - holding")

    def get_current_positions(self) -> List[int]:
        """Get current command positions / 获取当前命令位置"""
        return list(self._current_positions)

    def get_grab_config_dict(self) -> Dict[str, Any]:
        """
        Get grab configuration as dictionary (for pose recording).
        获取抓取配置字典（用于位姿录制）。

        Returns:
            Dictionary with grab parameters
        """
        return {
            "pre_grab_positions": list(self._config.pre_grab_positions),
            "speed": self._config.speed,
            "torque": self._config.torque,
            "use_sensor": self._config.use_sensor,
            "threshold": self._config.threshold,
            "step": self._config.step,
            "stall_time": self._config.stall_time,
        }
