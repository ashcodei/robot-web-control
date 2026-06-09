"""
Gloves Controller Module
手套控制器模块

Controller for teleoperation gloves via ROS.
通过 ROS 控制遥操作手套。
"""

import threading
import time
import logging
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from enum import Enum

from .ros_connection import ROSConnection, ROSConnectionState

logger = logging.getLogger(__name__)


class GlovesState(Enum):
    """Gloves connection state / 手套连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    CALIBRATING = "calibrating"
    ACTIVE = "active"
    ERROR = "error"


@dataclass
class HandData:
    """Hand tracking data / 手部跟踪数据"""
    timestamp: float = 0.0
    # Finger positions (0.0 = open, 1.0 = closed)
    thumb: float = 0.0
    index: float = 0.0
    middle: float = 0.0
    ring: float = 0.0
    pinky: float = 0.0
    # Wrist orientation (degrees)
    wrist_roll: float = 0.0
    wrist_pitch: float = 0.0
    wrist_yaw: float = 0.0
    # Position (mm)
    position_x: float = 0.0
    position_y: float = 0.0
    position_z: float = 0.0
    # Raw joint angles (optional)
    raw_joints: List[float] = field(default_factory=list)

    def to_finger_list(self) -> List[float]:
        """Convert to finger position list / 转换为手指位置列表"""
        return [self.thumb, self.index, self.middle, self.ring, self.pinky]

    def to_dexhand_positions(self, hand_type: str = "L6") -> List[int]:
        """
        Convert to dexhand positions (0-255).
        转换为灵巧手位置 (0-255)。

        Args:
            hand_type: "L6" or "L10"

        Returns:
            List of joint positions
        """
        # Map finger positions (0-1) to dexhand positions (255-0)
        # Note: dexhand uses 255=open, 0=closed
        if hand_type == "L6":
            return [
                int((1 - self.thumb) * 255),      # Thumb bend
                128,                               # Thumb yaw (neutral)
                int((1 - self.index) * 255),       # Index
                int((1 - self.middle) * 255),      # Middle
                int((1 - self.ring) * 255),        # Ring
                int((1 - self.pinky) * 255),       # Pinky
            ]
        else:  # L10
            return [
                int((1 - self.thumb) * 255),
                128,
                int((1 - self.index) * 255),
                128,
                int((1 - self.middle) * 255),
                128,
                int((1 - self.ring) * 255),
                128,
                int((1 - self.pinky) * 255),
                128,
            ]


@dataclass
class CalibrationData:
    """Calibration data for hand tracking / 手部跟踪校准数据"""
    left_offset: HandData = field(default_factory=HandData)
    right_offset: HandData = field(default_factory=HandData)
    left_scale: Dict[str, float] = field(default_factory=lambda: {"fingers": 1.0, "wrist": 1.0})
    right_scale: Dict[str, float] = field(default_factory=lambda: {"fingers": 1.0, "wrist": 1.0})


class GlovesController:
    """
    Teleoperation gloves controller.
    遥操作手套控制器。

    Subscribes to ROS topics for hand tracking data and provides
    calibrated finger/wrist positions for robot control.
    """

    # Default ROS topics
    DEFAULT_LEFT_TOPIC = "/gloves/left_hand"
    DEFAULT_RIGHT_TOPIC = "/gloves/right_hand"
    DEFAULT_MSG_TYPE = "std_msgs/Float32MultiArray"

    def __init__(self, ros_connection: Optional[ROSConnection] = None):
        """
        Initialize gloves controller.
        初始化手套控制器。

        Args:
            ros_connection: ROSConnection instance
        """
        self._ros = ros_connection
        self._state = GlovesState.DISCONNECTED
        self._lock = threading.Lock()

        # Configuration
        self._left_topic = self.DEFAULT_LEFT_TOPIC
        self._right_topic = self.DEFAULT_RIGHT_TOPIC
        self._msg_type = self.DEFAULT_MSG_TYPE
        self._update_rate = 50.0  # Hz
        self._smoothing_factor = 0.8

        # Data
        self._left_data = HandData()
        self._right_data = HandData()
        self._calibration = CalibrationData()

        # Smoothing buffers
        self._left_buffer: Optional[HandData] = None
        self._right_buffer: Optional[HandData] = None

        # Callbacks
        self._data_callbacks: List[Callable[[str, HandData], None]] = []
        self._state_callbacks: List[Callable[[GlovesState], None]] = []

    @property
    def state(self) -> GlovesState:
        """Get current state / 获取当前状态"""
        return self._state

    @property
    def left_hand(self) -> HandData:
        """Get left hand data / 获取左手数据"""
        with self._lock:
            return self._left_data

    @property
    def right_hand(self) -> HandData:
        """Get right hand data / 获取右手数据"""
        with self._lock:
            return self._right_data

    def set_ros_connection(self, ros_connection: ROSConnection):
        """Set ROS connection / 设置 ROS 连接"""
        self._ros = ros_connection

    def configure(self, left_topic: str = None, right_topic: str = None,
                  msg_type: str = None, update_rate: float = None,
                  smoothing_factor: float = None):
        """
        Configure gloves controller.
        配置手套控制器。

        Args:
            left_topic: Left hand ROS topic
            right_topic: Right hand ROS topic
            msg_type: ROS message type
            update_rate: Update rate in Hz
            smoothing_factor: Smoothing factor (0-1)
        """
        if left_topic:
            self._left_topic = left_topic
        if right_topic:
            self._right_topic = right_topic
        if msg_type:
            self._msg_type = msg_type
        if update_rate:
            self._update_rate = update_rate
        if smoothing_factor is not None:
            self._smoothing_factor = max(0.0, min(1.0, smoothing_factor))

    def add_data_callback(self, callback: Callable[[str, HandData], None]):
        """Add callback for hand data updates / 添加手部数据更新回调"""
        self._data_callbacks.append(callback)

    def add_state_callback(self, callback: Callable[[GlovesState], None]):
        """Add callback for state changes / 添加状态变化回调"""
        self._state_callbacks.append(callback)

    def _set_state(self, new_state: GlovesState):
        """Set state and notify callbacks / 设置状态并通知回调"""
        self._state = new_state
        for callback in self._state_callbacks:
            try:
                callback(new_state)
            except Exception as e:
                logger.warning(f"State callback error: {e}")

    def connect(self) -> bool:
        """
        Connect to gloves via ROS.
        通过 ROS 连接到手套。

        Returns:
            True if connection successful
        """
        if not self._ros or not self._ros.is_connected:
            logger.error("ROS not connected")
            return False

        self._set_state(GlovesState.CONNECTING)

        try:
            # Subscribe to hand tracking topics
            throttle_rate = int(1000 / self._update_rate)

            success_left = self._ros.subscribe(
                self._left_topic, self._msg_type,
                self._on_left_hand_data,
                throttle_rate=throttle_rate
            )

            success_right = self._ros.subscribe(
                self._right_topic, self._msg_type,
                self._on_right_hand_data,
                throttle_rate=throttle_rate
            )

            if success_left or success_right:
                self._set_state(GlovesState.CONNECTED)
                logger.info("Gloves connected")
                return True
            else:
                raise Exception("Failed to subscribe to hand topics")

        except Exception as e:
            logger.error(f"Gloves connection failed: {e}")
            self._set_state(GlovesState.ERROR)
            return False

    def disconnect(self):
        """Disconnect gloves / 断开手套"""
        if self._ros:
            self._ros.unsubscribe(self._left_topic)
            self._ros.unsubscribe(self._right_topic)

        self._set_state(GlovesState.DISCONNECTED)
        logger.info("Gloves disconnected")

    def _on_left_hand_data(self, msg: Dict[str, Any]):
        """Handle left hand data / 处理左手数据"""
        data = self._parse_hand_message(msg)
        data = self._apply_calibration(data, "left")
        data = self._apply_smoothing(data, "left")

        with self._lock:
            self._left_data = data

        self._notify_data_callbacks("left", data)

    def _on_right_hand_data(self, msg: Dict[str, Any]):
        """Handle right hand data / 处理右手数据"""
        data = self._parse_hand_message(msg)
        data = self._apply_calibration(data, "right")
        data = self._apply_smoothing(data, "right")

        with self._lock:
            self._right_data = data

        self._notify_data_callbacks("right", data)

    def _parse_hand_message(self, msg: Dict[str, Any]) -> HandData:
        """
        Parse ROS message to HandData.
        将 ROS 消息解析为 HandData。

        Expected format: Float32MultiArray with data:
        [thumb, index, middle, ring, pinky, wrist_roll, wrist_pitch, wrist_yaw, x, y, z]
        """
        data = HandData(timestamp=time.time())

        raw_data = msg.get('data', [])
        if len(raw_data) >= 5:
            data.thumb = raw_data[0]
            data.index = raw_data[1]
            data.middle = raw_data[2]
            data.ring = raw_data[3]
            data.pinky = raw_data[4]

        if len(raw_data) >= 8:
            data.wrist_roll = raw_data[5]
            data.wrist_pitch = raw_data[6]
            data.wrist_yaw = raw_data[7]

        if len(raw_data) >= 11:
            data.position_x = raw_data[8]
            data.position_y = raw_data[9]
            data.position_z = raw_data[10]

        data.raw_joints = list(raw_data)
        return data

    def _apply_calibration(self, data: HandData, side: str) -> HandData:
        """Apply calibration offset / 应用校准偏移"""
        offset = self._calibration.left_offset if side == "left" else self._calibration.right_offset
        scale = self._calibration.left_scale if side == "left" else self._calibration.right_scale

        # Apply offset and scale to fingers
        finger_scale = scale.get("fingers", 1.0)
        data.thumb = max(0, min(1, (data.thumb - offset.thumb) * finger_scale))
        data.index = max(0, min(1, (data.index - offset.index) * finger_scale))
        data.middle = max(0, min(1, (data.middle - offset.middle) * finger_scale))
        data.ring = max(0, min(1, (data.ring - offset.ring) * finger_scale))
        data.pinky = max(0, min(1, (data.pinky - offset.pinky) * finger_scale))

        return data

    def _apply_smoothing(self, data: HandData, side: str) -> HandData:
        """Apply exponential smoothing / 应用指数平滑"""
        if self._smoothing_factor <= 0:
            return data

        buffer = self._left_buffer if side == "left" else self._right_buffer

        if buffer is None:
            if side == "left":
                self._left_buffer = data
            else:
                self._right_buffer = data
            return data

        alpha = 1 - self._smoothing_factor

        # Smooth finger values
        data.thumb = alpha * data.thumb + self._smoothing_factor * buffer.thumb
        data.index = alpha * data.index + self._smoothing_factor * buffer.index
        data.middle = alpha * data.middle + self._smoothing_factor * buffer.middle
        data.ring = alpha * data.ring + self._smoothing_factor * buffer.ring
        data.pinky = alpha * data.pinky + self._smoothing_factor * buffer.pinky

        # Update buffer
        if side == "left":
            self._left_buffer = data
        else:
            self._right_buffer = data

        return data

    def _notify_data_callbacks(self, side: str, data: HandData):
        """Notify data callbacks / 通知数据回调"""
        for callback in self._data_callbacks:
            try:
                callback(side, data)
            except Exception as e:
                logger.warning(f"Data callback error: {e}")

    def start_calibration(self) -> bool:
        """
        Start calibration sequence.
        开始校准序列。

        Records current hand position as neutral/open position.
        """
        if self._state != GlovesState.CONNECTED:
            return False

        self._set_state(GlovesState.CALIBRATING)

        with self._lock:
            # Store current positions as calibration offset
            self._calibration.left_offset = HandData(
                thumb=self._left_data.thumb,
                index=self._left_data.index,
                middle=self._left_data.middle,
                ring=self._left_data.ring,
                pinky=self._left_data.pinky,
            )
            self._calibration.right_offset = HandData(
                thumb=self._right_data.thumb,
                index=self._right_data.index,
                middle=self._right_data.middle,
                ring=self._right_data.ring,
                pinky=self._right_data.pinky,
            )

        self._set_state(GlovesState.ACTIVE)
        logger.info("Gloves calibration complete")
        return True

    def get_calibration(self) -> CalibrationData:
        """Get current calibration / 获取当前校准"""
        return self._calibration

    def set_calibration(self, calibration: CalibrationData):
        """Set calibration data / 设置校准数据"""
        self._calibration = calibration
