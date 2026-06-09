"""
Touch Sensor Module
触觉传感器模块

Handles touch matrix data parsing and processing for LinkerHand.
处理 LinkerHand 触觉矩阵数据的解析和处理。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time


@dataclass
class TouchData:
    """Touch sensor data container / 触觉传感器数据容器"""
    timestamp: float = field(default_factory=time.time)
    thumb: Optional[List[int]] = None
    index: Optional[List[int]] = None
    middle: Optional[List[int]] = None
    ring: Optional[List[int]] = None
    little: Optional[List[int]] = None

    def get_max_values(self) -> Dict[str, int]:
        """Get maximum force value for each finger / 获取每个手指的最大力值"""
        result = {}
        for name, data in [
            ("thumb", self.thumb),
            ("index", self.index),
            ("middle", self.middle),
            ("ring", self.ring),
            ("little", self.little)
        ]:
            if data and len(data) > 0:
                valid = [v for v in data if isinstance(v, (int, float)) and v >= 0]
                result[name] = int(max(valid)) if valid else 0
            else:
                result[name] = 0
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary / 转换为字典"""
        return {
            "timestamp": self.timestamp,
            "thumb": self.thumb,
            "index": self.index,
            "middle": self.middle,
            "ring": self.ring,
            "little": self.little
        }


class TouchSensor:
    """
    Touch sensor data handler for LinkerHand.
    LinkerHand 触觉传感器数据处理器。

    Handles matrix data parsing, threshold detection, and normalization.
    处理矩阵数据解析、阈值检测和归一化。
    """

    # Standard matrix dimensions
    MATRIX_ROWS = 12
    MATRIX_COLS = 6
    MATRIX_SIZE = MATRIX_ROWS * MATRIX_COLS

    # Finger names mapping
    FINGER_KEYS = ["thumb", "index", "middle", "ring", "little"]

    def __init__(self, threshold: int = 50):
        """
        Initialize touch sensor handler.
        初始化触觉传感器处理器。

        Args:
            threshold: Default force threshold for touch detection
        """
        self._threshold = threshold
        self._last_data: Optional[TouchData] = None
        self._calibration_offset: Dict[str, List[int]] = {}

    @property
    def threshold(self) -> int:
        """Get current threshold / 获取当前阈值"""
        return self._threshold

    @threshold.setter
    def threshold(self, value: int):
        """Set threshold (0-255) / 设置阈值"""
        self._threshold = max(0, min(255, value))

    @property
    def last_data(self) -> Optional[TouchData]:
        """Get last touch data / 获取最后的触觉数据"""
        return self._last_data

    def parse_matrix_data(self, raw_data: Any) -> Optional[List[int]]:
        """
        Parse raw matrix data into flat list.
        将原始矩阵数据解析为扁平列表。

        Args:
            raw_data: Raw data from sensor (numpy array, list, etc.)

        Returns:
            Flat list of integers, or None if parsing fails
        """
        if raw_data is None:
            return None

        try:
            # Handle numpy arrays
            if hasattr(raw_data, 'flatten'):
                return [int(v) for v in raw_data.flatten().tolist()]

            # Handle nested lists
            if hasattr(raw_data, 'tolist'):
                data = raw_data.tolist()
            else:
                data = raw_data

            # Flatten if nested
            result = []
            if isinstance(data, (list, tuple)):
                for item in data:
                    if isinstance(item, (list, tuple)):
                        result.extend([int(v) for v in item])
                    else:
                        result.append(int(item))
                return result

            return None

        except Exception:
            return None

    def update_from_api(self, hand_api) -> Optional[TouchData]:
        """
        Update touch data from LinkerHand API.
        从 LinkerHand API 更新触觉数据。

        Args:
            hand_api: LinkerHandApi instance

        Returns:
            TouchData if successful, None otherwise
        """
        if not hand_api:
            return None

        try:
            data = TouchData()

            # Get data for each finger
            data.thumb = self.parse_matrix_data(hand_api.get_thumb_matrix_touch())
            data.index = self.parse_matrix_data(hand_api.get_index_matrix_touch())
            data.middle = self.parse_matrix_data(hand_api.get_middle_matrix_touch())
            data.ring = self.parse_matrix_data(hand_api.get_ring_matrix_touch())
            data.little = self.parse_matrix_data(hand_api.get_little_matrix_touch())

            self._last_data = data
            return data

        except Exception:
            return None

    def get_max_force(self, finger: str) -> int:
        """
        Get maximum force value for a specific finger.
        获取特定手指的最大力值。

        Args:
            finger: Finger name ("thumb", "index", "middle", "ring", "little")

        Returns:
            Maximum force value (0-255)
        """
        if not self._last_data:
            return 0

        data = getattr(self._last_data, finger, None)
        if not data:
            return 0

        valid = [v for v in data if isinstance(v, (int, float)) and v >= 0]
        return int(max(valid)) if valid else 0

    def get_all_max_forces(self) -> Dict[str, int]:
        """
        Get maximum force values for all fingers.
        获取所有手指的最大力值。

        Returns:
            Dictionary mapping finger names to max force values
        """
        if self._last_data:
            return self._last_data.get_max_values()
        return {f: 0 for f in self.FINGER_KEYS}

    def is_touching(self, finger: str) -> bool:
        """
        Check if a finger is touching (above threshold).
        检查手指是否接触（超过阈值）。

        Args:
            finger: Finger name

        Returns:
            True if touching, False otherwise
        """
        return self.get_max_force(finger) >= self._threshold

    def get_touching_fingers(self) -> List[str]:
        """
        Get list of fingers currently touching.
        获取当前接触的手指列表。

        Returns:
            List of finger names that are touching
        """
        return [f for f in self.FINGER_KEYS if self.is_touching(f)]

    def calibrate(self, hand_api) -> bool:
        """
        Calibrate touch sensors (store baseline values).
        校准触觉传感器（存储基线值）。

        Args:
            hand_api: LinkerHandApi instance

        Returns:
            True if calibration successful
        """
        data = self.update_from_api(hand_api)
        if not data:
            return False

        # Store current values as calibration offset
        for finger in self.FINGER_KEYS:
            finger_data = getattr(data, finger, None)
            if finger_data:
                self._calibration_offset[finger] = list(finger_data)

        return True

    def get_calibrated_data(self) -> Optional[TouchData]:
        """
        Get touch data with calibration offset applied.
        获取应用校准偏移后的触觉数据。

        Returns:
            Calibrated TouchData or None
        """
        if not self._last_data:
            return None

        calibrated = TouchData(timestamp=self._last_data.timestamp)

        for finger in self.FINGER_KEYS:
            raw_data = getattr(self._last_data, finger, None)
            if raw_data and finger in self._calibration_offset:
                offset = self._calibration_offset[finger]
                calibrated_values = [
                    max(0, raw_data[i] - offset[i]) if i < len(offset) else raw_data[i]
                    for i in range(len(raw_data))
                ]
                setattr(calibrated, finger, calibrated_values)
            else:
                setattr(calibrated, finger, raw_data)

        return calibrated

    def normalize_data(self, data: Optional[List[int]], max_value: int = 255) -> Optional[List[float]]:
        """
        Normalize touch data to 0-1 range.
        将触觉数据归一化到 0-1 范围。

        Args:
            data: Raw touch data
            max_value: Maximum expected value

        Returns:
            Normalized data or None
        """
        if not data:
            return None

        return [max(0.0, min(1.0, v / max_value)) for v in data]
