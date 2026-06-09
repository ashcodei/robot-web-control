"""
Linker Hand Controller Module
L6机械手控制器模块

Controls the L6 Linker Hand via CAN bus.
通过CAN总线控制L6机械手。
"""

import threading
import time
from typing import Dict, Any, Optional, List
from enum import Enum

from hardware.base_hardware import BaseHardwareController, HardwareState
from config.settings import get_settings
from app_core.logger import get_logger
from app_core.remote_control import remote_callable

logger = get_logger(__name__)


class HandSide(Enum):
    """Hand side enumeration / 手侧枚举"""
    LEFT = "left"
    RIGHT = "right"


class HandGesture(Enum):
    """Predefined hand gestures / 预定义手势"""
    OPEN = "open"
    CLOSE = "close"
    PINCH = "pinch"
    POINT = "point"
    FIST = "fist"
    PEACE = "peace"


class LinkerHandController(BaseHardwareController):
    """
    L6 Linker Hand controller.
    L6机械手控制器。

    Controls both left and right hands via CAN bus.
    通过CAN总线控制左右手。
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize linker hand controller.

        Args:
            config: Configuration dictionary (optional)
        """
        super().__init__("linker_hand", config)

        settings = get_settings()
        self._can_interface = config.get('can_interface') if config else settings.linker_hand.can_interface
        self._baudrate = config.get('baudrate') if config else settings.linker_hand.baudrate
        self._left_hand_id = config.get('left_hand_id') if config else settings.linker_hand.left_hand_id
        self._right_hand_id = config.get('right_hand_id') if config else settings.linker_hand.right_hand_id

        self._left_hand = None
        self._right_hand = None
        self._left_finger_positions: List[float] = [0.0] * 6
        self._right_finger_positions: List[float] = [0.0] * 6
        self._left_hand_state: float = 0.0   # hysteresis state: 0.0=open, 1.0=grasping
        self._right_hand_state: float = 0.0
        self._lock = threading.Lock()

        # Try to import LinkerHand SDK
        self._sdk_available = False
        try:
            import os as _os, sys as _sys
            _sdk_path = _os.path.abspath(
                _os.path.join(_os.path.dirname(__file__), '..', '..', 'libs', 'linkerhand-python-sdk-main')
            )
            if _os.path.exists(_sdk_path) and _sdk_path not in _sys.path:
                _sys.path.insert(0, _sdk_path)
            from LinkerHand.linker_hand_api import LinkerHandApi as _LinkerHandApi
            self._LinkerHandApi = _LinkerHandApi
            self._sdk_available = True
        except ImportError:
            logger.warning("LinkerHand SDK not installed, running in simulation mode")

    def connect(self) -> bool:
        """Connect to linker hands / 连接机械手"""
        self.state = HardwareState.CONNECTING

        if not self._sdk_available:
            logger.warning("Linker hand: LinkerHand SDK not installed, cannot connect (simulation mode)")
            self.state = HardwareState.DISCONNECTED
            return False

        try:
            # Create LinkerHand API instances using SDK imported in __init__
            self._left_hand = self._LinkerHandApi(
                hand_type="left",
                hand_joint="L6",
                can=self._can_interface,
            )
            self._right_hand = self._LinkerHandApi(
                hand_type="right",
                hand_joint="L6",
                can=self._can_interface,
            )

            logger.info(f"Linker hands connected on {self._can_interface}")
            self.state = HardwareState.CONNECTED
            return True

        except SystemExit as e:
            self._set_error(f"LinkerHand SDK exited (CAN interface not ready?): {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to connect linker hands: {e}")
            self._set_error(str(e))
            return False

    def disconnect(self) -> bool:
        """Disconnect from linker hands / 断开机械手连接"""
        if self._left_hand:
            try:
                self._left_hand.disconnect()
            except Exception:
                pass
            self._left_hand = None

        if self._right_hand:
            try:
                self._right_hand.disconnect()
            except Exception:
                pass
            self._right_hand = None

        self.state = HardwareState.DISCONNECTED
        logger.info("Linker hands disconnected")
        return True

    def connect_hand(self, side: str) -> bool:
        """Connect a single hand (left or right) / 连接单只机械手"""
        if not self._sdk_available:
            logger.warning("Linker hand: SDK not installed, cannot connect")
            return False

        try:
            hand = self._LinkerHandApi(
                hand_type=side,
                hand_joint="L6",
                can=self._can_interface,
            )
            if side == "left":
                self._left_hand = hand
            else:
                self._right_hand = hand

            logger.info(f"Linker {side} hand connected on {self._can_interface}")
            # Mark connected if at least one hand is up
            if self._left_hand or self._right_hand:
                self.state = HardwareState.CONNECTED
            return True

        except SystemExit as e:
            logger.error(f"LinkerHand SDK exited for {side} hand (CAN not ready?): {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to connect {side} linker hand: {e}")
            return False

    def disconnect_hand(self, side: str) -> bool:
        """Disconnect a single hand / 断开单只机械手"""
        hand = self._left_hand if side == "left" else self._right_hand
        if hand:
            try:
                hand.disconnect()
            except Exception:
                pass
        if side == "left":
            self._left_hand = None
        else:
            self._right_hand = None

        # If neither hand is connected, mark disconnected
        if not self._left_hand and not self._right_hand:
            self.state = HardwareState.DISCONNECTED
        logger.info(f"Linker {side} hand disconnected")
        return True

    def is_hand_connected(self, side: str) -> bool:
        """Check if a specific hand is connected."""
        hand = self._left_hand if side == "left" else self._right_hand
        return hand is not None

    def start(self) -> bool:
        """Start hands / 启动机械手"""
        if self.state != HardwareState.CONNECTED:
            return False
        self.state = HardwareState.RUNNING
        return True

    def stop(self) -> bool:
        """Stop hands / 停止机械手"""
        self.state = HardwareState.CONNECTED
        return True

    def pause(self) -> bool:
        """Pause hands / 暂停机械手"""
        self.state = HardwareState.PAUSED
        return True

    def resume(self) -> bool:
        """Resume hands / 恢复机械手"""
        self.state = HardwareState.RUNNING
        return True

    @remote_callable(
        name="急停",
        category="linker_hand",
        description="Emergency stop linker hands",
        description_zh="机械手紧急停止",
        is_emergency=True
    )
    def emergency_stop(self) -> bool:
        """Emergency stop hands / 机械手紧急停止"""
        self.state = HardwareState.EMERGENCY_STOP
        logger.warning("Linker hand emergency stop executed")
        return True

    def get_status(self) -> Dict[str, Any]:
        """Get hands status / 获取机械手状态. Safe to call; returns minimal dict on error."""
        try:
            state_val = self._state.value if self._state else "unknown"
        except Exception:
            state_val = "unknown"
        try:
            return {
                "name": getattr(self, "_name", "linker_hand"),
                "state": state_val,
                "left_finger_positions": list(self._left_finger_positions) if self._left_finger_positions else [0.0] * 6,
                "right_finger_positions": list(self._right_finger_positions) if self._right_finger_positions else [0.0] * 6,
                "can_interface": getattr(self, "_can_interface", "N/A"),
            }
        except Exception as e:
            logger.debug("Linker hand get_status: %s", e)
            return {"name": "linker_hand", "state": "unknown", "can_interface": "N/A"}

    def get_finger_positions_real(self, side: str = "left") -> Optional[List[float]]:
        """
        Read actual finger positions from SDK (CAN feedback).
        从SDK读取手指的实际位置（CAN反馈）。

        Args:
            side: "left" or "right"

        Returns:
            List of 6 finger positions (0-255), or None if no successful hardware read
            (so UI does not overwrite sliders with fallback zeros).
        """
        hand = self._left_hand if side == "left" else self._right_hand
        if hand:
            try:
                state = hand.get_state()
                if isinstance(state, (list, tuple)) and len(state) >= 6:
                    return [float(x) for x in state[:6]]
            except Exception as e:
                logger.debug(f"Read finger positions failed ({side}): {e}")
        return None

    def get_touch_type(self, side: str = "left") -> Optional[int]:
        """Return the hand's tactile capability: 2=matrix, 1=basic force, -1=none.

        Returns None if that hand is not connected or the query fails.
        返回触觉能力：2=矩阵, 1=基础力, -1=无；未连接或查询失败返回 None。
        """
        hand = self._left_hand if side == "left" else self._right_hand
        if not hand:
            return None
        try:
            return int(hand.get_touch_type())
        except Exception as e:
            logger.debug(f"get_touch_type failed ({side}): {e}")
            return None

    def get_touch_matrices(self, side: str = "left") -> Optional[Dict[str, List[int]]]:
        """Read the five per-finger tactile matrices from the connected hand.

        Returns {finger: flat list of 72 ints (0-255)} for thumb/index/middle/
        ring/little, or None if the hand is not connected or the read fails.
        读取五个手指的触觉矩阵；未连接或读取失败返回 None。
        """
        hand = self._left_hand if side == "left" else self._right_hand
        if not hand:
            return None
        readers = {
            "thumb": hand.get_thumb_matrix_touch,
            "index": hand.get_index_matrix_touch,
            "middle": hand.get_middle_matrix_touch,
            "ring": hand.get_ring_matrix_touch,
            "little": hand.get_little_matrix_touch,
        }
        try:
            return {finger: self._flatten_matrix(reader())
                    for finger, reader in readers.items()}
        except Exception as e:
            logger.debug(f"get_touch_matrices failed ({side}): {e}")
            return None

    @staticmethod
    def _flatten_matrix(raw) -> List[int]:
        """Flatten a finger touch matrix (numpy array or nested list) to a flat int list."""
        if raw is None:
            return []
        try:
            if hasattr(raw, "flatten"):
                return [int(v) for v in raw.flatten().tolist()]
            flat: List[int] = []
            for item in raw:
                if isinstance(item, (list, tuple)) or hasattr(item, "__iter__"):
                    flat.extend(int(v) for v in item)
                else:
                    flat.append(int(item))
            return flat
        except Exception:
            return []

    def get_hand_open_close(self, side: str = "left") -> float:
        """
        Determine hand open/close state with hysteresis.
        通过滞回判断手的张开/闭合状态。

        Finger values: 0=fully closed, 255=fully open.
        - Average > 230 → 0.0 (open)
        - Average < 200 → 1.0 (grasping)
        - 200~230 → keep previous state (hysteresis)

        Args:
            side: "left" or "right"

        Returns:
            0.0 (open) or 1.0 (grasping)
        """
        fingers = self.get_finger_positions_real(side)
        if fingers is None:
            fingers = self._left_finger_positions if side == "left" else self._right_finger_positions
        avg = sum(fingers) / len(fingers) if fingers else 255.0

        prev = self._left_hand_state if side == "left" else self._right_hand_state

        if avg > 230:
            result = 0.0  # open
        elif avg < 200:
            result = 1.0  # grasping
        else:
            result = prev  # hysteresis: keep previous

        if side == "left":
            self._left_hand_state = result
        else:
            self._right_hand_state = result

        return result

    def is_ready(self) -> bool:
        """Check if hands are ready / 检查机械手是否就绪"""
        return self.state in [HardwareState.CONNECTED, HardwareState.RUNNING]

    @remote_callable(
        name="左手手势",
        category="linker_hand",
        description="Set left hand gesture",
        description_zh="设置左手手势"
    )
    def set_left_gesture(self, gesture: str) -> bool:
        """Set left hand gesture / 设置左手手势"""
        return self._set_gesture(HandSide.LEFT, gesture)

    @remote_callable(
        name="右手手势",
        category="linker_hand",
        description="Set right hand gesture",
        description_zh="设置右手手势"
    )
    def set_right_gesture(self, gesture: str) -> bool:
        """Set right hand gesture / 设置右手手势"""
        return self._set_gesture(HandSide.RIGHT, gesture)

    def _set_gesture(self, side: HandSide, gesture: str) -> bool:
        """Set hand gesture / 设置手势"""
        # L6: 255 = open, 0 = closed (same as dexhand). SDK has no set_gesture; use finger_move.
        gesture_positions = {
            "open": [255, 128, 255, 255, 255, 255],
            "close": [0, 128, 0, 0, 0, 0],
            "pinch": [200, 128, 200, 0, 0, 0],
            "point": [200, 128, 0, 200, 200, 200],
            "fist": [0, 128, 0, 0, 0, 0],
        }
        positions = gesture_positions.get(gesture.lower())
        if positions and self.set_finger_positions(side, positions):
            logger.info(f"Set {side.value} hand gesture: {gesture}")
            return True
        return False

    def set_finger_positions(self, side: HandSide,
                             positions: List[float]) -> bool:
        """
        Set finger positions (0-255). Uses SDK finger_move for L6.
        设置手指位置（0-255）。L6 使用 SDK finger_move。
        """
        if len(positions) != 6:
            logger.error("Finger positions must have 6 values")
            return False

        hand = self._left_hand if side == HandSide.LEFT else self._right_hand
        pos_list = [int(round(float(p))) for p in positions]

        if hand:
            try:
                # LinkerHandApi uses finger_move(pose) for L6 (6 values 0-255)
                hand.finger_move(pos_list)
                if side == HandSide.LEFT:
                    self._left_finger_positions = list(positions)
                else:
                    self._right_finger_positions = list(positions)
                return True
            except Exception as e:
                logger.error(f"Set finger positions failed: {e}")
                return False
        else:
            if side == HandSide.LEFT:
                self._left_finger_positions = list(positions)
            else:
                self._right_finger_positions = list(positions)
            return True
